"""Pinned build identities shared by native compiler, adapter and packaging tools."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

RUST_VERSION = "1.98.1"
RUST_COMMIT = "48a229ceaefd4985c50990b14116b6d856af0985"
SOURCE_SHA256 = "be1816e7f6c40abb90245ad6e024bed2a7e88d7dda4561e4d5470207df616b9f"
MIRI_SHA256 = "92f51c0345496c6ef1edbba009985c84b612630dd5c7e81ea2cdd826d0d85764"
GUEST_TARGET = "x86_64-unknown-linux-gnu"
HOSTS = {
    "x86_64-pc-windows-gnu": ("windows", "x64"),
    "x86_64-pc-windows-msvc": ("windows", "x64"),
    "aarch64-pc-windows-msvc": ("windows", "arm64"),
    "x86_64-unknown-linux-gnu": ("linux", "x64"),
    "aarch64-unknown-linux-gnu": ("linux", "arm64"),
    "aarch64-linux-android": ("android", "arm64"),
    "x86_64-linux-android": ("android", "x64"),
    "aarch64-apple-darwin": ("macos", "arm64"),
    "x86_64-apple-darwin": ("macos", "x64"),
    "aarch64-apple-ios": ("ios", "arm64"),
    "aarch64-apple-ios-sim": ("ios", "arm64"),
    "x86_64-apple-ios": ("ios", "x64"),
    "aarch64-unknown-linux-ohos": ("ohos", "arm64"),
    "x86_64-unknown-linux-ohos": ("ohos", "x64"),
}


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(command, **kwargs):
    return subprocess.run([str(item) for item in command], check=True, **kwargs)


def compiler_identity(toolchain):
    compiler = Path(toolchain) / "bin" / ("rustc.exe" if os.name == "nt" else "rustc")
    version = run([compiler, "-vV"], capture_output=True, text=True).stdout
    fields = dict(line.split(": ", 1) for line in version.splitlines() if ": " in line)
    if fields.get("commit-hash") != RUST_COMMIT or fields.get("release") != RUST_VERSION:
        raise ValueError(f"Compiler must be Rust {RUST_VERSION} commit {RUST_COMMIT}")
    return fields


def source_revision(source, complete=False):
    source = Path(source)
    if complete:
        required = ("x.py", "Cargo.toml", "src/bootstrap/Cargo.toml",
                    "library/Cargo.toml", "library/std/Cargo.toml",
                    "library/backtrace/Cargo.toml", "compiler/rustc_driver/Cargo.toml",
                    "compiler/rustc_codegen_cranelift/Cargo.toml")
        missing = [item for item in required if not (source / item).is_file()]
        if missing:
            raise ValueError("Complete bootstrap source is required; missing " + ", ".join(missing))
    commit_file = source / "git-commit-hash"
    if commit_file.is_file():
        commit = commit_file.read_text().strip()
    else:
        environment = dict(os.environ, GIT_NO_LAZY_FETCH="1")
        try:
            commit = run(["git", "-c", f"safe.directory={source.resolve()}", "-C", source, "rev-parse", "HEAD"], env=environment,
                         capture_output=True, text=True).stdout.strip()
        except subprocess.CalledProcessError:
            # A copied sparse snapshot is sufficient for license inputs, but never bootstrap.
            detached = source / ".git/HEAD"
            if complete or not detached.is_file():
                raise
            commit = detached.read_text().strip()
            validate_miri_source(source / "src/tools/miri")
    if commit != RUST_COMMIT:
        raise ValueError(f"Rust source revision mismatch: {commit}")
    return commit


def validate_miri_source(source):
    source = Path(source)
    paths = [path.relative_to(source).as_posix() for folder in ("src", "cargo-miri/src")
             for path in (source / folder).rglob("*") if path.is_file()]
    paths += ["Cargo.toml", "Cargo.lock", "cargo-miri/Cargo.toml",
              "cargo-miri/Cargo.lock", "cargo-miri/build.rs"]
    if (source / "build.rs").exists():
        paths.append("build.rs")
    manifest = bytearray()
    for relative in sorted(paths):
        normalized = (source / relative).read_bytes().replace(b"\r\n", b"\n")
        digest = hashlib.sha256(normalized).hexdigest()
        manifest.extend(f"{digest}  {relative}\n".encode())
    actual = hashlib.sha256(manifest).hexdigest()
    if actual != MIRI_SHA256:
        raise ValueError(f"Miri source differs from pinned inputs: {actual}")


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def record_adapter(args):
    fields = compiler_identity(args.toolchain)
    validate_miri_source(args.miri_source)
    target = args.native_host or fields["host"]
    if target not in HOSTS:
        raise ValueError(f"Unsupported native host: {target}")
    compiler_root = Path(args.runtime_sysroot or args.compiler_sysroot or args.toolchain).resolve()
    # Bind the record to the private driver/backend binaries that packaging will copy.
    libraries = {}
    for folder in (compiler_root / "bin", compiler_root / "lib"):
        for pattern in ("*rustc_driver*.dll", "*rustc_driver*.so", "*rustc_driver*.dylib",
                        "*rustc_codegen*.dll", "*rustc_codegen*.so", "*rustc_codegen*.dylib",
                        "*std-*.dll", "*std-*.so", "*std-*.dylib", "*LLVM*.dll",
                        "*LLVM*.so*", "*LLVM*.dylib"):
            for path in folder.rglob(pattern):
                libraries[str(path.resolve())] = {"name": path.name, "path": str(path.resolve()),
                                                "sha256": sha256(path)}
    if not any("rustc_driver" in item["name"] for item in libraries.values()):
        raise ValueError("Matching compiler-private driver library is missing")
    adapter = Path(args.adapter).resolve(strict=True)
    metadata = Path(args.dependency_metadata).resolve(strict=True)
    write_json(args.output, {
        "schemaVersion": 1, "rustVersion": RUST_VERSION, "rustCommit": RUST_COMMIT,
        "nativeHost": target, "buildHost": fields["host"],
        "adapter": {"path": str(adapter), "sha256": sha256(adapter)},
        "dependencyMetadata": {"path": str(metadata), "sha256": sha256(metadata)},
        "compilerLibraries": sorted(libraries.values(), key=lambda item: item["path"]),
    })


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "check-source":
        parser = argparse.ArgumentParser(description="Verify the pinned upstream Miri source")
        parser.add_argument("command")
        parser.add_argument("source", type=Path)
        validate_miri_source(parser.parse_args().source)
        return
    if len(sys.argv) > 1 and sys.argv[1] == "record-guest":
        parser = argparse.ArgumentParser(description="Record guest libraries after pinned cargo-miri setup")
        parser.add_argument("command")
        parser.add_argument("--toolchain", type=Path, required=True)
        parser.add_argument("--miri-source", type=Path, required=True)
        parser.add_argument("--guest-sysroot", type=Path, required=True)
        args = parser.parse_args()
        compiler_identity(args.toolchain)
        validate_miri_source(args.miri_source)
        libraries = sorted((args.guest_sysroot / "lib/rustlib" / GUEST_TARGET / "lib").glob("*.rlib"))
        if not any(path.name.startswith("libstd-") for path in libraries):
            raise ValueError("cargo-miri guest standard library is missing")
        write_json(args.guest_sysroot / "miri-sysroot.json", {
            "schemaVersion": 2, "rustVersion": RUST_VERSION, "rustCommit": RUST_COMMIT,
            "guestTarget": GUEST_TARGET, "encodedMir": True,
            "files": [{"path": "sysroot/" + path.relative_to(args.guest_sysroot).as_posix(),
                       "size": path.stat().st_size, "sha256": sha256(path)} for path in libraries],
        })
        return
    parser = argparse.ArgumentParser(description="Record a successfully built pinned Miri adapter")
    parser.add_argument("--toolchain", type=Path, required=True)
    parser.add_argument("--compiler-sysroot", type=Path)
    parser.add_argument("--runtime-sysroot", type=Path)
    parser.add_argument("--miri-source", type=Path, required=True)
    parser.add_argument("--native-host", choices=HOSTS)
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--dependency-metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    record_adapter(parser.parse_args())


if __name__ == "__main__":
    main()
