# GitHub migration and cloud-only Rust workspace

## Goal

Preserve Rust source and portable Trellis progress on GitHub. Make the confirmed
E-drive clone the next working location. Run every build and test on GitHub.
Hand over verified state to its Codex coordinator through Herdr.

## Migration acceptance ruling — 2026-11-27 14:35

The coordinator ruling in
`D:/MyNewProjects/_orchestra/decisions/qflistudio-rust.md` narrows completion to
the workspace migration. The 2026-11-28 01:36 `core-ref-wave.md` ruling
supersedes the core-last hold and pins immutable `CORE_REF` to
`1ae4674a4b153701b0c3b3ff04b1a1b77a318611`. Make one pin-only commit, pass
the gate, renew target parity and acknowledgement, and record hosted CI.
Do not adopt another core SHA without a new brain-authorized wave. This pin
does not establish Rust product or SDK compatibility.

Hosted Dart formatting, Flutter analysis and the full root test suite remain
required evidence. The later 18:50 `ci-decoupled.md` ruling requires non-CI
migration steps to finish first. Write `migrated.json` after clean tracked
parity, committed agent rules, branch/backup/cleanup records and exact-SHA
receiver acknowledgement, with pending CI IDs allowed. One Pi watches CI.
For `done.json`, attach final-SHA evidence and triage: rerun infrastructure
failures once and fix repeated configuration failures; record defects proven
to exist at pre-migration GitHub main as follow-ups; fix migration-caused
path/core/lockfile/registrant failures and publish through the gate again.
Do not skip checks or relabel failures as success. A new SHA requires renewed
target comparison and acknowledgement.

Record the latest installer run, per-platform conclusion, artifact names and
signing state. Missing platform acceptance, SDK/native-hooks compatibility,
signing, device/UI execution, Android armv7 and receiver-hook diagnosis are
planning-only follow-ups in
[`11-27-rust-compatibility-followups`](../11-27-rust-compatibility-followups/prd.md).
Migration `done.json` must list those limits. It does not close product or
installer acceptance. This ruling supersedes earlier migration gates below.

## Initial audit facts and dependency context

- Source: `D:/MyNewProjects/qfli_rust`.
- Destination: `E:/MyNewProjects/QFLIProjects/qflistudio-rust`.
- User approved task creation and this destination on 2026-11-26.
- Initial source HEAD: `c999df6e75ce0626fe22db04a481a12035629ca0`.
- Initial GitHub/destination main: `540674ff95a83daa2848ee463f3c6aaf8986f6ff`.
- Initial origin fetched GitHub and pushed to GitHub, Gitee, GitLab, GitCode and CNB.
- All five advertised remote branch tips are ancestors of local main.
- Initially untracked work included `11-17-app-installers` and `tool/ci/ci_support.py`.
- Initial root ignore rules excluded specs, workflow, scripts, journals and agent helpers.
- At the initial audit only `.github/workflows/native-runtime.yml` existed.
  Application installer and quality workflows now have source implementation;
  their actual hosted validation remains pending. Native success never proves
  application installers.
- Core owner confirmed the editing folder `../qflistudio-core`.
  Dart package name remains `qfli_studio_core`. Checkout paths and overrides
  must agree. The external `patch_upstream_core.sh` is owned by qflistudio-next;
  its need in Rust depends on the final core/Flutter compatibility contract.
- Core migration and UI integration are concurrent. Final validated core SHA
  is pending owner handoff; `ee83f1c` is not the final integration pin.
- Herdr source coordinator is `w61:p1`; destination is `w6C:p1`.
  Source Pi researchers `w61:p2` through `w61:p5` confirmed gpt-6.1-sol.

## Requirements

- R1: Preserve authored source, configuration, build recipes, task history,
  research, project specs, portable agent rules and progress journals needed
  to resume on another computer.
- R2: Exclude compiled files, native/Flutter intermediates, tool caches, test
  outputs, session runtime state and credentials from source commits.
- R3: Inventory every configured endpoint and branch. Integrate unique reviewed
  work into main without discarding history. Record ancestry evidence.
- R4: GitHub is authoritative. Publish only through the orchestra push gate. The destination clone
  must have GitHub as its only remote endpoint.
- R5: Establish durable rules forbidding local builds, tests, dependency
  restoration, formatting tools, installer execution and artifact generation.
  Execute these on GitHub-hosted runners. Local Git, inventory and edits remain
  permitted. Do not run local pub get to repair a lockfile.
- R6: Record and triage hosted migration quality checks and Windows, Linux, macOS,
  iOS, Android and OHOS coverage: native inputs, intermediates, Flutter outputs,
  installers, checksums and provenance. Missing platform acceptance remains an
  explicit product follow-up rather than a migration-completion blocker.
