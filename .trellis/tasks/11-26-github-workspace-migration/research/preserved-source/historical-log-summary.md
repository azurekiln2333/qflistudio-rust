# Historical release log knowledge — 2026-11-27 rescue

## Evidence boundary

This is a sanitized summary of the 33 ignored logs under
`.trellis/tasks/10-15-rust-release-readiness/research/`. Their exact relative
paths, raw byte sizes and SHA-256 hashes are in `manifest.json` with category
`historical-release-log`. Originals remain unchanged. No raw log was copied.
No logged command was rerun. These old observations do not establish current
GitHub checks, current source correctness, production signing or device readiness.

The existing tracked `platform-builds.md` and `release-verification.md` in that
release task already describe the main conclusions. This summary preserves the
failure/success distinctions and specific diagnostic lessons without repeating
machine paths, device identifiers, signing values or long generated stack traces.

## Durable lessons retained

- Android release compilation failed while the generated registration source
  referenced the dev-only integration-test plugin. A later exclusive release log
  records a built release APK. Serialize preparation in hosted jobs; do not
  delete the registration entry manually or call the earlier failure a pass.
- The initial Android cancellation regression expected exit `130` but observed
  `null`. A later x64 log ends with seven passing cases. Preserve the original
  failed regression and later result as separate historical evidence.
- A six-case Android pass is not the same coverage as the later seven-case pass.
  Device-discovery warnings and interrupted attempts remain visible in the raw
  logs; a pass line alone does not reconstruct which exact device executed it.
- OHOS signing remained active in attempts that failed with configuration error
  `00303107` / invalid store-file input. A later log records an unsigned HAP.
  An unsigned build is not a successful installation or signed-package pass.
- The OHOS install log reports `9568320` / `no signature file`. Treat that as
  installation failure, regardless of the outer command's exit-code behavior.
- The attempted `:entry:default@DoNativeStrip` task was not found. A task-list
  operation that completed successfully does not prove an application build or
  correct final library stripping. Keep final archive-byte checks separate.
- Compiler/package logs, device transfer, package identity and release process
  observations each cover only their own stage. None alone proves complete
  native/runtime/installer/device acceptance.

## Per-log reviewed disposition

All names below are relative to the release task's `research/` directory.
The manifest, not this table, is the complete exact-hash ledger.

| Log | Sanitized observation retained |
| --- | --- |
| `android-arm64-seven-final-prebuild.log` | Debug APK prebuild output; not a seven-case execution result by itself |
| `android-build-exclusive.log` | Later release APK build output |
| `android-build-serial.log` | Release Java compilation failure involving integration registration |
| `android-build.log` | Earlier release Java compilation failure involving integration registration |
| `android-device-seven.log` | Incomplete attempt with device-discovery failure and debug APK output; not a pass |
| `android-device-test-fixed.log` | Historical six-case pass plus discovery warning; not seven-case coverage |
| `android-device-test.log` | Earlier failed test attempt; later fixed result must remain distinct |
| `android-final-arm64-apk-identity.log` | Package identity record; no execution pass inferred |
| `android-final-arm64-prebuild.log` | Debug APK prebuild record only |
| `android-final-arm64-release-pid.log` | Release process observation; no test-suite pass inferred |
| `android-final-arm64-release-smoke.log` | Release smoke observation; no full native-suite pass inferred |
| `android-final-arm64-seven.log` | Historical seven-case pass line plus discovery warning; retain source context |
| `android-final-build.log` | Later release APK build output |
| `android-final-release-pid.log` | Release process/log observation; contains graphics initialization warning |
| `android-final-release-smoke.log` | Release smoke observation; not a standalone test-suite pass |
| `android-integration-build.log` | Debug integration APK build output only |
| `android-seven-prebuild.log` | Debug APK preparation output only |
| `android-x64-device-seven-fixed.log` | Later historical seven-case pass |
| `android-x64-device-seven.log` | Earlier failed cancellation test: expected `130`, actual `null` |
| `android-x64-seven-final-prebuild.log` | Debug APK preparation output only |
| `android-x64-seven-prebuild.log` | Debug APK preparation output only |
| `ohos-arm64-adapter-build.log` | Adapter compilation record; not HAP installation/runtime evidence |
| `ohos-arm64-build.log` | Historical Hvigor build-success line; retains distinct stage scope |
| `ohos-arm64-package.log` | Native packaging record; no signed installation inference |
| `ohos-build-help.log` | Flutter command-help output; not a build result |
| `ohos-build.log` | Signing configuration failure and device-discovery warning |
| `ohos-device-abi.log` | Device architecture observation; not a packaged runtime result |
| `ohos-device-install.log` | Installation rejected: `9568320` / no signature file |
| `ohos-device-transfer.log` | Transfer record only; transfer is not installation |
| `ohos-final-build.log` | Historical unsigned HAP build output |
| `ohos-strip-check.log` | Requested native-strip task not found; not a stripping verification pass |
| `ohos-task-list.log` | Successful task enumeration only |
| `ohos-unsigned-build.log` | Signing task still ran and failed on store-file configuration |

## Small sanitized excerpts

These excerpts contain only diagnostic facts already described above:

- `android-x64-device-seven.log`: `Expected: <130>` and `Actual: <null>`.
- `android-x64-device-seven-fixed.log`: `00:16 +7: All tests passed!`.
- `android-device-test-fixed.log`: `00:07 +6: All tests passed!`.
- `android-final-arm64-seven.log`: `00:07 +7: All tests passed!`.
- `ohos-device-install.log`: `code:9568320 error: no signature file.`
- `ohos-unsigned-build.log`: `00303107 Configuration Error`.

A limited in-memory secret-shape inventory found no selected key/token/literal
credential pattern in these 33 logs. This is not a guarantee that raw logs are
public-safe. Original logs retain local/device identifiers and may contain
sensitive context outside those patterns; review them separately before any
future publication. This sanitized summary is the portable artifact.
