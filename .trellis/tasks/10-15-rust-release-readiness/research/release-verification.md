# Rust release verification — 2026-10-15

## Scope and result

All source writes and work commits in this session belong to
`D:/MyNewProjects/qfli_rust`. The three existing Pi panes were verified as Rust
workspace `wB:p2`, `wB:p3`, `wB:p4` before dispatch. They completed the two
curriculum ranges and terminal audit; their source ownership is now frozen.
Shared `qfli_studio_core` was inspected/tested read-only at `8b33443`. Other
products' source, application IDs and signing credentials were preserved.

Terminal, offline integration and curriculum work is implemented and verified.
Store publication remains conditional on production Android signing and a
matching Rust OHOS signing profile plus actual signed packaged execution.
The readiness and broad native-runtime tasks remain open for these limits.

## Implemented and reviewed

- Standalone and editor terminals share `rustProfile.terminalCommandDelegate`.
  `rust run file.rs` and `rust file.rs` use the actual desktop/native runner.
  Desktop rustc/Cargo retain source-target selection, stdin/EOF, diagnostics,
  user exit status and process-tree cancellation. Mobile unsupported raw CLI
  commands return truthful exit 127 with embedded-run guidance.
- Offline Cargo forces `CARGO_NET_OFFLINE=true` and prepends `--offline` for
  metadata and execution, even with conflicting inherited environment/config.
  Network subcommands are rejected behind global options as well.
- Shared core gates login/token refresh, cloud projects/terminals, Git UI,
  AI/community, network tasks/sync and terminal network shortcuts for the
  offline Rust profile. Rust's native OHOS AccountKit bridge and unresolved
  AGC client metadata were removed. Android APK has no INTERNET permission;
  OHOS platform permission and SDK declarations are distinguished from the
  gated product flows in the platform report.
- The Rust-local repository replaces the placeholder catalog with 166 complete
  Chinese tutorials and 166 paired examples: 30 beginner, 58 intermediate,
  78 advanced, including 23 full offline Cargo projects. Every lesson received
  semantic review. Exercises contain complete answers, meaningful requirements
  and real domain behavior. Advanced async and capstones use actual Wakers,
  persistence, bounded workers, cancellation and checked C ABI behavior.
- New-project imports retain edited learner source, selected entry and package
  identity while installing complete companion files. Existing/editor imports
  preserve their single-file contract. Strict preflight, path collision checks,
  fresh-root rollback and Windows reserved Cargo names are covered.
- Native source/build/package integration uses pinned Rust 1.98.1 revision
  `48a229ceaefd4985c50990b14116b6d856af0985`. Final ZIP checks must compare native
  member bytes with manifest SHA-256/size after platform stripping, not merely
  pre-package source libraries.

## Validation

| Check | Actual result | Evidence |
| --- | --- | --- |
| Final main and exercise programs | 332/332 compile and run | `curriculum-verification.json` |
| Offline Cargo projects | 23/23 workspace/all-target builds and requested runs/tests pass | same report; full Flutter imports |
| Lesson semantic review | 166/166 accepted | `curriculum-content-review.md` |
| Root unit/widget suite | 140 pass, 8 explicit Windows-native skips, 0 fail | `build/release-final-tests.log` |
| Python source/package/content tests | 13 pass | platform/content reports |
| Terminal/process/app regressions | 65 pass, no skips | `build/terminal-final-tests.log` |
| Shared-core offline/editor/terminal/tools | 61 pass | `shared-release-audit.md`; `core-coordination.md` |
| Shared-core import/About | 41 pass | `build/core-final-import-about-tests.log` |
| Whole `lib test integration_test` Dart analysis | Pass | `final-integration-review.md` |
| Dart formatting | Zero changes | same report |
| Final real Android ARM64 native/editor/terminal tests | 7/7 pass | `platform-builds.md` |
| Real API37 Android x64, 16KiB-page emulator | 7/7 native/editor/terminal pass | same report |
| OHOS signed packaged source execution | Not verified: missing Rust profile | same report |

The eight host-suite skips are native Miri sessions without a Windows
adapter/sysroot. Real Windows rustc/Cargo programs, including all 23 imported
Cargo workspaces, were executed. The installed NDK LLVM dlltool supplied the
missing GNU import-library tool; no proc-macro target was disabled.

