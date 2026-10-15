"""Verify pinned inputs and unpack the Windows compiler-private component."""

import argparse
import hashlib
from pathlib import Path
import tarfile


SOURCE_DIGEST = "92f51c0345496c6ef1edbba009985c84b612630dd5c7e81ea2cdd826d0d85764"
DEV_DIGEST = "b9914adb9e2d5769fdd49afee5055247fe7673137932f745f594a2f2b9f6e51d"
HOST = "x86_64-pc-windows-gnu"


def verify_source(source: Path) -> None:
    paths = [p.relative_to(source).as_posix() for directory in ("src", "cargo-miri/src")
             for p in (source / directory).rglob("*") if p.is_file()]
    paths.extend(("Cargo.toml", "Cargo.lock", "cargo-miri/Cargo.toml",
                  "cargo-miri/Cargo.lock", "cargo-miri/build.rs"))
    if (source / "build.rs").exists():
        paths.append("build.rs")
    digest = hashlib.sha256()
    for name in sorted(paths):
        data = (source / name).read_bytes().replace(b"\r\n", b"\n")
        digest.update(f"{hashlib.sha256(data).hexdigest()}  {name}\n".encode())
    if digest.hexdigest() != SOURCE_DIGEST:
        raise ValueError(f"Miri source differs from pinned Rust 1.98.1: {digest.hexdigest()}")


def unpack_dev(archive: Path, destination: Path) -> None:
    digest = hashlib.sha256()
    with archive.open("rb") as stream:
        while data := stream.read(1024 * 1024):
            digest.update(data)
    if digest.hexdigest() != DEV_DIGEST:
        raise ValueError("Windows rustc-dev archive checksum differs from official Rust 1.98.1")
    prefix = f"rustc-dev-1.98.1-{HOST}/rustc-dev/lib/rustlib/{HOST}/lib/"
    target = destination / "lib" / "rustlib" / HOST / "lib"
    target.mkdir(parents=True, exist_ok=True)
    count = 0
    with tarfile.open(archive, "r|xz") as bundle:
        for member in bundle:
            if not member.name.startswith(prefix) or member.isdir():
                continue
            relative = member.name[len(prefix):]
            if not member.isfile() or "/" in relative or "\\" in relative or relative in ("", ".", ".."):
                raise ValueError(f"Invalid compiler component member: {member.name}")
            stream = bundle.extractfile(member)
            if stream is None:
                raise ValueError(f"Missing component bytes: {member.name}")
            with stream, (target / relative).open("wb") as output:
                while data := stream.read(1024 * 1024):
                    output.write(data)
            count += 1
    if not list(target.glob("librustc_driver_impl-*.rmeta")):
        raise ValueError("Compiler-private metadata was not found in rustc-dev")
    print(f"Verified and extracted {count} compiler-private files into {target}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    verify = commands.add_parser("verify-source")
    verify.add_argument("source", type=Path)
    normalize = commands.add_parser("normalize-stage")
    normalize.add_argument("source", type=Path)
    unpack = commands.add_parser("unpack-dev")
    unpack.add_argument("archive", type=Path)
    unpack.add_argument("destination", type=Path)
    args = parser.parse_args()
    if args.command == "verify-source":
        verify_source(args.source)
    elif args.command == "normalize-stage":
        verify_source(args.source)
        for path in (args.source / "src").rglob("*.rs"):
            path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n"))
    else:
        unpack_dev(args.archive, args.destination)


if __name__ == "__main__":
    main()
