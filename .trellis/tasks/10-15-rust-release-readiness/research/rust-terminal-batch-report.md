> Historical worker batch snapshot, 2026-10-15. Pending compiler, wiring, offline and commit notes below are superseded by `rust-terminal-final-review.md`, `release-verification.md` and current Git commits. Retained for traceability.

# rust-terminal batch report — Rust terminal delegate + offline audit

Agent: Herdr wB rust-terminal. Task: .trellis/tasks/10-15-rust-release-readiness
Request: commit this batch (git staging is coordinator-owned; do NOT `git add .`).

## Files added (ready to commit)

- `lib/rust_terminal_commands.dart` — `rustTerminalCommandDelegate`
  (`TerminalCommandDelegate`). Claims `rust`/`rustc`/`cargo`; routes
  `rust run <file.rs>` through the existing `RustProgramRunner` (desktop real
  rustc/cargo, mobile packaged real Miri); spawns real `rustc`/`cargo` on
  desktop; mobile without a CLI reports honest 127 (no fabricated version or
  success). Declines compound/unknown lines so the sandbox reports them.
- `test/rust_terminal_commands_test.dart` — 10 tests, all passing:
  dispatch claims/declines, 6 parameter-failure cases (127 + diagnostic +
  empty stdout), real execution (3 skip: no host rustc/cargo), shared
  delegation through `TerminalManager`.
- `.trellis/tasks/10-15-rust-release-readiness/research/terminal-offline-audit.md`
  — read-only offline audit (see below).

## Checks

- `dart analyze lib test` → No issues found.
- `flutter test` (full suite) → 92 passed, 25 skipped (skips are the
  pre-existing rustc/cargo-dependent tests). No regressions.
- `flutter test test/rust_terminal_commands_test.dart` → 10 passed, 3 skipped.

## Coordinator action required (main.dart is coordinator-owned)

Wire the delegate in `rustProfile` (`lib/main.dart`):

```dart
import 'rust_terminal_commands.dart';
// inside the StudioProfile(...) literal:
terminalCommandDelegate: rustTerminalCommandDelegate,
```

Single seam; it wires the editor TerminalPane, TerminaxTerminalPage and
quick-tools local terminal simultaneously (both read
`StudioProfile.current?.terminalCommandDelegate`).

## Offline audit findings

- Guarded (verified by code): login/register, settings AI, AI menu, online
  terminal menu, editor online-enabled, online fallback, cloud SQL, cloud
  project creation/scope/fetch, community tabs (swap to local).
- FINDING (shared-core, not modified): editor `Git` menu item
  (`editor_page.dart:1586`, `_openGit` `:590`) is NOT gated by `offlineOnly`
  even though `GitPage` reaches network (server git for cloud projects).
  Recommend hiding it under `offlineOnly` like `ai`/`online_terminal`.

## Blockers

1. No host `rustc`/`cargo` on this machine → 3 real-compiler tests skip.
   Coordinator to install a host toolchain or record the gap.
2. main.dart wiring above.

No core files, no `main.dart`, no `pubspec.yaml`, no content files were edited.
No branch change. No `git add .`.
