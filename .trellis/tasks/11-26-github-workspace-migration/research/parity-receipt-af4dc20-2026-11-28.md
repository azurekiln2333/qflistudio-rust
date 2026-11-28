# af4dc20 parity receipt and closeout gaps - 2026-11-28

## Scope and evidence boundary

Worker `w61:p5` reviewed the existing migration task on `gpt-6.1-sol`, with
requested thinking level `max`. This worker owns only this new research file.
No model change, product edit, status-record write, Git mutation, CI query or
trigger, executable check, artifact download, cleanup or WSL command occurred.
Local operations were read-only source/Git inventories and coordination through
Herdr. The coordinator owns publication, receipt updates and final acceptance.

This is a **dated clean-snapshot receipt**, not a claim that the current source
worktree is clean. Source edits resumed after the measurements below. Adding
this research file also creates non-ignored untracked source content until the
coordinator reviews it.

## 1. Frozen clean tracked parity

Existing independent record:
`D:/MyNewProjects/_orchestra/status/qflistudio-rust.target-audit-af4dc20.json`.
Its `observed_at` is `2026-11-28T14:02:02.6684005+08:00`. It records both clones
clean, 875 tracked rows, zero tree-row differences, GitHub-only endpoints and
the committed parent agent rules. Its preservation statement inherits the
prior 119-copy/436-backup audits; it is not a fresh private-payload rehash.

This worker independently repeated the source/target Git measurements. The
complete clean parity and live-GitHub command finished at
`2026-11-28T12:43:10.147Z` (`20:43:10.147+08:00`), before p2's new edits.
The timestamp comes from this session's tool-result envelope, not a later
inference from file modification times.

| Item | Frozen result |
| --- | --- |
| Source | `D:/MyNewProjects/qfli_rust` |
| Target | `E:/MyNewProjects/QFLIProjects/qflistudio-rust` |
| Branch / upstream, both | `main` / `origin/main`, ahead 0, behind 0 |
| Source HEAD / target HEAD / live GitHub main | `af4dc20f1489217283ba613424036f7fdd4d1415` |
| Commit tree, both | `a95983ec81000ec128b2161bc877bd970d4b7c75` |
| Recursive tracked rows, both | 875 |
| Mode/blob/size/path row differences | 0, comparing `git ls-tree -r -l HEAD` |
| Full non-ignored status, both | Zero entries from `git status --porcelain --untracked-files=all` |
| Remote names, both | Only `origin` |
| Origin fetch and push, both | `https://github.com/azurekiln2333/qflistudio-rust.git` |
| Committed `AGENTS.md` blob, both | `d84c1f440511108c4d46c4e355424792f1d15792` |
| Tracked `.trellis` and `.agents/skills` paths, both | 483; included in the identical complete trees |
| Ignored collapsed inventory | Source 165 entries, target 1 entry |

The source and target `AGENTS.md` files were read. The identical committed blob
contains the cloud-only execution policy and shared product workspace rules.
Ignored-file inventories are intentionally separate from tracked parity. The
target's sole collapsed ignored entry was
`.trellis/scripts/common/__pycache__/`. Source-only categories are listed in
`cleanup-plan-2026-11-27.md`; no ignored content was deleted or copied.

### Later worktree observation: do not extend the clean claim

At `2026-11-28T20:50:53.0646833+08:00`, source HEAD/tree still identified
`af4dc20` / `a95983ec`, but porcelain v2 reported an unstaged modification to
`test/rust_workspace_integration_test.dart`. The coordinator assigned p2 the
two whitespace edits. At `20:50:53.1308647+08:00`, the target still measured
clean at the same commit/tree. This worker did not edit or discard p2's file.
These observations do not certify either worktree's state after that time.

## 2. Gate and exact receiver ACK recovered

The read-only gate receipt is
`D:/MyNewProjects/_orchestra/push/qflistudio-rust.result.json`:

- Commit: `af4dc20f1489217283ba613424036f7fdd4d1415`.
- Previous GitHub main: `8b92ddc98151a394a57a5d5ce3eb0bea35f2266e`.
- `checked_at`: `2026-11-28 13:42:23` (coordinator records use +08:00).
- `ok=true`, `push_rc=0`, `allowed=[]`, `problems=[]`, `warnings=[]`.
- The later independent `git ls-remote --heads origin` advertised only `main`
  at the same full SHA. No fetch or push was performed by this worker.

