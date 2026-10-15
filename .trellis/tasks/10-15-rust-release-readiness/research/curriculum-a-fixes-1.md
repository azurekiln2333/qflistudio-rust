# Curriculum A — round-6 exact-defect report (freeze candidate)

Agent: rust-curriculum-a. Working dir: D:/MyNewProjects/qfli_rust.

## Owned artifact + FINAL blob hash

- `tool/rust_content/topics_001_084.json`
- **FINAL git worktree blob hash: `abd15ee20fa7a290f13fd112e8b1ab78c345755b`**
- `git diff --numstat` vs HEAD (`dc2becf`): 10 insertions / 10 deletions.
- Only lesson IDs changed within this round: **57 and 68**. IDs 55/62/64 keep the
  already-accepted round-5 content; no other IDs touched.

No Flutter run, no Git staging/commit (root owns).

## Reviewer final-2 exact defects fixed

1. **057 exercise answer** — the prompt requires whole tens (including the F band)
   to carry a "(整十)" suffix, but `0..=59` had no guard, so `bucket(0)`,
   `bucket(10)`, `bucket(50)` returned `"F"`. Added an
   `s @ 0..=59 if s % 10 == 0 => "F(整十)"` branch (guards + `@` both used), and
   `assert_eq!` covering `bucket(0)/bucket(10)/bucket(50)` → `"F(整十)"` and the
   non-round `bucket(55)` → `"F"`.

2. **068 exercise answer** — `enum Command` had only `Set`/`Del` and `parse` had
   no `quit` arm, contradicting the prompt ("quit must reject extra args").
   Added `Command::Quit` plus a `"quit"` arm: zero args → `Ok(Command::Quit)`;
   extra args → `Err(ParseError::MissingArgs { command: "quit", expected: 0, got })`.
   Added asserts for `quit`, `quit now`, and the set/del legal+illegal cases.

Both changes are in the **answer field (actual code)**, not explain-only.

## Targeted self-verify (real rustc, 10 s child timeouts)

- `_build.py`: 84 lessons, ids 1..84 — OK.
- `_audit.py`: all convention/integrity checks pass.
- Real compile+run of lessons 57 and 68 (`code` and `exercise.answer`) with 10 s
  timeouts: **0 failures**; 068's `code` stdout equals `output` exactly.
- 6-point field assertion: 057 has the F(整十) branch + 0/10/50/55 asserts; 068
  has `Command::Quit`, zero-arg success, and extra-arg rejection — **all PASS**.
- `git diff` within this round touches only IDs 57 and 68 (vs round-5 state).

## Request

Commit ONLY:
- `tool/rust_content/topics_001_084.json`
- `.trellis/tasks/10-12-rust-curriculum-100/research/curriculum-a.md`

Suggested message: `fix(content): complete 057 whole-ten buckets and 068 quit arity`

**FREEZE**: no further edits unless a new defect is reported.
