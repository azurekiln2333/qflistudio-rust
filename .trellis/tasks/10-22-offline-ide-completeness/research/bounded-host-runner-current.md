# Bounded Rust host runner source review — 2026-10-24

This is source preparation for a **future fresh named grant**, not a host
reservation, executed check, compiler result, or OHOS result. The historical
Go287/Rust205/C211 handoff was explicitly deferred at global538 after the live
queue had superseded it. No WSL, native, SDK, Dart, Flutter, analyzer, test, build,
Job-control experiment, or device command was launched for this implementation.

## Change boundary

The ignored `build/offline-ide-audit/run-reserved-validation.ps1` prototype used
direct synchronous commands, had no enforced whole deadline or owned descendant
check, and inferred release from parent command completion. Its formatter also
changed source during validation. Replace only that validation entry and its
Rust-owned support files. Shipping Dart/native code, sibling products, shared
core, the native Linux supervisor, signing inputs and device state are outside
this ownership. The native-preflight checker separately owns the Linux wrapper.

The new PowerShell entry delegates to `run-rust-owned-window.py`. The Python
coordinator uses a byte-for-byte local copy of the frozen C-owned
`D:/MyNewProjects/qfli_studio_core/build/c_owned_job.py`, shared with permission
at global541. Its SHA256 remains:

`c0520616e6777d9587a6c0004487bd06a1b19b7d202563f8292c4c1a32c6b172`

The helper creates each process suspended, assigns its exact process handle to
a private non-breakaway Job, then resumes it. Limits request termination only
for that owned Job; the coordinator queries terminal status and zero active
processes before closing the handle. A successful root with surviving children
requires cleanup and fails the gate. An unconfirmed cleanup writes HOLD and
never an onward release. Closing a kill-on-close Job is only another termination
request, never evidence that its processes stopped.

## Invocation contract

Immediately before launch, root must inspect the **current** global queue,
receive an explicit fresh named Rust handoff, save its exact incoming event JSON,
publish acceptance, and choose the named successor. No numeric argument or
historical queue text grants a slot. The entry requires that root assurance and
the actual event, rejects seq<=533 and a self-authored readiness event, and binds
the grant event SHA256 to the unique run report.

```powershell
pwsh -NoProfile -File build/offline-ide-audit/run-reserved-validation.ps1 `
  -Mode Native `
  -GrantSeq <fresh-event-seq> `
  -GrantEvidenceFile <saved-exact-incoming-event.json> `
  -NextOwner <explicit-successor-handle> `
  -RootVerifiedGrant
```

Use `-Mode Dart` only for its separately granted window. Native is bounded to90s
and Dart to110s inclusive of reserved cleanup and release publication. The native
supervisor receives a dynamic maximum<=76s, including15s Linux cleanup, leaving
margin before the Windows deadline. No WSL reset, global process kill, foreign
process discovery/termination, package download or device action is present.

`active-owned-window/owner.json` prevents two local windows from starting at
once. `consumed-grants/<seq>/owner.json` permanently prevents replay of an event.
An active marker is cleared only after owned validation cleanup and confirmed
release publication. On HOLD or failed/ambiguous publication, root must inspect
the exact report and channel before reconciling the marker; no automatic PID
guess, stale-marker deletion, or implicit retry is implemented.

## Evidence and deadlines

Every run uses an exclusively created `runs/<mode>-<UTC>-<UUID>` directory.
Reports include exact child PID/creation FILETIME/thread identity, suspended
creation and assignment-before-resume flags, actual exits, timeout/orphan-cleanup
flags and zero-active-process Job evidence. Selected Rust files, all Rust lib
files, Rust content JSON catalogs, root pubspec/lock, shared core
lib/assets/re_editor source and both HEADs
are hashed before and after. Native mode additionally hashes the adapter,
fixtures, upstream patch, build script and both coordinator layers. Any drift or
incomplete snapshot fails validation. The formatter uses check-only arguments.

The effective `.dart_tool/package_config.json` is also hashed. Both snapshots
resolve qfli_rust, qfli_studio_core and re_editor rootUri/packageUri and require
the actual import roots to equal the trees being hashed. A stale `--no-pub`
configuration pointing to another checkout fails before SDK launch. Root/core
analysis options and core/vendor pubspecs are included in identity evidence.

Native calls the separately owned `run-native-validation-current.sh` with an
exclusive Linux run directory and the same runId. Its `native/run.json` must bind
schema1, exact runId/runDir/reportPath and supervisorPid, then prove
`groupEmpty=true` and `ownedProcessesRemaining=[]`. A WSL exit, timeout, missing
report, mismatched report, or incomplete group cleanup cannot establish terminal
ownership. A known unavailable Linux endpoint with a final empty-group report
can release the lane with failure/unavailable status. A native failure, including
the genuine compiler-confinement FS exit4, remains a failure in the host report.

Dart uses the absolute SDK at `D:/ProgramFiles/flutter_ohos/bin/cache`, raw
`dart.exe` and `flutter_tools.snapshot`, no pub, serial test concurrency1. It
checks six files and executes all tests in the debugger, feature-audit and
workspace files. The current authored count is42+15+5=62, not yet executed.

Publication itself runs inside an owned bounded Job through
`publish-rust-release.ps1`. A release message is prepared only after Windows
validation Jobs and any Linux group are confirmed empty. Publisher exit0,
empty-Job evidence and a matching returned channel event are required before
the final local report says `released=true`. Missing/ambiguous delivery remains
visible and retains the active marker. The successor must explicitly ACCEPT.

## First granted launch and source repair

Root accepted only fresh SQL556 Native90s in557 and named Java535 next. The
pre-coordinator PowerShell command exited1 after0.7259186s (tool4e399b):
`Get-Command python` returned Python313 plus the WindowsApps alias and their
Source array became one invalid executable name. No Python coordinator, owned
Job, WSL/Linux group, native build or ABI suite started. Root558 explicitly
released to Java535 and persisted a consumed556 marker; there was no retry.

The entry now takes `Select-Object -First 1` before reading Source. Root verified
that the two current candidates select exactly one existing Python313 executable,
and PowerShell syntax still parses. This is launcher/source evidence only. The
actual orchestrator and platform controls remain unrun; source-ready-20261024.json
contains the updated launcher hash and exact failed/not_run record.

## Checks and remaining verification

Python `ast.parse` succeeded for the coordinator and unchanged helper.
PowerShell's parser accepted the entry and publisher. Helper SHA256 matches the
frozen upstream bytes. These are **syntax/source checks only**; neither the new
orchestration nor its commands were run. Independent cross-boundary source
review by the current-core checker closed the effective-package-root binding
finding and found no additional concrete lifecycle/release defect. This is a
source review, not a control-process or runtime pass. Frozen host coordinator
SHA256 is `6aae56e341ba0961aa9895a00cc2743ffcc7f9eae23526b54f1e531745cd276a`.

Before relying on this runner, perform a short granted control in addition to
the actual gate: an owned root exits0 after spawning two sleeping descendants;
assert `orphanCleanup=true`, nonzero gate exit and eventual zero active processes.
The shared C helper's earlier control is useful provenance but does not execute
this new Rust orchestration. Linux ownership controls and actual native suites
remain separate. No host helper, source parser or fixture result substitutes for
the pinned native ABI, fresh catalog inventory, packaged HAP or real OHOS proof.
