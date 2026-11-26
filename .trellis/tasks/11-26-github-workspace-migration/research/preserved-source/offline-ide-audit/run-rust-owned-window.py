"""Rust-only bounded coordinator requiring a fresh root-verified named grant.

The root must inspect the CURRENT channel immediately before launch and save the
exact incoming grant event. This program does not derive ownership from numeric
arguments or old queue prose, publish ACCEPT, or modify shipping source.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time
from urllib.parse import urljoin, urlsplit
from urllib.request import url2pathname
import uuid

from rust_owned_job import OwnedJob

MODULE_STARTED = time.monotonic()

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
CORE = REPO.parent / "qfli_studio_core"
SDK = Path("D:/ProgramFiles/flutter_ohos/bin/cache")
DART = SDK / "dart-sdk/bin/dart.exe"
FLUTTER = SDK / "flutter_tools.snapshot"
HELPER_HASH = "c0520616e6777d9587a6c0004487bd06a1b19b7d202563f8292c4c1a32c6b172"
FOCUSED_FILES = (
    "lib/rust_debugger.dart", "lib/rust_native_feature_audit.dart",
    "lib/main_catalog_audit.dart", "test/rust_debugger_test.dart",
    "test/rust_native_feature_audit_test.dart", "test/rust_workspace_integration_test.dart",
)


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def write_json(path: Path, value: object) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def head_identity(root: Path) -> dict:
    """Read the exact local HEAD without starting an unowned git process."""
    gitdir = root / ".git"
    if gitdir.is_file():
        pointer = gitdir.read_text(encoding="utf-8").strip()
        if not pointer.startswith("gitdir: "):
            raise RuntimeError(f"Invalid gitdir pointer: {root}")
        gitdir = (root / pointer[8:]).resolve()
    common = gitdir
    if (gitdir / "commondir").is_file():
        common = (gitdir / (gitdir / "commondir").read_text(encoding="utf-8").strip()).resolve()
    head = (gitdir / "HEAD").read_text(encoding="ascii").strip()
    revision = head
    if head.startswith("ref: "):
        reference = head[5:]
        revision = None
        for base in (gitdir, common):
            ref = base / reference
            if ref.is_file():
                revision = ref.read_text(encoding="ascii").strip()
                break
        if revision is None:
            for base in (gitdir, common):
                packed = base / "packed-refs"
                if packed.is_file():
                    for line in packed.read_text(encoding="ascii").splitlines():
                        if line and not line.startswith(("#", "^")):
                            value, name = line.split(" ", 1)
                            if name == reference:
                                revision = value
                                break
                if revision is not None:
                    break
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40,64}", revision):
        raise RuntimeError(f"Unresolved local HEAD: {root}")
    return {"head": head, "revision": revision}


def package_resolution() -> dict:
    path = REPO / ".dart_tool/package_config.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("configVersion") != 2 or not isinstance(config.get("packages"), list):
        raise RuntimeError("Unsupported effective Dart package configuration")
    roots = {}
    for name, expected in (("qfli_rust", REPO), ("qfli_studio_core", CORE),
                           ("re_editor", CORE / "vendor/re_editor")):
        matches = [entry for entry in config["packages"] if entry.get("name") == name]
        if len(matches) != 1 or not isinstance(matches[0].get("rootUri"), str):
            raise RuntimeError("Effective package root missing or duplicated: " + name)
        entry = matches[0]
        uri = urljoin(path.as_uri(), entry["rootUri"])
        parsed = urlsplit(uri)
        if parsed.scheme != "file" or parsed.netloc not in ("", "localhost") or parsed.query or parsed.fragment:
            raise RuntimeError("Effective package root must be a local file URI: " + name)
        actual = Path(url2pathname(parsed.path)).resolve()
        package_uri = entry.get("packageUri", "")
        package_path = urlsplit(urljoin(uri.rstrip("/") + "/", package_uri))
        if (actual != expected.resolve() or package_path.scheme != "file"
                or package_path.netloc not in ("", "localhost")
                or Path(url2pathname(package_path.path)).resolve() != (expected / "lib").resolve()):
            raise RuntimeError("Effective package import root differs from hashed source: " + name)
        roots[name] = {"root": str(actual), "packageUri": package_uri}
    return roots


def snapshot(mode: str, deadline: float) -> dict:
    resolved_packages = package_resolution()
    source_paths = [REPO / name for name in FOCUSED_FILES]
    source_paths.extend(REPO / name for name in ("pubspec.yaml", "pubspec.lock", "lib/main.dart",
                                               "analysis_options.yaml", ".dart_tool/package_config.json"))
    source_paths.extend(path for path in (REPO / "lib").rglob("*") if path.is_file())
    source_paths.extend(path for path in (REPO / "assets/content_rust").rglob("*.json") if path.is_file())
    source_paths.extend(HERE / name for name in (
        "run-reserved-validation.ps1", "run-rust-owned-window.py", "rust_owned_job.py",
        "publish-rust-release.ps1", "run-native-validation-current.sh", "native-group-supervisor.py",
        "rust_runner_controls.py",
    ) if (HERE / name).is_file())
    if mode == "Native":
        for name in ("native/miri_adapter", "native/patches", "native/fixtures"):
            source_paths.extend(path for path in (REPO / name).rglob("*") if path.is_file())
        source_paths.append(REPO / "scripts/build_miri_adapter.sh")
    files = {}
    for root, paths, prefix in (
        (REPO, source_paths, "rust"),
        (CORE, [CORE / "pubspec.yaml", CORE / "analysis_options.yaml", CORE / "vendor/re_editor/pubspec.yaml"]
         + [path for directory in (CORE / "lib", CORE / "assets", CORE / "vendor/re_editor/lib")
            for path in directory.rglob("*") if path.is_file()], "core"),
    ):
        for path in sorted(set(paths)):
            if time.monotonic() >= deadline:
                raise TimeoutError("Source identity snapshot exceeded its reserved budget")
            key = prefix + "/" + path.relative_to(root).as_posix()
            files[key] = {"size": path.stat().st_size, "sha256": digest(path)}
    return {"files": files, "rust": head_identity(REPO), "core": head_identity(CORE),
            "resolvedPackages": resolved_packages}


def changes(before: dict | None, after: dict | None) -> list[str]:
    if before is None or after is None:
        return ["source snapshot incomplete"]
    result = [key for key in sorted(set(before["files"]) | set(after["files"]))
              if before["files"].get(key) != after["files"].get(key)]
    for root in ("rust", "core"):
        if before[root] != after[root]:
            result.append(root + "/HEAD")
    if before["resolvedPackages"] != after["resolvedPackages"]:
        result.append("effective package import roots")
    return result


def run_owned(name: str, command: list[str], cwd: Path, log: Path,
              work_deadline: float, cleanup_deadline: float) -> dict:
    """Run one exact owned root, then query membership before observing time.

    A root first observed terminal after its work deadline does not become a
    passing natural drain. Cleanup and reporting retain their own absolute end;
    neither observation nor report I/O starts another clock.
    """
    started = time.monotonic()
    work_deadline = min(work_deadline, cleanup_deadline)
    job = None
    error = None
    timed_out = False
    orphan_cleanup = False
    empty = False
    record = {}
    code = 1
    last_observed = started
    work_observed = started
    cleanup_observed = started
    cleanup_deadline_exceeded = False
    not_started = False

    def observe() -> bool:
        nonlocal last_observed
        value = job.empty()
        # The query can itself cross a deadline. Its completion time is the
        # evidence time; a preceding time check is not an observation bound.
        last_observed = time.monotonic()
        return value

    try:
        with log.open("wb") as output:
            if time.monotonic() >= work_deadline:
                not_started = True
                empty = True  # No Job or process was created by this call.
                timed_out = True
                code = 124
            else:
                job = OwnedJob()
                job.start(command, cwd, dict(os.environ), output, output)
                print("START", name, json.dumps(job.record, separators=(",", ":")), flush=True)
                while True:
                    empty = observe()
                    work_observed = last_observed
                    if last_observed > work_deadline:
                        timed_out = True
                        break
                    if empty or job.record.get("terminal"):
                        break
                    time.sleep(min(0.025, max(0.0, work_deadline - last_observed)))
                if not job.record.get("terminal"):
                    timed_out = True
                elif job.record.get("jobActiveProcesses"):
                    grace = min(work_deadline, last_observed + 0.4)
                    while True:
                        empty = observe()
                        work_observed = last_observed
                        if last_observed > work_deadline:
                            timed_out = True
                        if empty or last_observed >= grace:
                            break
                        time.sleep(min(0.025, max(0.0, grace - last_observed)))
                    if not empty:
                        orphan_cleanup = True
                if not empty and (timed_out or orphan_cleanup):
                    job.stop()
                code = 124 if timed_out else job.record.get("exitCode", 1)
    except BaseException as failure:
        error = repr(failure)
    finally:
        if job is not None:
            try:
                empty = observe()
                if not empty:
                    job.stop()
                while True:
                    empty = observe()
                    cleanup_observed = last_observed
                    if empty or last_observed >= cleanup_deadline:
                        break
                    time.sleep(min(0.025, max(0.0, cleanup_deadline - last_observed)))
                record = dict(job.record)
                cleanup_deadline_exceeded = cleanup_observed > cleanup_deadline
            except BaseException as failure:
                record = dict(job.record)
                error = error or repr(failure)
                empty = False
            finally:
                # Kill-on-close is an owned termination request only. The
                # preceding exact empty observation remains the release proof.
                job.close()
                cleanup_deadline_exceeded |= time.monotonic() > cleanup_deadline
        elif not_started or not record:
            empty = True  # No start call was reached without an owned Job.
    if error or orphan_cleanup:
        code = code or 1
    if cleanup_deadline_exceeded:
        code = code or 124
    if not empty:
        code = 125
    result = {"name": name, "command": command, "cwd": str(cwd), "process": record,
              "exit": code, "timeout": timed_out, "orphanCleanup": orphan_cleanup,
              "emptyJob": empty, "error": error, "notStarted": not_started, "log": str(log),
              "workBudgetSeconds": max(0.0, work_deadline - started),
              "cleanupBudgetSeconds": max(0.0, cleanup_deadline - started),
              "workObservedElapsedSeconds": work_observed - started,
              "cleanupObservedElapsedSeconds": cleanup_observed - started,
              "cleanupDeadlineExceeded": cleanup_deadline_exceeded}
    print("TERMINAL", json.dumps(result, separators=(",", ":")), flush=True)
    # The returned/persisted result includes serialization and stdout I/O. A
    # delayed terminal print cannot turn an over-budget phase into a pass.
    reported_at = time.monotonic()
    result["elapsedSeconds"] = reported_at - started
    result["reportDeadlineExceeded"] = reported_at > cleanup_deadline
    result["deadlineExceeded"] = (timed_out or cleanup_deadline_exceeded
                                  or result["reportDeadlineExceeded"])
    if result["deadlineExceeded"]:
        result["exit"] = result["exit"] or 124
    return result



def finalize_control_reports(controls_module, report: dict, run: Path,
                             report_path: Path, started: float,
                             absolute_deadline: float, slice_deadline: float) -> None:
    """Account for both report writes before permitting any validation Job.

    Persist the first finalized state, then finalize again so those writes also
    consume the same slice. A failure may need another diagnostic write, but can
    never regain permission to start validation. Cleanup proof is independent.
    """
    controls = report["controls"]
    module_deadline = controls.get("controlDeadlineMonotonic")
    if isinstance(module_deadline, (int, float)):
        slice_deadline = min(slice_deadline, module_deadline)
    write_started = time.monotonic()
    timing_flags = {key: bool(controls.get(key)) for key in (
        "timingExceeded", "sliceExceeded", "deadlineExceeded")}
    stop_subsequent = controls.get("stopSubsequent") is not False
    for _ in range(2):
        write_json(run / "controls.json", controls)
        write_json(report_path, report)
        controls_module.finalize_controls(
            controls, absolute_deadline,
            report_write_seconds=time.monotonic() - write_started)
        # An earlier violation must survive a module's later timing sample.
        for key in timing_flags:
            timing_flags[key] = bool(timing_flags[key] or controls.get(key))
            controls[key] = timing_flags[key]
        stop_subsequent |= controls.get("stopSubsequent") is not False
        if stop_subsequent or any(timing_flags.values()):
            controls.update(passed=False, stopSubsequent=True)
    # Keep the caller's unrounded observation authoritative even if a module
    # rounds elapsed time or measures its own start after the caller's start.
    observed = time.monotonic()
    slice_exceeded = observed > slice_deadline
    deadline_exceeded = observed > absolute_deadline
    timing_exceeded = bool(slice_exceeded or deadline_exceeded
                           or controls.get("timingExceeded")
                           or controls.get("sliceExceeded")
                           or controls.get("deadlineExceeded"))
    controls["sliceExceeded"] = bool(slice_exceeded or controls.get("sliceExceeded"))
    controls["deadlineExceeded"] = bool(deadline_exceeded or controls.get("deadlineExceeded"))
    controls["timingExceeded"] = timing_exceeded
    report["controlsElapsedSeconds"] = observed - started
    report["controlsOwnedJobsEmpty"] = controls.get("allOwnedJobsEmpty") is True
    if (controls.get("passed") is not True
            or controls.get("stopSubsequent") is not False
            or controls.get("controlsComplete") is not True
            or not report["controlsOwnedJobsEmpty"] or timing_exceeded):
        controls.update(passed=False, stopSubsequent=True)
        if timing_exceeded:
            controls.setdefault("problems", []).append(
                "caller observed a control timing violation after both report writes")
        write_json(run / "controls.json", controls)
        write_json(report_path, report)
        raise RuntimeError("Owned controls failed or cleanup/deadline is unconfirmed; validation not started")


def linux_path(path: Path) -> str:
    value = path.resolve().as_posix()
    if not re.match(r"^[A-Za-z]:/", value):
        raise RuntimeError("Native run path must use the explicit Windows drive mount")
    return "/mnt/" + value[0].lower() + "/" + value[3:]


def native_evidence(run: Path, run_id: str) -> tuple[dict, bool]:
    path = run / "native/run.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    if (value.get("schemaVersion") != 1 or value.get("runId") != run_id
            or value.get("runDir") != linux_path(run / "native")
            or value.get("reportPath") != linux_path(path)
            or not isinstance(value.get("supervisorPid"), int)):
        raise RuntimeError("Native report does not bind the exact launched run")
    empty = value.get("groupEmpty") is True and value.get("ownedProcessesRemaining") == []
    return value, empty


def grant_event(args: argparse.Namespace) -> dict:
    if not args.root_verified_grant or args.grant_seq <= 533:
        raise ValueError("A NEW root-verified explicit named handoff after readiness533 is required")
    event = json.loads(args.grant_evidence_file.read_text(encoding="utf-8-sig"))
    if (event.get("kind") != "message" or event.get("seq") != args.grant_seq
            or not isinstance(event.get("by"), str) or event["by"] == "rust-offline-1022"
            or not isinstance(event.get("text"), str) or "rust" not in event["text"].lower()):
        raise ValueError("Grant evidence must be the exact incoming NEW Rust named channel event")
    if not re.fullmatch(r"[a-z][a-z0-9_-]*", args.next_owner):
        raise ValueError("Next owner must be one explicit stable channel handle")
    return event


def current_process_identity() -> dict:
    """Capture this coordinator's own exact process identity, never a PID scan."""
    import ctypes as C
    from ctypes import wintypes as W
    kernel = C.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.argtypes = []
    kernel.GetCurrentProcess.restype = W.HANDLE
    kernel.GetProcessTimes.argtypes = [W.HANDLE] + [C.POINTER(W.FILETIME)] * 4
    kernel.GetProcessTimes.restype = W.BOOL
    stamps = [W.FILETIME() for _ in range(4)]
    if not kernel.GetProcessTimes(kernel.GetCurrentProcess(), *(C.byref(s) for s in stamps)):
        raise C.WinError(C.get_last_error())
    return {"pid": os.getpid(), "creationFiletime100ns": str(
        (stamps[0].dwHighDateTime << 32) | stamps[0].dwLowDateTime)}


