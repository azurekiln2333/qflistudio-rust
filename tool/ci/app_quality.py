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
import time
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
# Analyzer/workspace formatter failures were reported at hosted run
# 46014152444; the terminal fixture is included because it is changing here.
FORMAT_DIAGNOSTIC_PATHS = frozenset({
    "test/rust_code_analyzer_test.dart",
    "test/rust_workspace_integration_test.dart",
    "test/rust_terminal_commands_test.dart",
})
MAX_FORMAT_DIAGNOSTIC_PATHS = 8
MAX_FORMAT_DIAGNOSTIC_FILES = 3
MAX_FORMAT_DIAGNOSTIC_FILE_BYTES = 256 * 1024
MAX_FORMAT_DIAGNOSTIC_OUTPUT_BYTES = 256 * 1024
MAX_FORMAT_DIAGNOSTIC_BYTES = 48 * 1024
FORMAT_DIAGNOSTIC_TIMEOUT = 120
MAX_MACHINE_SUMMARY_ERRORS = 30
MAX_MACHINE_SUMMARY_BYTES = 64 * 1024
MAX_FRAMEWORK_EXCEPTION_BYTES = 16 * 1024
MAX_FRAMEWORK_EXCEPTION_RECORD_BYTES = 4000
FRAMEWORK_EXCEPTION_HEADER = "EXCEPTION CAUGHT BY FLUTTER TEST FRAMEWORK"
QUALITY_ASSET_TARGETS = ("ohos-arm64", "ohos-x64")


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


def format_diagnostic_paths(root):
    """Return the approved preview names that are tracked and confined.

    Names come from a literal allowlist, never from tool output, and every
    existing path must stay inside the checkout without links.
    """
    root = Path(root).resolve()
    require(len(FORMAT_DIAGNOSTIC_PATHS) <= MAX_FORMAT_DIAGNOSTIC_PATHS,
            "Formatter diagnostic allowlist exceeds its bound")
    names = []
    for name in sorted(FORMAT_DIAGNOSTIC_PATHS)[:MAX_FORMAT_DIAGNOSTIC_PATHS]:
        require(re.fullmatch(r"test/[A-Za-z0-9_]+(?:\.dart)", name),
                "Formatter diagnostic path is not a literal root test file")
        path = root / name
        if not path.exists() and not linked(path):
            continue
        require(not linked(path), "Formatter diagnostic source is linked: " + name)
        try:
            resolved = path.resolve()
        except OSError as error:
            raise RuntimeError("Formatter diagnostic source is unresolvable: " + name) from error
        require(resolved == path and resolved.is_relative_to(root) and path.is_file(),
                "Formatter diagnostic source escapes the checkout: " + name)
        names.append(name)
        if len(names) >= MAX_FORMAT_DIAGNOSTIC_FILES:
            break
    return names


def _format_source_snapshot(root, name):
    """Read one approved formatter input and redact it before any diff."""
    require(name in FORMAT_DIAGNOSTIC_PATHS, "Formatter diagnostic path is not approved")
    path = Path(root).resolve() / name
    if linked(path):
        return {"state": "linked"}
    try:
        resolved = path.resolve()
    except OSError:
        return {"state": "unresolvable"}
    if resolved != path or not path.is_file():
        return {"state": "missing" if not path.exists() else "unsafe"}
    try:
        with path.open("rb") as stream:
            data = stream.read(MAX_FORMAT_DIAGNOSTIC_FILE_BYTES + 1)
    except OSError:
        return {"state": "unreadable"}
    if len(data) > MAX_FORMAT_DIAGNOSTIC_FILE_BYTES:
        return {"state": "oversized"}
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return {"state": "binary", "size": len(data)}
    if "\0" in text:
        return {"state": "binary", "size": len(data)}
    return {"state": "text", "size": len(data), "text": safe_diff_text(text)}


def format_preview_command(executable, name):
    """Build one preview command already proven to emit formatted source.

    `--output=show` writes the formatted source to stdout without touching the
    file, and `--show=none`/`--summary=none` suppress the other stdout lines
    so the capture contains only formatted source.
    Leave the exit code alone so a genuine formatter error stays visible.
    """
    require(name in FORMAT_DIAGNOSTIC_PATHS, "Formatter preview path is not approved")
    return [str(executable), "format", "--output=show", "--show=none", "--summary=none", name]


