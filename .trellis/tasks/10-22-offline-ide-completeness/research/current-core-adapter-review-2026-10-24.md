# Current-core Rust adapter review — 2026-10-24

Reviewed the actual shared-core working tree with published HEAD
`2f9039a3ba95449679b17257b0313c1ee3644a2c`. This is source inspection of the
working tree, not proof of a clean commit-only core. Any future executed gate
must bind its actual lib/assets/config inputs before and after the run.
Read the saved Trellis hook, task check context, PRD/design/implementation plan,
backend/frontend indexes, debugger/analysis/catalog/native/terminal contracts,
and the shared profile, debug-session and editor-history code paths.

Scope: `lib/rust_debugger.dart`, `lib/rust_native_feature_audit.dart`, their
focused tests and `test/rust_workspace_integration_test.dart`. Root owns profile
wiring, audit entry and specs. Existing unrelated source was preserved.

## Findings fixed

1. `test/rust_workspace_integration_test.dart` cloned the production profile but
   omitted the new `supportsSavedWorkspaces` constructor field. It now copies
   `rustProfile.supportsSavedWorkspaces`, so a future production override cannot
   silently diverge from the consumer fixture. A static comparison finds no
   missing current constructor fields. Production currently inherits the core's
   `true` default; this review does not require a new flag in `lib/main.dart`.
2. `lib/rust_debugger.dart` replaced malformed UTF-8 with U+FFFD without marking
   lost bytes. The decoder now attempts strict decoding, retains its bounded
   replacement fallback on `FormatException`, and sets the affected loss flag.
   Valid encoded U+FFFD remains ordinary text. Existing deferral of an incomplete
   live tail and removal of a scalar split by a byte budget are preserved.
   One new regression checks malformed stdout, valid replacement text on stderr,
   and an incomplete final console scalar, including terminal flag retention.
3. The existing workspace fixtures only exercised legacy editor history. At
   root's explicit request, added two actual-Rust-profile consumer cases at
   widths 1100 and 600. The real toolbar dialog saves both Rust roots into the
   isolated `WorkspaceStore`. The editor persists a distinct secondary-only
   active tab, cursor and both roots' nested expansion. A new store reads the
   saved document and the actual Home `SavedWorkspacesTab` card opens a fresh
   `EditorPage`. Assertions cover workspace identity, source ownership, cursor,
   expansion, unchanged Rust bytes and isolation from deliberately different
   project history. The original three cases and their assertions are retained;
   fixture cleanup now drains workspace and project-store writes explicitly.

## Other reviewed paths

- `RustDebugger`, `_RustDebugSession`, the feature audit and their test doubles
  match the current shared `StudioDebugger`/`DebugSession` contract by source
  inspection. Commands dispatch without awaiting the next pause, stale tokens
  are rejected, and terminal/done publication follows active-call completion,
  worker wait and native destruction. Failed cleanup retains retry ownership.
- The feature audit retains the complete pending check and its fixtures through
  timeout/report-write failure, stops late launches, and preserves the typed
  retry owner after failed stop. Its public feature-provider contract needs no
  adaptation to this core revision. No feature-audit production source was
  changed in this review.
- Current legacy history APIs used by the three Rust consumer tests remain
  present. Rust's actual product identity retains language-product restoration,
  including simultaneous roots; the main-studio-only history filter does not
  apply to this profile.

## Findings not fixed / remaining acceptance

- The two newly authored named-workspace cases have not executed. They use the
  actual Home workspace tab/card and disk-backed stores; they do not establish
  full Home scope/navigation or member-management acceptance. Those broader
  shared UI gates and packaged Rust operation remain with their owners.
- Production `rustProfile.debugger` remains unwired. Root owns that decision and
  the required real native gate; this review does not enable it.
- Native compiler confinement failures, fresh strict native ABI runs, current
  HAP hashes and actual packaged OHOS execution remain separate open gates.
  This source review supplies none of that execution evidence.
- The existing debugger contract already requires bounded Unicode and visible
  lost content. Root may make malformed-byte replacement explicit in the spec;
  this reviewer did not edit root-owned spec files.

## Verification

- Source-only whitespace check: no trailing whitespace in the five scoped Dart
  files. Repository `git diff --check` returned 0 (tracked changes only).
