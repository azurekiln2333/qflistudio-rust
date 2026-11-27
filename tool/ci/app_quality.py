#!/usr/bin/env python3
"""Core-bound application quality checks; execute only on GitHub-hosted runners.

Bootstrap uses app_build init/preflight/verify-core/setup-flutter in
build/app-artifacts/app-quality-linux-x64. Quality reports live separately in
build/app-quality/linux-x64. This helper never packages an installer or treats
skipped fixtures as native/device evidence. Checksums exist only after successful
report finalization; artifact upload success remains a separate workflow outcome.
"""

import argparse
import copy
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request

import app_build as app
from ci_support import (
    CORE_DIRECTORY, CORE_REPOSITORY, LOG_LIMIT, ROOT, annotate, annotate_command_failure,
    bounded_log, print_untrusted, read_json, redact, report_failure,
    require_hosted_runner, run, sha256, step_summary, write_json,
)


CHECKS = ("format", "analyze", "test")
BOOTSTRAP_STAGES = {"init", "preflight", "verify-core", "setup-flutter"}
MAX_REPORT_BYTES = 32 * 1024**2
MAX_REPORT_FILES = 200
MAX_MACHINE_BYTES = 128 * 1024**2
MAX_TEST_EVENTS = 1000000
INPUT_ROOTS = ("lib", "test", "integration_test", "pubspec.yaml", "pubspec.lock", "analysis_options.yaml")
SAFE_DIFF_PATHS = frozenset({
    "pubspec.yaml", "pubspec.lock",
    "linux/flutter/generated_plugin_registrant.cc",
    "linux/flutter/generated_plugin_registrant.h",
    "linux/flutter/generated_plugins.cmake",
    "windows/flutter/generated_plugin_registrant.cc",
    "windows/flutter/generated_plugin_registrant.h",
    "windows/flutter/generated_plugins.cmake",
    "macos/Flutter/GeneratedPluginRegistrant.swift",
})
MAX_TRACKED_DIAGNOSTIC_BYTES = 256 * 1024
MAX_TRACKED_DIAGNOSTIC_PATHS = 2048
MAX_TRACKED_PATH_BYTES = 96 * 1024
MAX_SAFE_DIFF_BYTES = 16 * 1024
MAX_SAFE_DIFF_FILE_BYTES = 256 * 1024


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def linked(path):
    return path.is_symlink() or getattr(path, "is_junction", lambda: False)()


def confined_output(args):
    root = args.root.resolve()
    output = args.output.resolve()
    require(output.is_relative_to(root / "build/app-quality") and output != root / "build/app-quality",
            "Quality output must be below build/app-quality")
    require(args.bootstrap.resolve().is_relative_to(root / "build/app-artifacts"),
            "Bootstrap report must be below build/app-artifacts")
    for directory in (args.output, args.output / "reports", args.bootstrap):
        require(not linked(directory), "Quality/bootstrap output must not be linked")
    if args.output.exists():
        for path in args.output.rglob("*"):
            require(not linked(path), "Quality report tree must not contain links")
    return output


def quality_args(root=ROOT, output=None, bootstrap=None):
    root = Path(root).resolve()
    return argparse.Namespace(root=root,
        output=Path(output) if output else root / "build/app-quality/linux-x64",
        bootstrap=Path(bootstrap) if bootstrap else root / "build/app-artifacts/app-quality-linux-x64")


def source_inputs(root):
    tracked = app.git_value(root, "ls-files", "-z", "--", *INPUT_ROOTS).split("\0")
    rows = []
    for name in sorted(filter(None, tracked)):
        app.safe_relative(name)
        if not name.endswith(".dart") and name not in INPUT_ROOTS:
            continue
        path = root / name
        require(path.is_file() and not linked(path) and path.resolve().is_relative_to(root),
                "Quality source must be a regular tracked file: " + name)
        rows.append({"path": name, "size": path.stat().st_size, "sha256": sha256(path)})
    require(any(row["path"].startswith("lib/") for row in rows), "No tracked application Dart sources")
    require(any(row["path"].startswith("test/") and row["path"].endswith("_test.dart") for row in rows),
            "No tracked root test suites")
    return rows


def input_identity(rows):
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def tracked_snapshot(root):
    """Capture hashes for every tracked regular file without retaining its contents."""
    root = Path(root).resolve()
    entries = app.git_value(root, "ls-files", "--stage", "-z").split("\0")
    snapshot = {}
    for entry in sorted(filter(None, entries)):
        identity, name = entry.split("\t", 1)
        mode, blob, stage = identity.split()
        app.safe_relative(name)
        require(re.fullmatch(r"[0-7]{6}", mode) and re.fullmatch(r"[0-9a-f]{40,64}", blob)
                and stage == "0", "Malformed or unmerged tracked input")
        row = {"indexMode": mode, "indexBlob": blob}
        snapshot[name] = row
        path = root / name
        if linked(path):
            row.update(state="linked")
            try:
                row["linkSha256"] = hashlib.sha256(os.fsencode(os.readlink(path))).hexdigest()
            except OSError:
                pass
            continue
        try:
            resolved = path.resolve()
        except OSError:
            row.update(state="unresolvable")
            continue
        if not path.exists():
            row.update(state="missing")
        elif resolved != path or not path.is_file():
            row.update(state="unsafe")
        else:
            try:
                stat = path.stat()
                row.update(state="file", size=stat.st_size, mode=oct(stat.st_mode), sha256=sha256(path))
            except OSError:
                row.update(state="unreadable")
    return snapshot


