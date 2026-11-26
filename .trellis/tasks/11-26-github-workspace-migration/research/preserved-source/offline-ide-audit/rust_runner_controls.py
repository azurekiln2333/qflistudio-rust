"""Owned-Job controls that run INSIDE an already-granted validation clock.

This module prepares SOURCE ONLY. It is not executed by this change and starts
no WSL, SDK, Dart, Flutter, native, build or device step.

Model:

* There is no control window of its own. A control is never an authorization and
  never chains Native90 with Dart110.
* The one integration API is ``run_controls(coordinator, run_dir,
  absolute_deadline)``. The caller passes the absolute ``time.monotonic()``
  deadline it already holds. Every control shares that deadline, and the module
  opens no new total clock.
* The control slice is capped at ``CONTROL_SECONDS`` and then clamped again by
  the caller's deadline, so the caller's clock always wins.
* The loop is fail-fast. A control whose owned cleanup is unconfirmed stops the
  run immediately with HOLD. A control that drained but failed an assertion also
  stops the run, and no further Job is created.
* ``allOwnedJobsEmpty`` reports only the controls that actually ran. It does not
  turn unknown merely because fewer than four controls ran.
* Release refusal needs explicit evidence: a present owned process record, root
  terminal true, owned active count zero, the expected identity fields, an empty
  Job, exit zero and no timeout, orphan cleanup or harness error.
* Timing is checked against both the slice deadline and the caller's absolute
  deadline. The caller re-checks after writing the report with
  ``finalize_controls``, because the write cost is not inside this call.

Dry plan only, starts nothing:

    python build/offline-ide-audit/rust_runner_controls.py --list-plan
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time

REPO_FALLBACK = Path(__file__).resolve().parent.parent.parent

CONTROL_SECONDS = 10.0
REPORT_RESERVE_SECONDS = 1.0

PHASE_SECONDS = {
    "normal-exit": 1.5,
    "orphan-children": 2.5,
    "held-handles": 2.5,
    "timeout-cleanup": 2.0,
}
CONTROL_COUNT = len(PHASE_SECONDS)

TIMEOUT_WORK_SECONDS = 0.3

OBSERVE_SECONDS = 0.6
DRAIN_SECONDS = 0.5
POLL_SECONDS = 0.025

SLEEPER = "import time; time.sleep(600)"
ROOT_WITH_TWO_SLEEPERS = (
    "import subprocess, sys\n"
    "for _ in range(2):\n"
    f"    subprocess.Popen([sys.executable, '-c', {SLEEPER!r}])\n"
    "sys.exit(0)\n"
)

HOLD_STATUS = "hold_cleanup_unconfirmed"
TERMINAL_STATUS = "terminal"

# Exact identity fields the owned process record must carry before a release can
# even be considered. A record without them is unknown, never clean.
REQUIRED_JOB_FIELDS = (
    "pid",
    "threadId",
    "creationFiletime100ns",
    "createdSuspended",
    "assignedBeforeResume",
    "terminal",
    "exitCode",
    "jobActiveProcesses",
)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def plan(control_seconds: float = CONTROL_SECONDS) -> dict:
    reserved = sum(PHASE_SECONDS.values())
    if reserved + REPORT_RESERVE_SECONDS > control_seconds:
        raise ValueError(
            f"Phases need {reserved}s plus {REPORT_RESERVE_SECONDS}s report but "
            f"only {control_seconds}s is available"
        )
    return {
        "controlSeconds": control_seconds,
        "phases": dict(PHASE_SECONDS),
        "reservedSeconds": reserved,
        "reportReserveSeconds": REPORT_RESERVE_SECONDS,
        "spareSeconds": round(control_seconds - reserved - REPORT_RESERVE_SECONDS, 3),
        "timeoutWorkSeconds": TIMEOUT_WORK_SECONDS,
        "requiredJobFields": list(REQUIRED_JOB_FIELDS),
    }


def release_decision(result: dict) -> dict:
    """The real gate predicate over explicit observed evidence.

    A result with a missing process record, a missing identity field, a
    non-terminal root, an unknown or nonzero owned active count, a non-empty
    Job, a timeout, an orphan cleanup, a nonzero exit or a harness error is
    refused, and every reason is recorded. Only a fully observed clean result is
    released.
    """
    reasons: list[str] = []
    job = result.get("process")
    if not isinstance(job, dict):
        reasons.append("missing owned process record")
        job = {}
    missing = [name for name in REQUIRED_JOB_FIELDS if name not in job]
    if missing:
        reasons.append("missing owned identity fields: " + ", ".join(missing))
    for name in ("pid", "threadId"):
        value = job.get(name)
        if type(value) is not int or not 0 < value <= 0xFFFFFFFF:
            reasons.append("invalid owned identity: " + name)
    created = job.get("creationFiletime100ns")
    if (not isinstance(created, str) or len(created) > 20 or not created.isascii()
            or not created.isdigit() or not 0 < int(created) <= 0xFFFFFFFFFFFFFFFF):
        reasons.append("invalid owned creation FILETIME")
    for name in ("createdSuspended", "assignedBeforeResume"):
        if job.get(name) is not True:
            reasons.append("unconfirmed owned setup: " + name)
    if type(job.get("exitCode")) is not int or job.get("exitCode") != 0:
        reasons.append("owned root exit was not zero")
    if result.get("emptyJob") is not True:
        reasons.append("owned Job was not empty at the final query")
    if result.get("orphanCleanup"):
        reasons.append("owned children survived the root")
    if result.get("timeout"):
        reasons.append("work deadline expired")
    if type(result.get("exit")) is not int or result.get("exit") != 0:
        reasons.append(f"gate exit {result.get('exit')}")
    if result.get("error"):
        reasons.append(f"harness error {result['error']}")
    if job.get("terminal") is not True:
        reasons.append("owned root was not terminal")
    if type(job.get("jobActiveProcesses")) is not int or job.get("jobActiveProcesses") != 0:
        reasons.append(f"owned active count {job.get('jobActiveProcesses')}")
    return {"released": not reasons, "reasons": reasons}


def gate_safe(result: dict) -> bool:
    return bool(release_decision(result)["released"])


def _phase_end(deadline: float, cap: float) -> float:
    return min(deadline, time.monotonic() + cap)


def _gate_observations(result: dict) -> dict:
    return {
        "job": dict(result.get("process") or {}),
        "gateExit": result.get("exit"),
        "timeout": bool(result.get("timeout")),
        "orphanCleanup": bool(result.get("orphanCleanup")),
        "emptyJob": bool(result.get("emptyJob")),
        "error": result.get("error"),
        "log": result.get("log"),
    }


def _owned_empty(name: str, observations: dict) -> bool:
    if name == "held-handles":
        return bool(
            observations.get("finalActive") == 0
            and observations.get("finalEmpty") is True
            and observations.get("cleanupActive") == 0
        )
    job = observations.get("job") or {}
    return bool(
        observations.get("emptyJob") is True and job.get("jobActiveProcesses") == 0
    )


def _check_common(result: dict, name: str, problems: list[str]) -> None:
    if result.get("error"):
        problems.append(f"{name}: unexpected error {result['error']}")
    if not result.get("emptyJob"):
        problems.append(f"{name}: final owned Job was not empty")
    if (result.get("process") or {}).get("jobActiveProcesses") != 0:
        problems.append(f"{name}: final owned active count is not 0")


def control_normal_exit(
    run_owned, python_executable: str, cwd: Path, log_dir: Path, deadline: float
) -> dict:
    name = "normal-exit"
    problems: list[str] = []
    end = _phase_end(deadline, PHASE_SECONDS[name])
    result = run_owned(
        f"control {name}",
        [python_executable, "-c", "import sys; sys.exit(0)"],
        cwd,
        log_dir / f"{name}.log",
        end,
        end,
    )
    _check_common(result, name, problems)
    if result.get("timeout"):
        problems.append(f"{name}: unexpected timeout")
    if result.get("orphanCleanup"):
        problems.append(f"{name}: unexpected orphan cleanup")
    if type(result.get("exit")) is not int or result.get("exit") != 0:
        problems.append(f"{name}: exit {result.get('exit')} is not 0")
    if (result.get("process") or {}).get("exitCode") != 0:
        problems.append(f"{name}: owned root exit code is not 0")
    decision = release_decision(result)
    if not decision["released"]:
        problems.append(
            f"{name}: clean result did not pass the gate predicate: {decision['reasons']}"
        )
    observations = _gate_observations(result)
    return {
        "name": name,
        "observations": observations,
        "decision": decision,
        "cleanupConfirmed": _owned_empty(name, observations),
        "problems": problems,
    }


def control_orphan_children(
    run_owned, python_executable: str, cwd: Path, log_dir: Path, deadline: float
) -> dict:
    name = "orphan-children"
    problems: list[str] = []
    end = _phase_end(deadline, PHASE_SECONDS[name])
    result = run_owned(
        f"control {name}",
        [python_executable, "-c", ROOT_WITH_TWO_SLEEPERS],
        cwd,
        log_dir / f"{name}.log",
        end,
        end,
    )
    _check_common(result, name, problems)
    if not result.get("orphanCleanup"):
        problems.append(f"{name}: live owned children were not detected")
    if result.get("timeout"):
        problems.append(f"{name}: root should have exited, not timed out")
    if result.get("exit") == 0:
        problems.append(f"{name}: gate exit stayed 0 with owned survivors")
    decision = release_decision(result)
    if decision["released"]:
        problems.append(f"{name}: predicate released a result with survivors")
    if not any("survived" in reason for reason in decision["reasons"]):
        problems.append(f"{name}: refusal was not caused by surviving children")
    observations = _gate_observations(result)
    return {
        "name": name,
        "observations": observations,
        "decision": decision,
        "cleanupConfirmed": _owned_empty(name, observations),
        "problems": problems,
    }


def control_held_handles(
    owned_job_factory, python_executable: str, cwd: Path, log_dir: Path, deadline: float
) -> dict:
    name = "held-handles"
    problems: list[str] = []
    observations: dict = {}
    job = None
    end = _phase_end(deadline, PHASE_SECONDS[name])
    observe_end = min(end, time.monotonic() + OBSERVE_SECONDS)
    drain_end = min(end, time.monotonic() + DRAIN_SECONDS)
    cleanup_confirmed = False
    try:
        with (log_dir / f"{name}.log").open("wb") as output:
            job = owned_job_factory()
            job.start(
                [python_executable, "-c", ROOT_WITH_TWO_SLEEPERS],
                cwd,
                dict(os.environ),
                output,
                output,
            )
            observations["job"] = dict(job.record)
            while time.monotonic() < observe_end:
                job.empty()
                if job.record.get("terminal"):
                    break
                time.sleep(POLL_SECONDS)
            job.empty()
            live = int(job.record.get("jobActiveProcesses") or 0)
            observations["rootTerminal"] = bool(job.record.get("terminal"))
            observations["liveOwnedChildren"] = live
            observations["rootExitCode"] = job.record.get("exitCode")

            held = {
                "emptyJob": False,
                "orphanCleanup": live > 0,
                "timeout": False,
                "exit": 0 if job.record.get("exitCode") == 0 else 1,
                "error": None,
                "process": dict(job.record),
            }
            observations["decisionWhileLive"] = release_decision(held)
            if observations["decisionWhileLive"]["released"]:
                problems.append(f"{name}: predicate released while children were live")
            if not any(
                "survived" in reason
                for reason in observations["decisionWhileLive"]["reasons"]
            ):
                problems.append(f"{name}: refusal was not caused by live children")
            if not observations["rootTerminal"]:
                problems.append(f"{name}: owned root never became terminal")
            if live < 2:
                problems.append(f"{name}: expected 2 live owned children, saw {live}")
            if "exitCode" not in job.record:
                problems.append(f"{name}: owned root exit code was not recorded")

            job.stop()
            drain_end = min(end, time.monotonic() + DRAIN_SECONDS)
            while not job.empty() and time.monotonic() < drain_end:
                time.sleep(POLL_SECONDS)
            job.empty()
            observations["finalActive"] = int(job.record.get("jobActiveProcesses") or 0)
            observations["finalEmpty"] = observations["finalActive"] == 0
            observations["cleanupActive"] = observations["finalActive"]
            if not job.empty():
                problems.append(f"{name}: owned Job never reached active zero")
            if observations["finalActive"] != 0:
                problems.append(
                    f"{name}: final owned active {observations['finalActive']} is not 0"
                )
            # Carry the full identity record so the released case is explicit.
            clean = {
                "emptyJob": observations["finalActive"] == 0,
                "orphanCleanup": False,
                "timeout": False,
                "exit": 0,
                "error": None,
                "process": dict(job.record),
            }
            observations["decisionAfterDrain"] = release_decision(clean)
            if not observations["decisionAfterDrain"]["released"]:
                problems.append(
                    f"{name}: drained clean state still refused: "
                    f"{observations['decisionAfterDrain']['reasons']}"
                )
            cleanup_confirmed = bool(
                observations["finalEmpty"] and observations["finalActive"] == 0
            )
    except BaseException as failure:
        problems.append(f"{name}: {failure!r}")
        observations["error"] = repr(failure)
    finally:
        if job is not None:
            try:
                if not job.empty():
                    job.stop()
                while not job.empty() and time.monotonic() < drain_end:
                    time.sleep(POLL_SECONDS)
                job.empty()
                observations["cleanupActive"] = int(
                    job.record.get("jobActiveProcesses") or 0
                )
                if observations["cleanupActive"] != 0:
                    problems.append(f"{name}: cleanup left owned processes active")
                    cleanup_confirmed = False
            except BaseException as failure:
                problems.append(f"{name} cleanup: {failure!r}")
                cleanup_confirmed = False
            finally:
                job.close()
    return {
        "name": name,
        "observations": observations,
        "decision": observations.get("decisionAfterDrain"),
        "cleanupConfirmed": cleanup_confirmed,
        "problems": problems,
    }


def control_timeout_cleanup(
    run_owned, python_executable: str, cwd: Path, log_dir: Path, deadline: float
) -> dict:
    name = "timeout-cleanup"
    problems: list[str] = []
    end = _phase_end(deadline, PHASE_SECONDS[name])
    work_end = min(end, time.monotonic() + TIMEOUT_WORK_SECONDS)
    result = run_owned(
        f"control {name}",
        [python_executable, "-c", SLEEPER],
        cwd,
        log_dir / f"{name}.log",
        work_end,
        end,
    )
    _check_common(result, name, problems)
    if not result.get("timeout"):
        problems.append(f"{name}: work deadline was not enforced")
    if result.get("exit") != 124:
        problems.append(f"{name}: exit {result.get('exit')} is not 124")
    decision = release_decision(result)
    if decision["released"]:
        problems.append(f"{name}: predicate released a timed-out result")
    observations = _gate_observations(result)
    return {
        "name": name,
        "observations": observations,
        "decision": decision,
        "cleanupConfirmed": _owned_empty(name, observations),
        "problems": problems,
    }


def _hold_report(started: float, problems: list[str]) -> dict:
    return {
        "schemaVersion": 1,
        "kind": "owned-job-control",
        "status": HOLD_STATUS,
        "passed": False,
        "allOwnedJobsEmpty": False,
        "controlsComplete": False,
        "controlsPlanned": CONTROL_COUNT,
        "controlsExecuted": 0,
        "deadlineExceeded": False,
        "sliceExceeded": False,
        "timingExceeded": False,
        "stopSubsequent": True,
        "elapsedSeconds": round(time.monotonic() - started, 3),
        "startedMonotonic": started,
        "controls": [],
        "problems": problems,
    }


def run_controls(coordinator, run_dir, absolute_deadline) -> dict:
    """Run the owned controls inside the caller's single deadline.

    ``coordinator`` is the loaded ``run-rust-owned-window`` module. ``run_dir``
    receives control logs under ``run_dir / "controls"``. ``absolute_deadline``
    is an absolute ``time.monotonic()`` bound the caller already holds. This
    function never extends or reopens that clock.

    The loop is fail-fast: an unconfirmed owned cleanup stops immediately with
    HOLD, and an already-drained control failure also stops before another Job
    is created. ``allOwnedJobsEmpty`` describes the controls that actually ran.

    The caller must call ``finalize_controls`` after writing the report, so the
    report-write cost is inside the same bound.
    """
    started = time.monotonic()
    run_dir = Path(run_dir)
    log_dir = run_dir / "controls"
    log_dir.mkdir(parents=True, exist_ok=True)

    remaining = absolute_deadline - started
    if remaining <= REPORT_RESERVE_SECONDS:
        return _hold_report(started, ["no control budget inside the granted deadline"])

    control_span = min(CONTROL_SECONDS, remaining - REPORT_RESERVE_SECONDS)
    control_deadline = started + control_span
    try:
        table = plan(control_span)
    except ValueError as failure:
        return _hold_report(started, [
            str(failure),
            "granted window is too short for the reviewed control slice",
        ])

    run_owned = getattr(coordinator, "run_owned", None)
    owned_job_factory = getattr(coordinator, "OwnedJob", None)
    if run_owned is None or owned_job_factory is None:
        return _hold_report(started, ["coordinator does not expose run_owned and OwnedJob"])
    cwd = Path(getattr(coordinator, "REPO", REPO_FALLBACK))
    python_executable = sys.executable

    problems: list[str] = []
    identities: dict = {}
    digest = getattr(coordinator, "digest", None)
    helper_path = Path(getattr(coordinator, "HERE", cwd) / "rust_owned_job.py")
    helper_hash = getattr(coordinator, "HELPER_HASH", None)
    if digest is not None and helper_hash is not None and helper_path.is_file():
        try:
            actual = digest(helper_path)
            identities = {"helperSha256": actual, "helperExpected": helper_hash}
            if actual != helper_hash:
                problems.append("frozen owned Job helper identity changed")
        except OSError as failure:
            problems.append(f"helper identity unreadable: {failure!r}")

    controls: list[dict] = []
    slice_exhausted = False
    cleanup_unconfirmed = False
    if not problems:
        for build in (
            lambda: control_normal_exit(
                run_owned, python_executable, cwd, log_dir, control_deadline
            ),
            lambda: control_orphan_children(
                run_owned, python_executable, cwd, log_dir, control_deadline
            ),
            lambda: control_held_handles(
                owned_job_factory, python_executable, cwd, log_dir, control_deadline
            ),
            lambda: control_timeout_cleanup(
                run_owned, python_executable, cwd, log_dir, control_deadline
            ),
        ):
            if time.monotonic() >= control_deadline:
                slice_exhausted = True
                problems.append("control slice ended before all controls ran")
                break
            outcome = build()
            controls.append(outcome)
            outcome_problems = list(outcome.get("problems") or [])
            problems.extend(outcome_problems)
            if outcome.get("cleanupConfirmed") is not True:
                cleanup_unconfirmed = True
                problems.append(
                    f"{outcome['name']}: owned cleanup unconfirmed; HOLD, no onward work"
                )
                break
            if outcome_problems:
                problems.append(
                    f"{outcome['name']}: fail-fast on control failure; no further Job"
                )
                break

    executed = len(controls)
    all_executed_empty = executed > 0 and all(
        outcome.get("cleanupConfirmed") is True for outcome in controls
    )
    controls_complete = (
        executed == CONTROL_COUNT and not slice_exhausted and not cleanup_unconfirmed
    )
    now = time.monotonic()
    slice_exceeded = now > control_deadline
    deadline_exceeded = now > absolute_deadline
    total_exceeded = (now - started) > CONTROL_SECONDS
    timing_exceeded = slice_exceeded or deadline_exceeded or total_exceeded
    if timing_exceeded:
        problems.append("control window exceeded its bound")
    status = (
        HOLD_STATUS if (cleanup_unconfirmed or executed == 0) else TERMINAL_STATUS
    )
    passed = bool(
        all_executed_empty
        and controls_complete
        and not problems
        and not timing_exceeded
    )
    return {
        "schemaVersion": 1,
        "kind": "owned-job-control",
        "status": status,
        "passed": passed,
        "allOwnedJobsEmpty": all_executed_empty,
        "controlsComplete": controls_complete,
        "controlsPlanned": CONTROL_COUNT,
        "controlsExecuted": executed,
        "deadlineExceeded": deadline_exceeded,
        "sliceExceeded": slice_exceeded,
        "timingExceeded": timing_exceeded,
        "stopSubsequent": not passed,
        "elapsedSeconds": round(now - started, 3),
        "remainingGrantedSeconds": round(absolute_deadline - now, 3),
        "startedMonotonic": started,
        "controlDeadlineMonotonic": control_deadline,
        "absoluteDeadlineMonotonic": absolute_deadline,
        "plan": table,
        "identities": identities,
        "controls": controls,
        "problems": problems,
    }


def finalize_controls(
    report: dict, absolute_deadline, report_write_seconds=None
) -> dict:
    """Re-check timing after the caller writes the report.

    The caller writes the report, then calls this with the same
    ``absolute_deadline``. The total is measured from the ``startedMonotonic``
    stamp written by ``run_controls`` to this call, so the report-write cost is
    inside the bound. A total above ``CONTROL_SECONDS``, a slice overrun or an
    exceeded absolute deadline clears ``passed`` and sets ``stopSubsequent``.
    """
    now = time.monotonic()
    started = report.get("startedMonotonic")
    if isinstance(started, (int, float)):
        total = round(now - started, 3)
    else:
        total = report.get("elapsedSeconds", 0.0)
    deadline_exceeded = now > absolute_deadline
    total_exceeded = total > CONTROL_SECONDS
    timing_exceeded = bool(
        deadline_exceeded or total_exceeded or report.get("timingExceeded")
    )
    prior_passed = report.get("passed") is True

    report["totalSeconds"] = total
    if report_write_seconds is not None:
        report["reportWriteSeconds"] = round(float(report_write_seconds), 3)
    report["deadlineExceeded"] = bool(deadline_exceeded)
    report["timingExceeded"] = timing_exceeded
    if timing_exceeded:
        problems = list(report.get("problems") or [])
        problems.append("final timing exceeded the bound after the report write")
        report["problems"] = problems
    if report.get("allOwnedJobsEmpty") is not True:
        report["status"] = HOLD_STATUS
    report["passed"] = bool(
        prior_passed
        and report.get("allOwnedJobsEmpty") is True
        and report.get("controlsComplete") is True
        and not timing_exceeded
        and not report.get("problems")
    )
    report["stopSubsequent"] = not report["passed"]
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--list-plan",
        action="store_true",
        help="Print the exact slice table and start nothing",
    )
    parser.add_argument(
        "--control-seconds",
        type=float,
        default=CONTROL_SECONDS,
        help="Slice taken from the granted window; never an authorization",
    )
    args = parser.parse_args()
    if args.control_seconds > CONTROL_SECONDS:
        print(json.dumps({
            "planned": False,
            "error": (
                f"{args.control_seconds}s exceeds the reviewed {CONTROL_SECONDS}s slice; "
                "a larger slice is not authorized by this module"
            ),
        }, indent=2))
        return 2
    try:
        table = plan(args.control_seconds)
    except ValueError as failure:
        print(json.dumps({"planned": False, "error": str(failure)}, indent=2))
        return 2
    print(json.dumps({"planned": True, "started": False, "plan": table}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())