# Native debugger: implementation handoff

Status: **source complete, host type-checked, NOT yet built/run on any real
target.** Root owns the WSL/OHOS builds and the integration into `lib.rs`.

Written by the adapter worker. No Flutter, device, core or sibling files were
touched. The analysis/run bodies and the upstream Miri patch are untouched.

Pinned: Rust **1.98.1**, commit `48a229ceaefd4985c50990b14116b6d856af0985`.
Miri fingerprint `92f51c0345496c6ef1edbba009985c84b612630dd5c7e81ea2cdd826d0d85764`.

---

## 1. Files

| File | Status | Purpose |
| --- | --- | --- |
| `native/miri_adapter/src/debug.rs` | **new** | Real Miri stepping: worker thread, snapshot publishing, C ABI |
| `native/miri_adapter/qfli_debug.h` | **new** | Separate public header; no existing header modified |
| `native/miri_adapter/debug_abi_test.c` | **new** | C ABI test against a real built adapter |
| `native/fixtures/debug_basic.rs` | **new** | Step-in / locals, stable line map |
| `native/fixtures/debug_breakpoint.rs` | **new** | Breakpoint + step-in into a call + step-over |
| `native/fixtures/debug_locals.rs` | **new** | Exact scalar renderings and honest local states |
| `native/fixtures/debug_type_error.rs` | **new** | Compile error becomes an error pause |

Nothing else changed. `qfli_miri.h`, `src/lib.rs`, the analysis files and
`native/patches/miri-1.98.1-embedded-session.patch` are untouched.

---

## 2. The two `lib.rs` edits root must make

`debug.rs` is a **child module** of the adapter crate and imports the parent's
private helpers. Integration is exactly two lines:

```rust
// 1. next to the other `extern crate` lines (only rustc_span is new):
extern crate rustc_span;

// 2. near the top of the crate, e.g. after the other items:
mod debug;
```

`extern crate rustc_span;` is required because `debug.rs` resolves source
positions through
`loc.file.name.display(RemapPathScopeComponents::DIAGNOSTICS)`.
`rustc_ast`, `rustc_errors`, `rustc_interface` and `anstream` are already
declared by the parent.

Everything `debug.rs` imports from the parent was verified to exist and to be
reachable from a child module (Rust privacy is "visible to descendants"):

```
ABI_VERSION, COMPILER_LOCK, DiagnosticWriter, MAX_INPUT, SessionIo,
claim_backend, crate_name_string, ffi_guard, lock, make_backend,
new_session_io, path_string, resolve_backend
```

In particular a debug session uses `new_session_io(Vec::new(), None, timeout,
max_output, None)` — the `None` limits from the analysis fix are exactly what a
debugger needs (no block/memory budget; the step budget is enforced by the
debugger loop). `*lock(&io.start)` is set at create time so `check_stop`
enforces the timeout.

---

## 3. Architecture (why it is shaped this way)

```
qfli_miri_debug_create ──> Box<QfliDebugSession { Arc<Shared> }>
                              │
qfli_miri_debug_start ────────┤ spawn_worker(Arc<Shared>)
                              │      │
                              │      └─ thread: lock(COMPILER_LOCK)
                              │                 run_compiler(args, DebugCallbacks)
                              │                   └─ after_analysis:
                              │                        emit stashed diagnostics
                              │                        if has_errors -> FAILED/PAUSE_ERROR
                              │                        miri::create_ecx(...)
                              │                        publish_and_wait(PAUSE_ENTRY)  <- blocks
                              │                        loop { miri_step() ... publish_and_wait }
                              │
                              └─ wait_for_pause()  returns 0 (paused) / -1 (terminal)

qfli_miri_debug_resume ──> set control.command, notify, wait_for_pause()
qfli_miri_debug_cancel ──> set cancelled + notify (never takes COMPILER_LOCK)
qfli_miri_debug_pause  ──> set pause_requested + notify
```

Key facts:

