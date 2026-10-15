# Toolchain discovery and real compile/run plan

## Measured environment (2026-10-12, read-only)

| Probe | Result |
| --- | --- |
| `Get-Command rustc/cargo/rustup` | none |
| `RUST*`/`CARGO*` env | only `RUSTROVER_VM_OPTIONS` (a JetBrains vmoptions path) |
| `%USERPROFILE%\.cargo`, `%USERPROFILE%\.rustup` | absent |
| `D:\AppData\Local\Temp\qfli-rust-toolchain` (historical) | absent |
| `C:\Rust*`, `D:\Rust*`, JetBrains toolchains | absent |
| WSL distros | `Ubuntu` vhdx missing; `qfli-terminal-test` has no rustc/cargo; al3 distros fail to start |

Conclusion: **no usable Rust toolchain is present.** Real compile/run checks
cannot run until one is provisioned.

## Discovery steps to run at implementation time (before concluding "skipped")

1. Re-probe `rustc`/`cargo`/`rustup` on PATH and in the standard install
   locations above (they may appear between planning and implementation).
2. Probe WSL: `wsl -l -v`, then `wsl -d <distro> -e sh -lc 'command -v cargo rustc'`
   for each startable distro.
3. Probe a **permitted workspace-local toolchain**: if none exists, the
   coordinator may authorise installing a minimal toolchain under a
   workspace-local, ignored directory (e.g. `<repo>/.rust-toolchain/` with a
   `.gitignore` entry) via rustup, or a portable `rustc` archive.
   - This is a **network + disk** decision owned by the user; planning records
     it as an option, not an action.
   - If not authorised, real execution stays skipped.
4. Record the exact discovery output in the verification report.

## What can and cannot be verified here

| Check | Needs | Status if no toolchain |
| --- | --- | --- |
| Content integrity (counts, uniqueness, non-triviality, schema, labels) | Dart only | **can run** |
| Repository loading + filtering | Dart/Flutter | **can run** |
| Page/navigation + import (single + cargo-multi) | Flutter test | **can run** |
| `desktop` sample compile+run | `rustc` | skipped (reason recorded) |
| `cargo` sample build+run | `cargo` (+network for deps) | skipped (reason recorded) |
| `external` samples (libc/tokio/proc-macro) | `cargo` + crates.io | skipped (reason recorded) |
| `miri-candidate` samples | packaged engine (`QFLI_MIRI_LIBRARY`/`SYSROOT`) | skipped (reason recorded) |

## Honesty rules (no unqualified success)

- A run that skips all compiler checks **must not** be reported as the task
  passing. The final report states explicitly: "N of 166 examples executed; M
  skipped because no toolchain/engine is available", with the discovery evidence.
- The overall task is **not** complete-quality until either (a) a toolchain is
  provisioned and the `desktop`+`cargo` samples execute, or (b) the user
  explicitly accepts the skipped set. Planning flags this as a blocking risk,
  not a silent pass.

## Recommended path

Ask the user to authorise a workspace-local toolchain install (step 3). With
`rustc`+`cargo` present, ≥150 of 166 examples become genuinely runnable and the
remaining `external`/`miri-candidate` ones stay honestly labeled and skipped.
