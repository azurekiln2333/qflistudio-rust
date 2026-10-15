# Curriculum A research — topics 001..084 (Herdr wB:rust-curriculum-a)

Owner pane: Herdr wB (workspace cwd `D:/MyNewProjects/qfli_rust`).
Exclusive write scope: `tool/rust_content/topics_001_084.json` (this file only)
plus this research note. No shared-core edits, no `main.dart`, no `pubspec.yaml`.

## Deliverable

`tool/rust_content/topics_001_084.json` — a JSON array of 84 lesson objects,
IDs `1..84`, following `10-15-rust-release-readiness/design.md` Content contract:

```
id (int), title, level (beginner|intermediate|advanced), domain, summary,
concepts[string], objective, prerequisites[string], explain,
code (complete single-file Rust), output (exact stdout),
pitfalls[string], exercise { prompt, hint, answer (complete compilable code) },
runtime (desktop|cargo|miri-candidate|external),
optional files { relpath: source }, optional verify (run|build|test)
```

Lesson IDs 1..84 map to curriculum-index domains A–E:

| Range | Domain | Index domain |
| --- | --- | --- |
| 001–014 | toolchain-cargo | A Toolchain, Cargo, first programs |
| 015–032 | syntax-types | B Syntax, types, control flow |
| 033–052 | ownership-borrowing | C Ownership, borrowing, lifetimes |
| 053–068 | data-modeling | D Structs, enums, pattern matching |
| 069–084 | traits-generics | E Traits, generics, trait objects |

Pairing note: `topics_085_166.json` (owned by pane rust-curriculum-b) authors
lesson IDs 85..166. Authoring splits by ID range, not by domain.

## Runtime labels

- `desktop` — plain `rustc --edition 2021`, std only, deterministic output.
- `cargo` — needs a manifest / multi-file project. The lesson still keeps a
  runnable single-file `code`; the `files` map carries the real Cargo project.
- `miri-candidate` — std-only, *possibly* engine-compatible, unverified.
- `external` — needs an absent toolchain/crate; taught via a runnable std-only
  model, never claimed executed here.

For lessons 1..84 only lessons 5,6,7,9,12,13,14 are `cargo`; the rest `desktop`.
(The paired examples 85..166 carry the `external`/`miri-candidate` labels.) Per
the index, in this range no lesson is `miri-candidate` or `external`.

## Authoring rules applied

1. Every `code` is a unique, complete program with `fn main`, compiles with
   `rustc --edition 2021`, std-only unless `runtime == cargo`.
2. `output` is the exact stdout (trailing newline meaningful), reasoned from the
   code, not copied from a template. Time/thread output is made deterministic
   (join before print, sort before print, fixed sleep budgets).
3. No filler: no `TODO`/`unimplemented!`/`panic!` placeholders, no
   `println!`-only bodies, no repeated "weighted=", no duplicated exercise.
4. `answer` is itself a complete compilable program solving the exercise.
5. `desktop` lessons import as a single file (no `files` map needed). `cargo`
   lessons add `files` for the paired real project while retaining the
   single-file `code` counterpart.

## Progress

- [x] Read prd.md / design.md / implement.md / content-imports spec / index.
- [x] Create `tool/rust_content/` and this research note.
- [x] Author IDs 001–014.
- [x] Author IDs 015–032.
- [x] Author IDs 033–052.
- [x] Author IDs 053–068.
- [x] Author IDs 069–084.
- [x] Self-validate JSON schema, uniqueness, no filler, balanced per-domain.
- [x] Real compile+run all 84 lessons and 84 exercise answers plus 7 Cargo
      projects with the provisioned GNU toolchain (rustc 1.98.1).
- [ ] Report to coordinator via trellis channel for commit.

## Final import convention (coordinator, binding)

- every `lesson.code` / `example.code` is a standalone single-file program
  compilable by `rustc --edition 2021` (no stdin, deterministic stdout);
- when `files` is present, `files['src/main.rs']` MUST equal `code` byte-for-
  byte. `_build.py` enforces this by copying `code` into `files['src/main.rs']`
  and the audit re-checks it;
- extra `files` (lib.rs, tests, extra crates, workspace) add real structure but
  the single-file detail body never depends on an absent file;
- `projectOutput` holds the whole project stdout; `verify` ∈ {run,build,test};
- no network dependencies (std or local `path` only; `--offline`).

## Cross-review fixes (round 1)

Applied 2026-10-15 after coordinator cross-review; only my owned JSON changed
(8 lines in `topics_001_084.json`), then fully re-verified.

