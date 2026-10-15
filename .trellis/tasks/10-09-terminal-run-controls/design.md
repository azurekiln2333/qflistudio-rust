# Design

## Boundary

Reuse shared EditorPage and TerminalPane unchanged. Their current-file gesture and continuous transcript are already present. Correct the selected-source contract inside RustProgramRunner and simplify titles in both desktop and embedded runners. No native ABI/runtime packaging changes are needed.

## Execution contract

1. Editor Run tap resolves the configured project entry; long press captures and saves the current .rs source. Both pass one absolute entryFile to the profile runner.
2. Embedded execution continues to pass that source directly to NativeMiriProgramRunner.
3. Desktop execution without Cargo uses the existing direct rustc compilation.
4. Desktop execution with Cargo runs cargo metadata --no-deps --format-version 1 for the existing manifest, capturing stdout privately while retaining stderr and process cancellation.
5. Decode metadata once into typed target identity. Match normalized absolute src_path exactly; runnable kinds are bin and executable example. Run a matching target explicitly using its manifest/package plus --bin/--example, preserving dependency/build configuration.
6. If metadata is valid but the source is not registered as a runnable target, compile it through the existing standalone rustc route. Such a file must be independently compilable; external crate dependencies are not synthesized. Never change Cargo.toml or silently execute a different source.
7. Metadata errors and ambiguous/non-executable target states produce actionable diagnostics. Cancellation remains exit 130; failure-to-start remains kProgramNotRunExitCode. Do not swallow errors or convert them into success.

## Terminal contract

Both Rust runners provide a concise `run <project-relative-source>` title, with normal path display and quoting when needed. No backend suffix or localized completion boilerplate is added. The shared terminal controls prompt/command layout and quiet successful exits; user program output is never filtered.

## Expected files

- lib/rust_runner.dart: selected Cargo source routing and desktop title.
- lib/native_miri_runner.dart: matching concise embedded title.
- A small Rust-local Cargo metadata target module if needed to own typed decoding and selection.
- test/rust_app_test.dart and relevant native runner tests: regression coverage for actual run results.
- Focused Cargo target tests and a Rust editor gesture integration test if existing tests cannot verify the Rust seam.
- Task research/evidence and a scoped executable-contract spec update.

## Compatibility and risks

Existing standalone compilation, toolchain environment/linker overrides, input.txt, cancellation, mobile backend routing and shared ProgramRunner interfaces remain intact. No Cargo dependency support is added to standalone files. No runtime download, SDK replacement, shared-core redesign or other-language edit is part of this task.

Capture touched files before edits because both tracked and untracked runtime work predates this task. Restore only task-introduced hunks if a rollback is necessary; never reset the worktree.
