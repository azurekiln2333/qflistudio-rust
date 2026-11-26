# Design

## Boundaries

A new workflow `.github/workflows/app-installers.yml` ("App installers") builds
the Flutter application and its installer for seven targets. Python helpers
under `tool/ci/` hold all logic. The workflow file only orders steps.

The helpers live under `tool/ci/`, not `scripts/`. A push that changes
`scripts/**` starts the native runtime workflow, which takes about 100 minutes.
Application code stays unchanged. The native runtime workflow and its
helpers change only to add `android-armv7` (see "Native armeabi-v7a").

| File | Role |
| --- | --- |
| `tool/ci/ci_support.py` | Shared constants, target table, process runner, annotations, checksums |
| `tool/ci/app_build.py` | Stages `init`, `setup-ohos`, `resolve-runtime`, `install-runtime`, `setup-flutter`, `build`, `finalize` |
| `tool/ci/package_installer.py` | Creates and verifies the installer packages of one target |
| `tool/ci/windows_installer.iss` | Inno Setup script for the Windows setup program |
| `tool/ci/test_*.py` | Hermetic unit tests (no network, no Flutter, any host OS) |
| `docs/app-installers.zh-CN.md` | User document in controlled Chinese |

## Targets

| Platform | Arch value | Runner | Runtime archives | Package files |
| --- | --- | --- | --- | --- |
| android | `all` | ubuntu-24.04 | `android-arm64`, `android-armv7`, `android-x64` | `QFLIRustCore-android-arm64-v8a-test-signed.apk`, `QFLIRustCore-android-armeabi-v7a-test-signed.apk`, `QFLIRustCore-android-x86_64-test-signed.apk` |
| ios | `arm64` | macos-15-intel | `ios-arm64` | `QFLIRustCore-ios-arm64-unsigned.ipa` |
| ohos | `arm64` | ubuntu-24.04 | `ohos-arm64` | `QFLIRustCore-ohos-arm64-v8a-unsigned.hap` |
| linux | `x64` | ubuntu-24.04 | none | `QFLIRustCore-linux-x64.deb` |
| windows | `x64` | windows-2022 | none | `QFLIRustCore-windows-x64-setup.exe` |
| macos | `arm64` | macos-26 | none | `QFLIRustCore-macos-arm64.dmg` |
| macos | `x64` | macos-15-intel | none | `QFLIRustCore-macos-x64.dmg` |

`ci_support.TARGETS` and `ci_support.PACKAGE_NAMES` hold this table. Both
helpers reject any other platform and arch pair. The runners follow proven
precedents: `qfli_lua` builds the same Flutter-OH release on these Linux and
macOS images, and `qfli_dart` runs Inno Setup on `windows-2022`.

Desktop applications start the system `cargo` and `rustc`. They embed no
runtime, so desktop jobs skip the runtime stages.

## Workflow

Triggers: `workflow_dispatch` with the optional input `runtime_run_id`, and
`push` to `main` filtered to `.github/workflows/app-installers.yml`,
`tool/ci/**`, `lib/**`, `assets/**`, `android/**`, `ios/**`, `linux/**`,
`macos/**`, `ohos/**`, `windows/**`, `pubspec.yaml`, `pubspec.lock`.

Permissions are `contents: read` and `actions: read`. The second one lets the
job token list runs and download artifacts of another run. Concurrency groups
by ref and cancels the older run: installer builds are short and keep no
long-lived state. The matrix sets `fail-fast: false`, a 90 minute limit, `bash`
as shell and `qfli_rust` as working directory.

Step order per job:

1. Check out the application into `qfli_rust` and the core at the pinned commit
   into `qfli_studio_core`, both without persisted credentials.
2. Set up Python 3.13. Run `app_build.py init`, then the helper unit tests.
3. Linux: install the GTK build packages. Android and OHOS: Java 17. Android:
   NDK `27.0.12077973`. OHOS: `json5==0.12.1` and `app_build.py setup-ohos`.
4. Mobile only: `app_build.py resolve-runtime` (step id `runtime`), then
   `actions/download-artifact` with `run-id`, `github-token`, `pattern` and
   `merge-multiple: true` into `$RUNNER_TEMP/native-runtime`, then
   `app_build.py install-runtime --source <dir> --run-id <id>`.
