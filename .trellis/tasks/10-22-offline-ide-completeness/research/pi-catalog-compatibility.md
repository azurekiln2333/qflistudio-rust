# Rust catalog compatibility vs. the packaged native Miri/mobile project runner

Date: 2026-10-22. Research/evidence only. No product source was modified by this
audit; no build, no Flutter, no git operation, no device execution was claimed.

Scope: **all 166 authored topics** (`tool/rust_content/topics_001_084.json`,
`topics_085_166.json`) — 166 lesson programs (`code`), 166 exercise answers
(`exercise.answer`), and the 23 attached Cargo bundles (`files`) — reviewed
against the **actual shipped engine**, not against the host verifier.

## 1. What the shipped engine actually does (source-of-truth)

| Fact | Evidence |
| --- | --- |
| One file is compiled per run: `QfliConfig.source_path` only. No Cargo, no manifest, no `--extern`, no multi-crate graph. | `native/miri_adapter/src/lib.rs:405-419`, `lib/native_miri_runner.dart:129-224` |
| Fixed args: `--target=x86_64-unknown-linux-gnu --edition=2024 --crate-name=qfli_user_program --color=never`. Edition is **not** taken from the project. | `native/miri_adapter/src/lib.rs:413-418` |
| All three packaged adapters embed those args (proved on the binaries, not just the source). | `native/build/device/ohos-arm64/libqfli_miri.so`, `native/build/runtime/android-{arm64,x64}/libqfli_miri.so` contain `--edition=2024`, `x86_64-unknown-linux-gnu`, `qfli_user_program` |
| `--cfg=miri` is injected for every user crate. | `native/miri_adapter/src/lib.rs:242` |
| Miri runs with `MiriConfig::default()` except `args` and `short_fd_operations: false`. | `native/miri_adapter/src/lib.rs:281-285` |
| Isolation is **on**: `isolated_op: IsolatedOp::Reject(RejectOpWith::Abort)`. Filesystem, process spawn, sockets and real-time clocks reject the operation. | `native/build/miri-windows/miri/src/eval.rs:195-200` |
| Leak check is **on**: `ignore_leaks: false`. A deliberate leak is an error. | `native/build/miri-windows/miri/src/eval.rs:197`, `eval.rs:574-590` |
| "main thread terminated without waiting for all remaining threads" is an error. | `native/build/miri-windows/miri/src/eval.rs:576-581` |
| Interpreted environment is **empty** (`env: vec![]`); argv is exactly one element, the source filestem (`main`). | `eval.rs:93`, `native/miri_adapter/src/lib.rs:282` |
| `num_cpus: 1` (`available_parallelism` returns 1), RNG seed 0 (deterministic), virtual monotonic clock advancing 5000 ns per basic block. | `eval.rs:224-227`, `machine.rs:699`, `clock.rs:9-20` |
| `SystemTime::now()` (REALTIME) is an isolated op → error. `Instant::now()` is allowed but is the *virtual* clock. | `native/build/miri-windows/miri/src/shims/time.rs:60-76,105` |
| Any Miri error (UB, leak, isolation, unsupported op) becomes exit code **1** with state FINISHED; only adapter limits produce state 4/exit 124 or state 3/exit 130. | `eval.rs:592-604`, `native/miri_adapter/src/lib.rs:424-441` |
| Resource limits (Dart defaults): 10 000 000 basic blocks, 30 s wall clock, 1 MiB output (512 B reserved for diagnostics), 64 MiB guest memory. | `lib/native_miri_runner.dart:19-22`, `native/miri_adapter/src/lib.rs:37` |
| stdin is only the optional project `input.txt` (≤16 MiB). | `lib/native_miri_runner.dart:129-142` |
| On Android/iOS/OHOS the runner **always** uses the embedded engine, even when `Cargo.toml` exists. | `lib/rust_runner.dart:68-84` |
| The profile reports `runtimeStatus: 'available'` only on Android. On OHOS the UI declares the Rust runtime unavailable. | `lib/main.dart:26-40` |

