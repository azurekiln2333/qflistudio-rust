# Pi implementation handoff

Worker: pi-rust-terminal, right Herdr pane wB:p2. Implementation followed explicit final-plan approval. Pi is idle after delivery while the coordinator's independent Trellis check runs.

## Delivered files

Edited pre-existing files:
- lib/rust_runner.dart
- lib/native_miri_runner.dart (already untracked before this task)
- test/rust_app_test.dart

New files:
- lib/cargo_targets.dart
- lib/rust_run_title.dart
- test/cargo_targets_test.dart
- test/cargo_process_wiring_test.dart
- test/rust_editor_run_test.dart

The task-only patch and file hashes were generated against research/baseline, not git HEAD. test/native_miri_runner_test.dart remained unchanged.

## Behavior

- Shared-core UI changes from Java are reused directly.
- Desktop and native titles use run plus a relative source path, quoting whitespace paths and omitting backend suffixes.
- Cargo metadata maps the selected source to an explicit package/manifest/bin or executable example.
- Unregistered sources use standalone rustc; non-runnable and ambiguous registrations fail clearly.
- Metadata stdout stays private and metadata cancellation remains exit 130.
- Editor gesture regressions cover entry/current/entry and save/config preservation.

## Review corrections made before handoff

1. Preserve registered non-runnable ownership during metadata decoding; reject library-shaped examples.
2. Use explicit schema type checks and controlled FormatException diagnostics.
3. Handle cancellation before generic startup-error conversion.
4. Quote whitespace paths and transparently forward embedded results.
5. Use compiled fake program binaries in Windows process tests.
6. Gate metadata cancellation testing on a flushed ready marker, not a timed guess.

## Pi-reported validation

- Dart format on the nine checked Dart files: 0 changes required.
- dart analyze lib test: No issues found.
- Full Rust flutter test suite: 82 passed, 22 skipped.
- cargo_targets_test.dart: 14 passed.
- cargo_process_wiring_test.dart: 7 passed using actual subprocesses running compiled fake tools.
- rust_editor_run_test.dart: 3 passed using the Rust profile configuration and controlled runner.
- rust_app_test.dart: 15 passed, 13 skipped.
- Shared-core editor_run_test.dart and terminal_pane_test.dart: 22 passed.

These are the Pi handoff results; final independent review results are recorded separately. Compiler/native/device skips are not counted as passes. Mocked Cargo/rustc processes verify application wiring, not real Rust compilation. Five coordinator-inspected layout-only renders are described in baseline-verification.md.

## Remaining integration limitation

No usable Rust compiler/Cargo exists on the current PATH or in the checked historical temporary installation/WSL environment. Actual Rust/Cargo compilation and native-device execution are not verified in this task. Source selection and process lifecycle have deterministic automated coverage.
