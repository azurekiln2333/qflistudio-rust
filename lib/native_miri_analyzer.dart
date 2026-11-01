import 'dart:async';
import 'dart:convert';
import 'dart:ffi';
import 'dart:io';
import 'dart:isolate';

import 'package:ffi/ffi.dart';
import 'package:path/path.dart' as p;

import 'native_miri_assets.dart';
import 'rust_code_analyzer.dart';

typedef NativeMiriAnalysisSessionFactory =
    NativeMiriAnalysisSession Function(
      NativeMiriRuntime runtime,
      RustAnalysisJob job,
      int maxOutputBytes,
    );

/// Uses the packaged compiler's optional, nonexecuting analysis-only ABI.
///
/// Runtime preparation is identical to execution, including its architecture,
/// sysroot and backend identity. This transport never calls `qfli_miri_run`.
/// Missing analysis symbols are an unavailable backend, including on an older
/// ABI-1 runtime that can still execute programs.
///
/// The native compile call runs in a worker isolate. Timeout and [cancel] request
/// cooperative native cancellation and wait for that call before destroying the
/// session. An in-flight rustc query cannot be forcibly preempted; killing its
/// isolate or returning early would let the analyzer delete files still in use.
///
/// Because of that, [analyze] completes only after the blocking native call has
/// returned, and [cancel] completes only after every started call has returned.
/// The owning [RustCodeAnalyzer] relies on both to decide when the source mirror
/// may be deleted.
class NativeMiriAnalysisTransport
    implements RustAnalysisTransport, RustAnalysisCancellation {
  NativeMiriAnalysisTransport({
    Future<NativeMiriRuntime> Function()? prepareRuntime,
    NativeMiriAnalysisSessionFactory? sessionFactory,
    this.maxOutputBytes = 8 * 1024 * 1024,
  }) : _prepareRuntime = prepareRuntime ?? prepareNativeMiriAssets,
       _sessionFactory = sessionFactory ?? _FfiAnalysisSession.create;

  final Future<NativeMiriRuntime> Function() _prepareRuntime;
  final NativeMiriAnalysisSessionFactory _sessionFactory;
  final int maxOutputBytes;
  final Set<_ActiveAnalysis> _active = {};

  @override
  Future<RustAnalysisOutput> analyze(RustAnalysisJob job) async {
    final active = _ActiveAnalysis();
    _active.add(active);
    Timer? deadline;
    try {
      _validateLimits(job);
      final runtime = await _prepareRuntime();
      active.throwIfInterrupted();
      await _validatePaths(runtime, job);
      active.throwIfInterrupted();
      final session = _sessionFactory(runtime, job, maxOutputBytes);
      active.session = session;
      deadline = Timer(job.timeout, () => active.requestCancel(timedOut: true));

      // This Future completes only after the blocking native call returns.
      // Never use Future.timeout or Isolate.kill here: the owning analyzer may
      // remove the source mirror immediately after this method completes.
      final accepted = await session.analyze();
      deadline.cancel();
      active.throwIfInterrupted();
      if (accepted == 2) throw _busy;
      if (accepted != 0) {
        throw const RustAnalysisUnavailable('Rust 原生检查会话拒绝执行，未完成检查');
      }
      final result = session.result();
      switch (result.state) {
        case 2:
          if (result.exitCode != 0) {
            throw const RustAnalysisUnavailable('Rust 原生检查返回无效的完成状态');
          }
          final bytes = session.readDiagnostics(maxOutputBytes);
          // Enforce the limit independently of the native implementation and
          // injected sessions. Malformed UTF-8 cannot become clean source.
          if (bytes.length > maxOutputBytes) {
            throw const RustAnalysisUnavailable('Rust 检查诊断超过输出上限，未完成检查');
          }
          final String jsonl;
          try {
            jsonl = utf8.decode(bytes);
          } on FormatException {
            throw const RustAnalysisUnavailable('Rust 检查诊断不是有效的 UTF-8，未完成检查');
          }
          return RustAnalysisOutput(exitCode: 0, diagnosticsJsonl: jsonl);
        case 3:
          throw const RustAnalysisUnavailable('Rust 本地检查已取消，未完成检查');
        case 4:
          throw const RustAnalysisUnavailable('Rust 本地检查达到时间或诊断输出上限，未完成检查');
        case 5:
          throw const RustAnalysisUnavailable('Rust 原生检查器内部错误，未完成检查');
        default:
          // 0 (READY) and 1 (RUNNING) mean the call did not reach a terminal
          // state. `QFLI_BUSY` is a return code, never a session state, so a
          // busy answer is handled above and must not appear here.
          throw const RustAnalysisUnavailable('Rust 原生检查没有返回有效的结束状态');
      }
    } on RustAnalysisUnavailable {
      rethrow;
    } on Object catch (error) {
      throw RustAnalysisUnavailable('无法使用 Rust 原生检查器：$error');
    } finally {
      deadline?.cancel();
      final session = active.session;
      active.session = null;
      try {
        // Any native analyze call has returned. Cancel/result/copy calls on
        // this isolate are synchronous, so destruction is the final call.
        session?.destroy();
      } finally {
        _active.remove(active);
        active.done.complete();
      }
    }
  }

  /// Cancels requests currently owned by this transport, then waits for their
  /// workers and destruction. Future requests are unaffected.
  ///
  /// Completes only once no native call is still reading a caller's source
  /// mirror, so the caller may delete those files afterwards.
  @override
  Future<void> cancel() async {
    final current = _active.toList(growable: false);
    for (final active in current) {
      active.requestCancel();
    }
    await Future.wait(current.map((active) => active.done.future));
  }

  void _validateLimits(RustAnalysisJob job) {
    if (job.timeout.inMilliseconds <= 0 ||
        maxOutputBytes < 1024 ||
        maxOutputBytes > 16 * 1024 * 1024) {
      throw const RustAnalysisUnavailable('Rust 本地检查资源限制无效');
    }
    if (!const {'2015', '2018', '2021', '2024'}.contains(job.edition) ||
        !const {'bin', 'lib'}.contains(job.crateType) ||
        !RegExp(r'^[A-Za-z0-9_]{1,64}$').hasMatch(job.crateName)) {
      throw const RustAnalysisUnavailable('Rust 本地检查的版本或 crate 配置无效');
    }
  }

  Future<void> _validatePaths(
    NativeMiriRuntime runtime,
    RustAnalysisJob job,
  ) async {
    if (!p.isAbsolute(job.mirrorRoot) ||
        !p.isAbsolute(job.entryPath) ||
        !p.isWithin(job.mirrorRoot, job.entryPath) ||
        !await Directory(job.mirrorRoot).exists() ||
        !await File(job.entryPath).exists()) {
      throw const RustAnalysisUnavailable('Rust 检查源文件不存在或不在临时项目内');
    }
    if (!p.isAbsolute(runtime.sysrootPath) ||
        !await Directory(runtime.sysrootPath).exists()) {
      throw const RustAnalysisUnavailable('Rust 检查标准库目录不存在或不是绝对路径');
    }
    final backend = runtime.backendPath;
    if (backend != null &&
        (!p.isAbsolute(backend) || !await File(backend).exists())) {
      throw const RustAnalysisUnavailable('Rust 检查编译后端不存在或不是绝对路径');
    }
    // C string conversion must never turn a different Dart path into a valid
    // native prefix. Also check the library name before DynamicLibrary.open.
    if ([
      job.entryPath,
      runtime.sysrootPath,
      runtime.libraryPath,
      ?backend,
    ].any((path) => path.contains('\u0000'))) {
      throw const RustAnalysisUnavailable('Rust 检查路径包含无效字符');
    }
  }
}

