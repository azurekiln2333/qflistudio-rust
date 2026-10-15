> Historical worker batch snapshot, 2026-10-15. Pending compiler, wiring, offline and commit notes below are superseded by `rust-terminal-final-review.md`, `release-verification.md` and current Git commits. Retained for traceability.

# rust-terminal batch 2 report — hardening + real compiler

Agent: Herdr wB rust-terminal. Task: .trellis/tasks/10-15-rust-release-readiness
Request: commit (git staging is coordinator-owned; do NOT `git add .`).
PER COORDINATOR: platform builds own the Flutter command; only `dart analyze`
was run this batch. Do not run flutter test/pub/build until notified.

## Real compiler located and used

`native/build/miri-windows/compiler/bin` contains rustc 1.98.1 + cargo 1.98.1.
Both confirmed working by direct CLI probe (rustc compile+run exit 5;
`CARGO_NET_OFFLINE=true cargo run` succeeded offline). Tests discover this path
via a PATH-prepend helper; when no compiler exists the real-execution tests
FAIL (not skip), so a missing toolchain cannot hide behind a skip.

## Fixes applied on review feedback

1. **Raw-tool stdin** (`lib/rust_terminal_commands.dart`): every raw
   `rustc`/`cargo` child now closes stdin immediately (EOF) so a tool that polls
   stdin cannot hang. A stdin-reading form (`rustc -`) is rejected up front with
   an explicit "no interactive stdin" message and 127.
2. **Cargo offline** (`lib/rust_terminal_commands.dart` + `lib/rust_runner.dart`):
   - raw `cargo` gets `CARGO_NET_OFFLINE=true` when offline; networked
     subcommands (`login`/`logout`/`publish`/`search`/`install`/`uninstall`/
     `info`/`owner`/`add`/`remove`/`update`/`upgrade`/`yank`/`fetch`) are refused
     with 127 and a clear message before Cargo runs.
   - `RustProgramRunner` gained an `offline` flag (null → reads
     `StudioProfile.current.offlineOnly`). Its `cargo metadata` and `cargo run`
     environments now carry `CARGO_NET_OFFLINE=true`, so the editor Run button
     and `rust run` obey the same policy.
3. **Tree cancellation** (`lib/rust_runner.dart`): extracted the existing tree
   kill into public `terminateRustProcessTree(Process)` (taskkill /T /F on
   Windows; recursive PPID walk on POSIX) which now also awaits the direct
   child's exit. Both the editor runner and the terminal delegate use it, so
   cancelling raw `cargo`/`rustc` kills the `rustc`/linker grandchildren and
   waits for the process to settle instead of leaving a compiler behind.
4. **Integration regression** (`test/rust_terminal_commands_test.dart`): a test
   asserts the REAL `rustProfile.terminalCommandDelegate` is non-null and claims
   `rust run` / declines `ls`. This FAILS until the coordinator wires
   `terminalCommandDelegate: rustTerminalCommandDelegate` in `lib/main.dart`
   (missing wiring is caught instead of asserted away in a comment).

## Test coverage added (real behaviour, no skip)

`test/rust_terminal_commands_test.dart` now covers:
- dispatch claims/declines + compound-line decline.
- parameter failures (7): missing/too many/non-Rust/escape/options/stdin form.
- real rustc `--version`, real cargo `--version`, raw rustc compile diagnostics,
  `rust run` stdout+exit, bare `rust <file>`.
- offline: refuse search/publish/login/install/info/owner; allow local
  `cargo --version`; `RustProgramRunner(offline:)` sets CARGO_NET_OFFLINE.
- cancellation: real `cargo run` of a 60s program, cancel returns 130.
- shared delegation via `TerminalManager`; shipped-profile wiring regression.

## Static check

`dart analyze lib/rust_runner.dart lib/rust_terminal_commands.dart
test/rust_terminal_commands_test.dart` → No issues found.
(Full `dart analyze lib test` deferred to avoid racing platform builds.)

## Coordinator actions

1. Wire `terminalCommandDelegate: rustTerminalCommandDelegate` in `lib/main.dart`
   `rustProfile` (required — the new regression test asserts it).
2. Run `flutter test test/rust_terminal_commands_test.dart` once platform builds
   release the Flutter command. 3 real-compiler tests depend on the bundled
   compiler being present at the path above.
3. No core edits by this agent; the offline Git-menu finding from batch 1
   remains for the core owner.

Files touched this batch: `lib/rust_terminal_commands.dart`,
`lib/rust_runner.dart`, `test/rust_terminal_commands_test.dart`.
