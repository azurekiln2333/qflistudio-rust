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
- Android arm64/x64 and iOS arm64 remain in progress. The current artifact list
  contains shared guest data and diagnostic logs, not a complete native runtime.

## Separate license change

- Commit: 1cebc79 docs(license): add GPL-3.0 license aligned with qflistudio
- LICENSE is byte-identical to D:/MyNewProjects/qflistudio/LICENSE, SHA256
  3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986.
- Its normalized full text matches GNU's canonical GPLv3 text.
- Three root README editions link LICENSE and preserve separate component
  declarations. Chinese lint passed. Pushed independently before mobile CI.
