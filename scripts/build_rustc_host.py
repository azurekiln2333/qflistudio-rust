#!/usr/bin/env python3
"""Bootstrap patched compiler-private libraries for Linux, OHOS and mobile hosts."""

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
    COMPILER_BOUNDARY_KIND, COMPILER_BOUNDARY_PATCH_SHA256, compiler_boundary_patch,
    compiler_patch_hunks, compiler_artifacts, tree_identity, verify_compiler_build,
    run, sha256, source_revision, write_json, ensure_disjoint_build_root,
)

BOOTSTRAP_HOSTS = [host for host, (platform, _) in HOSTS.items()
                   if platform in ("linux", "ohos", "android", "ios")]
LINUX_BUILD_HOSTS = ("x86_64-unknown-linux-gnu", "aarch64-unknown-linux-gnu")


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



def local_llvm_tools(args, sdk=None):
    """Select only explicit tools or files in the selected OHOS native SDK."""
    tools = {}
    for key, name in (("cc", "clang"), ("cxx", "clang++"), ("ar", "llvm-ar"),
                      ("ranlib", "llvm-ranlib"), ("ld_lld", "ld.lld")):
        selected = getattr(args, key, None)
        if selected is None and sdk is not None:
            selected = sdk / "llvm/bin" / name
        if selected is None:
            option = key.replace("_", "-")
            raise ValueError(f"Supply --{option} with a preinstalled local LLVM tool path")
        tools[key] = executable(selected)
    return tools


def linux_tools(args, build_host):
    if build_host not in LINUX_BUILD_HOSTS:
        raise ValueError("Linux compiler bootstrap requires a Linux GNU build host")
    sysroot = getattr(args, "linux_sysroot", None)
    if args.native_host != build_host and sysroot is None:
        raise ValueError("Cross-architecture Linux bootstrap requires --linux-sysroot")
    flags = [f"--target={args.native_host}", "-fPIC"]
    if sysroot is not None:
        sysroot = Path(sysroot).resolve()
        if not (sysroot / "usr/include").is_dir():
            raise ValueError("Linux sysroot is incomplete (usr/include is missing)")
        flags.append(f"--sysroot={sysroot}")
    local = local_llvm_tools(args)
    flags.append(f"-fuse-ld={local['ld_lld']}")
    return {
        "cc": wrapper(args.build_root / "bin/target-clang", local["cc"], flags),
        "cxx": wrapper(args.build_root / "bin/target-clang++", local["cxx"], flags),
        "linker": wrapper(args.build_root / "bin/target-linker", local["cc"], flags),
        "ar": local["ar"], "ranlib": local["ranlib"],
        "compilerTarget": args.native_host, "sysroot": str(sysroot) if sysroot else None,
        "linkerExecutable": local["ld_lld"],
    }


