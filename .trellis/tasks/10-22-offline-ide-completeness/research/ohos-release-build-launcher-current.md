# OHOS release build: owned launcher validation and pub/registrant check

Source-only. No SDK, build, process, WSL or device was launched. No source,
signing, configuration or WIP was edited. No commit.

## 1. `run_owned` API

Defined at `build/offline-ide-audit/run-rust-owned-window.py:164`.

```python
def run_owned(name: str, command: list[str], cwd: Path, log: Path,
              work_deadline: float, cleanup_deadline: float) -> dict
```

- `command` is an argv list, not a shell string.
- Launch is `OwnedJob().start(command, cwd, dict(os.environ), output, output)`:
  stdout and stderr both go to `log`, env is a copy of the parent's.
- Both deadlines are absolute `time.monotonic()` values;
  `work_deadline = min(work_deadline, cleanup_deadline)`.
- Ownership is a Windows Job Object (`rust_owned_job.py`, frozen). `start` calls
  `_winapi.CreateProcess(None, subprocess.list2cmdline(command), ...)`, so
  `lpApplicationName` is `None` and the first token must be a real executable
  image. A `.bat` cannot be started this way; CreateProcess does not invoke
  `cmd.exe`. This is why the existing launcher runs the Flutter tool as
  `[DART, "--disable-dart-dev", FLUTTER, ...]`.
- Return keys read by callers: `emptyJob`, `exit`, `process` (with `pid`),
  plus `timeout` and `orphanCleanup`. `exit` is `124` on timeout, otherwise the
  owned root's `exitCode`.
- Importing `run_owned` alone does not pull in the 90/110 second `main` budgets,
  the grant checks or the `active-owned-window` marker. A separate launcher can
  supply its own 600 s deadlines.

Frozen helper identity matches: `rust_owned_job.py` SHA-256 is
`c0520616e6777d9587a6c0004487bd06a1b19b7d202563f8292c4c1a32c6b172`, equal to
`HELPER_HASH`.

## 2. Exact executable argv for the ohos-arm64 release build

Pinned endpoints (`run-rust-owned-window.py:14-25`):

```text
SDK     = D:/ProgramFiles/flutter_ohos/bin/cache
DART    = SDK/dart-sdk/bin/dart.exe            (4,685,312 bytes, present)
FLUTTER = SDK/flutter_tools.snapshot           (42,027,872 bytes, present)
REPO    = <repo root>
```

Documented production command
(`research/device-14u-deploy-readiness-current.md:41`):

```text
flutter build hap --release --target-platform ohos-arm64 --no-pub
```

Direct snapshot form, matching the launcher's own constants:

```text
D:/ProgramFiles/flutter_ohos/bin/cache/dart-sdk/bin/dart.exe
  --disable-dart-dev
  D:/ProgramFiles/flutter_ohos/bin/cache/flutter_tools.snapshot
  build hap --release --target-platform ohos-arm64 --no-pub
```

As a `run_owned` call, with `cwd = REPO` because `flutter build hap` resolves
`pubspec.yaml` and `ohos/` from the working directory:

```python
run_owned(
    "ohos-arm64 release production build",
    [str(DART), "--disable-dart-dev", str(FLUTTER),
     "build", "hap", "--release", "--target-platform", "ohos-arm64", "--no-pub"],
    REPO,
    run / "01.log",
    phase_deadline,
    deadline - 9,
)
```

Do **not** copy `--no-pub` into a release build; see section 3.

## 3. `--no-pub` release and integration_test registrant contamination

Contamination is not hypothetical. It is present on disk now.

`ohos/entry/src/main/ets/plugins/GeneratedPluginRegistrant.ets` imports and
registers the dev-only plugin:

```ts
import IntegrationTestPlugin from 'integration_test';
...
flutterEngine.getPlugins()?.add(new IntegrationTestPlugin());
```

`pubspec.yaml` lists `integration_test` under `dev_dependencies`, and
`.flutter-plugins-dependencies` marks the ohos entry `"dev_dependency":true`
with `native_build:true`. `integration_test/pubspec.yaml` declares a real ohos
platform implementation (`pluginClass: IntegrationTestPlugin`), so this is a
native plugin registration, not a Dart-only import.

