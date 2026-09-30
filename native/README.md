# OHOS native ABI probe

This probe verifies native packaging and a Dart-to-Rust C ABI call. It is not a
Rust source interpreter and does not enable the mobile runtime.

Install the official `aarch64-unknown-linux-ohos` Rust target, then run from the
repository root in PowerShell:

```powershell
./scripts/build_ohos_probe.ps1 -SdkRoot <OHOS-SDK-version-directory> -Rustc <rustc.exe>
flutter build hap --debug
```

The SDK directory must contain `native/llvm/bin` and `native/sysroot`. The
script writes the generated library to `ohos/entry/libs/arm64-v8a`, which is
ignored by Git. Build the probe again after cleaning generated platform files.

With a signing profile for `com.azurekiln.qfli.rustcore` and an online AArch64
device, install and launch the debug HAP. The expected Flutter device log is:

```text
QFLI native ABI probe: 51464c49
```

A missing library, missing symbol or unexpected value prints a failure in the
debug log. Release and profile builds do not call the probe. The call does not
change any product capability flags.
