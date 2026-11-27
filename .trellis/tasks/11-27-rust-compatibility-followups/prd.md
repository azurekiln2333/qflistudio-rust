# Rust compatibility and release acceptance follow-ups

## Status and origin

This independent task is planning only. The user-approved coordinator ruling
`D:/MyNewProjects/_orchestra/decisions/qflistudio-rust.md`, dated
2026-11-27 14:35, separates these product outcomes from
[`11-26-github-workspace-migration`](../11-26-github-workspace-migration/prd.md).
Do not start implementation, close the installer/native product tasks, or infer
execution approval from migration `done.json`.

The migration pins observed GitHub core `main` as immutable `CORE_REF`, currently
`476a30acee21dc486ee2849dd8064a7be665e4d5`. The reviewed SDK recipe remains
Flutter-OH `3.41.10-ohos-1.0.1` at
`adaf911c35c9136a7d18fc424d714c9ec7724e60`. Those input identities do not prove
Rust native-hooks or production compatibility. Do not reuse the old `9d2eaf`
tooling override or copy qflistudio-next patches speculatively.

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
suite are still required by migration. They cannot be deferred here or replaced
by helper/native success. Migration records the latest installer platform
outcomes and lists missing coverage in `done.json`; that file completes only
the workspace migration. Ignored source-only files are inventoried separately
from clean tracked HEAD/tree parity. No deletion or WSL unregistration is part
of either this plan or the migration.
