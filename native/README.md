# Native Rust components

The embedded runtime reuses upstream rustc/Miri with a fixed Linux x64 guest.
Native binaries are specific to the operating system and CPU. Desktop Cargo
compilation remains a separate execution route.

## Cross-platform builds

| Native host | Compiler-private inputs | Executable package |
| --- | --- | --- |
| Windows x64/arm64 | Exact matching official rustc-dev host component | DLL closure beside the desktop executable |
| Linux x64/arm64 | Exact matching official rustc-dev host component | Shared libraries in the desktop bundle's `lib/` |
| macOS x64/arm64 | Exact matching official rustc-dev host component | Signed frameworks in `Contents/Frameworks` |
| Android x64/arm64 | Complete pinned compiler source bootstrap with the NDK | Extracted `jniLibs` in `nativeLibraryDir` |
| iOS arm64 device, arm64/x64 simulator | Complete pinned compiler source bootstrap with Xcode | Signed frameworks in the app bundle |
| OHOS arm64/x64 | Existing official/custom host pipeline | Existing schema-1 HAP libraries and assets |

Every build uses Rust **1.98.1**, commit
`48a229ceaefd4985c50990b14116b6d856af0985`. Platform integration and a successful
library build do not establish packaged source execution. Only available
environments are tested; no Apple build or signing is claimed on Windows.

### Official desktop hosts

Install the matching compiler, rustc-dev and rust-src components. On Linux or
macOS, use an executable toolchain for that build machine:

```sh
sh scripts/build_miri_adapter.sh <pinned-source>/src/tools/miri <toolchain> <native-host>
```

The script selects Linux `.so` or Apple `.dylib` output and checks the compiler
revision and complete Miri source fingerprint. It writes an adapter build
record with checksums for the actual adapter and compiler libraries. macOS
requires Xcode command-line tools and Python 3. Windows uses
`scripts/build_miri_adapter.ps1` with the exact matching Windows toolchain.

Windows GNU also needs a real `dlltool` when building targets that generate
import libraries, including a proc-macro crate's workspace test harness. The
self-contained rust-lld fallback supplies linking but does not replace that
utility. Install matching MinGW tools, or use LLVM's `llvm-dlltool` through
rustc's `-C dlltool=<absolute-path>` option. This workspace's final checks used
the installed NDK 27.0.12077973 LLVM executable as `dlltool.exe` in the ignored
isolated compiler `bin` directory. All 23 Cargo workspace/all-target builds and
real consumer tests then passed; no test target was disabled.

### Compiler bootstrap for Android and iOS

Target rust-std and the compiler browsing sources from rustc-dev cannot replace
the complete Rust bootstrap source. `build_rustc_host.py` verifies the full
source layout and revision, or downloads the official source archive and
verifies its pinned SHA256. It builds `compiler/rustc_driver` and
`compiler/rustc_codegen_cranelift`, producing matching private metadata and
build-host proc macros for the embedded interpreter. It does not build a mobile
compiler CLI or rebuild stage1 standard libraries with Cranelift.

Use a separate minimal pinned build toolchain with the selected target's
matching official `rust-std` installed. These target libraries are bootstrap
inputs; they do not supply compiler-private runtime support. Preinstalled
`rustc-dev` metadata in this build toolchain conflicts with source-built
metadata and is rejected before compiler bootstrap. Existing desktop Miri
toolchains should remain separate.

The bootstrap uses an empty build description. Upstream adds a source-tarball
description by default, which changes the metadata version string and rejects
the otherwise matching guest standard libraries with E0514. The source revision
and compiler commit remain pinned and checked.

Downloaded source archives are validated, extracted into a temporary directory
and published only after successful extraction. An incomplete existing source
directory is preserved and replaced by a complete validated extraction.

For Android on Windows, Linux or macOS:

```sh
python scripts/build_rustc_host.py \
  --native-host aarch64-linux-android --toolchain <pinned-executable-toolchain> \
  --source <complete-pinned-rust-source> --ndk <complete-NDK> \
  --android-api 21 --build-root native/build/rustc-android-arm64
```

Use `x86_64-linux-android` for the x64 ABI. `--download-source` can replace
`--source`. NDK 27.0.12077973 is the project's default; Gradle property
`qfliNdkVersion` overrides it. The selected NDK must contain actual native-host
tools, headers and libraries. API level must be at least 21 and no higher than
the app's minimum supported Android API. Linkers use 16 KiB load-page alignment.

For iOS on a Mac with Xcode:

```sh
python3 scripts/build_rustc_host.py \
  --native-host aarch64-apple-ios --toolchain <pinned-Mac-toolchain> \
  --source <complete-pinned-rust-source> --ios-deployment-target 13.0 \
  --build-root native/build/rustc-ios-arm64
```