def safe_diff_text(text):
    # Redact full PEM blocks, including an unterminated block, before hunking.
    text = re.sub(r"(?s)-----BEGIN [^-]*PRIVATE KEY-----.*?(?:-----END [^-]*PRIVATE KEY-----|\Z)",
                  "[private key redacted]", text)
    # A sensitive YAML field may put its value on following indented lines.
    lines = []
    sensitive_indent = None
    for line in text.splitlines(keepends=True):
        indentation = len(line) - len(line.lstrip())
        if sensitive_indent is not None:
            if not line.strip() or indentation > sensitive_indent:
                lines.append("[sensitive diagnostic continuation redacted]\n")
                continue
            sensitive_indent = None
        clean = redact(line)
        if "[sensitive diagnostic line redacted]" in clean:
            sensitive_indent = indentation
        lines.append(clean)
    return "".join(lines)


def safe_diff_snapshot(root, tracked):
    """Retain redacted text only for tracked, literal-diff allowlist paths."""
    root = Path(root).resolve()
    snapshot = {}
    for name in sorted(SAFE_DIFF_PATHS & tracked.keys()):
        path = root / name
        if linked(path):
            snapshot[name] = {"state": "linked"}
            continue
        try:
            resolved = path.resolve()
        except OSError:
            snapshot[name] = {"state": "unresolvable"}
            continue
        if not path.exists():
            snapshot[name] = {"state": "missing"}
            continue
        if resolved != path or not path.is_file():
            snapshot[name] = {"state": "unsafe"}
            continue
        try:
            with path.open("rb") as stream:
                data = stream.read(MAX_SAFE_DIFF_FILE_BYTES + 1)
        except OSError:
            snapshot[name] = {"state": "unreadable"}
            continue
        if len(data) > MAX_SAFE_DIFF_FILE_BYTES:
            snapshot[name] = {"state": "oversized"}
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            snapshot[name] = {"state": "binary", "size": len(data)}
        else:
            if "\0" in text:
                snapshot[name] = {"state": "binary", "size": len(data)}
            else:
                # Redact complete files before generating context-limited hunks.
                # A private-key header may otherwise sit outside a diff hunk.
                snapshot[name] = {"state": "text", "size": len(data), "text": safe_diff_text(text)}
    return snapshot


def snapshot_summary(row):
    if row is None:
        return "missing"
    summary = str(row.get("state", "unknown"))
    for field in ("size", "mode", "sha256", "indexMode", "indexBlob", "linkSha256"):
        if field in row:
            summary += f" {field}={row[field]}"
    return summary


def safe_literal_diff(name, before, after):
    """Return content only for one exact allowlisted text path."""
    if name not in SAFE_DIFF_PATHS:
        return ""
    before_state = before.get(name, {"state": "missing"})
    after_state = after.get(name, {"state": "missing"})
    if before_state.get("state") == "text":
        old = before_state["text"]
    elif before_state.get("state") == "missing":
        old = ""
    else:
        return (f"[literal diff omitted: {before_state.get('state')} -> "
                f"{after_state.get('state')}]\n")
    if after_state.get("state") == "text":
        new = after_state["text"]
    elif after_state.get("state") == "missing":
        new = ""
    else:
        return (f"[literal diff omitted: {before_state.get('state')} -> "
                f"{after_state.get('state')}]\n")
    return "".join(difflib.unified_diff(
        old.splitlines(keepends=True), new.splitlines(keepends=True),
        fromfile="a/" + name, tofile="b/" + name, n=3))


def bounded_diagnostic(text, limit=None):
    text = redact(text)
    limit = MAX_TRACKED_DIAGNOSTIC_BYTES if limit is None else limit
    marker = "\n[tracked input diagnostic truncated]\n"
    encoded = text.encode("utf-8")
    if len(encoded) <= limit:
        return text
    content_limit = max(0, limit - len(marker.encode("utf-8")))
    marker = marker.encode("utf-8")[:limit].decode("utf-8", errors="ignore")
    return encoded[:content_limit].decode("utf-8", errors="ignore") + marker


