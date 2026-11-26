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
  writes. Publish only to the explicit GitHub URL and refspec; the old source
  `origin` has multiple push URLs.
- Record GitHub run/job results with commit and input identities. A read-only
  review, skipped check, unsigned package or native-only build is not evidence
  that all application or device checks passed.

改写中文技术文本时套用受控中文规则：一句一动作、主动语态、一词一义（同一概念全篇同一个词）、不用分号连接动作、句长（指令 ≤ 25 字、说明 ≤ 40 字）、去掉虚动词（进行 / 加以 + 名词）、套话（需要注意的是、在一定程度上）、营销形容词（无缝、强大、赋能、闭环）与含糊词（若干、一些、相关）； 不得改动情态（可能 / 也许）：置信度是内容。机械首查仅在 GitHub 托管运行器执行：python <repo>/scripts/ste-lint-zh.py <文件>。