import 'dart:async';
import 'dart:convert';
import 'dart:ffi';
import 'dart:io';
import 'dart:isolate';

import 'package:ffi/ffi.dart';
import 'package:path/path.dart' as p;
import 'package:qfli_studio_core/services/debug_session.dart';

import 'native_miri_assets.dart';

/// Real, optional Miri debugging. Loading an older runtime never falls back to
/// ordinary Run. Capabilities are discovered from the installed library before
/// controls are exposed; a missing extension has no advertised capabilities.
///
/// The editor saves before launching because this provider deliberately rejects
/// unsaved snapshots. Breakpoints are installed once, before the first native
/// instruction. Values are read-only native copies, never evaluated expressions.
class RustDebugger implements StudioDebugger {
  RustDebugger({
    this.libraryPath = 'libqfli_miri.so',
    Future<NativeMiriRuntime> Function()? prepareRuntime,
    NativeMiriDebugBackend? backend,
    this.timeout = const Duration(minutes: 10),
    this.maxSteps = 10000000,
    this.maxOutputBytes = 1024 * 1024,
    this.maxFrames = 128,
    this.maxLocals = 128,
    this.maxStringBytes = 4096,
    this.pollInterval = const Duration(milliseconds: 50),
    this.defaultEdition = 2021,
  }) : _prepareRuntime = prepareRuntime ?? prepareNativeMiriAssets,
       _backend = backend;

  final String libraryPath;
  final Future<NativeMiriRuntime> Function() _prepareRuntime;
  NativeMiriDebugBackend? _backend;
  final Duration timeout;
  final int maxSteps;
  final int maxOutputBytes;
  final int maxFrames;
  final int maxLocals;
  final int maxStringBytes;
  final Duration pollInterval;
  final int defaultEdition;
  int _nextSession = 0;

  @override
  String get displayName => 'Rust · Miri 离线调试';

  NativeMiriDebugBackend _loadBackend() =>
      _backend ??= _FfiDebugBackend(libraryPath);

  @override
  DebugCapabilities get capabilities {
    try {
      return _capabilities(_loadBackend().capabilityBits);
    } on Object {
      return const DebugCapabilities(
        breakpointUpdate: DebugBreakpointUpdate.launchOnly,
        outputDelivery: DebugOutputDelivery.exitOnly,
      );
    }
  }

  @override
  bool supportsLanguage(String language) => language.toLowerCase() == 'rust';

  @override
  Future<DebugSession> launch(DebugLaunchRequest request) async {
    if (!supportsLanguage(request.language)) {
      throw UnsupportedError('Rust 调试器只支持 Rust 源文件');
    }
    if (request.documents.isNotEmpty) {
      throw UnsupportedError('Rust 调试器需要先保存文件，不支持忽略未保存的源码快照');
    }
    if (timeout.inMilliseconds <= 0 ||
        maxSteps <= 0 ||
        maxOutputBytes < 1024 ||
        maxOutputBytes > 16 * 1024 * 1024 ||
        maxFrames <= 0 ||
        maxFrames > 512 ||
        maxLocals <= 0 ||
        maxLocals > 512 ||
        maxStringBytes <= 0 ||
        maxStringBytes > 64 * 1024 ||
        pollInterval.inMicroseconds <= 0 ||
        request.breakpoints.length > 1000 ||
        !_editions.contains(defaultEdition)) {
      throw StateError('Rust 调试资源限制无效');
    }
    _absolute(request.projectPath);
    final root = Directory(request.projectPath).resolveSymbolicLinksSync();
    final entry = _source(root, request.entryFilePath);
    if (p.extension(entry).toLowerCase() != '.rs') {
      throw StateError('Rust 调试入口必须是项目内的 .rs 文件');
    }
    final points = <DebugBreakpoint>[];
    for (final point in request.breakpoints) {
      if (point.line <= 0 || point.line > 0xffffffff) {
        throw StateError('Rust 断点行号无效');
      }
      points.add(
        DebugBreakpoint(
          filePath: _source(root, point.filePath),
          line: point.line,
        ),
      );
    }
    final backend = _loadBackend();
    final bits = backend.capabilityBits;
    // A non-generational implementation cannot uphold the frozen command
    // contract. All installed breakpoints must be real backend capabilities.
    if (bits & 256 == 0 || (points.isNotEmpty && bits & 1 == 0)) {
      throw UnsupportedError('当前 Rust 运行库不支持安全的暂停令牌或源码断点');
    }
    final runtime = await _prepareRuntime();
    if (backend is _FfiDebugBackend) backend.validateRuntime(runtime);
    _absolute(runtime.sysrootPath);
    if (!Directory(runtime.sysrootPath).existsSync()) {
      throw StateError('Rust 调试标准库目录不存在');
    }
    final backendPath = runtime.backendPath;
    if (backendPath != null) {
      _absolute(backendPath);
      if (!File(backendPath).existsSync()) {
        throw StateError('Rust 调试编译后端不存在');
      }
    }
    // Recheck after asynchronous preparation: replacing a symlink during
    // extraction must not redirect launch or a breakpoint outside this root.
    if (!_same(
          root,
          Directory(request.projectPath).resolveSymbolicLinksSync(),
        ) ||
        !_same(entry, _source(root, request.entryFilePath))) {
      throw StateError('Rust 调试源文件路径在启动前发生变化');
    }
    for (var i = 0; i < points.length; i++) {
      if (!_same(
        points[i].filePath,
        _source(root, request.breakpoints[i].filePath),
      )) {
        throw StateError('Rust 断点路径在启动前发生变化');
      }
    }
    final config = NativeMiriDebugLaunch(
      entryPath: entry,
      edition: _edition(root, defaultEdition),
      timeout: timeout,
      maxSteps: maxSteps,
      maxOutputBytes: maxOutputBytes,
      breakpoints: List.unmodifiable(points),
    );
    final sourceTexts = _captureSources(root);
    // create owns no running worker. If it fails, its backend must release any
    // partial handle. Once created, the session owns it through wait/destroy.
    final handle = backend.create(runtime, config);
    final session = _RustDebugSession(
      id: 'rust-miri-${DateTime.now().microsecondsSinceEpoch}-${_nextSession++}',
      owner: this,
      root: root,
      handle: handle,
      capabilities: _capabilities(bits),
      breakpoints: request.breakpoints,
      canonicalBreakpoints: points,
      sourceTexts: sourceTexts,
      stopOnEntry: request.stopOnEntry,
    );
    session.begin();
    return session;
  }
}

