# Android and OHOS build verification

Date: 2026-10-15. All commands below ran from
`D:/MyNewProjects/qfli_rust`, or its explicitly named `ohos` directory.
Sibling application repositories and shared-core source were not modified.
The coordinator owns Git commits and final content/profile integration.

## Toolchain and packaged inputs

- Flutter: `D:/ProgramFiles/flutter_ohos/bin/flutter.bat`,
  `3.27.5-ohos-1.0.1`; bundled Dart 3.11.5.
- Windows Rust: `native/build/miri-windows/compiler/bin/rustc.exe`,
  Rust 1.98.1 / `48a229ceaefd4985c50990b14116b6d856af0985`,
  host `x86_64-pc-windows-gnu`; Cargo 1.98.1.
- Android SDK: `D:/ProgramData/Android/Sdk`, complete NDK
  `27.0.12077973`, CMake `3.22.1`; SDK build tools `36.1.0`.
- OHOS SDK: `D:/ProgramFiles/Huawei/OpenHarmony/Sdk/23` plus DevEco SDK.
  Java/Node/Hvigor came from `D:/ProgramFiles/Huawei/DevEco Studio`.
- Real ignored assets exist: both Android schema-2 manifests and native
  libraries, plus OHOS schema-1 manifest. `.gitkeep` being the only tracked
  runtime asset does not mean the local runtime is missing.
- Both Android manifests: all 3 native libraries and 97 guest/license asset
  entries matched size and SHA-256. Original OHOS x64: 3 native libraries and
  98 assets matched SHA-256. No fake libraries or manifest placeholders used.

## Fixed local defects

- `scripts/check_native_packaging.py`: a relative `--toolchain` reached
  CMake's generated source directory as a relative DLL path and failed the
  real install probe. Resolve the toolchain before composing CMake inputs.
  Both relative and absolute invocations now pass.
- `integration_test/rust_native_test.dart`: require the actual native host to
  belong to the selected device target instead of hardcoding Android x64.
- The same integration test used the obsolete editor Run tooltip. Updated
  all 3 taps to the shared core's `运行（长按运行当前文件）` contract. Removed
  the unrelated x64-only profile availability assertion; actual native
  execution and editor output remain asserted.
- OHOS `EntryAbility.ets` still registered a real Account Kit `login`
  bridge even though the shared offline profile hides login. Removed the
  Rust-only Huawei account channel, its SDK import and channel constant,
  together with the unresolved `REPLACE_WITH_AGC_CLIENT_ID` module metadata.
  Local picker, share, startup progress and agreement handling are preserved.
  Android's sole custom channel resolves the native runtime library directory;
  no Android account/login bridge was present.

## Platform offline and identity audit

- Android's built release APK has no INTERNET permission. The only declared
  permission in `aapt dump permissions` is its own dynamic-receiver permission.
- OHOS retains INTERNET for Flutter's debug/service workflow and the existing
  agreement webview. Source search found the account bridge described above
  and agreement/browser URL handlers; no additional Rust-native Git, cloud
  terminal, HTTP client or WebSocket implementation was found.
- The shared agreement caller lives under `pages/auth/`; the offline profile
  hides that authentication flow. Keeping the platform agreement reader does
  not expose an account/login capability. Shared core UI/network policy is
  reviewed independently by the coordinator and terminal worker.
- Verified product identity from actual package metadata:
  Android APK `com.azurekiln.qfli.rustcore`; Android device test package
  `com.azurekiln.qfli.rustcore.integrationtest`; OHOS HAP `module.json` app
  bundle name `com.azurekiln.qfli.rustcore`, module `entry`. No neighboring
  product's ID, signing identity, or application data was substituted.

## Host validation

```powershell
python scripts/check_native_packaging.py `
  --toolchain native/build/miri-windows/compiler `
  --ndk D:/ProgramData/Android/Sdk/ndk/27.0.12077973 `
  --cmake D:/ProgramData/Android/Sdk/cmake/3.22.1/bin/cmake.exe
