import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;
import 'package:qfli_rust/native_miri_assets.dart';
import 'package:qfli_rust/rust_code_analyzer.dart';
import 'package:qfli_rust/rust_native_catalog.dart';
import 'package:qfli_rust/rust_native_catalog_audit.dart';
import 'package:qfli_rust/rust_native_feature_audit.dart';
import 'package:qfli_studio_core/services/debug_session.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory temporary;
  late File reportFile;

  setUp(() {
    temporary = Directory.systemTemp.createTempSync('qfli_feature_test_');
    reportFile = File(p.join(temporary.path, 'features.json'));
  });
  tearDown(() => temporary.deleteSync(recursive: true));

  test(
    'preparation sees new incomplete evidence before its first await',
    () async {
      writeRustAuditReport(reportFile, {
        'runId': 'old-success',
        'complete': true,
        'passed': true,
      });
      final fixture = _Dependencies(temporary);
      final dependencies = fixture.dependencies(
        prepare: () async {
          final report = _read(reportFile);
          expect(report['runId'], isNot('old-success'));
          expect(report['phase'], 'preparing');
          expect(report['passed'], isFalse);
          throw StateError('runtime preparation failed');
        },
      );
      await expectLater(
        runRustNativeFeatureAudit(
          reportFile: reportFile,
          dependencies: dependencies,
        ),
        throwsStateError,
      );
      final report = _read(reportFile);
      expect(report['phase'], 'interrupted');
      expect(report['passed'], isFalse);
      expect(report['complete'], isFalse);
      expect(report['error'], contains('runtime preparation failed'));
      expect(report, contains('auditBuildId'));
    },
  );

  test('runtime target mismatch fails before any provider call', () async {
    final fixture = _Dependencies(temporary);
    final context = fixture.context;
    final changed = RustNativeFeatureRuntime(
      runtime: NativeMiriRuntime(
        target: const NativeMiriTarget(platform: 'ohos', architecture: 'arm64'),
        nativeHost: context.runtime.nativeHost,
        sysrootPath: context.runtime.sysrootPath,
        libraryPath: context.runtime.libraryPath,
      ),
      identity: context.identity,
      manifestSha256: context.manifestSha256,
    );
    await expectLater(
      runRustNativeFeatureAudit(
        reportFile: reportFile,
        dependencies: fixture.dependencies(prepare: () async => changed),
      ),
      throwsStateError,
    );
    expect(fixture.analysis.jobs, isEmpty);
    expect(fixture.debugger.launches, isEmpty);
    expect(_read(reportFile)['passed'], isFalse);
  });

  test('all six real-shaped workflows bind hashes and clean up', () async {
    final fixture = _Dependencies(temporary);
    final report = await runRustNativeFeatureAudit(
      reportFile: reportFile,
      auditBuildId: 'test-build',
      dependencies: fixture.dependencies(),
    );
    expect(report.complete, isTrue);
    expect(report.checksPassed, isTrue);
    // Test seams must never manufacture packaged-device acceptance evidence.
    expect(report.passed, isFalse);
    expect(report.results, hasLength(6));
    expect(report.missingIds, isEmpty);
    expect(report.fixtureSha256, hasLength(8));
    expect(fixture.analysis.jobs, hasLength(2));
    expect(fixture.analysis.moduleTexts[0], contains('42'));
    expect(fixture.analysis.moduleTexts[1], contains('中🙂'));
    expect(fixture.analysis.moduleTexts[1], contains('\r\n'));
    expect(fixture.debugger.launches, hasLength(2));
    expect(fixture.debugger.events, [
      'cancelled',
      'disposed',
      'fresh',
      'disposed',
    ]);
    expect(fixture.methods, ['openUrl', 'openAgreement']);
    for (final entry in fixture.debugger.launches) {
      expect(File(entry).existsSync(), isFalse);
    }
    for (final job in fixture.analysis.jobs) {
      expect(Directory(job.mirrorRoot).existsSync(), isFalse);
    }
    final json = _read(reportFile);
    expect(json['phase'], 'finished');
    expect(json['cleanupComplete'], isTrue);
    expect(json['auditBuildId'], 'test-build');
    expect(json['manifestSha256'], fixture.context.manifestSha256);
    expect(json['evidenceKind'], 'injected_dependencies_not_acceptance');
    expect(
      (json['acceptance'] as Map)['sharedEditorSquigglesAndProblemsNavigation'],
      'not_tested',
    );
  });

  test(
    'missing and duplicate check results cannot establish completeness',
    () async {
      final fixture = _Dependencies(temporary);
      final report = await runRustNativeFeatureAudit(
        reportFile: reportFile,
        dependencies: fixture.dependencies(),
      );
      RustNativeFeatureReport withResults(
        List<RustNativeFeatureResult> results,
      ) => RustNativeFeatureReport(
        runId: report.runId,
        auditBuildId: report.auditBuildId,
        identity: report.identity,
        manifestSha256: report.manifestSha256,
        startedAt: report.startedAt,
        finishedAt: report.finishedAt,
        interrupted: false,
        cleanupComplete: true,
        actualProviders: false,
        fixtureSha256: report.fixtureSha256,
        results: results,
      );
      final missing = withResults(report.results.sublist(1));
      expect(missing.complete, isFalse);
      expect(missing.checksPassed, isFalse);
      expect(missing.missingIds, ['analysisValid']);
      final duplicate = withResults([...report.results, report.results.first]);
      expect(duplicate.missingIds, isEmpty);
      expect(duplicate.complete, isFalse);
      expect(duplicate.passed, isFalse);
      expect(withResults([]).missingIds, hasLength(6));
    },
  );

  test(
    'absent capabilities and absent native handlers fail instead of skipping',
    () async {
      final fixture = _Dependencies(temporary);
      fixture.debugger.available = false;
      final report = await runRustNativeFeatureAudit(
        reportFile: reportFile,
        dependencies: fixture.dependencies(
          invoke: (_) async =>
              throw MissingPluginException('missing native guard'),
        ),
      );
      expect(report.complete, isTrue);
      expect(report.checksPassed, isFalse);
      expect(
        report.results.where(
          (result) => result.status == RustNativeCaseStatus.failed,
        ),
        hasLength(4),
      );
      expect(report.results.last.detail, contains('MissingPluginException'));
      expect(fixture.debugger.launches, isEmpty);
    },
  );

  test(
    'clean or shifted diagnostics cannot pass the exact unsaved range check',
    () async {
      for (final offset in [-1, 1]) {
        final fixture = _Dependencies(temporary);
        fixture.analysis.offset = offset;
        final report = await runRustNativeFeatureAudit(
          reportFile: reportFile,
          dependencies: fixture.dependencies(),
        );
        final result = report.results.singleWhere(
          (result) =>
              result.check == RustNativeFeatureCheck.analysisUnsavedModule,
        );
        expect(result.status, RustNativeCaseStatus.failed);
        expect(result.detail, contains('incorrect UTF-16 offsets'));
        expect(report.checksPassed, isFalse);
      }
    },
  );

  test(
    'timeout checkpoints before waiting and retains live compiler inputs',
    () async {
      final fixture = _Dependencies(temporary);
      final release = Completer<void>();
      final cancelled = Completer<void>();
      fixture.analysis.firstCall = release.future;
      fixture.analysis.onCancel = () {
        if (!cancelled.isCompleted) cancelled.complete();
      };
      var finished = false;
      final pending =
          runRustNativeFeatureAudit(
            reportFile: reportFile,
            checkTimeout: const Duration(milliseconds: 500),
            dependencies: fixture.dependencies(),
          ).then((result) {
            finished = true;
            return result;
          });
      await cancelled.future;
      final checkpoint = _read(reportFile);
      expect(checkpoint['phase'], 'cancelling');
      expect(checkpoint['pendingCancellationId'], 'analysisValid');
      expect(checkpoint['complete'], isFalse);
      expect(checkpoint['passed'], isFalse);
      expect(finished, isFalse);
      final job = fixture.analysis.jobs.single;
      expect(File(job.entryPath).existsSync(), isTrue);
      expect(Directory(job.projectPath).existsSync(), isTrue);
      release.complete();
      final report = await pending;
      expect(report.results.first.status, RustNativeCaseStatus.error);
      expect(report.checksPassed, isFalse);
      expect(report.cleanupComplete, isTrue);
      expect(Directory(job.mirrorRoot).existsSync(), isFalse);
      expect(Directory(job.projectPath).existsSync(), isFalse);
    },
  );

  test(
    'late debug launch is cancelled and joined before sources disappear',
    () async {
      final fixture = _Dependencies(temporary);
      final release = Completer<void>();
      final entered = Completer<void>();
      fixture.debugger.launchGate = release.future;
      fixture.debugger.onLaunch = () => entered.complete();
      final pending = runRustNativeFeatureAudit(
        reportFile: reportFile,
        checkTimeout: const Duration(milliseconds: 500),
        dependencies: fixture.dependencies(),
      );
      await entered.future;
      // Poll the durable report, not a presumed worker exit after a sleep.
      while (_read(reportFile)['phase'] != 'cancelling') {
        await Future<void>.delayed(const Duration(milliseconds: 2));
      }
      final checkpoint = _read(reportFile);
      expect(
        checkpoint['pendingCancellationId'],
        'debuggerEntryBreakpointStep',
      );
      final entry = fixture.debugger.launches.single;
      expect(File(entry).existsSync(), isTrue);
      release.complete();
      final report = await pending;
      expect(report.checksPassed, isFalse);
      expect(report.results[2].status, RustNativeCaseStatus.error);
      expect(fixture.debugger.events.first, 'cancelled');
      expect(File(entry).existsSync(), isFalse);
    },
  );

  test('outer dispose retries a failed stop while done is pending', () async {
    final fixture = _Dependencies(temporary);
    fixture.debugger.badScalar = true;
    fixture.debugger.stopFailures = 1;
    fixture.debugger.onFailedStop = (session) {
      final checkpoint = _read(reportFile);
      expect(checkpoint['phase'], 'cancelling');
      expect(checkpoint['cleanupComplete'], isFalse);
      expect(File(session.request.entryFilePath).existsSync(), isTrue);
      expect(session.snapshot.phase, DebugPhase.stopping);
    };
    await expectLater(
      runRustNativeFeatureAudit(
        reportFile: reportFile,
        dependencies: fixture.dependencies(),
      ),
      throwsStateError,
    );
    expect(fixture.debugger.events, ['stop-failed', 'cancelled', 'disposed']);
    expect(File(fixture.debugger.launches.single).existsSync(), isFalse);
    final checkpoint = _read(reportFile);
    expect(checkpoint['phase'], 'interrupted');
    expect(checkpoint['cleanupComplete'], isTrue);
    expect(checkpoint['passed'], isFalse);
    expect(checkpoint['complete'], isFalse);
  });

  test(
    'repeated stop failure retains owner and sources for explicit retry',
    () async {
      final fixture = _Dependencies(temporary);
      fixture.debugger.badScalar = true;
      fixture.debugger.alwaysFailStop = true;
      RustNativeFeatureCleanupFailure? failure;
      try {
        await runRustNativeFeatureAudit(
          reportFile: reportFile,
          dependencies: fixture.dependencies(),
        );
        fail('persistent cleanup failure must surface a retry handle');
      } on RustNativeFeatureCleanupFailure catch (error) {
        failure = error;
      }
      final retained = failure;
      final entry = fixture.debugger.launches.single;
      try {
        expect(fixture.debugger.events, ['stop-failed', 'stop-failed']);
        expect(File(entry).existsSync(), isTrue);
        expect(_read(reportFile)['phase'], 'cancelling');
        expect(_read(reportFile)['cleanupComplete'], isFalse);
        await expectLater(retained.retryCleanup(), throwsStateError);
        expect(File(entry).existsSync(), isTrue);
        final checkpoint = _read(reportFile);
        expect(checkpoint['phase'], 'cancelling');
        expect(checkpoint['cleanupComplete'], isFalse);
        expect(checkpoint['passed'], isFalse);
        expect(
          checkpoint['cleanupError'],
          contains('injected stop cleanup failure'),
        );
      } finally {
        fixture.debugger.alwaysFailStop = false;
        await retained.retryCleanup();
      }
      expect(File(entry).existsSync(), isFalse);
      final checkpoint = _read(reportFile);
      expect(checkpoint['phase'], 'interrupted');
      expect(checkpoint['cleanupComplete'], isTrue);
      expect(checkpoint['passed'], isFalse);
      expect(checkpoint['complete'], isFalse);
      expect(
        fixture.debugger.events.sublist(fixture.debugger.events.length - 2),
        ['cancelled', 'disposed'],
      );
    },
  );

  test(
    'throwing analysis still observes sentinel and cannot claim clean',
    () async {
      final fixture = _Dependencies(temporary);
      fixture.analysis.failWithSentinel = true;
      final report = await runRustNativeFeatureAudit(
        reportFile: reportFile,
        dependencies: fixture.dependencies(),
      );
      expect(report.checksPassed, isFalse);
      expect(report.passed, isFalse);
      final failed = report.results.first;
      expect(failed.status, RustNativeCaseStatus.failed);
      expect(failed.evidence['completedCompilerCalls'], 0);
      expect(failed.evidence['mirrorSentinelChecks'], 1);
      expect(failed.evidence['executionSentinelPresent'], isTrue);
      expect(failed.detail, contains('injected analysis failure'));
    },
  );

  test('report write failure still cleans a paused debug session', () async {
    final fixture = _Dependencies(temporary);
    await expectLater(
      runRustNativeFeatureAudit(
        reportFile: reportFile,
        dependencies: fixture.dependencies(),
        onProgress: (result) {
          if (result.check !=
              RustNativeFeatureCheck.debuggerEntryBreakpointStep) {
            return;
          }
          reportFile.deleteSync();
          Directory(reportFile.path).createSync();
          throw StateError('injected progress failure');
        },
      ),
      throwsA(
        isA<StateError>().having(
          (error) => error.message,
          'message',
          'injected progress failure',
        ),
      ),
    );
    expect(fixture.debugger.events, ['cancelled', 'disposed']);
    expect(File(fixture.debugger.launches.single).existsSync(), isFalse);
  });

  test('unwritable report cannot discard a failed cleanup owner', () async {
    final fixture = _Dependencies(temporary);
    fixture.debugger.alwaysFailStop = true;
    RustNativeFeatureCleanupFailure? failure;
    try {
      await runRustNativeFeatureAudit(
        reportFile: reportFile,
        dependencies: fixture.dependencies(),
        onProgress: (result) {
          if (result.check !=
              RustNativeFeatureCheck.debuggerEntryBreakpointStep) {
            return;
          }
          reportFile.deleteSync();
          Directory(reportFile.path).createSync();
          throw StateError('injected progress failure');
        },
      );
      fail('persistent cleanup must retain its retry handle');
    } on RustNativeFeatureCleanupFailure catch (error) {
      failure = error;
    }
    final retained = failure;
    final entry = fixture.debugger.launches.single;
    try {
      expect(fixture.debugger.events, ['stop-failed']);
      expect(File(entry).existsSync(), isTrue);
      await expectLater(retained.retryCleanup(), throwsStateError);
      expect(File(entry).existsSync(), isTrue);
    } finally {
      Directory(reportFile.path).deleteSync();
      fixture.debugger.alwaysFailStop = false;
      await retained.retryCleanup();
    }
    expect(File(entry).existsSync(), isFalse);
    final checkpoint = _read(reportFile);
    expect(checkpoint['cleanupComplete'], isTrue);
    expect(checkpoint['passed'], isFalse);
    expect(checkpoint['complete'], isFalse);
    expect(checkpoint['reportWriteError'], isNotEmpty);
  });

  test('failed timeout checkpoint retains an unfinished check input', () async {
    final fixture = _Dependencies(temporary);
    final release = Completer<void>();
    final disposed = Completer<void>();
    fixture.debugger.stepGate = release.future;
    fixture.debugger.onStep = () {
      reportFile.deleteSync();
      Directory(reportFile.path).createSync();
    };
    fixture.debugger.onDisposed = () => disposed.complete();
    var settled = false;
    final expectation = expectLater(
      runRustNativeFeatureAudit(
        reportFile: reportFile,
        checkTimeout: const Duration(milliseconds: 500),
        dependencies: fixture.dependencies(),
      ).whenComplete(() => settled = true),
      throwsA(isA<FileSystemException>()),
    );
    await disposed.future;
    final entry = fixture.debugger.launches.single;
    try {
      expect(settled, isFalse);
      expect(File(entry).existsSync(), isTrue);
    } finally {
      release.complete();
      await expectation;
    }
    expect(File(entry).existsSync(), isFalse);
  });

  test('fresh launch rejects empty stderr with lost content', () async {
    final fixture = _Dependencies(temporary);
    fixture.debugger.truncatedFreshStderr = true;
    final report = await runRustNativeFeatureAudit(
      reportFile: reportFile,
      dependencies: fixture.dependencies(),
    );
    final result = report.results.singleWhere(
      (result) => result.check == RustNativeFeatureCheck.debuggerFreshLaunch,
    );
    expect(result.status, RustNativeCaseStatus.failed);
    expect(report.checksPassed, isFalse);
  });
}

