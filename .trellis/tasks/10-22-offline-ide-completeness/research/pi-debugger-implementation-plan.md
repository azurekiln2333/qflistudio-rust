# Native analysis ABI: independent review + debugger implementation plan

Status: review of delivered code, plus the fixes applied for the first real
Linux failure, plus a design for a real debugger.

**Update (root built the real pinned Linux adapter):** run ABI passed 13/13
(`build/offline-ide-audit/native-linux-run-abi.log`); analysis ABI failed on the
first type fixture with `state=4 exit=124` / `session basic block limit reached`
(`native-linux-analysis-abi.log`). That is exactly **R6** below, confirmed on
device-class code rather than by inspection. R1, R2, R4, R5 and R6 are now
fixed in `native/miri_adapter/src/lib.rs` + `analysis_abi_test.c`; see §1.4 for
the applied diff summary and rebuild readiness.

Pinned: Rust **1.98.1**, commit `48a229ceaefd4985c50990b14116b6d856af0985`.
Miri source fingerprint `92f51c0345496c6ef1edbba009985c84b612630dd5c7e81ea2cdd826d0d85764`.

Scope split for the whole feature:

| Track | Runs user code? | ABI | Status |
| --- | --- | --- | --- |
| **Analysis** (`qfli_miri_analyze`) | no | `QfliAnalysisConfig` | implemented, awaiting real build/test |
| **Debug** (`qfli_miri_debug_*`) | yes, under Miri | new, separate | design only (this file, §2) |

Keeping these separate is deliberate: analysis must never gain an execution
path, and debugging must never be faked with simulated breakpoints.

---

## 1. Review of the delivered analysis ABI

Line numbers refer to `native/miri_adapter/src/lib.rs` at review time (796 lines).

### 1.1 What is correct

- **Run path is byte-compatible.** `run_session` (461-500) still locks
  `COMPILER_LOCK` *inside* the unwinding closure (468), still uses
  `AnnotateSnippetEmitter` (277) via `CompilerCallbacks::config`, and the argv
  (470-476) is unchanged. Analysis adds a *separate* emitter (614-626) and a
  separate callback type (628-681); it cannot alter run output.
- **Layouts untouched.** `QfliConfig` (53-64) and `QfliResult` (79-84) are
  unchanged; the extension is `QfliAnalysisConfig` (67-76) only.
- **Busy is truly non-blocking and retryable** (736-740): `try_compiler()`
  uses `try_lock`, so a busy answer does not queue. The `started` flag is only
  consumed at 741, *after* the compiler was acquired, so a retry works.
- **Analysis cannot reach evaluation.** `after_analysis` returns
  `Compilation::Stop` (679) and `entry_fn`/`eval_entry` are never called on
  this path; no `cfg(miri)`, no `always_encode_mir`, no `extra_symbols`
  (698-701 comment + absence of the flags).
- **Analysis options are session-scoped** (102-106), so two concurrent
  analysis sessions cannot read each other's crate name/edition.
- **Silent abort is no longer reported as clean** (783-789): `Ok(false)` and
  `Err` both require `emitted > 0` to count as a source verdict.

### 1.2 Actual regression risks

Severity: **H** = can corrupt results or crash; **M** = wrong status, no crash;
**L** = cosmetic/robustness.

#### R1 — `destroy` guard has a window that can still free a live session — **H**

```rust
// run_session, 463-464
if session.started.swap(true, Ordering::AcqRel) { return -1; }
let _active = ActiveCall::begin(&session.active);      // <-- window here
```
```rust
// qfli_miri_destroy, 551-557
if unsafe { session.as_ref() }.is_some_and(|s| s.active.load(Ordering::Acquire) != 0) {
    return;
}
drop(unsafe { Box::from_raw(session) });
```

Between 463 and 464 the session is "started" but `active == 0`, so a concurrent
`destroy` sees an idle session and frees it. Line 465 (`lock(&session.result)`)
then writes to freed memory. The guard closes the *long* window (the whole
compile) but not this one. Analysis has the same shape at 741-742.

The guard is also advisory in the other direction: after `destroy` returns
without freeing, the caller has no way to learn that it must retry, so a
correct client can leak permanently without any signal.

**Fix (design, not applied):** make the flag the *first* thing touched, and
make it authoritative rather than advisory.

```rust
// replace AtomicU32 active + AtomicBool started with one owner-counted state
struct Lifetime { owners: AtomicU32 }   // bits 0..=30 = in-flight calls,
                                        // bit 31       = destroyed-requested
```
`begin()` must be an atomic RMW that fails if the destroyed bit is set:
`fetch_update(|n| (n & DESTROYED == 0).then(|| n.wrapping_add(1)))`. On failure
the call returns `-1` and the session is left alone. `destroy` sets the
DESTROYED bit and frees only when `owners == DESTROYED` (no in-flight calls).
That removes both the window and the silent leak. Until then, the contract's
"do not destroy while busy" is load-bearing and must stay documented.