python -m unittest discover -s scripts -p 'test_*.py' -v
python -m compileall -q scripts
& D:/ProgramFiles/flutter_ohos/bin/cache/dart-sdk/bin/dart.exe analyze integration_test/rust_native_test.dart
```

All exited 0: actual NDK arm64/x64 links and ELF inspection, Windows compiler
DLL import comparison with LLVM, real CMake DLL installation and missing-file
rejection; 6 Python bootstrap tests; Python compilation; Dart analysis with no
issues. The coordinator runs whole-app analysis/unit/widget checks separately.

## Android build and real device tests

Successful baseline command (exit 0, 153.2 seconds):

```powershell
flutter build apk --release --target-platform android-arm64,android-x64
```

Actual command used the absolute Flutter path above. Baseline artifact:

- `build/app/outputs/flutter-apk/app-release.apk`
- 153,965,590 bytes (Flutter reports 146.8 MB).
- SHA-256 `3d2eb6332b34fa36991013f9b84618cb9c28b09c91c756223090352d86c36a75`.
- ZIP audit found both native architectures, each adapter/driver/backend and
  both Android manifests with every referenced guest asset present.
- All 10 bundled `.so` files passed native inspection. Rust libraries have
  16,384-byte LOAD alignment; Flutter/app libraries have 65,536-byte alignment.
- `apksigner verify --print-certs` succeeded. Certificate subject is
  `C=US, O=Android, CN=Android Debug`: production signing remains a store
  release prerequisite. The project explicitly signs release with the debug key.

Earlier commands failed first on Maven TLS downloads, then on a generated
plugin registrant containing dev-only `integration_test` during release Java
compilation. Serializing Rust-workspace Flutter commands and running the
normal pub/tooling preparation produced the successful release build.
Do not run Flutter pub/test/build commands concurrently against this workspace
while preparing release registrants.

Authorized reachable Android device: OPD2413, `arm64-v8a`. Its mDNS name
contains a space and Flutter truncates it; read `adb mdns services`, then
`adb connect 192.168.68.236:35991` provided a stable selectable serial.

```powershell
flutter build apk --debug --target-platform android-arm64 --target integration_test/rust_native_test.dart
aapt dump badging build/app/outputs/flutter-apk/app-debug.apk
flutter test integration_test/rust_native_test.dart -d 192.168.68.236:35991 --no-pub
```

Pre-install APK inspection confirmed
`com.azurekiln.qfli.rustcore.integrationtest` and only `arm64-v8a`.
No ordinary application ID was installed or overwritten. The final test run
exited 0, **6/6 tests passed**, after a 17.1-second test build and 23.5-second
install; actual device tests took 7 seconds:

1. Automatic mobile runner executes Rust modules and generics.
2. stdin, EOF, UTF-8 and guest nonzero exit survive native calls.
3. Real compiler borrow diagnostics replace previous output.
4. Execution, output and guest memory limits are enforced.
5. Cancellation completes before a fresh successful native run.
6. The shared editor saves, runs, stops and runs changed source successfully.

The first device run passed 5/6 and revealed only the stale tooltip assertion;
the corrected suite passed all 6. This is real native Rust execution, not
mocked stdout. Android x64 device execution was not available in this session.

Logs: `android-build.log`, `android-build-serial.log`,
`android-build-exclusive.log`, `android-integration-build.log`,
`android-device-test.log`, `android-device-test-fixed.log` in this directory.

## OHOS arm64 native build and HAP

Initially only the x64 Miri payload was packaged, while HDC's device is arm64.
Located matching cached toolchain/source in WSL distro `qfli-java-build`:

- Pinned compiler/private target metadata: `/tmp/qfli-rustc-x64-ohos/stage0`.
- Pinned Miri source: `/tmp/qfli-rustc-x64-ohos/source/src/tools/miri`.
- Guest MIR sysroot: `/tmp/qfli-miri-reference-1.98.1/sysroot`.
- Source fingerprint validation matched the pinned Miri identity.

Rebuilt the current repository adapter, not an obsolete cached adapter:

```sh
cd /mnt/d/MyNewProjects/qfli_rust
QFLI_ADAPTER_BUILD_ROOT=/tmp/qfli-rust-release-ohos-arm64 \
QFLI_COMPILER_SYSROOT=/tmp/qfli-rustc-x64-ohos/stage0 \
QFLI_OHOS_CLANG=/usr/bin/clang \
CARGO_HOME=/tmp/qfli-miri-cross-1.98.1/cargo \
sh scripts/build_miri_adapter.sh \
  /tmp/qfli-rustc-x64-ohos/source/src/tools/miri \
  /tmp/qfli-rustc-x64-ohos/stage0 aarch64-unknown-linux-ohos
