# Design

Use one manually dispatchable and push-triggered workflow. Build pinned guest MIR data on Linux and share it with independent target jobs. Linux and macOS are build machines using official minimal Rust toolchains, not target runtime deliverables. Cross-compile patched compiler-private libraries and the embedded adapter for Android arm64/x64, OHOS arm64/x64 and iOS arm64 device. Keep macOS x64 an optional workflow_dispatch input. Use macos-15-intel because arm64 hosted capacity blocked both first runs.

Install matching target rust-std into a minimal build-host toolchain. Preserve the project's compiler patch and provenance checks: upstream binaries do not contain the embedded FileLoader/environment boundary changes. Fix the minimal-toolchain detection to allow standard-library rustc_* facade crates while rejecting real compiler-private metadata.

Use NDK 27.0.12077973 for Android. Download and checksum-pin the official OHOS Linux SDK, extracting only its native toolchain. Use the runner's Xcode iPhoneOS SDK for iOS. Existing compiler and adapter scripts own compilation. Existing general and OHOS schema-1 packagers own runtime packaging. Adapt the OHOS PowerShell script to Linux instead of duplicating its manifest contract.

Use fresh isolated runner.temp build roots, bounded parallelism/timeouts and 14-day artifact retention. Upload complete platform-native closures, guest assets, ABI headers, checksums and original build records. Upload diagnostics on failure. Never upload compiler caches or call failed logs a runtime package. Native packaging does not establish app/device execution.

Push only to the explicit GitHub URL. Keep local generated files intact. The desktop producer extension remains usable for developers but is removed from the CI target matrix.
