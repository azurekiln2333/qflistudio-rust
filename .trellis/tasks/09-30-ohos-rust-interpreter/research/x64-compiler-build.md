# x64 OHOS compiler build evidence

Date: 2026-09-30. This experiment builds upstream compiler components. It
does not establish an app-process Rust interpreter or change runtime status.

## Inputs

- Upstream Rust: **1.98.1**, commit
  `48a229ceaefd4985c50990b14116b6d856af0985`.
- Build host: WSL distribution `qfli-java-build`, x86_64 Linux.
- Stage0: official Linux Rust 1.98.1 copied from the existing isolated
  installation into `/tmp/qfli-rustc-x64-ohos/stage0`; the copy also contains
  official Rust 1.98.1 x64 OHOS `rust-std` target libraries.
- Target compiler host: `x86_64-unknown-linux-ohos`.
- SDK: `/mnt/d/ProgramFiles/Huawei/OpenHarmony/Sdk/23/native`.
- Linux linker tools: clang/clang++ 18.1.3, ld.lld 18.1.3,
  `/usr/bin/llvm-ar-18`, `/usr/bin/llvm-ranlib-18`.
- OHOS resource directory: SDK `llvm/lib/clang/15.0.4`.
- Isolated source and build root: `/tmp/qfli-rustc-x64-ohos`.

The release source archive is available at
`https://static.rust-lang.org/dist/rustc-1.98.1-src.tar.xz`, size
244,440,824 bytes. Its published SHA-256 is
`be1816e7f6c40abb90245ad6e024bed2a7e88d7dda4561e4d5470207df616b9f`.
The initial download was stopped after sustained low transfer speed. The
actual build uses an isolated copy of the existing upstream Git snapshot.
The shared snapshot was not changed.

The copied repository's missing `.git/refs` directory was recreated in the
isolated copy. `git rev-parse HEAD` then returned the pinned release commit.
Its sparse checkout was expanded to `.cargo`, `compiler`, `library`, `src/bootstrap`,
`src/tools`, `src/build_helper`, `src/ci`, `src/librustdoc`,
`src/rustdoc-json-types`, `src/rustc-std-workspace`, and `src/etc`.
`library/backtrace` was initialized at its pinned gitlink,
`d902726a1dcdc1e1c66f73d1162181b5423c645b`.

## Reproduction

`scripts/check_rustc_x64_ohos.sh` validates the exact stage0/source commit,
checks a real OHOS C link, writes an isolated bootstrap configuration and
runs upstream `x.py` for `rustc_driver`, then the complete compiler and backend
assembly. The optional third argument accepts a complete pinned
source snapshot; without it, the script downloads and checks the official
release archive.

Stage0 must include official `x86_64-unknown-linux-ohos` standard-library
target components. In a rustup-managed Linux toolchain, install them before
running the build:

```sh
rustup target add --toolchain 1.98.1 x86_64-unknown-linux-ohos
```

For this run, the already installed official target directory was copied from
the temporary Windows Rust installation into the isolated Linux stage0 copy.
The corresponding official `rust-std-1.98.1-x86_64-unknown-linux-ohos.tar.xz`
archive's published SHA-256 is
`e19f2d8010d72fdf4643e5750c3da646b08c63b1524de956a06edd58bba1671b`.

```sh
bash scripts/check_rustc_x64_ohos.sh \
  /mnt/d/ProgramFiles/Huawei/OpenHarmony/Sdk/23/native \
  /tmp/qfli-rustc-x64-ohos/stage0 \
  /tmp/qfli-rustc-x64-ohos/source
```

The relevant configuration is `codegen-backends = ["cranelift"]`,
`download-rustc = false`, `download-ci-llvm = false`, `local-rebuild = true`,
disabled jemalloc/sanitizers/profiler/optimized compiler builtins and LTO off.
The stage0 compiler's own LLVM generates these host libraries; no target LLVM
build is requested. Four concurrent jobs are the default; override with
`QFLI_RUSTC_BUILD_JOBS`. `QFLI_RUSTC_BUILD_ROOT` changes the isolated output root.

The command issued by the script is:

```sh
python3 /tmp/qfli-rustc-x64-ohos/source/x.py build \
  --config /tmp/qfli-rustc-x64-ohos/bootstrap.toml \
  --stage 1 --host x86_64-unknown-linux-ohos \
  --target x86_64-unknown-linux-ohos compiler/rustc_driver
python3 /tmp/qfli-rustc-x64-ohos/source/x.py build \
  --config /tmp/qfli-rustc-x64-ohos/bootstrap.toml \
  --stage 1 --host x86_64-unknown-linux-ohos \
  --target x86_64-unknown-linux-ohos compiler
```

