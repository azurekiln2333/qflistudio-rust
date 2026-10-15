# Embedded Rust Runtime

## 1. Scope / Trigger

Apply this contract when editing `native/miri_adapter/`, its upstream patch,
platform build/packaging scripts or the Dart FFI integration. The compiler and Miri
are pinned to Rust 1.98.1 commit `48a229ceaefd4985c50990b14116b6d856af0985`.

## 2. Signatures

The authoritative C layouts and signatures are in
`native/miri_adapter/qfli_miri.h`:

```c
uint32_t qfli_miri_abi_version(void);
QfliSession *qfli_miri_create(const QfliConfig *config);
QfliSession *qfli_miri_create_with_backend(const QfliConfig *config,
                                         const char *backend_path);
int32_t qfli_miri_run(QfliSession *session);
void qfli_miri_cancel(QfliSession *session);
size_t qfli_miri_copy_output(const QfliSession *session, uint32_t channel,
                           uint8_t *buffer, size_t capacity);
int32_t qfli_miri_result(const QfliSession *session, QfliResult *result);
void qfli_miri_destroy(QfliSession *session);
```

```sh
sh scripts/build_miri_adapter.sh <pinned-miri-source> <linux-toolchain> <host>
```

Packaging parameters are defined in `scripts/package_miri_ohos.ps1`.
Other platforms use `scripts/package_miri_runtime.py`. Mobile compiler bootstrap
is `scripts/build_rustc_host.py --native-host <host> --toolchain <minimal-pinned>
--source <complete-source> --build-root <independent-output>` with NDK or Xcode.

Unsigned OHOS verification from `ohos/` uses the typed Hvigor setting:

```powershell
hvigorw assembleHap -p product=default -p buildMode=release `
  -c properties.enableSignTask=false -p TARGET_PLATFORM=ohos-arm64 --no-daemon
