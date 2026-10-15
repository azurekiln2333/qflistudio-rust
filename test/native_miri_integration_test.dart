import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;
import 'package:qfli_rust/native_miri_runner.dart';
import 'package:qfli_rust/rust_runner.dart';
import 'package:qfli_studio_core/services/studio_profile.dart';

void main() {
  final library = Platform.environment['QFLI_MIRI_LIBRARY'];
  final sysroot = Platform.environment['QFLI_MIRI_SYSROOT'];
  final backend = Platform.environment['QFLI_MIRI_BACKEND'];
  final available =
      library != null &&
      sysroot != null &&
      File(library).existsSync() &&
      Directory(sysroot).existsSync();
  late Directory project;
  late String entry;

  NativeMiriProgramRunner runner({
    int maxBasicBlocks = 10000000,
    int maxOutputBytes = 1024 * 1024,
    int maxGuestMemoryBytes = 64 * 1024 * 1024,
  }) => NativeMiriProgramRunner(
    libraryPath: library!,
    sysrootPath: sysroot!,
    backendPath: backend,
    maxBasicBlocks: maxBasicBlocks,
    maxOutputBytes: maxOutputBytes,
    maxGuestMemoryBytes: maxGuestMemoryBytes,
  );

  void write(String source) => File(entry).writeAsStringSync(source);

  Future<(int, List<String>, List<String>)> run(
    ProgramRunner programRunner,
  ) async {
    final result = await programRunner.run(
      projectPath: project.path,
      entryFile: entry,
    );
    expect(result, isNotNull);
    final output = result!.stdout.toList();
    final errors = result.stderr.toList();
    final code = await result.exitCode;
    return (code, await output, await errors);
  }

  group(
    'real native rustc/Miri sessions',
    () {
      setUp(() {
        project = Directory.systemTemp.createTempSync('qfli_miri_integration_');
        entry = p.join(project.path, 'main.rs');
      });
      tearDown(() => project.deleteSync(recursive: true));

      test(
        'executes modules, generics, borrowing and standard-library containers',
        () async {
          write(
            await File('native/fixtures/modules_generics.rs').readAsString(),
          );
          final (code, output, errors) = await run(
            RustProgramRunner(
              executionMode: RustExecutionMode.embedded,
              embeddedRunner: runner(),
            ),
          );
          expect(code, 0, reason: errors.join('\n'));
          expect(output, ['total=12']);
          expect(errors, ['items=3']);
        },
      );

      test('returns both output channels and the guest exit code', () async {
        write('''
fn main() {
    println!("ready");
    eprintln!("warning");
    std::process::exit(23);
}
''');
        final (code, output, errors) = await run(runner());
        expect(code, 23);
        expect(output, ['ready']);
        expect(errors, ['warning']);
      });

      test(
        'compiler diagnostics do not replay a previous successful result',
        () async {
          write('fn main() { println!("first run"); }');
          final engine = runner();
          final (firstCode, firstOutput, firstErrors) = await run(engine);
          expect(firstCode, 0, reason: firstErrors.join('\n'));
          expect(firstOutput, ['first run']);
          write('fn main() { let value = ; }');
          final (code, output, errors) = await run(engine);
          expect(code, 1);
          expect(output, isEmpty);
          expect(errors.join('\n'), contains('error'));
        },
      );

      test('supplies input.txt bytes and sends EOF when absent', () async {
        write('''
use std::io::{self, Read};
fn main() {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input).unwrap();
    println!("{}", if input.is_empty() { "eof" } else { input.trim() });
}
''');
        final (emptyCode, emptyOutput, emptyErrors) = await run(runner());
        expect(emptyCode, 0, reason: emptyErrors.join('\n'));
        expect(emptyOutput, ['eof']);
        File(
          p.join(project.path, 'input.txt'),
        ).writeAsStringSync('from input\n');
        final (code, output, errors) = await run(runner());
        expect(code, 0, reason: errors.join('\n'));
        expect(output, ['from input']);
      });

      test('bounded execution returns the execution-limit code', () async {
        write('fn main() { loop { std::hint::black_box(1); } }');
        final (code, _, errors) = await run(runner(maxBasicBlocks: 10000));
        expect(code, 124, reason: errors.join('\n'));
      });

      test(
        'bounded output is streamed without exceeding the native cap',
        () async {
          write('fn main() { for _ in 0..10000 { println!("abcdefghijk"); } }');
          final (code, output, errors) = await run(
            runner(maxOutputBytes: 1024),
          );
          expect(code, 124, reason: errors.join('\n'));
          expect(output.join('\n').length, lessThanOrEqualTo(1024));
        },
      );

      test('guest-memory limits retain the native limit result', () async {
        write(
          'fn main() { let data = vec![1u8; 8 * 1024 * 1024]; println!("{}", data.len()); }',
        );
        final (code, _, errors) = await run(
          runner(maxGuestMemoryBytes: 1024 * 1024),
        );
        expect(code, 124, reason: errors.join('\n'));
      });

      test(
        'cancellation completes before destroy and allows a subsequent session',
        () async {
          write(
            'fn main() { println!("started"); loop { std::hint::black_box(1); } }',
          );
          final engine = runner(maxBasicBlocks: 1000000000);
          final result = await engine.run(
            projectPath: project.path,
            entryFile: entry,
          );
          final started = Completer<void>();
          final output = result!.stdout.map((line) {
            if (line == 'started' && !started.isCompleted) started.complete();
            return line;
          }).toList();
          final errors = result.stderr.toList();
          try {
            await started.future.timeout(const Duration(seconds: 30));
          } finally {
            await result.cancel!().timeout(const Duration(seconds: 30));
          }
          expect(await result.exitCode, 130);
          expect(await output, contains('started'));
          await errors;
          write('fn main() { println!("after cancellation"); }');
          final (code, nextOutput, nextErrors) = await run(engine);
          expect(code, 0, reason: nextErrors.join('\n'));
          expect(nextOutput, ['after cancellation']);
        },
        timeout: const Timeout(Duration(minutes: 2)),
      );
    },
    skip: available
        ? false
        : 'Matching native library/sysroot are not available',
  );
}
