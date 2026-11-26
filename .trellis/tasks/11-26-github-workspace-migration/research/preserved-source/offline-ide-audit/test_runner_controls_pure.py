"""Durable pure tests for the owned-Job controls and the coordinator gate.

No real Job, child process, native library, SDK, build, WSL or device is used.
Time comes from a fake clock and Jobs come from fake objects, so every timing
boundary is exact and repeatable.

Run only:

    python -m unittest discover -s build/offline-ide-audit -p test_runner_controls_pure.py

The controls module is read-only here. This file owns no production code.
"""
from __future__ import annotations

import ast
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
CONTROLS_PATH = HERE / "rust_runner_controls.py"
COORDINATOR_PATH = HERE / "run-rust-owned-window.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

controls = load_module("rust_runner_controls_under_test", CONTROLS_PATH)
coordinator = load_module("rust_coordinator_under_test", COORDINATOR_PATH)


class FakeClock:
    """A monotonic clock that only moves when the test moves it."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = float(start)

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += float(seconds)

    def advance(self, seconds: float) -> None:
        self.now += float(seconds)


IDENTITY = {
    "pid": 4242,
    "threadId": 17,
    "creationFiletime100ns": "132000000000000000",
    "createdSuspended": True,
    "assignedBeforeResume": True,
}


def job_record(active: int, *, terminal: bool = True, exit_code: int = 0) -> dict:
    record = dict(IDENTITY)
    record["terminal"] = terminal
    record["exitCode"] = exit_code
    record["jobActiveProcesses"] = active
    return record


def gate_result(
    *,
    active: int = 0,
    terminal: bool = True,
    exit_code: int = 0,
    empty_job: bool = True,
    gate_exit: int = 0,
    timeout: bool = False,
    orphan: bool = False,
    error: object = None,
    log: str = "log",
) -> dict:
    return {
        "name": "fake",
        "command": ["fake"],
        "cwd": "cwd",
        "process": job_record(active, terminal=terminal, exit_code=exit_code),
        "exit": gate_exit,
        "timeout": timeout,
        "orphanCleanup": orphan,
        "emptyJob": empty_job,
        "error": error,
        "log": log,
    }


class FakeJob:
    """Minimal owned-Job stand-in with explicit handle-held semantics."""

    def __init__(self, *, drain: bool = True, live: int = 2) -> None:
        self.record: dict = {}
        self.started = False
        self.closed = False
        self.stopped = False
        self.drain = drain
        self.live = live
        self.queries = 0

    def start(self, command, directory, env, stdout, stderr) -> None:
        self.started = True
        self.record = job_record(self.live, terminal=False)
        self.record.pop("exitCode", None)

    def empty(self) -> bool:
        self.queries += 1
        if not self.started:
            return False
        if self.stopped:
            active = 0 if self.drain else self.live
            self.record.update(
                terminal=True, exitCode=0, jobActiveProcesses=active
            )
            return active == 0
        if self.queries >= 2:
            # The owned root has exited; descendants are still alive.
            self.record.update(
                terminal=True, exitCode=0, jobActiveProcesses=self.live
            )
        return False

    def stop(self) -> None:
        self.stopped = True

    def close(self) -> None:
        self.closed = True


class FakeRunner:
    """A run_owned stand-in that records the deadlines it was given.

    Defaults reproduce the result each control expects to observe:
    a clean natural exit, a root that died while two children survived, and a
    work deadline that expired.
    """

    def __init__(self, responses: dict | None = None, on_call=None) -> None:
        self.responses = responses or {}
        self.on_call = on_call
        self.calls: list[dict] = []

    @staticmethod
    def default_response(control: str, log: str) -> dict:
        if control == "orphan-children":
            return gate_result(orphan=True, gate_exit=1, log=log)
        if control == "timeout-cleanup":
            return gate_result(timeout=True, gate_exit=124, log=log)
        return gate_result(log=log)

    def __call__(self, name, command, cwd, log, work_deadline, cleanup_deadline):
        control = Path(log).stem
        self.calls.append(
            {
                "control": control,
                "workDeadline": work_deadline,
                "cleanupDeadline": cleanup_deadline,
                "log": str(log),
            }
        )
        if self.on_call is not None:
            self.on_call(control, self)
        response = self.responses.get(control)
        if response is None:
            return self.default_response(control, str(log))
        if callable(response):
            response = response(str(log))
        return response


def fake_coordinator(run_owned, owned_job_factory=None, helper_hash=None,
                     digest_value=None) -> object:
    return types.SimpleNamespace(
        run_owned=run_owned,
        OwnedJob=owned_job_factory or (lambda: FakeJob()),
        digest=lambda path: digest_value or helper_hash or "helper-hash",
        HELPER_HASH=helper_hash or "helper-hash",
        HERE=HERE,
        REPO=REPO,
    )


class ControlPatchMixin:
    """Swap the module clocks for a fake and restore them afterwards."""

    def setUp(self) -> None:
        self.clock = FakeClock()
        self._saved = {
            "controls.time": controls.time,
            "coordinator.time": coordinator.time,
            "coordinator.write_json": coordinator.write_json,
        }
        controls.time = self.clock
        coordinator.time = self.clock
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.run_dir = Path(self.tmp.name) / "run"
        self.run_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        controls.time = self._saved["controls.time"]
        coordinator.time = self._saved["coordinator.time"]
        coordinator.write_json = self._saved["coordinator.write_json"]


class ReleaseDecisionTests(unittest.TestCase):
    """Missing ownership or an unknown active count must never be released."""

    def test_missing_process_record_is_refused(self) -> None:
        decision = controls.release_decision({"emptyJob": True, "exit": 0})
        self.assertFalse(decision["released"])
        self.assertIn("missing owned process record", decision["reasons"])

    def test_each_missing_identity_field_is_refused(self) -> None:
        for field in controls.REQUIRED_JOB_FIELDS:
            with self.subTest(field=field):
                record = job_record(0)
                record.pop(field)
                decision = controls.release_decision(
                    gate_result() | {"process": record}
                )
                self.assertFalse(decision["released"])
                self.assertTrue(
                    any("missing owned identity fields" in reason
                        for reason in decision["reasons"]),
                    decision["reasons"],
                )

    def test_missing_active_count_is_refused(self) -> None:
        record = job_record(0)
        record.pop("jobActiveProcesses")
        decision = controls.release_decision(gate_result() | {"process": record})
        self.assertFalse(decision["released"])
        self.assertTrue(
            any("jobActiveProcesses" in reason for reason in decision["reasons"])
        )

    def test_nonzero_active_count_is_refused(self) -> None:
        decision = controls.release_decision(gate_result(active=2, empty_job=False))
        self.assertFalse(decision["released"])
        self.assertTrue(
            any("owned active count 2" in reason for reason in decision["reasons"])
        )

    def test_nonterminal_root_is_refused(self) -> None:
        decision = controls.release_decision(gate_result(terminal=False))
        self.assertFalse(decision["released"])
        self.assertTrue(
            any("not terminal" in reason for reason in decision["reasons"])
        )

    def test_clean_terminal_result_is_accepted(self) -> None:
        decision = controls.release_decision(gate_result())
        self.assertTrue(decision["released"], decision["reasons"])
        self.assertEqual(decision["reasons"], [])

    def test_live_child_refuses_with_survivor_reason(self) -> None:
        decision = controls.release_decision(
            gate_result(active=2, empty_job=False, gate_exit=1, orphan=True)
        )
        self.assertFalse(decision["released"])
        self.assertTrue(
            any("survived" in reason for reason in decision["reasons"])
        )

    def test_timeout_and_error_and_exit_refuse(self) -> None:
        for kwargs, needle in (
            ({"timeout": True, "gate_exit": 124}, "work deadline expired"),
            ({"error": "boom", "gate_exit": 1}, "harness error"),
            ({"gate_exit": 3}, "gate exit 3"),
            ({"empty_job": False, "gate_exit": 1}, "not empty"),
        ):
            with self.subTest(needle=needle):
                decision = controls.release_decision(gate_result(**kwargs))
                self.assertFalse(decision["released"])
                self.assertTrue(
                    any(needle in reason for reason in decision["reasons"]),
                    decision["reasons"],
                )

    def test_gate_safe_mirrors_release_decision(self) -> None:
        self.assertTrue(controls.gate_safe(gate_result()))
        self.assertFalse(controls.gate_safe(gate_result(active=1, empty_job=False)))


class ReleaseEvidenceTests(unittest.TestCase):
    """Every identity and status field must be positively observed.

    Boolean, float, string, null, zero, negative, oversized and missing values
    are refused, because ``False`` is no longer accepted as a zero.
    """

    def _result(self, *, drop=(), **fields) -> dict:
        record = job_record(0)
        record.update(fields)
        for name in drop:
            record.pop(name, None)
        return gate_result() | {"process": record}

    def _assert_refused(self, result, needle: str) -> None:
        decision = controls.release_decision(result)
        self.assertFalse(decision["released"], decision["reasons"])
        self.assertTrue(
            any(needle in reason for reason in decision["reasons"]),
            f"expected {needle!r} in {decision['reasons']}",
        )

    def test_the_valid_fixture_is_accepted(self) -> None:
        decision = controls.release_decision(gate_result())
        self.assertTrue(decision["released"], decision["reasons"])

    def test_valid_identity_boundaries_are_accepted(self) -> None:
        for fields in (
            {"pid": 1},
            {"pid": 0xFFFFFFFF},
            {"threadId": 1},
            {"threadId": 0xFFFFFFFF},
            {"creationFiletime100ns": "1"},
            {"creationFiletime100ns": "00000000000000000001"},
            {"creationFiletime100ns": "18446744073709551615"},
        ):
            with self.subTest(fields=fields):
                decision = controls.release_decision(self._result(**fields))
                self.assertTrue(decision["released"], decision["reasons"])

    def test_pid_and_thread_id_need_a_positive_32_bit_integer(self) -> None:
        for name in ("pid", "threadId"):
            for value in (None, False, True, 0, -1, 0x1_00000000, 1.0, "1"):
                with self.subTest(field=name, value=value):
                    self._assert_refused(
                        self._result(**{name: value}),
                        "invalid owned identity: " + name,
                    )

    def test_missing_pid_or_thread_id_is_refused(self) -> None:
        for name in ("pid", "threadId"):
            with self.subTest(field=name):
                self._assert_refused(
                    self._result(drop=(name,)),
                    "missing owned identity fields: " + name,
                )

    def test_creation_filetime_needs_decimal_ascii_within_uint64(self) -> None:
        for value in (None, "", "0", "abc", "12 34", "1.5", "１２３",
                      "1" * 21, "18446744073709551616", 123.0, b"123"):
            with self.subTest(value=value):
                self._assert_refused(
                    self._result(creationFiletime100ns=value),
                    "invalid owned creation FILETIME",
                )

    def test_missing_creation_filetime_is_refused(self) -> None:
        self._assert_refused(
            self._result(drop=("creationFiletime100ns",)),
            "missing owned identity fields: creationFiletime100ns",
        )

    def test_setup_flags_must_be_exactly_true(self) -> None:
        for name in ("createdSuspended", "assignedBeforeResume"):
            for value in (False, 0, 1, "true", None):
                with self.subTest(field=name, value=value):
                    self._assert_refused(
                        self._result(**{name: value}),
                        "unconfirmed owned setup: " + name,
                    )

    def test_missing_setup_flag_is_refused(self) -> None:
        for name in ("createdSuspended", "assignedBeforeResume"):
            with self.subTest(field=name):
                self._assert_refused(
                    self._result(drop=(name,)),
                    "missing owned identity fields: " + name,
                )

    def test_root_exit_code_needs_an_explicit_integer_zero(self) -> None:
        for value in (False, True, None, 1, -1, 0.0, "0"):
            with self.subTest(value=value):
                self._assert_refused(
                    self._result(exitCode=value),
                    "owned root exit was not zero",
                )

    def test_owned_active_count_needs_an_explicit_integer_zero(self) -> None:
        for value in (False, True, None, 1, -1, 0.0):
            with self.subTest(value=value):
                self._assert_refused(
                    self._result(jobActiveProcesses=value),
                    "owned active count",
                )

    def test_gate_exit_needs_an_explicit_integer_zero(self) -> None:
        for value in (False, True, None, 1, "0", 0.0):
            with self.subTest(value=value):
                result = gate_result()
                result["exit"] = value
                self._assert_refused(result, "gate exit")

    def test_terminal_must_be_exactly_true(self) -> None:
        for value in (False, 1, "true", None):
            with self.subTest(value=value):
                self._assert_refused(
                    self._result(terminal=value),
                    "owned root was not terminal",
                )

    def test_empty_job_must_be_exactly_true(self) -> None:
        for value in (False, 1, None):
            with self.subTest(value=value):
                result = gate_result()
                result["emptyJob"] = value
                self._assert_refused(result, "not empty")

    def test_missing_process_record_is_refused(self) -> None:
        self._assert_refused({"emptyJob": True, "exit": 0},
                             "missing owned process record")


class RunControlsTests(ControlPatchMixin, unittest.TestCase):
    """The control loop must be fail-fast and must report only what it observed."""

    def _run(self, runner, factory=None, deadline_offset=77.0,
             helper_hash=None, digest_value=None):
        started = self.clock.now
        deadline = started + deadline_offset
        report = controls.run_controls(
            fake_coordinator(runner, factory, helper_hash, digest_value),
            self.run_dir,
            deadline,
        )
        return started, deadline, report

    def test_clean_set_passes_with_all_owned_jobs_empty(self) -> None:
        runner = FakeRunner()
        started, deadline, report = self._run(runner, lambda: FakeJob())
        self.assertTrue(report["passed"], report["problems"])
        self.assertTrue(report["allOwnedJobsEmpty"])
        self.assertTrue(report["controlsComplete"])
        self.assertEqual(report["status"], controls.TERMINAL_STATUS)
        self.assertEqual(report["controlsExecuted"], 4)
        self.assertEqual(report["controlsPlanned"], 4)
        self.assertFalse(report["stopSubsequent"])
        self.assertFalse(report["timingExceeded"])
        self.assertFalse(report["deadlineExceeded"])
        self.assertEqual([c["name"] for c in report["controls"]],
                         ["normal-exit", "orphan-children", "held-handles",
                          "timeout-cleanup"])

    def test_live_child_is_refused_by_both_controls(self) -> None:
        runner = FakeRunner()
        _, _, report = self._run(runner, lambda: FakeJob(drain=True, live=2))
        self.assertTrue(report["passed"], report["problems"])
        by_name = {c["name"]: c for c in report["controls"]}
        orphan = by_name["orphan-children"]
        self.assertFalse(orphan["decision"]["released"])
        self.assertTrue(
            any("survived" in reason for reason in orphan["decision"]["reasons"])
        )
        self.assertEqual(orphan["problems"], [])
        held = by_name["held-handles"]["observations"]
        self.assertGreaterEqual(held["liveOwnedChildren"], 2)
        self.assertFalse(held["decisionWhileLive"]["released"])
        self.assertEqual(held["finalActive"], 0)
        self.assertTrue(held["decisionAfterDrain"]["released"])

    def test_unconfirmed_cleanup_forbids_subsequent_controls(self) -> None:
        runner = FakeRunner()
        _, _, report = self._run(runner, lambda: FakeJob(drain=False, live=2))
        self.assertFalse(report["passed"])
        self.assertEqual(report["status"], controls.HOLD_STATUS)
        self.assertTrue(report["stopSubsequent"])
        self.assertFalse(report["allOwnedJobsEmpty"])
        self.assertFalse(report["controlsComplete"])
        self.assertEqual(report["controlsExecuted"], 3)
        executed = [call["control"] for call in runner.calls]
        self.assertEqual(executed, ["normal-exit", "orphan-children"])
        self.assertFalse((self.run_dir / "controls" / "timeout-cleanup.log").exists())
        self.assertTrue(
            any("unconfirmed" in problem for problem in report["problems"])
        )

    def test_ordinary_failure_stays_failed_and_stops(self) -> None:
        runner = FakeRunner({"normal-exit": gate_result(gate_exit=1)})
        _, _, report = self._run(runner)
        self.assertFalse(report["passed"])
        self.assertTrue(report["stopSubsequent"])
        self.assertEqual(report["controlsExecuted"], 1)
        self.assertFalse(report["controlsComplete"])
        # Cleanup of the one control that ran is still proven and reported.
        self.assertTrue(report["allOwnedJobsEmpty"])
        self.assertEqual(report["status"], controls.TERMINAL_STATUS)
        self.assertEqual([call["control"] for call in runner.calls], ["normal-exit"])
        self.assertTrue(
            any("fail-fast" in problem for problem in report["problems"])
        )

    def test_helper_identity_mismatch_runs_nothing(self) -> None:
        runner = FakeRunner()
        _, _, report = self._run(
            runner, lambda: FakeJob(), helper_hash="expected", digest_value="actual"
        )
        self.assertFalse(report["passed"])
        self.assertTrue(report["stopSubsequent"])
        self.assertEqual(report["controlsExecuted"], 0)
        self.assertEqual(runner.calls, [])
        self.assertTrue(
            any("helper identity changed" in problem for problem in report["problems"]),
            report["problems"],
        )

    def test_control_slice_is_exactly_ten_seconds(self) -> None:
        runner = FakeRunner()
        started, deadline, report = self._run(runner, lambda: FakeJob())
        self.assertAlmostEqual(report["controlDeadlineMonotonic"] - started, 10.0,
                               places=6)
        self.assertEqual(report["plan"]["controlSeconds"], 10.0)
        for call in runner.calls:
            self.assertLessEqual(call["workDeadline"],
                                 report["controlDeadlineMonotonic"])
            self.assertLessEqual(call["cleanupDeadline"],
                                 report["controlDeadlineMonotonic"])
            self.assertLessEqual(call["workDeadline"], deadline)

    def test_control_slice_is_clamped_by_a_tighter_caller_deadline(self) -> None:
        runner = FakeRunner()
        started, deadline, report = self._run(
            runner, lambda: FakeJob(), deadline_offset=10.5
        )
        self.assertAlmostEqual(report["controlDeadlineMonotonic"] - started, 9.5,
                               places=6)
        self.assertTrue(report["passed"], report["problems"])

    def test_caller_deadline_that_cannot_fit_the_slice_runs_nothing(self) -> None:
        runner = FakeRunner()
        _, _, report = self._run(runner, lambda: FakeJob(), deadline_offset=10.4)
        self.assertFalse(report["passed"])
        self.assertEqual(report["status"], controls.HOLD_STATUS)
        self.assertTrue(report["stopSubsequent"])
        self.assertEqual(report["controlsExecuted"], 0)
        self.assertEqual(runner.calls, [])

    def test_budget_below_reserve_runs_nothing(self) -> None:
        runner = FakeRunner()
        _, _, report = self._run(runner, lambda: FakeJob(), deadline_offset=1.0)
        self.assertFalse(report["passed"])
        self.assertEqual(report["controlsExecuted"], 0)
        self.assertEqual(runner.calls, [])

    def test_overrunning_the_slice_fails_the_window(self) -> None:
        def burn(control, runner):
            if control == "normal-exit":
                self.clock.advance(11.0)

        runner = FakeRunner(on_call=burn)
        _, _, report = self._run(runner, lambda: FakeJob())
        self.assertFalse(report["passed"])
        self.assertTrue(report["timingExceeded"])
        self.assertTrue(report["sliceExceeded"])
        self.assertTrue(report["stopSubsequent"])
        self.assertTrue(
            any("exceeded its bound" in problem for problem in report["problems"])
        )


class FinalizeControlsTests(ControlPatchMixin, unittest.TestCase):
    """The 10-second bound and the caller deadline must be exact."""

    def _report(self, *, started=None, **overrides):
        report = {
            "schemaVersion": 1,
            "kind": "owned-job-control",
            "status": controls.TERMINAL_STATUS,
            "passed": True,
            "allOwnedJobsEmpty": True,
            "controlsComplete": True,
            "controlsExecuted": 4,
            "controlsPlanned": 4,
            "deadlineExceeded": False,
            "sliceExceeded": False,
            "timingExceeded": False,
            "stopSubsequent": False,
            "startedMonotonic": self.clock.now if started is None else started,
            "elapsedSeconds": 1.0,
            "controls": [],
            "problems": [],
        }
        report.update(overrides)
        return report

    def test_in_bound_window_keeps_the_pass(self) -> None:
        report = self._report()
        self.clock.advance(2.0)
        controls.finalize_controls(report, self.clock.now + 60.0)
        self.assertTrue(report["passed"])
        self.assertFalse(report["timingExceeded"])
        self.assertAlmostEqual(report["totalSeconds"], 2.0, places=6)

    def test_exactly_ten_seconds_is_not_exceeded(self) -> None:
        report = self._report()
        self.clock.advance(10.0)
        controls.finalize_controls(report, self.clock.now + 60.0)
        self.assertFalse(report["timingExceeded"])
        self.assertTrue(report["passed"])

    def test_ten_seconds_plus_epsilon_is_exceeded(self) -> None:
        report = self._report()
        # The module rounds the total to 3 places, so the epsilon must survive
        # that rounding: 10.001 rounds to 10.001 and exceeds 10.0.
        self.clock.advance(10.001)
        controls.finalize_controls(report, self.clock.now + 60.0)
        self.assertEqual(report["totalSeconds"], 10.001)
        self.assertTrue(report["timingExceeded"])
        self.assertFalse(report["passed"])
        self.assertTrue(report["stopSubsequent"])

    def test_absolute_deadline_is_enforced(self) -> None:
        report = self._report()
        self.clock.advance(1.0)
        controls.finalize_controls(report, self.clock.now - 0.001)
        self.assertTrue(report["deadlineExceeded"])
        self.assertTrue(report["timingExceeded"])
        self.assertFalse(report["passed"])

    def test_report_write_cost_is_inside_the_bound(self) -> None:
        report = self._report()
        controls.finalize_controls(report, self.clock.now + 60.0,
                                   report_write_seconds=0.25)
        self.assertEqual(report["reportWriteSeconds"], 0.25)
        self.assertTrue(report["passed"])

    def test_unconfirmed_cleanup_forces_hold(self) -> None:
        report = self._report(allOwnedJobsEmpty=False, controlsComplete=False)
        controls.finalize_controls(report, self.clock.now + 60.0)
        self.assertEqual(report["status"], controls.HOLD_STATUS)
        self.assertFalse(report["passed"])

    def test_prior_problems_never_regain_a_pass(self) -> None:
        report = self._report(problems=["earlier failure"])
        controls.finalize_controls(report, self.clock.now + 60.0)
        self.assertFalse(report["passed"])

    def test_prior_failure_flag_stays_failed(self) -> None:
        report = self._report(passed=False)
        controls.finalize_controls(report, self.clock.now + 60.0)
        self.assertFalse(report["passed"])


class CoordinatorFinalizeTests(ControlPatchMixin, unittest.TestCase):
    """Both report writes must be charged to the same bound."""

    def _wire(self, io_cost: float) -> list:
        writes: list[Path] = []

        def fake_write_json(path, value):
            writes.append(Path(path))
            self.clock.advance(io_cost)

        coordinator.write_json = fake_write_json
        return writes

    def _controls_report(self, **overrides):
        report = {
            "passed": True,
            "allOwnedJobsEmpty": True,
            "controlsComplete": True,
            "controlsExecuted": 4,
            "controlsPlanned": 4,
            "status": controls.TERMINAL_STATUS,
            "stopSubsequent": False,
            "timingExceeded": False,
            "sliceExceeded": False,
            "deadlineExceeded": False,
            "startedMonotonic": self.clock.now,
            "controlDeadlineMonotonic": self.clock.now + 10.0,
            "elapsedSeconds": 0.5,
            "controls": [],
            "problems": [],
        }
        report.update(overrides)
        return report

    def _call(self, controls_report, *, slice_seconds=10.0, work_seconds=77.0):
        started = self.clock.now
        run_report = {"controls": controls_report}
        coordinator.finalize_control_reports(
            controls,
            run_report,
            self.run_dir,
            self.run_dir / "run.json",
            started,
            started + work_seconds,
            started + slice_seconds,
        )
        return run_report

    def test_four_writes_inside_the_slice_pass(self) -> None:
        writes = self._wire(2.0)  # 4 writes x 2.0 = 8.0 < 10.0
        run_report = self._call(self._controls_report())
        self.assertEqual(len(writes), 4)
        self.assertTrue(run_report["controls"]["passed"])
        self.assertFalse(run_report["controls"]["timingExceeded"])

    def test_four_writes_exactly_at_ten_seconds_pass(self) -> None:
        self._wire(2.5)  # 4 x 2.5 = 10.0, not greater than the slice
        run_report = self._call(self._controls_report())
        self.assertTrue(run_report["controls"]["passed"],
                        run_report["controls"]["problems"])

    def test_four_writes_just_over_ten_seconds_stop_validation(self) -> None:
        self._wire(2.5 + 1e-6)
        with self.assertRaises(RuntimeError):
            self._call(self._controls_report())

    def test_absolute_deadline_after_writes_stops_validation(self) -> None:
        self._wire(0.5)
        with self.assertRaises(RuntimeError):
            self._call(self._controls_report(), work_seconds=1.0)

    def test_prior_timing_failure_is_sticky(self) -> None:
        self._wire(0.1)
        with self.assertRaises(RuntimeError):
            self._call(self._controls_report(timingExceeded=True,
                                             stopSubsequent=True))

    def test_incomplete_controls_stop_validation(self) -> None:
        self._wire(0.1)
        with self.assertRaises(RuntimeError):
            self._call(self._controls_report(controlsComplete=False))

    def test_unknown_cleanup_stops_validation(self) -> None:
        self._wire(0.1)
        with self.assertRaises(RuntimeError):
            self._call(self._controls_report(allOwnedJobsEmpty=False))

    def test_drained_failure_keeps_cleanup_proof_stopped(self) -> None:
        self._wire(0.1)
        target = self._controls_report(passed=False, stopSubsequent=True,
                                       problems=["control failed"])
        with self.assertRaises(RuntimeError):
            self._call(target)
        self.assertFalse(target["passed"])
        self.assertTrue(target["allOwnedJobsEmpty"])


class PendingReleaseTests(unittest.TestCase):
    """A pending release must never claim the release while the parent is live."""

    def setUp(self) -> None:
        self.source = COORDINATOR_PATH.read_text(encoding="utf-8")
        self.tree = ast.parse(self.source)

    def test_report_never_sets_released_true(self) -> None:
        found = 0
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if not isinstance(target, ast.Subscript):
                    continue
                key = target.slice
                if isinstance(key, ast.Constant) and key.value in (
                    "released", "passed", "readyForRootRelease"
                ):
                    found += 1
                    if key.value == "released":
                        self.assertIs(
                            getattr(node.value, "value", object()), False,
                            "released is assigned a non-False value",
                        )
                    if key.value == "passed":
                        self.assertIs(
                            getattr(node.value, "value", object()), False,
                            "passed is assigned a non-False value",
                        )
                    if key.value == "readyForRootRelease":
                        # Must be derived, never a constant True.
                        self.assertNotIsInstance(node.value, ast.Constant)
        self.assertGreater(found, 0, "no release fields were assigned at all")

    def test_only_pending_release_text_exists(self) -> None:
        self.assertIn("RELEASE_PENDING_PARENT_TERMINAL", self.source)
        self.assertIn("NO_SUCCESSOR_GRANT", self.source)
        literals = [
            node.value
            for node in ast.walk(self.tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        ]
        # A final release channel message would begin with this prefix. Guidance
        # strings that merely describe the root step do not.
        final_releases = [
            text for text in literals if text.startswith("Rust RELEASE ")
        ]
        self.assertEqual(final_releases, [],
                         "a final RELEASE channel message literal exists")
        # The publisher receives the pending message, not a final one.
        message_start = self.source.index("message = (") if "message = (" in self.source else -1
        if message_start >= 0:
            self.assertIn(
                "RELEASE_PENDING_PARENT_TERMINAL",
                self.source[message_start:message_start + 200],
            )

    def test_report_requires_root_finalization(self) -> None:
        self.assertIn('"rootFinalizationRequired": True', self.source)
        self.assertIn('"readyForRootRelease": False', self.source)

    def test_active_marker_is_not_removed_by_the_coordinator(self) -> None:
        removals = []
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "attr", None)
            if name in ("rmdir", "unlink"):
                removals.append((name, node.lineno))
        # The only removal is the rollback of a just-created empty marker.
        self.assertLessEqual(len(removals), 1, removals)
        for _, lineno in removals:
            context = "\n".join(self.source.splitlines()[lineno - 6:lineno + 1])
            self.assertIn("consumed", context.lower() + context,
                          f"unexpected marker removal at line {lineno}")

    def test_finalize_gate_precedes_validation_selection(self) -> None:
        finalize_at = self.source.index("finalize_control_reports(")
        native_at = self.source.index('if args.mode == "Native":')
        self.assertLess(finalize_at, native_at)


class CoordinatorContractTests(unittest.TestCase):
    """The controls module keeps the API the coordinator calls."""

    def test_run_controls_signature_matches_the_coordinator_call(self) -> None:
        import inspect

        signature = inspect.signature(controls.run_controls)
        self.assertEqual(
            list(signature.parameters), ["coordinator", "run_dir", "absolute_deadline"]
        )
        self.assertIn(
            "run_controls(sys.modules[__name__], run, work_deadline)",
            COORDINATOR_PATH.read_text(encoding="utf-8"),
        )

    def test_finalize_controls_signature_matches_the_coordinator_call(self) -> None:
        import inspect

        signature = inspect.signature(controls.finalize_controls)
        self.assertEqual(
            list(signature.parameters),
            ["report", "absolute_deadline", "report_write_seconds"],
        )

    def test_control_slice_constant_is_ten_seconds(self) -> None:
        self.assertEqual(controls.CONTROL_SECONDS, 10.0)
        self.assertEqual(controls.CONTROL_COUNT, 4)

    def test_twenty_checks_were_owned_elsewhere_and_this_file_adds_more(self) -> None:
        # Reuse note: the coordinator's twenty ad hoc checks covered run_owned,
        # marker and sticky-flag behaviour. This file keeps durable coverage of
        # the controls module plus the coordinator finalize/release contracts.
        note = (REPO / ".trellis/tasks/10-22-offline-ide-completeness/research"
                / "runner-integration-current.md")
        if note.is_file():
            text = note.read_text(encoding="utf-8")
            self.assertIn("Twenty pure FakeJob", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)