Two independent mechanisms keep it there.

### 3.1 `--no-pub` skips registrant regeneration

- `runner/flutter_command.dart:242`: `shouldRunPub => _usesPubOption && boolArg('pub')`,
  and the `pub` flag defaults to `true`, so `--no-pub` makes it `false`.
- `runner/flutter_command.dart:1963-1970`:
  `regeneratePlatformSpecificToolingIfApplicable` begins with
  `if (!shouldRunPub) { return; }`.
- `injectPlugins` has exactly one call site, `project.dart:443`, inside
  `ensureReadyForPlatformSpecificTooling`, reached only through that method.

So `flutter build hap ... --no-pub` never calls `refreshPluginsList` and never
calls `injectPlugins`. Whatever registrant is on disk is packaged verbatim. With
the current working copy that is the contaminated registrant.

### 3.2 The OHOS registrant writer ignores the release dev-dependency filter

`flutter_plugins.dart:1317-1323` computes the filter:

```dart
if (releaseMode) {
  filteredPlugins = plugins.where((Plugin p) => !p.isDevDependency).toList();
}
```

Android, Linux and Windows receive `filteredPluginsByPlatform`. The OHOS branch
at `flutter_plugins.dart:1349` does not:

```dart
if (ohosPlatform) {
  await _writeOhosPluginRegistrant(project, plugins);   // unfiltered
}
```

`_writeOhosPluginRegistrant` (`flutter_plugins.dart:937`) filters only by
method-channel (`_filterMethodChannelPlugins`), never by dev-dependency.

Consequence: on OHOS the dev-dependency filter is computed and discarded, so
`IntegrationTestPlugin` is written into the release registrant **even when pub
is enabled**. iOS and macOS share the same gap and carry an explicit comment
referencing flutter issue 163874; the OHOS branch has no such note.

No guard fires either: `flutterPluginsListHasDevDependencies`
(`flutter_plugins.dart:331`) is defined but has zero call sites.

### 3.3 Answer

- The OHOS release registrant **does** import the dev-only plugin today. It is on
  disk, not hypothetical: `GeneratedPluginRegistrant.ets` line 2
  `import IntegrationTestPlugin from 'integration_test';` and the
  `getPlugins()?.add(new IntegrationTestPlugin())` registration.
- `--no-pub` release **does** risk shipping it, and currently does ship it: the
  build skips regeneration entirely, so the contaminated file is packaged
  verbatim.
- **The fork passes the raw, unfiltered plugin list for OHOS even with pub
  enabled.** `flutter_plugins.dart:1349` passes `plugins` while
  Android/Linux/Windows receive `filteredPluginsByPlatform`. Enabling pub
  removes staleness only. It never removes `integration_test` on OHOS.
- The module is really built into the HAP, not merely imported: hvigor reports
  record `project has submodules:entry,integration_test,path_provider_ohos` and
  `Module entry Collected Dependency: ...\\integration_test\\ohos`.

### 3.4 Supported clean release preparation: none exists

Searched, source-only:

| Candidate lever | Result |
| --- | --- |
| Flutter build flag to exclude dev plugins | none. `commands/build_hap.dart` exposes only `--target`, `--pub/--no-pub`, `--codesign`, experimentation and performance-file flags. `--no-plugins` exists only for `build_ios_framework` / `build_aar`. |
| Existing script in this repository | none. No file under `scripts/`, `tool/` or `build/offline-ide-audit/` touches `pubspec`, `pub get` or `integration_test`. `scripts/build_rust_catalog_audit.ps1` stages only the three json5 files with byte restore. |
| Ohos module dependency exclusion | not clean. `ohos/entry/oh-package.json5` declares `"dependencies": {}`; the plugin module arrives through tool-generated wiring (`ohos/.hvigor/dependencyMap`, `ohos/entry/oh-package-lock.json5`, the latter marked AUTOGENERATED / DO NOT EDIT). Dropping the module while the registrant imports it fails the ArkTS build instead of excluding it. |
| Temporarily removing `integration_test` from `dev_dependencies`, running pub, then building | works in principle but is unsupported here. It mutates shared pub state (`pubspec.yaml`, `pubspec.lock`, `.flutter-plugins-dependencies`, `.dart_tool/package_config.json`), breaks integration tests until restored, and pairing it with a `--no-pub` build to freeze the clean registrant is exactly the "inconsistent build preparation" the spec forbids concealing. |
| Upstream fix | the correct fix. Make the OHOS branch pass the filtered list, as Android/Linux/Windows do, and delete the dead `flutterPluginsListHasDevDependencies`. This is a Flutter-OHOS fork change, outside this repository. |

