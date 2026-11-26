"""Owned OHOS HAP transport: send one production ARM64 HAP to a device over HDC,
then verify the remote SHA-256.

PREPARATION MODULE. It never installs, never uses ADB, never resets a device and
never changes source, build or signing inputs. Running it requires an explicit
`--execute`, and `--prehash-only` stops after local validation.

Contract:

- `--execute --hap <path> --sha256 <hex> --grant <path>` are all required.
- A missing, malformed or incorrect local SHA-256 refuses before any transport.
- A local filename without `unsigned` refuses before any transport.
- The remote path is pinned; the local basename is recorded, not required to
  match it, because the Flutter output keeps its own name.
- Every child is one owned Job root. No process-name kill, no borrowed PID.
- `START` prints the exact root identity (pid, threadId, creation FILETIME and
  both handles) on stdout immediately after the suspended assign and resume,
  before the root is terminal, so the parent holds the identity early.
- Handles are released only after the exact root is terminal AND the job is
  observed empty. A cleanup that cannot be observed empty keeps its live job in
  the retained-custodian list: the module never closes it, never reports the
  resource released, persists HOLD with the identity and handles, and marks the
  run permanently failed.
- Retained custody is held by the process staying alive, never by module memory
  alone. `main` wraps `_main` in a hold loop: while any custodian is retained the
  process republishes HOLD with the exact handles and refuses to exit, because
  interpreter teardown would close the handle table and KILL_ON_JOB_CLOSE would
  then end the tree. An exception or an evidence-IO failure never ends custody.
  A custodian whose close was refused can never drain, so it holds forever.
- Every close goes through `CheckedJob`. The inherited `OwnedJob.close` ignores
  both CloseHandle BOOL results, so a return is not evidence of release. Each
  handle is closed at most once, the exact BOOL is recorded per handle, and a
  refused close keeps the handle value and its Win32 error in HOLD. A job is
  reported released only when both closes returned success.
- Budget for a 60 s module entry: send work <= 40 s, remote hash until 50 s,
  cleanup until 55 s, 5 s reserved for the parent's terminal publish.
"""

from __future__ import annotations

import argparse
import ctypes as C
import hashlib
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from rust_owned_job import OwnedJob  # noqa: E402


class CheckedJob(OwnedJob):
    """OwnedJob whose close verdict comes from CloseHandle, not from returning.

    The inherited `close` ignores both CloseHandle BOOL results and keeps the
    handle values, so it cannot distinguish a released handle from a leaked one,
    and a retry would re-issue CloseHandle on a stale value. Here each handle is
    closed at most once, the exact BOOL is recorded per handle, and a refused
    close is retained with its Win32 error instead of being reported as released.
    """

    SLOTS = (("process", "processHandle"), ("job", "jobHandle"))

    def __init__(self):
        super().__init__()
        self._init_close_state()

    def _init_close_state(self):
        self._closeState = {slot: None for slot, _ in self.SLOTS}
        self._closeError = {slot: None for slot, _ in self.SLOTS}
        self._closeAttempts = {slot: 0 for slot, _ in self.SLOTS}
        self._handleValues = {slot: None for slot, _ in self.SLOTS}
        self._closeRecord = []

    def close(self):
        """Override so no caller can reach the unchecked inherited close."""
        return self.close_checked()

    def close_checked(self):
        """Close each owned handle once and report the exact CloseHandle result."""
        for slot, label in self.SLOTS:
            if self._closeState[slot] is not None:
                continue  # Closed, or refused and therefore never retried.
            handle = getattr(self, slot)
            if not handle:
                self._closeState[slot] = True
                self._closeRecord.append(
                    {"handle": label, "value": None, "outcome": "absent"})
                continue
            self._handleValues[slot] = int(handle)
            self._closeAttempts[slot] += 1
            C.set_last_error(0)
            closed = bool(self.k.CloseHandle(handle))
            if closed:
                self._closeState[slot] = True
                # Null the attribute so a second CloseHandle on this value is
                # impossible even if another path reaches the inherited close.
                setattr(self, slot, None)
                self._closeRecord.append(
                    {"handle": label, "value": int(handle), "outcome": "closed"})
            else:
                error = C.get_last_error()
                self._closeState[slot] = False
                self._closeError[slot] = error
                self._closeRecord.append(
                    {"handle": label, "value": int(handle),
                     "outcome": "close_failed", "win32Error": error})
        return self.close_verdict()

    def close_verdict(self):
        """Per-handle truth; `closed` only when every handle is verified."""
        failed = [label for slot, label in self.SLOTS if self._closeState[slot] is False]
        pending = [label for slot, label in self.SLOTS if self._closeState[slot] is None]
        return {
            "closed": not failed and not pending,
            "processHandleClosed": self._closeState["process"] is True,
            "jobHandleClosed": self._closeState["job"] is True,
            "failedHandles": failed,
            "unattemptedHandles": pending,
            "handleValues": dict(self._handleValues),
            "win32Errors": {
                label: self._closeError[slot]
                for slot, label in self.SLOTS
                if self._closeError[slot] is not None
            },
            "attempts": dict(self._closeAttempts),
            "record": list(self._closeRecord),
        }


