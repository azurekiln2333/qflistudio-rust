# Research: pre-migration quality failure comparison

- Query: Classify the formatting, analysis and root-test failures at the published migration SHA against pre-migration source without running local validation.
- Scope: internal source and persisted hosted evidence; no local tests, builds, formatting, analysis, dependency restoration or artifact downloads.
- Date: 2026-11-27

## Findings

### Immutable comparison and its limit

The pre-migration source baseline is `540674ff95a83daa2848ee463f3c6aaf8986f6ff`.
The published migration candidate is `f990471556923f302f2d9b5afab9970a98291fe2`.
The retained read-only comparison found all 47 tracked blobs under `lib/`,
`test/`, `integration_test/`, and `analysis_options.yaml` identical between
these commits. No authored application/test/analyzer-configuration delta in
those paths explains the reported findings.

This is source identity evidence, not a pre-migration hosted test result.
The available watcher evidence found no matching pre-migration quality run in
its queried results. No same-SDK baseline execution has been established.
The migration changes `pubspec.yaml`, `pubspec.lock`, generated registrants,
and the core checkout/approval contract. The baseline is not bound to the
same resolved dependency graph or exact core `476a30acee21dc486ee2849dd8064a7be665e4d5`.
Therefore identical test source does not establish identical runtime behavior.

### Hosted failures and classification

Persisted evidence is the exact-SHA Application quality run `45990028561`,
core-bound job `140475207055`, and the coordinator/watch file
`D:/MyNewProjects/_orchestra/status/qflistudio-rust.ci-watch.json` as read on
2026-11-27. The watcher records completed/failure at the candidate SHA and
successful helper job `140475207728`.

| Check | Recorded result | Supported classification |
| --- | --- | --- |
| Format | `dart format --output=none --set-exit-if-changed lib test integration_test` exited 1; 46 files inspected and two would change: `test/rust_code_analyzer_test.dart` and `test/rust_workspace_integration_test.dart` | Existing identical source is the subject of the finding. There is no authored migration delta in either file. A failure on pre-migration main under an equivalent formatter has not been executed/proven. |
| Analyze | `unnecessary_non_null_assertion` at `test/rust_native_feature_audit_test.dart:327:31` and `:431:29`; exited 1 | Both `failure!` expressions already exist in the unchanged baseline blob. No authored migration delta, but equivalent baseline analyzer execution is not established. |
| Root tests | `mobile drawer reopening retains both Rust roots and nested expansion` failed with `Rust workspace operation did not finish`; stack includes `test/rust_workspace_integration_test.dart:748`, `:618`, `:227`; Flutter process exited 1 | Unresolved causality. The test blob is unchanged, but the dependency/core inputs differ. Do not classify the timeout as proven pre-existing or infrastructure merely from source equality. |
| Machine evidence parser | After the failed test process, the helper reported `Malformed test protocol event` | Separate helper/protocol finding under its assigned owner. Repairing parser handling cannot convert the actual nonzero test result into success. |
| Finalize | Required stages incomplete | Derived failure; no application quality pass. |

### Source locations and patterns

- `test/rust_workspace_integration_test.dart:197`: named drawer reopening test.
- `test/rust_workspace_integration_test.dart:227`: second explorer opening in the failing path.
- `test/rust_workspace_integration_test.dart:614`: `showExplorer` taps the file-tree control, pumps, then waits for both roots/rows.
- `test/rust_workspace_integration_test.dart:737`: bounded `_pumpIoUntil` helper; failure is raised at line 748.
- `test/rust_native_feature_audit_test.dart:327` and `:431`: unchanged `final retained = failure!` statements reported by the analyzer.
- `pubspec.yaml:13`: canonical sibling core path.
- `pubspec.yaml:21`: root overrides for both vendored `re_editor` and `xterm`; these resolved inputs matter to behavior comparison.

### Related policy and evidence files

- `.trellis/spec/guides/cloud-only-workspace.md`: all executable validation remains GitHub-hosted; migration receipts and CI classification are separate.
- `.trellis/spec/backend/github-app-builds.md:222`: quality report contract.
- `.trellis/spec/backend/github-app-builds.md:233`: exact format/analyze/full root-machine commands and full private protocol capture.
- `D:/MyNewProjects/_orchestra/decisions/ci-decoupled.md`, section 3: only failures established to exist at pre-migration GitHub main may become follow-ups; migration-caused inputs must be fixed and republished through the gate.
- `research/cloud-evidence-443c988.md` and `research/cloud-evidence-60524ea.md`: prior restore rejection blocked actual format/analyze/root processes, so those runs do not establish a passing or failing application baseline.
- `D:/MyNewProjects/_orchestra/status/qflistudio-rust.progress.md`: final-SHA migration receipt/parity and 20:33 quality triage entry.

### External references and versions

The recorded hosted SDK contract is Flutter-OH tag `3.41.10-ohos-1.0.1`,
revision `adaf911c35c9136a7d18fc424d714c9ec7724e60`; the recorded core pin is
`476a30acee21dc486ee2849dd8064a7be665e4d5`. Exact run/job IDs above are the
external evidence identities. This bounded comparison did not download
artifacts, refresh remote run state, or independently establish any older
SDK/dependency execution identity.

## Caveats / Not Found

- No pre-migration hosted quality result with an equivalent SDK and resolved dependency graph was found in the available evidence. Absence from the queried run results is not proof that no historical run ever existed.
- Format/analyzer source predates migration, but that alone is narrower than a demonstrated pre-migration failing check.
- The drawer timeout remains open. Do not skip or weaken its assertion, increase its timeout without a cause, waive it as historical, or claim the suite passed.
- No classification here grants product, native-hooks, installer, signing, device/UI, armv7 or receiver-hook acceptance.
- This researcher wrote only this research file. Coordinator owns orchestration progress/status receipts and publication. No product code or other worker file was changed; no Git write or local executable validation ran.