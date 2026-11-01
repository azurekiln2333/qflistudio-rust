import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:path/path.dart' as p;
import 'package:qfli_studio_core/services/studio_profile.dart';

import 'native_miri_assets.dart';
import 'native_miri_runner.dart';

enum RustExecutionMode { automatic, embedded }

/// Runs desktop Cargo/rustc or the packaged native rustc/Miri engine.
class RustProgramRunner implements ProgramRunner {
  const RustProgramRunner({
    this.cargoExecutable = 'cargo',
    this.rustcExecutable = 'rustc',
    this.executionMode = RustExecutionMode.automatic,
    this.embeddedRunner,
    this.rustcArguments = const [],
    this.environment,
  });

  final String cargoExecutable;
  final String rustcExecutable;
  final RustExecutionMode executionMode;
  final NativeMiriProgramRunner? embeddedRunner;
  final List<String> rustcArguments;
  final Map<String, String>? environment;

  @override
  Future<ProgramRunResult?> run({
    required String projectPath,
    required String entryFile,
  }) async {
    if (p.extension(entryFile).toLowerCase() != '.rs') return null;

    final root = p.normalize(p.absolute(projectPath));
    final entry = p.normalize(p.absolute(entryFile));
    final title = '运行 ${p.basename(entry)}（Rust）';
    if (executionMode == RustExecutionMode.embedded ||
        Platform.operatingSystem == 'ohos' ||
        Platform.isAndroid ||
        Platform.isIOS) {
      try {
        var runner = embeddedRunner;
        if (runner == null) {
          final runtime = await prepareNativeMiriAssets();
          runner = NativeMiriProgramRunner(
            sysrootPath: runtime.sysrootPath,
            libraryPath: runtime.libraryPath,
            backendPath: runtime.backendPath,
          );
        }
        return await runner.run(projectPath: projectPath, entryFile: entryFile);
      } catch (error) {
        return _failure(title, '无法加载 Rust 运行库：$error');
      }
    }
    if (!Platform.isWindows && !Platform.isLinux && !Platform.isMacOS) {
      return _failure(title, '当前平台无法启动 Rust 工具链。请在桌面端运行。');
    }
    if (!await Directory(root).exists()) {
      return _failure(title, '项目目录不存在：$root');
    }
    if (!p.isWithin(root, entry) || !await File(entry).exists()) {
      return _failure(title, 'Rust 源文件不存在或不在项目中：$entry');
    }

    final cargo = await File(p.join(root, 'Cargo.toml')).exists();
    final session = _RustRunSession(
      projectPath: root,
      entryFile: entry,
      cargo: cargo,
      cargoExecutable: cargoExecutable,
      rustcExecutable: rustcExecutable,
      rustcArguments: rustcArguments,
      environment: {...Platform.environment, ...?environment},
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

class _RustRunSession {
  _RustRunSession({
    required this.projectPath,
    required this.cargo,
    required this.cargoExecutable,
    required this.rustcExecutable,
    required this.entryFile,
    required this.rustcArguments,
    required this.environment,
  });

  final String projectPath;
  final String entryFile;
  final bool cargo;
  final String cargoExecutable;
  final String rustcExecutable;
  final List<String> rustcArguments;
  final Map<String, String> environment;
  final StreamController<String> _stdout = StreamController<String>();
  final StreamController<String> _stderr = StreamController<String>();
  final Completer<void> _done = Completer<void>();
  Directory? _temporary;
  Process? _active;
  bool _cancelled = false;
  Future<void>? _cancelFuture;

  Stream<String> get stdout => _stdout.stream;
  Stream<String> get stderr => _stderr.stream;

  String get _compilerExecutable {
    final configured = environment['RUSTC'];
    return rustcExecutable == 'rustc' &&
            configured != null &&
            configured.isNotEmpty
        ? configured
        : rustcExecutable;
  }

  Future<int> start() async {
    try {
      if (_cancelled) return 130;
      final compilerArguments = await _compilerArguments();
      if (_cancelled) return 130;
      if (cargo) {
        return await _runProcess(
          cargoExecutable,
          ['run', '--manifest-path', p.join(projectPath, 'Cargo.toml')],
          input: await _readInput(),
          processEnvironment: {
            ...environment,
            if (rustcExecutable != 'rustc') 'RUSTC': rustcExecutable,
            if (compilerArguments.isNotEmpty)
              'CARGO_ENCODED_RUSTFLAGS': compilerArguments.join('\u001f'),
          },
        );
      }

      _temporary = await Directory.systemTemp.createTemp('qfli_rust_');
      final output = p.join(
        _temporary!.path,
        Platform.isWindows ? 'program.exe' : 'program',
      );
      final compileCode = await _runProcess(_compilerExecutable, [
        entryFile,
        ...compilerArguments,
        '-o',
        output,
      ]);
      if (compileCode != 0 || _cancelled) return _cancelled ? 130 : compileCode;
      if (!await File(output).exists()) {
        _stderr.add('rustc 未生成可执行文件：$output');
        return kProgramNotRunExitCode;
      }
      return await _runProcess(output, const [], input: await _readInput());
    } on ProcessException catch (error) {
      if (_cancelled) return 130;
      _stderr.add(
        '无法启动 ${error.executable}：${error.message}。请检查 Rust 工具链与 PATH。',
      );
      return kProgramNotRunExitCode;
    } on FileSystemException catch (error) {
      if (_cancelled) return 130;
      _stderr.add('Rust 运行所需文件不可访问：${error.message}');
      return kProgramNotRunExitCode;
    } finally {
      final temporary = _temporary;
      if (temporary != null) {
        try {
          await temporary.delete(recursive: true);
        } on FileSystemException {
          // A locked compiler artifact must not override the actual exit code.
        }
      }
      unawaited(_stdout.close());
      unawaited(_stderr.close());
      _done.complete();
    }
  }

  Future<List<String>> _compilerArguments() async {
    final encoded = environment['CARGO_ENCODED_RUSTFLAGS'];
    final flags = encoded != null
        ? (encoded.isEmpty ? <String>[] : encoded.split('\u001f'))
        : (environment['RUSTFLAGS'] ?? '')
              .split(RegExp(r'\s+'))
              .where((flag) => flag.isNotEmpty)
              .toList();
    final configured = [...flags, ...rustcArguments];
    if (!Platform.isWindows ||
        rustcArguments.isNotEmpty ||
        _hasEnvironmentOverride ||
        await _hasCargoConfiguration()) {
      return configured;
    }
    final version = StringBuffer();
    if (await _runProcess(_compilerExecutable, [
          '-vV',
        ], captureStdout: version) !=
        0) {
      return configured;
    }
    final host = RegExp(
      r'^host: (\S+)\r?$',
      multiLine: true,
    ).firstMatch(version.toString())?.group(1);
    if (host == null || !host.endsWith('-pc-windows-gnu') || _cancelled) {
      return configured;
    }
    final sysroot = StringBuffer();
    if (await _runProcess(_compilerExecutable, [
          '--print',
          'sysroot',
        ], captureStdout: sysroot) !=
        0) {
      return configured;
    }
    final linker = p.join(
      sysroot.toString().trim(),
      'lib',
      'rustlib',
      host,
      'bin',
      'rust-lld.exe',
    );
    if (!await File(linker).exists()) return configured;
    return [
      '-C',
      'linker-flavor=ld.lld',
      '-C',
      'linker=$linker',
      '-C',
      'link-self-contained=yes',
    ];
  }

  bool get _hasEnvironmentOverride => environment.keys.any(
    (key) =>
        const {
          'RUSTFLAGS',
          'CARGO_ENCODED_RUSTFLAGS',
          'CARGO_BUILD_RUSTFLAGS',
          'CARGO_BUILD_TARGET',
          'RUSTC',
          'RUSTC_WRAPPER',
          'RUSTC_WORKSPACE_WRAPPER',
          'CARGO_BUILD_RUSTC',
          'CARGO_BUILD_RUSTC_WRAPPER',
          'CARGO_BUILD_RUSTC_WORKSPACE_WRAPPER',
          'CC',
          'CXX',
          'LD',
        }.contains(key) ||
        key.startsWith('CARGO_TARGET_') &&
            (key.endsWith('_LINKER') || key.endsWith('_RUSTFLAGS')),
  );

  Future<bool> _hasCargoConfiguration() async {
    // Cargo merges ancestor/global TOML files. Preserve any user configuration
    // rather than synthesizing higher-precedence flags over it.
    var directory = projectPath;
    final candidates = <String>{};
    while (true) {
      candidates.add(p.join(directory, '.cargo'));
      final parent = p.dirname(directory);
      if (p.equals(parent, directory)) break;
      directory = parent;
    }
    final cargoHome = environment['CARGO_HOME'];
    if (cargoHome != null && cargoHome.isNotEmpty) {
      candidates.add(
        p.isAbsolute(cargoHome) ? cargoHome : p.join(projectPath, cargoHome),
      );
    } else {
      for (final key in const ['USERPROFILE', 'HOME']) {
        final home = environment[key];
        if (home != null && home.isNotEmpty) {
          candidates.add(p.join(home, '.cargo'));
        }
      }
    }
    for (final candidate in candidates) {
      if (await File(p.join(candidate, 'config.toml')).exists() ||
          await File(p.join(candidate, 'config')).exists()) {
        return true;
      }
    }
    return false;
  }

  Future<String?> _readInput() async {
    final file = File(p.join(projectPath, 'input.txt'));
    return await file.exists() ? file.readAsString() : null;
  }

  Future<int> _runProcess(
    String executable,
    List<String> arguments, {
    String? input,
    StringBuffer? captureStdout,
    Map<String, String>? processEnvironment,
  }) async {
    if (_cancelled) return 130;
    final process = await Process.start(
      executable,
      arguments,
      workingDirectory: projectPath,
      runInShell: false,
      environment: processEnvironment ?? environment,
      includeParentEnvironment: false,
    );
    _active = process;
    // Attach to the process pipes before its output can be lost by a relay.
    final outDone = captureStdout == null
        ? _forward(process.stdout, _stdout)
        : _capture(process.stdout, captureStdout);
    final errDone = _forward(process.stderr, _stderr);
    unawaited(_sendInput(process, input));
    if (_cancelled) await _terminateProcessTree(process);
    try {
      final code = await process.exitCode;
      await Future.wait([outDone, errDone]);
      return _cancelled ? 130 : code;
    } finally {
      if (identical(_active, process)) _active = null;
    }
  }

  Future<void> _capture(
    Stream<List<int>> source,
    StringBuffer destination,
  ) async {
    await for (final chunk in source.transform(
      const Utf8Decoder(allowMalformed: true),
    )) {
      destination.write(chunk);
    }
  }

  Future<void> _sendInput(Process process, String? input) async {
    try {
      if (input != null) process.stdin.write(input);
      await process.stdin.close();
    } on IOException {
      // The process may exit before it consumes all of input.txt.
    }
  }

  Future<void> _forward(
    Stream<List<int>> source,
    StreamController<String> destination,
  ) async {
    await for (final line
        in source
            .transform(const Utf8Decoder(allowMalformed: true))
            .transform(const LineSplitter())) {
      destination.add(line);
    }
  }

  Future<void> cancel() {
    _cancelled = true;
    return _cancelFuture ??= _cancel();
  }

  Future<void> _cancel() async {
    final active = _active;
    if (active != null) await _terminateProcessTree(active);
    await _done.future;
  }

  Future<void> _terminateProcessTree(Process process) async {
    if (Platform.isWindows) {
      try {
        final result = await Process.run('taskkill', [
          '/PID',
          '${process.pid}',
          '/T',
          '/F',
        ], runInShell: false);
        if (result.exitCode == 0) return;
      } on ProcessException {
        // Fall through to the direct process handle.
      }
    } else {
      try {
        final result = await Process.run('ps', [
          '-A',
          '-o',
          'pid=',
          '-o',
          'ppid=',
        ]);
        if (result.exitCode == 0) {
          final children = <int, List<int>>{};
          for (final line in (result.stdout as String).split('\n')) {
            final columns = line.trim().split(RegExp(r'\s+'));
            if (columns.length != 2) continue;
            final pid = int.tryParse(columns[0]);
            final parent = int.tryParse(columns[1]);
            if (pid != null && parent != null) {
              children.putIfAbsent(parent, () => []).add(pid);
            }
          }
          void terminateChildren(int parent) {
            for (final child in children[parent] ?? const <int>[]) {
              terminateChildren(child);
              Process.killPid(child, ProcessSignal.sigkill);
            }
          }

          terminateChildren(process.pid);
        }
      } on ProcessException {
        // Fall through to the direct process handle.
      }
    }
    process.kill(ProcessSignal.sigkill);
  }
}
