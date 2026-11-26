# Rust Execution Guidelines

The application delegates shared UI and storage to `qfli_studio_core` and owns
Rust compilation, native source execution, process lifecycle and packaging here.
Read the contract for the layer being changed before implementing it.
Read [Cloud-only workspace](../guides/cloud-only-workspace.md) first: all
executable checks/builds run only on GitHub-hosted runners, not this checkout.

| Guide | Scope |
| --- | --- |
| [Native Runtime](./native-runtime.md) | Pinned rustc/Miri ABI, architecture packages, signing and device evidence |
| [Compiler Build Provenance](./compiler-build-provenance.md) | Patched compiler identities, immutable inputs and package hash binding |
| [GitHub Native Builds](./github-native-builds.md) | Cloud stages, copied/JNI integrity, absolute tool aliases and raw-byte fixtures |
| [GitHub Application CI](./github-app-builds.md) | Core/SDK gates, producer-byte provenance, typed OHOS no-sign, packages, intermediates and quality reports |
| [Offline Analysis](./offline-analysis.md) | Exact unsaved compiler diagnostics and cancellation ownership |
| [Offline Debugger](./offline-debugger.md) | Real Miri pauses, copied values, generations and joined cleanup |
| [Catalog Audit](./catalog-audit.md) | Complete inventory, exact output, durable reports and final HAP inspection |
| [Rust Run Controls](./rust-run-controls.md) | Cargo target selection, editor gestures and continuous terminal titles |
| [Rust Terminal](./rust-terminal.md) | Shared delegates, offline Cargo and real process execution |

For quality verification, run Dart analysis and the relevant real compiler
regressions, then the complete root Flutter suite on GitHub-hosted runners.
Record actual run/job evidence; missing hosted checks remain pending. Native packaging checks and
platform builds are separate from source execution evidence. Application CI
contracts have source-only review; actual application validation remains pending.
Keep all shared
core changes coordinated with the current owner and avoid sibling product edits.
