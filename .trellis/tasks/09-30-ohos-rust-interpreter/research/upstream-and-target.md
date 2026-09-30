# Upstream Runtime and OHOS Target Findings

Date: 2026-09-30. This is feasibility evidence, not a working app runtime.

## Current app boundary

`lib/rust_runner.dart` uses external Cargo/rustc on desktop. HarmonyOS cannot use this process path in the ordinary app sandbox. The shared core already accepts stdout, stderr, exit status, and cancellation from a product runner.

## Native Rust target verified locally

- Official rustc 1.98.1 lists `aarch64-unknown-linux-ohos` and `x86_64-unknown-linux-ohos`; `rustup target add aarch64-unknown-linux-ohos` succeeded.
- The installed DevEco OpenHarmony NDK provides `native/llvm/bin/clang.exe` and `native/sysroot`.
- A small `#[no_mangle] extern "C"` Rust function was cross-compiled with `rustc --crate-type cdylib --target aarch64-unknown-linux-ohos`, the DevEco clang linker, `--target=aarch64-linux-ohos`, and the NDK sysroot.
- `llvm-readelf -h` reported `ELF64`, `DYN`, `AArch64`; `llvm-nm -D` reported exported `qfli_probe`. The output was `libqfli_probe.so` in the temporary toolchain directory.
- This proves a native Rust shared library can be built. It does not prove that HarmonyOS loads the library, that NAPI calls it, or that Rust source can be interpreted.

## Upstream Miri boundary

- `rust-lang/miri` is licensed MIT OR Apache-2.0 and describes itself as an interpreter for Rust MIR: https://github.com/rust-lang/miri
- Its current `Cargo.toml` describes an experimental MIR interpreter. `src/bin/miri.rs` uses `#![feature(rustc_private)]` and imports `rustc_driver`, `rustc_interface`, `rustc_middle`, and other compiler-private crates. Source: https://raw.githubusercontent.com/rust-lang/miri/master/src/bin/miri.rs
- Miri is therefore not a self-contained parser/compiler that can simply be cross-compiled as an OHOS `.so`. A real port must provide a compatible Rust compiler front end and MIR generation in the app process, then connect interpretation and I/O through the native bridge. Official Rust 1.98.1 does provide OHOS host tools; see `rustc-host-feasibility.md` for the corrected host-tool status and Miri's separate dependency blockers.

## Next verification gates

1. Load and invoke the native Rust probe from an actual HarmonyOS HAP through Dart FFI, which can call a C ABI shared library directly from this Flutter app. This proves packaging and ABI before integrating a large upstream runtime.
2. Use the official OHOS host tools and version-matched rustc private crates to test Miri's build without its unsupported native dependencies. Record exact versions and failures.
3. If the compiler/Miri host build is viable, port a minimal source-to-MIR-to-execution path and compare output/diagnostics with the desktop toolchain; then expand fixture coverage. Do not advertise availability before device execution passes.
