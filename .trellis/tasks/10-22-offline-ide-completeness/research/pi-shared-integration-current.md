# Shared-core integration: current seams for Rust (R3/R4/R5/R6/R7/R10)

> Historical read-only findings below describe the earlier checkpoint.
> Current 2026-10-23 corrections: tools and analyzer are wired and tested;
> both OHOS analysis libraries were rebuilt/packaged (not device-executed);
> core owner fixed secondary-root Run in 0ec321c; debugger ABI/Dart adapter and
> core panels are now under implementation. Ports remains an open feasible
> local-only requirement; the old "not applicable" recommendation is rejected.
> Use acceptance.md and progress-2026-10-23.md for current evidence.

Date: 2026-10-22. Independent read-only audit for
`.trellis/tasks/10-22-offline-ide-completeness`. No shared-core, sibling product,
`lib/` source, git state or other worker's file was modified. Nothing below is a
completion claim; unverified items are labelled **UNVERIFIED** or **BLOCKED**.

Toolchain correction: this host is **no longer** compiler-less.
`native/build/miri-windows/compiler/bin/rustc.exe` exists and reports
`rustc 1.98.1 (48a229cea 2026-09-01)` (cargo.exe also present), and
`RustCodeAnalyzer.discoverRustc()` (`lib/rust_code_analyzer.dart:55-74`) already
pins that exact path. I did not execute any compilation (read-only mandate), so
Rust *language semantics* items stay **UNVERIFIED** in this report, but they are
now cheaply verifiable by the workers/root with that binary.

## 0. What the user requires, restated from research/user-request.txt

Per-requirement anchor (PRD R-ids, `prd.md`):
language chip filter + circular language badges on tutorial **and** example pages
(R3); language-unique tools flat on the tools page, no second-level hub (R4);
in-editor squiggles + accurate offline code checking (R5); sidebar no longer resets
expansion, VSCode-like workspace with several projects in one sidebar (R6);
VSCode-style panels — Problems / Output / Debug Console / Terminal / Ports — plus
real debugging, offline only (R7); highlighting for every language; all example
code must actually run on the current OHOS toolchain (R1/R2); offline-only products
(R10). All of this must be delivered **through the shared core the C coordinator
owns** — "我怕你们互抢共享核心导致混乱".

## 1. Ledger: is each shared surface present, and is Rust wired to it?

