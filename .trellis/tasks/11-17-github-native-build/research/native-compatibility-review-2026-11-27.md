# Native compatibility and focused cross-layer review — 2026-11-27

## Scope and evidence limits

Worker D owns `scripts/ci_native_runtime.py`, `scripts/test_ci_native_runtime.py`,
necessary native-workflow changes and this native-task research note. Follow-up
ownership added `.github/workflows/cloud-checks.yml` for independent hosted
validation. Other workers own application orchestration, packaging, manifests
and dependency pins. The coordinator owns Git writes.

This review used source inspection and read-only Git queries. No build, test,
formatter, analyzer, dependency restore, installer, artifact download or local
validation command ran. No commit was made. No core SHA was selected.

This note records current implementation facts, not a new successful cloud run.
The earlier run IDs in `cloud-runs.md` remain historical evidence. They do not
validate this change, the pending installer workflow or Android armv7.

## Change implemented

File: `scripts/ci_native_runtime.py`, function `collect_package`.

The collector previously copied two Android native-library trees into the
payload, but checked native hashes and optional sizes only in the source
`native/build/runtime/<key>` tree. The separate `android/app/src/main/jniLibs`
copy consumed by Gradle could differ without stopping archive creation.

The collector now checks the actual copied payload bytes before creating the
archive. It checks the exported runtime tree for every platform. For Android it
also checks the exported ABI-specific `jniLibs` tree against the same manifest.
A mismatching copy fails before the archive is written. Missing files also fail
before archive creation through the existing filesystem error path.

The change preserves schema-1 OHOS entries (`name` plus hash, no size), schema-2
entries (`path` plus hash and size), iOS framework-relative paths, output names,
provenance records, action pins, retention and concurrency. The workflow file is
unchanged. The default matrix remains five mobile targets with optional macOS x64.

Read-back confirmed the exact changed loop. No executed validation is claimed.

## Android armv7: blocked, not silently implemented

A matrix-only addition is unsafe. Evidence from the checked-in sources:

| Boundary | Existing behavior | Required coordinated work |
| --- | --- | --- |
| `scripts/ci_native_runtime.py`: `CI_HOSTS`, `workflow_matrix` | Android arm64 and x64 only | Add the new host/package only after lower-layer support exists |
| `scripts/miri_build_support.py`: `HOSTS` | No `armv7-linux-androideabi` | Define the reviewed architecture identity and all consumers |
| `scripts/build_rustc_host.py`: `BOOTSTRAP_HOSTS`, `android_tools` | Hosts derive from `HOSTS`; Android wrappers concatenate the Rust host and API | Establish correct NDK target/tool/library lookup and compiler-host support |
| `scripts/build_miri_adapter.sh`: Android branch | Accepts only aarch64/x86_64 Android and sets their Cargo linker variables | Add explicit armv7 compiler/linker behavior and regressions |
| `scripts/package_miri_runtime.py`: `inspect_elf` | Requires little-endian ELF64; accepts machine 62 or 183 | Add reviewed ELF32/ARM layouts, bounds checks and malformed-input fixtures |
| `scripts/package_miri_runtime.py`: `install_android`; CI `collect_package` | Any architecture other than arm64 falls back to x86_64 | Replace unsafe two-way mapping in every relevant producer/consumer |
| `android/app/build.gradle.kts`: `rustAbiMapping` | Rejects `android-arm`; permits only arm64-v8a/x86_64 | Extend ABI filters and manifest selection without routing ARM to arm64 |
| Gradle `checkAndroidRustRuntime` | Any non-x86_64 ABI selects architecture arm64 | Introduce an explicit three-way identity mapping |
| `lib/native_miri_assets.dart`: `NativeMiriTarget.nativeHosts` | No Android `arm` host; current ABI determines the manifest suffix | Define loader architecture/manifest identity consistently |
| `lib/main.dart`: `runtimeStatus` | Android availability covers only androidX64/androidArm64 | Keep unavailable until architecture-specific packaged execution is established |
| Installer task and helper target tables | Original plan promises three APKs; initial helper declares only two ABIs | Keep armv7 acceptance open; never call two APKs a three-ABI result |

The compiler bootstrap also requires a matching Cranelift backend and the fixed
x86_64 interpreted guest. This inspection does not establish that the complete
pinned compiler/backend/guest arrangement works on a 32-bit Android native host.
That is a feasibility gate, not permission to bypass backend or provenance checks.

Most required changes are outside Worker D ownership. No armv7 matrix row or
partial ABI support was added. Do not remove existing 64-bit checks to make the
new row appear supported. The parent design already requires a cross-layer
assessment before extending this contract.

