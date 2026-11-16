# Design

Use one manually dispatchable and push-triggered workflow. Build pinned guest MIR data on Linux and make it available to independent native matrix jobs. Native jobs use fresh isolated build roots and minimal official build compilers, apply the existing compiler patch, bootstrap compiler-private libraries, build the existing adapter and call the existing runtime packager. Extend the compiler producer for Windows GNU and macOS SDK tools. Keep provenance strict and preserve source inputs.

Use GitHub-hosted ubuntu-24.04, windows-2022 and macOS 15 arm64 runners. Bound build parallelism and job duration. Install tools through platform package managers or preinstalled runner tools. Use source vendoring or explicit locked dependency prefetch for clean CI. Do not upload compiler intermediate trees. Publish only the verified runtime closure and guest assets, plus human-readable build status and original records.

Upload diagnostics even when builds fail. A failed build must stay failed and must not create a success-labelled runtime package. Treat the first run as a real integration test and fix observed failures within this scope. Native artifact production does not establish packaged app execution.

Push via the explicit GitHub URL because origin has unrelated mirror push URLs. Preserve source/checksum pins. Rollback is removal of the new workflow/helper and reverting producer host support.
