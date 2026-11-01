# Compiler boundary cross-layer check

Date: 2026-10-26. Source inspection only.
No compiler, native, SDK, WSL or device execution occurred.
No runtime reservation was consumed.

## Fixed in Dart source

The native analysis ABI returns compiler errors as diagnostic data with
FINISHED/0. The transport therefore returns an output exit code of zero.
The JSON parser previously dropped diagnostic records without a usable span.
A spanless error could consequently produce an empty checked-clean result.
A mapped warning could also hide the absence of a mapped compiler error.

`RustcDiagnosticStream.hasErrors` now retains error/fatal presence independently
of selected spans. `_mapDiagnostics` reports unavailable when that flag is true
and no compiler error maps to the project. A warning does not satisfy this gate.
A mapped source error with an ordinary spanless abort summary still produces
normal source diagnostics. A mapped fatal record receives error severity.
Warnings, notes and empty successful streams retain their existing behavior.
The transport and native ABI remain unchanged.

Eight regression cases were authored: two parser cases and six analyzer cases.
They cover spanless error/fatal, warning plus spanless error, ordinary warning
plus note, and mapped error/fatal plus an abort summary. They use an injected
transport and do not invoke a compiler. These tests have NOT been executed.
Dart format, analysis and type checking have NOT been executed.

## Native findings not fixed by this reviewer

1. `compiler_boundary.rs` still declares `ensure_refusal(&self, ...)` while
   constructing `Loader { boundary: Arc::clone(self) }`. Here `self` has type
   `&CompilerBoundary`, whereas `Arc::clone` requires `&Arc<CompilerBoundary>`.
   This is a concrete source-level type mismatch. Change the receiver to
   `self: &Arc<Self>`, consistent with `install`. The Pi source owner must fix
   it. This reviewer owns no Rust source edits.
2. Analysis chooses `Path::parent(source)` as its project read root. Dart
   separately carries the complete `job.mirrorRoot`, and a normal Cargo entry
   is `<mirror>/src/main.rs`. Therefore `include_str!("../data.txt")` under the
   complete project mirror lies outside the native analysis read root. The
   source remains fail-closed but cannot check every supported project mirror.
   ABI 1 does not pass the mirror root. An additive constructor or another
   reviewed explicit-root contract is a design/interface decision.
3. Only verified OHOS architectures are accepted. Every other host now refuses
   loader installation. This is explicit source behavior, not a tested desktop
   compatibility result. Linux negative-boundary fixtures remain unavailable
   until a verified Linux implementation is added or the scope changes.
4. Compiler metadata search, backend dynamic loading and output paths remain
   separate trust surfaces. This loader is not a complete process sandbox.

The former invalid-UTF8 sticky-boundary defect is fixed in the current module:
`read_file` returns InvalidData without recording a policy denial. The patched
parser diagnostic retry uses FileLoader binary reads. This conclusion is static.

## API and result-flow observations

Pinned compiler browsing sources are under
`native/build/miri-windows/compiler/lib/rustlib/rustc-src/rust/compiler`.
The pinned FileLoader has exactly the four implemented signatures:
file_exists, read_file, read_binary_file, current_directory.
Config.file_loader accepts Box<dyn FileLoader + Send + Sync>.
The loader uses owned File descriptors and synchronized shared state.
Externs::iter and remap_cwd_prefix exist in the pinned options API.
FatalError.raise exists and raises the fatal marker caught by the driver.
The embedded_boundary option itself requires the committed compiler patch.
No currently installed compiler is claimed to contain it.

All three callbacks unconditionally install the boundary. A recorded boundary
failure becomes INTERNAL_ERROR in run/analysis and FAILED in debugger outcomes.
NativeMiriAnalysisTransport converts state 5 to RustAnalysisUnavailable.
RustCodeAnalyzer catches that and returns an unavailableReason to the shared
analysis consumer. Cancel/limit terminal states retain priority and are also
unavailable for editor checks. No boundary failure reaches checked-clean in
this inspected flow, apart from the separate spanless compiler-data defect
fixed above.

## Frozen identities

The following bytes were observed when writing this report. Source owners may
subsequently change Rust files. Rehash before accepting runtime evidence.

| File | SHA-256 |
| --- | --- |
| `native/miri_adapter/src/compiler_boundary.rs` | `5ae3c511dd04709faba948d30c6ef504262b1a46d6c3d5f2fc82a77fe1f21a87` |
| `native/miri_adapter/src/lib.rs` | `2bd562c164ddc973984f8b2f2678b14aa28f8ea46be62425f9c0de30b17b0ecb` |
| `native/miri_adapter/src/debug.rs` | `531962b102ceb9bf4c645acf9a75855f82d5ca7f767c0ec28fa057ec098ae357` |
| `native/patches/rustc-1.98.1-embedded-compiler-boundary.patch` | `7236eff645ddf45eb87e78865a7d805a3443234e23c0855bee7956882c9989ee` |
| `lib/native_miri_analyzer.dart` | `dbe8a8729c57566a1b5e09ca3f52989d4f47c6b7f47cff4292148a33e5f4a0fd` |
| `lib/rust_compiler_diagnostics.dart` | `7fdae634f9e4179432035684727bf3a4727626b997355d8159a21e86b53bc4bf` |
| `lib/rust_code_analyzer.dart` | `a944c0cc2d2aafd83b5edd96055e2b863daa21dc83e68f7c57201cd29af1fd28` |
| `test/rust_compiler_diagnostics_test.dart` | `63cba1d172e66de2c3982a1f2a713a343d68046d0f8d08dc521d7475c04832aa` |
| `test/rust_code_analyzer_test.dart` | `ff968cf5b247b88b8cecf9e67bdad40ccc2e74ae9cb4bf851ffe8e5b60fd0986` |

## Verification status

- Scoped git whitespace check: PASS. Pure four-file trailing-whitespace check: PASS.
- Controlled Chinese mechanical check: PASS, zero findings.
- SDK lint/typecheck: UNRUN, no shared runtime grant.
- Authored Dart regression cases: UNRUN, no shared runtime grant.
- Native compilation/runtime/device acceptance: UNRUN.

Source review cannot replace a patched compiler build or actual negative probes.

## Parent follow-up after this review

Pi p3 corrected the concrete receiver mismatch on 2026-10-26.
`ensure_refusal` now receives `self: &Arc<Self>`.
Its four callers are inside `install`, whose receiver has the same type.
Final module SHA-256:
`f5ed454e2fe4bf3556cd828d299ccc486c77c51ce1a40d81068eccda9bfbff42`.
The correction has source evidence only. No compiler or typechecker ran.
The analysis-root and non-OHOS compatibility findings remain open.
The frozen-identity table above records the review input, not this later delta.
