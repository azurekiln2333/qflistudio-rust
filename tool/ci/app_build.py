#!/usr/bin/env python3
"""Orchestrate source-bound application builds on disposable GitHub runners."""

import argparse
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

from ci_support import (
    APP_ID, APP_NAME, CORE_DIRECTORY, CORE_REPOSITORY, PACKAGE_NAMES, ROOT, SIGNING,
    TARGETS, add_target_arguments, read_json, read_version, redact,
    report_failure, require_hosted_runner, resolve_target, run, sha256, step_summary,
    write_json,
)

sys.path.insert(0, str(ROOT / "scripts"))
from miri_build_support import (
    COMPILER_BOUNDARY_KIND, COMPILER_BOUNDARY_PATCH_SHA256,
    GUEST_TARGET, HOSTS, RUST_COMMIT, RUST_VERSION,
)
from inspect_rust_catalog_hap import verify_compiler_boundary
from package_miri_runtime import framework_name

# Owner-provided baseline SDK evidence, not final core/six-platform proof.
# Every application build still requires the final approved core SHA and this
# explicit contract. Engine/tooling identities are read from this exact commit;
# overrides from the older, different SDK recipe must not leak into this one.
SDK_CONTRACT = "flutter-oh-3.41.10-ohos-1.0.1@adaf911c35c9136a7d18fc424d714c9ec7724e60"
FLUTTER_REPOSITORY = "https://gitcode.com/openharmony-tpc/flutter_flutter.git"
FLUTTER_TAG = "3.41.10-ohos-1.0.1"
FLUTTER_COMMIT = "adaf911c35c9136a7d18fc424d714c9ec7724e60"
CORE_DEPENDENCY_PATHS = {
    "qfli_studio_core": "../qflistudio-core",
    "re_editor": "../qflistudio-core/vendor/re_editor",
    "xterm": "../qflistudio-core/vendor/xterm",
}
OHOS_SDK_RELEASE = "26.0.0.821"
OHOS_SDK_SHA256 = "0cbdf7ac5c1be1e42694d448ffaee0c0be0ba9a948197e2bc5b61ca5bdc481f2"
OHOS_PARTS = {
    "aa": "4321eb328558169e9531594139910a42b1c88057fb09f852be85ff2487e6adbc",
    "ab": "26e9ae251e761fbc9ec4e7ad780b5b291130e7824af2324167530941e11ad592",
}
NATIVE_WORKFLOW = ".github/workflows/native-runtime.yml"
RUNTIME_INPUTS = ("native", "scripts", NATIVE_WORKFLOW)
MAX_RUNTIME_BYTES = 4 * 1024**3
MAX_RUNTIME_MEMBERS = 50000
MAX_REPORT_BYTES = 128 * 1024**2
MAX_PACKAGE_BYTES = 8 * 1024**3
MAX_INTERMEDIATE_BYTES = 4 * 1024**3
MAX_INTERMEDIATE_FILES = 30000
ARMV7_BLOCKER = "Android armeabi-v7a is pending native/compiler/ELF32/Gradle/Dart compatibility; only arm64 and x64 are built."


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def git_value(directory, *arguments):
    return subprocess.check_output(["git", *arguments], cwd=directory, text=True).strip()


def safe_relative(value):
    require(isinstance(value, str) and value and "\\" not in value and ":" not in value
            and not any(ord(character) < 32 for character in value), "Unsafe relative path")
    path = PurePosixPath(value)
    require(not path.is_absolute() and all(part not in ("", ".", "..")
                                          for part in value.split("/")), "Non-canonical relative path")
    return path


def publish_environment(values, paths=()):
    for key, value in values.items():
        require(re.fullmatch(r"[A-Z][A-Z0-9_]*", key) and "\n" not in str(value)
                and "\r" not in str(value), "Unsafe workflow environment value")
        os.environ[key] = str(value)
    if paths:
        os.environ["PATH"] = os.pathsep.join(map(str, paths)) + os.pathsep + os.environ["PATH"]
    for variable, lines in (("GITHUB_ENV", [f"{key}={value}" for key, value in values.items()]),
                            ("GITHUB_PATH", [str(path) for path in paths])):
        if os.environ.get(variable):
            with open(os.environ[variable], "a", encoding="utf-8") as stream:
                stream.write("".join(line + "\n" for line in lines))


def output_value(key, value):
    require(re.fullmatch(r"[a-z_]+", key) and "\n" not in str(value)
            and "\r" not in str(value), "Unsafe workflow output")
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
        stream.write(f"{key}={value}\n")


def environment():
    return dict(os.environ, CI="true", FLUTTER_SUPPRESS_ANALYTICS="true",
                FLUTTER_STORAGE_BASE_URL="https://storage.googleapis.com",
                FLUTTER_OHOS_STORAGE_BASE_URL="https://flutter-ohos.obs.cn-south-1.myhuaweicloud.com",
                PUB_HOSTED_URL="https://pub.dev", PYTHONDONTWRITEBYTECODE="1")


def flutter(args):
    return args.flutter_root / "bin" / ("flutter.bat" if os.name == "nt" else "flutter")


