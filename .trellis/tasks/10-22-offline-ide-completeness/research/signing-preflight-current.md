# Signing preflight: provision profile vs production bundle (current)

- Query: can the configured signing material produce a production HAP for bundle `com.azurekiln.qfli.rust`,
  and what device constraints does it carry?
- Scope: read-only inspection of local configuration and provision profile payloads.
- Date: 2026-10-26.
- Closes the open item in `device-14u-deploy-readiness-current.md`: "Check the actual provision profile
  against the production bundle and target device."
- No SDK, build, hvigor, hdc or device command was run. No source, signing file or WIP was modified.
- No password, keystore password, private key or certificate private material appears in this note.

## Answer

Two gaps stand between current configuration and a signed HAP.

1. The signing material named by configuration does not exist on disk.
2. No provision profile present on this machine binds `com.azurekiln.qfli.rust`.

Either gap stops signing as configured. A third condition is a constraint, not a gap: every present profile is
`type: debug`, so any HAP they sign installs only on the listed device UDIDs.

A `debug` profile does not block a release-mode build. Build mode and profile type are independent axes. DevEco
and Hvigor sign a `release` build with a debug profile without error. What a debug profile restricts is the set
of devices that may install the result. Distribution type matters for public release through AppGallery, which
lifts that allowlist. It is not required to sign a release build for a personal device.

## Production bundle confirmed

`ohos/AppScope/app.json5:3` sets `bundleName` to `com.azurekiln.qfli.rust`. This matches the requested target.
`ohos/build-profile.json5` selects `signingConfigs[0]` named `default` for product `default`, so signing is
wired and will be attempted. The earlier failure mode where `products[].signingConfig` was absent does not
apply to the current file.

## Defect 1: configured material is missing

`ohos/build-profile.json5` points `certpath`, `profile` and `storeFile` at these three names:

```
C:\Users\lichengyu\.ohos\config\default_ohos_EyK2s6zPODEbf3XHtkcGYQQuAS6k-HePGMeNPRNUwSI=.cer
C:\Users\lichengyu\.ohos\config\default_ohos_EyK2s6zPODEbf3XHtkcGYQQuAS6k-HePGMeNPRNUwSI=.p7b
C:\Users\lichengyu\.ohos\config\default_ohos_EyK2s6zPODEbf3XHtkcGYQQuAS6k-HePGMeNPRNUwSI=.p12
```

All three are absent. A recursive listing of `%USERPROFILE%\.ohos` returns no file with the
`EyK2s6zPODEbf3XHtkcGYQQuAS6k-HePGMeNPRNUwSI=` suffix for any extension. The directory holds eight complete
`.cer` / `.csr` / `.p12` / `.p7b` sets, all with other suffixes.

Consequence: Hvigor signing cannot read the configured material. Any build using this configuration fails at
or before SignHap. Do not read the present `.p7b` files as the configured ones. They are different files.

## Defect 2: no profile binds the production bundle

Eight provision profiles exist in `%USERPROFILE%\.ohos\config`. Payloads were parsed from the embedded profile
JSON inside each `.p7b`. All eight share `issuer: app_gallery`, `version-name: 2.0.0`, `developer-id:
10086000920797470`, `type: debug`, `device-id-type: udid`, and `acls: ohos.permission.READ_PASTEBOARD`.

| `.p7b` suffix | bundle-name | devices | validity (UTC) |
| --- | --- | ---: | --- |
| `Gu8zVby7…` | `com.azurekiln.qfli.java` | 2 | 2026-10-16 → 2027-10-16 |
| `GxYLofwt…` | `com.azurekiln.qfli.script` | 2 | 2026-10-15 → 2027-10-15 |
| `H2qDWxiv…` | `com.azurekiln.qfli.dartwing` | 2 | 2026-10-15 → 2027-10-15 |
| `HCrb5IAC…` | `com.azurekiln.qflistudio` | 3 | 2026-10-22 → 2027-10-22 |
| `PCM4VcSp…` | `com.azurekiln.qfli.go` | 2 | 2026-10-17 → 2027-10-17 |
| `udwsx4sz…` | `com.azurekiln.cloudterminal` | 2 | 2026-10-12 → 2027-10-12 |
| `unkvfObb…` | `com.azurekiln.qfli.note` | 3 | 2026-10-23 → 2027-10-23 |
| `weTSdRQh…` | `com.azurekiln.qfli.cpp` | 2 | 2026-10-16 → 2027-10-16 |

