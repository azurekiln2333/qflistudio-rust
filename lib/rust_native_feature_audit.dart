import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:path/path.dart' as p;
import 'package:qfli_studio_core/services/code_analysis.dart';
import 'package:qfli_studio_core/services/debug_session.dart';

import 'native_miri_analyzer.dart';
import 'native_miri_assets.dart';
import 'rust_code_analyzer.dart';
import 'rust_debugger.dart';
import 'rust_native_catalog.dart';
import 'rust_native_catalog_audit.dart' show writeRustAuditReport;

enum RustNativeFeatureCheck {
  analysisValid,
  analysisUnsavedModule,
  debuggerEntryBreakpointStep,
  debuggerLiveOutputCancel,
  debuggerFreshLaunch,
  nativeOfflineGuards,
}

final class RustNativeFeatureResult {
  RustNativeFeatureResult({
    required this.check,
    required this.status,
    required this.durationMs,
    this.detail,
    Map<String, Object?> evidence = const {},
  }) : evidence = Map.unmodifiable(evidence);

  final RustNativeFeatureCheck check;
  final RustNativeCaseStatus status;
  final int durationMs;
  final String? detail;
  final Map<String, Object?> evidence;

  Map<String, Object?> toJson() => {
    'id': check.name,
    'status': status.wireName,
    'durationMs': durationMs,
    if (detail != null) 'detail': detail,
    'evidence': evidence,
  };
}

/// Provider evidence only. Shared editor navigation and panel acceptance need
/// their own UI checks; the catalog's 332 programs remain a separate report.
final class RustNativeFeatureReport {
  RustNativeFeatureReport({
    required this.runId,
    required this.auditBuildId,
    required this.identity,
    required this.manifestSha256,
    required this.startedAt,
    required this.finishedAt,
    required this.interrupted,
    required this.cleanupComplete,
    required this.actualProviders,
    required Map<String, String> fixtureSha256,
    required List<RustNativeFeatureResult> results,
  }) : fixtureSha256 = Map.unmodifiable(fixtureSha256),
       results = List.unmodifiable(results);

  final String runId;
  final String auditBuildId;
  final RustNativeRuntimeIdentity identity;
  final String manifestSha256;
  final DateTime startedAt;
  final DateTime finishedAt;
  final bool interrupted;
  final bool cleanupComplete;
  final bool actualProviders;
  final Map<String, String> fixtureSha256;
  final List<RustNativeFeatureResult> results;

  List<String> get missingIds => [
    for (final check in RustNativeFeatureCheck.values)
      if (!results.any((result) => result.check == check)) check.name,
  ];

  bool get complete =>
      !interrupted &&
      cleanupComplete &&
      missingIds.isEmpty &&
      results.length == RustNativeFeatureCheck.values.length &&
      results.map((result) => result.check).toSet().length == results.length;

  bool get checksPassed =>
      complete &&
      results.every(
        (result) =>
            result.status == RustNativeCaseStatus.passed &&
            result.evidence.isNotEmpty,
      );

  bool get passed =>
      checksPassed &&
      actualProviders &&
      runId.isNotEmpty &&
      auditBuildId.isNotEmpty &&
      identity.platform == 'ohos' &&
      identity.manifestMatchesTarget &&
      _digest.hasMatch(manifestSha256) &&
      fixtureSha256.length == _fixtures.length &&
      _fixtures.entries.every(
        (entry) => fixtureSha256[entry.key] == sha256Hex(entry.value),
      );