const _editions = {2015, 2018, 2021, 2024};

DebugCapabilities _capabilities(int bits) => DebugCapabilities(
  breakpointUpdate: DebugBreakpointUpdate.launchOnly,
  outputDelivery: bits & 128 != 0
      ? DebugOutputDelivery.live
      : DebugOutputDelivery.pauseOrExit,
  supportsPause: bits & 64 != 0,
  supportsStepInto: bits & 2 != 0,
  supportsStepOver: bits & 4 != 0,
  supportsStepOut: bits & 8 != 0,
  supportsStopOnEntry: true,
  supportsStackFrames: true,
  supportsVariables: bits & 16 != 0,
);

void _absolute(String path) {
  if (path.isEmpty || path.contains('\u0000') || !p.isAbsolute(path)) {
    throw StateError('Rust 调试需要有效的绝对路径');
  }
}

String _source(String root, String path) {
  _absolute(path);
  final normalized = p.normalize(path);
  if (!p.isWithin(root, normalized)) {
    throw StateError('Rust 调试源文件不在所属项目内');
  }
  final resolved = File(normalized).resolveSymbolicLinksSync();
  if (!p.isWithin(root, resolved) || !File(resolved).existsSync()) {
    throw StateError('Rust 调试源文件通过符号链接离开了项目');
  }
  return resolved;
}

bool _same(String a, String b) => p.equals(p.normalize(a), p.normalize(b));

String _key(String path) => Platform.isWindows ? path.toLowerCase() : path;

/// Compiler columns count Unicode scalars. Keep the source used at launch so
/// edits made after compilation cannot change the UTF-16 conversion at a pause.
/// This is bounded local capture, not support for unsaved editor documents.
Map<String, List<String>> _captureSources(String root) {
  const skipped = {
    '.git',
    'target',
    'build',
    '.dart_tool',
    '.gradle',
    'node_modules',
  };
  final pending = <Directory>[Directory(root)];
  final sources = <String, List<String>>{};
  var entries = 0;
  var bytes = 0;
  while (pending.isNotEmpty) {
    final directory = pending.removeLast();
    for (final entity in directory.listSync(followLinks: false)) {
      if (++entries > 8192) throw UnsupportedError('项目超出 Rust 调试源文件快照范围');
      if (entity is Directory) {
        if (!skipped.contains(p.basename(entity.path))) pending.add(entity);
        continue;
      }
      if (entity is! File || p.extension(entity.path).toLowerCase() != '.rs') {
        continue;
      }
      final path = _source(root, entity.path);
      if (sources.containsKey(_key(path))) continue;
      final file = File(path);
      bytes += file.lengthSync();
      if (sources.length >= 512 || bytes > 16 * 1024 * 1024) {
        throw UnsupportedError('项目超出 Rust 调试源文件快照范围');
      }
      final text = file.readAsStringSync();
      // Preserve physical lines, including a trailing empty line and CRLF.
      sources[_key(path)] = List.unmodifiable(
        text
            .split('\n')
            .map(
              (line) => line.endsWith('\r')
                  ? line.substring(0, line.length - 1)
                  : line,
            ),
      );
    }
  }
  return Map.unmodifiable(sources);
}

int _edition(String root, int fallback) {
  final manifest = File(p.join(root, 'Cargo.toml'));
  if (!manifest.existsSync()) return fallback;
  _source(root, manifest.path);
  if (manifest.lengthSync() > 128 * 1024) {
    throw UnsupportedError('Cargo 清单过大，无法确认 Rust 调试版本');
  }
  var package = false;
  for (final line in const LineSplitter().convert(
    manifest.readAsStringSync(),
  )) {
    final trimmed = line.trim();
    if (trimmed.startsWith('[')) {
      package = RegExp(r'^\[package\]\s*(?:#.*)?$').hasMatch(trimmed);
    }
    if (!package || !RegExp(r'^edition\b').hasMatch(trimmed)) continue;
    final value = RegExp(
      r'''^edition\s*=\s*["'](2015|2018|2021|2024)["']\s*(?:#.*)?$''',
    ).firstMatch(trimmed);
    if (value == null) {
      throw UnsupportedError('当前 Rust 调试器需要 Cargo.toml 中的显式 edition');
    }
    return int.parse(value[1]!);
  }
  return fallback;
}

/// Testable native boundary. The production implementation below performs real
/// FFI calls. No method in this contract may evaluate expressions for inspection.
abstract interface class NativeMiriDebugBackend {
  int get capabilityBits;
  NativeMiriDebugHandle create(
    NativeMiriRuntime runtime,
    NativeMiriDebugLaunch configuration,
  );
}

class NativeMiriDebugLaunch {
  const NativeMiriDebugLaunch({
    required this.entryPath,
    required this.edition,
    required this.timeout,
    required this.maxSteps,
    required this.maxOutputBytes,
    required this.breakpoints,
  });

  final String entryPath;
  final int edition;
  final Duration timeout;
  final int maxSteps;
  final int maxOutputBytes;
  final List<DebugBreakpoint> breakpoints;
}

