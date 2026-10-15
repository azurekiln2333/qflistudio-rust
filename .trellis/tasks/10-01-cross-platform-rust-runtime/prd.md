# Enable native Rust runtime across platforms

## Goal

Reuse the upstream Rust compiler and Miri C ABI on native Flutter platforms, preserve desktop Cargo compilation, package each host correctly, and test only environments available on this machine.

## Requirements

- Reuse the upstream compiler and Miri implementation through the existing C
  session ABI. Do not implement a substitute Rust parser or return demo output.
- Preserve desktop Cargo/rustc compilation and execution. Make the embedded
  interpreter usable on Windows, Linux, macOS, Android and iOS as appropriate
  to each native host, while retaining OHOS behavior.
- Build and package matching compiler-private host libraries, interpreted
  standard libraries and native dependencies for each architecture.
- Route mobile execution through the in-process engine; retain diagnostics,
  stdin, stdout/stderr, user exit status, cancellation and execution limits.
- Use available environments for real compiler/interpreter execution tests.
  Do not run target tests when their device, SDK or host is unavailable.
- Preserve current parallel edits and commit completed changes with conventional
  messages, as requested earlier in this thread.

## Acceptance Criteria

- [x] Platform inspection identifies implemented and missing paths with evidence.
- [x] Desktop compiler execution works with the available Windows toolchain.
- [ ] The C ABI interpreter builds and executes real sources on available hosts.
- [x] Native target selection, asset preparation and library loading cover the
      supported native platforms without loading a library for another host.
- [ ] Android and Apple build integrations produce and package real native
      artifacts through reproducible source builds or validated matching inputs.
- [x] Diagnostics, stdin/EOF, exit status, cancellation and subsequent runs retain
      their contract across the shared native runner.
- [x] Tests are recorded by platform, with unavailable environments explicitly
      skipped and no claim that a skipped target passed execution.
- [x] Completed implementation batches are committed without unrelated changes.

## Notes

- Current 2026-10-15 evidence supersedes the historical environment notes below:
  real Windows rustc/Cargo execution, Android ARM64 six-case and x64 seven-case
  native execution pass. Pinned OHOS ARM64 libraries and unsigned HAP build pass;
  signed packaged source execution remains blocked. Windows native Miri and
  Apple-host execution remain unverified, so their broad acceptance stays open.
  Current user authorization includes available OHOS device checks and commits.

- Web scope is awaiting the user's clarification. Its browser sandbox requires
  a separate WebAssembly engine; native dynamic libraries cannot be loaded there.
- The new request authorizes available non-OHOS compiler/interpreter tests.
  Prior paused OHOS device tests are not required for this change.
- WSL inspection was not executed because automatic approval returned HTTP 503.
  This is an environment gate, not evidence that the Linux implementation fails.