| Surface | Core state (source) | Rust state (source) | Verdict |
| --- | --- | --- | --- |
| Language chips + badges (R3) | `pages/local_content_pages.dart:266-268,375-379` (`_ContentFilterBar`), `:320-323,362-365` (`_filter.matches(language:, query:, level:)`), `:418-419` `_contentLanguage`, `widgets/language_badge.dart:3-8` `languageKey/languageLabel`, `LanguageBadge` used in titles | `assets/content_rust/*.json` carry `language: rust`, `type: rust`, `level`; adapter `lib/content/local_content_adapter.dart:52-54,95-97` passes them through; `main.dart:37` `contentRepositoryFactory` → `home_page.dart:59-60,247-252` | **Wired, single-language** (chips show only Rust; no multi-language set to intersect). Rust cannot test R3's C/C++ intersection — that evidence is C-owned (R8/umbrella). |
| Direct tools page (R4) | `studio_profile.dart:156-159` `toolsTabBuilder`; `pages/tools_grid.dart:38` `commonTools`, `:154-195` `ToolsGridSliver`, `:198` **private** `_OfflineNote` | `lib/rust_tools_tab.dart:11-24` `RustToolsTab(store:, onOpenTerminal:, inspectorFactory:)`, `:185` `ToolsGridSliver(tools: commonTools)`, `AutomaticKeepAliveClientMixin` `:27-43` | **Implemented, NOT wired**: `lib/main.dart:28-45` still has no `toolsTabBuilder`. R4 evidence is currently zero. |
| Editor analysis (R5, desktop) | `services/code_analysis.dart` contract; `editor/editor_analysis_controller.dart:150-190` owner-aware snapshot build (`root = _path(active.projectRootPath)`, per-root file filter), `:196-260` accept/filter; `editor/editor_diagnostics.dart` squiggles; `editor/editor_problems_bar.dart` Problems bar+panel | `lib/rust_code_analyzer.dart:37` `implements CodeAnalyzer`, `:122-215` mirror+rustc JSONL, process transport `:388` | **Implemented, NOT wired**: no `codeAnalyzer:` in `lib/main.dart`. |
| Editor analysis (R5, OHOS/Android) | ABI source has the analysis extension: `native/miri_adapter/qfli_miri.h:80-118`, `src/lib.rs:683-725`, `analysis_abi_test.c` | `lib/rust_code_analyzer.dart:202-216` `_resolveBackend()` throws `当前平台尚未提供离线 Rust 代码检查器`; `lib/native_miri_runner.dart:381-402` binds only `abi_version/create/create_with_backend/cancel/copy_output/result/destroy` | **BLOCKED twice**: (a) no Dart FFI binding for `qfli_miri_create_analysis`/`qfli_miri_analyze`; (b) no shipped binary exports them (see §4). |
| Multi-root workspace + retained expansion (R6) | committed `daddce2`: `editor/file_explorer.dart:112-135` `_workspace = [browsing] + _workspaceProjects`, `:970` `KeyedSubtree(key: ValueKey('workspace-root-<path>'))` (simultaneous roots), `:924` `工作区 · N 个项目`, `:205-275` `_manageWorkspace` + `ProjectHistory.saveWorkspaceRoots`; `editor/project_history.dart:88-110,217-232,292-306` `workspaceRoots`/`documents`; `editor/editor_page.dart:325-370` restore resolves owner from `store.projects`; spec `.trellis/spec/frontend/offline-workspace.md` (C repo) | Rust needs **no** profile change; `RustProjectStore extends ProjectStore` supplies the project list used by `_manageWorkspace` | **Present and inheritable**, with one real defect that hits Rust first-class: **running a file owned by a secondary root fails** (§3.1). |
| Output / Debug Console / Ports (R7) | `editor/editor_page.dart:54` `enum _BottomPanel { none, terminal, ai, problems }` — that is the complete bottom-panel set. `terminal_pane.dart:979 attachOutput`, `:1043 appendDebug`, `:1051 appendSystem` are the only stream sinks. No `Output`, `DebugConsole`, `Ports` widget/service anywhere in core (grep) | `rust_terminal_commands.dart` delegates `rustc`/`cargo` on desktop only | **Gap is core-owned**: a product cannot add a panel — `_BottomPanel` is private and `StudioProfile` has no panel seam (`studio_profile.dart:118-216` field list). |
| Actual debugging (R7) | none in core | `native/miri_adapter/qfli_miri.h:10-17,39-44` states: READY/RUNNING/FINISHED/CANCELLED/LIMIT/ERROR + blocking `run`; `grep breakpoint|step|pause|resume` in `qfli_miri.h`/`src/lib.rs` finds nothing | **Not feasible today** (no pause/step/stack/variables, no DAP). Keep open per `design.md`; do not render simulated controls. |
| Offline-only (R10) | `studio_profile.dart:186-196` `isOffline`/`offlineOnly`; `home_page.dart` gates community/cloud/online terminal | `lib/main.dart:33` `isOffline: true`; terminal `_networkCargoCommands` refusal in `rust_terminal_commands.dart:121-135,247-256` | **Wired**; the new tools tab adds no process/network (integer/string tools pure; Cargo inspection uses `--offline` semantics or pasted metadata). |

## 2. Exact product integration seams (what root must land)

`lib/main.dart` `rustProfile` is the only file that can close R4/R5. Seam list:

```dart
// lib/main.dart (root-owned)
import 'rust_code_analyzer.dart';
import 'rust_tools_tab.dart';
...
  toolsTabBuilder: (store, onOpenTerminal) =>
      RustToolsTab(store: store, onOpenTerminal: onOpenTerminal),
  codeAnalyzer: RustCodeAnalyzer(),   // desktop only; reports unavailable elsewhere
```

Notes that matter for review:

1. `RustToolsTab` already keeps `commonTools` visible via
   `ToolsGridSliver` (`rust_tools_tab.dart:185`) and uses
   `AutomaticKeepAliveClientMixin`, so tab switches keep controller text. That
   satisfies R4's "flat, keeps shared tools" better than C's `ForgeToolsBody`,
   which drops `commonTools` entirely.
2. `RustCodeAnalyzer()` defaults `rustcPath` to the pinned Windows build. On
   Android/OHOS `_resolveBackend()` throws an explicit unavailable reason, which
   core renders as `unavailableReason` — **not** as clean code
   (`editor_problems_bar.dart:6-13`, contract in
   `offline-editor-analysis.md` §3). That is the honest state R5 allows today.
3. Do **not** add `toolsPageBuilder` for Rust: with `toolsTabBuilder` set, the old
   功能 entry disappears (`quick_tools_page.dart:39-56`), and a second route would
   break R4's "no detour".
4. `services=code_analysis` is re-exported through `studio_profile.dart`; the
   analyzer import can come from either package path, but import
   `package:qfli_studio_core/services/studio_profile.dart` to stay inside the
   re-export contract.

