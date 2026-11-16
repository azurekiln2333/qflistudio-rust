# Implementation

- [x] Extend the compiler producer for Windows GNU x64 and macOS arm64; test platform configuration and DLL artifact handling.
- [x] Add a clean-runner CI helper and workflow for guest, compiler, adapter and package stages.
- [x] Document artifacts, download/restore steps and local disk-use findings.
- [x] Run relevant Python regressions, workflow validation and controlled Chinese lint.
- [ ] Review the changes through a Trellis check agent.
- [ ] Commit, push only to GitHub, observe actual Actions jobs, and fix reproducible failures.
- [ ] Record real run results and artifact inventory. Keep failed or pending runtime evidence explicit.

## Validation
Use scripts/test_build_rustc_host.py, scripts/test_miri_build_support.py and scripts/test_compiler_provenance_consumers.py and new CI-helper tests where applicable. Validate YAML and shell/PowerShell syntax. Exercise the entire compiler/adapter/package path on GitHub runners. No local compiler bootstrap or Flutter rebuild is required for this workflow-only task.
