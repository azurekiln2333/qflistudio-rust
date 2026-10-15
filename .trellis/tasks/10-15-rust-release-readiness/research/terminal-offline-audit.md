# Rust terminal + offline audit (rust-terminal, 2026-10-15)

Owner: Herdr wB `rust-terminal`. Scope: Rust terminal command delegation and a
read-only audit of the shared offline (`offlineOnly` / `isOffline`) guards.
Shared core (`../qfli_studio_core`) was **read only, not modified**.

## 1. Rust terminal command delegate

### What shipped

- New `lib/rust_terminal_commands.dart` exports
  `rustTerminalCommandDelegate`, a `TerminalCommandDelegate`
  (`Future<bool> Function(SandboxShellBackend, String)`).

| Command | Behaviour |
| --- | --- |
| `rust run <file.rs>` / `rust <file.rs>` | Resolves the operand inside the sandbox, rejects escape/non-`.rs`, then runs through `RustProgramRunner`: desktop = real `rustc`/`cargo`; Android/iOS/HarmonyOS = packaged upstream rustc/Miri. stdout/stderr/exit forwarded unchanged, cancellation forwarded. |
| `rustc ...` | Real `Process.start('rustc', ...)` with the sandbox cwd and streamed output where a desktop CLI exists. |
| `cargo ...` | Real `Process.start('cargo', ...)`, same as above. |
| unknown / compound line | Returns `false` so the sandbox keeps its own honest diagnostic. |

Truthfulness rules enforced:

- A platform without an exec-able compiler CLI (mobile) reports
  `kProgramNotRunExitCode` (127) with an explicit message; it never fabricates a
  version string or a successful exit.
- Missing source, non-`.rs` operand, unsupported option, wrong arity, and
  sandbox escape each produce a 127 failure with an explanatory line and no
  stdout.
- No whole-shell reimplementation: only the three Rust tools are claimed.

### Wiring the coordinator must apply (main.dart is coordinator-owned)

Add to `lib/main.dart`:

```dart
import 'package:qfli_studio_core/terminal/shell/sandbox_shell_backend.dart';
import 'rust_terminal_commands.dart';

// inside `rustProfile`:
terminalCommandDelegate: rustTerminalCommandDelegate,
```

`StudioProfile.terminalCommandDelegate` is the single seam used by **both**
terminal surfaces:

- editor pane: `qfli_studio_core/lib/editor/terminal_pane.dart` `_backendFor()`
  passes `StudioProfile.current?.terminalCommandDelegate`.
- app-level terminal: `qfli_studio_core/lib/pages/terminax_terminal_page.dart`
  `initState`/`_createSession` set
  `TerminalManager.commandDelegate = StudioProfile.current?.terminalCommandDelegate`.

So one profile line wires the editor terminal, the app-level terminal, and the
quick-tools local terminal (`LocalTerminalPage` → `TerminaxTerminalPage`).

### Tests

`test/rust_terminal_commands_test.dart` (10 tests, all passing):

- claims `rust`/`rustc`/`cargo`, declines `javac`/`python`/`ls`/`rustup` and
  compound lines.
- parameter failures: no operand, too many operands, `--release`, non-`.rs`,
  sandbox escape, missing source — each asserts 127 + diagnostic + empty stdout.
- real execution: `rust run` stdout/exit, `rustc --version`, `cargo --version`
  (skipped when no host compiler is installed; a skipped test is never reported
  as a pass).
- shared delegation: a `TerminalManager`-created session routes `rust run main.rs`
  through the profile delegate, proving both surfaces share one delegate.

Host status: **no `rustc`/`cargo` on this machine** (checked PATH, `~/.cargo`,
rustup), so the three real-compiler tests skip. They are skipped, not faked.

## 2. Offline audit (read-only)

Entry points that must be unreachable when `StudioProfile.offlineOnly == true`
(Rust sets `isOffline: true`, so `offlineOnly` defaults to `true`).

