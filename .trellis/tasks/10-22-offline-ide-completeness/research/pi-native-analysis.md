# Native analysis-only API + real debugger capability (Rust/OHOS Miri adapter)

Research/review only. No product code, shared core, other products, git state or
other workers' files were changed. Task was not started or created; no Flutter,
pub, or build command was run. Everything below was read from this worktree or
from the pinned sources already present on this machine (read-only).

Every claim is labelled with the artifact that proves it. Items I could not
execute are labelled **UNVERIFIED**; nothing here is reported as a passing test.
I did run three *read-only* verifications, noted inline: two SHA-256 comparisons,
and `scripts/miri_build_support.py check-source` in the existing WSL build distro
(exit 0, silent).

## 0. What this report adds beyond `pi-diagnostics-review.md`

That report covers the Dart/core analyzer contract and flags CRLF/BOM byte bases
as **UNVERIFIED** (§4.1, §4.5) because no compiler was reachable from the host.
The pinned rustc source **is** on this machine, so this report settles those two
questions with source evidence, gives the concrete native entry design that makes
them moot, and adds the debugger capability finding (an upstream debugger for
exactly this pin exists inside the pinned source tree).

---

## 1. The current native adapter and FFI path (facts)

`native/miri_adapter/src/lib.rs` (18,541 bytes, ABI 1):

| Line | Fact |
| --- | --- |
| 30 | `const ABI_VERSION: u32 = 1` — the only version ever exposed. |
| 38 | `static COMPILER_LOCK: Mutex<()>` — **process-wide**, one compiler run at a time. |
| 39 | `static COMPILER_BACKEND: Mutex<Option<BackendIdentity>>` — **first successful create fixes the backend for the process** and it is never reset (`lib.rs:376-383`). |
| 199 | `make_backend` calls `rustc_interface::util::get_codegen_backend` eagerly, wraps it in `DummyCodegenBackend` only to override `target_config` (`has_reliable_f16/f128`). |
| 226-250 | `Callbacks::config` sets `extra_symbols = miri::sym::EXTRA_SYMBOLS`, forces `always_encode_mir`, `extra_const_ub_checks`, `mir_preserve_ub`, `mir_opt_level=0`, `deduplicate_diagnostics=false`, disables 5 MIR passes, pushes `cfg(miri)`, and installs `AnnotateSnippetEmitter` (human text) on channel 2 in `psess_created`. |
| 253-267 | Cancel/time checkpoints: `after_crate_root_parsing`, `after_expansion`. |
| 269-293 | `after_analysis`: `emit_stashed_diagnostics` → `abort_if_errors` → `flush_delayed` → `miri::entry_fn` → `miri::eval_entry`. Sets `Compilation::Stop`. |
| 405-437 | `run_session`: single-shot (`started.swap(true)` at 407), takes `COMPILER_LOCK` (411), hardcoded argv (413): `--target=x86_64-unknown-linux-gnu --edition=2024 --crate-name=qfli_user_program --color=never`. Maps outcome to state/exit. |
| 351-403 | `create_session` validates absolute paths, copies stdin, resolves backend identity, rejects a conflicting backend. |

FFI surface (`qfli_miri.h`): `abi_version`, `create`, `create_with_backend`,
`run`, `cancel`, `copy_output(channel)`, `result`, `destroy`. Channels 0/1/2 =
stdout/stderr/diagnostics, raw bytes, length-then-copy, no NUL.

Dart side (`lib/native_miri_runner.dart`): `providesSymbol`-guarded optional
`create_with_backend` (so *adding* symbols is already an accepted ABI-1
extension pattern), `abiVersion() != 1` is a hard reject, `_runInWorker` re-opens
the library in `Isolate.run`, 50 ms polling of all three channels, cancel waits
for the run call to return before `destroy`.

### Consequences for an analysis entry (not opinions — direct readings)

1. **There is no analysis mode.** `after_analysis` unconditionally interprets.
   A `QfliConfig` flag would be a struct-layout change; `QfliConfig` is passed by
   value from Dart (`_NativeConfig`), so adding a field silently breaks ABI 1.
2. **Diagnostics are human text.** `AnnotateSnippetEmitter` overrides whatever
   `--error-format` says. Any span extraction requires a JSON (or otherwise
   structured) emitter — see §3.
3. **Cancel is already correct for analysis** and needs no change: it is
   cooperative at three phase checkpoints plus MIR block terminators, and
   analysis has no block terminators, so analysis cancel is *coarser* than run
   cancel (3 checkpoints for the whole analysis).
4. **Run/analysis would serialize on `COMPILER_LOCK`.** A 30 s run blocks
   analysis for 30 s. This is the real reason the analyzer must have a bounded
   short timeout and an explicit "compiler busy" unavailable reason.

---

## 2. Minimal REAL analysis-only API (design, no source written)

### 2.1 Chosen shape: additive ABI-1 extension, no layout change

Mirror the precedent already in the header (`qfli_miri_create_with_backend` is
documented as "Optional ABI-1 extension" and is looked up with
`providesSymbol`):

```
uint32_t qfli_miri_abi_version(void);            /* unchanged, still 1 */
QfliSession *qfli_miri_create_analysis(const QfliAnalysisConfig *config);
int32_t      qfli_miri_analyze(QfliSession *session);   /* blocking */
void         qfli_miri_cancel(QfliSession *session);    /* reused as-is */
size_t       qfli_miri_copy_output(const QfliSession *, uint32_t channel, uint8_t *, size_t);
int32_t      qfli_miri_result(const QfliSession *, QfliResult *result);  /* reused */
void         qfli_miri_destroy(QfliSession *session);   /* reused */
```