#### R2 — `run_session` starts the timeout clock before acquiring the compiler — **M**

```rust
// 465-469
lock(&session.result).state = RUNNING;
*lock(&session.io.start) = Some(Instant::now());   // clock starts here
let result = catch_unwind(AssertUnwindSafe(|| {
    let _guard = lock(&COMPILER_LOCK);             // may block for a whole run
    if session.io.check_stop() { return 1; }
```

`start` is set *before* the blocking `lock`. If another session is running, the
waiting run burns its own `timeout_ms` while queued, and can then be reported
`LIMIT_REACHED`/`124` — with reason "session time limit reached" — **without
having executed a single guest instruction**. Analysis deliberately avoids this
by checking busy first (736), but the *run* path still has it, and the analysis
path would inherit it if `try_compiler` were ever relaxed.

This is pre-existing (not introduced by the analysis work), but it is a real
wrong-status bug and it interacts with the busy design, so it should be fixed
in the same pass: move the clock start to immediately after the lock is taken.

#### R3 — `check_stop` overwrites the cancel reason — **M**

```rust
// SessionIo::stop, 134-137
fn stop(&self, state: u32, reason: &'static str) {
    if self.stopped.compare_exchange(0, state, Ordering::AcqRel, Ordering::Acquire).is_ok() {
        *lock(&self.stop_reason) = Some(reason);
    }
}
```
`stop` is correctly first-wins for `state`. But look at `check_stop` (153-165):
the `cancelled` branch returns early (156), so cancel wins there — good. The
remaining two `stop` calls (159, 162) and `append`'s `stop` (147) are
first-wins too. So `state` is consistent.

The real defect is narrower: **cancellation is not sticky.** `cancelled` is
never cleared, so a *cancelled session cannot be reused*, which matches
"one compilation per session" — fine. But `cancel_session` (510-514) succeeds
even when the session has already finished, and `check_stop` is the only
consumer. For analysis, a cancel that arrives *after* `after_analysis`'s
`check_stop` (676) has no effect at all, and the caller is told `FINISHED`/`0`
even though it requested cancel. That is acceptable (the result is valid) but
the contract should say so explicitly rather than implying cancel always wins.

Worse case: cancel arriving during the compiler's own teardown is *silently
dropped*; a client that relies on cancel to avoid wasted work gets no signal.

**Fix:** expose the final snapshot honestly — `QfliResult` already carries
`state`, so document "cancel after `after_analysis` yields `FINISHED`" and have
the client treat `FINISHED` as authoritative. No code change required, but the
header comment at 528-534 must not claim cancel is conclusive.

#### R4 — `append` uses a `max_output - 512` bound that can underflow — **M**

```rust
// SessionIo::append, 140-151
let bound = if channel == 2 { self.max_output } else { self.max_output - 512 };
let available = bound.saturating_sub(total);
```

`available` is saturating, but `self.max_output - 512` is **not**. Both
constructors validate `max_output_bytes >= 1024` (create at 428, analysis at
696), so today it cannot underflow. It is one validation edit away from a panic
in a `pub extern "C"` path (`ffi_guard` would catch it, turning a stdout write
into `-1`/`INTERNAL_ERROR`).

Also note the accounting bug: `total` is the sum of *all three* channels, so a
session that has filled stdout reduces the budget available to diagnostics, and
`max_output` is documented as a *per-channel* diagnostics bound. For analysis
`max_output_bytes` is documented as "diagnostics channel bound" (header 84-85)
but is enforced against the **combined** size of channels 0..2. Since analysis
never writes channels 0/1 except `DiagnosticWriter`, which writes to 2, it
happens to work — but the guarantee is accidental.

**Fix:** use `saturating_sub(512)` and enforce the analysis bound per-channel
(`outputs[2].len()`), or restate the header as a total bound.

#### R5 — `BUSY` is written into `result.state` and is sticky — **M**

```rust
// 736-740
let Some(_guard) = try_compiler() else {
    if session.started.load(Ordering::Acquire) { return -1; }
    lock(&session.result).state = BUSY;
    return 2;
};
```

Two issues.

1. A busy answer **mutates observable state**. A client polling
   `qfli_miri_result` to detect `RUNNING`/`FINISHED` can observe `6` and must
   special-case it. `BUSY` is a *call* result, which is already the `2` return
   value; putting it in `QfliResult.state` duplicates it in a place clients are
   told to treat as the session's terminal status (header 96-99 lists states as
   terminal/discovery values).
