# Migration design

## Ownership and coordination

The migration parent owns source preservation, portable Trellis rules, Git
integration, destination comparison, cleanup planning and Herdr handover.
Existing children own native-runtime and app-installer implementation.
All agents share one checkout; assign disjoint files and prohibit worker commits.
The coordinator reviews, stages and commits source changes. Publication uses
the orchestration push gate only after the source `origin` fetch and push URLs
are both verified as GitHub-only.

Current Herdr routing:
- source Codex: w61:p1; Pi: w61:p2, w61:p3, w61:p4, w61:p5
- destination Codex: w6C:p1; destination workers remain idle until handover
- core owner: w63:p1; production compatibility remains a separate follow-up

## Preservation inventory

Compare authored working-tree content to the index and GitHub, including ignored
portable knowledge. Record each inclusion/exclusion class before staging.

Restore visibility for .agents skills, Trellis workflow/config/scripts/specs,
bootstrap task, agent definitions and workspace journals. Commit the nested
Trellis ignore rules so identity, session pointers, runtime logs and Python cache
remain local. Review version/template management files individually.
Do not blanket-add editor directories or generated research directories.
Inspect secret-like values without printing them; redact reports, not source
semantics. Preserve evidence screenshots, patches and authored source snapshots.
Generated platform registration sources remain unless there is evidence that
removing them is safe.

The initial Git object audit found 14 unreachable blobs and no unreachable
commits/trees. Keep the original object store until those blobs are classified.
Generated directories can contain authored scripts/evidence. Inspect them before
any deletion; retain unique source in appropriate tracked locations.

## Git topology and publication

All five currently advertised remote tips are ancestors of source main c999df6.
Recheck before publication. Integrate any newly discovered unique work through a
reviewed normal merge; do not force-push or invent empty merges.

Request publication only through the orchestration push gate. Before the gate,
make the source `origin` GitHub-only and verify its fetch and push URLs. The
target must retain GitHub-only fetch and push URLs.
Other mirrors are discovery inputs, not publication targets for this migration.
Existing mirror branch content is already incorporated; changing their server
defaults or deleting their branches is unnecessary to preserve source on GitHub.

## Clone and dependency contract

The E-drive editing layout uses repo names: qflistudio-rust beside
qflistudio-core. Update Rust-owned path dependencies and lockfile path entries
together, with all generation/validation performed in cloud where applicable.
Dart imports and package identity remain qfli_studio_core.

The approved 2026-11-27 14:35 migration ruling uses an immutable `CORE_REF`
from live GitHub core `main`, currently
`476a30acee21dc486ee2849dd8064a7be665e4d5`. The later 17:00 core-last ruling
holds this pin through consumer migration. A brain-coordinated bump wave after
final core publication requires another commit, gate and hosted CI.
Keep the exact reviewed Flutter-OH recipe.
This selection establishes migration inputs, not final SDK/native-hooks or
production compatibility. Do not reuse superseded ee83f1c or 573d1b6 pins.

Workflow `CORE_REF` feeds existing helper `CORE_SHA`/`APPROVED_CORE_SHA` values
before initialization. A manual `core_sha` must still equal the pinned input.
Keep SDK identity, source cleanliness, dependency-path and provenance checks.
Required hosted formatting, analysis and the full root suite retain real
outcomes. Apply the later 18:50 CI triage: rerun infrastructure failures once,
fix repeated configuration failures, record proven pre-migration defects as
follow-ups, and repair migration-caused failures through another gate commit.
Do not relax checks or claim unexecuted checks passed.

patch_upstream_core.sh belongs to qflistudio-next/tool/ci, not shared core.
It is not currently a Rust file. Do not copy it blindly. If upstream Flutter
needs an adaptation, review its behavior against the pinned core and record an
explicit Rust-owned contract. Existing CI aliases can remain only when every
checkout/path/override/patch consumer agrees. The new app workflow should use
the editing layout directly unless an audited SDK contract requires an alias.

## Cloud-only execution contract

Record the policy in root AGENTS.md, portable Trellis specs/workflow guidance and
developer-facing cloud instructions. Prohibit local builds/tests, pub get,
dependency installation, formatter/analyzer runs, package execution and
generated outputs, including in WSL or local containers.
Read-only file/Git/API inventory and source/planning edits remain allowed.

