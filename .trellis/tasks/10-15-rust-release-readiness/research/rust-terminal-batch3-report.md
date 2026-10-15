> Historical worker batch snapshot, 2026-10-15. Pending compiler, wiring, offline and commit notes below are superseded by `rust-terminal-final-review.md`, `release-verification.md` and current Git commits. Retained for traceability.

# rust-terminal batch 3 report — GNU linker fallback + raw-tool correctness

Agent: Herdr wB rust-terminal. Task: .trellis/tasks/10-15-rust-release-readiness
Request: commit (coordinator-owned staging; do NOT `git add .`).
PER COORDINATOR: platform Flutter lock still held; only `dart analyze` run.
Tests written but not executed — await the coordinator's notification.

## Review feedback addressed

1. **Raw `rustc`/`cargo` now get the minimal GNU linker fallback.**
   Extracted reusable, public helpers in `lib/rust_runner.dart`:
   - `resolveGnuLinkerFallbackFlags(...)` → `-C linker-flavor=ld.lld
     -C linker=<rust-lld> -C link-self-contained=yes` when the host is
     `*-pc-windows-gnu` and rust-lld exists; `[]` otherwise.
   - `hasRustLinkerEnvironmentOverride(env)` and
     `hasCargoLinkerConfiguration(path, env)` → user RUSTFLAGS/linker config and
     ancestor/global `.cargo/config.toml` keep precedence (fallback disabled).
   The editor runner (`_compilerArguments`) now calls these instead of its
   private copies; the terminal delegate calls them for raw tools. Verified by
   direct CLI probe: exactly these flags link a raw `rustc -o program.exe` and a
   `cargo run` with no gcc on the machine.

2. **Real compile-success tests** (not `--version`/intentional errors):
   - raw `rustc main.rs -o program.exe` compiles and the produced exe is run,
     asserting output `raw-link-ok` and exit 6.
   - raw `cargo run` compiles/links and prints `raw-cargo-ok` (fallback via
     `CARGO_ENCODED_RUSTFLAGS`).
   - unit tests assert the 6 fallback args and override detection.

3. **Offline correctness.**
   - Raw `cargo` gets `--offline` PREPENDED, so a later
     `--config net.offline=false` cannot re-enable the network (verified: cargo
     reports "offline mode (via `--offline`)").
   - Networked-subcommand detection skips leading global options, so
     `cargo -v --color never search x`, `cargo --offline install y`,
     `cargo -Z unstable-options info z` are all refused.
   - `RustProgramRunner(offline:)` routes CARGO_NET_OFFLINE through metadata and
     run (unchanged from batch 2, now covered).

4. **Explicit `offline` reaches `rust run`.** The delegate signature's `runner`
   is now nullable; without an injected runner it builds
   `RustProgramRunner(offline: offline)`, so `offline: true` genuinely applies
   instead of being an unused parameter. A test asserts a networked project
   fails offline through `rust run`.

5. **Executable resolution.** `resolveExecutableOnPath(executable, env)` resolves
   a bare `rustc`/`cargo` against the effective environment's PATH. `Process.start`
   on Windows resolves a bare name against the PARENT PATH, which would ignore a
   PATH-prepended toolchain; both the runner and the delegate now resolve first.
   This is what makes the bundled compiler usable in tests and in production
   without mutating the host PATH.

## Static check

`dart analyze lib test` → No issues found.

New helpers are public and unit-tested. Three real-compile tests depend on the
bundled compiler at `native/build/miri-windows/compiler/bin`; if missing they
fail loudly rather than skip.

## Coordinator actions

1. Wire `terminalCommandDelegate: rustTerminalCommandDelegate` in `lib/main.dart`
   `rustProfile` (still required; the shipped-profile regression asserts it).
2. Run `flutter test test/rust_terminal_commands_test.dart` when the Flutter lock
   releases.

Files touched: `lib/rust_runner.dart`, `lib/rust_terminal_commands.dart`,
`test/rust_terminal_commands_test.dart`.
