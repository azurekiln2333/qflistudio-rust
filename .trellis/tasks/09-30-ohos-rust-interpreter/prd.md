# Port Rust interpreter to HarmonyOS

## Goal

Port a genuine upstream Rust interpretation path into the HarmonyOS app and verify source execution on device

## Confirmed Facts

- Desktop execution already uses official Cargo/rustc through an external process.
- Rust native-library packaging and calls passed in a HAP on the x64 OHOS simulator at `127.0.0.1:5555`. This probe did not interpret Rust source.
- Miri depends on compiler-private Rust crates, so a target-compiled shared library alone does not provide a Rust source interpreter.
- The pinned upstream Miri library compiles for AArch64 OHOS. Its Linux CLI and MIR standard library execute five reference fixtures; mobile session execution remains unverified.

## Requirements

- Execute user-authored Rust source inside the HarmonyOS app process without invoking a sandbox-forbidden external executable.
- Port or integrate an upstream Rust implementation with genuine parsing, type checking, macros, and Rust semantics; do not present a hand-written subset as a complete interpreter.
- Return stdout, stderr, diagnostics, exit status, and cancellation through the existing `ProgramRunResult` contract.
- Keep the app's runtime availability claim tied to actual device or simulator execution evidence.
- Preserve the existing editor and project flows and avoid development-status text in the product UI.

## Acceptance Criteria

- [ ] A packaged HAP executes representative `.rs` fixtures on a HarmonyOS device or simulator, including modules, ownership/borrowing, generics, errors, stdin, and nonzero exit.
- [ ] Invalid Rust yields upstream-quality diagnostics without executing stale output.
- [ ] Cancellation and resource limits stop active work without freezing the Flutter UI.
- [ ] The bundled upstream source, build inputs, licensing, and ABI integration are reproducible.
- [ ] Automated tests and a device/simulator run prove the claimed behavior; only then is `runtimeStatus` changed to `available`.

## Out of Scope

- A handwritten Rust grammar or toy evaluator presented as a complete interpreter.
- Enabling the mobile runtime or showing a success claim based only on cross-compilation.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