`QfliAnalysisConfig` is a **new** struct (never extend `QfliConfig`). Minimum
fields, each justified by an observed gap:

| Field | Why it cannot be omitted |
| --- | --- |
| `abi_version` | Same guard as `QfliConfig`; reject unknown versions. |
| `source_path` | Absolute path to the mirrored **entry** file (crate root). |
| `sysroot_path` | Absolute guest sysroot; the packaged one already works (see §5). |
| `crate_name` | `--crate-name` affects hygiene/crate-path diagnostics; do not hardcode `qfli_user_program`. |
| `edition` | **Required.** A bare `rustc file.rs` is edition 2015 → fabricated errors on 2021/2024 code. Ship it as an integer/enum, not a string. |
| `crate_type` (lib/bin) | Analyzing `src/lib.rs` as a bin emits false `E0601 main function not found`. |
| `timeout_ms` | Must be **short** (see §7.4 of the sibling report); do not reuse a 30 s run budget. |
| `max_output_bytes` | Bounded, because the JSON stream can be large; overflow must become an explicit truncation signal, never "clean". |

Deliberately **absent**: `stdin` (analysis never runs the program),
`max_basic_blocks` / `max_guest_memory_bytes` (no MIR execution), `backend_path`
(see §2.3 — reuse the process backend, do not fork identity), `out_dir`
(analysis emits nothing because it stops before codegen).

`QfliResult` is reused unchanged. State semantics: `FINISHED` = analysis
completed and the JSON stream is authoritative (with or without errors),
`CANCELLED` = 130, `LIMIT_REACHED` = 124 **and output must be treated as
truncated**, `INTERNAL_ERROR` = 1 = ICE/panic, and only that last one may be
surfaced as a hard failure. Exit code from `QfliResult` is meaningless for
analysis; callers must key off `state`, not on 0/non-0.

### 2.2 Callback implementation shape (target design)

A second `Callbacks` impl, not a flag inside the existing one. Differences from
`CompilerCallbacks` (which must stay byte-for-byte compatible for the run path):

**`config(&mut self, config)`**
- Install a JSON emitter in `psess_created` instead of `AnnotateSnippetEmitter`
  (see §3.1).
- Install the same `make_codegen_backend` closure. **Do not** skip it — see §2.3.
- **Do not** set `extra_symbols`, `cfg(miri)`, `always_encode_mir`,
  `extra_const_ub_checks`, `mir_preserve_ub`, `mir_opt_level`, `mir_enable_passes`
  or `deduplicate_diagnostics`. Every one of those is Miri *execution* semantics.
  In particular `--cfg=miri` changes which code is analysed: `#[cfg(not(miri))]`
  branches would vanish and `#[cfg(miri)]` shims would appear, so the editor
  would report diagnostics for a program the user never wrote. This is the single
  most important behavioural divergence to get right.

**`after_crate_root_parsing` / `after_expansion`** — keep the identical
`if self.io.check_stop() { Compilation::Stop } else { Compilation::Continue }`.

**`after_analysis`**
- `tcx.dcx().emit_stashed_diagnostics()`, `tcx.dcx().flush_delayed()`.
- **Do not** call `abort_if_errors()`. Errors were already streamed as JSON; the
  analysis result is data, not a fatal condition.
- **Do not** call `miri::entry_fn` / `miri::eval_entry`. Return
  `Compilation::Stop`. This is the literal "stop rustc before Miri evaluation".
- Record "analysed" so `qfli_miri_analyze` can distinguish
  `Compilation::Stop`-before-analysis (cancel) from a completed analysis.

**Argv** — `["qfli-analysis", source, "--sysroot", sysroot,
"--target=x86_64-unknown-linux-gnu", "--edition=<config.edition>",
"--crate-name=<config.crate_name>", "--crate-type=<lib|bin>", "--color=never"]`.
No `--emit`, no `--out-dir` (analysis produces no artifacts). If a future variant
needs `--emit=metadata`, `--out-dir` must point inside the caller's temp root,
because a bare rustc invocation writes `*.rmeta` into the process CWD.

**`qfli_miri_analyze`** — same body as `run_session` minus interpretation:
`started.swap(true)`, `COMPILER_LOCK`, `catch_unwind` +
`rustc_driver::catch_fatal_errors`, then the existing
`stopped != 0 → (CANCELLED|LIMIT_REACHED)` mapping. Reuse the mapping verbatim so
exit codes 130/124/1 stay identical between run and analysis.

### 2.3 Why the codegen backend is still required (evidence, not assumption)

This is worth stating explicitly because "analysis-only" invites the wrong
optimisation (dropping Cranelift on OHOS). In the pinned compiler source:

- `compiler/rustc_interface/src/util.rs:44` `add_configuration(cfg, sess,
  codegen_backend: &dyn CodegenBackend)` calls `backend.target_config(sess)` and
  inserts `target_feature`/`target_has_reliable_f16`/`f128` cfgs.
- `compiler/rustc_interface/src/interface.rs:457` calls
  `util::add_configuration(&mut cfg, &mut sess, &*codegen_backend)` — i.e. during
  **session setup, before parsing**.

