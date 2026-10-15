# Rust terminal / offline — final read-only review

Reviewer: Herdr wB rust-terminal. Task: .trellis/tasks/10-15-rust-release-readiness.
Mode: **read-only**. No source modified, no Flutter run, no staging/commit.
Terminal work reviewed at committed `c2bc7b9`; core offline followup at `b7b2d2e`.

## 1. Both terminal surfaces — verified wired

The single profile hook reaches every Rust terminal:

| Surface | Wiring | Status |
| --- | --- | --- |
| Editor pane | `terminal_pane.dart:440` `delegate: StudioProfile.current?.terminalCommandDelegate` | OK |
| Standalone / quick-tools | `terminax_terminal_page.dart:42,109` → `TerminalManager.commandDelegate = StudioProfile.current?.terminalCommandDelegate` | OK |
| Product hook | `lib/main.dart:34` `terminalCommandDelegate: rustTerminalCommandDelegate` | OK |

The standalone page has **no** online/ApiClient/auth surface at all (grep: no
`online`, `ApiClient`, `auth` references), so it cannot leak the network. The
editor pane's online toggle is gated by `onlineEnabled: offlineOnly != true`
(`editor_page.dart:1895`) and every online method early-returns on
`!widget.onlineEnabled`.

Committed test `test/rust_terminal_commands_test.dart` asserts delegate sharing
through `TerminalManager` and the shipped-profile hook (29 tests, green in
batch 4). No regression.

## 2. Core offline followup `b7b2d2e` — verified

- Background task refresh / sync gated by `offlineOnly` (`home_page.dart:324,343`;
  `task_activity_service.dart` refresh/sync/pending paths).
- Profile self-refresh gated (`profile_page.dart:48`).
- Terminal shortcut bar hides `网络工具` and `git status` offline
  (`shortcut_bar.dart:433,451`); help text made product-agnostic.
- New core test `offline_background_and_shortcuts_test.dart` exercises these.

Earlier finding now resolved: the editor `Git`/cloud-pull menu items are
double-gated in current core (`editor_page.dart:1432-1446` case guards and
`:1595,1663` menu-item guards). Online-terminal and AI items likewise.

## 3. Real remaining issue (Rust-owned, one)

### ISSUE-1 — `RustProgramRunner` can be defeated by a host `CARGO_NET_OFFLINE=false`

`lib/rust_runner.dart:159-160`:

```dart
Map<String, String> get _baseEnvironment => offline
    ? {...environment,
       if (!environment.containsKey('CARGO_NET_OFFLINE'))
         'CARGO_NET_OFFLINE': 'true'}
    : environment;
```

`environment` in production is `{...Platform.environment}` (runner is
constructed as `RustProgramRunner()`, line 92/mai.dart). Because the guard only
adds the variable when the key is absent, a developer/host shell that exports
`CARGO_NET_OFFLINE=false` **wins over the profile's `offlineOnly: true`**.

Verified empirically with the bundled cargo 1.98.1: with
`CARGO_NET_OFFLINE=false` and no `--offline`, `cargo build` prints
`Updating crates.io index` — a real network operation — then fails on the
missing crate. So the runner's own documented contract ("Disallows every Cargo
network operation when true") is not upheld in that environment.

Impact: editor **Run button** and the terminal's `rust run <file.rs>` (both go
through `RustProgramRunner`). Raw `cargo`/`rustc` typed in the terminal are
**not** affected: the delegate force-sets `CARGO_NET_OFFLINE=true` (later map
key wins) and prepends `--offline`, which was verified to beat
`--config net.offline=false`.

Suggested fix (coordinator/implementer, one line): force the value —
`{...environment, if (offline) 'CARGO_NET_OFFLINE': 'true'}` — and additionally
pass `--offline` on the runner's `cargo metadata` / `cargo run` argument lists
so the policy does not depend on the environment alone.

Note: the committed test "RustProgramRunner sets CARGO_NET_OFFLINE for offline
cargo" passes a no-dependency project, so it passes even when the override is
defeated; it does not currently prove the guard. It should assert with a
networked/missing dependency (as the delegate tests already do) to close the
gap.

## 4. Non-issues / scoped observations (no action for Rust)

- `native_miri_assets.dart:101` `UnsupportedError` is the honest "no runtime for
  this platform/arch" branch, not a stub. `ohos_miri_assets.dart` /
  `ohos_miri_runner.dart` are compatibility shims over the shared native files.
- `RustContentRepository` reads only bundled assets (no network);
  `RustProjectStore` is filesystem-only.
- Raw arbitrary shell commands on **desktop** still fall through to the real
  shell (`createSandboxShell` desktop parity), so an offline desktop user can
  type `curl`/`git`. The in-app shortcut surface for these is hidden offline
  (core `b7b2d2e`), which is the product intent; blocking the raw shell is a
  shared-core decision, not Rust-owned. Recorded, not flagged.
- `_openOnlineTerminal()` lacks its own `offlineOnly` guard, but it is
  unreachable offline (menu item hidden + `showOnline()` early-returns on
  `!onlineEnabled`); defense-in-depth holds.

## 5. Verdict

Both terminal paths are correctly wired to the Rust delegate and carry no
network surface of their own. Core `b7b2d2e` closed the previously reported
Git/background/shortcut leaks. **One real Rust-owned issue remains
(ISSUE-1, host-`CARGO_NET_OFFLINE=false` override of the runner's offline
policy)**; everything else is complete for the Rust terminal/offline scope.

## 6. Resolution and coordinator verification

ISSUE-1 was corrected after this review: the runner forces the offline
environment value and prepends `--offline` for both metadata and execution.
The replacement regression uses a genuinely missing dependency, fresh Cargo
home, inherited `CARGO_NET_OFFLINE=false` and conflicting local config. It
requires the offline diagnostic and forbids an index-update message. A second
case preserves environment policy when explicit offline mode is disabled.

Coordinator executed terminal, Cargo process wiring and Rust app regressions
with the real bundled compiler: **65 passed, zero failures/skips**. Log:
`build/terminal-final-tests.log`. The finding above is resolved.
