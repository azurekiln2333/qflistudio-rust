# Plan summary — Rust curriculum (planning only)

## Final count
**166 lessons + 166 matching examples** (IDs `rust-tutorial-001..166` /
`rust-example-001..166`), 12 domains, beginner→expert. Expanded well past 120 so
async/`Future` (incl. `Pin`/`Poll`, executor, cancellation), macros
(declarative + proc-macro), `unsafe`/FFI, atomics/memory ordering, performance
and three multi-file capstones each get independent lessons.

## Current state (evidence: research/rust-content-audit.md)
Rust ships 100+100 template-filler entries: 1 distinct `explain`, 1 distinct
exercise prompt, 0 objectives, 0 pitfalls, all single-line code.

## Scope / integration
- Rust-local only: authored topics → generator → `assets/content_rust/*.json`,
  loaded by a new `RustContentRepository` injected via the **already supported**
  `StudioProfile.contentRepositoryFactory` (consumed by `HomePage`). Only
  non-content change: one field in `lib/main.dart`. **No shared-core edit.**
- IDs `001..100` preserved, `101..166` added (no rename, no gap) — see design §9.
- Import (traced, not assumed): single-file works on all three branches; the
  `cargo-multi` bundle imports **only** through the example "import to project →
  create project" branch (`RustProjectStore.createProjectFromExample`), because
  the shared lesson path (`ExampleCode`) has no fixtures/multi-file field.
  Lessons keep a working single-file counterpart; bundles are path-validated and
  never overwrite existing files.

## Key verification limits
- No `rustc`/`cargo` on PATH, in WSL, or in standard locations (2026-10-12);
  discovery + optional workspace-local toolchain plan in
  `research/toolchain-discovery.md`. Real compile/run is expected **skipped**
  unless a toolchain is provisioned; skips are never counted as passes and an
  all-skipped run is not reported as fully verified.
- `miri-candidate` examples are not labeled supported without device/engine
  evidence.
- Verifier uses fixed `rustc`/`cargo` argv, never a bundle `verify` string.

## Artifacts
`prd.md`, `design.md`, `implement.md`, `implement.jsonl`, `check.jsonl`,
`research/{rust-content-audit,source-evidence,curriculum-index,import-representation,toolchain-discovery,verification-plan,plan-summary}.md`.

## Status
Planning complete and self-reviewed; no product content/code written, no
`task.py start`, no commit. **Ready for your final review.** Awaiting explicit
implementation authorization.