2. It races with destroy: setting `state` after another thread freed the
   session is the same bug class as R1 (the window is between the `started`
   re-check at 737 and the `result` write at 738).

**Fix:** drop the state write entirely; return `2` only. If a state is wanted
for observability, use a separate `AtomicU32` "last call outcome" that is never
described as session status.

#### R6 — analysis sessions are created with `max_blocks = 0`, so every analysis fails — **H (confirmed)**

```rust
// 714  (create_analysis_session)
io: new_session_io(Vec::new(), 0, config.timeout_ms, config.max_output_bytes, 0),
//            input ─────────┘  max_blocks = 0                          max_memory = 0
```
```rust
// 153-165  SessionIo::check_stop
fn check_stop(&self) -> bool {
    if self.cancelled.load(Ordering::Acquire) { ... return true; }
    if self.blocks.load(Ordering::Relaxed) >= self.max_blocks {     // 158
        self.stop(LIMIT_REACHED, "session basic block limit reached");
    }
    ...
    self.stopped.load(Ordering::Acquire) != 0
}
```

With `max_blocks == 0` and `blocks == 0`, line 158 evaluates `0 >= 0` → true,
so `stop(LIMIT_REACHED, ...)` runs and `check_stop` returns `true`.

The three call sites of `check_stop` in the analysis path are lines 655, 663
and 676 (the `after_*` callbacks) and line 754 (`analyze_session`). Line 754
runs **before** rustc is invoked:

```rust
// 753-754
let analysed = catch_unwind(AssertUnwindSafe(|| {
    if session.io.check_stop() { return false; }   // always true → returns here
```

So `analysed == false`, `stopped == LIMIT_REACHED`, `emitted == 0`, and the
match at 783-789 resolves to `(stopped, 124)` — i.e. **every analysis is
reported `LIMIT_REACHED`/124 with reason "session basic block limit reached",
and rustc is never called.** It cannot reach `FINISHED` for any fixture.

(The 655/663/676 sites would fire the same way if 754 were removed, so this is
not a single-site bug.)

**Consequence for the review record:** no earlier statement that analysis
"works" is supportable. The stub-based type check could not catch this because
it is a runtime logic error, not a type error. `analysis_abi_test.c`
*will* catch it — its first `clean()` assertion requires
`state == FINISHED`, so it fails immediately. Running that test against the
real pinned build is therefore the highest-value next action, and the analysis
track must be reported as **broken, unverified** until it passes.

`max_memory = 0` has the same shape (183-193): any `reserve_memory` fails.
Analysis does not execute, so it is unreachable today, but it is a landmine.

**Fix:** analysis must not inherit execution limits. Either pass
`u64::MAX` for both, or give analysis its own minimal I/O type so the run
limits are structurally absent rather than "present but disabled by magic
values". The latter is safer, because a future `check_stop` added to the
analysis path would silently reintroduce this class of bug.

#### R7 — analysis `check_stop` at `after_analysis` converts success into a limit — **M**

```rust
// 674-679
if self.io.check_stop() { return Compilation::Stop; }
self.analysed = true;
Compilation::Stop
```

If the timeout elapses *during* type checking, the run is reported
`LIMIT_REACHED`/124 and `analysed` stays false — which is the intent. But
combined with R6 this line is also the second place where `max_blocks == 0`
would poison the result. Once R6 is fixed this becomes correct behaviour.

#### R8 — `ffi_guard` converts a poisoned panic into a plausible-looking result — **L**

`ffi_guard` (129-131) maps a panic to the caller-supplied fallback. For
`qfli_miri_analyze` the fallback is `-1`, which the header documents as
"null session, already-used session, or rejected execution" (header 90-92). A
panic therefore looks like a client bug, not an interpreter fault. For
`qfli_miri_run` the fallback is also `-1`, while `run_session`'s own panic path
(493-497) correctly produces `INTERNAL_ERROR`. Inconsistent: a panic inside
`run_session`'s outer `catch_unwind` (which does not cover 463-466) surfaces as
`-1`, indistinguishable from "invalid argument".

**Fix:** give the outer guard its own distinguishable return (e.g. `-2`) or
route it through the same `INTERNAL_ERROR` + message path.

#### R9 — `BUSY` (6) is not in the header's `QfliState` enum — **L**

The header puts `QFLI_BUSY` in a separate `enum QfliAnalysisState` (44-45) to
avoid touching `QfliState`, which is the right call for layout stability
(`QfliState` is a plain `enum` used as `uint32_t`). But the value `6` then
occupies the same field. The header must state that `QfliResult.state` may
carry `6` only as a *transient call outcome* (R5) — or R5 should be adopted and
the value removed entirely.

#### R10 — `try_compiler` recovers a poisoned `COMPILER_LOCK` — **L, but note it**

