import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:path/path.dart' as p;
// `code_analysis.dart` is the Flutter-free home of the frozen provider
// contract; the editor imports it directly too.
import 'package:qfli_studio_core/services/code_analysis.dart';

import 'rust_compiler_diagnostics.dart';
import 'rust_runner.dart'
    show resolveExecutableOnPath, terminateRustProcessTree;

/// Nonexecuting Rust source analysis for the offline editor.
///
/// The analyzer mirrors the project into a throw-away directory, overlays the
/// editor's exact unsaved buffers, and runs the compiler in **metadata-only,
/// JSON-diagnostics** mode. It never runs the user's program, Cargo, build
/// scripts, proc macros or a linker, and it never writes inside the project:
///
/// * `--emit=metadata --out-dir <temp>` keeps every artifact out of the project
///   (a bare `--emit=metadata` drops `lib<name>.rmeta` into the process CWD).
/// * Cargo is never invoked, so no build script, dependency download or proc
///   macro compilation can happen. Manifests that would need any of those are
///   reported as unavailable instead of producing fabricated errors.
/// * Every failure to actually check the source — missing compiler, timeout,
///   oversized output, internal compiler error — becomes an
///   `unavailableReason`, never an empty "clean" result.
///
/// ## Coordinates
///
/// Positions are converted from the compiler's raw UTF-8 byte offsets into
/// UTF-16 offsets of the exact text that was compiled. The mirror is written
/// with `utf8.encode(text)` and the index is built from those same bytes, so
/// CRLF pairs, a BOM, non-BMP characters and even lone surrogates cannot drift.
/// See `rust_compiler_diagnostics.dart` for the measured compiler behaviour.
class RustCodeAnalyzer implements CodeAnalyzer {
  RustCodeAnalyzer({
    String? rustcPath,
    this.timeout = const Duration(seconds: 8),
    this.defaultEdition = '2021',
    this.maxFiles = 512,
    this.maxMirrorBytes = 16 * 1024 * 1024,
    this.maxDiagnosticBytes = 8 * 1024 * 1024,
    this.transport,
    this.environment,
  }) : rustcPath = rustcPath ?? discoverRustc();

  /// Compiler used by the default desktop transport.
  ///
  /// `QFLI_RUSTC` wins, then the pinned toolchain in the repository's native
  /// build output (resolved against the current directory, so it only applies
  /// to a development checkout), then `rustc` on `PATH`. A missing compiler is
  /// reported as unavailable, never as clean code.
  static String discoverRustc() {
    final override = Platform.environment['QFLI_RUSTC'];
    if (override != null && override.isNotEmpty) return override;
    final executable = Platform.isWindows ? 'rustc.exe' : 'rustc';
    final bundled = p.normalize(
      p.absolute(
        p.join(
          'native',
          'build',
          'miri-windows',
          'compiler',
          'bin',
          executable,
        ),
      ),
    );
    if (File(bundled).existsSync()) return bundled;
    return executable;
  }

  /// Absolute or PATH-resolved compiler path; ignored when [transport] is set.
  final String rustcPath;

  /// Hard lifetime bound. The editor's own watchdog is longer, so a timeout
  /// arrives here first and is reported as an explicit unavailable result.
  final Duration timeout;

  /// Edition used for files and manifests that do not declare one.
  ///
  /// The product authors and verifies its Rust curriculum against 2021 and
  /// writes `edition = "2021"` into generated manifests, so guessing the
  /// compiler's 2015 default would produce false errors on correct lessons.
  final String defaultEdition;

  /// Upper bound on mirrored project files and bytes; exceeding either reports
  /// unavailable instead of silently analyzing a truncated project.
  final int maxFiles;
  final int maxMirrorBytes;

  /// Upper bound on captured compiler output; exceeding it is reported as
  /// unavailable rather than as a partial diagnostic list.
  final int maxDiagnosticBytes;

  /// Backend that actually runs the compiler. When null the desktop process
  /// transport is used and mobile platforms report unavailable, because the
  /// packaged runtime has no analysis entry yet.
  final RustAnalysisTransport? transport;

  /// Extra environment for the spawned compiler. Rust/Cargo variables that
  /// would change the target or flags are always removed.
  final Map<String, String>? environment;

  @override
  Future<CodeAnalysisResult> analyze(CodeAnalysisRequest request) async {
    try {
      return await _analyze(request);
    } on RustAnalysisUnavailable catch (error) {
      return CodeAnalysisResult(unavailableReason: error.reason);
    } on Object catch (error) {
      // A provider must never surface a raw exception: the editor would show
      // an empty Problems list that looks like clean code.
      return CodeAnalysisResult(
        unavailableReason: 'Rust 本地检查失败：${_describe(error)}',
      );
    }
  }