Therefore an analysis run needs a `target_config` that matches the run path or
user `#[cfg(target_feature = "...")]` code would be analysed under different
configuration than it is executed under. Keep `make_codegen_backend` exactly as
it is (real backend + `DummyCodegenBackend` override). On x64 OHOS that means the
Cranelift `.so` remains a hard dependency of analysis too; on arm64 the driver's
default backend is used.

Corollary trap: the analysis path must **not** invent its own backend identity.
`COMPILER_BACKEND` is fixed by the first successful create in the process, so
mixing an analysis session and a run session with different
`backend_path`/sysroot returns `NULL` from `create` (`lib.rs:376-383`). Either
share one identity deliberately, or document that a conflicting request fails
closed (current behaviour) rather than transparently switching.

---

## 3. Structured UTF-8 spans: exactly what the pin can emit

### 3.1 Emitter

`compiler/rustc_errors/src/json.rs:41,60`:

```rust
pub struct JsonEmitter { ... }
impl JsonEmitter {
    pub fn new(dst: Box<dyn Write + Send>,
               sm: Option<Arc<SourceMap>>,
               pretty: bool,
               json_rendered: HumanReadableErrorType,
               color_config: ColorConfig) -> JsonEmitter
}
```

Install in `psess_created` exactly where `AnnotateSnippetEmitter` is installed
today (`lib.rs:243-250` already has `psess.clone_source_map()`), with
`pretty=false` (one JSON object per line), `json_rendered = HumanReadableErrorType
{ short: false, unicode: false }` (so `rendered` carries the full human rendering
usable as `CodeDiagnostic.message`), `color_config = ColorConfig::Never`.

`Destination::new(writer, anstream::ColorChoice::Never)` is already imported by
the adapter, so the writer plumbing is reusable unchanged. Reuse
`DiagnosticWriter` too, **but note its current contract**: `append` swallows the
error and returns `Ok(bytes.len())` to avoid a rustc emitter I/O panic
(`lib.rs:188-197`) while `SessionIo::stop` records `LIMIT_REACHED`. For analysis
that is the correct behaviour *provided* the Dart caller treats
`state == LIMIT_REACHED` as "diagnostics incomplete" and never as "clean".
`JsonEmitter::emit_diagnostic` panics on write error, so swallowing is genuinely
required — this is not defensive style, it is load-bearing.

### 3.2 Span payload (pinned source, `json.rs:183-233`)

`Diagnostic { message, code{code, explanation}, level, spans[], children[],
rendered }`

`DiagnosticSpan { file_name, byte_start, byte_end, line_start, line_end,
column_start, column_end, is_primary, text[], label, suggested_replacement,
suggestion_applicability, expansion }`

`DiagnosticSpanLine { text, highlight_start, highlight_end }`

### 3.3 The CRLF / BOM question — now settled from source

`json.rs:493-498` builds a span with:

```rust
file_name: sm.filename_for_diagnostics(&start.file.name).to_string(),
byte_start: start.file.original_relative_byte_pos(span.lo()).0,
byte_end:   start.file.original_relative_byte_pos(span.hi()).0,
line_start: start.line, line_end: end.line,
column_start: start.col.0 + 1, column_end: end.col.0 + 1,
```

and `compiler/rustc_span/src/lib.rs`:

```rust
pub fn original_relative_byte_pos(&self, pos: BytePos) -> RelativeBytePos {
    let pos = self.relative_position(pos);
    let diff = match self.normalized_pos.binary_search_by(|np| np.pos.cmp(&pos)) {
        Ok(i) => self.normalized_pos[i].diff,
        Err(0) => 0,
        Err(i) => self.normalized_pos[i - 1].diff,
    };
    RelativeBytePos::from_u32(pos.0 + diff)
}
```

with `normalize_src` = `remove_bom` (**+3 bytes** for a UTF-8 BOM) +
`normalize_newlines` (**+1 byte per CRLF**) recorded into `normalized_pos`.
`SourceFile::new` captures `unnormalized_source_len` *before* normalisation and
runs `normalize_src` immediately after (`rustc_span/src/lib.rs`, ~line 2177).

**Conclusion (source-backed, not inferred):** `byte_start` / `byte_end` are byte
offsets into the **original, unnormalised file bytes** — BOM and `\r` included.
They are *not* measured over LF-normalised source. `line_start` / `column_start`
and `text[]`, by contrast, are computed over the **normalised** text
(`analyze_source_file(&src)` runs after `normalize_src`), and columns are 1-based
**characters**, not bytes and not display columns (tabs = 1).

This also resolves what would otherwise be an invisible drift: if a caller maps
`byte_start` against LF-normalised bytes it is wrong by 1 per preceding CRLF, and
core's acceptance filter drops or misplaces the span **silently**.

### 3.4 Recommended mapping (robust to `snapshot.text != mirror bytes`)

The sibling report (§4.2) documents that `OpenFile`/`_code_line.dart:113`
re-joins every line with the *first* detected break, so `snapshot.text` can be
all-CRLF even for a mixed-ending or lone-`\r` file. Mapping mirror-byte offsets
straight onto `snapshot.text` therefore breaks in that case. Two-stage mapping
sidesteps both problems:

```
mirror bytes (exactly what rustc read)
  └─ stage 1: byte offset → (line_no, char_column) using the mirror's own
     `\n` line table and UTF-8 decoding. This is exact for ANY line ending,
     because byte_start is original-byte based and `\n` is unambiguous.
        └─ stage 2: (line_no, char_column) → UTF-16 offset in snapshot.text by
           splitting snapshot.text on `\r\n|\r|\n` and walking code points of
           that line, adding 2 units per non-BMP scalar.
```