```rust
// 588-594
Err(std::sync::TryLockError::Poisoned(poison)) => Some(poison.into_inner()),
```

Recovering is right for availability, but rustc's global state is genuinely
compromised after a compiler panic; letting the next analysis proceed can
produce cascading nonsense. The run path's `lock()` (125-127) does the same, so
this is consistent, not a new risk — but a poisoned compiler should arguably
latch `INTERNAL_ERROR` for the process rather than be silently retried.

### 1.3 Review of the test that is supposed to prove all this

`native/miri_adapter/analysis_abi_test.c` is well shaped, but note what it
cannot catch:

- It asserts `state == FINISHED` for clean fixtures, so **R6 fails loudly** —
  this is the test that must be run first.
- It does **not** cover R1/R5 (destroy/busy race): `compiler_busy` (…)
  serialises, it never races `destroy` against an in-flight `analyze`.
- `output_bound` greps for the substring `"limit"`, which matches the
  *reason text*, so it would pass on the R6 block-limit path too if a fixture
  produced one diagnostic. It must assert the reason is the **output** limit.

Recommended additions before the analysis track is called done: a race test for
R1, an assertion that `analyze` on an idle session returns `state == RUNNING`
and *not* `BUSY`, and a positive check that a clean analysis reports
`basic_blocks == 0`.

### 1.4 Fixes applied (source is rebuild-ready)

All changes are confined to `native/miri_adapter/src/lib.rs`,
`native/miri_adapter/qfli_miri.h` and `native/miri_adapter/analysis_abi_test.c`.
No Flutter, device, core or sibling files touched.

| Item | Fix |
| --- | --- |
| **R6 (the actual failure)** | `SessionIo::max_blocks`/`max_memory` are now `Option<u64>`; `None` means the session kind has **no such limit**. Analysis passes `None, None`; run passes `Some(config.*)`. `check_stop` uses `max_blocks.is_some_and(...)`, so the block branch is structurally unreachable for analysis instead of tripping on a `0` sentinel. `reserve_memory` accounts but never refuses when unbounded. |
| **R1** | `active: AtomicU32` replaced by `owners: AtomicU32` with bit 31 = `DESTROYED` latch. `ActiveCall::begin` is an atomic `fetch_update` that fails once latched; both call sites take it **before** claiming `started`. `destroy` latches with `fetch_or` and only frees when the count is exactly `DESTROYED`. |
| **R2** | The timeout clock now starts *after* `COMPILER_LOCK` is acquired (inside the closure), so time spent queueing is not charged as run time. |
| **R4** | `max_output - 512` → `saturating_sub(512)`. Combined-budget accounting kept unchanged so run-path output-limit semantics are byte-identical. |
| **R5** | A busy answer no longer writes `result.state`; it returns `2` only. The constant is now `BUSY_RETURN: i32 = 2`. `QFLI_BUSY` stays in the header for source compatibility but is documented as a return-code meaning, not a session status. |
| **R8 (partial)** | Documented; not changed. A panic before the inner `catch_unwind` still maps to `-1`. |

Test changes in `analysis_abi_test.c`:

- `compiler_busy` now asserts `code == 2`, `state == QFLI_READY`,
  `exit_code == -1` — i.e. the busy answer did **not** disturb session status.
- New `no_block_limit` check asserts a clean analysis reaches `FINISHED`/`0`
  with `basic_blocks == 0` and never contains `"basic block limit"`. This is
  the direct regression test for the observed failure.
- `output_bound` now requires the reason to contain `"output limit"` and to
  **not** contain `"basic block limit"`, so the old `"limit"` grep can no
  longer pass on the wrong stop reason.

### 1.5 Rebuild readiness

**Round 2 (current): native library rebuilt OK; the run ABI still passes. The
analysis ABI now gets further and fails on a *test expectation*, not the
adapter.**

Observed (`build/offline-ide-audit/native-linux-abi-fixed.log`):

```
span 33..47 = ""not a number"", expected "not a number"
```

The adapter was **right**: the primary span of E0308 is the string literal
*including its quotes*, 14 bytes at 33..47. The test expected the bare contents
(12 of 14 bytes). Fixed: the expectation is now `"\"not a number\""`, and the
byte offset is pinned to 33 so a span-base regression cannot pass by luck.

Three further test-only defects found by auditing every expectation against the
pinned rustc rather than fixing just the reported one:

| Check | Defect | Fix |
| --- | --- | --- |
| `output_bound` | Used `analysis_syntax`, whose JSON is only **887 bytes** — *under* the 1024 bound, so it would never truncate and the check would fail for the wrong reason. It also asserted the reason text `"output limit"`, which is unobservable: when the diagnostics channel is what fills up, the reason append has zero room and is itself truncated. | Switched to `analysis_type` (**2425 bytes**, dominated by `code.explanation`), and asserts only the observable contract: `state == LIMIT_REACHED`, `exit_code == 124`, length `<= max_output_bytes`. |
| `analysis_type` span | Bare contents instead of the quoted literal. | Quoted literal + pinned offset 33. |
| `analysis_syntax` / `analysis_unicode` / `E0601` / clean fixtures | Audited, **no change needed** — see verified table below. | — |

