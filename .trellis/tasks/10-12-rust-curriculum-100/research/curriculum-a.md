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
