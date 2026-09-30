# HarmonyOS Rust Runtime Design

## Boundary

The desktop runner in `lib/rust_runner.dart` starts Cargo/rustc processes. The
HarmonyOS app sandbox needs an in-process native engine. Its Dart-facing result
must continue to match the shared core's `ProgramRunResult` contract. The
existing editor and project store do not need a new source format.

## Staged Integration

1. Build a small Rust `cdylib` for `aarch64-unknown-linux-ohos` with the
   installed official Rust target and DevEco LLVM linker. Package it in
   `ohos/entry/libs/arm64-v8a` and call it from the packaged Flutter app through
   Dart FFI. This tests actual HAP packaging, loader behavior and ABI. The
   probe is infrastructure only and must never set runtime availability.
2. Pin compatible rustc and Miri upstream revisions, then attempt an OHOS
   **host** build of the compiler-private crates and Miri. A Rust target build
   is insufficient: parsing, type checking, MIR generation and interpretation
   all need to run inside the app process.
3. Expose a native session API to Dart. Pass source paths and stdin in; return
   stdout, stderr, diagnostics and exit status out. Run long work off the UI
   isolate, with cancellation and bounded resources. Do not map an incomplete
   probe or failed engine initialization to success.
4. Compare representative device results with the same fixtures on desktop.
   Only after the complete acceptance suite passes may the profile advertise
   the mobile runtime.

## Compatibility And Failure Handling

- Keep `runtimeStatus` unavailable while the engine is unverified.
- Preserve the current desktop toolchain path and existing project files.
- A missing native library or unsupported ABI reports unavailability; it does
  not fall through to a stale executable or fabricated output.
- Record the upstream source revision, license, native build flags and device
  evidence alongside the integration.

## Key Risk

Official Rust OHOS targets are program targets, not proof that the rustc host
toolchain and Miri can be built and embedded on HarmonyOS. If the upstream host
build fails, record the exact blocker before choosing another genuine upstream
engine. Do not substitute a small custom Rust evaluator.

## Implemented Session And Packaging

`native/miri_adapter/qfli_miri.h` owns ABI 1. `create` copies absolute source and
sysroot paths, stdin and resource limits. `run` blocks on a worker thread;
`cancel`, output copying and result inspection may run concurrently. Compiler
sessions are serialized. Destroy follows completion of every active ABI call.

The interpreted guest is always `x86_64-unknown-linux-gnu`, independent of the
ARM64/x64 OHOS host. The sysroot contains MIR-encoded guest standard libraries
and the matching host backend used by compiler target-feature queries. x64 uses
the upstream Cranelift backend built with its custom compiler driver.

`scripts/package_miri_ohos.ps1` follows native ELF dependencies and copies them
to `ohos/entry/libs/<ABI>`. MIR libraries, the host backend and license files are
flattened as SHA-256 `.bin` assets because Flutter directory assets are not
recursive. The generated manifest identifies the native host, guest target,
checksums and dependency notices. It describes one native architecture per
packaging invocation; build the HAP for that same architecture.

`lib/ohos_miri_assets.dart` extracts assets into
`AppPaths.storageDirectory()/rust_runtime/<manifest-id>`. Completed files are
reused by size; partial files are written before rename. A failed preparation
can be retried. `lib/ohos_miri_runner.dart` loads the ABI, supplies `input.txt`,
polls bounded raw output with incremental UTF-8 decoding and runs compilation
and interpretation in a worker isolate. Cancellation retains the session until
the native call returns; it must not kill the isolate and free an active handle.

This path performs genuine upstream parsing, type checking, macro expansion and
MIR interpretation. ABI 1 does not resolve external Cargo dependencies or run
build scripts. Cancellation is cooperative at compiler phases and MIR blocks;
the guest allocation limit does not bound rustc host memory.
