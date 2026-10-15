# Execution Plan

1. Record platform/runtime and environment evidence; resolve Web scope.
2. Generalize native runtime selection and FFI asset preparation, retaining OHOS
   compatibility and the existing native session lifecycle.
3. Use bundled Windows GNU linking when applicable and verify both rustc and
   Cargo compile/run flows using real sources.
4. Add reproducible native host builds, Android/iOS compiler-private source
   bootstrap, target manifests and platform package integration.
5. Build the Windows Miri adapter from the pinned source and cached matching
   compiler components, then exercise its C ABI and real Dart runner.
6. Run available host checks for semantics, diagnostics, I/O, user exit status,
   cancellation, limits and reuse. Record unavailable target tests as skipped.
7. Review cross-layer contracts, update executable native-runtime specs, commit
   each completed batch, and audit the full goal before marking it complete.

## Verification Commands

- Flutter/Dart analysis and focused runner/asset/project tests using
  `D:/ProgramFiles/flutter_ohos`.
- Windows compiler tests with the isolated Rust 1.98.1 installation.
- Native C ABI fixture harness and Dart runner using the actual host library
  and compatible MIR sysroot.
- Platform build checks only where the required SDK, build host and signing
  environment exist; no OHOS device installation is required.

## Ownership

- Dart integration: `lib/` runtime selection/assets/runner, focused Dart tests.
- Native build integration: `scripts/`, `native/`, and platform build files.
- Main agent: environment evidence, build execution, task/spec documentation,
  final cross-layer review and narrow Git commits.
- Research agent: this task's `research/cross-platform-native.md` only.

## Progress

- [x] Inspected current platform branches and native build target restrictions.
- [x] Verified the Windows compiler and cached matching rustc-dev source.
- [x] Reproduced old MinGW linking failures; verified bundled stable LLD flags.
- [x] Dart runtime selection and asset preparation.
- [x] Native source builds and package integrations.
- [x] Android ARM64 six-case and x64 seven-case actual execution.
- [ ] OHOS signed packaged execution; matching signing profile absent.
- [ ] Windows native adapter/sysroot and Apple-host execution checks.
- [x] Spec sync, review, scoped commits and remaining-goal audit.

## Current release evidence (2026-10-15)

Current implementation is committed in c2bc7b9, 151fe59 and 0649363; final app
profile/content integration is5384d29. Root Flutter suite140passed,8Windows native
Miri skips,0failed; all332 curriculum programs and23Cargo workspaces execute on
the real host compiler. Android x64 API37/16KiB emulator seven-case native/editor/
terminal suite passed. Final APK/HAP results live in the release-readiness task
research/platform-builds.md. Keep this broad task open for the exact missing
Windows/Apple and OHOS signed-execution evidence; no stub enables those runtimes.
