# GitHub native builds

## 1. Scope and trigger

Apply to `.github/workflows/native-runtime.yml` and
`scripts/ci_native_runtime.py`. The workflow builds Android arm64/x64,
OHOS arm64/x64 and iOS arm64 device runtimes, not Flutter applications.
macOS x64 is optional. Linux/macOS are build hosts using official toolchains.
Linux/Windows runtime packages are outside the CI target matrix.
A successful native package does not establish app execution.

## 2. Signatures

```text
python scripts/ci_native_runtime.py guest --work-root <fresh-root> --output-root <outputs>
python scripts/ci_native_runtime.py runtime --work-root <fresh-root> --output-root <outputs> --build-host <official-toolchain-host> --native-host <target> --guest-archive <tar.gz>
```

The compiler producer is `scripts/build_rustc_host.py`. Adapter and packaging
commands retain the contracts in `compiler-build-provenance.md`.
The OHOS PowerShell packager accepts `-ProjectRoot <output-root>` and
`-GuestBuildInfo <miri-sysroot.json>`; the guest record defaults to that name
under `-GuestSysroot`. Linux uses local paths and native LLVM executables.

## 3. Contracts

- Keep Rust version, compiler commit, source SHA and patch SHA centralized in
  `miri_build_support.py`. Do not weaken pinned identities for a green CI job.
- Use a minimal pinned bootstrap toolchain without rustc-dev. Guest preparation
  uses a separate toolchain with rustc-dev and rust-src.
- Fresh runners must prepare locked adapter dependencies before offline builds.
- Set `PYTHONDONTWRITEBYTECODE=1` for bootstrap so Python imports cannot mutate
  the compiler source tree whose complete fingerprint is verified after build.
- Preserve and fingerprint safe in-tree source symlinks. The official source
  archive contains LLVM CUDA test links on both Linux and Windows.
- Keep large build roots in runner temporary storage. Upload no compiler cache.
- Runtime artifacts are named `native-runtime-<platform>-<architecture>` for
  android-arm64/x64, ohos-arm64/x64, ios-arm64, and optional macos-x64.
- Each runtime artifact carries a tar.gz and matching SHA-256 file. Preserve
  executable modes and framework layouts inside the archive.
- Archive paths preserve native packages, platform library directories and
  `assets/miri/` for restoration at repository root. iOS uses its native host
  triple as package directory; OHOS keeps schema1 and `ohos/entry/libs/<ABI>`.
  Include only the
  selected manifest's asset files, ABI headers, and original build records.
- Runtime packages and diagnostics expire after 14 days. Intermediate guest
  artifacts expire after one day. Never mark failure diagnostics as a runtime.
- Push explicitly to GitHub: this project's origin has multiple push URLs.

## 4. Validation and error matrix

| Condition | Required outcome |
| --- | --- |
| Source or toolchain identity mismatch | Fail before compilation |
| Patched compiler provenance mismatch | Fail before adapter/package use |
| Missing dependency on clean runner | Fail with retained step log |
| Missing manifest-covered artifact | Fail before runtime archive publication |
| Failed compiler/adapter/package stage | Failed job and diagnostic artifact |
| Platform build succeeds | Complete platform archive and checksum |
| Library builds without app execution | Keep app runtime verification separate |

## 5. Cases

- Good: a fresh runner downloads verified inputs and publishes a complete
  package whose native and guest files match its manifest.
- Base: re-run a commit on fresh runners with no local compiler directories.
- Bad: upload only `qfli_miri.dll`, mix stock private metadata with a patched
  driver, or call an archive of logs a usable native runtime.

## 6. Required tests

Test build-host/target separation, target std installation, SDK selection, archive
path confinement, manifest coverage, checksum publication, and failures before
runtime archive creation. Validate workflow syntax and execute the workflow
on actual requested hosts. Record run URL, commit and per-job conclusions.

## 7. Wrong and correct

Wrong: configure a desktop job with stock rustc-dev and bypass the compiler
record verifier when the adapter fails.

Correct: bootstrap the patched compiler, pass its private/runtime sysroots and
verified record to the adapter, then package and archive verified outputs.
