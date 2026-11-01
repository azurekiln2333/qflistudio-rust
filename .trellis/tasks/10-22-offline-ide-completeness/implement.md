# Execution plan

## Planning gate

- [x] Read attachment, workflow, specs, audit and current worktree.
- [x] Preserve Rust-local R1-R10, link umbrella and receive user continuation.
- [x] Reconcile the separately numbered full umbrella R1-R13 (global535,
  2026-10-24); preserve explicit highlighting and all-product evidence gates.
- [x] Review PRD/design/plan and curate real manifests.
- [x] Validate and start task (active status is in_progress).

## Batches and exclusive ownership

1. Record baseline hashes/reports, device status and initial dirty paths.
2. Parallel A owns scripts/device catalog harness and dedicated tests;
   B owns Rust CodeAnalyzer and its tests; C owns direct Rust tools and tests;
   D owns native analysis/debug capability and catalog incompatibility research.
   Root alone integrates main.dart. No shared or sibling product writes.
3. Review and integrate profile hooks; meaningful focused tests. Implement real
   native analysis backend with ABI/build tests before claiming mobile analysis.
4. Consume shared owner content/highlighting/Problems/explorer/workspace delivery.
   Keep persistent simultaneous multi-root distinct from project switching.
5. Run every existing case on a matching OHOS package; fix all failures.
   Physical hardware requires a valid matching signature. A normal unsigned
   emulator install is acceptable only when its emulator identity, installer
   success and actual execution are independently recorded; never call it signed.
   Only after R1 passes add 180 substantive paired topics, then reverify all.
6. Independent full-scope review, capture specs, conventional scoped commits,
   normal push and exact remote results. All-product goal remains open until
   every original requirement has current sufficient evidence.

## Validation

- python scripts/generate_rust_content.py --check
- python -m unittest discover -s scripts -p test_rust_content.py
- python scripts/verify_rust_content.py --report build/offline-ide-audit/host-baseline.json
- New inventory/completeness/timeout/output verifier tests.
- dart format --output=none --set-exit-if-changed lib test integration_test
- dart analyze lib test integration_test
- Focused analyzer/tools/native regressions, then full root flutter test.
- Existing native packaging checks, final target build/audit, signed OHOS install
  and all-case execution. Check textual installer status as well as exit code.
- Exact owned diff/status review and commit/normal push verification.

## Gates and rollback

Device queue is Lua → SQL → Python → Rust following Web's explicit seq163
release of 127.0.0.1:5555. The target was disconnected at handoff; neither the
queue nor an old availability observation grants Rust a device mutation window.
Re-read the channel and require explicit handoff. OHOS acceptance remains open. Core APIs are
being implemented live: inspect current source before using them. Preserve
initial native/README.md and OHOS identity/signing/build edits. A timeout is not
proof a worker stopped: poll its confirmed live handle before reassignment.

### Current handoff recovery, 2026-10-24

Historical Go287 -> Rust205 -> C211 was consumed and must not be replayed.
Go528 confirms that history; actual C537 terminal/empty-Job release is to fresh
Go509, then Web510 by coordination. Rust explicitly deferred the historical
handoff in538 without starting any heavy process. Rust533 requests two fresh
windows (Native90s, Dart110s) after earlier ready peers and grants neither one.
Re-read the current channel immediately before accepting a new named handoff.

Replace the ignored direct-invocation wrapper before use. It has neither a total
bound nor descendant-empty proof. New execution must bind exact source hashes,
start Windows children suspended in an owned Job, reserve cleanup/publication
time, and verify all owned Jobs empty. Native execution also needs an exact
owned Linux process-group report; wsl.exe exit is insufficient. Missing endpoint
or unconfirmed cleanup means explicit defer/hold, never a pass or onward grant.
