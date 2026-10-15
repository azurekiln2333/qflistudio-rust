# Design and ownership

Reuse qfli_studio_core StudioProfile seams: isOffline/ offlineOnly,
terminalCommandDelegate, contentRepositoryFactory and ProgramRunner. Do not
fork shared widgets or edit sibling products. Rust currently omits the terminal
delegate and a local content repository, so those are the likely Rust gaps.

## Parallel work

- Herdr wB:p2: author tool/rust_content/topics_001_084.json only (IDs 1..84).
- Herdr wB:p3: author tool/rust_content/topics_085_166.json only (IDs 85..166).
- Herdr wB:p4: Rust terminal delegate, runner completeness/offline audit,
  corresponding tests and research report; no main.dart/pubspec.yaml edits.
- Native Trellis implement agent: content generator/verifier, repository,
  content/import tests and necessary RustProjectStore support, excluding topic
  author JSON, main.dart and pubspec.yaml.
- Coordinator: main.dart/pubspec.yaml integration, native/build review, task
  records, specs, final verification and scoped commits.

## Content contract

Each authored JSON file is an array of objects with integer id, title, level
(beginner/intermediate/advanced), domain, summary, concepts (string array),
objective, prerequisites (string array), explain, code (complete single-file
Rust), output (exact stdout), pitfalls (string array), exercise (prompt/hint/
answer), runtime (desktop/cargo/miri-candidate/external). Optional files is a map
of relative project paths to source strings for a paired full Cargo project;
optional verify is run/build/test. Every lesson retains a runnable single-file
counterpart. Full-project support must follow the actual shared import data flow,
not assume ExampleCode preserves inputFixtures. Preserve IDs 001..100; extend
through 166. Use the previous curriculum index as the topic inventory.

Generated Rust-local assets override the placeholder Rust shared catalog using
ContentRepository. Other language catalogs and user data are untouched. The
generator/verifier must check authored and generated data and fail on gaps,
duplicates, filler, compile/run errors or output mismatch. No invented pass for
an unavailable compiler. Runtime support claims need actual engine evidence.

## Validation boundary

Build infrastructure may download host/build dependencies; shipped app offline
policy restricts user-facing network features. Target/device toolchain packaging
is audited separately from desktop rustc sample compilation and Flutter tests.
