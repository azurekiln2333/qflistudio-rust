import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;
import 'package:qfli_rust/rust_project_store.dart';
import 'package:qfli_rust/rust_runner.dart';
import 'package:qfli_studio_core/services/project_templates.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late Directory workspace;
  late RustProjectStore store;

  setUp(() {
    workspace = Directory.systemTemp.createTempSync('qfli_rust_project_test');
    store = RustProjectStore(
      storageFile: File(p.join(workspace.path, 'registry.json')),
    );
  });

  tearDown(() async {
    store.dispose();
    if (await workspace.exists()) await workspace.delete(recursive: true);
  });

  test(
    'Rust project creates a Cargo manifest and ignores build output',
    () async {
      final result = await store.createProject(
        name: 'Hello Rust',
        location: workspace.path,
        template: ProjectTemplate.rust,
      );
      expect(result.error, isNull);
      final root = result.project!.path;
      expect(await File(p.join(root, 'src', 'main.rs')).exists(), isTrue);
      expect(
        await File(p.join(root, 'Cargo.toml')).readAsString(),
        contains('name = "hello_rust"'),
      );
      expect(
        await File(p.join(root, '.gitignore')).readAsString(),
        '/target/\n',
      );
    },
  );

  test('package names remain valid for Unicode and leading digits', () async {
    expect(cargoPackageName('123 Rust'), 'rust_123_rust');
    expect(cargoPackageName('中文项目'), matches(RegExp(r'^rust_[0-9a-f]{8}$')));
    expect(cargoPackageName('项目 A'), matches(RegExp(r'^a_[0-9a-f]{8}$')));
    expect(cargoPackageName('中文项目'), isNot(cargoPackageName('其他项目')));
  });

  test('empty projects do not receive Rust files', () async {
    final result = await store.createProject(
      name: 'Empty',
      location: workspace.path,
    );
    expect(result.error, isNull);
    expect(
      await File(p.join(result.project!.path, 'Cargo.toml')).exists(),
      isFalse,
    );
  });

  test('importing an existing Rust directory does not rewrite it', () async {
    final existing = Directory(p.join(workspace.path, 'existing'));
    await Directory(p.join(existing.path, 'src')).create(recursive: true);
    await File(
      p.join(existing.path, 'src', 'main.rs'),
    ).writeAsString('fn main() {}');

    final result = await store.addExisting(existing.path);
    expect(result.error, isNull);
    expect(await File(p.join(existing.path, 'Cargo.toml')).exists(), isFalse);
    expect(await File(p.join(existing.path, '.gitignore')).exists(), isFalse);
  });

  test(
    'new Rust project compiles and executes through Cargo',
    () async {
      final result = await store.createProject(
        name: '中文 Rust',
        location: workspace.path,
        template: ProjectTemplate.rust,
      );
      expect(result.error, isNull);
      final project = result.project!;
      final metadata = await Process.run('cargo', [
        'metadata',
        '--no-deps',
        '--format-version',
        '1',
        '--manifest-path',
        p.join(project.path, 'Cargo.toml'),
      ]);
      expect(metadata.exitCode, 0, reason: '${metadata.stderr}');
      final packages =
          (jsonDecode(metadata.stdout as String)
                  as Map<String, dynamic>)['packages']
              as List;
      expect(
        (packages.single as Map<String, dynamic>)['name'],
        cargoPackageName('中文 Rust'),
      );

      final run = await const RustProgramRunner().run(
        projectPath: project.path,
        entryFile: p.join(project.path, 'src', 'main.rs'),
      );
      expect(run, isNotNull);
      final stdout = run!.stdout.toList();
      final stderr = run.stderr.toList();
      expect(await run.exitCode, 0, reason: (await stderr).join('\n'));
      expect(await stdout, ['Hello, QFLIStudio+!']);
    },
    skip: !isCargoAvailable(),
  );
}

bool isCargoAvailable() {
  try {
    return Process.runSync('cargo', ['--version']).exitCode == 0;
  } on ProcessException {
    return false;
  }
}
