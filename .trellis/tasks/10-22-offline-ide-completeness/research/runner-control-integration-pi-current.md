# Owned-Job controls inside a granted validation clock

Source preparation only, reviewed 2026-10-26. Nothing here was executed. No
WSL, SDK, Dart, Flutter, native, build, device, process-control or Job-control
command was started. Only `ast.parse` and the JSON dry plan were run.

## Correction from the previous revision

The previous revision proposed a standalone 45-second control window and a host
sequence that chained Native90 with Dart110 under one authorization. Both are
wrong and are withdrawn:

- A control window is not an authorization. Nothing in this work grants time.
- Native90 and Dart110 are separate grants. They are never chained.
- A control needs no clock of its own, because it runs inside the clock the root
  already holds.

## Corrected model

Controls run **first inside each granted window**, on that window's single
existing deadline, before the validation step of the same window.

- The root passes its own absolute `time.monotonic()` deadline to
  `run_controls`. That deadline already exists in the coordinator as
  `deadline = started + 90` (Native) or `started + 110` (Dart).
- Controls take a slice of that window and return it. They never create, extend
  or reopen a clock.
- A failed control returns `passed=false` and `stopSubsequent=true`. The caller
  must then stop the rest of that window and must not start validation.
- The loop is fail-fast. An unconfirmed owned cleanup stops the run immediately
  with HOLD and no further Job is created. A control that drained but failed an
  assertion also stops the run.
- `allOwnedJobsEmpty` describes only the controls that ran. It never turns
  unknown merely because fewer than four controls ran.
- A control pass carries no lane release. The release decision for the window
  remains the coordinator's own predicate over the real validation result.

## Change boundary

Owned paths are two files:

- `build/offline-ide-audit/rust_runner_controls.py` — control module.
- this note.

Not touched: the frozen helper `rust_owned_job.py`, the coordinator
`run-rust-owned-window.py`, the PowerShell entry, the publisher, the native
Linux supervisor, shipping Dart/native sources, shared core, README files,
signing inputs and device state. Wiring the module into the coordinator is a
root-owned change and is described here as an API, not performed.

Measured identities, unchanged:

| File | SHA-256 |
| --- | --- |
| `rust_owned_job.py` (frozen) | `c0520616e6777d9587a6c0004487bd06a1b19b7d202563f8292c4c1a32c6b172` |
| `run-rust-owned-window.py` (coordinator, owned by another writer) | `d28e0ae423b68de65ba4b6370b92058cef9315b8ee7962ccee9220cd6c63fcac` |
| `rust_runner_controls.py` (this module) | `68b1b0854f94c9ef936c1c2fb253b2fc4d860ccef1bce9e9381bd74e604c8795` |

The coordinator hash moved from `6aae56e3e341ba0961aa9895a00cc2743ffcc7f9eae23526b54f1e531745cd276a`
to `d28e0ae423b68de65ba4b6370b92058cef9315b8ee7962ccee9220cd6c63fcac` in a
separate coordinator change owned by another writer. This note does not edit
that file. The frozen helper bytes did not change.

The helper hash equals the coordinator's `HELPER_HASH`, so the identity gate
still passes. The coordinator's `snapshot()` hashes a fixed list of
`build/offline-ide-audit` files that does not include the control module, so
adding it changes no recorded validation source identity. The control module
reads the coordinator only through the passed object; a coordinator change
does not require editing this module.

## Integration API

Two fixed functions, no side effects at import:

```python
def run_controls(coordinator, run_dir, absolute_deadline) -> dict
def finalize_controls(report, absolute_deadline, report_write_seconds=None) -> dict
```

The coordinator currently calls the first one as:

```python
controls = controls_module.run_controls(sys.modules[__name__], run, work_deadline)
```

That is the coordinator module itself, the run directory and the coordinator's
existing `work_deadline`. It matches the signature above. The coordinator then
performs the report-write recheck itself; `finalize_controls` is the module-side
equivalent and is available if the coordinator prefers to call it.

- `coordinator` is the loaded `run-rust-owned-window` module. The module calls
  its `run_owned`, its `OwnedJob`, its `digest`, its `HELPER_HASH`, its `REPO`
  and its `HERE`. It never edits the coordinator.
- `run_dir` is the caller's run directory. Control logs go to
  `run_dir / "controls"` and nowhere else.
- `absolute_deadline` is an absolute `time.monotonic()` bound the caller already
  holds, for example `deadline - 13` from the same window. The module clamps the
  slice with `min(CONTROL_SECONDS, absolute_deadline - now - REPORT_RESERVE_SECONDS)`
  and then against the caller's deadline again, so the caller's clock always
  wins and no second total clock exists.

Returned keys:

| Key | Meaning |
| --- | --- |
| `passed` | Controls passed, cleanup confirmed, the full set ran, and neither clock was exceeded |
| `allOwnedJobsEmpty` | Every control that ran proved a final owned active count of 0 |
| `controlsComplete` | All four controls ran with no slice exhaustion |
| `controlsExecuted` / `controlsPlanned` | Executed count and the four-entry plan |
| `deadlineExceeded` | `time.monotonic() > absolute_deadline` at return |
| `sliceExceeded` | Return happened after the 10-second control deadline |
| `timingExceeded` | Either of the two clocks was exceeded |
| `elapsedSeconds` / `totalSeconds` | Control time before the write, and total after it |
| `remainingGrantedSeconds` | Time left on the caller's deadline |
| `startedMonotonic` | Stamp `finalize_controls` measures the write against |
| `status` | `terminal` only when every executed cleanup is confirmed, otherwise `hold_cleanup_unconfirmed` |
| `stopSubsequent` | True whenever `passed` is False |
| `controls` | One entry per control with exact process and Job observations |
| `problems` | Every reason a control, the cleanup or the timing failed |
| `identities` | Measured helper SHA-256 against the coordinator's `HELPER_HASH` |
| `plan` | The slice table below |

The helper is imported through the coordinator, never copied, so the frozen
bytes stay frozen.

## Slice table

`CONTROL_SECONDS = 10.0` by default. `plan()` raises when the phases do not fit.

| Phase | Seconds | Cap source |
| --- | --- | --- |
| `normal-exit` | 1.5 | `PHASE_SECONDS` |
| `orphan-children` | 2.5 | `PHASE_SECONDS` |
| `held-handles` | 2.5 | `PHASE_SECONDS` |
| `timeout-cleanup` | 2.0 | `PHASE_SECONDS` |
| Phases total | 8.5 | sum |
| Report reserve | 1.0 | `REPORT_RESERVE_SECONDS` |
| Spare | 0.5 | 10.0 − 8.5 − 1.0 |

The slice is capped at `CONTROL_SECONDS = 10.0` and then re-clamped by
`absolute_deadline`. When the remaining window is under 9.5 seconds the module
returns `status=hold_cleanup_unconfirmed` before creating any Job.

The timeout control uses a 0.3-second work deadline
(`TIMEOUT_WORK_SECONDS`). The owned root sleeps 600 seconds, so the control
proves deadline enforcement instead of waiting for a program to finish.

## Single deadline clamping

`control_span = min(CONTROL_SECONDS, absolute_deadline - now - REPORT_RESERVE_SECONDS)`
and `control_deadline = now + control_span`, computed once at entry.

Every phase then uses `_phase_end(deadline, cap) = min(deadline, now + cap)`.
That clamp can only shorten a phase, never extend it. Concretely:

- `normal-exit`, `orphan-children` and `timeout-cleanup` pass the clamped phase
  end as both the work deadline and the cleanup deadline of `run_owned`. The
  final empty-process query inside `run_owned` therefore targets the same
  deadline.
- `held-handles` uses three clamped ends: the observe end, the post-stop drain
  end and the `finally` drain end. Its final `job.empty()` query runs against
  the drain end.
- The loop stops starting new controls once `control_deadline` is reached and
  records `control slice ended before all controls ran`.
- `deadlineExceeded` compares the caller's absolute deadline against the clock
  at return. `sliceExceeded` compares the control deadline against the same
  clock. `timingExceeded` is their union, plus a total above `CONTROL_SECONDS`.
  `passed` requires all of them false.
- `REPORT_RESERVE_SECONDS` covers the final empty-process queries.

## Report-write recheck

The control call cannot see the caller's report write. The coordinator measures
it after `write_json(run / "controls.json", controls)` with
`control_limit = min(work_deadline, control_started + 10.0)`. When the measured
write crosses that limit it sets `passed=false`, `deadlineExceeded=true` and
`stopSubsequent=true`, and records `control report write exceeded its shared
slice`. That is the bound in force today.

`finalize_controls` provides the same check inside this module for a caller that
prefers one call. It measures from the `startedMonotonic` stamp to its own call,
so the write cost is inside the bound. It records `totalSeconds`, optionally
`reportWriteSeconds`, and sets `deadlineExceeded`, `timingExceeded`, `status`
and `passed`. A total above `CONTROL_SECONDS`, a slice overrun, an exceeded
absolute deadline, an unconfirmed cleanup or any recorded problem clears
`passed` and sets `stopSubsequent`. A control window that overran the bound
never reports a pass.

## Real release refusal

`release_decision(result)` is the real gate predicate over explicit evidence.
It needs a present owned process record and these fields: `pid`, `threadId`,
`createdSuspended`, `assignedBeforeResume`, `terminal`, `exitCode` and
`jobActiveProcesses`. It also requires `terminal` true, `jobActiveProcesses`
exactly 0, `emptyJob` true, `exit` 0, and no timeout, orphan cleanup or harness
error. A record missing any field is refused, so a bare
`{"emptyJob": true, "exit": 0}` is never released. Each refusal carries the
reasons that produced it.