def tracked_input_diagnostic(before, after, before_safe, after_safe, status=""):
    names = sorted(set(before) | set(after))
    changed = [name for name in names if before.get(name) != after.get(name)]
    lines = [
        "Tracked dependency-restore delta (path/hash data; bounded):",
        f"Changed tracked paths: {len(changed)}",
    ]
    for name in changed[:MAX_TRACKED_DIAGNOSTIC_PATHS]:
        lines.extend((f"{name}", f"  before: {snapshot_summary(before.get(name))}",
                      f"  after:  {snapshot_summary(after.get(name))}"))
    if len(changed) > MAX_TRACKED_DIAGNOSTIC_PATHS:
        lines.append(f"[additional changed paths omitted: {len(changed) - MAX_TRACKED_DIAGNOSTIC_PATHS}]")
    if not changed:
        lines.append("No whole-tree path/hash delta was observed.")
    if status:
        lines.extend(("", "Git tracked status (paths only):", status))
    diagnostic = bounded_diagnostic("\n".join(lines) + "\n", MAX_TRACKED_PATH_BYTES)
    safe_changed = [name for name in sorted(SAFE_DIFF_PATHS & set(changed))
                    if name in before_safe or name in after_safe]
    for name in safe_changed:
        diff = safe_literal_diff(name, before_safe, after_safe)
        section = f"\nSafe literal diff for {name}:\n" + (diff if diff else "[no textual delta after redaction]\n")
        diagnostic += bounded_diagnostic(section, MAX_SAFE_DIFF_BYTES)
    return bounded_diagnostic(diagnostic)


def write_tracked_input_diagnostic(args, before, after, before_safe, after_safe, status=""):
    """Publish a bounded diagnostic while leaving the strict rejection untouched."""
    report = args.output / "reports/pub-get-input-delta.txt"
    try:
        diagnostic = tracked_input_diagnostic(before, after, before_safe, after_safe, status)
    except Exception:
        # Never publish exception values: a reader may include source content.
        diagnostic = "Tracked input diagnostic unavailable; strict rejection retained.\n"
    try:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(diagnostic, encoding="utf-8", newline="\n")
    except OSError:
        pass
    # Both output channels see only the already-redacted bounded diagnostic.
    # The public annotation is further bounded by the shared annotation helper.
    for emit in (print_untrusted, lambda text: annotate(
            "error", text, heading="Dependency restore changed tracked inputs; see " + report.name)):
        try:
            emit(diagnostic)
        except Exception:
            pass


