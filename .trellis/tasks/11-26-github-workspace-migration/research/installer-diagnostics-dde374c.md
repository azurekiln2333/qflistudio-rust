# Research: Installer Diagnostics for dde374c

- Query: Diagnose the first concrete failures in installer run 46033399007, jobs 140622826210 and 140622826258; capture metadata for artifacts from those jobs.
- Scope: mixed (repository source/spec and exact GitHub-hosted logs/API metadata)
- Date: 2026-11-28

## Findings

Run 46033399007 is a completed push run on main, source SHA dde374cdcdbca4ee0f093b5b62261a65da32d125, created 2026-11-27T16:24:51Z. The two requested jobs both concluded failure. This report uses their exact job logs and artifact-list metadata; it does not inspect artifact contents.

### macOS x64

Job 140622826210 (macos/x64) ran from 2026-11-27T16:25:21Z to 16:26:25Z. During Prepare pinned Flutter SDK, at 16:26:12.537Z, curl reported (6) Could not resolve host: flutter-ohos.obs.cn-south-1.myhuaweicloud.com. The SDK setup then reported it could not retrieve the Dart SDK from that pinned host, and the job ended with Command failed (1); see flutter-config.log. This is a DNS/network infrastructure failure during SDK preparation; no application build ran.

Artifact metadata: app-installer-macos-x64, ID 15214724406, 9,890 bytes, created 2026-11-27T16:26:14Z, expired=false. Its existence does not establish that a verified installer was produced.

### iOS arm64

Job 140622826258 (ios/arm64) ran from 2026-11-27T16:26:01Z to 16:36:45Z. During Xcode's Embed Rust Runtime phase, at 16:36:27.964Z, the script raised AttributeError: module 'hashlib' has no attribute 'file_digest' from scripts/miri_build_support.py, line 41. Xcode then reported PhaseScriptExecution failed with a nonzero exit code; Flutter reported Failed to build iOS app. The subsequent generic Development Team / provisioning-profile advice is not the underlying diagnostic. This is a Python runtime/API compatibility failure in the embed phase, not evidence of a signing failure. The log does not identify the Python version used by that Xcode script.

Artifact metadata: app-installer-ios-arm64, ID 15215483861, 1,481,419 bytes, created 2026-11-27T16:36:33Z, expired=false. The workflow retains iOS --no-codesign; artifact presence does not establish a signed, device-installable package or successful installer validation.

### Classification and repository patterns

- macOS x64: infrastructure/DNS failure. The log identifies an unresolved SDK host, with no evidence in this job that source, core, lockfile or registrant inputs caused it.
- iOS arm64: build/configuration compatibility failure in the Rust embedding script. This run establishes the missing hashlib.file_digest API as the first concrete error. It does not establish whether the condition existed at pre-migration GitHub main, so migration causality remains unproven under the ci-decoupled rule.
- scripts/miri_build_support.py:39-41 opens the requested file and calls hashlib.file_digest(stream, "sha256"). The exact iOS log identifies line 41 as the failing call.
- ios/Runner.xcodeproj/project.pbxproj:229-235 declares the Embed Rust Runtime Xcode build phase implicated in the job log.
- .trellis/spec/backend/github-app-builds.md:147-150 requires verbose, no-code-sign iOS builds and says generic Development Team advice is not the underlying diagnosis. Its installer contract also says successful packaging requires complete-stage verification (:213-217).
- .trellis/spec/guides/cloud-only-workspace.md:12-18 places builds and artifact generation on GitHub-hosted Actions runners.

### Files found

- .trellis/workflow.md — workflow phases and research persistence requirements.
- .trellis/spec/guides/cloud-only-workspace.md — hosted-only validation and artifact boundary.
- .trellis/spec/backend/github-app-builds.md — installer targets, iOS build/signing behavior, and acceptance limits.
- scripts/miri_build_support.py — hashing helper that calls the unavailable API.
- ios/Runner.xcodeproj/project.pbxproj — declares the failing Xcode build phase.
- .trellis/tasks/11-26-github-workspace-migration/research/ci-triage-1935d3d-2026-11-27.md — prior CI triage; documents the earlier iOS generic-signing message without a concrete cause.

### External references

- GitHub Actions run 46033399007, repository azurekiln2333/qflistudio-rust, source SHA dde374cdcdbca4ee0f093b5b62261a65da32d125, created 2026-11-27. Job URLs: [macOS x64](https://github.com/azurekiln2333/qflistudio-rust/actions/runs/46033399007/job/140622826210) and [iOS arm64](https://github.com/azurekiln2333/qflistudio-rust/actions/runs/46033399007/job/140622826258).
- GitHub Actions artifact-list API for run 46033399007; metadata records the two artifact IDs, names, byte sizes, creation times and expired=false. No artifact download was performed.
- GitHub-hosted runner logs identify macOS 15.7.9, image macos-15 version 20260824.0482.1, and iOS Xcode 16.4. The failing Xcode script's Python version is not logged.

### Related specs

- .trellis/spec/backend/github-app-builds.md
- .trellis/spec/guides/cloud-only-workspace.md

## Caveats / Not Found

- No historical run or pre-migration source was queried; therefore the iOS condition cannot be assigned to pre-existing versus migration-caused scope from this evidence alone.
- The log proves DNS resolution failed for the pinned macOS SDK host during this attempt. It does not establish whether the host recovered later. No rerun was requested or triggered.
- Artifact metadata does not expose package contents, signing state or package-verification results. Artifacts were not downloaded.
- The iOS log does not report the interpreter version used by the Xcode build phase; infer only that this interpreter lacks hashlib.file_digest.