The controls prove the predicate both ways, so a refusal cannot be faked by a
constant:

- `normal-exit` asserts `release_decision(...).released` is **True** for a clean
  owned result.
- `orphan-children` asserts it is **False**, and that at least one reason
  mentions that owned children survived.
- `held-handles` asserts it is **False** while the live owned child count is at
  least 2, that a reason mentions live children, then after one owned
  termination request it asserts the count reached 0 and the same predicate is
  **True** again.

The module has no `releasePublished` field. A control is not a gate, so there is
nothing to publish and nothing is claimed about publication.

## Native90 arithmetic

The coordinator already fixes `seconds = 90`, `deadline = started + 90` and
`work_deadline = deadline - 13 = started + 77`. The pre-step source snapshot is
bounded to `started + 6`. The native slice is
`min(76, int(work_deadline - now) - 2)` with `--cleanup-seconds 15`.

| Case | Native slice | Linux cleanup | Approximate Linux work |
| --- | --- | --- | --- |
| Without controls | `min(76, int(77 - 6) - 2) = 69` | 15 | 54 |
| With a 10.0s control slice | `min(76, int(77 - 16) - 2) = 59` | 15 | 44 |

The reduction is the control slice itself, about 10 seconds. That is arithmetic
on the coordinator's own constants. The duration of the native build and ABI
suites was not measured in this source-only step.

If the root judges 44 seconds insufficient, the reviewed alternative is to drop
`held-handles` from the slice, which returns 2.5 seconds to the native step.
`orphan-children` is the control the source note explicitly requires and should
not be dropped.

## Dart110 arithmetic

The coordinator fixes `seconds = 110`, `deadline = started + 110` and
`work_deadline = deadline - 13 = started + 97`. The three steps declare 8, 30
and 62 seconds, which already total 100 against a 97-second work window.

Adding the control slice leaves `97 - 10 = 87` seconds for steps that declare
100. The loop then breaks on `time.monotonic() >= work_deadline` with exit 124,
so the Dart window would fail by construction, not because of a real defect.

This is a finding the root must resolve before granting a Dart window with
controls enabled. Reviewed options, in order of preference:

1. Re-declare the step caps to 8, 28 and 48 seconds. They total 84 and leave
   3 seconds of slack inside 87.
2. Run the control slice in the Native window only, as its own separately
   granted control, and leave the Dart step caps untouched.

The original 62-second test slice cannot coexist with a control slice inside 110
seconds. That arithmetic is the reason, not a preference.

## Refusals

`passed` requires all four control problems lists to be empty, `controlsComplete`
true, cleanup confirmed for every executed control, and `timingExceeded` false.
An unconfirmed cleanup returns `status=hold_cleanup_unconfirmed` with
`stopSubsequent=true` and creates no further Job. An exhausted slice, a drained
control failure or an exceeded clock returns `passed=false` with
`stopSubsequent=true`; `allOwnedJobsEmpty` still reports only what ran.

- The CLI rejects `--control-seconds` above `CONTROL_SECONDS` with status 2. The
  API takes no slice argument, so a caller cannot request a larger slice.
- No budget left inside the granted deadline: `passed=false` with
  `stopSubsequent=true` before any Job is created.
- A changed helper hash: recorded as a problem, and no control starts.
- A Job left non-empty, a nonzero final active count, a nonzero gate exit from a
  clean control, or a predicate that disagrees with observed state: `passed=false`.

## Remaining verification

Not performed and not claimed:

- Any execution of the four controls.
- Any WSL, native, SDK, Dart, Flutter, build or device command.
- Any measurement of native build, ABI suite or Dart test duration.
- That two sleeping descendants actually remain in the Job after the root exits
  on this host.
- Any OHOS packaged execution evidence.

Checks performed: `ast.parse` accepted the module, `plan()` returns the table
above and rejects an over-large slice, and the helper hash matches the
coordinator's expected `HELPER_HASH`.

Pure-logic checks were run on the two predicates without creating any Job:

- `release_decision({"emptyJob": true, "exit": 0})` refuses with a missing
  process record and missing identity fields.
- A complete clean record with `terminal` true and `jobActiveProcesses` 0 is
  released.
- A record missing only `jobActiveProcesses`, or with `terminal` false, or with
  a nonzero active count, is refused.
- An orphan result is refused with a reason that names surviving children.
- `finalize_controls` keeps a pass inside the bound, clears it past 10 seconds,
  clears it past the absolute deadline, clears it when cleanup is unconfirmed,
  and never keeps a pass that already carries problems.

These controls are a host process-cleanup control. They are not a substitute for
the pinned native ABI suite, the fresh catalog inventory, the packaged HAP or
real OHOS execution evidence.