Host verification (`scripts/verify_rust_content.py:78-81`) compiles with
`--edition=2021` and runs Cargo with each manifest's own edition. **A host pass
therefore cannot prove engine compatibility.**

## 2. Inventory (complete, nothing skipped)

- 166 topics, IDs 1..166 contiguous, no duplicates (`scripts/generate_rust_content.py --check` contract).
- Programs the engine can be asked to run: 166 `code` + 166 `answer` = **332**.
- Attached bundles: **23** (`005,006,007,009,012,013,014,105,106,107,111,112,146,150,151,152,157,158,159,161,164,165,166`).
- Authored runtime labels (labels only, not evidence): desktop 141, cargo 22, miri-candidate 2 (`134`,`154`), external 1 (`146`).
- Feature scan over all 332 programs (regex over authored text, then read by hand):
  threads 22 topics, `Arc/Mutex/RwLock/Condvar/atomics/mpsc` 26, `unsafe` 10,
  raw pointers 8, `HashMap/HashSet` 11, `async` 10, `Instant` 7,
  `fs`/`env`/`SystemTime`/`process::id` 4 (`164`,`165`), `Box::leak` 1 (`042`),
  `catch_unwind` 1 (`108`), `#[no_mangle]`/`extern "C" {}` 4 (`157`,`158`,`159`,`166`),
  `cfg(target_arch)` 1 (`008`).
  No authored program uses stdin, `Command`, sockets, `current_exe`, `Backtrace`,
  `libc`, `std::os::unix/windows`, signals, `asm!`, `no_std`, a global allocator,
  `thread_local!` or `OnceLock`.

## 3. Class A — hard compile failures on the engine (proved)

The engine forces **edition 2024**; the host verifier uses 2021. I compiled every
one of the 332 programs twice with the **pinned 1.98.1 compiler**
(`native/build/miri-windows/compiler/bin/rustc.exe`), `--cfg=miri`,
`--emit=metadata`, host target, no execution:

- edition 2021: **332/332 compile** (consistent with the recorded host pass).
- edition 2024: **8 records fail** (7 topics).

| ID | Program | Construct (line) | Engine error |
| --- | --- | --- | --- |
| 062 | answer | `Some((ref name, ref age)) => ...` on a `&[(String,u32)]` scrutinee — a teaching example for `ref` | `cannot explicitly borrow within an implicitly-borrowing pattern` (edition-2024 match ergonomics) |
| 157 | code | `#[no_mangle]` at lines 2 and 7; `extern "C" { pub fn rust_add(..); }` at line 15 | `unsafe attribute used without unsafe`; `extern blocks must be unsafe` |
| 157 | answer | `#[no_mangle]` line 1; `extern "C" {` line 8 | same two errors |
| 158 | code | `#[no_mangle]` line 5; `extern "C" {` line 20 | same |
| 158 | answer | — | compiles (no FFI attribute) |
| 159 | code | `#[no_mangle]` lines 4 and 16; `extern "C" {` line 22 | same |
| 159 | answer | `#[no_mangle]` line 1; `extern "C" {` line 7 | same |
| 166 | code | `#[no_mangle]` line 17; `extern "C" {` line 30 | same |
| 166 | answer | `#[no_mangle]` line 17; `extern "C" {` line 30 | same |

Mechanism: edition 2024 deny-by-default lints `unsafe_attr_outside_unsafe`
(`#[unsafe(no_mangle)]`) and `missing_unsafe_on_extern` (`unsafe extern "C" {}`).
These are also *teaching-content* regressions: FFI lessons currently teach a
syntax that the shipped compiler rejects. Fixing them is an authored-content
change (edition-2024 syntax) and must not be done by silently downgrading the
engine's edition, which is a pinned ABI contract.

## 4. Class B — hard runtime failures under the engine's isolation/leak policy

