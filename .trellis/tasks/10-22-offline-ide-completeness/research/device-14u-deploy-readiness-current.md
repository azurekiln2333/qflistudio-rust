# Research: Current OHOS delivery readiness for 14u

- Query: Identify the production OHOS build path and blockers before delivery to 192.168.68.207:46551.
- Scope: internal. Read-only source, configuration and archive inspection.
- Date: 2026-10-26

## Findings

### Delivery decision

The existing HAPs are dated 2026-10-17. They are not evidence of a build from current source. Their archived
module configuration requests INTERNET, whereas current source omits it. Do not present these archives as the
requested current offline build.

The device OS and transport remain unconfirmed. The name 14u and the port do not establish compatibility with
OHOS HAP installation. The parent session owns endpoint discovery and actual deployment.

### Files found

- `ohos/build-profile.json5`: production product, SDK versions and local signing configuration.
- `ohos/AppScope/app.json5`: production bundle and application version.
- `ohos/entry/build-profile.json5`: native architecture exclusion.
- `ohos/entry/src/main/module.json5`: current permission declarations.
- `.trellis/spec/backend/native-runtime.md`: build, signing and installer contracts.
- `.trellis/spec/backend/compiler-build-provenance.md`: compiler and adapter provenance requirements.
- `assets/miri/manifest.ohos-arm64.json`: currently packaged ARM64 native runtime manifest.
- `assets/miri/manifest.ohos-x64.json`: currently packaged x64 native runtime manifest.
- `scripts/package_miri_ohos.ps1`: native packaging with required adapter build information.
- `scripts/build_rust_catalog_audit.ps1`: separate unsigned audit build, not production delivery.

### Production configuration and command

`ohos/AppScope/app.json5:3` sets bundle `com.azurekiln.qfli.rust`. Lines 5-6 set versionCode 1000000 and
versionName 1.0.0. `ohos/build-profile.json5:36` selects signing configuration default. Lines 37-39 select
compatible SDK 5.1.0(18), HarmonyOS and target SDK 6.1.1(24). `ohos/entry/build-profile.json5:8` excludes
x86_64 libraries. The current production path is ARM64.

The production command derived from the established Flutter HAP invocation is:

```powershell
flutter build hap --release --target-platform ohos-arm64 --no-pub
```

This assumes dependencies are already resolved and the configured Flutter OHOS fork is available. It uses the
default application entry point. This research did not execute the command or establish that it currently
succeeds.

Local signing comments warn that the configured provisioning profile binds another bundle. This is a warning,
not verification of the current profile payload. Check the actual provision profile against the production
bundle and target device. Do not change the production bundle merely to reuse another application's signing
profile. No credentials are reproduced here.

`ohos/entry/src/main/module.json5:37` documents the offline permission choice. Line 40 requests
READ_PASTEBOARD. The source does not request INTERNET.

### Existing archives

The following were inspected as ZIP archives without executing build or device tools:

| Archive | Bytes | Date | Observed content |
| --- | ---: | --- | --- |
| `ohos/entry/build/default/outputs/default/entry-default-signed.hap` | 468889439 | 2026-10-17 | Production bundle, arm64-v8a, six native libraries, INTERNET permission |
| `ohos/entry/build/default/outputs/default/entry-default-unsigned.hap` | 466156516 | 2026-10-17 | Production bundle, arm64-v8a, six native libraries, INTERNET permission |
| `build/ohos/hap/entry-default-signed.hap` | 468889439 | Existing copy | Not independently signature-verified |
| `build/ohos/hap/entry-default-unsigned.hap` | 467773128 | Existing copy | Not independently signature-verified |

The signed filename is not proof of a valid signature for this device. No archive hash or signature validation
was performed.

### Native capability and provenance blockers

Both current native manifests lack compilerBoundary, compilerBuildSha256 and adapterBuildSha256 fields. The
ARM64 manifest identifies host aarch64-unknown-linux-ohos and runtimeId
942da7d84754906a38ce4806af64080f1624550860dd6b1e422cd6efd8550fa7. The x64 manifest identifies host
x86_64-unknown-linux-ohos and runtimeId 8bb951941b7088b5f920ebb4e77305022494c3a801164b75e21ea29085b150c4.

Prior static research records only 10/27 required exports in current packaged libraries
(`research/hap-inspector-dependency-review-current.md:123`). The current gate requires 27 callable exports
spanning run, analysis and debugging (`research/hap-inspector-checkpoint-current.md:10`). The checkpoint
records that no patched compiler or complete adapter was built
(`research/checkpoint-20261026-provenance-push.md:49`). These are inherited static findings, not fresh device
acceptance.

A Flutter build may package current Dart/UI source with existing native assets. It cannot manufacture the
missing native analysis/debugger exports or compiler confinement. Such a package cannot establish complete
current native capability or pass the provenance gate.

For complete delivery, build the patched compiler and matching metadata/runtime, build the ARM64 OHOS adapter,
regenerate native assets and manifest with trusted records, build the signed production HAP, inspect that
exact archive, then install and launch on a confirmed compatible device. `scripts/package_miri_ohos.ps1:3`
requires AdapterBuildInfo. Its packaging command passes that record at line 69.

### Unsigned build caveat

The established unsigned Flutter command is `flutter build hap --release --target-platform ohos-arm64
--no-codesign` (`.trellis/tasks/10-15-rust-release-readiness/research/platform-builds.md:268`). In this fork,
the flag alone does not disable Hvigor signing (`.trellis/spec/backend/native-runtime.md:124`). Direct Hvigor
uses typed `-c properties.enableSignTask=false -p TARGET_PLATFORM=ohos-arm64 --no-daemon` (line 43). The
Flutter path also requires the temporary typed Hvigor configuration described at lines 46-47, with exact
original bytes restored afterward.

An unsigned install can return process exit 0 while text reports 9568320 / no signature file
(`.trellis/spec/backend/native-runtime.md:131`). Treat that text as installation failure.

The catalog audit wrapper is a distinct artifact: it requires CompilerRecord and AdapterRecord
(`scripts/build_rust_catalog_audit.ps1:3`), uses bundle com.azurekiln.qfli.rust.audit (line 36), and targets
lib/main_catalog_audit.dart (line 37). Do not substitute it for the production app.

### Related specs and external references

Read `.trellis/workflow.md`, `.trellis/spec/backend/native-runtime.md`,
`.trellis/spec/backend/compiler-build-provenance.md`, and this task's PRD, design and implementation notes. No
external research was needed. SDK versions above are local configuration values, not externally verified
availability claims.

## Caveats / Not Found

- No build, compiler, SDK, WSL, device or transport commands were run in this research.
- No source, signing configuration or foreign process was changed.
- No fresh device OS, signing compatibility, installation or launch proof exists in this report.
- Shared host scheduling and current resource capacity require the parent's fresh coordination. This report
grants no build execution authorization.
- Full native capability remains blocked by missing current compiler/adapter builds and trusted records.
