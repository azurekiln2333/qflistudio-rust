# Native analysis-only ABI contract (ABI-1 additive extension)

Status: implemented in `native/miri_adapter/src/lib.rs` + `native/miri_adapter/qfli_miri.h`.
This file is the authoritative interface for Pi4/root wiring. It is an **additive
ABI-1 extension**: no existing symbol, struct layout, state value, exit code or
emitter changes.

Pinned toolchain: Rust 1.98.1, commit `48a229ceaefd4985c50990b14116b6d856af0985`.
Miri source fingerprint `92f51c0345496c6ef1edbba009985c84b612630dd5c7e81ea2cdd826d0d85764`.
The upstream Miri patch is **unchanged** by this work.

---

## 1. Header

```c
/* ---- analysis-only extension (ABI 1) ---------------------------------- */

enum QfliAnalysisCrateType {
    QFLI_ANALYSIS_CRATE_BIN = 0,   /* crate root must define `main`        */
    QFLI_ANALYSIS_CRATE_LIB = 1    /* no `main` required; analysed as lib  */
};

/* Legacy reserved source constant, never returned/written by this adapter.
 * The actual busy return code is 2; session state remains unchanged. */
enum QfliAnalysisState { QFLI_BUSY = 6 };

typedef struct {
    uint32_t abi_version;        /* must be 1                                */
    const char *source_path;     /* absolute UTF-8 crate root, copied        */
    const char *sysroot_path;    /* absolute UTF-8 guest sysroot, copied     */
    const char *crate_name;      /* 1..=64 bytes of [A-Za-z0-9_]             */
    uint32_t edition;            /* 2015, 2018, 2021 or 2024                 */
    uint32_t crate_type;         /* enum QfliAnalysisCrateType               */
    uint64_t timeout_ms;         /* > 0; includes waiting for the compiler   */
    size_t max_output_bytes;     /* 1024 ..= 16 MiB, diagnostics channel     */
} QfliAnalysisConfig;

/* NULL backend_path uses the same default resolution as `qfli_miri_create`.
 * Non-NULL is an absolute UTF-8 backend library path, copied by create.
 * Returns NULL on any invalid input, missing file, or backend identity
 * conflict (see §5). */
QfliSession *qfli_miri_create_analysis(const QfliAnalysisConfig *config,
                                       const char *backend_path);

/* Blocking: call on a worker. Return codes:
 *   0  accepted; the session reached a terminal state (see §3)
 *   2  compiler busy: another run/analysis holds the compiler; the session
 *      was NOT consumed and may be retried or destroyed
 *  -1  null session, already-used session, or rejected execution
 * Concurrent-safe with cancel/copy_output/result, like `qfli_miri_run`. */
int32_t qfli_miri_analyze(QfliSession *session);
```

Reused unchanged: `qfli_miri_abi_version`, `qfli_miri_cancel`,
`qfli_miri_copy_output`, `qfli_miri_result`, `qfli_miri_destroy`,
`QfliResult`, `QfliState`, `QfliOutput`.

Discovery rule for FFI bindings: look the new symbols up **optionally**
(`providesSymbol`), exactly as `qfli_miri_create_with_backend` already is.
Their absence means "this build has no analysis backend".

---

## 2. Behaviour

`qfli_miri_create_analysis` performs the same validation and copies as
`qfli_miri_create` (absolute existing source file, absolute existing sysroot
directory, bounded output, positive timeout) plus:

- `crate_name` non-NULL, 1..=64 bytes, ASCII `[A-Za-z0-9_]`.
- `edition` ∈ {2015, 2018, 2021, 2024}.
- `crate_type` ∈ {0, 1}.

It then resolves the codegen backend with the **same** rules as the run path and
claims the process-wide backend identity.

`qfli_miri_analyze` runs the pinned rustc over the crate root with:

```
--sysroot <sysroot> --target=x86_64-unknown-linux-gnu
--edition=<edition> --crate-name=<crate_name> --crate-type=<bin|lib> --color=never
```

and **stops at the end of analysis**. It never:

- calls `miri::entry_fn` / `miri::eval_entry` (no interpretation),
- sets `cfg(miri)` or any Miri MIR/UB flag,
- invokes Cargo, `build.rs`, a proc-macro executable or any user code,
- writes files (`--emit` is not passed; nothing is emitted).

Diagnostics are emitted as **JSON Lines** on channel 2 (`QFLI_DIAGNOSTICS`),
one `serde_json` object per line, each tagged `"$message_type":"diagnostic"`.
Channel 0 (stdout) and 1 (stderr) stay empty for analysis.

A JSON emitter is required because the run path's `AnnotateSnippetEmitter`
produces human text, which cannot yield exact spans. The run path keeps its
emitter unchanged.

---

## 3. Result contract

