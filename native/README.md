# OHOS native ABI probe

This probe verifies native packaging and a Dart-to-Rust C ABI call. It is not a
Rust source interpreter and does not enable the mobile runtime.

Install the official Rust target for the device architecture, then run from
the repository root in PowerShell. For an ARM64 device:

```powershell
./scripts/build_ohos_probe.ps1 -SdkRoot <OHOS-SDK-version-directory> -Rustc <rustc.exe>
flutter build hap --debug
```

For an x86_64 simulator, install `x86_64-unknown-linux-ohos` and use:

```powershell
./scripts/build_ohos_probe.ps1 -SdkRoot <OHOS-SDK-version-directory> -Rustc <rustc.exe> -Architecture x64
flutter build hap --debug --target-platform ohos-x64
```

The SDK directory must contain `native/llvm/bin` and `native/sysroot`. The
script writes the generated library to `ohos/entry/libs/<ABI>`, which is
ignored by Git. Build the probe again after cleaning generated platform files.

With a signing profile for `com.azurekiln.qfli.rustcore` and an online matching
device, install and launch the debug HAP. The expected Flutter device log is:

```text
QFLI native ABI probe: 51464c49
```

A missing library, missing symbol or unexpected value prints a failure in the
debug log. Release and profile builds do not call the probe. The call does not
change any product capability flags.

The x86_64 HarmonyOS simulator at `127.0.0.1:5555` accepted the unsigned debug
HAP and returned the expected value on 2026-09-30. Physical-device installation
still requires an appropriate signing profile.
