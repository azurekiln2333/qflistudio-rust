# Implementation plan

## Approval gate

- [x] User approved task creation and confirmed plural target root.
- [x] Four Herdr Pi researchers completed read-only audits on gpt-6.1-sol.
- [x] Destination Codex acknowledged staging and the cloud-only rule.
- [x] Independent Pi planning review found no material issue; context manifests
  reference existing research/spec files.
- [x] User reviewed the final plan and authorized transition to execution on
  2026-11-27 through Claude w61:p6.
- [x] Start the applicable task with task.py after the review gate.

## Current migration ruling — 2026-11-27 14:35

Apply `D:/MyNewProjects/_orchestra/decisions/qflistudio-rust.md` under the user's
approval. Pin live core `main` as immutable `CORE_REF`, currently
`476a30acee21dc486ee2849dd8064a7be665e4d5`. The later 17:00 core-last ruling
holds this pin until the brain starts the final-core consumer bump wave.
The exact SDK recipe remains fixed. This does not assert final product or
Rust native-hooks compatibility. Required hosted format, analysis and full root
tests retain exact revision and genuine outcomes under the later 18:50 ruling.

Apply `D:/MyNewProjects/_orchestra/decisions/ci-decoupled.md`: run steps 10-12
in parallel with CI, using Pis for target/AGENTS review, branch/backup review,
cleanup records and one CI watcher. The coordinator owns Git writes. Write
`migrated.json` as soon as non-CI parity and exact-SHA handover are complete.
Add final-SHA CI evidence to produce `done.json`: rerun infrastructure failures
once, fix repeated configuration failures, document proven pre-migration
defects as follow-ups, and fix migration-caused failures through another gate.
This ordering supersedes any sequential CI wait in the steps below.

Create and retain the independent planning-only
[`11-27-rust-compatibility-followups`](../11-27-rust-compatibility-followups/prd.md).
It owns SDK/native-hooks, signing, device/UI, armv7, receiver hooks and missing
installer acceptance. List them in migration `done.json` notes without closing
the child product tasks. Ignored source-only paths belong in the cleanup
inventory; they need not match the target. No deletion is authorized.

## Ordered execution

1. Capture a fresh source/target status and all remote advertised heads.
   Preserve concurrent edits and the original object store. Record ownership.
2. Restore portable Trellis/agent source visibility and review candidate files
   for source completeness and sensitive content. Classify ignored authored
   files, generated evidence, packages, source copies and unreachable blobs.
3. Add durable cloud-only rules to AGENTS/specs and update older local-test
   instructions. Preserve historical task results without inventing completion.
4. Review source/progress preservation. Before publication, the coordinator must
   verify that the source `origin` fetch and push URLs both name GitHub because
   the orchestration gate selects `origin`. Request publication only through
   that gate; do not run direct `git push`. Verify the gate result and advertised
   GitHub SHA before continuing.
5. Prepare CI helper, package and check workflows in disjoint worker ownership.
   Use the existing app-installer and native-runtime child tasks.
6. Read live core GitHub `main` and pin its full SHA as `CORE_REF`. Align Rust
   pubspec, lockfile paths, checkout layout and vendor override. Keep SDK identity
   checks. Final production compatibility is a follow-up. Do not run pub get locally.
7. Complete native and application workflows. Include bounded intermediate
   artifacts, installer/checksum/provenance outputs and cloud checks.
   Preserve explicit Android armv7 and signing prerequisites.
8. Use GitHub to run migration format, analysis and full root tests. One Pi
   observes logs and applies the 18:50 triage while target steps continue.
   Fix migration-caused source failures and republish through a new gate commit.
   If a failure is solely an unreleased core change, record it and pin the last
   passing core SHA. Record the latest installer run/outcome/artifacts/signing
   for each platform; missing product acceptance remains a named follow-up.
   Do not download large build artifacts to either local workspace.
9. Persist run evidence and accurate task progress. The coordinator reviews
   and commits source changes, then requests publication only through the
   orchestration gate after verifying source `origin` is GitHub-only. Verify
   the gate result and recheck discovered tips and final main ancestry.
10. Measure target status before updating it. If it is clean, pull from its
    GitHub-only origin with ff-only. If it has changes, preserve and review them
    before proceeding. Compare source/GitHub/target commit, tree, blobs/modes and
    portable progress without claiming parity before the comparison completes.
11. Finalize the exact cleanup inventory only. Do not delete files, old source,
    Git objects or shared storage, and do not unregister WSL. Relocation to the
    approved external backup is permitted without deleting originals. Record
    candidate paths and unresolved ownership or preservation evidence.
12. Commit handover evidence as needed, repeat target pull/comparison, and send
    final handover through Herdr. Obtain receiving Codex acknowledgement.
    Write `migrated.json` without waiting for CI, then `done.json` with final-SHA
    evidence and triage. List all product follow-ups. Refresh both files and
    exact-SHA acknowledgement after any later corrective publication.

## Worker ownership during execution

Execution approval is recorded above. Refresh exact ownership before writes:
- Worker A / w61:p2 current docs-only scope:
  `.trellis/spec/backend/github-app-builds.md` (new),
  `.trellis/spec/backend/github-native-builds.md`,
  `.trellis/spec/backend/index.md`,
  `.trellis/spec/guides/cloud-only-workspace.md`, and this parent's
  `prd.md`/`implement.md`. Earlier portability work is historical scope, not
  current permission to modify AGENTS, ignore rules or research.