  Map<String, Object?> toJson() => {
    'schemaVersion': 1,
    'scope': 'native_feature_providers',
    'runId': runId,
    'auditBuildId': auditBuildId,
    'startedAt': startedAt.toIso8601String(),
    'finishedAt': finishedAt.toIso8601String(),
    'interrupted': interrupted,
    'cleanupComplete': cleanupComplete,
    'complete': complete,
    'checksPassed': checksPassed,
    'passed': passed,
    'evidenceKind': actualProviders
        ? 'actual_packaged_runtime'
        : 'injected_dependencies_not_acceptance',
    'runtime': identity.toJson(),
    'manifestSha256': manifestSha256,
    'fixtureSha256': fixtureSha256,
    'expected': RustNativeFeatureCheck.values.length,
    'executed': results.length,
    'missingIds': missingIds,
    'checks': results.map((result) => result.toJson()).toList(),
    'acceptance': {
      'catalogExecution': 'separate_report',
      'sharedEditorSquigglesAndProblemsNavigation': 'not_tested',
      'sharedOutputDebugConsoleTerminalAndPorts': 'not_tested',
    },
  };
}

final _digest = RegExp(r'^[a-f0-9]{64}$');

final class RustNativeFeatureRuntime {
  const RustNativeFeatureRuntime({
    required this.runtime,
    required this.identity,
    required this.manifestSha256,
  });

  final NativeMiriRuntime runtime;
  final RustNativeRuntimeIdentity identity;
  final String manifestSha256;
}

/// Narrow boundaries for report/lifecycle regression tests. Any override is
/// explicitly marked as injected evidence and cannot produce an acceptance pass.
final class RustNativeFeatureAuditDependencies {
  const RustNativeFeatureAuditDependencies({
    required this.prepareRuntime,
    required this.analysisTransport,
    required this.debugger,
    required this.invokePlatformMethod,
  });

  final Future<RustNativeFeatureRuntime> Function() prepareRuntime;
  final RustAnalysisTransport Function(NativeMiriRuntime) analysisTransport;
  final StudioDebugger Function(NativeMiriRuntime) debugger;
  final Future<void> Function(String method) invokePlatformMethod;
}

/// Retains the live audit owner when automatic cleanup retries fail. The caller
/// can retry after the backend recovers; inputs remain owned until real cleanup.
final class RustNativeFeatureCleanupFailure implements Exception {
  RustNativeFeatureCleanupFailure._(this.cause, this._retry);

  final Object cause;
  final Future<void> Function() _retry;
  Future<void>? _retrying;

  Future<void> retryCleanup() =>
      _retrying ??= _retry().whenComplete(() => _retrying = null);

  @override
  String toString() => 'Rust native feature cleanup remains incomplete: $cause';
}

