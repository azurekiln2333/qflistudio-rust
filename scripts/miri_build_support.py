"""Pinned build identities shared by native compiler, adapter and packaging tools."""

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys

RUST_VERSION = "1.98.1"
RUST_COMMIT = "48a229ceaefd4985c50990b14116b6d856af0985"
SOURCE_SHA256 = "be1816e7f6c40abb90245ad6e024bed2a7e88d7dda4561e4d5470207df616b9f"
MIRI_SHA256 = "92f51c0345496c6ef1edbba009985c84b612630dd5c7e81ea2cdd826d0d85764"
COMPILER_BOUNDARY_KIND = "qfli-embedded-compiler-boundary-v1"
COMPILER_BOUNDARY_PATCH = (Path(__file__).resolve().parent.parent / "native/patches" /
                           "rustc-1.98.1-embedded-compiler-boundary.patch")
COMPILER_BOUNDARY_PATCH_SHA256 = "7236eff645ddf45eb87e78865a7d805a3443234e23c0855bee7956882c9989ee"
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



def ensure_disjoint_build_root(build_root, *input_roots):
    """Reject all input/output overlaps before any generated file is written."""
    output = Path(build_root).resolve()
    for value in input_roots:
        protected = Path(value).resolve()
        if output.is_relative_to(protected) or protected.is_relative_to(output):
            raise ValueError(f"Build root overlaps protected input: {protected}")
    return output


def compiler_boundary_patch():
    if sha256(COMPILER_BOUNDARY_PATCH) != COMPILER_BOUNDARY_PATCH_SHA256:
        raise ValueError("Compiler boundary patch differs from the reviewed SHA-256")
    return COMPILER_BOUNDARY_PATCH


def compiler_patch_hunks(patch):
    """Parse the reviewed existing-file unified diff without fuzzy application."""
    files = []
    current = None
    lines = Path(patch).read_text(encoding="utf-8").splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("diff --git "):
            parts = line.split()
            if len(parts) != 4 or not parts[2].startswith("a/") or parts[3] != "b/" + parts[2][2:]:
                raise ValueError("Compiler patch must modify existing paths without renames")
            relative = parts[2][2:]
            if (not relative or "\\" in relative or ":" in relative
                    or any(part in ("", ".", "..") for part in relative.split("/"))):
                raise ValueError("Unsafe compiler patch path")
            if any(row[0] == relative for row in files):
                raise ValueError("Duplicate compiler patch path")
            current = (relative, [])
            files.append(current)
        elif line.startswith("@@ "):
            match = re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
            if current is None or match is None:
                raise ValueError("Malformed compiler patch hunk")
            old_start, old_count, new_start, new_count = match.groups()
            old_count = int(old_count) if old_count is not None else 1
            new_count = int(new_count) if new_count is not None else 1
            before, after = [], []
            index += 1
            while index < len(lines) and not lines[index].startswith(("@@ ", "diff --git ")):
                content = lines[index]
                if not content or content[0] not in " +-":
                    raise ValueError("Unsupported compiler patch line")
                if content[0] in " -": before.append(content[1:])
                if content[0] in " +": after.append(content[1:])
                index += 1
            if len(before) != old_count or len(after) != new_count:
                raise ValueError("Compiler patch hunk counts do not match")
            current[1].append((int(old_start) - 1, int(new_start) - 1, before, after))
            continue
        elif (current is None or not line.startswith(("index ", "--- a/", "+++ b/"))):
            raise ValueError("Unsupported compiler patch metadata")
        index += 1
    if not files or any(not hunks for _, hunks in files):
        raise ValueError("Compiler patch has no complete file changes")
    return files


