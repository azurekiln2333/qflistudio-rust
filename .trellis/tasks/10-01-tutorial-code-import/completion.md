# Completion Evidence

## Requirements

| Requirement | Evidence |
| --- | --- |
| Compact MD3 catalogs without source previews | Shared catalog tests assert no CodeSnippet, SelectableText, copy action or Card on the catalog; actual Rust render tests verify the same behavior. |
| Source and both import commands in details | Tutorial/example detail tests and actual Rust render tests find both localized import commands. |
| Custom filename and automatic editor opening | Four HomePage import tests cover lesson/example imports into editor/new project, assert exact source on disk and in the real CodeEditor. |
| Existing/new project selection | New-project flows and the existing-project import test pass using real filesystem writes. |
| Imported file wins over history | Existing-project test seeds an old active tab, then verifies the imported source is the selected CodeEditor content. |
| Safe cancellation and conflicts | Cancel/invalid-name/write/registration-failure tests preserve files and registry; replacement rejection preserves content and confirmation writes with backup. |
| Current edited code and persistence | Edited example imports, save/reset, reopening and write-failure tests pass. |
| Responsive layout | 320/1280 px at 2x text in the shared suite; real Rust screenshots at 390x844 and 1280x900. All controls fit and no Flutter layout exception occurs. |
| Rust project compatibility | Root regression asserts custom Cargo bin path, actual imported source, configured runtime entry, no generated main.rs, and unchanged Cargo metadata after an existing-project import. |

## Commands

Use `D:/ProgramFiles/flutter_ohos/bin/cache/dart-sdk/bin/dart.exe` with
`D:/ProgramFiles/flutter_ohos/bin/cache/flutter_tools.snapshot` from the root.

```text
flutter test --no-pub ../qfli_studio_core/test/content_code_import_test.dart ../qfli_studio_core/test/studio_profile_test.dart test/rust_project_store_test.dart --name '^(?!.*compiles and executes through Cargo).*' --reporter expanded
43 passed

QFLI_UI_SCREENSHOTS=<task>/screenshots flutter test --no-pub test/rust_content_pages_test.dart --reporter expanded
4 passed; 12 PNG screenshots generated

dart analyze lib test <affected shared UI/service/editor/store files> ../qfli_studio_core/test/content_code_import_test.dart
No issues found
```

## Inspection

Rendered screenshots confirm real Rust titles, source, output, exercises, MD3
icons, compact catalog rows, constrained desktop content and fitting dialogs.
Material icon and editor fonts are loaded in the screenshot harness, not added
to the application's implementation.

Shared core had extensive unrelated changes before this task. Keep the original
snapshots for context and stage only attributable work when creating commits.
OHOS EntryAbility/main_pages changes and generated plugin files are unrelated.

Device installation and compiler execution were not run, as requested.
