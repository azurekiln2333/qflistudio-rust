# Research: x86_64 OHOS compiler-private bootstrap

- Query: Build x86_64 OHOS compiler frontend libraries for Miri without rebuilding target LLVM, using the installed Linux Rust 1.98.1 and OHOS SDK.
- Scope: mixed (official Rust 1.98.1 bootstrap sources, current source checkout, read-only WSL tool and linker checks)
- Date: 2026-09-30

## Findings

### Existing inputs and files

- Rust source checkout: `D:/AppData/Local/Temp/qfli-miri-ohos-source`, pinned by the parent session to Rust 1.98.1 commit `48a229ceaefd4985c50990b14116b6d856af0985`. It currently contains the Miri sparse checkout and root files; `compiler/` and `src/bootstrap/` were absent during this research. It must be expanded before bootstrap. A separate build checkout under `/tmp/qfli-rustc-x64-ohos` is owned by the implementation agent.
- Linux stage0 toolchain: `/tmp/qfli-miri-cross-1.98.1/rustup/toolchains/1.98.1-x86_64-unknown-linux-gnu`; local `rustc -vV` confirms the exact commit above, Linux GNU host, LLVM 22.1.8.
- `scripts/check_miri_ohos.sh`: existing AArch64 experiment uses both Cargo and rustc `-Zdual-proc-macros`. The parent session verified its successful build and cached rerun. This research independently checked `/tmp/qfli-miri-cross-1.98.1/target/aarch64-unknown-linux-ohos/debug/libmiri.rlib`: **722,512,724 bytes**.
- Local Linux `rustc -Zls=all` reports `rustc_macros-929a1f79f8e20681` hash **`8ab94d84df9b3cf3386f00c44f35b37a`**. This is the correct Svh display order for the OHOS metadata's numeric `Fingerprint(4066469831681356666, 9996106081008041203)`. The earlier concatenation `386f...8ab...` reversed the displayed words and must not be used as a mismatch claim.
- `src/tools/miri/src/bin/miri.rs:117` in the current checkout calls the default codegen backend to obtain target configuration even when evaluation uses `DummyCodegenBackend`. A compiler frontend library alone therefore does not prove that the unmodified Miri driver can run.
- Task `prd.md` and `design.md` require actual in-process source execution and preserve `runtimeStatus = unavailable` until device tests pass. `.trellis/spec/guides/cross-layer-thinking-guide.md` applies to the future native/Dart session boundary; package spec indexes remain generic templates.

### Empty backend configuration is explicitly rejected

