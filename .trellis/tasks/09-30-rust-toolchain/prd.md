# Rust interpreter and compiler toolchain

## Goal

Deliver verified Rust interpretation, compilation, execution and practical Rust tooling across supported platforms

## Requirements

- Port or integrate a real Rust language implementation; do not present a hand-written toy grammar as a complete Rust interpreter or compiler.
- Compile and execute Rust projects and single-file programs, with observable stdout, stderr, exit status, and cancellation.
- Provide practical Rust project tools such as build checking and formatting through verified toolchain paths.
- Support the target platforms truthfully, including the mobile sandbox limitations.
- Keep unfinished implementation status and placeholder output out of the app UI.
- Commit each completed code change with a conventional Git message without including unrelated worktree changes.

## Acceptance Criteria

- [ ] The app compiles and runs representative Rust projects and source files on each advertised target platform; tests execute the resulting programs.
- [ ] A ported interpreter, where required by platform restrictions, passes syntax, diagnostics, semantics, I/O, error, and cancellation tests against an upstream reference.
- [ ] Rust-specific tools are accessible in the app and verified on their supported targets.
- [ ] No visible UI labels runtime work as under development, and capability claims match tested behavior.
- [ ] Each implementation batch has its own conventional Git commit.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