def application_id(platform):
    if platform == "ohos":
        identity = read_json(ROOT / "ohos/AppScope/app.json5").get("app", {}).get("bundleName")
        require(isinstance(identity, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+", identity),
                "OHOS source bundle identifier is absent or malformed")
        return identity
    return APP_ID


def initialize(args):
    require(not (args.output / "manifest.json").exists(), "Refusing to reuse an artifact manifest")
    require(not (args.output / "packages").exists(), "Refusing to reuse package outputs")
    source = git_value(ROOT, "rev-parse", "HEAD")
    require(source == os.environ.get("GITHUB_SHA"), "Application checkout differs from workflow source")
    manifest = {
        "schemaVersion": 1,
        "application": {"name": APP_NAME, "id": application_id(args.platform), "version": read_version()},
        "platform": args.platform, "arch": args.arch, "status": "incomplete",
        "stage": "init", "completedStages": [],
        "source": {"repository": os.environ["GITHUB_REPOSITORY"], "commit": source,
                   "ref": os.environ.get("GITHUB_REF"), "runId": os.environ["GITHUB_RUN_ID"],
                   "runAttempt": os.environ["GITHUB_RUN_ATTEMPT"]},
        "core": {"repository": CORE_REPOSITORY, "commit": os.environ.get("CORE_SHA"),
                 "checkoutDirectory": CORE_DIRECTORY, "packageName": "qfli_studio_core",
                 "sdkContract": SDK_CONTRACT, "compatibility": "not_verified"},
        "flutter": {"repository": FLUTTER_REPOSITORY, "tag": FLUTTER_TAG,
                    "commit": FLUTTER_COMMIT, "sdkContract": SDK_CONTRACT,
                    "engine": None, "ohosEngine": None, "toolingOverride": None,
                    "nativeHooksRecipe": "unverified", "externalToolingOverrides": "none_applied_not_proof_none_needed",
                    "baselineInstallerEvidence": {"repository": "azurekiln2333/qflistudio-next",
                        "path": "tool/ci/setup_flutter.sh", "commit": "69656b4ab14e706e85907ef4c4205d8cd35a1338",
                        "blob": "05cb24cc4f0ecc3cbefbf9fe6f8a8e917ac14a05",
                        "scope": "owner_reported_ubuntu_core_checks_not_rust_packaging"}},
        "nativeRuntime": None, "signing": SIGNING[args.platform], "packages": [],
        "deviceReady": False, "deviceTests": "not_run", "applicationUiVerified": False,
        "desktopToolchain": "system_cargo_and_rustc_required" if not TARGETS[args.platform, args.arch] else None,
        "blockers": [ARMV7_BLOCKER] if args.platform == "android" else [],
        "packageCoverage": {"complete": False if args.platform == "android" else None,
                            "blockers": [ARMV7_BLOCKER] if args.platform == "android" else []},
        "retentionDays": {"reportsAndPackages": 14, "intermediates": 1},
    }
    write_json(args.output / "manifest.json", manifest)
    return manifest


def preflight(args, manifest):
    selected = os.environ.get("CORE_SHA", "")
    approved = os.environ.get("APPROVED_CORE_SHA", "")
    require(re.fullmatch(r"[0-9a-f]{40}", selected) and selected == approved,
            "Set QFLI_APPROVED_CORE_SHA to the owner's final immutable handoff; core_sha must match it")
    require(not selected.startswith(("ee83f1c", "573d1b6")), "Rejected superseded core integration SHA")
    require(os.environ.get("CORE_SDK_CONTRACT") == SDK_CONTRACT,
            f"Core owner must approve QFLI_CORE_SDK_CONTRACT={SDK_CONTRACT} or update the reviewed SDK recipe")
    manifest["core"]["approval"] = "owner_approved_inputs_pending_this_platform_build"
    output_value("core_sha", selected)


def verify_core(args, manifest):
    core = ROOT.parent / CORE_DIRECTORY
    require(core.is_dir() and not core.is_symlink(), "Expected sibling checkout qflistudio-core")
    require(git_value(core, "rev-parse", "HEAD") == manifest["core"]["commit"], "Core checkout SHA differs")
    text = (ROOT / "pubspec.yaml").read_text(encoding="utf-8")
    for name, expected in CORE_DEPENDENCY_PATHS.items():
        section = "dependencies" if name == "qfli_studio_core" else "dependency_overrides"
        block = re.search(r"(?ms)^" + section + r":[ \t]*\n(.*?)(?=^\S|\Z)", text)
        require(block and re.search(r"(?m)^  " + name + r":[ \t]*\n    path: ['\"]?"
                                    + re.escape(expected) + r"['\"]?[ \t]*$", block.group(1)),
                "Coordinator must align root " + section + " path for " + name)
    require(re.search(r"(?m)^name:\s*qfli_studio_core\s*$",
                      (core / "pubspec.yaml").read_text(encoding="utf-8")), "Core Dart package identity changed")
    for name in ("re_editor", "xterm"):
        require((core / "vendor" / name / "pubspec.yaml").is_file(), "Core vendor/" + name + " is absent")
    require(not (ROOT / "pubspec_overrides.yaml").exists(), "Unreviewed app dependency override")
    lock = (ROOT / "pubspec.lock").read_text(encoding="utf-8")
    for name, expected in CORE_DEPENDENCY_PATHS.items():
        block = re.search(r"(?ms)^  " + name + r":\n(.*?)(?=^  [a-zA-Z_]|^\S|\Z)", lock)
        require(block and re.search(r"(?m)^      path: ['\"]?" + re.escape(expected) + r"['\"]?[ \t]*$", block.group(1))
                and re.search(r"(?m)^      relative: true[ \t]*$", block.group(1))
                and re.search(r"(?m)^    source: path[ \t]*$", block.group(1)),
                "Coordinator must align committed lockfile path/source for " + name)
    manifest["core"]["checkoutVerified"] = True
    write_json(args.output / "reports/core-input.json", manifest["core"])


def api_json(path):
    require(path.startswith("/") and not path.startswith("//"), "GitHub API path must be relative")
    token = os.environ.get("GH_TOKEN", "")
    require(token, "Missing GitHub job token for runtime metadata")
    request = urllib.request.Request("https://api.github.com" + path, headers={
        "Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "qfli-app-ci",
    })
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                payload = response.read(16 * 1024**2 + 1)
            require(len(payload) <= 16 * 1024**2, "GitHub API response exceeds metadata bound")
            return json.loads(payload)
        except urllib.error.HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise RuntimeError(f"GitHub metadata request failed (HTTP {error.code})") from None
        except urllib.error.URLError:
            if attempt == 2:
                raise RuntimeError("GitHub metadata request failed after retries") from None
        time.sleep(3 * (attempt + 1))


def runtime_input_identity(repository, commit):
    record = api_json(f"/repos/{repository}/git/commits/{commit}")
    tree_sha = record.get("tree", {}).get("sha", "")
    require(re.fullmatch(r"[0-9a-f]{40}", tree_sha), "Runtime commit has no immutable source tree")
    tree = api_json(f"/repos/{repository}/git/trees/{tree_sha}")
    require(not tree.get("truncated"), "Truncated repository input tree")
    entries = {row["path"]: row for row in tree["tree"]}
    result = {}
    for folder in ("native", "scripts"):
        require(entries.get(folder, {}).get("type") == "tree", f"Missing runtime source tree {folder}")
        result[folder] = entries[folder]["sha"]
    record = api_json(f"/repos/{repository}/contents/{NATIVE_WORKFLOW}?ref={commit}")
    require(record.get("type") == "file", "Missing native workflow input")
    result[NATIVE_WORKFLOW] = record["sha"]
    return result


def runtime_artifacts(repository, run_id):
    result = []
    for page in range(1, 11):
        data = api_json(f"/repos/{repository}/actions/runs/{run_id}/artifacts?per_page=100&page={page}")
        batch = data.get("artifacts", [])
        result.extend(batch)
        if len(result) >= data.get("total_count", 0):
            return result
    raise RuntimeError("Runtime artifact metadata exceeds pagination bound")


def validate_runtime_run(record, repository, expected_inputs, required):
    require(record.get("status") == "completed" and record.get("conclusion") == "success",
            "Runtime run must have completed successfully")
    require(record.get("repository", {}).get("full_name", "").lower() == repository.lower()
            and record.get("head_repository", {}).get("full_name", "").lower() == repository.lower(),
            "Runtime run must originate from this repository, not a fork")
    require(record.get("event") in ("push", "workflow_dispatch") and record.get("head_branch") == "main"
            and record.get("path") == NATIVE_WORKFLOW, "Unexpected runtime workflow, event or branch")
    commit = record.get("head_sha", "")
    require(re.fullmatch(r"[0-9a-f]{40}", commit), "Runtime source commit is absent")
    inputs = runtime_input_identity(repository, commit)
    require(inputs == expected_inputs, "Runtime native/scripts/workflow Git objects differ from app inputs")
    artifacts = runtime_artifacts(repository, record["id"])
    selected = []
    now = datetime.now(timezone.utc)
    for key in required:
        matches = [row for row in artifacts if row.get("name") == "native-runtime-" + key]
        require(len(matches) == 1, f"Expected one native-runtime-{key} artifact")
        row = matches[0]
        expires = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
        require(not row.get("expired") and expires > now and 0 < row.get("size_in_bytes", 0) <= MAX_RUNTIME_BYTES,
                f"Native runtime {key} is expired, empty or above the size bound")
        selected.append({field: row.get(field) for field in
                         ("id", "name", "size_in_bytes", "digest", "created_at", "expires_at")})
    return {"runId": str(record["id"]), "sourceCommit": commit,
            "runAttempt": str(record["run_attempt"]), "url": record["html_url"],
            "inputCompatibility": {"method": "exact_git_objects", "objects": inputs}, "artifacts": selected}


def resolve_runtime(args, manifest):
    required = TARGETS[args.platform, args.arch]
    require(required, "Desktop builds do not consume a native runtime archive")
    repository = manifest["source"]["repository"]
    expected = {path: git_value(ROOT, "rev-parse", f"HEAD:{path}") for path in RUNTIME_INPUTS}
    explicit = args.run_id or os.environ.get("RUNTIME_RUN_ID", "")
    if explicit:
        require(re.fullmatch(r"[1-9][0-9]*", explicit), "runtime_run_id must be a positive integer")
        candidates = [api_json(f"/repos/{repository}/actions/runs/{explicit}")]
    else:
        data = api_json(f"/repos/{repository}/actions/workflows/native-runtime.yml/runs?branch=main&status=success&per_page=30")
        candidates = data.get("workflow_runs", [])
    failures = []
    for candidate in candidates:
        try:
            selected = validate_runtime_run(candidate, repository, expected, required)
        except RuntimeError as error:
            failures.append({"runId": candidate.get("id"), "reason": redact(str(error))})
            if explicit:
                write_json(args.output / "reports/native-runtime-rejections.json", failures)
                raise
            continue
        write_json(args.output / "reports/native-runtime-source.json", selected)
        manifest["nativeRuntime"] = {**selected, "packages": [], "status": "selected_not_installed"}
        output_value("run_id", selected["runId"])
        output_value("artifact_ids", ",".join(str(row["id"]) for row in selected["artifacts"]))
        return
    write_json(args.output / "reports/native-runtime-rejections.json", failures)
    raise RuntimeError("No unexpired source-compatible native runtime. Dispatch Native runtime for these inputs first")


def extract_runtime(archive, destination):
    """Reject traversal, devices, links and archive bombs before any extraction."""
    total = 0
    names = set()
    members = []
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle:
            require(len(members) < MAX_RUNTIME_MEMBERS, "Runtime member count exceeds bound")
            members.append(member)
            relative = safe_relative(member.name.rstrip("/"))
            require(relative.parts[0] in ("assets", "android", "ohos", "native", "build-info"),
                    "Unexpected runtime archive root")
            require(member.isfile() or member.isdir(), "Runtime archive links/devices are not accepted")
            require(relative.as_posix() not in names, "Duplicate runtime archive member")
            names.add(relative.as_posix())
            total += member.size
            require(member.size >= 0 and total <= MAX_RUNTIME_BYTES, "Runtime expansion exceeds bound")
        bundle.extractall(destination, members=members, filter="data")


def verify_file(path, record, *, size_required=True):
    require(path.is_file() and not path.is_symlink(), f"Missing runtime file: {path.name}")
    require(re.fullmatch(r"[0-9a-f]{64}", str(record.get("sha256", "")))
            and sha256(path) == record["sha256"], f"Runtime file hash differs: {path.name}")
    if size_required or "size" in record:
        require(type(record.get("size")) is int and record["size"] > 0
                and path.stat().st_size == record["size"], f"Runtime file size differs: {path.name}")


def producer_path_parts(value):
    """Compare recorded producer paths lexically; never resolve or open them."""
    require(isinstance(value, str) and value and value == value.strip()
            and not any(ord(character) < 32 for character in value), "Unsafe producer path")
    text = value.replace("\\", "/")
    if re.match(r"^[A-Za-z]:/", text):
        anchor, rest = text[:2].upper(), text[3:]
    elif text.startswith("//"):
        anchor, rest = "//", text[2:]
    elif text.startswith("/"):
        anchor, rest = "/", text[1:]
    else:
        raise RuntimeError("Producer path must be absolute in its recorded namespace")
    parts = rest.split("/")
    require(all(part and part not in (".", "..") and ":" not in part for part in parts),
            "Non-canonical producer path")
    require(anchor != "//" or len(parts) >= 3, "Incomplete producer UNC path")
    return (anchor, *parts)


def compiler_library_name(name):
    return ("rustc_driver" in name or "rustc_codegen" in name
            or name.startswith(("libstd-", "std-", "libLLVM", "LLVM")))


def verify_native_record_chain(data, compiler, adapter, platform):
    """Bind manifest source bytes to adapter and compiler-runtime inventories.

    Apple package bytes have been rewritten and signed. Their sourceSha256 is
    checked here against pre-transform producer records; verify_file checks the
    final transformed sha256 separately. No producer filesystem is accessed.
    """
    boundary = verify_compiler_boundary(data.get("compilerBoundary"))
    require(verify_compiler_boundary(compiler.get("compilerBoundary")) == boundary
            and verify_compiler_boundary(adapter.get("compilerBoundary")) == boundary,
            "Producer compiler boundary differs from the manifest")
    chain = adapter.get("compilerBuild")
    require(isinstance(chain, dict) and set(chain) == {"path", "sha256", "compilerBoundary"},
            "Adapter compilerBuild lacks the complete producer identity")
    producer_path_parts(chain["path"])
    require(verify_compiler_boundary(chain["compilerBoundary"]) == boundary,
            "Adapter nested compiler boundary differs")
    built = adapter.get("adapter")
    require(isinstance(built, dict) and re.fullmatch(r"[0-9a-f]{64}", str(built.get("sha256", ""))),
            "Adapter producer byte identity is missing or malformed")
    adapter_name = producer_path_parts(built.get("path"))[-1]
    require(adapter_name == ("libqfli_miri.dylib" if platform == "ios" else "libqfli_miri.so"),
            "Producer adapter basename differs from the selected platform")
    artifacts = compiler.get("compilerArtifacts")
    require(isinstance(artifacts, list) and artifacts, "Compiler producer inventory is missing")
    runtime = {}
    identities = set()
    for row in artifacts:
        require(isinstance(row, dict) and row.get("root") in ("compiler", "runtime"),
                "Malformed compiler producer artifact")
        relative = safe_relative(row.get("path")).as_posix()
        identity = (row["root"], relative)
        require(identity not in identities, "Duplicate compiler producer artifact")
        identities.add(identity)
        require(type(row.get("size")) is int and row["size"] > 0
                and re.fullmatch(r"[0-9a-f]{64}", str(row.get("sha256", ""))),
                "Malformed compiler producer artifact size/hash")
        if row["root"] == "runtime":
            runtime[relative] = row
    require(runtime, "Compiler producer runtime inventory is missing")
    root_parts = producer_path_parts(compiler.get("runtimeSysroot"))
    libraries = adapter.get("compilerLibraries")
    require(isinstance(libraries, list) and libraries, "Adapter producer compiler inventory is missing")
    recorded = {}
    recorded_paths = set()
    for row in libraries:
        require(isinstance(row, dict), "Malformed adapter producer compiler library")
        name = safe_relative(row.get("name"))
        require(len(name.parts) == 1, "Producer compiler library name must be a basename")
        parts = producer_path_parts(row.get("path"))
        require(parts[:len(root_parts)] == root_parts and len(parts) > len(root_parts),
                "Producer compiler library is outside its recorded runtime root")
        relative = "/".join(parts[len(root_parts):])
        require(parts[-1] == name.name and relative in runtime,
                "Producer compiler library has no matching runtime artifact identity")
        artifact = runtime[relative]
        require(relative not in recorded_paths, "Duplicate producer compiler library path")
        recorded_paths.add(relative)
        require(row.get("sha256") == artifact["sha256"],
                "Producer compiler inventories disagree on library hash")
        if name.name in recorded:
            require(recorded[name.name]["sha256"] == artifact["sha256"]
                    and recorded[name.name]["size"] == artifact["size"],
                    "Ambiguous producer compiler basename")
        recorded[name.name] = artifact
    required_paths = {relative for relative in runtime
                      if compiler_library_name(PurePosixPath(relative).name)
                      and (PurePosixPath(relative).suffix in (".so", ".dylib", ".dll")
                           or ".so." in PurePosixPath(relative).name)}
    require(required_paths.issubset(recorded_paths), "Adapter producer compiler inventory is incomplete")
    selected = data.get("nativeLibraries")
    require(isinstance(selected, list) and selected, "Packaged native inventory is missing")
    seen = set()
    packaged_compiler = set()
    adapter_count = 0
    for row in selected:
        require(isinstance(row, dict), "Malformed packaged native library")
        name = safe_relative(row.get("name"))
        require(len(name.parts) == 1 and name.name not in seen, "Duplicate/unsafe packaged native basename")
        seen.add(name.name)
        relative = safe_relative(row.get("path") if data["schemaVersion"] == 2 else row["name"])
        expected = framework_name(name.name) if platform == "ios" else None
        require(relative.as_posix() == (f"{expected}.framework/{expected}" if expected else name.name),
                "Packaged native path does not match its producer basename")
        source_hash = row.get("sourceSha256") if platform == "ios" else row.get("sha256")
        require(re.fullmatch(r"[0-9a-f]{64}", str(source_hash or "")), "Missing native source hash")
        if platform != "ios" and "sourceSha256" in row:
            require(row["sourceSha256"] == source_hash, "Untransformed native source/final hashes differ")
        if name.name == adapter_name:
            require(source_hash == built["sha256"], "Packaged adapter differs from producer bytes")
            require(data["schemaVersion"] == 1 or row.get("role") == "adapter", "Packaged adapter role differs")
            adapter_count += 1
        elif name.name in recorded or compiler_library_name(name.name) or row.get("role") == "backend":
            require(name.name in recorded, "Packaged compiler library is absent from producer inventories")
            require(source_hash == recorded[name.name]["sha256"], "Packaged compiler library differs from producer bytes")
            if platform != "ios" and data["schemaVersion"] == 2:
                require(row.get("size") == recorded[name.name]["size"], "Packaged compiler library producer size differs")
            packaged_compiler.add(name.name)
    require(adapter_count == 1, "Packaged native inventory lacks the producer adapter")
    for component in ("rustc_driver", "rustc_codegen"):
        require(any(component in name for name in packaged_compiler),
                "Packaged native inventory lacks producer " + component)
    return recorded


def verify_runtime_payload(root, key, selection):
    platform, architecture = key.split("-", 1)
    host = next((host for host, target in HOSTS.items() if target == (platform, architecture)), None)
    require(host, "Unknown runtime target")
    manifest_path = root / "assets/miri" / f"manifest.{key}.json"
    data = read_json(manifest_path)
    schema = data.get("schemaVersion")
    require(schema == (1 if platform == "ohos" else 2), "Unsupported runtime manifest schema")
    require(data.get("nativeHost") == host and data.get("rustVersion") == RUST_VERSION
            and data.get("rustCommit") == RUST_COMMIT and data.get("guestTarget") == GUEST_TARGET,
            "Runtime target or pinned compiler identity differs")
    if schema == 2:
        require(data.get("platform") == platform and data.get("architecture") == architecture,
                "Runtime platform/architecture mismatch")
    info = root / "build-info"
    ci = read_json(info / "ci-build.json")
    require(ci.get("schemaVersion") == 1 and ci.get("status") == "packaged"
            and ci.get("nativeHost") == host and ci.get("rustVersion") == RUST_VERSION
            and ci.get("rustCommit") == RUST_COMMIT and str(ci.get("runId")) == selection["runId"]
            and str(ci.get("runAttempt")) == selection["runAttempt"]
            and ci.get("sourceCommit") == selection["sourceCommit"], "Runtime CI source/run binding differs")
    compiler = read_json(info / "compiler-build.json")
    adapter = read_json(info / "adapter-build.json")
    guest = read_json(info / "miri-sysroot.json")
    compiler_hash = sha256(info / "compiler-build.json")
    adapter_hash = sha256(info / "adapter-build.json")
    require((data.get("compilerBuild", {}).get("sha256") if schema == 2
             else data.get("compilerBuildSha256")) == compiler_hash, "Compiler build record hash differs")
    require((data.get("adapterBuild", {}).get("sha256") if schema == 2
             else data.get("adapterBuildSha256")) == adapter_hash, "Adapter build record hash differs")
    require(compiler.get("schemaVersion") == 2 and compiler.get("status") == "built"
            and adapter.get("schemaVersion") == 1, "Runtime compiler/adapter provenance is incomplete")
    for record in (compiler, adapter):
        require(record.get("nativeHost") == host and record.get("rustVersion") == RUST_VERSION
                and record.get("rustCommit") == RUST_COMMIT, "Compiler/adapter target differs")
    boundary = compiler.get("compilerBoundary", {})
    require(boundary.get("kind") == COMPILER_BOUNDARY_KIND
            and boundary.get("patchSha256") == COMPILER_BOUNDARY_PATCH_SHA256
            and boundary.get("sourceCommit") == RUST_COMMIT
            and boundary == data.get("compilerBoundary") == adapter.get("compilerBoundary")
            and adapter.get("compilerBuild", {}).get("sha256") == compiler_hash,
            "Patched compiler boundary differs from app source")
    producer_libraries = verify_native_record_chain(data, compiler, adapter, platform)
    require(guest.get("rustVersion") == RUST_VERSION and guest.get("rustCommit") == RUST_COMMIT
            and guest.get("guestTarget") == GUEST_TARGET
            and (guest.get("schemaVersion") == 1
                 or guest.get("schemaVersion") == 2 and guest.get("encodedMir") is True), "Guest provenance differs")
    for name in ("qfli_miri.h", "qfli_debug.h"):
        actual = (root / "native/include" / name).read_text(encoding="utf-8").replace("\r\n", "\n")
        expected = (ROOT / "native/miri_adapter" / name).read_text(encoding="utf-8").replace("\r\n", "\n")
        require(actual == expected, "Runtime ABI header differs: " + name)
    abi = {"arm64": "arm64-v8a", "x64": "x86_64"}.get(architecture)
    library_root = (root / "ohos/entry/libs" / abi if platform == "ohos"
                    else root / "native/build/runtime" / (host if platform == "ios" else key))
    libraries = data.get("nativeLibraries", [])
    files = data.get("files", [])
    require(libraries and files and len(libraries) == ci.get("nativeLibraries")
            and len(files) == ci.get("guestAndLicenseFiles"), "Runtime inventory count differs")
    if schema == 2:
        require({"adapter", "backend"}.issubset({row.get("role") for row in libraries}), "Missing runtime adapter/backend")
    for row in libraries:
        relative = safe_relative(row.get("path") if schema == 2 else row.get("name"))
        verify_file(library_root / relative, row, size_required=schema == 2)
        if platform == "android":
            verify_file(root / "android/app/src/main/jniLibs" / abi / relative, row)
    guest_files = {row["path"]: row for row in guest.get("files", [])}
    require(guest_files, "Guest provenance has no standard-library inventory")
    covered_guest = set()
    for row in files:
        name = safe_relative(row.get("asset"))
        relative = safe_relative(row.get("path"))
        require(len(name.parts) == 1, "Guest asset must be a basename")
        verify_file(root / "assets/miri" / name, row)
        if relative.as_posix() in guest_files:
            expected = guest_files[relative.as_posix()]
            require(expected.get("sha256") == row["sha256"]
                    and expected.get("size") == row["size"], "Guest payload differs from the guest build record")
            covered_guest.add(relative.as_posix())
        elif relative.parts[0] == "sysroot":
            # OHOS schema1 also packages its native codegen backend as an asset.
            require(platform == "ohos" and relative.parts[:5] == ("sysroot", "lib", "rustlib", host, "codegen-backends")
                    and len(relative.parts) == 6
                    and producer_libraries.get(relative.name, {}).get("sha256") == row["sha256"],
                    "Unbound native backend in guest assets")
        elif relative.parts[0] != "licenses":
            raise RuntimeError("Unexpected guest/license manifest path")
    require(covered_guest == set(guest_files), "Guest build record coverage is incomplete")
    allowed = {"assets/miri/" + manifest_path.name,
               "native/include/qfli_miri.h", "native/include/qfli_debug.h"}
    allowed.update("assets/miri/" + row["asset"] for row in files)
    allowed.update("build-info/" + name for name in
                   ("ci-build.json", "compiler-build.json", "adapter-build.json", "miri-sysroot.json"))
    for row in libraries:
        relative = row.get("path") if schema == 2 else row["name"]
        allowed.add((library_root / relative).relative_to(root).as_posix())
        if platform == "android":
            allowed.add(f"android/app/src/main/jniLibs/{abi}/{relative}")
        if platform == "ios":
            framework = (library_root / relative).parent.relative_to(root).as_posix()
            allowed.update((framework + "/Info.plist", framework + "/_CodeSignature/CodeResources"))
    if platform != "ohos":
        package_manifest = library_root / "native-package.json"
        require(read_json(package_manifest) == data, "Native package manifest differs from asset manifest")
        allowed.add(package_manifest.relative_to(root).as_posix())
    if platform == "ohos" and architecture == "arm64":
        require(read_json(root / "assets/miri/manifest.json") == data, "Legacy OHOS manifest differs")
        allowed.add("assets/miri/manifest.json")
    actual = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    require(actual.issubset(allowed), "Runtime archive contains files outside the verified selected payload")
    return data


def merge_verified_tree(source, destination):
    if not source.exists():
        return
    for path in sorted(source.rglob("*")):
        require(not path.is_symlink(), "Runtime payload must not contain links")
        target = destination / path.relative_to(source)
        if path.is_file():
            require(not target.is_symlink(), "Refusing runtime copy through a symlink")
            if target.exists():
                require(target.is_file() and sha256(target) == sha256(path), "Refusing to replace differing runtime data")
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)


