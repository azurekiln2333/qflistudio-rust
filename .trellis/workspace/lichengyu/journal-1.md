# Journal - lichengyu (Part 1)

> AI development session journal
> Started: 2026-09-30

---



## Session 1: Embedded Miri runtime and OHOS integration
<!-- trellis-session: v=2 fp=dbe958269bd1ef8d -->

**Date**: 2026-09-30
**Task**: Embedded Miri runtime and OHOS integration
**Branch**: `main`

### Summary

Implemented upstream rustc/Miri session ABI and Flutter OHOS integration. Rebuilt ARM64 and x64 libraries and regenerated the unsigned x64 HAP. Fixture and device tests remain paused at the user's request.

### Main Changes

- Added session I/O, diagnostics, cancellation and execution limits; locked dependencies and pinned source/compiler inputs.
- Added Flutter FFI worker, retryable asset extraction and manifest packaging; recorded contracts in local native-runtime specs.

### Git Commits

| Hash | Message |
|------|---------|
| `c544537` | feat(native): embed upstream Miri session runtime |
| `c964209` | feat(ohos): integrate packaged Miri execution runner |
| `f88ffcb` | docs(runtime): record Miri integration progress |

### Testing

- [OK] Necessary ARM64/x64 builds passed. HAP reached PackageHap, then signing failed with existing 00303074 bundle/profile mismatch.

### Status

[OK] **Completed**

### Next Steps

- Keep the task active and runtimeStatus unavailable pending packaged source execution; mobile Cargo dependencies remain subsequent work.


## Session 2: Content imports and native startup handoff
<!-- trellis-session: v=2 fp=1df777a9f4ecfe6a -->

**Date**: 2026-10-01
**Task**: Content imports and native startup handoff
**Branch**: `main`

### Summary

Completed named Rust tutorial/example imports and retained the OHOS native progress splash until the Flutter home page first frame. Archived the completed content task and preserved existing parallel edits.

### Main Changes

- Added native progress events and deferred OHOS frames until bootstrap, startup timing and home page layout complete.
- Documented the startup platform contract and added a regression using the real app entry point.

### Git Commits

| Hash | Message |
|------|---------|
| `222913e` | feat(content): support named Rust example imports and verify MD3 pages |
| `9ed3164` | fix(ohos): retain native startup progress until Flutter renders |

### Testing

- [OK] Dart analysis passed; startup regression passed; default@CompileArkTS completed successfully.
- [OK] Content import/profile/project verification passed: 43 focused checks and 4 actual-content UI checks, with 12 screenshots.

### Status

[OK] **Completed**

### Next Steps

- Device installation and Rust compiler/runtime execution remain paused at the user request.


## Session 3: Rust release curriculum terminals and native platform verification
<!-- trellis-session: v=2 fp=479456c2ea527f36 -->

**Date**: 2026-10-15
**Task**: Rust release curriculum terminals and native platform verification
**Branch**: `main`

### Summary

Verified Rust-only three-Pi delivery, offline terminals, 166 complete lessons/examples, actual Android ARM64/x64 execution and final APK/unsigned HAP integrity. Keep production signing and OHOS signed execution open.

### Main Changes

- Both terminal delegates, enforced offline Cargo, complete paired curriculum and Cargo imports; shared core read-only at 8b33443.
- Final APK/HAP catalogs and all manifest-covered native library/assets match bytes; narrow OHOS strip exclusions fix actual package checksums.

### Git Commits

| Hash | Message |
|------|---------|
| `c59efb2` | docs(plan): define Rust release readiness and parallel ownership |
| `6082520` | feat(content): add validated Rust curriculum generation and execution checks |
| `a5a12aa` | feat(content): author Rust lessons 001-084 with verified examples |
| `c2bc7b9` | feat(terminal): connect Rust tools with offline execution and tree cancellation |
| `151fe59` | fix(terminal): enforce offline Cargo policy against host overrides |
| `0649363` | feat(runtime): package pinned Rust engines for native platforms |
| `dc2becf` | fix(content): correct Rust fundamentals and exercise contracts |
| `5384d29` | feat(content): ship 166 verified Rust lessons and complete Cargo imports |
| `08c2605` | docs(trellis): record verified Rust curriculum and terminal completion |
| `ca6853e` | fix(runtime): preserve OHOS libraries and verify native terminal flows |
| `6de0e35` | docs(release): record final Rust platform builds and device verification |

### Testing

- [OK] 332 real programs and 23 offline workspace/all-target Cargo projects passed; all 166 lessons semantically reviewed.
- [OK] Root Flutter 140 pass, 8 Windows-native Miri environment skips, 0 failures; Python13 pass; shared core102 pass; terminal/process/app65 pass; analysis and format clean.
- [OK] Actual Android ARM64 physical7/7 and x64 API37/16KiB7/7; final ordinary APK five-page smoke passed on both. OHOS unsigned build passed but signed execution not verified.

### Status

[OK] **Completed**

### Next Steps

- Obtain production Android signing and matching Rust OHOS signing, then verify signed packaged OHOS source execution; no unrelated credentials or device-policy changes.
- Retain readiness/OHOS/cross-platform tasks for actual remaining acceptance; Windows-native adapter/sysroot and Apple-host checks remain in broader task. Physical device explicitly released to Go; owned emulator/privateADB cleaned up.


## Session 4: Trilingual README and fresh Rust readiness checkpoint
<!-- trellis-session: v=2 fp=1af5e621fed9263f -->

**Date**: 2026-10-26
**Task**: Trilingual README and fresh Rust readiness checkpoint
**Branch**: `feat/rust-offline-ide-20261022`