/// Runs after (and independently of) the catalog audit in the isolated HAP.
/// No URL is supplied to the native guard probes, even if an old build is used.
/// Missing optional analysis/debug symbols fail checks rather than being skipped.
Future<RustNativeFeatureReport> runRustNativeFeatureAudit({
  required File reportFile,
  Duration checkTimeout = const Duration(seconds: 45),
  String auditBuildId = const String.fromEnvironment(
    'QFLI_RUST_AUDIT_BUILD_ID',
  ),
  RustNativeFeatureAuditDependencies? dependencies,
  void Function(RustNativeFeatureResult result)? onProgress,
}) async {
  final startedAt = DateTime.now().toUtc();
  final runId = '${startedAt.microsecondsSinceEpoch}-$pid-features';
  var latest = <String, Object?>{
    'schemaVersion': 1,
    'scope': 'native_feature_providers',
    'runId': runId,
    'auditBuildId': auditBuildId,
    'startedAt': startedAt.toIso8601String(),
    'complete': false,
    'passed': false,
    'interrupted': true,
    'cleanupComplete': false,
    'phase': 'preparing',
    'checks': <Object?>[],
  };
  void persist(Map<String, Object?> value) {
    latest = value;
    writeRustAuditReport(reportFile, value);
  }

  // Synchronous invalidation precedes runtime preparation and the first await.
  persist(latest);
  _FeatureAudit? audit;
  try {
    if (checkTimeout.inMicroseconds <= 0) {
      throw ArgumentError.value(
        checkTimeout,
        'checkTimeout',
        'must be positive',
      );
    }
    final selected = dependencies ?? _actualDependencies();
    final prepared = await selected.prepareRuntime();
    _validateRuntime(prepared);
    final instance = _FeatureAudit(prepared, selected);
    audit = instance;
    final results = <RustNativeFeatureResult>[];
    var interrupted = true;
    var cleanupComplete = false;
    RustNativeFeatureReport snapshot() => RustNativeFeatureReport(
      runId: runId,
      auditBuildId: auditBuildId,
      identity: prepared.identity,
      manifestSha256: prepared.manifestSha256,
      startedAt: startedAt,
      finishedAt: DateTime.now().toUtc(),
      interrupted: interrupted,
      cleanupComplete: cleanupComplete,
      actualProviders: dependencies == null,
      fixtureSha256: {
        for (final entry in _fixtures.entries)
          entry.key: sha256Hex(entry.value),
      },
      results: results,
    );
    void save(String phase, {RustNativeFeatureCheck? pending}) {
      persist({
        ...snapshot().toJson(),
        'phase': phase,
        if (pending != null) 'pendingCancellationId': pending.name,
      });
    }

    save('running');
    for (final check in RustNativeFeatureCheck.values) {
      final timer = Stopwatch()..start();
      final execution = instance.check(check);
      RustNativeFeatureResult result;
      try {
        final evidence = await execution.timeout(checkTimeout);
        result = RustNativeFeatureResult(
          check: check,
          status: RustNativeCaseStatus.passed,
          durationMs: timer.elapsedMilliseconds,
          evidence: evidence,
        );
      } on Object catch (error) {
        result = RustNativeFeatureResult(
          check: check,
          status: error is TimeoutException
              ? RustNativeCaseStatus.error
              : RustNativeCaseStatus.failed,
          durationMs: timer.elapsedMilliseconds,
          detail: '$error',
          evidence: instance.failureEvidence(check),
        );
        results.add(result);
        // Persist before waiting: timeout/cancel does not establish worker exit.
        save('cancelling', pending: check);
        await instance.cancelAndWait();
        await execution.then<void>(
          (_) {},
          onError: (Object _, StackTrace _) {},
        );
        save('running');
        onProgress?.call(result);
        continue;
      }
      results.add(result);
      save('running');
      onProgress?.call(result);
    }
    await instance.dispose();
    cleanupComplete = true;
    interrupted = false;
    save('finished');
    return snapshot();
  } on Object catch (error, stack) {
    // Report I/O can be the original failure. A second failed checkpoint must
    // never bypass native cleanup or discard the owner needed to retry it.
    void persistFailure(Map<String, Object?> value) {
      try {
        persist(value);
      } on Object catch (reportError) {
        latest = {...value, 'reportWriteError': '$reportError'};
      }
    }

    persistFailure({
      ...latest,
      'complete': false,
      'passed': false,
      'interrupted': true,
      'phase': audit == null ? 'interrupted' : 'cancelling',
      'error': '$error',
      'stack': '$stack',
      'finishedAt': DateTime.now().toUtc().toIso8601String(),
    });
    if (audit != null) {
      final retained = audit;
      Future<void> retryCleanup() async {
        try {
          await retained.dispose();
        } on Object catch (cleanupError) {
          persistFailure({
            ...latest,
            'phase': 'cancelling',
            'cleanupComplete': false,
            'cleanupError': '$cleanupError',
          });
          rethrow;
        }
        persistFailure({
          ...latest,
          'phase': 'interrupted',
          'cleanupComplete': true,
        });
      }

      try {
        await retryCleanup();
      } on Object catch (cleanupError) {
        throw RustNativeFeatureCleanupFailure._(cleanupError, retryCleanup);
      }
    }
    rethrow;
  }
}

RustNativeFeatureAuditDependencies _actualDependencies() =>
    RustNativeFeatureAuditDependencies(
      prepareRuntime: _prepareRuntime,
      analysisTransport: (runtime) =>
          NativeMiriAnalysisTransport(prepareRuntime: () async => runtime),
      debugger: (runtime) => RustDebugger(
        libraryPath: runtime.libraryPath,
        prepareRuntime: () async => runtime,
        timeout: const Duration(minutes: 3),
        maxSteps: 1000000000,
      ),
      invokePlatformMethod: (method) =>
          const MethodChannel('qflistudio/platform').invokeMethod<void>(method),
    );

