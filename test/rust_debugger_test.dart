import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;
import 'package:qfli_rust/native_miri_assets.dart';
import 'package:qfli_rust/rust_debugger.dart';
import 'package:qfli_studio_core/services/code_analysis.dart';
import 'package:qfli_studio_core/services/debug_session.dart';

void main() {
  late Directory temporary;
  late Directory project;
  late String entry;
  late NativeMiriRuntime runtime;
  late _Handle handle;
  late _Backend backend;
  final sessions = <DebugSession>[];

  setUp(() {
    temporary = Directory.systemTemp.createTempSync('qfli_debugger_test_');
    project = Directory(p.join(temporary.path, 'project'))..createSync();
    entry = p.join(project.path, 'main.rs');
    File(
      entry,
    ).writeAsStringSync('fn main() {\r\n    let answer = 42;\r\n}\r\n');
    final sysroot = Directory(p.join(temporary.path, 'sysroot'))..createSync();
    runtime = NativeMiriRuntime(
      target: const NativeMiriTarget(platform: 'ohos', architecture: 'x64'),
      nativeHost: 'x86_64-unknown-linux-ohos',
      sysrootPath: sysroot.path,
      libraryPath: p.join(temporary.path, 'not-an-installed-library'),
    );
    handle = _Handle(entry);
    backend = _Backend(handle);
  });

  tearDown(() async {
    handle.releaseAll();
    for (final session in sessions) {
      await session.dispose();
    }
    sessions.clear();
    temporary.deleteSync(recursive: true);
  });

  RustDebugger debugger({
    int? maxFrames,
    int? maxLocals,
    int? maxStringBytes,
    int? maxOutputBytes,
  }) => RustDebugger(
    backend: backend,
    prepareRuntime: () async => runtime,
    pollInterval: const Duration(milliseconds: 2),
    maxFrames: maxFrames ?? 128,
    maxLocals: maxLocals ?? 128,
    maxStringBytes: maxStringBytes ?? 4096,
    maxOutputBytes: maxOutputBytes ?? 1024 * 1024,
  );

  DebugLaunchRequest request({
    String? root,
    String? source,
    String language = 'rust',
    List<CodeDocumentSnapshot> documents = const [],
    List<DebugBreakpoint> breakpoints = const [],
    bool stopOnEntry = true,
  }) => DebugLaunchRequest(
    projectPath: root ?? project.path,
    entryFilePath: source ?? entry,
    language: language,
    documents: documents,
    breakpoints: breakpoints,
    stopOnEntry: stopOnEntry,
  );

  Future<DebugSession> launch({
    RustDebugger? provider,
    DebugLaunchRequest? launchRequest,
  }) async {
    final session = await (provider ?? debugger()).launch(
      launchRequest ?? request(),
    );
    sessions.add(session);
    return session;
  }

  test(
    'advertises discovered native capabilities and launch-only breakpoints',
    () {
      final provider = debugger();
      expect(provider.supportsLanguage('RUST'), isTrue);
      expect(provider.supportsLanguage('c++'), isFalse);
      final capabilities = provider.capabilities;
      expect(capabilities.breakpointUpdate, DebugBreakpointUpdate.launchOnly);
      expect(capabilities.outputDelivery, DebugOutputDelivery.live);
      expect(capabilities.supportsDocumentSnapshots, isFalse);
      expect(capabilities.supportsPause, isTrue);
      expect(capabilities.supportsStepInto, isTrue);
      expect(capabilities.supportsStepOver, isTrue);
      expect(capabilities.supportsStepOut, isTrue);
      expect(capabilities.supportsStackFrames, isTrue);
      expect(capabilities.supportsVariables, isTrue);
    },
  );

  test(
    'missing optional library exposes no controls and never executes Run',
    () async {
      var prepared = false;
      final provider = RustDebugger(
        libraryPath: p.join(temporary.path, 'missing-debug-library'),
        prepareRuntime: () async {
          prepared = true;
          return runtime;
        },
      );
      expect(provider.capabilities.supportsPause, isFalse);
      expect(provider.capabilities.supportsStepInto, isFalse);
      expect(provider.capabilities.supportsStackFrames, isFalse);
      await expectLater(provider.launch(request()), throwsA(anything));
      expect(prepared, isFalse);
      expect(backend.created, 0);
    },
  );

  test(
    'rejects unsaved snapshots before preparing or creating a worker',
    () async {
      await expectLater(
        debugger().launch(
          request(
            documents: [
              CodeDocumentSnapshot(
                path: entry,
                text: 'fn main() { panic!(); }',
                revision: 7,
              ),
            ],
          ),
        ),
        throwsA(isA<UnsupportedError>()),
      );
      expect(backend.created, 0);
      expect(handle.events, isEmpty);
      expect(File(entry).readAsStringSync(), contains('answer = 42'));
    },
  );

  test(
    'rejects foreign entry and breakpoint paths before native creation',
    () async {
      final foreign = File(p.join(temporary.path, 'foreign.rs'))
        ..writeAsStringSync('fn main() {}');
      await expectLater(
        debugger().launch(request(source: foreign.path)),
        throwsStateError,
      );
      await expectLater(
        debugger().launch(
          request(
            breakpoints: [DebugBreakpoint(filePath: foreign.path, line: 1)],
          ),
        ),
        throwsStateError,
      );
      expect(backend.created, 0);
    },
  );

  test('rejects project-local symlink escape before native creation', () async {
    final foreign = File(p.join(temporary.path, 'foreign.rs'))
      ..writeAsStringSync('fn main() {}');
    final link = Link(p.join(project.path, 'alias.rs'));
    // Windows file symlinks require Developer Mode or an elevated token. The
    // canonical containment contract is exercised on every capable host.
    try {
      link.createSync(foreign.path);
    } on FileSystemException {
      return;
    }
    await expectLater(
      debugger().launch(request(source: link.path)),
      throwsStateError,
    );
    expect(backend.created, 0);
  });

  test(
    'rechecks path identity after asynchronous runtime preparation',
    () async {
      final ready = Completer<NativeMiriRuntime>();
      final preparing = Completer<void>();
      final provider = RustDebugger(
        backend: backend,
        prepareRuntime: () {
          preparing.complete();
          return ready.future;
        },
      );
      final future = provider.launch(request());
      final checked = expectLater(future, throwsA(anything));
      await preparing.future;
      File(entry).deleteSync();
      ready.complete(runtime);
      await checked;
      expect(backend.created, 0);
    },
  );

  test(
    'reads manifest edition and installs exact launch breakpoints',
    () async {
      File(p.join(project.path, 'Cargo.toml')).writeAsStringSync('''
[package]
name = "debug_fixture"
edition = '2024' # exact project edition
''');
      final session = await launch(
        launchRequest: request(
          breakpoints: [DebugBreakpoint(filePath: entry, line: 2)],
        ),
      );
      await _until(() => session.snapshot.phase == DebugPhase.paused);
      expect(backend.configuration!.edition, 2024);
      expect(
        backend.configuration!.entryPath,
        File(entry).resolveSymbolicLinksSync(),
      );
      expect(backend.configuration!.breakpoints.single.line, 2);
      expect(
        session.snapshot.breakpoints.single.status,
        DebugBreakpointStatus.pending,
      );
      expect(handle.events, contains('start'));
    },
  );

  test(
    'workspace-inherited edition is unavailable instead of guessed',
    () async {
      File(
        p.join(project.path, 'Cargo.toml'),
      ).writeAsStringSync('[package]\nedition.workspace = true\n');
      await expectLater(
        debugger().launch(request()),
        throwsA(isA<UnsupportedError>()),
      );
      expect(backend.created, 0);
    },
  );

  test(
    'reports actual paused stack/scalars and unavailable aggregates',
    () async {
      handle.stack = [
        NativeMiriDebugFrame(
          index: 0,
          path: entry,
          line: 2,
          column: 5,
          function: 'fixture::main',
          totalLocals: 3,
          locals: const [
            NativeMiriDebugLocal(
              name: 'answer',
              type: 'u128',
              value: '340282366920938463463374607431768211455',
              state: 0,
            ),
            NativeMiriDebugLocal(
              name: 'future',
              type: 'i32',
              value: 'invented',
              state: 1,
            ),
            NativeMiriDebugLocal(
              name: 'items',
              type: 'Vec<u8>',
              value: 'invented',
              state: 2,
            ),
          ],
        ),
      ];
      final session = await launch();
      await _until(() => session.snapshot.phase == DebugPhase.paused);
      final snapshot = session.snapshot;
      expect(snapshot.pauseToken!.sessionId, session.id);
      expect(snapshot.pauseToken!.generation, 1);
      expect(snapshot.threads.single.id, 'active');
      final frame = snapshot.frames.single;
      expect(frame.location!.filePath, File(entry).resolveSymbolicLinksSync());
      expect(frame.name, 'fixture::main');
      expect(frame.locals[0].value, '340282366920938463463374607431768211455');
      expect(frame.locals[1].value, isEmpty);
      expect(frame.locals[1].unavailableReason, contains('初始化'));
      expect(frame.locals[2].value, isEmpty);
      expect(frame.locals[2].unavailableReason, contains('无法显示'));
    },
  );

  test(
    'maps scalar columns to UTF-16 columns without changing CRLF source',
    () async {
      const text = 'fn main() {\r\n    let _ = "😀中"; let bad = 1;\r\n}\r\n';
      File(entry).writeAsBytesSync(utf8.encode(text));
      final line = text.split('\r\n')[1];
      final utf16Column = line.indexOf('bad') + 1;
      final scalarColumn =
          line.substring(0, line.indexOf('bad')).runes.length + 1;
      handle.stack = [
        NativeMiriDebugFrame(
          index: 0,
          path: entry,
          line: 2,
          column: scalarColumn,
          function: 'main',
        ),
      ];
      final session = await launch();
      await _until(() => session.snapshot.phase == DebugPhase.paused);
      expect(session.snapshot.frames.single.location!.column, utf16Column);
      expect(File(entry).readAsBytesSync(), utf8.encode(text));
    },
  );

  test(
    'keeps real runtime/foreign frames without navigable project paths',
    () async {
      final foreign = File(p.join(temporary.path, 'stdlib.rs'))
        ..writeAsStringSync('fn runtime() {}');
      handle.stack = [
        NativeMiriDebugFrame(
          index: 0,
          path: foreign.path,
          line: 1,
          column: 1,
          function: 'std::rt::lang_start',
        ),
      ];
      final session = await launch();
      await _until(() => session.snapshot.phase == DebugPhase.paused);
      expect(session.snapshot.frames.single.name, 'std::rt::lang_start');
      expect(session.snapshot.frames.single.location, isNull);
    },
  );

  test(
    'later disk edits cannot change compiled-source UTF-16 columns',
    () async {
      const original =
          'fn main() {\r\n    let _ = "😀中"; let answer = 42;\r\n}\r\n';
      File(entry).writeAsBytesSync(utf8.encode(original));
      final line = original.split('\r\n')[1];
      final expectedColumn = line.indexOf('answer') + 1;
      final scalarColumn =
          line.substring(0, line.indexOf('answer')).runes.length + 1;
      handle.stack = [
        NativeMiriDebugFrame(
          index: 0,
          path: entry,
          line: 2,
          column: scalarColumn,
          function: 'main',
        ),
      ];
      final session = await launch();
      await _until(() => session.snapshot.phase == DebugPhase.paused);
      await session.command(
        DebugCommand.stepInto,
        pauseToken: session.snapshot.pauseToken,
      );
      File(entry).writeAsStringSync(
        'fn main() {\n    let _ = "ascii"; let answer = 42;\n}\n',
      );
      handle.reachPause(line: 2);
      await _until(() => session.snapshot.phase == DebugPhase.paused);
      expect(session.snapshot.frames.single.location!.column, expectedColumn);
    },
  );

  test('bounds frames, locals and strings and exposes lost data', () async {
    handle.frameTotal = 1000;
    handle.stack = [
      NativeMiriDebugFrame(
        index: 0,
        path: entry,
        line: 1,
        column: 1,
        function: 'long-function-name',
        totalLocals: 99,
        locals: const [
          NativeMiriDebugLocal(
            name: 'long-local-name',
            type: 'VeryLongType',
            value: '12345678901234567890',
            state: 0,
          ),
          NativeMiriDebugLocal(
            name: 'second',
            type: 'i32',
            value: '2',
            state: 0,
          ),
        ],
      ),
      NativeMiriDebugFrame(
        index: 1,
        path: entry,
        line: 1,
        column: 1,
        function: 'caller',
      ),
    ];
    final session = await launch(
      provider: debugger(maxFrames: 1, maxLocals: 1, maxStringBytes: 8),
    );
    await _until(() => session.snapshot.phase == DebugPhase.paused);
    expect(session.snapshot.frames, hasLength(1));
    expect(session.snapshot.framesTruncated, isTrue);
    final frame = session.snapshot.frames.single;
    expect(frame.name.length, 8);
    expect(frame.locals, hasLength(1));
    expect(frame.localsTruncated, isTrue);
    expect(frame.locals.single.truncated, isTrue);
    expect(frame.locals.single.value.length, 8);
  });

  test(
    'CJK and non-BMP strings use UTF-8 byte bounds and mark omitted content',
    () async {
      handle.stack = [
        NativeMiriDebugFrame(
          index: 0,
          path: entry,
          line: 1,
          column: 1,
          function: '中😀文',
          totalLocals: 1,
          locals: const [
            NativeMiriDebugLocal(
              name: '变量😀',
              type: '𐐷类型',
              value: '😀😀',
              state: 0,
            ),
          ],
        ),
      ];
      final session = await launch(provider: debugger(maxStringBytes: 6));
      await _until(() => session.snapshot.phase == DebugPhase.paused);
      final frame = session.snapshot.frames.single;
      expect(frame.name, '中');
      expect(session.snapshot.framesTruncated, isTrue);
      expect(frame.localsTruncated, isFalse);
      final local = frame.locals.single;
      expect(local.name, '变量');
      expect(local.type, '𐐷');
      expect(local.value, '😀');
      expect(local.truncated, isTrue);
      for (final text in [frame.name, local.name, local.type, local.value]) {
        _expectUtf8Bound(text, 6);
      }
    },
  );

  test(
    'a scalar exactly at the UTF-8 byte bound is retained without truncation',
    () async {
      handle.stack = [
        NativeMiriDebugFrame(
          index: 0,
          path: entry,
          line: 1,
          column: 1,
          function: '中😀',
          totalLocals: 1,
          locals: const [
            NativeMiriDebugLocal(
              name: '中😀',
              type: '中😀',
              value: '中😀',
              state: 0,
            ),
          ],
        ),
      ];
      final session = await launch(provider: debugger(maxStringBytes: 7));
      await _until(() => session.snapshot.phase == DebugPhase.paused);
      final frame = session.snapshot.frames.single;
      expect(frame.name, '中😀');
      expect(frame.locals.single.value, '中😀');
      expect(frame.locals.single.truncated, isFalse);
      expect(session.snapshot.framesTruncated, isFalse);
    },
  );

  test(
    'a byte bound inside a surrogate pair omits the entire scalar',
    () async {
      handle.stack = [
        NativeMiriDebugFrame(
          index: 0,
          path: entry,
          line: 1,
          column: 1,
          function: 'a😀b',
          totalLocals: 1,
          locals: const [
            NativeMiriDebugLocal(
              name: 'a😀b',
              type: '😀',
              value: 'a😀b',
              state: 0,
            ),
          ],
        ),
      ];
      final session = await launch(provider: debugger(maxStringBytes: 2));
      await _until(() => session.snapshot.phase == DebugPhase.paused);
      final frame = session.snapshot.frames.single;
      final local = frame.locals.single;
      expect(frame.name, 'a');
      expect(local.name, 'a');
      expect(local.type, isEmpty);
      expect(local.value, 'a');
      expect(local.truncated, isTrue);
      expect(session.snapshot.framesTruncated, isTrue);
      for (final text in [frame.name, local.name, local.type, local.value]) {
        _expectUtf8Bound(text, 2);
      }
    },
  );

  test(
    'CJK and non-BMP diagnostic messages have a bounded visible truncation marker',
    () async {
      handle.startFailure = true;
      const diagnostic = '中😀文错误：类型不匹配';
      handle.outputs[2] = utf8.encode(diagnostic);
      final session = await launch(provider: debugger(maxStringBytes: 9));
      await session.done;
      expect(session.snapshot.phase, DebugPhase.failed);
      expect(session.snapshot.message, '中…');
      expect(session.snapshot.console, diagnostic);
      expect(session.snapshot.consoleTruncated, isTrue);
      expect(session.snapshot.stdoutTruncated, isFalse);
      expect(session.snapshot.stderrTruncated, isFalse);
      _expectUtf8Bound(session.snapshot.message!, 9);
    },
  );

  test(
    'a tiny diagnostic byte bound still produces a valid nonempty failure message',
    () async {
      handle.startFailure = true;
      handle.outputs[2] = utf8.encode('😀错误');
      final session = await launch(provider: debugger(maxStringBytes: 1));
      await session.done;
      expect(session.snapshot.message, '.');
      expect(session.snapshot.consoleTruncated, isTrue);
      _expectUtf8Bound(session.snapshot.message!, 1);
    },
  );

  test(
    'transport error messages are bounded after adding their diagnostic prefix',
    () async {
      handle.frameReadError = StateError('中😀文' * 100);
      final session = await launch(provider: debugger(maxStringBytes: 16));
      await session.done;
      expect(session.snapshot.phase, DebugPhase.failed);
      expect(session.snapshot.message, endsWith('…'));
      expect(session.snapshot.consoleTruncated, isTrue);
      _expectUtf8Bound(session.snapshot.message!, 16);
    },
  );

  test(
    'an output byte bound drops a partial scalar and flags only the affected channel',
    () async {
      handle.outputs[0] = utf8.encode('${'a' * 1023}😀');
      final session = await launch(provider: debugger(maxOutputBytes: 1024));
      await _until(() => session.snapshot.phase == DebugPhase.paused);
      expect(session.snapshot.stdout, 'a' * 1023);
      expect(session.snapshot.stdoutTruncated, isTrue);
      expect(session.snapshot.stderrTruncated, isFalse);
      expect(session.snapshot.consoleTruncated, isFalse);
      _expectUtf8Bound(session.snapshot.stdout, 1024);
    },
  );

  test(
    'an incomplete live UTF-8 scalar is deferred until its remaining bytes arrive',
    () async {
      final session = await launch();
      await _until(() => session.snapshot.phase == DebugPhase.paused);
      await session.command(
        DebugCommand.resume,
        pauseToken: session.snapshot.pauseToken,
      );
      final encoded = utf8.encode('x😀');
      handle.outputs[0] = encoded.sublist(0, 3);
      handle.revision++;
      await _until(() => session.snapshot.stdout == 'x');
      expect(session.snapshot.stdoutTruncated, isFalse);
      expect(session.snapshot.stdout, isNot(contains('\ufffd')));
      handle.outputs[0] = encoded;
      handle.revision++;
      await _until(() => session.snapshot.stdout == 'x😀');
      expect(session.snapshot.stdoutTruncated, isFalse);
      _expectUtf8Bound(session.snapshot.stdout, 1024 * 1024);
    },
  );

  test(
    'malformed UTF-8 marks lost bytes while valid replacement text stays intact',
    () async {
      handle.outputs[0] = [0xff, 0x61];
      handle.outputs[1] = utf8.encode('\ufffd');
      final session = await launch();
      await _until(() => session.snapshot.phase == DebugPhase.paused);
      expect(session.snapshot.stdout, '\ufffda');
      expect(session.snapshot.stdoutTruncated, isTrue);
      expect(session.snapshot.stderr, '\ufffd');
      expect(session.snapshot.stderrTruncated, isFalse);
      expect(session.snapshot.consoleTruncated, isFalse);

      // A final incomplete scalar is lost data; live output may defer it.
      handle.outputs[2] = [0xf0, 0x9f];
      handle.terminate(0);
      await session.done;
      expect(session.snapshot.console, contains('\ufffd'));
      expect(session.snapshot.consoleTruncated, isTrue);
      expect(session.snapshot.stdoutTruncated, isTrue);
      expect(session.snapshot.stderrTruncated, isFalse);
      _expectUtf8Bound(session.snapshot.console, 1024 * 1024);
    },
  );

  test(
    'breakpoint becomes verified only at a matching real current frame',
    () async {
      final session = await launch(
        launchRequest: request(
          breakpoints: [DebugBreakpoint(filePath: entry, line: 2)],
        ),
      );
      await _until(() => session.snapshot.phase == DebugPhase.paused);
      expect(
        session.snapshot.breakpoints.single.status,
        DebugBreakpointStatus.pending,
      );
      await session.command(
        DebugCommand.resume,
        pauseToken: session.snapshot.pauseToken,
      );
      handle.reachPause(line: 2, reason: 1);
      await _until(() => session.snapshot.phase == DebugPhase.paused);
      final point = session.snapshot.breakpoints.single;
      expect(point.status, DebugBreakpointStatus.verified);
      expect(point.actualLocation!.line, 2);
      expect(point.actualLocation!.filePath, entry);
    },
  );

  test(
    'auto-continues initial pause only when stop-on-entry was not requested',
    () async {
      final session = await launch(launchRequest: request(stopOnEntry: false));
      await _until(
        () => handle.events.any((event) => event.startsWith('resume:')),
      );
      expect(session.snapshot.phase, DebugPhase.running);
      expect(session.snapshot.pauseToken, isNull);
      expect(session.snapshot.frames, isEmpty);
      expect(handle.events, contains('resume:0:1'));
    },
  );

  test(
    'does not auto-continue past a breakpoint at the real entry location',
    () async {
      final session = await launch(
        launchRequest: request(
          stopOnEntry: false,
          breakpoints: [DebugBreakpoint(filePath: entry, line: 1)],
        ),
      );
      await _until(() => session.snapshot.phase == DebugPhase.paused);
      expect(
        handle.events.where((event) => event.startsWith('resume:')),
        isEmpty,
      );
      expect(
        session.snapshot.breakpoints.single.status,
        DebugBreakpointStatus.verified,
      );
    },
  );

  for (final command in [
    DebugCommand.resume,
    DebugCommand.stepInto,
    DebugCommand.stepOver,
    DebugCommand.stepOut,
  ]) {
    test(
      '$command dispatches without waiting for the next pause and invalidates old token',
      () async {
        final session = await launch();
        await _until(() => session.snapshot.phase == DebugPhase.paused);
        final token = session.snapshot.pauseToken!;
        await session.command(command, pauseToken: token, threadId: 'active');
        expect(session.snapshot.phase, DebugPhase.running);
        expect(session.snapshot.frames, isEmpty);
        expect(session.snapshot.pauseToken, isNull);
        expect(handle.resumePending, isTrue);
        await expectLater(
          session.command(DebugCommand.resume, pauseToken: token),
          throwsStateError,
        );
        handle.reachPause(line: 2);
        await _until(() => session.snapshot.phase == DebugPhase.paused);
        expect(session.snapshot.pauseToken!.generation, 2);
        await expectLater(
          session.command(DebugCommand.resume, pauseToken: token),
          throwsStateError,
        );
        final mode = [
          DebugCommand.resume,
          DebugCommand.stepInto,
          DebugCommand.stepOver,
          DebugCommand.stepOut,
        ].indexOf(command);
        expect(handle.events.where((event) => event.startsWith('resume:')), [
          'resume:$mode:1',
        ]);
      },
    );
  }

  test(
    'rejects foreign session tokens and unknown threads without advancing',
    () async {
      final session = await launch();
      await _until(() => session.snapshot.phase == DebugPhase.paused);
      await expectLater(
        session.command(
          DebugCommand.resume,
          pauseToken: const DebugPauseToken(
            sessionId: 'foreign',
            generation: 1,
          ),
        ),
        throwsStateError,
      );
      await expectLater(
        session.command(
          DebugCommand.resume,
          pauseToken: session.snapshot.pauseToken,
          threadId: 'invented',
        ),
        throwsStateError,
      );
      expect(
        handle.events.where((event) => event.startsWith('resume:')),
        isEmpty,
      );
      expect(session.snapshot.phase, DebugPhase.paused);
    },
  );

  test(
    'unsupported step capability rejects command without resuming',
    () async {
      backend.bits &= ~8;
      final session = await launch();
      await _until(() => session.snapshot.phase == DebugPhase.paused);
      await expectLater(
        session.command(
          DebugCommand.stepOut,
          pauseToken: session.snapshot.pauseToken,
        ),
        throwsA(isA<UnsupportedError>()),
      );
      expect(
        handle.events.where((event) => event.startsWith('resume:')),
        isEmpty,
      );
    },
  );

  test(
    'launch-only breakpoint updates cannot silently mutate installed points',
    () async {
      final session = await launch();
      await _until(() => session.snapshot.phase == DebugPhase.paused);
      await expectLater(
        session.setBreakpoints([DebugBreakpoint(filePath: entry, line: 2)]),
        throwsA(isA<UnsupportedError>()),
      );
      expect(session.snapshot.breakpoints, isEmpty);
      expect(backend.configuration!.breakpoints, isEmpty);
    },
  );

  test(
    'live output replaces retained buffers and advances snapshot revisions',
    () async {
      final session = await launch();
      await _until(() => session.snapshot.phase == DebugPhase.paused);
      final revisions = <int>[];
      final subscription = session.updates.listen((snapshot) {
        expect(
          session.snapshot.revision,
          greaterThanOrEqualTo(snapshot.revision),
        );
        revisions.add(snapshot.revision);
      });
      await session.command(
        DebugCommand.resume,
        pauseToken: session.snapshot.pauseToken,
      );
      handle.outputs[0] = utf8.encode('first 😀\n');
      handle.revision++;
      await _until(() => session.snapshot.stdout == 'first 😀\n');
      final firstRevision = session.snapshot.revision;
      handle.outputs[0] = utf8.encode('first 😀\nsecond\n');
      handle.outputs[1] = utf8.encode('actual stderr');
      handle.outputs[2] = utf8.encode('actual diagnostics');
      handle.revision++;
      await _until(() => session.snapshot.stdout.endsWith('second\n'));
      expect(session.snapshot.stdout, 'first 😀\nsecond\n');
      expect(session.snapshot.stderr, 'actual stderr');
      expect(session.snapshot.console, 'actual diagnostics');
      expect(session.snapshot.revision, greaterThan(firstRevision));
      expect(revisions.toSet().length, revisions.length);
      expect(revisions, orderedEquals([...revisions]..sort()));
      await subscription.cancel();
    },
  );

  test('pause remains usable while resume waits in native worker', () async {
    final session = await launch();
    await _until(() => session.snapshot.phase == DebugPhase.paused);
    await session.command(
      DebugCommand.resume,
      pauseToken: session.snapshot.pauseToken,
    );
    await session.command(DebugCommand.pause);
    await _until(() => session.snapshot.phase == DebugPhase.paused);
    expect(handle.events, contains('pause'));
    expect(session.snapshot.pauseToken!.generation, 2);
  });

  test(
    'stop waits for active call, OS worker join and destruction before terminal',
    () async {
      handle.cancelCompletesWorker = false;
      handle.joinGate = Completer<void>();
      handle.destroyGate = Completer<void>();
      final session = await launch();
      await _until(() => session.snapshot.phase == DebugPhase.paused);
      await session.command(
        DebugCommand.resume,
        pauseToken: session.snapshot.pauseToken,
      );
      var done = false;
      unawaited(session.done.then((_) => done = true));
      final stopped = session.stop();
      await _until(() => handle.events.contains('cancel'));
      expect(done, isFalse);
      expect(session.snapshot.isTerminal, isFalse);
      expect(handle.events, isNot(contains('wait')));
      handle.terminate(130, reason: 7);
      await _until(() => handle.events.contains('wait'));
      expect(done, isFalse);
      expect(handle.events, isNot(contains('destroy-start')));
      handle.joinGate!.complete();
      await _until(() => handle.events.contains('destroy-start'));
      expect(done, isFalse);
      expect(session.snapshot.isTerminal, isFalse);
      handle.destroyGate!.complete();
      await stopped;
      await session.done;
      expect(done, isTrue);
      expect(session.snapshot.phase, DebugPhase.terminated);
      expect(session.snapshot.exitCode, 130);
      expect(handle.events.last, 'destroy-end');
      expect(session.snapshot.frames, isEmpty);
      await session.stop();
      expect(
        handle.events.where((event) => event == 'destroy-start'),
        hasLength(1),
      );
    },
  );

  test(
    'stop during compiler start retains resources until start actually returns',
    () async {
      handle.startGate = Completer<void>();
      handle.cancelCompletesWorker = false;
      final session = await launch();
      await handle.startCalled.future;
      var stopped = false;
      final stopping = session.stop().then((_) => stopped = true);
      await _until(() => handle.events.contains('cancel'));
      expect(stopped, isFalse);
      expect(handle.events, isNot(contains('destroy-start')));
      handle.startGate!.complete();
      await stopping;
      expect(session.snapshot.exitCode, 130);
      expect(
        handle.events.indexOf('start-return'),
        lessThan(handle.events.indexOf('wait')),
      );
      expect(handle.events.last, 'destroy-end');
    },
  );

  test(
    'compiler busy destroys idle handle without wait or fabricated exit',
    () async {
      handle.busy = true;
      final session = await launch();
      await session.done;
      expect(session.snapshot.phase, DebugPhase.failed);
      expect(session.snapshot.message, contains('占用'));
      expect(session.snapshot.exitCode, isNull);
      expect(handle.events, isNot(contains('wait')));
      expect(handle.events.last, 'destroy-end');
    },
  );

  test(
    'compiler failure retains real diagnostics and waits before releasing session',
    () async {
      handle.startFailure = true;
      handle.outputs[2] = utf8.encode('error[E0308]: mismatched types');
      final session = await launch();
      await session.done;
      expect(session.snapshot.phase, DebugPhase.failed);
      expect(session.snapshot.console, contains('E0308'));
      expect(session.snapshot.message, contains('E0308'));
      expect(session.snapshot.exitCode, 1);
      expect(
        handle.events.indexOf('wait'),
        lessThan(handle.events.indexOf('destroy-start')),
      );
    },
  );

  test('natural exit preserves real nonzero program status', () async {
    final session = await launch();
    await _until(() => session.snapshot.phase == DebugPhase.paused);
    await session.command(
      DebugCommand.resume,
      pauseToken: session.snapshot.pauseToken,
    );
    handle.terminate(17);
    await session.done;
    expect(session.snapshot.phase, DebugPhase.terminated);
    expect(session.snapshot.exitCode, 17);
  });

  test(
    'pause timeout invalidates frames and yields actual limit status',
    () async {
      final session = await launch();
      await _until(() => session.snapshot.phase == DebugPhase.paused);
      final old = session.snapshot.pauseToken;
      handle.terminate(124, reason: 6);
      await session.done;
      expect(session.snapshot.exitCode, 124);
      expect(session.snapshot.pauseToken, isNull);
      expect(session.snapshot.frames, isEmpty);
      await expectLater(
        session.command(DebugCommand.resume, pauseToken: old),
        throwsStateError,
      );
    },
  );

  test(
    'cleanup rejection keeps done and terminal unproven until retry succeeds',
    () async {
      final session = await launch();
      await _until(() => session.snapshot.phase == DebugPhase.paused);
      handle.waitResult = -1;
      var completed = false;
      unawaited(session.done.then((_) => completed = true));
      await expectLater(session.stop(), throwsStateError);
      expect(completed, isFalse);
      expect(session.snapshot.isTerminal, isFalse);
      expect(handle.events, isNot(contains('destroy-start')));
      handle.waitResult = 0;
      await session.stop();
      expect(completed, isTrue);
      expect(session.snapshot.isTerminal, isTrue);
    },
  );

  test(
    'dispose waits for cleanup then closes broadcast snapshots exactly once',
    () async {
      final session = await launch();
      await _until(() => session.snapshot.phase == DebugPhase.paused);
      final closed = Completer<void>();
      final subscription = session.updates.listen(
        (_) {},
        onDone: closed.complete,
      );
      await Future.wait([session.dispose(), session.dispose()]);
      await closed.future;
      expect(
        handle.events.where((event) => event == 'destroy-start'),
        hasLength(1),
      );
      await subscription.cancel();
    },
  );
}

