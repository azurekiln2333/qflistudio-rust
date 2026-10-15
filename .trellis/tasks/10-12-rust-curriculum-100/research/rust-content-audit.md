# Rust content audit (2026-10-12, read-only)

## What ships today

The Rust app uses `qfli_studio_core`. Rust content is not a separate file; it is
the `language == "rust"` slice of the shared aggregate assets:

- `../qfli_studio_core/assets/content/tutorials.json` (1620 entries total)
- `../qfli_studio_core/assets/content/examples.json` (1620 entries total)

There is **no** `assets/tutorials/rust.json` (the legacy per-language loader in
`lib/services/tutorial_service.dart` bundles c/cpp/web/python/java/dart/lua only).

## Measured deficiency (rust slice)

| Metric | Tutorials | Examples |
| --- | --- | --- |
| entries | 100 | 100 |
| distinct titles | 100 (a 24-topic list cycled 4×) | 100 |
| distinct `summary` | 24 | 24 |
| distinct lesson `explain` | **1** (byte-identical ×100) | n/a |
| distinct lesson `code` | 100, **all single-line** | 100, all single-line |
| distinct example `concepts` sets | 24 | 24 |
| distinct exercise prompt | **1** | n/a |
| lessons with `objective` | 0 | n/a |
| lessons with `pitfalls` | 0 | n/a |

Representative filler code (identical shape across entries):
`fn main() { let values = [1, 3, 5]; let weighted: i32 = ...; println!("weighted={weighted}"); }`
with the same generic `explain` and the same weights/data-pipeline exercise text.

Conclusion: the Rust curriculum is generated template padding and does not teach
Rust. It must be replaced wholesale.

## Delivery-path evidence (why Rust-local works)

- `lib/pages/home_page.dart:217,227` build `LocalTutorialsTab` / `ExampleCodeTab`.
- Both receive `repository: StudioProfile.current?.contentRepositoryFactory?.call()`
  (`home_page.dart:222,233`).
- `lib/services/studio_profile.dart:100,175` define `contentRepositoryFactory`
  (`ContentRepository Function()?`); the Rust profile never sets it.
- `lib/pages/local_content_pages.dart:22,100` accept an optional repository and
  fall back to `AssetContentRepository()` only when null.
- `ContentCatalog` / `ContentFilter` / `ContentRepository` are public imports;
  `test/rust_content_pages_test.dart` already imports
  `package:qfli_studio_core/content/content_repository.dart`.

Therefore the Rust repo can set `contentRepositoryFactory` and ship its own
assets + repository with **no shared-core edits**.

## Schema capacity already present

`TutorialLessonContent` (`lib/content/content_repository.dart:142`) already
exposes `objective`, `prerequisites`, `pitfalls`; the Rust content leaves them
empty. Populating them needs no model change and is verified to parse.

## Integration pattern to reuse

`tool/generate_python_content.dart` + `tool/verify_python_content.dart` establish:
authored topic list as source of truth, generator that writes only that
language's rows, `.last_run.json` manifest, and a verifier that cross-checks
authored vs emitted and runs samples (reporting skipped separately). Rust mirrors
this but writes self-contained Rust-local assets to avoid conflicts with
concurrent language agents.

## Boundary

Sibling repos are concurrently authoring other languages and may edit
`qfli_studio_core`. This task therefore reads core only and ships Rust-local
content/assets/repository; it will not edit shared core unless a minimal change
is proven necessary and reported for coordination.
