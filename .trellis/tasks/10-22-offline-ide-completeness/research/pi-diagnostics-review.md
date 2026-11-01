# Rust nonexecuting diagnostics: contract review and pitfall inventory

Research/review only. No product code, shared core, other products, git state or
other workers' files were changed. Everything below is read from the current
worktree; items I could not execute are labelled **UNVERIFIED** instead of being
reported as passing.

## 1. Evidence I actually read

| Path | What it establishes |
| --- | --- |
| `qfli_studio_core/lib/services/code_analysis.dart` | Frozen provider contract (`CodeAnalyzer`, `CodeDocumentSnapshot`, `CodeAnalysisRequest`, `CodeDiagnostic`, `CodeAnalysisResult`, `CodeDiagnosticSeverity`). |
| `qfli_studio_core/lib/editor/editor_analysis_controller.dart` | Scheduler, generation/staleness rules, watchdog, acceptance filters, `location()`. |
| `qfli_studio_core/lib/editor/editor_diagnostics.dart` | Wavy-span rendering, line-start table, surrogate-edge guard, `navigate()`. |
| `qfli_studio_core/lib/editor/open_file.dart` | How a buffer's text and **line-break mode** are produced. |
| `qfli_studio_core/vendor/re_editor/lib/src/_code_line.dart:113` | `String get text => codeLines.asString(lineBreak);` |
| `qfli_studio_core/lib/editor/editor_page.dart:202-205` | `EditorAnalysisController(analyzer: StudioProfile.current?.codeAnalyzer)` — provider slot is live. |
| `qfli_studio_core/lib/services/studio_profile.dart:9,11,99,135` | `codeAnalyzer` field + re-export of `code_analysis.dart`. |
| `qfli_studio_core/.trellis/tasks/10-22-offline-editor-analysis/design.md` | Provider-side obligations ("convert compiler UTF-8 bytes/line columns to UTF-16, never reinterpret bytes as Dart offsets"). |
| `qfli_rust/lib/main.dart:22-45` | `rustProfile` has **no** `codeAnalyzer`. |
| `qfli_rust/lib/rust_runner.dart` | Desktop rustc/cargo invocation; stderr is plain text; no JSON parsing anywhere. |
| `qfli_rust/lib/native_miri_runner.dart` | FFI bindings, `abiVersion() != 1` hard reject, one session per run, 50 ms output polling. |
| `qfli_rust/native/miri_adapter/src/lib.rs:225-292,401-430` | `CompilerCallbacks`, `AnnotateSnippetEmitter` on channel 2, hardcoded rustc args, Miri runs inside `after_analysis`. |
| `qfli_rust/native/miri_adapter/qfli_miri.h` | ABI 1: `QfliConfig` has no edition/target/crate-type/analysis/emit options. |
| `qfli_rust/assets/miri/manifest.json` | Packaged OHOS runtime: `schemaVersion 1`, `nativeHost aarch64-unknown-linux-ohos`, guest `x86_64-unknown-linux-gnu`, `libqfli_miri.so d409527a…`, driver `librustc_driver-2224b02d479e9414.so`, `libc++_shared.so`, 97 files. |
| `qfli_rust/native/build/runtime/ohos-x64/manifest.json` | Stale x86_64-ohos host manifest (driver `2223f3b2…`) — **not** the packaged one. |
| `qfli_rust/native/README.md` (modified, uncommitted) | "Current HAP packaging includes only `arm64-v8a` native libraries." |
| `qfli_rust/lib/rust_project_store.dart:113-122` | App-created Cargo projects declare `edition = "2021"` and a single `[[bin]]`. |
| `qfli_rust/scripts/verify_rust_content.py:59` | Host verification compiles content with `--edition=2021`. |
| `qfli_rust/assets/content_rust/examples.json` | 166 entries, **all single-file**, no `files` map, no external deps. |
| `.trellis/spec/backend/native-runtime.md` | ABI 1, manifest schema 1, "Run once, off the file UI isolate", "Cancellation does not preempt an active rustc query". |
| `.trellis/tasks/10-22-offline-ide-completeness/{prd,design,implement}.md` | R5 scope: nonexecuting, unsaved, UTF-16, CRLF, module overlays, truthful unavailable. |

## 2. Current state (no R5 claim)