def install_runtime(args, manifest):
    selection = manifest.get("nativeRuntime")
    require(selection and args.source and str(args.run_id) == selection["runId"], "Runtime selection/run ID is absent")
    source = args.source.resolve()
    require(source.is_relative_to(Path(os.environ["RUNNER_TEMP"]).resolve()), "Runtime downloads must stay in RUNNER_TEMP")
    for key in TARGETS[args.platform, args.arch]:
        matches = list(source.rglob(f"native-runtime-{key}.tar.gz"))
        require(len(matches) == 1 and not matches[0].is_symlink(), f"Expected one runtime archive for {key}")
        archive = matches[0]
        require(0 < archive.stat().st_size <= MAX_RUNTIME_BYTES, "Runtime archive exceeds download bound")
        fields = archive.with_suffix(archive.suffix + ".sha256").read_text(encoding="ascii").split()
        require(len(fields) == 2 and fields[1] == archive.name
                and re.fullmatch(r"[0-9a-f]{64}", fields[0]) and fields[0] == sha256(archive), "Runtime archive checksum differs")
        with tempfile.TemporaryDirectory(prefix="qfli-runtime-", dir=args.work_root) as temporary:
            extracted = Path(temporary)
            extract_runtime(archive, extracted)
            data = verify_runtime_payload(extracted, key, selection)
            for folder in ("android/app/src/main/jniLibs", "ohos/entry/libs", "native/build/runtime", "assets/miri"):
                merge_verified_tree(extracted / folder, ROOT / folder)
            shutil.copytree(extracted / "build-info", args.output / "reports/native-runtime" / key / "build-info")
            for row in data["files"]:
                relative = safe_relative(row["path"])
                if relative.parts[0] == "licenses":
                    license_path = args.output / "licenses" / key / Path(*relative.parts[1:])
                    license_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(extracted / "assets/miri" / row["asset"], license_path)
        selection["packages"].append({"target": key, "archiveSha256": fields[0], "manifestId": data.get("id"),
                                       "rustVersion": RUST_VERSION, "rustCommit": RUST_COMMIT,
                                       "nativeLibraries": len(data["nativeLibraries"]), "assets": len(data["files"])})
    selection["status"] = "verified_and_installed"