Map<String, dynamic> _read(File file) =>
    jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;

class _Dependencies {
  _Dependencies(this.directory);
  final Directory directory;
  final analysis = _Analysis();
  final debugger = _Debugger();
  final methods = <String>[];

  RustNativeFeatureRuntime get context {
    const target = NativeMiriTarget(platform: 'ohos', architecture: 'x64');
    const host = 'x86_64-unknown-linux-ohos';
    final runtime = NativeMiriRuntime(
      target: target,
      nativeHost: host,
      sysrootPath: p.join(directory.path, 'sysroot'),
      libraryPath: p.join(directory.path, 'libqfli_test.so'),
    );
    return RustNativeFeatureRuntime(
      runtime: runtime,
      manifestSha256: sha256Hex('test manifest bytes'),
      identity: RustNativeRuntimeIdentity(
        platform: 'ohos',
        architecture: 'x64',
        targetKey: target.key,
        nativeHost: host,
        targetNativeHosts: target.nativeHosts,
        guestTarget: 'x86_64-unknown-linux-gnu',
        libraryPath: runtime.libraryPath,
        sysrootPath: runtime.sysrootPath,
        backendPath: null,
        manifestAsset: target.manifestAsset,
        manifestId: sha256Hex('test content'),
        manifestNativeHost: host,
        rustVersion: '1.98.1',
        rustCommit: '48a229ceaefd4985c50990b14116b6d856af0985',
        manifestGuestTarget: 'x86_64-unknown-linux-gnu',
      ),
    );
  }

