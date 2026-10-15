# Design — Rust curriculum, Rust-local delivery

## 1. Boundary

Product content and tooling live in the `qfli_rust` repository. The shared
package `../qfli_studio_core` is consumed read-only. Other agents are editing
shared core concurrently, so this task must not depend on their uncommitted
edits and must not add competing edits to the same files.

Delivered inside `qfli_rust`:

- authored curriculum source of truth (Dart data files)
- a generator that writes the Rust catalog assets
- a verifier that checks integrity, uniqueness, non-triviality and runtime labels
- a Rust-local `ContentRepository` that loads those assets
- wiring of that repository through the already-supported
  `StudioProfile.contentRepositoryFactory`

## 2. Why Rust-local is sufficient (evidence)

- `HomePage` builds the local content tabs with
  `repository: StudioProfile.current?.contentRepositoryFactory?.call()`
  (`lib/pages/home_page.dart:222,233`). The Rust profile currently leaves the
  factory null, so it silently falls back to `AssetContentRepository()`.
- `LocalTutorialsTab` / `ExampleCodeTab` accept an optional `ContentRepository`
  (`lib/pages/local_content_pages.dart:22,100`) and default to
  `AssetContentRepository()` only when none is supplied.
- `ContentCatalog`, `ContentFilter`, `TutorialContent`, `ExampleContent`,
  `ContentRepository`, `TutorialLessonContent` are public import paths; the Rust
  test `test/rust_content_pages_test.dart` already imports
  `package:qfli_studio_core/content/content_repository.dart`.
- The lesson schema already carries `objective`, `prerequisites`, `pitfalls`
  (`lib/content/content_repository.dart:142-175`), so no model change is needed.

Conclusion: **no shared-core edit is technically required.** Setting the Rust
profile's `contentRepositoryFactory` is a `qfli_rust/lib/main.dart` change.

## 3. Components and data flow

```
tool/rust_content/rust_topic.dart        authored topic model (data only)
tool/rust_content/topics_*.dart          authored curriculum (166 topics)
        |
        v  dart run tool/generate_rust_content.dart
assets/content_rust/tutorials.json       Rust tutorials (166 entries)
assets/content_rust/examples.json        Rust examples (166 entries)
tool/rust_content/.last_run.json         generation manifest + runtime tally
        |
        v  loaded at runtime by
lib/rust_content_repository.dart         implements ContentRepository
        |
        v  injected via
lib/main.dart  rustProfile.contentRepositoryFactory: RustContentRepository.new
        |
        v  consumed by shared (unchanged)
HomePage -> LocalTutorialsTab / ExampleCodeTab -> CodeSnippet -> CodeImportService
```

The generator writes self-contained Rust assets rather than editing the shared
aggregate `../qfli_studio_core/assets/content/*.json`, so concurrent language
agents cannot conflict and the Rust content always wins for the Rust product.

## 4. Contracts

### 4.1 Authored topic model (`RustTopic`)

Mirrors `tool/python_content/python_topic.dart`:

- `id` (1..N, stable, no gaps), `level` (`beginner|intermediate|advanced`),
  `title`, `summary`, `concepts`, `objective`, `prerequisites`, `explain`,
  `code`, `output`, `pitfalls`, `tasks`, `runtime`, optional `input`.
- `runtime` is one of:
  - `desktop` — compiles/runs with a real desktop `rustc`/`cargo`.
  - `cargo` — needs a Cargo project and possibly crates.io dependencies.
  - `embedded` — runs on the packaged Miri engine (no external crates).
  - `external` — requires an absent toolchain/native dependency; taught but
    explicitly labeled, never run in CI here.
- IDs: `rust-tutorial-NNN` / `rust-example-NNN` (3-digit, stable, must not
  collide with the shared aggregate IDs already in use).

### 4.2 Emitted JSON (Rust-local assets)

Same shape as the shared aggregate entries (so the shared model parses them
unchanged):

