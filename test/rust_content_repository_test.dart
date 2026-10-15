import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:qfli_rust/rust_content_repository.dart';
import 'package:qfli_studio_core/content/content_repository.dart';
import 'package:qfli_studio_core/content/content_validator.dart';
import 'package:qfli_studio_core/content/local_content_adapter.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test(
    'bundled curriculum has every complete paired lesson and example',
    () async {
      final bundle = _FileBundle();
      final repository = RustContentRepository(bundle: bundle);
      final catalog = await repository.load();
      final validation = ContentCatalogValidator.validate(
        catalog,
        enforceReleaseMinimum: true,
        requiredTypes: {'rust'},
        minimumEntriesPerType: 166,
      );
      expect(validation.issues, isEmpty);
      expect(catalog.tutorials, hasLength(166));
      expect(catalog.examples, hasLength(166));
      expect(
        catalog.tutorials.map((entry) => entry.title).toSet(),
        hasLength(166),
      );
      expect(
        catalog.examples.map((entry) => entry.code).toSet(),
        hasLength(166),
      );
      for (var index = 0; index < 166; index++) {
        final suffix = (index + 1).toString().padLeft(3, '0');
        final tutorial = catalog.tutorials[index];
        final example = catalog.examples[index];
        expect(tutorial.id, 'rust-tutorial-$suffix');
        expect(example.id, 'rust-example-$suffix');
        expect(tutorial.lessons, hasLength(1));
        final lesson = tutorial.lessons.single;
        expect(lesson.id, '${tutorial.id}-lesson');
        expect(example.sourceLessonId, lesson.id);
        expect(example.code, lesson.code);
        expect(example.expectedOutput, lesson.output);
        expect(lesson.objective, isNotEmpty);
        expect(lesson.pitfalls, isNotEmpty);
        expect(lesson.concepts.length, greaterThanOrEqualTo(2));
        expect(lesson.explain.length, greaterThanOrEqualTo(100));
        expect(lesson.exercises, hasLength(1));
        expect(lesson.exercises.single.answer, contains('fn main'));
      }
      expect(await repository.load(), same(catalog));
      expect(bundle.requested.toSet(), {
        RustContentRepository.tutorialAsset,
        RustContentRepository.exampleAsset,
      });
      expect(bundle.requested, hasLength(2));
    },
  );

  test(
    'shared product and language filters cannot return other products',
    () async {
      final repository = RustContentRepository(bundle: _FileBundle());
      expect(
        await repository.tutorials(
          filter: ContentFilter.forProduct('rustcore'),
        ),
        hasLength(166),
      );
      expect(
        await repository.examples(
          filter: const ContentFilter(language: 'java'),
        ),
        isEmpty,
      );
      final examples = await LocalContentAdapter.loadExamples(
        repository: repository,
        language: 'rust',
        productKey: 'rustcore',
      );
      expect(examples, hasLength(166));
      expect(examples.last.id, 'rust-example-166');
      final tutorial = await LocalContentAdapter.loadTutorial(
        repository: repository,
        language: 'rust',
        displayName: 'Rust',
        productKey: 'rustcore',
      );
      expect(tutorial!.chapters, hasLength(166));
      expect(tutorial.chapters.last.lessons.single.tasks, hasLength(1));
    },
  );

  test('an asset error is reported and a subsequent load can retry', () async {
    final bundle = _FileBundle()..fail = true;
    final repository = RustContentRepository(bundle: bundle);
    await expectLater(repository.load(), throwsA(isA<StateError>()));
    bundle.fail = false;
    expect((await repository.load()).examples, hasLength(166));
  });

  test('bundled project paths reject escape, metadata and duplicate names', () {
    for (final invalid in [
      '../outside.rs',
      '/absolute.rs',
      r'C:\outside.rs',
      'src/../../outside.rs',
      '.qfli/project.json',
      '.GIT/config',
      'target/main.rs',
      'src//bad.rs',
    ]) {
      expect(
        () => RustExampleProject.fromJson({
          'Cargo.toml': '[package]',
          'src/main.rs': 'fn main() {}',
          invalid: 'unsafe path',
        }),
        throwsFormatException,
        reason: invalid,
      );
    }
    expect(
      () => RustExampleProject.fromJson({
        'Cargo.toml': '[package]',
        'src/main.rs': 'fn main() {}',
        'src/MAIN.rs': 'duplicate',
      }),
      throwsFormatException,
    );
    expect(
      () => RustExampleProject.fromJson({'src/main.rs': 'fn main() {}'}),
      throwsFormatException,
    );
  });

  test(
    'project attachments resolve through stable IDs, without replacing code',
    () async {
      final bundle = _ProjectBundle();
      final repository = RustContentRepository(bundle: bundle);
      final project = await repository.projectForExample('rust-example-001');
      expect(project!.files['src/lib.rs'], contains('pub fn total'));
      expect(await repository.projectForExample('user-example'), isNull);
      expect(() => project.files['outside.rs'] = '', throwsUnsupportedError);
    },
  );
  test(
    'bundled files reject file/directory prefixes and directory case aliases',
    () {
      for (final extra in [
        {'src/conflict': 'file', 'src/conflict/child.rs': 'file'},
        {'src/Foo/a.rs': 'file', 'src/foo/b.rs': 'file'},
      ]) {
        expect(
          () => RustExampleProject.fromJson({
            'Cargo.toml': '[package]\nname="sample"\nversion="0.1.0"\n',
            'src/main.rs': 'fn main() {}',
            ...extra,
          }),
          throwsFormatException,
        );
      }
    },
  );

  test('custom Cargo entries reject aliased and implicit explicit targets', () {
    for (final bin in [
      '[[bin]]\nname="sample"\npath="./src/main.rs"\n',
      '[[bin]]\nname="sample"\n',
    ]) {
      final project = RustExampleProject.fromJson({
        'Cargo.toml': '[package]\nname="sample"\nversion="0.1.0"\n$bin',
        'src/main.rs': 'fn main() {}',
      });
      expect(
        () => project.manifestForEntry('src/custom.rs', 'display'),
        throwsFormatException,
      );
    }
    final canonical = RustExampleProject.fromJson({
      'Cargo.toml':
          '[package]\nname="sample"\nversion="0.1.0"\n[[bin]]\nname="sample"\npath="src/main.rs"\n',
      'src/main.rs': 'fn main() {}',
    });
    expect(
      canonical.manifestForEntry('src/custom.rs', 'display'),
      contains('path = "src/custom.rs"'),
    );
  });
}

class _FileBundle extends CachingAssetBundle {
  final requested = <String>[];
  bool fail = false;

  @override
  Future<String> loadString(String key, {bool cache = true}) async {
    requested.add(key);
    if (fail) throw StateError('catalog unavailable');
    return File(key).readAsString();
  }

  @override
  Future<ByteData> load(String key) => throw UnimplementedError();
}

class _ProjectBundle extends CachingAssetBundle {
  @override
  Future<String> loadString(String key, {bool cache = true}) async =>
      jsonEncode({
        'schemaVersion': 1,
        'entries': key == RustContentRepository.tutorialAsset
            ? []
            : [
                {
                  'id': 'rust-example-001',
                  'language': 'rust',
                  'type': 'rust',
                  'inputFixtures': {
                    'cargoFiles': jsonEncode({
                      'Cargo.toml':
                          '[package]\nname = "fixture"\nversion = "0.1.0"\n',
                      'src/main.rs': 'fn main() { println!("original"); }',
                      'src/lib.rs': 'pub fn total() -> i32 { 42 }',
                    }),
                  },
                },
              ],
      });

  @override
  Future<ByteData> load(String key) => throw UnimplementedError();
}