| `QfliResult.state` | `exit_code` | Meaning |
| --- | --- | --- |
| `QFLI_FINISHED` (2) | `0` | Analysis completed. Channel 2 is authoritative: it may contain `error`/`warning` diagnostics, or be empty (checked clean). |
| `QFLI_CANCELLED` (3) | `130` | `qfli_miri_cancel` observed at a phase checkpoint. Channel 2 is partial. |
| `QFLI_LIMIT_REACHED` (4) | `124` | Output bound or timeout. Channel 2 is **truncated**, never "clean". |
| `QFLI_INTERNAL_ERROR` (5) | `1` | Panic/ICE outside rustc's fatal-diagnostic path. |
| `QFLI_READY` (0) | `-1` | Not analysed yet. |

**`exit_code` is not a compile verdict.** A source with errors still yields
`state == 2` and `exit_code == 0`; callers must read the diagnostics. This is
deliberate: the analysis result is data, not a process status.

Because rustc never calls `abort_if_errors` on this path, an `Err` from
`catch_fatal_errors` no longer implies an ICE. The adapter resolves it as
follows: if any bytes were already written to channel 2, rustc reported
structured diagnostics and the result is `FINISHED`/`0`; only a silent abort is
reported as `INTERNAL_ERROR`. The timeout is additionally re-checked at the
start of `after_analysis`, so an over-budget analysis reports
`LIMIT_REACHED`/`124` instead of claiming completion.

`qfli_miri_analyze` return codes are distinct from the state: `0` accepted,
`2` busy, `-1` invalid. A `-1` return also leaves state `READY` unless the
session was already used.

---

## 4. Span payload (source-verified for this pin)

`compiler/rustc_errors/src/json.rs` (pinned source) serialises:

```
{"$message_type":"diagnostic",
 "message":String,
 "code":{"code":String,"explanation":null}|null,
 "level":"error"|"warning"|"note"|"help"|"failure-note"|"error: internal compiler error",
 "spans":[{"file_name":String,
           "byte_start":u32,"byte_end":u32,
           "line_start":usize,"line_end":usize,
           "column_start":usize,"column_end":usize,
           "is_primary":bool,
           "text":[{"text":String,"highlight_start":usize,"highlight_end":usize}],
           "label":String|null,
           "suggested_replacement":String|null,
           "suggestion_applicability":String|null,
           "expansion":{...}|null}],
 "children":[...],
 "rendered":String}
```

Mapping rules that are **facts of this pin**, not preferences:

1. `byte_start`/`byte_end` are offsets into the **original file bytes** —
   BOM and `\r` included. `json.rs` uses
   `SourceFile::original_relative_byte_pos`, which re-adds the
   `normalized_pos` diffs recorded by `remove_bom` (+3) and
   `normalize_newlines` (+1 per CRLF). They are *not* LF-normalised offsets.
2. `line_start`/`column_start` and `text[].text` are computed over the
   **normalised** text. Columns are 1-based **characters** (a tab counts 1),
   not bytes and not display columns.
3. `file_name` is `SourceFile::name.display(RemapPathScopeComponents::DIAGNOSTICS)`,
   i.e. the path as given on the command line. The adapter passes absolute
   paths and never changes CWD, so project spans carry absolute paths; macro
   spans carry the **defining** file with the call site in `expansion.span`.
   `FileName` variants other than `Real` render as `<anon>`,
   `<macro expansion>`, `<proc-macro source code>`, `<crate attribute>`,
   `<cfgspec>` — these are not paths.
4. **`code.explanation` is always populated and is large.** In the pinned
   `json.rs` it is
   `explanation: crate::codes::try_find_description(code).ok()` — computed
   unconditionally, *not* gated by `json_rendered.short`, and `JsonEmitter`
   exposes no setter to disable it. A single `E0308` therefore carries ~700
   bytes of long description. Consequences: consumers must ignore
   `code.explanation`, and the output bound must be budgeted for ~1 KB of
   explanation per coded diagnostic. `short: true` is still used because it
   keeps the separate `rendered` field compact and suppresses the appended
   error-code explanation inside it.

Recommended consumer mapping (robust when the editor snapshot's line endings
differ from disk): `byte offset → (line_no, char_column)` using the emitted
line table, then `(line_no, char_column) → UTF-16 offset` inside the exact
snapshot text, splitting on `\r\n|\r|\n` and counting 2 UTF-16 units per
non-BMP scalar.

---

## 5. Compiler sharing, busy, cancel, destroy

- `QfliConfig` and `QfliResult` layouts are unchanged. Only new symbols and one
  new optional entry points are added. The legacy reserved constant 6 is never
  a session state or actual busy return value.
- Compilation is serialised by one process-wide mutex. `qfli_miri_analyze`
  **does not block** on it: it returns `2` immediately, leaving session state
  untouched (normally READY). This keeps
  an analysis request from queueing behind a 30 s program run.
- A busy attempt does **not** consume the session; `qfli_miri_analyze` may be
  called again. A successful or cancelled attempt does consume it (one
  compilation per session, same as run).
- Backend identity is process-global and fixed by the first successful create.
  An analysis session requesting a different backend/sysroot identity returns
  `NULL`, exactly like the run path. Create analysis sessions with the same
  backend the run path uses.
