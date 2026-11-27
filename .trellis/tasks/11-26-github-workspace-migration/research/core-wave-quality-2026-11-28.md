# Core wave and consumer quality evidence

## First wave: published and measured

Rust `f5ac2ee6195995ce6f4def865948540aef5a8ce8` pinned core
`1ae4674a4b153701b0c3b3ff04b1a1b77a318611`. The orchestra gate passed on
2026-11-28 at 03:04:43 +08 with no warnings or problems. Source and target
measured clean at tree `a9b27bdcdbff1af5947bb1b39f2256ec31686637`, with 870
identical tracked rows and GitHub-only endpoints. Target `w6C:p1` independently
acknowledged that exact SHA. These measurements precede subsequent source edits.

Cloud checks `46054107126` passed all four jobs. Linux logs record 291 native
helper tests and 137 application helper tests. Application quality `46054107056`
passed its helper job, strict preparation and analysis. Formatting reported two
changed files: `rust_code_analyzer_test.dart` and
`rust_workspace_integration_test.dart`. The root test process failed.

The visible test events show Cargo expected `1.98.1` but returned `1.100.0`,
plus two `compilerPath!` null errors. The public log starts inside an earlier
error at terminal test line 159. Neither that event's expected/actual values
nor drawer-test outcomes can be reconstructed from the bounded tail. Earlier
preparation independently recorded system rustc and Cargo `1.100.0`; that is
tool provenance, not the missing test event.

App installers `46054107087` passed Android, Windows, Linux, OHOS and both
macOS targets. iOS job `140692553596` failed in Embed Rust Runtime at
`scripts/miri_build_support.py:41`: `hashlib.file_digest` was unavailable.
The workflow's Python 3.13 declaration does not identify the interpreter
selected by Xcode's bare `python3` invocation. Generic Development Team advice
is secondary and does not establish a signing failure. iOS packaging was
skipped; its uploaded artifact contains failure reports, not an accepted IPA.

The run published seven installer-named artifacts and six intermediate artifacts.
The sole watcher retained their IDs, sizes, GitHub archive digests and expiry in
`D:/MyNewProjects/_orchestra/status/qflistudio-rust.ci-watch.json` under
`core_ref_wave_watch`. Android uses a testing/debug key, Windows is unsigned,
OHOS is unsigned, and macOS signing is ad hoc without notarization. No device,
UI, Android armv7 or native-hooks acceptance follows from these jobs. The native
producer was earlier successful run `45894657258`, not a new native run at this
consumer SHA. There was no infrastructure-only failed job and no rerun.

## Source diagnosis and repair boundary

The terminal version and null assertions predate migration, but the new Linux
quality workflow uses system tools rather than the Windows bundle assumed by
the fixture. No equivalent pre-migration execution proves an exemption. The
fixture repair retains real command claims, exit/output checks, exact bundled
version checks and all Windows GNU flag assertions. System-tool output must
contain a valid version. Non-Windows explicitly tests the helper's empty result.

Both formatter targets changed during migration. Old blob-identity evidence
through `f990471` cannot waive the later changed source. A manual call reflow is
included; hosted formatting remains required. Bounded formatter previews and
redacted machine summaries provide actionable public diagnostics while the
original required check failure remains authoritative.

The prior three-file follow-up was preserved in Git stash
`707464f2c45af4195873e42c3c53f1972a253f78` and exact-byte external backup
`D:/MyNewProjects/_migration-backup/qflistudio-rust-20261127/core-wave-deferred-20261128/`.
Its two research reports are restored unchanged. The reviewed fixture repair
extends the preserved patch; no stash or original backup was deleted.

## Second wave and remaining evidence

The 2026-11-28 03:30 ruling authorized core
`8e031313ffc8d531c5a6b4d131f721f35da04c86` and initially permitted its pin to
join the reviewed CI repair. The brain later required pin-only publication,
as recorded below. The immutable consumer-fixes and OHOS native ABI contracts
were read. Rust uses the OHOS fork on every job and already passed strict OHOS
arm64 packaging; no official-Flutter shim or speculative ABI filter is added.
The SDK stays `3.41.10-ohos-1.0.1` at
`adaf911c35c9136a7d18fc424d714c9ec7724e60`.