  Future<CodeAnalysisResult> _analyze(CodeAnalysisRequest request) async {
    if (request.language.toLowerCase() != 'rust') {
      throw const RustAnalysisUnavailable('当前文件不是 Rust 源文件，跳过本地检查');
    }
    final backend = _resolveBackend();
    final project = _Project.open(request);
    final plan = await _CratePlan.resolve(
      project: project,
      defaultEdition: defaultEdition,
    );
    final mirror = await _Mirror.build(
      project: project,
      maxFiles: maxFiles,
      maxMirrorBytes: maxMirrorBytes,
    );
    // Set once the backend may still be reading the mirror after this method
    // stops waiting for it; disposal then belongs to the backend's own future.
    var mirrorRetained = false;
    try {
      final job = RustAnalysisJob(
        mirrorRoot: mirror.root.path,
        entryPath: mirror.pathOf(plan.entry),
        crateName: plan.crateName,
        crateType: plan.crateType,
        edition: plan.edition,
        timeout: timeout,
        projectPath: project.root,
        remapFrom: mirror.root.path,
      );
      final output = await _awaitBackend(
        backend,
        job,
        onAbandoned: () => mirrorRetained = true,
        mirror: mirror,
      );
      if (output.timedOut) {
        throw RustAnalysisUnavailable('本地检查超时（${timeout.inSeconds} 秒），未完成检查');
      }
      if (output.truncated) {
        throw const RustAnalysisUnavailable('本地检查输出超过上限，未完成检查');
      }
      final stream = parseRustcDiagnostics(output.diagnosticsJsonl);
      if (stream.fatalMessage != null) {
        throw RustAnalysisUnavailable('本地检查器内部错误：${stream.fatalMessage}');
      }
      if (stream.unparsedLines > 0 && stream.reported == 0) {
        throw RustAnalysisUnavailable(
          '本地检查输出无法解析：${_firstLine(output.diagnosticsJsonl)}',
        );
      }
      if (!stream.decoded && output.exitCode != 0) {
        throw RustAnalysisUnavailable(
          '本地检查器异常退出（${output.exitCode}）：'
          '${_firstLine(output.diagnosticsJsonl)}',
        );
      }
      final diagnostics = await _mapDiagnostics(
        stream: stream,
        job: job,
        project: project,
        mirror: mirror,
        exitCode: output.exitCode,
      );
      return CodeAnalysisResult(diagnostics: diagnostics);
    } finally {
      // Skipped when the backend is still running: it owns the mirror now.
      if (!mirrorRetained) await mirror.dispose();
    }
  }

  /// Extra time a transport gets beyond [timeout] before the analyzer gives up.
  ///
  /// The process transport kills its child at [timeout]; this backstop only
  /// covers a transport that ignores its own bound (for example a native entry
  /// that never returns), so the editor lane cannot stay busy forever.
  static const Duration _transportGrace = Duration(seconds: 2);

  /// Waits for [backend] without ever pulling the mirror out from under it.
  ///
  /// When the wait expires the analyzer reports unavailable, but the work keeps
  /// running: a native adapter is blocked inside its own compile call and only
  /// stops at cooperative cancellation points. [onAbandoned] tells the caller to
  /// hand [mirror] over to [_disposeWhenStopped], so the compiler's input stays
  /// on disk exactly as long as the work can still read it.
  Future<RustAnalysisOutput> _awaitBackend(
    RustAnalysisTransport backend,
    RustAnalysisJob job, {
    required void Function() onAbandoned,
    required _Mirror mirror,
  }) async {
    final work = backend.analyze(job);
    try {
      return await work.timeout(timeout + _transportGrace);
    } on TimeoutException {
      onAbandoned();
      _disposeWhenStopped(mirror, backend, work);
      throw RustAnalysisUnavailable('本地检查超时（${timeout.inSeconds} 秒），未完成检查');
    }
  }

  /// Keeps [mirror] on disk until [work] really finishes.
  ///
  /// A transport that never returns (or returns while a worker is still
  /// running) still owns the mirrored sources. Deletion is chained to the
  /// abandoned future instead of happening at timeout, and a cancellable
  /// backend is asked to stop so that chain eventually completes. Errors are
  /// swallowed: cleanup must never surface as an analysis failure, and a
  /// transport that truly never stops leaves the temporary directory to the
  /// operating system rather than corrupting an in-flight compile.
  void _disposeWhenStopped(
    _Mirror mirror,
    RustAnalysisTransport backend,
    Future<RustAnalysisOutput> work,
  ) {
    // `RustAnalysisCancellation` is not a subtype of `RustAnalysisTransport`,
    // so the `is` test does not promote the parameter; the cast is required.
    if (backend is RustAnalysisCancellation) {
      final cancellation = backend as RustAnalysisCancellation;
      unawaited(
        cancellation.cancel().then<void>(
          (_) {},
          onError: (Object _, StackTrace _) {},
        ),
      );
    }
    unawaited(
      work
          .then<void>((_) {}, onError: (Object _, StackTrace _) {})
          .whenComplete(mirror.dispose)
          .then<void>((_) {}, onError: (Object _, StackTrace _) {}),
    );
  }