  RustNativeFeatureAuditDependencies dependencies({
    Future<RustNativeFeatureRuntime> Function()? prepare,
    Future<void> Function(String)? invoke,
  }) => RustNativeFeatureAuditDependencies(
    prepareRuntime: prepare ?? () async => context,
    analysisTransport: (_) => analysis,
    debugger: (_) => debugger,
    invokePlatformMethod:
        invoke ??
        (method) async {
          methods.add(method);
          throw PlatformException(code: 'OFFLINE_ONLY');
        },
  );
}

class _Analysis implements RustAnalysisTransport, RustAnalysisCancellation {
  final jobs = <RustAnalysisJob>[];
  final moduleTexts = <String>[];
  Future<void>? firstCall;
  void Function()? onCancel;
  Future<RustAnalysisOutput>? _active;
  int offset = 0;
  bool failWithSentinel = false;

  @override
  Future<RustAnalysisOutput> analyze(RustAnalysisJob job) {
    final work = _analyze(job);
    _active = work;
    return work;
  }

  Future<RustAnalysisOutput> _analyze(RustAnalysisJob job) async {
    jobs.add(job);
    final file = File(p.join(p.dirname(job.entryPath), 'helper.rs'));
    final source = file.readAsStringSync();
    moduleTexts.add(source);
    if (jobs.length == 1 && firstCall != null) await firstCall;
    if (jobs.length == 1 && failWithSentinel) {
      File(
        p.join(job.mirrorRoot, 'qfli-analysis-executed'),
      ).writeAsStringSync('executed');
      throw StateError('injected analysis failure');
    }
    const literal = '"坏🙂"';
    final index = source.indexOf(literal);
    if (index < 0 || offset == -1) {
      return const RustAnalysisOutput(exitCode: 0, diagnosticsJsonl: '');
    }
    final start = utf8.encode(source.substring(0, index)).length;
    return RustAnalysisOutput(
      exitCode: 0,
      diagnosticsJsonl: jsonEncode({
        r'$message_type': 'diagnostic',
        'message': 'mismatched types',
        'level': 'error',
        'code': {'code': 'E0308'},
        'spans': [
          {
            'file_name': file.path,
            'byte_start': start + offset,
            'byte_end': start + utf8.encode(literal).length + offset,
            'is_primary': true,
          },
        ],
      }),
    );
  }