abstract interface class NativeMiriDebugHandle {
  /// Blocking native calls run off the UI isolate. Futures must resolve only
  /// after those calls actually return; killing an isolate is not cancellation.
  Future<int> start();
  Future<int> resume(int mode, int generation);
  NativeMiriDebugStatus status();
  NativeMiriDebugPause pauseInfo();
  NativeMiriDebugFrames frames(
    int maxFrames,
    int maxLocals,
    int maxStringBytes,
  );
  List<int> output(int channel, int maxBytes);
  void pause();
  void cancel();
  Future<int> wait();
  Future<void> destroy();
}

class NativeMiriDebugStatus {
  const NativeMiriDebugStatus({
    required this.state,
    required this.workerExited,
    required this.generation,
    required this.revision,
  });

  final int state;
  final bool workerExited;
  final int generation;
  final int revision;
}

class NativeMiriDebugPause {
  const NativeMiriDebugPause({required this.reason, required this.exitCode});
  final int reason;
  final int exitCode;
}

class NativeMiriDebugFrames {
  const NativeMiriDebugFrames({required this.frames, required this.total});
  final List<NativeMiriDebugFrame> frames;
  final int total;
}

class NativeMiriDebugFrame {
  const NativeMiriDebugFrame({
    required this.index,
    required this.path,
    required this.line,
    required this.column,
    required this.function,
    this.locals = const [],
    this.totalLocals = 0,
    this.truncated = false,
  });

  final int index;
  final String path;
  final int line;
  final int column;
  final String function;
  final List<NativeMiriDebugLocal> locals;
  final int totalLocals;
  final bool truncated;
}

class NativeMiriDebugLocal {
  const NativeMiriDebugLocal({
    required this.name,
    required this.type,
    required this.value,
    required this.state,
    this.truncated = false,
  });

  final String name;
  final String type;
  final String value;
  final int state;
  final bool truncated;
}

class _RustDebugSession implements DebugSession {
  _RustDebugSession({
    required this.id,
    required this.owner,
    required this.root,
    required this.handle,
    required this.capabilities,
    required List<DebugBreakpoint> breakpoints,
    required this.canonicalBreakpoints,
    required this.sourceTexts,
    required this.stopOnEntry,
  }) : _snapshot = DebugSnapshot(
         sessionId: id,
         revision: 0,
         phase: DebugPhase.starting,
         breakpoints: [
           for (final point in breakpoints)
             DebugBreakpointResult(
               requested: point,
               status: DebugBreakpointStatus.pending,
             ),
         ],
       );

  @override
  final String id;
  final RustDebugger owner;
  final String root;
  final NativeMiriDebugHandle handle;
  final DebugCapabilities capabilities;
  final List<DebugBreakpoint> canonicalBreakpoints;
  final Map<String, List<String>> sourceTexts;
  final bool stopOnEntry;
  final _updates = StreamController<DebugSnapshot>.broadcast();
  final _done = Completer<void>();
  DebugSnapshot _snapshot;
  Timer? _timer;
  Future<int>? _blocking;
  Future<void>? _finishing;
  Future<void>? _disposeFuture;
  bool _stopRequested = false;
  bool _started = false;
  bool _entryObserved = false;
  bool _destroyed = false;
  int _suppressedGeneration = 0;
  int _nativeRevision = -1;
  String? _failure;
  bool _diagnosticTruncated = false;

  @override
  DebugSnapshot get snapshot => _snapshot;
  @override
  Stream<DebugSnapshot> get updates => _updates.stream;
  @override
  Future<void> get done => _done.future;

  void begin() {
    _timer = Timer.periodic(owner.pollInterval, (_) => _poll());
    _dispatch(start: true);
  }

  void _dispatch({bool start = false, int mode = 0, int generation = 0}) {
    final Future<int> call;
    try {
      call = start ? handle.start() : handle.resume(mode, generation);
    } on Object catch (error) {
      _fail(error);
      return;
    }
    _blocking = call;
    unawaited(_observeCall(call, start: start));
  }

  Future<void> _observeCall(Future<int> call, {required bool start}) async {
    try {
      final accepted = await call;
      if (identical(_blocking, call)) _blocking = null;
      if (start) _started = accepted != 2;
      if (accepted == 2) {
        _failure = 'Rust 编译器正被其他运行、检查或调试会话占用';
        await _finish();
      } else if (accepted != 0) {
        final status = handle.status();
        if (status.state != 3 && status.state != 4) {
          _failure = 'Rust 调试器拒绝命令或暂停令牌已失效';
        }
        await _finish();
      } else if (_finishing == null && !_done.isCompleted) {
        _poll(force: true);
      }
    } on Object catch (error) {
      if (identical(_blocking, call)) _blocking = null;
      _fail(error);
    }
  }

