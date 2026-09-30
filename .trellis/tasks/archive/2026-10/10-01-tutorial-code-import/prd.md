# Simplify tutorial and example pages with code imports

## Goal

Use simple MD3 catalogs and detail code blocks with named editor/project imports and automatic opening

## Requirements

- Tutorial and example catalogs use compact MD3 lists showing titles/summaries,
  with no inline source code or runtime implementation summaries.
- Detail pages show the real code and offer import into the editor and import
  into an existing or new local project.
- Both imports allow a custom filename; project import automatically opens the
  project and selects the imported file.
- Preserve primary navigation, content, existing edits, localization and theme.
- Report write/name conflicts without silently replacing existing user files.

## Acceptance Criteria

- [x] Catalogs show no code; tapping an item opens its detail.
- [x] Both tutorial and example detail code blocks expose both imports.
- [x] Named editor imports persist real code and open the imported file.
- [x] Named project imports write real code to existing/new projects and open it.
- [x] Existing session history does not hide the imported file.
- [x] Cancellation, invalid names, collisions and write errors retain safe state.
- [x] Mobile/desktop MD3 layouts fit; focused behavioral verification passes.

## Notes

- Editor imports retain the current shared implementation's persistent snippet
  registration so users can reopen them. The user requested importing and
  opening code, without requiring snippets to be excluded from the project list.
- Replacing an existing file requires confirmation and a successful backup.
- Rust projects created from examples retain Cargo support with custom entry names.
- Device and compiler execution checks remain paused at the user's request.