## 3. Defects found in the shared integration (all reproducible by reading)

### 3.1 BLOCKER (R6 × R1): a file from a secondary workspace root can never run

Two independent guards reject it:

- `editor/editor_page.dart:1235-1252` `_runActiveFile()` calls
  `_runProject(entryOverride: p.normalize(p.absolute(open!.path)))`, and
  `_activeFileRunError()` (`:1264-1268`) returns
  `'active file is outside the project'` because it compares against
  `widget.project.path` (the **primary** root), not `open.projectRootPath`.
- Even if it got through, `_runProject` sends
  `projectPath: widget.project.path` (`:1154`), and both Rust runners re-validate
  containment: `lib/rust_runner.dart:82` `!p.isWithin(root, entry)` →
  `'Rust 源文件不存在或不在项目中'`; `lib/native_miri_runner.dart:50` the same check
  on device.

Consequence: with a multi-root workspace (which R6 delivers), long-press Run on
`B/src/main.rs` fails on both desktop and device, and the run title would be
computed against the wrong root anyway (`rustRunTitle(root, entry)`,
`rust_runner.dart:50`).

Fix ownership: **core** (C), small and well-specified — `_runProject` should take
the owning root (e.g. `String? projectRootPath` from `open.projectRootPath`,
already available per tab: `editor/open_file.dart:32-38`) and pass it to
`RunnerService.runProject(projectPath: …)`; `_activeFileRunError` should validate
against the owner root, not `widget.project.path`. Rust-side alternative (worse):
resolve the owner from the nearest `Cargo.toml` ancestor — but the runner has no
`ProjectStore`, and `design.md` keeps entry authority in core.

### 3.2 Tap-Run semantics in a multi-root workspace (needs a documented decision)

