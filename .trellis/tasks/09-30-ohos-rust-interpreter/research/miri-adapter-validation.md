# Embedded Miri Session Validation

Date: 2026-09-30. This records native adapter implementation and Linux reference
execution. It is not HAP source-execution evidence.

## Inputs and outputs

- Upstream Rust/Miri: tag `1.98.1`, commit
  `48a229ceaefd4985c50990b14116b6d856af0985`.
- Pinned source input: `/tmp/qfli-miri-cross-1.98.1/source`.
- Linux rustc-dev:
  `/tmp/qfli-miri-cross-1.98.1/rustup/toolchains/1.98.1-x86_64-unknown-linux-gnu`.
- Adapter working root: `/tmp/qfli-miri-adapter-1.98.1`.
- MIR guest sysroot: `/tmp/qfli-miri-reference-1.98.1/sysroot`.
- Shared artifacts:
  `target/<host-triple>/debug/libqfli_miri.so` under the working root.
- Resolved dependency/license metadata:
  `dependencies-<host-triple>.json` under the working root.

The script verifies the normalized upstream source fingerprint, stages a private
copy, replays `miri-1.98.1-embedded-session.patch` with `--fuzz=0`, and compiles
the adapter as a `cdylib`. Native-library/GenMC/jemalloc features are disabled;
the upstream `stack-cache` feature remains enabled. Both Cargo and rustc use
`-Zdual-proc-macros` for cross-host compiler components.

## Proven builds

`scripts/build_miri_adapter.sh` completed with exit status 0 for:

1. `x86_64-unknown-linux-gnu`, official Linux Rust 1.98.1 rustc-dev.
2. `aarch64-unknown-linux-ohos`, official ARM64 OHOS compiler-private libraries
   installed under the Linux executable toolchain. The SDK linker uses clang18,
   SDK23 sysroot and the SDK clang15.0.4 resource directory.
3. `x86_64-unknown-linux-ohos`, with `QFLI_COMPILER_SYSROOT` set to
   `/tmp/qfli-rustc-x64-ohos/build/x86_64-unknown-linux-gnu/stage0-sysroot`.
   This uses the newly built target driver and matching Linux `rustc_macros`.
   The executable compiler remains official Linux Rust 1.98.1.

ARM64 library dynamic requirements: `librustc_driver-2224b02d479e9414.so`,
`libc++_shared.so`, `libc.so`; its runpath is `$ORIGIN`. The driver has no ELF TLS
segment or TLS relocations in the inspected official ARM64 artifact. The x64
compiler worker independently reports emulated TLS for its freshly built driver.

## Actual Linux C ABI execution

`native/miri_adapter/abi_test.c` dynamically loads the shared library. It was
compiled with `clang-18 -std=c11 -Wall -Wextra -Werror ... -ldl -lpthread`.
The resulting executable ran in one process with no `RUSTC_BOOTSTRAP` environment
variable and passed these 12 checks before the user's later instruction to stop
testing and prioritize implementation:

| Check | Evidence |
| --- | --- |
| Modules and generics | stdout `total=12`, stderr `items=3`, exit 0 |
| stdin | supplied `rust\n`, stdout `input=rust`, exit 0 |
| Nonzero exit | stdout `before-exit`, exit 7 |
| Invalid borrow | upstream `E0502`, empty stdout/stderr, exit 1 |
| Invalid type | upstream `E0308`, empty stdout/stderr, exit 1 |
| Basic-block bound | state 4, exit 124 |
| Concurrent cancellation | state 3, exit 130, cancel sent after >=2000 blocks |
| Guest memory bound | denied 128MiB allocation under 32MiB cap, state 4/exit124 |
| Output bound | combined captured output bounded, state 4/exit124 |
| Time bound | deadline reported, state 4/exit124 |
| Memory reuse | 100 allocations of 2MiB under 32MiB live cap, stdout `reused` |
| Fresh run after cancellation | modules/generics fixture succeeds again |

The C test also checks null entrypoints and rejects a second run of a session.
Cancellation polling accepts Ready/Running until the block threshold, asserts
active execution before cancelling, and has a 30-second monotonic deadline.

The Linux test environment supplied the official toolchain `lib` directory via
`LD_LIBRARY_PATH` and `GLIBC_TUNABLES=glibc.rtld.optional_static_tls=1048576`.
Without the latter, late `dlopen` failed with `cannot allocate memory in static
TLS block`: the official Linux driver TLS payload is `0x3388` bytes. That glibc
setting is reference-test setup, not an app workaround or on-device proof.

## Integration contract and remaining gates

The ABI header defines per-session source path, MIR sysroot, stdin, separate raw
stdout/stderr/diagnostics, exit status, cancellation, and explicit limits. The
compiler callbacks return `Compilation::Stop`; no upstream CLI `process::exit`
is used. rustc's diagnostic emitter writes to the session. Miri's normal stdio
and its explicit `miri_write_to_stdout/stderr` shims use the session hooks.

Guest allocations reserve bytes before calling the host allocator and release
them when allocation storage is dropped. Limit rejection unwinds using rustc's
fatal marker, preserving the app process and yielding the adapter's 124 result.
ABI calls contain panic boundaries and mutex poisoning is recovered.

Remaining limits are explicit:

- No HAP source execution has been performed for this adapter. Runtime
  availability must remain unverified until that acceptance gate is exercised.
- Compiler queries cannot be asynchronously preempted. Cancellation is checked
  at exposed phases and during interpretation; host compiler memory and Miri
  bookkeeping are outside the guest payload cap.
- Runtime packaging must include guest MIR libraries and a compatible host
  codegen backend for target features. x64 OHOS uses the built Cranelift backend.
- ABI 1 handles a Rust source crate with standard libraries. Cargo dependency
  resolution/build scripts/external proc-macro loading are separate work.
- Routine compiler diagnostics are captured. Upstream failures occurring before
  parse-session creation, backend loader failures and host panics may still use
  the platform diagnostic/panic path; there is no app-wide redirection.
- The shared library must stay loaded; destroy cannot race any active ABI call.

No further fixture or device runs were performed after the user's instruction
`别测了先做`. Final ARM64/x64 compilation and dependency metadata generation
were completed to make the integration concrete.

## Final Review Rebuild

The final review locked all 83 adapter packages to upstream versions/checksums,
validated the compiler commit and staged source, and captured the additional
uninitialized-memory dump through session stderr. Repeated builds remove only
generated `.rs.orig` patch backups from the staged copy, then validate it;
patching disables new backups. Shared source is untouched.

Both OHOS shared libraries were rebuilt with these corrections, using the
verified unmodified `/tmp/qfli-miri-reference-1.98.1/source` input:

```sh
sh scripts/build_miri_adapter.sh \
  /tmp/qfli-miri-reference-1.98.1/source \
  /tmp/qfli-miri-cross-1.98.1/rustup/toolchains/1.98.1-x86_64-unknown-linux-gnu \
  aarch64-unknown-linux-ohos

QFLI_COMPILER_SYSROOT=/tmp/qfli-rustc-x64-ohos/build/x86_64-unknown-linux-gnu/stage0-sysroot \
  sh scripts/build_miri_adapter.sh \
  /tmp/qfli-miri-reference-1.98.1/source \
  /tmp/qfli-miri-cross-1.98.1/rustup/toolchains/1.98.1-x86_64-unknown-linux-gnu \
  x86_64-unknown-linux-ohos
```

ARM64 completed with exit 0 in 6.32 seconds; x64 completed with exit 0 in
5.48 seconds. No new fixture executions were performed.