def verify_bootstrap(args, *, require_sdk=True):
    manifest = read_json(args.bootstrap / "manifest.json")
    require(manifest.get("platform") == "linux" and manifest.get("arch") == "x64",
            "Quality bootstrap target must be linux/x64")
    completed = set(manifest.get("completedStages", []))
    require(BOOTSTRAP_STAGES.issubset(completed), "Core/SDK bootstrap stages are incomplete")
    require(manifest.get("status") not in ("failed", "cancelled"), "Core/SDK bootstrap failed")
    source = manifest.get("source", {})
    require(source.get("commit") == os.environ.get("GITHUB_SHA")
            == app.git_value(args.root, "rev-parse", "HEAD"), "Quality source commit differs from workflow/bootstrap")
    require(not app.git_value(args.root, "status", "--porcelain", "--untracked-files=no"),
            "Tracked application source changed during quality checks")
    require(source.get("repository") == os.environ.get("GITHUB_REPOSITORY")
            and str(source.get("runId")) == os.environ.get("GITHUB_RUN_ID")
            and str(source.get("runAttempt")) == os.environ.get("GITHUB_RUN_ATTEMPT"),
            "Quality run identity differs from bootstrap")
    core = manifest.get("core", {})
    require(core.get("repository") == CORE_REPOSITORY and core.get("checkoutDirectory") == CORE_DIRECTORY
            and core.get("packageName") == "qfli_studio_core" and core.get("checkoutVerified") is True,
            "Core checkout/package identity is not verified")
    require(core.get("commit") == os.environ.get("CORE_SHA") == os.environ.get("APPROVED_CORE_SHA")
            and re.fullmatch(r"[0-9a-f]{40}", str(core.get("commit", "")))
            and not core["commit"].startswith(("ee83f1c", "573d1b6")), "Core SHA lacks current owner approval")
    require(os.environ.get("CORE_SDK_CONTRACT") == app.SDK_CONTRACT == core.get("sdkContract"),
            "Core SDK contract lacks current owner approval")
    core_root = args.root.parent / CORE_DIRECTORY
    require(core_root.is_dir() and not linked(core_root), "Expected real sibling qflistudio-core checkout")
    require(app.git_value(core_root, "rev-parse", "HEAD") == core["commit"], "Core SHA changed")
    require(not app.git_value(core_root, "status", "--porcelain", "--untracked-files=no"),
            "Tracked core source changed during quality checks")
    # Reuse B's exact path/override/lock checks without modifying its manifest.
    app.verify_core(argparse.Namespace(output=args.output), copy.deepcopy(manifest))
    if require_sdk:
        sdk = Path(os.environ.get("QFLI_FLUTTER_ROOT", ""))
        temporary = Path(os.environ["RUNNER_TEMP"]).resolve()
        require(sdk.is_dir() and not linked(sdk) and sdk.resolve().is_relative_to(temporary),
                "Quality SDK must be the bootstrapped RUNNER_TEMP checkout")
        require(app.git_value(sdk, "rev-parse", "HEAD") == app.FLUTTER_COMMIT,
                "Flutter checkout differs from approved SDK")
        flutter = manifest.get("flutter", {})
        require(flutter.get("commit") == app.FLUTTER_COMMIT and flutter.get("tag") == app.FLUTTER_TAG
                and flutter.get("repository") == app.FLUTTER_REPOSITORY
                and flutter.get("sdkContract") == app.SDK_CONTRACT
                and flutter.get("toolingOverride") is None
                and flutter.get("toolingOverridesApplied") is False,
                "SDK identity or external tooling override state differs")
        version = flutter.get("version", {})
        require(version.get("frameworkRevision") == app.FLUTTER_COMMIT
                and version.get("frameworkVersion") == app.FLUTTER_TAG and version.get("dartSdkVersion"),
                "Bootstrap did not verify the Flutter/Dart version")
        for name, identity in flutter.get("internalEngineFiles", {}).items():
            relative = "bin/internal/" + name
            require(re.fullmatch(r"engine(?:\.ohos(?:\.har)?)?\.version", name)
                    and (sdk / relative).read_text().strip() == identity
                    == app.git_value(sdk, "show", f"{app.FLUTTER_COMMIT}:{relative}"),
                    "SDK engine file changed")
        require(set(flutter.get("internalEngineFiles", {}))
                == {"engine.version", "engine.ohos.version", "engine.ohos.har.version"},
                "SDK engine identities are incomplete")
        locks = flutter.get("toolingLocks", [])
        require(locks, "SDK tooling lock evidence is missing")
        lock_paths = {"flutter-root-pubspec.lock": sdk / "pubspec.lock",
                      "flutter-tools-pubspec.lock": sdk / "packages/flutter_tools/pubspec.lock"}
        for row in locks:
            require(row.get("file") in lock_paths and sha256(lock_paths[row["file"]]) == row.get("sha256"),
                    "SDK tooling lock changed")
        changed = app.git_value(sdk, "diff", "--name-only", "HEAD", "--").splitlines()
        require(set(changed).issubset({"pubspec.lock", "packages/flutter_tools/pubspec.lock"}),
                "SDK source changed outside recorded bootstrap locks")
        override = sdk / "packages/flutter_tools/pubspec_overrides.yaml"
        if override.exists():
            recorded = flutter.get("forkToolingOverride", {})
            require(recorded.get("path") == override.relative_to(sdk).as_posix()
                    and recorded.get("sha256") == sha256(override)
                    and app.git_value(sdk, "hash-object", recorded["path"]) == recorded.get("gitBlob")
                    == app.git_value(sdk, "rev-parse", f"{app.FLUTTER_COMMIT}:{recorded['path']}"),
                    "Unapproved or changed SDK tooling override")
        else:
            require(not flutter.get("forkToolingOverride"), "Recorded SDK tooling override is missing")
    return manifest


def executables():
    sdk = Path(os.environ["QFLI_FLUTTER_ROOT"])
    flutter = sdk / "bin" / ("flutter.bat" if os.name == "nt" else "flutter")
    dart = sdk / "bin/cache/dart-sdk/bin" / ("dart.exe" if os.name == "nt" else "dart")
    require(flutter.is_file() and dart.is_file(), "Bootstrapped Flutter/Dart executables are missing")
    return flutter, dart


def command_environment():
    env = app.environment()
    # No read token should reach a restore, analyzer or executable test fixture.
    for name in ("GH_TOKEN", "GITHUB_TOKEN", "ACTIONS_RUNTIME_TOKEN"):
        env.pop(name, None)
    return env


def verify_resolved_paths(args):
    path = args.root / ".dart_tool/package_config.json"
    config = read_json(path)
    packages = {row["name"]: row for row in config.get("packages", [])}
    expected = {"qfli_rust": args.root, "qfli_studio_core": args.root.parent / CORE_DIRECTORY,
                "re_editor": args.root.parent / CORE_DIRECTORY / "vendor/re_editor",
                "xterm": args.root.parent / CORE_DIRECTORY / "vendor/xterm"}
    for name, root in expected.items():
        uri = urllib.parse.urlparse(packages.get(name, {}).get("rootUri", ""))
        require(uri.path and uri.scheme in ("", "file"), "Missing or unsupported resolved dependency: " + name)
        require(not uri.netloc and not uri.query and not uri.fragment,
                "Remote or qualified resolved dependency is not allowed: " + name)
        if uri.scheme == "file":
            resolved = Path(urllib.request.url2pathname(uri.path)).resolve()
        else:
            resolved = (path.parent / urllib.parse.unquote(uri.path)).resolve()
        require(resolved == root.resolve(), "Resolved package path differs: " + name)
    return {"sha256": sha256(path), "packages": {name: str(root) for name, root in expected.items()}}


