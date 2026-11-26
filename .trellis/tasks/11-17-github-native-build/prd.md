# GitHub native runtime builds

## Goal
Move expensive native compilation to GitHub Actions. Let the user inspect build status and download complete native packages without keeping compiler intermediates locally.

## Confirmed facts
- GitHub repository: azurekiln2333/qflistudio-rust. No workflow or prior Actions run exists.
- Current branch: feat/rust-offline-ide-20261022. Origin has five push URLs; push only the explicit GitHub URL.
- User approved task creation and immediate implementation. The latest correction distinguishes build hosts from target runtimes: use official Linux/Windows tools and build Android, OHOS, iOS, with optional macOS. This supersedes the initial desktop target interpretation.
- Adapter builders require patched compiler schema-2 provenance. The producer currently lacks Windows/macOS hosts.
- Repository logical disk usage is 14.887 GiB; tracked files are 8.98 MiB. About 9.86 GiB is regenerable app/build cache.

## Requirements
R1. Use official prebuilt build-host toolchains. Add target runtime builds for Android arm64/x64, OHOS arm64/x64 and iOS arm64 device. Offer macOS x64 as an optional manual target. Do not build Linux/Windows runtime packages in CI.
R2. Preserve the pinned Rust version, source checksum, boundary patch and artifact provenance checks.
R3. Upload complete platform runtime packages, guest data, ABI headers, checksums and build records. Upload diagnostic logs on failure.
R4. Push only to GitHub and run the workflow. Report observed status and exact download location, including failures or platform limitations.
R5. Explain local disk use and cleanup candidates. Do not delete existing local outputs in this task.
R6. Consolidate all current-repository local and GitHub branches into main, verify every tip is retained, set GitHub default to main, and delete the merged branches after verification. Other push destinations are outside this GitHub task.

## Acceptance
- Workflow and build helpers pass relevant static and unit checks.
- A real GitHub Actions run is triggered for the reviewed commit.
- Each requested platform reports its real outcome; successful jobs expose complete downloadable artifacts.
- Documentation distinguishes native runtime packages from app installers and explains Actions downloads and retention.

## Out of scope
Linux/Windows runtime packages, iOS simulator builds, Flutter app installers, release publishing, signing identities, changing runtime availability, and deleting local files.

## Migration coordination — 2026-11-26

This task is a child of 11-26-github-workspace-migration. The migration parent
owns source preservation, shared cloud-only policy and final integration.
All prior local-test instructions are superseded: run builds, tests, analysis,
formatting checks, dependency restoration and Chinese lint only on GitHub.
Do not run local pub get to repair the lockfile.

App integration depends on the core owner's final immutable SHA and verified
Flutter compatibility after concurrent wsui work. Preserve the Dart package
name qfli_studio_core. Editing folders use qflistudio-core. Review pubspec,
lock paths, CI checkout aliases and vendor overrides together. The external
patch_upstream_core.sh belongs to qflistudio-next and is not a Rust requirement
without compatibility evidence. The old core pins are not final migration pins.

Native-compatible artifacts must exist and pass provenance checks before app
packaging. Android armv7 remains pending across host/ABI/ELF32/Gradle layers.
Unsigned iOS/OHOS packages cannot satisfy device-installation acceptance.
No child may claim completion while its required cloud evidence is missing.
