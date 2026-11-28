# Takeover repair and publication boundary — 2026-11-28

The coordinator resumed the existing approved migration task at published
`af4dc20f1489217283ba613424036f7fdd4d1415`. No new task or planning approval
was required. All executable validation remains GitHub-hosted.

## Reviewed repair

- P2 applied only the two formatter preview wraps to
  `test/rust_workspace_integration_test.dart`. P5 independently confirmed
  unchanged strings, callbacks, assertions and pump budgets.
- P3 bound iOS `FLUTTER_XCODE_PATH` to the resolved running Python directory
  followed by the runner PATH. The existing Flutter pass-through supplies an
  individual `PATH=...` argument to Xcode. P2 independently reviewed this and
  the regression. No blocking source finding remained.
- `--no-codesign`, `--verbose`, release plugin generation, core/vendor/lock
  checks and other platform commands remain intact. This is a source review,
  not a hosted pass for the new revision.

The immutable SDK is `adaf911c35c9136a7d18fc424d714c9ec7724e60`.
Its `packages/flutter_tools/lib/src/ios/xcodeproj.dart:347-365` maps
`FLUTTER_XCODE_*` keys to Xcode build settings. Its `ios/mac.dart:524` adds
them and lines 744-748 execute the argument list. Apple Run Script build
phases receive command-line build settings in their environment.
The existing `ios/Runner.xcodeproj/project.pbxproj:229-240` invokes
`scripts/embed_miri_frameworks.sh`, whose line 4 executes bare `python3`.

Observed installer failure: run `46113314581`, job `140881573041`,
`2026-11-28T05:52:35.0124870Z`, embedding calls `hashlib.file_digest` and
raises `AttributeError`. Outer setup-python reports 3.13.15. The phase's own
interpreter path/version was not printed. An older interpreter is inferred;
the missing API is measured. Generic Development Team advice does not change
that diagnosis or authorize signing claims.

Runtime provenance inputs remain:

| Git object | Identity |
| --- | --- |
| `scripts` tree | `42c9ee7a3c51ef884a168ad2f6bd8e7abf3f0de6` |
| `native` tree | `1d110a450f2145a41a10d78744b63758a74176ea` |
| `.github/workflows/native-runtime.yml` blob | `2b8f84117cdb8128cecf5afa3c8b07bce205fba5` |
| Approved core | `8e031313ffc8d531c5a6b4d131f721f35da04c86` |

## Receipt and acceptance

The recovered historical ACK and dated clean source/target parity are in
`parity-receipt-af4dc20-2026-11-28.md`. The receiver repeated target-only
measurements at 21:04:12 +08:00, then reconfirmed GitHub-only fetch/push at
21:16:24. It found clean `af4dc20`, tree
`a95983ec81000ec128b2161bc877bd970d4b7c75`, 875 rows and zero differences
against the immutable source commit. It explicitly excluded CI/product
acceptance and current source cleanliness after repairs began.

The coordinator archived the old `8b92ddc` migrated receipt and refreshed
`D:/MyNewProjects/_orchestra/status/qflistudio-rust.migrated.json` with the
`af4dc20` gate, parity, ACK and real CI outcomes. The receipt separately records
the later dirty repair state. Current orchestration receiver is `w65:pD`;
the requested old `w65:pC` no longer exists. That routing change was confirmed
by the takeover operator.

The repair publication requires an exact-SHA gate request, a matching PASS,
fresh target comparison and ACK, plus final-SHA hosted quality evidence.
The sole watcher records installer outcomes without claiming unsigned outputs,
native skips or reports-only artifacts as device/product acceptance.
Planning-only `11-27-rust-compatibility-followups` retains SDK/native-hooks,
signing, device/UI, armv7, receiver-hook and missing installer acceptance.

No local checks, builds, dependency restore/install, artifact downloads, WSL,
direct push, scheduler restart, stash mutation or cleanup occurred. Both
preservation stashes, baselines, originals, backups and ignored state remain
held. Migration completion does not authorize source retirement.

## Hosted checkpoint at 2afc72c — 2026-11-28