def ohos_tools(args, build_host):
    if build_host not in LINUX_BUILD_HOSTS:
        raise ValueError("OHOS compiler bootstrap requires a Linux GNU build host")
    if getattr(args, "ohos_sdk", None) is None:
        raise ValueError("OHOS hosts require --ohos-sdk pointing to a local native SDK")
    sdk = Path(args.ohos_sdk).resolve()
    target = args.native_host.replace("-unknown", "")
    sysroot = sdk / "sysroot"
    if not (sysroot / "usr/lib" / target / "libc.so").is_file():
        raise ValueError(f"OHOS native SDK is incomplete (missing {target}/libc.so)")
    libraries = sdk / "llvm/lib" / target
    if not libraries.is_dir():
        raise ValueError(f"OHOS native SDK target library directory is missing: {libraries}")
    resource = getattr(args, "ohos_resource_dir", None)
    if resource is None:
        candidates = sorted(path for path in (sdk / "llvm/lib/clang").glob("*")
                            if (path / "lib" / target / "libclang_rt.builtins.a").is_file())
        if len(candidates) != 1:
            raise ValueError("Select --ohos-resource-dir with exactly matching local builtins")
        resource = candidates[0]
    resource = Path(resource).resolve()
    if (not resource.is_relative_to(sdk / "llvm/lib/clang")
            or not (resource / "lib" / target / "libclang_rt.builtins.a").is_file()):
        raise ValueError("OHOS Clang resource directory lacks matching SDK builtins")
    local = local_llvm_tools(args, sdk)
    flags = [f"--target={target}", f"--sysroot={sysroot}", "-resource-dir", str(resource),
             f"-L{libraries}", "-D__MUSL__", "-fPIC", f"-fuse-ld={local['ld_lld']}"]
    return {
        "cc": wrapper(args.build_root / "bin/target-clang", local["cc"], flags),
        "cxx": wrapper(args.build_root / "bin/target-clang++", local["cxx"], flags),
        "linker": wrapper(args.build_root / "bin/target-linker", local["cc"],
                          [*flags, "-Wl,-z,max-page-size=16384"]),
        "ar": local["ar"], "ranlib": local["ranlib"],
        "sdk": str(sdk), "sysroot": str(sysroot), "resourceDir": str(resource),
        "compilerTarget": target, "linkerExecutable": local["ld_lld"],
    }


def native_tools(args, build_host):
    platform = HOSTS[args.native_host][0]
    if platform == "linux":
        return linux_tools(args, build_host)
    if platform == "ohos":
        return ohos_tools(args, build_host)
    if platform == "android":
        return android_tools(args, build_host)
    if platform == "ios":
        return apple_tools(args, build_host)
    raise ValueError(f"Compiler bootstrap is unsupported for {args.native_host}")


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



def prepare_compiler_source(original, build_root):
    """Patch a private complete copy, never the caller's compiler checkout."""
    original = Path(original).resolve(strict=True)
    build_root = Path(build_root).resolve(strict=True)
    if build_root.is_relative_to(original):
        raise ValueError("Compiler build root must be outside its input source")
    source_revision(original, complete=True)
    patch = compiler_boundary_patch()
    hunks = compiler_patch_hunks(patch)
    inputs = tree_identity(original)
    destination = build_root / "patched-compiler-source"
    marker = destination / ".qfli-compiler-source.json"
    if destination.is_symlink() or getattr(destination, "is_junction", lambda: False)():
        raise ValueError("Owned compiler source destination cannot be a link")
    if destination.exists():
        if not marker.is_file():
            raise ValueError("Existing patched source has no provenance. Use a fresh build root")
        provenance = json.loads(marker.read_text(encoding="utf-8"))
        if (provenance.get("kind") != COMPILER_BOUNDARY_KIND
                or provenance.get("sourceCommit") != RUST_COMMIT
                or provenance.get("patchSha256") != COMPILER_BOUNDARY_PATCH_SHA256
                or provenance.get("inputTree") != inputs
                or provenance.get("patchedTree") != tree_identity(destination)):
            raise ValueError("Existing patched source differs from its reviewed inputs")
        changes = provenance.get("patchedFiles", [])
        expected_paths = ["compiler/" + relative for relative, _ in hunks]
        if (not isinstance(changes, list) or any(not isinstance(row, dict) for row in changes)
                or [row.get("path") for row in changes] != expected_paths
                or any(row.get("beforeSha256") != sha256(original / row["path"])
                       or row.get("afterSha256") != sha256(destination / row["path"])
                       for row in changes)):
            raise ValueError("Existing patched source file provenance differs from actual inputs")
        return destination, provenance
    with tempfile.TemporaryDirectory(prefix="compiler-source.", dir=build_root) as temporary:
        staged = Path(temporary) / "source"
        shutil.copytree(original, staged, ignore=shutil.ignore_patterns(".git"))
        if tree_identity(staged) != inputs or tree_identity(original) != inputs:
            raise ValueError("Compiler source changed while preparing its owned copy")
        changes = []
        outputs = []
        for relative, file_hunks in hunks:
            path = staged / "compiler" / relative
            if not path.resolve().is_relative_to(staged):
                raise ValueError("Compiler patch path escapes the owned source")
            before = path.read_bytes()
            lines = before.decode("utf-8").splitlines()
            output = []
            cursor = 0
            for old_start, new_start, old_lines, new_lines in file_hunks:
                if old_start < cursor or lines[old_start:old_start + len(old_lines)] != old_lines:
                    raise ValueError(f"Compiler patch context differs: {relative}:{old_start + 1}")
                output.extend(lines[cursor:old_start])
                if len(output) != new_start:
                    raise ValueError(f"Compiler patch output position differs: {relative}")
                output.extend(new_lines)
                cursor = old_start + len(old_lines)
            output.extend(lines[cursor:])
            after = ("\n".join(output) + ("\n" if before.endswith(b"\n") else "")).encode("utf-8")
            outputs.append((path, after))
            changes.append({"path": "compiler/" + relative, "beforeSha256": sha256(path)})
        # All patched files must match before the first write, even in the owned copy.
        for (path, after), change in zip(outputs, changes):
            path.write_bytes(after)
            change["afterSha256"] = sha256(path)
        (staged / "git-commit-hash").write_text(RUST_COMMIT + "\n", encoding="ascii")
        provenance = {"kind": COMPILER_BOUNDARY_KIND, "sourceCommit": RUST_COMMIT,
                      "patchSha256": COMPILER_BOUNDARY_PATCH_SHA256,
                      "inputSource": str(original), "inputTree": inputs,
                      "patchedFiles": changes, "patchedTree": tree_identity(staged)}
        write_json(staged / marker.name, provenance)
        staged.rename(destination)
    return destination, provenance


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
    if any(private.glob("*rustc_*.rmeta")) or any(private.glob("*rustc_*.rlib")):
        raise ValueError(
            "Bootstrap requires a clean compiler toolchain without rustc-dev private libraries; "
            "use a separate minimal pinned toolchain so source-built metadata cannot conflict"
        )