```
{ "schemaVersion": 2, "kind": "tutorials", "updatedAt": "...",
  "entries": [ { id, language:"rust", type:"rust", locale:"zh-CN", level,
                 title, summary, concepts, source, license, updatedAt,
                 lessons: [ { id, title, summary, concepts, objective,
                              prerequisites, explain, code, output, pitfalls,
                              exercises:[{prompt,hint,answer}] } ] } ] }
```

Examples: same entry fields plus `code`, `expectedOutput`, `inputFixtures`,
`templateType:"rust"`, `sourceLessonId`. The runtime label is carried in
`concepts` (e.g. `内置运行` / `需要桌面 Rust 工具链` / `需要 Cargo 依赖`) so the
UI and verifier can both see it without a schema change.

### 4.3 Repository (`RustContentRepository`)

- `load()` reads the two Rust-local assets via `rootBundle` using the tolerant
  key strategy (`assets/content_rust/...` and
  `packages/qfli_rust/assets/content_rust/...`), then
  `ContentCatalog.fromJson(tutorialsSource:, examplesSource:)`.
- `tutorials()` / `examples()` apply the supplied `ContentFilter` exactly like
  `AssetContentRepository`.
- Caches the parsed catalog; returns an actionable error object rather than
  crashing the page when assets are missing.

### 4.4 Wiring

`lib/main.dart`: add `contentRepositoryFactory: RustContentRepository.new` to
`rustProfile`. This is the only non-content product change.

## 5. Generator / verifier design

- `tool/generate_rust_content.dart`:
  - validates the authored list (166, unique id/title/code, id order 1..166,
    multi-line code, no `weighted=` filler, non-empty objective/pitfalls);
  - emits `assets/content_rust/{tutorials,examples}.json` and
    `tool/rust_content/.last_run.json` (counts per runtime + per domain);
  - never reads or writes any shared-core file.
- `tool/verify_rust_content.dart`:
  - re-parses the emitted assets and cross-checks every authored topic against
    its tutorial + example record (code, output, ids, objective, pitfalls);
  - asserts distinct counts, duplication, single-line and placeholder checks;
  - builds a topic-domain coverage table and a runtime-label tally;
  - where `rustc`/`cargo` exist, compiles/runs `desktop`/`cargo` samples and
    diffs `expectedOutput`; where they do not, records them as **skipped** with
    the reason, never as passed.

## 6. Curriculum inventory (166 lessons, 12 domains)

The exact, authoritative inventory is `research/curriculum-index.md`: **one row
per lesson ID/title, prerequisite, paired example ID, runtime label and import
representation**. Summary:

IDs `rust-tutorial-001..166`; each pairs 1:1 with `rust-example-001..166`.

| Range | Domain | Level |
| --- | --- | --- |
| 001–014 | Toolchain, Cargo, first programs | beginner |
| 015–032 | Syntax, types, control flow | beginner |
| 033–052 | Ownership, borrowing, lifetimes | beginner→intermediate |
| 053–068 | Structs, enums, pattern matching | intermediate |
| 069–084 | Traits, generics, trait objects | intermediate |
| 085–098 | Collections, iterators, closures | intermediate |
| 099–112 | Errors, modules, crates, testing | intermediate |
| 113–124 | Smart pointers, interior mutability | advanced |
| 125–137 | Concurrency: threads, channels, `Send`+`Sync` | advanced |
| 138–146 | Async / `Future` (incl. `Pin`/`Poll`, executor, cancellation) | advanced→expert |
| 147–152 | Macros (declarative + proc-macro/derive concepts) | advanced→expert |
| 153–166 | `unsafe`/FFI, performance, three multi-file capstones | expert |

166 exceeds the 120 minimum specifically so async/`Future`, macros,
`unsafe`/FFI, performance and the capstones each get independent lessons rather
than sharing six final slots. Progression per domain: concept → worked example →
pitfall → exercise with solution.

## 7. Import representation (traced, not assumed)

Full trace and pinned schema: `research/import-representation.md`. Summary of
what the existing code actually allows:

- The two `CodeSnippet` buttons both call `_import(intoProject:)` →
  `_CodeImportDialog._submit()` with three branches: `openInEditor`+`addExisting`
  (editor), `importIntoProject` (existing project), and
  `store.createProjectFromExample` (**create project**).
