# Pure controls tests with a fake clock and fake Jobs

Source-only test preparation, reviewed 2026-10-26. No real Job, child process,
native library, SDK, build, WSL or device was used. The durable suite runs with
plain `unittest` and synthetic collaborators only.

This note and the test file are the only paths owned here. The controls module
was edited by root; this work does not edit it, the coordinator, the frozen Job
helper, the launcher, the publisher, the Linux supervisor, application source or
shared core. No commit or push was made. C646 holds the host slot and Rust654 is
deferred, so nothing here starts a host window.

## Identity-gap fix that changed the target

Root closed the independent final-review identity gap in the controls module.
The module hash is now
`29526215ade5f3ff40bf0f9488912b35d3f698fe089a5e7d253c40c5857e1f99`, not the
older `68b1b0854f94c9ef936c1c2fb253b2fc4d860ccef1bce9e9381bd74e604c8795`.
Every check below was re-run against the current bytes.

`release_decision` now requires positive evidence for every field:

- `pid` and `threadId` need `type(value) is int` and `0 < value <= 0xFFFFFFFF`.
- `creationFiletime100ns` needs a `str` of at most 20 ASCII decimal digits with
  `0 < int(value) <= 0xFFFFFFFFFFFFFFFF`.
- `createdSuspended` and `assignedBeforeResume` need exactly `True`.
- `exitCode` (root exit), `jobActiveProcesses` (active count) and the result
  `exit` (gate exit) each need an explicit `int` equal to `0`.
- `terminal` and `emptyJob` need exactly `True`.

`False` is no longer accepted as a zero. A boolean, float, string, `None`, zero,
negative, oversized or missing value is refused with a named reason.

## The durable file

`build/offline-ide-audit/test_runner_controls_pure.py`, 58 tests, run with:

```text
python -m unittest discover -s build/offline-ide-audit -p test_runner_controls_pure.py
```

Fakes used, all in-process:

- `FakeClock` replaces the `time` module in both the controls module and the
  coordinator, so every deadline boundary is exact and repeatable. Its `sleep`
  and `advance` move the clock; nothing else does.
- `FakeJob` is an owned-Job stand-in with an explicit `record`, `start`, `empty`,
  `stop` and `close`. It never creates a real Job.
- `FakeRunner` is a `run_owned` stand-in that records the work and cleanup
  deadlines it was given and returns coordinator-shaped results.
- `fake_coordinator` is a namespace exposing `run_owned`, `OwnedJob`, `digest`,
  `HELPER_HASH`, `HERE` and `REPO`.
- `FakeJob`, `FakeRunner` and the coordinator patch are scoped by a mixin that
  restores the real `time` and `write_json` in `tearDown`.

## Coverage

| Class | Tests | Focus |
| --- | --- | --- |
| `ReleaseDecisionTests` | 9 | missing record, each missing identity field, missing or nonzero active count, non-terminal root, clean accept, live-child refusal, timeout/error/exit refusal, `gate_safe` mirror |
| `ReleaseEvidenceTests` | 14 | valid fixture accept, identity boundaries, null/false/zero/negative/oversized/missing `pid` and `threadId`, creation FILETIME rules, setup flags exactly true, explicit integer zeros for root exit, active count and gate exit, `terminal` and `emptyJob` exactly true |
| `RunControlsTests` | 10 | clean set passes, live child refused by both controls, unconfirmed cleanup forbids subsequent controls, ordinary failure stays failed, helper identity mismatch runs nothing, ten-second slice, tighter caller deadline, window too short to fit, budget below reserve, overrun fails the window |
| `FinalizeControlsTests` | 8 | in-bound pass, exactly ten seconds not exceeded, ten seconds plus epsilon exceeded, absolute deadline, report-write cost, unconfirmed cleanup hold, prior problems never regain a pass, prior failure flag stays failed |
| `CoordinatorFinalizeTests` | 8 | four writes inside the slice, four writes exactly at the bound, just-over bound stops validation, absolute deadline after writes, sticky prior timing failure, incomplete controls, unknown cleanup, drained failure keeps cleanup proof |
| `PendingReleaseTests` | 5 | no `released`/`passed` True assignment, only pending-release text, root finalization required, no coordinator marker removal, finalize gate precedes validation selection |
| `CoordinatorContractTests` | 4 | `run_controls` signature matches the coordinator call, `finalize_controls` signature, ten-second constant and four controls, reused ad-hoc note present |

## Required behaviours, where they are proven