The actual historical ACK was recovered from the known receiver and source
session text. It is not merely the coordinator's request for an ACK.

| Local-only evidence location | Exact event |
| --- | --- |
| Receiver transcript `C:/Users/lichengyu/.codex/sessions/2026/11/27/rollout-2026-11-27T19-23-59-01a21cbf-77a7-7eb2-b771-7be7d2ec0193.jsonl`, 1-based lines 305-306 | ACK command at `2026-11-28T05:48:16.248Z`; command completion at `05:48:17.211Z`, exit 0, Herdr `type=agent_prompted` to `w61:p1` |
| Source transcript `C:/Users/lichengyu/.codex/sessions/2026/11/26/rollout-2026-11-26T03-19-24-01a21426-0067-7c50-b13d-2c01ec5ebab3.jsonl`, 1-based line 7072 | Received user-message text at `2026-11-28T05:48:18.812Z` (`13:48:18.812+08:00`) |

The exact ACK text is preserved below. Only this narrow coordination evidence
is reproduced. The runtime transcripts remain local and must not be committed.

> ACK to w61:p1 from destination w6C:p1. Active task: .trellis/tasks/11-26-github-workspace-migration. Independently measured read-only target E:/MyNewProjects/QFLIProjects/qflistudio-rust after the af4dc20f1489217283ba613424036f7fdd4d1415 gate: local HEAD and live GitHub refs/heads/main both equal af4dc20f1489217283ba613424036f7fdd4d1415; exact tree is a95983ec81000ec128b2161bc877bd970d4b7c75. git status --porcelain --untracked-files=all exited 0 with empty output: target tracked files and non-ignored untracked status CLEAN. Origin fetch and push are both https://github.com/azurekiln2333/qflistudio-rust.git; GitHub-only endpoints CONFIRMED. Committed AGENTS.md blob d84c1f440511108c4d46c4e355424792f1d15792 contains the parent Shared QFLI product workspace rules and cloud-only execution policy. This is exact-SHA handover acknowledgement only. Quality acceptance remains pending and separate; no ownership transfer or full acceptance claim. Ignored files, CI results, hook operation, signing/device validation and installer acceptance are not asserted. No repository edits, Git writes, builds, tests, restores, downloads, hooks or CI polling performed.

Historical ACK recovery is therefore closed for `af4dc20`. Attaching it to the
coordinator-owned migration receipt remains necessary. A different published
SHA requires a new comparison and exact-SHA ACK; this ACK is not transferable.

## 3. Branches, worktrees, stashes and baselines

Read-only inventories found one registered worktree per clone: the source root
and target root above. Each clone had only local branch `main`. The target
stash list was empty. The source retained both preservation stashes:

| Reference at inspection | Immutable stash object | First-parent base | External preservation |
| --- | --- | --- | --- |
| `stash@{0}` | `5b675c98280aa7696e6c04e7d54ef32fd053bf7f` | `68723d029dfd9dae8ea91c97b8a26848f116e8cd` | `_migration-backup/qflistudio-rust-20261127/core-wave2-deferred-20261128-053557/manifest.json`, 14 recorded files |
| `stash@{1}` | `707464f2c45af4195873e42c3c53f1972a253f78` | `dde374cdcdbca4ee0f093b5b62261a65da32d125` | `_migration-backup/qflistudio-rust-20261127/core-wave-deferred-20261128/manifest.json`, 3 recorded files |

The external roots above are under `D:/MyNewProjects/`. Both manifest files and
backup directories were inspected as text/metadata only. No private payload was
rehash-verified in this review. The wave-2 external manifest labels its frozen
source `f5ac2ee6195995ce6f4def865948540aef5a8ce8`; that label is distinct from
the stash object's actual first-parent base `68723d0`. Preserve both identities
rather than silently rewriting one to match the other. No stash was applied,
popped, dropped or treated as redundant merely because repairs were restored.

Recorded mirror tips were rechecked against source `af4dc20`:

- Gitee/GitCode/CNB: `b8a69a8df4f9fe81641aa8916b8a10884863813b`.
- GitLab: `553e13928bb4c9af3d1cccf615053c81bca91af5`.
- Both `git merge-base --is-ancestor <tip> HEAD` queries exited 0.