def new_manifest(args):
    return {"schemaVersion": 1, "artifactKind": "application_quality_not_an_installer",
            "status": "incomplete", "prepared": False, "checks": {name: {"status": "not_run"} for name in CHECKS},
            "source": {"repository": os.environ.get("GITHUB_REPOSITORY"), "commit": os.environ.get("GITHUB_SHA"),
                       "runId": os.environ.get("GITHUB_RUN_ID"), "runAttempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
                       "ref": os.environ.get("GITHUB_REF"), "event": os.environ.get("GITHUB_EVENT_NAME")},
            "deviceExecuted": False, "nativeRuntimeExecuted": False, "applicationUiVerified": False,
            "coverage": "format_analysis_and_root_test_directory_only", "retentionDays": 14,
            "publication": {"status": "incomplete", "scope": "runner_report_files_only",
                            "artifactUpload": "not_established_by_helper"},
            "evidenceBounds": {"maxReportBytes": MAX_REPORT_BYTES, "maxReportFiles": MAX_REPORT_FILES,
                               "maxMachineBytes": MAX_MACHINE_BYTES, "maxTestEvents": MAX_TEST_EVENTS},
            "limitations": ["No installer, native runtime, target-device or application UI validation",
                            "integration_test sources are formatted, not executed as device tests",
                            "Host rustc/cargo versions are provenance, not a native execution pass",
                            "Owner approval of core/SDK inputs is not a Rust native-hooks compatibility result"]}


def save(args, manifest):
    write_json(args.output / "manifest.json", manifest)


def prepare(args, manifest):
    bootstrap = verify_bootstrap(args)
    manifest.update(source=bootstrap["source"], core=copy.deepcopy(bootstrap["core"]),
                    flutter=copy.deepcopy(bootstrap["flutter"]))
    before = source_inputs(args.root)
    before_tracked = tracked_snapshot(args.root)
    before_safe = safe_diff_snapshot(args.root, before_tracked)
    flutter, _ = executables()
    run([flutter, "pub", "get"], args.output / "reports/pub-get.log", cwd=args.root,
        env=command_environment(), timeout=1200)
    after_tracked = tracked_snapshot(args.root)
    after_safe = safe_diff_snapshot(args.root, after_tracked)
    tracked_status = app.git_value(args.root, "status", "--porcelain", "--untracked-files=no")
    source_error = None
    try:
        after = source_inputs(args.root)
    except Exception as error:
        source_error = error
        after = None
    if source_error is not None or after != before or after_tracked != before_tracked or tracked_status:
        write_tracked_input_diagnostic(args, before_tracked, after_tracked, before_safe, after_safe, tracked_status)
    if source_error is not None:
        raise source_error
    require(after == before,
            "Dependency restore changed tracked quality inputs; review cloud lockfile changes before retrying")
    require(after_tracked == before_tracked,
            "Dependency restore changed tracked repository inputs; review generated-source changes before retrying")
    verify_bootstrap(args)
    manifest["resolvedDependencies"] = verify_resolved_paths(args)
    _, dart = executables()
    manifest["sdkExecutableHashes"] = {"flutter": sha256(flutter), "dart": sha256(dart)}
    manifest["hostRustTools"] = {}
    for tool, arguments in (("rustc", ["-vV"]), ("cargo", ["--version"])):
        manifest["hostRustTools"][tool] = run([tool, *arguments], args.output / "reports" / f"{tool}-version.log",
                                             cwd=args.root, env=command_environment(), timeout=60).strip()[:4000]
    manifest["inputs"] = {"sha256": input_identity(before), "files": before}
    manifest["rootTestFiles"] = [row["path"] for row in before
                                 if row["path"].startswith("test/") and row["path"].endswith("_test.dart")]
    manifest["prepared"] = True
    manifest["core"]["compatibility"] = "quality_checks_pending"


def verify_prepared(args, manifest):
    require(manifest.get("prepared") is True, "Quality prepare did not complete; no check may pass")
    bootstrap = verify_bootstrap(args)
    for key in ("source", "flutter"):
        require(manifest.get(key) == bootstrap.get(key), "Quality/bootstrap provenance changed: " + key)
    require(manifest.get("core", {}).get("commit") == bootstrap.get("core", {}).get("commit"),
            "Quality core identity changed")
    rows = source_inputs(args.root)
    require(rows == manifest.get("inputs", {}).get("files")
            and input_identity(rows) == manifest.get("inputs", {}).get("sha256"),
            "Tracked inputs changed after quality preparation")
    require(verify_resolved_paths(args) == manifest.get("resolvedDependencies"),
            "Resolved dependency paths changed after preparation")
    flutter, dart = executables()
    require({"flutter": sha256(flutter), "dart": sha256(dart)} == manifest.get("sdkExecutableHashes"),
            "Flutter/Dart executable bytes changed after preparation")


