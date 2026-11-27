# Cleanup and ownership plan — qflistudio-rust — 2026-11-27

This plan records an inventory and preservation decision only. It does not
delete, move or unregister anything in the source workspace, target workspace
or WSL. The approved external backup relocation is copy-only in this pass.

## Preserved external backup

The selected scope contains 589 source entries from `build/content-author-scratch`,
`build/offline-ide-audit` and `native/build/.patchwork`. The external backup at
`D:/MyNewProjects/_migration-backup/qflistudio-rust-20261127/` contains 436
copied files totaling 11,575,677 bytes. All copied files match their recorded
source size and SHA-256. The manifest records 153 skipped entries: 138
generated or binary-extension entries and 15 secret-shape classifications.
Those classifications do not prove credentials. Three classified files also
exist in the published rescue ledger (`_b2.py`, `_d2.py` and
`send-production-hap.py`), and `EntryAbility-online-baseline.ets` was skipped
by the extension rule while preserved in the ledger. The backup is selected
scope only, not a complete private or generated-file backup. The copy is not a
Git source tree and is never executed. Originals remain in place.

## Candidate generated or private paths

The following paths are local-only candidates after source/target parity, provenance review, and owner approval:

- root `build/` outputs and caches
- `.dart_tool/`, Flutter ephemeral directories and plugin symlink trees
- Android and OHOS Gradle/Hvigor/node module outputs, local properties and generated registrants
- `native/build/` generated runtime and patchwork outputs
- `assets/miri/*.bin` and generated native manifests
- ignored Flutter logs and historical raw build/device logs
- editor/session state such as `.claude/`, `.cursor/`, `.pi/`, `.zcode/`, `.trellis/.runtime/` and `.trellis/.developer`

These candidates stay untouched because cleanup is inventory-only and the
original object store must remain available until receiving-clone comparison,
ownership review and credential review finish. Reparse points under generated
OHOS/Flutter trees were not followed or copied. Any later relocation must be
separately approved, path-contained and copy-verified before an owner decides
what may be removed.

## WSL inventory

The read-only WSL inventory found these distributions, all stopped at version 2:
`Ubuntu`, `qfli-terminal-test`, `qfli-terminal-al3-clean`,
`qfli-terminal-al3-test` and `qfli-java-build`. No distribution was started,
stopped, unregistered or modified.

## Safe future sequence

1. Confirm GitHub main, source and target tree/blob parity.
2. Confirm the destination Codex has acknowledged the handover.
3. Confirm owners approve any separately proposed relocation or removal.
4. If relocation is approved, copy to a path-contained external backup and
   verify hashes before changing source state.
5. Re-run read-only status and ownership inventories. No deletion is authorized
   by this plan.

No cleanup is authorized by this document.

## Migration ruling and source-only inventory — 2026-11-27 14:35

The coordinator ruling requires clean tracked HEAD/tree parity. Ignored local
state is expected to differ between clones and is not an additional parity
gate. It still needs an inventory and preservation disposition. The earlier
coordinator snapshot counted 14,790 ignored source entries and zero target
entries. A later read-only directory listing found target
`.trellis/scripts/common/__pycache__/`; runtime-state counts can change without
changing tracked source. Neither count authorizes deletion.

Read-only `git ls-files --others --ignored --exclude-standard --directory`
identified these source-only paths. A trailing slash denotes a collapsed
directory inventory, not a claim that every nested item is generated:

- `.claude/`, `.codebuddy/`, `.cursor/`, `.dsh/`, `.pi/`, `.zcode/`
- `.dart_tool/`, `.flutter-plugins-dependencies`
- `.trellis/.developer`, `.trellis/.runtime/`, `.trellis/.template-hashes.json`
- `android/.gradle/`, `android/build/`, `android/app/src/main/jniLibs/`
- `android/app/src/main/java/io/flutter/plugins/GeneratedPluginRegistrant.java`
- `android/gradle/wrapper/gradle-wrapper.jar`, `android/gradlew`,
  `android/gradlew.bat`, `android/local.properties`
- `assets/miri/` generated `.bin` entries and `manifest.json`,
  `manifest.android-arm64.json`, `manifest.android-x64.json`,
  `manifest.ohos-arm64.json`, `manifest.ohos-x64.json`; retain tracked `.gitkeep`
- `build/`, including retained authored `build/content-author-scratch/` and
  `build/offline-ide-audit/` originals and held `build/app/`/`build/ohos/`
- `flutter_01.log`, `flutter_02.log`, `flutter_03.log`, `flutter_04.log`,
  `flutter_05.log`, `flutter_06.log`
- `ios/Flutter/Generated.xcconfig`, `ios/Flutter/ephemeral/`,
  `ios/Flutter/flutter_export_environment.sh`,
  `ios/Runner/GeneratedPluginRegistrant.h`, `ios/Runner/GeneratedPluginRegistrant.m`
- `linux/flutter/ephemeral/`, `macos/Flutter/ephemeral/`,
  `windows/flutter/ephemeral/`
- `native/build/`, including retained `native/build/.patchwork/` originals
- `ohos/.hvigor/`, `ohos/.idea/`, `ohos/build/`, `ohos/entry/build/`,
  `ohos/entry/libs/`, `ohos/entry/oh_modules/`, `ohos/node_modules/`,
  `ohos/oh_modules/`
- `ohos/entry/oh-package-lock.json5`, `ohos/oh-package-lock.json5`,
  `ohos/local.properties`, `ohos/package-lock.json`, `ohos/package.json`
- `ohos/entry/src/main/ets/plugins/GeneratedPluginRegistrant.ets`,
  `ohos/entry/src/main/resources/rawfile/flutter_assets/`
- `scripts/__pycache__/`

The 33 retained raw logs under
`.trellis/tasks/10-15-rust-release-readiness/research/` are:

```text
android-arm64-seven-final-prebuild.log
android-build-exclusive.log
android-build-serial.log
android-build.log
android-device-seven.log
android-device-test-fixed.log
android-device-test.log
android-final-arm64-apk-identity.log
android-final-arm64-prebuild.log
android-final-arm64-release-pid.log
android-final-arm64-release-smoke.log
android-final-arm64-seven.log
android-final-build.log
android-final-release-pid.log
android-final-release-smoke.log
android-integration-build.log
android-seven-prebuild.log
android-x64-device-seven-fixed.log
android-x64-device-seven.log
android-x64-seven-final-prebuild.log
android-x64-seven-prebuild.log
ohos-arm64-adapter-build.log
ohos-arm64-build.log
ohos-arm64-package.log
ohos-build-help.log
ohos-build.log
ohos-device-abi.log
ohos-device-install.log
ohos-device-transfer.log
ohos-final-build.log
ohos-strip-check.log
ohos-task-list.log
ohos-unsigned-build.log
```

Their raw hashes and sanitized knowledge are in
`research/preserved-source/historical-log-summary.md`. Raw logs were not copied
into published source. Private/local properties and session files stay local;
never print their values. Preserve source-held native/package outputs, original
authored files, the selected external backup and Git objects. Do not follow
Flutter/OHOS reparse points or touch SDK/Pub junction targets. No relocation,
deletion or WSL change was performed for this documentation update.
