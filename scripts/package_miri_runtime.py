#!/usr/bin/env python3
"""Validate and package a pinned native Miri adapter and its dependency closure."""

import argparse
from collections import deque
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import shutil
import struct
import subprocess
import sys
import tempfile

from miri_build_support import GUEST_TARGET, HOSTS, RUST_COMMIT, RUST_VERSION, run, sha256, source_revision, write_json

REPOSITORY = Path(__file__).resolve().parent.parent
WINDOWS_SYSTEM = {
    "advapi32.dll", "bcrypt.dll", "bcryptprimitives.dll", "cabinet.dll", "cfgmgr32.dll",
    "combase.dll", "comdlg32.dll", "crypt32.dll", "dbghelp.dll", "dnsapi.dll",
    "gdi32.dll", "imm32.dll", "iphlpapi.dll", "kernel32.dll", "msvcrt.dll", "ncrypt.dll",
    "netapi32.dll", "normaliz.dll", "ntdll.dll", "ole32.dll", "oleaut32.dll", "powrprof.dll",
    "propsys.dll", "psapi.dll", "rpcrt4.dll", "secur32.dll", "setupapi.dll", "shell32.dll",
    "shlwapi.dll", "user32.dll", "userenv.dll", "ucrtbase.dll", "version.dll", "winhttp.dll",
    "winmm.dll", "winspool.drv", "wintrust.dll", "ws2_32.dll", "wtsapi32.dll",
}


def cstring(data, offset, limit=None):
    if offset < 0 or offset >= len(data):
        raise ValueError("Invalid native binary string offset")
    end = data.find(b"\0", offset, limit)
    if end < 0:
        raise ValueError("Unterminated native binary string")
    return data[offset:end].decode("utf-8")


def inspect_elf(data):
    if data[:6] != b"\x7fELF\x02\x01":
        raise ValueError("Expected a little-endian 64-bit ELF library")
    header = struct.unpack_from("<16sHHIQQQIHHHHHH", data)
    if header[1] != 3:
        raise ValueError("ELF input must be a shared object")
    architecture = {62: "x64", 183: "arm64"}.get(header[2])
    if not architecture:
        raise ValueError("Unsupported ELF machine")
    segments = [struct.unpack_from("<IIQQQQQQ", data, header[5] + index * header[9])
                for index in range(header[10])]
    loads = [row for row in segments if row[0] == 1]
    dynamic = next((row for row in segments if row[0] == 2), None)
    if not dynamic:
        raise ValueError("ELF library has no dynamic section")
    entries = []
    for offset in range(dynamic[2], dynamic[2] + dynamic[5], 16):
        row = struct.unpack_from("<qQ", data, offset)
        if row[0] == 0:
            break
        entries.append(row)
    strings = next((value for tag, value in entries if tag == 5), None)
    if strings is None:
        raise ValueError("ELF dynamic string table is missing")
    containing = next((row for row in loads if row[3] <= strings < row[3] + row[5]), None)
    if not containing:
        raise ValueError("ELF dynamic strings do not belong to a load segment")
    string_offset = containing[2] + strings - containing[3]
    needed = [cstring(data, string_offset + value) for tag, value in entries if tag == 1]
    soname = next((cstring(data, string_offset + value) for tag, value in entries if tag == 14), None)
    rpaths = [cstring(data, string_offset + value) for tag, value in entries if tag in (15, 29)]
    return {"format": "elf", "architecture": architecture, "dependencies": needed,
            "soname": soname, "rpaths": rpaths, "loadAlignments": [row[7] for row in loads]}


