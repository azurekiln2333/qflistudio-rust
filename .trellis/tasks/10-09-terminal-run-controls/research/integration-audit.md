# Java/shared-core audit and Rust integration gaps

Pi worker: pi-rust-terminal in Herdr pane wB:p2, current Rust workspace. The coordinator obtained two read-only reports and inspected source anchors on 2026-10-09.

## Confirmed shared behavior

- pubspec.yaml uses the local ../qfli_studio_core, so shared UI changes apply directly to Rust.
- EditorPage._runProject(entryOverride) saves open files, then selects the override or configured entry. _runActiveFile validates the selected file and passes its absolute path. Rust's profile already accepts .rs.
- TerminalPane renders command/output rows and the prompt as the last row of the same ListView. All three exit-reporting routes show only nonzero status; user stdout is preserved literally.
- Shared test/editor_run_test.dart covers tap/long-press/tap, save-before-run and invalid selection. Shared terminal_pane_test.dart covers transcript continuity, quiet success, nonzero failure, history, cancellation and session ownership.
- Java task research/pi-final-check.md reports 22 focused passes and five visual renders. These are prior-session evidence, not new results of this Rust task. The coordinator viewed phone-dark.png and confirmed one continuous surface.

## Rust defects

1. lib/rust_runner.dart:40 builds a Chinese title with a Rust suffix; lib/native_miri_runner.dart:41 adds a Rust / Miri suffix. The shared terminal echoes the runner-provided title, so these must be corrected at their Rust owners.
2. lib/rust_runner.dart:140-151 detects Cargo.toml and invokes cargo run without using entryFile. A valid current main2.rs is therefore replaced by Cargo's default target. Non-Cargo and native/Miri routes already use the selected source.
3. Existing Rust Cargo tests cover the default source, not switching to an alternate target. test/rust_app_test.dart also has a title assertion that expects Rust branding.

## Technical decision

Use Cargo's own no-dependency metadata to match normalized target src_path against entryFile. Select bin/example targets explicitly with their package/manifest identity. An unregistered .rs uses the existing standalone rustc route; it does not automatically inherit external Cargo dependencies. Metadata failure is an error, not a reason to run the wrong/default file. Do not parse TOML using regex or rewrite the user's manifest.

The existing session process wrapper must own metadata and compilation so cancellation, streams, flags and input.txt retain their behavior. Decode metadata into a typed target description at one boundary and cover it with meaningful selection tests.

## Ownership

The Java session still owns shared-core product code. This task edits only Rust sources/tests and its own Trellis records. There are extensive pre-existing worktree changes; capture exact touched-file baselines before implementation and never revert unrelated changes.

## Validation environment

Flutter/Dart resolve to D:/ProgramFiles/flutter_ohos/bin. rustc/cargo are absent from the ordinary PATH. Prior project research points to D:/AppData/Local/Temp/qfli-rust-toolchain/rustup/toolchains/stable-x86_64-pc-windows-gnu/bin; verify its current existence before deciding compiler tests must be skipped.