  void _poll({bool force = false}) {
    if (_finishing != null || _destroyed || _done.isCompleted) return;
    var readingPause = false;
    try {
      final status = handle.status();
      if (status.state < 0 || status.state > 5) {
        throw StateError('Rust 调试器返回了无效状态');
      }
      if (!force && status.revision == _nativeRevision) return;
      _nativeRevision = status.revision;
      final output = _output(
        finalOutput: status.state == 3 || status.state == 4,
      );
      if (status.state == 3 || status.state == 4) {
        _publish(DebugPhase.stopping, output: output);
        _backgroundFinish();
        return;
      }
      if (status.state == 2 &&
          _blocking == null &&
          status.generation > _suppressedGeneration &&
          !_stopRequested) {
        readingPause = true;
        final pause = handle.pauseInfo();
        final raw = handle.frames(
          owner.maxFrames,
          capabilities.supportsVariables ? owner.maxLocals : 0,
          owner.maxStringBytes,
        );
        final frames = [
          for (final frame in raw.frames.take(owner.maxFrames)) _frame(frame),
        ];
        // A paused timeout may race the read-only frame copies. Discard that
        // snapshot unless the same actual pause is still current afterwards.
        final after = handle.status();
        if (after.state != 2 || after.generation != status.generation) {
          _nativeRevision = -1;
          return;
        }
        final points = _verifyPoints(frames);
        if (!_entryObserved && pause.reason == 0) {
          _entryObserved = true;
          final hit = points.any(
            (point) => point.status == DebugBreakpointStatus.verified,
          );
          if (!stopOnEntry && !hit) {
            _suppressedGeneration = status.generation;
            _publish(DebugPhase.running, output: output, breakpoints: points);
            _dispatch(generation: status.generation);
            return;
          }
        }
        _publish(
          DebugPhase.paused,
          output: output,
          pauseToken: DebugPauseToken(
            sessionId: id,
            generation: status.generation,
          ),
          frames: frames,
          framesTruncated:
              raw.total > frames.length ||
              raw.frames
                  .take(owner.maxFrames)
                  .any(
                    (frame) =>
                        frame.truncated ||
                        _bound(frame.function, owner.maxStringBytes).truncated,
                  ),
          breakpoints: points,
        );
      } else {
        _publish(
          _stopRequested || status.state == 5
              ? DebugPhase.stopping
              : status.state == 0
              ? DebugPhase.starting
              : DebugPhase.running,
          output: output,
        );
      }
    } on Object catch (error) {
      // Frame readers can lose a pause to the native timeout. Do not turn that
      // legitimate transition into a transport failure.
      try {
        if (readingPause && handle.status().state != 2) {
          _nativeRevision = -1;
          return;
        }
      } on Object {
        // Preserve the original read error below.
      }
      _fail(error);
    }
  }

  _DebugOutput _output({bool finalOutput = false}) {
    final channels = <String>[];
    final truncated = <bool>[];
    var remaining = owner.maxOutputBytes;
    for (var channel = 0; channel < 3; channel++) {
      final bytes = handle.output(channel, owner.maxOutputBytes);
      final length = bytes.length.clamp(0, remaining);
      final bounded = _decodeUtf8Prefix(
        bytes,
        remaining,
        deferIncompleteTail: !finalOutput,
      );
      channels.add(bounded.text);
      truncated.add(bounded.truncated);
      remaining -= length;
    }
    return (
      stdout: channels[0],
      stderr: channels[1],
      console: channels[2],
      stdoutTruncated: truncated[0],
      stderrTruncated: truncated[1],
      consoleTruncated: truncated[2],
    );
  }

  DebugFrame _frame(NativeMiriDebugFrame frame) {
    DebugSourceLocation? location;
    if (frame.path.isNotEmpty && frame.line > 0) {
      try {
        final path = _source(root, frame.path);
        final lines = sourceTexts[_key(path)];
        if (lines != null) {
          if (frame.line <= lines.length) {
            int? column;
            if (frame.column > 0) {
              final runes = lines[frame.line - 1].runes;
              if (frame.column <= runes.length + 1) {
                var utf16Column = 1;
                for (final rune in runes.take(frame.column - 1)) {
                  utf16Column += rune > 0xffff ? 2 : 1;
                }
                column = utf16Column;
              }
            }
            location = DebugSourceLocation(
              filePath: path,
              line: frame.line,
              column: column,
            );
          }
        }
      } on Object {
        // Real foreign/runtime frames remain visible without navigable paths.
      }
    }
    return DebugFrame(
      id: '${frame.index}',
      threadId: 'active',
      name: _bound(frame.function, owner.maxStringBytes).text,
      location: location,
      locals: [
        if (capabilities.supportsVariables)
          for (final local in frame.locals.take(owner.maxLocals))
            _variable(local),
      ],
      localsUnavailableReason: capabilities.supportsVariables
          ? null
          : '当前运行库不支持局部变量',
      localsTruncated: frame.totalLocals > owner.maxLocals,
    );
  }

  DebugVariable _variable(NativeMiriDebugLocal local) {
    final name = _bound(local.name, owner.maxStringBytes);
    final type = _bound(local.type, owner.maxStringBytes);
    final value = _bound(
      local.state == 0 ? local.value : '',
      owner.maxStringBytes,
    );
    return DebugVariable(
      name: name.text,
      type: type.text,
      value: value.text,
      unavailableReason: switch (local.state) {
        0 => null,
        1 => '尚未初始化或已失效',
        2 => '当前 Miri 后端无法显示此类型',
        _ => 'Miri 返回了未知的局部变量状态',
      },
      truncated:
          local.truncated ||
          name.truncated ||
          type.truncated ||
          value.truncated,
    );
  }

  List<DebugBreakpointResult> _verifyPoints(List<DebugFrame> frames) => [
    for (var i = 0; i < _snapshot.breakpoints.length; i++)
      if (_snapshot.breakpoints[i].status == DebugBreakpointStatus.verified)
        _snapshot.breakpoints[i]
      else
        _verifyPoint(i, frames.isEmpty ? null : frames.first.location),
  ];

  DebugBreakpointResult _verifyPoint(int index, DebugSourceLocation? location) {
    final expected = canonicalBreakpoints[index];
    final hit =
        location != null &&
        _same(location.filePath, expected.filePath) &&
        location.line == expected.line;
    return DebugBreakpointResult(
      requested: _snapshot.breakpoints[index].requested,
      status: hit
          ? DebugBreakpointStatus.verified
          : DebugBreakpointStatus.pending,
      actualLocation: hit ? location : null,
    );
  }