- Missing ownership or active count rejected: `ReleaseDecisionTests` plus the
  `ReleaseEvidenceTests` null/false/zero/negative/oversized/missing matrix.
- Live child refuses: `test_live_child_is_refused_by_both_controls` asserts the
  orphan decision is refused with a survivor reason and the held-control
  `decisionWhileLive` is refused at two live children.
- Clean terminal accepts: `test_clean_terminal_result_is_accepted` and
  `test_the_valid_fixture_is_accepted`.
- Unconfirmed cleanup forbids subsequent controls: the unconfirmed test shows
  `controlsExecuted == 3`, no `timeout-cleanup` log exists, `status` is
  `hold_cleanup_unconfirmed`, and `allOwnedJobsEmpty` is false.
- Ordinary failure stays failed: the drained failure runs one control, keeps
  `allOwnedJobsEmpty` true, and still reports `passed` false with fail-fast.
- Ten-second slice and caller deadline including report I/O: the slice tests
  check `controlDeadlineMonotonic - started == 10.0`, the tighter deadline
  yields exactly `9.5`, and the coordinator tests charge four report writes at
  `2.5` seconds each, where `10.0` exactly passes and `10.0 + epsilon` stops
  validation.
- Pending release stays not released while the outer parent is unobserved:
  `PendingReleaseTests` asserts no assignment sets `released` or `passed` true,
  no final-release channel message literal exists, root finalization is required,
  and the only marker removal is the consumed-grant rollback.

## Reuse of the coordinator's ad-hoc checks

`research/runner-integration-current.md` recorded twenty ad-hoc `FakeJob` and
fake-clock checks of the coordinator side: natural and late empty queries,
orphan drain, expired work creating no Job, terminal-report and close overruns,
query-exception HOLD, both reports finalized, second-persistence overrun,
unrounded submillisecond overrun, sticky flags, independent unknown cleanup,
drained assertion failure, tighter module deadline, absolute deadline after
writes and incomplete controls.

Those checks were not retained as a durable file. This suite keeps durable
coverage of the listed behaviours and adds the controls-module identity-evidence
matrix the ad-hoc set did not cover. The coordinator finalize tests here
re-express the report-write timing and sticky-flag gaps durably.

## Results

`python -m unittest discover -s build/offline-ide-audit -p test_runner_controls_pure.py`

```text
Ran 58 tests in 0.059s
OK
```

Two consecutive discover runs both reported `Ran 58 tests` and `OK`, so the
suite is deterministic and free of real-time flakiness. `ast.parse` accepted
both the test file and the controls module. A grep for `subprocess`, `Popen`,
`CreateProcess`, `WinDLL`, `os.kill`, `wsl`, `dart`, `flutter`, `pwsh` and the
real helper matched only the module docstring line that says none is used.

### Mutation teeth

A transient script (created, run, deleted) mutated the current module source in
memory and confirmed the suite would fail against a regression:

| Regression | Baseline | Mutant |
| --- | --- | --- |
| Boolean gate exit refused | released false | released true |
| Boolean root exit refused | released false | released true |
| Boolean active count refused | released false | released true |
| Float `pid` refused | released false | n/a |

The mutant relaxed the three explicit-integer-zero rules and the identity int
rule. Baseline refused all four; the mutant released the three boolean cases.
The durable suite asserts the baseline behaviour, so it catches that regression.

## Remaining verification

Not performed and not claimed:

- Any real Job, child process, compiler, SDK, build, WSL or device action.
- Any owned-Job behaviour on a real host, including that two sleeping
  descendants remain in a real Job after the root exits.
- Any OHOS packaged execution evidence.
- Any runtime PASS, endpoint availability or release grant.

These tests are a pure logic and lifecycle control. They do not substitute for
the pinned native ABI suite, the fresh catalog inventory, the packaged HAP or
real OHOS execution evidence.

## Observed SHA-256 identities

| File | SHA-256 |
| --- | --- |
| `test_runner_controls_pure.py` (this work) | `6addcf4514042dfd9eae13f71df749b2ad17a22cf6f79956be6ddce241443737` |
| `rust_runner_controls.py` (root edit, read-only here) | `29526215ade5f3ff40bf0f9488912b35d3f698fe089a5e7d253c40c5857e1f99` |
| `run-rust-owned-window.py` (other writer) | `0f83fc7105c162c44479c68eb234744161e385ece40800afd2e21b8a96a14c12` |
| `rust_owned_job.py` (frozen) | `c0520616e6777d9587a6c0004487bd06a1b19b7d202563f8292c4c1a32c6b172` |