Every expectation is now measured, not assumed:

| Fixture | Verified via pinned rustc | Assertion |
| --- | --- | --- |
| `analysis_type` (bin) | `E0308`, primary 33..47 = `"not a number"`, line 2, cols 22..36 | `E0308` + span text + offset 33 |
| `analysis_syntax` (bin) | error, primary 28..29 = `;`, no code | level error only (no span assert) |
| `analysis_unicode` (bin) | `E0308`, primary 99..104 = `label`, line 4, cols 22..27 | `E0308` + span text + offset 99 |
| `analysis_valid` (bin) | exit 0, **0** JSON lines | clean (no error, no warning) |
| `analysis_library` (lib) | exit 0, **0** JSON lines | clean |
| `analysis_library` (bin) | `E0601` “`main` function not found” | `E0601` present |
| `analysis_cfg_miri` (bin) | exit 0, **0** JSON lines | clean (would fail if `cfg(miri)` were set) |
| `analysis_nonexecution` (bin) | exit 0, **0** JSON lines | clean + no `EXECUTED` anywhere |

Also verified locally this round (no WSL, no build, no device):

- `analysis_abi_test.c` compiles clean for **both** OHOS ABIs with
  `-Wall -Wextra -Werror`; compile-time ABI assertions still hold
  (`QfliAnalysisConfig` 56 bytes, `QfliResult` 24 bytes).
- `native/miri_adapter/src/lib.rs` and `qfli_miri.h` were **not modified** in
  this round (source additions on hold). The adapter still type-checks with
  `-D warnings` against the pinned rustc via the `miri` signature stub.
- Span expectations byte-compared against the fixture files themselves
  (bytes 33..47 == `"not a number"`, bytes 99..104 == `label`).

**Ready for the next root C compile + run.** Only
`native/miri_adapter/analysis_abi_test.c` changed; no `.so` rebuild is strictly
required (the library already built successfully and its behaviour is
unchanged), though rebuilding is harmless.

Expected next output, in order: `PASS analysis symbols and null handling`,
`PASS analysis config validation and single use`, `PASS analysis diagnostic
analysis_type`, `analysis_syntax`, `analysis_unicode`, three `clean` lines,
`PASS analysis crate type selects main requirement`, `PASS analysis does not
execute the program`, `PASS analysis output bound`, `PASS analysis has no block
budget`, `PASS analysis cancellation`, `PASS analysis compiler busy and retry`.

Residual risk if it still stops: the only unproven runtime assumptions left are
(a) whether the adapter's E0308 JSON is still >1024 bytes after dropping
`abort_if_errors`/`failure-note` lines (it was 2425 via the CLI, and the
explanation alone dominates), and (b) whether `basic_blocks` is exactly 0 for
analysis (it is never incremented without interpretation).

Note on the Linux driver: the `LD_PRELOAD` requirement for static TLS is an
environmental property of that driver, not an adapter defect, and is unaffected
by these changes.

### 1.6 Still open

- R8: a panic outside the inner `catch_unwind` is still reported as `-1`
  (indistinguishable from an invalid argument).
- R3: cancellation that lands after `after_analysis` yields `FINISHED`; correct
  but must be documented to clients (header already says `FINISHED` is
  authoritative).
- R10: a poisoned `COMPILER_LOCK` is recovered and retried rather than latching
  a process-wide failure.

---

## 2. Debugger design (real Miri stepping, no fake controls)

This section is intentionally separate from §1. Analysis is a compiler-only
path with no execution; the debugger is an execution path. They must not share
a session type, and neither may borrow the other's flags.

### 2.1 Non-negotiable capabilities, verified against pinned source