  RustAnalysisTransport _resolveBackend() {
    final explicit = transport;
    if (explicit != null) return explicit;
    if (Platform.isWindows || Platform.isLinux || Platform.isMacOS) {
      return RustcProcessTransport(
        rustcPath: rustcPath,
        environment: environment,
        maxOutputBytes: maxDiagnosticBytes,
      );
    }
    // The packaged OHOS/Android runtime exposes an execution-only ABI today, so
    // claiming analysis there would be a simulated result.
    throw const RustAnalysisUnavailable('当前平台尚未提供离线 Rust 代码检查器');
  }

  /// Converts compiler coordinates into project coordinates.
  Future<List<CodeDiagnostic>> _mapDiagnostics({
    required RustcDiagnosticStream stream,
    required RustAnalysisJob job,
    required _Project project,
    required _Mirror mirror,
    required int exitCode,
  }) async {
    final indexes = <String, Utf8ByteIndex?>{};
    final diagnostics = <CodeDiagnostic>[];
    var dropped = 0;
    var mappedError = false;
    for (final raw in stream.diagnostics) {
      if (raw.byteStart < 0 || raw.byteEnd < raw.byteStart) {
        dropped++;
        continue;
      }
      final original = mirror.originalOf(job, raw.filePath);
      if (original == null || !_within(project.root, original)) {
        dropped++;
        continue;
      }
      final index = await mirror.indexFor(original, indexes);
      if (index == null) {
        dropped++;
        continue;
      }
      mappedError |= raw.level == 'error' || raw.level == 'fatal';
      final start = index.utf16Offset(raw.byteStart);
      final end = index.utf16Offset(raw.byteEnd);
      diagnostics.add(
        CodeDiagnostic(
          filePath: original,
          startOffset: start,
          endOffset: end < start ? start : end,
          message: _messageFor(raw),
          severity: _severityFor(raw.level),
          source: 'rustc',
          code: raw.code,
        ),
      );
    }
    // Problems the compiler reported only outside the project (a sysroot span,
    // a macro definition) would otherwise turn a failing compile into a clean
    // result, which is the one thing this provider must never do.
    // Native FINISHED/0 can still carry a spanless compiler error. Warnings
    // must not hide that error, while a mapped source error plus rustc's
    // spanless abort summary remains a normal diagnostic result.
    if ((stream.hasErrors && !mappedError) ||
        (diagnostics.isEmpty && (dropped > 0 || exitCode != 0))) {
      throw const RustAnalysisUnavailable('本地检查发现的问题不在项目源码中，未完成项目级检查');
    }
    return diagnostics;
  }

  static String _messageFor(RustcDiagnostic raw) {
    final label = raw.label.trim();
    if (label.isEmpty || label == raw.message.trim()) return raw.message;
    return '${raw.message}：$label';
  }

  static CodeDiagnosticSeverity _severityFor(String level) {
    return switch (level) {
      'error' || 'fatal' => CodeDiagnosticSeverity.error,
      'warning' => CodeDiagnosticSeverity.warning,
      // `failure-note` only accompanies a real abort, so it is never a hint.
      'failure-note' => CodeDiagnosticSeverity.error,
      'note' => CodeDiagnosticSeverity.information,
      'help' => CodeDiagnosticSeverity.hint,
      _ => CodeDiagnosticSeverity.information,
    };
  }

  static String _firstLine(String value) {
    final text = value.trim();
    if (text.isEmpty) return '无输出';
    final index = text.indexOf('\n');
    return index < 0 ? text : text.substring(0, index);
  }
}

/// Raised when the source could not actually be checked.
///
/// [RustCodeAnalyzer] converts it into `CodeAnalysisResult.unavailableReason`;
/// a transport implementation may throw it for the same purpose.
class RustAnalysisUnavailable implements Exception {
  const RustAnalysisUnavailable(this.reason);
  final String reason;

  @override
  String toString() => 'RustAnalysisUnavailable: $reason';
}

/// Backend that performs the compile-only analysis step.
///
/// The shipped implementation runs the compiler as a child process. A native
/// adapter can implement this interface for OHOS: it must return the same JSONL
/// diagnostic stream and must stop **before** interpreting or executing any
/// user code (no MIR evaluation, no `main` invocation).
abstract interface class RustAnalysisTransport {
  Future<RustAnalysisOutput> analyze(RustAnalysisJob job);
}

/// Optional transport capability: the work started by [analyze] can outlive the
/// future it returns, and can be asked to stop early.
///
/// A native adapter is blocked inside its own compile call, so it can only stop
/// at cooperative cancellation points and cannot be preempted. The analyzer
/// therefore never deletes a job's source mirror while that work is alive, and
/// asks for cancellation through this interface instead of abandoning it.
/// Implementations must complete [cancel] only after every started [analyze]
/// call has returned, so a caller may delete the job's files afterwards.
abstract interface class RustAnalysisCancellation {
  Future<void> cancel();
}

