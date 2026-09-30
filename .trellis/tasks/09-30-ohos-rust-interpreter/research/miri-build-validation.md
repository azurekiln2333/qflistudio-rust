# Miri Build Experiments

Date: 2026-09-30. These are build results, not source-execution results.

## Inputs

- Rust 1.98.1, commit `48a229ceaefd4985c50990b14116b6d856af0985`.
- `rustup component add rustc-dev --target aarch64-unknown-linux-ohos
  --toolchain stable-x86_64-pc-windows-gnu` succeeded in the isolated temporary
  Rust installation.
- Sparse-cloned `rust-lang/rust` tag `1.98.1`; checked-out commit matched the
  installed compiler. Copied `src/tools/miri` to a standalone temporary
  package to avoid the Rust workspace's unrelated members.
- `RUSTC_BOOTSTRAP=1`, official OHOS sysroot, DevEco SDK 23 linker, and
  `--no-default-features --features stack-cache --lib --locked`.

## Windows Cross-build

1. `cargo build --target aarch64-unknown-linux-ohos ...` compiled the ordinary
   crate dependencies, then failed with **E0463** for `rustc_macros`,
   `derive_where`, `tracing_attributes` and cascading compiler-private crates.
2. The target sysroot contained AArch64 proc-macro `.so` files. These cannot
   serve as executable proc macros on the Windows host.
3. Installing host Windows `rustc-dev` in the same toolchain failed on shared
   `lib/rustlib/rustc-src/rust/Cargo.lock`. Extracted only the Windows proc-macro
   DLLs from the verified downloaded archive into a separate temporary path.
4. Enabled both `cargo -Zdual-proc-macros` and target rustflags
   `-Zdual-proc-macros`, with the Windows DLL directory added as a dependency
   search path. This advanced the error to **E0460**: the proc-macro crate
   identities do not match the OHOS compiler-private metadata.
5. `rustc -Zls=all` reported Windows `rustc_macros` hash
   `c2b035bd0efa146c7bd3eba98b2c41f7`; OHOS `rustc_abi` metadata records its
   build-host macro hash as `386f00c44f35b37a8ab94d84df9b3cf3`. Search paths or
   renamed DLLs cannot change this identity.

Logs: `$env:TEMP/qfli-miri-ohos-build.log` and
`$env:TEMP/qfli-miri-ohos-dual.log`. This attempt did not produce a Miri library.

## OHOS x64 Host Distribution

- `rustup toolchain install 1.98.1-x86_64-unknown-linux-ohos --force-non-host
  --profile minimal` failed: target not found in channel.
- Official Rust 1.98.1 platform docs list OHOS x64 under host-tool support,
  but the actual channel manifest lists `rust`, `rustc`, `cargo` and
  `rustc-dev` only for OHOS AArch64. Both architectures have `rust-std`.
- Direct official 1.98.1 x64 rustc, Cargo and rustc-dev archive requests each
  returned HTTP 404. The corresponding AArch64 archives exist.
- Consequently the online x64 simulator cannot use a downloaded x64 host
  compiler for a native Miri build at this version.

## Linux Cross-build

The remaining short experiment uses the official Linux host toolchain and
both dual-proc-macro flags, to test whether its macro identities match the
producer recorded by the OHOS compiler-private libraries. The reproducible
command is `scripts/check_miri_ohos.sh`; inputs and isolation are documented
in `native/README.md`.

- Used the working `qfli-java-build` WSL distro. Its existing GCC and curl were
  sufficient for the library build. Installed official Linux Rust 1.98.1 and
  its host `rustc-dev` in `/tmp/qfli-miri-cross-1.98.1`.
- Copied only the official AArch64 OHOS target `lib` directory into that
  isolated toolchain, avoiding rustup's shared compiler-source conflict.
- Both Cargo and rustc used `-Zdual-proc-macros`. The build disabled default
  features, enabled `stack-cache`, selected `--lib`, and used `--locked`.
- **Miri compilation succeeded**: Cargo reported `Finished dev profile
  [unoptimized + debuginfo] target(s) in 1m 08s`. The finalized script rerun
  exited **0** and Cargo reported `Finished ... in 0.11s` from cache.
- Output: `/tmp/qfli-miri-cross-1.98.1/target/aarch64-unknown-linux-ohos/debug/libmiri.rlib`.

This proves the upstream Miri core library can compile for an OHOS host when
native-library/FFI and jemalloc features are disabled and compiler components
match the build host. It does not provide a C ABI shared library, MIR standard
library, native session adapter, or app source-execution evidence. The next
simulator step also needs x64 compiler-private libraries absent from the
official 1.98.1 distribution.
