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
