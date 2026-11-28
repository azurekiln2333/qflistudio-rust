# Exact af4dc20 CI evidence - 2026-11-28

## Scope and freeze
- Task: `.trellis/tasks/11-26-github-workspace-migration`.
- Sole watcher: `w61:p4`, `gpt-6.1-sol`. Evidence collection ended at `2026-11-28T12:52:31.7008080Z`.
- App SHA: `af4dc20f1489217283ba613424036f7fdd4d1415`. All three runs: push/main, attempt 1, completed.
- Exact-SHA run inventory returned three workflows. No exact-SHA Native runtime run was listed.
- Gate receipt: `D:/MyNewProjects/_orchestra/push/qflistudio-rust.result.json`, commit equal to the app SHA, `ok=true`, `push_rc=0`, `checked_at=2026-11-28 13:42:23` (verbatim).
- The receipt was inspected during persistence follow-up, not before this fresh session's initial user-requested run reads. Do not claim otherwise.
- Sources: GitHub REST run/job/artifact metadata and public job text logs. No artifact archives or members were downloaded or inspected.
- Frozen after this report and the CI-watch update. No new CI reads until the coordinator supplies the exact next gate PASS.

## Runs and jobs
| Workflow / run | Conclusion | Jobs |
| --- | --- | --- |
| [Cloud checks 46113314638](https://github.com/azurekiln2333/qflistudio-rust/actions/runs/46113314638) | success | 4/4 success |
| [Application quality 46113314596](https://github.com/azurekiln2333/qflistudio-rust/actions/runs/46113314596) | failure | helper success; core-bound job failure |
| [App installers 46113314581](https://github.com/azurekiln2333/qflistudio-rust/actions/runs/46113314581) | failure | 3/3 orchestration and 6/7 platform jobs success |

Cloud jobs: source/workflow/portability `140881457378`; Windows Python `140881457532`; macOS Intel Python `140881457561`; Ubuntu Python `140881457567`. All succeeded.
Ubuntu logs: native helpers `Ran 291 tests in 16.945s`, `OK (skipped=3)`; application helpers `Ran 181 tests in 1.394s`, `OK`.
Windows/macOS helper totals remain unknown because bounded text-log reads failed; their job conclusions are success.
Quality helper job `140881457449`: success, `Ran 101 tests in 1.081s`, `OK`.

## Quality inputs and exact outcomes
- Core: `8e031313ffc8d531c5a6b4d131f721f35da04c86`, observed as `CORE_REF`, `CORE_SHA` and `APPROVED_CORE_SHA`.
- SDK contract: `flutter-oh-3.41.10-ohos-1.0.1@adaf911c35c9136a7d18fc424d714c9ec7724e60`.
- Observed SDK identity: Flutter `3.41.10-ohos-1.0.1`, framework revision `adaf911c35c9136a7d18fc424d714c9ec7724e60`, Dart `3.11.5`, engine `42d3d75a56efe1a2e9902f52dc8006099c45d937`.
- [Core-bound job 140881457317](https://github.com/azurekiln2333/qflistudio-rust/actions/runs/46113314596/job/140881457317): core/SDK verification, both OHOS asset verification/install, and strict dependency preparation all succeeded (steps 7-14).
- Quality selected native producer `45894657258`, source `a07511394cfc8a8079e226e37468c571b9d0ed1e`, successful push/main, attempt 1. Only packaged asset bytes were supplied to quality, not executed native libraries.
- Step 15 **failed**: `dart format --output=none --set-exit-if-changed lib test integration_test`; exit 1, `Changed test/rust_workspace_integration_test.dart`, `Formatted 46 files (1 changed) in 0.23 seconds.`
- Step 16 **passed**: `flutter analyze --no-pub`; `No issues found! (ran in 15.9s)`.
- Step 17 **passed with skips**: `flutter test --no-pub --machine test`.
- Complete public root summary: **354 completed, 334 passed, 20 skipped, 0 failed**, `protocolDone=true`, `success=true`, `scope=full_root_test_directory`, `rawReportPublished=false`.
- Summary arrays: `errors=[]`, `frameworkExceptions=[]`, `missingSuiteFiles=[]`, `unfinishedTestIds=[]`; 22 suite files listed. Protocol terminal event: `success=true`, `time=50050`.
- Native real-session group explicitly skipped eight cases: `Matching native library/sysroot are not available`. Do not count these as executed native passes.
- Visible drawer-reopening test `434` completed successfully. No failed framework diagnostic block appears in the complete summary.
- Step 18 **failed downstream**: `Quality job did not complete all required stages`. Report upload step 19 succeeded; overall quality remains failure.
- Formatter log exposes exactly two wrapping hunks in `test/rust_workspace_integration_test.dart`:
```diff
@@ -156,7 +156,8 @@
-        reason: 'Sidebar reopen: the secondary nested leaf must remain visible.',
+        reason:
+            'Sidebar reopen: the secondary nested leaf must remain visible.',
@@ -188,7 +189,8 @@
-        failureDetails: () => 'Reconstruction: both nested leaves must restore.',
+        failureDetails: () =>
+            'Reconstruction: both nested leaves must restore.',
```

## Installer jobs and signing boundaries
Orchestration jobs all succeeded: macOS Intel `140881457186`, Ubuntu `140881457337`, Windows `140881457371`.
Each platform job URL is `https://github.com/azurekiln2333/qflistudio-rust/actions/runs/46113314581/job/<job-id>`.
| Target | Job ID | Build / package | Package name and evidence boundary |
| --- | --- | --- | --- |
| windows/x64 | 140881573044 | success / success | `QFLIRustCore-windows-x64-setup.exe`; unsigned; hosted silent install/uninstall succeeded, not application launch/UI acceptance |
| linux/x64 | 140881573121 | success / success | `QFLIRustCore-linux-x64.deb`; hosted install/remove of `qfli-rust-core` `1.0.0+1` succeeded; no application launch/UI result |
| macos/arm64 | 140881573033 | success / success | `QFLIRustCore-macos-arm64.dmg`; architecture/signature checks and read-only mount succeeded; `Signature=adhoc`, no team, not notarized |
| macos/x64 | 140881573084 | success / success | `QFLIRustCore-macos-x64.dmg`; same boundary, x86_64 verified; ad hoc, not notarized |
| android/arm64-x64 | 140881573042 | success / success | `QFLIRustCore-android-arm64-v8a-test-signed.apk` and `QFLIRustCore-android-x86_64-test-signed.apk`; zipalign 16 KiB/apksigner passed; debug testing key, not store signing |
| ohos/arm64 | 140881573053 | success / success | `QFLIRustCore-ohos-arm64-v8a-unsigned.hap`; unsigned, manual signing required before device deployment |
| ios/arm64 | 140881573041 | failure / skipped | No verified IPA; unsigned build requested; installer-named artifact is failed-job reports |

- Android certificate SHA-256: `4529c1edcbf84c91d176f344d5178ee7aea1fc1877a151a5a8df1b4ed722835e`, DN `C=US, O=Android, CN=Android Debug`.
- Mobile installers selected native run `45894657258`. Android NDK `27.0.12077973` was installed on the hosted runner.
- iOS [job 140881573041](https://github.com/azurekiln2333/qflistudio-rust/actions/runs/46113314581/job/140881573041), step 19 `Build release application`: Xcode `Embed Rust Runtime` -> `scripts/embed_miri_frameworks.py:56` -> `scripts/miri_build_support.py:41` -> `AttributeError: module 'hashlib' has no attribute 'file_digest'` at `2026-11-28T05:52:35.0124870Z`.
- Actual iOS command retained `--no-codesign --verbose`. Generic Development Team advice follows the concrete Python exception; it is not proof signing caused this failure. Workflow Python path was `.../Python/3.13.15/x64`; Xcode child interpreter identity is unknown.
- iOS step 20 packaging was skipped. Finalization and report upload succeeded while recording failure. Intermediate upload warned no files; `app-intermediates-ios-arm64` is absent.
- Signing labels/package names also match committed `ci_support.py`/`package_installer.py` at the exact app SHA; source contracts are not independent package-member inspection.

## Output artifact metadata
All entries below report `expired=false` at collection. Digests are GitHub **uploaded-archive** SHA-256 digests, not independently verified package-member hashes. The first four entries expire on 2026-12-12; installer archives expire on 2026-12-12 and intermediate archives on 2026-11-29 at the listed UTC time.
| Name | Artifact ID | Bytes | SHA-256 archive digest | Expiry UTC |
| --- | --- | --- | --- | --- |
| cloud-checks-windows-2022 | 15251001114 | 14659 | `1c6a051cbb7a3d89f3a34ed5d1b6b84c706fcd76bb57a5ad0d308e91d3fdf6a3` | 12-12 05:42:59 |
| cloud-checks-ubuntu-24.04 | 15250946854 | 14566 | `64515727e02e54da5667318bb416f49b57b26594469c66bd654d0001c30392c1` | 12-12 05:43:17 |
| cloud-checks-macos-15-intel | 15250223316 | 14613 | `9789d169dbda21feaefae2e2aa4d8125616b12c3b55649aa0e8aa5b2895b5a62` | 12-12 05:43:49 |
| application-quality-linux-x64 | 15250546940 | 329259 | `669b8a9821e2f140a533a2c4930b92f613bbcace23da7adf8fdac8e4abc5c490` | 12-12 05:45:25 |
| app-installer-windows-x64 | 15250383515 | 18842790 | `10b3fcf3c3586dcba88fcfa21bc347577a0f185464cd732f15dc00377c778aed` | 12-12 05:47:17 |
| app-installer-linux-x64 | 15251076020 | 24082631 | `75c5822f007a42b54653b83e2b2b15c268a8b8f7bc10cdd024590a52b858e7a9` | 12-12 05:47:18 |
| app-installer-macos-arm64 | 15250768195 | 17842227 | `d18a27149fcd6a298102cbb29c351cca6dec2025e84bbb50d0333fc7b3eec62d` | 12-12 05:49:52 |
| app-installer-macos-x64 | 15251147035 | 19223954 | `03a80c8b970b670b716186b1910ac7bcd308b7ff62af9b5aee8f619b3e038878` | 12-12 05:57:06 |
| app-installer-android-arm64-x64 | 15250358869 | 196970086 | `9c09d96d0d1e39e891945762da7343586b4b25c533ebcb7cadd32b1489073530` | 12-12 05:49:38 |
| app-installer-ohos-arm64 | 15250767890 | 359971584 | `804079418d388f563b5bfbfb122034e77758b55b0b84b203fe8ef08da4df3617` | 12-12 05:47:51 |
| app-installer-ios-arm64 (failure reports) | 15250189574 | 1480803 | `14ca5356c456889b39f4834446f00f553dd09580c11866da136fab637835fef5` | 12-12 05:52:36 |
| app-intermediates-windows-x64 | 15250114163 | 23732459 | `5fb62254ba340c2368932e85acd102ce6b614e5f40c651b3caaaf3bc16e41a7c` | 11-29 05:47:19 |
| app-intermediates-linux-x64 | 15250603178 | 30171502 | `6afc45b0edf3ba8564dcf46710a1ba1e934f21c064089174bc6784a788067397` | 11-29 05:47:19 |
| app-intermediates-macos-arm64 | 15251066506 | 15856779 | `5e8995dd1cba3b568583cf094ace9d5779291534d87bfd3b347e153effd89369` | 11-29 05:49:55 |
| app-intermediates-macos-x64 | 15250684376 | 16930373 | `02667da9d60c962b112eba7be79d373eb04383c7e992a0bf1fbdab1d1b2bffc6` | 11-29 05:57:11 |
| app-intermediates-android-arm64-x64 | 15250319019 | 193913581 | `777e8f157288af4e41d3e3e9e7b0fdb8240ef84c660db2e815778f8c3e4eb8f5` | 11-29 05:49:40 |
| app-intermediates-ohos-arm64 | 15250707999 | 104249955 | `182261b4bc0654aba6b9cfe529bb79c846b3c821b05fc840c14eba3b48c4e5f3` | 11-29 05:47:54 |

## Reused producer inputs
[Native producer 45894657258](https://github.com/azurekiln2333/qflistudio-rust/actions/runs/45894657258) is historical input evidence, not an exact-af4dc20 native build. Its selected runtime metadata was unexpired. Quality used both OHOS entries; installers used their applicable mobile entries.
| Artifact name | ID | SHA-256 archive digest |
| --- | --- | --- |
| native-runtime-ohos-arm64 | 15155258958 | `86be112f8dee86eefc0c4230a434de01795e3a7b0c79524f595c6484c6f108da` |
| native-runtime-ohos-x64 | 15155143780 | `bc34f5396a0208f9accf8bbe9c70224b592edf75584f6ab3eeeb04e22961aa6a` |
| native-runtime-android-arm64 | 15156108223 | `8566283b374320dc3bb2e036a3207be780c18ce9d2d720568f579a47ee5884cc` |
| native-runtime-android-x64 | 15155672582 | `f0e37966d86f9fb6592672a288c67cc2f566e26d9001cef92b1c65b3accbb030` |
| native-runtime-ios-arm64 | 15159405814 | `9b6fcacd85e9abfc977a1151a06fe881ff764f44cfed25122a7ebedf31f5a499` |

## Disposition and local evidence
- Formatting and the repeated iOS Python API/interpreter failure are not infrastructure-only failures. No rerun or pre-migration waiver is claimed.
- Production signing, device/UI execution, Android armv7, native-hooks/SDK product compatibility and receiver-hook acceptance remain unestablished.
- Companion status: `D:/MyNewProjects/_orchestra/status/qflistudio-rust.ci-watch.json`, new `exact_af4dc20` record. Previous observations remain historical snapshots.
- No local build/test/analyzer/formatter/install/restore, WSL execution, Git mutation, workflow rerun/dispatch, or artifact download occurred. Only these two assigned evidence paths were authored.
- Text-log transport retries are read retries, not CI reruns. No repeated status-poll loop was used. Unknown helper totals were not inferred.