  void _publish(
    DebugPhase phase, {
    _DebugOutput? output,
    DebugPauseToken? pauseToken,
    List<DebugFrame> frames = const [],
    bool framesTruncated = false,
    List<DebugBreakpointResult>? breakpoints,
    String? message,
    int? exitCode,
  }) {
    final boundedMessage = message == null
        ? null
        : _boundDiagnostic(message, owner.maxStringBytes);
    _diagnosticTruncated =
        _diagnosticTruncated || (boundedMessage?.truncated ?? false);
    _snapshot = DebugSnapshot(
      sessionId: id,
      revision: _snapshot.revision + 1,
      phase: phase,
      pauseToken: pauseToken,
      threads: phase == DebugPhase.paused
          ? const [DebugThread(id: 'active', name: 'Miri 当前线程', isPaused: true)]
          : const [],
      frames: frames,
      framesTruncated: framesTruncated,
      breakpoints: breakpoints ?? _snapshot.breakpoints,
      stdout: output?.stdout ?? _snapshot.stdout,
      stderr: output?.stderr ?? _snapshot.stderr,
      console: output?.console ?? _snapshot.console,
      stdoutTruncated:
          (output?.stdoutTruncated ?? false) || _snapshot.stdoutTruncated,
      stderrTruncated:
          (output?.stderrTruncated ?? false) || _snapshot.stderrTruncated,
      consoleTruncated:
          (output?.consoleTruncated ?? false) ||
          _snapshot.consoleTruncated ||
          _diagnosticTruncated,
      message: boundedMessage?.text,
      exitCode: exitCode,
    );
    if (!_updates.isClosed) _updates.add(_snapshot);
  }

  void _fail(Object error) {
    if (_failure == null) {
      final failure = _boundDiagnostic(
        'Rust 调试失败：$error',
        owner.maxStringBytes,
      );
      _failure = failure.text;
      _diagnosticTruncated = _diagnosticTruncated || failure.truncated;
    }
    try {
      handle.cancel();
    } on Object {
      // Cleanup below must still await and join any actual worker.
    }
    _backgroundFinish();
  }

  void _backgroundFinish() {
    unawaited(
      _finish().catchError((Object error) {
        // Keep done pending and the session owned if cleanup is not proven.
        // Explicit stop/dispose can retry; never publish a fabricated terminal.
        _publish(DebugPhase.stopping, message: 'Rust 调试清理尚未完成：$error');
      }),
    );
  }

  Future<void> _finish() {
    if (_done.isCompleted) return _done.future;
    return _finishing ??= _cleanup().whenComplete(() => _finishing = null);
  }

  Future<void> _cleanup() async {
    _timer?.cancel();
    final blocking = _blocking;
    if (blocking != null) {
      try {
        final result = await blocking;
        // A busy start never acquired a native worker; wait would reject it.
        if (result != 2) _started = true;
      } on Object {
        // status/wait are authoritative about actual native worker ownership.
        _started = handle.status().state != 0;
      }
      if (identical(_blocking, blocking)) _blocking = null;
    }
    var state = handle.status();
    if (state.state != 0) _started = true;
    if (_started) {
      if (state.state != 3 && state.state != 4) handle.cancel();
      if (await handle.wait() != 0) {
        throw StateError('Rust 调试工作线程未完成退出');
      }
      state = handle.status();
      if (!state.workerExited || (state.state != 3 && state.state != 4)) {
        throw StateError('Rust 调试清理未得到工作线程退出证明');
      }
    }
    final pause = _started ? handle.pauseInfo() : null;
    final output = _output(finalOutput: true);
    await handle.destroy();
    _destroyed = true;
    final failed = _failure != null || state.state == 4 || !_started;
    final message =
        _failure ??
        (failed
            ? (output.console.isNotEmpty
                  ? output.console
                  : 'Rust 编译或 Miri 调试失败')
            : null);
    _publish(
      failed ? DebugPhase.failed : DebugPhase.terminated,
      output: output,
      message: message,
      exitCode: pause?.exitCode,
    );
    _done.complete();
  }

  @override
  Future<List<DebugBreakpointResult>> setBreakpoints(
    List<DebugBreakpoint> breakpoints,
  ) async {
    throw UnsupportedError('Rust 断点仅可在启动前设置；请停止后重新启动调试');
  }

  @override
  Future<void> command(
    DebugCommand command, {
    DebugPauseToken? pauseToken,
    String? threadId,
  }) async {
    if (_done.isCompleted || _finishing != null || _stopRequested) {
      throw StateError('Rust 调试会话正在停止或已经结束');
    }
    if (threadId != null && threadId != 'active') {
      throw StateError('Rust 调试线程不存在');
    }
    if (command == DebugCommand.pause) {
      if (!capabilities.supportsPause ||
          _snapshot.phase != DebugPhase.running) {
        throw UnsupportedError('当前 Rust 调试状态不支持暂停');
      }
      handle.pause();
      return;
    }
    if (_snapshot.phase != DebugPhase.paused ||
        pauseToken == null ||
        pauseToken != _snapshot.pauseToken ||
        _blocking != null) {
      throw StateError('Rust 暂停令牌已失效，请使用当前暂停位置');
    }
    final mode = switch (command) {
      DebugCommand.resume => 0,
      DebugCommand.stepInto when capabilities.supportsStepInto => 1,
      DebugCommand.stepOver when capabilities.supportsStepOver => 2,
      DebugCommand.stepOut when capabilities.supportsStepOut => 3,
      _ => throw UnsupportedError('当前 Rust 运行库不支持此单步操作'),
    };
    _suppressedGeneration = pauseToken.generation;
    _publish(DebugPhase.running);
    _dispatch(mode: mode, generation: pauseToken.generation);
  }

  @override
  Future<void> stop() async {
    if (_done.isCompleted) return;
    _stopRequested = true;
    _publish(DebugPhase.stopping);
    handle.cancel();
    await _finish();
    await _done.future;
  }

  @override
  Future<void> dispose() =>
      _disposeFuture ??= _dispose().onError<Object>((error, stack) {
        _disposeFuture = null;
        Error.throwWithStackTrace(error, stack);
      });