def setup_ohos(args, manifest):
    require(args.platform == "ohos", "OHOS setup is only valid for OHOS")
    sdk = args.work_root / "harmonyos-sdk"
    sdk.mkdir()
    archive = sdk / "ohos-sdk-linux-amd64.tar.gz"
    base = f"https://github.com/ErBWs/ohos-sdk/releases/download/{OHOS_SDK_RELEASE}"
    with archive.open("wb") as combined:
        for part, expected in OHOS_PARTS.items():
            target = archive.with_name(archive.name + "." + part)
            run(["curl", "--fail", "--location", "--retry", "3", "--max-time", "1800",
                 base + "/" + target.name, "-o", target], args.output / "reports" / f"ohos-download-{part}.log")
            require(sha256(target) == expected, "OHOS SDK split checksum differs")
            with target.open("rb") as stream:
                shutil.copyfileobj(stream, combined, 1024 * 1024)
            target.unlink()
    require(sha256(archive) == OHOS_SDK_SHA256, "OHOS SDK archive checksum differs")
    with tarfile.open(archive, "r:gz") as package:
        package.extractall(sdk, filter="data")
    archive.unlink()
    tools = sdk / "command-line-tools"
    metadata = read_json(tools / "sdk/default/sdk-pkg.json")
    require(str(metadata.get("data", {}).get("apiVersion")) == "26", "Expected OHOS API26 SDK")
    publish_environment({"HOS_SDK_HOME": tools / "sdk", "DEVECO_SDK_HOME": tools / "sdk",
                         "DEVECO_NODE_HOME": tools / "tool/node"}, [tools / "bin", tools / "tool/node/bin"])
    run([tools / "bin/ohpm", "--version"], args.output / "reports/ohpm-version.log")
    run([tools / "bin/hvigorw", "--version"], args.output / "reports/hvigor-version.log")
    manifest["ohosSdk"] = {"release": OHOS_SDK_RELEASE, "sha256": OHOS_SDK_SHA256,
                            "source": base, "provenance": "third_party_repackaged_mirror", "metadata": metadata}
    write_json(args.output / "reports/ohos-sdk.json", manifest["ohosSdk"])


