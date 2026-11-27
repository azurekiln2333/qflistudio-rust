# Cloud-only workspace and portable knowledge

## Scope and precedence

This project policy applies to every agent, contributor and working clone.
It overrides local-execution examples in generic Trellis skills, older task
plans, historical journals and product documentation. Preserve historical
results as evidence of their original date; do not rerun their commands locally.

## Execution boundary

Run every build, test, syntax check, analyzer, formatter, linter, dependency
restore, installer and artifact-generation command on GitHub-hosted Actions
runners. This includes Flutter/Dart, Cargo/native/ArkTS tooling, Python helper
regressions and `scripts/ste-lint-zh.py`. WSL, local containers and self-hosted
runners do not satisfy this policy. Do not use local `pub get` to repair paths
or a lockfile. Do not invoke a build helper locally to test its cloud guard.

Locally allowed work is source/planning editing and read-only inventory:
file inspection, Git status/diff/ls-files/check-ignore/ls-remote/ancestry queries,
Git blob comparisons, redacted secret-presence scans, and GitHub metadata/log
inspection. Do not download, extract or execute build artifacts in either
working clone. Coordination and approved Trellis task/journal metadata updates
are not product checks; use `PYTHONDONTWRITEBYTECODE=1` for Python metadata tools.

Keep validation requirements intact. Move their execution to GitHub rather
than replacing them with a read-only review or claiming they passed. If a
required hosted job does not exist, cannot run or lacks credentials, record
that check as pending/blocked with the reason. Record run ID, source SHA,
input identities and per-job outcomes when actual evidence becomes available.

## Durable and local-only files

Preserve authored source, root agent rules, Trellis workflow/configuration,
scripts, specs, agent definitions, task artifacts, research and progress journals.
Preserve reviewed screenshots, patches and authored source snapshots as evidence;
a directory named `research` or `build` alone does not determine ownership.
Never run blanket cleanup or discard the original Git object store on that basis.
The rescue ledger now preserves 119 authored/evidence copies, totaling
2,329,864 bytes. All 14 original unreachable blobs are reconciled: 11 preserved
copies and three exact index duplicates. Rescue classification is complete.
The directory-local `* -text` rule protects historical raw bytes; publication
and receiving-clone comparison are separate gates. Keep original source and
Git objects. This migration authorizes inventory only, not deletion.
See the migration task's `research/preservation-rescue.md` and dated execution
record. Do not alter the coordinator's raw-byte correction as part of a spec edit.

The root ignore rules expose only Markdown files in explicitly reviewed
`.agents/skills/trellis-*` directories. New skills and non-Markdown skill assets
need a separate review before inclusion. Keep other editor configuration,
transcripts, authentication data, session stores and runtime state local.

Commit `.trellis/.gitignore` so a clone still excludes developer identity,
current-task pointers, `.runtime`, machine-specific hook configuration, temporary
update state and Python caches. Preserve `.trellis/.version` as the installed
Trellis version marker. Keep `.trellis/.template-hashes.json` local as updater
management state; do not rewrite it just to mark project customizations clean.
Reinstall machine-specific platform integrations deliberately after migration;
portable specs/scripts alone do not prove an editor hook works on a new machine.
The source hook paths have been reviewed; that review does not establish hook
execution in the receiving clone. Do not blanket-copy machine integrations or
discard authored hooks as editor state. The receiver's startup transcript reports
`Hook failed` / exit code 1 without the command or stderr. Its execution failure
remains unresolved. The F2 service-tier/model support warning is a separate
warning, not hook diagnostics, and does not identify the hook's cause. Require
receiver-side command/stderr and successful execution evidence before claiming
a repair. Source review alone is not an integration pass.

Ignore rules are not a secret audit and do not untrack existing files. Review
outgoing file content and staged paths before publication. Secret-presence
reports contain paths and rule categories, never credential values. Keep signing
keys, certificates, local environment files and integration secrets out of Git.
Use GitHub environment/repository/organization metadata to assess prerequisites;
an empty repository secret list alone does not prove all signing inputs absent.

## Shared worktree and handover

Communicate and dispatch through Herdr. Assign disjoint file ownership and
preserve concurrent edits. Workers do not stage, commit, merge, push or reset.
The coordinator reviews and owns Git writes. `session_auto_commit: false` in
`.trellis/config.yaml` keeps archive/journal helpers from staging or committing
unexpected changes. Coordinator review still applies to metadata updates.

