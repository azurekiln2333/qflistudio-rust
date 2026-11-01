import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';
import 'package:qfli_studio_core/editor/editor_controller.dart';
import 'package:qfli_studio_core/editor/editor_page.dart';
import 'package:qfli_studio_core/editor/project_history.dart';
import 'package:qfli_studio_core/i18n/studio_localizations.dart';
import 'package:qfli_studio_core/models/project.dart';
import 'package:qfli_studio_core/models/tutorial.dart';
import 'package:qfli_studio_core/pages/home_page.dart';
import 'package:qfli_studio_core/pages/local_content_pages.dart';
import 'package:qfli_studio_core/services/code_import_service.dart';
import 'package:qfli_studio_core/services/example_code_store.dart';
import 'package:qfli_studio_core/services/project_config.dart';
import 'package:qfli_studio_core/services/project_templates.dart';
import 'package:qfli_studio_core/services/runner_service.dart';
import 'package:qfli_studio_core/services/studio_profile.dart';
import 'package:qfli_studio_core/store/auth_store.dart';
import 'package:qfli_studio_core/store/project_store.dart';
import 'package:qfli_studio_core/store/settings_store.dart';
import 'package:qfli_studio_core/theme/app_theme.dart';
import 'package:qfli_studio_core/widgets/code_snippet.dart';
import 'package:re_editor/re_editor.dart';

