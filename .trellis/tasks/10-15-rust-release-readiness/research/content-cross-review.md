# Research: Rust content generator, verifier, repository, and import cross review

- Query: Find concrete failures in curriculum generation, per-item compilation/stdout verification, Rust-local repository loading, and safe Cargo-project import.
- Scope: internal, read-only review of `scripts/{generate_rust_content,verify_rust_content,test_rust_content}.py`, `lib/rust_content_repository.dart`, `lib/rust_project_store.dart`, and actual shared APIs needed to trace their behavior.
- Date: 2026-10-15
- Workspace: `D:/MyNewProjects/qfli_rust`; shared API reads from `D:/MyNewProjects/qfli_studio_core` only.
- Ownership: this report only; no source, shared core, generated assets, or Git changes. No Flutter process was started while the platform worker holds its build lock.
- Snapshot: implementer changes are live. The projectOutput issue was fixed during review; remaining findings below refer to the observed source state and can be superseded by subsequent edits.

## Findings

### P2: Existing explicit Cargo binary entries can break custom-filename imports

**Location:** `lib/rust_project_store.dart:87,95-98`.

When a learner chooses `custom.rs`, the shared store writes `src/custom.rs`. The Rust bundle writer deliberately skips `src/main.rs`, then attempts to rewrite a bundled Cargo manifest only by replacing the exact quoted text `src/main.rs` if it detects any `[[bin]]` block.

A valid, accepted authored manifest can contain:

```toml
[package]
name = "demo"
version = "0.1.0"
edition = "2021"
[[bin]]
name = "demo"
path = "./src/main.rs"
```

`validate_topics` accepts this manifest; its canonical entry exists and equals the standalone code before import. On import with `fileName: 'custom.rs'`, the string replacement leaves `./src/main.rs` unchanged, while that file is never written. Cargo subsequently references a missing entry. A bin declaration without an explicit path, or a manifest with only an unrelated explicit bin, has the same basic problem: the presence of any `[[bin]]` prevents adding a target for the selected source.

**Fix direction:** rewrite the actual target that owns canonical `src/main.rs` using TOML/path semantics, or validate and reject unsupported manifest/rename combinations before creating the project. Preserve unrelated binary targets. Add a custom-filename regression for dot-relative paths and an implicit-path explicit bin. A test that checks only a manifest without `[[bin]]` does not cover this branch.

### P2: Failed companion-file writes leave a registered partial project

**Location:** `lib/rust_project_store.dart:56-72,83-90,148-149`.

`super.createProjectFromExample` finishes both directory creation and durable registration before `_addCargoFiles` starts writing the new Cargo bundle. Any later companion-file creation/write failure returns an error with the already-registered project and does not remove the registration or the newly owned directory. The shared import dialog correctly refuses success/navigation when `result.error` is non-null (`../qfli_studio_core/lib/widgets/code_snippet.dart:459-466`), but the failed import remains in the home project list and on disk. Retrying creates another project rather than completing or cleaning the failed one.

A deterministic data trigger is a bundle with both `src/conflict` and `src/conflict/child.rs`. The generator currently accepts it; the Dart bundle path validator also accepts both. Creating the parent as a file makes the later directory creation fail. A disk-full/permission failure after any successfully written companion has the same result with otherwise valid content. This is introduced as a new multi-file import failure boundary even though `_addCargoFiles` already had a simpler error-return convention.

**Fix direction:** validate filename prefix/type collisions before creation and make bundle augmentation transactional with respect to its newly created directory/registration. Roll back only the directory owned by this new import. Keep existing-project imports untouched. Add a failure injection after the first successful companion write and assert that both registry and directory return to their pre-import state.

### P2: `files: null` passes author validation but breaks both verifier and app import

**Location:** `scripts/generate_rust_content.py:129-132,187-188`; `scripts/verify_rust_content.py:82-90`; `lib/rust_content_repository.dart:49-51,66-68`.

The author validator does `files = topic.get('files')` and validates only when `files is not None`. Therefore explicitly providing JSON `"files": null` is accepted as though no bundle exists. Generation and verification instead use `if 'files' in topic`:

- Generation emits `inputFixtures: {"cargoFiles": "null", "cargoVerify": "run"}` and counts a Cargo project.
- Verification attempts `topic['files'].items()`, raising `AttributeError`; the main exception handler does not catch it, so the release report can stop partway through the catalog.
- App import decodes `"null"`; `RustExampleProject.fromJson` then rejects it, preventing an otherwise valid standalone lesson from being imported through the new-project route.

**Evidence:** a pure in-memory call to `validate_topics([record_with_files_null], expected_count=1)` returned success, and `build_documents` emitted exactly the fixtures above. No topic source file was altered.

**Fix direction:** reject a present non-map `files` value, or consistently normalize null to absence across validation, generation, counting, verification, and repository lookup. The authored contract says optional map, so rejection is the clearer behavior. Add a focused regression for explicit null.

### Resolved during review: Cargo project stdout was compared against standalone stdout

At initial read, `verify_rust_content.py:95-99` always compared `cargo run` output with `topic.output`, ignoring optional `projectOutput`; the generator also did not type-check the optional field. An all-memory mocked reproduction produced failure when actual project stdout exactly matched `projectOutput` but differed from the independently runnable source's output.

