import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:path/path.dart' as p;
import 'package:qfli_studio_core/services/studio_profile.dart';

import 'ohos_miri_assets.dart';
import 'ohos_miri_runner.dart';

/// Runs desktop Cargo/rustc or the packaged in-process OHOS Miri engine.
class RustProgramRunner implements ProgramRunner {
  const RustProgramRunner({
    this.cargoExecutable = 'cargo',
    this.rustcExecutable = 'rustc',
  });

  final String cargoExecutable;
  final String rustcExecutable;

  @override
  Future<ProgramRunResult?> run({
    required String projectPath,
    required String entryFile,
  }) async {
    if (p.extension(entryFile).toLowerCase() != '.rs') return null;

    final root = p.normalize(p.absolute(projectPath));
    final entry = p.normalize(p.absolute(entryFile));
    final title = '运行 ${p.basename(entry)}（Rust）';
    if (Platform.operatingSystem == 'ohos') {
      try {
        final sysroot = await prepareOhosMiriAssets();
        return OhosMiriProgramRunner(
          sysrootPath: sysroot,
        ).run(projectPath: projectPath, entryFile: entryFile);
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
  });

  final String projectPath;
  final String entryFile;
  final bool cargo;
  final String cargoExecutable;
  final String rustcExecutable;
  final StreamController<String> _stdout = StreamController<String>();
  final StreamController<String> _stderr = StreamController<String>();
  final Completer<void> _done = Completer<void>();
  Directory? _temporary;
  Process? _active;
  bool _cancelled = false;
  Future<void>? _cancelFuture;

  Stream<String> get stdout => _stdout.stream;
  Stream<String> get stderr => _stderr.stream;

  Future<int> start() async {
    try {
      if (_cancelled) return 130;
      if (cargo) {
        return await _runProcess(cargoExecutable, [
          'run',
          '--manifest-path',
          p.join(projectPath, 'Cargo.toml'),
        ], input: await _readInput());
      }

      _temporary = await Directory.systemTemp.createTemp('qfli_rust_');
      final output = p.join(
        _temporary!.path,
        Platform.isWindows ? 'program.exe' : 'program',
      );
      final compileCode = await _runProcess(rustcExecutable, [
        entryFile,
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

  Future<String?> _readInput() async {
    final file = File(p.join(projectPath, 'input.txt'));
    return await file.exists() ? file.readAsString() : null;
  }

  Future<int> _runProcess(
    String executable,
    List<String> arguments, {
    String? input,
  }) async {
    if (_cancelled) return 130;
    final process = await Process.start(
      executable,
      arguments,
      workingDirectory: projectPath,
      runInShell: false,
    );
    _active = process;
    // Attach to the process pipes before its output can be lost by a relay.
    final outDone = _forward(process.stdout, _stdout);
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
