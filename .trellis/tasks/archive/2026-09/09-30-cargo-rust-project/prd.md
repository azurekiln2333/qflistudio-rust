# Cargo-ready Rust project creation

## Goal

Make new Rust projects immediately usable with Cargo while preserving existing project behavior

## Requirements

- Creating a Rust template project in QFLIRustCore produces a valid Cargo binary project without requiring the installed compiler during creation.
- The package name derives predictably from the project name and remains valid for Chinese names, spaces, punctuation, and leading digits.
- Non-Rust/empty project creation retains the existing shared-store behavior.
- Existing Rust projects are not modified when opened or loaded.
- Generated Cargo build output is ignored by version control.

## Acceptance Criteria

- [ ] A newly created Rust project contains `Cargo.toml`, `src/main.rs`, and a `target` ignore rule.
- [ ] Cargo metadata accepts representative ASCII and non-ASCII project names.
- [ ] The app's run path compiles and executes a newly created Rust project with the upstream Cargo toolchain.
- [ ] Non-Rust creation and existing projects remain unaffected.
- [ ] Flutter analyze and tests pass.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