| ID | Program | Construct | Predicted engine result |
| --- | --- | --- | --- |
| 042 | code | `Box::leak(String::from("leaked").into_boxed_str())` (line 24) — deliberately taught as "leak to `'static`" | `the evaluated program leaked memory` → exit **1**; stdout stops after `holder.label = guest`. `ignore_leaks` is false and cannot be relaxed per-session by content. |
| 164 | code + answer | `Scratch::new()` → `SystemTime::now()` (REALTIME, line 131/143) then `env::temp_dir()`, `fs::create_dir`; `save()` → `OpenOptions::create_new` + `fs::rename`; `env::args()`; `process::id()` | Isolation abort on the first REALTIME/fs op → exit **1**. Also `env::args()` would yield only the filestem and the environment is empty. |
| 165 | code + answer | `Scratch::new()` → `SystemTime::now()` (line 112/117), `fs::write`/`fs::create_dir`; `count_file` → `fs::read_to_string`; `env::current_dir`; `process::id()` | Isolation abort → exit **1**. |

Note the distinction that the harness must encode: `code`/`answer` are what the
engine runs; `files` are Cargo-only artifacts. 164/165's `src/main.rs` equals
`code`, so the *bundle's* entry is equally unrunnable on device even though
`cargo test` passes on a desktop.

## 5. Class C — compiled but semantically different on the engine (must be measured, not assumed)

| ID(s) | Construct | Divergence |
| --- | --- | --- |
| 008 | answer `#[cfg(target_arch = "x86_64")]` / `"aarch64"` | The guest is always `x86_64-unknown-linux-gnu`, so an **arm64 phone prints `arch = x86_64`**. Deterministic, but it contradicts the device it runs on; expected output must be authored for the guest, not the host. |
| 013, 161 | `Instant::now()/elapsed()` (`as_nanos`, `Duration`) | Virtual clock = 5000 ns per basic block. Printed durations are a *basic-block* measure, not wall time; they differ from the recorded host `output` and from run to run only if the block count changes. 013 compares/prints derived "best" values. |
| 144, 146 | `mpsc::recv_timeout(Duration::from_millis(2))` | Deadlines use the virtual monotonic clock (~400 basic blocks for 2 ms). Correct but timing-model dependent; a change in preemption/GC can flip which branch wins. |
| 121-137, 139-146, 166 | 22 topics spawning threads, all of which `join()` (verified spawn↔join pairing) | Miri supports threads/`Condvar`/`scope`/`mpsc`, but the "no unjoined thread" rule and cooperative scheduling make deadlock/reordering possible. 136 holds the receiver `Mutex` across a blocking `recv()`; 132 relies on consistent lock order; 134/135 rely on atomics under `data_race_detector: true` + `weak_memory_emulation: true`. None of this is provable by inspection. |
| 153, 154, 155, 156, 160 | `unsafe`, `from_raw_parts(_mut)`, `&x as *const T as usize` arithmetic | Valid-by-contract code, but Miri (Stacked Borrows, `AlignmentCheck::Int`) is the strictest stack here; 154's `from_raw_parts(data.as_ptr(), 0)` and 156's `split_at_mut` replica are exactly the patterns Miri rejects when the contract is subtly wrong. |
| 124, 116, 118, 119 | `Rc`/`Rc<RefCell>` graphs | Inspected: 118 builds a cons list without a cycle, 119 breaks a cycle with `Weak`, 124 uses `replace` so closures never form a cycle. No leak expected — but this is the class where a future edit silently creates a cycle and turns into `memory leaked`. |
| 108 | `panic::catch_unwind` printing `panicked=true` | The default panic hook writes the Miri-formatted panic text to **stderr**. Any harness that compares the whole stream instead of stdout-only would fail; the recorded `output` is stdout. |
| 028, 045, 049, 053, 076, 086, 087, 098, 161 | `HashMap`/`HashSet` | Seed-0 RNG makes iteration deterministic but **different from the host**. Verified by reading: 028 has one entry; 045/049/086/087/098 sort or use `BTree*`; 053 prints `get(..)`, 081 prints `len()`. Safe today, fragile under any edit that prints map order. |
| 158 code, 159 code, 166 code | `#[no_mangle] pub extern "C"` re-imported through `extern "C"` in the *same* crate | Even after the edition-2024 syntax fix, self-reimport of an `#[no_mangle]` symbol is exactly the pattern the spec calls out as unsupported for external interop; it happens to work inside one crate but must be proved on device. |
| 009 code | `env!("CARGO_PKG_VERSION")` only in comments; uses a local `const` | Compiles and runs; no engine dependency. The bundle's `build.rs`, `src/bin/generated.rs` (`include!(concat!(env!("OUT_DIR"),…))`) are Cargo-only. |
| 062 exercise (whole topic) | teaching `ref` patterns | Even after fixing the answer, the lesson's premise (explicit `ref` in an implicitly-borrowing pattern) is edition-2024-illegal; the fix needs re-teaching, not a one-line patch. |

