# GitHub native runtime builds

## Goal
Move expensive native compilation to GitHub Actions. Let the user inspect build status and download complete native packages without keeping compiler intermediates locally.

## Confirmed facts
- GitHub repository: azurekiln2333/qflistudio-rust. No workflow or prior Actions run exists.
- Current branch: feat/rust-offline-ide-20261022. Origin has five push URLs; push only the explicit GitHub URL.
- User approved task creation and immediate implementation, then selected Linux, Windows and macOS.
- Adapter builders require patched compiler schema-2 provenance. The producer currently lacks Windows/macOS hosts.
- Repository logical disk usage is 14.887 GiB; tracked files are 8.98 MiB. About 9.86 GiB is regenerable app/build cache.

## Requirements
R1. Add reproducible GitHub-hosted native builds for Linux x64, Windows GNU x64 and macOS arm64.
R2. Preserve the pinned Rust version, source checksum, boundary patch and artifact provenance checks.
R3. Upload complete platform runtime packages, guest data, ABI headers, checksums and build records. Upload diagnostic logs on failure.
R4. Push only to GitHub and run the workflow. Report observed status and exact download location, including failures or platform limitations.
R5. Explain local disk use and cleanup candidates. Do not delete existing local outputs in this task.

## Acceptance
- Workflow and build helpers pass relevant static and unit checks.
- A real GitHub Actions run is triggered for the reviewed commit.
- Each requested platform reports its real outcome; successful jobs expose complete downloadable artifacts.
- Documentation distinguishes native runtime packages from app installers and explains Actions downloads and retention.

## Out of scope
Mobile builds, Flutter app installers, release publishing, signing identities, changing runtime availability, and deleting local files.