- Static profile clone comparison: no missing current constructor fields.
- Authored inventory: debugger **42** (39 registrations, including one loop
  expanded to four commands), feature audit **15**, workspace **5** (four
  registrations, including one loop expanded to two widths); total **62**.
- Formatting, lint, type checking and tests: **not run** in this review. No Dart,
  Flutter, compiler, WSL, build or device process was started. The old Rust205
  handoff was deferred after reading the newer ledger through event535; root
  explicitly retained execution/channel coordination. No process/session or
  reservation is retained by this reviewer.

For a fresh explicitly named Dart gate, validate these exact sources with the
SDK formatter and scoped analysis, then run these files serially:

```text
test/rust_debugger_test.dart
test/rust_native_feature_audit_test.dart
test/rust_workspace_integration_test.dart
```

Source SHA-256 at review freeze (raw file bytes):

| File | SHA-256 |
| --- | --- |
| `lib/rust_debugger.dart` | `ba8b77c318778257ad2672438441da9bc1b78275895673e7f7e05254648978ac` |
| `test/rust_debugger_test.dart` | `bf8e1d2b7df1f84ceb8b3337b623c2a125cfba31da469e3cc8aa3d6769ce6f2f` |
| `lib/rust_native_feature_audit.dart` | `fb8d997eae6af36dbbb39feedf35ac1b39c452f7079c83a6adedd3bb9a4eec4a` |
| `test/rust_native_feature_audit_test.dart` | `ad95f42056ed0ad92cad77d0b3a80297c6111f185e838ed201a485ab05e7f869` |
| `test/rust_workspace_integration_test.dart` | `e7e1eb2484418b09bdd85bc58f9a3279e033be985a5c2c951c0180361d1c3731` |

## Independent bounded-host runner review

Source-only review covered `run-reserved-validation.ps1`,
`run-rust-owned-window.py`, `publish-rust-release.ps1` and `rust_owned_job.py`
under `build/offline-ide-audit/`. Root separately owns native-supervisor review.
The runner owner, not this reviewer, made the correction below.

- Fixed finding: the original source snapshot hashed the adjacent shared core
  and editor but did not bind the effective Dart package map used by `--no-pub`
  validation. The owner now hashes `.dart_tool/package_config.json`, validates
  local resolved `rootUri` and `packageUri` paths for `qfli_rust`,
  `qfli_studio_core` and `re_editor` against the hashed repository/core/vendor
  roots, and compares the effective resolutions before and after validation.
  The source snapshot also records root/core analysis options and the core and
  vendored editor pubspecs. The current local package map matches those roots.
- No additional concrete host lifecycle or false-release defect was identified
  by source inspection. Windows processes start suspended, enter a private Job
  before resume, and retain exact identities. Residual processes require owned
  cleanup and fail validation; unknown cleanup holds the lane. Native evidence
  must bind the unique run ID, directory and report path and prove an empty
  group. Successful publication requires an empty publisher Job and the exact
  acknowledged message/author/sequence. The active marker is cleared only after
  that release condition. Fresh incoming grants remain subject to root's
  current-queue verification; the runner does not establish queue ownership.
- Runtime cleanup, Windows/Linux endpoint behavior, formatting, analysis and
  focused regressions remain **not run by this reviewer**. Static inspection
  cannot establish those execution results. No runtime process, channel action,
  reservation or release was started or retained. Root confirmed old Rust205
  was consumed/deferred at global538 and the newer queue proceeds through
  Web510/Note511; this review does not accept or reuse Rust205.
- Python AST parsing: **PASS** for the frozen runner and Job helper, without
  importing or executing either module. Lint/type checking/tests remain unrun.

Reviewed frozen raw SHA-256 values:

| File | SHA-256 |
| --- | --- |
| `run-rust-owned-window.py` | `6aae56e341ba0961aa9895a00cc2743ffcc7f9eae23526b54f1e531745cd276a` |
| `run-reserved-validation.ps1` | `2c400704502eb5bdf354852c5e676101fe288446b233b0ea0182873b91ea6173` |
| `publish-rust-release.ps1` | `9bc54c9e200cf4a207251cf1be41fc9a9dfd1d20ca1122860ac04e07586047e1` |
| `rust_owned_job.py` | `c0520616e6777d9587a6c0004487bd06a1b19b7d202563f8292c4c1a32c6b172` |
