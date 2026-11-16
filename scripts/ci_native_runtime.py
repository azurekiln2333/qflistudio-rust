#!/usr/bin/env python3
"""Build downloadable native packages on clean, disposable CI runners."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
from types import SimpleNamespace

from build_rustc_host import complete_source
from miri_build_support import (
    GUEST_TARGET, HOSTS, RUST_COMMIT, RUST_VERSION, compiler_identity,
    ensure_disjoint_build_root, sha256, validate_miri_source, write_json,
)


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
CI_HOSTS = ("x86_64-unknown-linux-gnu", "x86_64-pc-windows-gnu", "aarch64-apple-darwin")


class Runner:
    def __init__(self, work, output):
        self.work = work.resolve()
        self.output = output.resolve()
        ensure_disjoint_build_root(self.work, ROOT)
        self.work.mkdir(parents=True, exist_ok=True)
        self.logs = self.output / "logs"
        self.logs.mkdir(parents=True, exist_ok=True)
        self.env = dict(os.environ, RUSTUP_HOME=str(self.work / "rustup"),
                        CARGO_HOME=str(self.work / "cargo"), CARGO_BUILD_JOBS="2",
                        CARGO_INCREMENTAL="0", CARGO_PROFILE_DEV_DEBUG="0",
                        PYTHONDONTWRITEBYTECODE="1", RUSTC_BOOTSTRAP="1")
        for key in ("RUSTC", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER", "RUSTFLAGS",
                    "CARGO_ENCODED_RUSTFLAGS", "CARGO_NET_OFFLINE", "RUSTUP_TOOLCHAIN"):
            self.env.pop(key, None)

    def run(self, name, command, *, env=None, cwd=None):
        command = [str(item) for item in command]
        print(f"::group::{name}", flush=True)
        with (self.logs / f"{name}.log").open("w", encoding="utf-8", buffering=1) as log:
            log.write(json.dumps(command) + "\n")
            process = subprocess.Popen(command, cwd=cwd or ROOT, env=env or self.env,
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       text=True, encoding="utf-8", errors="replace", bufsize=1)
            for line in process.stdout:
                log.write(line)
                print(line, end="", flush=True)
            code = process.wait()
        print("::endgroup::", flush=True)
        if code:
            raise subprocess.CalledProcessError(code, command)

    def toolchain(self, host, *, reference=False):
        name = f"{RUST_VERSION}-{host}"
        command = ["rustup", "toolchain", "install", name, "--profile", "minimal", "--no-self-update"]
        if reference:
            command += ["--component", "rustc-dev,rust-src"]
        self.run("install-toolchain", command)
        result = subprocess.run(["rustup", "which", "--toolchain", name, "rustc"],
                                check=True, capture_output=True, text=True, env=self.env)
        toolchain = Path(result.stdout.strip()).resolve().parent.parent
        fields = compiler_identity(toolchain)
        if fields["host"] != host:
            raise ValueError(f"Installed toolchain host differs from {host}")
        self.env["RUSTUP_TOOLCHAIN"] = name
        self.env["PATH"] = str(toolchain / "bin") + os.pathsep + self.env.get("PATH", "")
        variable = "DYLD_LIBRARY_PATH" if sys.platform == "darwin" else "LD_LIBRARY_PATH"
        self.env[variable] = str(toolchain / "lib")
        return toolchain

    def source(self):
        inputs = self.work / "inputs"
        inputs.mkdir(exist_ok=True)
        return complete_source(SimpleNamespace(source=None, build_root=inputs, download_source=True))


def archive_tree(source, archive, prefix=None):
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "w:gz", compresslevel=6) as bundle:
        if prefix:
            bundle.add(source, arcname=prefix)
        else:
            for path in sorted(source.iterdir()):
                bundle.add(path, arcname=path.name)
    archive.with_suffix(archive.suffix + ".sha256").write_text(
        f"{sha256(archive)}  {archive.name}\n", encoding="ascii")


def build_guest(runner):
    if sys.platform != "linux":
        raise ValueError("The shared guest sysroot is built on Linux")
    toolchain = runner.toolchain(GUEST_TARGET, reference=True)
    source = runner.source() / "src/tools/miri"
    validate_miri_source(source)
    stage = runner.work / "reference-miri"
    shutil.copytree(source, stage)
    target = runner.work / "reference-target"
    guest = runner.work / "guest-sysroot"
    environment = dict(runner.env, CARGO_TARGET_DIR=str(target), MIRI_SYSROOT=str(guest))
    cargo = toolchain / "bin/cargo"
    runner.run("guest-miri", [cargo, "rustc", "--manifest-path", stage / "Cargo.toml",
                              "--no-default-features", "--features", "stack-cache", "--bin", "miri",
                              "--locked", "--", "-L", f"native={toolchain / 'lib'}"], env=environment)
    runner.run("guest-cargo-miri", [cargo, "build", "--manifest-path", stage / "cargo-miri/Cargo.toml",
                                    "--locked"], env=environment)
    environment["MIRI"] = str(target / "debug/miri")
    runner.run("guest-sysroot", [target / "debug/cargo-miri", "miri", "setup", "--target", GUEST_TARGET],
               env=environment)
    runner.run("guest-record", [sys.executable, SCRIPTS / "miri_build_support.py", "record-guest",
                               "--toolchain", toolchain, "--miri-source", source, "--guest-sysroot", guest])
    archive_tree(guest, runner.output / "guest-sysroot.tar.gz", "sysroot")


def native_tool_args(host, environment):
    if host == "x86_64-unknown-linux-gnu":
        names = (("cc", "clang"), ("cxx", "clang++"), ("ar", "llvm-ar"),
                 ("ranlib", "llvm-ranlib"), ("ld-lld", "ld.lld"))
    elif host == "x86_64-pc-windows-gnu":
        names = (("cc", "gcc"), ("cxx", "g++"), ("ar", "ar"), ("ranlib", "ranlib"),
                 ("dlltool", "dlltool"))
    else:
        return []
    result = []
    for option, name in names:
        path = shutil.which(name, path=environment.get("PATH"))
        if not path:
            raise ValueError(f"Missing native build tool: {name}")
        result += ["--" + option, path]
    return result


def unpack_guest(archive, destination):
    checksum = archive.with_suffix(archive.suffix + ".sha256")
    fields = checksum.read_text(encoding="ascii").split() if checksum.is_file() else []
    if len(fields) != 2 or fields[1] != archive.name or fields[0] != sha256(archive):
        raise ValueError("Guest archive checksum is missing or differs")
    with tarfile.open(archive) as bundle:
        bundle.extractall(destination, filter="data")
    guest = destination / "sysroot"
    if not (guest / "miri-sysroot.json").is_file():
        raise ValueError("Guest archive has no MIR build record")
    return guest


def prepare_adapter_cache(runner, toolchain, source, host):
    stage = runner.work / "dependency-stage"
    shutil.copytree(source, stage / "miri")
    shutil.copytree(ROOT / "native/miri_adapter", stage / "adapter")
    cargo = toolchain / "bin" / ("cargo.exe" if os.name == "nt" else "cargo")
    runner.run("adapter-fetch", [cargo, "fetch", "--manifest-path", stage / "adapter/Cargo.toml",
                                 "--locked", "--target", host])


def collect_package(package_root, host, records, output, commit):
    platform, architecture = HOSTS[host]
    key = f"{platform}-{architecture}"
    native = package_root / "native/build/runtime" / key
    manifest_path = package_root / "assets/miri" / f"manifest.{key}.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("nativeHost") != host or manifest.get("rustCommit") != RUST_COMMIT:
        raise ValueError("Generated package identity differs from this build")
    payload = output / "payload"
    payload.mkdir(parents=True)
    shutil.copytree(native, payload / "native/build/runtime" / key)
    assets = payload / "assets/miri"
    assets.mkdir(parents=True)
    shutil.copy2(manifest_path, assets / manifest_path.name)
    for row in manifest["files"]:
        name = row["asset"]
        if Path(name).name != name or "/" in name or "\\" in name:
            raise ValueError("Generated asset name is not a basename")
        source = package_root / "assets/miri" / name
        if sha256(source) != row["sha256"] or source.stat().st_size != row["size"]:
            raise ValueError(f"Generated asset changed before archive: {name}")
        shutil.copy2(source, assets / name)
    for row in manifest["nativeLibraries"]:
        library = native / row["path"]
        if sha256(library) != row["sha256"] or library.stat().st_size != row["size"]:
            raise ValueError(f"Generated native library changed before archive: {row['path']}")
    include = payload / "native/include"
    include.mkdir(parents=True)
    for name in ("qfli_miri.h", "qfli_debug.h"):
        shutil.copy2(ROOT / "native/miri_adapter" / name, include / name)
    info = payload / "build-info"
    info.mkdir()
    for name, source in records.items():
        shutil.copy2(source, info / name)
    write_json(info / "ci-build.json", {
        "schemaVersion": 1, "status": "packaged", "nativeHost": host,
        "rustVersion": RUST_VERSION, "rustCommit": RUST_COMMIT, "sourceCommit": commit,
        "runtimeExecuted": False, "deviceExecuted": False,
        "runId": os.environ.get("GITHUB_RUN_ID"), "runAttempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "nativeLibraries": len(manifest["nativeLibraries"]), "guestAndLicenseFiles": len(manifest["files"]),
    })
    archive = output / f"native-runtime-{key}.tar.gz"
    archive_tree(payload, archive)
    return archive


def build_runtime(runner, host, guest_archive):
    guest = unpack_guest(guest_archive, runner.work / "guest")
    toolchain = runner.toolchain(host)
    source = runner.source()
    compiler_root = runner.work / "compiler"
    runner.run("compiler-bootstrap", [sys.executable, "-u", SCRIPTS / "build_rustc_host.py",
                                      "--native-host", host, "--toolchain", toolchain,
                                      "--source", source, "--build-root", compiler_root, "--jobs", "2",
                                      *native_tool_args(host, runner.env)])
    compiler_record = compiler_root / "compiler-build.json"
    compiler = json.loads(compiler_record.read_text(encoding="utf-8"))
    miri = source / "src/tools/miri"
    prepare_adapter_cache(runner, toolchain, miri, host)
    adapter_root = runner.work / "adapter"
    environment = dict(runner.env, QFLI_COMPILER_SYSROOT=compiler["compilerSysroot"],
                       QFLI_RUNTIME_SYSROOT=compiler["runtimeSysroot"],
                       QFLI_COMPILER_BUILD_INFO=str(compiler_record), QFLI_ADAPTER_BUILD_ROOT=str(adapter_root))
    if os.name == "nt":
        patch = shutil.which("patch", path=environment.get("PATH"))
        if not patch:
            raise ValueError("Windows adapter build requires GNU patch")
        command = ["pwsh", "-NoProfile", "-File", SCRIPTS / "build_miri_adapter.ps1",
                   "-MiriSource", miri, "-Toolchain", toolchain,
                   "-CompilerSysroot", compiler["compilerSysroot"],
                   "-RuntimeSysroot", compiler["runtimeSysroot"],
                   "-CompilerBuildInfo", compiler_record, "-BuildRoot", adapter_root,
                   "-CargoHome", runner.env["CARGO_HOME"], "-PatchExecutable", patch,
                   "-PythonExecutable", sys.executable, "-Offline"]
    else:
        command = ["sh", SCRIPTS / "build_miri_adapter.sh", miri, toolchain, host]
    runner.run("adapter-build", command, env=environment)
    adapter_record = adapter_root / f"adapter-build-{host}.json"
    package_root = runner.work / "package"
    command = [sys.executable, SCRIPTS / "package_miri_runtime.py", "--build-info", adapter_record,
               "--guest-sysroot", guest, "--guest-build-info", guest / "miri-sysroot.json",
               "--rust-source", source, "--codegen-backend", compiler["codegenBackend"],
               "--project-root", package_root]
    search = [Path(compiler["runtimeSysroot"]) / "lib", Path(compiler["runtimeSysroot"]) / "bin"]
    if sys.platform == "linux":
        search += [Path("/lib/x86_64-linux-gnu"), Path("/usr/lib/x86_64-linux-gnu")]
    elif os.name == "nt":
        search += [Path(value) for value in runner.env.get("PATH", "").split(os.pathsep) if value]
    for path in search:
        if path.is_dir():
            command += ["--compiler-lib-directory", path]
    runner.run("package-runtime", command)
    archive = collect_package(package_root, host, {
        "compiler-build.json": compiler_record, "adapter-build.json": adapter_record,
        "miri-sysroot.json": guest / "miri-sysroot.json",
    }, runner.output, os.environ.get("GITHUB_SHA"))
    print(f"Native runtime package: {archive}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("guest", "runtime"))
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--native-host", choices=CI_HOSTS)
    parser.add_argument("--guest-archive", type=Path)
    args = parser.parse_args()
    if args.stage == "runtime" and (not args.native_host or not args.guest_archive):
        parser.error("runtime requires --native-host and --guest-archive")
    runner = Runner(args.work_root, args.output_root)
    status = {"stage": args.stage, "nativeHost": args.native_host, "status": "failed"}
    try:
        if args.stage == "guest":
            build_guest(runner)
        else:
            build_runtime(runner, args.native_host, args.guest_archive.resolve())
        status["status"] = "success"
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        status["error"] = str(error)
        raise
    finally:
        write_json(runner.logs / "status.json", status)
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a", encoding="utf-8") as stream:
                stream.write(f"### Native {args.stage}: {status['status']}\n\n")
                stream.write(f"Host: `{args.native_host or GUEST_TARGET}`. Download the artifacts below.\n\n")
                stream.write("Native packages contain libraries, MIR assets, headers and provenance. "
                             "They are not Flutter installers. Build success does not prove app execution.\n")


if __name__ == "__main__":
    main()