New source and regression coverage remain unexecuted until the next gated SHA.
Required sequence: source review, commit, gate PASS, target fast-forward,
clean tracked parity, fresh receiver ACK and exact-SHA hosted evidence.
Application quality is still open. iOS interpreter compatibility and missing
product acceptance remain named follow-ups. No local formatter, analyzer,
test, syntax check, build, restore or artifact download was run.

## Second-wave publication and latest hosted evidence — 2026-11-28

Pin-only consumer commit `68723d029dfd9dae8ea91c97b8a26848f116e8cd` changed
only the two workflow `CORE_REF` values to
`8e031313ffc8d531c5a6b4d131f721f35da04c86`. The orchestra gate passed at
05:44:37 +08 with no warnings or problems. Source, live GitHub main and target
measured at the same commit and tree
`a31888adb3b83fe71c2b94a73fe8dd03ad87a70a`, with 870 identical tracked rows,
clean worktrees and GitHub-only endpoints. Destination `w6C:p1` supplied a
fresh exact-SHA acknowledgement. These measurements preceded restoration of
the deferred quality repairs. Restoration made the source dirty at that recorded point; this snapshot does not prove
current source cleanliness or current source-to-target parity. The separate
repair publication requires a new gate, parity measurement and receiver ACK.

Cloud checks `46072255988` passed all four jobs. Application quality
`46072256145` passed helper contracts, strict preparation and analysis.
Formatting still reported two files. The root suite failed the drawer case:
the visible diagnostic recorded `drawerOpen=false` and zero for every reported
row count. Earlier terminal-test events were omitted from the bounded public
tail, so that omission proves neither terminal-test success nor failure. These
observations do not establish that the core bump caused the failures.

Final App installers run `46072256031` failed overall. All three orchestration
jobs and six of seven platform jobs passed: Android, Windows, Linux, OHOS and
both macOS targets. iOS job `140751856837` failed at
2026-11-27T21:56:54.1626360Z with the same unavailable `hashlib.file_digest`
API. Its uploaded artifact contains failure reports, not an accepted IPA.
The sole watcher retained 13 artifact metadata records under
`core_ref_wave_watch` in
`D:/MyNewProjects/_orchestra/status/qflistudio-rust.ci-watch.json`.
No workflow rerun occurred, and no infrastructure waiver was applied.

The SDK remains Flutter-OH `3.41.10-ohos-1.0.1` at
`adaf911c35c9136a7d18fc424d714c9ec7724e60`. Published pin evidence does not
execute the restored repairs or establish application quality or product
acceptance. Signing, device/UI, Android armv7, native-hooks and receiver-hook
acceptance remain separate. This documentation update used supplied frozen
watcher evidence and read-only source records; it ran no check, CI query, build,
test, formatter, analyzer, restore, artifact download or Git write.

## Separately reviewed repair candidate

The terminal fixture now distinguishes a selected Windows bundle's exact
`1.98.1` from a real system tool's semantic-version output. Non-Windows linker
fallback asserts the empty result and Cargo-config checks use the host
environment when no bundle is selected. Process and output assertions remain.

The drawer fixture's existing close wait now also requires one hit-testable
reopen control. The helper asserts that control before tapping once when the
explorer is not already visible. The 200-attempt budget, later pump and all
root/nested expansion assertions remain unchanged. This fixes a source-level
readiness gap; it is not proof of the hosted failure's cause or a passing test.

Formatter previews use bounded private-file capture instead of a pipe reader.
Independent review closed the cleanup-hang and read-error findings in source.
Redacted derived root summaries expose failures outside the raw console tail.
The current analyzer test still needs the exact hosted formatting preview.
All revised helpers and Dart fixtures require a new gated hosted run.
