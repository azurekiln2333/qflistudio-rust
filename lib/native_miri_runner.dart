import 'dart:async';
import 'dart:convert';
import 'dart:ffi';
import 'dart:io';
import 'dart:isolate';

import 'package:ffi/ffi.dart';
import 'package:path/path.dart' as p;
import 'package:qfli_studio_core/services/studio_profile.dart';

import 'rust_run_title.dart';

/// Invokes the packaged upstream rustc/Miri engine through its session ABI.
class NativeMiriProgramRunner implements ProgramRunner {
  const NativeMiriProgramRunner({
    required this.sysrootPath,
    this.libraryPath = 'libqfli_miri.so',
    this.backendPath,
    this.maxBasicBlocks = 10000000,
    this.timeout = const Duration(seconds: 30),
    this.maxOutputBytes = 1024 * 1024,
    this.maxGuestMemoryBytes = 64 * 1024 * 1024,
    this.pollInterval = const Duration(milliseconds: 50),
  });

  final String sysrootPath;
  final String libraryPath;
  final String? backendPath;
  final int maxBasicBlocks;
  final Duration timeout;
  final int maxOutputBytes;
  final int maxGuestMemoryBytes;
  final Duration pollInterval;

  static const int _maxNativeInput = 16 * 1024 * 1024;

  @override
  Future<ProgramRunResult?> run({
    required String projectPath,
    required String entryFile,
  }) async {
    if (p.extension(entryFile).toLowerCase() != '.rs') return null;
    final title = rustRunTitle(projectPath, entryFile);
    final root = p.normalize(p.absolute(projectPath));
    final entry = p.normalize(p.absolute(entryFile));
    try {
      if (!await Directory(root).exists()) {
        return _failure(title, '项目目录不存在：$root');
      }
      if (!p.isWithin(root, entry) || !await File(entry).exists()) {
        return _failure(title, 'Rust 源文件不存在或不在项目中：$entry');
      }
      if (!p.isAbsolute(sysrootPath) ||
          !await Directory(sysrootPath).exists()) {
        return _failure(title, 'Rust 标准库目录不存在或不是绝对路径：$sysrootPath');
      }
      final backend = backendPath;
      if (backend != null &&
          (!p.isAbsolute(backend) || !await File(backend).exists())) {
        return _failure(title, 'Rust 编译后端不存在或不是绝对路径：$backend');
      }
      if (maxBasicBlocks <= 0 ||
          timeout.inMilliseconds <= 0 ||
          maxOutputBytes < 1024 ||
          maxOutputBytes > _maxNativeInput ||
          maxGuestMemoryBytes <= 0 ||
          pollInterval.inMicroseconds <= 0) {
        return _failure(title, 'Rust 运行资源限制无效。');
      }
    } on FileSystemException catch (error) {
      return _failure(title, 'Rust 运行所需文件不可访问：${error.message}');
    }

    final session = _MiriRunSession(
      runner: this,
      projectPath: root,
      entryFile: entry,
    );
    return ProgramRunResult(
      title: title,
      stdout: session.stdout,
      stderr: session.stderr,
      exitCode: session.start(),
      cancel: session.cancel,
    );
  }

  ProgramRunResult _failure(String title, String message) => ProgramRunResult(
    title: title,
    stdout: const Stream<String>.empty(),
    stderr: Stream<String>.value(message),
    exitCode: Future<int>.value(kProgramNotRunExitCode),
  );
}

class _MiriRunSession {
  _MiriRunSession({
    required this.runner,
    required this.projectPath,
    required this.entryFile,
  }) {
    _channels = [
      _OutputChannel(_stdout),
      _OutputChannel(_stderr),
      _OutputChannel(_stderr),
    ];
  }

  final NativeMiriProgramRunner runner;
  final String projectPath;
  final String entryFile;
  final StreamController<String> _stdout = StreamController<String>();
  final StreamController<String> _stderr = StreamController<String>();
  final Completer<void> _done = Completer<void>();
  late final List<_OutputChannel> _channels;
  _MiriBindings? _bindings;
  Pointer<_NativeSession>? _handle;
  Timer? _timer;
  Object? _outputError;
  bool _cancelled = false;
  Future<void>? _cancelFuture;

  Stream<String> get stdout => _stdout.stream;
  Stream<String> get stderr => _stderr.stream;

