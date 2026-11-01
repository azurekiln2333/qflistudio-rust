# Coordinator baseline verification

2026-10-09, before this task's product edits:

- From D:/MyNewProjects/qfli_studio_core, ran flutter test --no-pub --reporter expanded test/editor_run_test.dart test/terminal_pane_test.dart.
- Result: 22 passed, exit 0. Confirms current shared-core terminal and editor gesture behavior; fake ProgramRunner tests are not real Rust compilation evidence.
- Viewed the existing Java phone-dark terminal PNG: command/output/prompt are in one uninterrupted transcript with no separate input box.
- The historical temporary GNU Rust toolchain path no longer exists. Ordinary PATH contains Flutter/Dart but no cargo/rustc.
- Captured only four expected existing Rust source/test files under research/baseline. These snapshots preserve pre-existing work and define this task's diff boundary.

## Rust layout verification

The coordinator ran:

flutter test --no-pub --reporter expanded .trellis/tasks/10-09-terminal-run-controls/research/terminal_visual_test.dart

Result: 5 passed, exit 0. The coordinator viewed all five generated PNGs in research/screenshots (desktop-dark, phone-dark, phone-light, short-viewport, phone-long-path).

Observed: command/output/prompt use one background and scrollback; prompt follows final output; no synthetic successful exit line appears; short viewports scroll the same transcript; long paths wrap without splitting the input into another panel.

These renders use a layout-only fixture with generated stdout. They prove presentation/layout, not actual Rust compilation or Cargo target selection.

Baseline scoped Dart analyze of lib/rust_runner.dart, lib/native_miri_runner.dart, test/rust_app_test.dart, and test/native_miri_runner_test.dart: No issues found.