def commands(args):
    flutter, dart = executables()
    return {"format": [dart, "format", "--output=none", "--set-exit-if-changed", "lib", "test", "integration_test"],
            "analyze": [flutter, "analyze", "--no-pub"],
            "test": [flutter, "test", "--no-pub", "--machine", "test"]}


def run_machine(command, log, machine, *, cwd, env, timeout=2400):
    """Keep the full protocol private; publish only a bounded, redacted log.

    Shared run() intentionally bounds/redacts merged output, so it cannot be
    used to capture a complete JSON protocol. Keep stderr separate from stdout
    and never replace the required --machine command with a filtered test run.
    """
    require_hosted_runner()
    command = [str(value) for value in command]
    print_untrusted("+ " + redact(" ".join(command)))
    stderr = machine.with_name("stderr.log")
    timed_out = False
    returncode = None
    with machine.open("w", encoding="utf-8") as stdout, stderr.open("w", encoding="utf-8") as errors:
        try:
            returncode = subprocess.run(command, cwd=cwd, env=env, stdout=stdout, stderr=errors,
                                        timeout=timeout, check=False).returncode
        except subprocess.TimeoutExpired:
            timed_out = True
        finally:
            stdout.flush()
            errors.flush()
            # Redact before truncation; raw JSON and stderr stay in RUNNER_TEMP.
            output = ("Machine stdout (bounded tail):\n" + bounded_log(machine)
                      + "\nStderr (bounded tail):\n" + bounded_log(stderr))
            output = output.encode("utf-8")[-LOG_LIMIT:].decode("utf-8", errors="ignore")
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text("Command: " + redact(repr(command)) + "\n\n" + output, encoding="utf-8")
            print_untrusted(output[-12000:])
    if timed_out:
        raise RuntimeError(f"Root tests timed out after {timeout} s; see {log.name}")
    if returncode:
        annotate_command_failure(log, returncode, output)
        raise RuntimeError(f"Root test command failed ({returncode}); see {log.name}")


def machine_summary(path, root, expected):
    root = Path(root).resolve()
    require(path.is_file() and not linked(path) and path.stat().st_size <= MAX_MACHINE_BYTES,
            "Root test machine report is absent or exceeds its bound")
    suites = set()
    tests = {}
    results = {}
    done = []
    failures = []
    errored = set()
    count = 0
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            count += 1
            require(count <= MAX_TEST_EVENTS and len(line) <= 1024**2, "Test protocol exceeds event bounds")
            if not line.strip():
                continue
            event = json.loads(line)
            require(isinstance(event, dict), "Malformed test protocol event")
            kind = event.get("type")
            if kind == "suite":
                suite = event.get("suite", {})
                value = suite.get("path")
                if value:
                    suite_path = Path(value)
                    if not suite_path.is_absolute():
                        suite_path = root / suite_path
                    resolved = suite_path.resolve()
                    require(resolved.is_relative_to(root / "test"), "Test report names a suite outside root test/")
                    suites.add(resolved.relative_to(root).as_posix())
            elif kind == "testStart":
                test = event["test"]
                require(test["id"] not in tests, "Duplicate test start")
                tests[test["id"]] = redact(str(test.get("name", "")))[:500]
            elif kind == "testDone":
                test_id = event["testID"]
                require(test_id in tests and test_id not in results
                        and event.get("result") in ("success", "failure", "error"),
                        "Duplicate or malformed test completion")
                results[test_id] = {"result": event["result"], "skipped": event.get("skipped") is True,
                                    "hidden": event.get("hidden") is True}
            elif kind == "done":
                done.append(event.get("success"))
            elif kind == "error":
                errored.add(event.get("testID"))
                if len(failures) < 30:
                    failures.append(redact(str(event.get("error", "test error")))[:2000])
    visible = {key: value for key, value in results.items() if not value["hidden"]}
    skipped = sum(row["skipped"] for row in visible.values())
    failed = len(errored | {key for key, row in results.items() if row["result"] in ("failure", "error")})
    unfinished = sorted(str(key) for key in set(tests) - set(results))
    missing = sorted(set(expected) - suites)
    summary = {"scope": "full_root_test_directory", "suiteFiles": sorted(suites), "missingSuiteFiles": missing,
               "completed": len(visible), "passed": sum(row["result"] == "success" and not row["skipped"]
                                                        for row in visible.values()),
               "skipped": skipped, "failed": failed, "unfinishedTestIds": unfinished, "protocolDone": done == [True],
               "skippedTestNames": [tests.get(key, str(key)) for key, row in visible.items() if row["skipped"]][:100],
               "errors": failures, "rawReportSha256": sha256(path), "rawReportBytes": path.stat().st_size,
               "rawReportPublished": False, "nativeRuntimeExecuted": False, "deviceExecuted": False}
    summary["success"] = summary["passed"] > 0 and not failed and not unfinished and not missing and done == [True]
    return summary


