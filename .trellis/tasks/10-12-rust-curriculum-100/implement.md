# Implementation and verification — Rust curriculum

## Review gate

- [x] User approved task creation and planning (2026-10-12).
- [x] Evidence collected: current Rust content is template filler (100/100, 1
      distinct explain, 1 distinct exercise prompt, 0 objectives, 0 pitfalls,
      all single-line code).
- [x] Rust-local delivery confirmed possible via `contentRepositoryFactory`.
- [ ] User explicitly approves the final planning summary; then coordinator runs
      `task.py start`. No product content/code is written before that.

## Ordered work

1. **Snapshot scope** — record the exact Rust files this task will add/modify so
   the diff stays isolated from the 68+ pre-existing dirty changes. Do not revert
   or reformat unrelated work.
2. **Authored source of truth** — create `tool/rust_content/rust_topic.dart`
   (model + `RustRuntime` enum) and staged topic files organised by the 12
   domains in `research/curriculum-index.md`, aggregated in `rust_topics.dart`.
   **166 topics**, ordered `1..166`, each with
   objective/prerequisites/explain/code/output/pitfalls/tasks, a runtime label
   (`desktop`/`cargo`/`miri-candidate`/`external`) and an import
   representation (`single`/`cargo-multi`).
3. **Generator** — `tool/generate_rust_content.dart` validating the authored list
   (166, unique id/title/code, id order 1..166, multi-line code, no filler) and
   emitting `assets/content_rust/{tutorials,examples}.json` +
   `tool/rust_content/.last_run.json`. Never touches shared core.
4. **Verifier** — `tool/verify_rust_content.dart` cross-checking authored topics
   against emitted assets, distinct/duplication/single-line/placeholder checks,
   domain-coverage + runtime tally, and real compile/run diff where a toolchain
   exists. It runs **fixed** `rustc`/`cargo` argv (never a bundle `verify`
   string); skips are recorded, never counted as pass.
5. **Runtime integration** — `lib/rust_content_repository.dart` implementing
   `ContentRepository`; register `assets/content_rust/` in `pubspec.yaml`; set
   `contentRepositoryFactory: RustContentRepository.new` in `lib/main.dart`.
6. **Cargo-multi import** — extend `RustProjectStore.createProjectFromExample` to
   expand the example's `inputFixtures['cargoFiles']` bundle (validated, no
   overwrite, create-project branch only) per
   `research/import-representation.md`.
7. **Tests** — Rust-local tests:
   - content integrity: 166/166, uniqueness, non-triviality, schema fields,
     runtime labels, no placeholder markers;
   - repository loading + filtering by product;
   - import: single-file on all three branches; cargo-multi on the create branch;
     adversarial bundle rejection; editor/existing-project branches ignore a
     bundle (documented limitation);
   - page/navigation: `test/rust_content_pages_test.dart` at 390px/1280px for
     tutorials, examples, and a cargo-multi example.
8. **Verification runs** — scoped `dart format`/`dart analyze`, generators,
   verifier, and focused `flutter test`. Record any skipped toolchain checks
   accurately.
9. **Report** — files changed, counts, domain/label tallies, command results,
   executed vs skipped examples, and the honest import-scope limit.

## Validation commands

```text
python scripts/generate_rust_content.py
python scripts/verify_rust_content.py --report build/rust-content-verification.json
D:/ProgramFiles/flutter_ohos/bin/cache/dart-sdk/bin/dart.exe format --output=none --set-exit-if-changed <owned dart files>
D:/ProgramFiles/flutter_ohos/bin/cache/dart-sdk/bin/dart.exe analyze <owned dart files>
D:/ProgramFiles/flutter_ohos/bin/flutter.bat test --no-pub --reporter expanded <new rust content tests> test/rust_content_pages_test.dart
```

Real compiler/device tests are only claimed when a `rustc`/`cargo`/device is
actually present; otherwise they are reported as skipped.

## Risks / rollback points

- Pre-existing dirty worktree: keep changes additive and path-scoped; never reset
  or reformat unrelated files.
- If a shared-core change is ever found technically necessary, stop and specify
  the exact minimal file for coordinated apply; do not apply it here.
- Rollback = delete new Rust files/assets + revert the one `main.dart` profile
  field; the shared aggregate and other languages are never modified.

## Review checks

- Distinct title/summary/explain/code counts equal the entry counts.
- No single-line or `println!`-only lesson code; every lesson has objective,
  prerequisites, pitfalls and a solved exercise.
- Every example carries a runtime label consistent with the available runtime.
- Existing navigation and code-import behavior unchanged; single-file import
  still works everywhere and the cargo-multi limit is explicit.
- Chinese explanations retained; no placeholder markers remain.
- Verification distinguishes authored-asset checks, repository tests, and real
  compiler/device execution.

## Final delivery

All acceptance criteria are met by 166 substantive tutorial/example pairs,
332 real host compile/run passes, 23 offline Cargo workspace/all-target builds,
complete semantic review and final root Flutter140/8skip/0fail verification.
See ../10-15-rust-release-readiness/research/content-integration.md and
curriculum-verification.json for exact-source evidence. Mobile runtime claims
remain separate from this curriculum acceptance.