  Future<int> start() async {
    var accepted = false;
    try {
      final input = File(p.join(projectPath, 'input.txt'));
      var stdin = const <int>[];
      if (await input.exists()) {
        if (await input.length() > NativeMiriProgramRunner._maxNativeInput) {
          _stderr.add('input.txt 超过 16 MiB 输入限制。');
          return kProgramNotRunExitCode;
        }
        stdin = await input.readAsBytes();
        if (stdin.length > NativeMiriProgramRunner._maxNativeInput) {
          _stderr.add('input.txt 超过 16 MiB 输入限制。');
          return kProgramNotRunExitCode;
        }
      }
      if (_cancelled) return 130;

      final bindings = _MiriBindings(runner.libraryPath);
      _bindings = bindings;
      if (bindings.abiVersion() != 1) {
        _stderr.add('Rust 原生运行库 ABI 不匹配，请重新安装匹配的运行库。');
        return kProgramNotRunExitCode;
      }
      final handle = _createSession(bindings, stdin);
      if (handle == nullptr) {
        _stderr.add('无法创建 Rust 运行会话，请检查标准库与源文件。');
        return kProgramNotRunExitCode;
      }
      _handle = handle;
      if (_cancelled) bindings.cancel(handle);
      _timer = Timer.periodic(runner.pollInterval, (_) => _poll());

      // The helper captures only a path and an address. Neither the session
      // owner nor its controllers are sent to the blocking worker isolate.
      final result = await _runInWorker(runner.libraryPath, handle.address);
      accepted = result == 0;
      _timer?.cancel();
      _poll();
      if (!accepted) {
        _stderr.add('Rust 原生运行会话拒绝执行。');
        return kProgramNotRunExitCode;
      }
      if (_outputError != null) return 1;
      final state = calloc<_NativeResult>();
      try {
        if (bindings.result(handle, state) != 0 ||
            state.ref.state < 2 ||
            state.ref.state > 5) {
          _stderr.add('Rust 原生运行库没有返回有效的结束状态。');
          return 1;
        }
        return state.ref.exitCode;
      } finally {
        calloc.free(state);
      }
    } catch (error) {
      _stderr.add('无法执行 Rust 原生运行库：$error');
      if (_cancelled && _handle == null) return 130;
      return accepted ? 1 : kProgramNotRunExitCode;
    } finally {
      _timer?.cancel();
      final handle = _handle;
      _handle = null;
      if (handle != null) {
        // Isolate.run has completed: no run call remains active. Poll and
        // cancel calls are synchronous on this isolate, so destroy is last.
        _bindings!.destroy(handle);
      }
      for (final channel in _channels) {
        channel.close();
      }
      unawaited(_stdout.close());
      unawaited(_stderr.close());
      _done.complete();
    }
  }

  Pointer<_NativeSession> _createSession(
    _MiriBindings bindings,
    List<int> stdin,
  ) => using((arena) {
    final config = arena<_NativeConfig>();
    final source = entryFile.toNativeUtf8(allocator: arena);
    final sysroot = runner.sysrootPath.toNativeUtf8(allocator: arena);
    final bytes = stdin.isEmpty
        ? nullptr.cast<Uint8>()
        : arena<Uint8>(stdin.length);
    if (stdin.isNotEmpty) bytes.asTypedList(stdin.length).setAll(0, stdin);
    config.ref
      ..abiVersion = 1
      ..sourcePath = source
      ..sysrootPath = sysroot
      ..stdinData = bytes
      ..stdinLength = stdin.length
      ..maxBasicBlocks = runner.maxBasicBlocks
      ..timeoutMs = runner.timeout.inMilliseconds
      ..maxOutputBytes = runner.maxOutputBytes
      ..maxGuestMemoryBytes = runner.maxGuestMemoryBytes;
    final backend = runner.backendPath;
    if (backend == null) return bindings.create(config);
    final createWithBackend = bindings.createWithBackend;
    if (createWithBackend == null) {
      throw StateError('Rust 原生运行库不支持所需的编译后端路径。');
    }
    return createWithBackend(config, backend.toNativeUtf8(allocator: arena));
  });

  void _poll() {
    final handle = _handle;
    if (handle == null || _outputError != null) return;
    try {
      for (var index = 0; index < _channels.length; index++) {
        final channel = _channels[index];
        final length = _bindings!.copyOutput(handle, index, nullptr, 0);
        if (length == channel.offset) continue;
        if (length < channel.offset || length > runner.maxOutputBytes) {
          throw StateError('Rust native output length is invalid');
        }
        final buffer = calloc<Uint8>(length);
        try {
          final currentLength = _bindings!.copyOutput(
            handle,
            index,
            buffer,
            length,
          );
          if (currentLength < length) {
            throw StateError('Rust native output changed unexpectedly');
          }
          // Output may grow between the length query and copy. Only the
          // requested prefix was copied; the next poll collects the remainder.
          channel.add(buffer.asTypedList(length).sublist(channel.offset));
          channel.offset = length;
        } finally {
          calloc.free(buffer);
        }
      }
    } catch (error) {
      _outputError = error;
      _stderr.add('Rust 运行输出读取失败：$error');
      _timer?.cancel();
      _bindings!.cancel(handle);
    }
  }

