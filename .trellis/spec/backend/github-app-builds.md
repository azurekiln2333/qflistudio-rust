# GitHub application CI contracts

All commands below run only on GitHub-hosted Actions runners. Read
[Cloud-only workspace](../guides/cloud-only-workspace.md) first. This contract
records reviewed source, not executed application validation. Application helper,
quality, installer, signing and device validation remain pending.

## 1. Scope / Trigger

Apply to `.github/workflows/app-installers.yml`, `app-quality.yml` and
`tool/ci/{ci_support,app_build,package_installer,app_quality}.py`. Changes to core
checkout, SDK inputs, runtime restoration, packaging or report publication require
these contracts and their failure regressions to remain aligned.

Installer targets are Android `arm64-x64`, iOS `arm64`, OHOS `arm64`, Linux
`x64`, Windows `x64`, and macOS `arm64`/`x64`. Android produces two APKs, not
three-ABI coverage. Android armv7 remains pending across compiler/backend, ELF32,
host selection, NDK triple, ABI maps, Gradle and Dart loading. Desktop packages
require system `cargo` and `rustc`; they do not embed the mobile runtime.

Quality runs on Linux/x64. Its format, analysis and full root `test/` results
are not target-device, native-runtime or installer evidence. Keep parent and
child tasks `in_progress` until their separate acceptance gates pass.

## 2. Signatures (commands)

```text
python tool/ci/app_build.py <stage> [--platform <platform>] [--arch <arch>] [--output-dir <target-dir>]
# stage: init, preflight, verify-core, setup-ohos, resolve-runtime,
#        install-runtime, setup-flutter, build, finalize
python tool/ci/app_build.py install-runtime --source <RUNNER_TEMP/native-runtime> --run-id <positive-id>
python tool/ci/app_build.py finalize --job-status <success|failure|cancelled>
python tool/ci/package_installer.py --platform <platform> --arch <arch>
python tool/ci/app_quality.py <prepare|format|analyze|test|finalize> [--output-dir <quality-dir>] [--bootstrap-dir <bootstrap-dir>] [--job-status <status>]
```

`QFLI_PLATFORM`/`QFLI_ARCH` supply target defaults. Installer bootstrap stages
run in order: `init`, `preflight`, `verify-core`, mobile runtime selection and
installation, platform setup, `setup-flutter`, `build`, `package`, `finalize`.
OHOS additionally requires `setup-ohos`. Finalization requires every applicable
stage, including the package stage, rather than trusting job status alone.

Quality bootstrap uses `app_build.py` stages `init`, `preflight`, `verify-core`,
`setup-flutter` with output `build/app-artifacts/app-quality-linux-x64`.
Then use `app_quality.py prepare`, each check and its own `finalize`. Never use
the installer finalizer as a quality-workflow API.

## 3. Contracts (environment, schemas and bytes)

### Hosted execution and approval

- Require `GITHUB_ACTIONS=true`, `RUNNER_ENVIRONMENT=github-hosted` and
  `RUNNER_TEMP`. Do not invoke helpers locally to exercise this guard.
- Bind reports to `GITHUB_REPOSITORY`, `GITHUB_SHA`, `GITHUB_RUN_ID` and
  `GITHUB_RUN_ATTEMPT`. Checkout HEAD must equal the workflow SHA.
- Workflow variable `QFLI_APPROVED_CORE_SHA` supplies `APPROVED_CORE_SHA` and
  default `CORE_SHA`. A dispatch `core_sha` must match it exactly: 40 lowercase
  hexadecimal characters. Reject superseded `ee83f1c` and `573d1b6` prefixes.
- `QFLI_CORE_SDK_CONTRACT` supplies `CORE_SDK_CONTRACT`. Current source expects
  `flutter-oh-3.41.10-ohos-1.0.1@adaf911c35c9136a7d18fc424d714c9ec7724e60`.
  This is a reviewed baseline recipe, not final Rust compatibility approval.
- No final core SHA, SDK approval or Rust native-hooks recipe has been handed
  off. Do not populate approval variables from provisional core main. A known
  provisional SHA or passing core-only checks cannot satisfy this gate.
- Check out sibling `qflistudio-core` from `azurekiln2333/qflistudio-core`.
  Keep Dart name `qfli_studio_core`. Pubspec, committed lockfile and resolved
  package configuration must agree on `../qflistudio-core` and its
  `vendor/re_editor`. Reject a linked checkout or app `pubspec_overrides.yaml`.

