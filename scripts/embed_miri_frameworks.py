#!/usr/bin/env python3
"""Xcode build phase: embed the selected runtime frameworks and sign with the app."""

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import subprocess

from miri_build_support import run, sha256
from package_miri_runtime import inspect_library, safe_relative


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("platform", choices=("ios", "macos"))
    args = parser.parse_args()
    if sys.platform != "darwin":
        raise ValueError("Framework embedding requires Xcode on macOS")
    root = Path(os.environ["PROJECT_DIR"]).resolve().parent
    asset_root = root / "assets/miri"
    if not list(asset_root.glob(f"manifest.{args.platform}-*.json")):
        return
    architectures = os.environ.get("ARCHS", "").split()
    if not architectures or any(arch not in ("arm64", "x86_64") for arch in architectures):
        raise ValueError("Runtime embedding requires explicit arm64/x86_64 ARCHS")
    sdk_platform = os.environ.get("PLATFORM_NAME", "macosx")
    packages = []
    for architecture in architectures:
        suffix = "arm64" if architecture == "arm64" else "x64"
        manifest_path = asset_root / f"manifest.{args.platform}-{suffix}.json"
        manifest = json.loads(manifest_path.read_text())
        expected_host = ("aarch64" if architecture == "arm64" else "x86_64") + "-apple-"
        if args.platform == "macos":
            expected_host += "darwin"
        elif sdk_platform == "iphoneos":
            if architecture != "arm64":
                raise ValueError("iOS device runtime supports arm64 only")
            expected_host += "ios"
        elif sdk_platform == "iphonesimulator":
            expected_host += "ios-sim" if architecture == "arm64" else "ios"
        else:
            raise ValueError(f"Unsupported Xcode SDK platform: {sdk_platform}")
        if manifest.get("nativeHost") != expected_host or manifest.get("platform") != args.platform:
            raise ValueError(f"Repackage {expected_host}; the selected Flutter manifest describes another SDK/host")
        package_key = expected_host if args.platform == "ios" else f"macos-{suffix}"
        package = root / "native/build/runtime" / package_key
        native_manifest = json.loads((package / "native-package.json").read_text())
        if native_manifest["id"] != manifest["id"]:
            raise ValueError("Framework package and Flutter manifest came from different builds")
        libraries = {entry["path"]: entry for entry in manifest["nativeLibraries"]}
        for relative, entry in libraries.items():
            binary = package / safe_relative(relative)
            if sha256(binary) != entry["sha256"]:
                raise ValueError(f"Generated framework differs from its package record: {relative}")
            deployment = os.environ["MACOSX_DEPLOYMENT_TARGET" if args.platform == "macos" else "IPHONEOS_DEPLOYMENT_TARGET"]
            minimum = tuple(int(part) for part in deployment.split("."))
            minimum = (minimum + (0, 0))[:3]
            if args.platform == "macos" and architecture == "arm64":
                minimum = max(minimum, (11, 0, 0))
            if inspect_library(binary, expected_host)["minimumOS"] > minimum:
                raise ValueError(f"Framework requires a newer OS than the app deployment target: {relative}")
        packages.append((package, libraries))
    expected_paths = set(packages[0][1])
    if any(set(libraries) != expected_paths for _, libraries in packages):
        raise ValueError("Universal runtime slices must contain the same framework dependency closure")
    destination = Path(os.environ["TARGET_BUILD_DIR"]) / safe_relative(os.environ["FRAMEWORKS_FOLDER_PATH"])
    destination.mkdir(parents=True, exist_ok=True)
    identity = os.environ.get("EXPANDED_CODE_SIGN_IDENTITY") or "-"
    for relative in sorted(expected_paths):
        framework_name = safe_relative(relative).parts[0]
        framework = destination / framework_name
        if framework.exists():
            if framework.is_symlink() or framework.parent.resolve() != destination.resolve():
                raise ValueError("Framework destination is outside the selected app bundle")
            shutil.rmtree(framework)
        shutil.copytree(packages[0][0] / framework_name, framework)
        binary = destination / relative
        if len(packages) > 1:
            run(["xcrun", "lipo", "-create", *[package / relative for package, _ in packages],
                 "-output", binary])
        actual = set(run(["xcrun", "lipo", "-archs", binary], capture_output=True, text=True).stdout.split())
        if actual != set(architectures):
            raise ValueError(f"Embedded runtime slice does not match Xcode ARCHS: {relative}")
        run(["codesign", "--force", "--sign", identity, "--timestamp=none", framework])
        run(["codesign", "--verify", "--strict", framework])
    print(f"Embedded and signed {len(expected_paths)} {args.platform} Rust runtime frameworks")


if __name__ == "__main__":
    try:
        main()
    except (KeyError, OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(2)