const _busy = RustAnalysisUnavailable('Rust 编译器正在运行或检查其他源码，请稍后重试');

class _ActiveAnalysis {
  final Completer<void> done = Completer<void>();
  NativeMiriAnalysisSession? session;
  bool _cancelled = false;
  bool _timedOut = false;
  Object? _cancelError;

  void requestCancel({bool timedOut = false}) {
    _timedOut |= timedOut;
    if (_cancelled) return;
    _cancelled = true;
    try {
      session?.cancel();
    } on Object catch (error) {
      // Timer callbacks must not emit uncaught asynchronous exceptions. Keep
      // awaiting the worker even if cancellation itself is unavailable.
      _cancelError = error;
    }
  }

  void throwIfInterrupted() {
    if (_cancelError != null) {
      throw RustAnalysisUnavailable('Rust 检查取消失败：$_cancelError');
    }
    if (_timedOut) {
      throw const RustAnalysisUnavailable('Rust 本地检查超时，未完成检查');
    }
    if (_cancelled) {
      throw const RustAnalysisUnavailable('Rust 本地检查已取消，未完成检查');
    }
  }
}

/// Narrow session seam for deterministic lifecycle tests. Production uses the
/// FFI implementation below; [analyze] must finish only once the native call has
/// stopped. Implementations must keep the native library loaded for the process.
abstract interface class NativeMiriAnalysisSession {
  Future<int> analyze();
  void cancel();
  NativeMiriAnalysisResult result();
  List<int> readDiagnostics(int maxBytes);
  void destroy();
}

