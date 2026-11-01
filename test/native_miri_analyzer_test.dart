import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;
import 'package:qfli_rust/native_miri_analyzer.dart';
import 'package:qfli_rust/native_miri_assets.dart';
import 'package:qfli_rust/rust_code_analyzer.dart';
import 'package:qfli_studio_core/services/code_analysis.dart';

void main() {
  late Directory temporary;
  late Directory mirror;
  late String entry;
  late NativeMiriRuntime runtime;

  setUp(() {
    temporary = Directory.systemTemp.createTempSync('qfli_native_analysis_');
    mirror = Directory(p.join(temporary.path, 'mirror'))..createSync();
    entry = p.join(mirror.path, 'main.rs');
    File(entry).writeAsStringSync('fn main() {}');
    final sysroot = Directory(p.join(temporary.path, 'sysroot'))..createSync();
    runtime = NativeMiriRuntime(
      target: const NativeMiriTarget(platform: 'ohos', architecture: 'x64'),
      nativeHost: 'x86_64-unknown-linux-ohos',
      sysrootPath: sysroot.path,
      libraryPath: p.join(temporary.path, 'missing-adapter'),
    );
  });

  tearDown(() => temporary.deleteSync(recursive: true));

  RustAnalysisJob job({
    Duration timeout = const Duration(seconds: 5),
    String? entryPath,
    String crateName = 'analysis_test',
    String edition = '2021',
    String crateType = 'bin',
  }) => RustAnalysisJob(
    mirrorRoot: mirror.path,
    entryPath: entryPath ?? entry,
    crateName: crateName,
    crateType: crateType,
    edition: edition,
    timeout: timeout,
    projectPath: p.join(temporary.path, 'original'),
    remapFrom: mirror.path,
  );

  NativeMiriAnalysisTransport transport(
    _Session session, {
    int maxOutputBytes = 8 * 1024 * 1024,
  }) => NativeMiriAnalysisTransport(
    prepareRuntime: () async => runtime,
    sessionFactory: (_, _, _) => session,
    maxOutputBytes: maxOutputBytes,
  );

  test(
    'completed compiler errors remain diagnostic data at exit zero',
    () async {
      const diagnostic = '{"level":"error","message":"类型不匹配 😀"}\n';
      final session = _Session(diagnostics: utf8.encode(diagnostic));
      final output = await transport(session).analyze(job());
      expect(output.exitCode, 0);
      expect(output.diagnosticsJsonl, diagnostic);
      expect(output.timedOut, isFalse);
      expect(output.truncated, isFalse);
      expect(session.events, [
        'analyze-start',
        'analyze-end',
        'result',
        'diagnostics',
        'destroy',
      ]);
    },
  );

  test(
    'passes the prepared runtime and exact crate plan to the session',
    () async {
      final planned = job(crateType: 'lib', edition: '2024');
      final session = _Session();
      final backend = NativeMiriAnalysisTransport(
        prepareRuntime: () async => runtime,
        maxOutputBytes: 4096,
        sessionFactory: (prepared, actual, limit) {
          expect(identical(prepared, runtime), isTrue);
          expect(identical(actual, planned), isTrue);
          expect(limit, 4096);
          return session;
        },
      );
      final output = await backend.analyze(planned);
      expect(output.diagnosticsJsonl, isEmpty);
    },
  );

  for (final accepted in [2, -1]) {
    test(
      'rejected native call $accepted is unavailable, never clean',
      () async {
        final session = _Session(accepted: accepted);
        await expectLater(
          transport(session).analyze(job()),
          throwsA(_unavailable(accepted == 2 ? '正在运行' : '拒绝执行')),
        );
        expect(session.events, ['analyze-start', 'analyze-end', 'destroy']);
      },
    );
  }

  for (final state in [0, 1, 3, 4, 5, 6, 7]) {
    test(
      'native terminal/state $state cannot produce a clean result',
      () async {
        final session = _Session(
          value: NativeMiriAnalysisResult(state: state, exitCode: -1),
        );
        await expectLater(
          transport(session).analyze(job()),
          throwsA(isA<RustAnalysisUnavailable>()),
        );
        expect(session.events, isNot(contains('diagnostics')));
        expect(session.events.last, 'destroy');
      },
    );
  }

  test('inconsistent finished exit status is unavailable', () async {
    final session = _Session(
      value: const NativeMiriAnalysisResult(state: 2, exitCode: 1),
    );
    await expectLater(
      transport(session).analyze(job()),
      throwsA(_unavailable('无效的完成状态')),
    );
    expect(session.events.last, 'destroy');
  });

  test(
    'cancellation retains the handle until the blocking call returns',
    () async {
      final session = _Session(blocked: true);
      final backend = transport(session);
      final pending = backend.analyze(job());
      final checked = expectLater(pending, throwsA(_unavailable('已取消')));
      await session.started.future;
      var cancellationDone = false;
      final cancelled = backend.cancel().then((_) => cancellationDone = true);
      await session.cancelled.future;
      expect(cancellationDone, isFalse);
      expect(session.events, ['analyze-start', 'cancel']);
      session.release.complete();
      await checked;
      await cancelled;
      expect(session.events, [
        'analyze-start',
        'cancel',
        'analyze-end',
        'destroy',
      ]);
    },
  );

  test(
    'timeout cancels but awaits native return before releasing source',
    () async {
      final session = _Session(blocked: true);
      final backend = transport(session);
      var completed = false;
      final pending = backend
          .analyze(job(timeout: const Duration(milliseconds: 20)))
          .whenComplete(() => completed = true);
      final checked = expectLater(pending, throwsA(_unavailable('超时')));
      await session.cancelled.future.timeout(const Duration(seconds: 5));
      expect(completed, isFalse);
      expect(session.events, ['analyze-start', 'cancel']);
      expect(File(entry).existsSync(), isTrue);
      session.release.complete();
      await checked;
      expect(session.events.last, 'destroy');
    },
  );

  test('cancellation during preparation prevents a native session', () async {
    final prepared = Completer<NativeMiriRuntime>();
    var created = false;
    final backend = NativeMiriAnalysisTransport(
      prepareRuntime: () => prepared.future,
      sessionFactory: (_, _, _) {
        created = true;
        return _Session();
      },
    );
    final checked = expectLater(
      backend.analyze(job()),
      throwsA(_unavailable('已取消')),
    );
    final cancelled = backend.cancel();
    prepared.complete(runtime);
    await checked;
    await cancelled;
    expect(created, isFalse);
  });

  test('cancelling an old request does not poison the next analysis', () async {
    final first = _Session(blocked: true);
    final second = _Session();
    var count = 0;
    final backend = NativeMiriAnalysisTransport(
      prepareRuntime: () async => runtime,
      sessionFactory: (_, _, _) => count++ == 0 ? first : second,
    );
    final checked = expectLater(
      backend.analyze(job()),
      throwsA(_unavailable('已取消')),
    );
    await first.started.future;
    final cancelled = backend.cancel();
    first.release.complete();
    await checked;
    await cancelled;
    expect((await backend.analyze(job())).exitCode, 0);
    expect(second.events, isNot(contains('cancel')));
  });

  test('oversized or damaged diagnostics are unavailable', () async {
    final session = _Session(diagnostics: List.filled(1025, 32));
    await expectLater(
      transport(session, maxOutputBytes: 1024).analyze(job()),
      throwsA(_unavailable('超过输出上限')),
    );
    expect(session.events.last, 'destroy');
    final damaged = _Session(diagnostics: const [0xff, 0xfe]);
    await expectLater(
      transport(damaged, maxOutputBytes: 1024).analyze(job()),
      throwsA(_unavailable('不是有效的 UTF-8')),
    );
    expect(damaged.events.last, 'destroy');
  });

  test(
    'worker failure still destroys only after its future completes',
    () async {
      final session = _Session(failure: StateError('worker failed'));
      await expectLater(
        transport(session).analyze(job()),
        throwsA(_unavailable('worker failed')),
      );
      expect(session.events, ['analyze-start', 'analyze-end', 'destroy']);
    },
  );

  test(
    'invalid limits or crate settings never prepare native assets',
    () async {
      var prepared = false;
      final backend = NativeMiriAnalysisTransport(
        prepareRuntime: () async {
          prepared = true;
          return runtime;
        },
      );
      for (final invalid in [
        job(timeout: Duration.zero),
        job(crateName: 'unsafe\u0000name'),
        job(crateName: 'unsafe-name'),
        job(crateName: 'x' * 65),
        job(edition: '2099'),
        job(crateType: 'proc-macro'),
      ]) {
        await expectLater(
          backend.analyze(invalid),
          throwsA(isA<RustAnalysisUnavailable>()),
        );
      }
      expect(prepared, isFalse);
      for (final limit in [0, 1023, 16 * 1024 * 1024 + 1]) {
        final session = _Session();
        await expectLater(
          transport(session, maxOutputBytes: limit).analyze(job()),
          throwsA(_unavailable('资源限制无效')),
        );
        expect(session.events, isEmpty);
      }
    },
  );

  test(
    'a source outside the mirror is rejected before native creation',
    () async {
      final source = File(p.join(temporary.path, 'outside.rs'))
        ..writeAsStringSync('fn main() {}');
      final session = _Session();
      await expectLater(
        transport(session).analyze(job(entryPath: source.path)),
        throwsA(_unavailable('不在临时项目内')),
      );
      expect(session.events, isEmpty);
    },
  );

  test(
    'missing native library is an unavailable backend without fallback',
    () async {
      final backend = NativeMiriAnalysisTransport(
        prepareRuntime: () async => runtime,
      );
      await expectLater(
        backend.analyze(job()),
        throwsA(_unavailable('missing-adapter')),
      );
      expect(File(entry).readAsStringSync(), 'fn main() {}');
    },
  );

  test('asset preparation failure remains retryable', () async {
    var attempts = 0;
    final backend = NativeMiriAnalysisTransport(
      prepareRuntime: () async {
        if (attempts++ == 0) throw StateError('asset extraction failed');
        return runtime;
      },
      sessionFactory: (_, _, _) => _Session(),
    );
    await expectLater(
      backend.analyze(job()),
      throwsA(_unavailable('asset extraction failed')),
    );
    expect((await backend.analyze(job())).exitCode, 0);
  });

  test(
    'native JSONL reaches unsaved Unicode Problems with original paths',
    () async {
      const saved = 'fn main() {}';
      const unsaved = '\uFEFF// 中文 😀\r\nfn main() { let x: i32 = "bad"; }\r\n';
      final start = unsaved.indexOf('"bad"');
      String? compiledMirror;
      final backend = NativeMiriAnalysisTransport(
        prepareRuntime: () async => runtime,
        sessionFactory: (_, actual, _) {
          compiledMirror = actual.mirrorRoot;
          expect(
            File(actual.entryPath).readAsBytesSync(),
            utf8.encode(unsaved),
          );
          final diagnostic = jsonEncode({
            '\$message_type': 'diagnostic',
            'message': 'mismatched types',
            'level': 'error',
            'code': {'code': 'E0308'},
            'spans': [
              {
                'file_name': actual.entryPath,
                'byte_start': utf8.encode(unsaved.substring(0, start)).length,
                'byte_end': utf8.encode(unsaved.substring(0, start + 5)).length,
                'is_primary': true,
              },
            ],
            'children': <Object>[],
          });
          return _Session(diagnostics: utf8.encode('$diagnostic\n'));
        },
      );
      final result = await RustCodeAnalyzer(transport: backend).analyze(
        CodeAnalysisRequest(
          projectPath: mirror.path,
          activeFilePath: entry,
          language: 'rust',
          revision: 9,
          documents: [
            CodeDocumentSnapshot(path: entry, text: unsaved, revision: 9),
          ],
        ),
      );
      expect(result.unavailableReason, isNull);
      expect(result.diagnostics, hasLength(1));
      final problem = result.diagnostics.single;
      expect(problem.filePath, entry);
      expect(problem.code, 'E0308');
      expect(problem.startOffset, start);
      expect(problem.endOffset, start + 5);
      expect(File(entry).readAsStringSync(), saved);
      expect(Directory(compiledMirror!).existsSync(), isFalse);
    },
  );

  group('source mirror lifetime', () {
    CodeAnalysisRequest request() => CodeAnalysisRequest(
      projectPath: mirror.path,
      activeFilePath: entry,
      language: 'rust',
      revision: 1,
      documents: const [],
    );

    test(
      'an abandoned backend call keeps its sources and cleans up later',
      () async {
        final backend = _BlockedTransport();
        final analyzer = RustCodeAnalyzer(
          transport: backend,
          timeout: const Duration(milliseconds: 20),
        );
        final result = await analyzer.analyze(request());
        expect(result.unavailableReason, contains('超时'));
        expect(
          backend.cancelRequested,
          isTrue,
          reason: 'giving up must ask the backend to stop cooperatively',
        );
        final abandoned = backend.job!.mirrorRoot;
        // The native call is still blocked inside the compiler: deleting these
        // files now is exactly the race this seam exists to prevent.
        expect(Directory(abandoned).existsSync(), isTrue);
        expect(File(backend.job!.entryPath).existsSync(), isTrue);

        backend.release.complete(
          const RustAnalysisOutput(exitCode: 0, diagnosticsJsonl: ''),
        );
        await _eventually(() => !Directory(abandoned).existsSync());
        expect(Directory(abandoned).existsSync(), isFalse);
      },
    );

    test('a completed analysis still removes its mirror', () async {
      final backend = _BlockedTransport();
      final analyzer = RustCodeAnalyzer(transport: backend);
      final pending = analyzer.analyze(request());
      backend.release.complete(
        const RustAnalysisOutput(exitCode: 0, diagnosticsJsonl: ''),
      );
      final result = await pending;
      expect(result.unavailableReason, isNull);
      expect(backend.cancelRequested, isFalse);
      await _eventually(() => !Directory(backend.job!.mirrorRoot).existsSync());
    });

    test(
      'a transport that ignores cancellation never loses its sources',
      () async {
        // Worst case: the backend never stops. The analyzer must still report
        // unavailable, and must not delete the files the worker may be reading.
        final backend = _BlockedTransport();
        final analyzer = RustCodeAnalyzer(
          transport: backend,
          timeout: const Duration(milliseconds: 10),
        );
        final result = await analyzer.analyze(request());
        expect(result.unavailableReason, contains('超时'));
        await Future<void>.delayed(const Duration(milliseconds: 100));
        expect(Directory(backend.job!.mirrorRoot).existsSync(), isTrue);
        // Release so the temporary directory does not outlive the test.
        backend.release.complete(
          const RustAnalysisOutput(exitCode: 0, diagnosticsJsonl: ''),
        );
        await _eventually(
          () => !Directory(backend.job!.mirrorRoot).existsSync(),
        );
      },
    );
  });
}

