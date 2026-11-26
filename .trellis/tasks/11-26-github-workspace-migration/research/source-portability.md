# Portable source and execution policy — 2026-11-27

## Scope and status

Worker A owns portable knowledge, ignore rules and source inventory only.
The coordinator owns Git writes and final outgoing-file review. The initial
preservation pass did not edit product code, CI workflows, app helpers, native
scripts, pubspec or lockfiles. Later authorized path/signing edits are recorded
in the follow-up section below. No stage, commit, merge, push, deletion, build, test, formatter,
analyzer, dependency restore, installer or artifact download was performed.
Only file/Git inventory, read-only content review, redacted secret-presence
inventory and scoped file edits were used. No local validation command ran.

The reviewed implementation plan records approval and activation on 2026-11-27.
No task was created or started by this worker. Herdr coordination remained with
`w61:p1`; this worker preserved the existing `gpt-6.1-sol` model.

## Preservation inventory

Initial counts are snapshots, not claims that every candidate is newly tracked.

| Candidate class | Observed source files | Handling |
| --- | ---: | --- |
| `.agents/skills` | 46 Markdown files in 12 Trellis skill directories | Explicit root allowlist exposes Markdown skills/references only |
| `.trellis/scripts` | 28 Python source files | Portable as source; not executed or modified |
| `.trellis/spec` | 28 original Markdown files | Restore visibility, retain substantive and placeholder guides; add cloud policy |
| `.trellis/agents` | 2 Markdown definitions | Portable; hosted-check and no-worker-Git rules made explicit |
| `.trellis/tasks/00-bootstrap-guidelines` | 2 task files | Portable task history; restore visibility without claiming it complete |
| `.trellis/workspace` | 3 Markdown files | Preserve workspace index and existing developer index/journal |
| `.trellis/workflow.md`, `config.yaml`, `.gitignore` | 3 files | Portable operational rules and local-state exclusions |
| `.trellis/.version` | Version marker `0.6.17` | Portable installed-template version evidence |
| `.trellis/.template-hashes.json` | Updater management file | Remains ignored, unchanged, retained locally |

The nested Trellis ignore file preserves local-only developer identity,
current-task pointers, session/runtime directories, agent logs, update scratch
state and Python caches. Machine-specific `hooks.local.json`,
`config.local.yaml` and environment files are now excluded explicitly.

Root ignore rules no longer hide authored Trellis workflow/config/scripts/specs,
agent definitions, bootstrap task and workspace index. Existing tracked progress
journals stay tracked. The `.agents` allowlist names the twelve existing
`trellis-*` skills individually; it does not expose arbitrary future skills,
non-Markdown assets or editor runtime data. No skill/reference file was deleted.

Existing Flutter/native/generated-output ignores remain. Additional cache,
compiled-binary/package and signing/environment patterns reduce accidental
inclusion; they do not untrack files or prove outgoing content is safe. No
`.env`/keystore/private-key/provisioning filename candidate was observed among
tracked or then-visible untracked paths in the limited filename inventory.

## Policy edits

`AGENTS.md`, the workflow, spec indexes, native guidance, runtime agents and
before-dev/check/finish-work skills now direct all executable checks, builds,
formatters/analyzers/linters, dependency restores, installers and generated
outputs to GitHub-hosted Actions runners. Local shells, WSL, containers and
self-hosted runners are not substitutes. Missing hosted jobs/evidence remain
pending; read-only inspection is not an executed pass.

The new source of truth is `.trellis/spec/guides/cloud-only-workspace.md`.
It supersedes generic/local command examples and historical task instructions
without rewriting historical results. Developer-facing native-build guidance
now consumes/checks/restores artifacts in hosted jobs, not editing clones.
No workflow capability or six-platform result is claimed by these docs.

`.trellis/config.yaml` now sets `session_auto_commit: false`. Inspection of the
existing helper source showed the default was true for journal/archive
operations. The explicit setting avoids surprising staging/commits in this
shared checkout. Helpers were not invoked to test the setting. The coordinator
must still review metadata writes and any configured hooks before using them.

## Files edited or created by Worker A

- `.gitignore`
- `AGENTS.md`
- `.trellis/.gitignore`
- `.trellis/config.yaml`
- `.trellis/workflow.md`
- `.trellis/agents/check.md`
- `.trellis/agents/implement.md`
- `.trellis/spec/backend/index.md`
- `.trellis/spec/backend/github-native-builds.md`
- `.trellis/spec/backend/native-runtime.md`
- `.trellis/spec/backend/rust-terminal.md`
- `.trellis/spec/frontend/index.md`
- `.trellis/spec/frontend/native-startup.md`
- `.trellis/spec/guides/index.md`
- `.trellis/spec/guides/readme-language.md`
- `.trellis/spec/guides/cloud-only-workspace.md` (new)
- `.agents/skills/trellis-before-dev/SKILL.md`
- `.agents/skills/trellis-check/SKILL.md`
- `.agents/skills/trellis-finish-work/SKILL.md`
- `docs/native-github-build.zh-CN.md`
- This research note (new)