def run_format_preview(command, *, cwd, env):
    """Capture a bounded private stdout snapshot without editing source.

    A regular file avoids waiting for pipe EOF when a descendant inherits
    stdout. Size polling is not a hard disk quota; stderr is discarded.
    Each invocation has its own 120-second deadline; up to three files are
    previewed sequentially, with a separate five-second cleanup wait.
    """
    require_hosted_runner()
    command = [str(value) for value in command]
    deadline = time.monotonic() + FORMAT_DIAGNOSTIC_TIMEOUT
    process = None
    scratch = tempfile.mkdtemp(prefix="qfli-format-preview-", dir=os.environ["RUNNER_TEMP"])
    try:
        stdout = Path(scratch) / "stdout.log"
        with stdout.open("wb", buffering=0) as output:
            process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                       stdout=output, stderr=subprocess.DEVNULL)
            while True:
                if time.monotonic() >= deadline:
                    raise subprocess.TimeoutExpired(command, FORMAT_DIAGNOSTIC_TIMEOUT)
                require(stdout.stat().st_size <= MAX_FORMAT_DIAGNOSTIC_OUTPUT_BYTES,
                        "Formatter preview output exceeds or fails to finish its bound")
                returncode = process.poll()
                if returncode is not None:
                    break
                time.sleep(0.05)
        require(returncode == 0, "Formatter preview command failed")
        data = bytearray()
        try:
            size = stdout.stat().st_size
            with stdout.open("rb") as captured:
                while True:
                    if time.monotonic() >= deadline:
                        raise subprocess.TimeoutExpired(command, FORMAT_DIAGNOSTIC_TIMEOUT)
                    chunk = captured.read(min(8192, MAX_FORMAT_DIAGNOSTIC_OUTPUT_BYTES + 1 - len(data)))
                    if not chunk:
                        break
                    data.extend(chunk)
                    require(len(data) <= MAX_FORMAT_DIAGNOSTIC_OUTPUT_BYTES,
                            "Formatter preview output exceeds or fails to finish its bound")
            require(len(data) == size == stdout.stat().st_size,
                    "Formatter preview output changed while reading")
        except (OSError, ValueError) as error:
            raise RuntimeError("Formatter preview output could not be read") from error
        return bytes(data).decode("utf-8", errors="replace")
    finally:
        # Cleanup must not replace a timeout, failed exit or failed read.
        if process is not None:
            try:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
            except (OSError, ValueError, subprocess.TimeoutExpired):
                pass
        shutil.rmtree(scratch, ignore_errors=True)


def format_diff(name, before, after):
    """Diff redacted snapshots of one approved file, keeping every hunk line."""
    old = before["text"].replace("\r\n", "\n")
    new = after.replace("\r\n", "\n")
    if not old.endswith("\n"):
        old += "\n"
    if not new.endswith("\n"):
        new += "\n"
    lines = list(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
                                      fromfile="a/" + name, tofile="formatted/" + name, n=3))
    return "".join(lines)


def format_failure_diagnostic(args, command, failure):
    """Collect bounded redacted formatter diffs without changing source files."""
    root = Path(args.root).resolve()
    rows = ["Dart format failed; bounded previews for approved root test files:",
            "Original failure: " + redact(str(failure))[:2000]]
    executable = str(command[0])
    try:
        names = format_diagnostic_paths(root)
    except RuntimeError as error:
        return bounded_diagnostic("\n".join(rows + ["Previews refused: " + str(error)]) + "\n",
                                  MAX_FORMAT_DIAGNOSTIC_BYTES)
    if not names:
        rows.append("No approved root test file exists for a preview.")
    for name in names:
        before = _format_source_snapshot(root, name)
        if before.get("state") != "text":
            rows.append(f"{name}: preview omitted ({before.get('state', 'unknown')})")
            continue
        try:
            stdout = run_format_preview(format_preview_command(executable, name),
                                        cwd=root, env=command_environment())
        except subprocess.TimeoutExpired:
            rows.append(f"{name}: preview timed out")
            continue
        except Exception:
            # Never publish an exception value: a reader may echo source text.
            rows.append(f"{name}: preview unavailable")
            continue
        # Redact the formatted text before diffing. A formatter can move or
        # duplicate a sensitive value the input snapshot alone would not hide.
        diff = format_diff(name, before, safe_diff_text(stdout))
        if diff:
            rows.append(f"\nSafe formatter diff for {name}:\n{diff}")
        else:
            rows.append(f"{name}: no textual delta after redaction")
    return bounded_diagnostic("\n".join(rows) + "\n", MAX_FORMAT_DIAGNOSTIC_BYTES)


