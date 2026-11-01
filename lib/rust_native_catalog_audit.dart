import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/services.dart';
import 'package:path/path.dart' as p;
import 'package:qfli_studio_core/services/studio_profile.dart';

import 'native_miri_assets.dart';
import 'native_miri_runner.dart';
import 'rust_native_catalog.dart';

/// Shared execution path for the standalone OHOS audit and integration suite.
/// A host run cannot establish packaged OHOS compatibility.
Future<RustNativeCatalogReport> runRustNativeCatalogAudit({
  required File reportFile,
  String requiredPlatform = 'ohos',
  Duration caseTimeout = const Duration(seconds: 120),
  AssetBundle? bundle,
  void Function(RustNativeCaseResult result, int completed, int total)?
  onProgress,
}) async {
  final startedAt = DateTime.now().toUtc();
  final runIdentity = <String, Object?>{
    'runId': '${startedAt.microsecondsSinceEpoch}-$pid',
    'auditBuildId': const String.fromEnvironment('QFLI_RUST_AUDIT_BUILD_ID'),
    'startedAt': startedAt.toIso8601String(),
  };
  var latest = <String, Object?>{
    'schemaVersion': RustNativeCatalogReport.schemaVersion,
    'complete': false,
    'passed': false,
    'interrupted': true,
    'phase': 'preparing',
    'executed': 0,
    'cases': <Object?>[],
  };
  void persist(Map<String, Object?> data) {
    latest = {...data, ...runIdentity};
    writeRustAuditReport(reportFile, latest);
  }

  // Invalidate any prior success before the first await or fallible preparation.
  persist(latest);
  try {
    if (caseTimeout.inMicroseconds <= 0) {
      throw ArgumentError.value(caseTimeout, 'caseTimeout', 'must be positive');
    }
    final assetBundle = bundle ?? rootBundle;
    final catalog = await RustNativeCatalog.load(bundle: assetBundle);
    final target = NativeMiriTarget.current();
    if (target.platform != requiredPlatform || target.nativeHosts.isEmpty) {
      throw StateError(
        'Expected packaged $requiredPlatform runtime, got ${target.key}',
      );
    }
    final manifestSource = await target.loadManifest(assetBundle);
    final manifest = jsonDecode(manifestSource) as Map<String, dynamic>;
    if (!target.nativeHosts.contains(manifest['nativeHost']) ||
        manifest['guestTarget'] != catalog.guestTarget) {
      throw StateError(
        'Packaged runtime manifest does not match ${target.key}',
      );
    }
    final assets = await AssetManifest.loadFromAssetBundle(assetBundle);
    final manifestAsset = assets.listAssets().contains(target.manifestAsset)
        ? target.manifestAsset
        : rustNativeLegacyManifestAsset;
    final runtime = await prepareNativeMiriAssets(target: target);
    final identity = RustNativeRuntimeIdentity(
      platform: target.platform,
      architecture: target.architecture,
      targetKey: target.key,
      nativeHost: runtime.nativeHost,
      targetNativeHosts: target.nativeHosts,
      guestTarget: manifest['guestTarget'] as String,
      libraryPath: runtime.libraryPath,
      sysrootPath: runtime.sysrootPath,
      backendPath: runtime.backendPath,
      manifestAsset: manifestAsset,
      manifestId: manifest['id'] as String,
      manifestNativeHost: manifest['nativeHost'] as String,
      rustVersion: manifest['rustVersion'] as String,
      rustCommit: manifest['rustCommit'] as String,
      manifestGuestTarget: manifest['guestTarget'] as String,
    );
    if (!identity.manifestMatchesTarget) {
      throw StateError('Prepared runtime differs from packaged manifest');
    }
    final results = <RustNativeCaseResult>[];
    RustNativeCaseResult? pendingCancellation;
    var interrupted = true;
    RustNativeCatalogReport snapshot() => RustNativeCatalogReport(
      identity: identity,
      catalog: catalog,
      results: [
        ...results,
        if (pendingCancellation != null) pendingCancellation!,
      ],
      missingIds: const [],
      interrupted: interrupted,
      startedAt: startedAt,
      finishedAt: DateTime.now().toUtc(),
    );
    void save() {
      final data = snapshot().toJson();
      data['manifestSha256'] = sha256Hex(manifestSource);
      data['phase'] = pendingCancellation != null
          ? 'cancelling'
          : interrupted
          ? 'running'
          : 'finished';
      if (pendingCancellation != null) {
        data['pendingCancellationId'] = pendingCancellation!.id;
      }
      data['bundleVerification'] = {
        'scope': 'bundled main entry only',
        'cargoBuildAllTargets': 'not_run',
        'cargoTest': 'not_run',
      };
      persist(data);
    }

    save();
    try {
      for (final testCase in catalog.cases) {
        final result = await runRustNativeCatalogCase(
          runnerFactory: (onStdoutBytes) => NativeMiriProgramRunner(
            sysrootPath: runtime.sysrootPath,
            libraryPath: runtime.libraryPath,
            backendPath: runtime.backendPath,
            onStdoutBytes: onStdoutBytes,
          ),
          testCase: testCase,
          timeout: caseTimeout,
          onTimeout: (result) {
            pendingCancellation = result;
            save();
          },
        );
        pendingCancellation = null;
        results.add(result);
        save();
        onProgress?.call(result, results.length, catalog.runCount);
      }
      interrupted = false;
    } finally {
      save();
    }
    return snapshot();
  } catch (error, stack) {
    persist({
      ...latest,
      'complete': false,
      'passed': false,
      'interrupted': true,
      'phase': 'interrupted',
      'error': '$error',
      'stack': '$stack',
      'finishedAt': DateTime.now().toUtc().toIso8601String(),
    });
    rethrow;
  }
}

