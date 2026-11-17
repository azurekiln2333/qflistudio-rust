# Cloud build evidence

## First run

- Run: https://github.com/azurekiln2333/qflistudio-rust/actions/runs/43923339583
- Commit: 63023213581d71905d059653916f0b85bf4a57ed
- Shared Linux MIR guest: succeeded. Uploaded native-guest-sysroot,
  67,433,038 bytes including artifact ZIP wrapping.
- Linux x64: failed before compilation. tree_identity rejected the official
  source tarball's LLVM CUDA test symlink at
  src/llvm-project/clang/test/Driver/Inputs/CUDA-symlinks/usr/bin/ptxas.
- Windows GNU x64: same source identity failure after successful toolchain
  installation and source extraction. Symlink extraction works on the runner.
- macOS arm64: queued when the first two platform failures were inspected.
- Diagnostic artifacts were uploaded successfully. No usable runtime package
  was produced by the failed Linux/Windows jobs.

Corrective work preserves and fingerprints safe source links rather than
dropping source files or weakening compiler patch provenance.

## Second run and scope correction

- Run: https://github.com/azurekiln2333/qflistudio-rust/actions/runs/43929421178
- Commit: 00b84c210b126ac00f585cc126c3437db7ebf33a
- Guest succeeded again. Linux passed source-link validation, then minimal
  toolchain detection falsely treated rust-std rustc_* facade libraries as
  compiler-private rustc-dev metadata. Windows also failed; no runtime package.
- macOS arm64 was not assigned a runner. GitHub annotations reported hosted
  arm64 capacity constraints, not repository access or source errors.
- User corrected scope to Android/OHOS/iOS and optional macOS. Linux and Windows
  are official build-toolchain hosts, not requested runtime outputs.

## Mobile-target run

- Run: https://github.com/azurekiln2333/qflistudio-rust/actions/runs/43939926708
- Commit: 341ffefb3562021323b444434c9fd136bfa31782
- Targets: Android arm64/x64, OHOS arm64/x64, iOS arm64 device.
- Shared MIR guest succeeded. Android NDK and both verified OHOS SDK installs
  succeeded. The iOS job acquired a macOS Intel runner and started compilation.
- OHOS arm64 and x64 failed while linking stage0 std: resolving the selected
  `ld.lld` alias changed the invocation name to the generic `lld` driver.
  The producer now validates the referent while preserving the selected alias.
  A separate review passed 103 producer/support/consumer tests.
- Android arm64 and x64 both completed the patched compiler and embedded
  Cranelift backend, emitted compiler-build.json and passed provenance checks.
  Their adapters then failed before compilation: the offline build lacked
  `memmap2 v0.2.3` despite a successful target-filtered cache fetch.
  `-Zdual-proc-macros` also needs the Linux host dependency graph. Fetching the
  full locked graph fixes that cache gap while retaining offline adapter builds.
  Ten helper checks passed, including a real Cargo/local-registry reproduction.
- iOS arm64 later completed successfully. The run failed overall because the
  Android and OHOS jobs failed. Use the corrected all-platform run below for
  the complete five-target artifact set.

## Corrected run: all mobile targets succeeded

- Run: https://github.com/azurekiln2333/qflistudio-rust/actions/runs/43946596992
- Commit: 76289a080335389ad3a283c7278fa548e5cd0ba3
- Includes LLVM alias preservation (76dd57f), complete locked adapter dependency
  prefetch (3a57b37), and manual-dispatch documentation (9fa6a09).
- Per-ref concurrency now keeps the active run and queues the newest update.
  GitHub confirmed this run pending while 43939926708 continued its iOS job.
- Final result checked on 2026-11-17: shared guest and all five mobile jobs
  succeeded. The logs confirm compiler sysroots, Cranelift backends, adapter
  records, platform manifests, runtime archives and two-file artifact uploads.
- The five runtime artifacts are available until 2026-11-30 UTC:

| Artifact | GitHub artifact ID | ZIP bytes |
| --- | --- | ---: |
| native-runtime-android-arm64 | 14271597100 | 128544961 |
| native-runtime-android-x64 | 14269058863 | 128563834 |
| native-runtime-ohos-arm64 | 14272446481 | 86388904 |
| native-runtime-ohos-x64 | 14271771731 | 86139254 |
| native-runtime-ios-arm64 | 14277174916 | 76132563 |

- Each artifact download URL is the run URL followed by `/artifacts/<ID>`.
  OHOS packaging reported 98 MIR/license assets per architecture.
- Build/package success does not establish device execution. Records retain
  runtimeExecuted=false and deviceExecuted=false. The independent review read
  logs and artifact metadata without downloading complete runtime archives.

## Main consolidation

- User requested one remaining branch, main, after merge and checks.
- Starting tips: local main 78fb7b1, local feature c423575, GitHub feature
  b8a69a8, local/GitHub CI d894819. All tips are ancestors of d894819.
- Main fast-forwarded to d894819 without conflicts. Native/scripts trees match
  the successful 76289a0 build; subsequent edits were documentation/journals.
- Git object connectivity passed. Root coordinates push/default migration and
  removes old branches only after the remote main contains all previous tips.
- Commit 540674f was pushed to main. The API verified its tip before setting
  default_branch=main. Both old GitHub branches were deleted atomically with
  expected-tip leases. Local branches were deleted with `git branch -d`.
- Fetch/prune left only local main and remote origin/main. Local main tracks
  origin/main and origin/HEAD points to main. No native source changed during
  consolidation; actionlint, Chinese lint and independent ancestry checks passed.

## Separate license change

- Commit: 1cebc79 docs(license): add GPL-3.0 license aligned with qflistudio
- LICENSE is byte-identical to D:/MyNewProjects/qflistudio/LICENSE, SHA256
  3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986.
- Its normalized full text matches GNU's canonical GPLv3 text.
- Three root README editions link LICENSE and preserve separate component
  declarations. Chinese lint passed. Pushed independently before mobile CI.
