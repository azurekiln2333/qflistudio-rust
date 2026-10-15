import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:path/path.dart' as p;
import 'package:qfli_studio_core/services/studio_profile.dart';
import 'package:qfli_studio_core/terminal/shell/command_parser.dart';
import 'package:qfli_studio_core/terminal/shell/sandbox_shell_backend.dart';

import 'rust_runner.dart';

/// Rust toolchain hook for the shared terminal.
///
/// Claims the real Rust command-line tools and routes them through the same
/// execution paths the editor's Run button uses:
///
///   * `rust run <file.rs>` / `rust <file.rs>` — runs one Rust source through
///     [RustProgramRunner]. On desktop that is a real `rustc`/`cargo`
///     invocation; on Android/iOS/HarmonyOS it is the packaged upstream
///     rustc/Miri engine. Either way the program's stdout, stderr and exit
///     status reach the terminal unchanged.
///   * `rustc ...` / `cargo ...` — spawns the real command-line tool where one
///     exists (desktop). A platform without an exec-able compiler does **not**
///     pretend to have one: it reports an honest, non-zero status instead.
///
/// Returns `false` for anything else (including compound shell lines) so the
/// sandbox backend keeps its own honest diagnostics.
Future<bool> rustTerminalCommandDelegate(
  SandboxShellBackend backend,
  String command, {
  RustProgramRunner? runner,
  bool? offline,
  Map<String, String>? environment,
}) async {
  // The sandbox always classifies Windows path separators literally, so
  // tokenize the same way; otherwise `C:\dir` would be mangled.
  const policy = EscapePolicy.backslashLiteral;
  if (CommandParser.classify(command, escapePolicy: policy) !=
      CommandSyntax.simple) {
    return false;
  }
  final parsed = CommandParser.tokenize(command, escapePolicy: policy);
  if (!parsed.ok || parsed.tokens.isEmpty) return false;
  final tokens = parsed.tokens.map((token) => token.text).toList();
  final tool = tokens.first;
  if (tool != 'rust' && tool != 'rustc' && tool != 'cargo') return false;

  // Effective offline policy: an explicit value wins; otherwise the active
  // product profile decides, so an offline product inherits the policy without
  // every call site repeating it.
  final isOffline = offline ?? (StudioProfile.current?.offlineOnly == true);

  if (tool == 'rust') {
    return _runRustSource(
      backend,
      tokens.sublist(1),
      runner ?? RustProgramRunner(offline: offline),
    );
  }
  return _runTool(
    backend,
    tool,
    tokens.sublist(1),
    offline: isOffline,
    environment: environment,
  );
}

/// `rust [run] <file.rs>` — runs one source through the packaged/desktop
/// runtime, with the current source resolved inside the sandbox root.
Future<bool> _runRustSource(
  SandboxShellBackend backend,
  List<String> arguments,
  RustProgramRunner runner,
) async {
  final title = 'rust ${arguments.join(' ')}'.trim();
  final operands = <String>[];
  for (final argument in arguments) {
    if (argument == 'run' && operands.isEmpty) continue;
    if (argument.startsWith('-')) {
      await _fail(backend, title, 'rust: 暂不支持选项：$argument（请使用 rust run <文件.rs>）');
      return true;
    }
    operands.add(argument);
  }
  if (operands.length != 1) {
    await _fail(backend, title, 'rust: 需要且仅需要一个 .rs 源文件。');
    return true;
  }

  final String entry;
  try {
    entry = backend.resolveSandboxPath(operands.single);
  } on SandboxEscapeException {
    await _fail(backend, title, 'rust: 不能越出沙盒目录：${operands.single}');
    return true;
  }
  if (p.extension(entry).toLowerCase() != '.rs') {
    await _fail(backend, title, 'rust: 只能运行 .rs 源文件：${operands.single}');
    return true;
  }

  // The runner validates the source/project paths and owns the title; forward
  // its result transparently so stdout/stderr/exit stay the program's own.
  final result = await runner.run(
    projectPath: backend.cwd,
    entryFile: entry,
  );
  if (result == null) return false;
  await backend.runStreams(
    title: result.title,
    stdout: result.stdout,
    stderr: result.stderr,
    exitCode: result.exitCode,
    cancel: result.cancel,
  );
  return true;
}