/// One analysis request handed to a [RustAnalysisTransport].
///
/// Paths are absolute and already mirror-relative; a transport must not modify
/// the project directory or the mirror's contents, and must not create files
/// outside [mirrorRoot].
class RustAnalysisJob {
  const RustAnalysisJob({
    required this.mirrorRoot,
    required this.entryPath,
    required this.crateName,
    required this.crateType,
    required this.edition,
    required this.timeout,
    required this.projectPath,
    required this.remapFrom,
  });

  /// Temporary directory that holds the mirrored sources.
  final String mirrorRoot;

  /// Absolute path of the crate root inside [mirrorRoot].
  final String entryPath;

  /// `bin` or `lib`.
  final String crateType;
  final String crateName;
  final String edition;
  final Duration timeout;

  /// Original project directory, used for `--remap-path-prefix`.
  final String projectPath;

  /// Prefix to remap from ([mirrorRoot]) to [projectPath].
  final String? remapFrom;

  /// Compiler arguments shared by every transport.
  ///
  /// Deliberately excludes Cargo-only inputs: no `--extern`, no build script
  /// output, no `--cfg feature`. The target is the host, matching a normal
  /// `rustc` invocation, so analysis does not need a cross sysroot.
  List<String> get arguments => [
    '--edition=$edition',
    '--crate-type=$crateType',
    '--crate-name=$crateName',
    '--emit=metadata',
    '--error-format=json',
    '--color=never',
    '--out-dir=${p.join(mirrorRoot, 'out')}',
    if (remapFrom != null && p.isAbsolute(remapFrom!))
      '--remap-path-prefix=$remapFrom=$projectPath',
    entryPath,
  ];
}

/// Raw compiler result in either transport's own terms.
class RustAnalysisOutput {
  const RustAnalysisOutput({
    required this.exitCode,
    required this.diagnosticsJsonl,
    this.timedOut = false,
    this.truncated = false,
  });

  final int exitCode;

  /// Verbatim `--error-format=json` stderr, decoded as UTF-8.
  final String diagnosticsJsonl;
  final bool timedOut;
  final bool truncated;
}

/// Runs the compiler as a child process. Desktop only.
class RustcProcessTransport implements RustAnalysisTransport {
  RustcProcessTransport({
    required this.rustcPath,
    this.environment,
    this.maxOutputBytes = 8 * 1024 * 1024,
  });

  final String rustcPath;
  final Map<String, String>? environment;
  final int maxOutputBytes;

  @override
  Future<RustAnalysisOutput> analyze(RustAnalysisJob job) async {
    if (!p.isAbsolute(rustcPath) || !await File(rustcPath).exists()) {
      throw const RustAnalysisUnavailable('未找到 Rust 编译器，无法执行本地检查');
    }
    await Directory(p.join(job.mirrorRoot, 'out')).create(recursive: true);
    final childEnvironment = _childEnvironment();
    final Process process;
    try {
      process = await Process.start(
        resolveExecutableOnPath(rustcPath, childEnvironment),
        job.arguments,
        workingDirectory: job.mirrorRoot,
        runInShell: false,
        environment: childEnvironment,
        includeParentEnvironment: false,
      );
    } on ProcessException catch (error) {
      throw RustAnalysisUnavailable('无法启动 Rust 编译器：${error.message}');
    }
    final buffer = <int>[];
    var truncated = false;
    final stdoutDone = process.stdout.drain<void>();
    final stderrDone = process.stderr.listen((chunk) {
      if (truncated) return;
      if (buffer.length + chunk.length > maxOutputBytes) {
        truncated = true;
        return;
      }
      buffer.addAll(chunk);
    }).asFuture<void>();
    var timedOut = false;
    int exitCode;
    try {
      exitCode = await process.exitCode.timeout(job.timeout);
    } on TimeoutException {
      timedOut = true;
      // Compiler cancellation is not observable from the outside, so the whole
      // tree has to go; otherwise a runaway expansion keeps a core busy and
      // starves the next analysis.
      await terminateRustProcessTree(process);
      exitCode = 124;
    }
    await Future.wait([stdoutDone, stderrDone]);
    return RustAnalysisOutput(
      exitCode: exitCode,
      diagnosticsJsonl: const Utf8Decoder(allowMalformed: true).convert(buffer),
      timedOut: timedOut,
      truncated: truncated,
    );
  }

  /// Minimal, deterministic child environment.
  ///
  /// Inherited `RUSTFLAGS`, `CARGO_ENCODED_RUSTFLAGS`, `RUSTC*` and `RUSTUP_*`
  /// would silently change the target or inject a wrapper, which would make the
  /// editor disagree with what the analyzed source actually means.
  Map<String, String> _childEnvironment() {
    final source = environment ?? Platform.environment;
    final result = <String, String>{};
    for (final entry in source.entries) {
      final upper = entry.key.toUpperCase();
      if (upper.startsWith('RUST') || upper.startsWith('CARGO')) continue;
      result[entry.key] = entry.value;
    }
    return result;
  }
}

