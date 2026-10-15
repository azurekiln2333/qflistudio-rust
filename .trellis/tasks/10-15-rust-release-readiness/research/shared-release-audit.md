# Research: Shared core, offline surfaces, and genuine Rust runtime readiness

- Query: Compare standalone and editor terminals; identify offline networking leaks, incomplete/fake runtime behavior, and the native engines actually packaged for Android/OHOS.
- Scope: internal, read-only source/asset inspection of `D:/MyNewProjects/qfli_rust` and `D:/MyNewProjects/qfli_studio_core`.
- Date: 2026-10-15
- Ownership: this report only. No source, shared core, platform configuration, or Git operations were performed by this researcher.
- Snapshot caveat: other sessions are actively editing shared core; line references identify the source read during this audit and can move.

## Findings

### Concrete release gaps

1. **Neither terminal exposes the Rust toolchain yet.** `lib/main.dart:26` configures `RustProgramRunner` but omits `terminalCommandDelegate`. `../qfli_studio_core/lib/services/studio_profile.dart:151` explicitly makes the delegate the language-command extension. Standalone `pages/terminax_terminal_page.dart:42,109` and embedded `editor/terminal_pane.dart:436` both forward this same delegate into the shared sandbox. `terminal/shell/sandbox_shell_backend.dart:223` invokes the handler or prints unsupported. Thus `cargo`, `rustc`, and execution commands in the terminal currently have no Rust implementation, even though the editor Run button can invoke Rust. This is a product integration gap, not an absent shared interface.

2. **Git is still visible in the offline product.** `../qfli_studio_core/lib/editor/editor_page.dart:1585` has an unconditional `PopupMenuItem(value: 'git')`. `_openGit` around line 590 also has no offline guard. `pages/git_page.dart:260` renders remote configuration, push, and pull whenever local desktop Git or cloud Git is supported; it does not consult the profile. `services/git_service.dart:22` directly starts Git, with push/pull helpers at lines 57/59 and no offline guard. Android/OHOS local Git is unsupported, but its dead page is still reachable; desktop Rust exposes real networking actions.

3. **The profile settings route leaks AI network configuration.** `../qfli_studio_core/lib/pages/profile_page.dart:58` builds `SettingsPage` without `showAi`. `pages/settings_page.dart:30` defaults it to true and lines 135-148 render the AI endpoint/API-key configuration entry. The editor settings route correctly derives `showAi` from `offlineOnly`; the profile route does not. This exposes a network-related product surface even though the editor AI menu itself is hidden.

4. **Offline profile refresh can still make a server request.** `pages/profile_page.dart:47` unconditionally calls `auth.refreshMe`; lines 91-94 retain its RefreshIndicator even in offline mode. `store/auth_store.dart:28` restores a trusted saved token from disk; `refreshMe` at line 101 calls `ApiClient.me` if it exists. Fresh installs without tokens do not trigger this request. An existing token plus a normal pull-to-refresh is a concrete reachable networking case.

5. **Desktop Cargo is not forced offline.** `lib/rust_runner.dart:229` invokes `cargo metadata` without `--offline`; `lib/cargo_targets.dart:228` constructs `cargo run` without `--offline`; neither sets `CARGO_NET_OFFLINE`. Dependency resolution/building can access registries or Git dependencies. The mobile source ABI does not execute Cargo and is unaffected by this particular issue. For an offline product, enforce offline mode at both metadata and build boundaries and document that user-authored desktop programs are a separate execution boundary.

6. **Current OHOS ARM64 package has no Rust engine.** The inspected `ohos/entry/libs/arm64-v8a/` contains only `libqfli_native_probe.so`. The active schema-1 `assets/miri/manifest.json` declares `x86_64-unknown-linux-ohos`; its three engine libraries are present only under `ohos/entry/libs/x86_64`. `NativeMiriAssets` validates the selected native host (`lib/native_miri_assets.dart:197`), so an ARM64 run rejects this x64 manifest before execution. Prior documentation that both architectures compiled is not evidence that ARM64 is currently packaged.