  Future<void> _dispose() async {
    await stop();
    await _done.future;
    await _updates.close();
  }
}

typedef _DebugOutput = ({
  String stdout,
  String stderr,
  String console,
  bool stdoutTruncated,
  bool stderrTruncated,
  bool consoleTruncated,
});

typedef _BoundedText = ({String text, bool truncated});

/// Limits encoded bytes, retaining complete Unicode scalars. In particular a
/// non-BMP character is either kept as both UTF-16 units or omitted entirely.
/// Invalid surrogate input from a transport/error is replaced with one bounded
/// U+FFFD scalar and explicitly reported as lost content.
_BoundedText _bound(String text, int limit) {
  final result = StringBuffer();
  var bytes = 0;
  var truncated = false;
  for (final original in text.runes) {
    final rune = original >= 0xd800 && original <= 0xdfff ? 0xfffd : original;
    final width = rune <= 0x7f
        ? 1
        : rune <= 0x7ff
        ? 2
        : rune <= 0xffff
        ? 3
        : 4;
    if (bytes + width > limit) {
      truncated = true;
      break;
    }
    result.writeCharCode(rune);
    bytes += width;
    truncated = truncated || rune != original;
  }
  return (text: result.toString(), truncated: truncated);
}

/// Messages have no separate truncation field in the frozen core contract.
/// A bounded visible ellipsis and consoleTruncated expose diagnostic loss.
_BoundedText _boundDiagnostic(String text, int limit) {
  final bounded = _bound(text, limit);
  if (!bounded.truncated) return bounded;
  final marker = limit >= 3 ? '…' : '.' * limit;
  final prefix = _bound(text, limit - utf8.encode(marker).length);
  return (text: '${prefix.text}$marker', truncated: true);
}

/// Decodes a bounded raw UTF-8 prefix without inventing U+FFFD for a scalar
/// split by the byte budget. A live output tail may simply be awaiting its next
/// byte; retain it in the native buffer and display it on the next full poll.
/// Malformed bytes are replaced and explicitly marked as lost content.
_BoundedText _decodeUtf8Prefix(
  List<int> bytes,
  int limit, {
  bool hasMore = false,
  bool deferIncompleteTail = false,
}) {
  var end = bytes.length.clamp(0, limit);
  final omitted = hasMore || end < bytes.length;
  if (end > 0 && (omitted || deferIncompleteTail)) {
    var start = end - 1;
    while (start > 0 && bytes[start] & 0xc0 == 0x80) {
      start--;
    }
    final first = bytes[start];
    final width = first >= 0xc2 && first <= 0xdf
        ? 2
        : first >= 0xe0 && first <= 0xef
        ? 3
        : first >= 0xf0 && first <= 0xf4
        ? 4
        : 1;
    if (end - start < width) end = start;
  }
  final prefix = bytes.sublist(0, end);
  String text;
  var malformed = false;
  try {
    text = utf8.decode(prefix);
  } on FormatException {
    text = utf8.decode(prefix, allowMalformed: true);
    malformed = true;
  }
  final decoded = _bound(text, limit);
  return (
    text: decoded.text,
    truncated: omitted || malformed || decoded.truncated,
  );
}

// Keep all libraries resident. Native compiler/backend identity is process-wide.
final _debugLibraries = <String, DynamicLibrary>{};

class _FfiDebugBackend implements NativeMiriDebugBackend {
  _FfiDebugBackend(this.libraryPath) : bindings = _DebugBindings(libraryPath);
  final String libraryPath;
  final _DebugBindings bindings;

  @override
  int get capabilityBits => bindings.capabilities();

  void validateRuntime(NativeMiriRuntime runtime) {
    final prepared = _debugLibraries.putIfAbsent(
      runtime.libraryPath,
      () => DynamicLibrary.open(runtime.libraryPath),
    );
    final discovered = _debugLibraries[libraryPath]!;
    if (prepared.handle.address != discovered.handle.address) {
      throw UnsupportedError('Rust 调试能力与准备后的运行库不是同一个已加载的原生库');
    }
  }

  @override
  NativeMiriDebugHandle create(
    NativeMiriRuntime runtime,
    NativeMiriDebugLaunch configuration,
  ) {
    final handle = using((arena) {
      final config = arena<_DebugConfig>();
      final points = arena<_Breakpoint>(
        configuration.breakpoints.length.clamp(1, 1000),
      );
      for (var i = 0; i < configuration.breakpoints.length; i++) {
        final point = configuration.breakpoints[i];
        points[i]
          ..path = point.filePath.toNativeUtf8(allocator: arena)
          ..line = point.line
          ..column = 0;
      }
      config.ref
        ..abiVersion = 1
        ..source = configuration.entryPath.toNativeUtf8(allocator: arena)
        ..sysroot = runtime.sysrootPath.toNativeUtf8(allocator: arena)
        ..crateName = 'qfli_debug'.toNativeUtf8(allocator: arena)
        ..edition = configuration.edition
        ..crateType = 0
        ..timeoutMs = configuration.timeout.inMilliseconds
        ..maxSteps = configuration.maxSteps
        ..maxOutputBytes = configuration.maxOutputBytes
        ..breakpoints = points
        ..breakpointCount = configuration.breakpoints.length;
      return bindings.create(
        config,
        runtime.backendPath?.toNativeUtf8(allocator: arena) ?? nullptr,
      );
    });
    if (handle == nullptr) {
      throw StateError('无法创建 Rust 调试会话，请检查标准库、源码及编译后端身份');
    }
    return _FfiDebugHandle(libraryPath, bindings, handle);
  }
}

class _FfiDebugHandle implements NativeMiriDebugHandle {
  _FfiDebugHandle(this.libraryPath, this.bindings, this.handle);
  final String libraryPath;
  final _DebugBindings bindings;
  final Pointer<_Handle> handle;
  bool _destroyed = false;