- There is **no** `CodeAnalyzer` implementation, no `rustc --error-format=json`
  parsing and no diagnostic offset mapping anywhere in `lib/`. A grep for
  `CodeAnalyzer|code_analysis|CodeAnalysisRequest|CodeDiagnostic` over
  `qfli_rust/lib/**/*.dart` returns nothing. The new analyzer files said to be
  owned by another worker are **not present** in this worktree at review time
  (`git status` shows only pre-existing `native/README.md`, `ohos/AppScope/app.json5`,
  `ohos/entry/build-profile.json5` edits plus untracked tooling dirs).
- The core provider slot is committed (`ef34591`) and live in `editor_page.dart`;
  supplying `codeAnalyzer:` in `rustProfile` is the whole integration seam.
- R5 therefore stays open: no provider, and OHOS has no analysis entry point at all.

## 3. Contract facts that bind the implementation

From `code_analysis.dart` and `editor_analysis_controller.dart`:

1. `CodeDiagnostic.startOffset/endOffset` are **zero-based, half-open, UTF-16 code
   units in the snapshot text**, insertion points allowed (`start == end`).
2. Accepted diagnostics must be: absolute path, `p.isWithin(projectPath, path)`,
   non-empty message, `0 <= start <= end`, and for captured snapshots
   `endOffset <= snapshot.text.length`. Anything else is silently dropped — so a
   broken mapping is *invisible*, not an error message.
3. `_owned()` additionally requires `File(file).resolveSymbolicLinksSync()` to stay
   inside `Directory(root).resolveSymbolicLinksSync()`.
4. `_current()` discards the whole response if any captured document's
   `revision`, `text` or root differs. A response that arrives on time is still
   accepted if the text is unchanged (including after the watchdog already
   showed a timeout message — see §7).
5. Bounds: 64 documents, 4 Mi UTF-16 units total, 1000 diagnostics, 300 ms
   debounce, 12 s watchdog, providers that hit bounds produce an
   `unavailableReason` and **no** request.
6. `location()` renders `file:line:col` by scanning `\r\n|\r|\n` over the snapshot
   prefix, so CRLF-aware offsets are what the Problems list prints.
7. Empty `diagnostics` **plus** `unavailableReason == null` means "checked clean".
   `unavailableReason != null` means "not checked" — the only truthful way to
   report an unavailable backend.

## 4. UTF-8 byte offset → UTF-16 offset (the core mapping problem)

rustc's JSON gives `spans[].byte_start/byte_end`, `line_start/line_end`,
`column_start/column_end`, plus `is_primary`, `file_name`, `suggested_replacement`,
`expansion`, `label`. The only safe pipeline is:

```
mirror bytes (what rustc read)  --line table-->  byte offset
   --UTF-8 decode-->  char index          (NFC-free, no re-encode)
   --UTF-16 encode-->  code units          -> CodeDiagnostic offsets
```

Concrete traps, in the order they will bite:

**4.1 CRLF changes the byte base.** If rustc normalizes source newlines before it
computes spans (the usual claim), then `byte_start` is measured over
LF-normalized source and a CRLF file loses 1 byte per preceding line ending;
reconstructing offsets from raw file bytes would then drift by exactly one byte
per line, invisibly, because core silently clamps out-of-range spans. Either way
the mitigation is the same: **write the mirror with one deliberate line ending**
and build the byte→char table from the bytes you wrote, never from disk.
Recommended: normalize the mirror to LF and derive the snapshot line table from
`\r\n|\r|\n` (line counts are identical), which makes the CRLF question moot.
**UNVERIFIED** (needs rustc): whether `byte_start` is over LF-normalized or raw
bytes; settle it with C1/C2 before freezing the algorithm.

**4.2 The editor snapshot may not equal disk text at all.** `OpenFile` derives
`TextLineBreak` from the *first* match (`content.contains('\r\n') ? crlf : ...`)
and `controller.text` re-joins **every** line with that single break
(`_code_line.dart:113`, `code_line.dart:488`). Consequences:
- a file with mixed CRLF/LF endings is presented to the analyzer as all-CRLF;
- a file with lone `\r` is presented as all-CR;
- therefore `snapshot.text` can be longer/shorter than the bytes on disk.
The analyzer must encode **`snapshot.text`**, and its offsets must be into
`snapshot.text` — never into `File(path).readAsBytes()`. For unopened files
(no snapshot) offsets must be validated against the disk text you mirrored, and
core will show "打开后重新检查" and refuse to decorate.