def write_format_failure_diagnostic(args, command, failure):
    """Persist and print only the bounded formatter diagnostic.

    The diagnostic is best effort. The caller keeps the original strict format
    failure, so a diagnostic fault can never turn a failure into a pass.
    """
    report = args.output / "reports/format-diagnostic.txt"
    try:
        diagnostic = format_failure_diagnostic(args, command, failure)
    except Exception:
        # Never publish exception values: a reader may include source content.
        diagnostic = "Dart formatter diagnostic unavailable; original failure retained.\n"
    try:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(diagnostic, encoding="utf-8", newline="\n")
    except OSError:
        pass
    for emit in (print_untrusted, lambda text: annotate(
            "error", text, heading="Dart format failed; see " + report.name)):
        try:
            emit(diagnostic)
        except Exception:
            pass
    return report


def framework_exception_text(message, limit):
    # Scrub complete blocks before slicing: secret markers can span print events.
    text = redact(message)
    text = re.sub(r"(?s)-----BEGIN [^-]*PRIVATE KEY-----.*\Z", "[incomplete private key redacted]", text)
    text = re.sub(r"(?im)^.*(?:vmserviceuri|vm service|observatory).*$", "[service detail omitted]", text)
    text = re.sub(r"\b(?:https?|wss?)://[^\s<>\"']+", "[URI omitted]", text, flags=re.IGNORECASE)
    return bounded_diagnostic(text, limit)


def public_framework_exceptions(records):
    """Revalidate the derived field instead of trusting arbitrary summary data."""
    result = []
    remaining = MAX_FRAMEWORK_EXCEPTION_BYTES
    if not isinstance(records, list):
        return result
    for record in records[:MAX_MACHINE_SUMMARY_ERRORS]:
        if not isinstance(record, dict) or remaining <= 0:
            continue
        identifier, text = str(record.get("testId", "")), record.get("text")
        if not re.fullmatch(r"[0-9]+", identifier) or not isinstance(text, str) \
                or FRAMEWORK_EXCEPTION_HEADER not in text:
            continue
        text = framework_exception_text(text, min(remaining, MAX_FRAMEWORK_EXCEPTION_RECORD_BYTES))
        result.append({"testId": identifier, "text": text})
        remaining -= len(text.encode("utf-8"))
    return result


def machine_summary_public(summary):
    """Select the bounded, redacted fields that may leave the runner."""
    def names(values):
        return [redact(str(value))[:200] for value in list(values or [])[:MAX_MACHINE_SUMMARY_ERRORS]]

    return {"success": summary.get("success") is True,
            "scope": "full_root_test_directory",
            "passed": summary.get("passed", 0), "skipped": summary.get("skipped", 0),
            "failed": summary.get("failed", 0), "completed": summary.get("completed", 0),
            "protocolDone": summary.get("protocolDone") is True,
            "suiteFiles": names(summary.get("suiteFiles")),
            "missingSuiteFiles": names(summary.get("missingSuiteFiles")),
            "unfinishedTestIds": names(summary.get("unfinishedTestIds")),
            "errors": [redact(str(value))[:2000] for value in
                       list(summary.get("errors") or [])[:MAX_MACHINE_SUMMARY_ERRORS]],
            "frameworkExceptions": public_framework_exceptions(summary.get("frameworkExceptions", [])),
            "rawReportPublished": False}


