# Curriculum B — Rust lessons 085..166 (author: rust-curriculum-b)

## Scope

- Exclusive artifact: `tool/rust_content/topics_085_166.json` (JSON array, 82 lessons, ids 85..166).
- This report: `.trellis/tasks/10-15-rust-release-readiness/research/curriculum-b.md`.
- Did not touch `tool/rust_content/topics_001_084.json`, `lib/`, `pubspec.yaml`, `main.dart`,
  any Dart/Flutter source, or `../qfli_studio_core`.

## Content contract

Each lesson object carries exactly the fields in the task `design.md` Content contract:

```
id, title, level (beginner|intermediate|advanced), domain, summary, concepts[],
objective, prerequisites[], explain, code (single-file Rust with main), output (exact stdout),
pitfalls[], exercise{prompt,hint,answer(complete compilable, has main)},
runtime (desktop|cargo|miri-candidate|external), optional files{path:source}, optional verify
```

Extra rules honoured:

- `files`, when present, always contains `Cargo.toml` and `src/main.rs`, and
  `files["src/main.rs"]` is byte-identical to `code` (enforced in the builder and the
  structure check). When `files` is present, `projectOutput` is also set (whole-project
  stdout, equal to `output` because the entry program is identical to `code`). Extra files
  (`src/lib.rs`, `tests/*.rs`, module trees) are real and are exercised by
  `verify=run|build|test`; the lesson's own single-file `code` never depends on them.
- Only std / local path dependencies. No network crates. `verify` is an enum token
  (`run|build|test`), never a shell command.
- Runtime labels: `desktop` 64, `cargo` 15, `miri-candidate` 2 (134, 154), `external` 1
  (146). 17 lessons carry a full Cargo `files` bundle; no Miri/engine claim is
  made; `miri-candidate` means std-only and *possibly* runnable on the packaged engine,
  unverified here.

## Domains covered (ids)

| Domain | ids | level |
| --- | --- | --- |
| 集合与迭代器 collections/iterators/closures | 085–098 | intermediate |
| 错误处理与模块 errors/modules/crates/testing | 099–112 | intermediate |
| 智能指针 smart pointers / interior mutability | 113–124 | advanced |
| 并发 concurrency: threads/channels/atomics/pool | 125–137 | advanced |
| 异步与 Future async: Future/Pin/Poll/executor | 138–146 | advanced |
| 宏 macros (declarative + proc-macro concepts) | 147–152 | advanced |
| unsafe 与性能 unsafe/FFI/performance + 3 capstones | 153–166 | advanced |

## Cross-review fixes applied (085..163)

A semantic cross review found real defects; all were fixed in the authored source and
re-verified with the real toolchain. 164..166 were **not** modified (content_plumbing
owns their replacement); a byte comparison confirms they are unchanged.

