#!/usr/bin/env python3
"""Gate a freshly built normal production unsigned HAP for file delivery.

This is a delivery gate, not an ABI audit. It proves five things about the
archive only:

1. The HAP is newer than the delivery window given by ``--not-before-ns``.
2. ``module.json`` names the normal production bundle.
3. Every native payload sits under ``libs/arm64-v8a/``.
4. The archive does not request the INTERNET permission.
5. The packaged adapter and the packaged architecture-specific arm64 manifest
   are byte-identical to the current repository copies. The legacy
   ``manifest.json`` never satisfies the manifest gate, because the app falls
   back to it only when the specific file is missing.
6. Every ``nativeLibraries`` record in the frozen manifest matches the packaged
   arm64 member byte-for-byte by sha256, so the adapter, the rustc driver and the
   C++ runtime are all bound to the manifest, not just the adapter.
7. Every ``files`` record matches the packaged asset by declared size and
   sha256, which binds the extracted runtime payload to the frozen manifest and
   makes a stripped or rebuilt asset fail.

It deliberately makes no claim about exported symbols, compiler provenance or
device behaviour. The report carries ``symbolsVerified``, ``provenanceVerified``
and ``deviceExecuted`` as ``false`` so no consumer can read this as a PASS for
those layers.

Pure Python standard library. No SDK, no build, no device.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADAPTER_PATH = ROOT / "ohos" / "entry" / "libs" / "arm64-v8a" / "libqfli_miri.so"
MANIFEST_PATH = ROOT / "assets" / "miri" / "manifest.ohos-arm64.json"

BUNDLE_NAME = "com.azurekiln.qfli.rust"
NATIVE_ABI = "arm64-v8a"
ADAPTER_MEMBER = f"libs/{NATIVE_ABI}/libqfli_miri.so"
INTERNET_PERMISSION = "ohos.permission.INTERNET"

# Every Flutter asset under assets/miri/ keeps its name inside the bundle.
ASSET_PREFIX = "resources/rawfile/flutter_assets/assets/miri/"
MANIFEST_MEMBER = ASSET_PREFIX + "manifest.ohos-arm64.json"
LEGACY_MANIFEST_MEMBER = ASSET_PREFIX + "manifest.json"
NATIVE_MEMBER = re.compile(rf"libs/{NATIVE_ABI}/[^/]+\.so")
NATIVE_MEMBER_PREFIX = f"libs/{NATIVE_ABI}/"
HEX64 = re.compile(r"[0-9a-f]{64}")

SCOPE = (
    "delivery gate only: freshness, bundle, native ABI, INTERNET absence, "
    "adapter bytes and manifest bytes. No symbol, provenance or device claim."
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_file(path: Path, chunk: int = 1 << 20) -> str:
    """Hash a file without loading it into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(chunk), b""):
            digest.update(block)
    return digest.hexdigest()


def stream_sha256(archive: zipfile.ZipFile, member: str, chunk: int = 1 << 20) -> str:
    """Hash one ZIP member without materialising the whole payload."""
    digest = hashlib.sha256()
    with archive.open(member) as handle:
        for block in iter(lambda: handle.read(chunk), b""):
            digest.update(block)
    return digest.hexdigest()


def permission_names(module: dict) -> list[str]:
    """Collect every requested permission name from module.json."""
    names: list[str] = []
    for holder in (module.get("module") or {}, module.get("app") or {}):
        for row in holder.get("requestPermissions") or ():
            if isinstance(row, dict) and isinstance(row.get("name"), str):
                names.append(row["name"])
    return names