5. `app_build.py setup-flutter`, `app_build.py build`, `package_installer.py`.
6. Always: `app_build.py finalize --job-status "$JOB_STATUS"`, then upload
   `build/app-artifacts/app-installer-<platform>-<arch>/` as the artifact
   `app-installer-<platform>-<arch>` (14 days, no recompression, warn when
   empty).

## Output layout

```text
build/app-artifacts/app-installer-<platform>-<arch>/
  packages/           verified packages only
  reports/            logs, records, packages.json, native-runtime/<key>/build-info/
  licenses/
  manifest.json
  SIGNING.txt
  SHA256SUMS          every file below this directory except itself
```

`manifest.json` uses camelCase keys: `schemaVersion` 1, `application` (name,
id, version), `platform`, `arch`, `status` (`incomplete`, `success`, `failed`,
`cancelled`), `stage`, `completedStages`, `source` (repository, commit, ref,
runId, runAttempt), `core` (repository, commit), `flutter` (repository, tag,
commit, engine, ohosEngine, toolingOverride, version), `nativeRuntime` (null on
desktop), `signing`, `packages`, `deviceTests: "not_run"`,
`applicationUiVerified: false` and `error` when a stage failed.

`init` creates the manifest. Every stage loads it, sets `stage`, appends to
`completedStages` on success and writes it back. A stage failure writes
`reports/<stage>-failure.txt`, stores `error`, and emits a bounded and redacted
`::error::` annotation. Job logs need a login to download. Annotations are
readable through the public checks API, so they carry the diagnostics.

## Package contract between the helpers

`package_installer.py` reads the Flutter build output of the checkout. It
builds every package of the target in a staging directory outside the artifact
directory and verifies each one. Only when all pass, it moves them into
`packages/` and writes `reports/packages.json`:

```json
{"schemaVersion": 1, "platform": "linux", "arch": "x64", "packages": [
  {"file": "QFLIRustCore-linux-x64.deb", "format": "deb", "sha256": "…",
   "size": 1, "validation": ["bundle-layout", "apt-install", "apt-remove"],
   "installVerified": true}]}
```

A failure leaves `packages/` and `packages.json` absent. `finalize` requires
exactly the names of `PACKAGE_NAMES` when the job status is `success`. On any
other status, or when a name is missing, it deletes `packages/`, records
`packages: []` and reports `failed` or `cancelled`. An output is therefore
never labelled as a package after a failure.

## Native runtime

`resolve-runtime` selects the run. With `RUNTIME_RUN_ID` it requires a
completed, successful run of `.github/workflows/native-runtime.yml` in this
repository (not a fork) started by `push` or `workflow_dispatch`. Without it,
it lists successful runs of that workflow on `main`, newest first, and takes
the first whose required artifacts all exist and are not expired. It uses the
REST API with the job token through `urllib`, never prints the token, writes
`run_id` to `GITHUB_OUTPUT` and records `reports/native-runtime-source.json`.
No candidate is an error that tells the reader to dispatch `Native runtime`.

`install-runtime` processes each required archive `native-runtime-<key>.tar.gz`:

1. Verify the `.sha256` file (two fields, matching name and digest).
2. Extract with `tarfile` and `filter="data"` into a new temporary directory.
3. Read `assets/miri/manifest.<key>.json`. Require the platform, architecture,
   `rustVersion` and `rustCommit` of this checkout (imported from
   `scripts/miri_build_support.py`, the single source of the pinned identity).
4. Verify every native library by SHA-256, and by size when the manifest
   states one. Schema 2 entries use `path`, schema 1 (OHOS) entries use `name`.
   Libraries live in `android/app/src/main/jniLibs/<abi>/`,
   `native/build/runtime/aarch64-apple-ios/` or `ohos/entry/libs/<abi>/`.
5. Verify every guest file `assets/miri/<asset>` by size and SHA-256.
6. Compare `native/include/qfli_miri.h` and `qfli_debug.h` with
   `native/miri_adapter/` of the checkout, ignoring line-ending style. A
   difference means the runtime was built for another ABI revision.
7. Require `build-info/ci-build.json` to name the resolved run.
8. Copy `android/app/src/main/jniLibs`, `ohos/entry/libs`,
   `native/build/runtime` and `assets/miri` into the checkout. Refuse to
   replace an existing file that has other content.
9. Keep `build-info/` under `reports/native-runtime/<key>/` and record run,
   source commit, Rust identity, archive digest and file counts in the manifest.