Other newly visible portable files are unchanged local source, not authored by
this worker. Other workers' current edits remain theirs. The coordinator should
stage only reviewed file lists, not blanket-add all ignored/editor content.

## Secret-presence review and limits

An in-memory read-only scan covered 116 initial knowledge candidates, totaling
885303 bytes. It looked for private-key headers, selected provider-token shapes,
credential-bearing HTTP URLs and literal sensitive assignments. It emitted no
rule hits and never printed source values. This is a limited shape inventory,
not a complete secret/history audit or a guarantee that credentials are absent.
Newly authored policy text contains no supplied credential values. Final staged
content and any additional preservation candidates need coordinator review.
No local secret-scanner package, test or validation tool was executed.

## Explicit pending preservation items

1. **`.codex` / `.trae` hooks and configuration:** not copied, rewritten or
   blanket-included. Portable authored hooks, relative helper dependencies and
   machine-specific settings require separate ownership/content review. The
   receiving coordinator's reported startup-hook failure is not resolved by
   making Trellis scripts visible. Do not discard authored hooks as runtime data.
2. **Fourteen unreachable Git blobs:** topology audit found blobs but no
   unreachable commits/trees. Their content/provenance remains unclassified.
   The original object store was not pruned, removed or repacked by this worker.
   Preserve it until the coordinator classifies and preserves any unique source.
3. **Authored code, patches and evidence under generated roots:** directory-level
   output classification is insufficient. Existing `build`, `native/build`,
   `ohos/build` and `ohos/entry/build` roots were retained. No contents were
   deleted, relocated or silently excluded from the preservation requirement.
   Inspect authored helpers, source snapshots, patches, reports and screenshots
   before cleanup; deliberately preserve unique source in reviewed tracked paths.
4. **Historical raw logs:** 33 ignored `.log` files remain in release-task
   research. Preserve them locally pending content/evidence/secret review; do not
   blanket-add logs or delete them because the source summary is already tracked.
   Existing tracked screenshots, patches and source snapshots remain unchanged.
5. **Source completeness and final checks:** outgoing staged content, placeholder
   specs, relative-link completeness, newly exposed helper syntax, ignore-rule
   regression coverage and controlled-Chinese lint still require coordinator
   review and actual GitHub-hosted validation where executable. No pass is
   claimed here. Git inventory/readback only showed intended portable classes
   visible and existing runtime/cache/management classes still ignored.
6. **Shared dependencies and final handover:** final core SHA/compatibility,
   hosted outputs/signing, clean source/target comparison and receiving-agent
   acknowledgement remain owned by the coordinator and other workstreams.

## Follow-up portability and path review

The existing `.codex/` and `.trae/` files are already tracked. Their settings
register project-relative hook paths. The inspected hooks resolve Trellis through
`<repo>/.trellis/scripts/common`, and the referenced helpers exist in the now
portable script tree. No hook was executed. The receiver previously reported
only `Hook failed` and `hook exited with code 1` before portable scripts were
available. That text does not identify a cause. Receiver-visible diagnostics
remain pending. Do not copy or discard these platform files based on that
message alone.

The path-only dependency edit is ready for review:

- `pubspec.yaml`: `qfli_studio_core` path is `../qflistudio-core`.
- `pubspec.yaml`: `re_editor` override path is
  `../qflistudio-core/vendor/re_editor`.
- `pubspec.lock`: both matching relative path entries use `../qflistudio-core`.

Dart package names and dependency versions were unchanged. No `pub get` ran.
The final cloud dependency-resolution job must confirm the sibling checkout and
lock metadata together.

`ohos/build-profile.json5` contained two signing material blocks. Each exposed
nonempty signing-property fields, including certificate/profile/store paths,
key aliases and passwords. The edit removed those two blocks and the automatic
product signing selector. Product, SDK, runtime, build-mode and module
definitions remain. No signing value was printed or preserved in this note.
Cloud signing injection and unsigned-package status remain pending. Credential
rotation and any history remediation belong to the credential owner; no history
rewrite was performed.

## Generated-root source evidence inventory

No generated-root file was deleted, moved or overwritten. Shallow, no-reparse
inventory found authored-looking source/evidence mixed with output under:

- `build/content-author-scratch/`: Python authoring/check/patch helpers and Rust
  exercise sources.
- `build/offline-ide-audit/`: Python, PowerShell and shell helpers, reports,
  JSON/Markdown/TXT evidence, a compiler-guide patch, Rust source snapshots and
  catalog examples.
- `native/build/.patchwork/`: large Rust source snapshots under patchwork `a/`
  and `b/`, including Miri modules and platform shims.
- `build/`: reports, screenshots, logs, verification JSON and an APK coexist
  with generated directories. These classes need per-file preservation review.

The roots `build`, `native/build`, `ohos/build` and `ohos/entry/build` remain
stable. Directory names and extensions do not decide deletion. The coordinator
must preserve unique helpers, patches, source snapshots, reports and screenshots
before any cleanup. Existing ignore patterns do not silently delete them.

## Unreachable blob classification

The original 14 unreachable blob objects remain in the object store. A
read-only content-shape review emitted no credential value and did not write
objects. No blob matched a current index path. The observed metadata was:

| Blob | Bytes | Shape classification |
| --- | ---: | --- |
| `c061fbc2df1ccfe063b18d27e46dcd36730c2ef5` | 293 | JSON-like |
| `ad74351a9e94d774540ea9d989e025d82f7985a1` | 5823 | Other text, unclassified |
| `f7d410bb4372572fcefad1eab8e0e7a8965cf91c` | 12498 | Markdown/source-like |
| `0536e7023be601e942704411ad6d5a3532a391e3` | 4472 | Markdown/source-like |
| `85773ae997b66e23833eb39273dd7d0d8e9aa24c` | 294 | JSON-like |
| `fd17e8e4886f8b90da8eb99251f79598adda506e` | 9085 | Patch-like |
| `8f38ee01d0f77d910a1d3422b2008aacbf6aade5` | 23457 | Python-like source |
| `a628adeb2b237c0221f6542e452069ee8d668f5b` | 4480 | Markdown/source-like |
| `9419652c85cf38acfb7ffa2789776772823a4f22` | 8798 | Python-like source |
| `9f0939861c79333ca58d4022d5dbf14694d414c2` | 3736 | Markdown/source-like |
| `bb697a15db8c53c619e4b664934f6e8c4619baab` | 694 | JSON-like |
| `26eadb67a213e026f04d79bac473085c4de386aa` | 286 | JSON-like |
| `56aa20a8e3cf74a67289914bd77b7ec4af5fe454` | 2099 | Markdown/source-like |
| `a88e238f9af960b6fce10e06539669634d5911dc` | 25129 | Markdown/source-like |

These are classifications, not content provenance. Preserve the objects until
coordinator review determines whether any unique source or evidence needs a
tracked copy. No prune, repack, reflog rewrite or other object mutation ran.

## Resolution note — 2026-11-27

The earlier pending source/blob/log rescue items above describe their inspection
snapshots, not the final rescue status. The authorized rescue is now completed
and documented in
`.trellis/tasks/11-26-github-workspace-migration/research/preservation-rescue.md`.
Its exact source/object mappings, raw SHA-256 hashes, duplicate references and
exclusion dispositions are in
`.trellis/tasks/11-26-github-workspace-migration/research/preserved-source/manifest.json`.
This note does not repeat or replace that ledger.

The rescue preserved 119 unique exact-byte historical files. All 14 original
unreachable blobs are accounted for: eleven received portable copies and three
matched exact stage-0 index content during the later rescue comparison. That
later comparison used a different index snapshot from the earlier statement
that no blob matched a current index path. The original observations above
remain unchanged. The tentative JSON-like classification of `85773ae...` was
refined to a Cargo/TOML manifest; descriptive names do not establish provenance.

Authored helpers, source variants, patch endpoints and selected useful evidence
from the three authorized generated roots now have portable copies or explicit
duplicate mappings. Unchanged upstream pairs and generated/transient outputs
were not bulk copied. All 33 ignored release logs were reviewed and hashed;
portable sanitized knowledge is recorded in
`.trellis/tasks/11-26-github-workspace-migration/research/preserved-source/historical-log-summary.md`.
Raw logs, original source files and original Git objects remain intact.

Rescue completion does not authorize cleanup or establish current check passes.
The rescue report retains provenance, excluded-record, secret-review, cloud
validation and receiving-clone gates. Receiver diagnostics remain only
`Hook failed` / `hook exited with code 1`; no hook cause or repair is inferred.
Worker A did not stage or commit this resolution note and ran no local
executable checks. The coordinator committed the earlier preservation report as
`c859677`.