This rechecks the recorded objects, not current mirror advertisements. There
was no mirror fetch, push, merge or deletion. Historical non-GitHub push-URL
wording in `branch-disposition-2026-11-27.md` is superseded by the measured
GitHub-only endpoints, not an instruction to restore mirrors.

| Baseline / handover identity | Meaning and limit |
| --- | --- |
| `540674ff95a83daa2848ee463f3c6aaf8986f6ff`, tree `01972c762445987f9e214ed0811b4fa6df090b3c` | Initial pre-migration GitHub/target baseline. Prior identical application blobs do not establish equivalent executed SDK/dependency quality results. |
| `c999df6e75ce0626fe22db04a481a12035629ca0`, tree `faf5fdb7322da6dc3d6b1cbc825a90288478bc64` | Initial source/rescue baseline; retain original Git objects and source evidence. |
| `68723d029dfd9dae8ea91c97b8a26848f116e8cd`, tree `a31888adb3b83fe71c2b94a73fe8dd03ad87a70a` | Published second core pin-only wave; its clean handover predates restored repair work. |
| `8b92ddc98151a394a57a5d5ce3eb0bea35f2266e`, tree `dd97539d93904ab93c46d5a3af90e95b2b2f9138` | Prior clean handover still named by the main migrated receipt at review. Not the final `af4dc20` receipt. |

Approved core remains `8e031313ffc8d531c5a6b4d131f721f35da04c86` in both
Rust application workflows. SDK contract remains
`flutter-oh-3.41.10-ohos-1.0.1@adaf911c35c9136a7d18fc424d714c9ec7724e60`.
No new core wave or production/native-hooks approval is inferred.

## 4. Preservation and retirement holds

The prior branch/backup audit is
`D:/MyNewProjects/_orchestra/status/qflistudio-rust.branch-backup-audit.json`.
Cleanup dispositions are in `qflistudio-rust.cleanup-audit.json` and this task's
`research/cleanup-plan-2026-11-27.md`.

- The portable rescue ledger preserves 119 exact copies, 2,329,864 bytes.
  All 14 original unreachable blobs are reconciled as 11 copies and 3 exact
  index duplicates. Manifest SHA-256 is
  `9521f09701b5aebc749b6329b8ba1ccd311057d9a9c18310a9ca2f77cf872e84`.
- The selected external backup records 589 entries: 436 copied files totaling
  11,575,677 bytes and 153 exclusions (138 extension/binary, 15 secret-shape).
  Earlier audits recorded 436 matching sizes/hashes. This is not a complete
  ignored/private/generated backup or a comprehensive secret audit.
- Git-object comparison from `8b92ddc` to `af4dc20` found no delta in the
  rescue subtree, cleanup plan, rescue report, `AGENTS.md`, `native`, `scripts`
  or native-runtime workflow. That supports retaining the prior ledgers; it
  does not freshly verify private originals, stashes or backup payload bytes.
- Preserve source `.git`, both stashes, authored `build/content-author-scratch`
  and `build/offline-ide-audit`, `native/build/.patchwork`, raw logs, held
  package/native outputs, generated Miri assets, local state and all external
  backup copies. Do not run rescued helpers or apply archived patches.
- Preserve reparse targets, SDK/Pub junction targets and shared storage. The
  historical 15-link inventory is not a current traversal or removal permit.
- Historical WSL names are `Ubuntu`, `qfli-terminal-test`,
  `qfli-terminal-al3-clean`, `qfli-terminal-al3-test` and `qfli-java-build`.
  Their registered locations are outside both Rust roots. All-consumer owner
  release and independent preservation remain unresolved. No WSL command or
  current distribution-state claim is made here.

**Retirement disposition: NOT SAFE to retire or remove the old source under
this assignment.** Active source writers, preserved local stashes/state and
shared-storage holds remain. The recovered ACK explicitly grants no ownership
transfer. No final Rust `cleanup-check.md`/SAFE record was present in the
reviewed orchestra status inventory. That is a separate retirement boundary,
not a reason to withhold a truthful tracked migration receipt.