Properties: independent of CRLF vs LF in the mirror; independent of BOM (stage 1
offsets include BOM bytes, which occupy line 0 before any token, so
`char_column` is unaffected); independent of `snapshot.text`'s synthetic
line-break normalisation; and it never reinterprets bytes as Dart indices. It
also gives the `line:column` needed by `location()` for free, computed from the
*snapshot*, which is what Problems prints.

Prefer this over the "normalise the mirror to LF" shortcut: that shortcut is
equally correct **only if** the mirror is the sole byte base used, but it still
fails when `snapshot.text` differs from the mirror, which is the real risk.

### 3.5 Other span traps specific to the native path

1. `file_name` is the **mirror** path (temp root), and for macro-backed spans it
   is the *defining* file, with `expansion.span` holding the call site. Map by
   relative path back to the project; for user-facing diagnostics prefer
   `expansion.span` when `is_primary` is false and the call site is in the
   project. Diagnostics pointing into the sysroot (std internals) must be dropped,
   never remapped to the active file.
2. `FileName::Macros`-style and `<anon>` / `<command line>` display names are not
   paths; drop or mark them.
3. Empty spans (`byte_start == byte_end`) are legitimate insertion points;
   preserve them.
4. The run path already emits `E0502`/`E0308` text into channel 2 for compiler
   errors (`native/fixtures/*` reference behaviour), so tests can assert that the
   **analysis** stream is JSON-only while the **run** stream stays annotated text.
   Do not switch the run path's emitter: that would change existing terminal
   behaviour and the fixtures' captured stderr.

---

## 4. Debugger capability: pause / step / variables (the real finding)

I expected to report "Miri has no debugger". That is wrong at this pin. The
pinned source tree contains an **upstream Miri debugger**, `priroda`, at
`native/build/miri-windows/miri/priroda/` (commit per
`native/build/miri-windows/miri/rust-version` = `16761606d606b6ec4d0c88fc9251670742ad9fd2`,
source fingerprint `miri_build_support.py: MIRI_SHA256`).

`priroda/README.md` documents exactly the four capabilities R7 asks about:

| Capability | Priroda command | Implementation |
| --- | --- | --- |
| **Pause / stop** | (implicit: control returns to the prompt after every step) | `PrirodaContext::resume`, `priroda/src/main.rs` |
| **Continue** | `c`, `continue` | `ResumeMode::Continue`, stops only at breakpoints |
| **Source step** | `s`, `step` | `ResumeMode::SourceLine(prev)` — stops when file/line changes |
| **MIR step** | `si`, `stepi` (and bare Enter) | `ResumeMode::MirInstruction`; hides `StorageLive/StorageDead/Nop` |
| **Breakpoints** | `b path:line`, `break` | `BreakpointTable = HashMap<PathBuf, HashSet<usize>>`, matched on resolved path+line |
| **Variables** | `l`, `locals` | names from `body.var_debug_info`, `VarDebugInfoContents::Place` → `place.as_local()`, types from `local_decls[].ty` |

### 4.1 The public API surface it proves (all reachable from a `miri`-dependent cdylib)

- `miri::create_ecx(tcx, entry_id, entry_type, &config, None)` — public
  ("Public because this is also used by `priroda`", `src/eval.rs:343`), returns a
  live `MiriInterpCx<'tcx>` **without** entering the run loop.