This section appends later evidence without rewriting the historical review.
It uses the sole watcher's frozen local record:
`D:/MyNewProjects/_orchestra/status/qflistudio-rust.ci-watch.json#exact_2afc72c`.
P4 froze that record at `2026-11-28T14:09:41.8337404+00:00`
(`22:09:41.8337404+08:00`). P5 read the supplied record only; no new CI query,
local executable check or artifact download was performed for this appendix.

### Published revision, clean snapshot and ACK

- Source, GitHub main and target matched
  `2afc72c3b4fa3e51580bc6b3ec06c6ce363e893c` after gate PASS at
  `2026-11-28 21:57:04 +08:00`; `push_rc=0`, no warnings or problems.
- Independent parity froze at `21:59:39.3603162+08:00`: both full non-ignored
  statuses were empty, tree `87cf768a53ec503ad807564e2c67689bc274a200`,
  878 mode/type/blob/size/path rows each, zero differences and GitHub-only
  fetch/push endpoints. The dated record is
  `D:/MyNewProjects/_orchestra/status/qflistudio-rust.target-audit-2afc72c.json`.
- Receiver `w6C:p1` independently measured the exact target at
  `21:59:12.2141997+08:00`. Its ACK is preserved in
  `D:/MyNewProjects/_orchestra/status/qflistudio-rust.handover-ack-2afc72c.txt`.
  It confirms the exact SHA/tree, 878 rows, clean target and committed cloud
  rules. It excludes CI/product acceptance and current source cleanliness.
- Both preservation stashes, originals, backups and ignored inventories remain
  held. This appendix makes the source worktree dirty; the preceding clean
  snapshot and exact-SHA ACK are historical observations, not current-clean
  claims or permission to retire the old source.

### Exact-SHA hosted quality

All three workflows below ran on push/main at the exact `2afc72c` revision,
run attempt 1. Core remains `8e031313ffc8d531c5a6b4d131f721f35da04c86`.
SDK remains Flutter-OH `3.41.10-ohos-1.0.1` at
`adaf911c35c9136a7d18fc424d714c9ec7724e60`, with Dart `3.11.5` and engine
`42d3d75a56efe1a2e9902f52dc8006099c45d937`.