1. **`InterpCx<'tcx>` borrows the compiler session**, so it cannot be stored in
   the `'static` C session. It lives entirely on the worker thread inside one
   `run_compiler` call. The C session holds only owned snapshots.
2. **`eval_entry` cannot host a debugger** (it owns the loop), so the loop is
   ours: `create_ecx` once, then `miri_step` per step, exactly like Priroda.
3. **The compiler lock is held by the worker for the session's lifetime**,
   because the compiler session is genuinely live. A paused debug session
   therefore makes `qfli_miri_analyze` return `2` (busy) immediately, and a
   `qfli_miri_run` waits. This is documented in the header. This is not a
   deadlock: cancel/pause/resume/snapshot readers never take `COMPILER_LOCK`.
4. **No lock is held across the control wait** except `control: Mutex<Control>`
   itself, which is the mutex the `Condvar` is bound to. Cancel and pause from
   another thread take that same mutex briefly and always make progress.

---

## 4. Truthfulness rules that are explicitly implemented

- **Nothing is simulated.** Stop positions come from
  `machine.current_user_relevant_span()` resolved through rustc's `SourceMap`;
  frames from `active_thread_stack()`.
- **Dead locals are never read.** `Frame::locals[local].access()` raises
  `throw_ub!(DeadLocal)` for a not-yet-live local, so the adapter checks
  `as_mplace_or_imm().is_some()` first and reports
  `QFLI_LOCAL_UNINITIALIZED` instead. Without this a debugger would fabricate
  UB diagnostics on every poll.
- **Values are exact or absent.** Scalars (bool/char/integer/float) are rendered
  precisely, with signedness from the layout (`-1i8` prints `-1`). Aggregates,
  references, pointers and unions are reported `QFLI_LOCAL_UNSUPPORTED`; there is
  no public `OpTy` pretty-printer in the pinned source, so guessing is not an
  option.
- **`QfliLocalState` is exhaustive and explicit**, so a frontend shows
  "uninitialized"/"unsupported" instead of silently hiding a variable.
- **Step-over/step-out are real, not aliases.** They compare
  `active_thread_stack().len()` before/after each step. If that ever proved
  inadequate the honest move is to clear the corresponding capability bit, not
  to degrade to step-in.
- **Capabilities are authoritative.** `qfli_miri_debug_capabilities()` returns
  the bits the loop really implements; the C test fails if any advertised bit is
  missing.
- **Miri findings are reported through Miri.** On `miri_step` error the adapter
  calls `miri::report_result`, which distinguishes normal termination
  (`Some((code, leak_check))`) from a reported error (`None`), and emits the
  diagnostics itself.

---

## 5. Pause / resume contract

`start` and `resume` are **blocking** and return when the session reaches the
next pause or a terminal state.

| Return | Meaning |
| --- | --- |
| `0` | paused; `qfli_miri_debug_pause_info` is readable |
| `2` | reserved for a compiler-busy answer (see §7) |
| `-1` | null session, already-started session, not-paused resume, or a compile failure |

`QfliDebugPause.reason` is one of `ENTRY`, `BREAKPOINT`, `STEP`,
`REQUESTED`, `TERMINATED`, `ERROR`, `LIMIT`. `TERMINATED` carries `exit_code`.

---

## 6. Test fixture expectations (real, measured)

Line maps are asserted by `debug_abi_test.c` and are stable:

**`debug_basic.rs`** — `let a = 1;` line 9, `let b = 2;` line 10,
`let sum = a + b;` line 11, `println!` line 12.
The test requires the entry pause (`reason=ENTRY`, `steps=0`), steps until line
9 becomes current, and asserts `a` is either exactly `"1"` or uninitialized —
never a wrong value.

**`debug_breakpoint.rs`** — `double` body line 10, `let value = 21;` line 14,
`let doubled = double(value);` line 15 (the breakpoint), `assert_eq!` line 16.
The test asserts: pause reason `BREAKPOINT` on line 15; `value == "21"`;
step-in reaches line 10 with `value == "21"`; step-over never reaches line 10 and
does not change stack depth.