## Existing producer/consumer contract to preserve

- Runtime archives contain `build-info/ci-build.json`, `compiler-build.json`,
  `adapter-build.json` and `miri-sysroot.json`, plus both ABI headers.
- `ci-build.json` records source commit, run ID/attempt, target and pinned Rust
  identity. `runtimeExecuted` and `deviceExecuted` remain false.
- Android and Apple use schema 2. Their manifests contain platform,
  architecture, native host, library relative paths, roles, sizes and hashes.
  Compiler/adapter record hashes are under `compilerBuild` and `adapterBuild`.
- OHOS uses schema 1. It has an exact native host and guest target, but no
  platform/architecture fields and no per-library role/path/size. Native entries
  use `name` and `sha256`. Record bindings are `compilerBuildSha256` and
  `adapterBuildSha256`. Infer its target only from the reviewed native-host map.
- OHOS arm64 also exports legacy `assets/miri/manifest.json`. OHOS x64 must not
  overwrite that arm64 fallback. The existing producer preserves this behavior.
- Android packages export both runtime and ABI-specific `jniLibs` inputs.
  iOS uses the native-host triple as its runtime package directory.
- Guest/toolchain identity, compiler-boundary patch hashes and paired private
  metadata remain mandatory. Equality of ABI headers alone does not establish
  source compatibility of a runtime selected from another application commit.
- Native runtime and diagnostics retention is 14 days. Shared guest retention
  is one day. Artifact availability must be checked when the installer resolves
  inputs; historical success does not prove an artifact remains downloadable.
- Desktop application jobs use installed cargo/rustc. Native workflow outputs
  are not six-platform Flutter application installers or signing evidence.

The schema distinction and armv7 blocker were sent to Worker B through Herdr.

## Independent quality findings and integration gates

1. **Fixed in scope:** the Android archive's consumed `jniLibs` copy lacked a
   manifest hash/size check at collection. Both exported native trees are now
   checked after copying, before archive creation.
2. **Blocking armv7:** host, compiler, adapter, parser, ABI, Gradle and Dart
   changes must be reviewed together. Existing acceptance still requires an
   explicit blocking report when no armv7 artifact exists.
3. **Installer provenance gate:** resolve a successful run and verify actual
   compiler/adapter record hashes, source/input compatibility, native host,
   guest identity, headers, archive digest and manifest-covered bytes. Do not
   select arbitrary latest-successful artifacts based only on the Rust version.
4. **OHOS compatibility gate:** a schema-2-only installer decoder rejects valid
   existing OHOS archives. Preserve the explicit schema-1 adapter described above.
5. **Core handoff gate:** the final immutable core SHA and Flutter compatibility
   remain with the core owner/coordinator. Neither stale core SHA is approved by
   this review. Native producer work does not resolve that application gate.
6. **Evidence gate:** existing native tests retain collection corruption and
   mobile layout fixtures. Worker D added the Android dual-copy regression after
   receiving ownership of the test file. It is authored, read back and unrun.

## Required follow-up on GitHub only

Worker D added
`test_changed_android_jni_library_cannot_create_success_archive` in
`scripts/test_ci_native_runtime.py`. It covers arm64 and x64 with same-size
corruption of only Android `jniLibs`, retains the valid runtime copy, expects
the JNI-library error, asserts `archive_tree` was not called and checks that
neither `.tar.gz` nor its checksum was published. Existing corruption and mobile
layout checks remain. No local test ran. Execute this regression on GitHub
before calling the fix validated.

The independent `cloud-checks.yml` runs native/helper suites and syntax/policy
checks without a core pin or long native compilation. It reports absent
committed app CI as not run. Once app CI is committed, missing required helpers
or test suites fail closed rather than silently skipping application coverage.

Run the native CI-helper, compiler provenance/support and packager regressions
on hosted runners, including `scripts/test_ci_native_runtime.py`,
`scripts/test_build_rustc_host.py`, `scripts/test_miri_build_support.py` and
`scripts/test_compiler_provenance_consumers.py`. Validate workflow syntax and
shell/PowerShell syntax on GitHub. Do not run these commands locally.

Then run the five supported mobile targets through the real compiler, adapter,
packager and archive path. Record exact commit, run ID, per-job outcome and
artifact retention. Check both Android payload native copies against their
manifest. Optional macOS remains separate. Packaged source/device execution and
signing are independent acceptance items, not consequences of a native build.

Armv7 requires a separately coordinated implementation and feasibility review,
then ELF32 regressions, actual hosted bootstrap/package evidence and matching
application/runtime acceptance. Its status remains blocked.