def main() -> int:
    # Argument checks, source hashing, controls, validation and publication all
    # consume this one process clock. Root separately retains the outer exec
    # handle and must account for launcher/finalization time before final release.
    started = MODULE_STARTED
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("Native", "Dart"), required=True)
    parser.add_argument("--grant-seq", type=int, required=True)
    parser.add_argument("--grant-evidence-file", type=Path, required=True)
    parser.add_argument("--root-verified-grant", action="store_true", required=True)
    parser.add_argument("--next-owner", required=True)
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("This coordinator requires Windows private Job Objects")
    event = grant_event(args)
    if digest(HERE / "rust_owned_job.py") != HELPER_HASH:
        raise RuntimeError("Frozen owned Job helper identity changed; review before reuse")
    seconds = 90 if args.mode == "Native" else 110
    deadline = started + seconds
    work_deadline = deadline - 13
    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + uuid.uuid4().hex
    run = HERE / "runs" / (args.mode.lower() + "-" + run_id)
    run.mkdir(parents=True, exist_ok=False)
    report_path = run / "run.json"
    write_json(run / "grant-event.json", event)
    # Neither a PID guess nor a successful pending publication reclaims this
    # marker. Only root can finalize after its exact outer handle is terminal.
    active = HERE / "active-owned-window"
    active.mkdir(exist_ok=False)
    consumed = HERE / "consumed-grants" / str(args.grant_seq)
    try:
        consumed.mkdir(parents=True, exist_ok=False)
    except BaseException:
        active.rmdir()  # This invocation just created it; it is still empty.
        raise
    coordinator_process = current_process_identity()
    ownership = {"runId": run_id, "coordinatorPid": os.getpid(), "grantSeq": args.grant_seq,
                 "coordinatorProcess": coordinator_process, "reportPath": str(report_path),
                 "nextOwner": args.next_owner}
    write_json(active / "owner.json", ownership)
    write_json(consumed / "owner.json", ownership)
    report = {"schemaVersion": 1, "runId": run_id, "mode": args.mode,
              "grantSeq": args.grant_seq, "grantEventSha256": digest(run / "grant-event.json"),
              "grantVerifiedByRoot": True, "nextOwner": args.next_owner,
              "coordinatorPid": os.getpid(), "coordinatorProcess": coordinator_process,
              "ownerIdentity": ownership, "budgetSeconds": seconds, "status": "starting",
              "results": [], "phaseBudgets": [], "controlsStarted": False,
              "controlsOwnedJobsEmpty": True,
              "validationOwnedJobsEmpty": True, "nativeGroupEmpty": True,
              "allOwnedJobsEmpty": False, "passed": False, "released": False,
              "readyForRootRelease": False, "rootFinalizationRequired": True,
              "parentTerminalObserved": False, "exit": 1, "reportPath": str(report_path),
              "activeMarkerCleared": False,
              "finalizationInstructions": [
                  "Retain and observe the exact outer exec handle terminal before final release.",
                  "Read this exact report and require readyForRootRelease and allOwnedJobsEmpty.",
                  "Verify runId, grantSeq, reportPath and coordinatorProcess against ownerIdentity.",
                  "Publish actual final RELEASE to nextOwner only after the outer handle is terminal.",
                  "Record final channel event and actual whole-window elapsed; an overrun is not a bounded pass.",
                  "Compare active-owned-window/owner.json to ownerIdentity before removing that exact marker.",
                  "Never remove consumed-grants/<grantSeq>/owner.json or replay the grant.",
              ]}
    before = after = None
    exit_code = 1
    native_empty = True  # Becomes unknown only when a WSL child may have run.
    write_json(report_path, report)
    try:
        before = snapshot(args.mode, min(work_deadline, started + 6))
        write_json(run / "source-before.json", before)
        import rust_runner_controls as controls_module
        control_started = time.monotonic()
        control_limit = min(work_deadline, control_started + 10.0)
        report["controlsSha256"] = digest(HERE / "rust_runner_controls.py")
        report["controlDeadlineSecondsFromStart"] = control_limit - started
        # The module uses its own <=10s slice AND the caller's existing work
        # deadline; no fresh grant, added window or second mode is created.
        report["controlsStarted"] = True
        report["controlsOwnedJobsEmpty"] = False  # Unknown until the harness returns exact proof.
        controls = controls_module.run_controls(sys.modules[__name__], run, work_deadline)
        report["controls"] = controls
        report["controlsOwnedJobsEmpty"] = controls.get("allOwnedJobsEmpty") is True
        finalize_control_reports(controls_module, report, run, report_path,
                                 control_started, work_deadline, control_limit)
        if args.mode == "Native":
            wsl = shutil.which("wsl.exe")
            if not wsl:
                raise FileNotFoundError("Explicit WSL endpoint executable unavailable")
            native_seconds = min(76, int(work_deadline - time.monotonic()) - 2)
            if native_seconds < 20:
                raise TimeoutError("Native work and cleanup budget unavailable after controls")
            report["nativeBudgetSecondsIncludingCleanup"] = native_seconds
            report["nativeCleanupReserveSeconds"] = 15
            command = [wsl, "-d", "qfli-java-build", "--", "sh",
                       linux_path(HERE / "run-native-validation-current.sh"),
                       "--max-seconds", str(native_seconds), "--cleanup-seconds", "15",
                       "--run-dir", linux_path(run / "native"), "--run-id", run_id]
            steps = [("native build and actual ABI suites", command, native_seconds + 2)]
        else:
            if not DART.is_file() or not FLUTTER.is_file():
                raise FileNotFoundError("Pinned absolute Dart/Flutter SDK endpoint unavailable")
            steps = [
                ("formatter check only", [str(DART), "format", "--output=none",
                 "--set-exit-if-changed", *FOCUSED_FILES], 8),
                ("scoped analysis", [str(DART), "analyze", *FOCUSED_FILES], 30),
                ("focused serial debugger feature workspace regressions",
                 [str(DART), "--disable-dart-dev", str(FLUTTER), "test", "--no-pub",
                  "--concurrency=1", "--reporter=expanded", "--timeout=30s",
                  *FOCUSED_FILES[3:]], 62),
            ]
        exit_code = 0
        for index, (name, command, limit) in enumerate(steps):
            phase_started = time.monotonic()
            if phase_started >= work_deadline:
                exit_code = exit_code or 124
                break
            phase_deadline = min(work_deadline, phase_started + limit)
            report["phaseBudgets"].append({"name": name, "capSeconds": limit,
                "allowedWorkSeconds": phase_deadline - phase_started,
                "workDeadlineSecondsFromStart": phase_deadline - started,
                "cleanupDeadlineSecondsFromStart": deadline - 9 - started})
            result = run_owned(name, command, REPO, run / f"{index + 1:02d}.log",
                               phase_deadline, deadline - 9)
            report["results"].append(result)
            report["validationOwnedJobsEmpty"] &= result["emptyJob"]
            if args.mode == "Native" and result["process"].get("pid"):
                native_empty = False
            write_json(report_path, report)
            exit_code = exit_code or result["exit"]
            if not result["emptyJob"]:
                break
        if args.mode == "Native" and not native_empty:
            native, native_empty = native_evidence(run, run_id)
            report["native"] = native
            exit_code = exit_code or native.get("exitCode", 1)
            if native.get("sourceDrift"):
                exit_code = exit_code or 1
        after = snapshot(args.mode, deadline - 7)
        write_json(run / "source-after.json", after)
    except BaseException as failure:
        report["error"] = repr(failure)
        exit_code = exit_code or 1
    finally:
        report["sourceDrift"] = changes(before, after)
        if report["sourceDrift"]:
            exit_code = exit_code or 1
        safe = (report["controlsOwnedJobsEmpty"]
                and report["validationOwnedJobsEmpty"] and native_empty)
        report["nativeGroupEmpty"] = native_empty
        report["exit"] = exit_code if safe else 125
        report["status"] = "awaiting_parent_terminal" if safe else "hold_cleanup_unconfirmed"
        report["validationPassed"] = safe and exit_code == 0 and not report["sourceDrift"]
        report["validationElapsedSeconds"] = time.monotonic() - started
        write_json(report_path, report)
        if safe:
            message = (f"Rust RELEASE_PENDING_PARENT_TERMINAL / NO_SUCCESSOR_GRANT; "
                       f"grant={args.grant_seq}; mode={args.mode}; run={run_id}; "
                       f"coordinator={json.dumps(coordinator_process, separators=(',', ':'))}; "
                       f"validationExit={report['exit']}; validationJobsActive0=true; "
                       f"nativeGroupEmpty={native_empty}; plannedSuccessor={args.next_owner}; "
                       f"report={report_path}. Root must observe the exact outer exec handle "
                       "terminal, verify publisher/owned Job empty and publish final RELEASE. "
                       "This pending notice authorizes no successor execution.")
        else:
            message = (f"Rust HOLD / NO_SUCCESSOR_GRANT; grant={args.grant_seq}; "
                       f"mode={args.mode}; run={run_id}; exact owned cleanup unconfirmed; "
                       f"coordinator={json.dumps(coordinator_process, separators=(',', ':'))}; "
                       f"report={report_path}. Root must retain the exact process identities; "
                       "no onward release is authorized.")
        release = run / "release-pending.txt"
        release.write_text(message, encoding="utf-8")
        publication = {"delivered": False, "emptyJob": True, "notStarted": True}
        # An uncertain owned cleanup forbids any further Job, including a
        # publisher. Root receives the retained HOLD report through the outer
        # handle and can publish the exact state after terminal observation.
        if safe and time.monotonic() < deadline - 4:
            pwsh = shutil.which("pwsh.exe") or shutil.which("pwsh")
            if pwsh:
                result = run_owned("publish pending parent terminal" if safe else "publish HOLD",
                    [pwsh, "-NoProfile", "-File", str(HERE / "publish-rust-release.ps1"),
                     "-TextFile", str(release), "-NextOwner", args.next_owner],
                    REPO, run / "publication.log", deadline - 2, deadline)
                publication = {"delivered": False, "emptyJob": result["emptyJob"], "result": result}
                if result["exit"] == 0 and result["emptyJob"]:
                    for line in (run / "publication.log").read_text(encoding="utf-8-sig", errors="replace").splitlines():
                        try:
                            published = json.loads(line)
                        except ValueError:
                            continue
                        if (published.get("kind") == "message" and published.get("by") == "rust-offline-1022"
                                and published.get("text") == message and isinstance(published.get("seq"), int)):
                            publication.update(delivered=True, channelSeq=published["seq"])
                            break
        report["publication"] = publication
        report["allOwnedJobsEmpty"] = safe and publication["emptyJob"]
        report["readyForRootRelease"] = (report["allOwnedJobsEmpty"]
                                          and publication["delivered"])
        report["released"] = False
        report["passed"] = False  # Overall completion awaits root's terminal observation.
        report["elapsedSeconds"] = time.monotonic() - started
        report["totalDeadlineExceeded"] = report["elapsedSeconds"] > seconds
        report["boundedValidationPassed"] = (report["validationPassed"]
            and not report["totalDeadlineExceeded"] and publication["delivered"]
            and publication["emptyJob"])
        if not publication["emptyJob"]:
            report["exit"] = 125
        elif not publication["delivered"]:
            report["exit"] = report["exit"] or 1
        if report["totalDeadlineExceeded"]:
            report["exit"] = report["exit"] or 124
        # The active marker deliberately survives every outcome. A pending
        # channel event while this process is live is never a final release.
        write_json(report_path, report)
        print("RUST_REPORT", report_path, flush=True)
        print(json.dumps(report, separators=(",", ":")), flush=True)
        observed_after_report = time.monotonic()
        if observed_after_report > deadline:
            report.update(totalDeadlineExceeded=True, boundedValidationPassed=False,
                          elapsedSeconds=observed_after_report - started)
            report["exit"] = report["exit"] or 124
            write_json(report_path, report)
    return report["exit"]


if __name__ == "__main__":
    raise SystemExit(main())
