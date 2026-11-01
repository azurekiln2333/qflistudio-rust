import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:path/path.dart' as p;
import 'package:qfli_rust/rust_native_catalog_audit.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  testWidgets(
    'packaged engine executes the complete authored catalog',
    (_) async {
      const reportOverride = String.fromEnvironment('QFLI_RUST_CATALOG_REPORT');
      final report = await runRustNativeCatalogAudit(
        reportFile: File(
          reportOverride.isEmpty
              ? p.join(Directory.systemTemp.path, 'rust_catalog_audit.json')
              : reportOverride,
        ),
        requiredPlatform: const String.fromEnvironment(
          'QFLI_RUST_CATALOG_PLATFORM',
          defaultValue: 'ohos',
        ),
        caseTimeout: const Duration(
          seconds: int.fromEnvironment(
            'QFLI_RUST_CATALOG_CASE_TIMEOUT',
            defaultValue: 120,
          ),
        ),
      );
      expect(report.complete, isTrue);
      expect(report.results, hasLength(report.catalog.runCount));
      expect(report.failedIds, isEmpty);
      expect(report.passed, isTrue);
    },
    timeout: const Timeout(Duration(minutes: 120)),
  );
}