1. **005** `projectOutput` held a stale `sum_sq=385…` from an earlier draft.
   `_build.py` now sets `projectOutput = output` whenever the project's default
   binary is the lesson `code` and `verify == "run"`; 005 therefore reports the
   real project stdout (the profile-knobs list + sum), identical to `output`.
2. **007** explain wrongly claimed a shared workspace lock prevents multiple
   incompatible versions. Corrected: the shared lock makes resolution consistent
   across members and avoids duplicate builds/feature skew, but Cargo *does*
   allow incompatible major versions to coexist; type-incompatibility only
   appears when such a value must cross crate boundaries.
3. **009** explain wrongly said a missing `rerun-if-changed` reuses stale
   artifacts. Corrected to the real semantics: with no rerun directives cargo
   re-runs the build script when any package file changes (conservative full
   watch); emitting specific directives disables that default. The pitfall was
   rewritten to the real risk (declaring only some paths while omitting others).
4. **025** explain wrongly said `repr(Rust)` keeps declaration order. Corrected:
   the default representation may reorder fields and is not C-layout-compatible;
   stable layout requires `repr(C)`.
5. **032** exercise answer did not actually preserve the original calculator's
   `*`/`/` precedence (it only folded `+`/`-` via `f64::INFINITY` sentinels).
   Replaced with a complete program: `neg` is normalized as a unary prefix that
   still yields a numeric token, so the original two-pass mul/div-then-add/sub
   precedence, divide-by-zero and trailing-operand errors are all preserved. The
   prompt/hint were rewritten to match, and the answer self-tests six inputs
   (`2 + 3 * 4`, `neg 5 + 2`, `neg 3 * 4`, `10 / 4 - 1`, `5 / 0`, `3 +`).

Re-validation after the fixes: `_build.py` OK, `_audit.py` all pass,
`_validate.py` **175/175 pass, 0 failures** (84 code + 84 answer + 7 projects)
with the same real GNU toolchain and link flags.

## Cross-review fixes (round 2)

1. **015** explain — corrected float→int `as`: it is *saturating* (since
   Rust 1.45), NaN→0, and integer/bool numeric `as` never causes UB; the old
   "undefined depending on version" claim was wrong.
2. **047** code — `tail` used `len - n` byte slicing, panicking on Chinese.
   Rewritten to count/slice by `chars`/`char_indices`, with a中文 test case and a
   new pitfall about UTF-8 byte-boundary slicing.
3. **048** explain — `Cell<T>`'s `set`/`replace`/`take`/`into_inner` work for
   *any* `T`; only `get` requires `Copy`. Corrected.
4. **049** explain — `HashMap::entry(key)` takes key **by value** (ownership),
   not by reference. Corrected.
5. **060** code — `render` byte-sliced `&text[..width-1]`, panicking on
   multi-byte input. Rewritten to char-count truncation/padding, with Chinese
   test cases; explain notes the byte hazard.

## Cross-review fixes (round 3)

1. **065** — exercise prompt said `i128` but answer used `i64`; prompt updated
   to `i64` (consistent, and `i64::MIN / -1` genuinely overflows).
2. **076** — the exercise required a real `merge` but the answer only had the
   default empty op. Now implements `entries()` and a genuine default `merge`
   that overwrites/补齐 from `other`; answer verified by real run.
3. **079** — `From<&str> for UserId` used `len()` and dropped the text while
   claiming lossless. Now `From<String>` is lossless (keeps the text) and
   `TryFrom<&str>` validates digits with real errors; the `From<&str>` +
   `TryFrom<&str>` E0119 blanket-impl conflict is documented and avoided.
4. **081** — tolerance `PartialEq` violated transitivity (20.0≈20.3≈20.6 but
   20.0≉20.6). Now `PartialEq` is exact per-field equality (`to_bits`/`Eq`) and a
   separate `approx_eq(tolerance)` method expresses approximate comparison.
5. **084** — lesson code and answer escaping was incomplete. Both now have
   `json_escape` (quote, backslash, `\n\r\t\b\f`, `\u00XX` for other control
   chars) and RFC-4180 `csv_escape` (quote when comma/quote/newline, double
   internal quotes), tested on a record with中文、引号、反斜杠、换行、逗号、制表符.

Re-validation after rounds 2+3: `_build.py` OK, `_audit.py` all pass,
`_validate.py` **175/175 pass, 0 failures** (84 code + 84 answers + 7 projects)
on the real GNU toolchain, and a 15-point content assertion confirms every fix.

