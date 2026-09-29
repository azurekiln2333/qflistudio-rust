# Desktop Rust compile and run

## Goal

Connect upstream rustc and Cargo to the Rust app, with streaming diagnostics, cancellation and executable tests

## Requirements

- On desktop, compile and run a Cargo project using Cargo and a standalone `.rs` entry using rustc.
- Forward compiler diagnostics and program stdout/stderr to the existing terminal result contract without losing early output.
- Return compiler or program exit codes accurately; use the backend-unavailable exit code only when execution never starts.
- Support cancellation of compilation and execution, including child processes.
- Let Cargo maintain its standard incremental `target` cache. Keep standalone rustc output temporary, and avoid stale executable reuse after compilation failure.
- Handle missing toolchains and source files with concise, actionable errors without claiming the runtime is under development.
- Do not change unrelated platform files or shared UI code.

## Acceptance Criteria

- [ ] Cargo project and standalone Rust source compile and execute with correct output and exit code.
- [ ] Syntax error prevents execution and its diagnostics and nonzero compiler status are shown.
- [ ] Missing toolchain/source and cancellation are covered by meaningful tests.
- [ ] Flutter analyze and test pass for the Rust package.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