- `miri::entry_fn(tcx)` → `(DefId, MiriEntryFnType)`.
- `miri::report_result(&ecx, err)` → `Option<(i32, bool)>` for honest exit codes.
- `ecx.miri_step()` — via `miri::concurrency::thread::EvalContextExt`
  (`src/concurrency/thread.rs:860`, comment: "Public because this is used by
  Priroda"), re-exported in `src/lib.rs` as `EvalContextExt as _`. Reachable with
  `use miri::*;` (which is what priroda does — the traits are exported as `_`).
- `ecx.active_thread_stack()` → `&[Frame<'tcx, Provenance, FrameExtra<'tcx>>]`;
  `Frame::body()` and `Frame::current_loc() -> Either<mir::Location, Span>` are
  public accessors over fields that are `pub(super)` (`rustc_const_eval/src/interpret/stack.rs`).
  Reading `frame.body` directly is impossible; the accessors are mandatory.
- `ecx.machine.current_user_relevant_span()` (`src/helpers.rs:1001`,
  `src/concurrency/thread.rs:291`) — the span that becomes the "current line".
- `ecx.tcx.sess.source_map().lookup_char_pos(span.lo())` and
  `span_to_diagnostic_string` for path/line resolution.
- `rustc_data_structures::either::Either` re-exported as `miri::Either`.

### 4.2 Values (not just names) are obtainable

`rustc_const_eval/src/interpret/operand.rs:727`:

```rust
pub fn local_to_op(&self, local: mir::Local,
                   layout: Option<TyAndLayout<'tcx>>)
    -> InterpResult<'tcx, OpTy<'tcx, M::Provenance>>
```

documented as public **because Aquascope uses it**, plus
`local_at_frame_to_op(frame, local, layout)` for a non-current frame. So a
`variables` payload can carry real values, not only `name: Type`. Two honest
caveats:

- Priroda itself only prints `Name / Id / Ty`; there is **no** public
  "pretty-print this `OpTy`" routine. Rendering a value means walking
  `Immediate`/`Allocation` (scalars are easy; `&T`, `String`, `Vec`, enums and
  anything with provenance need per-type logic or a `format` shim call).
  Scalar-primitive values are the realistic first increment; aggregates are
  follow-up work, and `LocalState::Dead` (a local not yet `StorageLive`) must
  render as "uninitialised", not as a wrong value.
- Reading locals on demand is fine; reading them every block is what makes
  stepping expensive.

### 4.3 Blockers and traps for shipping a real debugger in this app

1. **`miri_step` is not scheduler-aware.** Priroda's own FIXME: "use a
   Miri-owned scheduler-aware debugger step API before claiming support for
   multi-threaded interpreted programs", and `PrirodaContext::advance` has "FIXME:
   … before claiming support for multi-threaded". Stepping drives the *active*
   thread only. Multi-threaded user programs will step incorrectly. Claim
   single-threaded debugging only, or gate the UI on a "no `std::thread`" check.
   This is a capability limit, not a bug we can fix locally.
2. **`eval_entry` cannot host a debugger.** `eval_entry` owns `run_threads()` and
   only returns on termination. A debug API needs a *third* create path that calls
   `create_ecx` and then exposes step/continue/resume — i.e. a "debug session"
   distinct from run and analysis. Do not try to bolt stepping onto `run_session`.
3. **`create_ecx` requires a MIR-encoded sysroot.** It validates
   `core::ascii::escape_default` has MIR available and otherwise fatals
   ("the current sysroot was built without `-Zalways-encode-mir`"). The packaged
   guest sysroot is MIR-encoded (98/97 rlib entries in the manifests), so this
   holds — but it means the debug path inherits the run path's sysroot
   requirement and cannot use a lighter sysroot.
4. **`MiriConfig` differs from the current run config.** Priroda uses
   `MiriConfig::default()`; the adapter builds `MiriConfig` with
   `args = [filestem]`, `embedded_session = Some(io)`, `short_fd_operations =
   false`. A debug session must pass the same `embedded_session` or stdout/stderr
   escape to the host process instead of the session (the patch redirects both
   `files.rs` Stdout/Stderr and `foreign_items.rs` `miri_write_to_*` only when
   `embedded_session` is `Some`).
5. **"Pause" from another thread does not exist.** `qfli_miri_cancel` is a
   one-way stop flag. A *pause* (stop at the next step, stay alive) needs a new
   cooperative gate. The cheapest real design: reuse the existing
   `before_terminator` hook point but in the debug loop check a
   `pause_requested` flag between `miri_step()` calls, since the debug loop — not
   Miri — owns the stepping. That keeps the Miri patch unchanged, which matters:
   the patch is already applied by fingerprint-checked scripts and any change to
   it changes `miri_build_support.py`'s assumptions.
6. **Breakpoint path matching on device.** Priroda stores
   `canonicalize()`d paths. On OHOS the app-storage path may be reached via
   `/data/user/0/...` vs `/data/data/...`; canonicalising one side only makes
   breakpoints silently never hit. Same class of trap as the analyzer's
   `resolveSymbolicLinksSync` gate. Normalise both sides identically and fail
   loudly on an unmatched breakpoint.
7. **Macro lines.** Priroda's FIXME: macro-backed lines (`println!`,
   `assert_eq!`) are not resolved through `span.source_callsite()` before matching
   breakpoints, so a breakpoint on a `println!` line generally will not hit.
8. **`Compilation::Stop` + `catch_fatal_errors`.** The debug loop runs inside
   `after_analysis`, i.e. inside rustc's own `catch_fatal_errors` scope; an abort
   in the debugger unwinds into it. Keep the FFI `catch_unwind` boundary that
   already exists at every export.
9. **Packaging cost.** `priroda` is a binary crate, not a library — it cannot be
   depended on. The shipping path is ~200-400 lines re-implementing the same
   command surface against the same public APIs, inside the existing adapter
   cdylib, plus a rebuild of the packaged `libqfli_miri.so` and manifest hashes.

### 4.4 Honest verdict for R7

Actual offline debugging of *interpreted* Rust programs (pause, step, breakpoints,
locals) is **feasible and has an upstream reference implementation at this exact
pin**. What is not feasible with a debugger of any kind here: native/LLDB-style
debugging of real machine code, multi-thread-aware stepping, and watchpoints.
Therefore R7's "no simulated breakpoints" requirement can be met truthfully by an
interpreter-backed debugger, with the single-threaded limitation stated in the UI.
Until it is implemented and run on a signed package, the ledger entry stays open.

---

## 5. Pinned sources and build artifacts already on this machine (read-only)