- Worker B / w61:p3: tool/ci/ci_support.py, app_build.py,
  .github/workflows/app-installers.yml and orchestration helper tests.
- Worker C / w61:p4: tool/ci/package_installer.py, windows_installer.iss,
  test_package_installer.py and installer-contract notes.
- Worker D / w61:p5: scripts/ci_native_runtime.py,
  scripts/test_ci_native_runtime.py, native-runtime.yml when required,
  native task research, plus read-only review of A's changes.
The coordinator retains final task/spec integration, cross-review, Git writes,
target update and handover. A's explicitly delegated parent-doc edits are
limited to the two files listed above. Refine exact file ownership before each
dispatch; workers must preserve other edits and never commit.

## Historical execution record — 2026-11-27, before the 14:35 ruling

The user confirmed execution after the final planning review. Task start
succeeded and all four existing Pi workers received scoped implementation
through Herdr. Claude w61:p6 monitors without file or Git writes.

The native fix verifies both the copied runtime package and Android JNI library
copy against the manifest. Cloud checks `45894657274` at
`a07511394cfc8a8079e226e37468c571b9d0ed1e` passed all four jobs. Each OS ran
291 native tests, with Windows skipping one and Linux/macOS skipping three.
The JNI-only corruption regression passed. Source/workflow/portability policy
and controlled-Chinese checks passed. Application helper coverage was explicitly
NOT RUN because the application files were not part of that commit.

Native runtime `45890222976` at
`c859677d482ef358c5aed2efdad7e2daf9a6b288` passed shared guest and all five
mobile target jobs: Android arm64/x64, OHOS arm64/x64 and iOS arm64. At the
recorded inspection newer run `45894657258` at `a075113` had a successful guest
and five running targets. Preserve that dated state until the coordinator
records newer hosted evidence. App runtime selection still requires exact
native/scripts/workflow Git-object compatibility, not merely an older green run.
Android armv7 remains an explicit unmet requirement across compiler, ELF32,
host/ABI selection, Gradle and Dart loader layers. Do not count two APKs as three.

B and C share the canonical output directory and reports/packages.json contract.
Packaging leaves overall manifest status incomplete until finalization verifies
the complete package set. OHOS uses its source bundle ID com.azurekiln.qfli.rust.
The generic Android/Apple identity must not overwrite it.

Core's final migration SHA, validated SDK contract and Rust native-hooks recipe
remain external gates. No provisional core SHA is an approved production pin.
Independent cloud helper/native checks should run without that app dependency.

Rescue classification is complete: 119 preserved copies, 2,329,864 bytes and all
14 unreachable blobs reconciled (11 copies, three exact index duplicates).
Raw-byte corrective publication and target comparison remain separate gates.
Do not disturb the coordinator's correction or delete the original object store.
Source hook paths have been reviewed. Receiver hook execution remains unresolved:
its exit-code-1 transcript lacks command/stderr. The F2 service-tier/model warning
is separate and is not a hook diagnosis.

Worker A applied `trellis-update-spec` to the assigned documentation. The new
seven-section application contract records command/environment/schema behavior,
final core/SDK gates, producer-byte provenance, typed Hvigor Boolean no-sign,
exact packaging-input bytes, installer/quality reports, failure matrices and
required regressions. Native contracts now cover both library copies, selected
absolute aliases and raw topic-byte fixtures. This is source-only review, not
an application validation pass. Finalizer publication/checksum-failure cleanup
and quality-specific failure handling still require owner handoff/review and
hosted regression evidence. No local executable check or Git write was run by A.
Actual application quality/packaging, signing, devices and Android armv7 remain
pending. Parent/native/installer task status remains `in_progress`.

## Allowed local verification

Read-only git status/diff/ls-files/check-ignore/ls-remote/merge-base queries,
file inventories, Git blob comparisons, safe secret-presence scans and gh API
metadata/log inspection. Trellis task/context management is planning metadata,
not a product build/test. Use PYTHONDONTWRITEBYTECODE=1 for such Python commands.

No local Flutter/Cargo/native build, test command, analyzer, formatter, pub get,
dependency restoration, installer execution or artifact download is permitted.

## Required cloud verification

- Workflow/action pin and syntax checks.
- Helper regression tests for archive confinement, provenance and failure paths.
- Dart formatting/analysis and root Flutter tests.
- Applicable native compiler/adapter/package regressions.
- Controlled Chinese: python scripts/ste-lint-zh.py <changed Chinese document>.
- Latest six-platform run outcomes and format-appropriate installer evidence;
  missing coverage is recorded in the planning-only follow-up.
- Available package checksum, signing state and source/core/SDK/runtime identities.
- Available intermediate/final artifact and retention evidence, with absent
  outputs explicitly distinguished from successful publication.
- Fresh hosted-runner reproduction without local generated files.

## Review and rollback gates

- No blanket git add -f, git clean -fdx, hard reset or force-push.
- No remote branch deletion until ancestry/preservation is proved.
- No deletion based only on an ignore rule.
- No unsigned package labelled device-ready.
- Pin migration inputs to the observed immutable core `main`; do not claim final
  production compatibility from that selection.
- No old workspace or shared VHD removal before preservation and ownership.
- Keep original Git objects and untracked files until their audit is complete.
- Correct pushed mistakes with a reviewed follow-up or revert.