No row is `com.azurekiln.qfli.rust`. No row is `com.azurekiln.qfli.forge`, so the warning comment in
`ohos/build-profile.json5` naming `forge` is stale on that point as well. The comment also states the app bundle
as `com.azurekiln.qfli.rustcore`, which contradicts `app.json5`. `rustcore` is the identifier used by the
Android, iOS, macOS and Linux runners, not by the OHOS app.

## Profile type is not build mode

Every present profile is `type: debug`. This constrains installation, not signing. A debug profile signs a
`release`-mode build. The build modes `debug`, `profile` and `release` in `ohos/build-profile.json5` are a
separate axis from the profile's `type`.

Earlier wording in this note treated the absence of a distribution-type profile as a signing blocker. That
inference was unsupported and is corrected here. An independent review rejected it.

What `type: debug` does impose: the signed HAP installs only on devices listed in the profile's
`debug-info.device-ids`. A distribution-type profile, issued for AppGallery release, drops that allowlist. Do
not read a debug profile as a release-build blocker.

## Device constraints

The allowlists use UDID strings, not IP addresses.

- Two UDIDs appear in every profile:
  - `454D55057494E058383602E35E0E6866143E0A683AFBA33F3FBFF00000000000`
  - `92E9A6F718215C29D61E10F6EFD6F5A736961E9357BE34828A839CB42B565BA0`
- A third UDID appears only in `HCrb5IAC…` and `unkvfObb…`:
  - `454D55057494E058383602DD9C05BCD9E4026BE286E3F6B3CC57700000000000`

A debug-signed HAP installs only on a device whose UDID is listed in the profile that signed it. The target
endpoint `192.168.68.207:46551` cannot be mapped to a UDID without a device query, and no device command was
run. Treat the endpoint-to-UDID match as UNVERIFIED. Even a correctly bundled profile would fail installation
if the target device's UDID is not in its list.

## What a working production signing setup requires

1. A provision profile whose `bundle-info.bundle-name` is `com.azurekiln.qfli.rust`.
2. The `.cer`, `.p7b` and `.p12` triple that the profile belongs to, present at the paths
   `ohos/build-profile.json5` names.
3. `keyAlias` matching the key inside that `.p12`.
4. The target device's UDID listed in the profile when the profile is `type: debug`.
5. Confirmation that the target device accepts the resulting signature.

A `type: debug` profile satisfies this list for a personal-device build, including a `release`-mode build.
Choose a distribution-type profile only when the goal is public AppGallery release without a device allowlist.

Do not change `bundleName` to reuse another application's profile. That would ship the wrong application
identity and would overwrite-install against the real owner of that identity.

## Correct stale comments

`ohos/build-profile.json5` lines 2-6 and 19-22 describe an older state. They name `forge` and `rustcore`, and
they describe the missing-`signingConfig` failure. The current file does set `signingConfig`. Correcting these
comments is a separate edit and was not made here.

## Not run

- No `flutter build hap`, `hvigorw`, `hdc`, SDK or WSL command.
- No signature validation of any existing HAP.
- No mapping of `192.168.68.207:46551` to a UDID.
- No install or launch attempt.
- No change to any source, signing file, keystore or WIP.

## Evidence

- `ohos/build-profile.json5` — signing configuration and product selection.
- `ohos/AppScope/app.json5` — production bundle name.
- `ohos/entry/build-profile.json5` — module targets, x86_64 exclusion.
- `%USERPROFILE%\.ohos\config\*.p7b` — eight provision profiles, payload parsed read-only.
- `%USERPROFILE%\.ohos\config\*.cer`, `*.csr`, `*.p12` — presence and size only. No secret was read out.