Simulator hosts are `aarch64-apple-ios-sim` and `x86_64-apple-ios`; the script
selects the real iPhoneOS or iPhoneSimulator SDK. `--configure-only` checks
inputs and writes configuration without compiling or claiming a runtime build.

`compiler-build.json` reports the assembled `runtimeSysroot`, adapter
`compilerSysroot`, backend and target linker. For the POSIX adapter build,
set `QFLI_COMPILER_SYSROOT` and `QFLI_RUNTIME_SYSROOT` to those separate outputs.
Android also needs `QFLI_ANDROID_NDK` and optionally `QFLI_ANDROID_API`; Apple
can set `QFLI_APPLE_DEPLOYMENT_TARGET`. Custom host private metadata must stay
paired with that bootstrap's driver, backend and build-host proc macros.

### Validated platform packaging

`package_miri_runtime.py` consumes an adapter build record and matching
MIR-encoded guest standard libraries. New `prepare_miri_sysroot.sh` runs write
`miri-sysroot.json` after successful upstream cargo-miri setup. Existing
verified OHOS schema-1 manifests can identify the same guest data with
`--guest-build-info`; every `.rlib` checksum must match that record.

```sh
python scripts/package_miri_runtime.py \
  --build-info <adapter-build.json> --guest-sysroot <MIR-sysroot> \
  --guest-build-info <miri-sysroot.json-or-verified-OHOS-manifest> \
  --rust-source <pinned-source> --compiler-lib-directory <native-driver-directory>
```

Source-built mobile hosts additionally require
`--codegen-backend <matching-Cranelift-library>`. Repeated
`--compiler-lib-directory` options supply native dependency search directories,
including the selected SDK's C++ runtime when needed. `--validate-only` performs
all checks without copying or emitting a package. A copied sparse Miri snapshot
can supply pinned license inputs; it cannot supply a compiler bootstrap.

The packager reads actual PE/ELF/Mach-O headers and import/load tables, resolves
the native dependency closure, rejects wrong architectures and revisions, and
checks Android load-segment alignment and Apple SDK variants. It writes:

- `assets/miri/manifest.<platform>-<architecture>.json`: schema 2, compiler and
  guest identity, installed library paths/roles, checksums and flattened data.
- `native/build/runtime/<platform>-<architecture>/`: desktop/Android native
  package and its build record; iOS uses `<native-host>` to distinguish SDKs.
- `android/app/src/main/jniLibs/<ABI>/`: adapter, driver, backend and non-system
  dependencies. Gradle enables extraction; executable libraries never become
  writable Flutter data assets.

Windows/Linux CMake installs the generated closure into the desktop bundle.
Android and Apple expose `qflistudio/runtime` method
`getRuntimeLibraryDirectory` for their installed native library directory.

Apple packaging must run on macOS. Each dylib becomes a framework; all compiler
dependency install names are repaired to `@rpath/<name>.framework/<name>` and
frameworks are initially signed with `--sign-identity` (default ad hoc). The
Xcode build phase checks the selected host and Flutter manifest, combines
matching CPU slices for a universal build, embeds them and re-signs them with
the app's identity. Package hashes describe pre-app-signing inputs; final
signatures change native binary bytes. Guest data hashes remain unchanged.

For iOS arm64, the generated Flutter manifest describes one SDK variant at a
time. Repackage the arm64 runtime when switching device/simulator builds;
Xcode rejects a manifest for the other SDK. Universal simulator/macOS builds
require both matching packages with the same framework dependency closure.
The existing OHOS packager and schema-1 manifest remain available.

### Build and package checks

```sh
python scripts/check_native_packaging.py --toolchain <pinned-toolchain> \
  --ndk <complete-NDK> --miri-source <pinned-source>/src/tools/miri
```

This checks the pinned source, rejects invalid source/path/host inputs,
compares real Windows DLL import tables with LLVM and links real arm64/x64
NDK shared-library probes with 16 KiB alignment. These probes verify SDK and
packager behavior; they are not compiler/interpreter execution fixtures.
On Windows, optional `--cmake <cmake.exe>` also checks bundle installation with
a real dependency DLL and confirms that missing package files fail the build.

## OHOS runtime

The upstream source runtime lives in [miri_adapter](miri_adapter/README.md).
Its C ABI embeds Rust 1.98.1 and Miri, with session I/O, diagnostics,
cancellation and execution limits. Both ARM64 and x64 OHOS shared libraries
compile. The Flutter OHOS runner uses this ABI; packaged source execution is
still unverified and runtime availability remains unchanged.

## Native ABI probe

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

The session adapter is now implemented separately; this older script remains
the core-library compile experiment. Use `build_miri_adapter.sh` to build the
actual shared runtime.

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

The later C ABI reference checks and native build results are recorded in
`.trellis/tasks/09-30-ohos-rust-interpreter/research/miri-adapter-validation.md`.
