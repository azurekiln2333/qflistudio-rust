import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;
import 'package:qfli_rust/rust_runner.dart';
import 'package:qfli_studio_core/services/studio_profile.dart';

/// Process-wiring tests for the Cargo route.
///
/// A small Dart program is compiled into a throwaway executable that imitates
/// `cargo` (and `rustc`) enough to prove the real `_RustRunSession` wiring:
/// metadata stdout stays private, the exact `--bin`/`--example` selector is
/// used, a metadata failure never starts a build, and cancellation during
/// metadata returns 130. It is injected through the existing
/// `cargoExecutable`/`rustcExecutable`/`environment` parameters, so no
/// test-only production seam is added.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late Directory scratch;
  late String fakeCargo;
  late String fakeRustc;
  late String fakeProgram;
  late Directory project;

  const fakeToolchainSource = r'''
import 'dart:convert';
import 'dart:io';

Future<void> main(List<String> args) async {
  final mode = Platform.environment['QFLI_FAKE_MODE'] ?? 'ok';
  if (args.isNotEmpty && args.first == 'metadata') {
    if (mode == 'metadata-fail') {
      stderr.writeln('error: could not read manifest');
      await stderr.flush();
      exit(101);
    }
    if (mode == 'metadata-hang') {
      // Announce readiness on stderr *before* blocking, flushed, so the test
      // cancels only once this metadata process is genuinely live.
      stderr.writeln('FAKE_METADATA_READY');
      await stderr.flush();
      stdout.write('{"packages":');
      await stdout.flush();
      await Future<void>.delayed(const Duration(seconds: 30));
      stdout.write('[]}');
      await stdout.flush();
      exit(0);
    }
    stdout.writeln(Platform.environment['QFLI_FAKE_METADATA'] ?? '{}');
    await stdout.flush();
    exit(0);
  }
  if (args.isNotEmpty && args.first == 'run') {
    // Echo the exact selector on stderr so run selection is observable.
    stderr.writeln('CARGO_RUN ${args.join(' ')}');
    stdout.writeln('program-output');
    await stdout.flush();
    exit(0);
  }
  stderr.writeln('unexpected fake cargo args: $args');
  exit(2);
}
''';

  const fakeRustcSource = r'''
import 'dart:io';

Future<void> main(List<String> args) async {
  // `rustc <src> ... -o <output>`: copy a real prebuilt stand-in program.
  if (args.contains('-vV')) {
    stdout.writeln('host: x86_64-unknown-linux-gnu');
    exit(0);
  }
  if (args.contains('--print') && args.contains('sysroot')) {
    stdout.writeln('/fake/sysroot');
    exit(0);
  }
  final outputIndex = args.indexOf('-o');
  if (outputIndex < 0 || outputIndex + 1 >= args.length) exit(2);
  final output = args[outputIndex + 1];
  final program = Platform.environment['QFLI_FAKE_PROGRAM'];
  if (program == null || !File(program).existsSync()) {
    stderr.writeln('fake rustc: missing QFLI_FAKE_PROGRAM');
    exit(3);
  }
  // The copy is a genuine executable on every platform, so the standalone
  // rustc route runs it for real instead of failing to spawn a text script.
  File(program).copySync(output);
  exit(0);
}
''';

  const fakeProgramSource = r'''
import 'dart:io';

Future<void> main(List<String> args) async {
  // Stand-in for a program produced by the standalone rustc route.
  stdout.writeln('standalone-output');
  await stdout.flush();
  exit(0);
}
''';

  Future<String> compile(String source, String name) async {
    final sourceFile = File(p.join(scratch.path, '$name.dart'));
    sourceFile.writeAsStringSync(source);
    final output = p.join(
      scratch.path,
      Platform.isWindows ? '$name.exe' : name,
    );
    final result = await Process.run(_dartExecutable(), [
      'compile',
      'exe',
      sourceFile.path,
      '-o',
      output,
    ]);
    expect(
      result.exitCode,
      0,
      reason: 'Failed to compile $name: ${result.stdout}\n${result.stderr}',
    );
    return output;
  }

  setUpAll(() async {
    scratch = Directory.systemTemp.createTempSync('qfli_fake_toolchain_');
    fakeCargo = await compile(fakeToolchainSource, 'fake_cargo');
    fakeRustc = await compile(fakeRustcSource, 'fake_rustc');
    fakeProgram = await compile(fakeProgramSource, 'fake_program');
  });

  tearDownAll(() {
    if (scratch.existsSync()) scratch.deleteSync(recursive: true);
  });

  setUp(() {
    project = Directory.systemTemp.createTempSync('qfli_cargo_wiring_');
    File(p.join(project.path, 'Cargo.toml')).writeAsStringSync('''
[package]
name = "fake_pkg"
version = "0.1.0"
edition = "2021"

[[bin]]
name = "primary"
path = "src/main.rs"

[[bin]]
name = "secondary"
path = "src/alt.rs"
''');
    Directory(p.join(project.path, 'src')).createSync(recursive: true);
    File(
      p.join(project.path, 'src', 'main.rs'),
    ).writeAsStringSync('fn main() {}');
    File(
      p.join(project.path, 'src', 'alt.rs'),
    ).writeAsStringSync('fn main() {}');
  });

  tearDown(() {
    if (project.existsSync()) project.deleteSync(recursive: true);
  });

  String metadataFor(List<(String, String)> binaries) {
    final targets = binaries
        .map(
          (binary) => {
            'name': binary.$1,
            'src_path': p.join(project.path, binary.$2),
            'kind': ['bin'],
            'crate_types': ['bin'],
          },
        )
        .toList();
    return jsonEncode({
      'packages': [
        {
          'name': 'fake_pkg',
          'manifest_path': p.join(project.path, 'Cargo.toml'),
          'targets': targets,
        },
      ],
    });
  }

  RustProgramRunner runner({Map<String, String>? environment}) =>
      RustProgramRunner(
        cargoExecutable: fakeCargo,
        rustcExecutable: fakeRustc,
        // The standalone rustc fake copies this prebuilt program so the
        // generated artifact is a genuine executable on every platform.
        environment: {'QFLI_FAKE_PROGRAM': fakeProgram, ...?environment},
      );

  Future<(int, List<String>, List<String>)> run(
    String entry, {
    Map<String, String>? environment,
  }) async {
    final result = await runner(
      environment: environment,
    ).run(projectPath: project.path, entryFile: p.join(project.path, entry));
    expect(result, isNotNull);
    final output = result!.stdout.toList();
    final errors = result.stderr.toList();
    final code = await result.exitCode;
    return (code, await output, await errors);
  }

  test(
    'selects the matching alternate bin and keeps metadata stdout private',
    () async {
      final (code, output, errors) = await run(
        'src/alt.rs',
        environment: {
          'QFLI_FAKE_METADATA': metadataFor([
            ('primary', 'src/main.rs'),
            ('secondary', 'src/alt.rs'),
          ]),
        },
      );
      expect(code, 0, reason: errors.join('\n'));
      expect(output, ['program-output']);
      final cargoLine = errors.singleWhere(
        (line) => line.startsWith('CARGO_RUN'),
      );
      expect(cargoLine, contains('--bin secondary'));
      expect(cargoLine, isNot(contains('--bin primary')));
      // The metadata JSON must never leak onto the user streams.
      expect(errors.join('\n'), isNot(contains('packages')));
      expect(output.join('\n'), isNot(contains('packages')));
    },
  );

  test('selects an example with --example', () async {
    Directory(p.join(project.path, 'examples')).createSync(recursive: true);
    File(
      p.join(project.path, 'examples', 'demo.rs'),
    ).writeAsStringSync('fn main() {}');
    final metadata = jsonEncode({
      'packages': [
        {
          'name': 'fake_pkg',
          'manifest_path': p.join(project.path, 'Cargo.toml'),
          'targets': [
            {
              'name': 'demo',
              'src_path': p.join(project.path, 'examples', 'demo.rs'),
              'kind': ['example'],
              'crate_types': ['bin'],
            },
          ],
        },
      ],
    });
    final (code, _, errors) = await run(
      'examples/demo.rs',
      environment: {'QFLI_FAKE_METADATA': metadata},
    );
    expect(code, 0, reason: errors.join('\n'));
    final cargoLine = errors.singleWhere(
      (line) => line.startsWith('CARGO_RUN'),
    );
    expect(cargoLine, contains('--example demo'));
  });

  test('a metadata failure never starts cargo run', () async {
    final (code, output, errors) = await run(
      'src/alt.rs',
      environment: {'QFLI_FAKE_MODE': 'metadata-fail'},
    );
    expect(code, kProgramNotRunExitCode);
    expect(output, isEmpty);
    expect(errors.join('\n'), contains('cargo metadata'));
    expect(errors.where((line) => line.startsWith('CARGO_RUN')), isEmpty);
  });

  test('an unregistered source uses standalone rustc, not cargo run', () async {
    final (code, output, errors) = await run(
      'src/alt.rs',
      environment: {
        'QFLI_FAKE_METADATA': metadataFor([('primary', 'src/main.rs')]),
      },
    );
    expect(code, 0, reason: errors.join('\n'));
    expect(output, ['standalone-output']);
    expect(errors.where((line) => line.startsWith('CARGO_RUN')), isEmpty);
  });

  test(
    'a non-runnable registered source fails instead of running another target',
    () async {
      final metadata = jsonEncode({
        'packages': [
          {
            'name': 'fake_pkg',
            'manifest_path': p.join(project.path, 'Cargo.toml'),
            'targets': [
              {
                'name': 'primary',
                'src_path': p.join(project.path, 'src', 'main.rs'),
                'kind': ['bin'],
                'crate_types': ['bin'],
              },
              {
                'name': 'fake_pkg',
                'src_path': p.join(project.path, 'src', 'lib.rs'),
                'kind': ['lib'],
                'crate_types': ['lib'],
              },
            ],
          },
        ],
      });
      File(p.join(project.path, 'src', 'lib.rs')).writeAsStringSync('');
      final (code, output, errors) = await run(
        'src/lib.rs',
        environment: {'QFLI_FAKE_METADATA': metadata},
      );
      expect(code, kProgramNotRunExitCode);
      expect(output, isEmpty);
      expect(errors.join('\n'), contains('不可运行'));
      expect(errors.where((line) => line.startsWith('CARGO_RUN')), isEmpty);
    },
  );

  test('malformed metadata fails instead of falling back', () async {
    final (code, output, errors) = await run(
      'src/alt.rs',
      environment: {'QFLI_FAKE_METADATA': '{"packages": "nope"}'},
    );
    expect(code, kProgramNotRunExitCode);
    expect(output, isEmpty);
    expect(errors.join('\n'), contains('无法解析'));
    expect(errors.where((line) => line.startsWith('CARGO_RUN')), isEmpty);
  });

  test(
    'cancellation during metadata returns 130',
    () async {
      File(
        p.join(project.path, 'src', 'alt.rs'),
      ).writeAsStringSync('fn main() {}');
      final result =
          await runner(environment: {'QFLI_FAKE_MODE': 'metadata-hang'}).run(
            projectPath: project.path,
            entryFile: p.join(project.path, 'src/alt.rs'),
          );
      expect(result, isNotNull);
      // Consume both streams live so the ready marker is observed as soon as
      // it is flushed, and so an unread pipe cannot stall metadata.
      final outputLines = <String>[];
      final errorLines = <String>[];
      final ready = Completer<void>();
      final outDone = result!.stdout.listen(outputLines.add).asFuture<void>();
      final errDone = result.stderr.listen((line) {
        errorLines.add(line);
        if (line == 'FAKE_METADATA_READY' && !ready.isCompleted) {
          ready.complete();
        }
      }).asFuture<void>();
      // Wait for the deterministic marker the fake cargo writes and flushes
      // *before* blocking, then cancel the live metadata process.
      await ready.future.timeout(const Duration(seconds: 20));
      await result.cancel!().timeout(const Duration(seconds: 20));
      expect(await result.exitCode, 130);
      await Future.wait([outDone, errDone]);
      expect(errorLines.where((line) => line.startsWith('CARGO_RUN')), isEmpty);
      // Metadata JSON must never leak onto either user stream.
      expect(outputLines.join('\n'), isNot(contains('packages')));
      expect(errorLines.join('\n'), isNot(contains('packages')));
    },
    timeout: const Timeout(Duration(seconds: 40)),
  );
}

String _dartExecutable() {
  final executable = Platform.isWindows ? 'dart.exe' : 'dart';
  final candidates = <String>[
    if (Platform.environment['FLUTTER_ROOT'] case final root?
        when root.isNotEmpty)
      p.join(root, 'bin', 'cache', 'dart-sdk', 'bin', executable),
    // The Flutter-bundled SDK often sits three levels above the test runner.
    p.join(
      p.dirname(p.dirname(Platform.resolvedExecutable)),
      'cache',
      'dart-sdk',
      'bin',
      executable,
    ),
  ];
  for (final candidate in candidates) {
    if (File(candidate).existsSync()) return candidate;
  }
  return executable;
}
