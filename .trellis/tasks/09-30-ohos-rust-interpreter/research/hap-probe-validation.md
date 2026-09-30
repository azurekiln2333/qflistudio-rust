# Native HAP Probe Validation

Date: 2026-09-30. Native loading/calling passed on the x86_64 simulator.

- Built `native/ohos_probe.rs` with official Rust 1.98.1 and
  `D:/ProgramFiles/Huawei/OpenHarmony/Sdk/23` using
  `scripts/build_ohos_probe.ps1`. The script verified AArch64 ELF output and
  the exported `qfli_native_probe` symbol.
- `flutter analyze`: no issues. `flutter test` with the temporary official
  Rust toolchain on PATH: 23 tests passed, including actual compilation and
  execution on desktop.
- `flutter build hap --debug` completed ArkTS compilation and PackageHap.
  `tar -tf ohos/entry/build/default/outputs/default/entry-default-unsigned.hap`
  confirmed `libs/arm64-v8a/libqfli_native_probe.so` in the package.
- SignHap failed with Hvigor **00303074**: the app bundle name does not match
  the signing profile. `ohos/AppScope/app.json5` declares
  `com.azurekiln.qfli.rustcore`; inspecting the configured `.p7b` with
  `rg -a -o 'com\.[A-Za-z0-9.]+'` showed `com.azurekiln.qfli.forge`.
  No profile for the Rust bundle was found under the local `.ohos/config`.
- `hdc tconn 192.168.68.207:46551` failed, including the unrestricted retry;
  `hdc list targets` subsequently returned `[Empty]`.

## Simulator Follow-up

- The user supplied the existing simulator address `127.0.0.1:5555`.
  `hdc tconn` reported it was connected; `hdc shell uname -m` returned
  `x86_64`; its software version was
  `emulator 6.1.0.126(SP1DEVC00E120R4P11)`.
- Installed the official `x86_64-unknown-linux-ohos` standard library and built
  the probe with `scripts/build_ohos_probe.ps1 -Architecture x64`. ELF and
  symbol checks passed. `flutter build hap --debug --target-platform ohos-x64`
  reached PackageHap, then hit the same profile mismatch at SignHap.
- `hdc -t 127.0.0.1:5555 install -r
  ohos/entry/build/default/outputs/default/entry-default-unsigned.hap`
  returned `install bundle successfully`.
- `hdc -t 127.0.0.1:5555 shell aa start -a EntryAbility -b
  com.azurekiln.qfli.rustcore` returned `start ability successfully`.
- Device hilog at **10:56:31.607**, process **27260**, reported:

  ```text
  QFLI native ABI probe: 51464c49
  ```

This is actual HAP/app-process Rust shared-library loading and C ABI call
evidence. It is not Rust-source interpretation evidence, and does not prove
ARM64 loading on a physical device. The simulator accepts unsigned debug HAPs;
physical-device signing still needs a matching profile.