```

Exit 0 in 18.78 seconds, with a generated adapter build record. Adapter
SHA-256: `d409527a6c5bba8c203fea862db98a16441429bfcff550c7407ecd16c40fd60b`.
Used `scripts/package_miri_ohos.ps1 -Architecture arm64` with those matching
adapter, target compiler libraries, guest sysroot, source, generated dependency
metadata and SDK. Copied only Rust-workspace outputs. Preserved the original
x64 manifest under ignored `native/build/runtime/ohos-x64/manifest.json`.
New arm64 manifest: 3 native libraries (adapter, matching rustc driver,
`libc++_shared.so`) and 97 assets; all SHA-256 checks passed.

The Flutter `--no-codesign` flag did not disable this fork's Hvigor signing.
Neither does `-p enableSignTask=false`, which sets an extra property rather
than the typed core configuration. This command from `ohos/` succeeded:

```powershell
hvigorw assembleHap -p product=default -p buildMode=release `
  -c properties.enableSignTask=false -p TARGET_PLATFORM=ohos-arm64 --no-daemon
```

Exit 0, **BUILD SUCCESSFUL**, 2 minutes 9.730 seconds. Baseline artifact:

- `ohos/entry/build/default/outputs/default/entry-default-unsigned.hap`
- 482,723,165 bytes.
- SHA-256 `3e9ce3568cbb3d26333928d7566bca3888733215bdc54ba06d4735841ce854b9`.
- ZIP audit: arm64 `libapp.so`/`libflutter.so` and complete native Miri
  closure, arm64 manifest, all 97 referenced guest assets. Older x64 native
  libraries are also included by the current OHOS packaging configuration,
  increasing size; no x64 Flutter engine/app is included in this arm64 HAP.
- ArkTS compilation succeeded with existing SDK/Flutter deprecation warnings.

## OHOS device limits: not a runtime pass

HDC device `192.168.68.207:46551` is `aarch64`. Actual HAP installation was
attempted and rejected: **9568320 / no signature file**. HDC's own exit code
was 0 despite that failure; textual device result is authoritative.
The configured signing store file does not exist. The 3 other locally present
profiles bind JVM, cloud-terminal and Forge application IDs; none binds the
Rust ID. No credentials or package identities were replaced.

Also built the current C ABI test with the OHOS SDK Clang, staged actual
arm64 libraries, guest sysroot and fixtures under
`native/build/device/ohos-arm64`, and transferred 411,481,093 bytes/116 files
to the independent `/data/local/tmp/qfli_rust_release_20261015` directory.
Execution was denied by the device (`Permission denied`, shell exit **126**)
despite the executable mode being correct. Device execution policy was not
changed. This does not establish native runtime or packaged app execution.
Removed only that session-owned temporary device directory afterward; local
staged inputs remain available for a later signed-device verification.

OHOS remains **unavailable/unverified for runtime availability** until a
Rust-matching signature permits a packaged device run. HAP compilation and
native arm64 cross-compilation succeeded; actual OHOS execution did not.

Logs: `ohos-build.log`, `ohos-unsigned-build.log`, `ohos-arm64-build.log`,
`ohos-arm64-adapter-build.log`, `ohos-arm64-package.log`,
`ohos-device-transfer.log`, `ohos-device-abi.log`, `ohos-device-install.log`.

## Final integrated rebuild

Final source: Rust `5384d29`, native/platform `0649363`, offline terminal
`151fe59`, final integration tests/OHOS strip exclusions `ca6853e`, shared core
`8b33443`. The coordinator froze source and granted this
worker the exclusive Flutter window. Both final builds below contain the final
166-lesson curriculum; earlier baseline artifacts remain historical evidence.

### Final Android release: pass

```powershell
flutter build apk --release --target-platform android-arm64,android-x64
```

- Exit 0; release build 80.8 seconds.
- Artifact: `build/app/outputs/flutter-apk/app-release.apk`.
- Preserved production copy: `build/app-release-final.apk` (same bytes).
- Size: **154,284,485 bytes**.
- SHA-256: `b54ccc9430dc6b5e3c2ce4ddad9a232b2b4dc5b71c2180cdcb04b1890f5ca2d8`.
- Both packaged catalogs contain 166 records and are byte-identical to the final
  local catalogs. Both native manifests' 3 libraries and 97 guest/license assets
  match actual ZIP member SHA-256 and size, including both native architectures.
