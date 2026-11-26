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
Classification of the original 14 unreachable blobs and authored code/patches
inside generated roots remains pending. Preserve those bytes and their original
paths until unique source/evidence is reviewed and deliberately preserved.

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
`.codex` and `.trae` hook/config portability is explicitly pending separate
source/dependency review. Do not blanket-copy them or discard authored hooks
as editor state. The receiving coordinator's reported startup-hook failure
remains unresolved until that integration review has evidence.

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
required coverage or a task complete while checks, preservation or credentials
remain unresolved. Link real cloud evidence and name each blocker explicitly.