Future<void> _until(bool Function() condition) async {
  final deadline = DateTime.now().add(const Duration(seconds: 3));
  while (!condition()) {
    if (DateTime.now().isAfter(deadline)) {
      fail('Timed out waiting for an observable debugger transition');
    }
    await Future<void>.delayed(const Duration(milliseconds: 2));
  }
}

void _expectUtf8Bound(String text, int maxBytes) {
  final bytes = utf8.encode(text);
  expect(bytes.length, lessThanOrEqualTo(maxBytes));
  // Round-tripping replaces an unpaired surrogate, so equality also proves the
  // bound did not leave half of a non-BMP UTF-16 pair in the displayed text.
  expect(utf8.decode(bytes), text);
}

class _Backend implements NativeMiriDebugBackend {
  _Backend(this.handle);
  final _Handle handle;
  int bits = 0x1ff;
  int created = 0;
  NativeMiriDebugLaunch? configuration;

  @override
  int get capabilityBits => bits;
  @override
  NativeMiriDebugHandle create(
    NativeMiriRuntime runtime,
    NativeMiriDebugLaunch configuration,
  ) {
    created++;
    this.configuration = configuration;
    return handle;
  }
}

class _Handle implements NativeMiriDebugHandle {
  _Handle(String path)
    : stack = [
        NativeMiriDebugFrame(
          index: 0,
          path: path,
          line: 1,
          column: 1,
          function: 'fixture::main',
        ),
      ];
  final events = <String>[];
  final startCalled = Completer<void>();
  Completer<void>? startGate;
  Completer<void>? joinGate;
  Completer<void>? destroyGate;
  Completer<int>? _resume;
  final outputs = <List<int>>[[], [], []];
  List<NativeMiriDebugFrame> stack;
  int? frameTotal;
  int state = 0;
  int revision = 0;
  int generation = 0;
  bool workerExited = false;
  bool busy = false;
  bool startFailure = false;
  bool cancelCompletesWorker = true;
  bool cancelled = false;
  int reason = 0;
  int exitCode = 0;
  int waitResult = 0;
  Object? frameReadError;

