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

## Reproducibility Review

`check_miri_source.sh` pins the normalized build-input SHA-256 to
`92f51c0345496c6ef1edbba009985c84b612630dd5c7e81ea2cdd826d0d85764`.
It hashes the sorted relative paths and CRLF-normalized contents of all files
under `src/` and `cargo-miri/src/`, both manifests and lockfiles, and cargo-miri's
build script. Adding a root build script also changes the fingerprint. Tests,
Git metadata, generated targets and disabled optional-feature packages are not
part of this build-input pin. The input snapshot and existing Linux cached copy
matched before this pin was recorded.

Preparation validates both the supplied source and any cached copy, so changing
the source argument cannot silently reuse another revision. Validation also
checks the cached source and the Miri binary's compiler commit. A mismatched
cache exits with an error; it is not silently replaced. These checks establish
the known local build inputs, and do not authenticate independently supplied
binaries or prove mobile execution.

The review reran preparation successfully using the existing build and MIR
sysroot. All five CLI assertions passed again with results in
`/tmp/qfli-miri-reference-1.98.1/validation.gC9Ki3`. Shell syntax checks and
ShellCheck passed for all three scripts. A temporary source copy passed after
conversion to LF and to CRLF; changed manifest contents, changed CLI source,
and a missing cargo-miri build script each failed the source check.

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
