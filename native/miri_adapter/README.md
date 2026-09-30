# Embedded upstream Miri adapter

This crate embeds the Rust 1.98.1 compiler and the Miri library from Rust commit
`48a229ceaefd4985c50990b14116b6d856af0985`. It exposes the C ABI in
`qfli_miri.h`. Parsing, type checking, macro expansion, MIR generation and
execution are performed by the upstream compiler and interpreter.

## Build

The build script stages this crate beside a patched Miri source copy. Its Cargo
path dependency is resolved inside that staging directory, not this checkout.
The source fingerprint is checked before copying and again in the staged copy.
The adapter's tracked lockfile is derived from the upstream lockfile, retaining
its dependency versions and checksums; builds use `--locked`. The executable
compiler's pinned commit is also checked. Shared source and toolchain directories
are read without modification.

```sh
sh scripts/build_miri_adapter.sh /path/to/rust-1.98.1/src/tools/miri \
  /path/to/linux-rust-1.98.1-with-rustc-dev aarch64-unknown-linux-ohos

QFLI_COMPILER_SYSROOT=/path/to/rebuilt-stage0-sysroot \
  sh scripts/build_miri_adapter.sh /path/to/rust-1.98.1/src/tools/miri \
  /path/to/linux-rust-1.98.1-with-rustc-dev x86_64-unknown-linux-ohos
```

The Linux executable toolchain needs version-matched compiler-private host
components and target libraries. Rebuilt x64 OHOS components additionally need
their matching Linux proc macros; official host macros are not interchangeable.
`QFLI_ADAPTER_BUILD_ROOT`, `QFLI_OHOS_SDK`, `QFLI_OHOS_CLANG` and
`QFLI_COMPILER_SYSROOT` override the documented local paths in the script.
Dependency metadata for packaging licenses is emitted as `dependencies.json`
and `dependencies-<target>.json` in the build root.

## Session contract

- `create` copies UTF-8 absolute source/sysroot paths and stdin bytes.
- A session can be run once. `run` blocks and must be called on a worker thread.
- `cancel`, `copy_output` and `result` can run concurrently with `run`.
- Output channels contain raw bytes, not NUL-terminated strings. Fetch the full
  length before allocating a buffer; output can grow while the session runs.
- `destroy` requires all calls to have completed. Retain the shared library for
  the lifetime of the process because rustc/LLVM keep process-global state.
- Compiler runs are serialized. There is no app-wide fd redirection, cwd change,
  environment mutation, CLI subprocess, or process exit in this adapter.

| State | Value | Exit status |
| --- | --- | --- |
| Ready | 0 | -1 |
| Running | 1 | -1 |
| Finished | 2 | User status, or 1 for compiler/interpreter errors |
| Cancelled | 3 | 130 |
| Limit reached | 4 | 124 |
| Internal error | 5 | 1 |

Cancel/time checks run after root parsing, after expansion, after analysis, at
MIR basic-block terminators, and during guest allocation. They do not preempt a
running compiler query. The timeout includes waiting for the compiler lock.
Memory limits account for live Miri allocation payload bytes before allocation,
including interpreter globals; they do not bound compiler memory or interpreter
metadata. Output has a combined bound with 512 bytes reserved for diagnostics.

The interpreted target is `x86_64-unknown-linux-gnu` on all hosts. The provided
sysroot must contain MIR-encoded standard libraries for that guest and a matching
host codegen backend for target-feature queries. The x64 OHOS compiler uses its
built Cranelift backend. External Cargo dependencies and user compiler flags are
not part of ABI version 1.

## Validation status

Linux reference execution passed the fixtures recorded in
`.trellis/tasks/09-30-ohos-rust-interpreter/research/miri-adapter-validation.md`.
ARM64 and x64 OHOS shared libraries build successfully. HAP source execution is
still pending, and these build results do not enable the mobile runtime.

The official Linux rustc driver uses initial-exec TLS. Late `dlopen` on glibc
requires a sufficient static TLS reserve; the reference run used
`GLIBC_TUNABLES=glibc.rtld.optional_static_tls=1048576`. The OHOS compiler builds
use emulated TLS, but their app loading and execution still need device evidence.

The upstream source and dependencies retain their own licenses. The adapter is
MIT OR Apache-2.0, matching Miri's declared license.

## Flutter Packaging

Run `scripts/package_miri_ohos.ps1` in PowerShell with `-AdapterLibrary`,
`-CompilerLibDirectory`, `-GuestSysroot`, `-SdkRoot`, `-RustSource` and
`-DependencyMetadata` pointing at the matching build inputs. The Rust source
parameter is the complete source root containing licenses and `src/tools/miri`.
For x64, also supply `-Architecture x64` and `-CodegenBackend` pointing at the
Cranelift shared library from the same compiler build. WSL inputs may be read
through `\\wsl.localhost\<distro>\...`; `-WslDistro` resolves Linux license paths
from Cargo metadata and defaults to `qfli-java-build`.

The script follows ELF dependencies into `ohos/entry/libs/<ABI>` and writes
98 MIR/backend/license manifest entries for the current x64 build. Generated
assets under `assets/miri/` and native binaries are ignored by Git; regenerate
them before building a fresh checkout. Directory asset entries in Flutter do
not recurse, so the script flattens files into SHA-256 `.bin` names and records
their extraction paths in `manifest.json`. One invocation describes one native
architecture; select the corresponding HAP target.

`lib/ohos_miri_assets.dart` prepares the guest sysroot in app storage on demand.
`lib/ohos_miri_runner.dart` invokes the ABI on a worker isolate, supplies project
`input.txt`, decodes output incrementally, and waits for cancellation before
destroying the session. `lib/rust_runner.dart` selects this path on OHOS and
retains desktop Cargo/rustc execution elsewhere.

The final x64 debug HAP reached PackageHap with the native libraries and assets.
SignHap still fails with 00303074 because the existing profile's bundle name
does not match `com.azurekiln.qfli.rustcore`. No interpreter device execution was
performed after the instruction to prioritize implementation.
