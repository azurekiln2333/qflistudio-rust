import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;
import 'package:qfli_rust/rust_native_catalog.dart';
import 'package:qfli_rust/rust_native_catalog_audit.dart';
import 'package:qfli_studio_core/services/studio_profile.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory temporary;

  setUp(() {
    temporary = Directory.systemTemp.createTempSync('qfli_audit_test_');
  });
  tearDown(() => temporary.deleteSync(recursive: true));

  RustNativeCatalog catalog() => RustNativeCatalog.fromJson(
    jsonDecode(File(rustNativeCatalogAsset).readAsStringSync()),
  );

  test('a new startup failure replaces an older successful report', () async {
    final file = File(p.join(temporary.path, 'report.json'));
    writeRustAuditReport(file, {
      'runId': 'old-success',
      'passed': true,
      'complete': true,
    });
    final bundle = _BrokenBundle(() {
      // Invalidation must precede even the first catalog read, not just catch.
      final current = jsonDecode(file.readAsStringSync()) as Map;
      expect(current['runId'], isNot('old-success'));
      expect(current['phase'], 'preparing');
      expect(current['passed'], isFalse);
    });
    await expectLater(
      runRustNativeCatalogAudit(reportFile: file, bundle: bundle),
      throwsStateError,
    );
    final current = jsonDecode(file.readAsStringSync()) as Map;
    expect(current['runId'], isNot('old-success'));
    expect(current, contains('auditBuildId'));
    expect(current['complete'], isFalse);
    expect(current['passed'], isFalse);
    expect(current['interrupted'], isTrue);
    expect(current['phase'], 'interrupted');
    expect(current['error'], contains('catalog unavailable'));
  });

  test('raw stdout keeps terminators, blank lines and split UTF-8', () async {
    final testCase = _unicodeCase();
    for (final output in [
      testCase.expectedStdout!,
      testCase.expectedStdout!.replaceAll('\n', '\r\n'),
      '${testCase.expectedStdout!}\n',
      testCase.expectedStdout!.substring(
        0,
        testCase.expectedStdout!.length - 1,
      ),
    ]) {
      String? scratch;
      final result = await runRustNativeCatalogCase(
        testCase: testCase,
        timeout: const Duration(seconds: 5),
        onTimeout: (_) => fail('immediate fake output must not time out'),
        runnerFactory: (capture) => _Runner((projectPath, entryFile) async {
          scratch = projectPath;
          expect(
            File(entryFile).readAsBytesSync(),
            utf8.encode(testCase.source),
          );
          // Byte-sized chunks split every CJK character and emoji. The raw
          // callback, unlike terminal lines, preserves exact output boundaries.
          for (final byte in utf8.encode(output)) {
            capture([byte]);
          }
          return ProgramRunResult(
            title: 'fake native byte stream',
            stdout: Stream.fromIterable(const LineSplitter().convert(output)),
            stderr: const Stream.empty(),
            exitCode: Future.value(0),
          );
        }),
      );
      expect(result.stdout, output);
      expect(
        result.status,
        output.replaceAll('\r\n', '\n') == testCase.expectedStdout
            ? RustNativeCaseStatus.passed
            : RustNativeCaseStatus.failed,
      );
      expect(Directory(scratch!).existsSync(), isFalse);
    }
  });

  test('the exact complete Cargo overlay reaches the runner', () async {
    final testCase = catalog().byId('rust-catalog-007-example')!;
    String? scratch;
    final result = await runRustNativeCatalogCase(
      testCase: testCase,
      timeout: const Duration(seconds: 5),
      onTimeout: (_) => fail('fake bundle runner must not time out'),
      runnerFactory: (capture) => _Runner((projectPath, entryFile) async {
        scratch = projectPath;
        expect(entryFile, p.join(projectPath, 'src', 'main.rs'));
        for (final entry in testCase.files!.entries) {
          final file = File(p.joinAll([projectPath, ...entry.key.split('/')]));
          expect(file.readAsBytesSync(), utf8.encode(entry.value));
        }
        capture(utf8.encode(testCase.expectedStdout!));
        return ProgramRunResult(
          title: 'fake bundle runner',
          stdout: const Stream.empty(),
          stderr: const Stream.empty(),
          exitCode: Future.value(0),
        );
      }),
    );
    expect(result.status, RustNativeCaseStatus.passed);
    expect(Directory(scratch!).existsSync(), isFalse);
  });

  test(
    'malformed native UTF-8 cannot become accepted replacement text',
    () async {
      final result = await runRustNativeCatalogCase(
        testCase: _unicodeCase(),
        timeout: const Duration(seconds: 5),
        onTimeout: (_) => fail('invalid bytes do not require a timeout'),
        runnerFactory: (capture) => _Runner((projectPath, entryFile) async {
          capture([0xff]);
          return ProgramRunResult(
            title: 'invalid native bytes',
            stdout: const Stream.empty(),
            stderr: const Stream.empty(),
            exitCode: Future.value(0),
          );
        }),
      );
      expect(result.status, RustNativeCaseStatus.error);
      expect(result.detail, contains('FormatException'));
    },
  );

  test('timeout is durable while cancellation retains live sources', () async {
    final checkpointFile = File(p.join(temporary.path, 'timeout.json'));
    final exit = Completer<int>();
    final checkpoint = Completer<void>();
    final cancelled = Completer<void>();
    String? scratch;
    var finished = false;
    final pending = runRustNativeCatalogCase(
      testCase: _unicodeCase(),
      timeout: const Duration(milliseconds: 20),
      onTimeout: (result) {
        writeRustAuditReport(checkpointFile, {
          'interrupted': true,
          'passed': false,
          'cases': [result.toJson()],
        });
        checkpoint.complete();
      },
      runnerFactory: (_) => _Runner((projectPath, entryFile) async {
        scratch = projectPath;
        return ProgramRunResult(
          title: 'blocked compiler',
          stdout: const Stream.empty(),
          stderr: const Stream.empty(),
          exitCode: exit.future,
          cancel: () async {
            cancelled.complete();
            await exit.future;
          },
        );
      }),
    ).whenComplete(() => finished = true);

    await checkpoint.future.timeout(const Duration(seconds: 5));
    await cancelled.future.timeout(const Duration(seconds: 5));
    final saved = jsonDecode(checkpointFile.readAsStringSync()) as Map;
    expect(saved['passed'], isFalse);
    final result = (saved['cases'] as List).single as Map;
    expect(result['status'], 'error');
    expect(result['detail'], contains('waiting for native cancellation'));
    expect(finished, isFalse);
    expect(Directory(scratch!).existsSync(), isTrue);

    exit.complete(130);
    final stopped = await pending;
    expect(stopped.status, RustNativeCaseStatus.error);
    expect(stopped.exitCode, 130);
    expect(Directory(scratch!).existsSync(), isFalse);
  });

  test(
    'timeout before runner preparation still cancels the late session',
    () async {
      final prepared = Completer<ProgramRunResult>();
      final checkpoint = Completer<void>();
      final exit = Completer<int>();
      final cancelled = Completer<void>();
      String? scratch;
      var finished = false;
      final pending = runRustNativeCatalogCase(
        testCase: _unicodeCase(),
        timeout: const Duration(milliseconds: 20),
        onTimeout: (_) => checkpoint.complete(),
        runnerFactory: (_) => _Runner((projectPath, entryFile) {
          scratch = projectPath;
          return prepared.future;
        }),
      ).whenComplete(() => finished = true);

      await checkpoint.future.timeout(const Duration(seconds: 5));
      expect(finished, isFalse);
      expect(cancelled.isCompleted, isFalse);
      expect(Directory(scratch!).existsSync(), isTrue);
      prepared.complete(
        ProgramRunResult(
          title: 'late native session',
          stdout: const Stream.empty(),
          stderr: const Stream.empty(),
          exitCode: exit.future,
          cancel: () async {
            cancelled.complete();
            await exit.future;
          },
        ),
      );
      await cancelled.future.timeout(const Duration(seconds: 5));
      expect(finished, isFalse);
      exit.complete(130);
      expect((await pending).status, RustNativeCaseStatus.error);
      expect(Directory(scratch!).existsSync(), isFalse);
    },
  );
}