Future<RustNativeFeatureRuntime> _prepareRuntime() async {
  final target = NativeMiriTarget.current();
  if (target.platform != 'ohos' || target.nativeHosts.isEmpty) {
    throw StateError(
      'Feature acceptance requires packaged OHOS: ${target.key}',
    );
  }
  final source = await target.loadManifest(rootBundle);
  final manifest = jsonDecode(source) as Map<String, dynamic>;
  final inventory = await AssetManifest.loadFromAssetBundle(rootBundle);
  final runtime = await prepareNativeMiriAssets(target: target);
  return RustNativeFeatureRuntime(
    runtime: runtime,
    manifestSha256: sha256Hex(source),
    identity: RustNativeRuntimeIdentity(
      platform: target.platform,
      architecture: target.architecture,
      targetKey: target.key,
      nativeHost: runtime.nativeHost,
      targetNativeHosts: target.nativeHosts,
      guestTarget: manifest['guestTarget'] as String,
      libraryPath: runtime.libraryPath,
      sysrootPath: runtime.sysrootPath,
      backendPath: runtime.backendPath,
      manifestAsset: inventory.listAssets().contains(target.manifestAsset)
          ? target.manifestAsset
          : rustNativeLegacyManifestAsset,
      manifestId: manifest['id'] as String,
      manifestNativeHost: manifest['nativeHost'] as String,
      rustVersion: manifest['rustVersion'] as String,
      rustCommit: manifest['rustCommit'] as String,
      manifestGuestTarget: manifest['guestTarget'] as String,
    ),
  );
}

void _validateRuntime(RustNativeFeatureRuntime prepared) {
  final runtime = prepared.runtime;
  final identity = prepared.identity;
  if (runtime.target.platform != 'ohos' ||
      identity.platform != runtime.target.platform ||
      identity.architecture != runtime.target.architecture ||
      identity.targetKey != runtime.target.key ||
      identity.nativeHost != runtime.nativeHost ||
      identity.libraryPath != runtime.libraryPath ||
      identity.sysrootPath != runtime.sysrootPath ||
      identity.backendPath != runtime.backendPath ||
      !runtime.target.nativeHosts.contains(runtime.nativeHost) ||
      !identity.manifestMatchesTarget ||
      !_digest.hasMatch(identity.manifestId) ||
      !_digest.hasMatch(prepared.manifestSha256)) {
    throw StateError('Feature runtime and packaged manifest identity differ');
  }
}

const _sentinel = 'qfli-analysis-executed';
const _manifest =
    '[package]\nname = "qfli_feature_audit"\n'
    'version = "0.0.0"\nedition = "2021"\n';
const _analysisMain =
    'mod helper;\r\nfn main() {\r\n'
    '    helper::value();\r\n'
    '    std::fs::write("$_sentinel", b"executed").unwrap();\r\n}\r\n';
const _analysisModule = 'pub fn value() -> i32 { 42 }\r\n';
const _unsavedModule =
    'pub fn value() -> i32 {\r\n'
    '    let _label = "中🙂"; let value: i32 = "坏🙂";\r\n'
    '    value\r\n}\r\n';
const _debugSource =
    'fn main() {\n'
    '    let seed: i32 = 41;\n'
    '    let answer: i32 = seed + 1;\n'
    '    println!("audit-out:{answer}");\n'
    '    eprintln!("audit-err:{answer}");\n'
    '    let mut ticks = 0u64;\n'
    '    loop { ticks = ticks.wrapping_add(1); std::hint::black_box(ticks); }\n'
    '}\n';
