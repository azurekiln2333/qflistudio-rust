# Rust Application Integration Guidelines

`lib/main.dart` supplies the Rust StudioProfile. The shared package owns editor,
terminal, content pages, authentication and common tools. Rust-owned extensions
use profile seams and must preserve shared navigation and editable source.

| Guide | Scope |
| --- | --- |
| [Content Imports](./content-imports.md) | Local curriculum catalogs, complete Cargo imports, path validation and rollback |
| [Native Runtime](../backend/native-runtime.md) | Dart FFI, asset preparation, platform identity and cancellation |
| [Rust Run Controls](../backend/rust-run-controls.md) | Editor gestures, selected source and run titles |
| [Rust Terminal](../backend/rust-terminal.md) | Both terminal surfaces and offline command handling |

Run Dart analysis, canonical formatting and root Flutter tests before a code
commit. Catalog changes also require generation drift checks, actual compilation
of every main/answer and full offline Cargo bundle checks. Shared-core fixes
must be coordinated with their current owner; never patch another product's UI
or catalog from this repository.