Add cloud workflow preflight to build helpers where useful. Do not invoke the
helpers locally to test the guard. All syntax, unit, integration, Dart, native,
packaging and controlled-Chinese lint checks run on GitHub-hosted runners.
Update older plans/specs that still instruct local validation.

## Cloud outputs and verification

Preserve native provenance verification. Extend supported targets as needed.
App jobs cover Windows, Linux, macOS, iOS, Android and OHOS. Distinguish:

1. Native guest and selected stage outputs, runtime archives and diagnostics.
2. Flutter build outputs and necessary packaging intermediates.
3. Verified installer packages with checksums and input/output manifest.
4. Cloud test and installation-verification reports.
5. Signing/provisioning state and target-device validation state.

Use bounded, documented retention for intermediate artifacts and complete
packages. Never place these outputs in the source repository. Avoid dependency
on an arbitrary latest-successful runtime: verify source/input compatibility,
ABI headers, checksums, architecture and embedded build provenance.
Existing mobile runtime artifacts expire on 2026-12-01; fresh or durably
published compatible inputs are required after expiry. Store publication is
outside this task; long-lived artifact publication must be explicit.

Current desktop runtime behavior uses installed cargo/rustc. Document package
prerequisites rather than claiming an embedded runtime that is not implemented.
The prior Android armv7 plan crosses Gradle, host selection, ABI mapping and
ELF32 support. Preserve that pending requirement and assess it as a separate
native compatibility change; do not claim a three-ABI result from two APKs.
OHOS schema-1 manifests need their own validation adapter.

The repository-level secret and variable lists were empty at planning time.
Check environment/organization availability before concluding all signing inputs
are absent. Required signing jobs must clearly identify missing prerequisites.
Unsigned iOS/OHOS outputs are developer artifacts, not accepted device-ready
packages. No signing material belongs in Git.

## Comparison and cleanup

After gate publication, measure the target before updating it. If it is clean,
use a fast-forward pull. If it has changes, preserve and review them instead of
resetting them.

Compare HEAD and tree IDs, tracked blob IDs/modes and actual worktree diffs.
Windows LF/CRLF conversion can change raw byte hashes; normalize according to
Git attributes and report conversion separately from content mismatch.
Check portable Trellis links and Git status. Inventory ignored source-only
paths in the cleanup report; ignored files need not be reproduced in the target.
Keep preservation dispositions and originals. Do not compare local caches as
part of tracked source equality.

Resolve every cleanup candidate to an absolute path under the old Rust root.
Reject reparse-point traversal. Cleanup remains inventory-only in this task.
Do not delete SDK/Pub junction targets, old source, Git objects or shared
storage. Approved external relocation is copy-only until a separate owner
decision permits any later removal. Retain package/evidence/native source
copies until replacements are verified.

All registered WSL VHDs are outside the Rust roots. Send their inventory to
owning agents through Herdr; deletion requires their readiness and a validated
exact target. Do not unregister a shared distribution from this workspace.

## Rollback and handover

Before publication keep all original untracked source and Git objects.
After publication use corrective commits or a reviewed revert, not history
rewriting. Keep the old workspace until comparison and receiving-agent
acknowledgement.

Handover records final GitHub SHA/tree, paths, task hierarchy, cloud run evidence,
artifact lifetimes/signing limits, unresolved prerequisites and cleanup results.
The target coordinator acknowledges ownership through Herdr. The 18:50
`ci-decoupled.md` ruling requires `migrated.json` immediately after preservation,
clean tracked parity, committed agent rules, branch/backup/cleanup records and
exact-SHA acknowledgement. Include pending CI IDs; one Pi monitors CI separately.
Write `done.json` by adding final-SHA CI evidence and the documented triage above.
Repeat target parity and acknowledgement after each new publication.
Record each latest installer platform outcome and missing
artifact/signing evidence without claiming platform acceptance.

Per the 2026-11-27 14:35 ruling, SDK/native-hooks compatibility, signing,
device/UI tests, Android armv7, receiver-hook diagnosis and missing installer
acceptance are planned separately in
[`11-27-rust-compatibility-followups`](../11-27-rust-compatibility-followups/prd.md).
Include them in `done.json` notes. Completing this migration does not complete
those product tasks or change a failed check into a pass.

