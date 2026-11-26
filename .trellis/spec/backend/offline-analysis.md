# Offline Rust source analysis

## 1. Scope / Trigger

Apply to RustCodeAnalyzer, diagnostic mapping, NativeMiriAnalysisTransport and
their profile wiring. The shared core owns CodeAnalyzer, editor squiggles,
stale-result suppression and Problems navigation. Changes there require C ownership.

## 2. Signatures

```dart
RustCodeAnalyzer({String? rustcPath, RustAnalysisTransport? transport,
  Duration timeout = const Duration(seconds: 8)});
Future<CodeAnalysisResult> analyze(CodeAnalysisRequest request);
abstract interface class RustAnalysisTransport {
  Future<RustAnalysisOutput> analyze(RustAnalysisJob job);
}
abstract interface class RustAnalysisCancellation { Future<void> cancel(); }
NativeMiriAnalysisTransport({Future<NativeMiriRuntime> Function()? prepareRuntime,
  NativeMiriAnalysisSessionFactory? sessionFactory, int maxOutputBytes = 8388608});
```

The complete native C layout lives in qfli_miri.h. create_analysis/analyze are
optional ABI1 symbols. Old packages must report unavailable when absent.

## 3. Contracts

- Check immutable exact unsaved buffers in an isolated project mirror. Preserve
  all disk bytes, BOM, CRLF and binary companions. Never overwrite learner files.
- Desktop invokes real rustc with metadata-only JSON diagnostics and a temp
  output directory. Never invoke Cargo, build.rs, proc macros or the user program.
  Unsupported dependency configurations return unavailable.
- QFLI_RUSTC overrides discovery. Otherwise the pinned checkout compiler precedes
  PATH. Android/iOS/OHOS use the explicitly injected native analysis transport.
- Native analysis stops before Miri evaluation and never enables cfg(miri).
  FINISHED/0 can contain compile errors. Parse diagnostics rather than treating
  exit0 as checked clean. Busy is a call return2 and never mutates session state.
- Preserve error/fatal presence when JSON diagnostics have no source spans.
  A zero native exit code does not erase those errors. If no compiler error maps
  to a project buffer, report unavailable. Mapped warnings cannot satisfy this
  requirement. A mapped source error may coexist with a spanless abort summary.
- Map raw original UTF8 byte offsets into the exact source's UTF16 offsets,
  including BOM/CRLF/CJK/non-BMP. Remapped Windows paths must resolve to originals.
- A timeout reports unavailable and requests cooperative cancellation. The
  mirror belongs to the live backend future until it actually completes. A
  watchdog timeout does not prove a native compiler query stopped. Cancel,
  await active calls and destroy, in that order. Never kill the worker isolate.

## 4. Validation & Error Matrix

| Condition | Required result |
| --- | --- |
| Missing symbols/compiler, unsupported Cargo graph | Explicit unavailable reason |
| Valid source with real completed compiler | Empty diagnostics, no unavailable reason |
| Type/syntax error | Real exact-range diagnostic, no execution |
| Busy/timeout/output bound/malformed UTF8/ICE | Unavailable, no fabricated clean result |
| Timed out native query still active | Mirror retained until actual completion |

## 5. Good / Base / Bad Cases

Good: an unsaved module containing a type error produces an E0308 span in that
buffer. Base: a valid std-only crate is checked clean. Bad: returning an empty
diagnostic list when the runtime lacks the optional analysis extension.

## 6. Tests Required

Run rust_code_analyzer_test, rust_compiler_diagnostics_test and
native_miri_analyzer_test. Assert actual rustc nonexecution, exact UTF8/UTF16 spans,
module overlays, untouched project bytes and delayed cleanup after cancellation.
Run analysis_abi_test.c against a freshly built pinned adapter. Native builds,
packaging and actual OHOS analysis execution are separate evidence gates.

## 7. Wrong vs Correct

Wrong: delete the source mirror after Future.timeout returns.
Correct: report unavailable now, request cancellation, and dispose the mirror
only when the actual native backend future has stopped reading it.