def new_job() -> CheckedJob:
    """The only Job constructor this module uses."""
    return CheckedJob()

MODULE_STARTED = time.monotonic()

KIND = "ohos-hap-owned-transport"
SCHEMA_VERSION = 1

# Pinned transport endpoints. The exact hdc path is part of the contract.
HDC = Path("D:/ProgramFiles/Huawei/OpenHarmony/Sdk/23/toolchains/hdc.exe")
TARGET = "192.168.68.207:46551"
REMOTE_HAP = "/data/local/tmp/qfli-rust-20261026-arm64-unsigned.hap"
REQUIRED_NAME_TOKEN = "unsigned"

# 60 s module entry, split exactly as agreed with the parent's coordinator.
MODULE_SECONDS = 60.0
SEND_SECONDS = 40.0
HASH_UNTIL_SECONDS = 50.0
CLEANUP_SECONDS = 55.0
RESERVE_SECONDS = 5.0
POLL_SECONDS = 0.025
WORK_GRACE_SECONDS = 0.4

# Hold loop. While a custodian is retained the process must not exit, so it
# republishes HOLD on this period and retries a safe drain on this window.
HOLD_PUBLISH_SECONDS = 5.0
HOLD_DRAIN_SECONDS = 0.5
HOLD_EXIT = 5

STATUS_PASSED = "passed"
STATUS_HOLD = "hold_cleanup_unconfirmed"
STATUS_FAILED = "failed"
STATUS_PREHASH_ONLY = "validated_prehash_only"

# A silent budget edit would break the parent's terminal publish. Fail loudly at
# import time instead.
assert SEND_SECONDS <= HASH_UNTIL_SECONDS <= CLEANUP_SECONDS
assert CLEANUP_SECONDS + RESERVE_SECONDS <= MODULE_SECONDS, "reserve does not fit the budget"
assert HASH_UNTIL_SECONDS < CLEANUP_SECONDS < MODULE_SECONDS
assert len(TARGET.split(":")) == 2 and TARGET.split(":")[1].isdigit()
assert REQUIRED_NAME_TOKEN in Path(REMOTE_HAP).name

# Custody retained because cleanup could not be observed empty. A job in this
# list stays open on purpose: `OwnedJob` carries KILL_ON_JOB_CLOSE, so closing it
# would terminate the tree and destroy the very evidence that must be preserved.
# These jobs are never closed by this module; only a later confirmed empty state
# allows a close.
RETAINED_CUSTODIANS: list[dict] = []

# Sticky failure. Once uncertainty or a budget overrun is recorded, the run can
# never be reported as passed or released again.
STICKY = {"uncertainCleanup": False, "budgetOverrun": False, "failure": False}

# Published so the hold loop can refresh the same report the run already wrote.
LAST_REPORT: dict | None = None
LAST_REPORT_PATH: Path | None = None
HOLD_PUBLISH_COUNT = 0


