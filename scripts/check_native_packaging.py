#!/usr/bin/env python3
"""Check packaged OHOS assets, host binary parsing and NDK links without running Miri."""

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from types import SimpleNamespace

from build_rustc_host import android_tools
from miri_build_support import (GUEST_TARGET, RUST_COMMIT, RUST_VERSION,
                                compiler_identity, run, sha256, source_revision,
                                validate_miri_source)
from package_miri_runtime import inspect_library, safe_relative


def must_reject(operation, label):
    try:
        operation()
    except ValueError:
        print(f"Rejected {label}")
        return
    raise AssertionError(f"Incorrectly accepted {label}")


def check_ohos_assets(asset_root, native_root=None):
    """Audit both schema-1 architectures, sharing only content-addressed data."""
    manifests = {}
    reports = []
    for architecture, host, abi in (
        ("arm64", "aarch64-unknown-linux-ohos", "arm64-v8a"),
        ("x64", "x86_64-unknown-linux-ohos", "x86_64"),
    ):
        manifest_path = asset_root / f"manifest.ohos-{architecture}.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (not isinstance(manifest, dict)
                or type(manifest.get("schemaVersion")) is not int
                or manifest["schemaVersion"] != 1
                or manifest.get("rustVersion") != RUST_VERSION
                or manifest.get("rustCommit") != RUST_COMMIT
                or manifest.get("nativeHost") != host
                or manifest.get("guestTarget") != GUEST_TARGET
                or not isinstance(manifest.get("id"), str)
                or not re.fullmatch(r"[a-f0-9]{64}", manifest["id"])
                or not isinstance(manifest.get("files"), list)
                or not manifest["files"]):
            raise ValueError(f"Invalid or incompatible OHOS manifest: {manifest_path}")
        paths = set()
        for entry in manifest["files"]:
            if (not isinstance(entry, dict)
                    or not isinstance(entry.get("path"), str)
                    or not isinstance(entry.get("sha256"), str)
                    or not re.fullmatch(r"[a-f0-9]{64}", entry["sha256"])
                    or entry.get("asset") != f"{entry['sha256']}.bin"
                    or type(entry.get("size")) is not int
                    or entry["size"] < 0):
                raise ValueError(f"Invalid OHOS asset entry in {manifest_path}")
            relative = safe_relative(entry["path"])
            if relative.as_posix() != entry["path"] or entry["path"] in paths:
                raise ValueError(f"Duplicate or noncanonical OHOS asset path: {entry['path']}")
            paths.add(entry["path"])
            asset = asset_root / entry["asset"]
            if not asset.is_file():
                raise ValueError(f"Missing {host} asset for {entry['path']}: {asset}")
            if asset.stat().st_size != entry["size"] or sha256(asset) != entry["sha256"]:
                raise ValueError(f"Size or SHA-256 mismatch for {host} asset: {asset}")
        libraries = manifest.get("nativeLibraries")
        if not isinstance(libraries, list) or not libraries:
            raise ValueError(f"Missing native library inventory: {manifest_path}")
        names = set()
        for entry in libraries:
            if (not isinstance(entry, dict)
                    or not isinstance(entry.get("name"), str)
                    or len(safe_relative(entry["name"]).parts) != 1
                    or not isinstance(entry.get("sha256"), str)
                    or not re.fullmatch(r"[a-f0-9]{64}", entry["sha256"])
                    or entry["name"] in names):
                raise ValueError(f"Invalid OHOS native library entry: {manifest_path}")
            names.add(entry["name"])
        if "libqfli_miri.so" not in names:
            raise ValueError(f"Missing OHOS adapter inventory: {manifest_path}")
        if native_root is not None:
            system = {"libc.so", "libdl.so", "libm.so", "libpthread.so", "librt.so"}
            for entry in libraries:
                library = native_root / abi / entry["name"]
                if not library.is_file() or sha256(library) != entry["sha256"]:
                    raise ValueError(f"Missing or changed {host} native library: {library}")
                info = inspect_library(library, host)
                missing = set(info["dependencies"]) - names - system
                if missing:
                    raise ValueError(f"Unpackaged {host} dependencies of {library}: {sorted(missing)}")
        manifests[architecture] = manifest
        reports.append({"architecture": architecture, "nativeHost": host,
                        "id": manifest["id"], "files": len(paths),
                        "nativeLibraries": len(names),
                        "nativeLibrariesChecked": native_root is not None})
    legacy = asset_root / "manifest.json"
    if legacy.exists() and json.loads(legacy.read_text(encoding="utf-8")) != manifests["arm64"]:
        raise ValueError("Legacy OHOS manifest must preserve the ARM64 runtime identity")
    if manifests["arm64"]["id"] == manifests["x64"]["id"]:
        raise ValueError("OHOS architectures must have distinct runtime content IDs")
    return reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--toolchain", type=Path)
    parser.add_argument("--ndk", type=Path)
    parser.add_argument("--miri-source", type=Path)
    parser.add_argument("--cmake", type=Path)
    parser.add_argument("--ohos-assets", type=Path,
                        help="Audit both architecture manifests and every flattened asset")
    parser.add_argument("--ohos-libraries", type=Path,
                        help="Also audit OHOS entry/libs native hashes, ELF hosts and dependency closure")
    args = parser.parse_args()
    if args.ohos_libraries and not args.ohos_assets:
        parser.error("--ohos-libraries requires --ohos-assets")
    if not args.toolchain and not args.ohos_assets:
        parser.error("provide --toolchain or --ohos-assets")
    if args.ohos_assets:
        for report in check_ohos_assets(args.ohos_assets, args.ohos_libraries):
            print(json.dumps(report, sort_keys=True))
        print("OHOS asset audit passed; packaged-device execution remains a separate gate")
    if not args.toolchain:
        return
    # CMake resolves input files from its generated source directory, rather
    # than the caller's working directory.
    args.toolchain = args.toolchain.resolve(strict=True)
    identity = compiler_identity(args.toolchain)
    if args.miri_source:
        validate_miri_source(args.miri_source)
        print("Pinned upstream Miri source fingerprint matches")
    must_reject(lambda: safe_relative("../runtime.dll"), "escaping native library path")
    must_reject(lambda: safe_relative("C:/runtime.dll"), "absolute Windows path")
    root = Path(__file__).resolve().parent.parent / "native/build"
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="qfli-sdk-check-", dir=root) as temporary:
        folder = Path(temporary)
        must_reject(lambda: source_revision(folder, complete=True), "incomplete bootstrap source")
        if not args.ndk:
            print("Skipped NDK links and LLVM comparison: --ndk was not provided")
            return
        for target in ("aarch64-linux-android", "x86_64-linux-android"):
            stage = folder / target
            (stage / "bin").mkdir(parents=True)
            tools = android_tools(SimpleNamespace(ndk=args.ndk, android_api=21,
                                                  build_root=stage, native_host=target), identity["host"])
            library = stage / "libqfli_sdk_link_probe.so"
            run([tools["linker"], "-shared", "-x", "c", "-", "-o", library],
                input=b"int qfli_sdk_link_probe(void) { return 1; }\n")
            info = inspect_library(library, target)
            must_reject(lambda: inspect_library(library, "x86_64-pc-windows-gnu"), f"{target} ELF as Windows DLL")
            print(f"NDK {target}: SDK link succeeded, {len(info['loadAlignments'])} aligned ELF load segments")
        if "windows" in identity["host"]:
            readobj = Path(tools["ar"]).with_name("llvm-readobj.exe")
            count = 0
            for library in sorted((args.toolchain / "bin").glob("*.dll")):
                parsed = inspect_library(library, identity["host"])
                output = run([readobj, "--coff-imports", library], capture_output=True, text=True).stdout
                expected = re.findall(r"^  Name: (.+)$", output, re.MULTILINE)
                if parsed["dependencies"] != expected:
                    raise AssertionError(f"PE import parser differs from LLVM: {library}")
                count += len(expected)
                print(f"Windows {library.name}: {len(expected)} imports match LLVM")
            if not count:
                raise AssertionError("No real Windows compiler DLL imports were checked")
            if args.cmake:
                cmake_source = folder / "cmake-install"
                cmake_source.mkdir()
                (cmake_source / "CMakeLists.txt").write_text('''cmake_minimum_required(VERSION 3.13)
project(qfli_runtime_install_check NONE)
include("${QFLI_RUNTIME_MODULE}")
set(FLUTTER_TARGET_PLATFORM windows-x64)
set(QFLI_NATIVE_RUNTIME_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/input")
file(MAKE_DIRECTORY "${QFLI_NATIVE_RUNTIME_ROOT}/windows-x64")
configure_file("${QFLI_PACKAGE_LIBRARY}" "${QFLI_NATIVE_RUNTIME_ROOT}/windows-x64/dependency.dll" COPYONLY)
if(QFLI_TEST_MISSING)
  file(WRITE "${QFLI_NATIVE_RUNTIME_ROOT}/windows-x64/native-libraries.cmake" "set(QFLI_RUNTIME_LIBRARIES missing.dll)\\n")
else()
  file(WRITE "${QFLI_NATIVE_RUNTIME_ROOT}/windows-x64/native-libraries.cmake" "set(QFLI_RUNTIME_LIBRARIES dependency.dll)\\n")
endif()
qfli_install_runtime(windows "${CMAKE_CURRENT_BINARY_DIR}/installed")
''', encoding="utf-8")
                std = next((args.toolchain / "bin").glob("std-*.dll"))
                module = Path(__file__).resolve().parent.parent / "native/runtime_bundle.cmake"
                binary = cmake_source / "build"
                command = [args.cmake, "-S", cmake_source, "-B", binary, "-G", "Ninja",
                           f"-DQFLI_RUNTIME_MODULE={module}", f"-DQFLI_PACKAGE_LIBRARY={std}"]
                ninja = args.cmake.with_name("ninja.exe")
                if ninja.is_file():
                    command += [f"-DCMAKE_MAKE_PROGRAM={ninja}"]
                run(command, capture_output=True, text=True)
                run([args.cmake, "--install", binary, "--component", "Runtime"], capture_output=True, text=True)
                if sha256(binary / "installed/dependency.dll") != sha256(std):
                    raise AssertionError("CMake runtime install changed the native dependency")
                rejected = subprocess.run([str(item) for item in [*command, "-DQFLI_TEST_MISSING=ON"]],
                                          capture_output=True, text=True)
                if not rejected.returncode or "Packaged Rust runtime library is missing" not in rejected.stderr:
                    raise AssertionError("CMake did not reject a missing packaged dependency")
                print("CMake: installed a real DLL unchanged and rejected a missing package dependency")
        else:
            print("Skipped Windows PE comparison on this build host")
    print("Native build/package checks passed; compiler/interpreter execution requires separate tests")


if __name__ == "__main__":
    try:
        main()
    except (AssertionError, OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(1)