**4.3 Non-BMP characters (emoji, rare CJK, math letters).** One UTF-8 sequence,
one Unicode scalar, **two** UTF-16 code units. Any implementation that maps bytes
→ "chars" → offsets as if chars == UTF-16 units under-shoots every span after an
emoji, and after one surrogate pair the wavy underline lands on the wrong token.
`editor_diagnostics.dart` guards surrogate edges (`_lowSurrogate`) but that only
prevents a split rendering, not a wrong position. Content is Chinese-language, so
CJK (3-byte UTF-8, 1 UTF-16 unit) is the common case and will pass even when the
BMP mapping is broken — the regression suite must contain a 4-byte case
explicitly. Also note `'😀'.length == 2` in Dart, so a naive
`text.substring(0, offset)` in tests hides the bug too.

**4.4 Columns are not bytes and not display columns.** `column_start` is 1-based
and counted in characters for a tab = 1; `col_display` (used for carets) expands
tabs. Never use the rendered caret column. Prefer `byte_start` + your own byte
line table over `column_start`, and if you do use columns, convert char→UTF-16 by
iterating the code points of that line.

**4.5 BOM.** If a snapshot begins with `U+FEFF`, encoding it UTF-8 writes `EF BB BF`;
rustc may strip a BOM before span computation (it is treated as whitespace for the
lexer at file start). Either strip the BOM when writing the mirror **and** subtract
1 UTF-16 unit (or keep the BOM in the snapshot and offset by 1), or forbid BOM in
the mirror and clamp offsets to the snapshot. **UNVERIFIED**; needs a BOM case (§9, C5).

**4.6 Empty and zero-width spans.** rustc emits `byte_start == byte_end` for
"expected X" at a token boundary; core turns an empty range into a 1-unit
underline at `end-1` when it falls at end-of-line. Preserve empties rather than
widening them to the whole line — a widened span produces a whole-line wavy
underline and hides the real token.

**4.7 Spans that do not belong to the project.** `#[derive]` failures point at the
attribute; privacy/type errors in std point into the sysroot; macro expansions
have `file_name` of the defining file. Only emit diagnostics whose `file_name`
maps to a project file; drop the rest (do not map std paths to the active file).

## 5. Module overlays and the temporary mirror

Design requires "mirror required project source in a temporary root and overlay
all open buffers". Requirements and traps:

1. **Never write inside `projectPath`.** Also pass `--out-dir <temp>` — a bare
   `rustc --emit=metadata x.rs` drops `x.rmeta` into the process CWD, which is the
   project directory for the runner and would violate "never overwrite project
   files" and trip git-ignore/noise checks.
2. **Copy only Rust sources** (`**/*.rs`) plus `Cargo.toml` if needed; skip
   `target/`, `.git/`, `build/`, `.dart_tool/`. A copy of a `target/` directory is
   hundreds of MB and blows the 4 MiB/64-file analysis budget before the
   analyzer ever starts.
3. **Map `file_name` back by relative path**, and emit the *original* path string
   (same casing/separators as the request or the disk path). Verified semantics of
   the core filters: `p.equals`/`p.isWithin` (`path-1.9.1`) are **case-insensitive
   and slash/backslash-equivalent on Windows** (`windows.dart codeUnitsEqual`), so
   casing alone will not drop a diagnostic there — but they are **case-sensitive on
   POSIX**, i.e. on Android and OHOS. The real drop risks are: a non-absolute
   `filePath` (rejected before any comparison), a Windows extended-length `\\?\`
   prefix or a `subst`/junction drive that `p.relative` cannot bridge
   (`_PathRelation.different`), and the symlink gate in item 4.
4. **Device path shapes differ**: OHOS/Android app storage can be reached through
   `/data/user/0/...` vs `/data/data/...` (symlinked). If the project root passed
   in `CodeAnalysisRequest.projectPath` is the symlinked form while the mirrored
   copy resolves elsewhere, `_owned()` fails and *every* diagnostic is dropped
   with no message. Test on device with the real path the editor opened.
5. `mod foo;` resolution happens relative to the file rustc reads, so the mirror
   must preserve the whole subtree (`src/main.rs` + `src/foo.rs`, `src/foo/mod.rs`,
   `#[path = "..."]`, `include!("../shared/x.rs")`). Missing a file produces
   E0583 and a fabricated squiggle.
6. **Overlay only what core gave you.** `request.documents` contains the active
   file plus other *editable, same-root* open buffers. A buffer open from another
   root is never captured; do not synthesize it.
