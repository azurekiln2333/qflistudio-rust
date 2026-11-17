# Implementation

- [x] Extend the desktop producer and fix upstream source-link handling (initial scope).
- [x] Apply corrected target scope: Android/OHOS arm64+x64 and iOS arm64 device; optional macOS x64.
- [x] Fix standard-library facade detection and reuse official build-host toolchains.
- [x] Add pinned OHOS SDK acquisition and portable existing OHOS packager.
- [x] Add a clean-runner CI helper and workflow for guest, compiler, adapter and package stages.
- [x] Document artifacts, download/restore steps and local disk-use findings.
- [x] Run relevant Python regressions, workflow validation and controlled Chinese lint.
- [x] Review initial desktop/source-link changes through a Trellis check agent.
- [x] Review corrected mobile workflow changes through a Trellis check agent.
- [x] Commit, push only to GitHub, observe actual Actions jobs, and fix reproducible failures.
- [x] Record real run results and artifact inventory. All five mobile targets succeeded in run 43946596992.
- [x] Verify every other local and GitHub branch tip is an ancestor and fast-forward main.
- [x] Check main workflow/docs, push main, set GitHub default, and remove merged branches.

## Validation
Use scripts/test_build_rustc_host.py, scripts/test_miri_build_support.py and scripts/test_compiler_provenance_consumers.py and new CI-helper tests where applicable. Validate YAML and shell/PowerShell syntax. Exercise the entire compiler/adapter/package path on GitHub runners. No local compiler bootstrap or Flutter rebuild is required for this workflow-only task.