7. **Existing device integration tests are Android x64-specific.** `integration_test/rust_native_test.dart:28-33` asserts Android, host `x86_64-linux-android`, and an isolated Android test native-library path. It cannot be run unchanged as ARM64 or OHOS coverage. This is a test portability gap, not proof those engines fail execution.

### Terminal routing and intended differences

| Concern | Standalone terminal | Editor terminal |
| --- | --- | --- |
| UI/session owner | `pages/terminax_terminal_page.dart`, `terminal/state/terminal_manager.dart` | `editor/terminal_pane.dart` owns independent per-tab state |
| Backend | `createSandboxShell`, manager lines 44-51 | `createSandboxShell`, pane lines 432-441 |
| Language toolchain | `StudioProfile.current.terminalCommandDelegate` | The identical profile delegate |
| Initial directory | App private storage root (`terminax_terminal_page.dart:67`) | Current project directory (`terminal_pane.dart:438`) |
| File boundary | App private storage root | App private storage root with project start; external imported projects fall back to their own root (`sandbox_shell_backend.dart:32-48`) |
| Editor Run output | No direct Run-button attachment | `EditorPage -> RunnerService -> profile.runner -> attachOutput` |
| Online mode | Standalone Terminax page is local sandbox | Online mode exists but `onlineEnabled` follows `offlineOnly`; `showOnline` and `runOnlineProject` check it (pane lines 561,578) |

Shared file commands operate on actual files (`sandbox_shell_backend.dart:19`), not a virtual demonstration filesystem. Their missing pipeline/redirection/chaining/glob support is explicitly reported (`runExternal`/`_compoundConstruct`, lines 223 onward); implementing a real general-purpose shell is outside the current sandbox contract. Rust should implement its delegate in the Rust project, not copy shared terminal UI or patch other language profiles.

The core help/error wording still specifically says Java (`sandbox_shell_backend.dart:108,239`) when any delegate is installed. That is misleading for a future Rust delegate; coordinate a generic core wording fix with its owner rather than changing another language app.

### Offline behavior that already works

- `lib/main.dart:30` sets `isOffline: true`; `StudioProfile` constructor (`services/studio_profile.dart:111`) derives `offlineOnly` from it, so no redundant product flag is required.
- Home content/navigation uses offline pages (`pages/home_page.dart:99-103`); cloud scope is omitted (lines 307-310); persisted cloud projects are filtered around line 550; `_reloadProjects` exits before server calls (line 700).
- Profile login/account header, check-in, server admin, logout, and external ICP entry are excluded by `offlineOnly` (`pages/profile_page.dart:81-228`).
- Editor initializes cloud synchronization only when not offline (`editor/editor_page.dart:203`), hides AI/online-terminal menu entries (around lines 1625-1659), and prevents online fallback after local runtime failure (around lines 1092,1116).
- Terminal public online-entry methods check `onlineEnabled`; this is an operation guard at the UI service seam, beyond merely hiding a button.
- `AuthStore.load` is local disk IO only; the audit found no unconditional network request in bootstrap itself (`splash_screen.dart:69`, `auth_store.dart:28-52`).

These protections do **not** form a global network policy: `services/api_client.dart:129-146` sends ordinary HTTP requests without a profile guard, and `terminalEvents` at lines 647-659 uses a separate direct transport path. `AuthStore.refreshMe/updateProfile/signOut`, `GitService`, and `CloudSyncService` do not independently reject offline profiles. `ApiClient` hardening must cover both send paths if the core owner chooses a central policy. Merely calling a hidden service directly is a defense-depth concern; the Git/settings/refresh cases above have normal reachable UI triggers and are concrete gaps.

### Runtime implementation is genuine, with explicit limits

`lib/rust_runner.dart:43-59` selects embedded execution on OHOS, Android, and iOS; desktop automatic mode uses real Cargo/rustc subprocesses. Missing assets/libraries return a controlled not-run error (`rust_runner.dart:60,93`), not canned program output or a simulated interpreter.

