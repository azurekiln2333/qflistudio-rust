import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;
import 'package:qfli_rust/rust_project_store.dart';
import 'package:qfli_rust/rust_content_repository.dart';
import 'package:qfli_rust/rust_runner.dart';
import 'package:qfli_studio_core/models/tutorial.dart';
import 'package:qfli_studio_core/content/local_content_adapter.dart';
import 'package:qfli_studio_core/services/code_import_service.dart';
import 'package:qfli_studio_core/services/project_templates.dart';
import 'package:qfli_studio_core/services/runner_service.dart';

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

  test('package names avoid Windows device target basenames', () {
    for (final name in [
      'CON',
      'prn',
      'Aux',
      'NUL',
      'COM1',
      'com9',
      'LPT1',
      'lpt9',
    ]) {
      expect(cargoPackageName(name), 'rust_${name.toLowerCase()}');
    }
    expect(cargoPackageName('COM0'), 'com0');
    expect(cargoPackageName('con_demo'), 'con_demo');
    expect(cargoPackageName('Console'), 'console');
  });

  test(
    'a device display name imports and builds an offline Cargo binary',
    () async {
      const example = ExampleCode(
        id: 'rust-import-device-name',
        type: 'rust',
        title: 'Local Rust example',
        summary: 'An imported display name must not become a device filename.',
        code: 'fn main() { println!("device-name-safe"); }',
        output: 'device-name-safe\n',
      );
      await store.load();
      final result = await store.createProjectFromExample(
        name: 'CON',
        example: example,
        location: workspace.path,
        fileName: 'custom.rs',
      );
      expect(result.error, isNull);
      final project = result.project!;
      expect(project.name, 'CON');
      final manifest = File(p.join(project.path, 'Cargo.toml'));
      expect(await manifest.readAsString(), contains('name = "rust_con"'));
      final build = await Process.run('cargo', [
        'build',
        '--offline',
        '--quiet',
        '--manifest-path',
        manifest.path,
      ], environment: await _cargoEnvironment());
      expect(build.exitCode, 0, reason: '${build.stderr}');
      final executable = p.join(
        project.path,
        'target',
        'debug',
        Platform.isWindows ? 'rust_con.exe' : 'rust_con',
      );
      final run = await Process.run(executable, []);
      expect(run.exitCode, 0, reason: '${run.stderr}');
      expect((run.stdout as String).replaceAll('\r\n', '\n'), example.output);
    },
    skip: !isCargoAvailable(),
  );

  test('imported Rust code configures Cargo for its custom entry', () async {
    const example = ExampleCode(
      id: 'rust-import',
      type: 'rust',
      title: 'Rust example',
      summary: 'Print a message.',
      code: 'fn main() { println!("imported"); }',
      output: 'imported',
    );
    final result = await store.createProjectFromExample(
      name: 'Named example',
      example: example,
      location: workspace.path,
      fileName: 'custom entry.rs',
    );
    expect(result.error, isNull);
    final root = result.project!.path;
    final entry = p.join(root, 'src', 'custom entry.rs');
    expect(await File(entry).readAsString(), example.code);
    expect(RunnerService.findEntry(root), entry);
    expect(await File(p.join(root, 'src', 'main.rs')).exists(), isFalse);
    final manifest = await File(p.join(root, 'Cargo.toml')).readAsString();
    expect(manifest, contains('[[bin]]'));
    expect(manifest, contains('path = "src/custom entry.rs"'));
    expect(await File(p.join(root, '.gitignore')).readAsString(), '/target/\n');

    final imported = await CodeImportService.importIntoProject(
      project: result.project!,
      example: example.copyWith(code: 'fn helper() {}'),
      fileName: 'helper.rs',
    );
    expect(await File(imported.path).readAsString(), 'fn helper() {}');
    expect(RunnerService.findEntry(root), entry);
    expect(await File(p.join(root, 'Cargo.toml')).readAsString(), manifest);
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

  test('bundle file name conflicts fail before creating a project', () async {
    store.dispose();
    store = RustProjectStore(
      storageFile: File(p.join(workspace.path, 'registry.json')),
      contentRepository: _ProjectRepository(),
    );
    const example = ExampleCode(
      id: 'rust-example-164',
      type: 'rust',
      title: 'Cargo example',
      summary: 'A complete offline Cargo project.',
      code: 'fn main() {}',
      output: '',
    );
    final result = await store.createProjectFromExample(
      name: 'File conflict',
      example: example,
      location: workspace.path,
      fileName: 'lib.rs',
    );
    expect(result.project, isNull);
    expect(result.error, isNotNull);
    expect(workspace.listSync().whereType<Directory>(), isEmpty);
  });

  test(
    'bundled Cargo import preserves edited entry and all paired files',
    () async {
      store.dispose();
      store = RustProjectStore(
        storageFile: File(p.join(workspace.path, 'registry.json')),
        contentRepository: _ProjectRepository(),
      );
      const edited = 'fn main() { println!("edited by learner"); }';
      const example = ExampleCode(
        id: 'rust-example-164',
        type: 'rust',
        title: 'Cargo example',
        summary: 'A complete offline Cargo project.',
        code: edited,
        output: 'edited by learner\n',
      );
      final result = await store.createProjectFromExample(
        name: 'My bundled project',
        example: example,
        location: workspace.path,
        fileName: 'custom.rs',
      );
      expect(result.error, isNull);
      final root = result.project!.path;
      expect(
        await File(p.join(root, 'src', 'custom.rs')).readAsString(),
        edited,
      );
      expect(await File(p.join(root, 'src', 'main.rs')).exists(), isFalse);
      expect(
        await File(p.join(root, 'src', 'lib.rs')).readAsString(),
        contains('pub fn total'),
      );
      expect(await File(p.join(root, 'tests', 'total.rs')).exists(), isTrue);
      final manifest = await File(p.join(root, 'Cargo.toml')).readAsString();
      expect(manifest, contains('name = "bundled_example"'));
      expect(manifest, contains('path = "src/custom.rs"'));
      expect(RunnerService.findEntry(root), p.join(root, 'src', 'custom.rs'));
    },
  );

  test('invalid bundles leave registry and existing projects unchanged', () async {
    store.dispose();
    final registry = File(p.join(workspace.path, 'registry.json'));
    store = RustProjectStore(storageFile: registry);
    await store.load();
    final existing = await store.createProject(
      name: 'Existing',
      location: workspace.path,
    );
    expect(existing.error, isNull);
    final baseline = await registry.readAsString();
    const example = ExampleCode(
      id: 'rust-example-164',
      type: 'rust',
      title: 'Cargo',
      summary: 'Complete project',
      code: 'fn main() {}',
      output: '',
    );
    for (final repository in [
      _ProjectRepository(
        extra: {'src/conflict': 'file', 'src/conflict/child.rs': 'file'},
      ),
      _ProjectRepository(
        extra: {'src/Foo/a.rs': 'file', 'src/foo/b.rs': 'file'},
      ),
      _ProjectRepository(
        manifest:
            '[package]\nname="sample"\nversion="0.1.0"\n[[bin]]\nname="sample"\npath="./src/main.rs"\n',
      ),
      _ProjectRepository(
        manifest:
            '[package]\nname="sample"\nversion="0.1.0"\n[[bin]]\nname="sample"\n',
      ),
    ]) {
      store.dispose();
      store = RustProjectStore(
        storageFile: registry,
        contentRepository: repository,
      );
      await store.load();
      final result = await store.createProjectFromExample(
        name: 'Rejected',
        example: example,
        location: workspace.path,
        fileName: 'custom.rs',
      );
      expect(result.project, isNull);
      expect(result.error, isNotNull);
      expect(await registry.readAsString(), baseline);
      expect(workspace.listSync().whereType<Directory>(), hasLength(1));
      expect(await Directory(existing.project!.path).exists(), isTrue);
    }
  });

  test(
    'companion IO failure rolls back only the newly owned project',
    () async {
      store.dispose();
      final registry = File(p.join(workspace.path, 'registry.json'));
      store = RustProjectStore(
        storageFile: registry,
        contentRepository: _ProjectRepository(),
      );
      await store.load();
      final existing = await store.createProject(
        name: 'Existing',
        location: workspace.path,
      );
      final before = await registry.readAsString();
      String? createdRoot;
      var blocked = false;
      void blockManifest() {
        if (blocked || store.projects.length < 2) return;
        blocked = true;
        final created = store.projects.singleWhere(
          (project) => project.id != existing.project!.id,
        );
        createdRoot = created.path;
        Directory(p.join(created.path, 'Cargo.toml')).createSync();
      }

      store.addListener(blockManifest);
      const example = ExampleCode(
        id: 'rust-example-164',
        type: 'rust',
        title: 'Cargo',
        summary: 'Complete project',
        code: 'fn main() {}',
        output: '',
      );
      final result = await store.createProjectFromExample(
        name: 'Failed write',
        example: example,
        location: workspace.path,
      );
      store.removeListener(blockManifest);
      expect(blocked, isTrue);
      expect(result.error, isNotNull);
      expect(result.project, isNull);
      expect(store.projects.map((project) => project.id), [
        existing.project!.id,
      ]);
      expect(await registry.readAsString(), before);
      expect(createdRoot, isNotNull);
      expect(await Directory(createdRoot!).exists(), isFalse);
      expect(await Directory(existing.project!.path).exists(), isTrue);
    },
  );

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

  test(
    'every real bundled Cargo project builds after custom-name import',
    () async {
      final repository = RustContentRepository(bundle: _DiskBundle());
      store.dispose();
      store = RustProjectStore(
        storageFile: File(p.join(workspace.path, 'registry.json')),
        contentRepository: repository,
      );
      await store.load();
      final catalog = await repository.load();
      final examples = await LocalContentAdapter.loadExamples(
        repository: repository,
        language: 'rust',
      );
      final environment = await _cargoEnvironment();
      final bundled = catalog.examples.where(
        (example) => example.inputFixtures.containsKey('cargoFiles'),
      );
      expect(bundled, isNotEmpty);
      for (final bundledExample in bundled) {
        final example = examples.singleWhere(
          (example) => example.id == bundledExample.id,
        );
        final result = await store.createProjectFromExample(
          name: example.id,
          example: example,
          location: workspace.path,
          fileName: 'custom.rs',
        );
        expect(result.error, isNull, reason: example.id);
        final root = result.project!.path;
        expect(
          await File(p.join(root, 'src/custom.rs')).readAsString(),
          example.code,
          reason: example.id,
        );
        expect(RunnerService.findEntry(root), p.join(root, 'src', 'custom.rs'));
        expect(await File(p.join(root, 'src/main.rs')).exists(), isFalse);
        final build = await Process.run('cargo', [
          'build',
          '--offline',
          '--quiet',
          '--workspace',
          '--all-targets',
          '--manifest-path',
          p.join(root, 'Cargo.toml'),
        ], environment: environment);
        expect(build.exitCode, 0, reason: '${example.id}: ${build.stderr}');
      }
    },
    skip: !isCargoAvailable(),
    timeout: const Timeout(Duration(minutes: 10)),
  );
}

class _DiskBundle extends CachingAssetBundle {
  @override
  Future<String> loadString(String key, {bool cache = true}) =>
      File(key).readAsString();
  @override
  Future<ByteData> load(String key) => throw UnimplementedError();
}

Future<Map<String, String>?> _cargoEnvironment() async {
  if (!Platform.isWindows ||
      Platform.environment.containsKey('RUSTFLAGS') ||
      Platform.environment.containsKey('CARGO_ENCODED_RUSTFLAGS')) {
    return null;
  }
  final version = await Process.run('rustc', ['-vV']);
  final host = RegExp(
    r'^host: (\S+)\r?$',
    multiLine: true,
  ).firstMatch(version.stdout as String)?.group(1);
  if (host == null || !host.endsWith('-pc-windows-gnu')) return null;
  final sysroot = (await Process.run('rustc', [
    '--print',
    'sysroot',
  ])).stdout.toString().trim();
  final linker = p.join(sysroot, 'lib/rustlib', host, 'bin/rust-lld.exe');
  if (!File(linker).existsSync()) return null;
  return {
    'CARGO_ENCODED_RUSTFLAGS': [
      '-C',
      'linker-flavor=ld.lld',
      '-C',
      'linker=$linker',
      '-C',
      'link-self-contained=yes',
    ].join('\u001f'),
  };
}

class _ProjectRepository extends RustContentRepository {
  _ProjectRepository({this.extra = const {}, this.manifest});
  final Map<String, String> extra;
  final String? manifest;
  @override
  Future<RustExampleProject?> projectForExample(
    String id,
  ) async => RustExampleProject.fromJson({
    'Cargo.toml':
        manifest ??
        '[package]\nname = "bundled_example"\nversion = "0.1.0"\nedition = "2021"\n',
    'src/main.rs': 'fn main() { println!("catalog original"); }',
    'src/lib.rs': 'pub fn total() -> i32 { 42 }',
    'tests/total.rs':
        '#[test]\nfn total() { assert_eq!(bundled_example::total(), 42); }',
    ...extra,
  });
}

bool isCargoAvailable() {
  try {
    return Process.runSync('cargo', ['--version']).exitCode == 0;
  } on ProcessException {
    return false;
  }
}
