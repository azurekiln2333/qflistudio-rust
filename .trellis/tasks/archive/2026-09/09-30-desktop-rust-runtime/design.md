# Desktop Rust Runtime Design

## Boundary

`RustProgramRunner` owns `.rs` execution. It returns `ProgramRunResult` to the shared editor without changing the shared contract. On desktop, a `Cargo.toml` at the project root selects `cargo run` with Cargo's standard incremental `target` cache; otherwise `rustc` compiles the selected entry to a temporary executable, which is started only when compilation succeeds. Both stages stream output and share one cancellation owner.

## Process and data flow

The runner validates the entry path and project root, starts the selected upstream toolchain command, forwards UTF-8 lines from both pipes, records the exact exit code, then cleans any standalone temporary output. Cargo owns its regular build cache. The compiler and the binary run with the project as working directory. No project-controlled string is passed through a shell. Cancellation terminates the active process tree and returns a nonzero status.

## Platform boundary

The desktop path uses installed upstream Cargo/rustc. Mobile execution remains unavailable until a genuine in-process runtime is ported and tested; no desktop availability claim is applied to mobile. The app shows a direct toolchain/runtime error, not development-status text.

## Verification

Test command selection, compile failure, missing toolchain, cancellation, and output flow. Run a real Rust source program when `rustc` is available in the verification environment. Check the Flutter package with analyze and tests.
