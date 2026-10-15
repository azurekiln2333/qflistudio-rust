# Rust Terminal Commands

## 1. Scope / Trigger

Apply when changing `rust_terminal_commands.dart`, desktop compiler execution,
or the StudioProfile terminal delegate. Both editor and standalone terminals
must use the shared core delegate seam; do not fork their widgets.

## 2. Signatures

```dart
Future<bool> rustTerminalCommandDelegate(
  SandboxShellBackend backend,
  String command, {
  RustProgramRunner? runner,
  bool? offline,
  Map<String, String>? environment,
});
```

Supported simple commands are `rust run <file.rs>`, `rust <file.rs>`,
`rustc <arguments>` and `cargo <arguments>`. Unknown/compound shell commands
return false for normal shared-shell handling. Claimed commands return true
and expose the actual process status through `backend.runStreams`.

## 3. Contracts

- `rustProfile.terminalCommandDelegate` supplies the hook. TerminalManager and
  TerminalPane both obtain it from StudioProfile; preserve this common path.
- Rust source paths are resolved within the backend sandbox. Only `.rs` sources
  are accepted. RustProgramRunner selects desktop rustc/Cargo or embedded Miri.
- Mobile has an embedded source runner, not executable rustc/Cargo CLI tools.
  Raw CLI invocations fail with 127 and direct users to `rust run`.
- Offline policy comes from the explicit argument or current product profile.
  Force `CARGO_NET_OFFLINE=true` and pass Cargo `--offline`; a caller's false
  environment value or `--config net.offline=false` cannot enable fetching.
  Reject network commands such as login, publish, search and fetch even after
  Cargo global options. Local Cargo builds remain usable with cached/path deps.
- Resolve executable names against the effective child PATH on Windows before
  Process.start. Its bare executable lookup otherwise uses the parent's PATH.
- On Windows GNU without gcc, use bundled rust-lld and self-contained linking.
  Preserve explicit linker flags/environment and ancestor/global Cargo config.
- Close raw tool stdin to provide EOF. Reject rustc stdin source (`rustc -`)
  because this terminal contract does not supply interactive source input.
- Preserve stdout/stderr, actual exit status and process-tree cancellation.
  Cancellation is 130; a subsequent run must work normally.

## 4. Validation & Error Matrix

| Condition | Required result |
| --- | --- |
| Escaping source path / wrong extension / invalid operands | Diagnostic, 127 |
| Missing desktop compiler | Honest tool-not-found diagnostic, 127 |
| Raw CLI on mobile | Unsupported CLI diagnostic, 127 |
| Offline network Cargo subcommand | Rejected before spawning |
| Offline dependency absent from cache | Cargo offline failure; no index update |
| User cancels a running program | Entire child tree stops; 130 |
| Native source compile error | Real compiler diagnostics; no stale output |

## 5. Good / Base / Bad Cases

- Good: both terminal surfaces execute `rust run main.rs` through the shipped
  profile hook and show identical program output.
- Base: desktop `cargo run` builds an offline std-only project.
- Bad: a profile claims offline support but respects inherited
  `CARGO_NET_OFFLINE=false`, allowing editor Run to update crates.io.

## 6. Required Tests

`rust_terminal_commands_test.dart` must cover real raw rustc compile/link/run,
real offline Cargo execution, effective PATH resolution, linker override
precedence, unsupported mobile tools, sandbox rejection, global-option-prefixed
network commands and cancellation followed by fresh execution. An offline test
needs a missing dependency and conflicting environment/config; a dependency-free
program alone cannot prove network exclusion. `rust_native_test.dart` verifies
the shipped delegate through real TerminalManager/SandboxShellBackend on Android,
including Pending output, interrupt and a fresh marker after cancellation.

## 7. Wrong vs Correct

Wrong: wire only editor Run and assume standalone terminals can execute Rust.
Correct: supply the single profile delegate consumed by both terminal surfaces.

Wrong: report raw mobile `cargo` as successful using fabricated output.
Correct: expose unsupported CLI status while keeping real embedded source
execution available through `rust run`.
