# Runner integration source review, 2026-10-26

Status: implementation complete for root review. Runtime controls, Native90 and
Dart110 remain UNRUN. This note is not an ACCEPT, execution grant or RELEASE.
Old grant556 is consumed. Root published DEFER592. no historical grant is reused.

## Source boundary

Changed only the Rust coordinator and this note. The PS launcher is unchanged.
Pi p3 owns `rust_runner_controls.py`. this integration does not edit that module,
the Job helper, publisher, Linux supervisor, application source or shared core.
No native, SDK, WSL, device, real Job/process control or OS signal test ran.
No active marker was removed. No commit or push was made.

## Integration and deadline behavior

The coordinator passes its actual module object through
`run_controls(sys.modules[__name__], run, work_deadline)`. It hashes and snapshots
the controls module. Controls share the existing Native90 or separate Dart110
clock and have a caller-enforced maximum ten-second slice. There is no extra
control window and no automatic chaining between modes.

`finalize_control_reports` writes both controls.json and run.json, calls
`finalize_controls(report, absolute_deadline, report_write_seconds=...)`, persists
the finalized state, and calls the finalizer again. The coordinator then compares
an unrounded monotonic observation against the caller slice, the module's tighter
slice when present, and the absolute work deadline. Both pairs of report writes
are therefore checked before any validation Job can start. Diagnostic writes
following a failure cannot restore permission to run validation.

Prior timingExceeded, sliceExceeded, deadlineExceeded and stopSubsequent failures
are sticky, even if the module replaces a field during finalization. Incomplete
controls or any failed assertion also stop validation. allOwnedJobsEmpty remains
independent of pass/fail, so a drained failed check can retain cleanup proof.
Unknown cleanup prevents all subsequent Jobs, including the publisher.

`run_owned` queries membership before observing time. A terminal/empty observation
completed after the work deadline fails with124. Cleanup observation, handle-close
and terminal-reporting time are checked independently. Expired work creates no
Job. Membership-query failure retains unknown cleanup and returns125/HOLD.

## Release and marker contract

The coordinator reports RELEASE_PENDING_PARENT_TERMINAL / NO_SUCCESSOR_GRANT,
never final RELEASE. released and passed stay false. The active marker survives
coordinator completion. Only root may observe the exact outer exec handle terminal,
verify runId/grant/report/process-creation identity and empty Jobs, publish actual
final RELEASE, then remove the exact matching marker. Consumed-grant evidence stays.
The only coordinator rmdir is rollback of a newly created, still-empty marker if
creation of the consumed-grant directory fails.

## Budgets and scope

Native total90: work ends at77, initial source snapshot cap6, controls cap10,
native budget dynamically reduced to remaining work minus2 (maximum76), including
its15-second cleanup reserve. Full ordinary/analysis/debugger/filesystem scope is
preserved in the existing native entry point and supervisor.

Dart total110 is a separate grant: work ends at97. format cap8, scoped analysis
cap30, serial focused regression cap62 are each clamped by the common work end.
The debugger/feature/workspace scope remains42+15+5=62 tests. These phase caps
are not additive guaranteed allocations. Cleanup ends at total minus9. snapshots,
pending publication and reporting share the same remaining total clock.

The inner clock starts at MODULE_STARTED. Python/PS startup before that point and
root terminal observation/final release are outside the inner measurement. Root
must measure the entire outer window before claiming a bounded whole-window pass.
Inner boundedValidationPassed alone does not establish that claim.

## Source-only verification

AST parsing passed. Controlled-language mechanical lint passed for this note. Twenty pure FakeJob/fake-clock checks passed using extracted
functions. no real Job or child process was started:

- Natural empty. late natural query. late cleanup query. orphan drain.
- Expired work creates no Job. terminal-report overrun. close overrun. query exception HOLD.
- Both reports finalized. second persistence overrun. unrounded submillisecond overrun.
- Sticky timingExceeded, sliceExceeded, deadlineExceeded and stopSubsequent.
- Independent unknown cleanup. drained assertion failure. tighter module deadline.
- Absolute deadline after writes. incomplete controls stop validation.

Static lifecycle checks passed: no final-release text, explicit released=false,
no successful marker removal, controls snapshot binding, exact same-module API,
and finalized-report gate before validation selection. During these checks an
initial failure exposed module reset of a prior deadlineExceeded flag. the caller
now preserves that failure, and the full twenty-check set passed afterward.

Remaining gates: root review of this exact source set, a fresh current named grant,
actual owned controls within that grant, actual validation and cleanup evidence,
source-before/source-after identity equality, and root-observed terminal release.
No runtime PASS or endpoint availability is inferred from the pure checks.

## Observed SHA-256 identities

- `run-rust-owned-window.py`: `0f83fc7105c162c44479c68eb234744161e385ece40800afd2e21b8a96a14c12`
- `run-reserved-validation.ps1`: `ac466736f5d0cbd5160567300543b8137adc7eb1ef49b7c52cd48cfd46bb483b`
- `rust_owned_job.py`: `c0520616e6777d9587a6c0004487bd06a1b19b7d202563f8292c4c1a32c6b172`
- `rust_runner_controls.py`: `68b1b0854f94c9ef936c1c2fb253b2fc4d860ccef1bce9e9381bd74e604c8795`
- `run-native-validation-current.sh`: `9e4ea59dcaf6b221388f2caaa5f9ce5eb0a16284a5c8533fc7aeb5736ffed338`
- `native-group-supervisor.py`: `1624ea21ddab857429f4289981ea4e2145f8cdc734316f01ed372fbd1ab72f9c`
- `publish-rust-release.ps1`: `9bc54c9e200cf4a207251cf1be41fc9a9dfd1d20ca1122860ac04e07586047e1`
