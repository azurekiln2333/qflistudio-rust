# Native source preflight — 2026-10-24

Source-only checkpoint for `.trellis/tasks/10-22-offline-ide-completeness`.
No native compiler, WSL, SDK, Dart, Flutter, device or runtime process was
started. The recovered coordinator queue supersedes historical Go287 /
Rust205 / C211. Root owns every fresh grant and release; this review publishes
neither. No WSL reset or foreign-process action occurred.

## Findings fixed

- `native/miri_adapter/debug_abi_test.c`, `locals()`: zero-initialize the
  diagnostic local. Previously a failed name lookup short-circuited into a
  diagnostic reading an uninitialized `type_name` pointer. Strict entry
  line9 → line10 → line11 assertions and all runtime assertions are unchanged.
- `build/offline-ide-audit/run-native-validation-current.sh`: replace the
  unbounded command chain/shared output files with a UTF-8, no-BOM, LF shell
  entry for `native-group-supervisor.py`.
- New `build/offline-ide-audit/native-group-supervisor.py`: exclusive per-run
  directory; total time budget including cleanup; Linux session/group anchor
  with pid/pgid/sid/startTicks; inherited unique run token; child subreaper;
  TERM/KILL only after owned-group identity verification. IO/scan/marker
  failures remain bounded and cannot certify cleanup. Successful complete
  process inventory plus reaped anchor/adopted children is required for
  `groupEmpty=true`. Remaining or ambiguous ownership produces HOLD/exit125.
  Final report write failure produces exit126 and does not establish release.
- Native input snapshots include the complete adapter, fixtures, patch, build
  support, authored topic JSON and native/UI catalogs. Before/after maps detect
  new/deleted shipping source paths, changed snapshots and changed exports.
  Authored164/165 example/answer exports are freshly validated and reconstructed
  from frozen authored/native/UI catalogs, never reused from the old export
  directory. The pinned builder checks upstream source/compiler identity and
  uses offline Cargo. A copied per-run library has its own SHA256 and read-only
  file mode. Build and each compile/ABI phase retain exact commands, process
  identity, status and unique logs.

## Source readiness and remaining findings

- `EmbeddedFileSystem::current_dir()` returns the exact root when cwd is empty.
  Its retained temporary descriptor and no-follow directory/dev/inode teardown
  checks match the late cwd/replacement regressions. Missing/replaced/symlink
  names remain untouched. Initial descriptor acquisition failure uses only
  nonrecursive empty-directory rollback through the existing root descriptor.
- The replacement C harness captures the actual owned temp name, verifies both
  sentinels before and after destruction, then removes only its own suite data.
  The cleanup helper is declared before use. Fixture and harness names match.
- Shipped `embedded_fs.rs` patch hunk is393 lines and applies cleanly. The old
  ignored staging copy has two corrupted Unicode test literals where the
  shipped patch has `你好`. This read-only staging file is not used by the new
  runner; production patch bytes remain authoritative. Do not regenerate the
  patch from that stale staging copy.
- Compiler `include_str!` / `env!` confinement remains a known real failure.
  FS exit4 means runtime passed while compiler boundaries remain; it is not
  native acceptance. No scope expansion or assertion weakening was made.
- The old PowerShell wrapper's direct command return cannot prove descendant
  exit. The separately owned host runner must bind the exact fresh run ID/path,
  require Windows Job emptiness and consume the Linux terminal report. Missing
  Python may yield shell exit3 with no Linux report; absence of a report alone
  cannot establish Linux cleanup or authorize release.

## Host integration contract

After a fresh named native grant only:

```text
sh <repo>/build/offline-ide-audit/run-native-validation-current.sh
  --max-seconds 76 --cleanup-seconds 15
  --run-dir <exclusive-host-run>/native --run-id <host-run-id>
```

`run-dir` must not exist. `run.json` has `schemaVersion=1`, exact `runId`,
absolute `runDir`/`reportPath`, `supervisorPid`, `group` containing
`pid/pgid/sid/startTicks`, `anchorExitCode`, `ownedProcessesRemaining`,
`groupEmpty`, timing/phase/source/snapshot/export/library evidence and final
status/exitCode. Work is capped at61 seconds, preserving15 Linux cleanup
seconds within76, leaving14 seconds in a90-second outer reservation.
Endpoint inputs missing → unavailable/exit3, no bootstrap. Timeout → exit124;
runtime/build failure → actual failure; FS compiler boundary gap → exit4.
Every result is host evidence only, never packaged OHOS acceptance.

## Verification actually performed

- `git -C build/offline-ide-audit/fs-patch-base apply --check
  --whitespace=error-all <absolute native patch>`: PASS, exit0.
- Pure Python source checks: six C/Rust debug struct field orders/types,
 64-bit ctypes sizes/offsets versus existing C static assertions, exact fixture
 lines, trace declaration order and initialized diagnostic path: PASS.
- Python AST parse and source whitespace checks: PASS. Shell no-BOM/LF/argv
 forwarding checks: PASS. `git diff --check` for owned harness paths: PASS.
- Nine pure Python simulated cleanup checks: PASS; no child process or OS
 signal invoked. Covered clean anchor exit, TERM, ignored TERM/KILL, transient
 and permanent `/proc` errors, marker IO failure, ambiguous ownership refusal,
 vanished unanchored members and nonleader identity refusal.
- Lint/type-check with the native compiler: NOT RUN; no fresh grant.
- Actual Linux supervisor controls and native build/ordinary/analysis/debug/FS
 execution: NOT RUN. Fresh focused Dart checks, OHOS packaging/device and full
332 native acceptance remain with root and require their own evidence.