/// Cargo subcommands that require the network.
///
/// An offline product must refuse them up front with a clear message rather
/// than letting Cargo attempt a fetch and fail with a confusing transport
/// error (or, worse, hang waiting for a registry).
const Set<String> _networkCargoCommands = {
  'login',
  'logout',
  'publish',
  'search',
  'install',
  'uninstall',
  'info',
  'owner',
  'add',
  'remove',
  'update',
  'upgrade',
  'yank',
  'fetch',
};

/// Global Cargo options that take a following value, so the subcommand scan
/// does not mistake that value for the subcommand.
const Set<String> _cargoGlobalValueOptions = {
  '--color',
  '--config',
  '-Z',
  '-C',
  '--manifest-path',
  '--target-dir',
};

/// Flags that make a raw command read its input from stdin.
///
/// The terminal attaches no interactive stdin, so a reading form would block
/// forever. It is rejected with an explicit message instead of hanging. `-`
/// alone is the conventional standalone form (`rustc -`, `cargo ... -`).
bool _readsStdin(String tool, List<String> arguments) =>
    tool == 'rustc' && arguments.contains('-');

/// The Cargo subcommand, skipping leading global options.
///
/// Handles forms such as `cargo -v --color never search serde`, where the
/// subcommand is not the first argument, so an offline product still refuses
/// networked operations instead of letting the option ordering hide them.
String _cargoSubcommand(List<String> arguments) {
  var index = 0;
  while (index < arguments.length) {
    final argument = arguments[index];
    if (argument == '--') {
      index++;
      break;
    }
    if (!argument.startsWith('-')) break;
    // `--key=value` needs no separate skip; a bare value option consumes the
    // next token.
    if (!argument.contains('=') &&
        _cargoGlobalValueOptions.contains(argument)) {
      index += 2;
      continue;
    }
    index++;
  }
  return index < arguments.length ? arguments[index] : '';
}

/// Minimal GNU linker fallback flags for a raw tool, honouring user overrides.
///
/// Shares [resolveGnuLinkerFallbackFlags] with the editor runner so the
/// bundled Windows GNU toolchain (which ships `rust-lld` but no `gcc`) can link
/// from the terminal too. Returns an empty list when the caller configured its
/// own linker/rustflags or a Cargo configuration file exists.
Future<List<String>> _rawLinkerFlags({
  required String tool,
  required Map<String, String> environment,
  required String workingDirectory,
  required String? projectPath,
}) async {
  if (hasRustLinkerEnvironmentOverride(environment)) return const <String>[];
  if (projectPath != null &&
      await hasCargoLinkerConfiguration(projectPath, environment)) {
    return const <String>[];
  }
  return resolveGnuLinkerFallbackFlags(
    rustcExecutable: tool == 'cargo'
        ? (environment['CARGO_BUILD_RUSTC'] ?? 'rustc')
        : tool,
    environment: environment,
    workingDirectory: workingDirectory,
  );
}