def setup_flutter(args, manifest):
    reports = args.output / "reports"
    sdk = args.flutter_root
    require(not sdk.exists(), "Flutter SDK destination must be fresh")
    run(["git", "init", sdk], reports / "flutter-init.log")
    run(["git", "remote", "add", "origin", FLUTTER_REPOSITORY], reports / "flutter-remote.log", cwd=sdk)
    tag = "refs/tags/" + FLUTTER_TAG
    run(["git", "fetch", "--depth", "1", "origin", f"{tag}:{tag}"], reports / "flutter-fetch.log", cwd=sdk, timeout=1200)
    require(git_value(sdk, "rev-parse", tag + "^{commit}") == FLUTTER_COMMIT, "Flutter tag moved")
    run(["git", "checkout", "--detach", tag], reports / "flutter-checkout.log", cwd=sdk)
    engines = {}
    for name in ("engine.version", "engine.ohos.version", "engine.ohos.har.version"):
        relative = "bin/internal/" + name
        value = (sdk / relative).read_text().strip()
        require(re.fullmatch(r"[0-9a-f]{40}", value)
                and git_value(sdk, "show", f"{FLUTTER_COMMIT}:{relative}") == value,
                "Flutter engine identity differs from pinned SDK source")
        engines[name] = value
    manifest["flutter"].update(engine=engines["engine.version"], ohosEngine=engines["engine.ohos.version"],
                               internalEngineFiles=engines, toolingOverride=None)
    # Inspect immutable fork content without treating absence in the external
    # setup script as proof about the fork's internal dependency recipe.
    override_path = sdk / "packages/flutter_tools/pubspec_overrides.yaml"
    if override_path.exists():
        relative = override_path.relative_to(sdk).as_posix()
        expected = git_value(sdk, "rev-parse", f"{FLUTTER_COMMIT}:{relative}")
        require(git_value(sdk, "hash-object", relative) == expected,
                "Flutter tooling override differs from pinned fork source")
        manifest["flutter"]["forkToolingOverride"] = {"path": relative, "gitBlob": expected,
                                                       "sha256": sha256(override_path),
                                                       "rustNativeHooksVerified": False}
    write_json(reports / "flutter-sdk-input.json", manifest["flutter"])
    publish_environment({"QFLI_FLUTTER_ROOT": sdk}, [sdk / "bin"])
    env = environment()
    flag = "--enable-ohos" if args.platform == "ohos" else "--no-enable-ohos"
    run([flutter(args), "config", "--no-analytics", flag], reports / "flutter-config.log", env=env)
    version = json.loads(run([flutter(args), "--version", "--machine"], reports / "flutter-version.log", env=env))
    require(version.get("frameworkRevision") == FLUTTER_COMMIT and version.get("frameworkVersion") == FLUTTER_TAG
            and version.get("dartSdkVersion"), "Flutter/Dart version differs from pinned owner SDK")
    manifest["flutter"]["version"] = version
    if args.platform in ("linux", "windows", "macos"):
        run([flutter(args), "config", f"--enable-{args.platform}-desktop"], reports / "flutter-desktop-config.log", env=env)
    run([flutter(args), "precache", "--" + args.platform], reports / "flutter-precache.log", env=env)
    tooling_locks = []
    for source, name in ((sdk / "pubspec.lock", "flutter-root-pubspec.lock"),
                         (sdk / "packages/flutter_tools/pubspec.lock", "flutter-tools-pubspec.lock")):
        if source.exists():
            shutil.copy2(source, reports / name)
            tooling_locks.append({"file": name, "sha256": sha256(source)})
    require(tooling_locks, "Pinned Flutter bootstrap produced no tooling lock record")
    manifest["flutter"]["toolingLocks"] = tooling_locks
    manifest["flutter"]["toolingOverridesApplied"] = False