  Future<void> cancel() {
    _cancelled = true;
    return _cancelFuture ??= _cancel();
  }

  Future<void> _cancel() async {
    final handle = _handle;
    if (handle != null) _bindings!.cancel(handle);
    // Killing the worker isolate could leave its native call active. Wait for
    // native cancellation checks and preserve the handle until run returns.
    await _done.future;
  }
}

Future<int> _runInWorker(String libraryPath, int address) =>
    Isolate.run(() => _nativeRun(libraryPath, address));

int _nativeRun(String libraryPath, int address) {
  final library = DynamicLibrary.open(libraryPath);
  final run = library.lookupFunction<_RunNative, _RunDart>('qfli_miri_run');
  return run(Pointer<_NativeSession>.fromAddress(address));
}

class _OutputChannel {
  _OutputChannel(StreamController<String> destination) {
    final lines = const LineSplitter().startChunkedConversion(
      _LineSink(destination),
    );
    _sink = const Utf8Decoder(
      allowMalformed: true,
    ).startChunkedConversion(lines);
  }

  late final ByteConversionSink _sink;
  int offset = 0;

  void add(List<int> bytes) => _sink.add(bytes);
  void close() => _sink.close();
}

class _LineSink implements Sink<String> {
  _LineSink(this.destination);
  final StreamController<String> destination;

  @override
  void add(String data) => destination.add(data);

  @override
  void close() {}
}

final class _NativeSession extends Opaque {}

final class _NativeConfig extends Struct {
  @Uint32()
  external int abiVersion;
  external Pointer<Utf8> sourcePath;
  external Pointer<Utf8> sysrootPath;
  external Pointer<Uint8> stdinData;
  @Size()
  external int stdinLength;
  @Uint64()
  external int maxBasicBlocks;
  @Uint64()
  external int timeoutMs;
  @Size()
  external int maxOutputBytes;
  @Uint64()
  external int maxGuestMemoryBytes;
}

final class _NativeResult extends Struct {
  @Uint32()
  external int state;
  @Int32()
  external int exitCode;
  @Uint64()
  external int basicBlocks;
  @Uint64()
  external int peakGuestMemoryBytes;
}

typedef _VersionNative = Uint32 Function();
typedef _VersionDart = int Function();
typedef _CreateNative =
    Pointer<_NativeSession> Function(Pointer<_NativeConfig>);
typedef _CreateDart = Pointer<_NativeSession> Function(Pointer<_NativeConfig>);

typedef _CreateWithBackendNative =
    Pointer<_NativeSession> Function(Pointer<_NativeConfig>, Pointer<Utf8>);
typedef _CreateWithBackendDart =
    Pointer<_NativeSession> Function(Pointer<_NativeConfig>, Pointer<Utf8>);
typedef _RunNative = Int32 Function(Pointer<_NativeSession>);
typedef _RunDart = int Function(Pointer<_NativeSession>);
typedef _CancelNative = Void Function(Pointer<_NativeSession>);
typedef _CancelDart = void Function(Pointer<_NativeSession>);
typedef _CopyNative =
    Size Function(Pointer<_NativeSession>, Uint32, Pointer<Uint8>, Size);
typedef _CopyDart =
    int Function(Pointer<_NativeSession>, int, Pointer<Uint8>, int);
typedef _ResultNative =
    Int32 Function(Pointer<_NativeSession>, Pointer<_NativeResult>);
typedef _ResultDart =
    int Function(Pointer<_NativeSession>, Pointer<_NativeResult>);

class _MiriBindings {
  _MiriBindings(String libraryPath) {
    final library = DynamicLibrary.open(libraryPath);
    abiVersion = library.lookupFunction<_VersionNative, _VersionDart>(
      'qfli_miri_abi_version',
    );
    create = library.lookupFunction<_CreateNative, _CreateDart>(
      'qfli_miri_create',
    );
    createWithBackend = library.providesSymbol('qfli_miri_create_with_backend')
        ? library
              .lookupFunction<_CreateWithBackendNative, _CreateWithBackendDart>(
                'qfli_miri_create_with_backend',
              )
        : null;
    cancel = library.lookupFunction<_CancelNative, _CancelDart>(
      'qfli_miri_cancel',
    );
    copyOutput = library.lookupFunction<_CopyNative, _CopyDart>(
      'qfli_miri_copy_output',
    );
    result = library.lookupFunction<_ResultNative, _ResultDart>(
      'qfli_miri_result',
    );
    destroy = library.lookupFunction<_CancelNative, _CancelDart>(
      'qfli_miri_destroy',
    );
  }

  late final _VersionDart abiVersion;
  late final _CreateDart create;
  late final _CreateWithBackendDart? createWithBackend;
  late final _CancelDart cancel;
  late final _CopyDart copyOutput;
  late final _ResultDart result;
  late final _CancelDart destroy;
}
