# Hosted cloud evidence at 443c988

## Frozen scope and authority

- Task: `.trellis/tasks/11-26-github-workspace-migration`.
- Worker: Herdr `w61:p2`, model `gpt-6.1-sol`. Coordinator: `w61:p1`.
- Inspected on 2026-11-27, after all three requested runs completed.
- Only this research file is worker-owned. No other source/task/spec edits, Git writes, subagents, workflow dispatches, local checks or artifact downloads were performed.
- Evidence comes from `gh api` run/job/artifact metadata and hosted job text logs. Artifact archives and their internal reports were not opened. Sizes below are GitHub `size_in_bytes` ZIP sizes, not installer payload sizes. Digests are GitHub archive metadata, not independently recomputed package hashes.
- Read `AGENTS.md`, the cloud-only workspace policy, task artifacts, `D:/MyNewProjects/_orchestra/qfli-unified-migration.md` and `D:/MyNewProjects/_orchestra/decisions/qflistudio-rust.md`.
- The 2026-11-27 14:35 ruling makes actual hosted format, analysis and full root tests required migration gates. Installer gaps, SDK/native-hooks compatibility, signing, device/UI, armv7 and receiver-hook evidence remain explicit follow-ups. This report does not complete migration or product acceptance.

## 1. Immutable run and input identities

Repository: `azurekiln2333/qflistudio-rust`.
All requested runs are `push` on `main`, attempt **1**, at application SHA
`443c9887e6ab9e2c22d96ced491f06145aa74d66`.