  @override
  Future<int> start() => _worker(libraryPath, handle.address, 0, 0, 0);
  @override
  Future<int> resume(int mode, int generation) =>
      _worker(libraryPath, handle.address, 1, mode, generation);
  @override
  Future<int> wait() => _worker(libraryPath, handle.address, 2, 0, 0);
  @override
  Future<void> destroy() async {
    if (_destroyed) return;
    await _worker(libraryPath, handle.address, 3, 0, 0);
    _destroyed = true;
  }

  @override
  void pause() => bindings.pause(handle);
  @override
  void cancel() => bindings.cancel(handle);

  @override
  NativeMiriDebugStatus status() => using((arena) {
    final state = arena<_Status>();
    if (bindings.status(handle, state) != 0) throw StateError('无法读取 Rust 调试状态');
    return NativeMiriDebugStatus(
      state: state.ref.state,
      workerExited: state.ref.workerExited != 0,
      generation: state.ref.generation,
      revision: state.ref.revision,
    );
  });

  @override
  NativeMiriDebugPause pauseInfo() => using((arena) {
    final pause = arena<_Pause>();
    if (bindings.pauseInfo(handle, pause) != 0) {
      throw StateError('无法读取 Rust 暂停位置');
    }
    return NativeMiriDebugPause(
      reason: pause.ref.reason,
      exitCode: pause.ref.exitCode,
    );
  });

  @override
  List<int> output(int channel, int maxBytes) => using((arena) {
    final length = bindings.copyOutput(handle, channel, nullptr, 0);
    if (length < 0 || length > maxBytes) throw StateError('Rust 调试输出超过安全上限');
    if (length == 0) return const <int>[];
    final buffer = arena<Uint8>(length);
    final actual = bindings.copyOutput(handle, channel, buffer, length);
    if (actual < length) throw StateError('Rust 调试输出长度发生回退');
    return buffer.asTypedList(length).toList(growable: false);
  });

  @override
  NativeMiriDebugFrames frames(
    int maxFrames,
    int maxLocals,
    int maxStringBytes,
  ) => using((arena) {
    final total = bindings.frameCount(handle);
    final result = <NativeMiriDebugFrame>[];
    final frame = arena<_Frame>();
    final locals = arena<_Local>(maxLocals.clamp(1, 512));
    for (var index = 0; index < total && index < maxFrames; index++) {
      if (bindings.frame(handle, index, frame) != 0) {
        throw StateError('Rust 暂停已结束，无法读取调用栈');
      }
      final current = frame.ref;
      final path = _string(current.path, maxStringBytes);
      final function = _string(current.function, maxStringBytes);
      final count = maxLocals == 0
          ? 0
          : bindings.locals(handle, index, locals, maxLocals);
      final variables = <NativeMiriDebugLocal>[];
      for (
        var localIndex = 0;
        localIndex < count && localIndex < maxLocals;
        localIndex++
      ) {
        final local = locals[localIndex];
        final name = _string(local.name, maxStringBytes);
        final type = _string(local.type, maxStringBytes);
        final value = _string(local.value, maxStringBytes);
        variables.add(
          NativeMiriDebugLocal(
            name: name.text,
            type: type.text,
            value: value.text,
            state: local.state,
            truncated: name.truncated || type.truncated || value.truncated,
          ),
        );
      }
      result.add(
        NativeMiriDebugFrame(
          index: current.index,
          path: path.truncated ? '' : path.text,
          line: current.line,
          column: current.column,
          function: function.text,
          locals: variables,
          totalLocals: count,
          truncated: path.truncated || function.truncated,
        ),
      );
    }
    return NativeMiriDebugFrames(frames: result, total: total);
  });
}

_BoundedText _string(Pointer<Utf8> pointer, int maxBytes) {
  if (pointer == nullptr) return (text: '', truncated: false);
  final bytes = <int>[];
  final raw = pointer.cast<Uint8>();
  for (var index = 0; index <= maxBytes; index++) {
    final byte = raw[index];
    if (byte == 0) {
      return _decodeUtf8Prefix(bytes, maxBytes);
    }
    if (index == maxBytes) {
      return _decodeUtf8Prefix(bytes, maxBytes, hasMore: true);
    }
    bytes.add(byte);
  }
  throw StateError('无法读取 Rust 调试 UTF-8 字符串');
}

Future<int> _worker(
  String path,
  int address,
  int operation,
  int mode,
  int generation,
) => Isolate.run(() {
  final library = _debugLibraries.putIfAbsent(
    path,
    () => DynamicLibrary.open(path),
  );
  final handle = Pointer<_Handle>.fromAddress(address);
  if (operation == 3) {
    library.lookupFunction<_VoidNative, _VoidDart>('qfli_miri_debug_destroy')(
      handle,
    );
    return 0;
  }
  if (operation == 1) {
    return library.lookupFunction<_ResumeNative, _ResumeDart>(
      'qfli_miri_debug_resume_at',
    )(handle, mode, generation);
  }
  return library.lookupFunction<_CallNative, _CallDart>(
    operation == 0 ? 'qfli_miri_debug_start' : 'qfli_miri_debug_wait',
  )(handle);
});