const _freshSource = 'fn main() { println!("audit-fresh:42"); }\n';
const _fixtures = {
  'analysis/Cargo.toml': _manifest,
  'analysis/src/main.rs': _analysisMain,
  'analysis/src/helper.rs': _analysisModule,
  'unsaved/analysis/src/helper.rs': _unsavedModule,
  'debug/Cargo.toml': _manifest,
  'debug/src/main.rs': _debugSource,
  'fresh/Cargo.toml': _manifest,
  'fresh/src/main.rs': _freshSource,
};

class _FeatureAudit {
  _FeatureAudit(this.prepared, this.dependencies)
    : analysis = _ObservedAnalysis(
        dependencies.analysisTransport(prepared.runtime),
      ),
      debugger = dependencies.debugger(prepared.runtime),
      root = Directory.systemTemp.createTempSync('qfli_feature_audit_') {
    try {
      for (final fixture in _fixtures.entries) {
        if (fixture.key.startsWith('unsaved/')) continue;
        final file = File(p.joinAll([root.path, ...fixture.key.split('/')]));
        file.parent.createSync(recursive: true);
        file.writeAsStringSync(fixture.value, flush: true);
      }
    } on Object {
      root.deleteSync(recursive: true);
      rethrow;
    }
  }

  final RustNativeFeatureRuntime prepared;
  final RustNativeFeatureAuditDependencies dependencies;
  final Directory root;
  final _ObservedAnalysis analysis;
  final StudioDebugger debugger;
  DebugSession? _session;
  Future<DebugSession>? _launching;
  Future<Map<String, Object?>>? _checking;
  DebugSnapshot? _breakpoint;

  String _path(String relative) =>
      p.joinAll([root.path, ...relative.split('/')]);

  Future<Map<String, Object?>> check(RustNativeFeatureCheck check) {
    final execution = switch (check) {
      RustNativeFeatureCheck.analysisValid => _analyze(unsaved: false),
      RustNativeFeatureCheck.analysisUnsavedModule => _analyze(unsaved: true),
      RustNativeFeatureCheck.debuggerEntryBreakpointStep => _debugControls(),
      RustNativeFeatureCheck.debuggerLiveOutputCancel => _debugLiveCancel(),
      RustNativeFeatureCheck.debuggerFreshLaunch => _debugFresh(),
      RustNativeFeatureCheck.nativeOfflineGuards => _offlineGuards(),
    };
    _checking = execution;
    return execution.whenComplete(() {
      if (identical(_checking, execution)) _checking = null;
    });
  }

  Map<String, Object?> failureEvidence(RustNativeFeatureCheck check) =>
      check == RustNativeFeatureCheck.analysisValid ||
          check == RustNativeFeatureCheck.analysisUnsavedModule
      ? {
          'completedCompilerCalls': analysis.completed,
          'mirrorSentinelChecks': analysis.stopped,
          'executionSentinelPresent': analysis.sentinelSeen,
        }
      : const {};

