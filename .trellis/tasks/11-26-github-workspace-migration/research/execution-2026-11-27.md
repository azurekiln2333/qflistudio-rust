# Migration execution evidence — 2026-11-27

## Ownership and execution boundary

The user approved execution through Claude w61:p6. The task is active and
in_progress. Source is D:/MyNewProjects/qfli_rust. Target is
E:/MyNewProjects/QFLIProjects/qflistudio-rust. GitHub is authoritative.
Source origin still has five push URLs; publication uses the explicit GitHub
URL and main:main refspec. Workers make source edits through Herdr and no Git
writes. All builds, tests and executable checks run on GitHub-hosted runners.

## Published checkpoints

| Commit | Preserved work | Evidence boundary |
| --- | --- | --- |
| c859677d482ef358c5aed2efdad7e2daf9a6b288 | Portable Trellis/skills, cloud-only rules, dependency path metadata, sanitized OHOS profile, native copy integrity and cloud checks | First independent check run failed on fixture paths, Windows checkout bytes and three guide lint findings |
| a07511394cfc8a8079e226e37468c571b9d0ed1e | Historical source rescue, selected-tool fixture expectations, Windows LF checkout and guide corrections | Four independent hosted check jobs passed; application helpers were not yet committed |

The removal of machine-specific OHOS signing values does not erase their prior
Git history. Do not print the removed-value diff. Credential rotation/history
remediation remains with the credential owner; no force rewrite occurred.

## Hosted checks

Cloud checks 45890223129 at c859677 failed. Ubuntu ran 291 native tests with
three skips and passed. macOS had two selected-tool alias expectation failures.
Windows had three corresponding alias expectations and catalog/hash failures
caused by CRLF conversion of raw-hash-bound JSON. The source-policy job passed
syntax, action pin, actionlint and ignore checks, then failed only three guide
synonym findings. No test suite or lint rule was disabled.

Cloud checks 45894657274 at a075113 completed successfully in all four jobs.
Each OS ran 291 native tests; Windows skipped one, Linux/macOS skipped three.
The Android JNI-only corruption regression passed. Source/workflow/portability
policy and controlled-Chinese checks passed. Application helper coverage was
explicitly NOT RUN because those files were not part of that commit.

Native runtime 45890222976 at c859677 completed successfully: shared guest,
Android arm64/x64, OHOS arm64/x64 and iOS arm64. GitHub metadata was inspected;
no runtime archive was downloaded locally. Native package success does not
establish Flutter application, installer, signing or device success.

| Runtime artifact | GitHub artifact ID | ZIP bytes | Expires (UTC) |
| --- | --- | ---: | --- |
| native-runtime-android-arm64 | 15151693086 | 128544928 | 2026-12-10 20:35:34 |
| native-runtime-android-x64 | 15152336164 | 128568921 | 2026-12-10 20:34:49 |
| native-runtime-ohos-arm64 | 15151932676 | 86390143 | 2026-12-10 20:39:39 |
| native-runtime-ohos-x64 | 15151673573 | 86137540 | 2026-12-10 20:38:02 |
| native-runtime-ios-arm64 | 15155620318 | 76131132 | 2026-12-10 21:39:05 |

The guest artifact 15150992942 expires 2026-11-27 20:21:46 UTC. Runtime artifact
metadata was unexpired at inspection. Retention is finite, not a durable release.

Native runtime 45894657258 at a075113 subsequently started. Its shared guest
passed; all five target jobs were running at inspection. The exact scripts tree
changed with fixture fixes, so the app resolver must use an input-compatible
completed run rather than assuming the c859677 artifacts satisfy its gate.

## Exact-byte rescue correction

The 119 preserved worktree copies match the ledger: 2,329,864 bytes. Initial
a075113 publication normalized 43 copies. The directory-local * -text rule now
preserves raw historical source, evidence and manifest bytes. Coordinator
restaging and index-blob comparison found 119 exact copies and zero mismatches.
The cached rescue diff with end-of-line whitespace ignored contains only the
new attribute file. Original files and Git objects remain untouched.

The ledger SHA256 is
9521f09701b5aebc749b6329b8ba1ccd311057d9a9c18310a9ca2f77cf872e84.
Corrective publication and target raw-byte comparison must be recorded before
claiming this preservation gate complete. All 14 unreachable blobs are mapped
in the rescue ledger: 11 copies and three exact index duplicates.

## Application implementation and review

B owns ci_support.py/app_build.py/test_app_build.py/app-installers.yml.
C owns package_installer.py/windows_installer.iss/test_package_installer.py
and the new app_quality.py/test_app_quality.py/app-quality.yml.
D reviews their source. Application helpers have no hosted pass yet.

D's producer-byte-chain, typed Hvigor no-sign and actual intermediate-byte
findings were addressed in source. A final publication-error cleanup edge in
B's finalizer remains assigned to B with a checksum-failure regression. C's
quality-only finalizer needs its own failure handling; installer finalization
is not a quality workflow API. Both final handoffs and D review remain pending
at this checkpoint. No source review is represented as an executed pass.

## Core and SDK gates

Core w63:p1 reconfirmed that no final migration SHA or final Rust SDK/native-hooks
contract is available. Do not set approval variables from provisional main.
Known provisional core is 476a30acee21dc486ee2849dd8064a7be665e4d5. Owner-reported
core-check 45689025146 passed Ubuntu analysis/tests/screenshots, not Rust native
hooks or application installers.

The known Flutter fork is openharmony-tpc/flutter_flutter, tag
3.41.10-ohos-1.0.1, commit adaf911c35c9136a7d18fc424d714c9ec7724e60.
The pinned app installer is qflistudio-next tool/ci/setup_flutter.sh at
69656b4ab14e706e85907ef4c4205d8cd35a1338, blob
05cb24cc4f0ecc3cbefbf9fe6f8a8e917ac14a05. Core owner found no external tooling
override in that immutable script/workflow. Fork internals and Rust hooks remain
unverified. Do not reuse old 9d2eaf tooling pins or copy the app-owned upstream
patch speculatively. The editing directory is qflistudio-core; the Dart package
remains qfli_studio_core.

Core also reports its interop_arkts_contract_test.dart uses historical sibling
aliases. Full core-suite execution in the canonical layout needs an owner fix
or reviewed adaptation. That finding does not replace Rust's own root tests.

## Receiver and cleanup

Target w6C:p1 still reserves a clean clone at 540674f for the final fast-forward
and comparison. No ownership transfer has occurred. The existing startup
transcript says Hook failed / hook exited with code 1 without command/stderr.
F2 exposed a separate service-tier/model support warning, not hook diagnostics.
No hook cause or successful repair is inferred and no hook was invoked.

No old output, original object or WSL distribution has been deleted. Shared
WSL paths remain outside Rust ownership. See audit-2026-11-26.md and the rescue
ledger before any cleanup. Parent/native/installer tasks remain in_progress.
