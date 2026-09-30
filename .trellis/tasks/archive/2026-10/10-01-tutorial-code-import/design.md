# Content Code Import Design

The shared dependency at `../qfli_studio_core` owns the pages and editor.
Apply focused edits there, preserving its dirty worktree. Root task artifacts
and verification remain in qfli_rust. Writing the dependency requires sandbox
approval because it is outside the current writable root.

Use unframed Material ListTile catalogs and the existing MD3 theme. Detail
code blocks share CodeSnippet import controls. CodeImportService.openInEditor
writes a unique persistent snippet directory and project metadata; the dialog
registers it only after writing succeeds. Project import selects an existing
local project or creates a real project using ProjectStore. A custom filename
is placed in the template's source directory. Existing files require explicit
replacement confirmation and a successful backup before an atomic replacement.

Pass store/auth/settings through the existing HomePage routes. The native
EditorPage opens the imported path. Its explicit initial path takes precedence
over the remembered active tab while preserving other restored tabs.

Reuse filename validation and project templates. The import service returns
a typed project/path record; the UI owns localized dialogs, progress and
navigation. New projects use their custom source as the configured entry instead
of retaining the template's default source. RustProjectStore additionally writes
a Cargo binary entry for custom Rust filenames. Catalogs and details share a
maximum reading width of 960 pixels. Primary navigation and catalog data stay
owned by their existing modules.

The initial work/ staging copies were superseded by newer shared-core changes
found during continuation. The implementation and verification use the current
shared core; those staging copies are historical snapshots, not pending patches.