def publish_machine_summary(summary):
    """Print bounded redacted counts and errors; never raw protocol or a pass.

    The public job log already needs a login. `print_untrusted` keeps the text
    from becoming workflow commands, and only these derived fields are printed.
    """
    require(isinstance(summary, dict), "Root test summary is not a record")
    public = machine_summary_public(summary)
    text = bounded_diagnostic(json.dumps(public, indent=2, sort_keys=True) + "\n",
                              MAX_MACHINE_SUMMARY_BYTES)
    print_untrusted("Root test summary:\n" + text)
    return text


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


def quality_runtime_inputs(args):
    return {path: app.git_value(args.root, "rev-parse", f"HEAD:{path}") for path in app.RUNTIME_INPUTS}


def resolve_quality_assets(args, manifest):
    """Select real producer archives for packaged-asset tests, never execution."""
    require_hosted_runner()
    bootstrap = verify_bootstrap(args)
    require(not manifest.get("prepared"), "Cannot replace prepared quality asset inputs")
    repository = bootstrap["source"]["repository"]
    expected = quality_runtime_inputs(args)
    explicit = getattr(args, "run_id", None) or os.environ.get("RUNTIME_RUN_ID", "")
    if explicit:
        require(re.fullmatch(r"[1-9][0-9]*", str(explicit)), "Asset runtime run ID must be positive")
        candidates = [app.api_json(f"/repos/{repository}/actions/runs/{explicit}")]
    else:
        candidates = app.api_json(
            f"/repos/{repository}/actions/workflows/native-runtime.yml/runs?branch=main&status=success&per_page=30"
        ).get("workflow_runs", [])
    failures = []
    for candidate in candidates:
        try:
            selection = app.validate_runtime_run(candidate, repository, expected, QUALITY_ASSET_TARGETS)
        except RuntimeError as error:
            failures.append({"runId": candidate.get("id"), "reason": redact(str(error))[:2000]})
            if explicit:
                write_json(args.output / "reports/native-assets-rejections.json", failures)
                raise
            continue
        manifest["nativeAssetInputs"] = {
            **selection, "qualitySource": copy.deepcopy(bootstrap["source"]),
            "targets": list(QUALITY_ASSET_TARGETS), "status": "selected_not_installed",
            "scope": "packaged_asset_bytes_only", "nativeRuntimeExecuted": False,
            "deviceExecuted": False,
        }
        write_json(args.output / "reports/native-assets-selection.json", manifest["nativeAssetInputs"])
        app.output_value("run_id", selection["runId"])
        app.output_value("artifact_ids", ",".join(str(row["id"]) for row in selection["artifacts"]))
        return
    write_json(args.output / "reports/native-assets-rejections.json", failures)
    raise RuntimeError("No unexpired exact-input OHOS asset archives for both root-test targets")


def validate_quality_asset_selection(args, selection, bootstrap):
    require(isinstance(selection, dict) and selection.get("qualitySource") == bootstrap["source"],
            "Quality asset selection belongs to another source or run")
    require(selection.get("targets") == list(QUALITY_ASSET_TARGETS)
            and selection.get("inputCompatibility") == {
                "method": "exact_git_objects", "objects": quality_runtime_inputs(args)},
            "Quality asset producer inputs or targets differ")
    require(selection.get("scope") == "packaged_asset_bytes_only"
            and selection.get("nativeRuntimeExecuted") is False
            and selection.get("deviceExecuted") is False,
            "Quality assets cannot claim native or device execution")
    require(re.fullmatch(r"[1-9][0-9]*", str(selection.get("runId", "")))
            and re.fullmatch(r"[1-9][0-9]*", str(selection.get("runAttempt", "")))
            and re.fullmatch(r"[0-9a-f]{40}", str(selection.get("sourceCommit", ""))),
            "Quality asset producer identity is incomplete")
    artifacts = selection.get("artifacts", [])
    require(isinstance(artifacts, list) and len(artifacts) == len(QUALITY_ASSET_TARGETS)
            and all(isinstance(row, dict) and type(row.get("id")) is int and row["id"] > 0
                    for row in artifacts)
            and len({row["id"] for row in artifacts}) == len(artifacts)
            and {row.get("name") for row in artifacts} == {
                "native-runtime-" + key for key in QUALITY_ASSET_TARGETS},
            "Both selected OHOS artifact identities are required")