  @override
  Future<void> cancel() async {
    onCancel?.call();
    await _active?.then<void>((_) {}, onError: (Object _, StackTrace _) {});
  }
}

class _Debugger implements StudioDebugger {
  bool available = true;
  bool badScalar = false;
  bool truncatedFreshStderr = false;
  int stopFailures = 0;
  bool alwaysFailStop = false;
  void Function(_Session)? onFailedStop;
  Future<void>? launchGate;
  Future<void>? stepGate;
  void Function()? onLaunch;
  void Function()? onStep;
  void Function()? onDisposed;
  final launches = <String>[];
  final events = <String>[];

  @override
  String get displayName => 'test debugger';
  @override
  bool supportsLanguage(String language) => language == 'rust';
  @override
  DebugCapabilities get capabilities => DebugCapabilities(
    breakpointUpdate: DebugBreakpointUpdate.launchOnly,
    outputDelivery: available
        ? DebugOutputDelivery.live
        : DebugOutputDelivery.exitOnly,
    supportsStopOnEntry: available,
    supportsStepOver: available,
    supportsStackFrames: available,
    supportsVariables: available,
  );

  @override
  Future<DebugSession> launch(DebugLaunchRequest request) async {
    launches.add(request.entryFilePath);
    if (request.stopOnEntry && launchGate != null) {
      onLaunch?.call();
      onLaunch = null;
      await launchGate;
      launchGate = null;
    }
    expect(File(request.entryFilePath).existsSync(), isTrue);
    expect(request.documents, isEmpty);
    final session = _Session(request, this);
    if (!request.stopOnEntry) events.add('fresh');
    return session;
  }
}