Flutter source is the pinned `openharmony-tpc/flutter_flutter` tag
`3.41.10-ohos-1.0.1` at the commit above. Verify tag, HEAD, Flutter/Dart version,
and immutable `engine.version`, `engine.ohos.version` and
`engine.ohos.har.version`. Retain generated tooling locks with hashes. Record an
in-fork tooling override against its immutable Git blob and SHA-256 if present.
Do not infer that Rust hooks work merely because no external override was
applied. Do not copy an old tooling pin or the app-owned upstream patch.
The baseline setup-script evidence is qflistudio-next
`tool/ci/setup_flutter.sh` at `69656b4ab14e706e85907ef4c4205d8cd35a1338`, blob
`05cb24cc4f0ecc3cbefbf9fe6f8a8e917ac14a05`; its scope is not Rust packaging.

### Runtime selection and producer-byte provenance

`GH_TOKEN` is needed only for runtime metadata. Optional `RUNTIME_RUN_ID` or
`--run-id` selects a positive run ID. Otherwise search compatible successful
runs, not an arbitrary latest artifact. Require a completed successful run from
this repository and head repository, workflow `native-runtime.yml`, branch
`main`, event `push` or `workflow_dispatch`. Compare exact Git object identities
for `native`, `scripts` and `.github/workflows/native-runtime.yml` to app inputs.
Require exactly one unexpired, nonempty artifact per required target, at most
4 GiB each. Record run/attempt/source SHA, artifact IDs, digest and expiry.

Verify archive sidecar SHA-256 and filename before extraction. Confine downloads
to `RUNNER_TEMP`; reject traversal, duplicate members, links, devices, unexpected
roots, more than 50,000 members or more than 4 GiB expanded bytes. Runtime roots
are `assets`, `android`, `ohos`, `native` and `build-info`.

Use schema 2 for Android/iOS and schema 1 for OHOS. Bind manifest target,
Rust version/commit, guest target and compiler boundary to pinned app inputs.
Bind `ci-build.json` to the selected source commit, run and attempt. Verify raw
compiler/adapter record hashes and nested adapter `compilerBuild` identity.
Then bind actual library bytes, not only internally consistent JSON records:

- Adapter bytes must match `adapter.sha256` in the producer record.
- Compiler libraries must map from the adapter inventory into compiler
  `compilerArtifacts` runtime rows. Require producer path, size/hash coverage
  and matching driver/codegen inventory. Compare recorded absolute paths
  lexically across POSIX, drive and UNC namespaces; never open producer paths.
- For untransformed ELF payloads, final hashes equal producer hashes. For Apple
  transformations, bind `sourceSha256` to producer bytes and verify the final
  transformed `sha256` separately. App embedding may re-sign frameworks, but
  stripped-signature executable code must still match the verified input.
- Verify both Android `native/build/runtime/<target>` and
  `android/app/src/main/jniLibs/<ABI>` copies. Bind guest inventory, licenses,
  ABI headers and manifest aliases. Reject extra unverified payload files.

### Typed OHOS no-sign contract

In a clean disposable hosted checkout, temporarily edit both OHOS build files.
Clear `app.signingConfigs`, remove product `signingConfig` and
`compileSdkVersion`, and set `ohos/hvigor/hvigor-config.json5`
`properties.enableSignTask` to the Boolean `false` in an object. A string value,
CLI spelling or environment flag alone is not this typed Hvigor contract.
Build with `flutter build hap --release --no-pub --target lib/main.dart
--no-codesign --target-platform ohos-arm64`. Restore both original files byte
for byte in `finally`, including on failure. Record unsigned state and never
include signing credentials. OHOS API26 SDK source is a checksummed third-party
repackaged mirror, not proof of official producer provenance.

### Installer and intermediate output schemas

Canonical installer output is
`build/app-artifacts/app-installer-<platform>-<arch>/`. `manifest.json` schema 1
contains application/target, source/core/Flutter/runtime identities, `status`,
`stage`, `completedStages`, signing, packages and coverage. Initialization sets
`status=incomplete`, `packages=[]`, `deviceReady=false`, `deviceTests=not_run`
and `applicationUiVerified=false`. A release build only establishes
`core.compatibility=this_platform_release_build_only`.

`reports/packages.json` schema 1 must match platform/arch and the exact
`ci_support.PACKAGE_NAMES` set. Each package records `file`, `format`, positive
`size`, `sha256`, nonempty `validation`, Boolean `installVerified`, signing and
`deviceReady=false`. Preserve OHOS source bundle ID `com.azurekiln.qfli.rust`,
not generic Android/Apple ID `com.azurekiln.qfli.rustcore`. Packaging verification
does not finalize the overall manifest. Only complete stage and package
verification may produce `status=success`; Android coverage still remains
`complete=false` with its armv7 blocker.

