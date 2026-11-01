# Commit review

The product changes and verification are ready for review. No files have been staged or committed by this task.

## Recommended handling

Keep this task uncommitted until the pre-existing Rust runtime work is committed or explicitly included in an approved batch. The task-only patch is saved in research/task-only.patch.

Reason: lib/native_miri_runner.dart was already an untracked runtime implementation before this task; this task changes its import/title only. lib/rust_runner.dart also already depended on that unfinished runtime migration. Staging entire edited files would include previous work outside this task. Staging an isolated title change to a file absent from HEAD is not a valid standalone code commit.

## Candidate work commit after the dependency baseline is settled

`fix(runner): honor selected Rust sources and simplify terminal titles`

- lib/cargo_targets.dart
- lib/native_miri_runner.dart
- lib/rust_run_title.dart
- lib/rust_runner.dart
- test/cargo_process_wiring_test.dart
- test/cargo_targets_test.dart
- test/rust_app_test.dart
- test/rust_editor_run_test.dart

The current task PRD/design/execution plan and reviewed evidence can be recorded with the work commit. .trellis/spec is intentionally ignored by .gitignore:98; its locally updated run-control contract is not force-added.

## Other existing dirty paths (excluded from this proposed scope)

- ` M .gitignore`
- ` M .trellis/tasks/09-30-rust-toolchain/task.json`
- ` M android/app/build.gradle.kts`
- ` M android/app/src/main/kotlin/com/example/qflistudio/c/MainActivity.kt`
- ` M ios/Runner.xcodeproj/project.pbxproj`
- ` M ios/Runner/AppDelegate.swift`
- ` M lib/main.dart`
- ` M lib/ohos_miri_assets.dart`
- ` M lib/ohos_miri_runner.dart`
- ` M linux/CMakeLists.txt`
- ` M macos/Runner.xcodeproj/project.pbxproj`
- ` M macos/Runner/MainFlutterWindow.swift`
- ` M native/README.md`
- ` M native/miri_adapter/abi_test.c`
- ` M native/miri_adapter/qfli_miri.h`
- ` M native/miri_adapter/src/lib.rs`
- ` M ohos/entry/src/main/ets/entryability/EntryAbility.ets`
- ` M ohos/entry/src/main/resources/base/profile/main_pages.json`
- ` M pubspec.lock`
- ` M pubspec.yaml`
- ` M scripts/build_miri_adapter.sh`
- ` M scripts/check_miri_source.sh`
- ` M scripts/prepare_miri_sysroot.sh`
- ` M windows/CMakeLists.txt`
- `?? .codex/agents/trellis-check.toml`
- `?? .codex/agents/trellis-implement.toml`
- `?? .codex/agents/trellis-research.toml`
- `?? .codex/config.toml`
- `?? .codex/hooks.json`
- `?? .codex/hooks/inject-subagent-context.py`
- `?? .codex/hooks/inject-workflow-state.py`
- `?? .codex/hooks/session-start.py`
- `?? .gitattributes`
- `?? .trae/agents/trellis-check.md`
- `?? .trae/agents/trellis-implement.md`
- `?? .trae/agents/trellis-research.md`
- `?? .trae/commands/trellis-continue.md`
- `?? .trae/commands/trellis-finish-work.md`
- `?? .trae/hooks.json`
- `?? .trae/hooks/inject-shell-session-context.py`
- `?? .trae/hooks/inject-workflow-state.py`
- `?? .trae/hooks/session-start.py`
- `?? .trae/skills/trellis-before-dev/SKILL.md`
- `?? .trae/skills/trellis-brainstorm/SKILL.md`
- `?? .trae/skills/trellis-break-loop/SKILL.md`
- `?? .trae/skills/trellis-channel/SKILL.md`
- `?? .trae/skills/trellis-channel/references/command-reference.md`
- `?? .trae/skills/trellis-channel/references/forum.md`
- `?? .trae/skills/trellis-channel/references/progress-debugging.md`
- `?? .trae/skills/trellis-channel/references/workers.md`
- `?? .trae/skills/trellis-channel/references/workflows.md`
- `?? .trae/skills/trellis-check/SKILL.md`
- `?? .trae/skills/trellis-meta/SKILL.md`
- `?? .trae/skills/trellis-meta/references/customize-local/add-project-local-conventions.md`
- `?? .trae/skills/trellis-meta/references/customize-local/change-agents.md`
- `?? .trae/skills/trellis-meta/references/customize-local/change-context-loading.md`
- `?? .trae/skills/trellis-meta/references/customize-local/change-hooks.md`
- `?? .trae/skills/trellis-meta/references/customize-local/change-skills-or-commands.md`
- `?? .trae/skills/trellis-meta/references/customize-local/change-spec-structure.md`
- `?? .trae/skills/trellis-meta/references/customize-local/change-task-lifecycle.md`
- `?? .trae/skills/trellis-meta/references/customize-local/change-workflow.md`
- `?? .trae/skills/trellis-meta/references/customize-local/overview.md`
- `?? .trae/skills/trellis-meta/references/local-architecture/bundled-skills.md`
- `?? .trae/skills/trellis-meta/references/local-architecture/context-injection.md`
- `?? .trae/skills/trellis-meta/references/local-architecture/generated-files.md`
- `?? .trae/skills/trellis-meta/references/local-architecture/multi-agent-channel.md`
- `?? .trae/skills/trellis-meta/references/local-architecture/overview.md`
- `?? .trae/skills/trellis-meta/references/local-architecture/spec-system.md`
- `?? .trae/skills/trellis-meta/references/local-architecture/task-system.md`
- `?? .trae/skills/trellis-meta/references/local-architecture/workflow.md`
- `?? .trae/skills/trellis-meta/references/local-architecture/workspace-memory.md`
- `?? .trae/skills/trellis-meta/references/platform-files/agents.md`
- `?? .trae/skills/trellis-meta/references/platform-files/hooks-and-settings.md`
- `?? .trae/skills/trellis-meta/references/platform-files/overview.md`
- `?? .trae/skills/trellis-meta/references/platform-files/platform-map.md`
- `?? .trae/skills/trellis-meta/references/platform-files/skills-and-commands.md`
- `?? .trae/skills/trellis-session-insight/SKILL.md`
- `?? .trae/skills/trellis-session-insight/references/cli-quick-reference.md`
- `?? .trae/skills/trellis-session-insight/references/triggering-patterns.md`
- `?? .trae/skills/trellis-spec-bootstrap/SKILL.md`
- `?? .trae/skills/trellis-spec-bootstrap/references/mcp-setup.md`
- `?? .trae/skills/trellis-spec-bootstrap/references/repository-analysis.md`
- `?? .trae/skills/trellis-spec-bootstrap/references/spec-task-planning.md`
- `?? .trae/skills/trellis-spec-bootstrap/references/spec-writing.md`
- `?? .trae/skills/trellis-update-spec/SKILL.md`
- `?? .trellis/tasks/10-01-cross-platform-rust-runtime/check.jsonl`
- `?? .trellis/tasks/10-01-cross-platform-rust-runtime/design.md`
- `?? .trellis/tasks/10-01-cross-platform-rust-runtime/implement.jsonl`
- `?? .trellis/tasks/10-01-cross-platform-rust-runtime/implement.md`
- `?? .trellis/tasks/10-01-cross-platform-rust-runtime/prd.md`
- `?? .trellis/tasks/10-01-cross-platform-rust-runtime/research/cross-platform-native.md`
- `?? .trellis/tasks/10-01-cross-platform-rust-runtime/task.json`
- `?? .trellis/tasks/archive/2026-10/10-01-tutorial-code-import/apply-shared.ps1`
- `?? .trellis/tasks/archive/2026-10/10-01-tutorial-code-import/count.patch`
- `?? .trellis/tasks/archive/2026-10/10-01-tutorial-code-import/evict.patch`
- `?? .trellis/tasks/archive/2026-10/10-01-tutorial-code-import/generate-review.ps1`
- `?? .trellis/tasks/archive/2026-10/10-01-tutorial-code-import/review.patch`
- `?? .trellis/tasks/archive/2026-10/10-01-tutorial-code-import/review/snapshots/content_code_import_test.dart`
- `?? .trellis/tasks/archive/2026-10/10-01-tutorial-code-import/review/snapshots/local_content_pages.dart`
- `?? .trellis/tasks/archive/2026-10/10-01-tutorial-code-import/review/work/content_code_import_test.dart`
- `?? .trellis/tasks/archive/2026-10/10-01-tutorial-code-import/review/work/local_content_pages.dart`
- `?? .trellis/tasks/archive/2026-10/10-01-tutorial-code-import/screenshots/examples-1280-catalog.png`
- `?? .trellis/tasks/archive/2026-10/10-01-tutorial-code-import/screenshots/examples-1280-detail.png`
- `?? .trellis/tasks/archive/2026-10/10-01-tutorial-code-import/screenshots/examples-1280-dialog.png`
- `?? .trellis/tasks/archive/2026-10/10-01-tutorial-code-import/screenshots/examples-390-catalog.png`
- `?? .trellis/tasks/archive/2026-10/10-01-tutorial-code-import/screenshots/examples-390-detail.png`
- `?? .trellis/tasks/archive/2026-10/10-01-tutorial-code-import/screenshots/examples-390-dialog.png`
- `?? .trellis/tasks/archive/2026-10/10-01-tutorial-code-import/screenshots/tutorials-1280-catalog.png`
- `?? .trellis/tasks/archive/2026-10/10-01-tutorial-code-import/screenshots/tutorials-1280-detail.png`
- `?? .trellis/tasks/archive/2026-10/10-01-tutorial-code-import/screenshots/tutorials-1280-dialog.png`
- `?? .trellis/tasks/archive/2026-10/10-01-tutorial-code-import/screenshots/tutorials-390-catalog.png`
- `?? .trellis/tasks/archive/2026-10/10-01-tutorial-code-import/screenshots/tutorials-390-detail.png`
- `?? .trellis/tasks/archive/2026-10/10-01-tutorial-code-import/screenshots/tutorials-390-dialog.png`
- `?? .trellis/tasks/archive/2026-10/10-01-tutorial-code-import/snapshots/editor_page.dart`
- `?? .trellis/tasks/archive/2026-10/10-01-tutorial-code-import/snapshots/home_page.dart`
- `?? .trellis/tasks/archive/2026-10/10-01-tutorial-code-import/snapshots/local_content_pages.dart`
- `?? .trellis/tasks/archive/2026-10/10-01-tutorial-code-import/snapshots/project_store.dart`
- `?? .trellis/tasks/archive/2026-10/10-01-tutorial-code-import/snapshots/studio_localizations.dart`
- `?? .trellis/tasks/archive/2026-10/10-01-tutorial-code-import/work/code_import_service.dart`
- `?? .trellis/tasks/archive/2026-10/10-01-tutorial-code-import/work/code_snippet_block.dart`
- `?? .trellis/tasks/archive/2026-10/10-01-tutorial-code-import/work/editor_page.dart`
- `?? .trellis/tasks/archive/2026-10/10-01-tutorial-code-import/work/home_page.dart`
- `?? .trellis/tasks/archive/2026-10/10-01-tutorial-code-import/work/local_content_pages.dart`
- `?? .trellis/tasks/archive/2026-10/10-01-tutorial-code-import/work/project_store.dart`
- `?? .trellis/tasks/archive/2026-10/10-01-tutorial-code-import/work/studio_localizations.dart`
- `?? AGENTS.md`
- `?? integration_test/rust_native_test.dart`
- `?? lib/native_miri_assets.dart`
- `?? linux/flutter/generated_plugin_registrant.cc`
- `?? linux/flutter/generated_plugin_registrant.h`
- `?? macos/Flutter/GeneratedPluginRegistrant.swift`
- `?? native/runtime_bundle.cmake`
- `?? ohos/entry/src/main/ets/pages/AgreementReader.ets`
- `?? scripts/build_miri_adapter.ps1`
- `?? scripts/build_rustc_host.py`
- `?? scripts/check_native_packaging.py`
- `?? scripts/embed_miri_frameworks.py`
- `?? scripts/embed_miri_frameworks.sh`
- `?? scripts/miri_build_support.py`
- `?? scripts/package_miri_runtime.py`
- `?? scripts/prepare_miri_windows.py`
- `?? scripts/test_build_rustc_host.py`
- `?? test/native_miri_assets_test.dart`
- `?? test/native_miri_integration_test.dart`
- `?? test/native_miri_runner_test.dart`
- `?? windows/flutter/generated_plugin_registrant.cc`
- `?? windows/flutter/generated_plugin_registrant.h`

## Final user decision

On 2026-10-09 the user explicitly selected: keep this turn's changes and do not commit. No staging, commits or automatic commit/archive/journal operations were performed. Implementation and verification are complete; the task remains available for later integration with the pre-existing runtime work.
