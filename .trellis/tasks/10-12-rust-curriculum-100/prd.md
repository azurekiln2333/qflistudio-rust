# Replace placeholder Rust tutorials with 100+ complete lessons and examples

## Goal

Replace the Rust curriculum shipped in the shared content catalog with **166
substantive, original Rust lessons and 166 matching runnable examples**, ordered
beginner → expert, delivered from the `qfli_rust` repository and reachable
through the existing in-app tutorial / example navigation and code-import flow.

## Background

The Rust profile uses the shared `qfli_studio_core` package. Its content is the
`language == "rust"` slice of the aggregate assets
`../qfli_studio_core/assets/content/{tutorials,examples}.json`. That slice
currently has 100 tutorials and 100 examples that are template filler, measured
2026-10-12 (details in `research/rust-content-audit.md`): 1 distinct lesson
`explain`, 1 distinct exercise prompt, 0 objectives, 0 pitfalls, and all lesson
code single-line, with a 24-topic title list cycled 4×. It must be replaced
wholesale.

## Requirements

- **R1 Volume**: 166 distinct lessons and 166 matching examples, unique IDs and
  titles, no repeated template prose.
- **R2 Substance**: every lesson has an objective, prerequisites, a real concept
  explanation, complete runnable multi-line code, an expected result, topic
  pitfalls, and an exercise with a solution. `println!`-only or single-line
  filler is forbidden.
- **R3 Coverage**: toolchain/Cargo, syntax, ownership/borrowing/lifetimes,
  structs/enums/patterns, traits/generics, collections/iterators/closures,
  errors/modules/testing, smart pointers, threads/channels/locks/`Send`+`Sync`,
  async/`Future` (incl. `Pin`/`Poll`, executor, cancellation), macros
  (declarative + proc-macro concepts), `unsafe`/FFI, atomics/memory ordering,
  performance, and three multi-file capstones.
- **R4 Honest runtime labels**: each example declares what actually runs it
  (desktop `rustc`, `cargo`, unverified embedded candidate, or needs-external
  toolchain/dependency). No example is labeled supported without device/engine
  evidence; absence of crates alone does not imply embedded support.
- **R5 Integration**: existing content IDs, paths, navigation and the
  code-import capability are preserved; no navigation regression.
- **R6 Consistency**: Chinese explanations and the project's lesson schema
  conventions are respected; no fabricated verification.
- **R7 Rust-local delivery**: content, assets and tooling live in `qfli_rust`;
  shared core is not edited (if ever technically required, it is specified for
  coordination, not applied).

## Acceptance Criteria

- [x] AC1 (R1): Rust catalog has 166 tutorials and 166 examples; distinct
      title/code/summary/explain counts equal the entry counts.
- [x] AC2 (R2): zero lessons missing objective/prerequisites/explain/pitfalls or
      with single-line code; zero duplicated explain or exercise text.
- [x] AC3 (R3): all listed domains covered; verifier emits a domain→lesson-ID
      coverage table with no gap over IDs 001..166.
- [x] AC4 (R4): a runtime-label report accounts for every example, and every
      label matches what the available toolchain/engine can actually do;
      `miri-candidate` entries stay unverified until engine evidence exists.
- [x] AC5 (R5): `rust_content_pages_test.dart` passes at 390px/1280px for both
      tabs, and import from a lesson and from an example produces the expected
      files and Cargo configuration.
- [x] AC6 (R6): the content validator reports no issues for the Rust entries and
      no placeholder markers remain.
- [x] AC7 (R7): the diff is confined to `qfli_rust` plus task artifacts; shared
      core is untouched.
- [x] AC8 Import scope is honest: single-file import works on all import
      branches; multi-file (`cargo-multi`) examples import only through the
      example "import to project → create project" branch, and lessons retain a
      working single-file counterpart. This limitation is documented and tested,
      not implied to be broader.
- [x] AC9 Where a real toolchain exists, samples compile/run and their declared
      output matches; where it does not, those checks are reported as **skipped**,
      never as passed, and a run whose compile checks are all skipped is not
      reported as fully verified.