@contextmanager
def unsigned_ohos_profile():
    """Temporarily disable Hvigor signing in the disposable hosted checkout."""
    require_hosted_runner()
    names = ("ohos/build-profile.json5", "ohos/hvigor/hvigor-config.json5")
    require(not git_value(ROOT, "status", "--porcelain", "--", *names),
            "Refusing to overwrite modified OHOS build/signing configuration")
    import json5
    paths = [ROOT / name for name in names]
    require(all(path.is_file() and not path.is_symlink() for path in paths),
            "OHOS build configuration must be regular files")
    original = {path: path.read_bytes() for path in paths}
    try:
        profile = json5.loads(original[paths[0]].decode("utf-8"))
        profile["app"]["signingConfigs"] = []
        for product in profile["app"]["products"]:
            product.pop("signingConfig", None)
            product.pop("compileSdkVersion", None)
        config = json5.loads(original[paths[1]].decode("utf-8"))
        properties = config.setdefault("properties", {})
        require(isinstance(properties, dict), "Hvigor properties must be a typed object")
        properties["enableSignTask"] = False
        paths[0].write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
        paths[1].write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        yield
    finally:
        for path, content in original.items():
            path.write_bytes(content)


def release_command(args, env):
    command = [flutter(args), "build", "apk" if args.platform == "android" else "hap" if args.platform == "ohos" else args.platform,
               "--release", "--target", "lib/main.dart"]
    if args.platform == "android":
        command += ["--target-platform", "android-arm64,android-x64", "--split-per-abi"]
    elif args.platform in ("ios", "ohos"):
        command += ["--no-codesign"]
        if args.platform == "ios":
            command += ["--verbose"]
            # The pinned Flutter Xcode project forwards FLUTTER_XCODE_* values
            # as xcodebuild settings. Bind Xcode script phases to this runner's
            # Python before PATH can resolve an older system python3.
            python_bin = str(Path(sys.executable).resolve().parent)
            runner_path = env.get("PATH", "")
            env["FLUTTER_XCODE_PATH"] = os.pathsep.join(
                part for part in (python_bin, runner_path) if part)
        else:
            command += ["--target-platform", "ohos-arm64"]
    elif args.platform == "macos":
        env.update(FLUTTER_XCODE_ARCHS="x86_64" if args.arch == "x64" else "arm64", FLUTTER_XCODE_ONLY_ACTIVE_ARCH="YES",
                   CODE_SIGN_IDENTITY="-", CODE_SIGN_STYLE="Manual")
    return command


def resolved_dependency_paths(config_path):
    config = read_json(config_path)
    packages = {row["name"]: row for row in config["packages"]}
    resolved_paths = {}
    for name, relative in CORE_DEPENDENCY_PATHS.items():
        expected = (ROOT / relative).resolve()
        uri = urllib.parse.urlparse(packages.get(name, {}).get("rootUri", ""))
        require(uri.path and uri.scheme in ("", "file") and not uri.netloc,
                "Missing or unsupported resolved dependency URI: " + name)
        if uri.scheme == "file":
            resolved = Path(urllib.request.url2pathname(uri.path)).resolve()
        else:
            resolved = (config_path.parent / urllib.parse.unquote(uri.path)).resolve()
        require(resolved == expected, "Resolved dependency path differs: " + name)
        resolved_paths[name] = str(resolved)
    return resolved_paths


def build(args, manifest):
    context = unsigned_ohos_profile() if args.platform == "ohos" else nullcontext()
    with context:
        if args.platform == "ohos":
            manifest["ohosSigning"] = {"mode": "unsigned",
                                       "typedHvigorProperty": "properties.enableSignTask",
                                       "typedHvigorValue": False, "restoreOriginalConfig": True,
                                       "deviceReady": False}
        build_release(args, manifest)


