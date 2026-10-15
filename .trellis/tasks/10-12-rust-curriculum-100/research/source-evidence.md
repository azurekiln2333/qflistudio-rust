# Source evidence (read-only anchors)

Code anchors inspected 2026-10-12. Recorded here so the JSONL context manifests
can reference research docs instead of raw source paths.

## Content model and loader (shared core)

- `lib/content/content_repository.dart`
  - `ContentCatalog.fromJson({tutorialsSource, examplesSource})` parses the
    aggregate `{entries:[...]}` docs.
  - `TutorialLessonContent` exposes `objective`, `prerequisites`, `pitfalls`
    (already supported; Rust content leaves them empty today).
  - `ExampleContent` exposes `code`, `expectedOutput`, `inputFixtures`
    (`Map<String,String>`), `templateType`, `sourceLessonId`.
  - `ContentRepository` interface: `load/tutorials/examples`.
- `lib/content/asset_content_repository.dart`
  - asset keys `assets/content/tutorials.json` and `assets/content/examples.json`
    (and `packages/qfli_studio_core/...`) — the current Rust source of content.
- `lib/content/content_validator.dart`
  - release minimum 100 per type; checks id/language/type/locale/level/title/
    summary/source/license/updatedAt/concepts + lesson id/title/summary/explain/
    code/output/concepts + duplicate-id detection.

## Content pages and profiles

- `lib/pages/home_page.dart` builds `LocalTutorialsTab` / `ExampleCodeTab` with
  `repository: StudioProfile.current?.contentRepositoryFactory?.call()`.
- `lib/services/studio_profile.dart` defines `contentRepositoryFactory`
  (`ContentRepository Function()?`); Rust profile leaves it null.
- `lib/pages/local_content_pages.dart`
  - `LocalTutorialsTab` / `ExampleCodeTab` accept an optional repository.
  - `_LessonPage` builds `ExampleCode(code: lesson.code, ...)` and renders
    objective/prerequisites/pitfalls when non-empty.

## Import path (shared core)

- `lib/widgets/code_snippet.dart` — two buttons → `_import(intoProject:)` →
  `_CodeImportDialog._submit()` with three branches (openInEditor+addExisting /
  importIntoProject / createProjectFromExample).
- `lib/services/code_import_service.dart` — `resolveImport` returns one
  `(fileName, code)`; `openInEditor` and `importIntoProject` write exactly one
  file; no multi-file support.
- `lib/models/tutorial.dart` — `ExampleCode` has no fixtures/multi-file fields;
  `TutorialLesson` likewise.

## Rust product (this repo)

- `lib/rust_project_store.dart` — `RustProjectStore.createProjectFromExample`
  adds `Cargo.toml` (+ explicit `[[bin]]` for non-`src/main.rs` entries) and
  `.gitignore` after the shared write; `addExisting` is untouched.
- `lib/main.dart` — `rustProfile` (entry `main.rs`/`src/main.rs`, `.rs` only,
  offline) and no `contentRepositoryFactory`.
- `lib/rust_runner.dart` — Cargo routing matches `cargo metadata` `src_path`
  (task 10-09), so a custom `[[bin]]` path resolves to the right target.

## Established generator pattern (shared core tool/)

- `tool/generate_python_content.dart` / `tool/verify_python_content.dart` —
  authored topic source of truth, generator writing only that language's rows,
  `.last_run.json` manifest, verifier cross-checking authored vs emitted and
  running samples (skips reported separately). Rust mirrors this, writing
  Rust-local assets instead of shared rows.