The implementer corrected this during review:

- `generate_rust_content.py:120-121` rejects non-string `projectOutput`.
- `verify_rust_content.py:92` selects `topic.get('projectOutput', topic['output'])`.
- The verifier now first runs offline `cargo build --workspace --all-targets`, then the requested run/test operation, avoiding a default-bin-only compilation claim for companion projects.
- `test_rust_content.py` gained `test_cargo_project_output_is_distinct_from_standalone_stdout` and asserts both matching and mismatching cases.

This is no longer an open finding in the observed updated source. `projectOutput` is a verification expectation; not displaying it in the shared single-source example output is not itself a bug because that UI displays the standalone counterpart.

### Repository and shared navigation checks without additional findings

- `RustContentRepository` implements the actual `ContentRepository` methods and `ContentFilter.matches` contract (`lib/rust_content_repository.dart:8-42`; shared `content/content_repository.dart:263-273`). Generated schema-1 entries match the shared tutorial/example parser. Parsing through the top-level `compute` callback carries only the two JSON strings and works with the shared serializable model.
- `_load` resets its cached future on an asset/parse failure rather than permanently caching the error (`rust_content_repository.dart:20-30`). The temporary missing assets while authors/generator are working are not reported as code bugs.
- `inputFixtures` is present on `ExampleContent` but absent on shared `ExampleCode`. Resolving a bundled project by stable example ID is therefore an intentional and necessary Rust-owned bridge, rather than assuming the shared UI retains the fixture map.
- The new-project route uses the real `RustProjectStore.createProjectFromExample` override. Shared editor-open imports use `CodeImportService.openInEditor` and `addExisting`, while existing-project imports use `CodeImportService.importIntoProject`; those paths intentionally retain the standalone counterpart and do not append a Cargo bundle into an existing project.
- `CodeSnippet` uses the editable controller source via `example.copyWith(code: _code)`; the Rust bundle writer skips `src/main.rs`, preserving those edits. Shared successful import navigation supplies the real path to `openEditorPage(initialOpenPath: ...)` (`widgets/code_snippet.dart:210-217`).
- The Dart project-path validator rejects absolute paths, drive/UNC separators, control characters, traversal, metadata, and case-insensitive duplicate names. No path traversal outside the newly created directory was found. File/directory prefix collisions and portable reserved names are not rejected, which contributes to the write-failure case above; the ordinary verified authored bundle need not contain such names.

## Validation Performed

Ran current `scripts/test_rust_content.py` with `python -B`, directing `tempfile.tempdir` inside this task's `research/` directory to respect researcher write scope. All six tests passed. Temporary test directories were automatically removed. This covers structural pairing, placeholder rejection, project path/network dependency rejection, projectOutput selection, subprocess nonzero status, and subprocess timeout reporting.

Additional pure in-memory Python probes established:

| Probe | Observed result |
| --- | --- |
| Optional projectOutput differed from standalone output (initial snapshot) | Exact project output was incorrectly rejected; subsequently fixed |
| Explicit `files: null` | Accepted, then emitted as `cargoFiles: "null"` |
| Explicit bin `path="./src/main.rs"` | Accepted by schema/TOML validation |
| Both `src/conflict` and `src/conflict/child.rs` | Accepted by author validation |
| Reserved Windows file `src/CON.rs` | Accepted by author validation; supplementary portability gap, not a separate release finding |

No full catalog generation/compile sweep was run because the assigned author ranges are still being written. No Flutter analysis/tests, platform build, device installation, or real Rust engine execution was run in this review. Passing Python tests do not establish lesson program correctness; the coordinator still needs the final real per-item compiler/output report.

## Files Found / Related Specifications

- `scripts/generate_rust_content.py`: validates author fields and writes/checks app-local tutorial/example catalogs.
- `scripts/verify_rust_content.py`: invokes real host rustc/Cargo and records per-example, exercise, and full-project evidence.
- `scripts/test_rust_content.py`: focused Python contract and process-evidence regressions.
- `lib/rust_content_repository.dart`: rootBundle catalog boundary and strict bundled-file map decoding.
- `lib/rust_project_store.dart`: Rust-owned Cargo initialization and new-project bundle augmentation.
- Shared `content/content_repository.dart`, `models/tutorial.dart`, `pages/local_content_pages.dart`, `widgets/code_snippet.dart`, `services/code_import_service.dart`, `store/project_store.dart`: actual content conversion, editable source, filesystem/import/navigation contracts.
- Task `design.md`: standalone full code, same `files['src/main.rs']`, complete exercise answer, optional Cargo bundle, stable IDs.
- `.trellis/spec/frontend/content-imports.md`: preserve selected filename/current source, actual editor path, safe failure and shared ownership.

## External References

No external research required. TOML/path behavior was checked against the actual local validator and import source; Cargo execution assumptions concern the manifest's selected source path.

## Caveats / Not Found

- Findings are code-path/schema issues, not an audit of unfinished author JSON. No author absence or partial range was reported as a defect.
- The source tree is live; the implementer may already be correcting remaining P2 findings. Re-read the focused branches before final acceptance, and preserve corrected findings as resolved evidence rather than reopening them from stale line numbers.
- The shared core remains read-only. This review found fixes owned by the Rust project and does not require edits to another language product.