| Capability | Pinned API | Evidence |
| --- | --- | --- |
| Build an interpreter | `miri::create_ecx(tcx, entry_id, entry_type, &config, None)` | `miri/src/eval.rs:343`, doc "Public because this is also used by `priroda`" |
| Entry point | `miri::entry_fn(tcx) -> (DefId, MiriEntryFnType)` | `miri/src/eval.rs:40` |
| One step | `ecx.miri_step()` | `miri/src/concurrency/thread.rs:860`, doc "Public because this is used by Priroda" |
| Frame stack | `ecx.active_thread_stack() -> &[Frame]` | `thread.rs:487` |
| Current MIR location | `frame.current_loc() -> Either<mir::Location, Span>` | `rustc_const_eval/src/interpret/stack.rs:270`, doc "Used by priroda" |
| Current source span | `frame.body()` + `body.source_info(loc).span`; Miri helper `current_user_relevant_span()` | `thread.rs:291`, `helpers.rs` |
| Local names/types | `frame.body().local_decls`, `body.var_debug_info` (`VarDebugInfoContents::Place`) | priroda `main.rs:351-390` (proven pattern) |
| Local **values** | `ecx.local_at_frame_to_op(frame, local, None)` | `operand.rs:740`, doc "public because it is used by Aquascope" — reads `frame.locals[local]` internally despite the field being private |
| Report a Miri finding | `miri::report_result(...)` | `diagnostics.rs:240` |

### 2.2 Hard limits that shape the design

1. **`miri_step` returns `InterpResult`.** It propagates `MachineStop` (program
   terminated) and UB errors via `?`. The debugger driver must match on the
   result: `Ok` = step succeeded, `Err` with `MachineStop(TerminationInfo)` =
   normal/bounded termination, any other `Err` = UB/unsupported. Do not
   `.unwrap()` and do not convert everything to "stopped".
2. **`LocalValue` is `pub(super)`.** Reading a local through
   `local_at_frame_to_op` calls `frame.locals[local].access()`, which
   `throw_ub!(DeadLocal)` for a not-yet-live or already-dead local
   (`stack.rs:184-189`). **Polling locals naively fabricates UB diagnostics.**
   The driver must pre-check with `LocalState::as_mplace_or_imm() -> Option<_>`
   (`stack.rs:172`, returns `None` when `Dead`) before formatting a value, or
   catch and drop the `DeadLocal` error without reporting it.
3. **No pretty-printer for `OpTy`.** There is no public "render this value as
   source text" API. Values must be rendered by the adapter (immediate
   scalar/pointer/bytes with a depth+sized limit), and anything unsupported must
   be reported as `<unsupported: {ty}>`, never invented.
4. **Only the main thread is debuggable.** Miri's stepping path carries a
   known single-thread limitation; `miri_step` steps the *active* thread, and
   `active_thread_stack` is that thread's stack. Multi-threaded programs can
   only be presented as "thread N active", not stepped per-thread, without
   upstream work.
5. **`create_ecx` needs a MIR-encoded sysroot**, exactly like the run path
   (`-Zalways-encode-mir` was used at build time). This is already true of the
   MIR sysroot the run path ships, so reuse it; do not build a second one.
6. **`eval_entry` cannot host a debugger.** It takes ownership of the loop. The
   debugger must therefore *not* go through `eval_entry` and instead drive
   `create_ecx` + `miri_step` itself — i.e. it replaces part of `eval.rs`, not
   wraps it.

### 2.3 Integration seams in `lib.rs`

The debugger is a third callback type. It reuses the *existing* codegen-backend
and sysroot plumbing, and nothing else.

```
create_session (421) ──► resolve_backend (383) / claim_backend (395)
                          new_session_io (405)  ── reuse, see §2.6
qfli_miri_run (457)  ──► CompilerCallbacks (255)  ──► after_analysis ──► eval_entry   [existing]
qfli_miri_analyze    ──► AnalysisCallbacks (628)  ──► after_analysis ──► Stop          [existing]
qfli_miri_debug_*    ──► DebugCallbacks (new)     ──► after_analysis ──► create_ecx + own loop
```

Concretely, `DebugCallbacks::after_analysis` is the seam:

```rust
fn after_analysis<'tcx>(&mut self, _: &Compiler, tcx: TyCtxt<'tcx>) -> Compilation {
    if self.io.check_stop() { return Compilation::Stop; }
    let (entry_def_id, entry_type) = miri::entry_fn(tcx);       // eval.rs:40
    let mut config = self.miri_config.clone();                  // as CompilerCallbacks does today
    config.communicate = false;
    let ecx = miri::create_ecx(tcx, entry_def_id, entry_type, &config, None)?
        .discard_err();                                          // eval.rs:343
    // hand `ecx` + callbacks to the debug loop below, then Stop
    Compilation::Stop
}
```

The loop is the only new algorithmic code:

```rust
// Pseudocode, one step at a time, with cooperative checks between steps.
loop {
    if callbacks.check_stop() { return Cancelled }          // cancel/timeout/output
    if callbacks.should_pause_here(&ecx) {                   // breakpoint / step / pause
        callbacks.publish_state(&ecx);                       // stack + locals snapshot
        callbacks.wait_for_command();                        // blocks this thread only
    }
    match ecx.miri_step() {                                  // thread.rs:860
        Ok(()) => {}
        Err(e) if is_machine_stop(&e) => return Finished(e),
        Err(e) => return MiriError(e),                       // UB: report verbatim
    }
    callbacks.blocks.fetch_add(1, Relaxed);
}
```