def digest_bytes(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def write_json(path: Path, value: object) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def is_hex_digest(text: str) -> bool:
    return len(text) == 64 and all(character in "0123456789abcdef" for character in text)


def first_hex_digest(text: str) -> str | None:
    """First 64-character hex token, the shape `sha256sum` prints."""
    token = ""
    for character in text:
        if character in "0123456789abcdefABCDEF":
            token += character.lower()
            if len(token) == 64:
                return token
        else:
            token = ""
    return None


def identity(job: OwnedJob, record: dict) -> dict:
    """Exact root identity, including both handle values.

    Values survive a successful close: `CheckedJob` nulls the attribute to make a
    second close impossible, so the value is read back from its record.
    """
    values = getattr(job, "_handleValues", None) or {}
    return {
        "pid": record.get("pid"),
        "threadId": record.get("threadId"),
        "creationFiletime100ns": record.get("creationFiletime100ns"),
        "createdSuspended": record.get("createdSuspended"),
        "assignedBeforeResume": record.get("assignedBeforeResume"),
        "jobHandle": int(values.get("job") or getattr(job, "job", None) or 0),
        "processHandle": int(values.get("process") or getattr(job, "process", None) or 0),
    }


def announce_start(name: str, job: OwnedJob) -> dict:
    """Emit the root identity on stdout before the root is terminal."""
    value = identity(job, job.record)
    value["name"] = name
    print("START", name, json.dumps(value, separators=(",", ":")), flush=True)
    return value


def register_custodian(job: OwnedJob, record: dict, name: str, reason: str,
                       close: dict | None = None) -> dict:
    """Retain a live job whose release could not be proven."""
    custodian = identity(job, record)
    custodian.update({
        "name": name,
        "reason": reason,
        "terminal": record.get("terminal"),
        "jobActiveProcesses": record.get("jobActiveProcesses"),
        "exitCode": record.get("exitCode"),
        "retainedAtMonotonicFromStart": round(time.monotonic() - MODULE_STARTED, 3),
        "resourceReleasedByModule": False,
        "handlesLiveUntil": "module exit; interpreter teardown then closes them",
        "closeAttempted": close is not None,
    })
    if close is not None:
        custodian["closeVerdict"] = close
        custodian["failedHandles"] = close.get("failedHandles", [])
    RETAINED_CUSTODIANS.append({**custodian, "job": job})
    STICKY["uncertainCleanup"] = True
    STICKY["failure"] = True
    print("RETAIN", name, json.dumps(custodian, separators=(",", ":")), flush=True)
    return custodian


def drain_custodians(deadline: float) -> list[dict]:
    """Retry the empty observation for retained custody without releasing it.

    A custodian that reaches exact terminal and empty is closed here and only
    here. One that does not is left open and stays retained.
    """
    drained = []
    for custodian in list(RETAINED_CUSTODIANS):
        if custodian.get("closeAttempted"):
            continue  # A refused close is permanent: this stays in HOLD.
        job = custodian["job"]
        try:
            while True:
                empty = job.empty()
                now = time.monotonic()
                if empty:
                    verdict = job.close_checked()
                    if not verdict["closed"]:
                        # Refused handle: record it and never retry the close.
                        custodian["closeAttempted"] = True
                        custodian["closeVerdict"] = verdict
                        custodian["failedHandles"] = verdict.get("failedHandles", [])
                        break
                    released = {key: value for key, value in custodian.items() if key != "job"}
                    released["drained"] = True
                    released["resourceReleasedByModule"] = True
                    released["closeVerdict"] = verdict
                    released["drainedAtMonotonicFromStart"] = round(now - MODULE_STARTED, 3)
                    RETAINED_CUSTODIANS.remove(custodian)
                    drained.append(released)
                    print("DRAIN", custodian["name"],
                          json.dumps(released, separators=(",", ":")), flush=True)
                    break
                if now >= deadline:
                    break
                time.sleep(min(POLL_SECONDS, max(0.0, deadline - now)))
        except BaseException as failure:  # noqa: BLE001 - keep custody, report it
            custodian["drainError"] = repr(failure)
            break
    return drained


class Refusal(Exception):
    """A precondition failed. Nothing was started when this is raised."""


def validate(args: argparse.Namespace) -> dict:
    """All preconditions. Raises Refusal before any child process exists."""
    if not args.execute:
        raise Refusal("--execute is required; this module never runs implicitly")

    hap = Path(args.hap)
    if not hap.is_absolute():
        raise Refusal(f"--hap must be an absolute path: {hap}")
    if not hap.is_file():
        raise Refusal(f"--hap is not a file: {hap}")
    if REQUIRED_NAME_TOKEN not in hap.name:
        raise Refusal(
            f"--hap filename must contain `{REQUIRED_NAME_TOKEN}` to mark an unsigned "
            f"artifact: {hap.name}"
        )

    expected = (args.sha256 or "").strip().lower()
    if not is_hex_digest(expected):
        raise Refusal(f"--sha256 must be 64 hex characters, got {args.sha256!r}")
    actual = digest_bytes(hap)
    if actual != expected:
        raise Refusal(
            f"--sha256 does not match the local artifact: expected {expected}, actual {actual}"
        )

    grant = Path(args.grant)
    if not grant.is_file():
        raise Refusal(f"--grant is not a file: {grant}")
    if grant.stat().st_size == 0:
        raise Refusal(f"--grant is empty: {grant}")

    if not HDC.is_file():
        raise Refusal(f"pinned hdc endpoint is unavailable: {HDC}")

    return {
        "hapPath": str(hap),
        "hapBytes": hap.stat().st_size,
        "hapSha256Actual": actual,
        "hapSha256Expected": expected,
        "hapBasename": hap.name,
        # Recorded, not required: the built artifact keeps the Flutter output
        # name while the remote name is pinned by the transport contract.
        "remoteBasenameMatchesLocal": hap.name == Path(REMOTE_HAP).name,
        "grantPath": str(grant),
        "grantEvidenceSha256": digest_bytes(grant),
        "hdcPath": str(HDC),
        "target": TARGET,
        "remotePath": REMOTE_HAP,
    }


def run_owned(
    name: str,
    command: list[str],
    cwd: Path,
    log: Path,
    work_deadline: float,
    cleanup_deadline: float,
) -> dict:
    """Run one exact owned root; release handles only on confirmed cleanliness.

    The root identity is printed as `START` immediately after the suspended
    assign and resume. Cleanup is observed until `cleanup_deadline`. Only an
    observation of terminal plus empty releases the job. Anything else keeps the
    live job in `RETAINED_CUSTODIANS` and permanently fails the run.
    """
    started = time.monotonic()
    work_deadline = min(work_deadline, cleanup_deadline)
    job: OwnedJob | None = None
    error: str | None = None
    timed_out = False
    orphan_cleanup = False
    empty = False
    not_started = False
    record: dict = {}
    start_identity: dict = {}
    code = 1
    released = False
    cleanup_confirmed = False
    retained: dict | None = None
    close_verdict: dict | None = None
    last_observed = started
    cleanup_observed = started

    def observe() -> bool:
        nonlocal last_observed
        value = job.empty()
        # The query itself can cross a deadline; its completion is the evidence.
        last_observed = time.monotonic()
        return value

    try:
        with log.open("wb") as output:
            if time.monotonic() >= work_deadline:
                not_started = True
                empty = True  # No Job and no process were created by this call.
                released = True
                cleanup_confirmed = True
                timed_out = True
                code = 124
                STICKY["budgetOverrun"] = True
                STICKY["failure"] = True
            else:
                job = new_job()
                job.start(command, cwd, dict(os.environ), output, output)
                start_identity = announce_start(name, job)
                while True:
                    empty = observe()
                    if last_observed > work_deadline:
                        timed_out = True
                        break
                    if empty or job.record.get("terminal"):
                        break
                    time.sleep(min(POLL_SECONDS, max(0.0, work_deadline - last_observed)))
                if not job.record.get("terminal"):
                    timed_out = True
                elif job.record.get("jobActiveProcesses"):
                    # A terminal root with live descendants is an orphan risk.
                    grace = min(work_deadline, last_observed + WORK_GRACE_SECONDS)
                    while True:
                        empty = observe()
                        if last_observed > work_deadline:
                            timed_out = True
                        if empty or last_observed >= grace:
                            break
                        time.sleep(min(POLL_SECONDS, max(0.0, grace - last_observed)))
                    if not empty:
                        orphan_cleanup = True
                if not empty and (timed_out or orphan_cleanup):
                    # Exact owned termination only: the Job, never a name match.
                    job.stop()
                code = 124 if timed_out else job.record.get("exitCode", 1)
                if timed_out:
                    STICKY["budgetOverrun"] = True
                    STICKY["failure"] = True
    except BaseException as failure:  # noqa: BLE001 - recorded, then handled below
        error = repr(failure)
        STICKY["failure"] = True
    finally:
        if job is not None:
            try:
                while True:
                    empty = observe()
                    cleanup_observed = last_observed
                    if empty or last_observed >= cleanup_deadline:
                        break
                    time.sleep(min(POLL_SECONDS, max(0.0, cleanup_deadline - last_observed)))
                record = dict(job.record)
                cleanup_confirmed = bool(empty and cleanup_observed <= cleanup_deadline and not error)
            except BaseException as failure:  # noqa: BLE001
                record = dict(job.record)
                error = error or repr(failure)
                empty = False
                cleanup_confirmed = False
                STICKY["failure"] = True

            if cleanup_confirmed:
                # Exact terminal and observed empty. The tree is gone; only now
                # may the handles be closed, and each close must prove itself.
                close_verdict = job.close_checked()
                if close_verdict["closed"]:
                    released = True
                else:
                    # CloseHandle refused a handle, so nothing is released. Keep
                    # the job retained so the leak stays auditable.
                    retained = register_custodian(
                        job, record, name,
                        "cleanup confirmed but CloseHandle did not succeed for "
                        "every owned handle",
                        close=close_verdict,
                    )
            else:
                # Uncertainty. Closing here would trip KILL_ON_JOB_CLOSE and
                # destroy the state that must stay auditable, so the handles are
                # deliberately kept open and custody is retained instead.
                retained = register_custodian(
                    job, record, name,
                    "cleanup not observed empty before its deadline" if not error
                    else f"cleanup observation failed: {error}",
                )
        elif not_started or not record:
            empty = True  # No start call was reached, so nothing was created.
            released = True
            cleanup_confirmed = True

    return {
        "name": name,
        "command": command,
        "log": str(log),
        "workDeadlineSecondsFromStart": round(work_deadline - MODULE_STARTED, 3),
        "cleanupDeadlineSecondsFromStart": round(cleanup_deadline - MODULE_STARTED, 3),
        "rootIdentity": start_identity,
        "process": record,
        "exit": code,
        "timeout": timed_out,
        "orphanCleanup": orphan_cleanup,
        "emptyJob": bool(empty),
        "cleanupConfirmed": bool(cleanup_confirmed),
        "custodianRetained": retained is not None,
        "resourceReleased": bool(released),
        "handleClose": close_verdict,
        "error": error,
        "started": not not_started,
    }


def _main() -> int:
    global LAST_REPORT, LAST_REPORT_PATH
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", required=True)
    parser.add_argument("--hap", required=True, help="absolute path to the local unsigned HAP")
    parser.add_argument("--sha256", required=True, help="expected local SHA-256, 64 hex")
    parser.add_argument("--grant", required=True, help="root-verified grant evidence file")
    parser.add_argument("--report", type=Path, help="JSON report path")
    parser.add_argument(
        "--prehash-only",
        action="store_true",
        help="validate the local artifact and stop; performs no transport",
    )
    args = parser.parse_args()

    run = HERE / "runs" / ("hap-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()))
    run.mkdir(parents=True, exist_ok=True)
    report_path = args.report or (run / "send.json")

    module_deadline = MODULE_STARTED + MODULE_SECONDS
    send_deadline = MODULE_STARTED + SEND_SECONDS
    hash_deadline = MODULE_STARTED + HASH_UNTIL_SECONDS
    cleanup_deadline = MODULE_STARTED + CLEANUP_SECONDS

    report: dict = {
        "schemaVersion": SCHEMA_VERSION,
        "kind": KIND,
        "status": STATUS_FAILED,
        "grantVerifiedByRoot": True,
        "grantVerifiedBySelf": False,
        "transportExecuted": False,
        "installPerformed": False,
        "adbUsed": False,
        "resetPerformed": False,
        "passed": False,
        "released": False,
        "readyForParentPublish": False,
        "reportPath": str(report_path),
        "budgetSeconds": MODULE_SECONDS,
        "sendSeconds": SEND_SECONDS,
        "hashUntilSeconds": HASH_UNTIL_SECONDS,
        "cleanupSeconds": CLEANUP_SECONDS,
        "reserveSeconds": RESERVE_SECONDS,
        "results": [],
        "commands": [],
        "retainedCustodians": [],
        "drainedCustodians": [],
        "remoteSha256": None,
        "remoteSha256Match": False,
        "cleanupConfirmed": False,
        "allOwnedJobsEmpty": False,
        "custodianRetained": False,
        "resourceReleased": False,
        "retainedCustodyEndsAtInterpreterExit": True,
        "failurePermanent": False,
        "exit": 1,
        "refusal": None,
    }
    LAST_REPORT_PATH = report_path
    LAST_REPORT = report

    try:
        preconditions = validate(args)
    except Refusal as refusal:
        report["refusal"] = str(refusal)
        report["status"] = STATUS_FAILED
        write_json(report_path, report)
        print(f"REFUSE {refusal}", file=sys.stderr)
        return 1

    report.update(preconditions)

    if args.prehash_only:
        report["status"] = STATUS_PREHASH_ONLY
        report["prehashOnly"] = True
        report["exit"] = 0
        write_json(report_path, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    send_command = [str(HDC), "-t", TARGET, "file", "send", str(Path(args.hap)), REMOTE_HAP]
    hash_command = [str(HDC), "-t", TARGET, "shell", "sha256sum", REMOTE_HAP]
    report["commands"] = [send_command, hash_command]

    # Step 1: transport. Its own work deadline, shared cleanup deadline.
    send_result = run_owned(
        "hdc file send", send_command, HERE, run / "01-send.log", send_deadline, cleanup_deadline
    )
    report["results"].append(send_result)
    report["transportExecuted"] = send_result["started"]
    write_json(report_path, report)

    transport_ok = (
        send_result["started"]
        and send_result["exit"] == 0
        and not send_result["timeout"]
        and send_result["emptyJob"]
        and send_result["cleanupConfirmed"]
    )
    if not transport_ok:
        # Custody loop for anything retained, then report without releasing.
        report["drainedCustodians"] = drain_custodians(cleanup_deadline)
        report["retainedCustodians"] = [
            {key: value for key, value in custodian.items() if key != "job"}
            for custodian in RETAINED_CUSTODIANS
        ]
        report["custodianRetained"] = bool(RETAINED_CUSTODIANS)
        report["resourceReleased"] = all(result["resourceReleased"] for result in report["results"])
        report["failurePermanent"] = bool(STICKY["failure"])
        report["status"] = (
            STATUS_HOLD if (report["custodianRetained"] or not send_result["cleanupConfirmed"])
            else STATUS_FAILED
        )
        report["exit"] = 124 if send_result["timeout"] else (5 if report["custodianRetained"] else 1)
        write_json(report_path, report)
        print(json.dumps({key: report[key] for key in
                          ("status", "exit", "resourceReleased", "failurePermanent",
                           "retainedCustodians", "results")},
                         ensure_ascii=False, indent=2))
        return report["exit"]

    # Step 2: verify the hash of exactly that remote file.
    hash_result = run_owned(
        "hdc shell sha256sum", hash_command, HERE, run / "02-hash.log", hash_deadline,
        cleanup_deadline,
    )
    report["results"].append(hash_result)
    log_text = (run / "02-hash.log").read_text(encoding="utf-8", errors="replace")
    remote = first_hex_digest(log_text)
    report["remoteSha256"] = remote
    report["remoteSha256Match"] = bool(remote) and remote == args.sha256.strip().lower()
    write_json(report_path, report)

    hash_ok = (
        hash_result["started"]
        and hash_result["exit"] == 0
        and not hash_result["timeout"]
        and hash_result["emptyJob"]
        and hash_result["cleanupConfirmed"]
        and report["remoteSha256Match"]
    )

    if RETAINED_CUSTODIANS:
        report["drainedCustodians"] = drain_custodians(cleanup_deadline)

    report["retainedCustodians"] = [
        {key: value for key, value in custodian.items() if key != "job"}
        for custodian in RETAINED_CUSTODIANS
    ]
    report["custodianRetained"] = bool(RETAINED_CUSTODIANS)
    report["resourceReleased"] = all(result["resourceReleased"] for result in report["results"])
    report["cleanupConfirmed"] = bool(
        all(result["cleanupConfirmed"] for result in report["results"])
        and not RETAINED_CUSTODIANS
    )
    report["allOwnedJobsEmpty"] = bool(all(result["emptyJob"] for result in report["results"]))

    # An overrun of the 60 s entry is never a bounded pass, even when the
    # transport and the remote hash both succeeded.
    if time.monotonic() > module_deadline:
        report["moduleOverrun"] = True
        STICKY["budgetOverrun"] = True
        STICKY["failure"] = True

    report["failurePermanent"] = bool(STICKY["failure"])

    if hash_ok and report["cleanupConfirmed"] and not STICKY["failure"]:
        report["status"] = STATUS_PASSED
        report["passed"] = True
        report["released"] = True
        report["readyForParentPublish"] = True
        report["exit"] = 0
    elif report["custodianRetained"] or not report["cleanupConfirmed"]:
        # Uncertain custody: HOLD, nothing released, and the parent must not
        # publish a release for this run.
        report["status"] = STATUS_HOLD
        report["exit"] = 5
    else:
        report["status"] = STATUS_FAILED
        report["exit"] = 1

    write_json(report_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report["exit"]


def public_custodians() -> list[dict]:
    """Custodian records without the live job object, safe to serialize."""
    return [
        {key: value for key, value in custodian.items() if key != "job"}
        for custodian in RETAINED_CUSTODIANS
    ]


def publish_hold(code: int) -> None:
    """Publish HOLD with the exact handles of every retained custodian."""
    global HOLD_PUBLISH_COUNT
    HOLD_PUBLISH_COUNT += 1
    report = LAST_REPORT if isinstance(LAST_REPORT, dict) else {}
    report.update({
        "status": STATUS_HOLD,
        "exit": code,
        "passed": False,
        "released": False,
        "readyForParentPublish": False,
        "resourceReleased": False,
        "custodianRetained": bool(RETAINED_CUSTODIANS),
        "retainedCustodians": public_custodians(),
        "failurePermanent": True,
        "budgetFailed": bool(STICKY["budgetOverrun"]),
        "uncertainCleanup": bool(STICKY["uncertainCleanup"]),
        # Custody is held by this live process, not by module memory alone.
        "custodyHeldByLiveProcess": bool(RETAINED_CUSTODIANS),
        "retainedCustodyEndsAtInterpreterExit": not RETAINED_CUSTODIANS,
        "holdPublishCount": HOLD_PUBLISH_COUNT,
        "holdPublishedAtMonotonicFromStart": round(time.monotonic() - MODULE_STARTED, 3),
    })
    path = LAST_REPORT_PATH or (HERE / "runs" / "hold.json")
    write_json(path, report)
    print("HOLD", json.dumps({
        "status": report["status"],
        "exit": code,
        "budgetFailed": report["budgetFailed"],
        "publishCount": HOLD_PUBLISH_COUNT,
        "retained": [
            {key: custodian.get(key) for key in
             ("name", "reason", "pid", "threadId", "creationFiletime100ns",
              "jobHandle", "processHandle", "exitCode", "jobActiveProcesses",
              "closeAttempted", "failedHandles")}
            for custodian in report["retainedCustodians"]
        ],
    }, separators=(",", ":")), flush=True)


def hold_custody_loop(code: int) -> int:
    """Refuse to leave this process while a custodian is retained.

    In-memory retention is not custody beyond exit: interpreter teardown closes
    the handle table and KILL_ON_JOB_CLOSE then ends the tree. So while a
    custodian remains, this loop stays in the same process, keeps republishing
    HOLD with the exact handles and attempts a drain only when it is safe. A
    custodian whose close was refused can never drain, so it holds here forever
    by design until the parent or an operator ends the process.
    """
    if not RETAINED_CUSTODIANS:
        return code

    STICKY["failure"] = True
    STICKY["uncertainCleanup"] = True
    while True:
        try:
            publish_hold(HOLD_EXIT)
        except BaseException:  # noqa: BLE001 - evidence IO must not end custody
            pass
        try:
            drain_custodians(time.monotonic() + HOLD_DRAIN_SECONDS)
        except BaseException:  # noqa: BLE001 - a failed drain must not end custody
            pass
        if not RETAINED_CUSTODIANS:
            # Every handle closed with a verified BOOL, so leaving is safe. The
            # run still stays permanently failed: release was never clean.
            try:
                publish_hold(HOLD_EXIT)
            except BaseException:  # noqa: BLE001
                pass
            return HOLD_EXIT
        time.sleep(HOLD_PUBLISH_SECONDS)


def main() -> int:
    """Public entry. Custody outlives any return or raise from `_main`."""
    code = 1
    try:
        code = _main()
    except SystemExit:
        # Bad arguments can only happen before any Job exists.
        if not RETAINED_CUSTODIANS:
            raise
        STICKY["failure"] = True
        code = HOLD_EXIT
    except BaseException:  # noqa: BLE001 - an exception never ends custody
        STICKY["failure"] = True
        code = HOLD_EXIT if RETAINED_CUSTODIANS else 1
    finally:
        # Runs on the early returns too, which is exactly where the previous
        # version dropped custody and let interpreter teardown destroy it.
        code = hold_custody_loop(code)
    return code


if __name__ == "__main__":
    sys.exit(main())