`D:/MyNewProjects/_orchestra/CLEANUP.md` is a future procedure with separate
user/owner decisions. It does not authorize this worker to close panes, remove
worktrees, relocate/delete source, prune Git objects or unregister WSL.
Migration completion never removes these holds.

## 5. Concrete closeout gaps and coordinator actions

### A. Refresh the historical migration receipt without falsifying current state

At review, `D:/MyNewProjects/_orchestra/status/qflistudio-rust.migrated.json`
still names `8b92ddc`, tree `dd97539d`, 874 rows and the old ACK. Its
`pending_candidate` and `post_receipt_state` still say the `af4dc20` gate is
pending. Preserve the older receipt as history, then attach the actual gate,
875-row clean snapshot and recovered `af4dc20` ACK. Record subsequent source
edits separately. Do not replace the dated snapshot with a current-clean claim.
No CI wait is required for this non-CI receipt correction.

### B. Freeze the sole watcher's exact-SHA evidence and finish the format repair

The saved `qflistudio-rust.ci-watch.json` read in this review was last updated
at `09:42:28+08:00`; it still said `af4dc20_gate_pending_no_candidate_ci_query`.
It therefore cannot serve as the final `af4dc20` CI receipt. Worker p4 owns its
update and the durable exact-SHA cloud report; this worker made no CI query.

The coordinator's persisted `20:49:30+08:00` progress entry and p4's terminal
handoff report the following later observations, not independent CI findings
by this worker:

| Exact `af4dc20` workflow | Reported state requiring p4's durable evidence |
| --- | --- |
| Cloud checks `46113314638` | Four jobs passed. |
| Application quality `46113314596` | Helper job `140881457449` passed. Main job `140881457317` failed formatting plus derived finalization; analysis passed. Full root result: completed 354, passed 334, skipped 20, failed 0, protocolDone true, success true. |
| App installers `46113314581` | Six of seven platform jobs passed. iOS failed on `hashlib.file_digest`; installer-named iOS reports are not a successful IPA. |

Do not carry the older `8b92ddc` six root failures into the `af4dc20` result.
Conversely, the reported passing root protocol does not erase the failed
format stage or turn skipped native/device checks into execution evidence.
P2 owns the exact two whitespace hunks in
`test/rust_workspace_integration_test.dart`. Review them against the hosted
formatter preview, then obtain real formatting evidence at the new revision.

The iOS follow-up remains explicit. Generic Development Team advice does not
establish the cause. P3 owns the read-only interpreter proposal. If a later
repair changes `scripts` or another native producer input, re-evaluate exact
producer Git-object compatibility before reusing an older runtime archive;
unchanged artifact names are insufficient. Missing installer acceptance may
remain a named product follow-up under the ruling, not a fabricated pass.

### C. Renew all revision-specific gates after the next publication

The coordinator must review completed owned edits, keep origin fetch/push
GitHub-only and publish only through the orchestration push gate. A new SHA
supersedes this receipt as the final-revision parity evidence. Measure target
status before an authorized ff-only update, preserve any changes, then compare
source/GitHub/target SHA, tree and tracked modes/blobs. Obtain the new exact-SHA
receiver ACK. Include this research/evidence file in the reviewed publication
plan so a later documentation commit does not silently change the final SHA.

The sole watcher must bind final-SHA Cloud/helper results, actual Dart format,
Flutter analysis and the complete root protocol to the immutable core/SDK and
producer inputs. Preserve actual failures/skips, artifact names/digests/expiry
and per-platform signing states. Read-only source identity at the
pre-migration baseline is not an executed failure waiver. No blind rerun or
new trigger is authorized by this report.

### D. Write migration closeout only with its real limits

No `qflistudio-rust.done.json` was present in the reviewed inventory. Write it
only after the final-SHA receipt and required hosted quality disposition are
complete. Keep latest installer evidence separate from product acceptance.
List SDK/native-hooks compatibility, iOS/missing installer acceptance,
production signing, device/UI, Android armv7 and receiver-hook command/stderr
execution evidence under planning-only `11-27-rust-compatibility-followups`.
Do not close the native/installer product tasks or approve old-workspace
retirement merely because the migration is complete.

This file is a source-text/Git-metadata receipt only. All executable validation
remains on GitHub-hosted runners under the existing cloud-only policy.
