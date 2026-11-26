# Installer helper contract

This describes `tool/ci/package_installer.py`. It is implementation guidance,
not a record of passing checks. No local validation was performed.

## Invocation and ownership

Run only in a GitHub-hosted job:

```text
python tool/ci/package_installer.py --platform <platform> --arch <arch>
```

The helper uses `ci_support.TARGETS`, `PACKAGE_NAMES`, `SIGNING` and the existing
process runner. `--output-dir` must resolve below `build/app-artifacts`.
Canonical output remains
`build/app-artifacts/app-installer-<platform>-<arch>`.
`RUNNER_TEMP` holds package assembly, installer verification and mount scratch.
Only the verified publication copy is temporarily inside the artifact directory.
Build outputs are read from the hosted checkout, never created by this helper.

The helper requires a completed build stage in the initialized `manifest.json`.
It preserves source/core/Flutter/runtime provenance fields. On packaging success it writes:

- `packages/`: the exact declared filenames, promoted as one directory.
- `reports/packages.json`: schema 1, platform, arch, packages and coverage.
- `SIGNING.txt`: actual signing limitations and device-readiness disclaimer.
- `SHA256SUMS`: sorted hashes for all regular artifact files except itself.
- Updated manifest: `stage: package`, `packageStatus: verified`, package rows,
  `deviceReady: false`, `deviceTests: not_run`, `applicationUiVerified: false`.

Package rows include `file`, `format`, `size`, `sha256`, `validation`,
`installVerified`, `signing` and `deviceReady`. Overall manifest status remains
`incomplete` until orchestration finalization. A later stage failure must remove
packages. Finalization must verify the rows and regenerate `SHA256SUMS` after
its final manifest/log writes. Import `write_checksums(output)` or implement the
same sorted, no-links contract.

All package checks must finish before publication. A failure removes visible
packages, the hidden publication copy and `reports/packages.json`. Diagnostics
remain. The manifest records failure/cancellation and an empty package list.
Checksums then describe diagnostics only. Interrupted or killed runners still
need orchestration's always-run finalizer for cleanup.

## Platform checks

| Target | Hosted checks | Explicit limit |
| --- | --- | --- |
| Android arm64-x64 | Single ABI, aapt2 bundle ID, Flutter payload, selected native manifest and file hashes, zipalign 16-KiB check, apksigner verification with debug-key identity | Two APKs only. No emulator install, app launch or store signing. |
| iOS arm64 | Bundle ID, arm64 executable, runtime framework SDK/platform, signatures, code comparison against inputs after removing signatures from scratch copies, deterministic IPA ZIP layout, guest hashes, no app provisioning profile/signature | Unsigned developer IPA, not device-ready. Final native hashes are recorded because re-signing changes bytes. |
| OHOS arm64 | Source bundle ID, entry module, one ABI, Flutter payload, schema-1 runtime and asset hashes | Unsigned build product. ZIP checks do not validate a HAP signing block. |
| Linux x64 | Bundle/control fields, apt install, installed file hashes, launcher, ldd dependencies, apt remove | Never launches the application. Requires system cargo/rustc. |
| Windows x64 | PE machine, Inno Setup build, per-user silent install, file hashes, silent uninstall and cleanup | Unsigned setup program. Never launches the application. |
| macOS arm64/x64 | Bundle ID, architecture, ad hoc signature, DMG verification, read-only mount, mounted hashes and Applications link | No notarization, app launch or UI test. |

## Blockers that must remain visible

Android's old three-ABI requirement is not complete. Only `arm64-x64` is
accepted by the helper. `all` and armv7 fail explicitly. An Android result sets
`packageCoverage.complete: false` with the armv7 blocker. Finalization must
preserve it. Do not report two APKs as satisfaction of three-ABI acceptance.
Armv7 needs compiler/backend feasibility plus host, NDK triple, ELF32, ABI and
Gradle changes outside this helper.

OHOS uses schema 1 with `nativeHost` and library `name`. It does not require
schema-2 `platform`, `architecture` or `path` fields. The HAP bundle identity
comes from `ohos/AppScope/app.json5`; the current value differs from generic
`ci_support.APP_ID`. The package row records `bundleIdentifier`. The source
profile currently parses as strict JSON. If it becomes general JSON5, use a
reviewed parser contract rather than guessing.

Native archive/run/ABI-header/producer-record verification belongs to
`app_build install-runtime` before the Flutter build. Package checks bind the
embedded selected manifest and payload to those prepared inputs. They do not
replace upstream native provenance validation or establish an attestation.

Staging traversal, checksums and IPA ZIP member ordering/timestamps are
controlled. This does not claim byte-for-byte reproducible SDK outputs,
cryptographic signatures, Inno Setup executables or DMG filesystem images.

## GitHub checks still required

```text
python -m unittest discover -s tool/ci -p "test_*.py" -v
```

Execute discovery only on a GitHub-hosted runner. The packaging test module
also checks hosted-runner context during discovery. Its fixtures mock external
tools; they do not install anything. They cover path confinement, archive
ambiguity/links, stable ZIP ordering, schema-1 compatibility, payload tampering,
armv7 rejection, OHOS identity, checksums, cancellation and failed publication.

Actual six-platform packaging jobs must separately exercise the real platform
tools and install/uninstall/mount checks. Native ELF hashes stay strict; if
Gradle or Hvigor strips a manifest-covered dependency, fix or explicitly review
the upstream transform rather than bypassing the mismatch. Record real app/core/runtime SHAs,
run/job results, packages, signing status and artifact retention. No test or
build success is claimed by this document.