def build_embedded_backend(args, source, private, runtime, tools, environment):
    target_lib = private / "lib/rustlib" / args.native_host / "lib"
    backend_environment = dict(environment, CARGO_TARGET_DIR=str(args.build_root / "backend-target"))
    backend_environment["CARGO_BUILD_JOBS"] = str(args.jobs)
    backend_environment["CARGO_NET_OFFLINE"] = "true"
    target_key = args.native_host.replace("-", "_")
    for key, tool in (("CC", "cc"), ("CXX", "cxx"), ("AR", "ar"), ("RANLIB", "ranlib")):
        backend_environment[f"{key}_{target_key}"] = str(tools[tool])
    backend_environment[f"CARGO_TARGET_{target_key.upper()}_LINKER"] = str(tools["linker"])
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



def validate_build_paths(args):
    """Reject input/output ancestry before any writes or executable queries.

    Native Path ancestry preserves Windows case semantics. Resolve directory
    links first, and protect both the selected and resolved local-tool parents:
    a file symlink must not let generated wrappers overwrite its selected path.
    Internally extracted source is owned output, not a caller-provided input.
    """
    build_root = Path(args.build_root).resolve()
    inputs = []
    for key in ("toolchain", "source", "ndk", "ohos_sdk", "ohos_resource_dir", "linux_sysroot"):
        selected = getattr(args, key, None)
        if selected is not None:
            inputs.append((key, Path(selected).resolve()))
    for key in ("cc", "cxx", "ar", "ranlib", "ld_lld"):
        selected = getattr(args, key, None)
        if selected is not None:
            selected = Path(selected)
            inputs.append((key, selected.absolute().parent.resolve()))
            inputs.append((key, selected.resolve().parent))
    for key, input_root in inputs:
        try:
            ensure_disjoint_build_root(build_root, input_root)
        except ValueError as error:
            option = key.replace("_", "-")
            raise ValueError(f"--build-root overlaps --{option} input directory: {input_root}") from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-host", choices=BOOTSTRAP_HOSTS, required=True)
    parser.add_argument("--toolchain", type=Path, required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--download-source", action="store_true")
    parser.add_argument("--build-root", type=Path, required=True)
    parser.add_argument("--ndk", type=Path)
    parser.add_argument("--ohos-sdk", type=Path,
                        help="Local native SDK directory containing llvm/ and sysroot/")
    parser.add_argument("--ohos-resource-dir", type=Path,
                        help="Matching resource directory under the SDK llvm/lib/clang/")
    parser.add_argument("--linux-sysroot", type=Path,
                        help="Local target sysroot, required for Linux cross-architecture builds")
    for option in ("cc", "cxx", "ar", "ranlib", "ld-lld"):
        parser.add_argument("--" + option, type=Path,
                            help="Explicit preinstalled LLVM tool for Linux/OHOS")
    parser.add_argument("--android-api", type=int, default=21)
    parser.add_argument("--ios-deployment-target", default="13.0")
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--configure-only", action="store_true")
    args = parser.parse_args()
    args.toolchain = args.toolchain.resolve()
    args.build_root = args.build_root.resolve()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    try:
        validate_build_paths(args)
    except ValueError as error:
        parser.error(str(error))
    fields = compiler_identity(args.toolchain)
    args.build_root.mkdir(parents=True, exist_ok=True)
    (args.build_root / "bin").mkdir(exist_ok=True)
    tools = native_tools(args, fields["host"])
    input_source = complete_source(args)
    source, source_provenance = prepare_compiler_source(input_source, args.build_root)
    config = args.build_root / "bootstrap.toml"
    config.write_text(bootstrap_config(args, fields["host"], tools), encoding="utf-8")
    if args.configure_only:
        print(f"Configured {args.native_host}: {config}; no runtime was built")
        return

    # Reject stale or stock build outputs rather than mixing private metadata.
    for folder in ("build", "backend-target", "runtime"):
        if (args.build_root / folder).exists():
            raise ValueError(f"Existing {folder} output requires a fresh compiler build root")
    require_bootstrap_inputs(args.toolchain, args.native_host, fields["host"])
    environment = dict(os.environ, RUSTC_BOOTSTRAP="1", CARGO_HOME=str(args.build_root / "cargo"),
                       CARGO_NET_OFFLINE="true")
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
    if tree_identity(source) != source_provenance["patchedTree"]:
        raise ValueError("Patched compiler source changed during the build")
    build_record = args.build_root / "compiler-build.json"
    write_json(build_record, {
        "schemaVersion": 2, "status": "built", "rustVersion": RUST_VERSION, "rustCommit": RUST_COMMIT,
        "compilerBoundary": source_provenance,
        "compilerArtifacts": compiler_artifacts(private, runtime),
        "bootstrapConfig": {"path": str(config), "sha256": sha256(config)},
        "bootstrapCompiler": {"identity": fields, "path": str(args.toolchain),
                              "sha256": sha256(args.toolchain / "bin" /
                                               ("rustc.exe" if os.name == "nt" else "rustc"))},
        "nativeHost": args.native_host, "buildHost": fields["host"],
        "runtimeSysroot": str(runtime), "compilerSysroot": str(private),
        "codegenBackend": str(backend), "source": str(source),
        "tools": {name: str(value) if isinstance(value, Path) else value for name, value in tools.items()},
    })
    try:
        verify_compiler_build(build_record, private, runtime, args.native_host)
    except (OSError, ValueError):
        # Keep failed-build evidence, but never leave a consumable built record.
        info = json.loads(build_record.read_text(encoding="utf-8"))
        info["status"] = "rejected"
        write_json(build_record, info)
        raise
    print(f"Runtime compiler sysroot: {runtime}")
    print(f"Adapter compiler-private sysroot: {private}")
    print(f"Backend: {backend}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(2)
