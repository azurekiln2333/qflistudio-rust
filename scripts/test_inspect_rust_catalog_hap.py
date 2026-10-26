"""Final-archive regressions with real curriculum and tiny synthetic ELF data.

The archive must prove three things that byte identity alone cannot:

* the packaged adapter exports the whole Rust runtime ABI, not a stale
  run-surface-only build whose manifest was regenerated from itself;
* the manifest and the HAP agree about every native member, while the
  documented Flutter engine, AOT application snapshot and OHOS native probe
  stay allowed without being manifest-declared;
* malformed ELF input is rejected instead of being read past its bounds.

Every fixture below is built by hand so the suite stays pure Python: no
compiler, no SDK, no device.
"""

import contextlib
import hashlib
import inspect_rust_catalog_hap as inspector
import io
import itertools
import json
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

from generate_rust_content import ROOT, TOPIC_FILES
from inspect_rust_catalog_hap import (
    ADAPTER_LIBRARY, ANALYSIS_SYMBOLS, ASSETS, BUNDLE, DEBUGGER_SYMBOLS,
    PROBE_LIBRARY, PROBE_SYMBOLS, REQUIRED_RUNTIME_SYMBOLS, RUNTIME_SYMBOLS,
    TARGETS, declared_symbols, inspect, read_elf_exports,
    verify_build_metadata, verify_compiler_boundary, verify_compiler_provenance,
    verify_exported_symbols, verify_native_inventory,
)
from miri_build_support import (
    COMPILER_BOUNDARY_KIND, COMPILER_BOUNDARY_PATCH_SHA256, GUEST_TARGET,
    RUST_COMMIT, RUST_VERSION, compiler_boundary_patch, compiler_patch_hunks,
)

ELF_HEADER_BYTES = 64
SECTION_BYTES = 64
SYMBOL_BYTES = 24

TEXT, DYNSYM, DYNSTR, SHSTRTAB = 1, 2, 3, 4
SECTION_COUNT = 5
SHT_PROGBITS, SHT_STRTAB, SHT_DYNSYM = 1, 3, 11

# Section header fields: sh_name(4) sh_type(4) sh_flags(8) sh_addr(8) sh_offset(8)
# sh_size(8) sh_link(4) sh_info(4) sh_addralign(8) sh_entsize(8).
SECTION_FIELDS = {
    "name": (0, "<I"), "type": (4, "<I"), "flags": (8, "<Q"), "addr": (16, "<Q"),
    "offset": (24, "<Q"), "size": (32, "<Q"), "link": (40, "<I"),
    "info": (44, "<I"), "align": (48, "<Q"), "entsize": (56, "<Q"),
}
HEADER_FIELDS = {
    "class": (4, "<B"), "data": (5, "<B"), "machine": (18, "<H"),
    "shoff": (40, "<Q"), "shentsize": (58, "<H"), "shnum": (60, "<H"),
    "shstrndx": (62, "<H"),
}

# st_info(1) st_other(1) st_shndx(2) for the symbol flavours the loader
# distinguishes. Only "function" and "unique" are real callable exports.
SYMBOL_KINDS = {
    "function": (0x12, 0, TEXT),      # STB_GLOBAL | STT_FUNC
    "unique": (0xA2, 0, TEXT),        # STB_GNU_UNIQUE | STT_FUNC
    "ifunc": (0x1A, 0, TEXT),         # STB_GLOBAL | STT_GNU_IFUNC
    "local": (0x02, 0, TEXT),         # STB_LOCAL | STT_FUNC
    "hidden": (0x12, 2, TEXT),        # STV_HIDDEN
    "protected": (0x12, 3, TEXT),     # STV_PROTECTED
    "internal": (0x12, 1, TEXT),      # STV_INTERNAL
    "undefined": (0x12, 0, 0),        # SHN_UNDEF
    "object": (0x11, 0, TEXT),        # STB_GLOBAL | STT_OBJECT
    "weak": (0x22, 0, TEXT),          # STB_WEAK | STT_FUNC
}


def _align(value, alignment=8):
    return (value + alignment - 1) // alignment * alignment


# Compiler runtime libraries the packaged adapter depends on. The trusted adapter
# record declares them and the manifest must ship the same bytes.
COMPILER_LIBRARIES = ("librustc_driver-fixture.so", "librustc_codegen_fixture.so")


def boundary_record():
    """Return the reviewed embedded-compiler boundary identity for fixtures."""
    paths = ["compiler/" + relative
             for relative, _ in compiler_patch_hunks(compiler_boundary_patch())]
    return {
        "kind": COMPILER_BOUNDARY_KIND,
        "patchSha256": COMPILER_BOUNDARY_PATCH_SHA256,
        "sourceCommit": RUST_COMMIT,
        "inputTree": {"sha256": "1" * 64, "fileCount": 12},
        "patchedTree": {"sha256": "2" * 64, "fileCount": 12},
        "patchedFiles": [{"path": path, "beforeSha256": "3" * 64,
                          "afterSha256": "4" * 64} for path in paths],
    }


def default_libraries():
    """Return the recorded runtime library hashes used by the default fixtures."""
    return {COMPILER_LIBRARIES[0]: "7" * 64, COMPILER_LIBRARIES[1]: "8" * 64}


def compiler_record(host, libraries=None):
    """Return inert trusted compiler build record bytes for `host`.

    `libraries` maps each runtime shared object name to its recorded sha256, so
    the runtime artifacts and the adapter record name the same bytes.
    """
    libraries = libraries or default_libraries()
    artifacts = [{"root": "compiler", "size": 4096, "sha256": "5" * 64,
                  "path": f"lib/rustlib/{host}/lib/librustc_driver-fixture.rmeta"}]
    for name, digest in libraries.items():
        artifacts.append({"root": "runtime", "size": 8192, "sha256": digest,
                          "path": f"lib/{name}"})
    return json.dumps({
        "schemaVersion": 2, "status": "built",
        "rustVersion": RUST_VERSION, "rustCommit": RUST_COMMIT, "nativeHost": host,
        "compilerSysroot": "/build/compiler", "runtimeSysroot": "/build/runtime",
        "compilerBoundary": boundary_record(),
        "compilerArtifacts": artifacts,
    }, sort_keys=True).encode()


def adapter_record(host, adapter_sha, compiler=None, libraries=None):
    """Return inert trusted adapter build record bytes bound to `adapter_sha`."""
    boundary = boundary_record()
    libraries = libraries or default_libraries()
    compiler = compiler or compiler_record(host)
    return json.dumps({
        "schemaVersion": 1, "rustVersion": RUST_VERSION, "rustCommit": RUST_COMMIT,
        "nativeHost": host, "buildHost": host,
        "adapter": {"path": "/build/libqfli_miri.so", "sha256": adapter_sha},
        "dependencyMetadata": {"path": "/build/metadata.json", "sha256": "9" * 64},
        "compilerBuild": {
            "path": "/build/compiler-build.json",
            "sha256": hashlib.sha256(compiler).hexdigest(),
            "compilerBoundary": boundary,
        },
        "compilerBoundary": boundary,
        "compilerLibraries": [
            {"name": name, "sha256": digest, "path": f"/build/runtime/lib/{name}"}
            for name, digest in libraries.items()
        ],
    }, sort_keys=True).encode()


def trusted_records(host, adapter_sha, libraries=None):
    """Return a compiler record and an adapter record that agree on `libraries`."""
    libraries = libraries or default_libraries()
    compiler = compiler_record(host, libraries)
    return compiler, adapter_record(host, adapter_sha, compiler=compiler,
                                    libraries=libraries)