| Lesson | Defect | Fix |
| --- | --- | --- |
| 094 | said `sort_by_key` takes `Fn` | corrected to `FnMut` |
| 106 | thin bin "calls lib" while bin duplicated it | explain now matches the real code; `files` adds a lib + integration test showing genuine reuse |
| 118 | exercise asked for 4+5=9 but answer pre-seeded [1,2,3]→15 | answer starts from an empty Vec → 9 |
| 121 | `Arc<T>` Send/Sync oversimplified | explain + pitfalls now require `T: Send + Sync`; note Arc<RefCell>/Arc<Rc> are not Sync |
| 123 | said Cell "requires Copy" | clarified: only `get` needs `Copy`; `set/replace/take/into_inner` do not |
| 129 | prompt said halves sum to 6 and 10 | corrected to 3 and 7 to match `[1,2,3,4]` |
| 132 | `transfer(&m,&m,x)` self-deadlocks | added `std::ptr::eq` early-return + verified same-Mutex call |
| 138 | `spin_loop` implied as yielding | explain now states it is a spin hint, not a scheduling point; cooperative yield = return Pending |
| 139 | implied re-poll-after-Ready is UB; busy-spin noop executor | explain: it is a logic error, not UB; code uses a real wake-driven executor |
| 140 | explained wake but never called it | worker thread now calls `waker.wake()`; `wake_calls` is asserted observable |
| 143 | Join2 `expect` panicked if b finished first; Select2 never polled b | Join2 buffers either order (no panic); Select2 polls both, outputs `Either` |
| 144/145/146 | Pending futures never actually woken | all now use a real `Wake`+Condvar executor; 145 implements a ready-queue executor with `wakes>0` |
| 146 | exercise required `block_on_all` but answer lacked it | answer now defines and uses `block_on_all` (per-Sleep Shared, deterministic) |
| 147 | `max_of` evaluated `$rest` twice | binds `let v = $rest;` once |
| 148 | `sum_and_print` evaluated `$value` twice | binds `let v = $value;` once |
| 149 | `my_vec![expr; n]` re-evaluated `expr` per iteration | evaluates once into `let value`, then `clone`s |
| 150/151 | claimed proc-macro needs syn/quote / network | corrected: std `proc_macro` alone suffices; 150 ships a real offline derive-macro workspace (verified `cargo test`), 151 an offline path-dependency workspace |
| 157 | `rust_abs` overflowed on `i32::MIN` across C ABI | uses `wrapping_abs`; exercise verifies `i32::MIN` does not panic/abort |
| 158 | claimed FFI needs the libc crate | uses `std::os::raw::c_char` + `extern "C"` only; runtime `desktop`, verified offline |
| 161 | `hash_not_slower` timing assertion was nondeterministic | replaced with deterministic `assert_eq!`; timings no longer printed |

## Verification performed (real toolchain)

Compiler: `native/build/miri-windows/compiler/bin/rustc.exe` and `cargo.exe`, rustc/cargo 1.98.1.

For every one of the 82 lessons:

1. `lesson.code` written to a temp `main.rs`, compiled `rustc --edition 2021`, executed,
   and stdout byte-compared against `lesson.output`. **79/79 (085..163) match** (164..166
   are verified separately by their owner).
2. `lesson.exercise.answer` compiled and executed. **79/79 compile.**
3. Every lesson with `files` built as a real Cargo project (`cargo run` / `test`);
   `src/main.rs == code` verified; output compared. **All pass.**

Structural check (`structure_check.py`): ids exactly 85..166 gap-free, unique titles and
unique `code`, all required fields non-empty, `fn main` present in `code` and `answer`,
≥2 concepts, ≥3 pitfalls, no placeholder tokens (`TODO`, `unimplemented!`, `todo!()`),
no filler phrases, `level`/`runtime` from the allowed enums, `files` convention intact.

Summary: **79/79 (085..163) lessons compile and run; outputs match exactly; structure OK.**
164..166 untouched and byte-identical to the previously delivered version.

Reproduce (toolchain paths per the coordinator):

```
python build.py            # emits topics_085_166.json from the authored modules
python verify.py --from 85 --to 166   # compile + run + diff every lesson
python structure_check.py  # schema + quality gate
```

(The authoring/verification scripts live outside the repo in a scratch directory; only
the emitted JSON and this report ship. The JSON is UTF-8 without BOM.)

## Notes / honest limits

- Two lessons are labelled `miri-candidate` (134 Ordering, 154 from_raw_parts): std-only
  and deterministic under SeqCst ordering, but **no Miri/engine run evidence exists**, so
  they are not claimed as supported on any packaged engine.
- One lesson is `external` (146 tokio concept): it would need a crate download, so it is
  taught with a std-only wake-driven executor and the real dependency appears only as a
  comment in the `files` Cargo.toml. 150/151/158 no longer need network: proc-macro is
  implemented with std `proc_macro` and FFI with `std::os::raw`, both verified offline.
- Thread/timing examples are made deterministic with fixed work counts and `join`
  collection; no wall-clock assertions are printed or asserted (lesson 161 prints only
  the deterministic equality/count).
- 164..166 are intentionally untouched (content_plumbing owns their replacement); a byte
  comparison confirms byte-identical output for those ids.