  Future<Map<String, Object?>> _analyze({required bool unsaved}) async {
    final module = _path('analysis/src/helper.rs');
    final completedBefore = analysis.completed;
    final result =
        await RustCodeAnalyzer(
          transport: analysis,
          timeout: const Duration(seconds: 30),
        ).analyze(
          CodeAnalysisRequest(
            projectPath: _path('analysis'),
            activeFilePath: unsaved ? module : _path('analysis/src/main.rs'),
            language: 'rust',
            revision: unsaved ? 2 : 1,
            documents: [
              if (unsaved)
                CodeDocumentSnapshot(
                  path: module,
                  text: _unsavedModule,
                  revision: 2,
                ),
            ],
          ),
        );
    _require(
      result.unavailableReason == null,
      'Analysis unavailable: '
      '${result.unavailableReason}',
    );
    _require(
      analysis.completed == completedBefore + 1,
      'Analysis transport did not complete exactly one compiler call',
    );
    _require(!analysis.sentinelSeen, 'Analysis executed the sentinel program');
    _unchanged();
    if (!unsaved) {
      _require(result.diagnostics.isEmpty, 'Valid source produced diagnostics');
    } else {
      final start = _unsavedModule.indexOf('"坏🙂"');
      final end = start + '"坏🙂"'.length;
      _require(
        result.diagnostics.any(
          (item) =>
              p.equals(item.filePath, module) &&
              item.code == 'E0308' &&
              item.severity == CodeDiagnosticSeverity.error &&
              item.startOffset == start &&
              item.endOffset == end,
        ),
        'Unsaved Unicode/CRLF E0308 is absent or has incorrect UTF-16 offsets',
      );
    }
    return {
      'transport': 'NativeMiriAnalysisTransport',
      'completedCompilerCalls': analysis.completed,
      'unsavedOverlay': unsaved,
      'diskUnchanged': true,
      'executionSentinelPresent': false,
      'mirrorSentinelChecks': analysis.stopped,
      if (unsaved)
        'expectedDiagnostic': {
          'code': 'E0308',
          'filePath': module,
          'startOffset': _unsavedModule.indexOf('"坏🙂"'),
          'endOffset': _unsavedModule.indexOf('"坏🙂"') + '"坏🙂"'.length,
        },
      'diagnostics': [
        for (final item in result.diagnostics)
          {
            'filePath': item.filePath,
            'code': item.code,
            'severity': item.severity.name,
            'startOffset': item.startOffset,
            'endOffset': item.endOffset,
            'message': item.message,
          },
      ],
    };
  }

  void _unchanged() {
    for (final entry in _fixtures.entries) {
      if (entry.key.startsWith('unsaved/')) continue;
      _require(
        base64Encode(File(_path(entry.key)).readAsBytesSync()) ==
            base64Encode(utf8.encode(entry.value)),
        'Source bytes changed: ${entry.key}',
      );
    }
    _require(
      !root
          .listSync(recursive: true, followLinks: false)
          .any((entry) => p.basename(entry.path) == _sentinel),
      'Analysis wrote an execution sentinel',
    );
  }

  void _capabilities() {
    final caps = debugger.capabilities;
    _require(
      debugger.supportsLanguage('rust') &&
          caps.supportsStopOnEntry &&
          caps.supportsStepOver &&
          caps.supportsStackFrames &&
          caps.supportsVariables &&
          caps.outputDelivery == DebugOutputDelivery.live,
      'Required native debugger capabilities are unavailable',
    );
  }

  Future<DebugSession> _launch(
    String project, {
    bool controlled = false,
  }) async {
    _require(
      _session == null && _launching == null,
      'Prior debug worker is live',
    );
    final entry = _path('$project/src/main.rs');
    final work = debugger.launch(
      DebugLaunchRequest(
        projectPath: _path(project),
        entryFilePath: entry,
        language: 'rust',
        documents: const [],
        stopOnEntry: controlled,
        breakpoints: [
          if (controlled) DebugBreakpoint(filePath: entry, line: 4),
        ],
      ),
    );
    _launching = work;
    try {
      return _session = await work;
    } finally {
      _launching = null;
    }
  }

  Future<Map<String, Object?>> _debugControls() async {
    _capabilities();
    final session = await _launch('debug', controlled: true);
    final entry = await _observe(
      session,
      (state) => state.phase == DebugPhase.paused,
    );
    final frame = _projectFrame(entry, _path('debug/src/main.rs'));
    _require(
      frame.name.contains('main'),
      'Entry does not contain actual main frame',
    );
    await session.command(DebugCommand.stepOver, pauseToken: entry.pauseToken);
    final stepped = await _observe(
      session,
      (state) =>
          state.phase == DebugPhase.paused &&
          state.pauseToken != entry.pauseToken,
    );
    final stepFrame = _projectFrame(stepped, _path('debug/src/main.rs'));
    _require(
      stepFrame.location!.line != frame.location!.line ||
          stepFrame.location!.column != frame.location!.column,
      'Step did not advance the actual source location',
    );
    if (!_isBreakpoint(stepped)) {
      await session.command(
        DebugCommand.resume,
        pauseToken: stepped.pauseToken,
      );
    }
    final hit = await _observe(session, _isBreakpoint);
    final actual = _projectFrame(hit, _path('debug/src/main.rs'));
    _require(actual.location!.line == 4, 'Breakpoint paused at another line');
    for (final expected in {'seed': '41', 'answer': '42'}.entries) {
      _require(
        actual.locals.any(
          (local) =>
              local.name == expected.key &&
              local.value == expected.value &&
              local.unavailableReason == null &&
              !local.truncated,
        ),
        'Actual scalar ${expected.key}=${expected.value} is unavailable',
      );
    }
    _breakpoint = hit;
    return {
      'entry': _snapshot(entry),
      'stepOver': _snapshot(stepped),
      'breakpoint': _snapshot(hit),
    };
  }

