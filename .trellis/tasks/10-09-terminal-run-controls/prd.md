# Continuous terminal and current-file execution in QFLI Rust

## Goal

Make QFLI Rust use the professional, continuous terminal already implemented in the shared core, and honor the distinction between running the project and running the current file. Pi performs delegated work in the right Herdr pane under the coordinator's direction.

## Background

The user explicitly approved task creation and planning on 2026-10-09. The Rust application depends on ../qfli_studio_core. The active Java session already modified the shared editor and terminal and added focused regression tests. Other language sessions are active concurrently; their changes must be preserved.

## Requirements

- R1: Audit what the Java and shared-core changes already provide and identify Rust-specific gaps.
- R2: Run click launches the configured project entry. Long press launches the current runnable .rs file once after saving, without modifying the configured entry.
- R3: Commands, stdout/stderr, and the prompt occupy one continuous terminal scrollback; input follows output instead of living in a disconnected panel.
- R4: Successful runs add no synthetic completion or exit-code-0 message. Run titles omit Chinese boilerplate and backend suffixes such as (jdk), (Rust), or (Rust / Miri). Failure diagnostics and nonzero exits remain visible.
- R5: Cargo execution honors the selected source instead of silently running a different target. Preserve cancellation, input.txt handling, compiler flags, project configuration, and existing runtime routing.
- R6: The right-hand Pi agent owns approved Rust implementation and tests. The coordinator owns planning, review, evidence, and task records.

## Acceptance Criteria

- [x] AC1 (R1): Source-backed report distinguishes already implemented shared-core behavior from remaining Rust gaps.
- [x] AC2 (R2, R5): With main2.rs active, tap/long-press/tap run the configured entry/main2.rs/configured entry exactly once each; project metadata stays unchanged.
- [x] AC3 (R3): Empty and populated terminals render one scrollable command/output/prompt sequence.
- [x] AC4 (R4): Desktop and embedded run titles are concise; success is quiet; real stdout/stderr and failure codes are preserved.
- [x] AC5 (R5): Cargo targets use their selected source, and a standalone current file is never silently replaced with the default target.
- [x] AC6 (R6): Focused Rust and shared-core checks pass; verification limits are recorded without claiming unavailable device coverage.

## Out of Scope

Replacing compilers/interpreters, redesigning primary navigation, modifying other language editions, rewriting user Cargo manifests, or overwriting shared-core work owned by the Java session.

## Evidence

- pubspec.yaml: local ../qfli_studio_core dependency.
- ../qfli_studio_core/lib/editor/editor_page.dart:714-911: existing save pipeline, entry override, and active-file validation.
- ../qfli_studio_core/lib/editor/terminal_pane.dart:876-915: prompt is the final row of the transcript.
- lib/rust_runner.dart:40 and lib/native_miri_runner.dart:41: old localized/backend run titles.
- lib/rust_runner.dart:140-151: Cargo invocation currently discards entryFile.
- ../qfli_studio_core/test/editor_run_test.dart and terminal_pane_test.dart: existing shared regression coverage.

## Planning Status

Research is complete. PRD, design, implementation plan, and both context manifests are ready. The user explicitly approved the final planning summary on 2026-10-09; implementation is authorized.



All acceptance criteria are covered by the source audit, deterministic tests and visual checks in research/final-verification.md. Real compiler/device validation limits are explicit there. Commit handling remains separate.
