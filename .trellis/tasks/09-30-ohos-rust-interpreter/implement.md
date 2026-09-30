# Implementation Plan

- [x] Pin the Rust and DevEco toolchain paths and create a reproducible OHOS
      native probe build with explicit output and ABI checks.
- [x] Package the probe in the app and invoke it from a device-installed HAP;
      capture the device architecture, installation, call result and logs.
- [x] Pin Rust/Miri 1.98.1 at commit
      `48a229ceaefd4985c50990b14116b6d856af0985`; validate normalized source
      inputs and lock dependencies to upstream versions/checksums.
- [x] Build compiler-private OHOS host components. Official AArch64 components
      work with Linux host proc macros; x64 rustc_driver and Cranelift were
      built from upstream source. Record commands and failures in research.
- [x] Integrate source-to-MIR-to-execution through the native session ABI:
      stdin, separate output/diagnostics, exit status, cancellation and limits.
      Both AArch64 and x64 OHOS adapter shared libraries compile.
- [x] Wire OHOS execution through Dart FFI on a worker isolate, preserving the
      desktop Cargo/rustc path and the shared ProgramRunResult contract.
- [x] Package native dependencies, guest MIR libraries and upstream notices;
      extract manifest assets into the app storage directory on demand.
- [x] Record five upstream CLI fixtures and twelve Linux C ABI checks already
      completed before the user's instruction to stop testing.
- [x] Regenerate native libraries and the HAP with the final review fixes;
      record the resulting build and signing status.
- [ ] Exercise valid, invalid, stdin, nonzero-exit and cancellation fixtures on
      device; compare with desktop reference behavior.
- [x] Commit the native session and Flutter packaging batches with conventional
      messages after source review and necessary builds.

Implementation commits: `c544537` (`feat(native): embed upstream Miri session
runtime`) and `c964209` (`feat(ohos): integrate packaged Miri execution runner`).
Final packaging/build evidence is in `research/flutter-miri-integration.md`.

## Current Execution Direction

The latest user instruction is to stop testing and continue implementation.
Do not retry hdc connections or run fixture/device tests in this batch. Necessary
native and HAP builds continue. Device acceptance remains pending; do not archive
this task or change `runtimeStatus` to `available`.

ABI 1 accepts a source crate with standard libraries. Mobile Cargo dependency
resolution, build scripts and external proc macros require further work.
Cancellation checks compiler phase boundaries and MIR execution; compiler
queries and rustc host memory are outside the guest execution limits.

## Review Gates

- A cross-compiled `.so` alone does not pass the HAP loader gate.
- A probe call does not pass the interpreter gate or enable the runtime UI.
- An OHOS target build does not pass the rustc/Miri OHOS host gate.
- The current debug signing profile is bound to `com.azurekiln.qfli.forge`, while
  this app declares `com.azurekiln.qfli.rustcore`; signing fails with Hvigor
  00303074. The x86_64 simulator at `127.0.0.1:5555` accepts the unsigned debug
  HAP and passed the loader/call gate. A matching profile is still needed for
  physical-device signing.

## Risky Files

`ohos/entry/src/main/ets/entryability/EntryAbility.ets` contains unrelated
uncommitted user work. Native verification should avoid changing it. Any later
integration touching it must preserve and review that diff explicitly.