## Verified Results

- `bash -n scripts/check_rustc_x64_ohos.sh` passed.
- The real C link using Linux clang and OHOS SDK resources passed.
  `readelf -h /tmp/qfli-rustc-x64-ohos/ohos-link-check` reported ELF64,
  x86-64 and `DYN` (PIE). `readelf -d` reported `NEEDED: libc.so`.
- Upstream x64 OHOS standard-library compilation passed: Cargo reported
  `Finished dist profile [optimized] target(s) in 53.91s`.
- Stage1 `rustc_driver` compilation passed: `Finished release profile
  [optimized] target(s) in 3m 24s`; bootstrap exited **0** in `0:03:25`.
- Full compiler assembly passed: compiler rebuild completed in `2m 51s`,
  the Cranelift 0.132.0 backend in `1m 24s`; bootstrap exited **0** in `0:04:17`.
  The complete logs are `/tmp/qfli-rustc-x64-ohos/rustc-driver-build.log` and
  `/tmp/qfli-rustc-x64-ohos/compiler-assembly-build.log`. After finalizing the
  script, a complete cached rerun passed with exit **0**; the final logs record
  that rerun (`0:00:03` for the driver step, `0:00:01` for compiler assembly).
- Both output libraries are **ELF64 / DYN / x86-64**.
  The driver only needs `libc.so`; the backend needs the freshly built driver
  and `libc.so`. No target LLVM shared library is required.
- The driver has no native TLS program header or TLS relocation
  (`TPOFF`, `DTPMOD`, `DTPOFF`, `TLSDESC`). An `__emutls_unregister_key` symbol
  confirms emulated TLS code. Consequently the static TLS error found with
  the official Linux driver does not establish the same failure on OHOS.

## Output Paths And Checksums

Runtime sysroot:
`/tmp/qfli-rustc-x64-ohos/build/x86_64-unknown-linux-ohos/stage1`.

| File relative to runtime sysroot | Size in bytes | SHA-256 |
| --- | ---: | --- |
| `lib/librustc_driver-2223f3b215a042ae.so` | 139,920,288 | `41de5b503cf788989d64f59f2f4989508f70aed23fb6d9d7b64594d6e4db3982` |
| `lib/rustlib/x86_64-unknown-linux-ohos/codegen-backends/librustc_codegen_cranelift-1.98.1.so` | 15,807,056 | `8dc097c136a55561a1e84c546d45b43048dc55889aba8a62359aa32d6fcd41a2` |

The generated OHOS `bin/rustc` is also present. Neither it nor these libraries
was executed on a device in this build experiment.

Build-time compiler-private sysroot:
`/tmp/qfli-rustc-x64-ohos/build/x86_64-unknown-linux-gnu/stage0-sysroot`.
Its `lib/rustlib/x86_64-unknown-linux-ohos/lib` contains the target metadata
and runtime libraries, including 74 `librustc_*.rmeta` files.
Its `lib/rustlib/x86_64-unknown-linux-gnu/lib` contains matching Linux proc
macros, including `librustc_macros-07c7a5ffbf8df3fd.so`. The target proc-macro
counterpart is `librustc_macros-74c80c4cef30ef41.so`.

The runtime `stage1` assembly is not a rustc-dev installation. For Miri's
Linux cross-build, use the build-time sysroot and both dual-proc-macro flags;
do not substitute the runtime-only sysroot or mix official private metadata
with this custom driver.

## Resolved Build Failures

1. The first bootstrap Cargo build failed in `libc`'s build script because a
   rustc-dev copy of the stage0 driver was loaded without its LLVM search path:
   `libLLVM.so.22.1-rust-1.98.1-stable: cannot open shared object file`.
   The script now exports stage0's top-level `lib` as `LD_LIBRARY_PATH`.
2. The first sparse-source bootstrap compile was missing four editor config
   files included from `src/etc`. Adding `src/etc` and `.cargo` fixed this.
3. After the target std source build passed, compiler compilation failed with
   `E0463: can't find crate for core`. Upstream `StdLink`'s stage0 branch copies
   `initial_sysroot/lib` rather than installing the just-built target std;
   see `src/bootstrap/src/core/build_steps/compile.rs`, lines 816-829.
   The isolated stage0 copy was populated with the already installed official
   same-version x64 OHOS target libraries. The script now fails early when
   stage0 lacks that target and names the `rustup target add` command.

The shared Miri toolchain and shared source were not modified by these fixes.

## Remaining Gates

This experiment completed the compiler/backend build gate. It does not prove
HAP loading or source execution. The native session adapter, MIR sysroot,
packaging and representative source execution remain separate gates.
