import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:path/path.dart' as p;
import 'package:qfli_studio_core/services/studio_profile.dart';

import 'cargo_targets.dart';
import 'native_miri_assets.dart';
import 'native_miri_runner.dart';
import 'rust_run_title.dart';

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
    this.offline,
  });

  final String cargoExecutable;
  final String rustcExecutable;
  final RustExecutionMode executionMode;
  final NativeMiriProgramRunner? embeddedRunner;
  final List<String> rustcArguments;
  final Map<String, String>? environment;

  /// Whether Cargo must be forbidden from touching the network.
  ///
  /// When null the effective value is read from
  /// [StudioProfile.current]`.offlineOnly`, so an offline product inherits the
  /// policy without every call site repeating it. An explicit value lets tests
  /// pin the behaviour without a profile.
  final bool? offline;

  @override
  Future<ProgramRunResult?> run({
    required String projectPath,
    required String entryFile,
  }) async {
    if (p.extension(entryFile).toLowerCase() != '.rs') return null;

    final root = p.normalize(p.absolute(projectPath));
    final entry = p.normalize(p.absolute(entryFile));
    final title = rustRunTitle(root, entry);
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
        // The embedded runner generates its own concise title; forward its
        // result transparently so a custom embedded runner is not re-wrapped.
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
      offline: offline ?? (StudioProfile.current?.offlineOnly == true),
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
    required this.offline,
  });

  final String projectPath;
  final String entryFile;
  final bool cargo;
  final String cargoExecutable;
  final String rustcExecutable;
  final List<String> rustcArguments;
  final Map<String, String> environment;

  /// Disallows every Cargo network operation when true.
  final bool offline;
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

  /// Base environment every child process inherits.
  ///
  /// An offline product must not let Cargo reach the network: setting
  /// `CARGO_NET_OFFLINE=true` makes `cargo` itself refuse every fetch/index
  /// operation instead of silently hanging or failing with a network error.
  ///
  /// The value is **forced**, not merely defaulted: an inherited
  /// `CARGO_NET_OFFLINE=false` (for example exported by the developer's shell)
  /// used to survive the merge and re-enable the network, defeating the
  /// profile's `offlineOnly` policy while the runner still claimed to be
  /// offline. The runner also prepends `--offline` to every Cargo invocation so
  /// the policy does not depend on the environment alone. An explicit
  /// [RustProgramRunner.offline] of `false` keeps the caller's environment
  /// untouched, so online hosts can still opt into the network.
  Map<String, String> get _baseEnvironment =>
      offline ? {...environment, 'CARGO_NET_OFFLINE': 'true'} : environment;

  Future<int> start() async {
    try {
      if (_cancelled) return 130;
      final compilerArguments = await _compilerArguments();
      if (_cancelled) return 130;
      if (cargo) {
        final plan = await _resolveCargoPlan(compilerArguments);
        // Cancellation during metadata must keep the documented 130 contract.
        if (_cancelled || plan.cancelled) return 130;
        if (plan.error != null) {
          _stderr.add(plan.error!);
          return kProgramNotRunExitCode;
        }
        if (!plan.standalone) {
          return await _runProcess(
            cargoExecutable,
            // `--offline` is a Cargo global option, so it must precede the
            // subcommand. Prepending it makes the offline policy independent of
            // the environment: even a conflicting `--config net.offline=false`
            // (or an inherited CARGO_NET_OFFLINE=false) cannot re-enable the
            // network for this invocation.
            (offline ? ['--offline', ...plan.arguments] : plan.arguments),
            input: await _readInput(),
            processEnvironment: {
              ..._baseEnvironment,
              if (rustcExecutable != 'rustc') 'RUSTC': rustcExecutable,
              if (compilerArguments.isNotEmpty)
                'CARGO_ENCODED_RUSTFLAGS': compilerArguments.join('\u001f'),
            },
          );
        }
        // A valid manifest with no runnable target for this source falls
        // through to the standalone rustc route below. External crate
        // dependencies are intentionally not synthesized.
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

  /// Resolves how a Cargo project should run [entryFile].
  ///
  /// Runs `cargo metadata --no-deps --format-version 1` through the same
  /// cancelable process wrapper as compilation; metadata stdout never reaches
  /// the user stream. Returns either explicit `cargo run` arguments or a
  /// standalone fallback, or an actionable error when the manifest or target
  /// state is invalid.
  Future<_CargoRunPlan> _resolveCargoPlan(
    List<String> compilerArguments,
  ) async {
    final metadataOutput = StringBuffer();
    final metadataEnvironment = {
      ..._baseEnvironment,
      if (rustcExecutable != 'rustc') 'RUSTC': rustcExecutable,
      if (compilerArguments.isNotEmpty)
        'CARGO_ENCODED_RUSTFLAGS': compilerArguments.join('\u001f'),
    };
    final metadataCode = await _runProcess(
      cargoExecutable,
      [
        if (offline) '--offline',
        'metadata',
        '--no-deps',
        '--format-version',
        '1',
        '--manifest-path',
        p.join(projectPath, 'Cargo.toml'),
      ],
      captureStdout: metadataOutput,
      processEnvironment: metadataEnvironment,
    );
    if (_cancelled) return const _CargoRunPlan.cancelled();
    if (metadataCode != 0) {
      return const _CargoRunPlan.error(
        'cargo metadata 失败，无法确定 Cargo 目标。请检查 Cargo.toml 与工具链。',
      );
    }
    final List<CargoTarget> targets;
    try {
      targets = decodeCargoTargets(metadataOutput.toString());
    } on FormatException catch (error) {
      return _CargoRunPlan.error('cargo metadata 输出无法解析：${error.message}');
    }
    final lookup = selectCargoTarget(targets: targets, entryFile: entryFile);
    return switch (lookup) {
      CargoTargetMatch(:final target) => _CargoRunPlan.cargo(
        cargoRunArguments(target.manifestPath, target),
      ),
      CargoTargetUnregistered() => const _CargoRunPlan.standalone(),
      // A registered but non-runnable source must fail, never fall back to
      // rustc or to a different Cargo target.
      CargoTargetNotRunnable(:final targets) => _CargoRunPlan.error(
        cargoNotRunnableMessage(
          p.posix.joinAll(p.split(p.relative(entryFile, from: projectPath))),
          targets,
        ),
      ),
      CargoTargetAmbiguous(:final targets) => _CargoRunPlan.error(
        cargoAmbiguousMessage(
          p.posix.joinAll(p.split(p.relative(entryFile, from: projectPath))),
          targets,
        ),
      ),
    };
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
    // A caller-provided flag or linker configuration takes precedence over the
    // bundled-GNU fallback, matching the documented contract.
    if (rustcArguments.isNotEmpty ||
        hasRustLinkerEnvironmentOverride(environment) ||
        await hasCargoLinkerConfiguration(projectPath, environment)) {
      return configured;
    }
    final fallback = await resolveGnuLinkerFallbackFlags(
      rustcExecutable: _compilerExecutable,
      environment: environment,
      workingDirectory: projectPath,
      probe: _probe,
      isCancelled: () => _cancelled,
    );
    return [...configured, ...fallback];
  }

  /// Captures one compiler probe's stdout, or null when it could not run.
  ///
  /// Shares the session's cancellable process lifecycle so a probe during
  /// metadata resolution still honours Ctrl+C.
  Future<String?> _probe(String executable, List<String> arguments) async {
    final output = StringBuffer();
    if (await _runProcess(executable, arguments, captureStdout: output) != 0) {
      return null;
    }
    return output.toString();
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
    final effectiveEnvironment = processEnvironment ?? _baseEnvironment;
    final process = await Process.start(
      resolveExecutableOnPath(executable, effectiveEnvironment),
      arguments,
      workingDirectory: projectPath,
      runInShell: false,
      environment: effectiveEnvironment,
      includeParentEnvironment: false,
    );
    _active = process;
    // Attach to the process pipes before its output can be lost by a relay.
    final outDone = captureStdout == null
        ? _forward(process.stdout, _stdout)
        : _capture(process.stdout, captureStdout);
    final errDone = _forward(process.stderr, _stderr);
    unawaited(_sendInput(process, input));
    if (_cancelled) await terminateRustProcessTree(process);
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
    if (active != null) await terminateRustProcessTree(active);
    await _done.future;
  }
}

/// Kills [process] and every descendant, then waits for the direct child to
/// exit.
///
/// `cargo` spawns `rustc` and the linker as grandchildren; killing only the
/// direct child leaves those compilers running and holding file handles. The
/// same tree strategy is used by every Rust execution path (editor runs and
/// the terminal's raw `rustc`/`cargo` commands) so cancellation means the same
/// thing everywhere. Waiting for [Process.exitCode] keeps the "cancel then
/// observe the status" contract truthful instead of returning before the tree
/// is actually gone.
Future<void> terminateRustProcessTree(Process process) async {
  if (Platform.isWindows) {
    try {
      final result = await Process.run('taskkill', [
        '/PID',
        '${process.pid}',
        '/T',
        '/F',
      ], runInShell: false);
      if (result.exitCode == 0) {
        // taskkill has already signalled the whole tree; still await the
        // direct child so the caller observes a settled process.
        try {
          await process.exitCode;
        } on ProcessException {
          // The process may already be reaped.
        }
        return;
      }
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
  try {
    await process.exitCode;
  } on ProcessException {
    // The process may already be reaped.
  }
}

/// Environment variables that mean the caller has its own linker/compiler
/// configuration, which the bundled-GNU fallback must not override.
const Set<String> _linkerOverrideVariables = {
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
};

/// Whether [environment] carries an explicit Rust/linker configuration.
///
/// When true, callers must not synthesize the bundled-GNU linker fallback:
/// the user's flags, linker and crate metadata win, matching the documented
/// contract. Shared by the editor runner and the terminal's raw tools so the
/// two cannot drift.
bool hasRustLinkerEnvironmentOverride(Map<String, String> environment) =>
    environment.keys.any(
      (key) =>
          _linkerOverrideVariables.contains(key) ||
          key.startsWith('CARGO_TARGET_') &&
              (key.endsWith('_LINKER') || key.endsWith('_RUSTFLAGS')),
    );

/// Whether a Cargo configuration file could carry a custom linker.
///
/// Cargo merges ancestor and global TOML files. A user configuration must be
/// preserved rather than overridden by synthesized higher-precedence flags, so
/// its presence disables the bundled-GNU fallback.
Future<bool> hasCargoLinkerConfiguration(
  String projectPath,
  Map<String, String> environment,
) async {
  var directory = p.normalize(p.absolute(projectPath));
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

/// Captures one compiler probe's stdout, or null when it did not succeed.
typedef RustcProbe =
    Future<String?> Function(String executable, List<String> arguments);

/// The bundled Windows GNU toolchain ships `rust-lld` but no `gcc`.
///
/// A source compiled with the plain `rustc`/`cargo` default link line would
/// fail there, so when no user linker configuration exists this returns the
/// same minimal `-C` flags the editor runner already uses:
/// `-C linker-flavor=ld.lld -C linker=<rust-lld> -C link-self-contained=yes`.
///
/// Returns an empty list on any non-GNU host, when the linker binary is absent,
/// when a probe fails, or when [isCancelled] reports cancellation. [probe] lets
/// the cancellable editor session share its process lifecycle; the terminal
/// uses the default `Process.run` probe.
Future<List<String>> resolveGnuLinkerFallbackFlags({
  required String rustcExecutable,
  required Map<String, String> environment,
  required String workingDirectory,
  RustcProbe? probe,
  bool Function()? isCancelled,
}) async {
  if (!Platform.isWindows) return const <String>[];
  final run =
      probe ??
      (executable, arguments) => _runProbe(executable, arguments, environment);
  final version = await run(rustcExecutable, const ['-vV']);
  if (version == null || (isCancelled?.call() ?? false)) {
    return const <String>[];
  }
  final host = RegExp(
    r'^host: (\S+)\r?$',
    multiLine: true,
  ).firstMatch(version)?.group(1);
  if (host == null || !host.endsWith('-pc-windows-gnu')) {
    return const <String>[];
  }
  final sysroot = await run(rustcExecutable, const ['--print', 'sysroot']);
  if (sysroot == null || (isCancelled?.call() ?? false)) {
    return const <String>[];
  }
  final linker = p.join(
    sysroot.trim(),
    'lib',
    'rustlib',
    host,
    'bin',
    'rust-lld.exe',
  );
  if (!await File(linker).exists()) return const <String>[];
  return <String>[
    '-C',
    'linker-flavor=ld.lld',
    '-C',
    'linker=$linker',
    '-C',
    'link-self-contained=yes',
  ];
}

/// Resolves [executable] to an absolute path using [environment]'s `PATH`.
///
/// `Process.start` on Windows resolves a bare name against the *parent*
/// process' PATH, not the environment passed to the child, so a product that
/// makes a toolchain discoverable by prepending PATH to the spawn environment
/// would otherwise spawn the wrong (or no) binary. Callers pass the result to
/// `Process.start` and to the linker probe so both agree on the toolchain.
/// Returns [executable] unchanged when it is already absolute or not found.
String resolveExecutableOnPath(
  String executable,
  Map<String, String> environment,
) {
  if (p.isAbsolute(executable)) return executable;
  final path = environment['PATH'] ?? environment['Path'];
  if (path == null || path.isEmpty) return executable;
  final separator = Platform.isWindows ? ';' : ':';
  final extensions = Platform.isWindows
      ? _windowsExecutableExtensions(environment)
      : const [''];
  for (final directory in path.split(separator)) {
    if (directory.isEmpty) continue;
    for (final extension in extensions) {
      final candidate = p.join(directory, '$executable$extension');
      if (File(candidate).existsSync()) return candidate;
    }
  }
  return executable;
}

List<String> _windowsExecutableExtensions(Map<String, String> environment) {
  final raw = environment['PATHEXT'] ?? '.COM;.EXE;.BAT;.CMD';
  return [
    for (final entry in raw.split(';'))
      if (entry.isNotEmpty) entry.toLowerCase(),
    '',
  ];
}

/// Default probe used by terminal callers: resolves [executable] against
/// [environment]'s PATH, runs it, and returns its stdout, or null when the
/// process could not start or exited nonzero.
Future<String?> _runProbe(
  String executable,
  List<String> arguments,
  Map<String, String> environment,
) async {
  try {
    final result = await Process.run(
      resolveExecutableOnPath(executable, environment),
      arguments,
      runInShell: false,
      environment: environment,
      includeParentEnvironment: true,
    );
    if (result.exitCode != 0) return null;
    return result.stdout as String;
  } on ProcessException {
    return null;
  }
}

/// How a Cargo project run was resolved before spawning the build.
class _CargoRunPlan {
  const _CargoRunPlan._({
    this.arguments = const [],
    this.standalone = false,
    this.cancelled = false,
    this.error,
  });

  const _CargoRunPlan.cargo(List<String> arguments)
    : this._(arguments: arguments);

  const _CargoRunPlan.standalone() : this._(standalone: true);

  const _CargoRunPlan.cancelled() : this._(cancelled: true);

  const _CargoRunPlan.error(String message) : this._(error: message);

  /// Explicit `cargo run` arguments when a runnable target matched.
  final List<String> arguments;

  /// True when the manifest is valid but the source is not a runnable target.
  final bool standalone;

  /// True when cancellation interrupted metadata resolution.
  final bool cancelled;

  /// Actionable diagnostic; when set, no build must start.
  final String? error;
}
