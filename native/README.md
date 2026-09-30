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

## Miri cross-build check

`scripts/check_miri_ohos.sh` is a compile experiment for the upstream Miri
library. It is not an app runtime. Run it on an x86_64 Linux host with GCC,
curl, and a Miri source snapshot from Rust **1.98.1**, commit
`48a229ceaefd4985c50990b14116b6d856af0985`:

```sh
sh scripts/check_miri_ohos.sh <Rust-source>/src/tools/miri <Rust-sysroot>/lib/rustlib/aarch64-unknown-linux-ohos
```

The second argument contains the official OHOS target's `rustc-dev` libraries
and standard library. The script installs a separate Linux toolchain under
`/tmp/qfli-miri-cross-1.98.1`, copies the target libraries, and enables both
Cargo and rustc's `dual-proc-macros` mode. Miri's `native-lib` and jemalloc
features are disabled because the upstream dependencies do not support OHOS.
A successful library build would still need a native session adapter and HAP
source-execution tests before the app can use it.

The AArch64 OHOS library build passed in WSL on 2026-09-30. The x64 OHOS
compiler-private libraries needed for the simulator are not present in the
official Rust 1.98.1 distribution; that architecture needs a source bootstrap.

## Upstream reference execution

The adapter needs a standard library with encoded MIR, rather than the
ordinary downloaded `rust-std`. On the same Linux host used by the cross-build
check, prepare an isolated upstream Miri CLI and its MIR sysroot:

```sh
sh scripts/prepare_miri_sysroot.sh <Rust-source>/src/tools/miri
sh scripts/verify_miri_reference.sh
```

The preparation script uses the pinned Linux toolchain installed by
`check_miri_ohos.sh`, adds `rust-src`, and builds Miri and cargo-miri with their
upstream lockfiles. Outputs are in `/tmp/qfli-miri-reference-1.98.1`.
The guest target is `x86_64-unknown-linux-gnu`; Miri can interpret this target
independently of the native host's architecture. This guest choice must be
explicit in the eventual mobile session contract.

The reference check executes fixtures from `native/fixtures`, compares stdout
and stderr, checks stdin and exit status 7, and requires the upstream `E0502`
and `E0308` diagnostics with empty stdout for invalid programs. These five CLI
checks passed on Linux on 2026-09-30. They validate the upstream reference,
and do not establish in-process ABI behavior or HAP source execution.