class _Session implements DebugSession {
  _Session(this.request, this.owner) {
    if (request.stopOnEntry) {
      _pause(1, 2);
    } else {
      snapshot = DebugSnapshot(
        sessionId: id,
        revision: 1,
        phase: DebugPhase.terminated,
        stdout: 'audit-fresh:42\n',
        stderrTruncated: owner.truncatedFreshStderr,
        exitCode: 0,
      );
      _done.complete();
    }
  }

  final DebugLaunchRequest request;
  final _Debugger owner;
  List<String> get events => owner.events;
  final _updates = StreamController<DebugSnapshot>.broadcast(sync: true);
  final _done = Completer<void>();
  bool _disposed = false;
  @override
  String get id => request.stopOnEntry ? 'controlled-test' : 'fresh-test';
  @override
  late DebugSnapshot snapshot;
  @override
  Stream<DebugSnapshot> get updates => _updates.stream;
  @override
  Future<void> get done => _done.future;

  void _publish(DebugSnapshot value) {
    snapshot = value;
    _updates.add(value);
  }

  void _pause(int generation, int line) => _publish(
    DebugSnapshot(
      sessionId: id,
      revision: generation,
      phase: DebugPhase.paused,
      pauseToken: DebugPauseToken(sessionId: id, generation: generation),
      frames: [
        DebugFrame(
          id: 'main',
          threadId: 'active',
          name: 'qfli_feature_audit::main',
          location: DebugSourceLocation(
            filePath: request.entryFilePath,
            line: line,
            column: 5,
          ),
          locals: [
            if (line == 4) ...[
              DebugVariable(name: 'seed', type: 'i32', value: '41'),
              DebugVariable(
                name: 'answer',
                type: 'i32',
                value: owner.badScalar ? '43' : '42',
              ),
            ],
          ],
        ),
      ],
      breakpoints: [
        for (final point in request.breakpoints)
          DebugBreakpointResult(
            requested: point,
            status: line == 4
                ? DebugBreakpointStatus.verified
                : DebugBreakpointStatus.pending,
            actualLocation: line == 4
                ? DebugSourceLocation(filePath: request.entryFilePath, line: 4)
                : null,
          ),
      ],
    ),
  );