- R7: Record signing and installation status exactly. An unsigned IPA/HAP is
  not evidence of a device-installable signed package. Inspect credential
  metadata only and expose signing prerequisites in workflows and handover.
- R8: Record real run IDs, app/core SHAs, per-job results, artifact retention and
  installer checks. Missing credentials and failed installer jobs remain explicit
  product follow-ups. Migration-caused quality failures must be repaired;
  never fabricate successful coverage.
- R9: Pull the preserved GitHub state into the destination and compare commit,
  Git tree, source files and portable Trellis content. Both worktrees must be
  clean. List ignored source-only paths in the cleanup inventory. Ignored local
  state is expected to differ and is not a tracked-parity condition.
- R10: Inventory obsolete build output and WSL storage. Do not delete or
  unregister anything. Preserve originals and shared ownership records.
  Any separately approved external relocation must retain verified copies.
- R11: Dispatch and communicate through Herdr. Prefer gpt-6.1-sol. Inspect/retry
  concurrency failures, compact/restart exhausted sessions, and fall back to
  deepseek-v4.1-flash only after recovery fails.
- R12: Hand over paths, commit, task map, cloud evidence, remaining blockers and
  cleanup inventory to destination Codex. Obtain its acknowledgement.

## Acceptance criteria

- [ ] A1 (R1-R4): GitHub contains all authored and portable progress files;
  an audited inventory explains excluded local file categories.
- [ ] A2 (R3): Every discovered branch tip is an ancestor of final main, or its
  unresolved integration is explicitly reported without claiming completion.
- [ ] A3 (R2,R5): No output/credential enters the outgoing commits. Shared agent
  rules route every build/test and dependency restore to GitHub.
- [ ] A4 (R6-R8): Six-platform cloud results record intermediate, installer,
  signing and validation status separately. Required hosted format, analysis
  and full root tests have final-SHA evidence and the 18:50 failure disposition;
  missing product
  acceptance remains listed in the planning-only follow-up and `done.json`.
- [ ] A5 (R4,R9): Source HEAD/tree, GitHub main and destination HEAD/tree agree.
  Both Git statuses are clean; destination remotes are GitHub-only.
- [ ] A6 (R10): Exact cleanup paths have ownership and preservation evidence.
  Ignored source-only paths and shared-storage holds are recorded. No deletion
  or WSL unregistration occurs.
- [ ] A7 (R11,R12): Destination Codex acknowledges the committed handover.

## Ownership and scope boundaries

This parent owns migration, portable progress, policy and integration directly.
Existing child tasks own native runtime and application installer workstreams.
Their prior progress must survive the migration. Their local-test instructions
are superseded by the user's cloud-only constraint.

Other products and shared core source remain with their owners. Coordinate
shared dependencies through Herdr. Global SDK/cache deletion and shared WSL
unregistration are not inferred from ownership of this repository. Store
publication and acquiring paid signing accounts remain outside this task.

## Execution prerequisites

- Execution was approved on 2026-11-27 through Claude w61:p6. The task is
  `in_progress`; no further planning-review approval is pending.
- Select immutable migration `CORE_REF` from the brain-authorized wave; do not
  represent it as a final production compatibility approval.
- Audit signing metadata; do not treat absent secrets as a completed installer.
- Retain shared WSL ownership information without destructive operations.

## Planning convergence

The confirmed paths, repository ownership, GitHub-only destination, cloud-only
execution and Herdr collaboration resolve the requested scope. Technical
prerequisites above remain explicit execution gates, not assumed successes.
This PRD has been consolidated against the design, implementation plan and
dated research record. The user approved the final plan and execution on
2026-11-27. Continue the existing `in_progress` task, not a new planning gate.

## Historical evidence boundary — 2026-11-27, before the 14:35 ruling

Rescue classification is complete: 119 source/evidence copies preserve
2,329,864 bytes. All 14 unreachable blobs are reconciled as 11 copies and three
exact index duplicates. Raw-byte corrective publication and receiving-clone
comparison remain separate evidence gates. Preserve original source and objects.

Cloud checks `45894657274` at
`a07511394cfc8a8079e226e37468c571b9d0ed1e` passed all four jobs. Each OS ran
291 native tests with platform-specific skips. Application helpers were
explicitly NOT RUN because those files were not in that commit. Native run
`45890222976` at `c859677d482ef358c5aed2efdad7e2daf9a6b288` passed shared guest
and all five mobile targets. Newer native run `45894657258` at `a075113` was
running at the recorded inspection; do not promote that state to success.

The final core SHA, approved SDK contract and Rust native-hooks recipe are not
available. Actual application quality, packaging, signing/device checks and
Android armv7 remain pending. Keep this parent and its children `in_progress`.
Source hook paths have been reviewed, but receiver hook execution remains
unresolved. The F2 service-tier warning is separate from the hook failure.