| Entry | Guard site | Status |
| --- | --- | --- |
| Login / register / account | `profile_page.dart:81,97-103,196,217,228` hide header + login/logout + admin + ICP footer | guarded |
| Settings AI section | `editor_page.dart:1418` `showAi: offlineOnly != true` | guarded |
| AI assistant menu item | `editor_page.dart:1625` | guarded |
| Online terminal menu item | `editor_page.dart:1646` | guarded |
| Editor embedded online terminal toggle | `editor_page.dart:1881` `onlineEnabled: offlineOnly != true` | guarded |
| Online fallback after local run fails | `editor_page.dart:1092,1116` | guarded |
| Cloud SQL run (`.sql`) | `editor_page.dart:1001` | guarded |
| Cloud project creation menu item | `home_page.dart:430` | guarded |
| Cloud project scope tab + list | `home_page.dart:308` (scopes exclude `cloud`), `550` (filter `isCloud`), `700` (skip remote fetch) | guarded |
| Community tutorial/discussion tabs | `home_page.dart:99-104` swaps to `LocalTutorialsTab` under `offlineOnly` | guarded |
| Cloud project pull menu item | `editor_page.dart` gated by `widget.project.isCloud`; unreachable because cloud projects are filtered out | guarded transitively |

### Finding: editor Git entry is not offline-gated (core-owned)

`editor_page.dart:1586` always offers the `Git` menu item and `_openGit()`
(`:590`) pushes `GitPage` regardless of `offlineOnly`. `GitPage`
(`pages/git_page.dart`) runs local `git` on desktop **and** server-side git for
cloud projects (`CloudSyncService`), i.e. network operations.

- Impact for Rust: low on mobile (no cloud projects reach the project list, and
  no exec-able git), but the menu item is still shown, so an offline-only
  product advertises a surface whose cloud half needs the network.
- Recommended core fix (coordinator, since `qfli_studio_core` is read-only for
  this task): hide the `git` menu item when
  `StudioProfile.current?.offlineOnly == true`, matching the `ai` /
  `online_terminal` items.
- Rust-side mitigation available without core edits: none clean — the menu is
  drawn by the shared editor. Recorded here rather than patched.

### Finding: cloud-terminal / community network calls are backend-gated, not UI-only

`ApiClient`/`OnlineProgram` calls remain callable, but every UI entry into them
is guarded above. No unguarded reachable path was found from the Rust profile.

### Rust-side offline enforcement (this agent, batch 2)

The Rust runner now enforces offline itself rather than relying on UI hiding:

- `RustProgramRunner` gained `offline` (null → `StudioProfile.current.offlineOnly`);
  `cargo metadata` and `cargo run` receive `CARGO_NET_OFFLINE=true`, so Cargo
  refuses every fetch/index operation.
- The terminal delegate refuses networked cargo subcommands
  (`login`/`publish`/`search`/`install`/`info`/`owner`/...) under `offlineOnly`.

## 3. Runner completeness notes

- `RustProgramRunner` and `NativeMiriProgramRunner` already implement the
  `qfli_studio_core` `ProgramRunner` contract with cancellation, input.txt,
  title, and 127 startup failures. No runner change was required for the
  terminal delegate; it reuses `RustProgramRunner.run` directly.
- No new runner file was modified; `lib/rust_runner.dart`, `lib/cargo_targets.dart`
  and `lib/native_miri_runner.dart` were left at their pre-existing (uncommitted)
  state to avoid clobbering parallel work.

## 4. Remaining blockers

1. No host `rustc`/`cargo` — real compile/run execution is unverified on this
   machine (tests skip). Coordinator to install a host toolchain or record the
   gap.
2. `main.dart` profile wiring (`terminalCommandDelegate`) not applied — outside
   this agent's write scope.
3. Editor Git menu is not offline-gated in shared core (core change required).
