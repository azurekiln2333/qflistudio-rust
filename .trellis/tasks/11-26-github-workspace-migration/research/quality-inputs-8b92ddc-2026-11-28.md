# Quality inputs and hosted findings at 8b92ddc

Recorded on 2026-11-28 from the sole watcher's frozen evidence and a source-only
review. No CI query, local executable check, artifact download or Git write was
performed for this report. Repairs described below have not run on a hosted
runner at their new revision.

## Input identities and evidence

| Input | Identity |
| --- | --- |
| Rust source | `8b92ddc98151a394a57a5d5ce3eb0bea35f2266e` |
| Approved core | `8e031313ffc8d531c5a6b4d131f721f35da04c86` |
| SDK contract | `flutter-oh-3.41.10-ohos-1.0.1@adaf911c35c9136a7d18fc424d714c9ec7724e60` |
| Push gate | PASS at 2026-11-28 07:24:32 +08:00; `allow=[]`, `push_rc=0`, no problems or warnings |
| Frozen CI record | `D:/MyNewProjects/_orchestra/status/qflistudio-rust.ci-watch.json` |
| Exact quality extract | `D:/MyNewProjects/_orchestra/status/qflistudio-rust.quality-8b92ddc.txt` |

The watcher observed the core and SDK identities in the quality job. Its
quality extract came from the exact-SHA public job text, 1,451 lines, without
downloading an artifact. This report preserves that observation rather than
refreshing live run state. Earlier `68723d0` and `f5ac2ee` results remain
separate evidence.

## Hosted outcomes

| Workflow or check | Run / job | Observed outcome |
| --- | --- | --- |
| Cloud checks | Run `46082334826` | PASS, all four jobs |
| Source, workflow and portability policy | Job `140783908650` | PASS |
| Ubuntu Python contracts | Job `140783908566` | PASS; 291 native-helper tests and 160 application-helper tests |
| macOS Python contracts | Job `140783908285` | PASS |
| Windows Python contracts | Job `140783908578` | PASS |
| Application quality | Run `46082334790` | FAIL |
| Independent quality helper contracts | Job `140783908387` | PASS |
| Core-bound application quality | Job `140783908798` | FAIL; report upload succeeded |
| Strict bootstrap, restore, core paths and SDK preparation | Job `140783908798` | PASS |
| `flutter analyze --no-pub` | Job `140783908798` | PASS, no issues, 18.8 seconds |
| Dart format check | Job `140783908798` | FAIL, exit 1; 46 files, one would change |
| Full root test command | Job `140783908798` | FAIL, exit 1 |
| Quality finalization | Job `140783908798` | FAIL derived from required-check failures |

Helper success does not establish application, native runtime or device
acceptance. There was no native-runtime workflow at this exact source SHA.

The exact formatting command was
`dart format --output=none --set-exit-if-changed lib test integration_test`.
Only `test/rust_code_analyzer_test.dart` was reported changed. The bounded
public preview contains three complete hunks wrapping `_DiagnosticTransport`
callbacks. The terminal and workspace previews reported no textual delta
after redaction. Another source owner is applying the analyzer-test hunks;
this report makes no claim about a later formatter result.

## Full root test evidence

The executed command was `flutter test --no-pub --machine test`. The public
derived summary reports:

| Field | Value |
| --- | --- |
| completed | 354 |
| passed | 328 |
| failed | 6 |
| skipped | 20 |
| missingSuiteFiles | `[]` |
| unfinishedTestIds | `[]` |
| protocolDone | `false` |
| success | `false` |
| rawReportPublished | `false` |

The six public summary errors are recorded below in their emitted order.
The repeated arm64 manifest error is intentional.

1. Generic startup failure: `Test failed. See exception logs above.` The test
   description is `OHOS releases its first frame after the home page is ready`.
2. Greeting mismatch: expected `['Hello, QFLIStudio+!']`, actual
   `['Hello, QFLIStudioN!']`.
3. `PathNotFoundException` opening `assets/miri/manifest.ohos-arm64.json`.
4. `PathNotFoundException` opening `assets/miri/manifest.ohos-x64.json`.
5. `PathNotFoundException` opening `assets/miri/manifest.ohos-arm64.json` again.
6. Generic desktop workspace failure: `Test failed. See exception logs above.`
   The test description is `both Rust roots retain nested expansion across
   sidebar reopen and editor reconstruction`.

