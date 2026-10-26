# Complete native catalog audit

## 1. Scope / Trigger

Apply to native catalog generation, report models, standalone audit entry,
host/native harnesses, HAP audit build/inspection and acceptance evidence.

## 2. Signatures

```text
python scripts/generate_rust_native_catalog.py --check
python scripts/verify_rust_content.py --jobs 1 --report <host.json>
scripts/build_rust_catalog_audit.ps1 -Architecture ohos-x64 -CompilerRecord <compiler-build.json> -AdapterRecord <adapter-build.json>
python scripts/inspect_rust_catalog_hap.py --hap <file> --architecture ohos-x64 --compiler-record <compiler-build.json> --adapter-record <adapter-build.json> --report <json>
```

The standalone entry is lib/main_catalog_audit.dart. Its separate application ID
is com.azurekiln.qfli.rust.audit. QFLI_RUST_AUDIT_BUILD_ID binds observed reports
to build metadata. Report schemas and exact fields are owned by rust_native_catalog.dart.

```dart
Future<RustNativeFeatureReport> runRustNativeFeatureAudit({
  required File reportFile,
  Duration checkTimeout = const Duration(seconds: 45),
  String auditBuildId,
  RustNativeFeatureAuditDependencies? dependencies,
  void Function(RustNativeFeatureResult)? onProgress,
});
Future<void> RustNativeFeatureCleanupFailure.retryCleanup();
```

Feature report schema1 and fixture checks live in rust_native_feature_audit.dart.

## 3. Contracts

- Inventory every existing example and answer, including desktop/cargo/external
  labels. Bind source, expected output, entry, bundle files and inputs to SHA256.
- A complete report requires exactly one matching result for each inventory ID.
  Derive missing IDs from evidence. Reject duplicates, unexpected IDs and altered
  source hashes/expectations. Recheck actual exit and asserted stdout even if a
  result claims passed. Runtime host/architecture/manifest must agree.
- Capture native stdout bytes before the runner's line decoder. Compare exact
  UTF8 output, allowing CRLF conversion only. LineSplitter loses final delimiter
  information and cannot establish exact stdout. Malformed UTF8 fails.
- Every invocation invalidates prior success before fallible preparation. Every
  atomic checkpoint contains runId and auditBuildId. Persist a timed-out case
  with interrupted/cancelling status before awaiting cooperative cleanup. Retain
  the live source directory and stop the loop until the actual worker exits.
- Main-entry Miri execution does not prove Cargo all-target builds/tests. Keep
  those report fields explicitly not_run. Host332 is not OHOS332.
- The isolated entry runs catalog then six native provider checks: valid and
  unsaved Unicode/CRLF module analysis, actual entry/step/breakpoint/scalars,
  live stdout/stderr followed by cancel130, fresh debug launch and no-argument
  native openUrl/openAgreement OFFLINE_ONLY refusals. Feature reports bind exact
  fixture hashes, runtime/manifest identity and build ID. Injected dependencies
  always produce passed=false. Shared UI/Problems/panels remain not_tested.
- Invalidate the feature report before catalog preparation, so an interrupted
  catalog cannot leave old feature success current. Cleanup failure retains the
  audit owner and cancelling/cleanupComplete=false checkpoint through a typed
  retry handle. Never await pending done after stop already failed: allow retry
  without releasing input ownership. Successful later cleanup leaves the audit
  interrupted and failed. It cannot convert the original run into acceptance.
- A failure-checkpoint write can itself fail. Retain the latest checkpoint and
  reportWriteError, then still attempt cleanup. Repeated report I/O failure must
  not bypass stop or discard the typed cleanup retry owner. Await the entire
  failed/timed-out check Future before deleting its input, including work after
  native cancellation. If stop fails, retain source and return the retry owner
  promptly instead of awaiting a done Future that cannot yet complete.
- The host harness prefers optional create_with_project and passes the complete
  materialized bundle directory, including for entries beneath src/. Record
  constructor, canonical source, materialized project, effective guest root,
  root-selection mode and backend. A rejected project constructor must not retry
  a weaker constructor. Legacy adapters may use an explicitly recorded
  source-parent fallback. Recheck this evidence when assessing/checkpointing.
- Audit HAP builds preserve production identity/signing inputs. Save and restore
  exact app/entry-profile/Hvigor bytes in finally, use typed enableSignTask=false,
  select the matching ABI filter and keep an immutable hash-named artifact.
  Final archive checks cover bundle, no Internet permission, generated catalogs,
  guest resources, ELF architecture and every manifest-covered native checksum.
- Require explicit trusted compiler and adapter build-record bytes at archive
  inspection. Bind their exact hashes to the manifest, their reviewed boundary
  identity to the pinned patch, and their adapter/compiler library hashes to
  packaged bytes. A manifest regenerated from an arbitrary library is insufficient.
  Do not follow producer paths from those records during archive inspection.
- Every regular native member must have the form libs/<selected-abi>/<name>.so.
  Allow ZIP directory entries. Reject foreign-ABI and top-level native payloads.
  Require the complete 27-symbol run/analysis/debug ABI regardless of matching
  manifest hashes. Static archive success keeps deviceExecuted false.
- Inspect current explicit device handoff before installation. Physical hardware
  needs matching signatures. Record normally accepted unsigned emulator execution
  honestly with emulator identity. A HAP build alone never establishes execution.

## 4. Validation & Error Matrix

| Condition | Required result |
| --- | --- |
| Empty/duplicate/mismatched results | Incomplete/failed |
| Extra/lost final newline or malformed bytes | Failed stdout comparison |
| New invocation fails before preparation | New interrupted report replaces old success |
| Timeout with live compiler | Durable error checkpoint, retain worker and inputs |
| Native cleanup failure | Retain retry handle/inputs, incomplete report. No terminal pass |
| Feature test with injected providers | checksPassed may be true. Passed remains false |
| HAP ABI/hash/catalog/permission differs | Static inspection failure |
| HDC process0 but textual install failure | No install/runtime pass |

## 5. Good / Base / Bad Cases

Good: current hash-bound inventory runs completely on the inspected matching
package with exact results. Base: a partial report remains inspectable after a
case fails. Bad: treating an empty result list with supplied missingIds=[] as a pass.

## 6. Tests Required

Run rust_native_catalog_test and rust_native_catalog_audit_test, the Python
native catalog/host verifier/inspect_rust_catalog_hap regressions, and generation
drift checks. Assert missing/duplicate/hash/output corruption, startup replacement,
exact full bundle overlays and timeout-before-runner-ready ownership. Rebuild and
execute actual native/device inventories separately after content/native changes.
Run rust_native_feature_audit_test for stale-success invalidation, identity,
exact diagnostic range, source retention, late launch, stop failure/retry and
report I/O failure cleanup. Execute all six checks on the matching packaged OHOS
runtime separately. Passing fake-provider lifecycle tests is not native evidence.

## 7. Wrong vs Correct

Wrong: join decoded lines, trim another newline and claim exact output.
Correct: preserve raw stdout and compare all bytes after only CRLF normalization.
