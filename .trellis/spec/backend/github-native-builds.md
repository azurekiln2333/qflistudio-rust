# GitHub native builds

All commands and regressions below run only on GitHub-hosted Actions runners.
Read [Cloud-only workspace](../guides/cloud-only-workspace.md). Do not download,
restore or verify runtime artifacts in either local editing clone.

## 1. Scope and trigger

Apply to `.github/workflows/native-runtime.yml` and
`scripts/ci_native_runtime.py`. The workflow builds Android arm64/x64,
OHOS arm64/x64 and iOS arm64 device runtimes, not Flutter applications.
macOS x64 is optional. Linux/macOS are build hosts using official toolchains.
Linux/Windows runtime packages are outside the CI target matrix.
A successful native package does not establish app execution. Application CI
has its own [core/SDK, byte-provenance and packaging contract](./github-app-builds.md).
Actual application validation remains pending.
`main` is the repository's sole development and GitHub default branch.
Push builds target `main`; manual dispatch includes optional macOS builds.
Before removing merged branches, prove every local and remote tip is an
ancestor of the pushed `main`, then change the default branch before deletion.

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
- Fresh runners must prepare the complete locked adapter dependency graph before
  offline builds. Run `cargo fetch --locked --manifest-path <staged-adapter>`
  without `--target`. The `-Zdual-proc-macros` build also uses build-host crates;
  a mobile-only fetch can omit Linux dependencies such as `measureme`'s
  `memmap2`. Keep the same Cargo cache for prefetch and the offline adapter build.
- Set `PYTHONDONTWRITEBYTECODE=1` for bootstrap so Python imports cannot mutate
  the compiler source tree whose complete fingerprint is verified after build.
- Preserve and fingerprint safe in-tree source symlinks. The official source
  archive contains LLVM CUDA test links on both Linux and Windows.
- Keep large build roots in runner temporary storage. Upload no compiler cache.
- Group workflow concurrency by ref and set `cancel-in-progress: false`.
  Keep the active build running so its artifacts and diagnostics can finish.
  A newer push replaces the pending run, not the active run. Only one run per
  ref builds at a time.
- Runtime artifacts are named `native-runtime-<platform>-<architecture>` for
  android-arm64/x64, ohos-arm64/x64, ios-arm64, and optional macos-x64.
- Each runtime artifact carries a tar.gz and matching SHA-256 file. Preserve
  executable modes and framework layouts inside the archive.
- Verify manifest-covered libraries in the copied runtime package before
  archiving. Android also carries a separate
  `android/app/src/main/jniLibs/<ABI>` copy. Verify size and SHA-256 in both
  locations against the same manifest rows. An intact runtime copy must not
  hide a missing or corrupted JNI copy. Guest/license files and original
  producer records remain covered separately.
- Selected-tool command fixtures must expect the absolute alias paths selected
  by the build recipe. Do not weaken them to a basename or stock PATH tool to
  make macOS/Windows pass. Preserve host-specific executable suffixes and
  compare the selected aliases using the fixture's resolved tool root.
- Topic/catalog fixtures bind raw source bytes. Hash the original UTF-8 topic
  bytes, including the intended LF line endings, before parsing. Do not hash a
  reserialized JSON object or silently normalize the bytes inside the verifier.
  Ensure checkout attributes preserve hash-bound JSON bytes on Windows.
- Archive paths preserve native packages, platform library directories and
  `assets/miri/` for restoration at repository root. iOS uses its native host
  triple as package directory; OHOS keeps schema1 and `ohos/entry/libs/<ABI>`.
  Include only the
  selected manifest's asset files, ABI headers, and original build records.
- Runtime packages and diagnostics expire after 14 days. Intermediate guest
  artifacts expire after one day. Never mark failure diagnostics as a runtime.
- Publish only through the orchestra push gate. Verify that the selected
  source origin has GitHub-only fetch and push endpoints before submission.

## 4. Validation and error matrix

| Condition | Required outcome |
| --- | --- |
| Source or toolchain identity mismatch | Fail before compilation |
| Patched compiler provenance mismatch | Fail before adapter/package use |
| Missing dependency on clean runner | Fail with retained step log |
| Missing manifest-covered artifact | Fail before runtime archive publication |
| Copied runtime library size/hash differs | Fail before archive publication |
| Android JNI-only corruption or missing JNI copy | Fail even when runtime copy is intact |
| Selected-tool fixture uses a basename instead of the absolute alias | Fix fixture to the selected recipe path, not the production verifier |
| Raw topic bytes change through checkout conversion | Preserve the bound checkout bytes; do not weaken the hash check |
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
runtime archive creation. Corrupt only the copied runtime library, then only
Android's JNI library, and assert each path independently prevents publication.
Assert selected-tool commands use the complete absolute alias paths on each
host. Raw topic-byte fixtures must distinguish source-byte identity from
semantically equivalent reserialized JSON, including Windows checkout behavior.
A local-registry regression must demonstrate that a
target-only fetch leaves host metadata unavailable offline, then the complete
locked fetch makes that same metadata available from the shared cache. Validate
workflow syntax and execute the workflow
on actual requested hosts. Record run URL, commit and per-job conclusions.

Dated execution evidence: Cloud checks `45894657274` at
`a07511394cfc8a8079e226e37468c571b9d0ed1e` passed all four jobs. Each OS ran
291 native tests with platform-specific skips. This includes the JNI-only
corruption regression, not application helper coverage. Native runtime
`45890222976` at `c859677d482ef358c5aed2efdad7e2daf9a6b288` passed shared guest
and all five mobile target jobs. At the recorded inspection, newer native run
`45894657258` at `a075113` had a successful guest and five running targets.
Do not treat running targets as passed or substitute the older run without the
application resolver's exact input-object comparison. See the parent's dated
execution record for artifacts and finite retention. Application packaging,
signing, target-device checks and Android armv7 remain pending.

## 7. Wrong and correct

Wrong: configure a desktop job with stock rustc-dev and bypass the compiler
record verifier when the adapter fails.

Correct: bootstrap the patched compiler, pass its private/runtime sysroots and
verified record to the adapter, then package and archive verified outputs.

Wrong: verify only `native/build/runtime/<target>` while shipping an unchecked
Android JNI copy, or rewrite a topic fixture as JSON before computing its hash.

Correct: verify both library copies independently against the manifest and
compute topic fixture identity from the exact original bytes.