Tap Run always runs `RunnerService.findEntry(widget.project.path)` +
`projectPath: widget.project.path` (`editor_page.dart:1061-1062,1154`). With
several roots that is "run the primary project", which is defensible, but the
terminal title and Problems navigation then describe a project the user may not be
looking at. Either document it as intended or make tap-Run follow the active tab's
owner (consistent with §3.1's fix). Untracked either way — today no test covers
tap-Run with a secondary-root active tab.

### 3.3 `_BottomPanel` is closed to products (R7 structural gap)

`enum _BottomPanel { none, terminal, ai, problems }` (`editor_page.dart:54`) plus a
private `_terminalKey`. `StudioProfile` has no `panelsBuilder`/`outputPanel` field
(`studio_profile.dart:118-216`). Therefore:

- **Output**: not available. The nearest existing thing is
  `TerminalPaneState.appendSystem` (`terminal_pane.dart:1051`) — a terminal line,
  not a separate channel. `ProcessSupervisor`-managed processes (`managedProcess`
  in `RunResult`) are attached to the terminal only
  (`terminal_pane.dart:943-1042`).
- **Debug Console**: only `appendDebug` (`:1043`), used by the web preview
  console forwarder (`editor_page.dart:1120-1124`). Rust has no debug channel.
- **Ports**: nothing in core. Ports only make sense for products that listen
  (qfli_web's loopback preview, `../qfli_web/lib/pages/web_tools_page.dart:377,474`);
  the Rust runner spawns a compiler/process, never a listener. Honest conclusion:
  **Ports is not applicable to Rust** and should be recorded as such rather than
  faked.

If the umbrella still wants a shared Output/Problems/Debug Console tab strip, that
is one core change (add `outputPanelBuilder`/panel enum value + a `RunResult`
output-tap), owned by C — Rust must not fork `EditorPage`.

### 3.4 Packaging: the analysis ABI is in source but in no shipped binary

Byte-level check (read-only) of every candidate `libqfli_miri.so`:

| Binary | mtime | `qfli_miri_create_analysis` / `qfli_miri_analyze` | `qfli_miri_create_with_backend` |
| --- | --- | --- | --- |
| `ohos/entry/libs/arm64-v8a/libqfli_miri.so` (= packaged `d409527a…`) | 2026-10-15 18:36 | **absent** | present |
| `ohos/entry/libs/x86_64/libqfli_miri.so` | — | **absent** | **absent** |
| `native/build/device/ohos-arm64/libqfli_miri.so` (same sha256 `d409527a…`) | 2026-10-15 18:36 | **absent** | present |
| `android/app/src/main/jniLibs/arm64-v8a/libqfli_miri.so` | 2026-10-02 | **absent** | present |

while `native/miri_adapter/src/lib.rs` (mtime 2026-10-22 17:47) and
`qfli_miri.h` (17:48) declare/define them, and `assets/miri/manifest.json`
`nativeLibraries` still pins `libqfli_miri.so d409527a…`. So R5 on OHOS needs, in
order: rebuild the adapter for `aarch64-unknown-linux-ohos` (+ x86_64 variant),
update the packaged libs **and** `assets/miri/manifest.json` hashes, then add the
Dart FFI bindings + `RustAnalysisTransport` implementation. Android's x64/arm64
runtime libs (10-02) predate even `create_with_backend`, so they cannot run the
current `NativeMiriProgramRunner` path that looks that symbol up — worth a
regression check by whoever owns the Android artifact.

## 4. Requirement-by-requirement integration verdict

- **R3 (filters/badges)**: core surface complete and Rust data feeds it
  (`language/type/level` present in both catalogs). Rust's single-language app can
  only prove "chip + badge render and filter their one language"; the multi-language
  intersection evidence must come from Forge (C) — do not claim it from Rust.
- **R4 (flat tools)**: code ready (`rust_tools_tab.dart`), **evidence blocked on the
  root wiring** (§2). Verify with a widget test asserting
  `rustProfile.toolsTabBuilder != null` plus mounted `RustToolsTab` rendering the
  9 `commonTools` titles at 320/1024 × 1×/2× (pattern:
  `../qfli_c/test/forge_tools_test.dart:131-186`).
- **R5 (diagnostics)**: desktop provider is real and owner-aware through core
  (`editor_analysis_controller.dart:150-190` uses `active.projectRootPath`, so a
  secondary-root tab is analyzed against its own root — no Rust work needed).
  Remaining: root wiring; device path blocked by §3.4. Squiggle/Problems navigation
  are core-rendered (`editor_diagnostics.dart`, `editor_problems_bar.dart`), so
  Rust's only obligation is correct UTF-16 half-open ranges + truthful
  `unavailableReason` (`lib/rust_compiler_diagnostics.dart`).
- **R6 (explorer/workspace)**: core committed the multi-root session; expansion,
  per-root flags and tab ownership persist (`offline-workspace.md`). Rust inherits
  it. **But** §3.1 makes the new workspace non-functional for running Rust
  programs in a secondary root — file it against C before R6 is called done.
- **R7 (panels/debug)**: Terminal + Problems exist; Output/Debug Console/Ports do
  not, and the debugger ABI does not exist. Recommended honest scope: keep
  Terminal (real streams/cancel) and Problems (real rustc diagnostics), record
  "Output/Debug Console require a core panel seam (C-owned)" and "Ports not
  applicable to Rust", and leave actual breakpoint debugging open per `design.md`.
- **R10 (offline)**: `offlineOnly` handling is in place; the new tools tab performs
  no network I/O and no source writes (`rust_tools_tab.dart` only reads the
  selected project's `Cargo.toml`; `rust_tool_utilities.dart` inspector is a
  read-only metadata path).

## 5. Verification commands the owners can run (I did not run these)

```powershell
# shared core (C owner)
cd D:\MyNewProjects\qfli_studio_core
flutter test test/workspace_editor_session_test.dart test/file_explorer_state_test.dart `
             test/project_history_concurrency_test.dart test/editor_analysis_test.dart

# Rust (root)
cd D:\MyNewProjects\qfli_rust
flutter test test/rust_tools_tab_test.dart test/rust_code_analyzer_test.dart `
             test/rust_compiler_diagnostics_test.dart
# semantics spot-checks now possible with the pinned toolchain
native\build\miri-windows\compiler\bin\rustc.exe --version --verbose
```

Recommended new regression for §3.1 (core-owned):
open root A + root B in one workspace, activate `B/src/main.rs`, long-press Run,
assert the run reaches `RunnerService.runProject` with `projectPath == B` and the
title is `run src/main.rs` (not a cross-root or "outside the project" error).

## 6. Remaining blockers (ordered)

1. **Root wiring in `lib/main.dart`** (`toolsTabBuilder:`, `codeAnalyzer:`) — without
   it R4 and R5-desktop have no evidence at all. Small, root-owned, no core change.
2. **§3.1 secondary-root run** — core-owned (`editor_page.dart:1154,1265-1267`);
   R6 acceptance otherwise hides a functional regression that only appears once
   the workspace feature lands.
3. **§3.4 stale native adapter** — rebuild + manifest hash update + Dart FFI
   bindings before any OHOS analysis claim; Android libs additionally lack
   `create_with_backend`.
4. **R7 panel seam** — core-owned decision. Until then, do not display Output /
   Debug Console / Ports as product features.
5. **Actual debugging** — unsupported by the ABI; keep open, no simulated UI.