## 6. Class D — attached Cargo bundles the mobile engine cannot execute

The native runner ignores `Cargo.toml` entirely; only `code` (= `src/main.rs`)
runs. Bundle-only structure that therefore has **no mobile execution path at all**:

| ID | Bundle structure | What is lost on device |
| --- | --- | --- |
| 007 | workspace with `crates/mathlib`, `crates/cli`, path dependency | multi-crate graph, second binary |
| 150, 151 | path-dependent **proc-macro** crates (`[lib] proc-macro = true`) | macro expansion of the real crate, `tests/proc_macro.rs`, `tests/derive.rs` |
| 012, 105, 106, 107, 111, 112, 146, 164, 165, 166 | `verify: test` bundles, `tests/*.rs`, `#[cfg(test)] mod tests`, `bin/thin.rs`, `src/lib.rs`, `src/inventory.rs` | unit/integration/doc tests, `src/lib.rs` API, extra bins |
| 009 | `build.rs` + `src/bin/generated.rs` (`include!(env!("OUT_DIR"))`) | build script, generated code, second bin |
| 006, 013, 014 | `verify: build` | build-only contract; still runnable as `code` |
| 164, 165, 166 | `tests/contract.rs` using `Command::new(env!("CARGO_BIN_EXE_…"))`, `current_dir`, temp dirs | process spawning, REALTIME clock, fs — impossible on the engine |

`scripts/generate_rust_content.py` only enforces `files["src/main.rs"] == code`.
It does **not** require path-dependency/`tests`/`build.rs` structure to be
reachable by any mobile runner, so today 23/23 bundles have host-only evidence.

## 7. Class E — the device gate that blocked every case

> **Superseded on 2026-10-22 (harness slice).** An OHOS x86_64 runtime is now
> packaged: `assets/miri/manifest.ohos-x64.json` (schema 1, `id
> b8c4f32546e3…`, `nativeHost: x86_64-unknown-linux-ohos`, 98 payload files, all
> present on disk) alongside the unchanged arm64 build
> (`manifest.ohos-arm64.json` / legacy `manifest.json`, identical `id
> 1e31884bf8e0…`). `NativeMiriTarget.loadManifest` selects the per-target
> manifest and only falls back to the legacy asset when the package inventory
> proves the per-target asset is absent. The arm64-only blocker below is
> therefore **historical**; what remains unproved is execution, which still
> requires a device run of `integration_test/rust_catalog_native_test.dart`.
> No case is claimed passing here.

Historical state (arm64-only packaging):

- `hdc list targets` → `127.0.0.1:5555`; `param get const.product.model` → `emulator`;
  `const.product.cpu.abilist` → **`x86_64`**.
- The then-packaged runtime (`assets/miri/manifest.json`) was schema 1 with
  `nativeHost: aarch64-unknown-linux-ohos` and `libqfli_miri.so` /
  `librustc_driver-*.so` / `libc++_shared.so` built for **aarch64**
  (`native/build/device/ohos-arm64/libqfli_miri.so` ELF `e_machine = 183`).
