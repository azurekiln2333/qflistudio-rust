# Takeover repair and publication boundary — 2026-11-28

The coordinator resumed the existing approved migration task at published
`af4dc20f1489217283ba613424036f7fdd4d1415`. No new task or planning approval
was required. All executable validation remains GitHub-hosted.

## Reviewed repair

- P2 applied only the two formatter preview wraps to
  `test/rust_workspace_integration_test.dart`. P5 independently confirmed
  unchanged strings, callbacks, assertions and pump budgets.
- P3 bound iOS `FLUTTER_XCODE_PATH` to the resolved running Python directory
  followed by the runner PATH. The existing Flutter pass-through supplies an
  individual `PATH=...` argument to Xcode. P2 independently reviewed this and
  the regression. No blocking source finding remained.
- `--no-codesign`, `--verbose`, release plugin generation, core/vendor/lock
  checks and other platform commands remain intact. This is a source review,
  not a hosted pass for the new revision.

The immutable SDK is `adaf911c35c9136a7d18fc424d714c9ec7724e60`.
Its `packages/flutter_tools/lib/src/ios/xcodeproj.dart:347-365` maps
`FLUTTER_XCODE_*` keys to Xcode build settings. Its `ios/mac.dart:524` adds
them and lines 744-748 execute the argument list. Apple Run Script build
phases receive command-line build settings in their environment.
The existing `ios/Runner.xcodeproj/project.pbxproj:229-240` invokes
`scripts/embed_miri_frameworks.sh`, whose line 4 executes bare `python3`.

Observed installer failure: run `46113314581`, job `140881573041`,
`2026-11-28T05:52:35.0124870Z`, embedding calls `hashlib.file_digest` and
raises `AttributeError`. Outer setup-python reports 3.13.15. The phase's own
interpreter path/version was not printed. An older interpreter is inferred;
the missing API is measured. Generic Development Team advice does not change
that diagnosis or authorize signing claims.

Runtime provenance inputs remain:

| Git object | Identity |
| --- | --- |
| `scripts` tree | `42c9ee7a3c51ef884a168ad2f6bd8e7abf3f0de6` |
| `native` tree | `1d110a450f2145a41a10d78744b63758a74176ea` |
| `.github/workflows/native-runtime.yml` blob | `2b8f84117cdb8128cecf5afa3c8b07bce205fba5` |
| Approved core | `8e031313ffc8d531c5a6b4d131f721f35da04c86` |

## Receipt and acceptance

The recovered historical ACK and dated clean source/target parity are in
`parity-receipt-af4dc20-2026-11-28.md`. The receiver repeated target-only
measurements at 21:04:12 +08:00, then reconfirmed GitHub-only fetch/push at
21:16:24. It found clean `af4dc20`, tree
`a95983ec81000ec128b2161bc877bd970d4b7c75`, 875 rows and zero differences
against the immutable source commit. It explicitly excluded CI/product
acceptance and current source cleanliness after repairs began.

The coordinator archived the old `8b92ddc` migrated receipt and refreshed
`D:/MyNewProjects/_orchestra/status/qflistudio-rust.migrated.json` with the
`af4dc20` gate, parity, ACK and real CI outcomes. The receipt separately records
the later dirty repair state. Current orchestration receiver is `w65:pD`;
the requested old `w65:pC` no longer exists. That routing change was confirmed
by the takeover operator.

The repair publication requires an exact-SHA gate request, a matching PASS,
fresh target comparison and ACK, plus final-SHA hosted quality evidence.
The sole watcher records installer outcomes without claiming unsigned outputs,
native skips or reports-only artifacts as device/product acceptance.
Planning-only `11-27-rust-compatibility-followups` retains SDK/native-hooks,
signing, device/UI, armv7, receiver-hook and missing installer acceptance.

No local checks, builds, dependency restore/install, artifact downloads, WSL,
direct push, scheduler restart, stash mutation or cleanup occurred. Both
preservation stashes, baselines, originals, backups and ignored state remain
held. Migration completion does not authorize source retirement.