def build_elf(machine=62, symbols=REQUIRED_RUNTIME_SYMBOLS, *, kind="function",
              kinds=None, name_offsets=None, raw_names=None, terminate=True):
    """Return an ELF64LE shared object that exports `symbols`.

    `kinds` overrides the flavour per symbol name, `name_offsets` overrides the
    st_name of one symbol and `raw_names` replaces the encoded name bytes, so a
    single builder can produce both honest and malformed fixtures.
    """
    kinds = kinds or {}
    name_offsets = name_offsets or {}
    raw_names = raw_names or {}

    dynstr = bytearray(b"\x00")
    offsets = {}
    for name in symbols:
        offsets[name] = len(dynstr)
        dynstr += raw_names.get(name, name.encode("ascii")) + b"\x00"
    if not terminate:
        del dynstr[-1]

    dynsym = bytearray(SYMBOL_BYTES)  # index 0 is the reserved null symbol
    for name in symbols:
        st_info, st_other, st_shndx = SYMBOL_KINDS[kinds.get(name, kind)]
        dynsym += struct.pack("<IBBHQQ", name_offsets.get(name, offsets[name]),
                              st_info, st_other, st_shndx, 0x1000, 16)

    shstrtab = bytearray(b"\x00")

    def add(text):
        offset = len(shstrtab)
        shstrtab.extend(text.encode("ascii") + b"\x00")
        return offset

    named = [add(".text"), add(".dynsym"), add(".dynstr"), add(".shstrtab")]

    text = b"\xc3\x00\x00\x00"
    off_text = ELF_HEADER_BYTES
    off_dynsym = _align(off_text + len(text))
    off_dynstr = _align(off_dynsym + len(dynsym))
    off_shstrtab = _align(off_dynstr + len(dynstr))
    off_sections = _align(off_shstrtab + len(shstrtab))

    data = bytearray(off_sections + SECTION_COUNT * SECTION_BYTES)
    data[:ELF_HEADER_BYTES] = (
        b"\x7fELF\x02\x01\x01" + b"\x00" * 9
        + struct.pack("<HHIQQQIHHHHHH", 3, machine, 1, 0, 0, off_sections, 0,
                      ELF_HEADER_BYTES, 56, 0, SECTION_BYTES, SECTION_COUNT, SHSTRTAB))
    data[off_text:off_text + len(text)] = text
    data[off_dynsym:off_dynsym + len(dynsym)] = dynsym
    data[off_dynstr:off_dynstr + len(dynstr)] = dynstr
    data[off_shstrtab:off_shstrtab + len(shstrtab)] = shstrtab

    sections = [
        bytes(SECTION_BYTES),
        struct.pack("<IIQQQQIIQQ", named[0], SHT_PROGBITS, 0x6, 0, off_text,
                    len(text), 0, 0, 16, 0),
        struct.pack("<IIQQQQIIQQ", named[1], SHT_DYNSYM, 0, 0, off_dynsym,
                    len(dynsym), DYNSTR, 1, 8, SYMBOL_BYTES),
        struct.pack("<IIQQQQIIQQ", named[2], SHT_STRTAB, 0x2, 0, off_dynstr,
                    len(dynstr), 0, 0, 1, 0),
        struct.pack("<IIQQQQIIQQ", named[3], SHT_STRTAB, 0, 0, off_shstrtab,
                    len(shstrtab), 0, 0, 1, 0),
    ]
    for index, section in enumerate(sections):
        start = off_sections + index * SECTION_BYTES
        data[start:start + SECTION_BYTES] = section
    return bytes(data)


def patch_header(data, field, value):
    offset, fmt = HEADER_FIELDS[field]
    patched = bytearray(data)
    struct.pack_into(fmt, patched, offset, value)
    return bytes(patched)


def patch_section(data, index, field, value):
    offset, fmt = SECTION_FIELDS[field]
    shoff = struct.unpack_from("<Q", data, 40)[0]
    patched = bytearray(data)
    struct.pack_into(fmt, patched, shoff + index * SECTION_BYTES + offset, value)
    return bytes(patched)


def symbol_index(data, index):
    """Return `data` with the first real dynamic symbol pointed at `index`."""
    shoff = struct.unpack_from("<Q", data, 40)[0]
    dynsym = struct.unpack_from("<Q", data, shoff + DYNSYM * SECTION_BYTES + 24)[0]
    patched = bytearray(data)
    struct.pack_into("<H", patched, dynsym + SYMBOL_BYTES + 6, index)
    return bytes(patched)


class ElfExportReadingTest(unittest.TestCase):
    """The reader must report what the dynamic loader would resolve."""

    def require_abi(self, data):
        report = verify_exported_symbols(data, ADAPTER_LIBRARY, REQUIRED_RUNTIME_SYMBOLS)
        self.assertEqual(report["required"], len(REQUIRED_RUNTIME_SYMBOLS))
        self.assertEqual(report["sha256"], hashlib.sha256(data).hexdigest())
        return report

    def test_complete_adapter_satisfies_the_runtime_abi(self):
        data = build_elf(62, REQUIRED_RUNTIME_SYMBOLS)
        exports = read_elf_exports(data, ADAPTER_LIBRARY)
        self.assertEqual(set(exports), set(REQUIRED_RUNTIME_SYMBOLS))
        self.assertEqual(len(exports), 27)
        report = self.require_abi(data)
        self.assertIn("qfli_miri_create_with_project", report["exported"])
        self.assertIn("qfli_miri_analyze", report["exported"])
        self.assertIn("qfli_miri_debug_pause_info", report["exported"])

    def test_undefined_symbol_is_not_an_export(self):
        data = build_elf(62, REQUIRED_RUNTIME_SYMBOLS, kinds={"qfli_miri_run": "undefined"})
        self.assertNotIn("qfli_miri_run", read_elf_exports(data, ADAPTER_LIBRARY))
        with self.assertRaisesRegex(ValueError, r"missing exported \['qfli_miri_run'\]"):
            self.require_abi(data)

    def test_local_binding_is_not_an_export(self):
        data = build_elf(62, REQUIRED_RUNTIME_SYMBOLS,
                         kinds={"qfli_miri_create_with_project": "local"})
        self.assertNotIn("qfli_miri_create_with_project",
                         read_elf_exports(data, ADAPTER_LIBRARY))
        with self.assertRaisesRegex(ValueError, "Stale Rust runtime ABI"):
            self.require_abi(data)

    def test_hidden_visibility_is_not_an_export(self):
        data = build_elf(62, REQUIRED_RUNTIME_SYMBOLS,
                         kinds={"qfli_miri_analyze": "hidden"})
        self.assertNotIn("qfli_miri_analyze", read_elf_exports(data, ADAPTER_LIBRARY))
        with self.assertRaisesRegex(ValueError, "Stale Rust runtime ABI"):
            self.require_abi(data)

    def test_internal_visibility_is_not_an_export(self):
        data = build_elf(62, REQUIRED_RUNTIME_SYMBOLS,
                         kinds={"qfli_miri_debug_create": "internal"})
        self.assertNotIn("qfli_miri_debug_create",
                         read_elf_exports(data, ADAPTER_LIBRARY))

    def test_protected_visibility_is_still_an_export(self):
        """STV_PROTECTED stays reachable through dlsym, so it satisfies the ABI."""
        data = build_elf(62, REQUIRED_RUNTIME_SYMBOLS,
                         kinds={"qfli_miri_debug_create": "protected"})
        exports = read_elf_exports(data, ADAPTER_LIBRARY)
        self.assertEqual(exports["qfli_miri_debug_create"].visibility, 3)
        self.require_abi(data)

    def test_data_symbol_is_not_a_callable_export(self):
        data = build_elf(62, REQUIRED_RUNTIME_SYMBOLS,
                         kinds={"qfli_miri_result": "object"})
        self.assertNotIn("qfli_miri_result", read_elf_exports(data, ADAPTER_LIBRARY))

    def test_unique_and_ifunc_bindings_are_exports(self):
        data = build_elf(62, REQUIRED_RUNTIME_SYMBOLS,
                         kinds={"qfli_miri_create": "unique", "qfli_miri_cancel": "ifunc"})
        self.assertIn("qfli_miri_create", read_elf_exports(data, ADAPTER_LIBRARY))
        self.assertIn("qfli_miri_cancel", read_elf_exports(data, ADAPTER_LIBRARY))

    def test_weak_binding_is_a_loader_visible_export(self):
        """The loader resolves STB_WEAK definitions like global ones."""
        data = build_elf(62, REQUIRED_RUNTIME_SYMBOLS,
                         kinds={"qfli_miri_debug_frame": "weak"})
        exports = read_elf_exports(data, ADAPTER_LIBRARY)
        self.assertEqual(exports["qfli_miri_debug_frame"].binding, 2)
        self.require_abi(data)

    def test_definition_index_outside_the_section_table_rejected(self):
        """A nonreserved st_shndx past the section table cannot be defined."""
        data = build_elf(62, REQUIRED_RUNTIME_SYMBOLS)
        for index in (SECTION_COUNT, SECTION_COUNT + 4, 99):
            with self.subTest(index=index):
                with self.assertRaisesRegex(ValueError, r"section index"):
                    read_elf_exports(symbol_index(data, index), ADAPTER_LIBRARY)

    def test_repeat_definitions_collapse_to_one_export(self):
        duplicated = list(REQUIRED_RUNTIME_SYMBOLS) + list(REQUIRED_RUNTIME_SYMBOLS)
        exports = read_elf_exports(build_elf(62, duplicated), ADAPTER_LIBRARY)
        self.assertEqual(len(exports), len(REQUIRED_RUNTIME_SYMBOLS))
        # A name defined twice as hidden is absent no matter where it sits.
        hidden = read_elf_exports(
            build_elf(62, duplicated, kinds={"qfli_miri_run": "hidden"}), ADAPTER_LIBRARY)
        self.assertNotIn("qfli_miri_run", hidden)

    def test_missing_project_export_rejected(self):
        surface = tuple(name for name in REQUIRED_RUNTIME_SYMBOLS
                        if name != "qfli_miri_create_with_project")
        with self.assertRaisesRegex(ValueError, "qfli_miri_create_with_project"):
            self.require_abi(build_elf(62, surface))

    def test_missing_analysis_exports_rejected(self):
        surface = RUNTIME_SYMBOLS + DEBUGGER_SYMBOLS
        with self.assertRaisesRegex(ValueError, "qfli_miri_create_analysis"):
            self.require_abi(build_elf(62, surface))

    def test_missing_debug_exports_rejected(self):
        surface = RUNTIME_SYMBOLS + ANALYSIS_SYMBOLS
        with self.assertRaisesRegex(ValueError, "qfli_miri_debug_capabilities"):
            self.require_abi(build_elf(62, surface))

    def test_run_surface_only_adapter_rejected(self):
        with self.assertRaisesRegex(ValueError, "rebuild and repackage the adapter"):
            self.require_abi(build_elf(62, RUNTIME_SYMBOLS))