| Target | Output and verification boundary | Signing |
| --- | --- | --- |
| Android arm64/x64 | Two single-ABI APKs; Flutter/runtime bytes, ID, zipalign 16 KiB and debug certificate | Testing debug key, not store release |
| iOS arm64 | IPA Payload layout, device architecture, Flutter/framework bytes and code identity; no app profile/signature | Unsigned, not device-ready |
| OHOS arm64 | One unsigned HAP; source bundle ID, entry module, ABI, Flutter bytes and schema-1 runtime hashes | Unsigned, signature not verified |
| Linux x64 | DEB metadata, hosted install, installed hashes, dependencies and uninstall | Not applicable |
| Windows x64 | Inno Setup EXE, x64 PE, silent hosted install, hashes and uninstall | Unsigned executable |
| macOS arm64/x64 | DMG with selected architecture and ad hoc app verification | Ad hoc, not notarized |

Installer packages are bounded to 8 GiB total. Reports/licenses are bounded to
2,000 files and 128 MiB. Upload packages/reports as
`app-installer-<platform>-<arch>` for 14 days. Failure/cancellation must retain a
failure report, not publish packages as successful. Remove package outputs and
the stale package report on finalization failure. Recompute `SHA256SUMS` after
all final manifest writes. Publication/checksum errors must also fail closed.
B's frozen source now invalidates package outputs and stale checksums on that
failure boundary; source review is underway and hosted regressions remain
pending. This source change is not an executed application-helper pass.

Intermediates are separate `app-intermediates-<platform>-<arch>` artifacts under
`build/app-intermediates/<platform>-<arch>/`, retained one day. Archive the exact
Flutter inputs consumed by packaging: split APKs, unsigned HAP, Runner.app,
Linux bundle, Windows Release bundle or macOS app. Retain actual bytes in
`flutter-packaging-inputs.tar.gz`, not only an inventory. `selection.json`
records per-file size/hash, directory/link entries, archive hash/size,
`uncompressedBytes`, limits and
`artifactKind=unverified_packaging_inputs_not_installers`. `provenance.json`
binds source/core/SDK/runtime; include resolved dependency evidence and checksums.
Limit selected/archive bytes to 4 GiB and members to 30,000. Preserve only safe
relative links within a selected bundle. Reject escapes, junctions, duplicates
and changes before archiving. Remove partial output on failure. Never upload
SDK, compiler, Gradle/Hvigor/CMake caches or the whole build root.

### Quality-only reports

Output is `build/app-quality/linux-x64/`, artifact
`application-quality-linux-x64`, retained 14 days. Schema 1 has
`artifactKind=application_quality_not_an_installer`, `prepared`, source/core/SDK
identities, input hashes and `checks.{format,analyze,test}.status`. Status starts
`incomplete`; checks start `not_run`. Preparation verifies approved bootstrap,
clean tracked app/core source, resolved dependency paths, SDK executable/engine
and tooling-lock hashes. Dependency restoration must not change tracked inputs.
Remove read tokens from check subprocess environments.

Commands are non-mutating Dart format over `lib test integration_test`,
`flutter analyze --no-pub`, and exactly `flutter test --no-pub --machine test`.
The dedicated `run_machine` captures full machine-protocol stdout privately in
`RUNNER_TEMP`, with stderr in a separate file. Do not use `--file-reporter`,
`--reporter=expanded`, a filtered test selection or the shared bounded/redacted
merged-output helper to capture the protocol. Parse the complete private stdout;
limit accepted protocol to 128 MiB and 1,000,000 events. Publish only bounded,
redacted stdout/stderr tails, never the raw protocol or raw stderr.

Validate every tracked root test suite, positive passed count, no
failed/unfinished cases and exactly one successful protocol completion. Preserve
skips as `passed_with_skips`, never device/native passes. Publish sanitized
`reports/root-tests.json` with counts, missing suites, skipped names, errors and
raw-report hash/size; do not publish raw events.

Finalization independently verifies all checks and rechecks the persisted root
test summary against manifest evidence, complete suite coverage and skip status.
Report `blocked` when approval or preparation never completed, `failed` after
prepared failures, `cancelled` for cancellation, or `passed`/`passed_with_skips`
only for complete evidence. Always keep `deviceExecuted=false`,
`nativeRuntimeExecuted=false` and `applicationUiVerified=false`.