- `lib/native_miri_assets.dart` maps a manifest for **any** OHOS architecture and
  then rejects it unless `nativeHosts` contains the host
  (`('ohos','x64') → x86_64-unknown-linux-ohos`). With only the arm64 manifest,
  **no Rust program could run on the only reachable OHOS target**.
- Consequence at the time: the R1 gate had **0/332 executed cases**.

Current constraint (unchanged in kind, narrower in scope): the packaged
`manifest.ohos-x64.json` proves a matching *manifest* exists, not that the
native libraries load or that any program runs. Until a device run produces a
complete `RustNativeCatalogReport` (`complete: true`, `missingIds: []`), the R1
gate still has **0 executed cases**, and nothing in this catalog may be declared
passing.

- Secondary UI gate: `lib/main.dart:26-40` sets `runtimeStatus: 'available'` only
  for Android, so on OHOS the product itself reports the Rust runtime unavailable
  even if the engine were present. (Root owns `lib/main.dart`.)

## 8. Class F — acceptance ambiguity that will produce fake passes

- `topic["output"]` is asserted for `code` only; `exercise.answer` has **no**
  expected stdout field and `scripts/verify_rust_content.py:86-88` passes
  `expected=None` for answers. Host evidence for answers is therefore
  "compiled + exit 0". A device harness must either derive and freeze the
  expected answer output or explicitly record "exit-status-only" per answer —
  never treat "no assertion" as a pass.
- Example of the gap: **053 answer** prints `Some("one-two")` while the topic's
  `output` (`a = User { … }`) belongs to `code`.