## Cross-review fixes (round 4)

1. **006** code+explain — `caret_allows` only checked equal-major; the general
   `^` claim was wrong for pre-1.0. Rewritten with correct Cargo semantics:
   `^1.2.3` → `<2.0.0`, `^0.2.3` → `<0.3.0`, `^0.0.3` → `<0.0.4`; code now
   computes a proper upper bound and tests 0.x / 0.0.x cases; explain and output
   updated (real run).
2. **012** explain — corrected the `#[test]` signature: functions take no
   arguments and may return `()` **or** any `Termination` type (e.g.
   `Result<(), E>`, where `Err` fails), not only `()`.
3. **015** explain — the float→float "saturates" claim was wrong. Corrected to
   IEEE 754 round-to-nearest: f64→f32 can yield ±infinity when out of range
   (`f64::MAX as f32 == f32::INFINITY`), NaN stays NaN; saturation applies only
   to float→int.
4. **049** explain — `HashMap::remove` deletes the whole entry (no `None` slot);
   the `Option<V>` only signals a possibly-missing key. `Vec` has no holes either.
5. **079** explain — made explicit that `From` must be genuinely lossless (cannot
   drop/encode less information, e.g. via `len()`); the answer's `From<String>`
   keeps the text and `TryFrom<&str>` is the validated fallible path.