Final manifest write, report bounds, checksum generation, final bounds and step
summary share one failure boundary. Remove previous checksums before finalizing;
write checksums through `.SHA256SUMS.pending` and replace `SHA256SUMS` only after
the complete checksum file is written. Limit reports to 200 files/32 MiB. On any
publication-boundary failure, revoke candidate success, remove stale manifest
and checksum files, and attempt bounded failed diagnostics. Recovery is best
effort on a broken filesystem; failed recovery cannot establish publication.
Preserve individual check outcomes without retaining a successful overall
claim. `publication.status=complete` means runner report files only, with
`scope=runner_report_files_only` and
`artifactUpload=not_established_by_helper`; workflow artifact upload must
separately succeed. Installer-finalizer behavior is not evidence for this path.
These are C's final source contracts. Its machine-capture and finalizer failure
regressions are authored but UNRUN. No application helper, format, analysis or
root-test execution pass is established.

## 4. Validation & Error Matrix

| Condition | Required outcome |
| --- | --- |
| Non-hosted invocation | Reject before restore/build/check execution |
| Missing final core/SDK approval, mismatched SHA or stale paths | Fail preflight/bootstrap; quality reports blocked, not skipped success |
| Fork run, wrong source objects, expired runtime or bad checksum | Reject selection/install with source-bound diagnostics |
| Producer hashes disagree, JNI-only corruption or extra payload | Reject before Flutter embedding |
| OHOS typed properties malformed or build fails | Fail and restore both original config byte sequences |
| Missing package, wrong ABI/ID/runtime bytes or absent install evidence | No successful installer publication |
| Intermediate bound/link/hash violation | Remove partial intermediate output and fail |
| Missing root suite, incomplete protocol, all-skipped or changed inputs | Quality cannot pass |
| Package/checksum/report publication failure | Revoke candidate success; report-file completion does not prove artifact upload; hosted regressions pending |
| Native-only/helper-only success | Application, signing, armv7 and device acceptance remain pending |

## 5. Good / Base / Bad Cases

- Good: owner approves immutable inputs, a fresh hosted runner verifies the
  producer-to-package byte chain, checks the exact installer set and publishes
  bounded reports with honest signing/device limits.
- Base: approval is absent. Independent helper contracts can run; core-bound
  application jobs fail with blocked evidence rather than becoming skipped passes.
- Bad: approve provisional main, trust a recent runtime by name, rehash fabricated
  producer records, supply string `"false"` to Hvigor, upload an inventory as
  intermediate bytes, or label two debug APKs complete Android release coverage.

## 6. Tests Required (assertion points)

Run on GitHub-hosted runners only:

```text
python -m unittest discover -s tool/ci -p 'test_*.py' -v
```

Assert hosted guard, target allowlist, core approval/path/lock/SDK identity,
runtime API source/expiry/input-object rejection, safe extraction and duplicate
handling. Mutate producer adapter/compiler bytes while recomputing surrounding
record hashes: verification must still reject broken producer bindings. Cover
Apple source/final hashes, Windows producer paths, guest coverage and JNI-only
corruption. Cover typed Boolean no-sign configuration and byte-exact restoration
on success/failure. Assert actual intermediate archive bytes, per-file hashes,
safe links, limits and partial-output removal.

Package tests must reject missing/extra packages, wrong ABI, wrong OHOS ID,
stale runtime bytes, dishonest signing/device flags and absent desktop install
verification. Require finalizer checksum/publication-failure cleanup assertions
for both installer and quality reports. C's authored quality regressions cover
private machine capture with separate stderr, redacted published logs, nonzero
exit, checksum/hash-read failure, partial checksum plus diagnostic failure,
manifest-write failure and summary failure. They remain UNRUN. Quality tests
must also cover missing approval, input/SDK drift, source mutation, missing
suite, malformed/incomplete protocol, all-skipped results, explicit skips and
no installer-finalizer coupling. B's frozen finalizer source remains under
review; hosted installer-finalizer regressions are pending.

Validate workflow syntax, immutable action pins and Node 24 action runtimes.
Then execute real approved-input quality and six-platform application builds,
format-specific installer checks and upload/retention checks. Record app/core
SHAs, SDK/runtime identities, run/attempt/job results and output digests. No app
helper or application pass is established by Cloud checks 45894657274 at
`a075113`; those application files were not in that commit. Actual application
validation remains pending.

## 7. Wrong vs Correct

Wrong: choose the latest successful native artifact, verify only its outer hash,
reuse generic IDs and mark an unsigned HAP plus logs as a completed installer.

Correct: require owner-approved core/SDK inputs, compare exact native input Git
objects, verify producer and both copied-library byte chains, preserve OHOS ID,
validate the exact package set and publish final-byte checksums. Report unsigned,
armv7, device and unexecuted application gates separately.