void writeRustAuditReport(File file, Map<String, Object?> data) {
  file.parent.createSync(recursive: true);
  final temporary = File('${file.path}.part');
  temporary.writeAsStringSync(
    '${const JsonEncoder.withIndent('  ').convert(data)}\n',
    flush: true,
  );
  temporary.renameSync(file.path);
}

/// Executes one case through a fresh runner, preserving exact native stdout.
///
/// [onTimeout] runs before awaiting cooperative cancellation. The caller can
/// durably checkpoint the failure while this future retains the live run and
/// its scratch directory until the backend has actually stopped.
Future<RustNativeCaseResult> runRustNativeCatalogCase({
  required ProgramRunner Function(void Function(List<int>) onStdoutBytes)
  runnerFactory,
  required RustNativeCatalogCase testCase,
  required Duration timeout,
  required void Function(RustNativeCaseResult) onTimeout,
}) async {
  final started = DateTime.now();
  Directory? directory;
  var exitCode = kProgramNotRunExitCode;
  final stdoutBytes = BytesBuilder();
  final errors = <String>[];
  var status = RustNativeCaseStatus.error;
  String? detail;
  Future<void> Function()? cancelRun;
  final runnerReady = Completer<void>();

  RustNativeCaseResult snapshot() => RustNativeCaseResult(
    id: testCase.id,
    topicId: testCase.topicId,
    kind: testCase.kind,
    runtime: testCase.runtime,
    entryFile: testCase.entryFile,
    sourceSha256: testCase.sourceSha256,
    status: status,
    exitCode: exitCode,
    expectedExitCode: testCase.expectedExitCode,
    stdoutAsserted: testCase.stdoutAsserted,
    expectedStdout: testCase.expectedStdout,
    stdout: utf8.decode(stdoutBytes.toBytes(), allowMalformed: true),
    stderr: errors.join('\n'),
    durationMs: DateTime.now().difference(started).inMilliseconds,
    detail: detail,
  );

  Future<int> run() async {
    try {
      if (sha256Hex(testCase.source) != testCase.sourceSha256) {
        throw const FormatException('Catalog source digest differs before run');
      }
      final scratch = Directory.systemTemp.createTempSync('qfli_catalog_case_');
      directory = scratch;
      if (testCase.files != null) {
        for (final entry in testCase.files!.entries) {
          if (sha256Hex(entry.value) != testCase.filesSha256?[entry.key]) {
            throw FormatException('Catalog file digest differs: ${entry.key}');
          }
          final file = File(p.joinAll([scratch.path, ...entry.key.split('/')]));
          file.parent.createSync(recursive: true);
          file.writeAsStringSync(entry.value, flush: true);
        }
      }
      final entryFile = p.joinAll([
        scratch.path,
        ...testCase.entryFile.split('/'),
      ]);
      File(entryFile).writeAsStringSync(testCase.source, flush: true);
      final runner = runnerFactory(stdoutBytes.add);
      final result = await runner.run(
        projectPath: scratch.path,
        entryFile: entryFile,
      );
      if (result == null) {
        errors.add('ProgramRunner declined a .rs entry file.');
        return kProgramNotRunExitCode;
      }
      cancelRun = result.cancel;
      final stdoutDone = result.stdout.drain<void>();
      final stderrDone = result.stderr.forEach(errors.add);
      runnerReady.complete();
      try {
        return await result.exitCode;
      } finally {
        await Future.wait([stdoutDone, stderrDone]);
      }
    } finally {
      if (!runnerReady.isCompleted) runnerReady.complete();
    }
  }

  Future<void> cancelAndWait(Future<int> execution) async {
    // A timeout can precede runner.run's return. Do not miss cancellation of
    // a session that is still being prepared, or delete its inputs early.
    await runnerReady.future;
    try {
      await cancelRun?.call();
    } catch (error) {
      errors.add('Native cancellation failed: $error');
    }
    await execution.then<void>(
      (code) => exitCode = code,
      onError: (Object _, StackTrace _) {},
    );
  }

  final execution = run();
  try {
    exitCode = await execution.timeout(
      timeout,
      onTimeout: () {
        throw TimeoutException(
          'case exceeded ${timeout.inMilliseconds}ms without completing',
        );
      },
    );
    final mismatch = compareNativeStdout(
      testCase: testCase,
      // Malformed complete output is an execution error. Replacement decoding
      // is reserved for partial timeout evidence, never for accepting stdout.
      stdout: utf8.decode(stdoutBytes.toBytes()),
      exitCode: exitCode,
    );
    if (mismatch == null) {
      status = RustNativeCaseStatus.passed;
    } else {
      status = RustNativeCaseStatus.failed;
      detail = mismatch;
    }
  } on TimeoutException catch (error) {
    status = RustNativeCaseStatus.error;
    detail =
        '${error.message}; the engine did not finish within '
        '${timeout.inMilliseconds}ms; waiting for native cancellation';
    // This callback must finish its durable write before any unbounded native
    // wait. It is unsafe to destroy the worker or run the next case meanwhile.
    try {
      onTimeout(snapshot());
    } finally {
      await cancelAndWait(execution);
    }
    detail = '${error.message}; native execution stopped after timeout';
  } catch (error) {
    status = RustNativeCaseStatus.error;
    detail = 'native execution error: $error';
    await cancelAndWait(execution);
  } finally {
    try {
      directory?.deleteSync(recursive: true);
    } on FileSystemException {
      // A leftover scratch directory must not hide the real case outcome.
    }
  }

  return snapshot();
}
