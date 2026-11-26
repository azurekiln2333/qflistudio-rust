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
Git objects until the coordinator records those gates and authorizes cleanup.
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

GitHub is authoritative. Use its explicit repository URL and explicit refspec
for publication, not the old source `origin` name with multiple push URLs.
Recheck advertised tips before publication and stop for unreviewed unique work.
The receiving clone must have only GitHub fetch/push endpoints. Compare commit,
Git tree, tracked modes/content and ignored authored inventory before handover.
Do not delete old source, generated-output candidates or shared storage without
preservation, ownership and replacement evidence. Coordinate shared WSL owners.

## Quality and acceptance evidence

A successful native-runtime job does not prove a Flutter application installer,
application tests or target-device execution. Keep these outcomes separate.
An unsigned IPA/HAP is not a device-installable signed-package pass. Do not mark
required coverage or a task complete while checks, transfer comparison or
credentials remain unresolved. Link real cloud evidence and name each blocker
explicitly. See [Application CI contracts](../backend/github-app-builds.md) for
core/SDK approval, producer-byte verification, typed OHOS no-sign, bounded
intermediates and quality-only report semantics. Native/helper success does not
approve an absent final core SHA, SDK contract or Rust native-hooks recipe.
Actual application packaging, signing, device validation and Android armv7
remain pending.