/// A normalized view of the request: absolute project root plus the exact text
/// of every captured buffer.
class _Project {
  _Project({
    required this.root,
    required this.activeFile,
    required this.documents,
  });

  factory _Project.open(CodeAnalysisRequest request) {
    final root = p.normalize(p.absolute(request.projectPath));
    final active = p.normalize(p.absolute(request.activeFilePath));
    if (!_within(root, active)) {
      throw const RustAnalysisUnavailable('当前文件不在项目目录内，跳过本地检查');
    }
    return _Project(
      root: root,
      activeFile: active,
      documents: {
        for (final document in request.documents)
          _pathKey(p.normalize(p.absolute(document.path))): document,
      },
    );
  }

  final String root;
  final String activeFile;

  /// Captured buffers keyed by path identity. The values carry the exact
  /// unsaved text, which is what the mirror writes.
  final Map<String, CodeDocumentSnapshot> documents;

  /// Captured text for [path], or null when the file must be read from disk.
  CodeDocumentSnapshot? snapshot(String path) => documents[_pathKey(path)];
}

/// Resolved crate root, type, name and edition for the active file.
class _CratePlan {
  const _CratePlan({
    required this.entry,
    required this.crateType,
    required this.crateName,
    required this.edition,
  });

  /// Absolute **project** path of the crate root to compile.
  final String entry;
  final String crateType;
  final String crateName;
  final String edition;

  static const int _maxModuleFiles = 256;

  static Future<_CratePlan> resolve({
    required _Project project,
    required String defaultEdition,
  }) async {
    final manifest = await _Manifest.load(project.root);
    final blocker = manifest.blocker;
    if (blocker != null) throw RustAnalysisUnavailable(blocker);
    final edition = manifest.edition ?? defaultEdition;
    final targets = <_Target>[
      for (final target in manifest.targets)
        if (await _exists(project, target.absolutePath(project.root))) target,
    ];
    // The active file is a declared target root: analyze exactly that target.
    for (final target in targets) {
      if (_samePath(target.absolutePath(project.root), project.activeFile)) {
        return _plan(target, project.root, edition);
      }
    }
    // Otherwise the active file is a module: analyze the target that can reach
    // it, so `use crate::…` resolves and the rest of the crate is checked too.
    final reachable = <_Target>[];
    for (final target in targets) {
      if (await _reaches(
        project,
        target.absolutePath(project.root),
        project.activeFile,
      )) {
        reachable.add(target);
      }
    }
    if (reachable.length == 1) {
      return _plan(reachable.single, project.root, edition);
    }
    if (reachable.isEmpty && targets.length == 1) {
      return _plan(targets.single, project.root, edition);
    }
    // A file no target reaches (or an ambiguous project) is analyzed on its
    // own, which is exactly what running it standalone would do.
    return _CratePlan(
      entry: project.activeFile,
      crateType: await _hasMain(project, project.activeFile) ? 'bin' : 'lib',
      crateName: _sanitize(p.basenameWithoutExtension(project.activeFile)),
      edition: edition,
    );
  }

  static _CratePlan _plan(_Target target, String root, String edition) =>
      _CratePlan(
        entry: target.absolutePath(root),
        crateType: target.crateType,
        crateName: target.name,
        edition: edition,
      );

  /// Whether [file] is reachable from crate root [root] by `mod` declarations.
  ///
  /// Only *target selection* depends on this scan; every diagnostic still comes
  /// from the compiler. Comments and strings are not stripped, so the scan can
  /// over-approximate, but it can never invent a position.
  static Future<bool> _reaches(
    _Project project,
    String root,
    String file,
  ) async {
    final target = _pathKey(file);
    final queue = <String>[root];
    final seen = <String>{_pathKey(root)};
    while (queue.isNotEmpty && seen.length <= _maxModuleFiles) {
      final current = queue.removeLast();
      if (_pathKey(current) == target) return true;
      final text = await _text(project, current);
      if (text == null) continue;
      for (final candidate in _declaredModules(current, text)) {
        if (seen.add(_pathKey(candidate))) queue.add(candidate);
      }
    }
    return false;
  }

