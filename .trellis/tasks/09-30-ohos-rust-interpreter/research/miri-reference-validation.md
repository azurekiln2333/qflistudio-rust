# Upstream Miri Reference Validation

Date: 2026-09-30. This is Linux CLI evidence, not HAP or session-ABI evidence.

## Inputs And Commands

- Miri from Rust 1.98.1, pinned compiler commit
  `48a229ceaefd4985c50990b14116b6d856af0985`.
- WSL distro `qfli-java-build`, official Linux Rust 1.98.1 and `rustc-dev`
  under `/tmp/qfli-miri-cross-1.98.1`. Added matching `rust-src`.
- `sh scripts/prepare_miri_sysroot.sh <Rust-source>/src/tools/miri`.
  Copied Miri into `/tmp/qfli-miri-reference-1.98.1/source`, built the upstream
  CLI without native-library/jemalloc features, and built cargo-miri from its
  separate lockfile. No upstream source changes were needed.
- `cargo-miri miri setup --target x86_64-unknown-linux-gnu` built the standard
  library with MIR. Output: `/tmp/qfli-miri-reference-1.98.1/sysroot`.
  The interpreter guest target is independent of the OHOS host architecture.
- `sh scripts/verify_miri_reference.sh` exited **0** and printed
  `Five upstream CLI fixtures passed.` The captured results are under
  `/tmp/qfli-miri-reference-1.98.1/validation.NGTfcj`.

## Assertions

| Fixture | Required result |
| --- | --- |
| `modules_generics.rs` | exit 0; stdout `total=12`; stderr `items=3`; assertions pass |
| `stdin.rs` | input `rust`; exit 0; stdout `input=rust`; empty stderr |
| `nonzero.rs` | exit 7; stdout `before-exit`; empty stderr |
| `invalid_borrow.rs` | exit 1; diagnostic E0502; empty stdout |
| `invalid_type.rs` | exit 1; diagnostic E0308; empty stdout |

Expected output files include their final newline, and are compared with `cmp`.
The `cancel.rs` fixture is for the later native cancellation gate and is not
part of this CLI reference check.

## Build And Invocation Details

- The first Linux CLI link failed to find `-lLLVM-22-rust-1.98.1-stable`.
  Adding `-L native=<Linux-sysroot>/lib` to the final Miri binary link fixed it.
  `LD_LIBRARY_PATH=<Linux-sysroot>/lib` is also needed at runtime.
- This stable-version source snapshot needs `RUSTC_BOOTSTRAP=1` for Miri's
  internal `-Z` compiler arguments. The verification script supplies it.
- Direct CLI invocation needs an explicit `--sysroot`; `MIRI_SYSROOT` alone
  is consumed by cargo-miri, and does not select the direct CLI's sysroot.
- stdin requires `-Zmiri-disable-isolation` for the unmodified CLI. The mobile
  adapter should provide per-session stdin without reading the app's stdin
  or redirecting process-global file descriptors.

## Remaining Gates

The app-process API, captured diagnostics/I/O, cancellation, resource limits,
x64 compiler-private libraries and HAP source execution are not proved by
these CLI runs. `runtimeStatus` remains unavailable.