The native chain is complete in source:

- `NativeMiriProgramRunner.run` validates project/source/sysroot/backend and limits (`lib/native_miri_runner.dart:38-85`).
- The session loads the dynamic library, checks ABI 1, creates the session, invokes a worker isolate, polls real byte channels, and obtains the native result (`native_miri_runner.dart:126-178`).
- Optional explicit-backend creation rejects a required but absent ABI symbol (`native_miri_runner.dart:225-231`); required ABI functions are bound at lines 377-404. There is no `UnimplementedError`/TODO fallback in these runner files.
- `native/miri_adapter/src/lib.rs:280-289` invokes upstream `miri::eval_entry`; lines 413-424 run upstream `rustc_driver::run_compiler` with the exact source, guest sysroot, x64 Linux guest target, and Rust edition 2024. This is not a hand-written Rust parser.
- Cancellation waits for the worker's real native call before destroy (`native_miri_runner.dart:187-194,277-282`); handles are not freed while execution remains active.
- ABI v1 supplies an exact source crate and `input.txt`; it does not support external Cargo dependencies, build scripts, external proc macros, user compiler flags, dynamic stdin, or user arguments. The limits are documented in `native/miri_adapter/README.md:63-67` and the ABI layout.
- Compiler cancellation is cooperative at phase/guest execution boundaries; guest memory accounting does not bound rustc host memory (`native/miri_adapter/README.md:56-61`). Do not report a hard OS-level compiler timeout/memory cap.

Potential desktop consistency follow-up: standalone rustc invocation (`rust_runner.dart:175`) does not add an edition flag, while native uses edition 2024. Standalone code requiring a modern edition may fail under rustc's default unless caller/environment flags supply it. Add a focused modern-syntax case if standalone terminal support promises parity; this is source-backed but not runtime-reproduced here.

### Actual packaged native inventory and validation

Independent read-only Python checks decoded every present manifest, read every listed data blob, compared byte length and SHA256, and checked both Android native closures plus the OHOS x64 native closure. All listed files matched. ELF `e_machine` inspection confirmed AArch64 (183) versus x86-64 (62), rather than trusting directory names.

| Platform/ABI | Manifest | Engine libraries present in this checkout | Audit result / execution evidence |
| --- | --- | --- | --- |
| Android arm64-v8a | schema 2, `aarch64-linux-android`, 97 data entries | Miri 17,300,072 B; Cranelift 16,029,192 B; driver 150,422,552 B | Complete size/hash-matched genuine native package. No device execution performed by this researcher. |
| Android x86_64 | schema 2, `x86_64-linux-android`, 97 data entries | Miri 18,212,808 B; Cranelift 15,808,104 B; driver 144,326,392 B | Complete size/hash-matched genuine native package. `rustProfile.runtimeStatus` declares available only for this ABI; declaration alone is not fresh device evidence. |
| OHOS x86_64 | schema 1, `x86_64-unknown-linux-ohos`, 98 data entries | Miri 16,083,560 B; Cranelift 15,807,056 B; driver 139,920,288 B | Complete size/hash-matched genuine native package. Historical HAP source execution remains unverified. |
| OHOS arm64-v8a | No matching active manifest | Probe only; no Miri/driver/backend | Cannot execute Rust from current package. |
| iOS/macOS/Linux/Windows embedded | No platform manifest/package observed under assets | No matching packaged engine established | Mobile iOS auto-route will fail asset preparation; desktop automatic mode can use installed Cargo/rustc independently. |

Android native packages live under `android/app/src/main/jniLibs/<ABI>`, with matching copies under `native/build/runtime/android-*`. Gradle preBuild checks identity/roles/size/presence (`android/app/build.gradle.kts:77-113`), filters x64/arm64 explicitly, and enables native extraction; `MainActivity.kt` implements the real `qflistudio/runtime/getRuntimeLibraryDirectory` channel. Guest data is declared in `pubspec.yaml:37` and loaded from flattened names.

