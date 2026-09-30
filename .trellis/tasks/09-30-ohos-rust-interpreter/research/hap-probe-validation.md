# Native HAP Probe Validation

Date: 2026-09-30. Loader execution remains unverified.

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

The unsigned HAP is packaging evidence only. Neither native loading/calling
on device nor Rust-source interpretation is claimed by this batch.