The startup summary does not expose its underlying exception, file or line.
The desktop failure event is test ID 431 and has an empty `stackTrace`; the
available public text does not expose its underlying exception body. A later,
distinct event, test ID 434, identifies the mobile test at source line 196.
That location must not be assigned to the failed desktop event. Test IDs are
local to a run and must not be joined across revisions.

The earlier `68723d0` drawer counts are not evidence for this run. Absence of
earlier rustc/cargo/null errors or a mobile failure from this public summary
does not establish those individual tests' outcomes. Eight native rustc/Miri
cases were skipped because a matching native library/sysroot was unavailable;
they provide no native integration execution evidence. The summary alone does
not establish why `protocolDone` is false.

## Source follow-up and boundaries

| Follow-up | Source observation and current boundary |
| --- | --- |
| Desktop collapse/reopen fixture | Frozen source repair adds one zero-duration pump after collapse and before the existing 250 ms pump. Pinned core uses a 200 ms `AnimatedAlign` for the retained sidebar. Phase-specific assertion details were added without raising timeouts or removing assertions. UNRUN; the missing failure body prevents a proven-cause claim. |
| OHOS startup fixture | Existing pinned-core `QfliApp.formFactor` accepts `AppFormFactor.phone`. Its default resolver reads the actual host OS independently of the OHOS debug override. The authorized fixture repair preserves the real entry point, original key/stores/readiness/navigation/controller inputs, progress, timing and first-frame assertions. Source-only and UNRUN; no exact runtime-cause claim. |
| Greeting assertion | A separate source owner is aligning the assertion with the observed product greeting. No new hosted result is established by this report. |
| Missing OHOS manifests | Real asset integration is assigned separately and remains pending. The three failures involve two actual expected manifest paths. No fabricated manifest, skipped assertion or acceptance claim is authorized by this report. |
| Analyzer-test formatting | Another source owner is transcribing the exact three public formatter hunks. UNRUN at the repaired revision. |

The startup fixture contract is recorded in
`../../../spec/frontend/native-startup.md`. These changes keep the approved
core and SDK pins. Source review is not a substitute for the next exact-SHA
hosted format, analysis and full root protocol results. No equivalent
pre-migration executed proof was established, and no waiver or infrastructure
rerun is supported by these quality findings.

## Separate installer evidence

App installers run `46082334773` completed with six of seven platform jobs
successful: Android, OHOS, Windows, Linux and both macOS architectures. iOS
job `140784015241` failed. Its first concrete exception, at
`2026-11-27T23:32:47.2829660Z`, was
`AttributeError: module 'hashlib' has no attribute 'file_digest'` at
`scripts/miri_build_support.py:41`.

The generic Development Team advice is secondary and does not establish a
signing cause. iOS packaging was skipped. Its installer-named artifact holds
failure reports; it is not proof of a successful IPA, and there is no iOS
intermediate artifact. The watcher recorded metadata for 13 artifacts, seven
installer-named and six intermediate, without downloads. These outcomes do
not establish signing, device, UI, armv7 or native-hooks acceptance.

The coordinator owns publication, target parity and final acceptance. This
report does not mark the migration task complete.

## Coordinator integration after the frozen report

The four Dart repairs are now source-complete: the three exact analyzer-test
formatter hunks, the core template's `QFLIStudioN` greeting, the explicit phone
startup fixture and the desktop animation's initial pump. They preserve real
commands, assertions and existing wait budgets. Their hosted results remain
pending; the startup and desktop failure bodies remain unproven.

The quality workflow now selects both OHOS architecture archives from one
successful same-repository main producer with identical native/scripts/workflow
Git objects. It verifies both complete payloads before copying only the real
`assets/miri` bytes into the disposable checkout. It records source/run/input
and archive/manifest identities, and rechecks the exact asset inventory around
restore and checks. It neither installs native libraries nor claims native or
device execution. Missing or incompatible assets still fail preparation.

The helper also retains bounded, redacted Flutter framework exception blocks
across split print events so a generic test error can carry assertion context.
Only failed-test blocks are public. Raw machine data remains private. The
strict exit/protocol/suite/count gates are unchanged. The actual pinned Flutter
reporter's output shape still requires hosted confirmation.

Independent source review found one combined-budget defect: sanitizing one
completed block could expand its text without reserving other active blocks.
The owner fixed the budget by reserving all remaining active bytes. Independent
delta review closed the finding in source and reviewed the new interleaved
expanding-redaction regression. The 21 new helper regressions (13 asset and
eight framework-diagnostic methods) remain UNRUN. No local or new hosted check
has run. The next committed revision requires
Cloud/helper checks and real format, analysis and full root-suite evidence.