- No topic supplies `input.txt`, so the engine's stdin path is unexercised by
  this catalog (the adapter's stdin contract is covered only by native fixtures).

## 9. Required real-engine validation cases (minimum set, per class)

Run on the packaged OHOS arm64 engine, in this order, with per-case
stdout/stderr/exit/state/target/nativeHost/manifest-id/compiler-revision recorded:

1. **Edition-2024 compile regressions (must be fixed, then re-proved):**
   062(answer), 157(code+answer), 158(code), 159(code+answer), 166(code+answer).
   Expected after fix: compiles and matches the authored stdout.
2. **Leak policy:** 042 code. Decide the contract (retain the leak demonstration
   and accept a documented `memory leaked` line, or re-teach with a non-leaking
   alternative). Do not flip `ignore_leaks` for one lesson.
3. **Isolation:** 164 code+answer, 165 code+answer. Either teach an
   isolation-safe variant or mark these as desktop-only with an explicit,
   recorded non-engine status — not a skip.
4. **Threads/concurrency:** 121, 122, 125, 126, 127, 128, 129, 130, 131, 132, 133,
   134, 135, 136, 137, 139, 140, 142, 144, 146, 165(scope), 166. Watch for
   deadlock reports, "main thread terminated without waiting", data-race
   reports and 124/30 s limit hits.
5. **Timing model:** 013, 144, 146, 161 — record that durations are virtual-clock
   values; freeze the authored `output` accordingly (013/161 print derived
   numbers).
6. **Target identity:** 008 answer — pin the expected `arch = x86_64` for the
   guest, and state it in the lesson.
7. **UB-adjacent unsafe:** 153, 154, 155, 156, 160 — confirm Miri accepts them
   (any `Undefined Behavior` line is a content bug).
8. **Panic-path stderr:** 108 — assert stdout only, and assert that stderr
   contains the panic text.
9. **Limits/cancel:** re-use the existing fixtures (`native/fixtures/*`) so
   state 3/4 and exit 130/124 are covered by native evidence, not by catalog
   lessons.
10. **Bundles:** for each of the 23 (`005,006,007,009,012,013,014,105,106,107,
    111,112,146,150,151,152,157,158,159,161,164,165,166`) record explicitly
    that `files` are Cargo-only and that the device run covers `code` only. Do
    not count `cargo test`/`build` as device evidence.

## 10. Blockers and what remains unproved

1. **No executed device evidence yet**: a matching OHOS x86_64 manifest
   (`assets/miri/manifest.ohos-x64.json`) is now packaged alongside arm64, so the
   manifest gate can pass, but no device run has produced a complete report →
   still 0/332 executed cases, and every `ohos-*` claim remains unproved.
2. **`runtimeStatus` is Android-only** (`lib/main.dart`, root-owned) → the OHOS
   product surface cannot present a real run today.
3. **Answers have no authored expectation** → the harness records them as
   explicit exit-status-only evidence (`stdoutAsserted: false`); a decided
   contract is still needed before any "all answers pass" claim.
4. **Edition mismatch** between host evidence (2021) and engine (2024) → host
   passes are not transferable; 7 topics need content changes.
5. **Bundle-only structure** (workspaces, proc macros, `build.rs`, `tests/`) has
   no mobile execution path → the harness writes every bundle file and runs its
   `src/main.rs` through the single-file engine; `cargo test`/`cargo build` are
   never counted as device evidence.
6. **Unproven by inspection:** scheduling outcomes of 121-137/139-146/166,
   Miri's verdict on 153-156/160, and the exact virtual-clock numbers of
   013/144/161. These need the engine, not more reading.

## 11. Runnable OHOS audit harness (what executes the full inventory)

Files (all owned by the catalog-harness slice):

| Path | Role |
| --- | --- |
| `scripts/generate_rust_native_catalog.py` | deterministic generator + `--check` drift/completeness gate |
| `assets/content_rust/native_catalog.json` | generated inventory: 166 lessons, 166 examples, 166 answers, 23 bundles, 332 runs |
| `lib/rust_native_catalog.dart` | strict model, dependency-free SHA-256, report and result types, `compareNativeStdout` |
| `integration_test/rust_catalog_native_test.dart` | the device harness that runs all 332 cases |
| `test/rust_native_catalog_test.dart` | host unit coverage (decode, digests, identity, incompleteness, OHOS manifests) |
| `scripts/test_rust_native_catalog.py` | generator determinism / drift / completeness tests |

Audit procedure (root runs the device steps):

1. `python scripts/generate_rust_native_catalog.py --check` — fails on any
   missing, duplicate, extra or drifted case, or on a tampered bundle file.
2. `python -m unittest discover -s scripts -p "test_rust_native_catalog.py"`.
3. `flutter test test/rust_native_catalog_test.dart`.
4. On a matching OHOS target
   (`flutter test integration_test/rust_catalog_native_test.dart`):
   the harness reads `NativeMiriTarget.current()`, loads the per-target manifest
   via `NativeMiriTarget.loadManifest`, refuses to run when
   `manifestMatchesTarget` is false or the interpreted `guestTarget` differs from
   the catalog, then executes every case.

Guarantees the harness enforces (no runtime-label skips, no silent omissions):

- one record per case with `id`, `topicId`, `kind`, `runtime` label,
  `entryFile`, `sourceSha256`, actual and expected exit status, actual and
  expected stdout, `stdoutAsserted`, stdout, stderr, duration, detail;
- a report header carrying runtime target key, native host, packaged manifest
  asset/id/host, rustc version and commit;
- individual failures are recorded and the run **continues**;
- `complete` is false when `interrupted` or when any inventoried id is missing,
  and a report is written every 10 cases and in `finally` even on abort;
- the test fails when any case is missing or failing, and it cannot pass on a
  non-`ohos` platform (`--dart-define=QFLI_RUST_CATALOG_PLATFORM` overrides only
  by explicit intent, never silently).

Known limitations, stated rather than hidden: bundle `files` are executed only
via `src/main.rs`; answers assert exit status only; the report is engine
behaviour, not a compiler backend check.

No engine pass is claimed for any ID in this report.
