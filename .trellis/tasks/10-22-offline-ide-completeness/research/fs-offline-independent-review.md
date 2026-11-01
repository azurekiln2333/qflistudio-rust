# Independent filesystem and offline-host evidence review

Reviewed on 2026-10-23 against the current working tree. Scope: the real-native
filesystem C harness, its fixtures/current execution log, and the Node behavior
suite for the actual OHOS EntryAbility source. No Flutter, WSL, native rebuild,
HAP build, signing change or device operation was performed by this reviewer.

## Fixed finding

`scripts/test_ohos_offline_host.cjs` previously replaced `isPickerMethod` with a
mock accepting `pickFiles`. The production `PickerBridge.ets` does not expose
that method: it accepts `pickDocument`, `saveDocument`, `pickPhotos`, `readUri`
and `writeUri`. The old check therefore did not establish preservation of an
actual production picker entry point.

The test now transpiles the actual PickerBridge module using the installed SDK
TypeScript and consumes its exported method predicate. Native picker I/O remains
mocked so each of the five production methods is checked for delegation with the
same ability context and exact method. `pickFiles` and an unknown method must
return `notImplemented`. The common module loader also bounds synchronous VM
evaluation to one second. Production OHOS source was not changed in this review.

## Filesystem harness assessment

- It dynamically loads the real adapter and requires the additive project-root
  constructor and ABI version 1. It does not substitute a runtime implementation.
- It creates a fresh private suite root with real outside sentinels before any
  negative probe. Runtime escape checks re-read their exact bytes, reject missing
  or nonregular sentinels, inspect prohibited creations, and retain ordinary
  project bytes. Symlink checks prepare real outside targets, deny traversal and
  distinguish unlinking the link from deleting its target.
- Every synchronous native run must actually finish, execute basic blocks where
  appropriate and reject reuse. Output is copied while the session is alive.
  Destruction follows the completed blocking run, output reads and second-run
  rejection; this harness does not free a live native worker.
- Socket denial needs a nonzero final exit, interpreted blocks and actual socket
  isolation diagnostics. An additional listening loopback endpoint detects a
  connection even when the guest ignores the connect result. A generic failure
  or refused connection cannot satisfy those checks.
- Two simultaneously retained sessions must have distinct private temporary
  directories and independent cwd. Destroying the first must preserve a marker
  in the second. The exact root-cwd output assertion remains unchanged; the
  observed trailing slash mismatch is a production issue, not normalized away.
- Suite cleanup operates only below its exclusively created directory, uses
  `lstat` so symlinks are unlinked without traversal, and follows session teardown.
  Setup or lifecycle failures exit unsuccessfully and are not passes.
- Authored164/165 source copies are checked byte for byte. Example stdout is
  exact; answer stdout is explicitly unasserted because these authored answers
  have no expected-output contract. This small suite is not a substitute for
  the full hash-bound332 catalog report or Cargo all-target verification.

The inspected `build/offline-ide-audit/native-fs-abi-current.log` records the
substantive runtime probes and authored164/165 succeeding, with one exact
second-session root-cwd mismatch. The parent has reported a source correction;
this reviewer did not rerun or claim verification of the corrected native build.

Both compiler negative probes disclose their prepared synthetic sentinel in
that log (`include_str!` and `env!`, exit0). The harness correctly reports both
as `REMAINING`, redacts their output, and keeps the suite unsuccessful rather
than accepting missing data as a confinement pass. Its distinct exit4 is reserved
for runtime success with the compiler boundary still open; the inspected log has
a runtime failure and therefore reports exit1 instead.

## Temporary-entry replacement finding and regression

The initially reviewed upstream patch's `EmbeddedFileSystem::Drop` removed the
temporary pathname through its pinned root descriptor, but retained no identity check for
the directory originally created at that name. `rename` permits arbitrary
in-root source and destination entries. A guest can move its own temporary away,
rename an ordinary project directory onto the remembered temporary name, then
cause destruction to recursively delete that replacement directory. Existing
normal-lifecycle tests do not exercise this path replacement. This is a concrete
source-level ownership gap, not a demonstrated runtime result.

