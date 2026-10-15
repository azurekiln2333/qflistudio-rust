# Implementation and verification

## Review gate

- [x] User approved task creation and planning.
- [x] Pi completed shared-core/Java and Rust source audits.
- [x] Requirements converged; no unresolved product decision remains.
- [x] User explicitly approved the final plan on 2026-10-09; coordinator may run task.py start.

## Ordered work

1. Snapshot only the expected Rust source/test files before edits; read the task artifacts, context manifests and applicable specs.
2. Pi simplifies desktop/native run titles and implements selected-source Cargo target routing. Keep all shared-core and other-language files untouched.
3. Add regressions that fail against the old routing: multiple Cargo binaries, custom target paths/names, ordinary current main2.rs, bad metadata, and source-selection/configuration preservation. Retain exit/stdin/cancellation tests.
4. Verify the actual Rust profile's tap/long-press/tap seam using the existing shared editor, reusing established fixture cleanup conventions.
5. Run scoped Dart formatting/analyzer and focused tests. Use an already installed compiler if found; record any skipped compiler/device checks accurately. Do not claim mocked metadata tests as real Cargo execution.
6. Coordinator reviews the task-only diff, inspects terminal render evidence, runs the final required quality gate, records any remaining limitations, and updates the narrow Rust execution spec.
7. Keep staging/commits limited to this task's own work; do not include pre-existing runtime or shared-core changes.

## Validation commands

- D:/ProgramFiles/flutter_ohos/bin/cache/dart-sdk/bin/dart.exe format --output=none --set-exit-if-changed <owned Dart files>
- D:/ProgramFiles/flutter_ohos/bin/cache/dart-sdk/bin/dart.exe analyze <owned Dart files>
- flutter test --no-pub --reporter expanded test/rust_app_test.dart test/native_miri_runner_test.dart <new focused tests>
- flutter test --no-pub --reporter expanded test/rust_project_store_test.dart
- From ../qfli_studio_core: flutter test --no-pub --reporter expanded test/editor_run_test.dart test/terminal_pane_test.dart
- git diff --check for owned tracked files and task-only baseline comparison for pre-existing untracked files.

## Review checks

- Commands and inputs remain one scrollback surface; no completion line on success.
- Current-file run never substitutes Cargo's default source.
- Metadata output stays out of user stdout; Cargo/compiler diagnostics retain original status.
- Compiler/environment overrides and cancellation apply to every new subprocess phase.
- Project entry, Cargo.toml and unrelated work stay unchanged.
- Record real commands/results and distinguish source review, widget testing, desktop compiler execution, and mobile device execution.

Implementation steps 1-6 are complete. Step 7 (commit/archive) is explicitly deferred by the user; preserve all working-tree changes without staging or committing.

## Final integration (2026-10-15)

User now explicitly authorizes commits. Completed source integration is committed
in c2bc7b9 and151fe59, with final canonical formatting in5384d29. Both standalone
and editor terminals use the Rust profile delegate. Final root140pass/8Windows
native skips/0fail, targeted terminal/process/app65pass, and Androidx64 seven
actual native/editor/terminal cases passed. Historical no-commit notes and skipped
compiler observations remain session history, superseded by current evidence.