def tree_identity(root):
    """Hash copied regular inputs in stable path order, excluding Git metadata."""
    root = Path(root)
    manifest = hashlib.sha256()
    count = 0
    for folder, directories, names in os.walk(root, followlinks=False):
        directories[:] = sorted(name for name in directories if name != ".git")
        for name in directories + names:
            path = Path(folder) / name
            if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
                raise ValueError(f"Compiler source contains a link: {path}")
        for name in sorted(names):
            if name in (".git", ".qfli-compiler-source.json"):
                continue
            path = Path(folder) / name
            if not path.is_file():
                raise ValueError(f"Compiler source contains a non-file: {path}")
            relative = path.relative_to(root).as_posix()
            manifest.update(json.dumps([relative, path.stat().st_size, sha256(path)],
                                       ensure_ascii=True, separators=(",", ":")).encode() + b"\n")
            count += 1
    return {"sha256": manifest.hexdigest(), "fileCount": count}


def compiler_artifacts(compiler_sysroot, runtime_sysroot):
    files = []
    for label, root in (("compiler", Path(compiler_sysroot)), ("runtime", Path(runtime_sysroot))):
        for folder in (root / "bin", root / "lib"):
            for path in sorted(folder.rglob("*")):
                if path.is_file():
                    files.append({"root": label, "path": path.relative_to(root).as_posix(),
                                  "size": path.stat().st_size, "sha256": sha256(path)})
    return files


def verify_compiler_build(record_path, compiler_sysroot, runtime_sysroot, native_host,
                          path_mapper=None):
    """Reject stock/private-library mixtures before recording or consuming them."""
    map_path = path_mapper or Path
    record_path = map_path(record_path).resolve(strict=True)
    info = json.loads(record_path.read_text(encoding="utf-8"))
    boundary = info.get("compilerBoundary", {})
    if (info.get("schemaVersion") != 2 or info.get("status") != "built"
            or info.get("rustVersion") != RUST_VERSION or info.get("rustCommit") != RUST_COMMIT
            or info.get("nativeHost") != native_host
            or boundary.get("kind") != COMPILER_BOUNDARY_KIND
            or boundary.get("patchSha256") != COMPILER_BOUNDARY_PATCH_SHA256
            or boundary.get("sourceCommit") != RUST_COMMIT):
        raise ValueError("A successfully built patched compiler provenance record is required")
    patch = compiler_boundary_patch()
    for key in ("inputTree", "patchedTree"):
        tree = boundary.get(key, {})
        if (not isinstance(tree, dict) or not re.fullmatch(r"[0-9a-f]{64}", str(tree.get("sha256", "")))
                or not isinstance(tree.get("fileCount"), int) or tree["fileCount"] <= 0):
            raise ValueError("Compiler provenance lacks frozen source-tree identities")
    changes = boundary.get("patchedFiles")
    expected_paths = ["compiler/" + relative for relative, _ in compiler_patch_hunks(patch)]
    if (not isinstance(changes, list) or any(not isinstance(row, dict) for row in changes)
            or [row.get("path") for row in changes] != expected_paths
            or any(not re.fullmatch(r"[0-9a-f]{64}", str(row.get(key, "")))
                   for row in changes for key in ("beforeSha256", "afterSha256"))):
        raise ValueError("Compiler provenance lacks the exact patched source-file hashes")
    roots = {"compiler": map_path(compiler_sysroot).resolve(), "runtime": map_path(runtime_sysroot).resolve()}
    for label, field in (("compiler", "compilerSysroot"), ("runtime", "runtimeSysroot")):
        if map_path(info.get(field, "")).resolve() != roots[label]:
            raise ValueError(f"Compiler provenance {field} does not match the selected sysroot")
    expected = info.get("compilerArtifacts")
    if not isinstance(expected, list) or not expected:
        raise ValueError("Compiler provenance has no private-library hashes")
    actual = compiler_artifacts(roots["compiler"], roots["runtime"])
    if actual != expected:
        raise ValueError("Compiler private libraries differ from their patched build record")
    private_names = [Path(row["path"]).name for row in actual if row["root"] == "compiler"
                     and row["path"].startswith(f"lib/rustlib/{native_host}/lib/")]
    for component in ("rustc_driver", "rustc_interface", "rustc_session"):
        if not any(component in name and name.endswith(".rmeta") for name in private_names):
            raise ValueError(f"Patched compiler metadata missing: {component}")
    runtime_names = [Path(row["path"]).name for row in actual if row["root"] == "runtime"]
    for component in ("rustc_driver", "rustc_codegen"):
        if not any(component in name and Path(name).suffix in (".so", ".dylib", ".dll") for name in runtime_names):
            raise ValueError(f"Patched compiler runtime missing: {component}")
    return {"path": str(record_path), "sha256": sha256(record_path),
            "compilerBoundary": boundary}


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