  @override
  Future<void> command(
    DebugCommand command, {
    DebugPauseToken? pauseToken,
    String? threadId,
  }) async {
    expect(pauseToken, snapshot.pauseToken);
    if (command == DebugCommand.stepOver) {
      owner.onStep?.call();
      await owner.stepGate;
      if (_done.isCompleted) return;
      _pause(2, 3);
    } else if (snapshot.pauseToken?.generation == 2) {
      _pause(3, 4);
    } else {
      _publish(
        DebugSnapshot(
          sessionId: id,
          revision: 4,
          phase: DebugPhase.running,
          stdout: 'audit-out:42\n',
          stderr: 'audit-err:42\n',
        ),
      );
    }
  }

  @override
  Future<List<DebugBreakpointResult>> setBreakpoints(
    List<DebugBreakpoint> breakpoints,
  ) => throw UnsupportedError('launch only');

  @override
  Future<void> stop() async {
    if (_done.isCompleted) return;
    if (owner.stopFailures > 0 || owner.alwaysFailStop) {
      if (owner.stopFailures > 0) owner.stopFailures--;
      events.add('stop-failed');
      _publish(
        DebugSnapshot(
          sessionId: id,
          revision: snapshot.revision + 1,
          phase: DebugPhase.stopping,
          stdout: snapshot.stdout,
          stderr: snapshot.stderr,
        ),
      );
      owner.onFailedStop?.call(this);
      throw StateError('injected stop cleanup failure');
    }
    events.add('cancelled');
    _publish(
      DebugSnapshot(
        sessionId: id,
        revision: snapshot.revision + 1,
        phase: DebugPhase.terminated,
        exitCode: 130,
        stdout: snapshot.stdout,
        stderr: snapshot.stderr,
      ),
    );
    _done.complete();
  }

  @override
  Future<void> dispose() async {
    if (_disposed) return;
    await stop();
    await done;
    _disposed = true;
    events.add('disposed');
    await _updates.close();
    owner.onDisposed?.call();
  }
}
