# Native feature audit source review — 2026-10-23

Scope: `lib/rust_native_feature_audit.dart`, its focused tests and the isolated
`lib/main_catalog_audit.dart` entry. Read `check.jsonl`, its listed specs, the
PRD/design/implementation plan and the catalog/analysis/debugger contracts.
This review used source inspection and formatting only. The shared resource
lane belonged to other products; no analyzer, Flutter test, native/WSL process,
build or device command was started by this reviewer.

## Findings fixed

1. The outer error handler persisted its failure checkpoint before attempting
   cleanup. If report I/O failed repeatedly, it threw again before stopping an
   owned paused session; cleanup failures could also lose their retry owner.
   Failure checkpoints now retain their latest state and `reportWriteError`
   while actual cleanup still runs. A failed cleanup still surfaces the typed
   `RustNativeFeatureCleanupFailure` and its retained retry closure.
2. A failed timeout checkpoint bypassed the ordinary await of the timed-out
   check. Backend cancellation alone did not prove the complete check Future
   had stopped using its source. The audit now tracks that Future and awaits
   it before deleting fixtures. Failed stop still returns its error promptly
   with the session and source retained for the outer retry.
3. The fresh-launch check asserted empty stderr but did not reject
   `stderrTruncated`. It now rejects lost stderr content, including an empty
   retained buffer whose original content was lost.

Added four focused regressions for repeated report-write failure with successful
cleanup, report-write failure with retained retry ownership, failed timeout
checkpoint with an unfinished command, and lost fresh-launch stderr. There are
now 15 tests in `rust_native_feature_audit_test.dart`; none were executed here.
The timeout regression uses an explicit command gate and a completed disposal
notification, then checks that the still-pending check retains its real input.

## Other reviewed paths

- The production dependency path uses `NativeMiriAnalysisTransport` and
  `RustDebugger` with the same prepared runtime. Runtime/manifest/target identity
  is checked; injected dependencies cannot set an acceptance pass through the
  pipeline. Optional capability absence is a failure, not a skipped pass.
- Prior success is replaced synchronously before runtime preparation. The
  entry also invalidates the feature report before catalog preparation.
- Exact unsaved CRLF/non-BMP diagnostic offsets, unchanged disk bytes, actual
  paused source/scalars, live output, cancellation and a fresh launch are checked.
- The audit entry retains typed cleanup failure and offers a serialized cleanup
  retry. Successful cleanup retains interrupted/failed audit status.
- `main_catalog_audit.dart` required formatting only during this review.

## Verification and remaining work

Formatting passed using the raw SDK formatter, exit 0:

```powershell
& 'D:\ProgramFiles\flutter_ohos\bin\cache\dart-sdk\bin\dart.exe' format lib/rust_native_feature_audit.dart test/rust_native_feature_audit_test.dart lib/main_catalog_audit.dart
```

After an explicit serialized tool-lane grant, run:

```powershell
& 'D:\ProgramFiles\flutter_ohos\bin\cache\dart-sdk\bin\dart.exe' analyze lib/rust_native_feature_audit.dart lib/main_catalog_audit.dart test/rust_native_feature_audit_test.dart
& 'D:\ProgramFiles\flutter_ohos\bin\flutter.bat' test --no-pub --concurrency=1 test/rust_native_feature_audit_test.dart test/rust_native_catalog_audit_test.dart test/rust_native_catalog_test.dart
```

Lint/type checking and all 15 focused tests remain **not run**, so this review
does not claim a verified green gate. The tests intentionally exercise injected
providers and cannot establish native debugger production behavior, an actual
packaged OHOS feature pass, UI/panel acceptance or R1 catalog acceptance.

Root-owned spec follow-up: extend `backend/catalog-audit.md` to cover this
separate feature report, injected-evidence exclusion, cleanup retry ownership,
failure-checkpoint I/O and complete-check input lifetime. Native ABI execution,
matching package rebuild/hash inspection and actual OHOS execution remain
separate gates. No additional concrete source defect was identified within the
reviewed files after these local fixes.
