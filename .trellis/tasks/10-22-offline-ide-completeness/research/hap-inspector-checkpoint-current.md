# Rust archive inspection checkpoint

Date: 2026-10-26. Baseline commit: aa8594a.
The all-product task remains in progress.

## Result

The archive gate rejects incomplete Rust ABI exports, stale compiler provenance,
foreign native payloads and mismatched packaged compiler bytes.
It requires 27 callable exported symbols across run, analysis and debugging.
Manifest checksums alone cannot establish those capabilities.

Trusted compiler and adapter build records are explicit byte inputs.
Their hashes bind the manifest and optional build metadata.
The compiler boundary must match the reviewed patch and pinned source identity.
Each adapter compiler-library entry must match a compiler runtime artifact.
Packaged compiler bytes must match that verified entry.
The gate never follows producer paths from a build record.
It rejects rooted or unsafe runtime-relative artifact paths.

## Scoped source closure

The source slice includes the inspector, regression suite, native catalog
builder, catalog regressions, two ABI headers and existing catalog repairs.
The 166 topic IDs remain unchanged.
The generated inventory covers 332 example/answer cases and 23 project bundles.
No new topic bypasses the pending OHOS baseline.
Controlled-Chinese repairs change prose only relative to the repair snapshot.
Code, answers, expected output and bundle file contents remain unchanged by
those prose repairs. The earlier complete-topic input hashes are now stale.

The separate HAP build wrapper has source changes that forward explicit records
and capture their initial hashes. Its application-entry closure still needs SDK
verification. It is outside this commit slice.

## Verification

A temporary minimal tree contained committed dependency scripts and only the
candidate catalog, headers and inspector files from this working tree.
Its 144 pure tests passed: 121 inspector cases and 23 content/catalog cases.
Both generation drift checks passed in that same tree.
The temporary tree was removed after checking its location under the system
temporary directory.

Independent review rejected both previously accepted inconsistent chains:
a driver hash mismatch and a backend missing from compiler runtime artifacts.
The reviewer found no remaining issue in this focused source gate.
PowerShell caller AST validation passed separately without running the script.
Controlled-Chinese reports and changed prose fields passed their scoped checks.
The full JSON mechanical scan includes Rust syntax and existing prose debt.
The prose report explains those findings instead of claiming a clean full corpus.

Final inspector SHA-256:
`3f8d1eb83b0303d78a7c71f8ff2ff4e43a8757fce266ceaa5710d80bf5ee6112`.
Final inspector test SHA-256:
`b0e52f2a8b84c6e413429255bd0f7fe75cb6600ff1772a535347b07a6d020a85`.
Ignored local closure evidence:
`build/offline-ide-audit/inspector-commit-closure-final.json`.

## Acceptance still open

No compiler, adapter, SDK, WSL, HAP build or device execution ran for this slice.
The existing real manifests lack the new provenance fields.
No current OHOS archive packages the complete required ABI.
Static archive success always keeps deviceExecuted false.
The actual 332-case OHOS baseline and six provider checks remain unexecuted.
Native and Dart readiness remain deferred under global coordination event 757.
No runtime slot is held and no old grant may be replayed.