def execute_check(args, manifest, stage):
    verify_prepared(args, manifest)
    command = commands(args)[stage]
    manifest["checks"][stage] = {"status": "running", "command": [str(value) for value in command]}
    save(args, manifest)
    failure = None
    try:
        if stage == "test":
            with tempfile.TemporaryDirectory(prefix="qfli-quality-tests-", dir=os.environ["RUNNER_TEMP"]) as scratch:
                machine = Path(scratch) / "events.jsonl"
                try:
                    run_machine(command, args.output / "reports/test.log", machine, cwd=args.root,
                                env=command_environment(), timeout=2400)
                except Exception as error:
                    failure = error
                try:
                    summary = machine_summary(machine, args.root, manifest["rootTestFiles"])
                except Exception as error:
                    if failure:
                        raise RuntimeError(f"{failure}; machine evidence unavailable: {error}") from error
                    raise
                write_json(args.output / "reports/root-tests.json", summary)
                manifest["checks"][stage].update(summary=summary)
                require(failure is None and summary["success"],
                        str(failure) if failure else "Root tests lack a complete successful protocol or suite coverage")
        else:
            run(command, args.output / "reports" / f"{stage}.log", cwd=args.root,
                env=command_environment(), timeout=1200)
        # Format verification uses --output=none. Guard against any check changing
        # authored inputs or resolution despite reporting a successful exit.
        verify_prepared(args, manifest)
        status = "passed_with_skips" if stage == "test" and summary["skipped"] else "passed"
        manifest["checks"][stage]["status"] = status
    except BaseException as error:
        manifest["checks"][stage].update(status="cancelled" if isinstance(error, KeyboardInterrupt) else "failed",
                                           error=redact(str(error))[:4000])
        raise


def retain_bootstrap(args):
    reports = args.bootstrap / "reports"
    candidates = [args.bootstrap / "manifest.json"]
    if reports.is_dir():
        require(not linked(reports), "Linked bootstrap reports are forbidden")
        candidates += sorted(path for path in reports.rglob("*") if path.is_file())
    require(len(candidates) <= 70, "Bootstrap report file count exceeds bound")
    for source in candidates:
        if not source.exists():
            continue
        require(not linked(source) and source.resolve().is_relative_to(args.bootstrap.resolve())
                and source.stat().st_size <= 3 * 1024**2, "Unsafe or oversized bootstrap report")
        relative = source.relative_to(args.bootstrap)
        destination = args.output / "reports/bootstrap" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(bounded_log(source), encoding="utf-8", newline="\n")


def checksums(args):
    rows = []
    destination = args.output / "SHA256SUMS"
    pending = args.output / ".SHA256SUMS.pending"
    pending.unlink(missing_ok=True)
    for path in sorted(args.output.rglob("*")):
        require(not linked(path), "Quality reports must not contain links")
        if path.is_file() and path not in (destination, pending):
            rows.append(f"{sha256(path)}  {path.relative_to(args.output).as_posix()}\n")
    pending.write_bytes("".join(rows).encode())
    pending.replace(destination)


def verify_report_bounds(args):
    files = []
    for path in args.output.rglob("*"):
        require(not linked(path), "Quality reports must not contain links")
        if path.is_file():
            files.append(path)
    require(len(files) <= MAX_REPORT_FILES
            and sum(path.stat().st_size for path in files) <= MAX_REPORT_BYTES,
            "Quality reports exceeded publication bounds")


def quality_summary(manifest):
    outcomes = ", ".join(f"{name}: {manifest['checks'].get(name, {}).get('status', 'not_run')}" for name in CHECKS)
    return (f"### Application quality: {manifest['status']}\n\n{outcomes}.\n\n"
            f"Source `{manifest['source'].get('commit')}`; core `{manifest.get('core', {}).get('commit', 'unapproved')}`; "
            f"SDK `{app.SDK_CONTRACT}`.\n\n"
            "Reports: `build/app-quality/linux-x64`; bootstrap: `build/app-artifacts/app-quality-linux-x64`. "
            "Report retention: 14 days; publication bound: 200 files / 32 MiB. "
            "The private machine protocol is bounded at 128 MiB / 1,000,000 events and is not uploaded.\n\n"
            "Skipped fixtures remain skipped evidence. No installer, target-device, native-runtime or application UI "
            "execution is established. Core/SDK approval does not establish a Rust native-hooks recipe. "
            "Artifact upload must separately succeed in this job.\n")


