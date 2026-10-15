#!/usr/bin/env python3
"""Check real host binary parsing and available NDK links; this does not run Miri."""

import argparse
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from types import SimpleNamespace

from build_rustc_host import android_tools
from miri_build_support import compiler_identity, run, sha256, source_revision, validate_miri_source
from package_miri_runtime import inspect_library, safe_relative


def must_reject(operation, label):
    try:
        operation()
    except ValueError:
        print(f"Rejected {label}")
        return
    raise AssertionError(f"Incorrectly accepted {label}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--toolchain", type=Path, required=True)
    parser.add_argument("--ndk", type=Path)
    parser.add_argument("--miri-source", type=Path)
    parser.add_argument("--cmake", type=Path)
    args = parser.parse_args()
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