`should_pause_here` folds three triggers, all computed from real state:

- **step command**: `Step { kind: In | Over | Out }`. `Step`/`Out` need the
  frame depth from `active_thread_stack().len()`; `Over` additionally requires
  that the *current* frame is still on top before pausing again. There is no
  way to fake `Over` — it is depth comparison, and if the depth API is not
  available the command must be reported unsupported rather than silently
  behaving like `Step`.
- **breakpoint**: match the *source* position of the current frame.
  The authoritative position is `frame.current_loc()`; for
  `Either::Left(loc)` use `frame.body().source_info(loc).span`, for
  `Either::Right(span)` use that span directly (frame-init / unwinding). Use
  Miri's `current_user_relevant_span()` when the raw span is a macro expansion
  so the breakpoint matches the *call site* the user sees. Compare on
  `(file, line)` from the pinned `SourceMap` — reuse the same span→line logic as
  the analysis consumer, so both tracks agree about CRLF/BOM.
- **pause request**: a plain flag, so the IDE can break into a runaway program.

Breakpoint resolution happens **client-side** (the IDE owns the buffer and its
line numbers) or adapter-side via a `(file, line) -> ()` set; the adapter must
not re-parse source text. Lines are matched after the same normalisation the
analysis track documents.

### 2.4 Minimal ABI

Design goal: the smallest surface that can express real stepping. One session
per debug session, one blocking control call on a worker thread, snapshots read
from the session. No control exists that the adapter cannot honour.

```c
enum QfliDebugCrateType { QFLI_DEBUG_CRATE_BIN = 0, QFLI_DEBUG_CRATE_LIB = 1 };

typedef struct {
    uint32_t abi_version;     /* 1 */
    const char *source_path;  /* absolute UTF-8 crate root, copied */
    const char *sysroot_path; /* MIR-encoded sysroot, absolute, copied */
    const char *crate_name;   /* 1..=64 [A-Za-z0-9_] */
    uint32_t edition;         /* 2015|2018|2021|2024 */
    uint32_t crate_type;      /* enum QfliDebugCrateType */
    uint64_t timeout_ms;      /* total wall clock for the whole session */
    uint64_t max_steps;       /* hard step budget; >0 */
    size_t max_output_bytes;  /* channel 2 bound, 1024..=16MiB */
    /* Breakpoints given up front, so the first step already honours them. */
    const QfliBreakpoint *breakpoints;
    size_t breakpoint_count;
} QfliDebugConfig;

typedef struct {
    const char *file_path;    /* absolute UTF-8, as rustc sees it */
    uint32_t line;            /* 1-based */
    uint32_t column;          /* 1-based char column, 0 = whole line */
} QfliBreakpoint;

enum QfliResume { QFLI_RESUME_CONTINUE = 0, QFLI_RESUME_STEP_IN = 1,
                  QFLI_RESUME_STEP_OVER = 2, QFLI_RESUME_STEP_OUT = 3 };

enum QfliPauseReason { QFLI_PAUSE_ENTRY = 0, QFLI_PAUSE_BREAKPOINT = 1,
                       QFLI_PAUSE_STEP = 2, QFLI_PAUSE_REQUESTED = 3,
                       QFLI_PAUSE_TERMINATED = 4, QFLI_PAUSE_ERROR = 5,
                       QFLI_PAUSE_LIMIT = 6 };

typedef struct {
    uint32_t reason;          /* enum QfliPauseReason */
    uint32_t frame_count;
    uint64_t steps;
    int32_t  exit_code;       /* valid only when reason == TERMINATED */
} QfliPause;

QfliSession *qfli_miri_create_debug(const QfliDebugConfig *, const char *backend_path);
/* Runs to the first pause. Returns 0 when `QfliPause` is readable, -1 invalid,
 * 2 compiler busy (session not consumed, retryable). */
int32_t qfli_miri_debug_start(QfliSession *session);
/* Resume from the current pause under `cmd`. Same return codes as start.
 * Calling it in any state other than "paused" returns -1. */
int32_t qfli_miri_debug_resume(QfliSession *session, uint32_t cmd);
/* Request a pause at the next step boundary. Safe from any thread. */
void qfli_miri_debug_pause(QfliSession *session);
/* Snapshot readers; valid while paused. */ 
int32_t qfli_miri_debug_pause_info(const QfliSession *, QfliPause *);
size_t  qfli_miri_debug_frame_count(const QfliSession *);
int32_t qfli_miri_debug_frame(const QfliSession *, size_t index, QfliFrame *);
size_t  qfli_miri_debug_locals(const QfliSession *, size_t frame, QfliLocal *buffer, size_t capacity);
```

