# Rust content integration

## Boundary and data flow

Only `D:/MyNewProjects/qfli_rust` is modified. The sibling shared core is read
only. The two authored `tool/rust_content/topics_*.json` arrays are the source
of truth; `scripts/generate_rust_content.py` emits app-local
`assets/content_rust/tutorials.json` and `examples.json` using the existing
`ContentCatalog` schema. The coordinator wires `RustContentRepository` into
`StudioProfile.contentRepositoryFactory` and registers the asset directory.

IDs remain `rust-tutorial-001..166`, `rust-tutorial-NNN-lesson` and
`rust-example-001..166`. Every example references its paired lesson ID.
The repository uses shared product/language filtering and off-isolate JSON
parsing, caches successful loads, and permits retry after an asset failure.
No package-qualified shared catalog fallback can silently restore placeholders.

## Real import representation

The shared `ExampleContent` preserves `inputFixtures`, but `ExampleCode` does
not. Shared editor and existing-project import routes use static
`CodeImportService`; replacing their UI or modifying the shared repository
would cross the authorized boundary.

Therefore every lesson/example detail code is a complete independently runnable
Rust program. Optional `files` maps must contain `Cargo.toml` and `src/main.rs`,
with the latter equal to `code`. These maps become a JSON `cargoFiles` fixture.
`RustProjectStore.createProjectFromExample` resolves them by the stable example
ID through `RustContentRepository`. Newly created project imports receive all
supplemental files while retaining the learner's current edited source and
selected filename. Existing-project/editor imports remain complete standalone
programs. A chosen filename that collides with an attached supplemental file
fails before project creation. Unsafe relative paths and case-insensitive
duplicate paths, file/directory prefix collisions and conflicting directory
case are rejected before writes.

For custom entry names, Cargo's bin path and `.qfli` entry agree. The original
bundled package name is retained so `default-run` and integration-test binary
names continue to match. Already existing projects are never expanded or have
their manifests rewritten by this path.

Custom entries reject ambiguous root binary ownership, explicit bins without
canonical paths and dot-relative aliases before creation. Companion file writes
are exclusive. If a companion write fails, remove only the freshly created root,
then call the shared deletion path on that absent root to persist registry
removal; leave pre-existing projects untouched.

## Verification commands and interpretation

```powershell
python scripts/test_rust_content.py
python scripts/generate_rust_content.py
python scripts/generate_rust_content.py --check
python scripts/verify_rust_content.py --report .trellis/tasks/10-15-rust-release-readiness/research/content-execution.json
flutter test test/rust_content_repository_test.dart test/rust_project_store_test.dart test/rust_content_pages_test.dart --no-pub
```

The generator rejects missing/duplicate IDs, repeated titles/summary/explanation/
source, empty or insubstantial lesson fields, incomplete main programs,
unfinished macros, malformed/unsafe project files, remote Cargo dependencies
and generated asset drift. It records domain, level, runtime and project counts.

The execution verifier uses a real host `rustc`, compares exact stdout (allowing
platform newline conversion only), and separately compiles/runs every exercise
answer. Exercise stdout is recorded; it is compared if an optional exercise
output is authored. Every attached Cargo project builds all workspace targets
offline before its requested run/build/test operation. Timeouts, compiler
errors, nonzero exit codes, output mismatch and missing compiler/Cargo return
failure and individual evidence. Windows GNU uses the bundled `rust-lld`
self-contained link configuration when no explicit user Rust flags are set.

`--structure-only` explicitly reports `compilerStatus: not_run`; it is never a
compiler pass. Desktop host compilation is not proof of Android/OHOS embedded
engine execution. Runtime classification and prerequisites are stated in each
generated explanation without promising mobile engine support.

## Current evidence

- Seven Python contract regressions passed: source pairing, ID/duplicate checks,
  placeholder/incomplete exercise rejection, offline/contained project bundles,
  file/directory and directory-case conflicts, process exit and timeout reporting.
- Targeted analysis of the repository/store and three content test files passed.
- The three scoped Flutter content suites passed 22 tests. This included actual
  custom-name imports and offline all-target Cargo builds for all 23 baseline
  bundled projects, plus learner source preservation, manifest preflight,
  rollback and real catalog page checks.
- Baseline full execution passed all 166 lessons: 332 main/answer programs
  compiled and ran, and all 23 attached Cargo projects passed. Its evidence is
  `curriculum-verification.json`. That report predates substantive 085..163
  revisions and replacement capstones; it must be regenerated after merging
  final source inputs and assets. It is not final release evidence.
- Replacement records 164..166 are isolated in ignored
  `build/capstone-replacements.json` while the second author owns its JSON file.
  The replacements implement a persistent multi-process CLI, bounded channel
  file-processing worker pool, and wake-driven pending/cancellation task queue
  with a checked C ABI. All six replacement main/answer programs and all three
  Cargo all-target builds/tests passed; evidence is
  `build/capstone-verification.json`.
- Independent review found that a filename-less worker job could terminate all
  workers while a retained Receiver kept the bounded producer blocked. The
  replacement now emits one error Event per such input and drops the original
  receiver Arc after worker creation. An eight-root-path self-check and real
  process regression (three workers, queue capacity two, ten-second deadline)
  verify termination and all eight errors. All replacement checks were rerun
  after this fix and passed.
- The coordinator owns final source merge, regeneration, full current-hash
  execution, platform build windows and conventional commits. No root Flutter
  command is started by this role during its platform build window. Android/OHOS
  embedded-engine execution remains separate from host compiler evidence.

## Final coordinator acceptance (2026-10-15)

The historical pending notes above are superseded by the final merged snapshot.
All 166 lessons received semantic review. The 5 async replacements and 3 capstones
are merged exactly; all 332 main/answer programs and all 23 Cargo workspace /
all-target projects passed final real execution. `curriculum-verification.json`
records the exact final input hashes. The GNU host lacked dlltool for a real
proc-macro workspace test target; the installed NDK LLVM tool repaired the
isolated compiler environment, with no target disabled.

Final root Flutter suite: **140 passed, 8 skipped, 0 failed**, including every
actual bundled Cargo project after custom-name import and the CON target-name
regression. The eight skips are Windows-host native Miri sessions without a
Windows adapter/sysroot, distinct from Android device coverage. Dart analysis
passes and formatting requires zero changes. All 13 Python tests pass.

Catalog generation/check: 166 tutorials, 166 examples, 23 complete Cargo bundles;
30 beginner, 58 intermediate and 78 advanced lessons. Only this Rust-local
repository shadows the original placeholder catalog; sibling data is untouched.