def inspect_pe(data):
    header_offset = struct.unpack_from("<I", data, 60)[0]
    if data[header_offset:header_offset + 4] != b"PE\0\0":
        raise ValueError("Invalid PE header")
    header = struct.unpack_from("<HHIIIHH", data, header_offset + 4)
    architecture = {0x8664: "x64", 0xAA64: "arm64"}.get(header[0])
    if not architecture or not header[6] & 0x2000:
        raise ValueError("Expected a 64-bit Windows DLL")
    optional = header_offset + 24
    if struct.unpack_from("<H", data, optional)[0] != 0x20B:
        raise ValueError("Expected a PE32+ Windows DLL")
    sections = [struct.unpack_from("<8sIIIIIIHHI", data, optional + header[5] + index * 40)
                for index in range(header[1])]

    def file_offset(rva):
        row = next((row for row in sections if row[2] <= rva < row[2] + row[3]), None)
        if not row:
            raise ValueError("PE import RVA is outside the file sections")
        return row[4] + rva - row[2]

    needed = []
    count = struct.unpack_from("<I", data, optional + 108)[0]
    image_base = struct.unpack_from("<Q", data, optional + 24)[0]
    for index, entry_size in ((1, 20), (13, 32)):
        if count <= index:
            continue
        address, size = struct.unpack_from("<II", data, optional + 112 + index * 8)
        if not address:
            continue
        offset = file_offset(address)
        for cursor in range(offset, offset + size, entry_size):
            entry = struct.unpack_from("<" + "I" * (entry_size // 4), data, cursor)
            if not any(entry):
                break
            name_rva = entry[3] if index == 1 else entry[1]
            if index == 13 and not entry[0] & 1:
                name_rva -= image_base
            needed.append(cstring(data, file_offset(name_rva)))
    return {"format": "pe", "architecture": architecture, "dependencies": needed}


def inspect_macho(data):
    if data[:4] != b"\xcf\xfa\xed\xfe":
        raise ValueError("Package thin 64-bit Mach-O slices separately before creating an XCFramework")
    header = struct.unpack_from("<IiiIIIII", data)
    architecture = {0x1000007: "x64", 0x100000C: "arm64"}.get(header[1])
    if not architecture or header[3] != 6:
        raise ValueError("Expected a 64-bit Mach-O dynamic library")
    result = {"format": "macho", "architecture": architecture, "dependencies": [], "rpaths": []}
    cursor = 32
    for _ in range(header[4]):
        command, size = struct.unpack_from("<II", data, cursor)
        if size < 8 or cursor + size > len(data):
            raise ValueError("Invalid Mach-O load command")
        if command in (0xC, 0xD, 0x80000018, 0x8000001F, 0x80000023):
            string_offset = struct.unpack_from("<I", data, cursor + 8)[0]
            name = cstring(data, cursor + string_offset, cursor + size)
            if command == 0xD:
                result["installName"] = name
            else:
                result["dependencies"].append(name)
        elif command == 0x8000001C:
            string_offset = struct.unpack_from("<I", data, cursor + 8)[0]
            result["rpaths"].append(cstring(data, cursor + string_offset, cursor + size))
        elif command == 0x32:
            result["applePlatform"] = struct.unpack_from("<I", data, cursor + 8)[0]
            minimum = struct.unpack_from("<I", data, cursor + 12)[0]
            result["minimumOS"] = (minimum >> 16, (minimum >> 8) & 0xFF, minimum & 0xFF)
        cursor += size
    return result


def inspect_library(path, host):
    data = Path(path).read_bytes()
    if data.startswith(b"\x7fELF"):
        result = inspect_elf(data)
    elif data.startswith(b"MZ"):
        result = inspect_pe(data)
    else:
        result = inspect_macho(data)
    platform, architecture = HOSTS[host]
    expected_format = "pe" if platform == "windows" else "macho" if platform in ("ios", "macos") else "elf"
    if result["architecture"] != architecture or result["format"] != expected_format:
        raise ValueError(f"Wrong binary format or architecture for {host}: {path}")
    if platform == "android":
        if any(alignment < 16384 for alignment in result["loadAlignments"]):
            raise ValueError(f"Android library lacks 16 KiB load-segment alignment: {path}")
        if any(name.endswith(".so.6") or name.startswith("ld-linux") for name in result["dependencies"]):
            raise ValueError(f"Android cannot load glibc dependencies: {path}")
    if expected_format == "macho":
        expected_platform = 1 if platform == "macos" else 2 if host == "aarch64-apple-ios" else 7
        if result.get("applePlatform") != expected_platform:
            raise ValueError(f"Mach-O SDK platform does not match {host}: {path}")
    return result


def is_system_library(name, platform):
    if platform == "windows":
        lower = name.lower()
        return lower in WINDOWS_SYSTEM or lower.startswith(("api-ms-win-", "ext-ms-win-"))
    if platform == "android":
        return name in {"libc.so", "libdl.so", "libm.so", "liblog.so", "libandroid.so", "libz.so"}
    if platform == "linux":
        return name in {"libc.so.6", "libdl.so.2", "libm.so.6", "libpthread.so.0", "librt.so.1",
                        "libresolv.so.2", "libutil.so.1", "ld-linux-x86-64.so.2", "ld-linux-aarch64.so.1"}
    return name.startswith(("/usr/lib/", "/System/Library/"))


def safe_relative(value):
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "\\" in value or ":" in value:
        raise ValueError(f"Unsafe package relative path: {value}")
    return path


def collect_libraries(args, build_info):
    platform, _ = HOSTS[args.native_host]
    adapter = Path(build_info["adapter"]["path"])
    expected_name = "qfli_miri.dll" if platform == "windows" else "libqfli_miri.dylib" if platform in ("macos", "ios") else "libqfli_miri.so"
    if adapter.name != expected_name:
        raise ValueError(f"Expected the session adapter {expected_name}, not another compiler library")
    if sha256(adapter) != build_info["adapter"]["sha256"]:
        raise ValueError("Adapter differs from its pinned build record")
    compiler_records = build_info["compilerLibraries"]
    search = [adapter.parent, *args.compiler_lib_directory]
    search += list(dict.fromkeys(Path(row["path"]).parent for row in compiler_records))
    queue = deque([(adapter.name, adapter, "adapter")])
    if args.codegen_backend:
        if "rustc_codegen" not in args.codegen_backend.name or not any(
            row["name"] == args.codegen_backend.name and row["sha256"] == sha256(args.codegen_backend)
            for row in compiler_records
        ):
            raise ValueError("Codegen backend is not part of the matching compiler build")
        queue.append((args.codegen_backend.name, args.codegen_backend, "backend"))
        search.append(args.codegen_backend.parent)
    elif platform in ("android", "ios"):
        raise ValueError("Source-built mobile hosts require their matching --codegen-backend")
    libraries = {}
    while queue:
        name, path, role = queue.popleft()
        safe_relative(name)
        key = name.lower() if platform == "windows" else name
        if key in libraries:
            if sha256(path) != sha256(libraries[key]["source"]):
                raise ValueError(f"Conflicting native libraries with the same name: {name}")
            continue
        binary = inspect_library(path, args.native_host)
        if platform == "ios":
            deployment = tuple(int(part) for part in args.apple_deployment_target.split("."))
            deployment = (deployment + (0, 0))[:3]
            if binary["minimumOS"] > deployment:
                raise ValueError(f"Framework was built for a newer iOS release than {args.apple_deployment_target}")
        if platform in ("android", "linux") and any("/" in needed or "\\" in needed for needed in binary["dependencies"]):
            raise ValueError(f"ELF dependencies must use relocatable SONAMEs: {name}")
        if "rustc_driver" in name or "rustc_codegen" in name or name.startswith(("libstd-", "std-", "libLLVM", "LLVM")):
            if not any(row["name"] == path.name and row["sha256"] == sha256(path) for row in compiler_records):
                raise ValueError(f"Compiler library differs from the pinned build record: {name}")
        libraries[key] = {"name": name, "source": path, "role": role, "binary": binary}
        for needed in binary["dependencies"]:
            if is_system_library(needed, platform):
                continue
            basename = PurePosixPath(needed).name
            candidates = [directory / basename for directory in search]
            if platform in ("macos", "ios") and needed.startswith("@loader_path/"):
                candidates.insert(0, path.parent / needed.removeprefix("@loader_path/"))
            if Path(needed).is_absolute():
                candidates.insert(0, Path(needed))
            dependency = next((candidate for candidate in candidates if candidate.is_file()), None)
            if not dependency:
                raise ValueError(f"Missing native dependency {needed} required by {name}")
            queue.append((basename, dependency, "dependency"))
    if not any("rustc_driver" in row["name"] for row in libraries.values()):
        raise ValueError("The adapter dependency closure does not contain a real rustc driver")
    return list(libraries.values())


def guest_files(args):
    folder = args.guest_sysroot / "lib/rustlib" / GUEST_TARGET / "lib"
    files = sorted(folder.glob("*.rlib"))
    if not any(path.name.startswith("libstd-") for path in files) or not any(path.name.startswith("libcore-") for path in files):
        raise ValueError(f"Missing interpreted standard-library data: {folder}")
    provenance = args.guest_build_info or args.guest_sysroot / "miri-sysroot.json"
    if not provenance.is_file():
        raise ValueError("Supply --guest-build-info from cargo-miri setup or a verified legacy OHOS manifest")
    info = json.loads(provenance.read_text(encoding="utf-8"))
    if info.get("rustVersion") != RUST_VERSION or info.get("rustCommit") != RUST_COMMIT or info.get("guestTarget") != GUEST_TARGET:
        raise ValueError("Guest MIR identity does not match the compiler revision and interpreted target")
    if info.get("schemaVersion") != 1 and not info.get("encodedMir"):
        raise ValueError("Guest provenance does not identify MIR-encoded standard libraries")
    recorded = {entry["path"]: entry["sha256"] for entry in info["files"]}
    for file in files:
        relative = "sysroot/" + file.relative_to(args.guest_sysroot).as_posix()
        if recorded.get(relative) != sha256(file):
            raise ValueError(f"Guest standard library differs from its build record: {file.name}")
    return [(path, "sysroot/" + path.relative_to(args.guest_sysroot).as_posix()) for path in files]


def license_files(args, metadata):
    source_revision(args.rust_source)
    files = [(args.rust_source / name, f"licenses/rust/{name}")
             for name in ("COPYRIGHT", "LICENSE-APACHE", "LICENSE-MIT", "license-metadata.json")]
    files += [(args.rust_source / "src/tools/miri" / name, f"licenses/miri/{name}")
              for name in ("LICENSE-APACHE", "LICENSE-MIT")]
    resolved = {row["id"] for row in metadata["resolve"]["nodes"]}
    notices = []
    for package in sorted(metadata["packages"], key=lambda row: (row["name"], row["version"])):
        if package["id"] not in resolved:
            continue
        directory = Path(package["manifest_path"]).parent
        licenses = [path for path in directory.iterdir() if path.is_file()
                    and re.fullmatch(r"(LICENSE|LICENCE|COPYING|NOTICE)([._-].*)?", path.name)]
        if package.get("license_file"):
            licenses.append(directory / package["license_file"])
        for path in sorted(set(licenses)):
            files.append((path, f"licenses/dependencies/{package['name']}-{package['version']}/{path.name}"))
        notices.append({"name": package["name"], "version": package["version"], "license": package.get("license")})
    for source, relative in files:
        safe_relative(relative)
        if not source.is_file():
            raise ValueError(f"Missing dependency/Rust license: {source}")
    return files, notices


def framework_name(name):
    if "rustc_driver" in name:
        return "qfli_rustc_driver"
    if "rustc_codegen_cranelift" in name:
        return "qfli_codegen_cranelift"
    if name.startswith("libstd-"):
        return "qfli_rust_std"
    if name.startswith("libLLVM"):
        return "qfli_llvm"
    stem = name.removesuffix(".dylib").removeprefix("lib")
    return re.sub(r"[^A-Za-z0-9_]", "_", stem)


def package_frameworks(libraries, destination, args):
    if sys.platform != "darwin":
        raise ValueError("Apple frameworks must be repaired and signed on macOS with Xcode")
    names = {row["name"]: framework_name(row["name"]) for row in libraries}
    if len(set(names.values())) != len(names):
        raise ValueError("Framework executable names collide after normalization")
    platform, _ = HOSTS[args.native_host]
    for row in libraries:
        name = names[row["name"]]
        row["path"] = f"{name}.framework/{name}"
        framework = destination / f"{name}.framework"
        framework.mkdir()
        executable = framework / name
        shutil.copy2(row["source"], executable)
        executable.chmod(0o755)
        plist = {
            "CFBundleIdentifier": f"com.azurekiln.qfli.runtime.{name.replace('_', '-').lower()}",
            "CFBundleExecutable": name, "CFBundleName": name, "CFBundlePackageType": "FMWK",
            "CFBundleShortVersionString": RUST_VERSION, "CFBundleVersion": RUST_VERSION,
            "CFBundleSupportedPlatforms": ["MacOSX" if platform == "macos" else "iPhoneOS"
                                           if args.native_host == "aarch64-apple-ios" else "iPhoneSimulator"],
        }
        if platform == "ios":
            plist["MinimumOSVersion"] = args.apple_deployment_target
        with (framework / "Info.plist").open("wb") as stream:
            plistlib.dump(plist, stream)
        command = ["install_name_tool", "-id", f"@rpath/{row['path']}"]
        for needed in row["binary"]["dependencies"]:
            if not is_system_library(needed, platform):
                target = names[PurePosixPath(needed).name]
                command += ["-change", needed, f"@rpath/{target}.framework/{target}"]
        if "@loader_path/.." not in row["binary"]["rpaths"]:
            command += ["-add_rpath", "@loader_path/.."]
        run([*command, executable])
        run(["codesign", "--force", "--sign", args.sign_identity, framework])
        run(["codesign", "--verify", "--strict", framework])
        inspect_library(executable, args.native_host)


def install_android(libraries, staged, args, previous):
    _, architecture = HOSTS[args.native_host]
    abi = "arm64-v8a" if architecture == "arm64" else "x86_64"
    directory = args.project_root / "android/app/src/main/jniLibs" / abi
    directory.mkdir(parents=True, exist_ok=True)
    current = {row["name"] for row in libraries}
    for row in previous:
        relative = safe_relative(row["path"])
        if len(relative.parts) != 1:
            raise ValueError("Invalid previously generated Android native library path")
        obsolete = directory / relative.name
        if row["name"] not in current and obsolete.is_file() and sha256(obsolete) == row["sha256"]:
            obsolete.unlink()
    for row in libraries:
        shutil.copy2(staged / row["path"], directory / row["name"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-info", type=Path, required=True)
    parser.add_argument("--guest-sysroot", type=Path, required=True)
    parser.add_argument("--guest-build-info", type=Path)
    parser.add_argument("--rust-source", type=Path, required=True)
    parser.add_argument("--compiler-lib-directory", type=Path, action="append", default=[])
    parser.add_argument("--codegen-backend", type=Path)
    parser.add_argument("--project-root", type=Path, default=REPOSITORY)
    parser.add_argument("--sign-identity", default="-")
    parser.add_argument("--apple-deployment-target", default="13.0")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    args.project_root = args.project_root.resolve()
    info = json.loads(args.build_info.read_text(encoding="utf-8"))
    args.native_host = info["nativeHost"]
    if info.get("schemaVersion") != 1 or info.get("rustVersion") != RUST_VERSION or info.get("rustCommit") != RUST_COMMIT:
        raise ValueError("Build record is not for the pinned Rust compiler")
    if args.native_host not in HOSTS or HOSTS[args.native_host][0] == "ohos":
        raise ValueError("Use package_miri_ohos.ps1 for existing OHOS schema-1 packages")
    platform, architecture = HOSTS[args.native_host]
    dependency_info = info["dependencyMetadata"]
    metadata_path = Path(dependency_info["path"])
    if sha256(metadata_path) != dependency_info["sha256"]:
        raise ValueError("Dependency metadata differs from the adapter build record")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    libraries = collect_libraries(args, info)
    assets = guest_files(args)
    licenses, notices = license_files(args, metadata)
    assets += licenses
    if args.validate_only:
        print(f"Validated {args.native_host}: {len(libraries)} native libraries, {len(assets)} MIR/license files")
        return

    runtime_root = args.project_root / "native/build/runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)
    package_key = args.native_host if platform == "ios" else f"{platform}-{architecture}"
    destination = runtime_root / package_key
    previous = []
    if platform == "android" and (destination / "native-package.json").is_file():
        previous = json.loads((destination / "native-package.json").read_text())["nativeLibraries"]
    with tempfile.TemporaryDirectory(prefix=".package-", dir=runtime_root) as temporary:
        staged = Path(temporary)
        if platform in ("ios", "macos"):
            package_frameworks(libraries, staged, args)
        else:
            for row in libraries:
                row["path"] = row["name"]
                shutil.copy2(row["source"], staged / row["path"])
        native_entries = [{"name": row["name"], "path": row["path"], "role": row["role"],
                           "size": (staged / row["path"]).stat().st_size,
                           "sha256": sha256(staged / row["path"])} for row in libraries]
        manifest = {
            "schemaVersion": 2, "platform": platform, "architecture": architecture,
            "rustVersion": RUST_VERSION, "rustCommit": RUST_COMMIT,
            "nativeHost": args.native_host, "guestTarget": GUEST_TARGET,
            "libraryName": next(row["path"] for row in libraries if row["role"] == "adapter"),
            "nativeLibraries": native_entries, "files": [], "dependencies": notices,
        }
        asset_root = args.project_root / "assets/miri"
        asset_root.mkdir(parents=True, exist_ok=True)
        for source, relative in assets:
            digest = sha256(source)
            name = digest + ".bin"
            shutil.copy2(source, asset_root / name)
            manifest["files"].append({"path": relative, "asset": name,
                                      "size": source.stat().st_size, "sha256": digest})
        manifest["id"] = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        write_json(staged / "native-package.json", manifest)
        if platform in ("windows", "linux"):
            names = ";".join(row["path"] for row in libraries)
            if any(";" in row["path"] for row in libraries) or any(character in names for character in '\\"$\n\r'):
                raise ValueError("Native library name cannot be represented safely in CMake")
            (staged / "native-libraries.cmake").write_text(f'set(QFLI_RUNTIME_LIBRARIES "{names}")\n', encoding="utf-8")
        if destination.exists():
            if destination.is_symlink() or destination.parent.resolve() != runtime_root.resolve():
                raise ValueError("Generated runtime destination is outside its managed directory")
            shutil.rmtree(destination)
        shutil.copytree(staged, destination)
        if platform == "android":
            install_android(libraries, staged, args, previous)
        manifest_path = asset_root / f"manifest.{platform}-{architecture}.json"
        write_json(manifest_path, manifest)
    print(f"Packaged {args.native_host}: {destination}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    try:
        main()
    except (KeyError, OSError, ValueError, struct.error, subprocess.CalledProcessError) as error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(2)
