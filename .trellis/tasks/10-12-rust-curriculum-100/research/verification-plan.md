# Verification plan — Rust curriculum

## Acceptance gates

1. **Volume / uniqueness** (AC1, AC2)
   - `tutorials == examples == N >= 120`.
   - distinct `id`, `title`, lesson `code`, `summary`, `explain` each == N.
   - zero lessons missing objective/prerequisites/explain/pitfalls.
   - zero single-line lesson code; zero `println!`-only code.
   - zero duplicated exercise prompt/answer across lessons.
2. **Domain coverage** (AC3)
   - verifier emits a table mapping the 10 domains from `design.md` to lesson-id
     ranges; every domain has ≥ the planned count and no gap in 001..120.
3. **Runtime labels** (AC4)
   - every example carries exactly one runtime concept
     (`内置运行` / `需要桌面 Rust 工具链` / `需要 Cargo 依赖` / `外部环境`);
   - the tally is written to the verification report;
   - no example is labeled runnable when its required environment is absent.
4. **Integration / navigation** (AC5, AC8)
   - `test/rust_content_pages_test.dart` (real Rust repository) passes at
     390px and 1280px for both tutorials and examples: catalog → detail →
     import dialog, with CodeSnippet present and no overflow; plus a
     `cargo-multi` example detail.
   - import regression covers the three traced branches (editor / existing
     project / create project) for single files, the cargo-multi create branch,
     adversarial bundle rejection, and the documented fact that the
     editor/existing-project branches ignore a bundle.
5. **Schema validity** (AC6)
   - `ContentCatalogValidator.validate(rustCatalog, enforceReleaseMinimum: true)`
     reports no issues for the Rust entries; no placeholder markers
     (`TBD`, `TODO`, `weighted=`, `数据建模与不变量` filler) remain.
6. **Scope** (AC7)
   - `git status` shows no shared-core modification from this task.
7. **Real execution** (AC9)
   - verifier runs `rustc`/`cargo` for `desktop`/`cargo` samples **iff** the
     toolchain exists on PATH (or via an explicit env var), diffing
     `expectedOutput`. It uses **fixed argv** (`rustc <file> -o <tmp>`;
     `cargo run|build|test --manifest-path <p>Cargo.toml [--bin <name>]`); it
     never executes a bundle `verify` string. Otherwise each sample is listed as
     `skipped (no toolchain)`.
   - `miri-candidate` samples are checked against the packaged engine only when
     `QFLI_MIRI_LIBRARY`/`QFLI_MIRI_SYSROOT` are present (device/engine
     evidence); otherwise skipped. No example is labeled embedded-supported just
     because it has no crates.
   - a run whose compile checks are all skipped is **not** reported as fully
     verified; the report states executed vs skipped counts explicitly.

## Environment constraints (measured)

- Windows PATH: no `rustc`, no `cargo`; `~/.cargo` absent; no rustup.
- WSL: `Ubuntu` vhdx missing; `qfli-terminal-test` has no rustc/cargo; al3
  distros fail to start.
- Flutter/Dart: `D:/ProgramFiles/flutter_ohos/bin`.
- Therefore real compiler execution is expected to be **skipped** during this
  task and reported as such; content integrity and repository/navigation tests
  do not depend on a compiler.

## Tooling

- `tool/generate_rust_content.dart` — validate + emit Rust assets + manifest.
- `tool/verify_rust_content.dart` — integrity, coverage, labels, optional real
  run; writes a machine-readable report.
- New Dart tests under `test/` for content integrity, repository filtering and
  import/pages regression.

## Non-claims

- Mocked/asset-level checks are not "Rust execution".
- Skipped compiler/device checks are never counted as passing.