def invalidate_publication(args, manifest, job_status, error):
    """Never leave success metadata/checksums after a final publication error.

    Recovery is best effort on a broken filesystem. Remove the old manifest
    before attempting diagnostics so a second write failure cannot leave a
    readable success manifest. Preserve individual check outcomes as evidence.
    """
    manifest.update(status="cancelled" if job_status == "cancelled" else "failed" if manifest.get("prepared") else "blocked",
                    error=redact(str(error))[:4000])
    manifest["publication"] = {"status": "failed", "scope": "runner_report_files_only",
                               "artifactUpload": "not_established_by_helper"}
    if "core" in manifest:
        manifest["core"]["compatibility"] = "not_established_by_failed_quality_finalization"
    recovery_errors = []
    for name in ("SHA256SUMS", ".SHA256SUMS.pending", "manifest.json"):
        try:
            (args.output / name).unlink(missing_ok=True)
        except OSError as recovery:
            recovery_errors.append(redact(str(recovery))[:1000])
    try:
        verify_report_bounds(args)
    except (OSError, RuntimeError):
        # Reports are this helper's generated output only, never source or the
        # sibling bootstrap directory. Do not retain an unbounded failed upload.
        shutil.rmtree(args.output / "reports", ignore_errors=True)
    try:
        report_failure(args.output, "quality-finalize", manifest["error"])
    except Exception as recovery:
        recovery_errors.append(redact(str(recovery))[:1000])
    if recovery_errors:
        manifest["recoveryErrors"] = recovery_errors
    try:
        save(args, manifest)
    except Exception as recovery:
        # A partial failed write is not valid publication evidence either.
        try:
            (args.output / "manifest.json").unlink(missing_ok=True)
        except OSError:
            pass
        recovery_errors.append(redact(str(recovery))[:1000])
    try:
        step_summary(quality_summary(manifest))
    except Exception:
        pass
    return recovery_errors


def finalize(args, manifest, job_status):
    manifest.update(jobStatus=job_status, deviceExecuted=False, nativeRuntimeExecuted=False, applicationUiVerified=False)
    try:
        # Invalidate a previous attempt before doing any failure-prone work.
        for name in ("SHA256SUMS", ".SHA256SUMS.pending"):
            (args.output / name).unlink(missing_ok=True)
        retain_bootstrap(args)
        require(job_status == "success", "Quality job did not complete all required stages")
        require(manifest.get("prepared") is True, "Core/SDK approval or quality preparation is blocked")
        verify_prepared(args, manifest)
        require(all(manifest["checks"].get(name, {}).get("status") in ("passed", "passed_with_skips") for name in CHECKS),
                "At least one required application quality check did not pass")
        summary = manifest["checks"]["test"].get("summary", {})
        require(summary.get("success") is True and summary.get("protocolDone") is True
                and summary.get("passed", 0) > 0 and not summary.get("failed")
                and not summary.get("unfinishedTestIds") and not summary.get("missingSuiteFiles")
                and set(manifest["rootTestFiles"]).issubset(summary.get("suiteFiles", []))
                and read_json(args.output / "reports/root-tests.json") == summary,
                "Complete successful root test evidence is missing or changed")
        skips = summary.get("skipped", 0)
        require(manifest["checks"]["test"]["status"] == ("passed_with_skips" if skips else "passed"),
                "Root test skip evidence differs from the recorded check status")
        manifest["status"] = "passed_with_skips" if skips else "passed"
        manifest.pop("error", None)
        manifest.pop("recoveryErrors", None)
        manifest["core"]["compatibility"] = "linux_host_quality_checks_only"
        manifest["publication"] = {"status": "complete", "scope": "runner_report_files_only",
                                   "artifactUpload": "not_established_by_helper"}
        # These writes belong to one failure boundary. A checksum, final bound,
        # manifest or summary failure must revoke the candidate success below.
        save(args, manifest)
        verify_report_bounds(args)
        checksums(args)
        verify_report_bounds(args)
        step_summary(quality_summary(manifest))
    except BaseException as error:
        recovery_errors = invalidate_publication(args, manifest, job_status, error)
        detail = "; recovery also failed: " + "; ".join(recovery_errors) if recovery_errors else ""
        raise RuntimeError(redact(str(error)) + detail) from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare", *CHECKS, "finalize"))
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--bootstrap-dir", type=Path)
    parser.add_argument("--job-status", default="failure")
    options = parser.parse_args()
    require_hosted_runner()
    args = quality_args(output=options.output_dir, bootstrap=options.bootstrap_dir)
    confined_output(args)
    args.output.mkdir(parents=True, exist_ok=True)
    path = args.output / "manifest.json"
    manifest = read_json(path) if path.exists() else new_manifest(args)
    if options.stage == "finalize":
        finalize(args, manifest, options.job_status)
        return
    try:
        if options.stage == "prepare":
            require(not manifest.get("prepared"), "Quality prepare must not reuse prepared results")
            prepare(args, manifest)
        else:
            execute_check(args, manifest, options.stage)
    except BaseException as error:
        manifest.update(status="blocked" if not manifest.get("prepared") else "failed",
                        error=redact(str(error))[:4000])
        report_failure(args.output, "quality-" + options.stage, manifest["error"])
        raise
    finally:
        save(args, manifest)


if __name__ == "__main__":
    main()