RustNativeCatalogCase _unicodeCase() {
  const source = '\uFEFF// 中文 😀\r\nfn main() { println!("中文 😀"); }\r\n';
  return RustNativeCatalogCase(
    id: 'test-unicode-example',
    topicId: 1,
    kind: RustNativeCaseKind.example,
    runtime: 'miri-candidate',
    level: 'beginner',
    entryFile: 'main.rs',
    source: source,
    sourceSha256: sha256Hex(source),
    expectedExitCode: 0,
    expectedStdout: '中文 😀\n',
    stdoutAsserted: true,
    files: null,
    filesSha256: null,
    bundleVerify: null,
  );
}

class _BrokenBundle extends AssetBundle {
  _BrokenBundle(this.onRead);
  final void Function() onRead;

  @override
  Future<ByteData> load(String key) async =>
      throw StateError('unused byte read');

  @override
  Future<String> loadString(String key, {bool cache = true}) async {
    onRead();
    throw StateError('catalog unavailable');
  }
}

class _Runner implements ProgramRunner {
  _Runner(this.onRun);
  final Future<ProgramRunResult?> Function(String projectPath, String entryFile)
  onRun;

  @override
  Future<ProgramRunResult?> run({
    required String projectPath,
    required String entryFile,
  }) => onRun(projectPath, entryFile);
}