- `qfli_miri_cancel` is concurrent-safe and is the only way to stop an analysis.
  Cancellation is cooperative at `after_crate_root_parsing`, `after_expansion`
  and `after_analysis`; it cannot preempt an in-flight compiler query.
- **Do not call `qfli_miri_destroy` while `qfli_miri_analyze` (or
  `qfli_miri_run`) is active.** Call `cancel`, wait for the analyze call to
  return, then destroy. `destroy` now refuses to free a session with an active
  call (it leaks instead of dereferencing freed memory), but that is a safety
  net, not a licence to race.

---

## 6. Verification status

### 6.1 Verified on this host (no adapter build needed)

1. **Rust type-checks clean.** The adapter compiles with `--emit metadata` and
   `-D warnings` against the pinned
   `native/build/miri-windows/compiler/bin/rustc.exe`. Caveat: `miri` was a
   signature-compatible stub, because `~/.cargo/registry` is empty and the real
   `miri` crate cannot be built offline. The stub mirrors the pinned
   `eval.rs`/`lib.rs` signatures (`EmbeddedSession`, `MiriEntryFnType`,
   `MiriConfig`, `sym::EXTRA_SYMBOLS`, `entry_fn`, `eval_entry`); those
   signatures were read from the pinned source.
2. **C test compiles clean** for both OHOS ABIs:
   `clang --target={x86_64,aarch64}-linux-ohos -std=c11 -Wall -Wextra -Werror`,
   with compile-time ABI assertions that `QfliAnalysisConfig` is 56 bytes at
   offsets 0/8/16/24/32/36/40/48 and `QfliResult` stays 24 bytes. Those offsets
   were measured from the Rust side with the pinned rustc
   (`offset_of!`), so header and `#[repr(C)]` are proven to agree.
3. **The header is valid C11 and C++17** (`extern "C"` clean, no reserved
   identifiers, no `-Wpedantic` complaints).
4. **Fixture expectations are real, not guessed.** Every `native/fixtures/analysis_*.rs`
   was compiled with the pinned rustc (`--emit metadata --error-format=json`)
   and the resulting JSON recorded:

   | fixture | crate type | result | recorded span |
   | --- | --- | --- | --- |
   | `analysis_syntax.rs` | bin | error | syntax diagnostics |
   | `analysis_type.rs` | bin | `E0308` | bytes 33..47 = `"not a number"`, line 2, cols 22..36 |
   | `analysis_valid.rs` | bin | clean | — |
   | `analysis_library.rs` | lib | clean | — |
   | `analysis_unicode.rs` | bin | `E0308` | bytes 99..104 = `label`, line 4, cols 22..27 |
   | `analysis_nonexecution.rs` | bin | clean | — |
   | `analysis_cfg_miri.rs` | bin | clean | — |

   The Unicode case is the byte-base proof: the primary span sits after
   `// 中文注释：变量声明 😀`, so byte offsets differ from character offsets, and
   bytes 99..104 decode to exactly `label`. The test decodes the file at the
   reported byte range and compares the text, so a byte/char base regression
   fails rather than silently shifting the squiggle.
   `analysis_cfg_miri.rs` carries `#[cfg(miri)] compile_error!`, so it is clean
   **only** if analysis does not enable `cfg(miri)`; the recorded clean result
   from plain `rustc` confirms the fixture is the right probe.

### 6.2 Not yet verified — requires a built adapter (root-owned)

`native/miri_adapter/analysis_abi_test.c` is written and compiles, but has not
run against a real adapter. It asserts: syntax error, `E0308` with decoded span
text, clean source, `lib` crate without `main`, and the same file as a `bin`
producing `E0601` (proves the crate type is really applied), Unicode span
bytes, **no execution** (`analysis_nonexecution.rs` would print `EXECUTED` and
`exit(7)`), `cfg(miri)` independence, pre-cancel → state 3/130, output-bound
truncation → state 4/124, single-use rejection, invalid-config rejection, and
compiler-busy (`analyze` returns 2 / state 6 immediately while a `cancel.rs`
run holds the compiler) followed by a successful retry on the same session.

It exits `3` and prints `SKIP` when the analysis symbols are absent, so an
older adapter build cannot masquerade as a pass.

Until that test has run against a packaged adapter, **mobile analysis must be
reported as unavailable**, not as working.

### 6.3 Integration work still owned elsewhere

- Dart bindings (`lib/native_miri_runner.dart`) do not yet declare
  `qfli_miri_create_analysis` / `qfli_miri_analyze`. They are optional symbols
  resolved via `providesSymbol`, so adding them cannot break an older adapter.
- `scripts/build_miri_adapter.sh` / `check_native_packaging.py` do not build or
  hash the analysis test. Neither needed a change: the extension adds symbols
  to the same shared library, so existing packaging and manifest pins keep
  working once the library is rebuilt.
- Rebuilding `libqfli_miri.so` changes its sha256, so the packaged manifest pins
  (`assets/miri/manifest.json`, `native/build/runtime/ohos-x64/manifest.json`)
  must be regenerated by root as usual.