- All 10 SO files have ELF64 LOAD alignment at least 16 KiB, with congruent
  virtual-address/file offsets. Rust libraries use 16 KiB; Flutter/app use 64 KiB.
  `zipalign -c -P 16 4` passes. Package ID is
  `com.azurekiln.qfli.rustcore`; no INTERNET permission is present.
- `apksigner verify` passes, but the certificate is **Android Debug**. Production
  store signing is still required; no signing keys were replaced.

Installed this exact ordinary release using `install -r` on the exclusively
owned API37 x86_64 emulator with 16 KiB pages. Launch returned `Status: ok`,
Rust MainActivity owned focus, and PID-specific logs contained no matching fatal
or unhandled exception. Reviewed screenshots of Home, Tools, Tutorials, Examples
(166 visible) and Profile/About: local tools/content, correct QFLIRustCore
identity, and no online/login entry points on those pages. Release Flutter
semantics exposed no UIAutomator text labels; the first text-based oracle could
not assert labels, so the completed verification used actual screenshot review,
activity/PID checks and PID-specific logs. This was an oracle limitation, not an
application launch failure.

Screenshots: `build/rust-final-release-emulator.png`,
`build/rust-final-release-tools.png`, `build/rust-final-release-tutorials.png`,
`build/rust-final-release-examples.png`, `build/rust-final-release-profile.png`.
Logs: `android-final-build.log`, `android-final-release-smoke.log`,
`android-final-release-pid.log`.

### Final OHOS release compilation and byte-integrity audit: pass

```powershell
flutter build hap --release --target-platform ohos-arm64 --no-codesign
```

Temporarily set typed `properties.enableSignTask = false` in
`ohos/hvigor/hvigor-config.json5`, then restored its original bytes in `finally`.
Before/after SHA-256 is identical:
`17580932075c994635cdb2e9c6ad65bb3d80dc798a96cbeabd16f549a49ed819`.

- Exit 0; Hvigor task 74.3 seconds, including final ArkTS compilation.
- Artifact: `build/ohos/hap/entry-default-unsigned.hap`.
- Native output copy:
  `ohos/entry/build/default/outputs/default/entry-default-unsigned.hap`.
- Both copies: **638,135,918 bytes**, SHA-256
  `bc64d9f1d721a7d75a391f13a0ea1a568586aec34341643736775bf97e7ae780`.
- Actual ZIP catalogs contain 166 tutorials and 166 examples, each byte-identical
  to final local source. Tutorial SHA-256
  `f736dfd39b1813de61f9a0632c0aaefa46a329dcbbad1b41c44d7a4ad50010e6`;
  examples SHA-256
  `55647a17a464807969ebfeca84a2afea1773cc3b5f457b1a47656d26a730428d`.
- The packaged schema-1 manifest is the final arm64 source manifest, pinned to
  Rust commit `48a229ceaefd4985c50990b14116b6d856af0985`. All 97 actual guest /
  license members match manifest size and SHA-256.
- All 3 arm64 native members match their manifest SHA-256 and local source size:
  adapter 16,002,848; driver 282,735,328; C++ runtime 1,262,248 bytes. This proves
  the strip-exclusion fix preserves the actual packaged bytes. The arm64 native
  libraries, Flutter engine and application are ELF64 AArch64.
- `module.json` identifies `com.azurekiln.qfli.rustcore` and contains no
  `client_id` metadata. No duplicate ZIP member names were found.
- Four residual x64 native SO members remain (16,083,560 + 348,928 + 15,807,056 +
  139,920,288 bytes); there is no x64 Flutter engine/application in this arm64
  HAP. These are packaging size overhead, not x64 runtime verification. Optional
  cleanup was left out to avoid invalidating the completed final build.
- This is unsigned build/integrity evidence. The previously documented missing
  Rust signing profile and denied OHOS execution remain runtime blockers.

Evidence: `ohos-final-build.log`, `ohos-final-package-audit.json`.

### Final x64 integration and emulator cleanup: pass