def quality_asset_snapshot(root):
    """Hash only the flat verified asset directory; never publish payload bytes."""
    root = Path(root).resolve()
    assets = root / "assets/miri"
    require(assets.is_dir() and not linked(assets) and assets.resolve() == assets,
            "Quality native asset directory is missing or linked")
    rows = []
    total = 0
    for path in sorted(assets.iterdir()):
        require(path.is_file() and not linked(path) and path.resolve() == path,
                "Quality native assets must be regular flat files")
        if path.name == ".gitkeep":
            continue
        require(re.fullmatch(r"(?:manifest(?:\.ohos-(?:arm64|x64))?\.json|[0-9a-f]{64}\.bin)", path.name),
                "Unexpected quality native asset name")
        size = path.stat().st_size
        total += size
        require(len(rows) < app.MAX_RUNTIME_MEMBERS and total <= app.MAX_RUNTIME_BYTES,
                "Quality native assets exceed their inventory or byte bound")
        rows.append({"path": path.name, "size": size, "sha256": sha256(path)})
    names = {row["path"] for row in rows}
    require({"manifest.json", *(f"manifest.{key}.json" for key in QUALITY_ASSET_TARGETS)}.issubset(names),
            "Quality native assets lack both manifests or the ARM64 alias")
    return rows


def install_quality_assets(args, manifest):
    """Verify both complete archives, then copy only assets into the checkout."""
    require_hosted_runner()
    bootstrap = verify_bootstrap(args)
    require(not manifest.get("prepared"), "Cannot replace prepared quality asset inputs")
    selection = manifest.get("nativeAssetInputs")
    validate_quality_asset_selection(args, selection, bootstrap)
    require(selection.get("status") == "selected_not_installed"
            and str(getattr(args, "run_id", "")) == selection["runId"],
            "Quality asset selection/run ID is absent or already consumed")
    require(getattr(args, "source", None), "Quality asset download path is required")
    source = Path(args.source).absolute()
    temporary_root = Path(os.environ["RUNNER_TEMP"]).resolve()
    require(source.is_dir() and source.resolve() == source and not linked(source)
            and source.is_relative_to(temporary_root) and source != temporary_root,
            "Quality asset downloads must stay below RUNNER_TEMP without links")
    require(all(not linked(path) for path in source.rglob("*")), "Linked quality archive input")
    selection["status"] = "installation_incomplete"
    packages = []
    with tempfile.TemporaryDirectory(prefix="qfli-quality-assets-", dir=temporary_root) as scratch:
        scratch = Path(scratch)
        combined = scratch / "combined"
        for key in QUALITY_ASSET_TARGETS:
            matches = list(source.rglob(f"native-runtime-{key}.tar.gz"))
            require(len(matches) == 1, "Expected one quality runtime archive for " + key)
            archive = matches[0]
            require(archive.is_file() and 0 < archive.stat().st_size <= app.MAX_RUNTIME_BYTES,
                    "Quality runtime archive exceeds download bound")
            sidecar = archive.with_suffix(archive.suffix + ".sha256")
            require(sidecar.is_file() and sidecar.stat().st_size <= 1024, "Invalid quality archive checksum file")
            fields = sidecar.read_text(encoding="ascii").split()
            require(len(fields) == 2 and fields[1] == archive.name
                    and re.fullmatch(r"[0-9a-f]{64}", fields[0]) and fields[0] == sha256(archive),
                    "Quality runtime archive checksum differs")
            extracted = scratch / key
            app.extract_runtime(archive, extracted)
            data = app.verify_runtime_payload(extracted, key, selection)
            app.merge_verified_tree(extracted / "assets/miri", combined / "assets/miri")
            packages.append({"target": key, "archiveSha256": fields[0], "manifestId": data["id"],
                             "manifestSha256": sha256(extracted / "assets/miri" / f"manifest.{key}.json"),
                             "rustVersion": data["rustVersion"], "rustCommit": data["rustCommit"]})
        # Do not expose one architecture when the other failed verification.
        rows = quality_asset_snapshot(combined)
        require(packages[0]["manifestId"] != packages[1]["manifestId"],
                "Quality OHOS architectures must have distinct runtime identities")
        destination = args.root / "assets/miri"
        require(destination.is_dir() and not linked(destination) and destination.resolve() == destination,
                "Quality asset destination must be an existing unlinked directory")
        app.merge_verified_tree(combined / "assets/miri", destination)
        require(quality_asset_snapshot(args.root) == rows, "Installed quality asset inventory differs")
    selection.update(status="verified_assets_only", packages=packages, files=rows,
                     totalBytes=sum(row["size"] for row in rows))
    try:
        write_json(args.output / "reports/native-assets.json", selection)
        verify_report_bounds(args)
    except BaseException:
        selection["status"] = "installation_incomplete"
        raise