  bool _isBreakpoint(DebugSnapshot state) =>
      state.phase == DebugPhase.paused &&
      state.breakpoints.any(
        (point) =>
            point.status == DebugBreakpointStatus.verified &&
            point.requested.line == 4 &&
            point.actualLocation?.line == 4 &&
            point.actualLocation?.filePath == _path('debug/src/main.rs'),
      );

  Future<Map<String, Object?>> _debugLiveCancel() async {
    final session = _session;
    final pause = _breakpoint;
    _require(
      session != null && pause != null,
      'No preceding verified breakpoint',
    );
    await session!.command(DebugCommand.resume, pauseToken: pause!.pauseToken);
    final live = await _observe(
      session,
      (state) =>
          state.phase == DebugPhase.running &&
          state.stdout == 'audit-out:42\n' &&
          state.stderr == 'audit-err:42\n',
    );
    _require(
      !live.stdoutTruncated && !live.stderrTruncated,
      'Live output was truncated',
    );
    await _stopSession();
    final terminal = session.snapshot;
    _require(
      terminal.isTerminal &&
          terminal.exitCode == 130 &&
          terminal.phase == DebugPhase.terminated,
      'Cancellation did not exit130',
    );
    return {
      'liveBeforeStop': _snapshot(live),
      'afterJoinedStop': _snapshot(terminal),
    };
  }

  Future<Map<String, Object?>> _debugFresh() async {
    _capabilities();
    final session = await _launch('fresh');
    await session.done;
    final terminal = session.snapshot;
    _require(
      terminal.phase == DebugPhase.terminated &&
          terminal.exitCode == 0 &&
          terminal.stdout == 'audit-fresh:42\n' &&
          terminal.stderr.isEmpty &&
          !terminal.stdoutTruncated &&
          !terminal.stderrTruncated,
      'Fresh debug launch did not finish correctly',
    );
    await _stopSession();
    _unchanged();
    return {'afterJoinedExit': _snapshot(terminal), 'diskUnchanged': true};
  }

  Future<Map<String, Object?>> _offlineGuards() async {
    final codes = <String, String>{};
    for (final method in const ['openUrl', 'openAgreement']) {
      try {
        // Deliberately no URL/arguments: an older handler cannot open a URL.
        await dependencies.invokePlatformMethod(method);
        throw StateError('$method accepted an online entry');
      } on PlatformException catch (error) {
        _require(
          error.code == 'OFFLINE_ONLY',
          '$method returned ${error.code}',
        );
        codes[method] = error.code;
      }
    }
    return {'argumentsSupplied': false, 'nativeRejections': codes};
  }

  Future<void> _stopSession() async {
    final launching = _launching;
    if (launching != null) {
      try {
        _session = await launching;
      } on Object {
        // The provider contract requires launch failure to clean partial handles.
      }
    }
    final session = _session;
    if (session == null) return;
    // A failed stop deliberately keeps done pending in RustDebugger so its
    // cleanup can be retried. Surface that error with _session still owned;
    // awaiting done here would prevent the outer dispose retry forever.
    await session.stop();
    await session.done;
    await session.dispose();
    _session = null;
    _breakpoint = null;
  }

  Future<void> cancelAndWait() async {
    try {
      await analysis.cancelAndWait();
    } finally {
      await _stopSession();
    }
  }

