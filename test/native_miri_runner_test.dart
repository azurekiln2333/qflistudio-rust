import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;
import 'package:qfli_rust/ohos_miri_runner.dart';
import 'package:qfli_rust/rust_runner.dart';
import 'package:qfli_studio_core/services/studio_profile.dart';

void main() {
  late Directory project;
  late String entry;
  late String sysroot;

  setUp(() {
    project = Directory.systemTemp.createTempSync('qfli_miri_runner_');
    entry = p.join(project.path, 'main.rs');
    File(entry).writeAsStringSync('fn main() { println!("native only"); }');
    sysroot = (Directory(p.join(project.path, 'sysroot'))..createSync()).path;
  });

  tearDown(() => project.deleteSync(recursive: true));

  Future<List<String>> errors(ProgramRunner runner) async {
    final result = await runner.run(
      projectPath: project.path,
      entryFile: entry,
    );
    expect(result, isNotNull);
    final output = result!.stdout.toList();
    final errors = result.stderr.toList();
    expect(await result.exitCode, kProgramNotRunExitCode);
    expect(await output, isEmpty);
    return errors;
  }

  test(
    'OHOS compatibility constructor uses the native session implementation',
    () {
      final NativeMiriProgramRunner runner = OhosMiriProgramRunner(
        sysrootPath: sysroot,
      );
      expect(runner.libraryPath, 'libqfli_miri.so');
    },
  );

  test(
    'embedded execution does not compile when its native library is missing',
    () async {
      final messages = await errors(
        RustProgramRunner(
          executionMode: RustExecutionMode.embedded,
          embeddedRunner: NativeMiriProgramRunner(
            sysrootPath: sysroot,
            libraryPath: p.join(project.path, 'missing_native_library'),
          ),
        ),
      );
      expect(messages.join('\n'), contains('missing_native_library'));
    },
  );

  test('invalid backend fails before attempting to load the adapter', () async {
    final messages = await errors(
      NativeMiriProgramRunner(
        sysrootPath: sysroot,
        backendPath: p.join(project.path, 'missing_backend'),
      ),
    );
    expect(messages.join('\n'), contains('missing_backend'));
  });

  test(
    'invalid execution limits fail before attempting native calls',
    () async {
      final messages = await errors(
        NativeMiriProgramRunner(sysrootPath: sysroot, maxBasicBlocks: 0),
      );
      expect(messages.join('\n'), contains('资源限制无效'));
    },
  );

  test('non-Rust files are returned to the shared runner', () async {
    final result = await NativeMiriProgramRunner(sysrootPath: sysroot).run(
      projectPath: project.path,
      entryFile: p.join(project.path, 'main.py'),
    );
    expect(result, isNull);
  });
}