def verify_quality_assets(args, manifest, bootstrap):
    selection = manifest.get("nativeAssetInputs")
    validate_quality_asset_selection(args, selection, bootstrap)
    require(selection.get("status") == "verified_assets_only"
            and read_json(args.output / "reports/native-assets.json") == selection,
            "Quality native asset installation is incomplete or its report changed")
    require(quality_asset_snapshot(args.root) == selection.get("files"),
            "Quality native assets changed after verification")


def prepare(args, manifest):
    bootstrap = verify_bootstrap(args)
    verify_quality_assets(args, manifest, bootstrap)
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
    verify_quality_assets(args, manifest, bootstrap)
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
    verify_quality_assets(args, manifest, bootstrap)
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
    exception_prints = {}
    active_exception_blocks = {}
    exception_bytes = 0
    active_exception_bytes = 0
    errored = set()
    started_processes = 0
    count = 0

    def finish_exception(test_id):
        nonlocal exception_bytes, active_exception_bytes
        block = active_exception_blocks.pop(test_id, None)
        if block is None:
            return
        active_exception_bytes -= block["bytes"]
        # Never sanitize a partially captured block: an omitted suffix could
        # close a credential marker. Overflow omits the entire diagnostic.
        remaining = MAX_FRAMEWORK_EXCEPTION_BYTES - exception_bytes - active_exception_bytes
        if block["overflow"] or remaining <= 0:
            return
        # Redaction can expand short lines. Reserve every other active block
        # before converting this completed raw block into stored public text.
        text = framework_exception_text("\n".join(block["parts"]), min(
            MAX_FRAMEWORK_EXCEPTION_RECORD_BYTES, remaining))
        exception_bytes += len(text.encode("utf-8"))
        exception_prints.setdefault(test_id, []).append(text)

    def capture_exception(test_id, message):
        nonlocal active_exception_bytes
        for line in message.splitlines():
            if FRAMEWORK_EXCEPTION_HEADER in line:
                finish_exception(test_id)
                active_exception_blocks[test_id] = {"parts": [], "bytes": 0, "overflow": False}
            block = active_exception_blocks.get(test_id)
            if block is None:
                continue
            size = len(line.encode("utf-8")) + 1
            if active_exception_bytes + exception_bytes + size > MAX_FRAMEWORK_EXCEPTION_BYTES:
                active_exception_bytes -= block["bytes"]
                block.update(parts=[], bytes=0, overflow=True)
            if not block["overflow"]:
                block["parts"].append(line)
                block["bytes"] += size
                active_exception_bytes += size
            if re.fullmatch(r"\s*[═─━=]{8,}\s*", line):
                finish_exception(test_id)

    with path.open(encoding="utf-8") as stream:
        for line in stream:
            count += 1
            require(count <= MAX_TEST_EVENTS and len(line) <= 1024**2, "Test protocol exceeds event bounds")
            if not line.strip():
                continue
            event = json.loads(line)
            if isinstance(event, list):
                # Flutter EventPrinter interleaves this singleton notification
                # with package:test's object events. It is not a test outcome.
                require(len(event) == 1 and isinstance(event[0], dict),
                        "Malformed Flutter test notification")
                notification = event[0]
                params = notification.get("params")
                require(set(notification) == {"event", "params"}
                        and notification["event"] == "test.startedProcess"
                        and isinstance(params, dict) and set(params) == {"vmServiceUri"}
                        and (params["vmServiceUri"] is None or isinstance(params["vmServiceUri"], str)),
                        "Malformed or unsupported Flutter test notification")
                started_processes += 1
                continue
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
                finish_exception(test_id)
                require(test_id in tests and test_id not in results
                        and event.get("result") in ("success", "failure", "error"),
                        "Duplicate or malformed test completion")
                results[test_id] = {"result": event["result"], "skipped": event.get("skipped") is True,
                                    "hidden": event.get("hidden") is True}
                if event["result"] == "success" and test_id not in errored:
                    exception_bytes -= sum(len(text.encode("utf-8"))
                                           for text in exception_prints.pop(test_id, []))
            elif kind == "done":
                done.append(event.get("success"))
            elif kind == "error":
                finish_exception(event.get("testID"))
                errored.add(event.get("testID"))
                if len(failures) < 30:
                    failures.append(redact(str(event.get("error", "test error")))[:2000])
            elif kind == "print":
                message = event.get("message")
                test_id = event.get("testID")
                if test_id in tests and test_id not in results and isinstance(message, str):
                    capture_exception(test_id, message)
    for test_id in list(active_exception_blocks):
        finish_exception(test_id)
    visible = {key: value for key, value in results.items() if not value["hidden"]}
    skipped = sum(row["skipped"] for row in visible.values())
    failed = len(errored | {key for key, row in results.items() if row["result"] in ("failure", "error")})
    unfinished = sorted(str(key) for key in set(tests) - set(results))
    missing = sorted(set(expected) - suites)
    failed_ids = errored | {key for key, row in results.items() if row["result"] in ("failure", "error")}
    summary = {"scope": "full_root_test_directory", "suiteFiles": sorted(suites), "missingSuiteFiles": missing,
               "completed": len(visible), "passed": sum(row["result"] == "success" and not row["skipped"]
                                                        for row in visible.values()),
               "skipped": skipped, "failed": failed, "unfinishedTestIds": unfinished, "protocolDone": done == [True],
               "skippedTestNames": [tests.get(key, str(key)) for key, row in visible.items() if row["skipped"]][:100],
               "errors": failures, "rawReportSha256": sha256(path), "rawReportBytes": path.stat().st_size,
               "frameworkExceptions": [{"testId": str(key), "text": text}
                                       for key, messages in exception_prints.items() if key in failed_ids
                                       for text in messages],
               "rawReportPublished": False, "flutterStartedProcesses": started_processes,
               "nativeRuntimeExecuted": False, "deviceExecuted": False}
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
                # Public logs otherwise hide every failure detail behind the
                # private protocol file. This stays bounded, redacted and does
                # not alter the strict summary or finalize gate.
                try:
                    publish_machine_summary(summary)
                except Exception:
                    pass
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
        # Best-effort formatter context; the strict format failure below is
        # recorded and re-raised unchanged even when the preview also fails.
        if stage == "format" and isinstance(error, Exception):
            try:
                verify_prepared(args, manifest)
                write_format_failure_diagnostic(args, command, error)
            except Exception:
                pass
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
    parser.add_argument("stage", choices=("resolve-assets", "install-assets", "prepare", *CHECKS, "finalize"))
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--bootstrap-dir", type=Path)
    parser.add_argument("--job-status", default="failure")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--run-id")
    options = parser.parse_args()
    require_hosted_runner()
    args = quality_args(output=options.output_dir, bootstrap=options.bootstrap_dir)
    args.source, args.run_id = options.source, options.run_id
    confined_output(args)
    args.output.mkdir(parents=True, exist_ok=True)
    path = args.output / "manifest.json"
    manifest = read_json(path) if path.exists() else new_manifest(args)
    if options.stage == "finalize":
        finalize(args, manifest, options.job_status)
        return
    try:
        if options.stage == "resolve-assets":
            resolve_quality_assets(args, manifest)
        elif options.stage == "install-assets":
            install_quality_assets(args, manifest)
        elif options.stage == "prepare":
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