class MalformedElfTest(unittest.TestCase):
    """Every bound is checked before use, so bad input never reads past EOF."""

    def assertRejected(self, data, message):
        with self.assertRaisesRegex(ValueError, message):
            read_elf_exports(data, ADAPTER_LIBRARY)

    def test_truncated_header_rejected(self):
        self.assertRejected(b"\x7fELF\x02\x01" + bytes(26), "truncated")

    def test_bad_magic_rejected(self):
        self.assertRejected(b"XXXX" + bytes(60), "bad magic")

    def test_elf32_rejected(self):
        self.assertRejected(patch_header(build_elf(), "class", 1), "not a 64-bit ELF")

    def test_big_endian_rejected(self):
        self.assertRejected(patch_header(build_elf(), "data", 2), "not little-endian")

    def test_absent_section_table_rejected(self):
        bare = bytearray(ELF_HEADER_BYTES)
        bare[:6] = b"\x7fELF\x02\x01"
        struct.pack_into("<H", bare, 18, 62)
        self.assertRejected(bytes(bare), "absent, symbols unverifiable")

    def test_truncated_section_table_rejected(self):
        self.assertRejected(patch_header(build_elf(), "shnum", 200), "section table")

    def test_section_entry_size_mismatch_rejected(self):
        self.assertRejected(patch_header(build_elf(), "shentsize", 56), "entry size 56")

    def test_section_name_index_out_of_range_rejected(self):
        self.assertRejected(patch_header(build_elf(), "shstrndx", 9), "bad string index")

    def test_section_name_table_must_be_a_string_table(self):
        data = patch_section(build_elf(), SHSTRTAB, "type", SHT_PROGBITS)
        self.assertRejected(data, "section names are not a string table")

    def test_section_escaping_the_file_rejected(self):
        data = patch_section(build_elf(), DYNSYM, "size", 1 << 20)
        self.assertRejected(data, r"section 2 escapes the file")

    def test_unaligned_dynamic_symbol_table_rejected(self):
        data = patch_section(build_elf(), DYNSYM, "size", SYMBOL_BYTES + 1)
        self.assertRejected(data, "unaligned size")

    def test_dynamic_symbol_table_needs_a_string_table(self):
        for link in (0, TEXT, 77):
            with self.subTest(link=link):
                self.assertRejected(patch_section(build_elf(), DYNSYM, "link", link),
                                    "no string table")

    def test_missing_dynamic_symbol_section_rejected(self):
        data = patch_section(build_elf(), DYNSYM, "type", SHT_PROGBITS)
        self.assertRejected(data, r"no \.dynsym section")

    def test_name_offset_beyond_string_table_rejected(self):
        data = build_elf(name_offsets={"qfli_miri_run": 4096})
        self.assertRejected(data, "name offset")

    def test_unterminated_symbol_name_rejected(self):
        self.assertRejected(build_elf(terminate=False), "unterminated name")

    def test_non_ascii_symbol_name_rejected(self):
        data = build_elf(raw_names={"qfli_miri_run": b"qfli_miri_caf\xe9"})
        self.assertRejected(data, "non-ASCII symbol name")

    def test_required_symbols_are_checked_independently_of_the_reader(self):
        # A reader-level rejection must surface as a rejected archive too.
        data = build_elf(62, REQUIRED_RUNTIME_SYMBOLS)
        broken = patch_section(data, DYNSYM, "size", SYMBOL_BYTES * 3)
        with self.assertRaisesRegex(ValueError, "Stale Rust runtime ABI"):
            verify_exported_symbols(broken, ADAPTER_LIBRARY, REQUIRED_RUNTIME_SYMBOLS)


class NativeInventoryTest(unittest.TestCase):
    """The manifest declares what it ships; documented members are allowed."""

    def test_documented_application_libraries_are_allowed(self):
        packaged = {ADAPTER_LIBRARY, "libflutter.so", "libapp.so", PROBE_LIBRARY}
        report = verify_native_inventory({ADAPTER_LIBRARY}, packaged)
        self.assertEqual(report["unexpected"], [])
        self.assertEqual(report["manifestDeclared"], [ADAPTER_LIBRARY])
        self.assertEqual(report["applicationLibraries"],
                         ["libapp.so", "libflutter.so", PROBE_LIBRARY])

    def test_intruder_library_rejected(self):
        with self.assertRaisesRegex(ValueError, r"Unexpected native library.*libuploader\.so"):
            verify_native_inventory({ADAPTER_LIBRARY},
                                    {ADAPTER_LIBRARY, "libflutter.so", "libapp.so",
                                     "libuploader.so"})

    def test_adapter_must_be_manifest_declared(self):
        with self.assertRaisesRegex(ValueError, r"Unexpected native library.*libqfli_miri\.so"):
            verify_native_inventory(set(), {ADAPTER_LIBRARY, "libflutter.so", "libapp.so"})

    def test_missing_application_library_rejected(self):
        with self.assertRaisesRegex(ValueError, r"Missing release Flutter/native runtime.*libapp"):
            verify_native_inventory({ADAPTER_LIBRARY}, {ADAPTER_LIBRARY, "libflutter.so"})


class RequiredAbiConstantsTest(unittest.TestCase):
    """The Python constants must stay derived from the shipped headers."""

    def test_required_abi_matches_the_adapter_headers(self):
        declared = set()
        for header in ("qfli_miri.h", "qfli_debug.h"):
            declared |= set(declared_symbols(
                (ROOT / "native/miri_adapter" / header).read_text(encoding="utf-8")))
        self.assertEqual(declared, set(REQUIRED_RUNTIME_SYMBOLS))

    def test_abi_tiers_are_the_documented_three_tiers(self):
        self.assertEqual((len(RUNTIME_SYMBOLS), len(ANALYSIS_SYMBOLS),
                          len(DEBUGGER_SYMBOLS)), (9, 2, 16))
        self.assertEqual(set(REQUIRED_RUNTIME_SYMBOLS),
                         set(RUNTIME_SYMBOLS) | set(ANALYSIS_SYMBOLS) | set(DEBUGGER_SYMBOLS))
        self.assertIn("qfli_miri_create_with_project", RUNTIME_SYMBOLS)

    def test_vendored_headers_are_not_inside_the_symbol_constants(self):
        # Non-`qfli_miri_` prototypes must never be treated as runtime exports.
        for name in REQUIRED_RUNTIME_SYMBOLS:
            self.assertTrue(name.startswith("qfli_miri_"), name)


