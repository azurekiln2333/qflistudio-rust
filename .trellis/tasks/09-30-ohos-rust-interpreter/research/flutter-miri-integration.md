# Flutter Miri Integration Build

Date: 2026-09-30. The user directed implementation to continue while pausing
fixture and device tests. This records packaging and compilation only.

## Implemented Path

`RustProgramRunner` selects `OhosMiriProgramRunner` on OHOS. It first prepares
the manifest's sysroot under app storage. Preparation uses partial writes and
rename, reuses completed files by size, and clears its cached future on failure
so the next run can retry. Desktop execution continues through Cargo/rustc.

The FFI runner validates project/source paths, supplies up to 16 MiB of
`input.txt`, checks ABI 1, and invokes the blocking native call in a worker
isolate. The UI isolate polls independent output channels and incrementally
decodes UTF-8. Cancellation preserves the native handle until execution has
returned, then cleanup closes output and destroys the session.

Defaults: 30 seconds, 10 million basic blocks, 1 MiB combined output and 64 MiB
live guest allocation payload. Compiler queries are cooperatively cancellable
only at phase boundaries; rustc memory is outside the guest memory limit.

## Final Packaging Inputs

Paths below are Linux paths in WSL `qfli-java-build` unless otherwise stated.
PowerShell reads them through that distribution's UNC share.

| Input | Path |
| --- | --- |
| Adapter | `/tmp/qfli-miri-adapter-1.98.1/target/x86_64-unknown-linux-ohos/debug/libqfli_miri.so` |
| Compiler libraries | `/tmp/qfli-rustc-x64-ohos/build/x86_64-unknown-linux-ohos/stage1/lib` |
| Backend | compiler libraries plus `rustlib/x86_64-unknown-linux-ohos/codegen-backends/librustc_codegen_cranelift-1.98.1.so` |
| Guest sysroot | `/tmp/qfli-miri-reference-1.98.1/sysroot` |
| Adapter dependencies | `/tmp/qfli-miri-adapter-1.98.1/dependencies-x86_64-unknown-linux-ohos.json` |
| Windows Rust source | `D:/AppData/Local/Temp/qfli-miri-ohos-source` |
| Windows SDK root | `D:/ProgramFiles/Huawei/OpenHarmony/Sdk/23` |

The packaging command completed with exit 0 for `-Architecture x64`, copying
the native dependency closure and generating 98 MIR/backend/license entries.
Manifest id:
`b8c4f32546e3863ce26d0b649bb91e9f1c6aa49cc449a79454259428b5603c68`.
The manifest fixes the native host to `x86_64-unknown-linux-ohos` and interpreted
guest to `x86_64-unknown-linux-gnu`.

## HAP Build Result

```powershell
& 'D:/ProgramFiles/flutter_ohos/bin/cache/dart-sdk/bin/dart.exe' `
  'D:/ProgramFiles/flutter_ohos/bin/cache/flutter_tools.snapshot' `
  build hap --debug --target-platform ohos-x64 --no-pub
```

Flutter assembly, ArkTS compilation, PackageHap and PackingCheck completed.
The overall command exited 1 at SignHap with **00303074**: the configured
profile belongs to `com.azurekiln.qfli.forge`, while the app declares
`com.azurekiln.qfli.rustcore`. The final Hvigor report is
`ohos/.hvigor/report/report-202609301707147770.json`.

Generated HAP:
`ohos/entry/build/default/outputs/default/entry-default-unsigned.hap`,
**350,513,806 bytes**. Reading its archive inventory confirmed:

```text
libs/x86_64/libqfli_miri.so
libs/x86_64/librustc_codegen_cranelift-1.98.1.so
libs/x86_64/librustc_driver-2223f3b215a042ae.so
resources/rawfile/flutter_assets/assets/miri/manifest.json
```

The earlier full Dart analysis passed. The reviewer subsequently checked the
modified asset loader with Dart analysis/formatting and checked shell and
PowerShell syntax. No new fixture, Flutter test or device run was performed.

## Remaining Acceptance

The genuine upstream engine and app integration are implemented and compiled.
No packaged Rust source execution has been established for this adapter, so
`runtimeStatus` remains `unavailable` and the task remains active. ABI 1 supports
a source crate with standard libraries; mobile Cargo dependencies, build
scripts and external proc macros are subsequent work. The compiler bootstrap
checks revision identifiers; complete content verification of mutable custom
compiler checkouts is not currently enforced by that script.