Runtime artifacts expire after 14 days. After that the mobile jobs fail until
`Native runtime` runs again. This is documented, not hidden.

## Build

`setup-ohos`, `setup-flutter` and the unsigned OHOS profile follow
`qfli_lua/tools/ci_app_build.py`, which builds these platforms with the same
pinned Flutter-OH release, tooling override and HarmonyOS command-line tools.
OHOS support is enabled only in the OHOS job. The OHOS job rewrites the
checkout copy of `ohos/build-profile.json5` without signing configuration and
never prints the committed one.

`build` verifies the core and Flutter checkouts, runs `flutter pub get`, keeps
the resolved `pubspec.lock` as a report and runs one release build:

- android: `flutter build apk --release --no-pub --target lib/main.dart
  --target-platform android-arm,android-arm64,android-x64 --split-per-abi`
- ios: `flutter build ios --release --no-pub --no-codesign --target lib/main.dart`
- ohos: `flutter build hap --release --no-pub --no-codesign --target
  lib/main.dart --target-platform ohos-arm64`
- linux, windows, macos: `flutter build <platform> --release --no-pub --target
  lib/main.dart`; macOS sets `FLUTTER_XCODE_ARCHS` to the job architecture,
  `FLUTTER_XCODE_ONLY_ACTIVE_ARCH=YES` and ad hoc manual signing.

## Packages and verification

| Target | Package | Checks on the runner |
| --- | --- | --- |
| android | Split APK per ABI, signed with the debug key | One ABI under `lib/`; Flutter engine, application snapshot and every runtime library of the manifest; runtime manifest asset; `zipalign -c -P 16`; `apksigner verify` |
| ios | `Payload/Runner.app` zipped as IPA, unsigned | Entries only under `Payload/`; `Info.plist` bundle ID; Flutter and App frameworks; runtime frameworks of the manifest; no provisioning profile |
| ohos | Unsigned HAP | `module.json`; `libs/arm64-v8a` only; Flutter engine, application snapshot and runtime libraries; runtime manifest asset |
| linux | `.deb` with `/opt/qfli-rust-core`, launcher, desktop entry, icon | Control fields; `apt-get install`; launcher and `ldd` resolution; `apt-get remove` |
| windows | Inno Setup program, per-user by default | Silent install into a temporary directory; file set equals the bundle; silent uninstall |
| macos | `.dmg` with the application and an `/Applications` link | `hdiutil verify`; mount; `lipo -verify_arch`; `codesign --verify --deep --strict` |

No job starts the application. The manifest states `deviceTests: "not_run"`
and `applicationUiVerified: false`.

Signing states: Android debug key (test only), iOS unsigned, OHOS unsigned,
macOS ad hoc and not notarized, Windows unsigned, Linux not applicable. iOS and
OHOS packages need signing before they install on a device. `SIGNING.txt`
states this next to the package.

## Native armeabi-v7a

`scripts/ci_native_runtime.py` adds the matrix row `ubuntu-24.04`,
`x86_64-unknown-linux-gnu`, `armv7-linux-androideabi`, `android-armv7`. Every
host-to-ABI mapping in the native helpers maps `armv7` to `armeabi-v7a`
instead of falling back to `x86_64`. The runtime manifest is
`manifest.android-armv7.json`. The libraries live in
`android/app/src/main/jniLibs/armeabi-v7a/`.

## Action pins (Node 24)

`ci_support.ACTION_PINS` lists every allowed `owner/repo@sha` with its tag.
Each entry was checked against its `action.yml`: `runs.using` is `node24`.
`test_action_pins.py` parses every file under `.github/workflows/` and fails
when a `uses:` reference is missing from the list or not a 40-hex commit.
Adding an action means checking its `action.yml` first.

## Tradeoffs

- One helper suite for all platforms instead of two per-platform scripts: one
  manifest format and one failure path.
- The runtime comes from a previous run, not from a rebuild. A rebuild costs
  100 minutes per target. The price is the 14 day artifact lifetime.
- `cancel-in-progress: true` differs from the native runtime workflow, which
  must finish long builds. Installer builds restart cheaply.
- No `workflow_run` chain from `Native runtime`. It cannot be observed without
  a new runtime build. After a runtime change the user dispatches manually.

## Rollback

Delete the workflow file, `tool/ci/` and the document. No other file depends on
them. Artifacts expire on their own.