class InspectRustCatalogHapTest(unittest.TestCase):
    fixtures = itertools.count()

    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="rust-hap-test-")
        cls.root = Path(cls.temporary.name)
        for relative in [*(f"tool/rust_content/{name}" for name in TOPIC_FILES),
                         *(f"assets/content_rust/{name}.json"
                           for name in ("examples", "tutorials", "native_catalog"))]:
            destination = cls.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, destination)
        cls.guest_data = b"guest MIR test data"
        cls.guest_asset = hashlib.sha256(cls.guest_data).hexdigest() + ".bin"
        cls.manifests = {}
        cls.libraries = {}
        for architecture, (abi, host, machine) in TARGETS.items():
            libraries = {
                ADAPTER_LIBRARY: build_elf(machine, REQUIRED_RUNTIME_SYMBOLS),
                PROBE_LIBRARY: build_elf(machine, PROBE_SYMBOLS),
                "libflutter.so": build_elf(machine, ()),
                "libapp.so": build_elf(machine, ()),
                COMPILER_LIBRARIES[0]: build_elf(machine, ()),
                COMPILER_LIBRARIES[1]: build_elf(machine, ()),
            }
            cls.libraries[architecture] = libraries
            manifest = json.dumps(cls.runtime_for(machine, host, libraries)).encode()
            cls.manifests[architecture] = manifest
            path = cls.root / f"assets/miri/manifest.{architecture}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(manifest)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    @classmethod
    def runtime_for(cls, machine, host, libraries, adapter=None):
        digest = hashlib.sha256(cls.guest_data).hexdigest()
        adapter = adapter or libraries[ADAPTER_LIBRARY]
        runtime_hashes = {name: hashlib.sha256(libraries[name]).hexdigest()
                          for name in COMPILER_LIBRARIES}
        compiler, trusted = trusted_records(host, hashlib.sha256(adapter).hexdigest(),
                                           runtime_hashes)
        declared = [{"name": ADAPTER_LIBRARY,
                     "sha256": hashlib.sha256(adapter).hexdigest()}]
        for name in COMPILER_LIBRARIES:
            declared.append({"name": name, "sha256": runtime_hashes[name]})
        return {
            "schemaVersion": 1, "nativeHost": host, "guestTarget": GUEST_TARGET,
            "rustVersion": RUST_VERSION, "rustCommit": RUST_COMMIT, "id": "a" * 64,
            "compilerBoundary": boundary_record(),
            "compilerBuildSha256": hashlib.sha256(compiler).hexdigest(),
            "adapterBuildSha256": hashlib.sha256(trusted).hexdigest(),
            "files": [{"path": "lib/test.rlib", "asset": digest + ".bin",
                       "size": len(cls.guest_data), "sha256": digest}],
            "nativeLibraries": declared,
        }

    @classmethod
    def records(cls, architecture="ohos-x64", adapter=None):
        """Return trusted record bytes bound to the packaged libs of `architecture`."""
        host = TARGETS[architecture][1]
        libraries = cls.libraries[architecture]
        adapter = adapter if adapter is not None else libraries[ADAPTER_LIBRARY]
        return trusted_records(host, hashlib.sha256(adapter).hexdigest(),
                               {name: hashlib.sha256(libraries[name]).hexdigest()
                                for name in COMPILER_LIBRARIES})

    def verify(self, hap, architecture="ohos-x64", root=None, records=None):
        """Inspect an archive with trusted records for `architecture`."""
        compiler, adapter = records or self.records(architecture)
        return inspect(hap, architecture, root or self.root,
                       compiler_record=compiler, adapter_record=adapter)

    @classmethod
    def members_for(cls, architecture):
        abi = TARGETS[architecture][0]
        members = {
            "module.json": json.dumps({"app": {"bundleName": BUNDLE}, "module": {
                "type": "entry", "mainElement": "EntryAbility", "requestPermissions": []}}).encode(),
            "pack.info": json.dumps({"summary": {"app": {"bundleName": BUNDLE}}}).encode(),
            ASSETS + f"assets/miri/manifest.{architecture}.json": cls.manifests[architecture],
            ASSETS + "assets/miri/" + cls.guest_asset: cls.guest_data,
        }
        for name, data in cls.libraries[architecture].items():
            members[f"libs/{abi}/{name}"] = data
        for name in ("examples", "tutorials", "native_catalog"):
            relative = f"assets/content_rust/{name}.json"
            members[ASSETS + relative] = (cls.root / relative).read_bytes()
        return members

    def archive(self, changes=None, architecture="ohos-x64"):
        """Build a HAP; a `None` value removes that member."""
        members = self.members_for(architecture)
        for name, data in (changes or {}).items():
            if data is None:
                del members[name]
            else:
                members[name] = data
        path = self.root / f"test-{next(self.fixtures)}.hap"
        with zipfile.ZipFile(path, "w") as handle:
            for name, data in members.items():
                handle.writestr(name, data)
        return path

    @contextlib.contextmanager
    def runtime_override(self, architecture, runtime):
        """Temporarily point the manifest the inspector reads from `root`."""
        path = self.root / f"assets/miri/manifest.{architecture}.json"
        original = path.read_bytes()
        path.write_bytes(json.dumps(runtime).encode())
        try:
            yield
        finally:
            path.write_bytes(original)

    def library_member(self, architecture, name=ADAPTER_LIBRARY):
        return f"libs/{TARGETS[architecture][0]}/{name}"

    def manifest_member(self, architecture):
        return ASSETS + f"assets/miri/manifest.{architecture}.json"

    def test_current_catalog_and_final_hashes_pass_static_inspection(self):
        report = self.verify(self.archive(), "ohos-x64", self.root)
        self.assertEqual(report["catalog"]["runCount"], 332)
        self.assertFalse(report["deviceExecuted"])
        self.assertEqual(report["runtimeFiles"], 1)
        self.assertEqual(report["runtimeAbi"]["required"], 27)
        self.assertEqual(report["runtimeAbi"]["exported"],
                         sorted(REQUIRED_RUNTIME_SYMBOLS))
        self.assertEqual(report["probeAbi"]["exported"], sorted(PROBE_SYMBOLS))
        self.assertEqual(report["nativeInventory"]["unexpected"], [])
        self.assertEqual(report["nativeInventory"]["applicationLibraries"],
                         ["libapp.so", "libflutter.so", PROBE_LIBRARY])

    def test_arm64_archive_passes_static_inspection(self):
        report = self.verify(self.archive(architecture="ohos-arm64"), "ohos-arm64", self.root)
        self.assertEqual(report["architecture"], "ohos-arm64")
        self.assertEqual(report["runtimeAbi"]["required"], 27)
        self.assertEqual(report["runtimeAbi"]["sha256"],
                         hashlib.sha256(self.libraries["ohos-arm64"][ADAPTER_LIBRARY]).hexdigest())
        self.assertEqual(sorted(report["nativeLibraries"]),
                         sorted(["libapp.so", "libflutter.so", PROBE_LIBRARY, ADAPTER_LIBRARY,
                                 *COMPILER_LIBRARIES]))

    def test_arm64_archive_rejects_x64_adapter(self):
        stale = build_elf(62, REQUIRED_RUNTIME_SYMBOLS)
        with self.assertRaisesRegex(ValueError, "Wrong ELF architecture"):
            self.verify(self.archive({self.library_member("ohos-arm64"): stale},
                                 architecture="ohos-arm64"), "ohos-arm64", self.root)

    def test_run_surface_only_adapter_rejected_by_the_archive(self):
        """Byte identity alone would pass this: the manifest is regenerated too."""
        stale = build_elf(62, RUNTIME_SYMBOLS)
        runtime = self.runtime_for(62, TARGETS["ohos-x64"][1],
                                   self.libraries["ohos-x64"], adapter=stale)
        members = {self.library_member("ohos-x64"): stale,
                   self.manifest_member("ohos-x64"): json.dumps(runtime).encode()}
        with self.runtime_override("ohos-x64", runtime):
            with self.assertRaisesRegex(ValueError, "Stale Rust runtime ABI"):
                self.verify(self.archive(members), "ohos-x64", self.root)

    def test_bare_elf_header_rejected_by_the_archive(self):
        """The pre-symbol fixture (64 bytes, no sections) must not pass."""
        fake = bytearray(ELF_HEADER_BYTES)
        fake[:6] = b"\x7fELF\x02\x01"
        struct.pack_into("<H", fake, 18, 62)
        runtime = self.runtime_for(62, TARGETS["ohos-x64"][1],
                                   self.libraries["ohos-x64"], adapter=bytes(fake))
        members = {self.library_member("ohos-x64"): bytes(fake),
                   self.manifest_member("ohos-x64"): json.dumps(runtime).encode()}
        with self.runtime_override("ohos-x64", runtime):
            with self.assertRaisesRegex(ValueError, "absent, symbols unverifiable"):
                self.verify(self.archive(members), "ohos-x64", self.root)

    def test_missing_adapter_member_rejected(self):
        with self.assertRaisesRegex(
                ValueError, r"Missing manifest-covered native library in HAP: libqfli_miri\.so"):
            self.verify(self.archive({self.library_member("ohos-x64"): None}),
                    "ohos-x64", self.root)

    def test_unexpected_native_library_rejected(self):
        extra = self.library_member("ohos-x64", "libuploader.so")
        with self.assertRaisesRegex(ValueError, r"Unexpected native library.*libuploader\.so"):
            self.verify(self.archive({extra: build_elf(62, ())}), "ohos-x64", self.root)

    def test_unmanifested_native_payload_rejected(self):
        """A non-.so regular file would otherwise ride along unaudited."""
        payload = "libs/x86_64/config.bin"
        with self.assertRaisesRegex(ValueError,
                                    r"Unmanifested native payload in HAP: libs/x86_64/config\.bin"):
            self.verify(self.archive({payload: b"unverified payload"}), "ohos-x64", self.root)

    def test_nested_native_payload_rejected(self):
        payload = "libs/x86_64/extra/payload.dat"
        with self.assertRaisesRegex(ValueError, r"Unmanifested native payload in HAP"):
            self.verify(self.archive({payload: b"unverified payload"}), "ohos-x64", self.root)

    def test_foreign_abi_native_payload_rejected(self):
        """Any regular member under libs/ must be libs/<selected-abi>/<name>.so."""
        payload = "libs/arm64-v8a/config.bin"
        with self.assertRaisesRegex(
                ValueError, r"Unmanifested native payload in HAP: libs/arm64-v8a/config\.bin"):
            self.verify(self.archive({payload: b"unverified payload"}), "ohos-x64", self.root)

    def test_payload_directly_under_libs_rejected(self):
        with self.assertRaisesRegex(
                ValueError, r"Unmanifested native payload in HAP: libs/config\.bin"):
            self.verify(self.archive({"libs/config.bin": b"unverified payload"}),
                        "ohos-x64", self.root)

    def test_native_directory_entries_are_allowed(self):
        """Directory entries are packaging structure, not native payload."""
        report = self.verify(self.archive({"libs/x86_64/": b"",
                                       "libs/x86_64/unused/": b""}),
                         "ohos-x64", self.root)
        self.assertEqual(report["runtimeAbi"]["required"], 27)
        self.assertEqual(report["nativeInventory"]["unexpected"], [])

    def test_missing_application_library_rejected(self):
        library = self.library_member("ohos-x64", "libapp.so")
        with self.assertRaisesRegex(ValueError, "Missing release Flutter/native runtime"):
            self.verify(self.archive({library: None}), "ohos-x64", self.root)

    def test_probe_library_allowed_without_a_manifest_entry(self):
        report = self.verify(self.archive(), "ohos-x64", self.root)
        self.assertNotIn(PROBE_LIBRARY, [item["name"]
                                         for item in self.runtime_for(
                                             62, TARGETS["ohos-x64"][1],
                                             self.libraries["ohos-x64"])["nativeLibraries"]])
        self.assertEqual(report["probeAbi"]["library"], PROBE_LIBRARY)
        self.assertIn(PROBE_LIBRARY, report["nativeInventory"]["applicationLibraries"])

    def test_probe_library_must_export_its_symbol(self):
        silent = self.library_member("ohos-x64", PROBE_LIBRARY)
        with self.assertRaisesRegex(ValueError, r"Stale Rust runtime ABI in libqfli_native_probe\.so"):
            self.verify(self.archive({silent: build_elf(62, ())}), "ohos-x64", self.root)

    def test_absent_probe_is_reported_as_unpackaged(self):
        report = self.verify(self.archive({self.library_member("ohos-x64", PROBE_LIBRARY): None}),
                         "ohos-x64", self.root)
        self.assertEqual(report["probeAbi"], {"library": PROBE_LIBRARY, "packaged": False})

    def test_production_identity_rejected(self):
        module = json.loads(self.members_for("ohos-x64")["module.json"])
        module["app"]["bundleName"] = "com.azurekiln.qfli.rust"
        with self.assertRaisesRegex(ValueError, "isolated"):
            self.verify(self.archive({"module.json": json.dumps(module)}), "ohos-x64", self.root)

    def test_internet_permission_rejected(self):
        module = json.loads(self.members_for("ohos-x64")["module.json"])
        module["module"]["requestPermissions"] = [{"name": "ohos.permission.INTERNET"}]
        with self.assertRaisesRegex(ValueError, "Internet"):
            self.verify(self.archive({"module.json": json.dumps(module)}), "ohos-x64", self.root)

    def test_transformed_native_library_rejected(self):
        member = self.library_member("ohos-x64")
        with self.assertRaisesRegex(ValueError, "native bytes"):
            self.verify(self.archive({member: self.libraries["ohos-x64"][ADAPTER_LIBRARY] + b"stripped"}),
                    "ohos-x64", self.root)

    def test_wrong_native_architecture_rejected(self):
        with self.assertRaisesRegex(ValueError, "architecture"):
            self.verify(self.archive({"libs/arm64-v8a/extra.so": b""}), "ohos-x64", self.root)

    def test_stale_catalog_rejected(self):
        with self.assertRaisesRegex(ValueError, "Stale packaged native catalog"):
            self.verify(self.archive({ASSETS + "assets/content_rust/native_catalog.json": b"{}"}),
                    "ohos-x64", self.root)

    def test_corrupt_guest_asset_rejected(self):
        asset = ASSETS + "assets/miri/" + self.guest_asset
        with self.assertRaisesRegex(ValueError, "Runtime data differs"):
            self.verify(self.archive({asset: b"corrupt"}), "ohos-x64", self.root)

    def test_absent_build_records_rejected(self):
        with self.assertRaisesRegex(ValueError, "required to establish provenance"):
            inspect(self.archive(), "ohos-x64", self.root,
                    compiler_record=None, adapter_record=None)

    def test_manifest_without_provenance_rejected(self):
        """The old fixture shape, with no boundary or record hashes, must fail."""
        runtime = self.runtime_for(62, TARGETS["ohos-x64"][1], self.libraries["ohos-x64"])
        for key in ("compilerBoundary", "compilerBuildSha256", "adapterBuildSha256"):
            runtime.pop(key)
        members = {self.manifest_member("ohos-x64"): json.dumps(runtime).encode()}
        with self.runtime_override("ohos-x64", runtime):
            with self.assertRaisesRegex(ValueError, "Compiler boundary is missing"):
                self.verify(self.archive(members), "ohos-x64", self.root)

    def test_swapped_compiler_with_regenerated_manifest_rejected(self):
        """Byte identity cannot catch this: only the trusted record can."""
        host = TARGETS["ohos-x64"][1]
        swapped = build_elf(62, ()) + b"swapped compiler payload"
        runtime = self.runtime_for(62, host, self.libraries["ohos-x64"])
        for item in runtime["nativeLibraries"]:
            if item["name"] == COMPILER_LIBRARIES[0]:
                item["sha256"] = hashlib.sha256(swapped).hexdigest()
        members = {self.library_member("ohos-x64", COMPILER_LIBRARIES[0]): swapped,
                   self.manifest_member("ohos-x64"): json.dumps(runtime).encode()}
        with self.runtime_override("ohos-x64", runtime):
            with self.assertRaisesRegex(
                    ValueError, r"Packaged compiler library differs from the adapter build record"):
                self.verify(self.archive(members), "ohos-x64", self.root)

    def test_report_binds_the_trusted_records(self):
        compiler, adapter = self.records("ohos-x64")
        report = self.verify(self.archive(), "ohos-x64", self.root)
        provenance = report["compilerProvenance"]
        self.assertEqual(provenance["compilerBuildSha256"],
                         hashlib.sha256(compiler).hexdigest())
        self.assertEqual(provenance["adapterBuildSha256"],
                         hashlib.sha256(adapter).hexdigest())
        self.assertEqual(provenance["kind"], COMPILER_BOUNDARY_KIND)
        self.assertEqual(provenance["packagedCompilerLibraries"], sorted(COMPILER_LIBRARIES))

    def build_metadata(self, report, **overrides):
        """Return audit build metadata bound to `report` and its records."""
        compiler, adapter = self.records("ohos-x64")
        value = {"sha256": report["artifact"]["sha256"], "bundleName": BUNDLE,
                 "architecture": "ohos-x64", "target": "lib/main_catalog_audit.dart",
                 "signed": False, "buildId": "0" * 32,
                 "compilerRecordSha256": hashlib.sha256(compiler).hexdigest(),
                 "adapterRecordSha256": hashlib.sha256(adapter).hexdigest()}
        value.update(overrides)
        return value

    def test_metadata_binds_the_consumed_records(self):
        report = self.verify(self.archive(), "ohos-x64", self.root)
        self.assertEqual(verify_build_metadata(self.build_metadata(report), report),
                         "0" * 32)

    def test_metadata_with_a_swapped_record_rejected(self):
        """A record swapped after the metadata was written must not pass."""
        report = self.verify(self.archive(), "ohos-x64", self.root)
        metadata = self.build_metadata(report, compilerRecordSha256="f" * 64)
        with self.assertRaisesRegex(
                ValueError, r"compilerRecordSha256 differs from the consumed build record"):
            verify_build_metadata(metadata, report)

    def run_cli(self, hap, metadata=None, records=None):
        """Drive the real CLI through `main()` with record and metadata files."""
        compiler, adapter = records or self.records("ohos-x64")
        compiler_path = self.root / "compiler-build.json"
        adapter_path = self.root / "adapter-build.json"
        compiler_path.write_bytes(compiler)
        adapter_path.write_bytes(adapter)
        metadata_path = None
        if metadata is not None:
            metadata_path = self.root / f"build-{next(self.fixtures)}.json"
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        report_path = self.root / f"report-{next(self.fixtures)}.json"
        argv = ["inspect_rust_catalog_hap.py", "--hap", str(hap),
                "--architecture", "ohos-x64",
                "--compiler-record", str(compiler_path),
                "--adapter-record", str(adapter_path),
                "--report", str(report_path)]
        if metadata_path is not None:
            argv += ["--metadata", str(metadata_path)]
        saved = sys.argv
        original = inspector.inspect

        def bound(*args, **kwargs):
            # The CLI deliberately has no --root flag, so point the fixture root
            # at the copy of the catalog and manifest this suite built.
            kwargs.setdefault("root", self.root)
            return original(*args, **kwargs)

        try:
            sys.argv = argv
            with mock.patch.object(inspector, "inspect", bound):
                with contextlib.redirect_stdout(io.StringIO()):
                    with contextlib.redirect_stderr(io.StringIO()):
                        status = inspector.main()
        finally:
            sys.argv = saved
        return status, json.loads(report_path.read_text(encoding="utf-8"))

    def test_cli_accepts_metadata_bound_to_the_consumed_records(self):
        hap = self.archive()
        report = self.verify(hap, "ohos-x64", self.root)
        status, written = self.run_cli(hap, self.build_metadata(report))
        self.assertEqual(status, 0, written.get("error"))
        self.assertEqual(written["status"], "PASS")
        self.assertEqual(written["buildId"], "0" * 32)
        compiler, adapter = self.records("ohos-x64")
        self.assertEqual(written["compilerProvenance"]["compilerBuildSha256"],
                         hashlib.sha256(compiler).hexdigest())
        self.assertEqual(written["compilerProvenance"]["adapterBuildSha256"],
                         hashlib.sha256(adapter).hexdigest())

    def test_cli_rejects_metadata_naming_another_record(self):
        hap = self.archive()
        report = self.verify(hap, "ohos-x64", self.root)
        status, written = self.run_cli(
            hap, self.build_metadata(report, adapterRecordSha256="f" * 64))
        self.assertEqual(status, 1)
        self.assertEqual(written["status"], "FAIL")
        self.assertIn("adapterRecordSha256 differs from the consumed build record",
                      written["error"])

    def test_cli_rejects_metadata_without_record_hashes(self):
        hap = self.archive()
        report = self.verify(hap, "ohos-x64", self.root)
        metadata = self.build_metadata(report)
        metadata.pop("compilerRecordSha256")
        status, written = self.run_cli(hap, metadata)
        self.assertEqual(status, 1)
        self.assertIn("lacks a well-formed compilerRecordSha256", written["error"])