def compiler_libraries(compiler_root):
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
    return sorted(libraries.values(), key=lambda item: item["path"])



def windows_wsl_path_mapper(distro):
    """Resolve Linux build-record paths through one explicit Windows WSL mount.

    This maps paths only. It does not start WSL or invoke a command.
    """
    if os.name != "nt" or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", distro):
        raise ValueError("WSL record mapping requires Windows and an explicit distribution name")
    def mapped(value):
        value = str(value)
        drive = re.fullmatch(r"/mnt/([a-zA-Z])/(.*)", value)
        if drive:
            return Path(drive[1].upper() + ":/" + drive[2])
        if value.startswith("/"):
            return Path("//wsl.localhost/" + distro + value)
        return Path(value)
    return mapped


def verify_adapter_build(record_path, adapter, compiler_sysroot=None,
                         runtime_sysroot=None, native_host=None, path_mapper=None):
    """Bind an adapter to the exact patched compiler record and library set."""
    map_path = path_mapper or Path
    record_path = map_path(record_path).resolve(strict=True)
    info = json.loads(record_path.read_text(encoding="utf-8"))
    if (info.get("schemaVersion") != 1 or info.get("rustVersion") != RUST_VERSION
            or info.get("rustCommit") != RUST_COMMIT
            or (native_host is not None and info.get("nativeHost") != native_host)):
        raise ValueError("Adapter build record does not match the pinned compiler/host")
    target = info.get("nativeHost")
    if target not in HOSTS:
        raise ValueError("Adapter build record has an unsupported native host")
    compiler = info.get("compilerBuild", {})
    if not isinstance(compiler, dict) or not compiler.get("path") or not compiler.get("sha256"):
        raise ValueError("Adapter build record lacks patched compiler provenance")
    compiler_path = map_path(compiler["path"]).resolve(strict=True)
    if sha256(compiler_path) != compiler["sha256"]:
        raise ValueError("Compiler build record differs from the adapter provenance")
    compiler_info = json.loads(compiler_path.read_text(encoding="utf-8"))
    private = map_path(compiler_sysroot or compiler_info.get("compilerSysroot", ""))
    runtime = map_path(runtime_sysroot or compiler_info.get("runtimeSysroot", ""))
    verified = verify_compiler_build(compiler_path, private, runtime, target,
                                     path_mapper=path_mapper)
    if path_mapper is not None:
        # The record retains the producer path. Mapping only locates the same
        # hash-bound bytes on the explicitly selected consumer filesystem.
        verified["path"] = compiler["path"]
    if (compiler != verified or info.get("compilerBoundary") != verified["compilerBoundary"]):
        raise ValueError("Adapter compiler boundary differs from the compiler build record")
    adapter = map_path(adapter).resolve(strict=True)
    if (map_path(info.get("adapter", {}).get("path", "")).resolve() != adapter
            or info.get("adapter", {}).get("sha256") != sha256(adapter)):
        raise ValueError("Adapter differs from its patched compiler build record")
    recorded_libraries = info.get("compilerLibraries")
    if path_mapper is not None and isinstance(recorded_libraries, list):
        recorded_libraries = sorted(
            [dict(row, path=str(map_path(row["path"]).resolve(strict=True)))
             for row in recorded_libraries], key=lambda row: row["path"])
    if recorded_libraries != compiler_libraries(runtime.resolve()):
        raise ValueError("Adapter compiler libraries differ from patched build provenance")
    return info