def build_release(args, manifest):
    verify_core(args, manifest)
    require(git_value(args.flutter_root, "rev-parse", "HEAD") == FLUTTER_COMMIT, "Flutter checkout changed")
    if TARGETS[args.platform, args.arch]:
        require((manifest.get("nativeRuntime") or {}).get("status") == "verified_and_installed", "Missing verified native runtime")
    env = environment()
    reports = args.output / "reports"
    run([flutter(args), "pub", "get"], reports / "pub-get.log", env=env, timeout=1200)
    shutil.copy2(ROOT / "pubspec.lock", reports / "resolved-pubspec.lock")
    verify_core(args, manifest)
    config_path = ROOT / ".dart_tool/package_config.json"
    resolved_dependency_paths(config_path)
    package_config_sha256_before_build = sha256(config_path)
    resolved_lock_sha256 = sha256(ROOT / "pubspec.lock")
    run(release_command(args, env), reports / "flutter-build.log", env=env, timeout=5400)
    final_lock_sha256 = sha256(ROOT / "pubspec.lock")
    require(final_lock_sha256 == resolved_lock_sha256,
            "Flutter build changed pubspec.lock after dependency verification")
    resolved_paths = resolved_dependency_paths(config_path)
    write_json(reports / "resolved-core.json", {"coreCommit": manifest["core"]["commit"],
                                               "packageName": "qfli_studio_core", "pathVerified": True,
                                               "packages": resolved_paths,
                                               "packageConfigSha256BeforeBuild": package_config_sha256_before_build,
                                               "packageConfigSha256": sha256(config_path),
                                               "lockfileSha256BeforeBuild": resolved_lock_sha256,
                                               "lockfileSha256": final_lock_sha256})
    manifest["core"]["compatibility"] = "this_platform_release_build_only"
    # Keep bounded evidence of available intermediates, never a compiler/cache tree.
    roots = [ROOT / "build" / args.platform]
    if args.platform == "android":
        roots = [ROOT / "build/app/outputs"]
    elif args.platform == "ohos":
        roots = [ROOT / "ohos/entry/build/default/outputs"]
    entries = []
    for root in roots:
        for path in sorted(root.rglob("*")):
            if path.is_file() and not path.is_symlink():
                require(len(entries) < 30000, "Intermediate inventory exceeds bound")
                entries.append({"path": path.relative_to(ROOT).as_posix(), "size": path.stat().st_size})
    write_json(reports / "intermediate-inventory.json", {"files": entries, "retainedInSource": False})
    retain_intermediates(args, manifest)


def packaging_inputs(args):
    """Retain only the exact Flutter outputs consumed by installer assembly.

    Mobile: split release APKs, unsigned HAP or Runner.app. Desktop: the single
    release bundle/app. Never retain .dart_tool, SDKs, Gradle/Hvigor/CMake caches,
    native compiler build roots or a second copy of the whole build tree.
    """
    if args.platform == "android":
        paths = [ROOT / "build/app/outputs/flutter-apk" / f"app-{abi}-release.apk"
                 for abi in ("arm64-v8a", "x86_64")]
    elif args.platform == "ohos":
        paths = list((ROOT / "ohos/entry/build/default/outputs/default").glob("*-unsigned.hap"))
        require(len(paths) == 1, "Expected one unsigned Flutter HAP intermediate")
    elif args.platform == "ios":
        paths = [ROOT / "build/ios/iphoneos/Runner.app"]
    elif args.platform == "linux":
        paths = [ROOT / f"build/linux/{args.arch}/release/bundle"]
    elif args.platform == "windows":
        paths = [ROOT / f"build/windows/{args.arch}/runner/Release"]
    elif args.platform == "macos":
        paths = list((ROOT / "build/macos/Build/Products/Release").glob("*.app"))
        require(len(paths) == 1, "Expected one macOS Flutter app intermediate")
    else:
        raise RuntimeError("No intermediate selection for this target")
    require(all(path.exists() and not path.is_symlink() for path in paths), "Flutter packaging input is missing or linked")
    return paths


def archive_packaging_inputs(paths, archive):
    """Hash and archive a bounded set of real output bytes, preserving safe links."""
    entries = []
    total = 0
    root = ROOT.resolve()
    for source in paths:
        require(source.resolve().is_relative_to(root) and not source.is_symlink(), "Packaging input escapes checkout")
        candidates = [source]
        if source.is_dir():
            for folder, directories, files in os.walk(source, followlinks=False):
                candidates.extend(Path(folder) / name for name in sorted(directories + files))
                directories[:] = [name for name in directories if not (Path(folder) / name).is_symlink()]
        for path in candidates:
            require(not getattr(path, "is_junction", lambda: False)(), "Intermediate junctions are not supported")
            relative = path.relative_to(ROOT).as_posix()
            safe_relative(relative)
            if path.is_symlink():
                target = os.readlink(path)
                require(not Path(target).is_absolute() and "\\" not in target and ":" not in target
                        and path.exists() and path.resolve().is_relative_to(source.resolve()),
                        "Intermediate link is broken or escapes its selected bundle")
                row = {"path": relative, "kind": "symlink", "target": target}
            elif path.is_file():
                size = path.stat().st_size
                total += size
                require(total <= MAX_INTERMEDIATE_BYTES, "Selected intermediate bytes exceed 4 GiB bound")
                row = {"path": relative, "kind": "file", "size": size, "sha256": sha256(path)}
            else:
                require(path.is_dir(), "Unsupported intermediate output type")
                row = {"path": relative, "kind": "directory"}
            entries.append((path, row))
            require(len(entries) <= MAX_INTERMEDIATE_FILES, "Selected intermediate count exceeds bound")
    require(any(row["kind"] == "file" for _, row in entries), "No actual Flutter intermediate bytes selected")
    require(len({row["path"] for _, row in entries}) == len(entries), "Duplicate intermediate selection")
    with tarfile.open(archive, "w:gz", compresslevel=6, dereference=False) as bundle:
        for path, row in entries:
            if row["kind"] == "file":
                require(path.stat().st_size == row["size"] and sha256(path) == row["sha256"],
                        "Intermediate changed before archive")
            elif row["kind"] == "symlink":
                require(os.readlink(path) == row["target"], "Intermediate link changed before archive")
            bundle.add(path, arcname="payload/" + row["path"], recursive=False)
    require(archive.stat().st_size <= MAX_INTERMEDIATE_BYTES, "Intermediate archive exceeds 4 GiB bound")
    return {"files": [row for _, row in entries], "uncompressedBytes": total,
            "archiveSha256": sha256(archive), "archiveBytes": archive.stat().st_size}


def retain_intermediates(args, manifest):
    intermediate = ROOT / "build/app-intermediates" / f"{args.platform}-{args.arch}"
    require(not intermediate.exists(), "Refusing to reuse intermediate output")
    intermediate.mkdir(parents=True)
    reports = args.output / "reports"
    try:
        inputs = packaging_inputs(args)
        selection = archive_packaging_inputs(inputs, intermediate / "flutter-packaging-inputs.tar.gz")
        selection.update(selection="exact_flutter_outputs_consumed_by_installer_assembly",
                         maxUncompressedBytes=MAX_INTERMEDIATE_BYTES, maxMembers=MAX_INTERMEDIATE_FILES,
                         artifactKind="unverified_packaging_inputs_not_installers", retentionDays=1)
        write_json(intermediate / "selection.json", selection)
        for name in ("resolved-pubspec.lock", "resolved-core.json", "core-input.json"):
            shutil.copy2(reports / name, intermediate / name)
        write_json(intermediate / "provenance.json", {"source": manifest["source"], "core": manifest["core"],
                   "flutter": manifest["flutter"], "nativeRuntime": manifest["nativeRuntime"],
                   "actualFlutterOutputBytesRetained": True, "retentionDays": 1})
        write_checksums(intermediate)
        manifest["intermediates"] = {"status": "retained", "retentionDays": 1,
                                     "archiveSha256": selection["archiveSha256"],
                                     "uncompressedBytes": selection["uncompressedBytes"]}
    except BaseException:
        shutil.rmtree(intermediate)
        manifest["intermediates"] = {"status": "failed_not_retained", "retentionDays": 1}
        raise


def write_checksums(directory):
    checksums = []
    for path in sorted(directory.rglob("*")):
        require(not path.is_symlink(), "Artifact output links are not allowed")
        if path.is_file() and path != directory / "SHA256SUMS":
            checksums.append(f"{sha256(path)}  {path.relative_to(directory).as_posix()}\n")
    (directory / "SHA256SUMS").write_bytes("".join(checksums).encode("utf-8"))


