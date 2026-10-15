# Import representation research (traced call chains)

All statements below are traced from `../qfli_studio_core` source read-only on
2026-10-12. No hook is invented; where an extension is proposed it is named as a
proposal with the exact seam.

## 1. The two buttons and their real call chain

`CodeSnippet` (`lib/widgets/code_snippet.dart`) renders two import actions which
both funnel into `_CodeSnippetState._import(intoProject:)` →
`_CodeImportDialog._submit()`:

```
CodeSnippet._import(intoProject: false)   // tooltip: importCodeEditor
  -> CodeImportService.openInEditor({example, fileName})
  -> store.addExisting(snippet.project.path)          // register snippet project

CodeSnippet._import(intoProject: true)    // tooltip: importCodeProject
  -> dialog branch A (existing project selected)
       -> CodeImportService.destinationPath(...)
       -> CodeImportService.importIntoProject({project, example, fileName, overwrite})
  -> dialog branch B (createProject)
       -> store.createProjectFromExample({name, example, fileName})
```

`openInEditor` and `importIntoProject` write exactly **one** file
(`resolveImport` → `(fileName, code)`); `importIntoProject` refuses to overwrite
unless the user confirmed replacement. Only branch B calls
`store.createProjectFromExample`, which is the method `RustProjectStore`
overrides in this repo.

## 2. Lesson path is NOT the same as example path

`_LessonPage` (`lib/pages/local_content_pages.dart`) renders `CodeSnippet` with:

```
ExampleCode(
  id: lesson.id, type: lesson.type, title: lesson.title,
  summary: lesson.summary, code: lesson.code, output: lesson.output,
  sourceLessonId: lesson.id,
)
```

`ExampleCode` (`lib/models/tutorial.dart`) exposes **only**
`id/type/title/summary/code/output/sourceLessonId`. It has **no `inputFixtures`**
and no multi-file field. `TutorialLesson` likewise has no fixtures. The example
tab flows through `ExampleCodeStore`/`ExampleCode` with the same shape.

Consequence: **the lesson button can never carry a bundle** without changing
shared core (`ExampleCode`/`_LessonPage`), which is out of scope. Any plan that
claims lesson bundles import is false.

## 3. Supported representations after the trace

### R1 `single` — works on all three branches (default)

- `code` = one complete single-file Rust program.
- Editor branch: `<storage>/code_snippets/.../src/<name>.rs` + `.qfli` entry.
- Existing-project branch: writes into `<project>/src/<name>.rs`.
- Create-project branch: shared single-file write, then `RustProjectStore`
  adds `Cargo.toml` (explicit `[[bin]]` when not `src/main.rs`) + `.gitignore`.
- **Every lesson and example supports this today.** The large majority of the
  166 lessons use it.

### R2 `cargo-multi` — **create-project branch only** (design proposal, tested)

Multi-file examples (workspace, modules, capstones, proc-macro layout) cannot be
represented by the single `code` string and the lesson path cannot carry a
bundle. The only seam that can expand files **without editing shared core** is
`RustProjectStore.createProjectFromExample`, reached only from dialog branch B.

Proposal (implementation item, pinned schema):

- The Rust **example** entry stores the entry `code` plus a bundle in the
  shared-serialized `ExampleContent.inputFixtures` map:

  ```
  inputFixtures: {
    "cargoFiles": "{\"Cargo.toml\":\"...\",\"src/main.rs\":\"...\",\"src/lib.rs\":\"...\"}",
    "entry": "src/main.rs",
    "verify": "run"        // enum token, NOT a command line
  }
  ```

- `RustProjectStore.createProjectFromExample` expands `cargoFiles` after the
  shared write, with hard validation (below), and records `entry`.
- **Lesson counterpart**: a lesson may only ship `single`. If a topic genuinely
  needs multiple files, it is taught by the lesson's prose + the paired
  **example** (same ID) whose create-project branch carries the bundle; the
  lesson's own code block stays a working single-file demonstration. This
  distinction is explicit in `curriculum-index.md` (`Import` column:
  `single` for lessons, `cargo-multi` for the paired example where applicable).

### R3 `external` — create-project branch only, not executed here

Same as R2, manifest pins real crate versions (`libc = "=0.2.x"`, `tokio`,
`proc-macro2`/`syn`/`quote`). Labeled `external`; never claimed run.

## 4. Bundle validation (mandatory before any write)

In `RustProjectStore`, before writing a single bundled file:

1. Reject if `cargoFiles` is not valid JSON object of `String -> String`.
2. For each key: normalize, reject absolute paths, reject any `..` segment,
   reject control chars / reserved Windows names (reuse
   `CodeImportService.isValidFileName` semantics for the base name), and require
   `p.isWithin(resolvedProjectRoot, p.normalize(p.join(root, key)))` after
   `resolveSymbolicLinksSync`.
3. Never overwrite an existing file: if a target exists, fail the import with a
   localized error and delete only the files this import created.
4. `Cargo.toml` in the bundle wins over the generated one **only** when the
   project was just created by this import (never on `addExisting` or
   existing-project imports, preserving the shared contract).
5. Cap total bundle size (e.g. 512 KiB) and file count (e.g. 32) to bound writes.

## 5. Verifier command policy

The verifier never executes the bundle's `verify` string as a shell command.
`verify` is an enum token (`run` / `build` / `test`) mapped to **fixed argv**:

```
run   -> cargo run  --manifest-path <project>/Cargo.toml --bin <entry bin>
build -> cargo build --manifest-path <project>/Cargo.toml --bin <entry bin>
test  -> cargo test --manifest-path <project>/Cargo.toml
```

`rustc` samples run as `rustc <file> -o <tmp>` then the produced binary. No
`sh -c`, no user-supplied arguments.

## 6. Required tests (exact)

1. **Single-file, all three branches**
   - editor: `openInEditor(example 032)` → file exists, `.qfli` `entryFile`
     points at it, content == `example.code`.
   - existing project: `importIntoProject(example 032)` → file content exact;
     second call without `overwrite` → `CodeImportException(fileExists)` and
     original bytes unchanged.
   - create project: `RustProjectStore.createProjectFromExample(example 032)` →
     `Cargo.toml` present, `[[bin]] path` correct when name != `src/main.rs`.
2. **cargo-multi, create branch only**
   - `createProjectFromExample(example 164)` with a bundle → every path written
     with exact content, dirs created, bundled `Cargo.toml` preserved, entry
     `[[bin]]` resolves; `verify` token recorded.
   - adversarial bundle (`../escape.rs`, absolute path, `Cargo.toml` overwrite on
     existing project) → import fails, nothing written outside the project, no
     pre-existing file modified.
   - assert the **editor/existing-project** branches *cannot* carry a bundle
     (bundle ignored, only `code` written) so the limitation is documented by a
     test, not just prose.
3. **Model round-trip**: build `ContentCatalog` from the generated Rust assets and
   decode `inputFixtures['cargoFiles']` — proves it survives the untyped→typed
   boundary for examples.
4. **Navigation**: `rust_content_pages_test.dart` opens a `cargo-multi` example
   detail at 390/1280px and a `single` lesson detail; both render `CodeSnippet`
   and the import dialog without overflow.

## 7. Honest summary of the limitation

- Bundles import **only** via the example "import to project → create project"
  branch.
- Lessons always import as a single file; their paired example carries any
  multi-file exercise.
- This is stated in the PRD acceptance criteria so the delivered capability is
  not overstated.