  /// Module files declared by `mod name;` / `#[path = "…"] mod name;`.
  static Iterable<String> _declaredModules(String file, String text) sync* {
    final directory = p.dirname(file);
    final pattern = RegExp(
      r'''#\s*\[\s*path\s*=\s*"([^"]+)"\s*\]\s*(?:pub(?:\([^)]*\))?\s+)?mod\s+([A-Za-z_][A-Za-z0-9_]*)\s*;'''
      r'''|(?:^|\n)\s*(?:pub(?:\([^)]*\))?\s+)?mod\s+([A-Za-z_][A-Za-z0-9_]*)\s*;''',
    );
    for (final match in pattern.allMatches(text)) {
      final explicit = match.group(1);
      if (explicit != null &&
          !explicit.contains(r'\') &&
          !explicit.contains(':') &&
          !p.isAbsolute(explicit)) {
        yield p.normalize(p.join(directory, explicit));
        continue;
      }
      final name = match.group(2) ?? match.group(3);
      if (name == null || name == 'mod') continue;
      yield p.normalize(p.join(directory, '$name.rs'));
      yield p.normalize(p.join(directory, name, 'mod.rs'));
    }
  }

  static Future<bool> _hasMain(_Project project, String file) async {
    final text = await _text(project, file);
    if (text == null) return false;
    // Dart's RegExp has no inline `(?m)` flag; ECMAScript treats `^` as
    // line-start only through the named option.
    return RegExp(
      r'^[ \t]*(?:pub(?:\([^)]*\))?[ \t]+)?(?:const[ \t]+)?(?:async[ \t]+)?(?:unsafe[ \t]+)?fn[ \t]+main[ \t]*\(',
      multiLine: true,
    ).hasMatch(text);
  }

  static Future<bool> _exists(_Project project, String path) async {
    if (project.snapshot(path) != null) return true;
    try {
      return await File(path).exists();
    } on FileSystemException {
      return false;
    }
  }

  static Future<String?> _text(_Project project, String path) async {
    final snapshot = project.snapshot(path);
    if (snapshot != null) return snapshot.text;
    try {
      final file = File(path);
      if (!await file.exists()) return null;
      return const Utf8Decoder(
        allowMalformed: true,
      ).convert(await file.readAsBytes());
    } on FileSystemException {
      return null;
    }
  }

  static String _sanitize(String value) {
    final cleaned = value.replaceAll(RegExp(r'[^A-Za-z0-9_]'), '_');
    if (cleaned.isEmpty) return 'analysis';
    return RegExp(r'^[A-Za-z_]').hasMatch(cleaned) ? cleaned : 'r_$cleaned';
  }
}

class _Target {
  const _Target({
    required this.name,
    required this.path,
    required this.crateType,
  });

  final String name;

  /// Manifest-relative path, for example `src/main.rs`.
  final String path;
  final String crateType;

  String absolutePath(String root) =>
      p.normalize(p.joinAll([root, ...p.split(path)]));
}

/// Minimal `Cargo.toml` reader.
///
/// Only the keys that decide *how to analyze* are read: edition, declared
/// targets and whether the manifest needs something the offline analyzer must
/// refuse (external crates, build scripts). Unknown keys are ignored rather
/// than guessed at, and an empty `[dependencies]` table is not a dependency.
class _Manifest {
  _Manifest({
    required this.edition,
    required this.targets,
    required this.blocker,
  });

  final String? edition;
  final List<_Target> targets;

  /// Human-readable reason the manifest cannot be analyzed offline, or null.
  final String? blocker;

  static Future<_Manifest> load(String root) async {
    final file = File(p.join(root, 'Cargo.toml'));
    if (!await file.exists()) {
      return _Manifest(edition: null, targets: const [], blocker: null);
    }
    final String text;
    try {
      text = const Utf8Decoder(
        allowMalformed: true,
      ).convert(await file.readAsBytes());
    } on FileSystemException {
      return _Manifest(
        edition: null,
        targets: const [],
        blocker: '无法读取 Cargo.toml，跳过本地检查',
      );
    }
    return parse(
      text,
      hasBuildScript: await File(p.join(root, 'build.rs')).exists(),
    );
  }

