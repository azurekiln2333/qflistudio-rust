# Cross-Platform Native Rust Runtime

## Current Evidence

- `RustProgramRunner` already invokes Cargo/rustc on Windows/Linux/macOS, but
  rejects Android/iOS. Its OHOS branch uses an upstream Miri session library.
- `build_miri_adapter.sh` currently accepts Linux x64 and OHOS arm64/x64 only.
- Native assets have one schema-1 manifest for OHOS x64. They must not be used
  as if they described another host.
- Windows Rust 1.98.1 GNU is available in an isolated temporary installation.
  Its old external MinGW fails `--high-entropy-va`; Rust's bundled `rust-lld`
  with `-C linker-flavor=ld.lld -C link-self-contained=yes` successfully
  compiled and executed the real modules/generics fixture.
- The exact Windows `rustc-dev` archive is already cached, as confirmed by its
  SHA256 in the installed channel manifest. It can be extracted into a separate
  build sysroot without changing the existing Rust installation.

## Boundaries

The missing behavior belongs in platform selection, the reusable C ABI runner,
native build inputs and platform packaging. Shared editor UI and existing OHOS
agreement-page work are outside this change. Keep the upstream session behavior
and C struct layout stable unless an actual platform constraint requires a
compatible extension.

## Native Runtime Selection

Generalize the OHOS FFI runner instead of duplicating sessions per platform.
Keep compatibility exports for existing OHOS callers. Mobile Run uses the
embedded runtime. Desktop Cargo/rustc stays available for native executables and
Cargo dependencies; an explicit embedded execution option permits the same
session engine to be exercised on desktop.

Runtime selection must use both the operating system and native architecture.
Return the matching sysroot and library location as one typed configuration.
Use native filenames and platform installation locations: Android jniLibs,
Apple signed frameworks/static linking as the researched build requires, and
desktop bundle libraries. Do not execute libraries extracted into writable
Flutter data assets on platforms that prohibit it.

## Asset Contract

Retain schema 1 for the existing OHOS package. New target-specific manifests
are flat Flutter assets named `assets/miri/manifest.<platform>-<architecture>.json`.
Schema 2 contains:

```json
{
  "schemaVersion": 2,
  "platform": "windows",
  "architecture": "x64",
  "rustVersion": "1.98.1",
  "rustCommit": "48a229ceaefd4985c50990b14116b6d856af0985",
  "nativeHost": "x86_64-pc-windows-gnu",
  "guestTarget": "x86_64-unknown-linux-gnu",
  "id": "<content SHA256>",
  "libraryName": "qfli_miri.dll",
  "nativeLibraries": [],
  "files": []
}
```

Each `files` entry retains the current relative path, flattened asset name,
size and SHA256 fields. `nativeLibraries` describes compiled libraries that
are installed as executable platform artifacts, not writable data. The
packager verifies real binary architecture, dependency closure and pinned
compiler/source revision before copying inputs. Reject mismatched platforms,
architectures and unsafe relative paths during preparation.

The fixed guest target remains Linux x64 because interpreted guest semantics
are independent of the native host. Guest MIR and compiler components must
come from compatible builds. Official LLVM-enabled hosts embed their backend;
the existing custom Cranelift OHOS build also requires its matching external
backend, preserving the current OHOS path.

## Builds

- Windows/macOS/Linux can use official matching host rustc-dev components.
  Keep all generated source staging, toolchain overlays and artifacts isolated.
- Android/iOS require compiler-private libraries built from the pinned complete
  Rust source; a rust-std target installation alone cannot supply them.
- Extend the build scripts with exact supported triples and real SDK/linker
  inputs. Provide a pinned source bootstrap where no host compiler distribution
  exists. Do not emit a manifest for a missing or incompatible runtime.
- Wire artifacts into the existing Gradle, CMake and Xcode packaging boundaries.
  Apple binaries must be signed with the app and use valid framework paths.

## Windows Compilation

Resolve the actual compiler host and sysroot before choosing bundled GNU
linker arguments. Apply the same configuration to direct rustc and Cargo.
Respect explicit user toolchain configuration. Retain existing process-tree
cancellation, output forwarding, stdin and temporary-output cleanup.

## Validation And Limits

Run actual Windows compiler and C ABI/Dart interpreter executions. Test Linux
only after approved WSL access is available. Android/iOS/macOS tests require
their real SDK/device/host and are skipped when absent. Broad host claims must
be backed by real source execution; loader or ABI-version checks alone are
insufficient. Web requires its own engine if the user includes it.
