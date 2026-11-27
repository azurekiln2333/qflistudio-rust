# Hosted evidence at 60524ea — 2026-11-27

Read-only GitHub metadata and job-log inspection on 2026-11-27, beginning
18:31 +08:00. All three runs below are completed push runs at source
`60524ea9d3d5c2d5fde8d4a0e77b22a5e4650f69`.
Application logs bind core `476a30acee21dc486ee2849dd8064a7be665e4d5` and
Flutter-OH `3.41.10-ohos-1.0.1` revision
`adaf911c35c9136a7d18fc424d714c9ec7724e60`.
This is the migration pin, not final production compatibility approval.

## Cloud checks: passed

[Run 45980976052](https://github.com/azurekiln2333/qflistudio-rust/actions/runs/45980976052)
completed successfully at 10:19:33 UTC. All four jobs passed.

| Hosted OS / job | Native tests | Application helper tests |
| --- | --- | --- |
| Ubuntu 24.04 / 140444480583 | 291, OK, 3 skipped | 122, OK |
| macOS 15 Intel / 140444480532 | 291, OK, 3 skipped | 122, OK |
| Windows 2022 / 140444480689 | 291, OK, 1 skipped | 122, OK |

Source, workflow and portability policy job `140444480320` passed, including
operational Python parsing, shell/PowerShell checks, workflow/action checks,
actionlint and the configured portability/Chinese guidance checks. These are
hosted helper/policy results, not Dart/Flutter application quality results.

## Application quality: failed before checks

[Run 45980975989](https://github.com/azurekiln2333/qflistudio-rust/actions/runs/45980975989)
completed with failure at 10:20:14 UTC. Independent helper job `140444479982`
ran 54 tests and passed. Core-bound job `140444480216` failed first at
`Restore dependencies and bind quality input provenance`.

Dependency restore completed but changed six tracked inputs. The guard reported
`Dependency restore changed tracked quality inputs; review cloud lockfile changes before retrying`.
The bounded `pub-get-input-delta.txt` log lists:

1. `linux/flutter/generated_plugin_registrant.cc`
2. `linux/flutter/generated_plugins.cmake`
3. `macos/Flutter/GeneratedPluginRegistrant.swift`
4. `pubspec.lock`
5. `windows/flutter/generated_plugin_registrant.cc`
6. `windows/flutter/generated_plugins.cmake`

The later format, analysis and full-root-test steps failed their preparation
guard (`Quality prepare did not complete; no check may pass`). Their Dart or
Flutter validation commands did not establish any result. Finalization also
failed because the required stages were incomplete. Required migration format,
analysis and full root tests therefore remain pending.

The uploaded `application-quality-linux-x64` artifact (`15189421636`, 94,984
bytes, expires 2026-12-11 10:20:09 UTC) is failure-report evidence, not a quality
pass or application package. It was not downloaded during this review.

## Application installers: one unsigned package, six failed targets

[Run 45980975900](https://github.com/azurekiln2333/qflistudio-rust/actions/runs/45980975900)
completed with failure at 10:27:20 UTC. Its three orchestration jobs each ran
122 application helper tests successfully: macOS `140444479625`, Windows
`140444479975`, Ubuntu `140444480062`.

| Target / job | Outcome and first failed stage | Uploaded artifact names |
| --- | --- | --- |
| Linux x64 / 140444678269 | Failed build: required `libsecret-1>=0.18.4` missing | `app-installer-linux-x64` (failure reports) |
| Windows x64 / 140444678344 | Failed SDK setup: Python `UnicodeEncodeError`, `charmap` cannot encode command output | `app-installer-windows-x64` (failure reports) |
| macOS arm64 / 140444678193 | Build passed; package verification failed because `lipo -verify_arch` interpreted the executable path as an architecture flag | `app-installer-macos-arm64` (failure reports), `app-intermediates-macos-arm64` |
| macOS x64 / 140444678322 | Build passed; same `lipo -verify_arch` package verification failure | `app-installer-macos-x64` (failure reports), `app-intermediates-macos-x64` |
| iOS arm64 / 140444678275 | Failed SDK setup: Dart SDK host DNS lookup failed, `curl: (6) Could not resolve host` | `app-installer-ios-arm64` (failure reports) |
| Android arm64/x64 / 140444678297 | Failed Gradle configuration: `ndk abiFilters` conflicts with split ABI filters | `app-installer-android-arm64-x64` (failure reports) |
| OHOS arm64 / 140444678309 | Build, package verification, finalization and uploads passed; unsigned HAP | `app-installer-ohos-arm64`, `app-intermediates-ohos-arm64` |

The six failed target artifacts do not establish verified installers or signing
acceptance. Successful finalization/upload of failure reports does not change
their failed job conclusions. macOS intermediate archives retain build inputs;
they do not establish accepted DMGs. Installer/report artifacts expire after
14 days; the three uploaded intermediate artifacts expire after one day.

### OHOS evidence and limits

The build log reports `build/ohos/hap/entry-default-unsigned.hap` (359.3 MB) and
explicitly warns that device deployment requires manual codesigning. Hosted
native payload verification, application build, package verification and
finalization passed. This establishes the workflow's unsigned package result,
not signing, device installation, UI execution or complete product acceptance.

| Artifact | ID | Bytes | Expires (UTC) |
| --- | --- | ---: | --- |
| `app-installer-ohos-arm64` | 15190300135 | 359,953,208 | 2026-12-11 10:23:54 |
| `app-intermediates-ohos-arm64` | 15189457576 | 104,249,368 | 2026-11-28 10:24:09 |

GitHub records archive SHA-256
`0c10e613b3d0a0d76f5852ff5764051d970ccb2fc6aac540faa27ed98a931ccd`
for the installer artifact and
`8e3bb8b8f606e53e1ac8b812d25db783504c45aa0f17ead3d04249770a18e011`
for the intermediate artifact. These are service archive digests, not an
independently inspected HAP checksum. No artifact was downloaded or extracted.

## Remaining acceptance

Repair and rerun required migration quality checks through a new reviewed
commit and orchestra gate. Keep platform failures, Android armv7, signing,
device/UI, native-hooks compatibility and receiver-hook evidence separate from
the helper success and OHOS unsigned result. Hold the coordinated core pin;
`CORE_REF bump after the final core push` remains a later coordinated follow-up.
This report does not establish source/target parity or migration completion.

Only this new research file was written. Evidence collection used `gh run view`
and artifact-list metadata. No local validation, dependency restore, artifact
download, Git write or edit to another worker's files occurred.
