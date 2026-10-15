# Tutorial And Example Imports

## 1. Scope And Trigger

The shared package `../qfli_studio_core` owns content models/pages, CodeSnippet,
project persistence and the editor. The Rust application owns its authored
catalog, RustContentRepository and RustProjectStore. Check these boundaries when
catalog assets, bundled projects or custom source names change. Keep shared-core
changes in their own authorized workspace; local content uses the shared schema.

## 2. Signatures

```dart
RustContentRepository({AssetBundle? bundle});
RustContentRepository.load(); // Future<ContentCatalog>
RustContentRepository.projectForExample(String id); // Future<RustExampleProject?>
RustExampleProject.fromJson(Object? value); // validates Map<String, String>
RustExampleProject.manifestForEntry(String entry, String fallbackPackage);
// String; throws FormatException for unsupported custom-entry manifests
CodeImportService.openInEditor({
  required ExampleCode example, required String fileName, String? location,
}); // Future<({Project project, String path})>
CodeImportService.importIntoProject({
  required Project project, required ExampleCode example,
  required String fileName, bool overwrite = false,
}); // same result type
ProjectStore.createProjectFromExample({
  required String name, required ExampleCode example,
  String? location, String? fileName,
}); // Future<ProjectResult>
```

```powershell
python scripts/generate_rust_content.py --check
python scripts/test_rust_content.py
python scripts/verify_rust_content.py --report <evidence.json>
```

## 3. Contracts

- Catalogs contain titles/summaries. CodeSnippet and import actions live in details.
- StudioProfile.contentRepositoryFactory supplies RustContentRepository. Its
  assets are `assets/content_rust/tutorials.json` and `examples.json`, registered
  in the root pubspec. Successful loads are cached; a failed load clears the
  cached future so retry can succeed. Do not fall back to shared sample catalogs.
- Author inputs are `tool/rust_content/topics_001_084.json` and
  `topics_085_166.json`. Generate both catalogs together. IDs are
  `rust-tutorial-NNN`, `rust-tutorial-NNN-lesson` and `rust-example-NNN` for
  001 through 166; examples link to their paired lesson IDs.
- Every visible code block and exercise answer is a complete standalone Rust
  program. Optional `files` maps include `Cargo.toml` and `src/main.rs`, and the
  latter matches `code`. The generator stores the map as the JSON string
  `ExampleContent.inputFixtures['cargoFiles']` using the shared catalog schema.
- Shared ExampleCode carries the editable source but drops inputFixtures.
  RustProjectStore resolves supplemental files by stable `rust-example-NNN` ID
  only when creating a new Rust project. Editor and existing-project imports
  continue to receive the complete standalone code. Noncatalog examples do not
  require an asset load.
- Import/copy/save read the editable controller's current source.
- Bundle installation skips its original `src/main.rs`: the shared store has
  already written the learner's current source to the selected entry. A catalog
  source must never overwrite that file.
- Imports return real filesystem paths. Successful navigation supplies that path
  as EditorPage.initialOpenPath using the existing store/auth/settings objects.
- Restore remembered tabs, then select initialOpenPath before the remembered tab.
- New projects configure the chosen source as ProjectConfig.entryFile and omit
  generated default source. Existing-project imports preserve the entry metadata.
- Editor imports persist a snippet and register it after successful writes;
  registration failures clean up the newly owned snippet directory.
- RustProjectStore must handle createProjectFromExample as well as createProject.
  Package names derived from display names must avoid Windows device basenames
  (`con`, `prn`, `aux`, `nul`, `com1`..`com9`, `lpt1`..`lpt9`) with a `rust_`
  prefix; Cargo otherwise accepts the name but cannot link its Windows binary.
  Keep the project display name unchanged and preserve valid package names.
  Custom Rust entries receive a project-relative Cargo `path`. Preserve the
  bundled package/bin name, `default-run` and integration-test binary identity;
  change a canonical `src/main.rs` bin path or append a bin with the package name.
  Reject ambiguous, implicit explicit-bin and aliased root paths during preflight.
- Bundled paths are nonempty relative POSIX paths; reject absolute/drive paths,
  backslashes, control/Windows-invalid characters, empty/dot/parent segments,
  `.qfli`, `.git` and `target` segments. Reject case-insensitive duplicates,
  conflicting directory case and paths used as both file and directory.
