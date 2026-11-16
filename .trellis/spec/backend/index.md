# Rust Execution Guidelines

The application delegates shared UI and storage to `qfli_studio_core` and owns
Rust compilation, native source execution, process lifecycle and packaging here.
Read the contract for the layer being changed before implementing it.

| Guide | Scope |
| --- | --- |
| [Native Runtime](./native-runtime.md) | Pinned rustc/Miri ABI, architecture packages, signing and device evidence |
| [Compiler Build Provenance](./compiler-build-provenance.md) | Patched compiler identities, immutable inputs and package hash binding |
| [GitHub Native Builds](./github-native-builds.md) | Cloud build stages, downloadable archives, diagnostics and restoration |
| [Offline Analysis](./offline-analysis.md) | Exact unsaved compiler diagnostics and cancellation ownership |
| [Offline Debugger](./offline-debugger.md) | Real Miri pauses, copied values, generations and joined cleanup |
| [Catalog Audit](./catalog-audit.md) | Complete inventory, exact output, durable reports and final HAP inspection |
| [Rust Run Controls](./rust-run-controls.md) | Cargo target selection, editor gestures and continuous terminal titles |
| [Rust Terminal](./rust-terminal.md) | Shared delegates, offline Cargo and real process execution |

For quality verification, run Dart analysis and the relevant real compiler
regressions, then the complete root Flutter suite. Native packaging checks and
platform builds are separate from source execution evidence. Keep all shared
core changes coordinated with the current owner and avoid sibling product edits.
