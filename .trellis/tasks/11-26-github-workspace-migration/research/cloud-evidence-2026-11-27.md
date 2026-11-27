# Cloud evidence - 2026-11-27

## Scope and evidence boundary

Read-only GitHub Actions metadata, logs, artifact metadata, and Git-object identity checks were inspected for runs `45916330398`, `45916330390`, `45916330453`, and `45894657258`. No run was started. No artifact was downloaded. No local build, test, lint, syntax check, restore, or generated output was run.

The three latest app-related runs use source commit `f226cf90b51e99c082db025336a17a963e544fd4`. Native run `45894657258` uses `a07511394cfc8a8079e226e37468c571b9d0ed1e`. The cloud checks and helper regressions validate source/workflow/helper contracts only; they are not application acceptance.

## 1. Cloud checks - run 45916330398

- Workflow: `Cloud checks`; event `push`; branch `main`; source `f226cf90b51e99c082db025336a17a963e544fd4`.
- Run conclusion: `success`.
- Per-job conclusions:

| Job | Conclusion | Job ID | Evidence scope |
| --- | --- | ---: | --- |
| Source, workflow and portability policy | success | 140236337951 | Source policy, workflow/action checks, committed operational syntax, source visibility, local-state exclusions, controlled-Chinese/native guidance |
| Python contracts (macos-15-intel) | success | 140236338123 | 105 application-helper tests plus native tests; application helper suites passed |
| Python contracts (ubuntu-24.04) | success | 140236338131 | 105 application-helper tests plus native tests; application helper suites passed |
| Python contracts (windows-2022) | success | 140236338226 | 105 application-helper tests plus native tests; application helper suites passed |

Application helper regressions did run on all three runners in this commit. This does not mean Flutter formatting, analysis, root application tests, Flutter builds, installers, signing, or device execution ran.

Cloud-check artifacts (all unexpired at inspection; 14-day retention):

| Artifact | Size (bytes) | Expires |
| --- | ---: | --- |
| `cloud-checks-macos-15-intel` | 11,221 | 2026-12-11 00:23:23Z |
| `cloud-checks-ubuntu-24.04` | 11,175 | 2026-12-11 00:22:51Z |
| `cloud-checks-windows-2022` | 11,237 | 2026-12-11 00:23:05Z |

## 2. App installers - run 45916330390

- Workflow: `App installers`; event `push`; branch `main`; source `f226cf90b51e99c082db025336a17a963e544fd4`.
- Run conclusion: `failure`.
- Orchestration helper jobs all passed:

| Job | Conclusion | Job ID |
| --- | --- | ---: |
| Orchestration checks (ubuntu-24.04) | success | 140236337500 |
| Orchestration checks (macos-15-intel) | success | 140236337821 |
| Orchestration checks (windows-2022) | success | 140236338154 |

- All seven platform jobs failed in the required preflight gate before core checkout, SDK setup, runtime selection, Flutter setup, application build, or packaging:

| Job | Conclusion | Job ID |
| --- | --- | ---: |
| android/arm64-x64 | failure | 140236451486 |
| ios/arm64 | failure | 140236451533 |
| ohos/arm64 | failure | 140236451601 |
| linux/x64 | failure | 140236451470 |
| windows/x64 | failure | 140236451492 |
| macos/arm64 | failure | 140236451481 |
| macos/x64 | failure | 140236451449 |

The logged preflight error requires the owner's final immutable core handoff through `QFLI_APPROVED_CORE_SHA`; selected and approved core SHAs must match. The run also had no approved SDK contract. Finalization and report-upload steps succeeded after the failures. Those outcomes do not mean any installer was built or verified.

The workflow reports were uploaded as these small failure-report artifacts (all unexpired at inspection; 14-day retention through 2026-12-11):

| Artifact | Size (bytes) | Expires |
| --- | ---: | --- |
| `app-installer-android-arm64-x64` | 3,624 | 2026-12-11 00:23:00Z |
| `app-installer-ios-arm64` | 3,289 | 2026-12-11 00:22:59Z |
| `app-installer-ohos-arm64` | 3,286 | 2026-12-11 00:22:54Z |
| `app-installer-linux-x64` | 3,242 | 2026-12-11 00:22:54Z |
| `app-installer-windows-x64` | 3,258 | 2026-12-11 00:23:00Z |
| `app-installer-macos-arm64` | 3,256 | 2026-12-11 00:22:56Z |
| `app-installer-macos-x64` | 3,254 | 2026-12-11 00:23:00Z |

No `app-intermediates-*` artifact exists for this run. The Linux log reports no intermediate files to upload. No Flutter packaging inputs, installer package, checksum-verified product, or installation result was produced. The successful artifact upload contains failure reports, not installer acceptance evidence.

## 3. Application quality - run 45916330453

- Workflow: `Application quality`; event `push`; branch `main`; source `f226cf90b51e99c082db025336a17a963e544fd4`.
- Run conclusion: `failure`.

| Job | Conclusion | Job ID | Evidence scope |
| --- | --- | ---: | --- |
| Quality helper contracts (no core required) | success | 140236337871 | Hermetic quality-helper regressions passed |
| Core-bound format, analysis and full root tests | failure | 140236338203 | Required preflight failed; quality preparation did not complete |

The core-bound job failed at the approval gate because `QFLI_APPROVED_CORE_SHA` was not supplied with the owner's final immutable handoff. The `format`, `analyze`, and `test` helper entry points later exited because the report was not prepared. The actual Dart formatter, analyzer, dependency-resolution/restore phase, and `flutter test --no-pub --machine test` suite did not execute. The final quality report was uploaded but is not a passing quality result.