def validate_packages(args):
    record = read_json(args.output / "reports/packages.json")
    require(record.get("deviceTests") == "not_run" and record.get("applicationUiVerified") is False,
            "Package report must not claim unperformed device/UI verification")
    require(record.get("schemaVersion") == 1 and record.get("platform") == args.platform
            and record.get("arch") == args.arch, "Installer report target differs")
    packages = record.get("packages", [])
    require(len(packages) == len(PACKAGE_NAMES[args.platform, args.arch])
            and {row.get("file") for row in packages} == set(PACKAGE_NAMES[args.platform, args.arch]),
            "Installer package set is incomplete")
    actual = {path.name for path in (args.output / "packages").iterdir()}
    require(actual == set(PACKAGE_NAMES[args.platform, args.arch]), "Unexpected installer output")
    total = 0
    formats = {"android": "apk", "ios": "ipa", "ohos": "hap", "linux": "deb", "windows": "exe", "macos": "dmg"}
    for row in packages:
        name = safe_relative(row["file"])
        require(len(name.parts) == 1 and row.get("validation") and isinstance(row.get("installVerified"), bool)
                and row.get("signing") == SIGNING[args.platform] and row.get("deviceReady") is False
                and row.get("format") == formats[args.platform],
                "Installer report lacks verification/signing evidence")
        path = args.output / "packages" / name
        verify_file(path, row)
        require(args.platform not in ("linux", "windows") or row["installVerified"] is True,
                "Desktop installer install/uninstall verification is absent")
        require(args.platform != "ohos" or row.get("bundleIdentifier") == application_id("ohos"),
                "OHOS package report bundle identifier differs")
        total += path.stat().st_size
    require(total <= MAX_PACKAGE_BYTES, "Installer packages exceed upload bound")
    return packages


def finalize(args, manifest):
    failure = None

    def invalidate_packages(error):
        manifest["packages"] = []
        manifest["packageStatus"] = "failed"
        manifest["status"] = "cancelled" if args.job_status == "cancelled" else "failed"
        message = redact(str(error))
        previous = manifest.get("error")
        manifest["error"] = f"{previous}\nFinalization failed: {message}" if previous and previous != message else message
        # Attempt every removal even if another output cannot be removed. Never
        # follow a linked package directory when invalidating upload candidates.
        for name in ("packages", ".verified-packages", "reports/packages.json", "SHA256SUMS"):
            path = args.output / name
            try:
                if path.is_symlink() or not path.is_dir():
                    path.unlink(missing_ok=True)
                else:
                    shutil.rmtree(path)
            except OSError as cleanup_error:
                manifest["error"] += f"\nCould not remove {name}: {redact(str(cleanup_error))}"

    try:
        required = {"init", "preflight", "verify-core", "setup-flutter", "build", "package"}
        if TARGETS[args.platform, args.arch]:
            required.update(("resolve-runtime", "install-runtime"))
        if args.platform == "ohos":
            required.add("setup-ohos")
        require(args.job_status == "success" and required.issubset(manifest.get("completedStages", [])),
                "Build stages did not all complete; no packages may be published")
        require(manifest.get("packageStatus") == "verified", "Installer stage did not verify every package")
        manifest["packages"] = validate_packages(args)
        if args.platform == "android":
            require(manifest.get("packageCoverage", {}).get("complete") is False
                    and manifest.get("packageCoverage", {}).get("blockers"),
                    "Android armv7 must remain an explicit incomplete coverage item")
        metadata = [path for path in args.output.rglob("*") if path.is_file()
                    and not path.is_relative_to(args.output / "packages")]
        require(len(metadata) <= 2000 and sum(path.stat().st_size for path in metadata) <= MAX_REPORT_BYTES,
                "Reports/licenses exceed bounded upload policy")
        manifest["status"] = "success"
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        invalidate_packages(error)
        failure = error
    manifest["stage"] = "finalize"
    manifest["deviceReady"] = False
    manifest["deviceTests"] = "not_run"
    manifest["applicationUiVerified"] = False
    try:
        write_json(args.output / "manifest.json", manifest)
        (args.output / "SIGNING.txt").write_text(
            f"Signing: {SIGNING[args.platform]}\nDevice tests: not run. Application UI: not verified.\n"
            "Unsigned iOS/OHOS artifacts require signing/provisioning before device installation.\n"
            "Desktop Rust execution requires installed cargo and rustc.\n"
            + (ARMV7_BLOCKER + "\n" if args.platform == "android" else ""), encoding="utf-8")
        # Failure reports have the same upload bound. Do not upload an oversized
        # directory merely because finalization itself failed.
        metadata = [path for path in args.output.rglob("*") if path.is_file()
                    and not path.is_relative_to(args.output / "packages")]
        if len(metadata) > 2000 or sum(path.stat().st_size for path in metadata) > MAX_REPORT_BYTES:
            shutil.rmtree(args.output / "reports", ignore_errors=True)
            shutil.rmtree(args.output / "licenses", ignore_errors=True)
            report_failure(args.output, "finalize", "Oversized reports/licenses omitted under bounded upload policy")
        write_checksums(args.output)
        step_summary(f"### {args.platform}/{args.arch}: {manifest['status']}\n\n"
                     f"App `{manifest['source']['commit']}`; core `{manifest['core'].get('commit')}`.\n\n"
                     f"Signing: `{SIGNING[args.platform]}`. Device/UI tests: **not run**. "
                     "Packages/reports: 14 days; selected intermediates: 1 day.\n")
    except BaseException as error:
        # Even an interrupted publication must leave no verified upload set.
        invalidate_packages(error)
        try:
            write_json(args.output / "manifest.json", manifest)
        except Exception:
            # A failed recovery write must not leave the earlier success record
            # available to an always-upload step.
            try:
                (args.output / "manifest.json").unlink(missing_ok=True)
            except OSError:
                pass
        try:
            report_failure(args.output, "finalize", manifest["error"])
        except Exception:
            pass
        raise
    if failure and args.job_status == "success":
        raise RuntimeError(str(failure))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("init", "preflight", "verify-core", "setup-ohos", "resolve-runtime",
                                          "install-runtime", "setup-flutter", "build", "finalize"))
    add_target_arguments(parser)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--job-status", default="failure")
    args = resolve_target(parser.parse_args(), parser)
    require_hosted_runner()
    require(args.output.is_relative_to(ROOT / "build/app-artifacts") and args.output != ROOT / "build/app-artifacts",
            "Output must be a target directory below build/app-artifacts")
    args.work_root = Path(os.environ["RUNNER_TEMP"]).resolve() / f"qfli-app-{args.platform}-{args.arch}"
    args.work_root.mkdir(parents=True, exist_ok=True)
    args.flutter_root = args.work_root / "flutter"
    manifest = initialize(args) if args.stage == "init" else read_json(args.output / "manifest.json")
    require(manifest.get("platform") == args.platform and manifest.get("arch") == args.arch, "Manifest target changed")
    if args.stage == "finalize":
        finalize(args, manifest)
        return
    manifest["stage"] = args.stage
    write_json(args.output / "manifest.json", manifest)
    try:
        stages = {"preflight": preflight, "verify-core": verify_core, "setup-ohos": setup_ohos,
                  "resolve-runtime": resolve_runtime, "install-runtime": install_runtime,
                  "setup-flutter": setup_flutter, "build": build}
        if args.stage != "init":
            stages[args.stage](args, manifest)
        manifest["completedStages"].append(args.stage)
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.CalledProcessError, tarfile.TarError) as error:
        manifest["status"] = "failed"
        manifest["error"] = redact(str(error))
        report_failure(args.output, args.stage, manifest["error"])
        raise
    finally:
        write_json(args.output / "manifest.json", manifest)


if __name__ == "__main__":
    main()
