#!/usr/bin/env python3
"""Bootstrap matching compiler-private libraries for Android and iOS hosts."""

import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import uuid

from miri_build_support import (
    HOSTS, RUST_COMMIT, RUST_VERSION, SOURCE_SHA256, compiler_identity,
    run, sha256, source_revision, write_json,
)

MOBILE_HOSTS = [host for host, (platform, _) in HOSTS.items() if platform in ("android", "ios")]


def executable(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError(f"Missing executable: {path}")
    return path


def wrapper(path, program, flags):
    path = Path(path)
    if os.name == "nt":
        path = path.with_suffix(".cmd")
        # These SDK paths and generated flags cannot contain cmd expansion syntax.
        if any(any(character in str(item) for character in '%!\r\n"') for item in [program, *flags]):
            raise ValueError("Windows SDK paths may not contain cmd expansion characters")
        arguments = " ".join(f'"{item}"' for item in [program, *flags])
        path.write_text(f"@echo off\n{arguments} %*\n", encoding="utf-8")
    else:
        command = " ".join(shlex.quote(str(item)) for item in [program, *flags])
        path.write_text(f'#!/bin/sh\nexec {command} "$@"\n', encoding="utf-8")
        path.chmod(0o755)
    return path


def android_tools(args, build_host):
    if not args.ndk:
        raise ValueError("Android hosts require --ndk pointing to a complete NDK installation")
    ndk = args.ndk.resolve()
    if not (ndk / "source.properties").is_file():
        raise ValueError("The selected NDK is incomplete (source.properties is missing)")
    if args.android_api < 21:
        raise ValueError("64-bit Android hosts require API 21 or later")
    if "windows" in build_host:
        tag = "windows-x86_64"
    elif "apple-darwin" in build_host:
        tag = "darwin-x86_64"
    elif build_host == "x86_64-unknown-linux-gnu":
        tag = "linux-x86_64"
    else:
        raise ValueError(f"No NDK prebuilt toolchain for build host {build_host}")
    prebuilt = ndk / "toolchains/llvm/prebuilt" / tag
    suffix = ".exe" if os.name == "nt" else ""
    clang = executable(prebuilt / "bin" / f"clang{suffix}")
    clangxx = executable(prebuilt / "bin" / f"clang++{suffix}")
    sysroot = prebuilt / "sysroot"
    target = f"{args.native_host}{args.android_api}"
    flags = [f"--target={target}", f"--sysroot={sysroot}", "-fPIC"]
    return {
        "cc": wrapper(args.build_root / "bin/target-clang", clang, flags),
        "cxx": wrapper(args.build_root / "bin/target-clang++", clangxx, flags),
        "linker": wrapper(args.build_root / "bin/target-linker", clang,
                          [*flags, "-Wl,-z,max-page-size=16384"]),
        "ar": executable(prebuilt / "bin" / f"llvm-ar{suffix}"),
        "ranlib": executable(prebuilt / "bin" / f"llvm-ranlib{suffix}"),
        "sdk": str(ndk), "apiLevel": args.android_api,
    }


def apple_tools(args, build_host):
    if sys.platform != "darwin" or not build_host.endswith("apple-darwin"):
        raise ValueError("iOS compiler hosts must be built on macOS with Xcode")
    simulator = args.native_host != "aarch64-apple-ios"
    sdk_name = "iphonesimulator" if simulator else "iphoneos"
    sdk = run(["xcrun", "--sdk", sdk_name, "--show-sdk-path"],
              capture_output=True, text=True).stdout.strip()

    def find(tool):
        return executable(run(["xcrun", "--sdk", sdk_name, "--find", tool],
                              capture_output=True, text=True).stdout.strip())

    architecture = "arm64" if args.native_host.startswith("aarch64") else "x86_64"
    clang_target = f"{architecture}-apple-ios{args.ios_deployment_target}"
    if simulator:
        clang_target += "-simulator"
    flags = [f"--target={clang_target}", "-isysroot", sdk]
    os.environ["SDKROOT"] = sdk
    os.environ["IPHONEOS_DEPLOYMENT_TARGET"] = args.ios_deployment_target
    return {
        "cc": wrapper(args.build_root / "bin/target-clang", find("clang"), flags),
        "cxx": wrapper(args.build_root / "bin/target-clang++", find("clang++"), flags),
        "linker": wrapper(args.build_root / "bin/target-linker", find("clang"), flags),
        "ar": find("ar"), "ranlib": find("ranlib"),
        "sdk": sdk, "deploymentTarget": args.ios_deployment_target,
    }


def complete_source(args):
    if args.source:
        source = args.source.resolve()
    else:
        archive = args.build_root / f"rustc-{RUST_VERSION}-src.tar.xz"
        if not archive.exists():
            if not args.download_source:
                raise ValueError("Supply complete --source or explicitly use --download-source")
            partial = archive.with_suffix(".partial")
            with urllib.request.urlopen(
                f"https://static.rust-lang.org/dist/rustc-{RUST_VERSION}-src.tar.xz"
            ) as response, partial.open("wb") as destination:
                shutil.copyfileobj(response, destination)
            if sha256(partial) != SOURCE_SHA256:
                raise ValueError("Downloaded pinned Rust source checksum does not match")
            partial.replace(archive)
        if sha256(archive) != SOURCE_SHA256:
            raise ValueError("Cached pinned Rust source checksum does not match")
        source = args.build_root / f"rustc-{RUST_VERSION}-src"
        marker = source / ".qfli-source-sha256"
        if not marker.is_file() or marker.read_text().strip() != SOURCE_SHA256:
            # An interrupted extraction must never become the next build's source.
            with tempfile.TemporaryDirectory(prefix="source.", dir=args.build_root) as temporary:
                staging = Path(temporary)
                with tarfile.open(archive) as bundle:
                    bundle.extractall(staging, filter="data")
                extracted = staging / source.name
                source_revision(extracted, complete=True)
                (extracted / marker.name).write_text(SOURCE_SHA256 + "\n", encoding="ascii")
                if source.exists():
                    previous = source.with_name(f"{source.name}.incomplete-{uuid.uuid4().hex[:8]}")
                    source.rename(previous)
                extracted.rename(source)
    source_revision(source, complete=True)
    return source


def bootstrap_config(args, build_host, tools):
    def quote(value):
        return json.dumps(str(value).replace("\\", "/"))

    lines = [
        'change-id = "ignore"', "", "[build]", 'description = ""', f"build = {quote(build_host)}",
        f"host = [{quote(args.native_host)}]", f"target = [{quote(args.native_host)}]",
        f"build-dir = {quote(args.build_root / 'build')}",
        f"rustc = {quote(args.toolchain / 'bin' / ('rustc.exe' if os.name == 'nt' else 'rustc'))}",
        f"cargo = {quote(args.toolchain / 'bin' / ('cargo.exe' if os.name == 'nt' else 'cargo'))}",
        f"jobs = {args.jobs}", "submodules = false", "local-rebuild = true",
        "optimized-compiler-builtins = false", "sanitizers = false", "profiler = false", "",
        "[rust]", 'channel = "stable"', "download-rustc = false",
        'codegen-backends = ["cranelift"]', "jemalloc = false", "llvm-tools = false",
        "llvm-bitcode-linker = false", "lld = false", 'lto = "off"',
        'llvm-libunwind = "no"', "debuginfo-level = 0", "", "[llvm]",
        "download-ci-llvm = false", "", f"[target.{args.native_host}]",
        *[f"{name} = {quote(tools[name])}" for name in ("cc", "cxx", "linker", "ar", "ranlib")],
        "crt-static = false", 'rustflags = ["-C", "link-arg=-Wl,-rpath,@loader_path", "-C", "link-arg=-Wl,-headerpad_max_install_names"]'
        if "apple" in args.native_host else 'rustflags = ["-C", "link-arg=-Wl,-rpath,$ORIGIN"]',
    ]
    if build_host == "x86_64-pc-windows-gnu":
        lld = executable(args.toolchain / "lib/rustlib" / build_host / "bin/rust-lld.exe")
        lines += ["", f"[target.{build_host}]", f"linker = {quote(lld)}",
                  'rustflags = ["-C", "linker-flavor=ld.lld", "-C", "link-self-contained=yes"]']
    return "\n".join(lines) + "\n"


def require_bootstrap_inputs(toolchain, native_host, build_host):
    libraries = Path(toolchain) / "lib/rustlib" / native_host / "lib"
    if not any(libraries.glob("libcore-*.rlib")) or not any(libraries.glob("libstd-*.rlib")):
        raise ValueError(
            f"Build toolchain is missing the matching {native_host} rust-std bootstrap input; "
            "install the pinned target standard library into the build toolchain before bootstrap"
        )
    private = Path(toolchain) / "lib/rustlib" / build_host / "lib"
    if any(private.glob("librustc_driver_impl-*.rmeta")):
        raise ValueError(
            "Bootstrap requires a clean compiler toolchain without rustc-dev private libraries; "
            "use a separate minimal pinned toolchain so source-built metadata cannot conflict"
        )


def build_embedded_backend(args, source, private, runtime, tools, environment):
    target_lib = private / "lib/rustlib" / args.native_host / "lib"
    backend_environment = dict(environment, CARGO_TARGET_DIR=str(args.build_root / "backend-target"))
    backend_environment["CARGO_BUILD_JOBS"] = str(args.jobs)
    flags = [
        f"--sysroot={private}", "-Cprefer-dynamic", "-Zdual-proc-macros",
        "-C", f"linker={tools['linker']}", "-L", f"native={target_lib}",
    ]
    if "apple" in args.native_host:
        flags += ["-C", "link-arg=-Wl,-rpath,@loader_path",
                  "-C", "link-arg=-Wl,-headerpad_max_install_names"]
    backend_environment["CARGO_ENCODED_RUSTFLAGS"] = "\x1f".join(flags)
    command = [args.toolchain / "bin" / ("cargo.exe" if os.name == "nt" else "cargo"),
               "-Zdual-proc-macros", "rustc", "--manifest-path",
               source / "compiler/rustc_codegen_cranelift/Cargo.toml",
               "--target", args.native_host, "--locked", "--offline", "--release", "--lib",
               "--message-format=json"]
    artifacts = set()
    with (args.build_root / "embedded-backend.log").open("w", encoding="utf-8", buffering=1) as log:
        process = subprocess.Popen([str(item) for item in command], cwd=source,
                                   env=backend_environment, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True)
        for line in process.stdout:
            log.write(line)
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                print(line, end="", flush=True)
                continue
            if message.get("reason") == "compiler-message":
                print(message["message"].get("rendered", ""), end="", flush=True)
            if (message.get("reason") == "compiler-artifact"
                    and message.get("target", {}).get("name") == "rustc_codegen_cranelift"):
                artifacts.update(Path(path) for path in message["filenames"]
                                 if Path(path).suffix in (".so", ".dylib"))
        if process.wait() != 0:
            raise RuntimeError("Embedded backend compilation failed; see embedded-backend.log")
    if len(artifacts) != 1:
        raise ValueError("Cargo did not report exactly one native Cranelift backend")
    backend = artifacts.pop()
    destination = runtime / "lib/rustlib" / args.native_host / "codegen-backends"
    destination.mkdir(parents=True, exist_ok=True)
    installed = destination / f"librustc_codegen_cranelift-{RUST_VERSION}{backend.suffix}"
    shutil.copy2(backend, installed)
    return installed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-host", choices=MOBILE_HOSTS, required=True)
    parser.add_argument("--toolchain", type=Path, required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--download-source", action="store_true")
    parser.add_argument("--build-root", type=Path, required=True)
    parser.add_argument("--ndk", type=Path)
    parser.add_argument("--android-api", type=int, default=21)
    parser.add_argument("--ios-deployment-target", default="13.0")
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--configure-only", action="store_true")
    args = parser.parse_args()
    args.toolchain = args.toolchain.resolve()
    args.build_root = args.build_root.resolve()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    if args.source and args.build_root.is_relative_to(args.source.resolve()):
        parser.error("--build-root must be outside the Rust source checkout")
    fields = compiler_identity(args.toolchain)
    args.build_root.mkdir(parents=True, exist_ok=True)
    (args.build_root / "bin").mkdir(exist_ok=True)
    source = complete_source(args)
    tools = (android_tools(args, fields["host"]) if "android" in args.native_host
             else apple_tools(args, fields["host"]))
    config = args.build_root / "bootstrap.toml"
    config.write_text(bootstrap_config(args, fields["host"], tools), encoding="utf-8")
    if args.configure_only:
        print(f"Configured {args.native_host}: {config}; no runtime was built")
        return

    require_bootstrap_inputs(args.toolchain, args.native_host, fields["host"])
    environment = dict(os.environ, RUSTC_BOOTSTRAP="1", CARGO_HOME=str(args.build_root / "cargo"))
    environment["PATH"] = str(args.toolchain / "bin") + os.pathsep + environment.get("PATH", "")
    for key in ("RUSTC", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER", "RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS"):
        environment.pop(key, None)
    if fields["host"] == "x86_64-pc-windows-gnu":
        prefix = "CARGO_TARGET_X86_64_PC_WINDOWS_GNU_"
        environment[prefix + "LINKER"] = str(args.toolchain / "lib/rustlib" / fields["host"] / "bin/rust-lld.exe")
        environment[prefix + "RUSTFLAGS"] = "-C linker-flavor=ld.lld -C link-self-contained=yes"
    if os.name != "nt":
        variable = "DYLD_LIBRARY_PATH" if sys.platform == "darwin" else "LD_LIBRARY_PATH"
        environment[variable] = str(args.toolchain / "lib") + os.pathsep + environment.get(variable, "")
    for component in ("compiler/rustc_driver",):
        command = [sys.executable, source / "x.py", "build", "--config", config, "--stage", "1",
                   "--host", args.native_host, "--target", args.native_host, component]
        log = args.build_root / (component.replace("/", "-") + ".log")
        with log.open("w", encoding="utf-8") as stream:
            process = subprocess.Popen([str(item) for item in command], env=environment,
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in process.stdout:
                print(line, end="")
                stream.write(line)
            if process.wait() != 0:
                raise RuntimeError(f"Compiler bootstrap failed; see {log}")

    runtime = args.build_root / "runtime"
    private = args.build_root / "build" / fields["host"] / "stage0-sysroot"
    target_lib = private / "lib/rustlib" / args.native_host / "lib"
    if not any(target_lib.glob("*rustc_driver*.rmeta")):
        raise ValueError(f"Bootstrap did not produce compiler-private metadata: {target_lib}")
    runtime_lib = runtime / "lib"
    runtime_lib.mkdir(parents=True, exist_ok=True)
    for pattern in ("*rustc_driver*.so", "*rustc_driver*.dylib", "libstd-*.so", "libstd-*.dylib"):
        for library in target_lib.glob(pattern):
            shutil.copy2(library, runtime_lib / library.name)
    if not any(runtime_lib.glob("*rustc_driver*")):
        raise ValueError("Bootstrap did not produce its native driver library")
    backend = build_embedded_backend(args, source, private, runtime, tools, environment)
    write_json(args.build_root / "compiler-build.json", {
        "schemaVersion": 1, "rustVersion": RUST_VERSION, "rustCommit": RUST_COMMIT,
        "nativeHost": args.native_host, "buildHost": fields["host"],
        "runtimeSysroot": str(runtime), "compilerSysroot": str(private),
        "codegenBackend": str(backend), "source": str(source),
        "tools": {name: str(value) if isinstance(value, Path) else value for name, value in tools.items()},
    })
    print(f"Runtime compiler sysroot: {runtime}")
    print(f"Adapter compiler-private sysroot: {private}")
    print(f"Backend: {backend}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(2)