class NativeMiriAnalysisResult {
  const NativeMiriAnalysisResult({required this.state, required this.exitCode});

  final int state;
  final int exitCode;
}

// Deliberately never close these handles. The adapter shares process-global
// compiler/backend state with the execution runner and other worker isolates.
final _libraries = <String, DynamicLibrary>{};

class _FfiAnalysisSession implements NativeMiriAnalysisSession {
  _FfiAnalysisSession(this.libraryPath, this.bindings, this.handle);

  static NativeMiriAnalysisSession create(
    NativeMiriRuntime runtime,
    RustAnalysisJob job,
    int maxOutputBytes,
  ) {
    final bindings = _AnalysisBindings(runtime.libraryPath);
    final handle = using((arena) {
      final config = arena<_AnalysisConfig>();
      config.ref
        ..abiVersion = 1
        ..sourcePath = job.entryPath.toNativeUtf8(allocator: arena)
        ..sysrootPath = runtime.sysrootPath.toNativeUtf8(allocator: arena)
        ..crateName = job.crateName.toNativeUtf8(allocator: arena)
        ..edition = int.parse(job.edition)
        ..crateType = job.crateType == 'lib' ? 1 : 0
        ..timeoutMs = job.timeout.inMilliseconds
        ..maxOutputBytes = maxOutputBytes;
      final backend = runtime.backendPath;
      return bindings.create(
        config,
        backend == null
            ? nullptr.cast<Utf8>()
            : backend.toNativeUtf8(allocator: arena),
      );
    });
    if (handle == nullptr) {
      throw const RustAnalysisUnavailable('无法创建 Rust 检查会话，请检查源码、标准库和编译后端');
    }
    return _FfiAnalysisSession(runtime.libraryPath, bindings, handle);
  }

  final String libraryPath;
  final _AnalysisBindings bindings;
  final Pointer<_AnalysisSessionHandle> handle;

  @override
  Future<int> analyze() => _analyzeInWorker(libraryPath, handle.address);

  @override
  void cancel() => bindings.cancel(handle);

  @override
  NativeMiriAnalysisResult result() => using((arena) {
    final result = arena<_AnalysisNativeResult>();
    if (bindings.result(handle, result) != 0) {
      throw const RustAnalysisUnavailable('无法读取 Rust 原生检查结果');
    }
    return NativeMiriAnalysisResult(
      state: result.ref.state,
      exitCode: result.ref.exitCode,
    );
  });

  @override
  List<int> readDiagnostics(int maxBytes) {
    if (bindings.copyOutput(handle, 0, nullptr, 0) != 0 ||
        bindings.copyOutput(handle, 1, nullptr, 0) != 0) {
      throw const RustAnalysisUnavailable('Rust 原生检查返回了非诊断输出，未完成检查');
    }
    final length = bindings.copyOutput(handle, 2, nullptr, 0);
    if (length < 0 || length > maxBytes) {
      throw const RustAnalysisUnavailable('Rust 检查诊断超过输出上限，未完成检查');
    }
    if (length == 0) return const [];
    return using((arena) {
      final bytes = arena<Uint8>(length);
      if (bindings.copyOutput(handle, 2, bytes, length) != length) {
        throw const RustAnalysisUnavailable('Rust 检查结束后诊断长度发生变化');
      }
      // Detach the result before arena disposal.
      return bytes.asTypedList(length).toList(growable: false);
    });
  }