```

For `flutter build hap`, the equivalent local configuration is
`"properties": {"enableSignTask": false}` in `ohos/hvigor/hvigor-config.json5`.
Save its original bytes and restore them in `finally` after verification.

## 3. Contracts

- ABI version is 1. Source/sysroot paths are absolute UTF-8; create copies them.
- stdin is at most 16 MiB. Output is 1024 bytes to 16 MiB, combined across three
  raw byte channels: 0 stdout, 1 stderr, 2 diagnostics. Reserve 512 bytes for
  diagnostics. Basic-block, time and guest-memory limits must be positive.
- Run once, off the Flutter UI isolate. Poll/cancel/result may overlap run;
  destroy must follow all active calls. Keep the library loaded for the process.
- Results: state 2 finished/user exit, 3 cancelled/130, 4 limit/124,
  5 internal failure/1. Ready/running states 0/1 have no final exit status.
- Use a fixed `x86_64-unknown-linux-gnu` interpreted guest on both OHOS hosts.
  Package matching guest MIR libraries and host codegen backend. Custom x64
  compiler metadata and Linux proc macros must come from the same build.
- `QFLI_COMPILER_SYSROOT`, `QFLI_ADAPTER_BUILD_ROOT`, `QFLI_OHOS_SDK` and
  `QFLI_OHOS_CLANG` override build inputs; source and compiler commits are checked.
- Generated manifest schema 1 records Rust revision, native host, guest target,
  content id, native library checksums and file path/asset/size/checksum entries.
  Flatten assets as hash-named `.bin` files for Flutter's directory inclusion.
- One manifest describes one packaged architecture. HAP target must match it.
- Non-OHOS manifests use schema 2, `platform`, `architecture`, `nativeHost`,
  `guestTarget`, `libraryName`, `nativeLibraries` (name/path/role/size/sha256),
  flattened guest/license `files` and content `id`. Android native code remains
  in extracted `nativeLibraryDir`, resolved through `qflistudio/runtime`.
- Android source bootstrap requires matching target std in a minimal pinned
  executable toolchain without preinstalled rustc-dev metadata. Build the
  stage1 driver and the upstream Cargo Cranelift crate against its private
  sysroot; do not require full CLI/std assembly through an absent LLVM backend.
- Set `build.description = ""`: source-archive descriptions change metadata
  identity and reject otherwise matching guest libraries with E0514. Keep
  exact revision validation and the compiler compatibility check enabled.
- Android libraries require 16 KiB LOAD alignment and a resolved public-system
  dependency closure. Target filters must cover defaultConfig and buildTypes.
- Device tests require a distinct application ID. Detect both integration paths
  and generated `flutter_test_listener.*/listener.dart`; explicit Gradle property
  `qfliIntegrationTest=true` forces isolation. Prebuild and inspect the APK before
  Flutter test, which captures its package before rebuilding the listener.
- Serialize Flutter pub, tests and builds within this workspace. They rewrite
  plugin metadata/registrants; concurrent integration and release preparation
  can leave a release registrant referencing the dev-only integration plugin.
  Regenerate through the normal release build with pub enabled. Do not patch
  generated registrants or the SDK to hide inconsistent build preparation.
- Hvigor `-p enableSignTask=false` and this Flutter fork's `--no-codesign` do
  not disable the HAP signing task. Use typed `-c properties.enableSignTask=false`
  or the temporary local config above for an unsigned compilation check.
  Never replace the Rust application ID or credentials with another product's
  profile to make installation succeed.
- HDC installation requires checking the textual device result as well as its
  process exit code. An unsigned HAP may return process exit 0 but report
  `9568320` / `no signature file`; this is an installation failure.
- Extract under app storage `rust_runtime/<id>`. Reuse completed files by size,
  rename partial writes, and retry preparation after an extraction failure.

## 4. Validation & Error Matrix

| Condition | Required result |
| --- | --- |
| Missing source/sysroot, invalid config | create returns null |
| Null or already-run session | run returns -1 |
| Compiler error | upstream diagnostic channel, final exit 1 |
| Cancellation or execution limit | final state 3/4, exit 130/124 |
| Missing library/ABI mismatch in Dart | ProgramRunResult failure |
| Invalid manifest or extraction failure | preparation throws; next run may retry |
| Build input does not match pinned revision | stop before compilation |
| ELF dependency absent or wrong architecture | stop packaging |
| Library compiled but HAP execution unverified | runtimeStatus stays unavailable |
| Source archive description differs from guest version | E0514; fix bootstrap identity, retain compiler checks |
| Android test APK has ordinary application ID | stop before installation or Flutter test |
| Android ARM64 built but no matching device | record build/audit separately; no execution pass |
| Release registrant references the integration plugin | serialize tooling, regenerate via normal release pub/build |
| OHOS signing material unavailable | compile unsigned with typed no-sign config; report installation/runtime as unverified |
| HDC exits 0 but reports no signature file | installation failed; no packaged runtime pass |

## 5. Good / Base / Bad Cases

- Good: a source crate with modules/generics and std executes through upstream
  rustc/Miri; output and exit status reach ProgramRunResult.
- Base: a source crate reads project `input.txt`; EOF follows the supplied bytes.
- Bad: borrowed data violates Rust ownership rules; return diagnostics without
  executing an older result. Do not claim external Cargo dependency support.

## 6. Required Evidence

Linux reference evidence is in the task's `research/miri-adapter-validation.md`:
diagnostics, I/O, nonzero exit, limits, cancellation and a fresh subsequent run.
Necessary build evidence must cover both OHOS native architectures, matched ELF
dependencies, asset inclusion and HAP packaging. Runtime availability requires
actual packaged source execution. Android integration tests assert
modules/generics, streams, stdin/EOF/UTF-8, compiler diagnostics, guest exit,
limits and stop followed by fresh execution. Editor tests cover save/run/stop
with actual native source execution. Terminal tests invoke the shipped profile
delegate through `TerminalManager`/`SandboxShellBackend`, asserting stdout,
exit 0, native cancellation/130, cleared busy state and a fresh source run.
Android ARM64 execution is established only by its matching packaged device
test; Android x64 availability requires its own packaged device checks. Apple
and OHOS evidence remain distinct; retain unavailable environment entries.
Record final APK/HAP SHA-256, packaged content counts and matching native
manifest/asset checks after the final source integration, separately from
baseline build results.

## 7. Wrong vs Correct

Wrong: kill a worker isolate and free its handle while native execution remains
active. Correct: request native cancellation, await run completion, then destroy.

Wrong: mix private metadata from the official driver with a custom x64 driver.
Correct: use that build's target metadata and matching Linux proc macros.

Wrong: point Flutter at nested MIR asset folders and assume recursive inclusion.
Correct: include flattened files and reconstruct their paths from the manifest.

Wrong: identify a Flutter device test only by its integration_test source path.
Correct: also detect its generated listener, force the isolated package property
and inspect a prebuilt APK before Flutter test can install or uninstall it.

Wrong: call a successful unsigned HAP build or HDC process exit 0 a device pass.
Correct: inspect the install result and execute packaged source on the matching
device before changing runtime availability.

Cancellation does not preempt an active rustc query, and guest memory accounting
does not cap host compiler memory. Keep these limits explicit in technical docs.
