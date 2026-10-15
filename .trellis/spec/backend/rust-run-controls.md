# Rust Run Controls And Terminal Titles

## 1. Scope / Trigger

Apply when editing RustProgramRunner, NativeMiriProgramRunner, Cargo target selection, run-title formatting, or tests at the shared EditorPage / Rust runner boundary. The shared terminal UI belongs to ../qfli_studio_core; check its current changes before attempting an app-local replacement. Native ABI/packaging rules remain in native-runtime.md.

## 2. Signatures

```dart
Future<ProgramRunResult?> run({
  required String projectPath,
  required String entryFile,
});
String rustRunTitle(String projectRoot, String entryFile);
```

```text
cargo metadata --no-deps --format-version 1 --manifest-path <project/Cargo.toml>
cargo run --manifest-path <owning-package/Cargo.toml> --package <package> --bin <target>
cargo run --manifest-path <owning-package/Cargo.toml> --package <package> --example <target>
```

Metadata fields used: packages[].name, manifest_path, targets[].name, src_path, kind, crate_types. Decode this untyped JSON at one Rust-local boundary; consumers use the resulting typed target/selection description.

## 3. Contracts

- Editor tap resolves ProjectConfig.entryFile/profile defaults; long press captures the selected .rs path and uses the normal save pipeline. Neither gesture rewrites the configured project entry.
- entryFile is the authoritative source. Never replace it with Cargo's implicit default simply because Cargo.toml exists.
- Cargo supplies target/package names; do not derive them from basenames. Match normalized absolute src_path, retain package identity, and handle platform path equality.
- Bin targets and examples whose crate_types include bin are runnable. Preserve non-runnable target ownership through decoding so a registered library/test/bench/build script is not misclassified as an independent source.
- Exactly one matching runnable target uses explicit Cargo selectors. Valid metadata with no registered owner uses existing standalone rustc. That route requires an independently compilable file and does not synthesize external Cargo dependencies.
- Malformed metadata, ambiguous ownership, and registered non-runnable sources produce diagnostics; they do not fall back to the default source or masquerade as an unregistered file.
- Metadata and compilation use the same cancellable process lifecycle. Capture metadata stdout privately; keep diagnostics on stderr. Preserve input.txt, toolchain environment, RUSTC and compiler/linker overrides.
- Cancellation remains 130, including during metadata. Startup/selection failures use kProgramNotRunExitCode. Preserve the actual program's stdout/stderr and exit status.
- Both desktop and embedded runners own a concise `run <relative-source>` title, using portable separators and quoting whitespace paths. Keep embedded results transparently forwarded after their source owner formats the title.
- Shared TerminalPane renders command/output/prompt in one scrollback. Exit 0 adds no artificial completion text; real program output is never filtered just because it resembles a status line.

## 4. Validation & Error Matrix

| Condition | Required result |
| --- | --- |
| Main2 is open and tap Run is used | Configured project entry runs once |
| Main2 is open and Run is long-pressed | Main2 runs once; configured entry stays unchanged |
| Cargo bin name differs from source name | Use the metadata target name |
| Same target name appears in multiple workspace packages | Use the owning package and manifest |
| Current source is not registered | Standalone source route, never another bin |
| Current source is a library or library-shaped example | Selection failure with diagnostic |
| More than one runnable target owns the source | Report ambiguity; do not choose the first |
| Metadata JSON/schema is malformed | Controlled parse/selection failure |
| Cancellation arrives during metadata | Exit 130; no subsequent compilation/run |
| Source path contains whitespace | Quoted concise title; executable arguments remain separate |
| Program exits 0 | Original output, then prompt; no generated exit-0 line |
| Program exits nonzero | Original diagnostics and nonzero status remain available |

## 5. Good / Base / Bad Cases

- Good: project entry src/main.rs and current src/bin/tool.rs share a Cargo workspace. Tap runs the configured source; long press runs Cargo's matching named tool target with its dependencies.
- Base: standalone main2.rs has its own main function. Long press compiles that source while leaving project entry metadata unchanged.
- Bad: src/lib.rs is filtered out during metadata decoding and later compiled as if it were unregistered. Preserve its ownership and reject it as a non-runnable Cargo target.

## 6. Required Tests

- Target decoding/selection: custom names and paths, workspace package identity, bin/executable example, non-runnable targets, ambiguity, and malformed field types.
- Runner integration: private metadata stdout, explicit selectors, no run after metadata failure, cancellation during metadata, standalone selected-source routing, and unchanged manifest.
- Rust editor seam: tap/long-press/tap selects entry/current/entry exactly once using the real Rust profile, saves edits, and preserves ProjectConfig.
- Titles: desktop/native use the same concise formatting, including paths with spaces.
- Shared regressions: editor_run_test.dart and terminal_pane_test.dart cover continuous transcript, quiet success, diagnostic preservation, history and session ownership.
- Distinguish mocked process tests, real Cargo/rustc tests, visual fixture renders, and mobile device execution. Skipped compiler tests and mocked stdout must never be reported as real Rust execution.

## 7. Wrong vs Correct

Wrong: `if (Cargo.toml exists) cargo run` discards entryFile and makes both gestures run the default.

Correct: obtain Cargo target metadata, select the exact source explicitly, and use the existing standalone route only when valid metadata has no registered owner.

Wrong: metadata cancellation becomes a generic preparation error and exits 127.

Correct: handle cancellation before converting a selection error into a failure-to-start result; return 130 and do not start another process.