  bool get resumePending => _resume != null && !_resume!.isCompleted;

  @override
  Future<int> start() async {
    events.add('start');
    state = 1;
    revision++;
    startCalled.complete();
    if (startGate != null) await startGate!.future;
    if (busy) {
      state = 0;
      workerExited = true;
    } else if (cancelled) {
      terminate(130, reason: 7);
    } else if (startFailure) {
      terminate(1, failed: true, reason: 5);
    } else {
      reachPause(line: stack.first.line, reason: 0);
    }
    events.add('start-return');
    return busy
        ? 2
        : startFailure
        ? -1
        : 0;
  }

  @override
  Future<int> resume(int mode, int generation) {
    if (state != 2 || generation != this.generation) return Future.value(-1);
    events.add('resume:$mode:$generation');
    state = 1;
    revision++;
    _resume = Completer<int>();
    return _resume!.future;
  }

  void reachPause({required int line, int reason = 2}) {
    state = 2;
    generation++;
    revision++;
    this.reason = reason;
    if (stack.isNotEmpty) {
      final previous = stack.first;
      stack = [
        NativeMiriDebugFrame(
          index: previous.index,
          path: previous.path,
          line: line,
          column: previous.column,
          function: previous.function,
          locals: previous.locals,
          totalLocals: previous.totalLocals,
          truncated: previous.truncated,
        ),
        ...stack.skip(1),
      ];
    }
    if (resumePending) _resume!.complete(0);
  }

