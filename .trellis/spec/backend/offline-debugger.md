# Rust offline debugger

## 1. Scope / Trigger

Apply to `native/miri_adapter/src/debug.rs`, `qfli_debug.h`,
`lib/rust_debugger.dart` and the profile seam. The shared owner controls the
editor, debugger panels and `services/debug_session.dart`; read its frozen
contract before changing the product adapter.

## 2. Signatures

```dart
RustDebugger implements StudioDebugger;
Future<DebugSession> launch(DebugLaunchRequest request);
```

The authoritative optional ABI1 extension is `native/miri_adapter/qfli_debug.h`.
Its status includes state, actual worker exit, pause generation and revision.
Use `qfli_miri_debug_resume_at` for generation-checked commands and
`qfli_miri_debug_wait` to join before destroying.

## 3. Contracts

- Discover actual optional symbols/capabilities before exposing controls. Check
  prepared runtime identity against the library used for discovery. Missing
  debugging never falls back to Run or diagnostics.
- Launch validates canonical entry/breakpoint containment and explicit edition.
  The adapter rejects nonempty unsaved document snapshots; the editor must save
  before launching. Bounded saved-source capture supplies physical UTF16 source
  columns without rereading changed file text when paused.
- Bootstrap the real interpreter into its actual entry frame before publishing
  an entry pause. Breakpoints remain pending until a real paused location matches
  them; no guessed relocation. Breakpoints are launch-only.
- A paused source line describes the next instruction, not the last completed
  instruction. The entry may already be the first user statement; inspect it
  before resuming. The debug_basic regression requires entry9 (a uninitialized),
  first step10 (a=1), next step11 (a=1,b=2), with real increasing generations and
  steps. Searching after resume for the already-consumed entry line is invalid.
- Capture step origin depth/position before advancing. Copy actual stack frames
  and scalar values through pinned public Miri APIs. Unsigned128-bit values must
  remain unsigned; unsupported aggregates/references report unavailable.
- Debugging performs the public thread-termination check. It does not perform
  heap-leak validation: pinned additional static roots are private, and passing
  empty roots would produce false leaks. Ordinary Run separately allows safe
  intentional leaks while preserving its live-memory budget.
- Invalidate frames/tokens after resume. Reject stale generations before any
  execution. Busy start returns2 without consuming the retryable handle.
  Stdout/stderr/diagnostics are retained bounded live channels; snapshots replace
  buffers. All string/output truncation preserves valid Unicode and is marked.
- Detect malformed native UTF8 independently of a legitimate U+FFFD scalar.
  Replacement decoding must mark lost content; a live incomplete final scalar
  may wait for the next snapshot, but an incomplete terminal tail is loss. Keep
  raw-byte bounds and decoded UTF8 bounds separate so malformed input cannot
  silently produce an accepted exact-output result.
- Stop bypasses a blocking resume through cooperative cancellation. Cancel is130,
  limits124 and real program status remains real. Publish terminal/done only
  after the compiler lease is released, blocking calls finish, OS worker joins
  and native destruction succeeds. Cleanup failure retains ownership for retry.

## 4. Validation & Error Matrix

| Condition | Required result |
| --- | --- |
| Missing optional ABI or mismatched prepared library | Explicit unavailable/error |
| Nonempty unsaved documents or foreign source | Reject before native execution |
| Stale pause generation | Reject without changing native position |
| Scalar unsupported/uninitialized | Explicit value unavailable state |
| Cancel while paused/running | Real exit130, joined worker, no stale frames |
| Cleanup cannot be proven | Stopping and retained ownership; done pending |

## 5. Good / Base / Bad Cases

Good: step out returns to the actual caller, then a breakpoint is verified at a
matching project line. Base: stop-on-entry shows a real main frame. Bad: mark a
requested line verified at launch or publish terminal immediately after cancel.

## 6. Tests Required

Run `rust_debugger_test.dart` for capability/path/edition validation, snapshots,
generation commands, bounds, Unicode, output-only changes and retryable cleanup.
Execute `debug_abi_test.c` against the fresh pinned adapter for actual entry,
breakpoints, each step, scalars, compiler busy/retry, live channels, asynchronous
pause, cancellation and real source errors. Also rerun analysis/ordinary ABI
regressions. Host/debug ABI, target compilation, package hashes and actual OHOS
debugging are separate evidence; record each independently.

## 7. Wrong vs Correct

Wrong: infer worker exit from a stop request or elapsed timeout.
Correct: cancel, await every active call, join, then destroy and complete done.