Generated libraries/assets are intentionally ignored (`.gitignore:67-76`). A fresh checkout does not contain these engines solely because the local working copy has them. Reproducible packaging/build prerequisites therefore remain essential release evidence. The check above validates the current checkout and does not establish reproducibility on a clean machine.

The historical source-backed evidence is narrower than a device pass:

- `native/miri_adapter/README.md:71-79` and `.trellis/tasks/09-30-ohos-rust-interpreter/research/miri-adapter-validation.md` document Linux reference execution and both OHOS library builds.
- `.trellis/tasks/09-30-ohos-rust-interpreter/research/flutter-miri-integration.md:53-78` records x64 PackageHap success, SignHap error 00303074 from a bundle/profile mismatch, and no packaged source execution. This is historical evidence; the current platform worker must determine whether signing has since changed.
- `.trellis/tasks/10-09-terminal-run-controls/research/final-verification.md:35` explicitly distinguishes compiler/native skips, compiled fake Cargo/rustc wiring fixtures, layout-only PNGs, and absent mobile execution. Those test passes do not validate native source execution.
- `test/native_miri_integration_test.dart:11-18,189-191` skips the engine group unless matching library/sysroot environment inputs exist. `test/native_miri_assets_test.dart` uses synthetic asset bundles; it validates loader logic, not a native engine.

### Files found and related specifications

- `lib/main.dart`: Rust profile, offline flag, runner injection, ABI-specific availability declaration.
- `lib/rust_runner.dart`, `lib/cargo_targets.dart`, `lib/rust_run_title.dart`: desktop/native routing, exact Cargo source ownership, concise title contract.
- `lib/native_miri_runner.dart`, `lib/native_miri_assets.dart`: complete FFI session lifecycle and platform manifest extraction.
- `native/miri_adapter/{qfli_miri.h,src/lib.rs,README.md}`: source ABI, upstream compiler/interpreter execution, stated limits.
- `../qfli_studio_core/lib/services/studio_profile.dart`: shared runner/delegate/offline integration contracts.
- Shared `pages/terminax_terminal_page.dart`, `terminal/state/terminal_manager.dart`, `editor/terminal_pane.dart`: two UI surfaces, same sandbox/delegate hook.
- Shared `pages/{home_page,profile_page,settings_page,git_page}.dart`, `editor/editor_page.dart`: offline entry rendering and route gaps.
- Shared `services/{api_client,git_service,cloud_sync_service}.dart`, `store/auth_store.dart`: transport/service boundaries.
- `.trellis/spec/backend/native-runtime.md`: pinned compiler/ABI/native packaging and real-device evidence contract.
- `.trellis/spec/backend/rust-run-controls.md`: exact source ownership, concise titles, cancellation and mocked/real test distinctions.
- `.trellis/spec/frontend/content-imports.md`: shared core owns content/editor/import behavior; Rust should not fork those surfaces.

### Windows native-engine feasibility follow-up

`scripts/build_miri_adapter.ps1:1-18` is a real pinned Windows GNU x64 adapter builder. It verifies compiler revision, isolated output directories, exact source/component checksums, stages compiler-private metadata, applies the embedded-session patch, uses bundled LLD and `RUSTC_BOOTSTRAP`, and invokes real Cargo compilation (lines 55-77). This is an available implementation, not an empty method. It accepts `-Offline` for cached dependencies and restores process environment after compilation.

The current `native/build/miri-windows/` has `adapter`, `compiler`, and `miri` staging directories. Matching Windows `rustc_driver-e1f467aab84e86c3.dll` exists under the staged compiler's `bin` and host library directory. No `qfli_miri.dll`, built adapter target directory, Windows platform manifest, or `native/build/runtime/windows-x64/` package was found in the scoped inventory. Thus staged compiler prerequisites exist, but the engine itself has not been demonstrated as built/packaged here. The builder only implements `x86_64-pc-windows-gnu`; supported target names elsewhere do not establish Windows ARM64/MSVC builds.

