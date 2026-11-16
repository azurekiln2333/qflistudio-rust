# Local disk inventory — 2026-11-17

Read-only Windows long-path inventory. No files were removed.

- Repository: 14.887 GiB, 16,575 files.
- Git-tracked files: 584 files, 8.98 MiB. No tracked native binaries or archives.
- Regenerable app/cache candidates: build/app 4.204 GiB, build/ohos 1.231 GiB,
  ohos/entry/build 2.655 GiB, ohos/build 0.604 GiB,
  .dart_tool/flutter_build 1.169 GiB. Total approximately 9.86 GiB.
- native/build 3.329 GiB includes miri-windows 2.604 GiB, runtime 0.337 GiB
  and device 0.383 GiB. Preserve until replacements are verified.
- android/app/src/main/jniLibs 0.337 GiB, ohos/entry/libs 0.463 GiB,
  assets/miri 0.118 GiB are inputs needed by local app packaging.
- Do not remove the whole build/ tree: audit reports, screenshots and authored
  helper files also live there. Existing APK/HAP files require retention decisions.

GitHub builds reduce future local compilation intermediates; they do not delete
these existing files. No local cleanup was requested or performed.
