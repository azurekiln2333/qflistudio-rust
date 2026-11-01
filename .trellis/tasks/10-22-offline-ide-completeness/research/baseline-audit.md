# Unified offline IDE goal: Rust evidence and planning packet

Date: 2026-10-22. This is research, not a completed task or product change.

## Full source requirements retained

The attachment requires all standalone language apps to have all current examples
verified on their actual current OHOS toolchains before substantially more than
100 new examples are added and verified; combined language filters and language
circles in tutorials/examples; useful flat language tools; real editor syntax
diagnostics and wave underlines; retained explorer expansion; multi-project
workspaces; feasible real offline debugging, Problems/Output/Debug Console/
Terminal/local Ports; complete highlighting; C/C++ local headers; Python offline
modules/packages; coordinated shared-core changes; scoped conventional commits
and normal pushes when available. One product cannot close the umbrella goal.

## Current authoritative evidence

- Repository: D:/MyNewProjects/qfli_rust, main at 78fb7b1. No active Trellis task.
- Preserve pre-existing native/README.md and OHOS identity/build edits and all
  unrelated untracked files. No product source has been changed in this audit.
- `python scripts/generate_rust_content.py --check` passes: 166 tutorials,
  166 examples, 23 Cargo projects. These are baseline content, not new additions.
- Source runtime labels: 141 desktop, 22 cargo, 1 external, 2 miri-candidate.
  These labels are not evidence of OHOS execution.
- `python -m unittest discover -s scripts -p test_rust_content.py`: 7 tests pass.
- `scripts/verify_rust_content.py` invokes host rustc/Cargo and explicitly records
  `mobileExecution=not_tested`. It cannot establish OHOS acceptance.
- `integration_test/rust_native_test.dart` setUpAll asserts Platform.isAndroid,
  Android runtime and an isolated Android package path. It does not validate the
  entire catalog and cannot currently run unchanged as OHOS coverage.
- `hdc list targets` returns `[Empty]` during this audit. Actual device execution
  remains unverified; independent host/tooling work can proceed.
- `lib/main.dart` has an offline Rust profile and app-owned content repository,
  runner and terminal delegate; no Rust toolsTabBuilder is configured.
- Shared dependency worktree has existing file_explorer.dart/project_history.dart
  edits and tests. Do not overwrite these or infer their writer from a lock.
- Shared-core task 10-22-offline-content-explorer assigns content chips/badges
  to C coordinator w1R:p1; explorer/history ownership is unresolved in its PRD,
  and diagnostics APIs are reserved separately.
- New shared-core task 10-22-offline-editor-analysis now owns typed analysis,
  wavy decorations, Problems and missing default grammars. Its design freezes
  `StudioProfile.codeAnalyzer`, `CodeAnalyzer.analyze(CodeAnalysisRequest)`,
  immutable unsaved CodeDocumentSnapshot objects and CodeAnalysisResult. Spans
  use zero-based half-open UTF-16 offsets. Rust should implement this contract
  without running user programs or overwriting source during analysis.
- Shared UI research confirms toolsTabBuilder already provides a direct tools
  body. Current bottom panels only contain terminal/AI, and simultaneous multi-
  root workspace remains missing. New explorer/history fixes are in progress,
  not yet a verified completion claim.
- Existing umbrella requirements R1-R10 are recorded in
  D:/MyNewProjects/qfli_c/.trellis/tasks/10-22-offline-standalone-ide/prd.md.
  Rust must link evidence to that ledger and preserve every original requirement.
- Herdr inherited environment points to OBS, not Rust. Inventory identifies
  actual Rust workspace w2B with four idle Pi panes p2, p5, p3, p4. Use verified
  exact IDs only. No foreign-pane input was sent.
- Two native research agents failed with account concurrency errors; this is not
  completion evidence and does not prevent local research/implementation.

## Proposed task and execution sequence

Create a Rust Trellis task linked to the existing all-product umbrella, preserving
requirements R1-R10. Persist prd.md, design.md, implement.md, evidence ledger and
real context manifests before activation. Coordinate shared API/file ownership
centrally; Rust owns only its runtime, catalog, tools and adapter paths.

1. Establish a hash-bound all-catalog native/OHOS verification harness including
   lesson programs, answers, imported multi-file projects, output, exit status,
   failures and timeout handling. Host and OHOS reports remain separate.
2. Fix existing Rust OHOS incompatibilities. No new catalog additions are
   accepted until baseline OHOS execution is proven, as required by the user.
3. Add 180 substantive new paired Rust topics (target total 346) after that gate,
   retain unique authored content and compare all outputs on the shipped engine.
4. Add flat useful offline Rust tools through profile extension seams and real
   nonexecuting source diagnostics through the agreed shared provider contract.
5. Integrate shared filter/badge/explorer/workspace/highlighting/panel changes
   without duplicate writers. Assess actual debugger backend capability before
   exposing breakpoint controls; track unsupported required work explicitly.
6. Run analysis, meaningful tests, full catalog verification and final package/
   device audits. Review exact owned diffs, commit conventionally and verify
   normal pushes. Do not stage unrelated initial modifications.

## Open evidence gates

OHOS device reachability and Rust-specific matching signing/install evidence;
full catalog OHOS runs; shared diagnostics contract and explorer/workspace owner;
genuine native debugger capability; fresh all-product evidence and final push
results. None is satisfied by historical reports or a host-only pass.
