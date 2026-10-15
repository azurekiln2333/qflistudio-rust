> Historical worker batch snapshot, 2026-10-15. Pending compiler, wiring, offline and commit notes below are superseded by `rust-terminal-final-review.md`, `release-verification.md` and current Git commits. Retained for traceability.

# rust-terminal ISSUE-1 fix — ready for test

Agent: Herdr wB rust-terminal. Task: .trellis/tasks/10-15-rust-release-readiness.
Scope honored: ONLY `lib/rust_runner.dart` + `test/rust_terminal_commands_test.dart`.
No Flutter run (root owns the window). `dart analyze` clean. No git staging/commit.

## Fix

`lib/rust_runner.dart` `_RustRunSession`:

1. **Force offline** — `_baseEnvironment` now sets `CARGO_NET_OFFLINE: 'true'`
   unconditionally when `offline` is true (was `if (!environment.containsKey(
   'CARGO_NET_OFFLINE'))`). An inherited/host `CARGO_NET_OFFLINE=false` can no
   longer re-enable the network. When `offline` is false the caller's
   environment is untouched.
2. **Prepend `--offline`** to `cargo metadata --no-deps …` and to the
   `cargo run …` argument list (global option before the subcommand), so the
   policy does not depend on the environment and beats a conflicting
   `--config net.offline=false`. `cargo_targets.dart` is untouched; only the
   runner's call site is prefixed.

## Tests (in `test/rust_terminal_commands_test.dart`)

Replaced the weak no-dependency test with two real regressions:

- `RustProgramRunner forces offline over an explicit CARGO_NET_OFFLINE=false`:
  project has a genuinely uncached dependency, fresh `CARGO_HOME`, and a
  conflicting `.cargo/config.toml` `[net] offline = false`; env passes
  `CARGO_NET_OFFLINE: 'false'`. Asserts nonzero exit, stderr contains
  `offline`, and NEITHER stream contains `Updating crates.io index`.
- `RustProgramRunner honours the environment when offline is disabled`:
  `offline: false` + `CARGO_NET_OFFLINE: 'true'` (uncached dep) proves the force
  only applies offline and the caller's value is respected; same offline /
  no-index assertions.

## Affected process-argument tests — reviewed, no change required

- `cargo_process_wiring_test.dart` uses a fake cargo and leaves
  `StudioProfile.current` null → runner `offline == false` → no `--offline`
  prepended; its `args.first == 'metadata'/'run'` assertions still hold.
- `rust_app_test.dart` sets `rustProfile` (offlineOnly true), so its real-cargo
  tests now get `--offline`. All its Cargo projects have no external
  dependencies; verified by direct CLI probe that `cargo --offline run` on a
  no-dep project with a fresh `CARGO_HOME` succeeds (exit 0). The invalid-manifest
  and missing-linker tests fail for their own reasons and are unaffected.

Only directly-required expectations were touched; no other test file changed.
If root finds `rust_app_test.dart` or `cargo_process_wiring_test.dart` needs a
change after running, notify me rather than editing in parallel.

## Static check

`dart analyze lib/rust_runner.dart test/rust_terminal_commands_test.dart
test/rust_app_test.dart test/cargo_process_wiring_test.dart` → No issues found.

## Requested next steps (root)

1. Run `flutter test test/rust_terminal_commands_test.dart` (expect the two new
   offline regressions + existing 29 to pass), then the runner-related files and
   the full suite.
2. Commit the two files.
