# Curriculum A report — topics_001_084.json (IDs 1..84)

Agent: rust-curriculum-a (Herdr wB). Working dir: D:/MyNewProjects/qfli_rust.

## Deliverable (staged for commit)

- `tool/rust_content/topics_001_084.json` — JSON array, 84 lesson objects,
  IDs 1..84 contiguous/unique, 303 KB.
- `.trellis/tasks/10-12-rust-curriculum-100/research/curriculum-a.md` —
  authoring/coverage/validation note.

Exclusive scope respected: no shared-core edits, no `main.dart`/`pubspec.yaml`,
no branch switch, no sibling repo touched. All commits by the coordinator.

## Content contract

Every lesson has id (int), title, level, domain, summary, concepts[], objective,
prerequisites[], explain, code (complete single-file Rust), output (exact
stdout), pitfalls[], exercise{prompt,hint,answer (complete compilable program)},
runtime. 7 lessons (IDs 5, 6, 7, 9, 12, 13, 14) are `cargo` and add `files`
(a real Cargo project) + `projectOutput` + `verify`.

Final import convention honored:
- all `code` are standalone single-file programs (`rustc --edition 2021`);
- `files['src/main.rs'] == code` byte-for-byte for every project lesson;
- extra files (build.rs, src/bin, tests/, workspace crates) add real structure;
  the single-file detail body never depends on an absent file;
- no network deps (`--offline`, std or local `path` only);
- 007 is now root `[package] + [workspace]` with `default-members = ["."]` so
  `cargo run` is unique and stdout == `output`; child crates still demonstrate a
  real workspace.

## Coverage

| Range | Domain | Count |
| --- | --- | --- |
| 001–014 | toolchain-cargo | 14 |
| 015–032 | syntax-types | 18 |
| 033–052 | ownership-borrowing | 20 |
| 053–068 | data-modeling | 16 |
| 069–084 | traits-generics | 16 |

Levels: 30 beginner / 30 intermediate / 24 advanced.
Runtimes: 77 desktop / 7 cargo. No miri-candidate or external in this range.

## Real-compiler validation (self-run, NOT skipped)

Toolchain: `native/build/miri-windows/compiler/bin/rustc.exe` 1.98.1 (GNU).
Linking flags used for every compile (Windows GNU has no system gcc/ld):
`-C linker-flavor=ld.lld -C linker=<...>/rustlib/x86_64-pc-windows-gnu/bin/rust-lld.exe
-C link-self-contained=yes`; cargo run with `--offline` and the same `RUSTFLAGS`.

- code blocks: 84/84 compile + stdout == `output`.
- exercise answers: 84/84 compile + run.
- Cargo projects (ver = run/build/test): 7/7 succeed, stdout == `projectOutput`.
- TOTAL: 175/175 checks pass, 0 compile/run/output/project errors.

Integrity audit: no duplicate title/explain/code/output/summary/exercise prompt;
no filler markers (TODO/unimplemented!/placeholder/weighted=/数据建模与不变量);
every code and answer contains `fn main`; all required fields non-empty;
`files['src/main.rs'] == code` for all 7 project lessons. All pass.

## Request

Please commit, explicitly staging only:
- `tool/rust_content/topics_001_084.json`
- `.trellis/tasks/10-12-rust-curriculum-100/research/curriculum-a.md`

Do NOT commit the scratch helpers under `tool/rust_content/_*.py`
(`_build.py`, `_validate.py`, `_audit.py`, `_a1/_a2/_b1/_b2/_c1/_c2/_c3/_d1/_d2/_e1/_e2.py`).
They are authoring aids kept in the working tree for the coordinator's final
`verify` tool; they are not staging candidates.

Suggested message: `feat(content): author Rust lessons 001-084 with verified examples`