| Workflow | Run | Source workflow | Started (UTC) | Final update (UTC) | Conclusion |
| --- | ---: | --- | --- | --- | --- |
| App installers | [45966800141](https://github.com/azurekiln2333/qflistudio-rust/actions/runs/45966800141) | `.github/workflows/app-installers.yml` | 2026-11-27 08:35:06 | 2026-11-27 08:41:31 | failure |
| Application quality | [45966799846](https://github.com/azurekiln2333/qflistudio-rust/actions/runs/45966799846) | `.github/workflows/app-quality.yml` | 2026-11-27 08:35:06 | 2026-11-27 08:36:48 | failure |
| Cloud checks | [45966800064](https://github.com/azurekiln2333/qflistudio-rust/actions/runs/45966800064) | `.github/workflows/cloud-checks.yml` | 2026-11-27 08:35:06 | 2026-11-27 08:36:10 | success |

Installer and quality logs bind `CORE_REF`, `CORE_SHA` and `APPROVED_CORE_SHA`
to `476a30acee21dc486ee2849dd8064a7be665e4d5` from
`azurekiln2333/qflistudio-core`. They select the exact SDK contract
`flutter-oh-3.41.10-ohos-1.0.1@adaf911c35c9136a7d18fc424d714c9ec7724e60`.
The SDK checkout is `openharmony-tpc/flutter_flutter`, tag
`3.41.10-ohos-1.0.1`, fetched through its GitCode origin. Successful SDK version
logs report Flutter `3.41.10-ohos-1.0.1`, framework revision
`adaf911c35c9136a7d18fc424d714c9ec7724e60`, engine revision
`42d3d75a56efe1a2e9902f52dc8006099c45d937` and Dart `3.11.5`.

All seven installer targets passed migration pin/preflight, core checkout and
core/package-path verification. Quality passed those gates and SDK preparation.
The older missing-approval diagnosis does **not** describe these runs. The
migration pin/recipe selection is not final production compatibility approval.

## 2. App installers: every platform target

All target jobs ran in the `GitHub Actions` runner group. All seven concluded
`failure`. Every `Package and verify installer` step (19) was `skipped`.
Finalization (20) and report upload (21) succeeded for every target. Neither
success establishes application build, packaging, signing or installation.

| Target | Hosted runner | Job ID / log | First failed step | First actual error and later diagnostic |
| --- | --- | --- | --- | --- |
| Android arm64/x64 | `ubuntu-24.04` | [140397607493](https://github.com/azurekiln2333/qflistudio-rust/actions/runs/45966800141/job/140397607493) | 18: Build release application | First error output: Kotlin daemon terminated on startup attempt 1 with code 0. The fatal Gradle configuration diagnostic is `Conflicting configuration : 'arm64-v8a,x86_64' in ndk abiFilters cannot be present when splits abi filters are set : x86_64,arm64-v8a`. Gradle names `android/build.gradle.kts:19` while configuring `:app`. `assembleRelease` exits 1. |
| iOS arm64 | `macos-15-intel` | [140397607498](https://github.com/azurekiln2333/qflistudio-rust/actions/runs/45966800141/job/140397607498) | 17: Prepare pinned Flutter SDK | `flutter precache --ios` cannot download `sky_engine.zip` from `flutter-ohos.obs.cn-south-1.myhuaweicloud.com`: `SocketException: Failed host lookup` (`nodename nor servname provided, or not known`, errno 8). Build step 18 is skipped. |
| OHOS arm64 | `ubuntu-24.04` | [140397607432](https://github.com/azurekiln2333/qflistudio-rust/actions/runs/45966800141/job/140397607432) | 18: Build release application | First compiler error: `../qflistudio-core/lib/remote_control/models/herdr.dart:753:7: Error: Type 'UnicodeV11' not found.` Later errors include num-to-int assignments at lines 742, 746 and 908, missing `UnicodeV11` constructor/type, and `xterm-4.0.0/lib/src/ui/shortcut/shortcuts.dart:6:11` not exhaustively matching `TargetPlatform.ohos`. Kernel snapshot/Hvigor build fails. |
| Linux x64 | `ubuntu-24.04` | [140397607501](https://github.com/azurekiln2333/qflistudio-rust/actions/runs/45966800141/job/140397607501) | 18: Build release application | CMake `FindPkgConfig.cmake:645`: required `libsecret-1>=0.18.4` not found. Caller: `flutter_secure_storage_linux/linux/CMakeLists.txt:15`. `Unable to generate build files`; Flutter exits 1. |
| Windows x64 | `windows-2022` | [140397607536](https://github.com/azurekiln2333/qflistudio-rust/actions/runs/45966800141/job/140397607536) | 17: Prepare pinned Flutter SDK | `UnicodeEncodeError: 'charmap' codec can't encode characters in position 28-30: character maps to <undefined>`. Trace: `app_build.py:660` calls `git checkout --detach refs/tags/3.41.10-ohos-1.0.1`; `ci_support.py:253` calls `print_untrusted`, line 197 prints to cp1252 stdout. This is a logging/console-encoding failure, not evidence that Git checkout itself failed. Build step 18 is skipped. |
| macOS arm64 | `macos-26` | [140397607481](https://github.com/azurekiln2333/qflistudio-rust/actions/runs/45966800141/job/140397607481) | 18: Build release application | First fatal compiler error is the same `herdr.dart:753:7` missing `UnicodeV11`. Later num-to-int and xterm `TargetPlatform.ohos` exhaustiveness errors appear. Earlier Metal-toolchain Swift search-path messages are linker warnings, not the first fatal error. Xcode/Flutter build exits 1. |
| macOS x64 | `macos-15-intel` | [140397607479](https://github.com/azurekiln2333/qflistudio-rust/actions/runs/45966800141/job/140397607479) | 18: Build release application | First compiler error is the same `herdr.dart:753:7` missing `UnicodeV11`. Later num-to-int and xterm `TargetPlatform.ohos` exhaustiveness errors appear. Kernel snapshot and Xcode PhaseScriptExecution fail. |

Diagnostic log timestamps (UTC) are 08:39:38 for Android, 08:39:10 for iOS,
08:39:47 for OHOS, 08:38:21 for Linux, 08:36:24 for Windows, 08:40:01 for
macOS arm64 and 08:41:16 for macOS x64. Helper output is buffered; these are
published log timestamps, not precise first-occurrence times inside subprocesses.
The echoed shell branch containing `core_sha must be ...` is script text, not
an executed failure: the pin-binding step passed.

### Successful orchestration jobs, separate from application results

| Hosted job | Job ID | Conclusion | Actual regression count |
| --- | ---: | --- | --- |
| Orchestration checks (`ubuntu-24.04`) | 140397300911 | success | 105 tests, OK |
| Orchestration checks (`windows-2022`) | 140397301277 | success | 105 tests, OK |
| Orchestration checks (`macos-15-intel`) | 140397301431 | success | 105 tests, OK |

Workflow parsing/pinned-action verification executed on Ubuntu. Its matrix
copies on Windows/macOS were deliberately skipped. Do not describe those
skipped steps as executions on all three hosts.

### Uploaded installer-run artifacts

The run's complete artifact listing contains **seven** `app-installer-*`
artifacts and **zero** `app-intermediates-*` artifacts. Every target's intermediate
upload log says `No files were found ... No artifacts will be uploaded`.
The intermediate upload step's `success` conclusion therefore does not mean an
intermediate artifact exists. No verified installer publication completed.
The seven named artifacts retain failure diagnostics/provenance, not accepted
installer packages. This classification follows failed/skipped stages and
upload logs; archive contents were not independently inspected.

All seven artifacts were unexpired at inspection. Retention is 14 days.

| Artifact name | Artifact ID | ZIP bytes | Expires (UTC) |
| --- | ---: | ---: | --- |
| `app-installer-android-arm64-x64` | 15182519978 | 1,205,640 | 2026-12-11 08:39:39 |
| `app-installer-ios-arm64` | 15183666247 | 573,230 | 2026-12-11 08:39:11 |
| `app-installer-ohos-arm64` | 15183601837 | 668,711 | 2026-12-11 08:39:47 |
| `app-installer-linux-x64` | 15182714842 | 100,578 | 2026-12-11 08:38:21 |
| `app-installer-windows-x64` | 15182624771 | 5,666 | 2026-12-11 08:36:24 |
| `app-installer-macos-arm64` | 15183192791 | 102,959 | 2026-12-11 08:40:04 |
| `app-installer-macos-x64` | 15183083188 | 101,865 | 2026-12-11 08:41:17 |

GitHub archive SHA-256 metadata, keyed by artifact ID:

```text
15182519978 bffb454adaff0231348aa31f4f1200f588d14b53353239e23bb09f4c94ff62c9
15183666247 c17a167c1b3b766f62a9ba14d670c65f816c66cda739989914210f72bb98a39e
15183601837 e31bd489dfe23e34f0015564f80f866e01f6f47f2dad6565e6ecf971a20a98fa
15182714842 a9edb8151c7f843b2161f2a9702e0f955923870983a20d45605c58754652ccf5
15182624771 8ec2de43285d7bb39f18e46a81ba6776d35fee63a05b81517a7f8463feb2ce59
15183192791 272b33dc8dcaca451c074a3befc334b80db8255b486dd396c678ff36258b35df
15183083188 8b67b2b0d36e122572b844cace220c053c074e8cb543227e6bffb85d6cff23ab
```

### Mobile runtime inputs actually selected by the hosted jobs

Android, iOS and OHOS each passed compatible-runtime selection, hosted download
and producer/payload verification/install steps before their later failure.
They selected native run [45894657258](https://github.com/azurekiln2333/qflistudio-rust/actions/runs/45894657258),
attempt 1, `push`/`main`, successful, workflow `.github/workflows/native-runtime.yml`,
source `a07511394cfc8a8079e226e37468c571b9d0ed1e`.
Downloads in these logs happened on hosted runners, not in either working clone.
Desktop jobs skipped mobile-runtime stages as intended.

| Selected runtime artifact | Artifact ID | ZIP bytes | GitHub archive SHA-256 |
| --- | ---: | ---: | --- |
| `native-runtime-android-arm64` | 15156108223 | 128,544,947 | `8566283b374320dc3bb2e036a3207be780c18ce9d2d720568f579a47ee5884cc` |
| `native-runtime-android-x64` | 15155672582 | 128,566,749 | `f0e37966d86f9fb6592672a288c67cc2f566e26d9001cef92b1c65b3accbb030` |
| `native-runtime-ios-arm64` | 15159405814 | 76,132,526 | `9b6fcacd85e9abfc977a1151a06fe881ff764f44cfed25122a7ebedf31f5a499` |
| `native-runtime-ohos-arm64` | 15155258958 | 86,389,814 | `86be112f8dee86eefc0c4230a434de01795e3a7b0c79524f595c6484c6f108da` |

These are verified input-stage outcomes, not Flutter output, native execution,
installer or device acceptance. Runtime identity verification passing does not
resolve the later app/core/SDK compilation failures.

### Signing and installation evidence limits, per target

| Target | Contract/intention only | What this run actually establishes |
| --- | --- | --- |
| Android arm64/x64 | Testing/debug key, not store-release signing | Gradle failed before successful APK packaging. No APK certificate/zipalign/package verification completed. No store-signing or device-install pass. |
| iOS arm64 | Unsigned IPA, no app provisioning/profile, not device-ready | SDK preparation failed; the app build and IPA packager were skipped. No IPA or signature/provisioning result is established. |
| OHOS arm64 | Unsigned HAP, signature not verified | The actual command includes `--no-codesign`; Flutter warns that codesigning is disabled and manual signing is required before deployment. Compilation fails. No verified unsigned HAP, signed HAP or device-ready result exists. |
| Linux x64 | Signing not applicable to the declared DEB contract | Build failed; DEB packaging and hosted install/hash/uninstall verification did not execute. |
| Windows x64 | Unsigned installer executable | SDK preparation failed. No EXE, Authenticode or silent install/hash/uninstall result exists. |
| macOS arm64 | Ad hoc app signature, not notarized | Compilation failed; DMG packager/ad hoc signature verification did not execute. No notarization, accepted package or installation result. |
| macOS x64 | Ad hoc app signature, not notarized | Compilation failed; DMG packager/ad hoc signature verification did not execute. No notarization, accepted package or installation result. |

No credential values or secret lists were requested. These runs do not prove
that signing credentials are absent at repository, environment or organization
scope. No target-device execution or application UI verification is established.
Android covers only the intended arm64/x64 matrix, not armv7. Native payload
installation into a hosted build checkout is not installation on a device.

## 3. Application quality: run 45966799846

| Job | Job ID / evidence | Conclusion |
| --- | --- | --- |
| Quality helper contracts (no core required) | [140397300483](https://github.com/azurekiln2333/qflistudio-rust/actions/runs/45966799846/job/140397300483), Ubuntu, 44 hermetic helper tests, OK | success |
| Core-bound format, analysis and full root tests | [140397299810](https://github.com/azurekiln2333/qflistudio-rust/actions/runs/45966799846/job/140397299810), Ubuntu | failure |

The core-bound job passes bootstrap through SDK preparation (step 10).
Step 11, `Restore dependencies and bind quality input provenance`, really runs
hosted `flutter pub get`. The log reports `Changed 17 dependencies!`, including
selection of `xterm 4.0.0`. Preparation then fails at 08:36:41 UTC with:

```text
Dependency restore changed tracked quality inputs; review cloud lockfile changes before retrying
```

This is the first actual quality error. The inspected log does not provide an
exact tracked-file diff. No archive was opened to infer one. Do not attribute
the entire failure solely to an unreleased core change or declare a last-passing
core SHA without further hosted evidence.

Steps 12, 13 and 14 invoke the format/analyze/test **helper entry points** under
failure-continuation conditions. Each fails with:

```text
Quality prepare did not complete; no check may pass
```

The actual Dart formatter, Flutter analyzer and full
`flutter test --no-pub --machine test` process do **not** run. These are blocked
checks, not observed formatting violations, analyzer findings or failed root
test cases. Step 15 finalization also fails:
`Quality job did not complete all required stages`. Step 16 uploads diagnostics
successfully; this is not passing quality evidence. Helper regression logs
contain expected injected failure messages followed by `OK`; those are distinct
from the genuine core-bound preparation failure.

| Artifact | ID | ZIP bytes | Expires (UTC) | GitHub archive SHA-256 |
| --- | ---: | ---: | --- | --- |
| `application-quality-linux-x64` | 15182857891 | 82,807 | 2026-12-11 08:36:42 | `f75e85bc9bbb361cf9477f549de026229e56a5eb540ae42520d33fa8cf4f58f0` |

The artifact was unexpired at inspection, with 14-day retention. It is a
quality diagnostic artifact, never an installer. Required migration format,
analysis and root-suite passes remain **unmet at 443c988**.

## 4. Cloud checks: run 45966800064

All four jobs passed. The independent policy job covers committed operational
Python/shell/PowerShell syntax, workflow parsing/action pins, actionlint,
source visibility/local-state exclusions, and controlled-Chinese tooling/native
guidance. Its scope is not executing the application or building its compiler.

| Job | Job ID | Conclusion | Hosted test evidence |
| --- | ---: | --- | --- |
| Source, workflow and portability policy (`ubuntu-24.04`) | 140397300698 | success | Policy/syntax/workflow checks, including controlled-Chinese selftest |
| Python contracts (`ubuntu-24.04`) | 140397300915 | success | 291 native-helper tests, OK (3 skipped); 105 app-helper tests, OK |
| Python contracts (`windows-2022`) | 140397300832 | success | 291 native-helper tests, OK (1 skipped); 105 app-helper tests, OK |
| Python contracts (`macos-15-intel`) | 140397300373 | success | 291 native-helper tests, OK (3 skipped); 105 app-helper tests, OK |

The actual logs explicitly say `Application helper suites passed. Flutter
builds, target installers, signing and device execution are separate checks.`
Do not confuse echoed fallback script text saying `NOT RUN` with the actual
successful app-helper execution. Expected fault-injection annotations in these
passing helper suites are not failed application jobs.

All three retained artifacts were unexpired at inspection, with 14-day retention:

| Artifact | ID | ZIP bytes | Expires (UTC) | GitHub archive SHA-256 |
| --- | ---: | ---: | --- | --- |
| `cloud-checks-ubuntu-24.04` | 15182812848 | 11,177 | 2026-12-11 08:35:37 | `5826f2fa96b88d89c03923f116283297a0b6d0a99eb1184f7bb0596f91c19d3a` |
| `cloud-checks-windows-2022` | 15183336163 | 11,238 | 2026-12-11 08:35:51 | `17443579923c1f0f51334712a607c3734afa800bf774fceaedab2e62681e9e55` |
| `cloud-checks-macos-15-intel` | 15183551370 | 11,227 | 2026-12-11 08:36:05 | `0eddb5cbecedc692dfcfe9b308f926044b8ca39d039ec79c110d0d524698e2b3` |

## 5. Reproducible read-only evidence access and frozen handoff

The evidence was obtained through these GitHub API surfaces, with JSON field
selection or text-log filtering in PowerShell:

```text
gh api repos/azurekiln2333/qflistudio-rust/actions/runs/<run-id>
gh api --paginate 'repos/azurekiln2333/qflistudio-rust/actions/runs/<run-id>/jobs?per_page=100'
gh api 'repos/azurekiln2333/qflistudio-rust/actions/runs/<run-id>/artifacts?per_page=100'
gh api repos/azurekiln2333/qflistudio-rust/actions/jobs/<job-id>/logs
```

No artifact archive endpoint was called. No hosted report was represented as
locally verified bytes. This is a frozen observation of the requested runs,
not a claim about later commits, reruns, clone parity or receiving hooks.

Handoff to `w61:p1`: at `443c9887e6ab9e2c22d96ced491f06145aa74d66`, Cloud checks
`45966800064` passes all four jobs. Quality `45966799846` fails because hosted
restore changes tracked inputs; actual format/analyze/root tests remain blocked.
Installer `45966800141` fails all seven targets: Android ABI-filter conflict,
iOS SDK-host DNS failure, OHOS/macOS missing `UnicodeV11` plus xterm OHOS switch
coverage, Linux missing libsecret, Windows cp1252 log encoding. Seven diagnostic
`app-installer-*` artifacts exist; no intermediate artifacts or accepted
installers exist. Signing, installation, devices/UI, armv7 and final SDK/native-
hooks compatibility remain unverified follow-ups. Only the assigned research
file changed; the coordinator retains review, remediation, publication and
migration acceptance ownership.
