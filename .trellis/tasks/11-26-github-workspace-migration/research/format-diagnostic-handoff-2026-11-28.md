# Formatter diagnostic helper handoff (2026-11-28)

Status: FROZEN, source only, UNRUN.

This records the initial worker handoff. Independent review subsequently found
two preview-runner defects: buffered-pipe cleanup could block after the reader
join expired, and read errors could be mistaken for complete output. A narrow
coordinator-assigned repair supersedes that runner design. No executed pass is
claimed by either source handoff.

Model correction: Pi `w61:p2` confirmed `deepseek-v4.1-flash` in its environment,
despite the dispatched `gpt-6.1-sol` selection. It reported no sol attempt or
retry within that recovered session. The source is independently reviewed;
do not describe that Pi handoff as work executed on sol.

## Ownership and files

Worker `trellis-implement` edited only these two paths:

- `tool/ci/app_quality.py` (+286 lines, 0 deletions)
- `tool/ci/test_app_quality.py` (+319 lines, 0 deletions)

No workflow, spec, task, product Dart test or Git write was performed. Other
workers' edits in `.github/workflows/`, `.trellis/` and `test/` were preserved
untouched.

## What the helper now does

Bounded best-effort Dart format context for the literal allowlisted root test
files `test/rust_code_analyzer_test.dart`,
`test/rust_workspace_integration_test.dart` and
`test/rust_terminal_commands_test.dart`. Hosted run `46014152444` named the
analyzer and workspace test files. The terminal test is included because the
current fixture repair changes it; that run did not identify it as a format failure.

- `format_diagnostic_paths` accepts only the literal allowlist. A name must
  match `test/[A-Za-z0-9_]+\.dart`, stay inside the checkout, and not be a
  link. Missing allowlisted files are skipped, not invented.
- `format_preview_command` builds
  `dart format --output=show --show=none --summary=none <name>`.
  `--output=show` emits formatted source on stdout and never writes the file.
  `--show=none` and `--summary=none` suppress the other stdout lines. The exit
  code is untouched so a genuine formatter error stays a visible failure.
- `run_format_preview` gives the child no stdin, sends stderr to a private
  `RUNNER_TEMP` file, caps captured stdout at
  `MAX_FORMAT_DIAGNOSTIC_OUTPUT_BYTES` (256 KiB), and enforces one shared
  wall-clock deadline of `FORMAT_DIAGNOSTIC_TIMEOUT` (120 s). Overflow, timeout
  and nonzero exit each become a named failure rather than a pass.
- The diagnostic order is: read the input snapshot, redact it with
  `safe_diff_text`, redact the previewed source with `safe_diff_text`, then
  diff. `format_diff` normalizes line endings and end-of-file newlines so no
  hunk line is truncated and no `&&`/`||` artifact appears. The result is
  bounded to `MAX_FORMAT_DIAGNOSTIC_BYTES` (48 KiB).
- `write_format_failure_diagnostic` writes
  `build/app-quality/linux-x64/reports/format-diagnostic.txt`, prints it with
  `print_untrusted`, and annotates it. Every emission step swallows its own
  failure and no exception value is published.
- `execute_check` runs the diagnostic only for the `format` stage and only
  after `verify_prepared` succeeds. A drifted or mutated tree therefore skips
  the preview, because the preview would describe different bytes. The
  original strict failure is recorded in `manifest["checks"]["format"]` and
  re-raised unchanged.
- `publish_machine_summary` runs immediately after
  `reports/root-tests.json` is written. It prints counts, suite lists,
  unfinished ids and up to 30 redacted error strings as bounded JSON through
  `print_untrusted`. It publishes no raw protocol field, no `rawReportSha256`,
  no test names and no VM service URI. `success` in the public record is
  derived from the summary and cannot rise above it.

## Regression tests added

`QualityFormatDiagnosticTests` (14 tests) covers preview flags, redaction
before diff, diff line integrity, captured-output bound, the real deadline
kill path, nonzero exit, link and path-escape refusal, unsafe source states,
bounded and redacted publication, diagnostic failure that preserves the strict
failure, prepare drift that skips previews, and non-format stages.

`QualityMachineSummaryPublicationTests` (6 tests) covers counts printed after
the evidence write, redaction and bounds, publication faults that cannot alter
the evidence, a failing protocol that stays failing, raw field exclusion, and
rejection of a non-record summary.

## Not established

The tests and helper are UNRUN. No hosted run exists for this revision. Nothing
here is a passing format, analysis or root-test claim. Required evidence is a
new hosted Application quality run at the published revision.

## Reviewed runner repair superseding the initial capture design

The follow-up source replaces the threaded pipe with an unbuffered regular
stdout file in `RUNNER_TEMP`. It never waits for pipe EOF and discards stderr.
The runner polls output size and a 120-second deadline per invocation, then
reads at most 256 KiB in bounded chunks. Timeout, nonzero exit, overflow,
read errors and a changing-size snapshot reject the preview. Cleanup attempts
to kill/wait for the direct process for at most five more seconds and removes
the temporary directory best effort. Up to three previews run sequentially;
120 seconds is not an aggregate bound and size polling is not a disk quota.

Mock regressions now hold a duplicated output descriptor open, inject partial
reads followed by `OSError`/`ValueError`, and exercise failed kill/wait cleanup.
This supersedes the pipe/thread design and initial test count above. The
incorrect claim that joining diff lines creates shell operators was removed.
The exact Dart 3.11.5 formatter dependency, dart_style
`e8190bf2242654daee7ebf21fd6d8c8046989822`, was inspected as primary source to
confirm the preview flags. All new regressions remain UNRUN.
