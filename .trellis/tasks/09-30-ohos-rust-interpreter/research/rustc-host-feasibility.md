# Research: rustc and Miri as OpenHarmony host code

- Query: Can a version-matched upstream rustc and Miri run as an OHOS host inside the HarmonyOS app process?
- Scope: mixed (local toolchain and app, official Rust sources and distributions, upstream dependency issues)
- Date: 2026-09-30

## Findings

### Files found and local boundary

- `lib/rust_runner.dart`: desktop runner calls `Process.start` at line 151 and uses `ProgramRunResult` at lines 19 and 46; this executable path cannot serve the required in-process mobile runtime.
- `lib/main.dart:32`: mobile `runtimeStatus` remains `unavailable`.
- `.trellis/tasks/09-30-ohos-rust-interpreter/{prd.md,design.md,implement.md}`: requires in-process Rust source execution, real device proof, and an OHOS **host** compiler/Miri gate, beyond a target-built `.so`.
- `.trellis/tasks/09-30-ohos-rust-interpreter/research/upstream-and-target.md`: records the earlier AArch64 target `cdylib` probe; it does not establish host-tool or Miri support.
- `.trellis/spec/frontend/index.md`, `.trellis/spec/backend/index.md`: package spec indexes are currently generic templates. `.trellis/spec/guides/cross-layer-thinking-guide.md` applies to the Dart/native result boundary.

### Pinned toolchain and host distribution