def record_adapter(args):
    fields = compiler_identity(args.toolchain)
    validate_miri_source(args.miri_source)
    target = args.native_host or fields["host"]
    if target not in HOSTS:
        raise ValueError(f"Unsupported native host: {target}")
    compiler_root = Path(args.runtime_sysroot or args.compiler_sysroot or args.toolchain).resolve()
    compiler_sysroot = Path(args.compiler_sysroot or args.toolchain).resolve()
    build_info = (getattr(args, "compiler_build_info", None)
                  or compiler_root.parent / "compiler-build.json")
    compiler_build = verify_compiler_build(build_info, compiler_sysroot, compiler_root, target)
    libraries = compiler_libraries(compiler_root)
    adapter = Path(args.adapter).resolve(strict=True)
    metadata = Path(args.dependency_metadata).resolve(strict=True)
    write_json(args.output, {
        "schemaVersion": 1, "rustVersion": RUST_VERSION, "rustCommit": RUST_COMMIT,
        "nativeHost": target, "buildHost": fields["host"],
        "adapter": {"path": str(adapter), "sha256": sha256(adapter)},
        "dependencyMetadata": {"path": str(metadata), "sha256": sha256(metadata)},
        "compilerLibraries": libraries,
        "compilerBuild": compiler_build,
        "compilerBoundary": compiler_build["compilerBoundary"],
    })


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "check-build-root":
        parser = argparse.ArgumentParser(description="Refuse build outputs overlapping compiler inputs")
        parser.add_argument("command")
        parser.add_argument("--build-root", type=Path, required=True)
        parser.add_argument("--input-root", type=Path, action="append", required=True)
        args = parser.parse_args()
        ensure_disjoint_build_root(args.build_root, *args.input_root)
        return
    if len(sys.argv) > 1 and sys.argv[1] == "verify-adapter":
        parser = argparse.ArgumentParser(description="Verify adapter and patched compiler provenance")
        parser.add_argument("command")
        parser.add_argument("--adapter-build-info", type=Path, required=True)
        parser.add_argument("--adapter", type=Path, required=True)
        parser.add_argument("--compiler-sysroot", type=Path)
        parser.add_argument("--runtime-sysroot", type=Path)
        parser.add_argument("--native-host", choices=HOSTS, required=True)
        parser.add_argument("--wsl-distro")
        args = parser.parse_args()
        mapper = windows_wsl_path_mapper(args.wsl_distro) if args.wsl_distro else None
        info = verify_adapter_build(args.adapter_build_info, args.adapter,
                                    args.compiler_sysroot, args.runtime_sysroot, args.native_host, mapper)
        print(json.dumps(info, sort_keys=True))
        return
    if len(sys.argv) > 1 and sys.argv[1] == "check-compiler":
        parser = argparse.ArgumentParser(description="Verify patched compiler build provenance")
        parser.add_argument("command")
        parser.add_argument("--compiler-build-info", type=Path, required=True)
        parser.add_argument("--compiler-sysroot", type=Path, required=True)
        parser.add_argument("--runtime-sysroot", type=Path, required=True)
        parser.add_argument("--native-host", choices=HOSTS, required=True)
        args = parser.parse_args()
        result = verify_compiler_build(args.compiler_build_info, args.compiler_sysroot,
                                       args.runtime_sysroot, args.native_host)
        print(json.dumps(result, sort_keys=True))
        return
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
    parser.add_argument("--compiler-build-info", type=Path)
    parser.add_argument("--runtime-sysroot", type=Path)
    parser.add_argument("--miri-source", type=Path, required=True)
    parser.add_argument("--native-host", choices=HOSTS)
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--dependency-metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    record_adapter(parser.parse_args())


if __name__ == "__main__":
    main()