There are two distinct Windows paths: automatic desktop `RustProgramRunner` uses installed Cargo/rustc and needs no Miri DLL; explicit embedded tests require a successfully built matching DLL plus MIR sysroot and dependency load paths. Setting host rustc PATH alone cannot make `native_miri_integration_test.dart` run. The coordinator reports its current verification as 109 tests passed with 8 real-engine cases skipped because `QFLI_MIRI_LIBRARY`/`QFLI_MIRI_SYSROOT` are unavailable. That is coordinator-reported evidence, not an execution performed by this researcher.

`native/runtime_bundle.cmake:17-27` installs a package if present and rejects a manifest without its native package. With neither Windows package nor manifest it intentionally permits a desktop build using installed toolchains. Building the missing engine appears technically actionable with the existing builder and pinned prerequisites, but compiler/linker success, dependency cache completeness, sysroot identity, and actual source execution still need verification. No Windows engine build was attempted in this audit.

### Focused validation for implementers/coordinator

Run from the explicitly identified roots; this researcher ran no mutating test/build commands and made no Git commits.

```powershell
# D:/MyNewProjects/qfli_rust
flutter analyze
flutter test test/cargo_targets_test.dart test/cargo_process_wiring_test.dart test/rust_editor_run_test.dart test/native_miri_assets_test.dart test/native_miri_runner_test.dart
flutter test
flutter build apk --debug --target-platform android-arm64,android-x64
flutter build hap --debug --target-platform ohos-x64 --no-pub

# D:/MyNewProjects/qfli_studio_core (coordinate the shared owner's live edits)
flutter test test/home_navigation_test.dart test/service_configuration_test.dart test/terminal_manager_delegate_test.dart test/sandbox_terminal_test.dart test/editor_run_test.dart test/terminal_pane_test.dart
```

Add focused regressions for: (1) Rust profile delegates on both terminal surfaces, including real stdout/stderr/exit/cancel; (2) offline editor hides/rejects Git routes; (3) profile settings hides AI despite SettingsPage's default; (4) offline refresh with a persisted token produces zero transport calls; (5) offline Cargo metadata and run cannot fetch dependencies. Preserve networked profile behavior.

For real native verification, use matching library/sysroot/backend environment variables with `native_miri_integration_test.dart`, or a safely isolated actual device integration package. Inspect the prebuilt Android application ID before installation as required by native-runtime.md. Do not label Android ARM64 or OHOS covered by the current hardcoded Android-x64 suite. Generalize its platform/ABI assertions first, then verify module/generic source, diagnostics, input/EOF/UTF-8, user exit, resource limits, cancellation, and a fresh run afterward. OHOS ARM64 first needs a matching package; building a probe HAP is insufficient.

## External References

No external network research was needed or performed. Exact versions and upstream calling patterns were verified from local pinned source/contracts: Rust 1.98.1 commit `48a229ceaefd4985c50990b14116b6d856af0985`, ABI 1, fixed `x86_64-unknown-linux-gnu` guest. Existing native build docs reference Android NDK 27.0.12077973 and 16 KiB ELF LOAD alignment.

## Caveats / Not Found

- No new actual Rust execution, Flutter test, emulator install, device install, compiler bootstrap, or HAP/APK build was run by this read-only researcher. Asset checksum/ELF inspection was performed and passed.
- Fresh Android x64 device-pass logs were not found in the scoped task evidence. Its profile says available, so the platform owner should recover or regenerate concrete evidence instead of treating this declaration as proof.
- OHOS historical signing mismatch may already be being handled by the platform owner; avoid duplicating or racing that work.
- Shared core is live across language sessions. Coordinate core fixes through one owner, keep Rust-specific delegates in this project, and do not overwrite another workspace's language code or catalogs.
- Shared release coordination uses the global `qfli-core-release-sync` channel. Core Pi `wF:p2`, whose cwd has been verified as `D:/MyNewProjects/qfli_studio_core`, exclusively owns the shared offline gate fixes. The Rust root session and this researcher remain read-only in core; forward findings there rather than editing the same files.