- Local `rustc -vV`: **rustc 1.98.1**, commit `48a229ceaefd4985c50990b14116b6d856af0985` (2026-09-01), Windows GNU host, LLVM 22.1.8. The local rustup installation has only `stable-x86_64-pc-windows-gnu`; `rust-std-aarch64-unknown-linux-ohos` is installed. `rustc --print cfg --target aarch64-unknown-linux-ohos` reports `target_arch="aarch64"`, `target_os="linux"`, `target_env="ohos"`, and `unix`.
- The Rust **1.98.1** [OpenHarmony platform page](https://raw.githubusercontent.com/rust-lang/rust/1.98.1/src/doc/rustc/src/platform-support/openharmony.md) classifies AArch64, ARMv7 and x86_64 OHOS as **Tier 2 with Host Tools**, explicitly distinct from merely building programs *for* OHOS. It documents cross-linker wrappers and an upstream `bootstrap.toml` recipe. Therefore an OHOS rustc host build is supported upstream; a new rustc source port is not the first prerequisite.
- Read-only `curl.exe -I -L` checks of Rust 1.98.1 distribution archives each returned `HTTP/1.1 200 OK`: [rustc host archive](https://static.rust-lang.org/dist/rustc-1.98.1-aarch64-unknown-linux-ohos.tar.xz) (89,721,732 bytes), [Cargo host archive](https://static.rust-lang.org/dist/cargo-1.98.1-aarch64-unknown-linux-ohos.tar.xz) (9,850,940 bytes), and [rustc-dev host archive](https://static.rust-lang.org/dist/rustc-dev-1.98.1-aarch64-unknown-linux-ohos.tar.xz) (141,622,276 bytes). No large archive was downloaded. The Windows `rustup component list` prints `rustc-dev-aarch64-unknown-linux-ohos` but lists `rustc` and Cargo only for its installed Windows host; archive checks resolve that listing ambiguity.
- Reproduction commands (PowerShell): `$env:RUSTUP_HOME = Join-Path $env:TEMP 'qfli-rust-toolchain/rustup'`; `$env:CARGO_HOME = Join-Path $env:TEMP 'qfli-rust-toolchain/cargo'`; `& (Join-Path $env:CARGO_HOME 'bin/rustc.exe') -vV`; `& (Join-Path $env:CARGO_HOME 'bin/rustup.exe') toolchain list`; `& (Join-Path $env:CARGO_HOME 'bin/rustc.exe') --print cfg --target aarch64-unknown-linux-ohos`; `curl.exe -I -L <archive URL>`.

### Exact Miri blocker and candidate route

- The same [official 1.98.1 page](https://raw.githubusercontent.com/rust-lang/rust/1.98.1/src/doc/rustc/src/platform-support/openharmony.md) explicitly **excludes Miri** from its OHOS host-tool support because `libffi` and `tikv-jemalloc-sys` do not compile for OHOS. Existing rustc/Cargo host archives therefore do not imply an OHOS Miri runtime.
- The version-matched [Miri snapshot in Rust 1.98.1](https://raw.githubusercontent.com/rust-lang/rust/1.98.1/src/tools/miri/Cargo.toml) is a `rustc_private` tool. Its default features are `stack-cache` and `native-lib`; `native-lib` includes the optional `libffi` dependency. It also has a separate empty `jemalloc` feature. The [Miri binary source](https://raw.githubusercontent.com/rust-lang/rust/1.98.1/src/tools/miri/src/bin/miri.rs) imports compiler-private crates and `rustc_driver`, conditionally imports `tikv_jemalloc_sys` when `jemalloc` is enabled on AArch64 Linux, and calls `std::process::exit` in its compiler-run path. Since OHOS reports `target_os="linux"`, those AArch64 Linux conditions can apply.
- Rust 1.98.1 [bootstrap tool step](https://raw.githubusercontent.com/rust-lang/rust/1.98.1/src/bootstrap/src/core/build_steps/tool.rs) enables Miri's `jemalloc` feature when `builder.config.jemalloc(target)` is true. [Bootstrap config](https://raw.githubusercontent.com/rust-lang/rust/1.98.1/src/bootstrap/src/core/config/config.rs) defaults `rust_jemalloc` to false when unset. Disabling `jemalloc` and building Miri with `--no-default-features` is a **candidate experiment** to avoid both named native dependencies; it disables Miri's native-library feature, and neither compilation nor representative program support on OHOS has been verified. This does not remove the separate work of exposing Miri/rustc through an in-process C ABI instead of the CLI's argument, exit, and process model.
- [libffi-rs OHOS registration PR #105](https://github.com/libffi-rs/libffi-rs/pull/105) is closed without merge. The maintainer's [comment](https://github.com/libffi-rs/libffi-rs/pull/105#issuecomment-2779673788) requests upstream libffi changes instead of crate-local patches. [tikv/jemallocator OHOS issue #121](https://github.com/tikv/jemallocator/issues/121) remains open; its reported cross-build includes `configure: error: cannot find sources (Makefile.in)` and links a [tikv/jemalloc registry PR #5](https://github.com/tikv/jemalloc/pull/5), also closed without merge. This issue is an x86_64 OHOS report, so it is evidence of missing support, not a reproduced AArch64 error in this workspace.
- The [Miri 1.98.1 binary source](https://raw.githubusercontent.com/rust-lang/rust/1.98.1/src/tools/miri/src/bin/miri.rs) calls `rustc_driver::run_compiler` through callbacks, so a same-process compiler call exists in upstream code. The file also reads CLI arguments and calls `std::process::exit`; a Flutter app cannot treat the unmodified binary as a callable session library. Packaging/linking its compiler dependencies, diagnostics/I/O capture, cancellation, and resource bounds remain unproved.

## Caveats / Not Found

- No local OHOS **host** rustc/Cargo installation, matching `rustc-dev` libraries, full Rust source tree, or Miri build was present. No actual OHOS host or Miri build was run in this research pass. This finding is based on official distribution and source evidence; it does not claim an embeddable engine or successful HAP execution.
- No merged OHOS patch for the two named Miri native dependencies was found in the checked upstream issues/PRs. `--no-default-features` plus disabled jemalloc remains a hypothesis, not a tested workaround. A successful compile would still need the app-process ABI and the PRD's Rust fixture suite on device.
- The official Tier 2 host-tool classification corrects the earlier implication in `upstream-and-target.md` that rustc host feasibility was unknown; Miri support remains the distinct blocker. Keep `runtimeStatus` unavailable until actual source execution passes on a packaged HAP.

## Follow-up Build Evidence

The subsequent experiments in `miri-build-validation.md` compiled the upstream
Miri library for AArch64 OHOS using a matching Linux host toolchain, both
dual-proc-macro flags, and disabled native-library/jemalloc features. The
Windows combination failed on proc-macro identity mismatch. Official 1.98.1
channel manifests and HTTP checks also showed that x64 OHOS host-tool
distributions are absent despite the platform page's host-tools wording.
Native app-process interpretation remains unverified.