```powershell
flutter test integration_test/rust_native_test.dart -d emulator-5580 --no-pub
```

All **7/7** real native/compiler/editor/terminal cases passed on API37/x86_64
with 16 KiB pages. Build 14.5 seconds, installation 3.2 seconds, tests 16 seconds.
The first x64 run passed six cases and exposed a test-only mismatch: shared
`SandboxShellBackend` intentionally leaves `lastExitCode` null after interrupt.
Corrected the terminal assertion to require null, `^C`, cancellation diagnostics,
cleared busy state and a fresh successful run. The separate native runner still
asserts actual cancellation exit 130. No shared-core source was changed.

Go coordinator explicitly transferred emulator5580/private ADB5039 in global
seq48; Rust accepted in seq49. After the final release smoke, Rust force-stopped
only its own app, successfully sent `emu kill` to only emulator5580, then stopped
only private ADB5039. Original AVD/snapshots, shared ADB5037 and physical OPD2413
were untouched by this cleanup (global seq55 announcement). The temporary
emulator resource is no longer abandoned or held.

Log: `android-x64-device-seven-fixed.log`.

### Final ARM64 physical integration: pass

SQL coordinator explicitly released OPD2413/direct `192.168.68.236:35991` in
global seq53; Rust coordinator accepted seq54 and this platform worker
acknowledged seq55. Re-read those authoritative events before device operations.
The physical phone uses 4 KiB pages (16 KiB execution is separately proven by
the x64 emulator above). Prebuilt the ARM64-only integration APK, inspected its
actual `com.azurekiln.qfli.rustcore.integrationtest` package ID/native ABI with
`aapt`, and then ran:

```powershell
flutter test integration_test/rust_native_test.dart -d 192.168.68.236:35991 --no-pub
```

All **7/7** cases passed on the physical ARM64 device: modules/generics,
stdin/EOF/UTF-8/nonzero exit, genuine compiler diagnostics/fresh output,
execution/output/guest-memory limits, native cancel/fresh execution, the real
shipped terminal delegate through shared TerminalManager/SandboxShellBackend,
and actual editor save/run/stop/fresh source. Build 13.7 seconds, installation
12.6 seconds, tests 7 seconds. Flutter also logged a failed property probe for
an unrelated stale mDNS alias; the selected direct serial installed and ran all
seven cases successfully. No neighboring product's data was cleared/uninstalled.

Logs: `android-final-arm64-prebuild.log`, `android-final-arm64-apk-identity.log`,
`android-final-arm64-seven.log`.

Installed the preserved final ordinary APK (`b54ccc9430dc6b5e3c2ce4ddad9a232b2b4dc5b71c2180cdcb04b1890f5ca2d8`)
with `install -r`: Success. The baseline package query found no installed normal
Rust package; the final package therefore has a new firstInstallTime
2026-10-15 21:28:02. No production package was uninstalled or cleared.
`am start -W` returned `Status: ok`, the correct MainActivity owned focus, and
the production PID remained 4560 through all five screenshot checks. Reviewed
Home, Tools, Tutorials, Examples (166 visible) and Profile/About: correct Rust
identity and local/offline entrances, with no matching fatal/unhandled/overflow
lines in PID-specific logs. The unrelated user system overlay was left alone.

Screenshots: `build/rust-final-release-arm64-home.png`,
`build/rust-final-release-arm64-tools.png`,
`build/rust-final-release-arm64-tutorials.png`,
`build/rust-final-release-arm64-examples.png`,
`build/rust-final-release-arm64-profile.png`.
Logs: `android-final-arm64-release-smoke.log`,
`android-final-arm64-release-pid.log`.

Force-stopped only Rust's ordinary and isolated-test apps, then **explicitly
released the physical device to Go coordinator in global seq56**. Rust
coordinator wB:p1 authoritatively confirmed this physical release in global
seq58. No further Rust device actions are planned. The exclusive Flutter
build/test window was returned to the Rust root coordinator after both final build audits,
both seven-case integration runs and both ordinary release smoke checks.

### Final quality gate and remaining release limits

- Scoped Dart format (zero changes), Dart analyze and Git whitespace checks
  passed after the final integration-test assertion correction. Final native
  script/packaging checks were already passed in `0649363`. Root committed the
  verified final integration test/strip configuration as `ca6853e`, independently
  confirmed final APK/HAP hashes/sizes and the original Hvigor config SHA-256,
  and accepted the Flutter/device handback.
