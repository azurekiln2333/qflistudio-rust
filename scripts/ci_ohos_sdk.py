#!/usr/bin/env python3
"""Install the checksum-pinned OpenHarmony Linux native SDK on a CI runner."""

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import sys
import tarfile
import tempfile
import urllib.request
import zipfile

from miri_build_support import ensure_disjoint_build_root, sha256, write_json


SDK_RELEASE = "6.1"
SDK_ARCHIVE = "ohos-sdk-windows_linux-public.tar.gz"
SDK_SHA256 = "b833b75a64ee46bbd7880921abbb49b733ec5c8171b6684c9b524d57f624cee0"
# Both domains are operated by Huawei. The digest is pinned from its release
# sidecar, not accepted dynamically from the same download connection.
SDK_URLS = tuple(f"https://{domain}/openharmony/os/{SDK_RELEASE}-Release/{SDK_ARCHIVE}"
                for domain in ("mirrors.huaweicloud.com", "repo.huaweicloud.com"))
TARGETS = ("aarch64-linux-ohos", "x86_64-linux-ohos")
ROOT = Path(__file__).resolve().parent.parent


def download_archive(destination):
    errors = []
    for url in SDK_URLS:
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "qfli-native-ci"})
            with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as output:
                shutil.copyfileobj(response, output, length=1024 * 1024)
            if sha256(destination) != SDK_SHA256:
                raise ValueError("OpenHarmony SDK archive checksum differs from the pinned release")
            return url
        except (OSError, ValueError) as error:
            errors.append(f"{url}: {error}")
            destination.unlink(missing_ok=True)
    raise ValueError("OpenHarmony SDK download failed: " + "; ".join(errors))


def native_component(archive, destination):
    """Read only the Linux native ZIP from the verified cross-host SDK bundle."""
    count = 0
    with tarfile.open(archive, "r|gz") as bundle:
        for member in bundle:
            parts = PurePosixPath(member.name).parts
            if (not member.isfile() or "linux" not in parts[:-1]
                    or not parts[-1].startswith("native-") or not parts[-1].endswith(".zip")):
                continue
            count += 1
            if count != 1:
                raise ValueError("SDK archive contains multiple Linux native components")
            with bundle.extractfile(member) as source, destination.open("wb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
    if count != 1:
        raise ValueError("SDK archive has no Linux native component")


def unpack_native(component, destination):
    """Preserve executable modes and confined LLVM tool links inside native/."""
    destination = Path(destination).resolve()
    destination.mkdir(parents=True)
    entries = []
    names = set()
    with zipfile.ZipFile(component) as bundle:
        for entry in bundle.infolist():
            name = PurePosixPath(entry.filename)
            if (not name.parts or name.parts[0] != "native" or name.is_absolute()
                    or ".." in name.parts or "\\" in entry.filename or ":" in entry.filename):
                raise ValueError(f"Unsafe SDK component member: {entry.filename}")
            if name.as_posix() in names:
                raise ValueError(f"Duplicate SDK component member: {entry.filename}")
            names.add(name.as_posix())
            mode = entry.external_attr >> 16
            kind = stat.S_IFMT(mode)
            if kind not in (0, stat.S_IFREG, stat.S_IFDIR, stat.S_IFLNK):
                raise ValueError(f"Unsupported SDK component member: {entry.filename}")
            path = destination.joinpath(*name.parts)
            entries.append((entry, path, mode))
        # Regular files first: a link must never redirect a later file write.
        for entry, path, mode in entries:
            if stat.S_ISLNK(mode):
                continue
            if entry.is_dir():
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(entry) as source, path.open("xb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
                if mode & 0o777:
                    path.chmod(mode & 0o777)
        for entry, path, mode in entries:
            if not stat.S_ISLNK(mode):
                continue
            target = bundle.read(entry).decode("utf-8")
            if (not target or "\\" in target or ":" in target
                    or PurePosixPath(target).is_absolute()
                    or not (path.parent / target).resolve().is_relative_to(destination / "native")):
                raise ValueError(f"SDK link escapes native directory: {entry.filename}")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.symlink_to(target)
    for _, path, mode in entries:
        if stat.S_ISLNK(mode) and (not path.exists()
                                  or not path.resolve().is_relative_to(destination / "native")):
            raise ValueError(f"SDK link is broken or escapes native directory: {path}")


def inspect_sdk(sdk):
    native = sdk / "native"
    metadata = json.loads((native / "oh-uni-package.json").read_text(encoding="utf-8"))
    for tool in ("clang", "clang++", "llvm-ar", "llvm-ranlib", "llvm-readobj", "llvm-readelf", "ld.lld"):
        path = native / "llvm/bin" / tool
        if not path.is_file() or (os.name != "nt" and not os.access(path, os.X_OK)):
            raise ValueError(f"SDK executable is missing: {path}")
    for target in TARGETS:
        if not (native / "sysroot/usr/lib" / target / "libc.so").is_file():
            raise ValueError(f"SDK libc is missing for {target}")
    resources = [path for path in (native / "llvm/lib/clang").glob("*")
                 if all((path / "lib" / target / "libclang_rt.builtins.a").is_file()
                        for target in TARGETS)]
    if len(resources) != 1:
        raise ValueError("SDK requires exactly one Clang resource directory for both OHOS targets")
    return {"sdkRoot": str(sdk), "nativeSdk": str(native), "resourceDir": str(resources[0]),
            "sdkVersion": metadata["version"], "apiVersion": metadata["apiVersion"]}


def install_sdk(destination):
    destination = ensure_disjoint_build_root(destination, ROOT)
    if destination.exists():
        raise ValueError("OHOS SDK destination must be fresh")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="qfli-ohos-sdk-", dir=destination.parent) as temporary:
        temporary = Path(temporary)
        archive = temporary / SDK_ARCHIVE
        url = download_archive(archive)
        component = temporary / "native-linux.zip"
        native_component(archive, component)
        archive.unlink()
        stage = temporary / "installed"
        unpack_native(component, stage / "sdk")
        inspect_sdk(stage / "sdk")
        stage.rename(destination)
    result = inspect_sdk(destination / "sdk")
    result.update({"release": SDK_RELEASE, "archiveUrl": url, "archiveSha256": SDK_SHA256})
    write_json(destination / "sdk-build.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not sys.platform.startswith("linux"):
        parser.error("This SDK installer targets Linux CI build hosts")
    result = install_sdk(args.destination)
    if args.output:
        write_json(args.output, result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