  static _Manifest parse(String text, {required bool hasBuildScript}) {
    var section = '';
    String? edition;
    String? packageName;
    String? libPath;
    String? buildKey;
    final bins = <({String name, String path})>[];
    var hasDependencies = false;
    var hasBuildDependencies = false;
    var binIndex = -1;
    for (final rawLine in const LineSplitter().convert(text)) {
      final line = _stripComment(rawLine).trim();
      if (line.isEmpty) continue;
      if (line.startsWith('[')) {
        section = line.replaceAll(RegExp(r'[\[\]]'), '').trim();
        if (section == 'bin') {
          binIndex = bins.length;
          bins.add((name: '', path: ''));
        }
        continue;
      }
      final separator = line.indexOf('=');
      if (separator <= 0) continue;
      final key = line.substring(0, separator).trim();
      final value = _unquote(line.substring(separator + 1).trim());
      if (section == 'package') {
        if (key == 'edition') edition = value;
        if (key == 'name') packageName = value;
        if (key == 'build') buildKey = value;
      } else if (section == 'lib') {
        if (key == 'path') libPath = value;
      } else if (section == 'dependencies' ||
          section.endsWith('.dependencies')) {
        hasDependencies = true;
      } else if (section == 'build-dependencies' ||
          section.endsWith('.build-dependencies')) {
        hasBuildDependencies = true;
      } else if (section == 'bin' && binIndex >= 0) {
        final current = bins[binIndex];
        bins[binIndex] = (
          name: key == 'name' ? value : current.name,
          path: key == 'path' ? value : current.path,
        );
      }
    }
    if (hasDependencies) {
      return _Manifest(
        edition: edition,
        targets: const [],
        blocker: '项目声明了外部依赖，离线检查无法解析依赖，未完成检查',
      );
    }
    if (hasBuildDependencies) {
      return _Manifest(
        edition: edition,
        targets: const [],
        blocker: '项目包含构建脚本依赖，离线检查不会执行构建脚本，未完成检查',
      );
    }
    if (buildKey == 'true' || (buildKey == null && hasBuildScript)) {
      return _Manifest(
        edition: edition,
        targets: const [],
        blocker: '项目包含 build.rs，离线检查不会执行构建脚本，未完成检查',
      );
    }
    final crateName = _CratePlan._sanitize(packageName ?? 'analysis');
    final targets = <_Target>[
      _Target(name: crateName, path: libPath ?? 'src/lib.rs', crateType: 'lib'),
      for (final bin in bins)
        _Target(
          name: bin.name.isEmpty ? crateName : _CratePlan._sanitize(bin.name),
          path: bin.path.isNotEmpty
              ? bin.path
              : bin.name.isEmpty
              ? 'src/main.rs'
              : 'src/bin/${bin.name}.rs',
          crateType: 'bin',
        ),
      if (bins.isEmpty)
        _Target(name: crateName, path: 'src/main.rs', crateType: 'bin'),
    ];
    return _Manifest(edition: edition, targets: targets, blocker: null);
  }

  static String _stripComment(String line) {
    final index = line.indexOf('#');
    return index < 0 ? line : line.substring(0, index);
  }

  static String _unquote(String value) {
    if (value.length >= 2) {
      final first = value[0];
      final last = value[value.length - 1];
      if ((first == '"' && last == '"') || (first == "'" && last == "'")) {
        return value.substring(1, value.length - 1);
      }
    }
    return value;
  }
}

/// Temporary project copy that the compiler reads.
///
/// Unsaved buffers are written as `utf8.encode(text)`, so the bytes the
/// compiler sees are exactly the bytes the editor shows and the offset index
/// built from those same bytes is exact by construction. Unopened files are
/// copied verbatim, which is identical for valid UTF-8 and keeps other assets
/// byte-exact.
class _Mirror {
  _Mirror._(this.root, this._mirrorToOriginal, this._originalToMirror);

  final Directory root;
  final Map<String, String> _mirrorToOriginal;
  final Map<String, String> _originalToMirror;

  static const _skippedDirectories = {
    'target',
    '.git',
    '.dart_tool',
    '.gradle',
    'node_modules',
  };

  static Future<_Mirror> build({
    required _Project project,
    required int maxFiles,
    required int maxMirrorBytes,
  }) async {
    final source = Directory(project.root);
    if (!await source.exists()) {
      throw const RustAnalysisUnavailable('项目目录不存在，跳过本地检查');
    }
    final directory = await Directory.systemTemp.createTemp(
      'qfli_rust_analysis_',
    );
    final mirrorToOriginal = <String, String>{};
    final originalToMirror = <String, String>{};
    var total = 0;
    var files = 0;
    try {
      await for (final entity in source.list(
        recursive: true,
        followLinks: false,
      )) {
        if (entity is! File) continue;
        final relative = p.relative(entity.path, from: project.root);
        if (_skipped(relative)) continue;
        final snapshot = project.snapshot(entity.path);
        // Unsaved text is authoritative; otherwise the disk bytes are copied
        // verbatim. Valid UTF-8 round-trips byte for byte through decode and
        // re-encode, and copying raw bytes keeps non-UTF-8 assets (for example
        // `include_bytes!` targets) exact instead of inflating them with
        // replacement characters that would also eat the size budget.
        final bytes = snapshot != null
            ? utf8.encode(snapshot.text)
            : await _readBytes(entity);
        if (bytes == null) continue;
        total += bytes.length;
        if (++files > maxFiles || total > maxMirrorBytes) {
          throw const RustAnalysisUnavailable('项目超出本地检查范围（文件数或体积过大），未完成检查');
        }
        final destination = await _write(directory, relative, bytes);
        final original = p.normalize(
          p.joinAll([project.root, ...p.split(relative)]),
        );
        mirrorToOriginal[_pathKey(destination)] = original;
        originalToMirror[_pathKey(original)] = destination;
      }
      // A captured buffer that is not on disk yet (a new unsaved file) is still
      // part of the project the user is editing.
      for (final document in project.documents.values) {
        final key = _pathKey(document.path);
        if (originalToMirror.containsKey(key)) continue;
        if (!_within(project.root, document.path)) continue;
        final relative = p.relative(document.path, from: project.root);
        if (_skipped(relative)) continue;
        final bytes = utf8.encode(document.text);
        total += bytes.length;
        if (++files > maxFiles || total > maxMirrorBytes) {
          throw const RustAnalysisUnavailable('项目超出本地检查范围（文件数或体积过大），未完成检查');
        }
        final destination = await _write(directory, relative, bytes);
        mirrorToOriginal[_pathKey(destination)] = document.path;
        originalToMirror[key] = destination;
      }
      return _Mirror._(directory, mirrorToOriginal, originalToMirror);
    } on Object {
      await _deleteQuietly(directory);
      rethrow;
    }
  }