- Root's final full Flutter suite: 140 passed, 8 explicit Windows native-host
  skips, zero failures. Root separately validated all 166 lessons / 332 main and
  answer programs / 23 complete Cargo bundles against the final source hashes.
  These host checks are separate from both actual Android seven-case results.
- Android release still needs a production signing certificate; its verified
  debug signature is suitable for these local tests, not store publication.
- OHOS needs matching Rust signing materials and actual packaged execution;
  unsigned HAP build/asset checks do not establish runtime availability.
- Residual OHOS x64 native libraries increase HAP size. They do not provide an
  x64 Flutter application or a verified x64 OHOS runtime. ABI filtering/size
  cleanup is a follow-up optimization, not a byte-integrity failure.

### Seven-test terminal regression preparation and interrupted attempt

Added a real shipped-terminal regression to `integration_test/rust_native_test.dart`:
`TerminalManager` creates the real mobile `SandboxShellBackend` using the shipped
Rust profile delegate, executes Rust, checks session stdout/exit 0, interrupts an
actual loop, then executes changed source without stale output. The native
runner separately asserts cancellation exit 130; the shared shell deliberately
leaves its last status null on cancellation and emits `^C`/cancellation output.
Dart format and scoped analyze passed. The arm64 integration APK prebuild exited
0; `aapt` confirmed `com.azurekiln.qfli.rustcore.integrationtest`, arm64-v8a only.

The first seven-test attempt was **interrupted, not a pass**. Rust incorrectly
accepted Web offline worker release (global seq30), although Web coordinator
seq28 retained the native device window. On receiving the correction, stopped
the Rust Flutter process immediately (exit 1) and withdrew the Rust claim in
global seq34. The log records only the isolated package inspection and a
14.6-second successful debug build; no installation/launch/test-result lines
were produced. Flutter may have begun a silent installation; the log cannot
establish that no device mutation occurred. Host inspection after stopping
showed only the persistent ADB server, no installer process. No explicit Rust
ADB install/launch/tap command was run. No further Rust device action is allowed
until Web coordinator explicitly releases or authorizes a release delegate.

Log: `android-seven-prebuild.log`, `android-device-seven.log`. This interrupted
attempt remains historical evidence; the final authorized physical and emulator
seven-case successes are recorded separately above.

### Final ZIP checksum review: OHOS stripping defect fixed in configuration

Read-only checksum audit of the baseline Android release APK passed for all six
declared native libraries and both manifests' 97 guest/license entries. Baseline
APK/HAP contain no `content_rust` entries; they do not represent final curriculum
integration and must be rebuilt.

The stricter HAP-native ZIP audit exposed default Hvigor stripping:

| ARM64 library | Original bytes | Baseline HAP bytes | Manifest matches HAP |
| --- | ---: | ---: | --- |
| `libqfli_miri.so` | 16,002,848 | 9,650,296 | No |
| `librustc_driver-2224b02d479e9414.so` | 282,735,328 | 199,722,656 | No |
| `libc++_shared.so` | 1,262,248 | 1,262,248 | Yes |

Adapter HAP SHA-256 was
`e540abd6785aa82e41e62b6629df9293fd0b0a5fe37f9eeac21f0967071972d6`,
but manifest/source hash is
`d409527a6c5bba8c203fea862db98a16441429bfcff550c7407ecd16c40fd60b`.
Driver HAP SHA-256 was
`b30377e024d599c51c7e9e3b9fd6470d04fc5c529230460ce0cac8dc75821d2a`,
but manifest/source hash is
`acf961fdd527e1ccc8a503c5874af3038dd1de00079c0626fdbfcc024997dcc8`.

Configured `ohos/entry/build-profile.json5` with
`buildOption.nativeLib.debugSymbol.strip = true`, excluding
`**/libqfli_miri.so` and `**/librustc_*.so`. This matches Android's existing
keep-symbol policy for manifest-covered libraries while leaving unrelated
libraries' stripping enabled. Installed Hvigor schema explicitly supports these
keys. The final HAP must prove actual ZIP-native SHA-256/size agreement after
this configuration change; the final integrated HAP audit above now passes it.