Final authored-source SHA-256:

- `topics_001_084.json`:
  `487226f138b70fdb6b06843dfe83076ac52a4d9734fe52bd92a794cfbaf5e2ba`
- `topics_085_166.json`:
  `22669421c29c3d3e89cecbe79c9074c3ab105f429ab8db2c2e1d79ede644f4b9`

## Platform evidence and handoff

| Final artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `build/app-release-final.apk` (saved dual-ABI release) | 154284485 | `b54ccc9430dc6b5e3c2ce4ddad9a232b2b4dc5b71c2180cdcb04b1890f5ca2d8` |
| `build/ohos/hap/entry-default-unsigned.hap` (ARM64 release) | 638135918 | `bc64d9f1d721a7d75a391f13a0ea1a568586aec34341643736775bf97e7ae780` |

Final Android build passed in 80.8 seconds; final OHOS Flutter build passed
in 74.3 seconds. Both ZIP catalogs match the final 166 tutorials and 166 examples
byte-for-byte. Android's two manifests each match all 3 native libraries and 97
guest/license entries. OHOS ARM64 manifest matches all 3 native libraries and 97
entries after the narrow strip exclusions; the manifest/checksum defect is
therefore fixed in the actual HAP. Android's 10 ELF files and 16KiB ZIP alignment
pass. OHOS has correct ARM64 Flutter/app libraries; four residual x64 native
libraries are size overhead, without an x64 Flutter engine/app. Typed temporary
Hvigor no-sign configuration was restored exactly after the final build.

The ordinary final APK was actually installed/launched on the 16KiB x64 emulator:
correct Rust process/focus and five pages checked, no app fatal error. Root also
visually inspected the saved Profile, Tools, Tutorials and Examples screenshots;
166 examples are displayed and offline account/cloud shortcuts are absent.
Exact commands, package audits and device smoke details are recorded in
`platform-builds.md`; baseline artifacts there are explicitly historical.

The first seven-test physical attempt was interrupted after contradictory Web
worker/coordinator ownership; it is not a test pass. Authoritative Web
coordinator release is global seq44, followed by SQL coordinator claim seq46.
Go coordinator explicitly handed Rust only emulator5580/private ADB5039 in
seq48, acknowledged in seq49. Rust's successful seven-test x64 run used that
owned emulator. Rust then stopped only emulator5580 and private ADB5039 after
its final release-app smoke; the original AVD and shared5037 were preserved.
SQL coordinator explicitly released the physical device in seq53, accepted by
Rust coordinator54/platform55; the final seven-case ARM64 run passed 7/7. Rust
then installed the exact saved ordinary APK with `-r`, launched it successfully,
reviewed all five product pages and confirmed a stable PID with no matching
fatal/unhandled/overflow entries. The ordinary Rust package was not previously
installed, so its firstInstallTime is new, not asserted unchanged. Only Rust's
ordinary/test apps were force-stopped; no product was uninstalled or data-cleared.
Rust explicitly released the physical window to Go coordinator in global seq56.
Rust coordinator wB:p1 authoritatively confirmed that release in global seq58.
All Rust Flutter/build and device ownership is now released. No release may be
inferred from a worker's limited scope or another pane's blocked status.

OHOS unsigned install was actually attempted: HDC exited 0 but the installer
reported `9568320 / no signature file`. Native shell execution was denied126
by device policy. Neither is an execution pass. No policy or other application's
credentials were changed; OHOS runtime availability stays unverified.

## Work commits

- `c59efb2` — release plan and verified parallel ownership.
- `6082520` — curriculum generation and real execution validator.
- `a5a12aa` — authored lessons001–084.
- `c2bc7b9` — terminal/native routing and cancellation.
- `151fe59` — robust offline Cargo policy.
- `0649363` — pinned native engines and platform packaging.
- `dc2becf` — independently reviewed fundamentals/exercises.
- `5384d29` — complete 166 lessons, imports and accepted final corpus.
- `08c2605` — final curriculum/terminal task completion and shared-core evidence.
- `ca6853e` — preserved OHOS library checksums and final native terminal suite.
- `6de0e35` — final package/device audits, executable specs and release evidence.

Final platform and task/journal commits are recorded in Git and task metadata.
Unrelated initial editor configuration, diagnostic snapshots and generated
desktop registrants remain outside this task's commits.