- Companion files are created exclusively inside the fresh project root. An I/O
  failure removes only this newly owned root, then calls shared deleteProject on
  the missing root to persist registry removal. A cleanup failure is surfaced
  with the remaining project; never report a successful import.
- Verification compiles/runs the exact authored main and answer sources and
  records their SHA256. Main stdout must match exactly, allowing CRLF conversion
  only; answer stdout is compared when exercise.output is supplied. Every Cargo
  bundle builds `--offline --workspace --all-targets` before its run/build/test
  operation. Cargo run uses projectOutput when supplied, otherwise output.
- Evidence records input-file SHA256, individual failures, timeouts and exit
  codes. Regenerate and rerun after author changes. `--structure-only` explicitly
  reports `compilerStatus: not_run`; host compilation does not prove mobile Miri
  execution. No environment key is required for normal catalog/import behavior.
- `QFLI_UI_SCREENSHOTS` is an optional verification-only output directory.

## 4. Validation And Error Matrix

| Condition | Result |
| --- | --- |
| Invalid/empty/reserved filename or path separators | invalidFileName before writes |
| Invalid bundled path or ambiguous custom-entry Cargo target | Format error before project creation |
| Custom filename matches a supplemental bundled file, ignoring case | Conflict error before project creation |
| Catalog asset read fails | Error propagates; next load retries |
| Unknown example ID or example without cargoFiles | Ordinary standalone project creation |
| Missing/cloud project or source directory outside project | projectUnavailable |
| Existing destination without replacement permission | fileExists; unchanged content |
| User declines replacement or cancels import | No write or editor navigation |
| Replacement approved | Backup succeeds before replacement |
| Write/registration failure | Localized error; no success navigation |
| Companion file I/O fails | Remove fresh root and registry entry; preserve existing projects |
| Compiler/Cargo missing, failed, timed out, or stdout mismatch | Verification failure with individual evidence |

## 5. Good, Base And Bad Cases

- Good: create a Rust example with `lesson.rs`; src/lesson.rs, project metadata
  and Cargo's bin path all point to the learner's current source. All attached
  local modules/tests are available and the bundled binary name still resolves.
- Base: import `helper.rs` into an existing project; open it while preserving the
  original entry and Cargo manifest.
- Bad: invalid names or rejected replacement must not mutate the registry/source.
- Bad: an unsafe bundle, colliding filename or unsupported custom-bin declaration
  must not create a project. A missing compiler must not yield a compiler pass.

## 6. Required Tests

Keep shared import regressions for exact current source on disk, real editor
selection, history precedence, cancellation, conflicts and persistence failures.
Root rust_content_repository_test.dart covers actual catalog pairing, filtering,
load caching/retry, bundle paths and manifest preflight. rust_project_store_test.dart
checks edited source preservation, complete bundles, custom-name Cargo metadata,
failure rollback and unchanged existing projects; build each actual bundled
project offline after a custom-name import. rust_content_pages_test.dart uses
the real catalog and checks details, current-source actions and mobile/desktop
bounds. Python contract tests cover malformed sources/bundles and failed or timed
out processes; the full verifier must compile/run every main/answer and build all
bundle targets against the current input hashes.

Flutter clears mock channel handlers between tests. Register asset mocks in
setUp and evict rootBundle's catalog strings for each test so cached futures from
a previous fake async zone cannot strand later loads. Render a frame after
scrolling and start navigation before advancing its animation clock.

## 7. Wrong And Correct

Wrong: override only createProject and assume example imports call that override.
Shared example creation currently uses its own internal creation path.

Correct: override createProjectFromExample in RustProjectStore and add Cargo
files after successful shared creation, preflighting the custom bin entry and
resolving its bundle through the repository. Keep addExisting and existing-project
imports free of manifest rewriting.

Wrong: recover bundled files from ExampleCode.inputFixtures, rewrite the learner's
entry from catalog code, or accept an old execution report after source changes.

Correct: resolve by stable catalog ID, skip the bundled entry during companion
installation, and regenerate/reverify current sources with hashes in the report.