class CompilerProvenanceTest(unittest.TestCase):
    """Trusted record bytes must bind the packaged manifest and packaged bytes."""

    host = TARGETS["ohos-x64"][1]
    adapter_bytes = b"packaged adapter bytes"

    def packaged(self, **overrides):
        values = {ADAPTER_LIBRARY: hashlib.sha256(self.adapter_bytes).hexdigest(),
                  COMPILER_LIBRARIES[0]: "7" * 64, COMPILER_LIBRARIES[1]: "8" * 64}
        values.update(overrides)
        return values

    def records(self, compiler_edit=None, adapter_edit=None, link_edited=True):
        """Build record bytes, optionally corrupting one record."""
        compiler = json.loads(compiler_record(self.host))
        if compiler_edit is not None:
            compiler_edit(compiler)
        compiler_bytes = json.dumps(compiler, sort_keys=True).encode()
        linked = compiler_bytes if link_edited else compiler_record(self.host)
        adapter = json.loads(adapter_record(
            self.host, hashlib.sha256(self.adapter_bytes).hexdigest(), compiler=linked))
        if adapter_edit is not None:
            adapter_edit(adapter)
        return compiler_bytes, json.dumps(adapter, sort_keys=True).encode()

    def runtime(self, compiler, adapter, **overrides):
        value = {"compilerBoundary": boundary_record(),
                 "compilerBuildSha256": hashlib.sha256(compiler).hexdigest(),
                 "adapterBuildSha256": hashlib.sha256(adapter).hexdigest()}
        value.update(overrides)
        return value

    def require(self, runtime, compiler, adapter, packaged=None):
        return verify_compiler_provenance(runtime, compiler, adapter, self.adapter_bytes,
                                          self.host, packaged or self.packaged())

    def assertRejected(self, runtime, compiler, adapter, message, packaged=None):
        with self.assertRaisesRegex(ValueError, message):
            self.require(runtime, compiler, adapter, packaged)

    def test_accepts_the_trusted_chain(self):
        compiler, adapter = self.records()
        report = self.require(self.runtime(compiler, adapter), compiler, adapter)
        self.assertEqual(report["adapterSha256"],
                         hashlib.sha256(self.adapter_bytes).hexdigest())
        self.assertEqual(report["compilerLibraries"], 2)

    def test_missing_boundary_rejected(self):
        compiler, adapter = self.records()
        runtime = self.runtime(compiler, adapter)
        runtime.pop("compilerBoundary")
        self.assertRejected(runtime, compiler, adapter, "Compiler boundary is missing")

    def test_stock_compiler_boundary_rejected(self):
        compiler, adapter = self.records()
        runtime = self.runtime(compiler, adapter,
                               compilerBoundary=dict(boundary_record(), kind="stock-rustc"))
        self.assertRejected(runtime, compiler, adapter,
                            "not the reviewed embedded compiler")

    def test_wrong_patch_boundary_rejected(self):
        compiler, adapter = self.records()
        runtime = self.runtime(compiler, adapter,
                               compilerBoundary=dict(boundary_record(), patchSha256="0" * 64))
        self.assertRejected(runtime, compiler, adapter,
                            "differs from the reviewed SHA-256")

    def test_malformed_manifest_hash_rejected(self):
        compiler, adapter = self.records()
        runtime = self.runtime(compiler, adapter, compilerBuildSha256="not-a-hash")
        self.assertRejected(runtime, compiler, adapter,
                            "compilerBuildSha256 is missing or malformed")

    def test_manifest_compiler_hash_mismatch_rejected(self):
        compiler, adapter = self.records()
        other, _ = self.records(compiler_edit=lambda value: value.update(
            compilerSysroot="/build/other"))
        self.assertRejected(self.runtime(compiler, adapter), other, adapter,
                            "compiler build hash differs from the supplied compiler record")

    def test_manifest_adapter_hash_mismatch_rejected(self):
        compiler, adapter = self.records()
        _, other = self.records(adapter_edit=lambda value: value["adapter"].update(
            path="/build/other.so"))
        self.assertRejected(self.runtime(compiler, adapter), compiler, other,
                            "adapter build hash differs from the supplied adapter record")

    def test_failed_compiler_record_rejected(self):
        compiler, adapter = self.records(
            compiler_edit=lambda value: value.update(status="failed"))
        self.assertRejected(self.runtime(compiler, adapter), compiler, adapter,
                            "not a completed pinned build")

    def test_stock_compiler_record_rejected(self):
        compiler, adapter = self.records(
            compiler_edit=lambda value: value["compilerBoundary"].update(kind="stock-rustc"))
        self.assertRejected(self.runtime(compiler, adapter), compiler, adapter,
                            "not the reviewed embedded compiler")

    def test_compiler_record_without_artifacts_rejected(self):
        compiler, adapter = self.records(
            compiler_edit=lambda value: value.update(compilerArtifacts=[]))
        self.assertRejected(self.runtime(compiler, adapter), compiler, adapter,
                            "no private-library hashes")

    def test_compiler_record_foreign_host_rejected(self):
        compiler, adapter = self.records(
            compiler_edit=lambda value: value.update(nativeHost="aarch64-unknown-linux-ohos"))
        self.assertRejected(self.runtime(compiler, adapter), compiler, adapter,
                            "targets another native host")

    def test_adapter_record_wrong_adapter_rejected(self):
        compiler, adapter = self.records(
            adapter_edit=lambda value: value["adapter"].update(sha256="a" * 64))
        self.assertRejected(self.runtime(compiler, adapter), compiler, adapter,
                            "Packaged adapter differs from the adapter build record")

    def test_adapter_record_foreign_compiler_rejected(self):
        compiler, adapter = self.records(
            compiler_edit=lambda value: value.update(compilerSysroot="/build/other"),
            link_edited=False)
        self.assertRejected(self.runtime(compiler, adapter), compiler, adapter,
                            "points at another compiler build")

    def test_adapter_record_compiler_identity_shape_rejected(self):
        compiler, adapter = self.records(
            adapter_edit=lambda value: value["compilerBuild"].pop("path"))
        self.assertRejected(self.runtime(compiler, adapter), compiler, adapter,
                            "lacks the compiler identity")

    def test_adapter_record_boundary_mismatch_rejected(self):
        compiler, adapter = self.records(link_edited=False)
        adapter = json.loads(adapter)
        # Structurally valid but a different tree than the compiler record names.
        adapter["compilerBuild"]["compilerBoundary"]["inputTree"]["sha256"] = "c" * 64
        mutated = json.dumps(adapter, sort_keys=True).encode()
        self.assertRejected(self.runtime(compiler, mutated), compiler, mutated,
                            "compilerBuild boundary differs from the compiler record")

    def test_adapter_record_missing_runtime_library_rejected(self):
        compiler, adapter = self.records(adapter_edit=lambda value: value[
            "compilerLibraries"].pop())
        self.assertRejected(self.runtime(compiler, adapter), compiler, adapter,
                            "lacks a rustc_codegen runtime library")

    def test_swapped_packaged_compiler_rejected(self):
        """A regenerated manifest still cannot hide a swapped compiler."""
        compiler, adapter = self.records()
        self.assertRejected(self.runtime(compiler, adapter), compiler, adapter,
                            "Packaged compiler library differs from the adapter build record",
                            packaged=self.packaged(**{COMPILER_LIBRARIES[0]: "b" * 64}))

    def test_adapter_runtime_hash_conflicts_with_the_compiler_artifact(self):
        """The adapter row must carry the compiler-record hash, not its own."""
        compiler, adapter = self.records(compiler_edit=lambda value: [
            row.update(sha256="6" * 64) for row in value["compilerArtifacts"]
            if row["path"].endswith(COMPILER_LIBRARIES[0])])
        self.assertRejected(self.runtime(compiler, adapter), compiler, adapter,
                            "Compiler artifacts disagree with the adapter build record")

    def test_adapter_runtime_absent_from_the_compiler_artifacts_rejected(self):
        """Codegen recorded by the adapter but missing from the compiler record."""
        compiler, adapter = self.records(compiler_edit=lambda value: value.update(
            compilerArtifacts=[row for row in value["compilerArtifacts"]
                               if not row["path"].endswith(COMPILER_LIBRARIES[1])]))
        self.assertRejected(self.runtime(compiler, adapter), compiler, adapter,
                            "names a runtime library absent from the compiler artifacts")

    def test_adapter_runtime_path_outside_the_runtime_sysroot_rejected(self):
        def edit(value):
            for row in value["compilerLibraries"]:
                row["path"] = "/build/other/lib/" + row["name"]
        compiler, adapter = self.records(adapter_edit=edit)
        self.assertRejected(self.runtime(compiler, adapter), compiler, adapter,
                            "lies outside the runtime sysroot")

    def test_adapter_runtime_path_with_a_parent_reference_rejected(self):
        def edit(value):
            for row in value["compilerLibraries"]:
                row["path"] = "/build/runtime/../etc/lib/" + row["name"]
        compiler, adapter = self.records(adapter_edit=edit)
        self.assertRejected(self.runtime(compiler, adapter), compiler, adapter,
                            "compiler library path is unsafe")

    def test_adapter_runtime_name_disagreeing_with_its_path_rejected(self):
        def edit(value):
            value["compilerLibraries"][0]["name"] = "librustc_other-fixture.so"
        compiler, adapter = self.records(adapter_edit=edit)
        self.assertRejected(self.runtime(compiler, adapter), compiler, adapter,
                            "library name disagrees with its recorded path")

    def test_adapter_conflicting_duplicate_library_rejected(self):
        """Two rows for one name, each matching its own artifact, must conflict."""
        name = COMPILER_LIBRARIES[0]

        def add_artifact(value):
            value["compilerArtifacts"].append({"root": "runtime", "size": 1024,
                                               "sha256": "a" * 64,
                                               "path": f"lib/other/{name}"})

        def add_row(value):
            value["compilerLibraries"].append({"name": name, "sha256": "a" * 64,
                                               "path": f"/build/runtime/lib/other/{name}"})

        compiler, adapter = self.records(compiler_edit=add_artifact,
                                         adapter_edit=add_row)
        self.assertRejected(self.runtime(compiler, adapter), compiler, adapter,
                            "conflicts on compiler library")

    def test_compiler_conflicting_duplicate_runtime_artifact_rejected(self):
        def edit(value):
            row = dict(value["compilerArtifacts"][-1])
            row["sha256"] = "c" * 64
            value["compilerArtifacts"].append(row)
        compiler, adapter = self.records(compiler_edit=edit)
        self.assertRejected(self.runtime(compiler, adapter), compiler, adapter,
                            "conflicts on runtime artifact")

    def test_compiler_record_without_runtime_artifacts_rejected(self):
        def edit(value):
            for row in value["compilerArtifacts"]:
                row["root"] = "compiler"
        compiler, adapter = self.records(compiler_edit=edit)
        self.assertRejected(self.runtime(compiler, adapter), compiler, adapter,
                            "lists no runtime artifacts")

    def test_compiler_record_without_a_runtime_sysroot_rejected(self):
        def edit(value):
            value.pop("runtimeSysroot")
        compiler, adapter = self.records(compiler_edit=edit)
        self.assertRejected(self.runtime(compiler, adapter), compiler, adapter,
                            "has no runtime sysroot")

    def test_rooted_compiler_artifact_paths_rejected(self):
        """Artifact paths are relative, so every rooted form is corrupt."""
        for path in ("/lib/librustc_driver-fixture.so",
                     "C:/lib/librustc_driver-fixture.so",
                     "C:\\lib\\librustc_driver-fixture.so",
                     "C:lib/librustc_driver-fixture.so",
                     "//server/share/lib/librustc_driver-fixture.so",
                     "\\\\server\\share\\lib\\librustc_driver-fixture.so"):
            with self.subTest(path=path):
                def edit(value, path=path):
                    for row in value["compilerArtifacts"]:
                        if row["path"].endswith(COMPILER_LIBRARIES[0]):
                            row["path"] = path
                compiler, adapter = self.records(compiler_edit=edit)
                self.assertRejected(self.runtime(compiler, adapter), compiler, adapter,
                                    "runtime artifact path is not relative")

    def test_nul_byte_in_compiler_artifact_path_rejected(self):
        def edit(value):
            for row in value["compilerArtifacts"]:
                if row["path"].endswith(COMPILER_LIBRARIES[0]):
                    row["path"] = "lib/\x00librustc_driver-fixture.so"
        compiler, adapter = self.records(compiler_edit=edit)
        self.assertRejected(self.runtime(compiler, adapter), compiler, adapter,
                            "runtime artifact path contains a NUL byte")

    def test_empty_compiler_artifact_path_rejected(self):
        def edit(value):
            for row in value["compilerArtifacts"]:
                if row["path"].endswith(COMPILER_LIBRARIES[0]):
                    row["path"] = "   "
        compiler, adapter = self.records(compiler_edit=edit)
        self.assertRejected(self.runtime(compiler, adapter), compiler, adapter,
                            "runtime artifact path is empty")

    def test_absolute_producer_paths_stay_accepted(self):
        """runtimeSysroot and compilerLibraries remain absolute by contract."""
        compiler, adapter = self.records()
        record = json.loads(compiler)
        self.assertTrue(record["runtimeSysroot"].startswith("/"))
        for row in json.loads(adapter)["compilerLibraries"]:
            self.assertTrue(row["path"].startswith(record["runtimeSysroot"] + "/"))
        report = self.require(self.runtime(compiler, adapter), compiler, adapter)
        self.assertEqual(report["compilerLibraries"], 2)

    def test_windows_and_posix_separators_are_normalized(self):
        """A foreign producer path chain still links without touching disk."""
        windows = "D:\\build\\runtime"
        compiler, adapter = self.records(
            compiler_edit=lambda value: value.update(runtimeSysroot=windows))
        adapter = json.loads(adapter)
        for row in adapter["compilerLibraries"]:
            row["path"] = windows + "\\lib\\" + row["name"]
        adapter = json.dumps(adapter, sort_keys=True).encode()
        report = self.require(self.runtime(compiler, adapter), compiler, adapter)
        self.assertEqual(report["compilerLibraries"], 2)

    def test_absolute_posix_paths_link_to_the_runtime_inventory(self):
        report = self.require(self.runtime(*self.records()), *self.records())
        self.assertEqual(report["packagedCompilerLibraries"], sorted(COMPILER_LIBRARIES))

    def test_recorded_compiler_absent_from_package_rejected(self):
        compiler, adapter = self.records()
        packaged = self.packaged()
        packaged.pop(COMPILER_LIBRARIES[1])
        self.assertRejected(self.runtime(compiler, adapter), compiler, adapter,
                            "lack the recorded rustc_codegen runtime library",
                            packaged=packaged)

    def test_malformed_record_bytes_rejected(self):
        compiler, adapter = self.records()
        with self.assertRaisesRegex(ValueError, "Malformed compiler build record"):
            self.require(self.runtime(compiler, adapter), b"{not json", adapter)

    def test_absent_record_bytes_rejected(self):
        compiler, adapter = self.records()
        with self.assertRaisesRegex(ValueError, "Missing compiler build record bytes"):
            self.require(self.runtime(compiler, adapter), b"", adapter)

    def test_compiler_library_hash_malformed_rejected(self):
        compiler, adapter = self.records(adapter_edit=lambda value: value[
            "compilerLibraries"][0].update(sha256="xyz"))
        self.assertRejected(self.runtime(compiler, adapter), compiler, adapter,
                            "compiler library hash is malformed")

    def test_boundary_requires_the_reviewed_patched_file_list(self):
        compiler, adapter = self.records()
        runtime = self.runtime(compiler, adapter)
        runtime["compilerBoundary"]["patchedFiles"] = runtime["compilerBoundary"][
            "patchedFiles"][:1]
        self.assertRejected(runtime, compiler, adapter,
                            "patched file list differs from the reviewed patch")

    def test_boundary_requires_well_formed_tree_identity(self):
        compiler, adapter = self.records()
        runtime = self.runtime(compiler, adapter)
        runtime["compilerBoundary"]["inputTree"]["fileCount"] = 0
        self.assertRejected(runtime, compiler, adapter,
                            "inputTree file count is invalid")

    def test_boundary_helper_returns_the_exact_reviewed_identity(self):
        boundary = verify_compiler_boundary(boundary_record())
        self.assertEqual(boundary["kind"], COMPILER_BOUNDARY_KIND)
        self.assertEqual(boundary["patchSha256"], COMPILER_BOUNDARY_PATCH_SHA256)
        self.assertEqual(boundary["sourceCommit"], RUST_COMMIT)


