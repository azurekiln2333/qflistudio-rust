# Build installer packages on GitHub

## Goal

GitHub Actions builds installable packages of QFLIRustCore for Android, iOS,
OHOS, Linux, Windows and macOS. A push to `main` starts the builds. Each
platform uploads its package with checksums and a build record.

## Confirmed facts

- `.github/workflows/native-runtime.yml` is the only workflow. It builds the
  embedded Rust runtime archives for Android arm64/x64, OHOS arm64/x64 and iOS
  arm64. It builds no application and no installer.
- Run `44012848384` of that workflow succeeded on `main` (commit `540674f`).
  Its artifacts expire 14 days after 2026-11-17.
- Android, iOS and OHOS applications embed the runtime. Android Gradle fails
  without it (`checkAndroidRustRuntime`). The runtime files are not tracked.
- Desktop applications start the system `cargo` and `rustc`
  (`lib/rust_runner.dart`). They embed no runtime.
- The application depends on the sibling checkout `../qfli_studio_core`. The
  GitHub repository `azurekiln2333/qflistudio-core` has `main` at `573d1b6`.
- The project uses the Flutter-OH fork. The sibling project `qfli_lua` builds
  all six platforms with tag `3.41.9+ohos-1.0.2` on hosted runners.
- The repository holds no signing secrets. `ohos/build-profile.json5` contains
  a signing configuration that only works on the developer machine.
- A push that changes `scripts/**` or `native/**` starts the native runtime
  workflow (about 100 minutes).

## Requirements

- R1. One workflow builds seven jobs: Android APK for arm64-v8a, armeabi-v7a
  and x86_64 (one job, three APKs),
  iOS IPA for arm64, OHOS HAP for arm64-v8a, Linux `.deb` for x64, Windows
  setup program for x64, macOS `.dmg` for arm64 and for x64.
- R2. The workflow starts on a push to `main` that changes application or
  packaging inputs, and on manual dispatch.
- R3. Mobile jobs take the runtime from a successful `Native runtime` run on
  `main`. Manual dispatch can name the run. The job verifies archive
  checksums, library hashes and the ABI headers before the build.
- R4. Every third-party input is pinned: actions by commit, Flutter-OH by tag
  and commit, HarmonyOS tools by SHA-256, the core checkout by commit.
- R5. Each job verifies its package as far as a hosted runner allows: install
  and remove for Windows and Linux, mount and signature check for macOS,
  archive content checks for Android, iOS and OHOS.
- R6. Each artifact contains the package, `SHA256SUMS`, a signing note, a
  manifest with source commits and validation results, and build logs.
- R7. The signing state is stated exactly: Android debug key, iOS unsigned,
  OHOS unsigned, macOS ad hoc and not notarized, Windows unsigned.
- R8. A failed job uploads its logs and reports the failing command as an
  error annotation. A failed job never labels an output as a package.
- R9. The native runtime workflow gains one target, `android-armv7`
  (`armv7-linux-androideabi`, ABI `armeabi-v7a`). Its other targets stay
  unchanged. Desktop targets need no native runtime.
- R12. Every action in every workflow is pinned to a commit whose `action.yml`
  declares `runs.using: node24`. No run shows the annotation
  "Node.js 20 is deprecated". A hermetic test enforces the pin list.
- R10. A Chinese document describes triggers, outputs, signing states and
  limits. It follows the controlled Chinese rules of this repository.
- R11. Commits use Conventional Commits and carry no AI attribution. Pushes go
  only to the GitHub remote URL.

## Acceptance

- Helper unit tests pass locally and in every job.
- The workflow file parses and every action is pinned by commit.
- A real run on `main` is observed. The report lists the real result of each
  of the seven jobs with the run URL. The Android job lists three APKs.
- A real `Native runtime` run on `main` builds `android-armv7`, or the report
  states the blocking failure with evidence.
- No run annotation mentions Node.js 20.
- Reproducible failures are fixed and re-run, or reported with evidence.
- No commit in the pushed range contains an AI attribution line.

## Out of scope

- Store signing, notarization, provisioning profiles and release publishing.
- Device, emulator and UI tests of the installed applications.
- Windows arm64, Linux arm64, 32-bit Windows and Linux (Flutter supports
  neither), and OHOS x86_64 packages.
- Changes to application code. Native workflow changes beyond R9.
- Removal of the local signing configuration from `ohos/build-profile.json5`.