const _lessonTitle = 'First Dart program';
const _exampleTitle = 'Editable Dart example';
const _lessonCode = "void main() {\n  print('lesson');\n}\n";
const _exampleCode = "void main() {\n  print('example');\n}\n";
const _editedCode = "void main() {\n  print('edited example');\n}\n";
const _example = ExampleCode(
  id: 'dart-example',
  type: 'dart',
  title: _exampleTitle,
  summary: 'Print a message.',
  code: _exampleCode,
  output: 'example',
);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory root;
  late Directory directory;
  late PathProviderPlatform originalPaths;
  StudioProfile? originalProfile;

  setUpAll(() async {
    root = await Directory.systemTemp.createTemp('qfli_content_import_');
    originalPaths = PathProviderPlatform.instance;
    PathProviderPlatform.instance = _TemporaryPaths(root.path);
  });

  setUp(() {
    for (final asset in ['tutorials', 'examples']) {
      rootBundle.evict('assets/content/$asset.json');
      rootBundle.evict('packages/qfli_studio_core/assets/content/$asset.json');
    }
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMessageHandler('flutter/assets', (message) async {
      if (message == null) return null;
      final key = utf8.decode(
        message.buffer.asUint8List(
          message.offsetInBytes,
          message.lengthInBytes,
        ),
      );
      final source = key.endsWith('assets/content/tutorials.json')
          ? _tutorialSource
          : key.endsWith('assets/content/examples.json')
          ? _exampleSource
          : null;
      return source == null
          ? null
          : ByteData.sublistView(Uint8List.fromList(utf8.encode(source)));
    });
    directory = root.createTempSync('case_');
    final defaults = File(p.join(root.path, 'examples.json'));
    if (defaults.existsSync()) defaults.deleteSync();
    originalProfile = StudioProfile.current;
    StudioProfile.current = const StudioProfile(
      id: 'dart',
      appTitle: StudioProductCatalog.dartWing,
      productKey: StudioProductCatalog.dartWingKey,
      templates: [ProjectTemplate.dart],
      isOffline: true,
    );
  });

  tearDown(() => StudioProfile.current = originalProfile);

  tearDownAll(() async {
    PathProviderPlatform.instance = originalPaths;
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMessageHandler('flutter/assets', null);
    await Future<void>.delayed(const Duration(milliseconds: 50));
    await root.delete(recursive: true);
  });

  group('real file imports', () {
    test(
      'project template determines the destination without changing its entry',
      () async {
        final original = File(p.join(directory.path, 'README.md'))
          ..writeAsStringSync('# Existing document');
        final project = Project.create(
          name: 'Notes',
          path: directory.path,
          type: 'markdown',
          language: 'Markdown',
        );
        final result = await CodeImportService.importIntoProject(
          project: project,
          example: _example,
          fileName: 'imported.dart',
        );
        expect(result.path, p.join(directory.path, 'imported.dart'));
        expect(await File(result.path).readAsString(), _exampleCode);
        expect(await original.readAsString(), '# Existing document');
        expect(Directory(p.join(directory.path, 'src')).existsSync(), isFalse);
      },
    );

    test(
      'failed registry writes do not leave a successfully registered project',
      () async {
        final registry = Directory(p.join(directory.path, 'registry.json'))
          ..createSync();
        final store = ProjectStore(storageFile: File(registry.path));
        addTearDown(store.dispose);
        await store.load();
        final result = await store.createProjectFromExample(
          name: 'Cannot register',
          location: directory.path,
          example: _example,
          fileName: 'entry.dart',
        );
        expect(result.error, isNotNull);
        expect(result.project, isNull);
        expect(store.projects, isEmpty);
        expect(registry.listSync(), isEmpty);
        expect(
          Directory(p.join(directory.path, 'dartProjects')).listSync(),
          isEmpty,
        );
      },
    );

    test(
      'closing a controller during a pending read cannot add or notify a tab',
      () async {
        final file = File(p.join(directory.path, 'pending.dart'))
          ..writeAsStringSync(_exampleCode);
        final controller = EditorController(
          project: Project.create(name: 'Pending', path: directory.path),
        );
        var notifications = 0;
        controller.addListener(() => notifications++);
        final opening = controller.openPath(file.path);
        controller.dispose();
        await opening;
        expect(notifications, 0);
        expect(controller.files, isEmpty);
      },
    );

    test(
      'customized existing-project import preserves the original entry',
      () async {
        final source = Directory(p.join(directory.path, 'src'))..createSync();
        final original = File(p.join(source.path, 'main.dart'))
          ..writeAsStringSync('existing entry');
        final project = Project.create(
          name: 'Existing',
          path: directory.path,
          type: 'dart',
          language: 'Dart',
        );
        final result = await CodeImportService.importIntoProject(
          project: project,
          example: _example,
          fileName: 'custom_example.dart',
        );
        expect(result.project, same(project));
        expect(result.path, p.join(source.path, 'custom_example.dart'));
        expect(await File(result.path).readAsString(), _exampleCode);
        expect(await original.readAsString(), 'existing entry');
      },
    );

    test(
      'new projects use a custom entry and remove generated default code',
      () async {
        final store = ProjectStore(
          storageFile: File(p.join(directory.path, 'registry.json')),
        );
        addTearDown(store.dispose);
        await store.load();
        final result = await store.createProjectFromExample(
          name: 'Custom Dart project',
          location: directory.path,
          example: _example,
          fileName: 'custom_entry.dart',
        );
        expect(result.error, isNull);
        final project = result.project!;
        final imported = File(p.join(project.path, 'src', 'custom_entry.dart'));
        expect(await imported.readAsString(), _exampleCode);
        expect(
          File(p.join(project.path, 'src', 'main.dart')).existsSync(),
          isFalse,
        );
        expect(
          ProjectConfig.read(project.path)?['entryFile'],
          p.join('src', 'custom_entry.dart'),
        );
        expect(RunnerService.findEntry(project.path), imported.path);
        expect(store.projects.single.id, project.id);
        final restored = ProjectStore(
          storageFile: File(p.join(directory.path, 'registry.json')),
        );
        addTearDown(restored.dispose);
        await restored.load();
        expect(restored.projects.single.path, project.path);
      },
    );

    test(
      'default entry imports remain compatible and web companion files survive',
      () async {
        final store = ProjectStore();
        addTearDown(store.dispose);
        final dart = await store.createProjectFromExample(
          name: 'Default Dart',
          location: directory.path,
          example: _example,
        );
        expect(dart.error, isNull);
        expect(
          await File(
            p.join(dart.project!.path, 'src', 'main.dart'),
          ).readAsString(),
          _exampleCode,
        );
        final web = await store.createProjectFromExample(
          name: 'Custom web',
          location: directory.path,
          example: const ExampleCode(
            id: 'html-example',
            type: 'html',
            title: 'Web example',
            summary: 'A web document.',
            code: '<h1>Imported</h1>',
            output: 'Imported',
          ),
          fileName: 'custom.html',
        );
        expect(web.error, isNull);
        expect(
          await File(
            p.join(web.project!.path, 'src', 'custom.html'),
          ).readAsString(),
          '<h1>Imported</h1>',
        );
        expect(
          File(p.join(web.project!.path, 'src', 'index.html')).existsSync(),
          isFalse,
        );
        expect(
          File(p.join(web.project!.path, 'src', 'style.css')).existsSync(),
          isTrue,
        );
        expect(
          File(p.join(web.project!.path, 'src', 'main.js')).existsSync(),
          isTrue,
        );
      },
    );

    test(
      'editor import writes the chosen filename without an unrelated main',
      () async {
        final result = await CodeImportService.openInEditor(
          example: _example,
          fileName: 'editor_entry.dart',
          location: directory.path,
        );
        expect(p.isWithin(directory.path, result.project.path), isTrue);
        expect(
          result.path,
          p.join(result.project.path, 'src', 'editor_entry.dart'),
        );
        expect(await File(result.path).readAsString(), _exampleCode);
        expect(
          File(p.join(result.project.path, 'src', 'main.dart')).existsSync(),
          isFalse,
        );
        expect(RunnerService.findEntry(result.project.path), result.path);
      },
    );

    test(
      'an unknown type still writes the actual source into a new project',
      () async {
        final store = ProjectStore();
        addTearDown(store.dispose);
        final example = ExampleCode(
          id: 'unknown',
          type: 'custom-language',
          title: 'Unknown language',
          summary: '',
          code: 'actual source',
          output: '',
        );
        final result = await store.createProjectFromExample(
          name: 'Unknown project',
          location: directory.path,
          example: example,
          fileName: 'entry.custom',
        );
        expect(result.error, isNull);
        expect(
          await File(
            p.join(result.project!.path, 'src', 'entry.custom'),
          ).readAsString(),
          example.code,
        );
      },
    );

    test(
      'invalid basenames cannot create a project or escape its directory',
      () async {
        final store = ProjectStore();
        addTearDown(store.dispose);
        for (final name in [
          '',
          '.',
          '..',
          '../escape.dart',
          r'..\escape.dart',
          'bad:name.dart',
          'bad\u0000.dart',
          'NUL.dart',
          'entry.dart.',
        ]) {
          expect(
            CodeImportService.isValidFileName(name),
            isFalse,
            reason: name,
          );
          await expectLater(
            store.createProjectFromExample(
              name: 'Rejected',
              location: directory.path,
              example: _example,
              fileName: name,
            ),
            throwsA(_importFailure(CodeImportFailure.invalidFileName)),
          );
        }
        expect(store.projects, isEmpty);
        expect(directory.listSync(), isEmpty);
      },
    );

    test(
      'conflicts preserve files and explicit replacement changes only the target',
      () async {
        final source = Directory(p.join(directory.path, 'src'))..createSync();
        final target = File(p.join(source.path, 'existing.dart'))
          ..writeAsStringSync('keep me');
        final untouched = File(p.join(source.path, 'main.dart'))
          ..writeAsStringSync('untouched');
        final project = Project.create(
          name: 'Existing',
          path: directory.path,
          type: 'dart',
        );
        await expectLater(
          CodeImportService.importIntoProject(
            project: project,
            example: _example,
            fileName: 'existing.dart',
          ),
          throwsA(_importFailure(CodeImportFailure.fileExists)),
        );
        expect(await target.readAsString(), 'keep me');
        await CodeImportService.importIntoProject(
          project: project,
          example: _example,
          fileName: 'existing.dart',
          overwrite: true,
        );
        expect(await target.readAsString(), _exampleCode);
        expect(await untouched.readAsString(), 'untouched');
      },
    );

    test(
      'missing, cloud, directory targets and blocked I/O cannot report success',
      () async {
        final unavailable = Project.create(
          name: 'Missing',
          path: p.join(directory.path, 'missing'),
          type: 'dart',
        );
        final cloud = Project.create(
          name: 'Cloud',
          path: directory.path,
          cloudId: 'remote-id',
          type: 'dart',
        );
        for (final project in [unavailable, cloud]) {
          await expectLater(
            CodeImportService.importIntoProject(
              project: project,
              example: _example,
              fileName: 'rejected.dart',
            ),
            throwsA(_importFailure(CodeImportFailure.projectUnavailable)),
          );
        }
        final project = Project.create(
          name: 'Blocked',
          path: directory.path,
          type: 'dart',
        );
        final blocker = File(p.join(directory.path, 'src'))
          ..writeAsStringSync('block');
        await expectLater(
          CodeImportService.importIntoProject(
            project: project,
            example: _example,
            fileName: 'rejected.dart',
          ),
          throwsA(isA<FileSystemException>()),
        );
        expect(await blocker.readAsString(), 'block');
        await blocker.delete();
        final target = Directory(p.join(directory.path, 'src', 'rejected.dart'))
          ..createSync(recursive: true);
        await expectLater(
          CodeImportService.importIntoProject(
            project: project,
            example: _example,
            fileName: 'rejected.dart',
            overwrite: true,
          ),
          throwsA(
            anyOf(isA<CodeImportException>(), isA<FileSystemException>()),
          ),
        );
        expect(await target.exists(), isTrue);
        expect(target.listSync(), isEmpty);
      },
    );
  });

  group('saved examples', () {
    test(
      'default storage persists user edits and loads them once over bundled defaults',
      () async {
        final file = File(p.join(root.path, 'examples.json'));
        final store = ExampleCodeStore();
        addTearDown(store.dispose);
        await store.load(defaults: [_example]);
        await store.upsert(_example.copyWith(code: _editedCode));
        expect(_storedExampleCode(file, _example.id), _editedCode);
        await store.load(defaults: [_example]);
        expect(store.items.single.code, _editedCode);
        final restored = ExampleCodeStore();
        addTearDown(restored.dispose);
        await restored.load(defaults: [_example]);
        expect(restored.items.single.code, _editedCode);
        expect(restored.items.single.title, _example.title);
      },
    );

    test(
      'a disposed example store does not notify after a pending load',
      () async {
        final file = File(p.join(directory.path, 'examples.json'));
        await file.writeAsString(
          jsonEncode({
            'schemaVersion': 1,
            'examples': [
              {
                'id': _example.id,
                'type': _example.type,
                'title': _example.title,
                'summary': _example.summary,
                'code': _editedCode,
                'output': _example.output,
              },
            ],
          }),
        );
        final store = ExampleCodeStore(storageFile: file);
        var notifications = 0;
        store.addListener(() => notifications++);
        final loading = store.load(defaults: [_example]);
        store.dispose();
        await loading;
        expect(notifications, 0);
      },
    );
  });

  for (final examplesPage in [false, true]) {
    testWidgets(
      '${examplesPage ? 'example' : 'tutorial'} catalog hides code and detail offers both imports',
      (tester) async {
        final stores = await _createStores(tester, directory);
        await tester.pumpWidget(
          _app(_catalog(stores, examplesPage: examplesPage)),
        );
        final title = examplesPage ? _exampleTitle : _lessonTitle;
        await _waitFor(
          tester,
          () => find.text(title).evaluate().isNotEmpty,
          'catalog',
        );
        expect(find.text(_lessonCode), findsNothing);
        expect(find.text(_exampleCode), findsNothing);
        expect(find.byType(SelectableText), findsNothing);
        expect(find.byIcon(Icons.copy_outlined), findsNothing);
        expect(find.byType(Card), findsNothing);
        expect(
          Theme.of(tester.element(find.byType(ListTile).first)).useMaterial3,
          isTrue,
        );
        await tester.tap(find.text(title));
        await _settleRoute(tester);
        _expectDetail(tester, examplesPage: examplesPage);
        expect(tester.takeException(), isNull);
      },
    );
  }

  for (final examplesPage in [false, true]) {
    for (final intoProject in [false, true]) {
      testWidgets(
        'HomePage ${examplesPage ? 'example' : 'lesson'} imports to ${intoProject ? 'new project' : 'editor'} and opens custom file',
        (tester) async {
          final stores = await _createStores(tester, directory);
          await _homeDetail(tester, stores, examplesPage: examplesPage);
          if (examplesPage) {
            await tester.enterText(find.byType(TextField), _editedCode);
            await tester.pump();
          }
          final l10n = _l10n(tester);
          await _importDialog(tester, intoProject: intoProject);
          final fileName =
              '${examplesPage ? 'edited' : 'lesson'}_${intoProject ? 'project' : 'editor'}.dart';
          expect(_fileName(tester), 'main.dart');
          await tester.enterText(
            find.byKey(const ValueKey('import-file-name')),
            fileName,
          );
          if (intoProject) {
            await tester.enterText(
              find.byKey(const ValueKey('import-project-name')),
              'New ${examplesPage ? 'example' : 'lesson'} project',
            );
          }
          await tester.tap(find.text(l10n.importAndOpen));
          final code = examplesPage ? _editedCode : _lessonCode;
          await _expectOpenedEditor(
            tester,
            stores,
            code: code,
            fileName: fileName,
          );
          final editor = tester.widget<EditorPage>(find.byType(EditorPage));
          expect(stores.projects.projects.single.id, editor.project.id);
          expect(
            File(p.join(editor.project.path, 'src', 'main.dart')).existsSync(),
            isFalse,
          );
          expect(p.isWithin(root.path, editor.project.path), isTrue);
          expect(tester.takeException(), isNull);
        },
      );
    }
  }

  testWidgets(
    'existing-project import activates the new file over a restored session',
    (tester) async {
      final stores = await _createStores(tester, directory);
      final existing = await _existingProject(tester, stores, directory);
      await tester.runAsync(
        () => ProjectHistory.save(
          existing.path,
          cursors: {},
          openFiles: ['src/main.dart'],
          activeFile: 'src/main.dart',
        ),
      );
      final original = File(
        p.join(existing.path, 'src', 'main.dart'),
      ).readAsStringSync();
      await _homeDetail(tester, stores, examplesPage: true);
      await tester.enterText(find.byType(TextField), _editedCode);
      await _importDialog(tester, intoProject: true);
      await _chooseProject(tester, existing);
      await tester.enterText(
        find.byKey(const ValueKey('import-file-name')),
        'selected.dart',
      );
      await tester.tap(find.text(_l10n(tester).importAndOpen));
      await _expectOpenedEditor(
        tester,
        stores,
        code: _editedCode,
        fileName: 'selected.dart',
      );
      final editor = tester.widget<EditorPage>(find.byType(EditorPage));
      expect(editor.project.id, existing.id);
      expect(stores.projects.projects, hasLength(1));
      expect(
        File(p.join(existing.path, 'src', 'main.dart')).readAsStringSync(),
        original,
      );
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'replacement rejection keeps the file and confirmation imports and opens it',
    (tester) async {
      final stores = await _createStores(tester, directory);
      final existing = await _existingProject(tester, stores, directory);
      final file = File(p.join(existing.path, 'src', 'existing.dart'))
        ..writeAsStringSync('keep this source');
      await _homeDetail(tester, stores, examplesPage: false);
      await _importDialog(tester, intoProject: true);
      await _chooseProject(tester, existing);
      await tester.enterText(
        find.byKey(const ValueKey('import-file-name')),
        'existing.dart',
      );
      final l10n = _l10n(tester);
      await tester.tap(find.text(l10n.importAndOpen));
      await _waitFor(
        tester,
        () => find.text(l10n.replaceResource).evaluate().isNotEmpty,
        'replacement confirmation',
      );
      await tester.pump(const Duration(milliseconds: 400));
      expect(file.readAsStringSync(), 'keep this source');
      await tester.tap(find.text(l10n.cancel).last);
      await tester.pump(const Duration(milliseconds: 400));
      expect(file.readAsStringSync(), 'keep this source');
      expect(find.byType(EditorPage), findsNothing);
      expect(find.byKey(const ValueKey('import-file-name')), findsOneWidget);
      await tester.tap(find.text(l10n.importAndOpen));
      await _waitFor(
        tester,
        () => find.text(l10n.replaceResource).evaluate().isNotEmpty,
        'replacement retry',
      );
      await tester.pump(const Duration(milliseconds: 400));
      await tester.tap(find.text(l10n.replaceResource));
      await _expectOpenedEditor(
        tester,
        stores,
        code: _lessonCode,
        fileName: 'existing.dart',
      );
      expect(file.readAsStringSync(), _lessonCode);
      expect(
        tester.widget<EditorPage>(find.byType(EditorPage)).project.id,
        existing.id,
      );
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'invalid filename keeps the dialog open without creating a project',
    (tester) async {
      final stores = await _createStores(tester, directory);
      await _homeDetail(tester, stores, examplesPage: true);
      await _importDialog(tester, intoProject: true);
      await tester.enterText(
        find.byKey(const ValueKey('import-file-name')),
        '../escape.dart',
      );
      final l10n = _l10n(tester);
      await tester.tap(find.text(l10n.importAndOpen));
      await tester.pump();
      expect(find.text(l10n.invalidFileName), findsOneWidget);
      expect(find.byType(EditorPage), findsNothing);
      expect(stores.projects.projects, isEmpty);
      expect(
        root
            .listSync(recursive: true)
            .where((file) => p.basename(file.path) == 'escape.dart'),
        isEmpty,
      );
      await tester.tap(find.text(l10n.cancel));
      await tester.pump(const Duration(milliseconds: 400));
      expect(find.byType(AlertDialog), findsNothing);
    },
  );

  for (final intoProject in [false, true]) {
    testWidgets(
      '${intoProject ? 'project' : 'editor'} import cancellation has no file or navigation',
      (tester) async {
        final stores = await _createStores(tester, directory);
        await _homeDetail(tester, stores, examplesPage: intoProject);
        await _importDialog(tester, intoProject: intoProject);
        final fileName = 'cancel_${intoProject ? 'project' : 'editor'}.dart';
        await tester.enterText(
          find.byKey(const ValueKey('import-file-name')),
          fileName,
        );
        await tester.tap(find.text(_l10n(tester).cancel));
        await tester.pump(const Duration(milliseconds: 400));
        expect(find.byType(AlertDialog), findsNothing);
        expect(find.byType(EditorPage), findsNothing);
        expect(stores.projects.projects, isEmpty);
        expect(
          root
              .listSync(recursive: true)
              .where((file) => p.basename(file.path) == fileName),
          isEmpty,
        );
        _expectDetail(tester, examplesPage: intoProject);
      },
    );
  }

  testWidgets('real I/O failure remains an error and does not open an editor', (
    tester,
  ) async {
    final stores = await _createStores(tester, directory);
    final broken = Directory(p.join(directory.path, 'broken'))..createSync();
    File(p.join(broken.path, 'src')).writeAsStringSync('blocks a directory');
    final registered = await tester.runAsync(
      () => stores.projects.addExisting(broken.path),
    );
    expect(registered!.error, isNull);
    await _homeDetail(tester, stores, examplesPage: false);
    await _importDialog(tester, intoProject: true);
    await _chooseProject(tester, registered.project!);
    await tester.enterText(
      find.byKey(const ValueKey('import-file-name')),
      'failed.dart',
    );
    final l10n = _l10n(tester);
    await tester.tap(find.text(l10n.importAndOpen));
    await _waitFor(
      tester,
      () => find.textContaining(l10n.importFailed).evaluate().isNotEmpty,
      'I/O error',
    );
    expect(find.byType(EditorPage), findsNothing);
    expect(find.byKey(const ValueKey('import-file-name')), findsOneWidget);
    expect(
      File(p.join(broken.path, 'src')).readAsStringSync(),
      'blocks a directory',
    );
    expect(stores.projects.projects, hasLength(1));
    expect(find.text(l10n.projectImported), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('failed editor registration removes its imported files', (
    tester,
  ) async {
    final stores = await _createStores(tester, directory);
    final registry = File(p.join(directory.path, 'registry.json'));
    if (registry.existsSync()) registry.deleteSync();
    Directory(registry.path).createSync();
    await _homeDetail(tester, stores, examplesPage: true);
    await _importDialog(tester, intoProject: false);
    const fileName = 'failed_registration.dart';
    await tester.enterText(
      find.byKey(const ValueKey('import-file-name')),
      fileName,
    );
    final l10n = _l10n(tester);
    await tester.tap(find.text(l10n.importAndOpen));
    await _waitFor(
      tester,
      () => find.textContaining(l10n.importFailed).evaluate().isNotEmpty,
      'registration error',
    );
    expect(stores.projects.projects, isEmpty);
    expect(find.byType(EditorPage), findsNothing);
    expect(find.byKey(const ValueKey('import-file-name')), findsOneWidget);
    expect(
      root
          .listSync(recursive: true)
          .where((entry) => p.basename(entry.path) == fileName),
      isEmpty,
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('editable examples retain save and reset controls', (
    tester,
  ) async {
    final stores = await _createStores(tester, directory);
    final examples = ExampleCodeStore(
      storageFile: File(p.join(directory.path, 'examples.json')),
    );
    addTearDown(examples.dispose);
    await tester.runAsync(() => examples.load(defaults: [_example]));
    await tester.pumpWidget(
      _app(
        ExampleDetailPage(
          example: _example,
          store: stores.projects,
          auth: stores.auth,
          settings: stores.settings,
          examples: examples,
        ),
      ),
    );
    await tester.pump();
    await tester.enterText(find.byType(TextField), _editedCode);
    final l10n = _l10n(tester);
    await tester.ensureVisible(find.byTooltip(l10n.saveExample));
    await tester.pump();
    await tester.tap(find.byTooltip(l10n.saveExample));
    await _waitFor(tester, () {
      final file = File(p.join(directory.path, 'examples.json'));
      return file.existsSync() &&
          file.readAsStringSync().contains('edited example');
    }, 'saved editable example');
    expect(examples.items.single.code, _editedCode);
    await tester.tap(find.byTooltip(l10n.restoreDefault));
    await tester.pump();
    expect(
      tester.widget<TextField>(find.byType(TextField)).controller!.text,
      _exampleCode,
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'HomePage save survives detail reopening and a newly created HomePage',
    (tester) async {
      final stores = await _createStores(tester, directory);
      final file = File(p.join(root.path, 'examples.json'));
      await _homeDetail(tester, stores, examplesPage: true);
      final l10n = _l10n(tester);
      final save = find.byTooltip(l10n.saveExample);
      expect(tester.widget<IconButton>(save).onPressed, isNotNull);
      await tester.enterText(find.byType(TextField), _editedCode);
      await tester.ensureVisible(save);
      await tester.pump();
      await tester.tap(save);
      await tester.pump();
      await _waitFor(
        tester,
        () =>
            _storedExampleCode(file, _example.id) == _editedCode &&
            tester.widget<IconButton>(save).onPressed != null,
        'default example storage written',
      );
      expect(find.text(l10n.exampleSaved), findsOneWidget);
      await tester.pageBack();
      await tester.pump(const Duration(milliseconds: 400));
      await _homeDetail(
        tester,
        stores,
        examplesPage: true,
        expectedCode: _editedCode,
      );
      await tester.pageBack();
      await tester.pump(const Duration(milliseconds: 400));
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pump();
      await _homeDetail(
        tester,
        stores,
        examplesPage: true,
        expectedCode: _editedCode,
      );
      final reset = find.byTooltip(_l10n(tester).restoreDefault);
      await tester.ensureVisible(reset);
      await tester.pump();
      await tester.tap(reset);
      await tester.pump();
      expect(
        tester.widget<TextField>(find.byType(TextField)).controller!.text,
        _exampleCode,
      );
      expect(_storedExampleCode(file, _example.id), _editedCode);
      await tester.tap(find.byTooltip(_l10n(tester).saveExample));
      await _waitFor(
        tester,
        () => _storedExampleCode(file, _example.id) == _exampleCode,
        'reset example saved',
      );
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'save I/O failure preserves the saved value and allows another attempt',
    (tester) async {
      final stores = await _createStores(tester, directory);
      final blocked = Directory(p.join(directory.path, 'examples.json'))
        ..createSync();
      final examples = ExampleCodeStore(storageFile: File(blocked.path));
      addTearDown(examples.dispose);
      await tester.runAsync(() => examples.load(defaults: [_example]));
      await tester.pumpWidget(
        _app(
          ExampleDetailPage(
            example: _example,
            store: stores.projects,
            auth: stores.auth,
            settings: stores.settings,
            examples: examples,
          ),
        ),
      );
      await tester.pump();
      await tester.enterText(find.byType(TextField), _editedCode);
      final l10n = _l10n(tester);
      final save = find.byTooltip(l10n.saveExample);
      await tester.ensureVisible(save);
      await tester.pump();
      await tester.tap(save);
      await _waitFor(
        tester,
        () => find.textContaining('FileSystemException').evaluate().isNotEmpty,
        'save failure',
      );
      expect(examples.items.single.code, _exampleCode);
      expect(
        tester.widget<TextField>(find.byType(TextField)).controller!.text,
        _editedCode,
      );
      expect(tester.widget<IconButton>(save).onPressed, isNotNull);
      expect(find.text(l10n.exampleSaved), findsNothing);
      expect(blocked.listSync(), isEmpty);
      expect(tester.takeException(), isNull);
    },
  );

  for (final size in [const Size(320, 900), const Size(1280, 900)]) {
    for (final examplesPage in [false, true]) {
      testWidgets(
        '${examplesPage ? 'example' : 'lesson'} catalog, detail and dialog fit ${size.width.toInt()}px with 2x text',
        (tester) async {
          tester.view.physicalSize = size;
          tester.view.devicePixelRatio = 1;
          tester.platformDispatcher.textScaleFactorTestValue = 2;
          addTearDown(tester.view.resetPhysicalSize);
          addTearDown(tester.view.resetDevicePixelRatio);
          addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
          final stores = await _createStores(tester, directory);
          await tester.pumpWidget(
            _app(_catalog(stores, examplesPage: examplesPage)),
          );
          final title = examplesPage ? _exampleTitle : _lessonTitle;
          await _waitFor(
            tester,
            () => find.text(title).evaluate().isNotEmpty,
            'large-text catalog',
          );
          expect(tester.takeException(), isNull);
          await tester.tap(find.text(title));
          await _settleRoute(tester);
          _expectDetail(tester, examplesPage: examplesPage);
          expect(tester.takeException(), isNull);
          await _importDialog(tester, intoProject: true);
          expect(tester.takeException(), isNull);
          final action = find.byKey(const ValueKey('import-code-confirm'));
          await tester.ensureVisible(action);
          await tester.pump();
          final rectangle = tester.getRect(action);
          expect(rectangle.left, greaterThanOrEqualTo(0));
          expect(rectangle.right, lessThanOrEqualTo(size.width));
          expect(rectangle.bottom, lessThanOrEqualTo(size.height));
          expect(tester.takeException(), isNull);
        },
      );
    }
  }

  testWidgets('long read-only code is kept in a bounded scroll surface', (
    tester,
  ) async {
    final stores = await _createStores(tester, directory);
    final source = List.generate(
      120,
      (index) => '// source line $index',
    ).join('\n');
    await tester.pumpWidget(
      _app(
        Scaffold(
          body: ListView(
            children: [
              CodeSnippet(
                example: _example.copyWith(code: source),
                store: stores.projects,
                auth: stores.auth,
                settings: stores.settings,
              ),
            ],
          ),
        ),
      ),
    );
    await tester.pump();
    expect(find.text(source), findsOneWidget);
    expect(
      tester.getSize(find.byType(CodeSnippet)).height,
      lessThanOrEqualTo(460),
    );
    expect(tester.takeException(), isNull);
  });
}

Matcher _importFailure(CodeImportFailure reason) => isA<CodeImportException>()
    .having((error) => error.reason, 'reason', reason);

MaterialApp _app(Widget home) => MaterialApp(
  locale: const Locale('en'),
  supportedLocales: StudioLocalizations.supportedLocales,
  localizationsDelegates: const [
    StudioLocalizations.delegate,
    GlobalMaterialLocalizations.delegate,
    GlobalWidgetsLocalizations.delegate,
    GlobalCupertinoLocalizations.delegate,
  ],
  theme: AppTheme.light,
  home: home,
);

Widget _catalog(_Stores stores, {required bool examplesPage}) => examplesPage
    ? ExampleCodeTab(
        language: 'dart',
        store: stores.projects,
        auth: stores.auth,
        settings: stores.settings,
      )
    : LocalTutorialsTab(
        language: 'dart',
        store: stores.projects,
        auth: stores.auth,
        settings: stores.settings,
      );

StudioLocalizations _l10n(WidgetTester tester) =>
    StudioLocalizations.of(tester.element(find.byType(Scaffold).first));

void _expectDetail(
  WidgetTester tester, {
  required bool examplesPage,
  String expectedCode = _exampleCode,
}) {
  final l10n = _l10n(tester);
  expect(find.byTooltip(l10n.copyExample), findsOneWidget);
  expect(find.byTooltip(l10n.importCodeEditor), findsOneWidget);
  expect(find.byTooltip(l10n.importCodeProject), findsOneWidget);
  if (examplesPage) {
    expect(
      tester.widget<TextField>(find.byType(TextField)).controller!.text,
      expectedCode,
    );
  } else {
    expect(find.text(_lessonCode), findsOneWidget);
  }
}

Future<_Stores> _createStores(WidgetTester tester, Directory directory) async {
  final stores = (await tester.runAsync(() => _Stores.create(directory)))!;
  addTearDown(() async {
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 30)),
    );
    stores.dispose();
  });
  return stores;
}

Future<Project> _existingProject(
  WidgetTester tester,
  _Stores stores,
  Directory directory,
) async {
  final location = Directory(p.join(directory.path, 'projects'))..createSync();
  final result = (await tester.runAsync(
    () => stores.projects.createProject(
      name: 'Existing project',
      location: location.path,
      template: ProjectTemplate.dart,
    ),
  ))!;
  expect(result.error, isNull);
  return result.project!;
}

Future<void> _homeDetail(
  WidgetTester tester,
  _Stores stores, {
  required bool examplesPage,
  String expectedCode = _exampleCode,
}) async {
  await tester.pumpWidget(
    _app(
      HomePage(
        store: stores.projects,
        auth: stores.auth,
        settings: stores.settings,
      ),
    ),
  );
  await tester.pump();
  final l10n = _l10n(tester);
  await tester.tap(
    find.descendant(
      of: find.byType(NavigationBar),
      matching: find.text(examplesPage ? l10n.examples : l10n.tutorial),
    ),
  );
  final title = examplesPage ? _exampleTitle : _lessonTitle;
  await _waitFor(
    tester,
    () => find.text(title).evaluate().isNotEmpty,
    'HomePage catalog',
  );
  await tester.pump(const Duration(milliseconds: 400));
  await tester.tap(find.text(title));
  await _settleRoute(tester);
  _expectDetail(tester, examplesPage: examplesPage, expectedCode: expectedCode);
}

String? _storedExampleCode(File file, String id) {
  if (!file.existsSync()) return null;
  try {
    final data = jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
    for (final example in data['examples'] as List) {
      if (example is Map && example['id'] == id)
        return example['code'] as String?;
    }
  } on FormatException {
    return null;
  } on FileSystemException {
    return null;
  }
  return null;
}

Future<void> _importDialog(
  WidgetTester tester, {
  required bool intoProject,
}) async {
  final l10n = _l10n(tester);
  final command = find.byTooltip(
    intoProject ? l10n.importCodeProject : l10n.importCodeEditor,
  );
  await tester.ensureVisible(command);
  await tester.pump();
  await tester.tap(command);
  await _settleRoute(tester);
  expect(find.byKey(const ValueKey('import-file-name')), findsOneWidget);
}

String _fileName(WidgetTester tester) => tester
    .widget<TextFormField>(find.byKey(const ValueKey('import-file-name')))
    .controller!
    .text;

Future<void> _chooseProject(WidgetTester tester, Project project) async {
  final target = find.byKey(const ValueKey('import-target-project'));
  await tester.tap(target);
  await _settleRoute(tester);
  await tester.tap(find.text(project.name).last);
  await _settleRoute(tester);
  expect(find.byKey(const ValueKey('import-project-name')), findsNothing);
}

Future<void> _expectOpenedEditor(
  WidgetTester tester,
  _Stores stores, {
  required String code,
  required String fileName,
}) async {
  await _waitFor(
    tester,
    () => find.byType(EditorPage).evaluate().isNotEmpty,
    'imported EditorPage',
  );
  await tester.pump(const Duration(milliseconds: 400));
  final editor = tester.widget<EditorPage>(find.byType(EditorPage));
  final expected = p.join(editor.project.path, 'src', fileName);
  expect(editor.initialOpenPath, expected);
  expect(editor.auth, same(stores.auth));
  expect(editor.store, same(stores.projects));
  expect(editor.settings, same(stores.settings));
  expect(File(expected).readAsStringSync(), code);
  await _waitFor(
    tester,
    () => find.byType(CodeEditor).evaluate().any((element) {
      final controller = (element.widget as CodeEditor).controller;
      return controller?.text.replaceAll('\r\n', '\n') == code;
    }),
    'imported file selected in real editor',
  );
  expect(find.byType(AlertDialog), findsNothing);
}

Future<void> _settleRoute(WidgetTester tester) async {
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pump();
}

Future<void> _waitFor(
  WidgetTester tester,
  bool Function() condition,
  String description,
) async {
  // Real I/O and isolate work need real time; route transitions use fake time.
  for (var attempt = 0; attempt < 200; attempt++) {
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 10)),
    );
    await tester.pump(const Duration(milliseconds: 30));
    if (condition()) return;
  }
  fail('Timed out waiting for $description');
}

class _Stores {
  _Stores(this.projects, this.auth, this.settings);

  final ProjectStore projects;
  final AuthStore auth;
  final SettingsStore settings;

  static Future<_Stores> create(Directory directory) async {
    final projects = ProjectStore(
      storageFile: File(p.join(directory.path, 'registry.json')),
    );
    final auth = AuthStore(
      storageFile: File(p.join(directory.path, 'auth.json')),
    );
    final settings = SettingsStore(
      storageFile: File(p.join(directory.path, 'settings.json')),
    );
    await Future.wait([projects.load(), auth.load(), settings.load()]);
    settings.syntaxHighlighting = false;
    settings.minimap = false;
    return _Stores(projects, auth, settings);
  }

  void dispose() {
    projects.dispose();
    auth.dispose();
    settings.dispose();
  }
}

class _TemporaryPaths extends PathProviderPlatform {
  _TemporaryPaths(this.path);
  final String path;
  @override
  Future<String?> getApplicationSupportPath() async => path;
  @override
  Future<String?> getApplicationDocumentsPath() async => path;
  @override
  Future<String?> getExternalStoragePath() async => path;
}

final _tutorialSource = jsonEncode({
  'schemaVersion': 1,
  'entries': [
    {
      'id': 'dart-basics',
      'language': 'dart',
      'type': 'dart',
      'locale': 'en',
      'level': 'beginner',
      'title': 'Dart basics',
      'summary': 'First programs.',
      'concepts': ['output'],
      'source': 'test-fixture',
      'license': 'test-fixture',
      'updatedAt': '2026-10-01',
      'lessons': [
        {
          'id': 'dart-lesson',
          'title': _lessonTitle,
          'summary': 'Print a short message.',
          'concepts': ['print'],
          'explain': 'A program starts in main.',
          'code': _lessonCode,
          'output': 'lesson',
          'exercises': [
            {
              'prompt': 'Change the message',
              'hint': 'Edit print',
              'answer': 'Another message',
            },
          ],
        },
      ],
    },
  ],
});

final _exampleSource = jsonEncode({
  'schemaVersion': 1,
  'entries': [
    {
      'id': _example.id,
      'language': 'dart',
      'type': _example.type,
      'locale': 'en',
      'level': 'beginner',
      'title': _example.title,
      'summary': _example.summary,
      'concepts': ['output'],
      'source': 'test-fixture',
      'license': 'test-fixture',
      'updatedAt': '2026-10-01',
      'code': _example.code,
      'expectedOutput': _example.output,
      'inputFixtures': {},
      'templateType': 'dart',
    },
  ],
});