/// `rustc ...` / `cargo ...` — spawns the real command-line tool when the host
/// allows exec-ing one.
Future<bool> _runTool(
  SandboxShellBackend backend,
  String tool,
  List<String> arguments, {
  required bool offline,
  Map<String, String>? environment,
}) async {
  final title = '$tool ${arguments.join(' ')}'.trim();

  if (_readsStdin(tool, arguments)) {
    await _fail(
      backend,
      title,
      '$tool: 当前终端不提供交互式标准输入，无法编译来自 stdin 的源码。'
      '请把源码保存为 .rs 文件后再编译。',
    );
    return true;
  }

  if (!_hasCliToolchain) {
    // Mobile/embedded platforms ship a runtime engine, not a compiler CLI.
    // Report the truth (127) instead of faking a version or a success.
    await _fail(
      backend,
      title,
      '$tool: 当前平台没有可执行的 Rust 命令行工具链。'
      '移动端请使用「rust run <文件.rs>」运行已打包的真实 Miri 运行时。',
    );
    return true;
  }

  if (offline && tool == 'cargo') {
    final subcommand = _cargoSubcommand(arguments);
    if (_networkCargoCommands.contains(subcommand)) {
      await _fail(
        backend,
        title,
        'cargo $subcommand: 当前离线版禁止联网的 Cargo 操作。'
        '请使用已在本地缓存中的依赖（cargo build/run/test 等）。',
      );
      return true;
    }
  }

  // The bundled Windows GNU toolchain has no gcc, so raw cargo/rustc must get
  // the same rust-lld fallback the editor runner uses. Explicit user flags and
  // Cargo configuration keep precedence (the helpers return empty then).
  final childEnvironment = <String, String>{
    if (environment != null) ...environment,
    if (offline && tool == 'cargo') 'CARGO_NET_OFFLINE': 'true',
  };
  final linkerFlags = await _rawLinkerFlags(
    tool: tool,
    environment: childEnvironment,
    workingDirectory: backend.cwd,
    projectPath: tool == 'cargo' ? backend.cwd : null,
  );
  if (linkerFlags.isNotEmpty) {
    if (tool == 'rustc') {
      arguments = [...arguments, ...linkerFlags];
    } else {
      // Cargo only accepts rustflags through the environment/CLI global option
      // it understands; encoded flags are the documented transport.
      childEnvironment['CARGO_ENCODED_RUSTFLAGS'] = linkerFlags.join('\u001f');
    }
  }
  if (offline && tool == 'cargo') {
    // Prepended so a later `--config net.offline=false` cannot silently
    // re-enable the network for this invocation.
    arguments = ['--offline', ...arguments];
  }

  final Process process;
  try {
    // Resolve against the effective environment's PATH so a prepended
    // toolchain is honoured on Windows, where a bare name would otherwise be
    // resolved against the parent process' PATH.
    final effectiveEnvironment = {
      ...Platform.environment,
      ...childEnvironment,
    };
    process = await Process.start(
      resolveExecutableOnPath(tool, effectiveEnvironment),
      arguments,
      workingDirectory: backend.cwd,
      runInShell: false,
      environment: childEnvironment.isEmpty ? null : effectiveEnvironment,
      includeParentEnvironment: true,
    );
  } on ProcessException catch (error) {
    await _fail(
      backend,
      title,
      '无法启动 ${error.executable}：${error.message}。请检查 Rust 工具链与 PATH。',
    );
    return true;
  }

  // No writer is attached to this command, so close stdin immediately. Without
  // this, a tool that polls stdin (rustc on `-`, cargo prompts) would wait
  // forever even though nothing will ever be typed into it.
  try {
    await process.stdin.close();
  } on IOException {
    // The tool may already have exited without reading stdin.
  }

  await backend.runStreams(
    title: title,
    stdout: process.stdout
        .transform(const Utf8Decoder(allowMalformed: true))
        .transform(const LineSplitter()),
    stderr: process.stderr
        .transform(const Utf8Decoder(allowMalformed: true))
        .transform(const LineSplitter()),
    exitCode: process.exitCode,
    // Cancel must take the whole tree: `cargo` spawns `rustc`/the linker as
    // grandchildren, and killing only the direct child leaves them running.
    cancel: () => terminateRustProcessTree(process),
  );
  return true;
}

/// Emits one honest failure line with [kProgramNotRunExitCode].
Future<void> _fail(
  SandboxShellBackend backend,
  String title,
  String message,
) => backend.runStreams(
  title: title,
  stdout: const Stream<String>.empty(),
  stderr: Stream<String>.value(message),
  exitCode: Future<int>.value(kProgramNotRunExitCode),
);

/// Whether a real `rustc`/`cargo` CLI can be exec-ed on this host.
///
/// Desktop only. Android, iOS and HarmonyOS embed the runtime engine but do not
/// permit the app to exec a compiler CLI, so those platforms report the honest
/// unsupported status instead of a fabricated one.
bool get _hasCliToolchain {
  if (Platform.isAndroid || Platform.isIOS) return false;
  final os = Platform.operatingSystem;
  return os == 'windows' || os == 'linux' || os == 'macos';
}