## Shared Core Follow-up: b7b2d2e / 7b8b7f2

- Date: 2026-10-15.
- Scope: current shared-core source read only; commit-to-file mapping supplied by coordinator (no Git operation performed by this researcher).
- b7b2d2e supplied scope: home_page.dart, profile_page.dart, task_activity_service.dart, sandbox_shell_backend.dart, shortcut_bar.dart, offline_background_and_shortcuts_test.dart.
- 7b8b7f2 supplied scope: tools_grid.dart and tools_grid_test.dart.
- Earlier 54a58ca editor/Git/profile-settings gates were read to connect the full navigation flow.

### Observed source behavior

- home_page.dart:324/343 suppress background task refresh for restored account state when offlineOnly; cloud scopes/project rows/create/pull also have explicit gates.
- profile_page.dart:47–50 returns before refreshMe for offlineOnly, and account/login/checkin/admin/signout/ICP UI is hidden. Its SettingsPage route sets showAi from offlineOnly.
- task_activity_service.dart:232/246 maintains local counts without creating new remote pending events in offlineOnly. syncPending and refreshIfDue guard before network work; sync queue rechecks the policy before subsequent events and task refresh rechecks after pending sync.
- shortcut_bar.dart:227/394/433/451 hides the network group and git status shortcut for offlineOnly while preserving symbol/navigation/local commands.
- sandbox shell now describes the host language toolchain generically instead of claiming Java-only support; real delegate/cwd/output behavior still requires the existing regression suite.
- tools_grid.dart computes additional fixed card height from the actual TextScaler and title/description line metrics. Default scaler preserves the original height; large text gets additional space. No network feature is introduced by the shared grid.
- No new release blocker was identified in these supplied source areas. checkin and calendar service entry methods themselves are not globally offline-guarded, but their product UI routes are omitted and these commits explicitly target background activity/profile paths. This review does not claim all service APIs enforce offline policy independently.

### Exact regression suites for coordinator

Run within the coordinated exclusive shared-core Flutter window (researcher did not start Flutter):

1. `test/offline_background_and_shortcuts_test.dart` — eight instantiated tests:
   - `offline restored account keeps local activity without remote events`
   - `offline policy holds an old pending event until online sync`
   - `online activity, task refresh, checkin and calendar remain functional`
   - `profile refresh respects offlineOnly=true with restored auth`
   - `profile refresh respects offlineOnly=false with restored auth`
   - `expanded shortcuts respect offlineOnly=true`
   - `expanded shortcuts respect offlineOnly=false`
   - `sandbox describes the host toolchain without naming a language`
2. `test/offline_editor_gates_test.dart` — offline-only hides Git and cloud pull, online keeps Git, profile settings hides/retains AI under the two profiles.
3. `test/tools_grid_test.dart` — especially `large text keeps all cards reachable in Brightness.light` and `.dark`; whole file also exercises normal phone/desktop dimensions, each of nine real tools, product sections, and terminal navigation.
4. `test/terminal_manager_delegate_test.dart` — app terminal sessions receive the profile delegate.
5. `test/sandbox_terminal_test.dart` — sandbox roots, real delegate stdout/stderr/exit codes, cwd after cd, unsupported syntax, and desktop fallback.

A source read is not a passing regression result. Coordinator owns commands, logs and final pass/fail evidence. Unrelated shared-core code_import_service.dart/content_code_import_test.dart changes remain Go-owned and were not changed or reviewed in this follow-up.


Coordinator follow-up: `/root` reports the coordinated shared-core targeted regression run completed **61/61 passing**. This result was supplied by the runner/coordinator; this researcher did not start an additional Flutter run. The later Go-owned exact-filename commit a838c25 is slated for relevant import regression in the final baseline and is not included in this source review's pass claim.