| Input | Path | State |
| --- | --- | --- |
| Windows compiler-private toolchain | `native/build/miri-windows/compiler/` (`bin` + 3,684 `lib` files, `rustc.exe`, `rustc_driver-e1f467aab84e86c3.dll`) | Present, marker `.qfli-rustc-dev-sha256` present |
| Pinned **rustc source** (compiler only) | `native/build/miri-windows/compiler/lib/rustlib/rustc-src/rust/` | Present: all `compiler/rustc_*` crates incl. `rustc_errors/src/json.rs`. **No** `src/tools/miri`, **no** `git-commit-hash` → cannot serve as `build_rustc_host.py --source` |
| Pinned **Miri source** (Windows stage) | `native/build/miri-windows/miri/` | Present, includes `priroda/`, `tests/`, `Cargo.toml` |
| Pinned Miri source (Linux stage, fingerprint-verified) | WSL distro `qfli-java-build`: `/tmp/qfli-miri-reference-1.98.1/source` | `miri_build_support.py check-source` → **exit 0, silent** (verified this session) |
| Linux executable toolchain | WSL `/tmp/qfli-miri-cross-1.98.1/rustup/toolchains/1.98.1-x86_64-unknown-linux-gnu` | Present (`bin/rustc`, `bin/cargo`) |
| x64 OHOS stage0 sysroot | WSL `/tmp/qfli-rustc-x64-ohos/build/x86_64-unknown-linux-gnu/stage0-sysroot` | Present |
| Adapter build root | WSL `/tmp/qfli-miri-adapter-1.98.1/target/` | `aarch64-unknown-linux-ohos`, `x86_64-unknown-linux-ohos`, `x86_64-unknown-linux-gnu` `libqfli_miri.so` all present |
| **Packaged arm64** adapter | `ohos/entry/libs/arm64-v8a/libqfli_miri.so` (16,002,848 B) | sha256 `d409527a…` — equals `assets/miri/manifest.json` |
| **Packaged x64** adapter | `ohos/entry/libs/x86_64/libqfli_miri.so` (16,083,560 B) | sha256 `eabe127c…` — equals `native/build/runtime/ohos-x64/manifest.json` |
| Device ABI harness | `native/build/device/ohos-arm64/{abi_test,libqfli_miri.so,librustc_driver-2224b02d479e9414.so,sysroot,fixtures}` | `abi_test` is a real ELF (magic `7f 45 4c 46`, `e_machine=0xB7` = AArch64) |

### 5.1 Provenance facts I verified by hashing

- x64 OHOS: WSL
  `/tmp/qfli-miri-adapter-1.98.1/target/x86_64-unknown-linux-ohos/debug/libqfli_miri.so`
  sha256 = `eabe127c2e0ce9d554a8f857d0190d57c190f2a8f37bf2873b564b3bfb7bc917`
  = packaged `ohos/entry/libs/x86_64/libqfli_miri.so` = the manifest's
  `nativeLibraries[libqfli_miri.so]`. **The packaged x64 library is
  byte-identical to the retained build root.**
