# Analyzer ↔ native transport lifecycle seam (Pi4 completion review)

Scope: `lib/native_miri_analyzer.dart`, `test/native_miri_analyzer_test.dart`, and
the transport seam in `lib/rust_code_analyzer.dart`. No adapter, core, sibling or
`main.dart` edits.

## The race that was closed

`RustCodeAnalyzer` waits for its backend with a backstop
(`timeout + 2s`) so a broken transport cannot hold the editor lane forever.
A native adapter cannot be preempted: it is blocked inside `qfli_miri_analyze`,
which is reading the mirrored sources, and the ABI forbids `destroy` while a
call is active. The previous code hit its bound, threw, and ran
`finally { await mirror.dispose(); }` — deleting the compiler's input while the
worker isolate was still reading it.

## The seam

```dart
/// Optional transport capability: work started by [analyze] can outlive the
/// future it returns, and can be asked to stop early.
abstract interface class RustAnalysisCancellation {
  Future<void> cancel();
}
```

- `RustAnalysisTransport` is unchanged, so existing and third-party transports
  keep compiling; cancellation is an opt-in capability.
- `NativeMiriAnalysisTransport` implements it. Its `analyze` future completes
  only after the blocking native call returns (destroy already issued), and
  `cancel()` completes only after every started call returned.

Analyzer rules (in `_awaitBackend` / `_disposeWhenStopped`):

1. Normal case — the backend future completed, so its call has stopped and the
   mirror is deleted immediately. No extra wait is added.
2. Backstop case — report unavailable now, mark the mirror as retained, ask a
   `RustAnalysisCancellation` backend to stop cooperatively (unawaited), and
   **chain deletion onto the abandoned future**. Deletion therefore happens
   exactly when the work really stops, not when the analyzer stops waiting.
3. Cleanup errors are swallowed; a transport that never stops leaves the temp
   directory to the OS instead of corrupting an in-flight compile.

No `Isolate.kill`, no orphaned destroy, no widened delete window.

## Contract drift found in `native-analysis-contract.md`

`native/miri_adapter/qfli_miri.h` (newer than the doc) states that
`QFLI_BUSY = 6` is **only** the `qfli_miri_analyze` return code and is never
written to `QfliResult.state`; a busy answer leaves state `READY` (0).
The doc still lists:

- §3 table row `QFLI_BUSY (6) | -1 | ...` as a session state;
- §5 "it returns `2` and state `6` immediately".

Doc should be corrected. The Dart transport already follows the header: it
branches on the return code (`0` accepted, `2` busy, other = rejected) and its
state switch no longer contains a `6` case. `state` 0/1 (READY/RUNNING) cannot
produce a clean result.

## Deliberate limitations

- A busy answer is reported as unavailable ("编译器正在运行…"), not retried:
  the run path holds the compiler for up to its own budget, and retrying inside
  the editor lane would block it. The user's next analyze request retries.
- Mobile analysis stays **unavailable** until a packaged adapter with the
  analysis symbols is built and `analysis_abi_test.c` passes (§6.2 of the
  contract). Missing symbols produce an explicit reason, never a clean result.
- Cancellation is cooperative: an in-flight rustc query finishes its current
  step. Worst-case latency is one query, not one analysis.
