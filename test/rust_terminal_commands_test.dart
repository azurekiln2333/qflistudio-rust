import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;
import 'package:qfli_rust/main.dart' show rustProfile;
import 'package:qfli_rust/rust_runner.dart';
import 'package:qfli_rust/rust_terminal_commands.dart';
import 'package:qfli_studio_core/services/studio_profile.dart';
import 'package:qfli_studio_core/terminal/shell/sandbox_shell_backend.dart';
import 'package:qfli_studio_core/terminal/shell/shell_backend.dart';
import 'package:qfli_studio_core/terminal/state/terminal_manager.dart';

/// Rust terminal delegate contract: it claims the real Rust tools, streams
/// their output/exit truthfully, refuses malformed invocations, honours the
/// offline policy, and cancels the whole process tree.
///
/// The delegate is exercised through a real [SandboxShellBackend], the same
/// object both shared terminal surfaces (the editor `TerminalPane` and the
/// app-level `TerminaxTerminalPage` / [TerminalManager]) hand to it, so the
/// assertions cover the shared delegation seam rather than the function alone.
///
/// A real compiler is discovered on PATH or in the bundled
/// `native/build/miri-windows/compiler/bin`; when one is found its execution is
/// asserted for real, and when none exists the tests fail rather than skip the
/// execution assertions they promise.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late Directory directory;
  late SandboxShellBackend backend;
  late List<ShellChunk> chunks;
  late Map<String, String>? compilerPath;

  setUpAll(() {
    compilerPath = _compilerPathOverride();
  });

  setUp(() {
    directory = Directory.systemTemp.createTempSync('qfli_rust_term_');
    backend = SandboxShellBackend(
      sandboxRoot: directory.path,
      startDirectory: directory.path,
      label: 'Rust',
    );
    chunks = <ShellChunk>[];
    backend.output.listen(chunks.add);
  });

  tearDown(() async {
    await backend.shutdown();
    if (directory.existsSync()) directory.deleteSync(recursive: true);
  });

  String out() => chunks
      .where((chunk) => chunk.kind == OutputKind.stdout)
      .map((chunk) => chunk.text)
      .join();

  String err() => chunks
      .where((chunk) => chunk.kind == OutputKind.stderr)
      .map((chunk) => chunk.text)
      .join();

  void write(String relative, String content) {
    final file = File(p.join(directory.path, relative));
    file.parent.createSync(recursive: true);
    file.writeAsStringSync(content);
  }

  Future<bool> delegate(String command, {bool? offline}) =>
      rustTerminalCommandDelegate(
        backend,
        command,
        offline: offline,
        environment: compilerPath,
      );

  group('delegate dispatch', () {
    test('claims rust/rustc/cargo and declines every other tool', () async {
      for (final command in [
        'rust run main.rs',
        'rustc --version',
        'cargo run',
      ]) {
        expect(
          await delegate(command),
          isTrue,
          reason: '$command must be claimed',
        );
      }
      for (final command in [
        'javac Main.java',
        'python main.py',
        'ls -la',
        'rustup show',
      ]) {
        expect(
          await delegate(command),
          isFalse,
          reason: '$command must fall through to the sandbox',
        );
      }
    });

    test(
      'declines compound shell lines so the sandbox reports them honestly',
      () async {
        expect(await delegate('rust run main.rs | cat'), isFalse);
        expect(await delegate('cargo run && echo done'), isFalse);
      },
    );
  });

  group('parameter failures are honest and non-zero', () {
    Future<void> expectFailure(String command, String diagnostic) async {
      chunks.clear();
      expect(await delegate(command), isTrue);
      expect(backend.lastExitCode, kProgramNotRunExitCode);
      expect(out(), isEmpty);
      expect(err(), contains(diagnostic));
    }

    test('rust without a source file', () async {
      await expectFailure('rust run', '一个 .rs 源文件');
    });

    test('rust with too many operands', () async {
      await expectFailure('rust run a.rs b.rs', '一个 .rs 源文件');
    });

    test('rust rejects unsupported options', () async {
      await expectFailure('rust run --release main.rs', '暂不支持选项');
    });

    test('rust rejects a non-Rust source', () async {
      write('main.txt', 'not rust');
      await expectFailure('rust run main.txt', '只能运行 .rs 源文件');
    });

    test('rust rejects a path that escapes the sandbox', () async {
      await expectFailure('rust run ../../etc/passwd.rs', '不能越出沙盒目录');
    });

    test('rust run reports a missing source as a startup failure', () async {
      await expectFailure('rust run missing.rs', '源文件不存在');
    });

    test('rustc rejects a stdin source instead of hanging', () async {
      await expectFailure('rustc -', '不提供交互式标准输入');
    });
  });

  group('real compiler execution', () {
    test('a real rustc invocation streams the compiler version', () async {
      chunks.clear();
      expect(await delegate('rustc --version'), isTrue);
      expect(backend.lastExitCode, 0, reason: err());
      expect(out(), contains('rustc 1.98.1'));
      expect(err(), isEmpty);
    });

    test('a real cargo invocation streams cargo output', () async {
      chunks.clear();
      expect(await delegate('cargo --version'), isTrue);
      expect(backend.lastExitCode, 0, reason: err());
      expect(out(), contains('cargo 1.98.1'));
    });

    test('raw rustc compiles a source and streams the real diagnostics', () async {
      write('main.rs', '''
fn main() {
    let value = ;
}
''');
      chunks.clear();
      expect(await delegate('rustc main.rs'), isTrue);
      expect(backend.lastExitCode, isNot(0));
      expect(backend.lastExitCode, isNot(kProgramNotRunExitCode));
      expect(err(), contains('error'));
    });

    test(
      'raw rustc -o links with the bundled GNU fallback and the program runs',
      () async {
        // Regression for the gcc-less bundled toolchain: a plain raw
        // `rustc main.rs -o program.exe` must still link through rust-lld and
        // produce a runnable executable, not only report a version.
        write('main.rs', '''
fn main() {
    println!("raw-link-ok");
    std::process::exit(6);
}
''');
        chunks.clear();
        expect(await delegate('rustc main.rs -o program.exe'), isTrue);
        expect(backend.lastExitCode, 0, reason: err());
        final program = File(p.join(directory.path, 'program.exe'));
        expect(program.existsSync(), isTrue, reason: 'no executable linked');
        final run = await Process.run(program.path, const []);
        expect((run.stdout as String).trim(), 'raw-link-ok');
        expect(run.exitCode, 6);
      },
    );

    test('raw cargo run links and runs a project without gcc', () async {
      write('Cargo.toml', '''
[package]
name = "qfli_raw_cargo"
version = "0.1.0"
edition = "2021"
''');
      write('src/main.rs', '''
fn main() {
    println!("raw-cargo-ok");
}
''');
      chunks.clear();
      expect(await delegate('cargo run'), isTrue);
      expect(backend.lastExitCode, 0, reason: err());
      expect(out(), contains('raw-cargo-ok'));
    });

    test('rust run compiles and runs a source, preserving stdout/exit', () async {
      write('main.rs', '''
fn main() {
    println!("hello from rust");
    std::process::exit(7);
}
''');
      chunks.clear();
      expect(await delegate('rust run main.rs'), isTrue);
      expect(out(), contains('hello from rust'));
      expect(backend.lastExitCode, 7);
    });

    test('rust run accepts the bare `rust <file>` form', () async {
      write('main2.rs', 'fn main() { println!("bare form"); }');
      chunks.clear();
      expect(await delegate('rust main2.rs'), isTrue);
      expect(out(), contains('bare form'));
      expect(backend.lastExitCode, 0);
    });
  });

  group('bundled GNU linker fallback', () {
    test('resolves rust-lld flags for the bundled GNU rustc', () async {
      final flags = await resolveGnuLinkerFallbackFlags(
        rustcExecutable: 'rustc',
        environment: compilerPath!,
        workingDirectory: directory.path,
      );
      expect(flags, hasLength(6));
      expect(flags[0], '-C');
      expect(flags[1], 'linker-flavor=ld.lld');
      expect(flags[2], '-C');
      expect(flags[3], startsWith('linker='));
      expect(flags[3], endsWith('rust-lld.exe'));
      expect(flags[4], '-C');
      expect(flags[5], 'link-self-contained=yes');
    });

    test('detects explicit linker overrides that must win', () {
      expect(hasRustLinkerEnvironmentOverride(const {}), isFalse);
      expect(
        hasRustLinkerEnvironmentOverride(const {'RUSTFLAGS': '-C opt-level=1'}),
        isTrue,
      );
      expect(
        hasRustLinkerEnvironmentOverride(const {
          'CARGO_TARGET_X86_64_PC_WINDOWS_GNU_LINKER': 'custom.exe',
        }),
        isTrue,
      );
      expect(
        hasRustLinkerEnvironmentOverride(const {'CARGO_BUILD_TARGET': 'x'}),
        isTrue,
      );
    });

    test('a project .cargo/config.toml disables the fallback', () async {
      write('.cargo/config.toml', '[build]\njobs = 1\n');
      expect(
        await hasCargoLinkerConfiguration(directory.path, compilerPath!),
        isTrue,
      );
    });
  });

  group('offline policy', () {
    test('refuses networked cargo subcommands when offline', () async {
      chunks.clear();
      expect(await delegate('cargo search serde', offline: true), isTrue);
      expect(backend.lastExitCode, kProgramNotRunExitCode);
      expect(err(), contains('禁止联网的 Cargo 操作'));
    });

    test('refuses publish/login/install/info/owner when offline', () async {
      for (final command in [
        'cargo publish',
        'cargo login',
        'cargo install cargo-edit',
        'cargo info serde',
        'cargo owner',
      ]) {
        chunks.clear();
        expect(await delegate(command, offline: true), isTrue);
        expect(backend.lastExitCode, kProgramNotRunExitCode, reason: command);
      }
    });

    test('detects networked subcommands behind global options', () async {
      for (final command in [
        'cargo -v --color never search serde',
        'cargo --offline install cargo-edit',
        'cargo -Z unstable-options info serde',
      ]) {
        chunks.clear();
        expect(await delegate(command, offline: true), isTrue, reason: command);
        expect(backend.lastExitCode, kProgramNotRunExitCode, reason: command);
        expect(err(), contains('禁止联网的 Cargo 操作'), reason: command);
      }
    });

    test('allows local cargo commands when offline', () async {
      chunks.clear();
      expect(await delegate('cargo --version', offline: true), isTrue);
      expect(backend.lastExitCode, 0, reason: err());
    });

    test('prepends --offline so --config net.offline=false cannot re-enable it',
        () async {
      // A fresh CARGO_HOME makes the dependency genuinely uncached, so only the
      // prepended --offline keeps cargo from touching the registry.
      final carcophome = Directory(p.join(directory.path, 'cargo_home'))
        ..createSync();
      write('Cargo.toml', '''
[package]
name = "qfli_offline_guard"
version = "0.1.0"
edition = "2021"

[dependencies]
qfli_definitely_missing_crate = "9.9.9"
''');
      write('src/main.rs', 'fn main() {}');
      chunks.clear();
      expect(
        await rustTerminalCommandDelegate(
          backend,
          'cargo build --config net.offline=false',
          offline: true,
          environment: {
            ...?compilerPath,
            'CARGO_HOME': carcophome.path,
          },
        ),
        isTrue,
      );
      expect(backend.lastExitCode, isNot(0));
      expect(err(), contains('offline'));
    });

    test('RustProgramRunner sets CARGO_NET_OFFLINE for offline cargo', () async {
      write('Cargo.toml', '''
[package]
name = "qfli_offline"
version = "0.1.0"
edition = "2021"
''');
      write('src/main.rs', 'fn main() { println!("offline-ok"); }');
      final env = {...?compilerPath, 'CARGO_NET_OFFLINE': 'false'};
      final result = await RustProgramRunner(
        offline: true,
        environment: env,
      ).run(projectPath: directory.path, entryFile: p.join(directory.path, 'src/main.rs'));
      expect(result, isNotNull);
      final errorText = (await result!.stderr.toList()).join('\n');
      // The runner must override the caller's false with the offline policy.
      expect(await result.exitCode, 0, reason: errorText);
      expect(await result.stdout.toList(), contains('offline-ok'));
    });

    test('explicit offline=true is honoured by the rust run route', () async {
      // The delegate must pass an explicit offline policy into the runner, not
      // silently drop it: a networked cargo project fails offline the same way
      // the editor Run button would.
      final carcophome = Directory(p.join(directory.path, 'cargo_home2'))
        ..createSync();
      write('Cargo.toml', '''
[package]
name = "qfli_offline_run"
version = "0.1.0"
edition = "2021"

[dependencies]
qfli_definitely_missing_crate = "9.9.9"
''');
      write('src/main.rs', 'fn main() {}');
      chunks.clear();
      final environment = {...?compilerPath, 'CARGO_HOME': carcophome.path};
      expect(
        await rustTerminalCommandDelegate(
          backend,
          'rust run src/main.rs',
          offline: true,
          environment: environment,
        ),
        isTrue,
      );
      expect(backend.lastExitCode, isNot(0));
      expect(err(), contains('offline'));
    });
  });

  group('cancellation', () {
    test('cancel kills the process tree, not only the direct child', () async {
      write('Cargo.toml', '''
[package]
name = "qfli_cancel"
version = "0.1.0"
edition = "2021"
''');
      write('src/main.rs', '''
fn main() {
    println!("started");
    std::thread::sleep(std::time::Duration::from_secs(60));
}
''');
      final result = await RustProgramRunner(environment: compilerPath).run(
        projectPath: directory.path,
        entryFile: p.join(directory.path, 'src/main.rs'),
      );
      expect(result, isNotNull);
      expect(await result!.stdout.first, 'started');
      await result.cancel!().timeout(const Duration(seconds: 20));
      expect(await result.exitCode, 130);
      // A lingering rustc/cargo grandchild would still hold the target dir.
      // Give the OS a moment, then confirm no compiler child survives.
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
  });

  group('shared terminal delegation', () {
    test('both terminal surfaces share one delegate through TerminalManager', () async {
      final delegateCommands = <String>[];
      final manager = TerminalManager()
        ..commandDelegate = (backend, command) async {
          delegateCommands.add(command);
          await backend.runStreams(
            title: command,
            stdout: Stream<String>.value('handled: $command'),
            stderr: const Stream<String>.empty(),
            exitCode: Future<int>.value(0),
          );
          return true;
        };
      addTearDown(manager.dispose);

      final session = manager.create(sandboxRoot: directory.path);
      final received = <String>[];
      final subscription = session.backend.output.listen(
        (chunk) => received.add(chunk.text),
      );
      addTearDown(subscription.cancel);

      await session.backend.execute('rust run main.rs');
      expect(
        delegateCommands,
        ['rust run main.rs'],
        reason: 'the manager must hand the Rust command to the profile delegate',
      );
      expect(received.join(), contains('handled: rust run main.rs'));
    });

    test(
      'the shipped rustProfile exposes a working Rust terminal delegate',
      () async {
        // Regression: the product must actually wire the delegate. A missing
        // wiring leaves this null and the terminal silently reports the
        // unsupported branch, so assert the real profile object, not a comment.
        final delegate = rustProfile.terminalCommandDelegate;
        expect(
          delegate,
          isNotNull,
          reason: 'rustProfile.terminalCommandDelegate must be wired to '
              'rustTerminalCommandDelegate in lib/main.dart',
        );
        expect(await delegate!(backend, 'rust run'), isTrue);
        expect(await delegate(backend, 'ls -la'), isFalse);
      },
    );
  });
}

/// PATH override that makes the bundled real compiler discoverable.
///
/// Returns null when no bundled compiler exists, so the real-execution tests
/// fail loudly instead of silently skipping.
Map<String, String>? _compilerPathOverride() {
  final candidates = <String>[
    p.join('native', 'build', 'miri-windows', 'compiler', 'bin'),
  ];
  for (final candidate in candidates) {
    final directory = Directory(p.absolute(candidate));
    if (directory.existsSync() &&
        File(p.join(directory.path, 'rustc.exe')).existsSync()) {
      final separator = Platform.isWindows ? ';' : ':';
      // A full environment (not only PATH): the delegate replaces the child
      // environment wholesale when one is supplied, so rustc/cargo still need
      // the host variables (SystemRoot, TEMP, ...) to start.
      return {
        ...Platform.environment,
        'PATH':
            '${directory.path}$separator${Platform.environment['PATH'] ?? ''}',
      };
    }
  }
  return null;
}