class _DebugBindings {
  _DebugBindings(String path) {
    final library = _debugLibraries.putIfAbsent(
      path,
      () => DynamicLibrary.open(path),
    );
    const symbols = [
      'qfli_miri_abi_version',
      'qfli_miri_debug_capabilities',
      'qfli_miri_debug_create',
      'qfli_miri_debug_start',
      'qfli_miri_debug_resume_at',
      'qfli_miri_debug_status',
      'qfli_miri_debug_pause',
      'qfli_miri_debug_cancel',
      'qfli_miri_debug_wait',
      'qfli_miri_debug_destroy',
      'qfli_miri_debug_pause_info',
      'qfli_miri_debug_frame_count',
      'qfli_miri_debug_frame',
      'qfli_miri_debug_locals',
      'qfli_miri_debug_copy_output_channel',
    ];
    if (symbols.any((symbol) => !library.providesSymbol(symbol)) ||
        library.lookupFunction<_VersionNative, _VersionDart>(
              'qfli_miri_abi_version',
            )() !=
            1) {
      throw UnsupportedError('当前 Rust 运行库未包含完整的 Miri 离线调试扩展');
    }
    capabilities = library.lookupFunction<_VersionNative, _VersionDart>(
      'qfli_miri_debug_capabilities',
    );
    if (capabilities() & 256 == 0) throw UnsupportedError('Rust 调试扩展不支持暂停代次校验');
    create = library.lookupFunction<_CreateNative, _CreateDart>(
      'qfli_miri_debug_create',
    );
    status = library.lookupFunction<_StatusNative, _StatusDart>(
      'qfli_miri_debug_status',
    );
    pauseInfo = library.lookupFunction<_PauseNative, _PauseDart>(
      'qfli_miri_debug_pause_info',
    );
    pause = library.lookupFunction<_VoidNative, _VoidDart>(
      'qfli_miri_debug_pause',
    );
    cancel = library.lookupFunction<_VoidNative, _VoidDart>(
      'qfli_miri_debug_cancel',
    );
    frameCount = library.lookupFunction<_CountNative, _CountDart>(
      'qfli_miri_debug_frame_count',
    );
    frame = library.lookupFunction<_FrameNative, _FrameDart>(
      'qfli_miri_debug_frame',
    );
    locals = library.lookupFunction<_LocalsNative, _LocalsDart>(
      'qfli_miri_debug_locals',
    );
    copyOutput = library.lookupFunction<_OutputNative, _OutputDart>(
      'qfli_miri_debug_copy_output_channel',
    );
  }

  late final _VersionDart capabilities;
  late final _CreateDart create;
  late final _StatusDart status;
  late final _PauseDart pauseInfo;
  late final _VoidDart pause;
  late final _VoidDart cancel;
  late final _CountDart frameCount;
  late final _FrameDart frame;
  late final _LocalsDart locals;
  late final _OutputDart copyOutput;
}

final class _Handle extends Opaque {}

final class _Breakpoint extends Struct {
  external Pointer<Utf8> path;
  @Uint32()
  external int line;
  @Uint32()
  external int column;
}

final class _DebugConfig extends Struct {
  @Uint32()
  external int abiVersion;
  external Pointer<Utf8> source;
  external Pointer<Utf8> sysroot;
  external Pointer<Utf8> crateName;
  @Uint32()
  external int edition;
  @Uint32()
  external int crateType;
  @Uint64()
  external int timeoutMs;
  @Uint64()
  external int maxSteps;
  @Size()
  external int maxOutputBytes;
  external Pointer<_Breakpoint> breakpoints;
  @Size()
  external int breakpointCount;
}

final class _Status extends Struct {
  @Uint32()
  external int state;
  @Uint32()
  external int workerExited;
  @Uint64()
  external int generation;
  @Uint64()
  external int revision;
}

final class _Pause extends Struct {
  @Uint32()
  external int reason;
  @Uint32()
  external int frameCount;
  @Uint64()
  external int steps;
  @Int32()
  external int exitCode;
}

final class _Frame extends Struct {
  @Uint32()
  external int index;
  @Uint32()
  external int pad;
  external Pointer<Utf8> path;
  @Uint32()
  external int line;
  @Uint32()
  external int column;
  external Pointer<Utf8> function;
}

final class _Local extends Struct {
  external Pointer<Utf8> name;
  external Pointer<Utf8> type;
  @Uint32()
  external int local;
  @Uint32()
  external int state;
  external Pointer<Utf8> value;
}

typedef _VersionNative = Uint32 Function();
typedef _VersionDart = int Function();
typedef _CreateNative =
    Pointer<_Handle> Function(Pointer<_DebugConfig>, Pointer<Utf8>);
typedef _CreateDart =
    Pointer<_Handle> Function(Pointer<_DebugConfig>, Pointer<Utf8>);
typedef _CallNative = Int32 Function(Pointer<_Handle>);
typedef _CallDart = int Function(Pointer<_Handle>);
typedef _ResumeNative = Int32 Function(Pointer<_Handle>, Uint32, Uint64);
typedef _ResumeDart = int Function(Pointer<_Handle>, int, int);
typedef _VoidNative = Void Function(Pointer<_Handle>);
typedef _VoidDart = void Function(Pointer<_Handle>);
typedef _StatusNative = Int32 Function(Pointer<_Handle>, Pointer<_Status>);
typedef _StatusDart = int Function(Pointer<_Handle>, Pointer<_Status>);
typedef _PauseNative = Int32 Function(Pointer<_Handle>, Pointer<_Pause>);
typedef _PauseDart = int Function(Pointer<_Handle>, Pointer<_Pause>);
typedef _CountNative = Size Function(Pointer<_Handle>);
typedef _CountDart = int Function(Pointer<_Handle>);
typedef _FrameNative = Int32 Function(Pointer<_Handle>, Size, Pointer<_Frame>);
typedef _FrameDart = int Function(Pointer<_Handle>, int, Pointer<_Frame>);
typedef _LocalsNative =
    Size Function(Pointer<_Handle>, Size, Pointer<_Local>, Size);
typedef _LocalsDart = int Function(Pointer<_Handle>, int, Pointer<_Local>, int);
typedef _OutputNative =
    Size Function(Pointer<_Handle>, Uint32, Pointer<Uint8>, Size);
typedef _OutputDart = int Function(Pointer<_Handle>, int, Pointer<Uint8>, int);
