# Design and change boundaries

## Ownership

Rust owns its lib runtime/adapters/tools, tool/rust_content authored sources,
assets/content_rust generated catalogs, native adapter, scripts and tests.
C owns core filters/badges, code_analysis API, squiggles/Problems and grammars.
Confirm the explorer/history/multi-root owner before integration. Never revert
parallel changes. Root owns main.dart wiring, records, specs and scoped commits.

## Verification before expansion

Retain the host verifier as host evidence. Add a catalog device/native harness
driven by exact authored inventory: every example and answer, attached files,
SHA-256, expected stdout and exit status. Bind reports to catalog hashes, host,
compiler revision, runtime content ID, manifest and packaged application.
Continue after individual failures with bounded cancellation/timeout; missing
cases and interrupted runs are incomplete, never passes. Enumerate every
desktop/cargo/external-labeled record instead of skipping it. Repair current
engine/content incompatibilities without removing meaningful teaching.
No new topic publication before the baseline OHOS execution gate passes.

## Nonexecuting Rust diagnostics

Implement CodeAnalyzer using exact immutable unsaved snapshots. Mirror required
project source in a temporary root and overlay all open buffers. Preserve CRLF,
map rustc JSON spans to UTF-16 ranges in original snapshots, and clean temporary
files after completion/cancellation. Invoke rustc directly, metadata-only with
JSON diagnostics and bounded lifetime, using the real entry/module graph.
Do not invoke Cargo/build.rs, user programs, annotation processors or proc macros
merely to analyze. Never overwrite project files. Backend failures are explicit.

Desktop rustc supports analysis without source execution. OHOS needs a native
analysis-only entry through the pinned adapter, stopping before Miri evaluation.
Reuse real compiler diagnostics, not regex approximations claiming clean Rust.
Native changes require ABI, exact pinned builds and packaged-device validation.

## Direct offline tools

Use StudioProfile.toolsTabBuilder inside the existing core Scaffold. Provide
responsive direct sections for Rust integer literals/type bounds/bit operations,
UTF-8 and Rust string literal inspection, and local Cargo target/project
inspection through the existing resolver. Keep shared common tools accessible.
No extra Scaffold or secondary language-tool route. Use BigInt for wide Rust
integers and state target assumptions such as usize width. Pure tools never
alter source or initiate a network operation.

## Debug and panels

Inspect the pinned rustc/Miri ABI before showing controls. Diagnostics are not
a debugger. Preserve real terminal streams/cancellation and consume coordinated
shared Output/Debug Console/local Ports APIs. Actual breakpoints require pause,
resume, step, stack and variable support. Keep unsupported requirements open.

## Compatibility and rollback

Profile hooks remain optional for other products. Existing content IDs/imports
stay compatible. Revert only owned paths; never reset signing/user/parallel work.
Serialize Flutter pub/analyze/test/build within this workspace. Keep manifest-
covered native library bytes intact and separate host/device/native evidence.