**`debug_locals.rs`** — `small = -1i8` line 12, `letter = 'A'` 13,
`flag = true` 14, `pair = (1, 2)` 15, `text = "hi"` 16, `let later;` 17,
`later = small as i32;` 18. At line 18 the test asserts exactly:
`small == "-1"`, `letter == "'A'"`, `flag == "true"`,
`pair` → `UNSUPPORTED`, `text` → `UNSUPPORTED`,
`later` → `UNINITIALIZED`, and `small.type_name == "i8"`.

**`debug_type_error.rs`** — E0308 on line 7. The test asserts `start` returns
`-1`, the pause reason is `ERROR`, and the diagnostics channel contains `E0308`.

All four fixtures were compiled with the pinned rustc: the first three are clean
programs, the fourth produces `E0308`.

---

## 7. Known gaps / decisions to confirm

1. **`2` (compiler busy) is not yet produced by `start`.** Because the worker
   thread takes `COMPILER_LOCK` with a blocking `lock()`, a debug session that
   starts while an analysis/run holds the compiler *waits* instead of returning
   `2`. If you want the same fail-fast semantics as `qfli_miri_analyze`, the
   one-line change is to use `COMPILER_LOCK.try_lock()` in `spawn_worker` and
   publish `FAILED` when it is unavailable. I left the blocking form because a
   debug start is a foreground action and waiting is more useful than failing;
   say which behaviour you want and I will change it.
2. **Single-thread limitation is inherited.** `miri_step` steps the active
   thread; Miri's own stepping path carries a single-thread FIXME. Multi-threaded
   fixtures are not covered by the test, and the capability set does not claim
   per-thread debugging.
3. **`REQUESTED` pause granularity.** `qfli_miri_debug_pause` takes effect at the
   next step boundary, so a program blocked inside one long step is not
   interrupted. This is stated in the header.
4. **Host verification is type-check only.** The adapter compiles clean with
   `-D warnings` against the pinned rustc, but `miri` was a
   signature-compatible **stub** (`$TEMP/qfli-analysis-check/stub`), because the
   crate registry is empty on this host. Real signatures were read from the
   pinned source, and two stub inaccuracies were found and corrected during this
   work (`Provenance` is a concrete enum, not a trait; the thread stack type is
   `Frame<'tcx, Provenance, FrameExtra<'tcx>>`). A real `cargo build` can still
   surface a signature mismatch, which is what root's build will reveal.

---

## 8. What root should run

```
# build the adapter as usual (now including mod debug)
scripts/build_miri_adapter.sh ...

# run the ABI tests against the real library
native/miri_adapter/debug_abi_test.c <libqfli_miri.so> <MIR-sysroot> <native/fixtures>
```

Expected output, first failure first:

```
PASS debug symbols and null handling
PASS debug config validation
PASS debug entry pause and step-in
PASS debug breakpoint and step-in into a call
PASS debug step-over stays in the caller
PASS debug locals values and states
PASS debug cancel while paused
PASS debug step budget
PASS debug source error reports an error pause
```

The test exits `3` and prints `SKIP` if the debug symbols are absent, so an
older `.so` cannot masquerade as a pass. It will also fail loudly (not skip) if
any advertised capability is missing.

Highest-risk assertions, in the order they are likely to break if a real
signature differs from the stub: the `create_ecx` call shape, the
`local_at_frame_to_op(frame, local, None)` call, and
`report_result(&ecx, error)` destructuring.

---

## 9. Deliberately not built

- No `evaluate expression` command: it needs a full expression parser over
  `InterpCx` and cannot be implemented honestly today.
- No data watchpoints / conditional breakpoints: Miri exposes no hook for them.
- No per-thread stepping (see §7.2).
- No shared session type between run/analysis/debug: `QfliDebugSession` is
  opaque and distinct, as required.