Prefer `gpt-6.1-sol`. Inspect/retry transient concurrency failures and
compact/restart exhausted sessions first. Use `deepseek-v4.1-flash` only after
those recovery attempts fail under the approved coordination policy.

The coordinator reviews and owns Git writes. Publish only through the
orchestration push gate. Because the gate selects the named `origin`, the
coordinator must first set the source `origin` fetch and push endpoints to the
GitHub repository and verify both endpoints. Do not invoke direct `git push`.
Recheck advertised tips and stop for unreviewed unique work before requesting
the gate.

The receiving clone must use GitHub for both fetch and push endpoints. Measure
its worktree before updating it. If it is clean, use `git pull --ff-only`; if it
has changes, preserve and review them before proceeding. Compare source,
GitHub and destination commit IDs, tree IDs, tracked modes and blob contents,
and portable Trellis files. List ignored source-only paths in the cleanup
procedure; ignored local state need not exist in the receiving clone. Preserve
its ownership and rescue dispositions separately. Do not claim clean status or
tracked parity until those measurements finish.

Keep preservation and ownership guards separate from publication. Do not delete
the old source, generated-output candidates, Git objects or shared storage, and
do not unregister WSL. Relocate approved material to the external migration
backup only when the copy and ownership record are complete, while retaining
the originals. Reject reparse-point traversal and coordinate shared-storage
owners before any future cleanup decision.

## Quality and acceptance evidence

A successful native-runtime job does not prove a Flutter application installer,
application tests or target-device execution. Keep these outcomes separate.
An unsigned IPA/HAP is not a device-installable signed-package pass. Do not mark
product coverage complete while its checks or credentials remain unresolved.
Link real cloud evidence and name each incomplete result explicitly. See
[Application CI contracts](../backend/github-app-builds.md) for immutable core
and SDK inputs, producer-byte verification, typed OHOS no-sign, bounded
intermediates and quality-only report semantics.

The coordinator's 2026-11-27 14:35 ruling limits `done.json` to workspace
migration. Pin the brain-authorized core SHA as immutable `CORE_REF`, retain the exact
reviewed SDK recipe, and retain actual hosted Dart formatting, Flutter
analysis and complete root-suite evidence at the published migration SHA.
The 2026-11-28 03:30 `core-ref-wave-2.md` ruling replaces the first wave's pin
with core `8e031313ffc8d531c5a6b4d131f721f35da04c86`. The brain later required
pin-only publication, completed at `68723d029dfd9dae8ea91c97b8a26848f116e8cd`.
Gate, clean target parity and exact-SHA acknowledgement passed before deferred
quality repairs were restored. Restoration made the source dirty at that recorded point. The separate repair commit
requires a new gate, parity measurement and acknowledgement. Cloud checks
`46072255988` passed. Quality `46072256145` passed helpers, preparation and
analysis but failed formatting and root tests. Installers `46072256031` passed
six of seven platform jobs; iOS failed on `hashlib.file_digest`. Application
quality and product acceptance remain open.
Do not adopt another core SHA unless the brain sends another wave.
Missing final production core/SDK or Rust native-hooks approval does not block
this migration pin. It remains unverified product compatibility.

The later 18:50 `ci-decoupled.md` ruling separates workspace handover from CI.
While one Pi watches runs, finish target fast-forward, clean tracked parity,
committed agent rules, branch/backup/cleanup records and the exact-SHA receiver
acknowledgement. Write `migrated.json` with those facts and CI run IDs even when
CI is pending. Repeat parity and acknowledgement whenever the published SHA changes.
Write `done.json` only with final-SHA CI evidence and explicit failure triage:
rerun infrastructure failures once, then fix repeated configuration failures;
document failures proven to exist at pre-migration GitHub main as follow-ups;
fix migration-caused path, core, lockfile or registrant failures and pass the
push gate again. Never change a failed or unexecuted check into a passing claim.

Record latest installer runs per platform with conclusions, artifact names and
signing states. Missing installer platforms, SDK/native-hooks, signing,
device/UI, armv7 and receiver-hook evidence remain in the planning-only
`11-27-rust-compatibility-followups` task and `done.json` notes. Migration
completion does not close those tasks or relabel required migration quality checks,
or permit deletion. Source/target comparison requires clean tracked HEAD/tree
parity; differing ignored inventories are expected and must be recorded.