| Workflow / run | Frozen hosted outcome |
| --- | --- |
| [Cloud checks 46152144084](https://github.com/azurekiln2333/qflistudio-rust/actions/runs/46152144084) | PASS, all four jobs; each OS ran 291 native-helper and 182 application-helper tests, with platform-specific native-helper skips retained. |
| [Application quality 46152143988](https://github.com/azurekiln2333/qflistudio-rust/actions/runs/46152143988) | PASS, helper job `141000884441` (101 tests) and core-bound job `141000884756`; strict preparation, both verified OHOS asset inputs, finalization and report upload succeeded. |
| [App installers 46152143967](https://github.com/azurekiln2333/qflistudio-rust/actions/runs/46152143967) | FAIL, all three orchestration jobs and six of seven platform jobs passed; iOS failed. |

The real formatter command reported `Formatted 46 files (0 changed) in
0.18 seconds.` Analysis reported `No issues found! (ran in 12.7s)`.
The complete root command was `flutter test --no-pub --machine test`:
354 completed, 334 passed, 20 skipped, zero failed and 22 suite files.
`protocolDone=true`, `success=true`; errors, framework exceptions, missing
suites and unfinished test IDs were empty. The root result is a pass with
skips, not all-checks or target-device acceptance.

Eight real native rustc/Miri session cases remained skipped because a matching
native library/sysroot was unavailable. No exact-SHA Native runtime run was
listed. Quality used packaged OHOS assets from historical producer
`45894657258` at `a07511394cfc8a8079e226e37468c571b9d0ed1e`; verified asset
preparation does not establish executed native libraries, native hooks or
production SDK compatibility.

### Final installer outcomes and repeated iOS failure

| Platform | Job | Frozen result and signing boundary |
| --- | --- | --- |
| Android arm64/x64 | `141001008918` | Build/package passed; two test-signed APKs, debug key only, no store signing or armv7 result. |
| Windows x64 | `141001008921` | Build/package passed; setup EXE uses the unsigned-executable contract, not an independent Authenticode or application/UI acceptance claim. |
| OHOS arm64 | `141001008929` | Build/package passed; unsigned HAP requires signing before device deployment. |
| Linux x64 | `141001008938` | Build/package passed; DEB signing is not applicable; no application/UI acceptance claim. |
| macOS arm64 | `141001008953` | Build/package passed; ad hoc signature, not notarized. |
| macOS x64 | `141001008963` | Build/package passed; ad hoc signature, not notarized. |
| iOS arm64 | `141001008941` | Build failed, packaging skipped; unsigned build requested, no verified IPA or iOS intermediate artifact. |

The repeated concrete iOS exception occurred at
`2026-11-28T14:04:46.5932100Z` during `Embed Rust Runtime`:
`scripts/miri_build_support.py:41` called `hashlib.file_digest` and raised
`AttributeError: module 'hashlib' has no attribute 'file_digest'`.
The earlier PATH-based binding did not resolve this hosted failure. The
missing API is measured; the Xcode child executable, Python version and
`hashlib` module origin remain unknown. The setup-python 3.13.15 path does
not establish the child interpreter identity. Generic Development Team advice
is not evidence that signing caused this exception.

Failure reports were uploaded, but packaging was skipped and
`app-intermediates-ios-arm64` was absent. The installer-named iOS artifact is
not a successful IPA. The frozen watcher recorded 17 output artifacts:
three Cloud, one quality, seven installer-named and six intermediates.
Their IDs, sizes, uploaded-archive SHA-256 digests and expiry times remain in
the exact-SHA record. These are metadata, not independently inspected package
contents or member hashes. No unchanged CI rerun or pre-migration waiver is
claimed.

### Proposed next correction and remaining boundary

The next direct-interpreter correction is **proposed/pending**, not successful
at this revision: bind the actual embed phase to an explicit hosted Python
executable rather than relying only on PATH precedence. Its source changes,
review and exact-next-SHA hosted execution remain separate gates. Do not infer
a successful correction from the earlier source review or the green quality
workflow. If approved changes touch native producer identity inputs, recheck
producer compatibility before reusing historical runtime archives.

Any new publication requires the orchestration gate, renewed clean tracked
parity, a new exact-SHA receiver ACK and final-revision hosted evidence.
Production signing, devices/UI, Android armv7, SDK/native-hooks compatibility,
receiver-hook execution and missing installer acceptance remain explicit
follow-ups. This checkpoint does not claim full product acceptance or remove
preservation and retirement holds. P5 appended only this assigned document;
no status receipt or other worker file was edited, and no Git mutation was
performed by P5.

## Later source-review checkpoint — 2026-11-28

P3 completed direct interpreter binding in `app_build.py`, its hosted
regression source and the iOS Embed Rust Runtime phase. P2 approved the final
diff. `FLUTTER_XCODE_QFLI_RUNTIME_PYTHON` carries resolved `sys.executable`;
the phase reads the exported setting, validates an explicit absolute regular
executable and quotes both executable and Python script paths. Exact-name
`printenv` detection preserves fallback only for an absent setting. The
decoded PBX phase regression covers paths with spaces, invalid values,
unrelated multiline environment data, fallback and exit propagation.
It models environment injection, not Xcode internals. Actual hosted helpers
and iOS execution remain pending for the next published revision.

The external CI record was truncated by a watcher metadata command at
14:11:11Z and recovered from retained local output. Raw original pages,
backups and incident provenance remain external. P5 verified all 23 legacy
top-level values, with only 17 same-instant timestamp presentation changes,
and all 17 output artifact rows per revision plus five historical producer
rows. P4 corrected two attribution errors before P5 accepted the recovery:
mixed platform log lines are explicitly unattributed, and a superseded
quality-helper transport failure is outside Cloud totals. Missing interim
and per-step fields remain disclosed. No CI reread, product/Git mutation or
invented child-interpreter identity was used to restore the record.