- arm64: WSL
  `/tmp/qfli-miri-adapter-1.98.1/target/aarch64-unknown-linux-ohos/debug/libqfli_miri.so`
  sha256 = `e766c7d0…`, **≠** packaged `d409527a…`. The packaged arm64 library —
  which is the *only* architecture in `assets/miri/manifest.json`
  (`nativeHost: aarch64-unknown-linux-ohos`, `schemaVersion 1`, 97 files, 3 native
  libraries) — therefore **cannot be reproduced from the retained build root**.
  It was rebuilt later (Sep 30 mtime vs the release commit `ca6853e` "preserve
  OHOS libraries"). Do not claim arm64 reproducibility until a rebuild reproduces
  `d409527a…` or the recorded hash is deliberately updated.
- `native/build/runtime/ohos-x64/manifest.json` describes driver
  `librustc_driver-2223f3b215a042ae.so`, while the packaged arm64 set uses
  `2224b02d479e9414`. They are different builds; treat the `ohos-x64` manifest as
  a separate, non-packaged record (the sibling report reached the same conclusion
  from `native/README.md`).

---

## 6. Rebuilding the adapter: concrete commands and current blockers

### 6.1 Blockers that are real right now

1. **The pinned Windows host compiler EXISTS but is not on `PATH`.** Correction to
   an earlier claim in this file: `native/build/miri-windows/compiler/bin/rustc.exe`
   is present and reports
   `rustc 1.98.1 (48a229cea 2026-09-01)` / `host: x86_64-pc-windows-gnu`, with
   `cargo.exe`, `rustc_driver-e1f467aab84e86c3.dll` and 3,684 `lib` files beside
   it. `cargo`/`rustc` are absent from `PATH` and `~/.rustup` has no toolchains,
   so shell discovery fails, but the compiler is usable by absolute path. What is
   genuinely missing is the **crate registry cache**: `~/.cargo/registry` is
   empty and no `aes-0.9.1` source exists anywhere on this host, so
   `cargo check/build --offline` of the adapter (which must compile the `miri`
   path dependency and its ~83 packages) cannot resolve dependencies here.
   A full rebuild therefore still needs the WSL build root.
2. **No `patch` on `PATH`.** It exists at `D:\ProgramFiles\Git\usr\bin\patch.exe`
   — pass `-PatchExecutable`. The script does not search for it.
3. **WSL works, but only for the named distro.** `wsl -d qfli-java-build` works
   (proven by the `check-source` run). The default `Ubuntu` distro fails to start
   (`ERROR_FILE_NOT_FOUND` on
   `D:\WindowsExt\Subsystem\Ubuntu\Ubuntu_2204.1.7.0_x64\ext4.vhdx`). Every build
   command must pin `-d qfli-java-build`.
4. **`--locked --offline` needs the cargo registry cache** already present; it is
   (`~/.cargo/registry` exists, and the build root has prior successful builds).

### 6.2 OHOS x64 (this is the packaged-x64 provenance path)

```powershell
wsl.exe -d qfli-java-build -- bash -lc "cd /mnt/d/MyNewProjects/qfli_rust && \
  QFLI_COMPILER_SYSROOT=/tmp/qfli-rustc-x64-ohos/build/x86_64-unknown-linux-gnu/stage0-sysroot \
  sh scripts/build_miri_adapter.sh \
    /tmp/qfli-miri-reference-1.98.1/source \
    /tmp/qfli-miri-cross-1.98.1/rustup/toolchains/1.98.1-x86_64-unknown-linux-gnu \
    x86_64-unknown-linux-ohos"
```

Output: `/tmp/qfli-miri-adapter-1.98.1/target/x86_64-unknown-linux-ohos/debug/libqfli_miri.so`
plus `adapter-build-x86_64-unknown-linux-ohos.json` and
`dependencies-x86_64-unknown-linux-ohos.json` in the build root. This is exactly
the command recorded in
`.trellis/tasks/09-30-ohos-rust-interpreter/research/miri-adapter-validation.md`
and it reproduces the packaged x64 hash today (§5.1).

### 6.3 OHOS arm64

```powershell
wsl.exe -d qfli-java-build -- bash -lc "cd /mnt/d/MyNewProjects/qfli_rust && \
  sh scripts/build_miri_adapter.sh \
    /tmp/qfli-miri-reference-1.98.1/source \
    /tmp/qfli-miri-cross-1.98.1/rustup/toolchains/1.98.1-x86_64-unknown-linux-gnu \
    aarch64-unknown-linux-ohos"
```

Needs `QFLI_OHOS_SDK` (default `/mnt/d/ProgramFiles/Huawei/OpenHarmony/Sdk/23/native`)
and `QFLI_OHOS_CLANG` (default `clang-18`). Afterwards, packaging must be re-run
(`scripts/package_miri_ohos.ps1` with `-AdapterLibrary`, `-CompilerLibDirectory`,
`-GuestSysroot`, `-SdkRoot`, `-RustSource`, `-DependencyMetadata`; `-Architecture
x64 -CodegenBackend` for x64) because `assets/miri/manifest.json` pins the
adapter's SHA-256 and the file list.

### 6.4 Host (Windows) adapter — partially verified

`native/build/miri-windows/compiler/bin/rustc.exe` can type-check the adapter
in place. What was actually run for this work (see
`research/native-analysis-contract.md` §7 for the results):

```powershell
# signature-compatible stub miri, then the adapter's own logic
& compiler/bin/rustc.exe --edition 2024 --crate-type cdylib --emit metadata `
  --sysroot compiler -Cprefer-dynamic -D warnings `
  -Lnative=compiler/bin -Lnative=compiler/lib/rustlib/x86_64-pc-windows-gnu/lib `
  -Lnative=<stubout> --extern miri=<stubout>/libmiri.rmeta lib.rs
```

A real `cargo build` needs the crate registry cache (blocker 1 in §6.1). Intended
invocation once sources are available:

```powershell
powershell -File scripts/build_miri_adapter.ps1 `
  -MiriSource <complete-supplied-miri-source> `
  -Toolchain <1.98.1-x86_64-pc-windows-gnu> `
  -RustcDevArchive <matching rustc-dev tar.xz> `
  -PatchExecutable 'D:\ProgramFiles\Git\usr\bin\patch.exe' `
  -Offline
```

`-MiriSource` must be a **complete supplied** source: the staged copy under
`native/build/miri-windows/miri` is the *patched* stage, and
`prepare_miri_windows.py verify-source` re-checks it against
`SOURCE_DIGEST = 92f51c03…`; passing the already-patched stage will fail the
fingerprint, which is the intended guard. Also note
`scripts/build_miri_adapter.ps1` sets `-Clink-self-contained=yes` and expects
`compiler/lib/rustlib/x86_64-pc-windows-gnu/bin/rust-lld.exe`.

### 6.5 Cheap verification that needs no device

- `native/miri_adapter/abi_test.c` is a full in-process C ABI harness
  (12 documented checks in the validation record: modules/generics, stdin,
  nonzero exit, `E0502`, `E0308`, block bound, concurrent cancel, memory bound,
  output bound, time bound, memory reuse, fresh run after cancel). The analysis
  extension adds `native/miri_adapter/analysis_abi_test.c` on the same pattern;
  it compiles clean under `-Wall -Wextra -Werror` for both OHOS ABIs and carries
  compile-time assertions that the C `QfliAnalysisConfig`/`QfliResult` layout
  matches Rust (`sizeof 56`, offsets 0/8/16/24/32/36/40/48, measured with the
  pinned rustc). Running it requires a built adapter.
- `sh scripts/verify_miri_reference.sh` (reference Miri binary, 5 fixtures) and
  `sh scripts/check_miri_ohos.sh <miri-src> <ohos-sysroot>` (library-only) are the
  existing non-device gates.
- `native/build/device/ohos-arm64/abi_test` is a ready aarch64 ELF; it only needs
  a reachable target to run.

---

## 7. Compatibility traps (consolidated)

| # | Trap | Evidence |
| --- | --- | --- |
| T1 | Never extend `QfliConfig`; Dart builds it field-by-field and rejects `abiVersion() != 1`. New entry points must take a new struct. | `lib/native_miri_runner.dart` `_NativeConfig`, `create`, `_MiriBindings` |
| T2 | Adding symbols is safe and already an accepted pattern; removing/renaming is not. | `providesSymbol('qfli_miri_create_with_backend')` + header comment |
| T3 | The compiler backend identity is fixed by the **first** successful create in the process and never reset; a conflicting second identity returns `NULL`. | `lib.rs:38-39, 376-383` |
| T4 | One compiler run at a time process-wide; analysis must fail fast with a reason instead of queueing behind a long run. | `lib.rs:38, 411` |
| T5 | A session runs once (`started.swap`); `destroy` requires no active call; the library must stay loaded for the process lifetime (rustc global state). | `lib.rs:407`, README "Session contract" |
| T6 | Analysis must not set `cfg(miri)` / MIR-preserving flags, or the editor analyses a different program than the user wrote. | `lib.rs:236-245` |
| T7 | Analysis **must** keep a codegen backend because `target_config` is read during session setup. | `rustc_interface/src/util.rs:44`, `interface.rs:457` |
| T8 | Do not call `abort_if_errors()` in analysis; errors are data. But `catch_fatal_errors` still returns `Err` for `dcx().fatal()` paths, so `Err` is **not** automatically an ICE — distinguish by "did an `error`-level diagnostic arrive". | `lib.rs:270-272` |
| T9 | `DiagnosticWriter` deliberately swallows write errors; `LIMIT_REACHED` therefore means "diagnostics truncated", never "clean". | `lib.rs:188-197`, `SessionIo::stop` |
| T10 | `byte_start/byte_end` are original-byte offsets (BOM+CRLF included); columns are 1-based characters over normalised text; `text[]` is normalised. Never mix bases. | `json.rs:493-498`, `rustc_span/src/lib.rs` `original_relative_byte_pos`, `normalize_src` |
| T11 | `snapshot.text` may be re-joined with a single line break, so it can differ from disk bytes; map through `(line, char column)`. | `_code_line.dart:113`, sibling report §4.2 |
| T12 | Macro spans: `file_name` is the defining file; the call site is `expansion.span`. Sysroot spans must be dropped. | `json.rs:183-233` |
| T13 | The run path's annotated-text emitter and the fixtures' captured stderr must not change while adding the JSON path. | `native/fixtures/*.stderr`, `verify_miri_reference.sh` |
| T14 | `create_ecx` requires a MIR-encoded sysroot and fatals otherwise (debug path inherits this, analysis does not). | `src/eval.rs:343`+ |
| T15 | `EmbeddedSession` redirection covers `files.rs` Stdout/Stderr and `miri_write_to_*` only when `Some`; a debug session must pass it or output escapes to the host process. | `native/patches/miri-1.98.1-embedded-session.patch` |
| T16 | Any change to the Miri patch invalidates `MIRI_SHA256` in `miri_build_support.py` and the `--fuzz=0` replay; prefer designs that leave the patch untouched (the debug loop can live entirely in the adapter). | `scripts/miri_build_support.py:14`, `build_miri_adapter.sh` |
| T17 | Rebuilding `libqfli_miri.so` changes its SHA-256, which is pinned in `assets/miri/manifest.json` and `native/build/runtime/ohos-x64/manifest.json`; packaging must be re-run or the HAP ships a library the manifest does not describe. | both manifests |
| T18 | arm64 packaged hash is not reproducible from the retained build root (§5.1). | hashes above |
| T19 | Breakpoint/analysis paths on device can be reached via `/data/user/0` vs `/data/data`; canonicalise consistently on both sides. | Priroda `normalize_path`; sibling report §5.4 |
| T20 | Stepping is single-thread-only. | `priroda/src/main.rs` FIXMEs |

---

## 8. Recommended sequencing (adapter scope only)

1. **Now, no rebuild needed:** land the Dart-side analyzer on desktop rustc first
   (sibling report's step 1). It needs no ABI change whatsoever.
2. **Analysis ABI:** add `qfli_miri_create_analysis`/`qfli_miri_analyze` + JSON
   emitter + `after_analysis` early return, leaving `CompilerCallbacks` untouched.
   Extend `abi_test.c` with (a) valid file → clean JSON stream, (b) `E0308` →
   one diagnostic with a primary span, (c) `--crate-type=lib` + no `main` → clean,
   (d) `cfg(miri)`-differing source → same result as plain rustc, (e) cancel →
   state 3 / 130, (f) tiny `max_output_bytes` → state 4 / 124 and truncation
   visible.
3. **Rebuild + package x64** (§6.2, §6.4 packaging) and confirm the hash chain
   `build root → ohos/entry/libs/x86_64 → manifest`.
4. **Rebuild arm64** and reconcile the `d409527a…` discrepancy (§5.1) — either
   reproduce it or update the manifest with an explicit note.
5. **Only after a signed package exists:** run the analysis ABI on device and
   compare offsets against desktop rustc for the same fixtures (sibling report's
   C1-C7 + C20). Until then, mobile must report the explicit unavailable state.
6. **Debugger:** separate follow-up. Ship a stepping session (`create_ecx` +
   `miri_step` loop) with breakpoints, source step, and locals. Values for scalar
   primitives only at first, with "uninitialised"/"unsupported" for the rest, and a
   documented single-thread limitation. Do not present it as a native debugger.

## 9. Open items I could not settle

- Whether an analysis-only run leaves the rustc incremental/query cache in a state
  that affects a later run session in the same process — **UNVERIFIED** (needs a
  built adapter).
- Whether the x64 OHOS Cranelift backend's `target_config` is stable across the
  analysis/run split once `mir_opt_level` differs — **UNVERIFIED**.
- Real offset parity between the adapter's JSON `byte_start` and Dart's
  `snapshot.text` for a mixed-ending file — **UNVERIFIED** (fixture needed).
- Whether the packaged arm64 build (`d409527a…`) was produced by a newer source or
  a newer adapter commit — **UNVERIFIED**; no build record for it exists in
  `native/build/` (`adapter-build-*.json` files are absent from the worktree).
- `hdc list targets` state was taken from the task audit, not re-run here; device
  acceptance remains open regardless.
