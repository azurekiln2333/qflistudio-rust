# GitHub migration and cloud-only Rust workspace

## Goal

Preserve Rust source and portable Trellis progress on GitHub. Make the confirmed
E-drive clone the next working location. Run every build and test on GitHub.
Hand over verified state to its Codex coordinator through Herdr.

## Confirmed facts

- Source: `D:/MyNewProjects/qfli_rust`.
- Destination: `E:/MyNewProjects/QFLIProjects/qflistudio-rust`.
- User approved task creation and this destination on 2026-11-26.
- Initial source HEAD: `c999df6e75ce0626fe22db04a481a12035629ca0`.
- Initial GitHub/destination main: `540674ff95a83daa2848ee463f3c6aaf8986f6ff`.
- Origin fetches GitHub and pushes to GitHub, Gitee, GitLab, GitCode and CNB.
- All five advertised remote branch tips are ancestors of local main.
- Untracked work includes `11-17-app-installers` and `tool/ci/ci_support.py`.
- Root ignore rules exclude specs, workflow, scripts, journals and agent helpers.
- Only `.github/workflows/native-runtime.yml` exists. Successful run
  `44012848384` proves its native targets, not application installers.
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
- R4: GitHub is authoritative. Push explicitly to GitHub. The destination clone
  must have GitHub as its only remote endpoint.
- R5: Establish durable rules forbidding local builds, tests, dependency
  restoration, formatting tools, installer execution and artifact generation.
  Execute these on GitHub-hosted runners. Local Git, inventory and edits remain
  permitted. Do not run local pub get to repair a lockfile.
- R6: Complete Windows, Linux, macOS, iOS, Android and OHOS cloud coverage:
  native dependencies, required intermediates, Flutter outputs, installers,
  cloud checks, checksums and provenance.
- R7: Record signing and installation status exactly. An unsigned IPA/HAP is
  not evidence of a device-installable signed package. Inspect credential
  metadata only and expose signing prerequisites in workflows and handover.
- R8: Record real run IDs, app/core SHAs, per-job results, artifact retention and
  installer checks. External missing credentials or failed jobs remain explicit
  incomplete acceptance items; never fabricate successful coverage.
- R9: Pull the preserved GitHub state into the destination and compare commit,
  Git tree, source files and portable Trellis content. Both worktrees must be
  clean. Ignored authored files cannot silently disappear from the comparison.
- R10: Inventory obsolete build output and WSL storage. Clean only verified,
  project-owned generated paths after preservation and comparison. Shared WSL
  requires cross-product ownership/readiness. Provide exact cleanup steps.
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
  signing and validation status separately.
- [ ] A5 (R4,R9): Source HEAD/tree, GitHub main and destination HEAD/tree agree.
  Both Git statuses are clean; destination remotes are GitHub-only.
- [ ] A6 (R10): Exact cleanup paths have ownership and preservation evidence.
  Deleted output and remaining shared-storage blockers are recorded.
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

- Review the final planning summary before implementation.
- Obtain the final core handoff before selecting the production CI pin.
- Audit signing metadata; do not treat absent secrets as a completed installer.
- Resolve shared WSL ownership before destructive distribution removal.

## Planning convergence

The confirmed paths, repository ownership, GitHub-only destination, cloud-only
execution and Herdr collaboration resolve the requested scope. Technical
prerequisites above remain explicit execution gates, not assumed successes.
This PRD has been consolidated against the design, implementation plan and
dated research record. The final planning summary awaits user review.