### Summary

Session summary was not supplied.

### Main Changes

- Rewrote Simplified Chinese, Traditional Chinese and English README editions with equivalent features, commands and platform limitations.
- Published controlled-Chinese checker and README language contract; preserved unrelated source changes.
- Used four actual Rust Herdr Pi panes, retried terminal connection failures and restored exited Pi sessions without resetting WSL or killing foreign processes.

### Git Commits

| Hash | Message |
|------|---------|
| `dd3343b` | docs: add trilingual README and controlled Chinese checks |
| `553e139` | docs: align README terminology and platform limits |

### Testing

- [OK] Both Chinese READMEs passed default and strict25 checks with zero findings; checker selftest20 passed; independent final review passed.
- [OK] Relative links, three identical fenced blocks and actual166 tutorials plus166 examples verified; no native/SDK/device execution.
- [OK] 553e139 exact remote branch hash verified on GitHub/Gitee/GitCode/CNB. GitLab HTTPS lacked noninteractive credentials; existing SSH retry timed out with owned Job empty.

### Status

[OK] **Completed**

### Next Steps

- C592 explicitly defers this Rust queue turn. Runtime ownership controls remain unrun; Native90 and separate Dart110 require fresh named grants after source freeze refresh.
- Four actual Pi panes continue disjoint source-only compiler boundary, owned-controls, packaged-runtime and full-goal evidence tasks. Keep umbrella task in_progress.


## Session 5: Rust compiler provenance and archive gate checkpoint
<!-- trellis-session: v=2 fp=8c895e411a03ccaf -->

**Date**: 2026-10-26
**Task**: Rust compiler provenance and archive gate checkpoint
**Branch**: `feat/rust-offline-ide-20261022`

### Summary

Bound compiler and adapter provenance. Added complete ABI and archive checks. Preserved the open OHOS acceptance gate.

### Main Changes

- Verified and pushed scoped compiler provenance and archive inspector commits to four remotes.
- Four Herdr Pi panes implemented and reviewed source fixes. Retried the observed Pi connection failure.
- Authored spanless diagnostic and invalid UTF8 regressions. Actual SDK and native checks remain unrun.

### Git Commits

| Hash | Message |
|------|---------|
| `aa8594a` | build: bind native adapters to patched compiler provenance |
| `b8a69a8` | feat(audit): verify Rust archive ABI and compiler provenance |

### Testing

- [OK] 81 compiler provenance pure tests and 58 runner control pure tests passed.
- [OK] Minimal committed-dependency tree passed 144 inspector and catalog pure tests plus both generation drift checks.
- [OK] Changed Chinese prose fields passed scoped controlled-language checks. Program bytes and expected output were preserved.

### Status

[OK] **Completed**

### Next Steps

- Keep task in progress. Add explicit analysis mirror-root handling and verified non-OHOS loader support.
- Refreeze current core metadata and exact source identities before requesting fresh bounded runtime grants.
- Build patched compiler and adapters. Run actual ABI and OHOS catalog acceptance before adding topics.


## Session 6: GPL alignment and mobile native CI validation
<!-- trellis-session: v=2 fp=3fb285a92f58118f -->

**Date**: 2026-11-17
**Task**: GPL alignment and mobile native CI validation
**Branch**: `ci/native-runtime`

### Summary

Aligned GPLv3 with qflistudio and pushed mobile native builds. Android compiler and backend succeeded; fixed LLVM aliases and missing host dependency cache. Corrected run is queued; iOS and complete runtime artifact validation remain open.

### Main Changes

- Preserved active native runs and queued subsequent updates.

### Git Commits

| Hash | Message |
|------|---------|
| `1cebc79` | docs(license): add GPL-3.0 license aligned with qflistudio |
| `341ffef` | ci(native): cross-build Android OHOS and iOS runtimes |
| `76dd57f` | fix(native): preserve LLVM executable aliases |
| `3a57b37` | fix(ci): prefetch host dependencies for native adapters |
| `9fa6a09` | docs(ci): clarify manual workflow prerequisites |
| `76289a0` | ci(native): queue updates without cancelling active builds |

### Testing

- [OK] 103 producer/support/consumer checks and 10 helper checks passed; workflow and Chinese lint passed.

### Status

[OK] **Completed**

### Next Steps

- Inspect iOS in run 43939926708, then jobs and runtime artifacts in corrected run 43946596992.


## Session 7: Rust migration takeover and hosted CI repairs
<!-- trellis-session: v=2 fp=c5e90d36baf1bc9e -->

**Date**: 2026-11-28
**Task**: Rust migration takeover and hosted CI repairs
**Branch**: `main`

### Summary

Recovered exact af4dc20 gate/parity/receiver ACK and refreshed migration receipt. Cloud passed; analysis and full root protocol passed with 334 passed and 20 skipped; quality format and iOS interpreter failures required narrow repairs. Applied exact formatter wraps and iOS Xcode PATH binding with independent source review. New-revision hosted validation and renewed gate/parity/ACK remain pending. Preserve all baselines, both stashes, ignored state and source-retirement holds. No local executable checks or artifact downloads.

### Git Commits

| Hash | Message |
|------|---------|
| `af4dc20` | fix(ci): verify quality assets and repair hosted fixtures |
| `6eed554` | fix(test): apply hosted workspace formatter output |
| `86a89c6` | fix(ci): bind iOS script phases to hosted Python |

### Status

**In progress** — repairs committed and source-reviewed. Final gate,
tracked parity/ACK and hosted validation remain pending.
