# Rust compatibility and release acceptance follow-ups

## Status and origin

This independent task is planning only. The user-approved coordinator ruling
`D:/MyNewProjects/_orchestra/decisions/qflistudio-rust.md`, dated
2026-11-27 14:35, separates these product outcomes from
[`11-26-github-workspace-migration`](../11-26-github-workspace-migration/prd.md).
Do not start implementation, close the installer/native product tasks, or infer
execution approval from migration `done.json`.

The 2026-11-28 03:30 ruling in
`D:/MyNewProjects/_orchestra/decisions/core-ref-wave-2.md` replaces the first
wave's pin. Pin immutable `CORE_REF` to
`8e031313ffc8d531c5a6b4d131f721f35da04c86` for this authorized wave.
The brain later required pin-only publication, completed at
`68723d029dfd9dae8ea91c97b8a26848f116e8cd`. Gate, clean target parity and the
exact-SHA acknowledgement passed before deferred quality repairs were restored.
Restoration made the source dirty at that recorded point; later repairs require separate publication, a new gate,
renewed parity and acknowledgement.
Do not adopt another core SHA unless the brain sends another wave.
The reviewed SDK recipe remains
Flutter-OH `3.41.10-ohos-1.0.1` at
`adaf911c35c9136a7d18fc424d714c9ec7724e60`. Those input identities do not prove
Rust native-hooks or production compatibility. Do not reuse the old `9d2eaf`
tooling override or copy qflistudio-next patches speculatively.

The core owner confirmed that consumer root dependency overrides are required
because dependency pubspec overrides are not inherited. Root `pubspec.yaml`
must include `re_editor: {path: ../qflistudio-core/vendor/re_editor}` and
`xterm: {path: ../qflistudio-core/vendor/xterm}` under `dependency_overrides`.
Committed lock metadata and hosted resolved package roots must match those
paths. P3/P4 own the implementation and hosted regressions; this planning note
does not claim they are complete or passing.

## Planned requirements

- F1: Establish the supported core/SDK/Rust native-hooks contract from exact
  source, tooling/engine identities and GitHub-hosted results. Document any
  required override by immutable repository/path/ref and behavior.
- F2: Complete missing installer acceptance for Android arm64/x64, iOS arm64,
  OHOS arm64, Linux x64, Windows x64 and macOS arm64/x64. Record actual inputs,
  intermediate bytes, final artifacts, checksums, installation/mount checks
  and retention. Preserve strict native producer-to-package byte verification.
- F3: Review platform signing and distribution prerequisites. Unsigned
  IPA/HAP/Windows outputs, Android testing keys and ad hoc macOS signing are
  not store or device acceptance. Do not commit signing credentials.
- F4: Plan device/UI validation with owners. No local devices, emulators,
  builds, dependency restoration or tests are authorized by migration work.
- F5: Address Android armv7 across compiler/backend, ELF32, ABI/host mapping,
  NDK/Gradle and Dart loading. Two APK architectures do not meet this requirement.
- F6: Obtain receiver-hook command, stderr and execution evidence before
  diagnosing or claiming repair. The separate service-tier warning is not
  evidence of the hook's cause.
- F7: The brain authorized the second core wave at
  `8e031313ffc8d531c5a6b4d131f721f35da04c86`. Its pin-only consumer commit
  `68723d029dfd9dae8ea91c97b8a26848f116e8cd` passed the orchestra gate, target
  parity and acknowledgement before repair restoration. Cloud checks
  `46072255988` passed. Quality `46072256145` passed helpers, preparation and
  analysis but failed formatting and root tests. Installers `46072256031`
  passed six of seven platform jobs; iOS failed on `hashlib.file_digest`.
  Application quality and product acceptance remain open. Keep root core/vendor
  dependencies and lock/resolution provenance coherent with the pin. Any repair
  publication requires a new gate, target parity, acknowledgement and hosted CI.

## Evidence and acceptance

For each requirement, retain current scope, owner, input identities, real run
IDs and explicit missing evidence. Installer/native child plans remain the
source of their implementation details. This planning task coordinates their
remaining product acceptance; it does not claim those outcomes succeeded.

Completion requires reviewed implementation plans and actual evidence for the
requirements selected for execution. All build, test, syntax, lint, analyzer,
formatter, restore and installer commands must run on GitHub-hosted runners.
Any future device procedure needs its own approved boundary. Preserve original
source, historical rescue copies, local-only inventories and shared WSL data.

## Migration boundary

Actual hosted Dart formatting, Flutter analysis and the complete root test
suite retain their real evidence; helper/native success cannot replace them.
The later 18:50 `ci-decoupled.md` ruling permits `migrated.json` before CI ends.
`done.json` adds final-SHA evidence: rerun infrastructure failures once and fix
repeated configuration failures, record proven pre-migration defects as
follow-ups, and fix migration-caused failures through another gate commit.
Migration records the latest installer platform
outcomes and lists missing coverage in `done.json`; that file completes only
the workspace migration. Record the exact core pin and the authorized wave's
publication, target acknowledgement and hosted CI evidence in that file.
Ignored source-only files are inventoried separately
from clean tracked HEAD/tree parity. No deletion or WSL unregistration is part
of either this plan or the migration.
