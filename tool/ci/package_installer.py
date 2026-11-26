#!/usr/bin/env python3
"""Package existing Flutter outputs on GitHub; never build or launch the app.

Packages are promoted only after every selected package passes verification.
The orchestrator must re-create SHA256SUMS after its final manifest update.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import time
import zipfile

from ci_support import (
    APP_ID, APP_NAME, BINARY_NAME, HOMEPAGE, PACKAGE_NAMES, ROOT, SIGNING, TARGETS,
    add_target_arguments, read_json, read_version, redact, report_failure,
    require_hosted_runner, resolve_target, run, sha256, write_json,
)

sys.path.insert(0, str(ROOT / "scripts"))
from miri_build_support import GUEST_TARGET, RUST_COMMIT, RUST_VERSION
from package_miri_runtime import inspect_library


ARMV7_BLOCKER = (
    "Android armeabi-v7a is not implemented: compiler/backend compatibility, "
    "host selection, NDK triple, ELF32 inspection, ABI maps and Gradle must be "
    "verified together. Two APKs do not satisfy the three-ABI requirement."
)
ANDROID_ABIS = {"arm64": "arm64-v8a", "x64": "x86_64"}
DEB_NAME = "qfli-rust-core"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def runner_scratch():
    value = os.environ.get("RUNNER_TEMP")
    require(value and Path(value).is_dir(), "Packaging scratch requires RUNNER_TEMP")
    return Path(value).resolve()


def safe_relative(value):
    require(isinstance(value, str) and value and not any(ord(c) < 32 for c in value),
            "Package path is empty or contains control characters")
    require("\\" not in value and ":" not in value and not value.startswith("/"),
            f"Package path is not relative: {value!r}")
    path = PurePosixPath(value)
    require(all(part not in ("", ".", "..") for part in value.split("/")),
            f"Package path is not canonical: {value!r}")
    return path


def is_link(path):
    return path.is_symlink() or getattr(path, "is_junction", lambda: False)()


def tree_entries(root):
    """Return a sorted, confined file/link inventory without following links."""
    root = Path(root)
    require(root.is_dir() and not is_link(root), f"Bundle root must be a real directory: {root}")
    resolved = root.resolve()
    entries = {}
    for folder, directories, files in os.walk(root, followlinks=False):
        directories.sort()
        for name in sorted(directories + files):
            path = Path(folder) / name
            relative = path.relative_to(root).as_posix()
            safe_relative(relative)
            require(not getattr(path, "is_junction", lambda: False)(),
                    f"Junctions are not package inputs: {relative}")
            if path.is_symlink():
                target = os.readlink(path)
                require(not Path(target).is_absolute() and "\\" not in target and ":" not in target,
                        f"Bundle link must be relative: {relative}")
                require(path.resolve().is_relative_to(resolved) and path.exists(),
                        f"Bundle link escapes its tree or is broken: {relative}")
                entries[relative] = {"link": target}
            elif path.is_file():
                entries[relative] = {"sha256": sha256(path), "size": path.stat().st_size}
            else:
                require(path.is_dir(), f"Unsupported bundle entry: {relative}")
        directories[:] = [name for name in directories if not (Path(folder) / name).is_symlink()]
    return dict(sorted(entries.items()))


def copy_bundle(source, destination):
    expected = tree_entries(source)
    shutil.copytree(source, destination, symlinks=True)
    require(tree_entries(destination) == expected, "Bundle changed while staging")
    return expected


def zip_tree(source, archive, prefix):
    """Stable ordering, timestamps and modes; no mobile bundle symlink guessing."""
    source = Path(source)
    safe_relative(prefix)
    entries = tree_entries(source)
    require(all("link" not in row for row in entries.values()),
            "Mobile ZIP input contains symlinks; an explicit layout adapter is required")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for relative, row in entries.items():
            path = source / relative
            require(sha256(path) == row["sha256"], f"ZIP source changed: {relative}")
            info = zipfile.ZipInfo(f"{prefix}/{relative}", date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            mode = 0o755 if path.stat().st_mode & 0o111 else 0o644
            info.external_attr = (stat.S_IFREG | mode) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            with path.open("rb") as source_stream, bundle.open(info, "w", force_zip64=True) as output:
                shutil.copyfileobj(source_stream, output, 1024 * 1024)


def archive_index(bundle):
    entries = {}
    folded = set()
    for entry in bundle.infolist():
        name = entry.filename.rstrip("/") if entry.is_dir() else entry.filename
        safe_relative(name)
        require(name not in entries and name.casefold() not in folded,
                f"Duplicate or case-colliding archive member: {name}")
        mode = entry.external_attr >> 16
        require(stat.S_IFMT(mode) in (0, stat.S_IFREG, stat.S_IFDIR),
                f"Archive links and special files are not supported: {name}")
        require(not entry.flag_bits & 1, f"Encrypted package member: {name}")
        entries[name] = entry
        folded.add(name.casefold())
    return entries


def archive_file(bundle, entries, name):
    safe_relative(name)
    require(name in entries and not entries[name].is_dir(), f"Package member is missing: {name}")
    return bundle.read(entries[name])


def member_hash(bundle, entries, name):
    require(name in entries and not entries[name].is_dir(), f"Package member is missing: {name}")
    digest = hashlib.sha256()
    with bundle.open(entries[name]) as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def runtime_manifest(root, platform, arch):
    require(arch in ("arm64", "x64"), ARMV7_BLOCKER)
    path = Path(root) / "assets/miri" / f"manifest.{platform}-{arch}.json"
    require(path.is_file(), f"Missing native runtime manifest: {path}")
    manifest = read_json(path)
    expected_host = {
        ("android", "arm64"): "aarch64-linux-android",
        ("android", "x64"): "x86_64-linux-android",
        ("ios", "arm64"): "aarch64-apple-ios",
        ("ohos", "arm64"): "aarch64-unknown-linux-ohos",
    }.get((platform, arch))
    require(expected_host and manifest.get("nativeHost") == expected_host,
            "Runtime manifest nativeHost differs from the package target")
    require(manifest.get("rustVersion") == RUST_VERSION
            and manifest.get("rustCommit") == RUST_COMMIT
            and manifest.get("guestTarget") == GUEST_TARGET,
            "Runtime manifest is not for the pinned compiler and guest")
    if platform == "ohos":
        # The existing OHOS schema has nativeHost/name, not platform/architecture/path.
        require(manifest.get("schemaVersion") == 1, "OHOS requires its schema-1 validation adapter")
    else:
        require(manifest.get("schemaVersion") == 2 and manifest.get("platform") == platform
                and manifest.get("architecture") == arch, "Runtime schema/architecture differs")
    libraries = manifest.get("nativeLibraries")
    files = manifest.get("files")
    require(isinstance(libraries, list) and libraries and isinstance(files, list) and files,
            "Runtime manifest has an empty native or guest inventory")
    paths = []
    for row in libraries:
        require(isinstance(row, dict), "Malformed native library row")
        relative = row.get("name") if platform == "ohos" else row.get("path")
        safe_relative(relative)
        require(re.fullmatch(r"[0-9a-f]{64}", str(row.get("sha256", ""))),
                "Native library hash is missing")
        if platform in ("android", "ohos"):
            require(len(PurePosixPath(relative).parts) == 1 and relative.endswith(".so"),
                    "Mobile ELF library path must be a direct .so member")
        paths.append(relative)
    require(len(paths) == len(set(paths)), "Runtime manifest repeats a native library")
    require(any("qfli_miri" in name for name in paths)
            and any("rustc_driver" in name for name in paths)
            and any("rustc_codegen" in name or "qfli_codegen" in name for name in paths),
            "Runtime inventory lacks the adapter, compiler driver or codegen backend")
    return path, manifest


def verify_runtime_members(bundle, entries, root, platform, arch, assets, libraries,
                           *, transformed_native=False):
    path, manifest = runtime_manifest(root, platform, arch)
    packaged = archive_file(bundle, entries, assets + "assets/miri/" + path.name)
    require(packaged == path.read_bytes(), "Packaged runtime manifest differs from the selected input")
    if platform == "ohos":
        legacy = Path(root) / "assets/miri/manifest.json"
        if legacy.is_file():
            require(legacy.read_bytes() == path.read_bytes(), "OHOS legacy manifest is stale")
            require(archive_file(bundle, entries, assets + "assets/miri/manifest.json") == packaged,
                    "Packaged OHOS legacy manifest differs")
    for row in manifest["files"]:
        require(isinstance(row, dict), "Malformed runtime asset row")
        name = row.get("asset")
        safe_relative(name)
        require(len(PurePosixPath(name).parts) == 1, "Runtime asset is not a basename")
        member = assets + "assets/miri/" + name
        require(member in entries and entries[member].file_size == row.get("size")
                and member_hash(bundle, entries, member) == row.get("sha256"),
                f"Packaged runtime asset differs: {name}")
    final_hashes = {}
    for row in manifest["nativeLibraries"]:
        relative = row["name"] if platform == "ohos" else row["path"]
        member = libraries + relative
        digest = member_hash(bundle, entries, member)
        if not transformed_native:
            require(digest == row["sha256"], f"Packaged native library differs: {relative}")
            if "size" in row:
                require(entries[member].file_size == row["size"], f"Native size differs: {relative}")
        # Apple app signing can alter framework bytes. Preserve the final hash;
        # input provenance remains the responsibility of install-runtime.
        final_hashes[relative] = digest
    return final_hashes


def android_tools(name):
    sdk = os.environ.get("ANDROID_SDK_ROOT") or os.environ.get("ANDROID_HOME")
    require(sdk, "Android package checks require ANDROID_SDK_ROOT or ANDROID_HOME")
    tools = Path(sdk) / "build-tools"
    versions = sorted((path for path in tools.glob("*") if re.fullmatch(r"\d+(?:\.\d+)+", path.name)),
                      key=lambda path: tuple(map(int, path.name.split("."))), reverse=True)
    for version in versions:
        candidate = version / (name + (".bat" if os.name == "nt" and name == "apksigner" else ""))
        if candidate.is_file():
            return candidate
    raise RuntimeError(f"Android SDK tool is missing: {name}")


def verify_android(apk, root, arch, reports):
    abi = ANDROID_ABIS[arch]
    with zipfile.ZipFile(apk) as bundle:
        entries = archive_index(bundle)
        observed = {name.split("/")[1] for name in entries if name.startswith("lib/")
                    and not entries[name].is_dir()}
        require(observed == {abi}, f"APK ABI set differs: {sorted(observed)}")
        archive_file(bundle, entries, "AndroidManifest.xml")
        archive_file(bundle, entries, f"lib/{abi}/libflutter.so")
        archive_file(bundle, entries, f"lib/{abi}/libapp.so")
        final_hashes = verify_runtime_members(bundle, entries, root, "android", arch,
                                             "assets/flutter_assets/", f"lib/{abi}/")
    run([android_tools("zipalign"), "-c", "-P", "16", "4", apk], reports / f"zipalign-{arch}.log")
    signature = run([android_tools("apksigner"), "verify", "--verbose", "--print-certs", apk],
                    reports / f"apksigner-{arch}.log")
    require("Android Debug" in signature, "APK is not signed by the expected testing debug key")
    badging = run([android_tools("aapt2"), "dump", "badging", apk], reports / f"apk-identity-{arch}.log")
    require(re.search(r"(?m)^package: name='" + re.escape(APP_ID) + r"'", badging),
            "APK application identifier differs")
    return {"validation": ["single-abi", "bundle-id", "flutter-payload", "runtime-assets-and-hashes",
                           "zipalign-16k", "apksigner-debug-key"],
            "nativeOutputHashes": final_hashes, "installVerified": False}


def package_android(root, stage, reports, arch):
    require(arch == "arm64-x64", ARMV7_BLOCKER)
    require(len(PACKAGE_NAMES[("android", arch)]) == 2, ARMV7_BLOCKER)
    results = []
    for native_arch, filename in zip(("arm64", "x64"), PACKAGE_NAMES[("android", arch)]):
        abi = ANDROID_ABIS[native_arch]
        source = root / "build/app/outputs/flutter-apk" / f"app-{abi}-release.apk"
        destination = stage / filename
        require(source.is_file() and not is_link(source), f"Missing Flutter APK: {source}")
        shutil.copy2(source, destination)
        checks = verify_android(destination, root, native_arch, reports)
        results.append((destination, "apk", checks))
    return results


def app_info(app, platform):
    plist = app / ("Contents/Info.plist" if platform == "macos" else "Info.plist")
    require(plist.is_file(), f"Application Info.plist is missing: {plist}")
    info = plistlib.loads(plist.read_bytes())
    require(info.get("CFBundleIdentifier") == APP_ID, "Application bundle identifier differs")
    executable = info.get("CFBundleExecutable")
    safe_relative(executable)
    require(len(PurePosixPath(executable).parts) == 1, "Application executable must be a basename")
    binary = app / ("Contents/MacOS" if platform == "macos" else "") / executable
    require(binary.is_file(), "Application executable is missing")
    return binary


def package_ios(root, stage, reports, arch):
    require(arch == "arm64", "Only the iOS arm64 device package is supported")
    source = root / "build/ios/iphoneos/Runner.app"
    app_info(source, "ios")
    require(not (source / "embedded.mobileprovision").exists(),
            "Unsigned IPA unexpectedly includes a provisioning profile")
    run(["xcrun", "lipo", "-verify_arch", "arm64", app_info(source, "ios")], reports / "ios-arch.log")
    _, runtime = runtime_manifest(root, "ios", arch)
    for index, row in enumerate(runtime["nativeLibraries"]):
        relative = safe_relative(row["path"])
        require(len(relative.parts) == 2 and relative.parts[0].endswith(".framework"),
                "iOS runtime must use direct framework executable paths")
        binary = source / "Frameworks" / relative
        inspect_library(binary, "aarch64-apple-ios")
        run(["codesign", "--verify", "--strict", binary.parent], reports / f"ios-framework-{index}.log")
        original = root / "native/build/runtime/aarch64-apple-ios" / relative
        require(original.is_file() and sha256(original) == row["sha256"],
                f"iOS input framework no longer matches its runtime record: {relative}")
        # Compare executable code after removing signatures from disposable
        # copies. Re-signing is allowed; swapping validly signed code is not.
        before, after = stage / f"ios-input-{index}", stage / f"ios-output-{index}"
        shutil.copy2(original, before)
        shutil.copy2(binary, after)
        run(["codesign", "--remove-signature", before], reports / f"ios-input-signature-{index}.log")
        run(["codesign", "--remove-signature", after], reports / f"ios-output-signature-{index}.log")
        require(sha256(before) == sha256(after), f"Embedded iOS runtime code differs: {relative}")
    destination = stage / PACKAGE_NAMES[("ios", arch)][0]
    zip_tree(source, destination, "Payload/Runner.app")
    with zipfile.ZipFile(destination) as bundle:
        entries = archive_index(bundle)
        require(all(name.startswith("Payload/Runner.app/") for name in entries), "IPA escapes Payload/Runner.app")
        for name in ("Flutter.framework/Flutter", "App.framework/App"):
            archive_file(bundle, entries, "Payload/Runner.app/Frameworks/" + name)
        require(not any(name.endswith("embedded.mobileprovision")
                        or name.startswith("Payload/Runner.app/_CodeSignature/") for name in entries),
                "Unsigned IPA unexpectedly contains an application signature/profile")
        final_hashes = verify_runtime_members(
            bundle, entries, root, "ios", arch,
            "Payload/Runner.app/Frameworks/App.framework/flutter_assets/",
            "Payload/Runner.app/Frameworks/", transformed_native=True)
    return [(destination, "ipa", {"validation": ["payload-layout", "bundle-id", "arm64-device",
             "flutter-frameworks", "runtime-framework-platform-signatures-and-input-code",
             "runtime-assets-and-final-hashes", "no-app-profile-or-signature"],
             "nativeOutputHashes": final_hashes, "installVerified": False})]


def ohos_bundle_id(root):
    # The checked-in file is strict JSON despite its .json5 suffix. Fail rather
    # than guess if the source contract changes to general JSON5.
    profile = read_json(Path(root) / "ohos/AppScope/app.json5")
    identity = profile.get("app", {}).get("bundleName")
    require(isinstance(identity, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+", identity),
            "OHOS source bundleName is missing or malformed")
    return identity


def package_ohos(root, stage, reports, arch):
    require(arch == "arm64", "The HAP module excludes x86_64; only arm64 is supported")
    candidates = sorted((root / "ohos/entry/build/default/outputs/default").glob("*-unsigned.hap"))
    require(len(candidates) == 1, "Expected exactly one unsigned Flutter HAP")
    destination = stage / PACKAGE_NAMES[("ohos", arch)][0]
    shutil.copy2(candidates[0], destination)
    with zipfile.ZipFile(destination) as bundle:
        entries = archive_index(bundle)
        module = json.loads(archive_file(bundle, entries, "module.json"))
        require(module.get("app", {}).get("bundleName") == ohos_bundle_id(root),
                "HAP application identifier differs from ohos/AppScope/app.json5")
        require(module.get("module", {}).get("type") == "entry", "HAP entry module is missing")
        observed = {name.split("/")[1] for name in entries if name.startswith("libs/")
                    and not entries[name].is_dir()}
        require(observed == {"arm64-v8a"}, f"Unexpected HAP ABI set: {sorted(observed)}")
        for library in ("libflutter.so", "libapp.so"):
            archive_file(bundle, entries, "libs/arm64-v8a/" + library)
        final_hashes = verify_runtime_members(bundle, entries, root, "ohos", arch,
                     "resources/rawfile/flutter_assets/", "libs/arm64-v8a/")
    # HAP signing uses an out-of-ZIP signing block. The build contract supplies
    # only the -unsigned.hap product; do not infer device readiness from ZIP checks.
    return [(destination, "hap", {"validation": ["unsigned-build-product", "bundle-id",
             "arm64-only", "flutter-payload", "ohos-schema1-runtime-and-hashes"],
             "nativeOutputHashes": final_hashes, "installVerified": False,
             "signatureVerified": False, "bundleIdentifier": ohos_bundle_id(root)})]


def desktop_bundle(root, platform, arch):
    if platform == "linux":
        source = root / f"build/linux/{arch}/release/bundle"
        required = [BINARY_NAME, "lib/libflutter_linux_gtk.so", "data/icudtl.dat"]
    elif platform == "windows":
        source = root / f"build/windows/{arch}/runner/Release"
        required = [BINARY_NAME + ".exe", "flutter_windows.dll", "data/icudtl.dat"]
    else:
        raise RuntimeError(f"No desktop bundle adapter for {platform}")
    tree_entries(source)
    for relative in required:
        require((source / relative).is_file(), f"Flutter bundle member is missing: {relative}")
    require((source / "data/flutter_assets").is_dir(), "Flutter application assets are missing")
    return source


def package_linux(root, stage, reports, arch):
    require(arch == "x64", "Linux installer supports x64 only")
    source = desktop_bundle(root, "linux", arch)
    package = stage / "deb-root"
    payload = package / "opt" / DEB_NAME
    payload.parent.mkdir(parents=True)
    expected = copy_bundle(source, payload)
    (payload / BINARY_NAME).chmod(0o755)
    control = package / "DEBIAN/control"
    control.parent.mkdir()
    version = read_version(root / "pubspec.yaml")
    control.write_text(f"Package: {DEB_NAME}\nVersion: {version}\nArchitecture: amd64\n"
                       "Section: devel\nPriority: optional\nMaintainer: QFLI contributors\n"
                       "Depends: libgtk-3-0, libstdc++6, libc6, libgcc-s1, libblkid1, liblzma5\n"
                       f"Homepage: {HOMEPAGE}\nDescription: QFLI offline Rust editor\n"
                       " Requires system cargo and rustc on PATH for desktop Rust execution.\n",
                       encoding="utf-8", newline="\n")
    launcher = package / "usr/bin" / DEB_NAME
    launcher.parent.mkdir(parents=True)
    launcher.write_text(f'#!/bin/sh\nexec /opt/{DEB_NAME}/{BINARY_NAME} "$@"\n', encoding="utf-8", newline="\n")
    launcher.chmod(0o755)
    desktop = package / "usr/share/applications" / f"{APP_ID}.desktop"
    desktop.parent.mkdir(parents=True)
    desktop.write_text(f"[Desktop Entry]\nType=Application\nName={APP_NAME}\nExec={DEB_NAME}\n"
                       f"Icon={APP_ID}\nTerminal=false\nCategories=Development;IDE;\n",
                       encoding="utf-8", newline="\n")
    icon = package / "usr/share/icons/hicolor/256x256/apps" / f"{APP_ID}.png"
    icon.parent.mkdir(parents=True)
    shutil.copy2(root / "assets/app_icon.png", icon)
    destination = stage / PACKAGE_NAMES[("linux", arch)][0]
    environment = dict(os.environ, SOURCE_DATE_EPOCH=os.environ.get("SOURCE_DATE_EPOCH", "0"))
    run(["dpkg-deb", "--root-owner-group", "--build", package, destination], reports / "deb-build.log", env=environment)
    for field, value in (("Package", DEB_NAME), ("Version", version), ("Architecture", "amd64")):
        actual = run(["dpkg-deb", "--field", destination, field], reports / f"deb-field-{field}.log").strip()
        require(actual == value, f"Debian {field} differs")
    installed = Path("/opt") / DEB_NAME
    installed_launcher = Path("/usr/bin") / DEB_NAME
    require(not installed.exists() and not installed_launcher.exists(), "Refusing to replace an installed application")
    launcher_run = package / "usr/bin" / DEB_NAME
    require(os.access(launcher_run, os.X_OK), "Staged Linux launcher is not executable")
    try:
        run(["sudo", "apt-get", "install", "--no-install-recommends", "-y", destination], reports / "deb-install.log", timeout=1200)
        require(tree_entries(installed) == expected, "Installed Debian payload differs from the Flutter bundle")
        require(installed_launcher.read_bytes() == launcher.read_bytes(), "Installed launcher differs")
        for index, binary in enumerate([installed / BINARY_NAME, *sorted((installed / "lib").glob("*.so*"))]):
            output = run(["ldd", binary], reports / f"ldd-{index}.log")
            require("not found" not in output, f"Unresolved Linux runtime dependency: {binary.name}")
    finally:
        run(["sudo", "apt-get", "remove", "-y", DEB_NAME], reports / "deb-remove.log", timeout=1200)
    require(not installed.exists() and not installed_launcher.exists(), "Debian uninstall left application files")
    return [(destination, "deb", {"validation": ["bundle-layout", "control-fields", "apt-install",
             "installed-file-hashes", "launcher", "ldd", "apt-remove"], "installVerified": True})]


def windows_wait(command, log):
    # Start-Process -Wait includes the setup/uninstaller's child process tree.
    quote = lambda value: "'" + str(value).replace("'", "''") + "'"
    arguments = subprocess.list2cmdline([str(value) for value in command[1:]])
    script = (f"$p = Start-Process -FilePath {quote(command[0])} -ArgumentList {quote(arguments)} "
              "-Wait -PassThru; exit $p.ExitCode")
    return run(["pwsh", "-NoProfile", "-NonInteractive", "-Command", script], log, timeout=1200)


def package_windows(root, stage, reports, arch):
    require(arch == "x64", "Windows installer supports x64 only")
    source = desktop_bundle(root, "windows", arch)
    binary = (source / (BINARY_NAME + ".exe")).read_bytes()
    require(binary.startswith(b"MZ") and len(binary) >= 64, "Windows executable is not PE")
    offset = struct.unpack_from("<I", binary, 60)[0]
    require(binary[offset:offset + 4] == b"PE\0\0" and len(binary) >= offset + 6
            and struct.unpack_from("<H", binary, offset + 4)[0] == 0x8664,
            "Windows executable is not x64")
    bundle = stage / "windows-bundle"
    expected = copy_bundle(source, bundle)
    require(all("link" not in row for row in expected.values()), "Windows installer input contains links")
    compiler = (os.environ.get("QFLI_ISCC") or shutil.which("ISCC.exe")
                or str(Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Inno Setup 6/ISCC.exe"))
    require(Path(compiler).is_file(), "Inno Setup compiler is unavailable; set QFLI_ISCC")
    destination = stage / PACKAGE_NAMES[("windows", arch)][0]
    version = read_version(root / "pubspec.yaml")
    numeric_version = version.replace("+", ".") if "+" in version else version + ".0"
    run([compiler, "/Qp", f"/DBundleDir={bundle}", f"/DOutputDir={stage}",
         f"/DInstallerBase={destination.stem}", f"/DAppVersion={version}",
         f"/DFileVersion={numeric_version}", Path(__file__).with_name("windows_installer.iss")],
        reports / "inno-build.log")
    require(destination.is_file(), "Inno Setup produced no installer")
    install = stage / "installed-windows"
    try:
        windows_wait([destination, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-",
                      "/CURRENTUSER", f"/DIR={install}", f"/LOG={reports / 'windows-install-detail.log'}"],
                     reports / "windows-install.log")
        actual = tree_entries(install)
        extras = set(actual) - set(expected)
        require(all(re.fullmatch(r"unins\d{3}\.(exe|dat|msg)", name) for name in extras),
                "Windows installation contains unexpected files")
        require({name: actual.get(name) for name in expected} == expected,
                "Installed Windows payload differs from the Flutter bundle")
    finally:
        uninstallers = sorted(install.glob("unins*.exe"))
        if uninstallers:
            require(len(uninstallers) == 1, "Ambiguous Windows uninstaller")
            windows_wait([uninstallers[0], "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                          f"/LOG={reports / 'windows-uninstall-detail.log'}"], reports / "windows-uninstall.log")
    deadline = time.monotonic() + 30
    while install.exists() and any(install.iterdir()) and time.monotonic() < deadline:
        time.sleep(0.25)
    require(not install.exists() or not any(install.iterdir()), "Windows uninstall left application files")
    return [(destination, "exe", {"validation": ["bundle-layout", "x64-pe", "silent-install",
             "installed-file-hashes", "silent-uninstall"], "installVerified": True})]


def verify_macos(app, arch, reports, label):
    executable = app_info(app, "macos")
    run(["xcrun", "lipo", "-verify_arch", "arm64" if arch == "arm64" else "x86_64", executable],
        reports / f"macos-arch-{label}.log")
    run(["codesign", "--verify", "--deep", "--strict", app], reports / f"macos-signature-{label}.log")
    signature = run(["codesign", "--display", "--verbose=4", app], reports / f"macos-signing-{label}.log")
    require("Signature=adhoc" in signature, "macOS package requires an explicitly ad hoc-signed app")


def package_macos(root, stage, reports, arch):
    require(arch in ("arm64", "x64"), "Unsupported macOS architecture")
    candidates = sorted((root / "build/macos/Build/Products/Release").glob("*.app"))
    require(len(candidates) == 1, "Expected exactly one release macOS application")
    contents = stage / "dmg-root"
    contents.mkdir()
    app = contents / (APP_NAME + ".app")
    expected = copy_bundle(candidates[0], app)
    verify_macos(app, arch, reports, "staged")
    (contents / "Applications").symlink_to("/Applications", target_is_directory=True)
    destination = stage / PACKAGE_NAMES[("macos", arch)][0]
    run(["hdiutil", "create", "-volname", APP_NAME, "-srcfolder", contents, "-format", "UDZO", "-ov", destination],
        reports / "dmg-create.log")
    run(["hdiutil", "verify", destination], reports / "dmg-verify.log")
    mount = stage / "mounted-dmg"
    mount.mkdir()
    attached = False
    try:
        run(["hdiutil", "attach", "-readonly", "-nobrowse", "-mountpoint", mount, destination], reports / "dmg-mount.log")
        attached = True
        mounted = mount / app.name
        require(tree_entries(mounted) == expected, "Mounted DMG payload differs")
        require((mount / "Applications").is_symlink()
                and os.readlink(mount / "Applications") == "/Applications", "DMG Applications link differs")
        verify_macos(mounted, arch, reports, "mounted")
    finally:
        if attached or os.path.ismount(mount):
            run(["hdiutil", "detach", mount], reports / "dmg-unmount.log")
    return [(destination, "dmg", {"validation": ["bundle-id", "architecture", "ad-hoc-signature",
             "hdiutil-verify", "read-only-mount", "mounted-file-hashes", "applications-link"],
             "installVerified": False, "mountVerified": True, "notarized": False})]


PACKAGERS = {"android": package_android, "ios": package_ios, "ohos": package_ohos,
             "linux": package_linux, "windows": package_windows, "macos": package_macos}


def write_checksums(output):
    """Call again after finalization: manifest/status changes invalidate old sums."""
    output = Path(output)
    require(not is_link(output / "SHA256SUMS"), "Checksum output must not be a link")
    entries = tree_entries(output)
    require(all("link" not in row for row in entries.values()), "Artifact output must not contain links")
    lines = [f"{row['sha256']}  {name}\n" for name, row in entries.items() if name != "SHA256SUMS"]
    (output / "SHA256SUMS").write_bytes("".join(lines).encode("utf-8"))


def signing_note(platform):
    details = {
        "android": "APKs use the Android debug key for testing. They are not store releases. " + ARMV7_BLOCKER,
        "ios": "Unsigned IPA. Signing identity and a matching provisioning profile are required before device installation.",
        "ohos": "Unsigned HAP build product. Matching certificate, profile and signing key are required before device installation. ZIP verification is not signature verification.",
        "linux": "Unsigned Debian package. Desktop Rust execution requires cargo and rustc on PATH.",
        "windows": "Unsigned Windows setup executable. Desktop Rust execution requires cargo and rustc on PATH.",
        "macos": "Ad hoc-signed application; not notarized. Desktop Rust execution requires cargo and rustc on PATH.",
    }
    return (f"Signing status: {SIGNING[platform]}\n{details[platform]}\n"
            "Device ready: false. No application launch, UI test or target-device execution was verified.\n")


def remove_packages(output):
    packages = output / "packages"
    require(not is_link(packages), "Refusing to clean a linked packages directory")
    publication = output / ".verified-packages"
    require(not is_link(publication), "Refusing to clean a linked publication directory")
    if packages.exists():
        shutil.rmtree(packages)
    if publication.exists():
        shutil.rmtree(publication)
    (output / "reports/packages.json").unlink(missing_ok=True)
    (output / "SHA256SUMS").unlink(missing_ok=True)


def package_target(platform, arch, output, *, root=ROOT):
    require_hosted_runner()
    root, output = Path(root).resolve(), Path(output).resolve()
    require(output.is_relative_to(root / "build/app-artifacts")
            and output != root / "build/app-artifacts", "Artifact directory must be a target below build/app-artifacts")
    require(not is_link(output / "reports") and not is_link(output / "manifest.json")
            and not is_link(output / "SIGNING.txt"), "Artifact metadata must not be linked")
    if output.exists():
        require(all("link" not in row for row in tree_entries(output).values()),
                "Artifact metadata tree must not contain links")
    require((platform, arch) in TARGETS and (platform, arch) in PACKAGE_NAMES,
            ARMV7_BLOCKER if platform == "android" else "Unsupported package target")
    require(platform != "android" or arch == "arm64-x64", ARMV7_BLOCKER)
    manifest_path = output / "manifest.json"
    manifest = read_json(manifest_path)
    require(manifest.get("platform") == platform and manifest.get("arch") == arch,
            "Packaging target differs from the initialized manifest")
    require(manifest.get("status") not in ("failed", "cancelled"),
            "Reinitialize the failed/cancelled build before packaging")
    require("build" in manifest.get("completedStages", []),
            "Packaging requires a completed build stage for this manifest")
    reports = output / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    remove_packages(output)
    (reports / "package-failure.txt").unlink(missing_ok=True)
    manifest.pop("error", None)
    manifest.update(stage="package", packageStatus="incomplete", packages=[],
                    signing=SIGNING[platform], deviceReady=False, deviceTests="not_run",
                    applicationUiVerified=False)
    blockers = [ARMV7_BLOCKER] if platform == "android" else []
    manifest["packageCoverage"] = {"complete": not blockers, "blockers": blockers}
    write_json(manifest_path, manifest)
    (output / "SIGNING.txt").write_text(signing_note(platform), encoding="utf-8", newline="\n")
    try:
        expected_os = {"android": "linux", "ios": "darwin", "ohos": "linux",
                       "linux": "linux", "windows": "win32", "macos": "darwin"}[platform]
        require(sys.platform == expected_os, f"{platform} packaging requires a {expected_os} hosted runner")
        with tempfile.TemporaryDirectory(prefix=f"qfli-package-{platform}-{arch}-", dir=runner_scratch()) as temporary:
            stage = Path(temporary)
            results = PACKAGERS[platform](root, stage, reports, arch)
            expected = set(PACKAGE_NAMES[(platform, arch)])
            require(len(results) == len(expected) and {path.name for path, _, _ in results} == expected,
                    "Verified package filenames differ from the declared target")
            rows = []
            for path, kind, checks in results:
                require(path.parent == stage and path.is_file() and not is_link(path)
                        and path.stat().st_size > 0, "Packager returned an invalid output")
                require(kind == path.suffix.lstrip(".") and checks.get("validation")
                        and isinstance(checks.get("installVerified"), bool),
                        "Packager omitted its format or verification evidence")
                if platform in ("linux", "windows"):
                    require(checks["installVerified"], "Desktop installer install/uninstall was not verified")
                rows.append({**checks, "file": path.name, "format": kind, "size": path.stat().st_size,
                             "sha256": sha256(path), "signing": SIGNING[platform], "deviceReady": False})
            rows.sort(key=lambda row: row["file"])
            # A half-populated directory is never published under packages/.
            promotion = output / ".verified-packages"
            promotion.mkdir()
            for path, _, _ in results:
                shutil.copy2(path, promotion / path.name)
            for row in rows:
                published = promotion / row["file"]
                require(published.stat().st_size == row["size"] and sha256(published) == row["sha256"],
                        f"Package changed during publication: {row['file']}")
            promotion.replace(output / "packages")
            write_json(reports / "packages.json", {"schemaVersion": 1, "platform": platform,
                       "arch": arch, "packages": rows, "coverage": manifest["packageCoverage"],
                       "deviceTests": "not_run", "applicationUiVerified": False})
            manifest.update(packageStatus="verified", packages=rows)
            completed = manifest.setdefault("completedStages", [])
            if "package" not in completed:
                completed.append("package")
            # Overall success belongs to app_build.finalize, not to this stage.
            manifest["status"] = "incomplete"
            write_json(manifest_path, manifest)
            write_checksums(output)
            return rows
    except BaseException as error:
        remove_packages(output)
        manifest.update(status="cancelled" if isinstance(error, KeyboardInterrupt) else "failed",
                        packageStatus="failed", packages=[], error=redact(str(error)))
        manifest["completedStages"] = [stage for stage in manifest.get("completedStages", []) if stage != "package"]
        write_json(manifest_path, manifest)
        report_failure(output, "package", redact(str(error)))
        write_checksums(output)
        raise


def main():
    require_hosted_runner()
    parser = argparse.ArgumentParser(description=__doc__)
    add_target_arguments(parser)
    args = parser.parse_args()
    if args.platform == "android" and args.arch != "arm64-x64":
        parser.error(ARMV7_BLOCKER)
    args = resolve_target(args, parser)
    package_target(args.platform, args.arch, args.output)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        print(f"error: {redact(str(error))}", file=sys.stderr)
        sys.exit(1)