| Artifact | Size (bytes) | Expires |
| --- | ---: | --- |
| `application-quality-linux-x64` | 4,882 | 2026-12-11 00:22:40Z |

## 4. Native runtime - run 45894657258

- Workflow: `Native runtime`; event `push`; branch `main`; source `a07511394cfc8a8079e226e37468c571b9d0ed1e`.
- Run conclusion: `success`; all six jobs succeeded.

| Job | Conclusion | Job ID |
| --- | --- | ---: |
| Shared Linux x64 MIR data | success | 140182880027 |
| ohos-x64 | success | 140183648523 |
| android-arm64 | success | 140183648528 |
| ohos-arm64 | success | 140183648540 |
| android-x64 | success | 140183648546 |
| ios-arm64 | success | 140183648564 |

This is native guest/compiler/adapter/runtime build evidence for the listed native targets. It is not evidence of Flutter application quality, Flutter application builds, installer verification, application signing, or device installation/testing. Android armv7 is not among the targets.

Native artifacts from this run (all reported unexpired at inspection):

| Artifact | Size (bytes) | Expires |
| --- | ---: | --- |
| `native-guest-sysroot` | 67,433,177 | 2026-11-27 21:43:59Z (one-day retention) |
| `native-diagnostics-guest` | 3,559 | 2026-12-10 21:44:01Z |
| `native-runtime-android-arm64` | 128,544,947 | 2026-12-10 22:02:11Z |
| `native-diagnostics-android-arm64` | 9,559 | 2026-12-10 22:02:13Z |
| `native-runtime-android-x64` | 128,566,749 | 2026-12-10 21:57:27Z |
| `native-diagnostics-android-x64` | 9,539 | 2026-12-10 21:57:30Z |
| `native-runtime-ohos-arm64` | 86,389,814 | 2026-12-10 22:03:11Z |
| `native-diagnostics-ohos-arm64` | 9,446 | 2026-12-10 22:03:12Z |
| `native-runtime-ohos-x64` | 86,138,119 | 2026-12-10 22:00:00Z |
| `native-diagnostics-ohos-x64` | 9,432 | 2026-12-10 22:00:02Z |
| `native-runtime-ios-arm64` | 76,132,526 | 2026-12-10 22:57:35Z |
| `native-diagnostics-ios-arm64` | 9,531 | 2026-12-10 22:57:40Z |

## 5. Native input identity comparison

Read-only Git object lookups compared the native run's source tree with current source `f226cf90b51e99c082db025336a17a963e544fd4`. All three producer inputs are byte-identical Git objects at the two revisions:

| Path | Native run `a075113` tree object | Current `f226cf9` tree object | Equal |
| --- | --- | --- | --- |
| `native` | `1d110a450f2145a41a10d78744b63758a74176ea` | `1d110a450f2145a41a10d78744b63758a74176ea` | yes |
| `scripts` | `42c9ee7a3c51ef884a168ad2f6bd8e7abf3f0de6` | `42c9ee7a3c51ef884a168ad2f6bd8e7abf3f0de6` | yes |
| `.github/workflows/native-runtime.yml` | `2b8f84117cdb8128cecf5afa3c8b07bce205fba5` | `2b8f84117cdb8128cecf5afa3c8b07bce205fba5` | yes |

This establishes exact Git-object identity for those three inputs only. It does not establish the missing app/core/SDK approvals or replace application-runtime producer verification and package-byte checks.

## 6. Blockers and limits (kept separate)

- **Core approval:** The final immutable core SHA has not been handed off. App installer and quality preflight require `QFLI_APPROVED_CORE_SHA`; `CORE_SHA` and `APPROVED_CORE_SHA` were empty in run logs.
- **SDK approval:** The approved SDK contract has not been handed off. The workflow expects `QFLI_CORE_SDK_CONTRACT`; `CORE_SDK_CONTRACT` was empty in run logs. The source's reviewed SDK baseline is not final Rust/core compatibility approval.
- **Native-hooks approval:** The Rust native-hooks recipe/compatibility approval is still absent. Matching native/script/workflow objects alone does not provide that approval.
- **Application checks/builds:** Application helper suites passed on three runners, and quality helper contracts passed. Flutter formatting, Dart analysis, full root tests, and all seven Flutter application builds/package jobs did not run successfully. The actual application checks remain pending.
- **Signing:** No app signing step or signed package completed. Intended package limits remain: Android debug/testing key is not store signing; iOS output would be unsigned and not device-ready; OHOS output would be unsigned and not signature-verified; Windows output would be unsigned; macOS ad-hoc output would not be notarized. No produced package proves any of these targets.
- **Device validation:** No application install/device/UI execution was performed. Native compilation is not device validation.
- **Android armv7:** Not present in the installer matrix and remains a separate unmet compiler/ELF32/ABI/Gradle/loader requirement. Two Android APK ABIs do not satisfy armv7 coverage.
- **GitHub variable/secret metadata:** Repository-level `gh variable list` and `gh secret list` returned no names. No values were requested or recorded. This check does not establish organization- or environment-level availability, nor is an empty repository list proof that all signing inputs are absent.

## 7. Current conclusion

The newest cloud checks establish successful source/workflow and Python-helper contracts. The native run establishes successful native runtime outputs, and the producer source objects match current native inputs. The app installer and application-quality runs are blocked before their actual app validation because final core/SDK approvals are absent. Do not mark application quality, six-platform installer acceptance, signing, device validation, Android armv7, core approval, SDK approval, or Rust native-hooks approval complete based on these runs.