Matcher _unavailable(String reason) => isA<RustAnalysisUnavailable>().having(
  (error) => error.reason,
  'reason',
  contains(reason),
);

/// A backend that stops only when told to, like the native adapter: it is
/// blocked inside its own compile call and cannot be preempted.
class _BlockedTransport
    implements RustAnalysisTransport, RustAnalysisCancellation {
  final release = Completer<RustAnalysisOutput>();
  int cancels = 0;
  RustAnalysisJob? job;

  bool get cancelRequested => cancels > 0;

  @override
  Future<RustAnalysisOutput> analyze(RustAnalysisJob job) {
    this.job = job;
    // Never completes on its own: the analyzer's bound must not wait for it.
    return release.future;
  }

  @override
  Future<void> cancel() async {
    cancels++;
  }
}

/// Pumps the event queue until [condition] holds, so a test never depends on
/// incidental timing order between the deferred cleanup and the assertion.
Future<void> _eventually(bool Function() condition) async {
  for (var attempt = 0; attempt < 200; attempt++) {
    if (condition()) return;
    await Future<void>.delayed(const Duration(milliseconds: 10));
  }
  fail('condition was never satisfied');
}

class _Session implements NativeMiriAnalysisSession {
  _Session({
    this.accepted = 0,
    this.value = const NativeMiriAnalysisResult(state: 2, exitCode: 0),
    this.diagnostics = const [],
    this.blocked = false,
    this.failure,
  });

  final int accepted;
  final NativeMiriAnalysisResult value;
  final List<int> diagnostics;
  final bool blocked;
  final Object? failure;
  final List<String> events = [];
  final started = Completer<void>();
  final cancelled = Completer<void>();
  final release = Completer<void>();
  bool running = false;

  @override
  Future<int> analyze() async {
    running = true;
    events.add('analyze-start');
    started.complete();
    try {
      if (blocked) await release.future;
      if (failure != null) throw failure!;
      return accepted;
    } finally {
      running = false;
      events.add('analyze-end');
    }
  }

  @override
  void cancel() {
    events.add('cancel');
    if (!cancelled.isCompleted) cancelled.complete();
  }

  @override
  NativeMiriAnalysisResult result() {
    events.add('result');
    return value;
  }

  @override
  List<int> readDiagnostics(int maxBytes) {
    events.add('diagnostics');
    return diagnostics;
  }

  @override
  void destroy() {
    if (running) throw StateError('Destroyed an active native call');
    events.add('destroy');
  }
}