Rust 1.98.1 [bootstrap config parser](https://github.com/rust-lang/rust/blob/1.98.1/src/bootstrap/src/core/config/toml/rust.rs#L413) accepts built-in backend names `llvm`, `cranelift`, and `gcc`. At [line 457](https://github.com/rust-lang/rust/blob/1.98.1/src/bootstrap/src/core/config/toml/rust.rs#L457), an empty list exits with:

```text
ERROR: `<section>.codegen-backends` should not be set to `[]`
```

`codegen-backends = []` is not a supported Rust 1.98.1 bootstrap path. Patching this validation alone would also be insufficient: bootstrap chooses the first backend for `CFG_DEFAULT_CODEGEN_BACKEND`, and the Miri driver loads that backend for target features.

### Supported Cranelift configuration is a candidate

- [Bootstrap `rustc_features`](https://github.com/rust-lang/rust/blob/1.98.1/src/bootstrap/src/lib.rs) enables the compiler's `llvm` feature only when `llvm_enabled(target)` is true (or for `x check`). Choosing `cranelift` for the target makes this false for a real build.
- [rustc_interface/Cargo.toml](https://github.com/rust-lang/rust/blob/1.98.1/compiler/rustc_interface/Cargo.toml) makes `rustc_codegen_llvm` optional behind the `llvm` feature. [rustc/Cargo.toml](https://github.com/rust-lang/rust/blob/1.98.1/compiler/rustc/Cargo.toml) forwards that feature. Thus frontend compilation can omit target LLVM while the downloaded Linux stage0 still uses its already installed LLVM backend to compile Rust code.
- [Bootstrap `Rustc` step](https://github.com/rust-lang/rust/blob/1.98.1/src/bootstrap/src/core/build_steps/compile.rs#L1016) accepts individual compiler crates. Its `make_run` uses stage `top_stage - 1` on the build triple, targets the requested host triple, and links the resulting libraries and host proc macros into that build compiler's sysroot. `compiler/rustc_driver` is therefore the minimal supported frontend build target at stage 1.
- [Bootstrap Cranelift step](https://github.com/rust-lang/rust/blob/1.98.1/src/bootstrap/src/core/build_steps/compile.rs#L1758) is an upstream backend build step. Full `compiler` assembly builds its target backend dylib as well as the compiler; a frontend-only `rustc_driver` request does not establish a loadable backend.
- [Cranelift backend manifest](https://github.com/rust-lang/rust/blob/1.98.1/compiler/rustc_codegen_cranelift/Cargo.toml) pins Cranelift crates to `0.132.0` and target-lexicon `0.13`; the backend is a Rust `dylib`. It does not require an OHOS LLVM C++ build.
- [Cranelift `target_config`](https://github.com/rust-lang/rust/blob/1.98.1/compiler/rustc_codegen_cranelift/src/lib.rs#L156) covers `Arch::X86_64` with OS other than `None`; OHOS's Rust target reports Linux OS and OHOS environment. This is a plausible replacement for the default backend call used by Miri. It is not an OHOS runtime compatibility test. The backend rejects whole-program Thin/Fat LTO and LLVM coverage instrumentation, so use `lto = "off"` and no instrumentation.

Candidate bootstrap configuration, to be validated by the implementation agent:

```toml
profile = "compiler"

[build]
build = "x86_64-unknown-linux-gnu"
host = ["x86_64-unknown-linux-ohos"]
target = ["x86_64-unknown-linux-ohos"]
rustc = "/tmp/qfli-miri-cross-1.98.1/rustup/toolchains/1.98.1-x86_64-unknown-linux-gnu/bin/rustc"
cargo = "/tmp/qfli-miri-cross-1.98.1/rustup/toolchains/1.98.1-x86_64-unknown-linux-gnu/bin/cargo"
local-rebuild = true
submodules = false
docs = false
compiler-docs = false
extended = false
sanitizers = false
profiler = false
optimized-compiler-builtins = false

[llvm]
download-ci-llvm = false

[rust]
channel = "stable"
download-rustc = false
codegen-backends = ["cranelift"]
llvm-tools = false
llvm-bitcode-linker = false
lld = false
jemalloc = false
llvm-libunwind = "no"
lto = "off"

[target.x86_64-unknown-linux-ohos]
cc = "/tmp/qfli-rustc-x64-ohos/toolchain/ohos-clang"
cxx = "/tmp/qfli-rustc-x64-ohos/toolchain/ohos-clang++"
linker = "/tmp/qfli-rustc-x64-ohos/toolchain/ohos-clang"
ar = "/usr/bin/llvm-ar-18"
ranlib = "/usr/bin/llvm-ranlib-18"
```

`build.rustc`, `build.cargo`, and `local-rebuild` are documented in the checkout's `bootstrap.example.toml`: the local rebuild setting is intended for recompiling matching sources with a local compiler. `optimized-compiler-builtins = false`, disabled sanitizers/profiler, and `llvm-libunwind = "no"` avoid separate LLVM compiler-rt/libunwind source build requirements. A complete matching source tree, including `compiler/`, `library/`, `src/bootstrap/`, `src/build_helper/`, and required workspace support crates, is still necessary. With automatic submodule management disabled, `library/backtrace` must be present if the selected standard-library features use it. Do not disable submodule management and leave required sources empty.

From the prepared source root, the ordered candidate commands are:

```sh
python3 x.py build --config /tmp/qfli-rustc-x64-ohos/bootstrap.toml --stage 1 \
  --host x86_64-unknown-linux-ohos --target x86_64-unknown-linux-ohos \
  compiler/rustc_driver

python3 x.py build --config /tmp/qfli-rustc-x64-ohos/bootstrap.toml --stage 1 \
  --host x86_64-unknown-linux-ohos --target x86_64-unknown-linux-ohos compiler
```

The first command tests and stages frontend libraries. The second is needed to validate an assembled OHOS compiler plus Cranelift backend. Use bootstrap's matching staged target libraries and host macros when building Miri; do not mix newly built target metadata with unrelated installed `rustc-dev` identities. Keep both dual-proc-macro modes enabled for a manual cross-build of Miri. No compiler build was started during this research.

### Current WSL compiler and linker route

- Distro `qfli-java-build`: Ubuntu 24.04.5 LTS, Python **3.12.3**, `/usr/bin/clang` and `clang++` **18.1.3**, `/usr/bin/ld.lld` **18.1.3**, `/usr/bin/llvm-ar-18`, `/usr/bin/llvm-ranlib-18`, `/usr/bin/llvm-readelf-18`, GCC/G++, make, CMake **3.28.3**, and pkg-config are present. Ninja and unversioned `llvm-ar`/`llvm-ranlib` were not found. Target LLVM is omitted in the candidate, so Ninja is not a prerequisite for that omitted build.
- The installed OHOS SDK is Windows-hosted at `D:/ProgramFiles/Huawei/DevEco Studio/sdk/default/openharmony/native`, mounted in WSL as `/mnt/d/ProgramFiles/Huawei/DevEco Studio/sdk/default/openharmony/native`. No separate Linux OHOS SDK was found in the checked `/tmp` or `/opt` directories. The Windows `clang.exe` should not receive Linux `/tmp` source/output paths.
- A read-only native Linux Clang dry run (`-###`, no compilation/linking) recognized `--target=x86_64-linux-ohos` and the mounted SDK sysroot. Without overrides it referenced missing `/usr/lib/llvm-18/lib/clang/18/lib/x86_64-linux-ohos/libclang_rt.builtins.a` and unresolved `crtbeginS.o`/`crtendS.o`.
- Adding `-resource-dir <SDK>/llvm/lib/clang/15.0.4` made the dry run select existing OHOS `clang_rt.crtbegin.o`, `clang_rt.crtend.o`, and `libclang_rt.builtins.a`. The target SDK also contains `libunwind.a` under `<SDK>/llvm/lib/x86_64-linux-ohos`; add this directory with `-L`, because it was absent from the driver's printed search paths. `sysroot/usr/lib/x86_64-linux-ohos` has the libc and startup objects.

Candidate C/linker wrapper for the implementation agent to validate:

```sh
#!/bin/sh
sdk_native='/mnt/d/ProgramFiles/Huawei/DevEco Studio/sdk/default/openharmony/native'
exec /usr/bin/clang --target=x86_64-linux-ohos \
  --sysroot="$sdk_native/sysroot" \
  -resource-dir "$sdk_native/llvm/lib/clang/15.0.4" \
  -L"$sdk_native/llvm/lib/x86_64-linux-ohos" \
  -D__MUSL__ -fuse-ld=lld "$@"
```

The C++ wrapper would use `/usr/bin/clang++` with the same target/sysroot/runtime paths; validate its SDK C++ headers and libraries if any selected dependency requires C++. The source-defined OHOS wrapper pattern comes from the [official platform guide](https://github.com/rust-lang/rust/blob/1.98.1/src/doc/rustc/src/platform-support/openharmony.md); the resource-dir and library search additions above are specific to this machine's Linux-Clang/Windows-SDK combination.

## Caveats / Not Found

- No x64 frontend, Cranelift backend, native session adapter, or Miri source execution was built or run in this research pass. All proposed commands remain candidates until the implementation agent records actual outputs.
- The compiler/linker route was checked only with `clang -###`; it did not compile or link an ELF library. Verify a small OHOS shared library first, including the expected ELF machine and dynamic dependencies, before a large bootstrap.
- Rust 1.98.1 platform docs claim x64 OHOS host tools, but the parent session's manifest and HTTP checks found only AArch64 host archives. The local frontend build addresses that specific distribution gap; it does not change the device architecture or make the AArch64 Miri artifact runnable on the x64 simulator.
- Miri's disabled `native-lib`/jemalloc features still limit the native dependencies selected for this build. A completed frontend/backend build still needs version-matched Miri integration, diagnostics/I/O/cancellation behavior, and actual HAP fixture execution before availability can change.