Reuses `qfli_miri_copy_output`, `qfli_miri_result`, `qfli_miri_destroy`,
`QfliResult`, `QfliState`. New symbol names only.

Why this shape:

- **`start` + `resume` instead of a command queue.** A queue implies an
  asynchronous worker the adapter does not have; `miri_step` must run on the
  thread that owns `ecx`. One blocking call per pause is the honest mapping.
- **Breakpoints at create time** so the entry point is not accidentally
  executed before the first breakpoint is installed.
- **`QfliPause.reason` is exhaustive** over the states the loop can actually
  observe, and `TERMINATED` is distinct from `LIMIT` and `ERROR`. No
  "paused" state is reported that the adapter did not reach.
- **Snapshots are pull-based and index-addressed**, so the adapter never has to
  push variable-size data across the FFI boundary mid-step.
- **No `evaluate expression` command.** It cannot be implemented honestly
  without a full expression parser over Miri's `InterpCx`; omitting it is
  better than shipping a control that always returns "unsupported".

`QfliFrame` / `QfliLocal` should mirror the proven priroda shape (index, name,
type string, rendered value, `Option`-like availability) and must carry an
explicit "value unavailable" state instead of omitting entries, so the IDE can
show `uninitialized` rather than silently hiding a variable.

### 2.5 What must *not* be built

- No breakpoint that the loop cannot test (e.g. data watchpoints, conditional
  expressions) — Miri has no such hooks, so those must stay out of the ABI.
- No per-thread stepping: single-thread is a real limitation; present it.
- No fabricated locals: if `local_at_frame_to_op` errors (dead local), report
  unavailable; never print a stale value.
- No shared session between analysis and debug; no `cfg(miri)` in analysis.
- No "resume" that ignores `max_steps`: the budget is what keeps a runaway
  print loop from hanging the device.

### 2.6 Reuse decisions

- **Reuse** `resolve_backend` (383), `claim_backend` (395), `path_string` (329),
  `crate_name_string` (598), `ffi_guard` (129), `lock` (125),
  `DiagnosticWriter` (208) and the `QfliSession` shell.
- **Do not reuse** `SessionIo`'s run limits for the debug loop as-is: `max_blocks`
  doubles as the step budget, which is fine, but `check_stop`'s
  `blocks >= max_blocks` semantics (R6) mean the debug session must start with a
  real budget, never `0`.
- **Do** reuse the `EncodeMIR` sysroot the run path already ships; a debug
  session and a run session must share backend identity anyway (`claim_backend`
  is process-global), which also means a debug session cannot coexist with a
  differently-configured run session — worth stating in the header.

### 2.7 Ordering of work

1. Fix R1/R2/R6 in the analysis/run paths first; they are correctness bugs and
   R6 blocks the debug loop's step budget semantics too.
2. Run `analysis_abi_test.c` against the real pinned build and make it pass.
   Until then the analysis track stays "unverified".
3. Implement `DebugCallbacks` + loop against `create_ecx`/`miri_step` with a
   single-step, no-breakpoint smoke test (entry pause, N steps, terminate).
4. Add breakpoints by source line, then locals with the dead-local guard.
5. Only then consider step-over/step-out; ship them as unsupported if the
   frame-depth comparison proves inadequate.

---

## 3. Evidence index

| Claim | Source |
| --- | --- |
| `create_ecx` public for priroda | `miri/src/eval.rs:341-349` |
| `entry_fn` | `miri/src/eval.rs:40` |
| `miri_step` public for Priroda | `miri/src/concurrency/thread.rs:858-874` |
| `active_thread_stack` | `miri/src/concurrency/thread.rs:487` |
| `current_loc -> Either<Location, Span>` | `rustc_const_eval/src/interpret/stack.rs:262-272` |
| `LocalValue::Dead` → `throw_ub!(DeadLocal)` on read | `rustc_const_eval/src/interpret/stack.rs:184-189` |
| `as_mplace_or_imm() -> None` for dead | `rustc_const_eval/src/interpret/stack.rs:172-180` |
| `local_at_frame_to_op` public for Aquascope | `rustc_const_eval/src/interpret/operand.rs:735-753` |
| priroda locals = names/types only | `miri/priroda/src/main.rs:351-390` |
| analysis emitter isolated from run emitter | `native/miri_adapter/src/lib.rs:277`, `:614-626` |
| busy is non-blocking | `native/miri_adapter/src/lib.rs:588-594`, `:736-740` |
| destroy guard window | `native/miri_adapter/src/lib.rs:463-464`, `:551-557` |
| timeout clock before lock | `native/miri_adapter/src/lib.rs:465-469` |
| analysis `max_blocks = 0` | `native/miri_adapter/src/lib.rs:707`, `:158-160` |