  static bool _skipped(String relative) =>
      p.split(relative).any(_skippedDirectories.contains);

  static Future<String> _write(
    Directory root,
    String relative,
    List<int> bytes,
  ) async {
    final destination = p.joinAll([root.path, ...p.split(relative)]);
    final target = File(destination);
    await target.parent.create(recursive: true);
    await target.writeAsBytes(bytes, flush: true);
    return destination;
  }

  static Future<void> _deleteQuietly(Directory directory) async {
    try {
      await directory.delete(recursive: true);
    } on FileSystemException {
      // Best effort: a locked file must not replace the real error.
    }
  }

  /// Absolute path inside the mirror for [original].
  String pathOf(String original) {
    final mirrorPath = _originalToMirror[_pathKey(original)];
    if (mirrorPath == null) {
      throw RustAnalysisUnavailable(
        '无法为 ${p.basename(original)} 建立临时分析副本，未完成检查',
      );
    }
    return mirrorPath;
  }

  /// Project path for a compiler-reported path, or null when it is foreign.
  ///
  /// Three shapes are accepted, because the exact form depends on whether the
  /// compiler honoured `--remap-path-prefix` and on how it joined the relative
  /// part (Windows reports the remapped prefix with backslashes and the rest
  /// with forward slashes, so every comparison goes through [_pathKey]):
  ///
  /// 1. a mirrored path (remap ignored) — mapped through the mirror table;
  /// 2. an already-remapped project path — accepted only if it is a real
  ///    mirrored file, so a compiler cannot invent a location;
  /// 3. a mirrored path that still needs prefix translation.
  String? originalOf(RustAnalysisJob job, String reported) {
    if (reported.isEmpty) return null;
    final normalized = p.normalize(reported);
    final key = _pathKey(normalized);
    final direct = _mirrorToOriginal[key];
    if (direct != null) return direct;
    // The compiler remapped the prefix already: the path is a project path.
    final original = _originalToMirror.containsKey(key)
        ? normalized
        : _translate(job, normalized);
    if (original == null) return null;
    // Only report files that really took part in the compile.
    return _originalToMirror.containsKey(_pathKey(original)) ? original : null;
  }

  /// Rewrites a mirrored path into project coordinates.
  String? _translate(RustAnalysisJob job, String path) {
    final from = job.remapFrom;
    if (from == null) return null;
    final normalizedFrom = p.normalize(from);
    if (!p.isWithin(normalizedFrom, path)) return null;
    return p.normalize(
      p.joinAll([
        job.projectPath,
        ...p.split(p.relative(path, from: normalizedFrom)),
      ]),
    );
  }

  /// Offset index for the mirrored copy of [original].
  Future<Utf8ByteIndex?> indexFor(
    String original,
    Map<String, Utf8ByteIndex?> cache,
  ) async {
    final key = _pathKey(original);
    if (cache.containsKey(key)) return cache[key];
    final mirrorPath = _originalToMirror[key];
    Utf8ByteIndex? index;
    if (mirrorPath != null) {
      try {
        index = Utf8ByteIndex.fromBytes(await File(mirrorPath).readAsBytes());
      } on FileSystemException {
        index = null;
      }
    }
    cache[key] = index;
    return index;
  }

  Future<void> dispose() => _deleteQuietly(root);

  static Future<List<int>?> _readBytes(File file) async {
    try {
      return await file.readAsBytes();
    } on FileSystemException {
      return null;
    }
  }
}

String _pathKey(String path) {
  final normalized = p.normalize(p.absolute(path));
  // Windows paths compare case-insensitively everywhere else in the product;
  // POSIX stays exact so a case-sensitive filesystem is not misreported.
  return Platform.isWindows ? normalized.toLowerCase() : normalized;
}

bool _within(String root, String file) {
  final normalizedRoot = p.normalize(p.absolute(root));
  final normalizedFile = p.normalize(p.absolute(file));
  if (_pathKey(normalizedRoot) == _pathKey(normalizedFile)) return false;
  return p.isWithin(normalizedRoot, normalizedFile);
}

bool _samePath(String a, String b) => _pathKey(a) == _pathKey(b);

String _describe(Object error) =>
    error is FileSystemException ? error.message : error.toString();
