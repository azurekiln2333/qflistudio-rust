# Rust Execution Guidelines

The application delegates shared UI and storage to `qfli_studio_core` and owns
Rust compilation, native source execution, process lifecycle and packaging here.
Read the contract for the layer being changed before implementing it.

| Guide | Scope |
| --- | --- |
| [Native Runtime](./native-runtime.md) | Pinned rustc/Miri ABI, architecture packages, signing and device evidence |
| [Rust Run Controls](./rust-run-controls.md) | Cargo target selection, editor gestures and continuous terminal titles |
| [Rust Terminal](./rust-terminal.md) | Shared delegates, offline Cargo and real process execution |

For quality verification, run Dart analysis and the relevant real compiler
regressions, then the complete root Flutter suite. Native packaging checks and
platform builds are separate from source execution evidence. Keep all shared
core changes coordinated with the current owner and avoid sibling product edits.