  void terminate(int code, {int reason = 4, bool failed = false}) {
    state = failed ? 4 : 3;
    exitCode = code;
    this.reason = reason;
    workerExited = true;
    revision++;
    if (resumePending) _resume!.complete(failed ? -1 : 0);
  }

  @override
  NativeMiriDebugStatus status() => NativeMiriDebugStatus(
    state: state,
    workerExited: workerExited,
    generation: generation,
    revision: revision,
  );
  @override
  NativeMiriDebugPause pauseInfo() =>
      NativeMiriDebugPause(reason: reason, exitCode: exitCode);
  @override
  NativeMiriDebugFrames frames(
    int maxFrames,
    int maxLocals,
    int maxStringBytes,
  ) {
    final error = frameReadError;
    if (error != null) throw error;
    return NativeMiriDebugFrames(
      frames: stack,
      total: frameTotal ?? stack.length,
    );
  }

  @override
  List<int> output(int channel, int maxBytes) => List.of(outputs[channel]);
  @override
  void pause() {
    events.add('pause');
    reachPause(line: 2, reason: 3);
  }

  @override
  void cancel() {
    events.add('cancel');
    cancelled = true;
    if (state == 3 || state == 4 || state == 0) return;
    state = 5;
    revision++;
    if (cancelCompletesWorker &&
        (startGate == null || startGate!.isCompleted)) {
      terminate(130, reason: 7);
    }
  }

  @override
  Future<int> wait() async {
    events.add('wait');
    if (joinGate != null) await joinGate!.future;
    return waitResult;
  }

  @override
  Future<void> destroy() async {
    events.add('destroy-start');
    if (destroyGate != null) await destroyGate!.future;
    events.add('destroy-end');
  }

  void releaseAll() {
    if (startGate != null && !startGate!.isCompleted) startGate!.complete();
    if (joinGate != null && !joinGate!.isCompleted) joinGate!.complete();
    if (destroyGate != null && !destroyGate!.isCompleted) {
      destroyGate!.complete();
    }
    cancelCompletesWorker = true;
    if (resumePending) terminate(130, reason: 7);
  }
}