class BuildMetadataTest(unittest.TestCase):
    """Audit build metadata must name the exact record bytes that were consumed."""

    def report(self):
        return {"architecture": "ohos-x64", "artifact": {"sha256": "a" * 64},
                "compilerProvenance": {"compilerBuildSha256": "b" * 64,
                                       "adapterBuildSha256": "c" * 64}}

    def metadata(self, **overrides):
        value = {"sha256": "a" * 64, "bundleName": BUNDLE, "architecture": "ohos-x64",
                 "target": "lib/main_catalog_audit.dart", "signed": False,
                 "buildId": "d" * 32, "compilerRecordSha256": "b" * 64,
                 "adapterRecordSha256": "c" * 64}
        value.update(overrides)
        return value

    def assertRejected(self, metadata, message, report=None):
        with self.assertRaisesRegex(ValueError, message):
            verify_build_metadata(metadata, report or self.report())

    def test_accepts_bound_metadata(self):
        self.assertEqual(verify_build_metadata(self.metadata(), self.report()), "d" * 32)

    def test_missing_compiler_record_hash_rejected(self):
        metadata = self.metadata()
        metadata.pop("compilerRecordSha256")
        self.assertRejected(metadata, "lacks a well-formed compilerRecordSha256")

    def test_missing_adapter_record_hash_rejected(self):
        metadata = self.metadata()
        metadata.pop("adapterRecordSha256")
        self.assertRejected(metadata, "lacks a well-formed adapterRecordSha256")

    def test_malformed_compiler_record_hash_rejected(self):
        self.assertRejected(self.metadata(compilerRecordSha256="not-a-hash"),
                            "lacks a well-formed compilerRecordSha256")

    def test_malformed_adapter_record_hash_rejected(self):
        self.assertRejected(self.metadata(adapterRecordSha256="A" * 64),
                            "lacks a well-formed adapterRecordSha256")

    def test_swapped_compiler_record_hash_rejected(self):
        self.assertRejected(self.metadata(compilerRecordSha256="e" * 64),
                            "compilerRecordSha256 differs from the consumed build record")

    def test_swapped_adapter_record_hash_rejected(self):
        self.assertRejected(self.metadata(adapterRecordSha256="e" * 64),
                            "adapterRecordSha256 differs from the consumed build record")

    def test_hap_hash_mismatch_rejected(self):
        self.assertRejected(self.metadata(sha256="f" * 64), "Build HAP hash differs")

    def test_identity_mismatch_rejected(self):
        self.assertRejected(self.metadata(bundleName="com.azurekiln.qfli.rust"),
                            "Build metadata differs")

    def test_signed_metadata_rejected(self):
        self.assertRejected(self.metadata(signed=True), "Build metadata differs")

    def test_missing_build_id_rejected(self):
        metadata = self.metadata()
        metadata.pop("buildId")
        self.assertRejected(metadata, "lacks a build id")

    def test_non_object_metadata_rejected(self):
        with self.assertRaisesRegex(ValueError, "not a JSON object"):
            verify_build_metadata([], self.report())


if __name__ == "__main__":
    unittest.main()