  Future<void> dispose() async {
    await cancelAndWait();
    // A timeout checkpoint can itself fail while the check is still unwinding,
    // or before analysis has created its native worker. Keep its inputs until
    // that complete operation has stopped using them too.
    await _checking?.then<void>((_) {}, onError: (Object _, StackTrace _) {});
    if (root.existsSync()) root.deleteSync(recursive: true);
  }
}

DebugFrame _projectFrame(DebugSnapshot snapshot, String path) {
  for (final frame in snapshot.frames) {
    if (frame.location?.filePath == path) return frame;
  }
  throw StateError('Native pause has no actual project source frame');
}

Future<DebugSnapshot> _observe(
  DebugSession session,
  bool Function(DebugSnapshot) matches,
) async {
  final result = Completer<DebugSnapshot>();
  void accept(DebugSnapshot state) {
    if (result.isCompleted) return;
    if (matches(state)) {
      result.complete(state);
    } else if (state.isTerminal) {
      result.completeError(
        StateError(
          'Debugger ended before expected state: '
          '${state.phase.name}/${state.exitCode}: ${state.message}',
        ),
      );
    }
  }

  final subscription = session.updates.listen(
    accept,
    onError: (Object error, StackTrace stack) {
      if (!result.isCompleted) result.completeError(error, stack);
    },
    onDone: () {
      if (!result.isCompleted) {
        result.completeError(StateError('Debug stream closed'));
      }
    },
  );
  accept(session.snapshot);
  try {
    return await result.future;
  } finally {
    await subscription.cancel();
  }
}

Map<String, Object?> _snapshot(DebugSnapshot state) => {
  'sessionId': state.sessionId,
  'revision': state.revision,
  'phase': state.phase.name,
  'pauseGeneration': state.pauseToken?.generation,
  'exitCode': state.exitCode,
  'stdout': state.stdout,
  'stderr': state.stderr,
  'console': state.console,
  'frames': [
    for (final frame in state.frames)
      {
        'name': frame.name,
        'path': frame.location?.filePath,
        'line': frame.location?.line,
        'column': frame.location?.column,
        'locals': [
          for (final local in frame.locals)
            {
              'name': local.name,
              'type': local.type,
              'value': local.value,
              'unavailableReason': local.unavailableReason,
              'truncated': local.truncated,
            },
        ],
      },
  ],
};

void _require(bool condition, String message) {
  if (!condition) throw StateError(message);
}

/// Observes the actual compiler mirror before the analyzer can remove it.
/// Completion/cancellation waits remain tied to the delegate's real work.
class _ObservedAnalysis
    implements RustAnalysisTransport, RustAnalysisCancellation {
  _ObservedAnalysis(this.delegate);
  final RustAnalysisTransport delegate;
  final Set<Future<RustAnalysisOutput>> _active = {};
  int completed = 0;
  int stopped = 0;
  bool sentinelSeen = false;

  @override
  Future<RustAnalysisOutput> analyze(RustAnalysisJob job) async {
    final work = delegate.analyze(job);
    _active.add(work);
    try {
      final result = await work;
      completed++;
      return result;
    } finally {
      // The delegate's real call has stopped, including when it throws. Inspect
      // before completing this wrapper so the analyzer still owns the mirror.
      sentinelSeen |=
          File(p.join(job.mirrorRoot, _sentinel)).existsSync() ||
          File(p.join(p.dirname(job.entryPath), _sentinel)).existsSync();
      stopped++;
      _active.remove(work);
    }
  }

  @override
  Future<void> cancel() => cancelAndWait();

  Future<void> cancelAndWait() async {
    final pending = _active.toList();
    try {
      if (delegate is RustAnalysisCancellation) {
        await (delegate as RustAnalysisCancellation).cancel();
      }
    } finally {
      await Future.wait(
        pending.map(
          (work) =>
              work.then<void>((_) {}, onError: (Object _, StackTrace _) {}),
        ),
      );
    }
  }
}
