<!-- TRELLIS:START -->
# Trellis Instructions

These instructions are for AI assistants working in this project.

This project is managed by Trellis. The working knowledge you need lives under `.trellis/`:

- `.trellis/workflow.md` — development phases, when to create tasks, skill routing
- `.trellis/spec/` — package- and layer-scoped coding guidelines (read before writing code in a given layer)
- `.trellis/workspace/` — per-developer journals and session traces
- `.trellis/tasks/` — active and archived tasks (PRDs, research, jsonl context)

If a Trellis command is available on your platform (e.g. `/trellis:finish-work`, `/trellis:continue`), prefer it over manual steps. Not every platform exposes every command.

If you're using Codex or another agent-capable tool, additional project-scoped helpers may live in:
- `.agents/skills/` — reusable Trellis skills
- `.codex/agents/` — optional custom subagents

Managed by Trellis. Edits outside this block are preserved; edits inside may be overwritten by a future `trellis update`.

<!-- TRELLIS:END -->

## Project execution policy

Read `.trellis/spec/guides/cloud-only-workspace.md` before executing commands.
This project-specific policy overrides older local-check examples in skills,
specs, task plans and historical notes.

- Run builds, tests, dependency restoration, formatters, analyzers, linters,
  installers and artifact generation only on GitHub-hosted Actions runners.
  This includes Python helper tests, syntax checks and the Chinese prose linter.
  Do not run them in local shells, WSL, containers or self-hosted runners.
- Keep local work to source/planning edits, read-only file/Git inventories,
  redacted secret-presence scans and GitHub metadata/log inspection. Do not
  download or extract build artifacts into either working clone.
- Preserve portable Trellis workflow/config/scripts/specs/tasks/journals and
  the reviewed `.agents/skills` sources. Do not commit identity, sessions,
  editor runtime state, caches, build outputs or signing credentials.
- Coordinate agents through Herdr. Prefer `gpt-6.1-sol`; inspect/retry transient
  failures and compact/restart exhausted sessions before the approved
  `deepseek-v4.1-flash` fallback. Do not change models silently.
- Shared-worktree workers edit only assigned paths and never stage, commit,
  merge, push or discard another worker's changes. The coordinator owns Git
  writes. Publish only through the orchestration push gate. Before invoking it,
  the coordinator must make the selected source `origin` GitHub-only because
  the gate selects that named remote.
- Keep cleanup inventory-only. Do not delete data or unregister WSL. Relocation
  to an external backup is allowed without deleting preserved data.
- Record GitHub run/job results with commit and input identities. A read-only
  review, skipped check, unsigned package or native-only build is not evidence
  that all application or device checks passed.

改写中文技术文本时套用受控中文规则：一句一动作、主动语态、一词一义（同一概念全篇同一个词）、不用分号连接动作、句长（指令 ≤ 25 字、说明 ≤ 40 字）、去掉虚动词（进行 / 加以 + 名词）、套话（需要注意的是、在一定程度上）、营销形容词（无缝、强大、赋能、闭环）与含糊词（若干、一些、相关）； 不得改动情态（可能 / 也许）：置信度是内容。机械首查仅在 GitHub 托管运行器执行：python <repo>/scripts/ste-lint-zh.py <文件>。

## Shared QFLI product workspace rules

# QFLI product workspace rules

These rules apply to every agent and every repository under this directory.
The user requires all builds and tests to run on GitHub-hosted runners.

- Do not run local builds, tests, benchmarks, emulators, or native compilation.
- Do not run dependency installation, SDK installation, or dependency restore.
- Do not download build artifacts, installers, SDKs, or build caches to this workspace.
- Do not run Flutter, Dart, Gradle, CMake, Ninja, Xcode, Hvigor, or package-manager commands that generate output.
- Read and edit source locally. Inspect Git metadata and text without creating build or test outputs.
- Run validation through the repository's GitHub Actions workflows. Read results through GitHub API or log output.
- Keep artifacts on GitHub. Record immutable source revisions, run IDs, job conclusions, checksums, and signing limitations in Trellis.
- Keep durable Trellis tasks, specs, research, journals, and project instructions in version control. Keep local runtime/session state and secrets ignored.
- Use GitHub as the sole remote for migrated clones. Check both fetch and push URLs.
- Preserve another agent's work. Coordinate repository ownership and handoff through Herdr.
- Do not delete shared WSL distributions or old source workspaces without the owning coordinators' preservation decision.
- Folder names follow GitHub repository names. Shared core is `qflistudio-core`; its Dart package name remains `qfli_studio_core`.

Each repository must also commit these restrictions in its own AGENTS.md or project policy so fresh clones on another PC retain the rules. This parent file is a convenience copy, not a substitute for versioned repository policy.

Initial coordinated writer: SQL coordinator, Herdr w62:p1, 2026-11-26.