- `openInEditor`/`importIntoProject` write exactly one file; only the
  **create-project** branch reaches `RustProjectStore.createProjectFromExample`.
- `_LessonPage` builds `ExampleCode(code: lesson.code, ...)`; `ExampleCode` has
  no fixtures/multi-file field. Therefore a **lesson can only import a single
  file**, and this is a hard shared-core limit we do not edit.

Representations:

- `single` — one `.rs` in `code`; works on all three branches. Used by every
  lesson and by the large majority of examples.
- `cargo-multi` / `external` — **example create-project branch only**: `code` is
  the entry `.rs`; additional files + pinned `Cargo.toml` ride in the example's
  already-serialized `ExampleContent.inputFixtures['cargoFiles']` JSON map and
  are expanded by `RustProjectStore.createProjectFromExample` after the shared
  write. Lessons whose topic needs multiple files keep a working single-file
  `code` and point to the paired example for the full project.
- Bundle writes are validated (relative, in-project, no `..`/absolute/control
  chars, no overwrite of existing files, size/count caps) before any write.
- The verifier never runs a bundle `verify` string as a shell command; `verify`
  is an enum token mapped to a fixed `rustc`/`cargo run|build|test` argv.

## 8. Runtime-label policy

Labels: `desktop` · `cargo` · `miri-candidate` · `external`.

- `desktop` — plain `rustc`, no crates. Runs when a real `rustc` exists.
- `cargo` — needs a manifest (and, for some lessons, crates.io); not claimed
  runnable without `cargo`.
- `miri-candidate` — std-only, **no crates**, so it *may* run on the packaged
  engine. It is **not** labeled supported merely because it lacks crates:
  `design` requires explicit device/engine evidence
  (`QFLI_MIRI_LIBRARY`/`QFLI_MIRI_SYSROOT` + a passing run) before the label is
  upgraded to supported. Until then the example keeps the neutral label and is
  recorded as unverified.
- `external` — needs an absent toolchain/native dependency (libc, tokio,
  proc-macro crates); taught, explicitly labeled, never claimed run here.

## 9. ID compatibility (replaces the previous contradictory rule)

The shared aggregate already uses `rust-tutorial-001..100` /
`rust-example-001..100` (contiguous, lesson ids `rust-tutorial-NNN-lesson`). The
new curriculum **preserves that ID space and extends it**:

- **Preserve**: for NNN `001..100`, the tutorial/example/lesson IDs keep their
  existing string values. No existing ID is renamed or removed, so any external
  reference or bookmark still resolves.
- **Extend**: `101..166` are new, contiguous, gap-free.
- **Rule**: the new content replaces the *bodies* at `001..100` and adds
  `101..166`; it never reuses an ID for an unrelated new topic, and the validator
  asserts ids form exactly `001..166` with no gap, no duplicate, and no ID that
  the shared aggregate does not already own (for ≤100) or that exceeds 166.

This resolves the earlier contradiction: there is no "must not collide with the
IDs being replaced" requirement — the replaced IDs are intentionally retained.

## 10. Compatibility and risks

- **Concurrent shared-core edits**: avoided by shipping Rust-local assets and
  using only the stable `contentRepositoryFactory` seam. No dependency on other
  agents' files.
- **Asset volume**: 240 rich entries as JSON is a few hundred KB; acceptable and
  loaded once via the cached repository.
- **Duplicate-ID collision**: Rust-local IDs live in their own assets and follow
  the preservation rule in §9; the validator asserts ids are exactly
  `001..166`, gap-free and duplicate-free.
- **Honest verification** (see `research/toolchain-discovery.md`): the machine has
  no `rustc`/`cargo` and no packaged engine, so real compile/run checks are
  expected to be skipped. This is recorded, never faked, and the task is **not**
  reported as fully verified while all compiler checks are skipped.
- **Rollback**: the change is additive (new files + one profile field). Reverting
  consists of removing the new assets/repository/wiring; the shared aggregate is
  never modified.
