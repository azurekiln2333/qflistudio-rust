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
