# Curriculum A — round-4 completion report (FINAL, freeze)

Agent: rust-curriculum-a. Working dir: D:/MyNewProjects/qfli_rust.

## Owned artifact + FINAL blob hash

- `tool/rust_content/topics_001_084.json`
- **FINAL git worktree blob hash: `c193d466d69c39e770689a97e74df676b54c3032`**
- `git diff --numstat` vs HEAD: 42 insertions / 41 deletions (rounds 1–4)

No staging / no commit (root owns). No shared-core, main.dart, pubspec.yaml,
branch switch, or sibling repo touched. `tool/rust_content/` now contains only
the two JSON files (`topics_001_084.json` mine, `topics_085_166.json` sibling's).

## What round 4 had missed, now fixed

1. **079 MAIN `code`** (the real bug) — it still had `struct UserId(u64)` and
   `impl From<&str> for UserId { UserId(value.len() as u64) }`, printing
   `id = UserId(4)`, contradicting the corrected lossless text. Replaced with a
   genuinely lossless `struct UserId(String)`:
   - `impl From<String> for UserId` and `impl From<&str> for UserId` preserve the
     entire text (no `len()`, no truncation);
   - `assert_eq!`/`assert_ne!` prove the round-trip and that two **same-length,
     different-text** ids (`"abcd"` vs `"wxyz"`) remain distinct;
   - `Percentage` keeps the `TryFrom<i64>` range-validated conversion;
   - `output` recomputed from a real run (no more `UserId(4)`).
   079 is `desktop`, so there is no bundled `src/main.rs` to mirror.

2. **081 exercise `answer` comment** — deleted the wrong line
   "PartialEq 必须是等价关系：自反、对称、传递。" It now reads the correct
   contract: PartialEq requires **symmetry + transitivity** (reflexivity is
   `Eq`'s additional requirement), with the `to_bits` bit-equality choice noted.

3. **048 explain first sentence** — now clarifies `set`/`replace`/`into_inner`
   work for any `T`, **`take` requires `T: Default`** (leaves `T::default()`),
   and only `get` requires `T: Copy`.

## Targeted self-verify (real compiler; no full-84 rerun, per instruction)

- `_build.py`: 84 lessons, ids 1..84 — OK.
- `_audit.py`: schema / uniqueness / filler ban / `files['src/main.rs']==code` /
  projectOutput / verify — all pass.
- 10-point assertion for 048/079/081 (fields, not just explain) — **all PASS**.
- Real compile+run of lessons 48, 79, 81 (`code` and `exercise.answer`) — **0
  failures**; 079 `code` stdout equals `output` exactly.
- Earlier round 1–3 fixes re-checked present — all True.

## Scratch helpers relocated (no deletions of other files)

Moved all authoring/validation helpers from `tool/rust_content/` to
`build/content-author-scratch/`:
`_a1/_a2/_b1/_b2/_c1/_c2/_c3/_d1/_d2/_e1/_e2.py`, `_build.py`, `_validate.py`,
`_audit.py`, `_fixquotes.py`, `_patch_r4b.py`, `_check_r4b.py`,
`_check_r4b_run.py`, `_scratch079.rs/.exe`.

`build/content-author-scratch/` is **gitignored** (`**/build/`) and inside the
Rust repo. `_build.py`/`_validate.py`/`_audit.py` were repointed to read/write the
canonical `tool/rust_content/topics_001_084.json`. `topics_085_166.json` was not
touched.

## Request

Commit ONLY:
- `tool/rust_content/topics_001_084.json`
- `.trellis/tasks/10-12-rust-curriculum-100/research/curriculum-a.md`

Suggested message: `fix(content): correct lessons 006/012/015/048/049/079/081 and earlier review findings`

**FREEZE**: this content is frozen pending root review; I will make no further
edits unless a new defect is reported.