There is no supported, in-repository way to produce a release HAP without the
dev-only plugin on this fork.

## 4. Should the normal build enable pub

Yes. `.trellis/spec/backend/native-runtime.md` states:

> Serialize Flutter pub, tests and builds within this workspace. They rewrite
> plugin metadata/registrants; concurrent integration and release preparation can
> leave a release registrant referencing the dev-only integration plugin.
> Regenerate through the normal release build with pub enabled. Do not patch
> generated registrants or the SDK to hide inconsistent build preparation.

So `--no-pub` is non-conforming for the release build, and editing the
registrant or the SDK to clear it is explicitly forbidden. Keep `--no-pub` only
for read-only phases (`dart format`, `dart analyze`, `flutter test`), where
regeneration is undesirable.

Gap to record: on OHOS the spec's mandated remedy is necessary but not
sufficient. A pub-enabled release build still writes `IntegrationTestPlugin`
into the registrant, per section 3.2. That is an upstream Flutter-OHOS fork
defect, not something this repository can fix without patching the SDK or the
generated registrant, both of which the spec forbids.

Do not present enabling pub as a cure for the dev-plugin inclusion. It is not.

### Delivery decision

Because no supported fix exists (section 3.4), the production HAP delivery must
disclose that the packaged application includes the dev-only `integration_test`
plugin and its native module. Record that in the delivery evidence next to the
artifact hash. Do not claim the shipped HAP is dev-plugin free, and do not
attribute its removal to pub being enabled.

## 5. Build prerequisites

Present and verified:

| Input | State |
| --- | --- |
| `dart.exe`, `flutter_tools.snapshot` | present, sizes above |
| `pubspec.yaml`, `pubspec.lock`, `.dart_tool/package_config.json` | present |
| `lib/main.dart` (default entry) | present |
| `ohos/build-profile.json5`, `ohos/entry/build-profile.json5`, `ohos/AppScope/app.json5`, `ohos/hvigor/hvigor-config.json5` | present |
| `rust_owned_job.py` identity | matches `HELPER_HASH` |

Configuration facts:

- `bundleName` `com.azurekiln.qfli.rust`, versionCode `1000000`, versionName `1.0.0`.
- Product `default`: signingConfig `default`, compatibleSdkVersion `5.1.0(18)`,
  targetSdkVersion `6.1.1(24)`, runtimeOS HarmonyOS.
- `ohos/entry/build-profile.json5` excludes `**/x86_64/**`, matching
  `--target-platform ohos-arm64`; it strips debug symbols except
  `**/libqfli_miri.so` and `**/librustc_*.so`.
- `--no-pub` also means dependency resolution must already be current; nothing
  re-resolves it.

Blocking prerequisite, signing: `ohos/build-profile.json5`'s own comment states
the local `.p7b` binds `com.azurekiln.qfli.forge`, not this app's bundle. A
profile is bound to a bundle name, so a signed release build is expected to fail
or yield an unusable artifact until a matching profile exists.

Related trap recorded in the same file: `--no-codesign` does not disable Hvigor
signing in this fork; the typed `properties.enableSignTask=false` does. An
unsigned HAP installs with `code:9568320 error: no signature file` while the
process still exits 0.

## 6. Not performed

No SDK, Hvigor, Flutter, Dart, WSL, device or build command was run. No file was
edited except this report. No commit.
