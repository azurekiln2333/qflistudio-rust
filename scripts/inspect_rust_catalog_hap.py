#!/usr/bin/env python3
"""Verify the final isolated Rust audit HAP bytes; this does not run a device.

Besides bundle identity, offline permissions, generated catalogs, guest data and
manifest-covered native checksums, this inspection proves the packaged adapter
actually exports the runtime ABI this product calls. A library whose bytes match
its manifest can still be stale (built before the project constructor, the
analysis extension or the debugger extension existed), so byte identity alone
cannot gate an audit package.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import struct
import sys
import zipfile

from generate_rust_content import ROOT, load_topics
from generate_rust_native_catalog import verify_native_catalog, verify_paired_catalogs
from miri_build_support import (COMPILER_BOUNDARY_KIND, COMPILER_BOUNDARY_PATCH_SHA256,
                               GUEST_TARGET, RUST_COMMIT, RUST_VERSION,
                               compiler_boundary_patch, compiler_patch_hunks, sha256)
from package_miri_runtime import safe_relative

ASSETS = "resources/rawfile/flutter_assets/"
BUNDLE = "com.azurekiln.qfli.rust.audit"
TARGETS = {
    "ohos-x64": ("x86_64", "x86_64-unknown-linux-ohos", 62),
    "ohos-arm64": ("arm64-v8a", "aarch64-unknown-linux-ohos", 183),
}

# --------------------------------------------------------------------------
# Runtime ABI surface.
#
# The names below are the exact prototypes in the shipped headers; the tiers
# mirror how the header documents them and how lib/ binds them.
#
#   qfli_miri.h (ABI 1)
#     run surface, always looked up by NativeMiriProgramRunner      (9 names)
#     analysis-only extension, optional in the header, required by
#       the unexecuted-source diagnostics checks                    (2 names)
#   qfli_debug.h (optional extension, separate symbols)
#     interactive debugger                                         (16 names)
#
# An audit package must export all three tiers: the isolated entry runs six
# native provider checks that compile unsaved buffers, launch a real debugger
# session and step through it. Exporting only the ABI-1 run surface would make
# every one of those checks report "unavailable", which must fail the archive
# inspection instead of passing quietly.
#
# `declared_symbols()` re-derives these tiers from header text, so the Python
# suites can prove the constants below still match native/miri_adapter/*.h.
# --------------------------------------------------------------------------
RUNTIME_SYMBOLS = (
    "qfli_miri_abi_version",
    "qfli_miri_create",
    "qfli_miri_create_with_backend",
    "qfli_miri_create_with_project",
    "qfli_miri_run",
    "qfli_miri_cancel",
    "qfli_miri_copy_output",
    "qfli_miri_result",
    "qfli_miri_destroy",
)
ANALYSIS_SYMBOLS = (
    "qfli_miri_create_analysis",
    "qfli_miri_analyze",
)
DEBUGGER_SYMBOLS = (
    "qfli_miri_debug_capabilities",
    "qfli_miri_debug_create",
    "qfli_miri_debug_start",
    "qfli_miri_debug_resume",
    "qfli_miri_debug_resume_at",
    "qfli_miri_debug_pause",
    "qfli_miri_debug_pause_info",
    "qfli_miri_debug_cancel",
    "qfli_miri_debug_wait",
    "qfli_miri_debug_status",
    "qfli_miri_debug_destroy",
    "qfli_miri_debug_frame_count",
    "qfli_miri_debug_frame",
    "qfli_miri_debug_locals",
    "qfli_miri_debug_copy_output",
    "qfli_miri_debug_copy_output_channel",
)
REQUIRED_RUNTIME_SYMBOLS = RUNTIME_SYMBOLS + ANALYSIS_SYMBOLS + DEBUGGER_SYMBOLS

# Native members that are shipped next to the runtime but are not covered by the
# runtime manifest: the Flutter engine, the AOT application snapshot and the
# OHOS native ABI probe. The probe is built by scripts/build_ohos_probe.ps1 into
# ohos/entry/libs/<abi> and opened by lib/ohos_native_probe.dart; it is a
# supported member, so it is allow-listed rather than treated as an intruder.
ADAPTER_LIBRARY = "libqfli_miri.so"
PROBE_LIBRARY = "libqfli_native_probe.so"
PROBE_SYMBOLS = ("qfli_native_probe",)
APPLICATION_LIBRARIES = frozenset({"libflutter.so", "libapp.so", PROBE_LIBRARY})
REQUIRED_APPLICATION_LIBRARIES = frozenset({"libflutter.so", "libapp.so"})

# ELF constants used by the strict dynamic-symbol reader.
_ELF_HEADER_BYTES = 64
_ELF_SECTION_BYTES = 64
_ELF_SYMBOL_BYTES = 24
_SHT_STRTAB = 3
_SHT_DYNSYM = 11
_SHB_UNDEF = 0
# st_shndx values at or above this point are reserved by the ELF ABI (SHN_ABS,
# SHN_COMMON, SHN_XINDEX and the processor ranges); only lower values are
# ordinary section-table indices that must point at a real section.
_SHN_LORESERVE = 0xFF00
_STB_GLOBAL = 1
# STB_WEAK is a normal loader-visible definition: dlsym resolves weak symbols
# exactly like global ones, so a weak ABI entry still satisfies the contract.
_STB_WEAK = 2
_STB_GNU_UNIQUE = 10
_STT_FUNC = 2
_STT_GNU_IFUNC = 10
# Symbol visibility that the dynamic loader still resolves by name. STV_DEFAULT
# and STV_PROTECTED are both reachable through dlsym/libffi lookup; only
# STV_INTERNAL (1) and STV_HIDDEN (2) are not exported outside the object.
_STV_LOADER_VISIBLE = (0, 3)
# Guards pathological files without bounding legitimate libraries: the adapter
# is ~16 MiB with a few thousand dynamic symbols.
_MAX_ELF_SYMBOLS = 1_000_000
_MAX_SYMBOL_NAME = 512


class ElfExport:
    """One exported dynamic symbol, as the loader would see it."""

    __slots__ = ("binding", "type", "visibility", "section")

    def __init__(self, binding: int, type: int, visibility: int, section: int) -> None:
        self.binding = binding
        self.type = type
        self.visibility = visibility
        self.section = section

    def as_dict(self) -> dict:
        return {"binding": self.binding, "type": self.type,
                "visibility": self.visibility, "section": self.section}

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (f"ElfExport(binding={self.binding}, type={self.type}, "
                f"visibility={self.visibility}, section={self.section})")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def member_hash(archive: zipfile.ZipFile, name: str) -> str:
    with archive.open(name) as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def check_archive_names(names: list[str]) -> None:
    require(len(names) == len(set(names)), "Duplicate ZIP member")
    for name in names:
        require("\\" not in name and not name.startswith("/"), f"Unsafe ZIP member: {name}")
        require(".." not in PurePosixPath(name).parts, f"Escaping ZIP member: {name}")


def declared_symbols(header_text: str) -> tuple[str, ...]:
    """Return the `qfli_miri_*` prototypes declared by one adapter header.

    Comments are stripped and whitespace collapsed first, so multi-line
    declarations are found. Non-function mentions inside comments therefore
    cannot inflate the result.
    """
    text = re.sub(r"/\*.*?\*/", " ", header_text, flags=re.S)
    text = re.sub(r"//[^\n]*", " ", text)
    text = re.sub(r"\s+", " ", text)
    found: list[str] = []
    for name in re.findall(r"\b(qfli_miri_[a-z0-9_]+)\s*\(", text):
        if name not in found:
            found.append(name)
    return tuple(found)


def _elf_sections(data: bytes, library: str) -> list[tuple[int, int, int, int, int]]:
    """Return (name_offset, type, offset, size, link) for every ELF64LE section."""
    require(len(data) >= _ELF_HEADER_BYTES, f"Malformed ELF header in {library}: truncated")
    require(data[:4] == b"\x7fELF", f"Malformed ELF header in {library}: bad magic")
    require(data[4] == 2, f"Malformed ELF header in {library}: not a 64-bit ELF")
    require(data[5] == 1, f"Malformed ELF header in {library}: not little-endian")
    shoff, = struct.unpack_from("<Q", data, 40)
    shentsize, shnum, shstrndx = struct.unpack_from("<HHH", data, 58)
    require(shoff != 0 and shnum != 0,
            f"Malformed ELF section table in {library}: absent, symbols unverifiable")
    require(shentsize == _ELF_SECTION_BYTES,
            f"Malformed ELF section table in {library}: entry size {shentsize}")
    require(shstrndx < shnum, f"Malformed ELF section table in {library}: bad string index")
    end = shoff + shnum * _ELF_SECTION_BYTES
    require(end <= len(data), f"Malformed ELF section table in {library}: truncated")
    sections = []
    for index in range(shnum):
        fields = struct.unpack_from("<IIQQQQIIQQ", data, shoff + index * _ELF_SECTION_BYTES)
        name, sh_type, offset, size, link = (fields[0], fields[1], fields[4], fields[5],
                                             fields[6])
        require(offset + size <= len(data) or sh_type == 8,
                f"Malformed ELF section table in {library}: section {index} escapes the file")
        sections.append((name, sh_type, offset, size, link))
    # The section-name string table must itself be a valid in-file section.
    strtab = sections[shstrndx]
    require(strtab[1] == _SHT_STRTAB,
            f"Malformed ELF section table in {library}: section names are not a string table")
    return sections


def _read_c_string(data: bytes, base: int, size: int, offset: int, library: str) -> str:
    require(offset < size, f"Malformed ELF dynamic symbol table in {library}: name offset")
    start = base + offset
    stop = base + size
    require(stop <= len(data), f"Malformed ELF dynamic symbol table in {library}: name escapes")
    terminator = data.find(b"\x00", start, stop)
    require(terminator != -1,
            f"Malformed ELF dynamic symbol table in {library}: unterminated name")
    require(terminator - start <= _MAX_SYMBOL_NAME,
            f"Malformed ELF dynamic symbol table in {library}: overlong name")
    try:
        return data[start:terminator].decode("ascii")
    except UnicodeDecodeError as error:
        raise ValueError(
            f"Malformed ELF dynamic symbol table in {library}: non-ASCII symbol name"
        ) from error


def read_elf_exports(data: bytes, library: str = "<memory>") -> dict[str, ElfExport]:
    """Return the dynamic symbols an ELF64LE shared object actually exports.

    A name is kept only when the loader would resolve it as a callable export:
    defined (not SHN_UNDEF), global, weak or uniquely bound, loader-visible
    (default or protected, not internal/hidden) and of function type. Local,
    hidden, internal and undefined entries are therefore rejected instead of
    being counted as a satisfied ABI.

    Every definition whose ``st_shndx`` is not reserved must name a section that
    exists in the section table; a nonreserved index past the table is corrupt
    input rather than a definition.
    """
    sections = _elf_sections(data, library)
    exports: dict[str, ElfExport] = {}
    seen_dynsym = 0
    for name_offset, sh_type, offset, size, link in sections:
        if sh_type != _SHT_DYNSYM:
            continue
        seen_dynsym += 1
        require(size % _ELF_SYMBOL_BYTES == 0,
                f"Malformed ELF dynamic symbol table in {library}: unaligned size")
        count = size // _ELF_SYMBOL_BYTES
        require(count <= _MAX_ELF_SYMBOLS,
                f"Malformed ELF dynamic symbol table in {library}: too many symbols")
        require(link < len(sections) and sections[link][1] == _SHT_STRTAB,
                f"Malformed ELF dynamic symbol table in {library}: no string table")
        _, _, str_offset, str_size, _ = sections[link]
        for index in range(count):
            entry = offset + index * _ELF_SYMBOL_BYTES
            st_name, st_info, st_other, st_shndx = struct.unpack_from("<IBBH", data, entry)
            if st_name == 0:
                continue
            symbol = _read_c_string(data, str_offset, str_size, st_name, library)
            # A nonreserved index must reference a real section. Reserved values
            # (>= SHN_LORESERVE) are not section indices, so they are left alone.
            if st_shndx != _SHB_UNDEF and st_shndx < _SHN_LORESERVE:
                require(st_shndx < len(sections),
                        f"Malformed ELF dynamic symbol table in {library}: symbol "
                        f"{symbol} names section index {st_shndx} outside the table")
            binding = st_info >> 4
            symbol_type = st_info & 0x0F
            visibility = st_other & 0x03
            if (st_shndx == _SHB_UNDEF
                    or binding not in (_STB_GLOBAL, _STB_WEAK, _STB_GNU_UNIQUE)
                    or visibility not in _STV_LOADER_VISIBLE
                    or symbol_type not in (_STT_FUNC, _STT_GNU_IFUNC)):
                continue
            exports.setdefault(symbol, ElfExport(binding, symbol_type, visibility, st_shndx))
    require(seen_dynsym != 0,
            f"Malformed ELF dynamic symbol table in {library}: no .dynsym section")
    return exports


def verify_exported_symbols(data: bytes, library: str, required: tuple[str, ...]) -> dict:
    """Prove `library` exports every required name; return the observed surface."""
    exports = read_elf_exports(data, library)
    missing = [name for name in required if name not in exports]
    require(not missing,
            f"Stale Rust runtime ABI in {library}: missing exported {missing}; "
            f"rebuild and repackage the adapter from the current source")
    return {"library": library, "required": len(required),
            "exported": sorted(exports), "sha256": hashlib.sha256(data).hexdigest()}


def verify_native_inventory(declared: set[str], packaged: set[str]) -> dict:
    """Reject native members that are neither manifest-declared nor allow-listed."""
    unexpected = sorted(packaged - declared - APPLICATION_LIBRARIES)
    require(not unexpected,
            f"Unexpected native library in HAP: {unexpected}; add it to the runtime "
            f"manifest or remove it from ohos/entry/libs")
    missing = sorted(REQUIRED_APPLICATION_LIBRARIES - packaged)
    require(not missing, f"Missing release Flutter/native runtime: {missing}")
    return {
        "manifestDeclared": sorted(declared & packaged),
        "applicationLibraries": sorted(packaged & APPLICATION_LIBRARIES),
        "unexpected": [],
    }


_HEX64 = re.compile(r"[0-9a-f]{64}")
_DRIVE = re.compile(r"^[A-Za-z]:")
_ARTIFACT_PATH = "Compiler build record runtime artifact path"
_BOUNDARY_TREES = ("inputTree", "patchedTree")
_REQUIRED_COMPILER_LIBRARIES = ("rustc_driver", "rustc_codegen")


def _require_hex64(value: object, message: str) -> None:
    require(isinstance(value, str) and _HEX64.fullmatch(value) is not None, message)


def _read_record(record, label: str) -> dict:
    """Decode operator-supplied record bytes; never resolve a path from them."""
    require(isinstance(record, (bytes, bytearray)) and len(record) > 0,
            f"Missing {label} bytes")
    try:
        value = json.loads(bytes(record).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Malformed {label}: {error}") from error
    require(isinstance(value, dict), f"Malformed {label}: not a JSON object")
    return value


def verify_compiler_boundary(boundary: object) -> dict:
    """Require the exact reviewed embedded-compiler boundary identity.

    This rejects a stock compiler, a differently patched compiler and a truncated
    boundary record. The expected patched-file paths come from the reviewed patch
    itself, so the check follows the repository contract instead of a copy.
    """
    require(isinstance(boundary, dict),
            "Compiler boundary is missing from the packaged manifest")
    require(boundary.get("kind") == COMPILER_BOUNDARY_KIND,
            "Compiler boundary is not the reviewed embedded compiler")
    require(boundary.get("patchSha256") == COMPILER_BOUNDARY_PATCH_SHA256,
            "Compiler boundary patch differs from the reviewed SHA-256")
    require(boundary.get("sourceCommit") == RUST_COMMIT,
            "Compiler boundary source commit differs from the pinned revision")
    for key in _BOUNDARY_TREES:
        tree = boundary.get(key)
        require(isinstance(tree, dict), f"Compiler boundary lacks {key}")
        _require_hex64(tree.get("sha256"), f"Compiler boundary {key} hash is malformed")
        count = tree.get("fileCount")
        require(isinstance(count, int) and not isinstance(count, bool) and count > 0,
                f"Compiler boundary {key} file count is invalid")
    expected = ["compiler/" + relative
                for relative, _ in compiler_patch_hunks(compiler_boundary_patch())]
    changes = boundary.get("patchedFiles")
    require(isinstance(changes, list) and all(isinstance(row, dict) for row in changes),
            "Compiler boundary lacks the patched source-file hashes")
    require([row.get("path") for row in changes] == expected,
            "Compiler boundary patched file list differs from the reviewed patch")
    for row in changes:
        for key in ("beforeSha256", "afterSha256"):
            _require_hex64(row.get(key),
                           f"Compiler boundary patched hash is malformed for {row.get('path')}")
    return boundary


def _normalized_parts(value: object, message: str) -> list[str]:
    """Split a recorded path into parts, treating both separators the same.

    Windows and POSIX separators are normalized without touching a filesystem.
    Parent references and empty results are rejected, so a record cannot escape
    the root it claims to live under.
    """
    require(isinstance(value, str) and value.strip(), message)
    text = value.strip().replace("\\", "/")
    parts = [part for part in text.split("/") if part not in ("", ".")]
    require(parts and all(part != ".." for part in parts), message)
    return parts


def _relative_artifact_path(value: object) -> str:
    """Return a canonical relative artifact path, rejecting every rooted form.

    Compiler artifacts are recorded relative to their root, so an absolute POSIX
    path, a drive-rooted or drive-relative Windows path and a UNC share are all
    corrupt. They are also ambiguous: dropping the root would make them
    indistinguishable from a genuine relative path. Absolute producer paths in
    ``runtimeSysroot`` and ``compilerLibraries`` are a separate contract and are
    normalized elsewhere.
    """
    require(isinstance(value, str) and value.strip(), f"{_ARTIFACT_PATH} is empty")
    require("\x00" not in value, f"{_ARTIFACT_PATH} contains a NUL byte")
    text = value.strip().replace("\\", "/")
    # A leading slash also covers a UNC share after separator normalization.
    require(not text.startswith("/") and _DRIVE.match(text) is None,
            f"{_ARTIFACT_PATH} is not relative")
    parts = [part for part in text.split("/") if part not in ("", ".")]
    require(parts and all(part != ".." for part in parts),
            f"{_ARTIFACT_PATH} is unsafe")
    return "/".join(parts)


def _runtime_inventory(artifacts: list) -> dict:
    """Map runtime-relative artifact paths to their recorded hashes.

    The compiler record already pins the private runtime libraries. Deriving
    this map makes the adapter's compilerLibraries answerable to the compiler
    record rather than to itself.
    """
    inventory: dict[str, str] = {}
    for row in artifacts:
        if row.get("root") != "runtime":
            continue
        relative = _relative_artifact_path(row.get("path"))
        digest = row["sha256"]
        if relative in inventory:
            require(inventory[relative] == digest,
                    f"Compiler build record conflicts on runtime artifact {relative}")
            continue
        inventory[relative] = digest
    require(inventory, "Compiler build record lists no runtime artifacts")
    return inventory


def verify_compiler_provenance(runtime: dict, compiler_record, adapter_record,
                               adapter_bytes: bytes, native_host: str,
                               packaged_libraries: dict) -> dict:
    """Bind the packaged manifest and packaged bytes to trusted build records.

    No record path is resolved and no compiler sysroot is walked: the chain is
    pure bytes. The manifest hashes select the records, the records must carry
    the reviewed boundary identity, the adapter record must name the exact
    packaged adapter bytes, and its recorded compiler libraries must match the
    libraries actually packaged in the HAP.
    """
    boundary = verify_compiler_boundary(runtime.get("compilerBoundary"))
    compiler = _read_record(compiler_record, "compiler build record")
    adapter = _read_record(adapter_record, "adapter build record")
    compiler_sha = hashlib.sha256(bytes(compiler_record)).hexdigest()
    adapter_sha = hashlib.sha256(bytes(adapter_record)).hexdigest()
    _require_hex64(runtime.get("compilerBuildSha256"),
                   "Manifest compilerBuildSha256 is missing or malformed")
    _require_hex64(runtime.get("adapterBuildSha256"),
                   "Manifest adapterBuildSha256 is missing or malformed")
    require(runtime["compilerBuildSha256"] == compiler_sha,
            "Manifest compiler build hash differs from the supplied compiler record")
    require(runtime["adapterBuildSha256"] == adapter_sha,
            "Manifest adapter build hash differs from the supplied adapter record")
    require(compiler.get("schemaVersion") == 2 and compiler.get("status") == "built",
            "Compiler build record is not a completed pinned build")
    require(compiler.get("rustVersion") == RUST_VERSION
            and compiler.get("rustCommit") == RUST_COMMIT,
            "Compiler build record is not the pinned revision")
    require(compiler.get("nativeHost") == native_host,
            "Compiler build record targets another native host")
    require(verify_compiler_boundary(compiler.get("compilerBoundary")) == boundary,
            "Manifest compiler boundary differs from the compiler build record")
    artifacts = compiler.get("compilerArtifacts")
    require(isinstance(artifacts, list) and artifacts,
            "Compiler build record has no private-library hashes")
    for row in artifacts:
        require(isinstance(row, dict) and row.get("root") in ("compiler", "runtime"),
                "Compiler build record artifact has an invalid root")
        require(isinstance(row.get("path"), str) and row["path"],
                "Compiler build record artifact has no path")
        size = row.get("size")
        require(isinstance(size, int) and not isinstance(size, bool) and size > 0,
                "Compiler build record artifact size is invalid")
        _require_hex64(row.get("sha256"), "Compiler build record artifact hash is malformed")
    runtime_root = compiler.get("runtimeSysroot")
    require(isinstance(runtime_root, str) and runtime_root.strip(),
            "Compiler build record has no runtime sysroot")
    root_parts = _normalized_parts(runtime_root,
                                   "Compiler build record runtime sysroot is unsafe")
    runtime_inventory = _runtime_inventory(artifacts)
    require(adapter.get("schemaVersion") == 1,
            "Adapter build record has an unsupported schema")
    require(adapter.get("rustVersion") == RUST_VERSION
            and adapter.get("rustCommit") == RUST_COMMIT,
            "Adapter build record is not the pinned revision")
    require(adapter.get("nativeHost") == native_host,
            "Adapter build record targets another native host")
    built = adapter.get("adapter")
    require(isinstance(built, dict), "Adapter build record lacks the adapter identity")
    require(built.get("sha256") == hashlib.sha256(adapter_bytes).hexdigest(),
            "Packaged adapter differs from the adapter build record")
    # The nested identity is the same object verify_compiler_build returns:
    # path, sha256 and the boundary. Comparing the whole dict binds the adapter
    # record to the compiler record rather than to a loose boundary copy.
    chain = adapter.get("compilerBuild")
    require(isinstance(chain, dict)
            and set(chain) == {"path", "sha256", "compilerBoundary"},
            "Adapter build record compilerBuild lacks the compiler identity")
    require(isinstance(chain.get("path"), str) and chain["path"],
            "Adapter build record compilerBuild has no recorded path")
    require(chain.get("sha256") == compiler_sha,
            "Adapter build record points at another compiler build")
    require(verify_compiler_boundary(chain.get("compilerBoundary")) == boundary,
            "Adapter build record compilerBuild boundary differs from the compiler record")
    require(verify_compiler_boundary(adapter.get("compilerBoundary")) == boundary,
            "Adapter compiler boundary differs from the packaged manifest")
    libraries = adapter.get("compilerLibraries")
    require(isinstance(libraries, list) and libraries,
            "Adapter build record has no compiler library hashes")
    recorded = {}
    for row in libraries:
        require(isinstance(row, dict), "Adapter build record compiler library is not an object")
        name_parts = _normalized_parts(
            row.get("name"), "Adapter build record compiler library name is unsafe")
        require(len(name_parts) == 1,
                "Adapter build record compiler library name is not a single component")
        name = name_parts[0]
        _require_hex64(row.get("sha256"),
                       "Adapter build record compiler library hash is malformed")
        parts = _normalized_parts(
            row.get("path"), "Adapter build record compiler library path is unsafe")
        require(parts[:len(root_parts)] == root_parts,
                "Adapter build record compiler library lies outside the runtime sysroot: "
                + "/".join(parts))
        relative = "/".join(parts[len(root_parts):])
        require(relative in runtime_inventory,
                "Adapter build record names a runtime library absent from the compiler "
                "artifacts: " + relative)
        require(runtime_inventory[relative] == row["sha256"],
                "Compiler artifacts disagree with the adapter build record on " + relative)
        require(relative.split("/")[-1] == name,
                "Adapter build record library name disagrees with its recorded path: " + name)
        if name in recorded:
            require(recorded[name] == row["sha256"],
                    "Adapter build record conflicts on compiler library " + name)
            continue
        recorded[name] = row["sha256"]
    # Tie the record to the bytes that were actually packaged. A manifest can be
    # regenerated from swapped libraries and still agree with itself, so only the
    # trusted record can detect a replaced compiler.
    for name in sorted(recorded):
        if name in packaged_libraries:
            require(packaged_libraries[name] == recorded[name],
                    "Packaged compiler library differs from the adapter build record: "
                    + name)
    for component in _REQUIRED_COMPILER_LIBRARIES:
        matches = [name for name in recorded
                   if component in name and Path(name).suffix in (".so", ".dylib", ".dll")]
        require(matches, f"Adapter build record lacks a {component} runtime library")
        require(any(name in packaged_libraries for name in matches),
                f"Packaged native libraries lack the recorded {component} runtime library")
    return {"kind": boundary["kind"], "sourceCommit": boundary["sourceCommit"],
            "patchSha256": boundary["patchSha256"], "compilerBuildSha256": compiler_sha,
            "adapterBuildSha256": adapter_sha, "adapterSha256": built["sha256"],
            "compilerArtifacts": len(artifacts), "compilerLibraries": len(recorded),
            "packagedCompilerLibraries": sorted(name for name in recorded
                                                if name in packaged_libraries)}


def inspect(hap: Path, architecture: str, root: Path = ROOT, *, compiler_record,
            adapter_record) -> dict:
    require(compiler_record is not None and adapter_record is not None,
            "Compiler and adapter build records are required to establish provenance")
    abi, host, machine = TARGETS[architecture]
    manifest_name = f"assets/miri/manifest.{architecture}.json"
    manifest_bytes = (root / manifest_name).read_bytes()
    runtime = json.loads(manifest_bytes)
    require(runtime["schemaVersion"] == 1 and runtime["nativeHost"] == host,
            "Wrong runtime manifest architecture/schema")
    require(runtime["rustVersion"] == RUST_VERSION and runtime["rustCommit"] == RUST_COMMIT
            and runtime["guestTarget"] == GUEST_TARGET, "Wrong pinned compiler/guest identity")
    report = {"architecture": architecture, "bundleName": BUNDLE, "deviceExecuted": False,
              "signed": False, "runtimeId": runtime["id"],
              "manifestSha256": hashlib.sha256(manifest_bytes).hexdigest(),
              "artifact": {"path": str(hap.resolve()), "sha256": sha256(hap),
                           "bytes": hap.stat().st_size}}
    with zipfile.ZipFile(hap) as archive:
        names = archive.namelist()
        check_archive_names(names)
        module = json.loads(archive.read("module.json"))
        require(module["app"]["bundleName"] == BUNDLE, "Audit bundle must be isolated from production")
        require(module["module"]["type"] == "entry"
                and module["module"]["mainElement"] == "EntryAbility", "Wrong HAP entrypoint")
        permissions = [item["name"] for item in module["module"].get("requestPermissions", [])]
        require("ohos.permission.INTERNET" not in permissions, "Offline audit requests Internet")
        require(json.loads(archive.read("pack.info"))["summary"]["app"]["bundleName"] == BUNDLE,
                "Pack-info bundle differs")
        require(archive.read(ASSETS + manifest_name) == manifest_bytes, "Stale packaged manifest")
        topics = load_topics(root / "tool/rust_content")
        catalog_bytes = archive.read(ASSETS + "assets/content_rust/native_catalog.json")
        require(catalog_bytes == (root / "assets/content_rust/native_catalog.json").read_bytes(),
                "Stale packaged native catalog")
        catalog = json.loads(catalog_bytes)
        counts = verify_native_catalog(catalog, topics)
        verify_paired_catalogs(root, catalog)
        report["catalog"] = counts
        report["catalogAssets"] = {}
        for name in ("examples", "tutorials", "native_catalog"):
            relative = f"assets/content_rust/{name}.json"
            data = archive.read(ASSETS + relative)
            require(data == (root / relative).read_bytes(), f"Stale packaged content: {relative}")
            report["catalogAssets"][relative] = hashlib.sha256(data).hexdigest()
        for item in runtime["files"]:
            safe_relative(item["path"])
            require(item["asset"] == item["sha256"] + ".bin", "Noncanonical runtime asset")
            member = ASSETS + "assets/miri/" + item["asset"]
            require(archive.getinfo(member).file_size == item["size"]
                    and member_hash(archive, member) == item["sha256"],
                    f"Runtime data differs: {item['path']}")
        report["runtimeFiles"] = len(runtime["files"])
        libraries = {}
        for name in names:
            # Directory entries carry no payload of their own and are legitimate
            # in a ZIP, so they are skipped rather than treated as native data.
            if not name.startswith("libs/") or name.endswith("/"):
                continue
            parts = name.split("/")
            if not name.endswith(".so"):
                # Only shared objects belong in the packaged native tree. Both
                # shipped HAPs and both ohos/entry/libs trees contain nothing
                # else, so any other regular file would otherwise ride along
                # without the manifest, the allow-list or the symbol gate
                # covering it. This applies at every depth under libs/,
                # including a foreign-ABI directory and libs/ itself.
                require(False,
                        f"Unmanifested native payload in HAP: {name}; only .so "
                        f"libraries directly under libs/{abi}/ are allowed")
            require(len(parts) == 3 and parts[1] == abi, f"Wrong native architecture: {name}")
            with archive.open(name) as stream:
                header = stream.read(_ELF_HEADER_BYTES)
            require(len(header) == _ELF_HEADER_BYTES and header[:6] == b"\x7fELF\x02\x01"
                    and struct.unpack_from("<H", header, 18)[0] == machine,
                    f"Wrong ELF architecture: {name}")
            libraries[parts[2]] = member_hash(archive, name)
        declared = set()
        for item in runtime["nativeLibraries"]:
            require(len(safe_relative(item["name"]).parts) == 1, "Unsafe native library name")
            require(item["name"] in libraries,
                    f"Missing manifest-covered native library in HAP: {item['name']}")
            require(libraries[item["name"]] == item["sha256"],
                    f"Final HAP changed manifest-covered native bytes: {item['name']}")
            declared.add(item["name"])
        report["nativeInventory"] = verify_native_inventory(declared, set(libraries))
        # Symbol verification is stronger than byte identity: a manifest can be
        # regenerated from a stale library and still agree with itself.
        adapter = f"libs/{abi}/{ADAPTER_LIBRARY}"
        require(adapter in names, f"Missing release Flutter/native runtime: {ADAPTER_LIBRARY}")
        report["runtimeAbi"] = verify_exported_symbols(
            archive.read(adapter), ADAPTER_LIBRARY, REQUIRED_RUNTIME_SYMBOLS)
        probe = f"libs/{abi}/{PROBE_LIBRARY}"
        report["probeAbi"] = (verify_exported_symbols(archive.read(probe), PROBE_LIBRARY,
                                                     PROBE_SYMBOLS)
                              if probe in names else {"library": PROBE_LIBRARY,
                                                      "packaged": False})
        report["nativeLibraries"] = libraries
        report["permissions"] = permissions
        # Provenance runs last so that an earlier failure keeps its own message:
        # a stale adapter must still report its missing symbols, not the record
        # mismatch that a regenerated package would also have.
        report["compilerProvenance"] = verify_compiler_provenance(
            runtime, compiler_record, adapter_record, archive.read(adapter), host,
            libraries)
    return report


def verify_build_metadata(metadata: dict, report: dict) -> str:
    """Bind the audit build metadata to the exact consumed build records.

    The caller writes the metadata from its pre-build inputs, so it names the
    records it handed over. Comparing those names with the hashes of the bytes
    the inspector actually read closes a record swap during the HAP build, which
    the packaged manifest alone cannot see.
    """
    require(isinstance(metadata, dict), "Build metadata is not a JSON object")
    require(metadata.get("sha256") == report["artifact"]["sha256"],
            "Build HAP hash differs")
    require(metadata.get("bundleName") == BUNDLE
            and metadata.get("architecture") == report["architecture"]
            and metadata.get("target") == "lib/main_catalog_audit.dart"
            and metadata.get("signed") is False, "Build metadata differs")
    provenance = report["compilerProvenance"]
    for field, recorded in (("compilerRecordSha256", provenance["compilerBuildSha256"]),
                            ("adapterRecordSha256", provenance["adapterBuildSha256"])):
        value = metadata.get(field)
        require(isinstance(value, str) and _HEX64.fullmatch(value) is not None,
                f"Build metadata lacks a well-formed {field}")
        require(value == recorded,
                f"Build metadata {field} differs from the consumed build record")
    build_id = metadata.get("buildId")
    require(isinstance(build_id, str) and build_id, "Build metadata lacks a build id")
    return build_id


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hap", type=Path, required=True)
    parser.add_argument("--architecture", choices=TARGETS, required=True)
    parser.add_argument("--compiler-record", type=Path, required=True,
                        help="trusted patched compiler build record (JSON bytes)")
    parser.add_argument("--adapter-record", type=Path, required=True,
                        help="trusted adapter build record (JSON bytes)")
    parser.add_argument("--metadata", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = {"status": "FAIL", "checkedAt": datetime.now(timezone.utc).isoformat(),
              "deviceExecuted": False}
    try:
        for label, path in (("compiler build record", args.compiler_record),
                            ("adapter build record", args.adapter_record)):
            require(path.is_file(), f"Missing {label}: {path}")
        report.update(inspect(args.hap, args.architecture,
                              compiler_record=args.compiler_record.read_bytes(),
                              adapter_record=args.adapter_record.read_bytes()))
        if args.metadata:
            metadata = json.loads(args.metadata.read_text(encoding="utf-8-sig"))
            report["buildId"] = verify_build_metadata(metadata, report)
        report["status"] = "PASS"
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile, struct.error) as error:
        report["error"] = str(error)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{report['status']}: {args.report}")
    if report["status"] != "PASS":
        print(report["error"], file=sys.stderr)
        return 1
    print(f"{report['catalog']['runCount']} programs; "
          f"{report['runtimeAbi']['required']} runtime ABI exports; "
          f"compiler boundary {report['compilerProvenance']['kind']}; "
          f"final native/data hashes verified; device unverified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