def verify(hap: Path, not_before_ns: int) -> dict:
    errors: list[str] = []
    report: dict = {
        "ok": False,
        "scope": SCOPE,
        "hap": str(hap),
        "sha256": None,
        "size": None,
        "mtimeNs": None,
        "mtimeUtc": None,
        "bundle": None,
        "permissions": [],
        "nativeAbi": NATIVE_ABI,
        "nativeLibraries": [],
        "packagedNativeLibraryCount": 0,
        "nativeLibraryRecords": 0,
        "nativeLibrarySizeDeclared": False,
        "nativeLibraryMatches": 0,
        "nativeLibrariesMatch": False,
        "nativeLibraryMismatches": [],
        "missingNativeMembers": [],
        "packagedAssetCount": 0,
        "fileAssetRecords": 0,
        "fileAssetUniqueCount": 0,
        "fileAssetMatches": 0,
        "fileAssetsMatch": False,
        "fileAssetMismatches": [],
        "missingAssetMembers": [],
        "undeclaredAssetCount": 0,
        "expected": {
            "adapterPath": str(ADAPTER_PATH),
            "adapterSha256": None,
            "adapterMember": ADAPTER_MEMBER,
            "manifestPath": str(MANIFEST_PATH),
            "manifestSha256": None,
            "manifestMember": MANIFEST_MEMBER,
        },
        "fresh": False,
        "bundleMatches": False,
        "nativeAbiOnly": False,
        "internetAbsent": False,
        "adapterBytesMatch": False,
        "manifestBytesMatch": False,
        "symbolsVerified": False,
        "provenanceVerified": False,
        "deviceExecuted": False,
        "errors": errors,
    }

    if not hap.is_file():
        errors.append(f"HAP is not a file: {hap}")
        return report

    stat = hap.stat()
    report["sha256"] = hash_file(hap)
    report["size"] = stat.st_size
    report["mtimeNs"] = stat.st_mtime_ns
    report["mtimeUtc"] = datetime.datetime.fromtimestamp(
        stat.st_mtime_ns / 1e9, tz=datetime.timezone.utc
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 1. Freshness. A stale archive must never leave the host.
    if stat.st_mtime_ns >= not_before_ns:
        report["fresh"] = True
    else:
        errors.append(
            f"HAP is older than the delivery window: mtimeNs {stat.st_mtime_ns} "
            f"< not-before-ns {not_before_ns}"
        )
    inputs_ready = True
    for path in (ADAPTER_PATH, MANIFEST_PATH):
        if not path.is_file():
            errors.append(f"Expected input is missing: {path}")
            inputs_ready = False
    if not inputs_ready:
        return report

    adapter_expected = ADAPTER_PATH.read_bytes()
    manifest_expected = MANIFEST_PATH.read_bytes()
    report["expected"]["adapterSha256"] = sha256(adapter_expected)
    report["expected"]["manifestSha256"] = sha256(manifest_expected)

    try:
        archive = zipfile.ZipFile(hap)
        names = archive.namelist()
    except zipfile.BadZipFile as error:
        errors.append(f"HAP is not a readable ZIP archive: {error}")
        return report

    # Duplicate member names make the contained bytes ambiguous: a reader may
    # take the first or the last copy. Reject before any content check.
    duplicates = sorted(
        name for name, count in Counter(names).items() if count > 1
    )
    if duplicates:
        errors.append("HAP repeats ZIP member names: " + ", ".join(duplicates))

    # Directory entries are structure, not payload.
    files = [name for name in names if not name.endswith("/")]

    # Content-addressed assets share one .bin across several records, so cache
    # per member instead of hashing the same payload again.
    digests: dict[str, str] = {}

    def member_sha256(member: str) -> str:
        if member not in digests:
            digests[member] = stream_sha256(archive, member)
        return digests[member]

    # 2. Bundle identity.
    try:
        module = json.loads(archive.read("module.json"))
    except KeyError:
        errors.append("HAP has no module.json")
        module = None
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        errors.append(f"module.json is not readable JSON: {error}")
        module = None

    if isinstance(module, dict):
        bundle = (module.get("app") or {}).get("bundleName")
        report["bundle"] = bundle
        report["permissions"] = permission_names(module)
        if bundle == BUNDLE_NAME:
            report["bundleMatches"] = True
        else:
            errors.append(
                f"Bundle is not the normal production bundle: {bundle!r} != {BUNDLE_NAME!r}"
            )

        # 4. INTERNET must be gone.
        if INTERNET_PERMISSION not in report["permissions"]:
            report["internetAbsent"] = True
        else:
            errors.append(f"HAP still requests {INTERNET_PERMISSION}")
    else:
        errors.append("Bundle and permissions could not be read")

    # 3. Native payloads are arm64-v8a only. Directory entries are ignored.
    native = [name for name in files if name.startswith("libs/")]
    stray = [name for name in native if not NATIVE_MEMBER.fullmatch(name)]
    if not native:
        errors.append("HAP ships no native libraries")
    elif stray:
        errors.append("Native payload outside libs/" + NATIVE_ABI + "/: " + ", ".join(sorted(stray)))
    else:
        report["nativeAbiOnly"] = True

    for name in sorted(native):
        if NATIVE_MEMBER.fullmatch(name):
            report["nativeLibraries"].append(
                {
                    "name": name,
                    "size": archive.getinfo(name).file_size,
                    "sha256": member_sha256(name),
                }
            )
    report["packagedNativeLibraryCount"] = len(report["nativeLibraries"])

    # 5a. Adapter bytes equal the current repository adapter.
    if ADAPTER_MEMBER not in names:
        errors.append(f"HAP has no {ADAPTER_MEMBER}")
    else:
        actual = member_sha256(ADAPTER_MEMBER)
        report["expected"]["adapterMemberSha256"] = actual
        if actual == report["expected"]["adapterSha256"]:
            report["adapterBytesMatch"] = True
        else:
            errors.append(
                f"Packaged adapter differs from {ADAPTER_PATH}: "
                f"{actual} != {report['expected']['adapterSha256']}"
            )

    # 5b. The packaged architecture-specific manifest must be the exact member
    # the ARM64 asset selector asks for, and its bytes must match the source.
    report["expected"]["legacyManifestPresent"] = LEGACY_MANIFEST_MEMBER in files
    if MANIFEST_MEMBER not in files:
        errors.append(
            f"HAP has no {MANIFEST_MEMBER}; the legacy manifest.json does not "
            "satisfy the ARM64 asset selector"
        )
    else:
        actual = member_sha256(MANIFEST_MEMBER)
        report["expected"]["manifestMemberSha256"] = actual
        if actual == report["expected"]["manifestSha256"]:
            report["manifestBytesMatch"] = True
        else:
            errors.append(
                f"Packaged manifest {MANIFEST_MEMBER} differs from {MANIFEST_PATH}: "
                f"{actual} != {report['expected']['manifestSha256']}"
            )

    # 6. Bind every frozen manifest record to the packaged bytes. The frozen
    # manifest is the source manifest, because 5b already required the packaged
    # copy to be byte-identical to it.
    try:
        frozen = json.loads(manifest_expected)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        errors.append(f"{MANIFEST_PATH} is not readable JSON: {error}")
        frozen = None

    if not isinstance(frozen, dict):
        report["ok"] = not errors
        return report

    # 6a. Native library records. The manifest carries no declared size, so the
    # binding is the sha256 and the packaged size is reported alongside it.
    library_records = frozen.get("nativeLibraries") or []
    report["nativeLibraryRecords"] = len(library_records)
    libraries_matched = 0
    for row in library_records:
        name = row.get("name") if isinstance(row, dict) else None
        declared = row.get("sha256") if isinstance(row, dict) else None
        if not isinstance(name, str) or not name or "/" in name:
            errors.append("Manifest nativeLibraries entry has no usable name")
            continue
        if not isinstance(declared, str) or not HEX64.fullmatch(declared):
            errors.append(f"Manifest nativeLibraries {name} has no well-formed sha256")
            continue
        member = NATIVE_MEMBER_PREFIX + name
        if member not in files:
            errors.append(f"Manifest declares {name} but the HAP has no {member}")
            report["missingNativeMembers"].append(member)
            continue
        actual = member_sha256(member)
        if actual == declared:
            libraries_matched += 1
        else:
            report["nativeLibraryMismatches"].append(
                {
                    "member": member,
                    "declaredSha256": declared,
                    "declaredSize": None,
                    "actualSha256": actual,
                    "size": archive.getinfo(member).file_size,
                }
            )
            errors.append(
                f"Packaged {member} differs from the manifest record: "
                f"{actual} != {declared}"
            )
    report["nativeLibraryMatches"] = libraries_matched
    report["nativeLibrariesMatch"] = (
        bool(library_records) and libraries_matched == len(library_records)
    )

    # 6b. Extracted runtime assets. Size is compared first, so a stripped or
    # rebuilt asset fails without hashing its payload.
    asset_records = frozen.get("files") or []
    report["fileAssetRecords"] = len(asset_records)
    assets_matched = 0
    for row in asset_records:
        asset = row.get("asset") if isinstance(row, dict) else None
        declared = row.get("sha256") if isinstance(row, dict) else None
        declared_size = row.get("size") if isinstance(row, dict) else None
        if not isinstance(asset, str) or not asset or "/" in asset:
            errors.append("Manifest files entry has no usable asset name")
            continue
        if not isinstance(declared, str) or not HEX64.fullmatch(declared):
            errors.append(f"Manifest files {asset} has no well-formed sha256")
            continue
        if not isinstance(declared_size, int) or isinstance(declared_size, bool):
            errors.append(f"Manifest files {asset} has no integer size")
            continue
        member = ASSET_PREFIX + asset
        if member not in files:
            errors.append(f"Manifest declares asset {asset} but the HAP has no {member}")
            report["missingAssetMembers"].append(member)
            continue
        actual_size = archive.getinfo(member).file_size
        if actual_size != declared_size:
            report["fileAssetMismatches"].append(
                {
                    "member": member,
                    "declaredSize": declared_size,
                    "actualSize": actual_size,
                    "sha256Checked": False,
                }
            )
            errors.append(
                f"Packaged {asset} size {actual_size} differs from the manifest "
                f"record size {declared_size}"
            )
            continue
        actual = member_sha256(member)
        if actual == declared:
            assets_matched += 1
        else:
            report["fileAssetMismatches"].append(
                {
                    "member": member,
                    "declaredSha256": declared,
                    "actualSha256": actual,
                    "declaredSize": declared_size,
                    "actualSize": actual_size,
                    "sha256Checked": True,
                }
            )
            errors.append(
                f"Packaged {asset} sha256 {actual} differs from the manifest "
                f"record sha256 {declared}"
            )
    report["fileAssetMatches"] = assets_matched
    report["fileAssetsMatch"] = bool(asset_records) and assets_matched == len(asset_records)

    # Informational only: packaged assets the manifest does not declare.
    packaged_assets = {
        name.rsplit("/", 1)[-1]
        for name in files
        if name.startswith(ASSET_PREFIX) and name.endswith(".bin")
    }
    declared_assets = {
        row.get("asset") for row in asset_records
        if isinstance(row, dict) and isinstance(row.get("asset"), str)
    }
    report["packagedAssetCount"] = len(packaged_assets)
    report["undeclaredAssetCount"] = len(packaged_assets - declared_assets)
    report["fileAssetUniqueCount"] = len(declared_assets)

    report["ok"] = not errors
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Gate a freshly built normal production unsigned HAP for delivery."
    )
    parser.add_argument("--hap", required=True, type=Path, help="HAP to gate")
    parser.add_argument(
        "--not-before-ns",
        required=True,
        type=int,
        help="Delivery window start as integer nanoseconds since the epoch",
    )
    arguments = parser.parse_args(argv)

    report = verify(arguments.hap, arguments.not_before_ns)
    json.dump(report, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
