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

## Ordered execution

1. Capture a fresh source/target status and all remote advertised heads.
   Preserve concurrent edits and the original object store. Record ownership.
2. Restore portable Trellis/agent source visibility and review candidate files
   for source completeness and sensitive content. Classify ignored authored
   files, generated evidence, packages, source copies and unreachable blobs.
3. Add durable cloud-only rules to AGENTS/specs and update older local-test
   instructions. Preserve historical task results without inventing completion.
4. Review and commit source/progress preservation. Push explicitly to GitHub
   with main:main, then verify the advertised SHA. No ordinary source-origin push.
5. Prepare CI helper, package and check workflows in disjoint worker ownership.
   Use the existing app-installer and native-runtime child tasks.
6. Obtain core owner's final SHA/compatibility handoff. Align Rust pubspec,
   lockfile path metadata, checkout layout, vendor override and any required
   upstream-Flutter adaptation. Do not run pub get locally.
7. Complete native and application workflows. Include bounded intermediate
   artifacts, installer/checksum/provenance outputs and cloud checks.
   Preserve explicit Android armv7 and signing prerequisites.
8. Use GitHub to validate all checks and actual platform builds. Observe each
   run through gh APIs; fix evidenced failures and rerun affected jobs.
   Do not download large build artifacts to either local workspace.
9. Persist run evidence and accurate task progress. Commit/push final source.
   Recheck all discovered tips and final main ancestry.
10. Confirm target remains clean; pull from its GitHub-only origin with ff-only.
    Compare source/GitHub/target commit, tree, blobs/modes and portable progress.
11. Finalize exact cleanup inventory. Remove only verified project-owned
    generated paths after evidence/replacement checks. Coordinate WSL ownership.
12. Commit handover evidence as needed, repeat target pull/comparison, and send
    final handover through Herdr. Obtain receiving Codex acknowledgement.
    Report remaining external blockers rather than marking them complete.

## Worker ownership during execution

Assign work only after approval and refreshed context:
- Worker A / w61:p2: AGENTS.md, root and Trellis ignore rules, portable
  workflow/config/spec/skill guidance, research/source-portability.md.
- Worker B / w61:p3: tool/ci/ci_support.py, app_build.py,
  .github/workflows/app-installers.yml and orchestration helper tests.
- Worker C / w61:p4: tool/ci/package_installer.py, windows_installer.iss,
  test_package_installer.py and installer-contract notes.
- Worker D / w61:p5: scripts/ci_native_runtime.py,
  scripts/test_ci_native_runtime.py, native-runtime.yml when required,
  native task research, plus read-only review of A's changes.
The coordinator owns task documents, spec integration, final cross-review,
Git writes, target update and handover. Refine exact file ownership before each
dispatch; workers must preserve other edits and never commit.

## Execution record — 2026-11-27

The user confirmed execution after the final planning review. Task start
succeeded and all four existing Pi workers received scoped implementation
through Herdr. Claude w61:p6 monitors without file or Git writes.

The first native fix verifies both Android library copies in the archived
payload. Its regression is assigned to D; cloud execution remains pending.
Android armv7 remains an explicit unmet requirement across compiler, ELF32,
host/ABI selection, Gradle and Dart loader layers. Do not count two APKs as three.

B and C share the canonical output directory and reports/packages.json contract.
Packaging leaves overall manifest status incomplete until finalization verifies
the complete package set. OHOS uses its source bundle ID com.azurekiln.qfli.rust.
The generic Android/Apple identity must not overwrite it.

Core's final migration SHA and validated SDK contract remain external gates.
Independent cloud helper/native checks should run without that app dependency.

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
- Actual six-platform builds and format-appropriate installer checks.
- Per-package checksum, signing state, source/core/SDK/runtime input identities.
- Intermediate/final artifact upload and retention checks.
- Fresh hosted-runner reproduction without local generated files.

## Review and rollback gates

- No blanket git add -f, git clean -fdx, hard reset or force-push.
- No remote branch deletion until ancestry/preservation is proved.
- No deletion based only on an ignore rule.
- No unsigned package labelled device-ready.
- No core final pin before owner handoff.
- No old workspace or shared VHD removal before preservation and ownership.
- Keep original Git objects and untracked files until their audit is complete.
- Correct pushed mistakes with a reviewed follow-up or revert.