6. **081** explain+answer — clarified `PartialEq`'s contract is symmetry +
   transitivity (reflexivity is `Eq`'s extra requirement); the bit-equality
   `PartialEq` (`to_bits`, `impl Eq`) is symmetric/transitive but treats `+0.0`
   and `-0.0` as unequal and same-bit `NaN` as equal — documented as an explicit
   choice; `approx_eq` carries the tolerance comparison.

Round-4 re-validation: `_build.py` OK, `_audit.py` all pass, `_validate.py`
**175/175 pass, 0 failures**, plus an 8-point round-4 assertion (all PASS) and a
re-check that all rounds 1–3 fixes are still present (all True).

## Cross-review fixes (round 4 completion)

The first round-4 pass missed the **079 main `code`** (only the answer was fixed).
Final corrections:

1. **079 main code** — replaced the still-wrong `struct UserId(u64)` +
   `From<&str> { UserId(value.len() as u64) }` (output `UserId(4)`) with a
   genuinely lossless `struct UserId(String)`, `From<String>`/`From<&str>`
   preserving all text, plus `assert_ne!` proving two same-length, different-text
   ids (`"abcd"` vs `"wxyz"`) stay distinct. `output` updated from a real run.
   (079 is desktop, so there is no bundled `files`/`src/main.rs` to mirror.)
2. **081 exercise answer comment** — removed the wrong line "PartialEq 必须是
   等价关系：自反、对称、传递。" It now states the correct contract
   (symmetry + transitivity; reflexivity is `Eq`'s extra requirement) and notes
   the `to_bits` bit-equality choice.
3. **048 explain first sentence** — clarified that `set`/`replace`/`into_inner`
   work for any `T`, while `take` requires `T: Default` (it leaves
   `T::default()`), and only `get` requires `T: Copy`.

Targeted re-verify (no full 84 rerun, per instruction):
`_build.py` OK, `_audit.py` all pass; 10-point assertion for 048/079/081 all
PASS; real compile+run of lessons 48/79/81 (code + answer) all ok, and 079's
`code` stdout equals `output` exactly.

## Scratch helpers relocated

All authoring/validation helpers (`_a*.*`, `_b*.*`, `_c*.*`, `_d*.*`, `_e1.py`,
`_e2.py`, `_build.py`, `_validate.py`, `_audit.py`, `_fixquotes.py`,
`_patch_r4b.py`, `_check_r4b*.py`, `_scratch079.*`) were moved from
`tool/rust_content/` to `build/content-author-scratch/`, which is gitignored
(`**/build/`) and stays safely inside the Rust repo. No other files were deleted.
`_build.py`/`_validate.py`/`_audit.py` were repointed so they read/write the
canonical `tool/rust_content/topics_001_084.json`.

## Cross-review fixes (round 5 — final alignment)

055/057/062/064/068 answers or prompts were not aligned with their stated tasks:

1. **055** exercise `answer` — prompt asked for `struct Task` but the answer only
   had a free `transition(status, action)` fn. Rewrote to define `struct Task`
   with `Task::new` and a `transition(&mut self, action)` method that mutates
   `status`, then demos a legal transition, an archive, and a rejected re-open.
2. **057** exercise — prompt asked for guards **and** `@`; the answer only used
   `@`. Answer now uses `@` bindings plus an `if s % 10 == 0` guard (whole tens
   get a "(整十)" suffix), and the prompt describes that behaviour.
3. **062** exercise `answer` — prompt asked for an explicit `ref`; the answer
   used implicit binding. Now binds `Some((ref name, ref age))` explicitly.
4. **064** exercise — prompt asked for explicit `Outside/InWord/InNumber` states
   but the answer used a `bool` and split `a1` ambiguously. Rewrote with an
   `enum State { Outside, InWord, InNumber }` scanner; the prompt now states the
   grammar explicitly, including that `a1` splits into `word:a` then `number:1`.
5. **068** — `quit` ignored extra args and the prompt said `set k v` is
   "三个参数". Lesson `code` now rejects `quit now` (expected 0 args) and only
   `quit` is accepted; output updated from a real run. The exercise prompt now
   says `set` needs **two arguments after the command name**; the answer rejects
   `del a b` too.

Targeted re-verify (10 s child timeouts, no Flutter, no staging): `_build.py` OK,
`_audit.py` all pass; lessons 55/57/62/64/68 compile+run (code and answer) with
0 failures and 068's code stdout matching `output`; 14-point alignment assertion
all PASS; diff vs HEAD touches exactly IDs 55/57/62/64/68 (frozen blessings
preserved).

## Cross-review fixes (round 6 — reviewer final-2 exact defects)

1. **057** answer — the prompt's blanket clause "当分数是整十时返回带（整十）后缀的等级"
   was not honoured for the F band: `0..=59` had no guard, so `bucket(0/10/50)`
   returned `"F"`. Added an `s @ 0..=59 if s % 10 == 0 => "F(整十)"` branch and
   `assert_eq!` for 0/10/50 (→ F(整十)) and non-round 55 (→ F).
2. **068** answer — `enum Command` only had `Set`/`Del` and `parse` had no `quit`
   handling, contradicting the prompt's "quit rejects extra args". Added
   `Command::Quit`, a `"quit"` arm that succeeds on zero args and returns
   `MissingArgs { expected: 0 }` on extras, and asserts for `quit`/
   `quit now` plus the set/del cases.

Targeted re-verify (10 s child timeouts): 057 and 068 compile+run (code and
answer) with 0 failures; 068's code stdout equals `output`; 6-point field
assertion all PASS; diff vs HEAD within this round changes only IDs 57 and 68
against the round-5 state (55/62/64 accepted, untouched).

## Validation performed locally (real compiler)

`native/build/miri-windows/compiler/bin/rustc.exe` 1.98.1 was used:

- `_build.py` — assembles the five domain modules into the owned JSON, sorts by
  id, applies the main.rs==code rule and checks schema gaps/dup exercices.
- `_validate.py` — compiles+runs every `code` and `exercise.answer` with fixed
  argv `rustc --edition 2021 <file> -o <tmp>` plus GNU linking flags
  (`-C linker-flavor=ld.lld -C linker=<...>/rust-lld.exe -C link-self-contained=yes`),
  diffs stdout against `output`; materializes each `files` project and runs
  `cargo --offline run|build|test` with the same `RUSTFLAGS`. Result:
  **175/175 checks pass, 0 failures** (84 code + 84 answer + 7 projects).
- `_audit.py` — schema, uniqueness (title/explain/code/output/summary/exercise
  prompt), non-empty required fields, `fn main` presence, filler-marker ban,
  main.rs==code, projectOutput/verify presence. Result: **all pass**.

The `_*.py` scripts are scratch authoring/validation aids. They are kept in the
working tree for the coordinator to re-run but MUST NOT be staged for commit.

## Coverage

| Domain range | Domain | Count |
| --- | --- | --- |
| 001–014 | toolchain-cargo | 14 |
| 015–032 | syntax-types | 18 |
| 033–052 | ownership-borrowing | 20 |
| 053–068 | data-modeling | 16 |
| 069–084 | traits-generics | 16 |

Levels: 30 beginner / 30 intermediate / 24 advanced. Runtimes: 77 desktop +
7 cargo (IDs 5, 6, 7, 9, 12, 13, 14; all carry a `files` project with
`src/main.rs == code` and a `projectOutput`). Lesson 1 legitimately has an empty
`prerequisites` array (it is the first lesson).