7. **Cleanup must be unconditional** — success, error, cancel, and callers that
   abandon the future. Core abandons the result on a new keystroke but does not
   cancel the future, so cleanup must live inside the analyzer's own `finally`.
   A leaked temp dir per keystroke will fill app storage.
8. **Two concurrent analyses must not share a temp root** — core keeps a single
   lane per editor but the analyzer object is per profile, and a cancelled-but-
   still-running native analysis can overlap the next one.

## 6. Library vs binary crate roots

`CodeAnalysisRequest` gives `projectPath`, `activeFilePath` and `language`, but no
target information. The analyzer must derive it:

- Analyze `src/lib.rs` (or a `[lib] path`) as `--crate-type=lib`; analyzing it as
  a binary emits **E0601 "main function not found"** — a fabricated error on valid
  code.
- Analyze `src/main.rs`, `src/bin/*.rs`, `examples/*.rs`, `tests/*.rs` as `--crate-type=bin`
  (and `--test` only if you intend to type-check `#[cfg(test)]` items, which are
  otherwise skipped — a "clean" result that never looked at unit tests is not a lie
  the UI can show, so document it).
- Respect a `[[bin]] path = "..."` override: `rust_project_store.dart:116-118`
  writes the entry file into `[[bin]] path` and also writes plain `.rs` files
  that are **not** registered targets. Analyzing an unregistered `.rs` as a
  standalone crate is acceptable (matches the runner's standalone fallback) but
  must not be presented as "part of the binary".
- `--crate-name` must match the target name or `#![crate_name]`/`crate::` hygiene
  diagnostics can disagree with `cargo build`; the native adapter currently forces
  `qfli_user_program`.

## 7. Timeout, proc macros, build scripts, and the native path

**7.1 No analysis entry exists in the pinned adapter.** `qfli_miri_run` always
runs `run_compiler` and then, inside `after_analysis`, calls `miri::entry_fn` +
`miri::eval_entry`. There is no way to stop before evaluation, and `QfliConfig`
carries no analysis flag, no edition, no target, no crate type, no `--error-format`.
So: **OHOS/mobile nonexecuting analysis is impossible without an ABI change**
(header, `lib.rs` callbacks that return `Compilation::Stop` after
`tcx.dcx().abort_if_errors()` instead of interpreting, `abi_test.c`, Dart
bindings, and rebuilt `libqfli_miri.so` + driver for aarch64-ohos).

**7.2 The native diagnostics channel is human-rendered text, not JSON.** The
adapter installs `AnnotateSnippetEmitter` at `psess_created`
(`lib.rs:243-250`), which overrides whatever `--error-format` would have selected.
Reusing channel 2 for the analyzer would require either parsing annotated text
(forbidden: that is the "regex approximation" the design rejects) or installing a
JSON emitter variant. A JSON emitter must still be bounded by the session's
`maxOutputBytes` (1 MiB by default from `NativeMiriProgramRunner`) and must not
colour.

**7.3 ABI/versioning consequences.** `native_miri_runner.dart` rejects any
`abiVersion() != 1`. Adding functions is source-compatible but changing the
`QfliConfig` layout is not; a v2 bump requires updating that check, the C ABI
test, the packaging audit and the schema-1 manifest hashes. The packaged OHOS
host is **aarch64 only** (`native/README.md`) while
`native/build/runtime/ohos-x64/manifest.json` describes a different, stale
x86_64 driver (`2223f3b2…` vs packaged `2224b02d…`) — do not treat that file as
packaged evidence.

**7.4 Timeout semantics are worse than they look.**
- `EditorAnalysisController` re-arms its 12 s watchdog *at dispatch*, and the
  comment in `_pump` claims queue wait must not consume the timeout. For a
  one-shot `analyze()` that is false: time spent waiting inside your provider
  counts, and the user sees "本地检查器响应超时".
- `qfli_miri_run` takes a process-wide `COMPILER_LOCK`, and a session is
  single-shot (`started.swap(true)`). A 30 s program run therefore blocks
  analysis for up to 30 s and produces a timeout message even though nothing is
  wrong.
- `qfli_miri_cancel` does **not** preempt an active rustc query
  (`native-runtime.md` §7). Cancelling on timeout returns control only at
  `after_crate_root_parsing` / `after_expansion` / `after_analysis` — three
  checkpoints for the whole analysis. A pathological macro expansion keeps the
  lock, so a timed-out analysis can starve the next one *and* the Run button.
- Rust-side mitigation to specify: a per-process analysis mutex plus a bounded
  `unavailableReason` ("代码检查正在运行/编译中，稍后重试") instead of queueing
  past ~2 s, and a hard cap much shorter than the UI watchdog (e.g. 4–6 s) so the
  provider always answers before 12 s.
- Late results are still applied: after a timeout, if the text is unchanged,
  `_current()` passes and the response overwrites the timeout message. Harmless
  but should be asserted in a test so it is a decision, not an accident.

**7.5 Proc macros.** Metadata-only rustc still expands derives, which requires a
*host-native* proc-macro dylib for each external derive. The packaged OHOS
manifest ships `libstd`/`libcore`-class rlibs including `libproc_macro-*.rlib` but
**no `libproc_macro*.so`, and no third-party proc-macro dylibs at all**; the guest
is `x86_64-unknown-linux-gnu` interpreted by Miri, which cannot `dlopen` a
proc-macro to run it on the host. Practical consequence: on device, only builtin
derives and `macro_rules!` work. Do not spend the native-analysis work on external
derives — detect them and report unavailable.

**7.6 build.rs.** Running Cargo is forbidden by design, and metadata-only `rustc`
never executes `build.rs`, so anything depending on generated code
(`include!(concat!(env!("OUT_DIR"), ...))`), `cargo::rustc-env`,
`cargo::rustc-cfg` or `--cfg feature="..."` cannot be analyzed truthfully. The
honest behaviour is a manifest gate: if `Cargo.toml` has `[build-dependencies]`,
`build = "..."`, a `build.rs`, or a non-empty `[dependencies]`, return
`unavailableReason` ("项目包含构建脚本/外部依赖，离线检查不可用") instead of
emitting E0432/E0433 noise. Current shipped content has none of these (all 166
examples are single-file, no `files` map, no dependency sections), so the gate
costs nothing today and prevents fabricated red squiggles on user projects later.

**7.7 Edition/target/cfg drift — three sources of truth today.**
- app-created Cargo projects: `edition = "2021"` (`rust_project_store.dart:122`)
- host content verification: `--edition=2021` (`verify_rust_content.py:59`)
- embedded runner: `--edition=2024`, `--target=x86_64-unknown-linux-gnu`,
  `--crate-cfg miri`, `always_encode_mir`, `deduplicate_diagnostics = false`
  (`native/miri_adapter/src/lib.rs:236-245,405-411`)
- a bare `rustc file.rs` with no `--edition` means **edition 2015** — forgetting
  the flag turns valid 2021 code (`let ... else`, bare `dyn`, 2021 array
  `IntoIterator`) into false errors.
On desktop the analyzer must read `edition` from `Cargo.toml` (default 2021 for
Cargo, and an explicit choice for standalone files), and must decide whether it
mirrors the embedded runner (2024 + `cfg(miri)`) or the host verifier (2021).
Mismatch means "Run passes but the editor is red", or the reverse. `cfg(miri)`
in particular hides `#[cfg(not(miri))]` code from analysis and enables
`#[cfg(miri)]` shims, which is a semantic change, not a formatting one.

## 8. Meaningful regression cases

Each case must assert exact offsets (start/end) **and** the rendered line, not
just "diagnostics is not empty". `CM` = captured-snapshot model, i.e. what core
actually sends.

| ID | Fixture | Assertion |
| --- | --- | --- |
| C1 | LF file, error on line 3 | offsets select exactly the offending token; `location()` prints `file:3:<col>`. |
| C2 | Pure-CRLF file, same error on line 3 | identical token selected as C1 modulo the `\r` (offsets grow by 3 on line 3); this is the byte-base regression. |
| C3 | Mixed CRLF/LF file | analyzer receives the all-CRLF snapshot; spans still land on the right token (proves the analyzer used `snapshot.text`, not disk bytes). |
| C4 | Emoji (`😀`) in a comment before the error, same line and previous line | no off-by-one/two; proves UTF-8→UTF-16 (surrogate) handling. |
| C5 | UTF-8 BOM file | offsets land on the token; no 1-unit drift. |
| C6 | Tab-indented `match` with a non-exhaustive pattern | span covers the arm/expression, not the whole line; proves no use of display columns. |
| C7 | CJK comment immediately before the token | correct span (3-byte UTF-8, 1 UTF-16 unit). |
| C8 | `src/main.rs` + `src/helper.rs` with an unsaved edit in `helper.rs` | error reported in `helper.rs` uses the unsaved text; editing `helper.rs` bumping revision invalidates it. |
| C9 | Error only in the non-active module file | diagnostic still returned for `helper.rs` and Problems shows `helper.rs:l:c`; navigation opens it. |
| C10 | `src/lib.rs` with no `main` | **clean** (no E0601); proves crate-type selection. |
| C11 | `src/bin/tool.rs` + `[[bin]] path` override | analyzed as its own bin target, no cross-target duplicates. |
| C12 | Valid file | `diagnostics == []` **and** `unavailableReason == null` (the only "clean" state). |
| C13 | Project with `build.rs` / `[dependencies]` | `unavailableReason` set, `diagnostics` empty, Problems shows the reason — never red squiggles on imports. |
| C14 | Project above 64 files / 4 MiB | analyzer is not even called (core short-circuits); assert the message, and assert no temp dir is created. |
| C15 | Cancel/abandon then re-analyze | no stale squiggles, no leaked temp dir, second result wins. |
| C16 | Edit while analysis is in flight | whole response dropped by `_current()`; no squiggles from the old text. |
| C17 | Timeout (fake slow provider / lock held) | `unavailableReason` mentions timeout and `checked == false`; **no** claim of clean code. |
| C18 | POSIX-cased path mismatch (device) or Windows `\\?\`/junction path from the compiler | diagnostic is either delivered with the exact requested path or deliberately dropped — assert the chosen behaviour; note Windows `p.equals` is already case-insensitive, POSIX is not. |
| C19 | Empty file / insertion-point diagnostic | 1-unit underline or gutter mark at the position, no crash. |
| C20 | Native (device) parity | the same fixtures produce the same offsets from the native analysis entry as from desktop rustc — required before claiming mobile analysis. |

## 9. Blockers (do not report these as done)

- **B1 — no OHOS analysis backend.** Adapter ABI 1 has no analysis mode and no JSON
  diagnostics; the packaged OHOS host is aarch64 while the only ohos manifest in
  `native/build/runtime/` is x86_64 and stale. Any mobile claim needs: ABI
  extension, `Compilation::Stop` path that never calls `miri::eval_entry`, JSON or
  otherwise structured diagnostics, adapter + driver rebuild for
  `aarch64-unknown-linux-ohos`, updated manifest hashes, and a signed HAP run.
- **B2 — no compiler on this host.** `rustc`/`cargo` are not on `PATH`, no
  `~/.rustup` toolchain and no bundled compiler directory, so the JSON schema
  details flagged **UNVERIFIED** (§4.1 CRLF byte base, §4.5 BOM, `column_start`
  unit) could not be measured here. Whoever owns the analyzer must run C1/C2/C4/C5
  against the pinned 1.98.1 rustc before freezing the mapping.
- **B3 — no device.** `hdc list targets` is empty (per the task audit), so no
  packaged-device analysis evidence is possible yet. R5's "actual compiler tests"
  evidence cannot be produced on OHOS in this session.
- **B4 — ownership.** The analyzer files are another worker's. This report is
  therefore a review input: the mapping algorithm, the crate-root rule, the
  manifest gate and the timeout policy in §4–§7 are the points to check in their
  implementation, and C1–C20 are the cases to demand as proof.
- **B5 — edition drift** (§7.7) is a product-wide inconsistency that predates this
  work; whoever changes it must change the runner, the content verifier and the
  analyzer together or the three will disagree.

## 10. Recommended order if the analyzer is to be completed

1. Desktop provider first (it can be validated today): temp mirror (LF-normalized,
   `.rs`-only, `--out-dir` inside the temp root), `--emit=metadata
   --error-format=json --json=diagnostics`, edition from `Cargo.toml`, crate type
   from the active file, deterministic temp→project path mapping.
2. Byte→UTF-16 mapper with the C1–C7 fixtures wired as unit tests before any UI
   wiring; assert exact offsets.
3. Manifest gate for build scripts/external deps (C13) so "unavailable" is
   truthful rather than noisy.
4. Bounded-timeout policy (§7.4) and cleanup/cancel tests (C15–C17).
5. Only then the native analysis entry, with ABI/versioning changes and a
   packaged aarch64 device run (C20). Until that exists, `codeAnalyzer` must be
   installed only where the desktop backend is actually reachable, so mobile shows
   the explicit unavailable state rather than an empty Problems panel.