  @override
  void destroy() => bindings.destroy(handle);
}

Future<int> _analyzeInWorker(String libraryPath, int address) =>
    Isolate.run(() => _nativeAnalyze(libraryPath, address));

int _nativeAnalyze(String libraryPath, int address) {
  final library = DynamicLibrary.open(libraryPath);
  final analyze = library.lookupFunction<_AnalyzeNative, _AnalyzeDart>(
    'qfli_miri_analyze',
  );
  return analyze(Pointer<_AnalysisSessionHandle>.fromAddress(address));
}

class _AnalysisBindings {
  _AnalysisBindings(String libraryPath) {
    final library = _libraries.putIfAbsent(
      libraryPath,
      () => DynamicLibrary.open(libraryPath),
    );
    if (!library.providesSymbol('qfli_miri_abi_version')) {
      throw const RustAnalysisUnavailable('Rust 原生检查库 ABI 不匹配');
    }
    if (library.lookupFunction<_VersionNative, _VersionDart>(
          'qfli_miri_abi_version',
        )() !=
        1) {
      throw const RustAnalysisUnavailable('Rust 原生检查库 ABI 不匹配');
    }
    if (!library.providesSymbol('qfli_miri_create_analysis') ||
        !library.providesSymbol('qfli_miri_analyze')) {
      throw const RustAnalysisUnavailable('当前 Rust 运行库尚未包含离线代码检查功能');
    }
    // Core ABI-1 symbols. A version-1 library always exports them; checking
    // first keeps a damaged build an explicit reason instead of a raw lookup
    // error that would read as an internal failure.
    if (!library.providesSymbol('qfli_miri_cancel') ||
        !library.providesSymbol('qfli_miri_copy_output') ||
        !library.providesSymbol('qfli_miri_result') ||
        !library.providesSymbol('qfli_miri_destroy')) {
      throw const RustAnalysisUnavailable('Rust 原生检查库缺少必要的会话接口');
    }
    create = library.lookupFunction<_CreateNative, _CreateDart>(
      'qfli_miri_create_analysis',
    );
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

  late final _CreateDart create;
  late final _CancelDart cancel;
  late final _CopyDart copyOutput;
  late final _ResultDart result;
  late final _CancelDart destroy;
}

final class _AnalysisSessionHandle extends Opaque {}

final class _AnalysisConfig extends Struct {
  @Uint32()
  external int abiVersion;
  external Pointer<Utf8> sourcePath;
  external Pointer<Utf8> sysrootPath;
  external Pointer<Utf8> crateName;
  @Uint32()
  external int edition;
  @Uint32()
  external int crateType;
  @Uint64()
  external int timeoutMs;
  @Size()
  external int maxOutputBytes;
}

final class _AnalysisNativeResult extends Struct {
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
    Pointer<_AnalysisSessionHandle> Function(
      Pointer<_AnalysisConfig>,
      Pointer<Utf8>,
    );
typedef _CreateDart =
    Pointer<_AnalysisSessionHandle> Function(
      Pointer<_AnalysisConfig>,
      Pointer<Utf8>,
    );
typedef _AnalyzeNative = Int32 Function(Pointer<_AnalysisSessionHandle>);
typedef _AnalyzeDart = int Function(Pointer<_AnalysisSessionHandle>);
typedef _CancelNative = Void Function(Pointer<_AnalysisSessionHandle>);
typedef _CancelDart = void Function(Pointer<_AnalysisSessionHandle>);
typedef _CopyNative =
    Size Function(
      Pointer<_AnalysisSessionHandle>,
      Uint32,
      Pointer<Uint8>,
      Size,
    );
typedef _CopyDart =
    int Function(Pointer<_AnalysisSessionHandle>, int, Pointer<Uint8>, int);
typedef _ResultNative =
    Int32 Function(
      Pointer<_AnalysisSessionHandle>,
      Pointer<_AnalysisNativeResult>,
    );
typedef _ResultDart =
    int Function(
      Pointer<_AnalysisSessionHandle>,
      Pointer<_AnalysisNativeResult>,
    );
