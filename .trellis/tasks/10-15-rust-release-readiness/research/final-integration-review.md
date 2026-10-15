# Final Rust integration review

Reviewed only `D:/MyNewProjects/qfli_rust`; adjacent shared core was read-only at
`8b33443`. Existing author, native-platform and coordinator edits were preserved.
This review covers repository/store integration and offline profile wiring; the
independent lesson semantic review and native packaging/device checks remain
separate evidence.

## Findings fixed

`lib/rust_project_store.dart`: `cargoPackageName('CON')` produced `con`. An
imported example preserves arbitrary valid display names while the shared store
creates an ASCII `demo_*` directory, so this reaches a real Cargo manifest rather
than failing at directory creation. The pinned host Cargo accepts the package
but its Windows build exits 101: it warns that `con` is a reserved Windows
filename and fails copying/linking `target/debug/con.exe`.

The helper now prefixes normalized `con`, `prn`, `aux`, `nul`, `com1` through
`com9`, and `lpt1` through `lpt9` with `rust_`. Display names and valid ordinary
package names remain unchanged. `test/rust_project_store_test.dart` adds device
name/boundary assertions plus a real imported `CON` display-name regression:
create the project using `custom.rs`, build its actual manifest with
`cargo build --offline`, execute the generated `rust_con` binary, and check
stdout. The test preserves explicit compiler flags and uses the existing Windows
GNU self-contained linker fallback. `content-imports.md` records the contract.

`lib/rust_runner.dart`: after the coordinator's final formatting pass, three
multiline guards in `resolveGnuLinkerFallbackFlags` lacked braces and triggered
`curly_braces_in_flow_control_structures`. Added only those braces; behavior is
unchanged. Formatting then reported zero changes and analysis of all `lib`,
`test`, and `integration_test` sources completed without issues.

## Accepted paths

- `rustProfile.contentRepositoryFactory` constructs `RustContentRepository`;
  pubspec registers `assets/content_rust/`. Shared `HomePage` supplies that
  repository to both local content pages. There is no shared placeholder fallback
  in the Rust repository. It implements all three shared repository methods,
  caches successful loads and clears a failed load for retry.
- Shared `LocalContentAdapter` intentionally drops `inputFixtures` when creating
  editable `ExampleCode`. Rust new-project creation resolves Cargo companions by
  the stable `rust-example-NNN` ID. User/noncatalog examples bypass asset lookup.
  Companion installation skips the original `src/main.rs`, preserving the
  learner's current source at the selected entry.
- Bundle validation rejects escaping/reserved metadata paths, case collisions,
  file/directory prefix collisions and conflicting directory case. Custom Cargo
  entry preflight rejects ambiguous owners, explicit bins without paths and
  dot-relative aliases of the replaced root target. It preserves package/bin
  identities and `default-run` for supported canonical manifests.
- New-project imports configure the selected source in project metadata and
  Cargo. Existing-project/editor imports use the shared standalone-code service
  and do not expand the bundle or rewrite an existing manifest. Existing source
  import checks destination ownership, conflicts and replacement backups.
- Companion I/O failure removes only the newly owned project root, then invokes
  the actual shared `deleteProject` missing-root path to persist registry removal.
  Cleanup failure remains an error with the affected project returned; it never
  becomes a successful import. The regression checks registry bytes, remaining
  project IDs and preservation of the pre-existing directory.
- `isOffline: true` also sets `offlineOnly`. Startup `AuthStore.load` restores
  local data without a refresh request. Shared Home/Profile restored-token
  refreshes are gated; product content pages use local filtering. Both terminal
  surfaces consume `rustProfile.terminalCommandDelegate`; shared offline shortcut
  and editor gates are present at the reviewed core revision.
- The inspected Rust repository/store/profile methods contain no unimplemented
  method bodies or placeholder branches. Their `null` results represent missing
  optional bundles/unknown IDs rather than missing implementations.

## Verification

- Dart analysis: passed for `lib/rust_content_repository.dart`,
  `lib/rust_project_store.dart`, `lib/main.dart`,
  `test/rust_content_repository_test.dart`, `test/rust_project_store_test.dart`
  and `test/rust_app_test.dart`, including the new fix/regressions.
- Formatting: all six files pass; the modified two were formatted after editing.
- Final follow-up analysis of `lib test integration_test`: passed after the
  three mechanical runner lint fixes; runner formatting reports zero changes.
- Python content contract tests: seven passed.
- Real pinned Cargo reproduction: original `con` binary build failed with the
  concrete reserved-filename diagnostic (exit 101).
- Flutter commands were intentionally not started by this reviewer because the
  coordinator owns the serialized final whole-suite/build window. The new real
  imported-project regression must pass in that run before the batch is committed.

## Remaining limits

No further source defect was found in this assigned integration scope. Final
catalog compiler evidence must use the final authored-source hashes; changing
author inputs during review are not treated as generated-asset product defects.
This review does not establish Android/OHOS native execution, signing or final
artifact validity. Those belong to the platform evidence and actual device
ownership handoff.

## Final coordinator verification

After the reviewer released source ownership, the coordinator ran the complete
root suite with the real pinned compiler and complete GNU tools: **140 passed,
8 Windows-native Miri skips, zero failures**. This includes both added DOS-name
regressions and all 23 custom-name Cargo bundle builds. Final whole-tree Dart
analysis passed and formatting required no changes. The final corpus verifier
passed all 166 lessons / 332 programs / 23 Cargo projects at recorded hashes.