The parent added a retained `File` for the created directory, and compares the
current no-follow metadata descriptor's type/device/inode to that retained
identity before cleanup. Source review confirms this skips missing entries,
symlinks and replacement directories, prevents inode reuse while the original
descriptor remains open, and does not chase the renamed original. The new module
regression covers both a directory replacement and a symlink replacement. This
check assumes the documented post-interpreter namespace quiescence; it does not
make the check/remove sequence atomic against an external concurrent host rename.

At the parent's request this review adds `native/fixtures/fs_temp_replace.rs`
and `temporary_replacement_cleanup()` to the real C ABI harness. The fixture
writes a marker in its own temporary, renames that directory aside, and moves a
seeded ordinary project directory onto the remembered temporary name. The
harness verifies the moves occurred, destroys the completed session, then checks
both the replacement's ordinary sentinel and moved original's owned marker are
unchanged. Only the harness's explicit owned-suite cleanup removes these entries.
The policy is: never delete a changed replacement, and do not chase the renamed
temporary by a guest-selected path. No expected cwd/output assertion was weakened.

A further source-review finding was sent to the parent: if opening the newly
created directory descriptor fails after mkdir, its temporary path/identity have
not yet been recorded and Drop cannot remove it. The parent added a nonrecursive
`remove_dir` rollback before returning the original error. This is safe against
recursively deleting replacement contents, but its current helper clones the
root descriptor again, so persistent `EMFILE` also prevents that rollback.
Recommend using the already owned root descriptor with nonrecursive `unlinkat`
for this pre-guest rollback. The production patch remains parent-owned. The new
actual ABI regression and revised native implementation have not been executed
by this reviewer.

## Offline-host assessment and verification

The actual EntryAbility rejects both `openAgreement` and `openUrl` with
`OFFLINE_ONLY` before reading method arguments or invoking router/startAbility.
The real source still contains startup-progress finite checking/clamping,
Flutter engine/plugin registration, local text sharing and picker delegation.
Tests use the actual host module; the router and ability mocks expose accidental
external invocation. Existing agreement/signing files were not edited.

- `node --check scripts/test_ohos_offline_host.cjs`: passed.
- `node --test scripts/test_ohos_offline_host.cjs`: 6 passed, 0 failed.
- Baseline sensitivity: exact bytes from `git show
  78fb7b1:ohos/entry/src/main/ets/entryability/EntryAbility.ets` were written to an
  exclusively created temporary file and selected with
  `QFLI_OHOS_HOST_SOURCE`. Exactly the two offline-entry checks failed; the four
  preservation checks passed. The owned temporary file/directory were removed.
- The SDK TypeScript transpilation reports no syntax diagnostics for the actual
  host and bridge modules. This is not an ArkTS semantic type check, HAP build,
  native picker execution, whole-app network audit or packaged device evidence.
- SDK clang `-std=c11 -Wall -Wextra -Werror -fsyntax-only` passed for the changed
  C harness with both `x86_64-linux-ohos` and `aarch64-linux-ohos` targets.
- Native execution and ArkTS semantic build/type checks were not rerun because
  this review had no native/build window. Their acceptance remains with the
  parent. A rustfmt executable was unavailable; the new fixture was manually
  formatted.

The compiler boundary, actual temporary replacement regression, full current native
catalog execution and packaged OHOS evidence remain open.

Parent follow-up after review: constructor rollback now calls nonrecursive
`fs::remove_dir` using the existing root descriptor's `/proc/self/fd` path.
It no longer calls the helper that clones the descriptor, so this path does
not require allocating another root fd after an `EMFILE` acquisition failure.
This is source evidence only; failure injection and actual ABI execution remain
separate from the source review above.
