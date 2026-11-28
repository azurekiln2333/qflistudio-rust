import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;
import 'package:qfli_rust/main.dart' show rustProfile;
import 'package:qfli_rust/rust_run_title.dart';
import 'package:qfli_studio_core/editor/editor_controller.dart';
import 'package:qfli_studio_core/editor/editor_page.dart';
import 'package:qfli_studio_core/editor/editor_problems_bar.dart';
import 'package:qfli_studio_core/editor/project_history.dart';
import 'package:qfli_studio_core/editor/terminal_pane.dart';
import 'package:qfli_studio_core/models/project.dart';
import 'package:qfli_studio_core/services/project_config.dart';
import 'package:qfli_studio_core/services/studio_profile.dart';
import 'package:qfli_studio_core/store/auth_store.dart';
import 'package:qfli_studio_core/store/project_store.dart';
import 'package:qfli_studio_core/store/settings_store.dart';
import 'package:qfli_studio_core/workspace/saved_workspaces_tab.dart';
import 'package:qfli_studio_core/workspace/workspace_store.dart';
import 'package:re_editor/re_editor.dart';

const _runTooltip = '运行（长按运行当前文件）';

/// Consumer regressions for Rust's actual offline profile. Only its runner is
/// replaced: this proves UI routing, saved source and cwd, not Rust execution.
void main() {
  late _WorkspaceFixture fixture;
  StudioProfile? previousProfile;

  setUp(() async {
    previousProfile = StudioProfile.current;
    fixture = await _WorkspaceFixture.create();
    StudioProfile.current = _withRecordingRunner(fixture.runner);
  });
  tearDown(() => StudioProfile.current = previousProfile);

  testWidgets(
    'secondary Rust root owns normal and active-file Run without saving another root',
    (tester) async {
      await fixture.mount(tester);
      await fixture.showExplorer(tester);
      expect(fixture.root(fixture.primary), findsOneWidget);
      expect(fixture.root(fixture.secondary), findsOneWidget);
      final editor = fixture.editor(tester);
      expect(editor.files.map((file) => file.projectRootPath), [
        fixture.primary.path,
        fixture.secondary.path,
      ]);
      expect(editor.current!.projectRootPath, fixture.secondary.path);

      final primarySource = fixture.file(fixture.primary, 'src/main.rs');
      final primarySaved = primarySource.readAsStringSync();
      final secondarySource = fixture.file(
        fixture.secondary,
        'src/bin/inspect.rs',
      );
      const primaryEdit = 'fn main() { println!("primary pending edit"); }\n';
      const secondaryEdit =
          'fn main() { println!("secondary unsaved 中文 😀"); }\r\n';
      final primaryBuffer = editor.files.singleWhere(
        (file) => p.equals(file.projectRootPath, fixture.primary.path),
      );
      primaryBuffer.controller.text = primaryEdit;
      editor.current!.controller.text = secondaryEdit;
      await tester.pump();

      final config = fixture.config(fixture.secondary).readAsStringSync();
      final cargo = fixture
          .file(fixture.secondary, 'Cargo.toml')
          .readAsStringSync();
      await tester.tap(find.byTooltip(_runTooltip));
      await fixture.waitForRun(tester, 1);
      final normal = fixture.runner.records[0];
      expect(normal.root, fixture.secondary.path);
      expect(
        normal.entry,
        fixture.file(fixture.secondary, 'src/configured.rs').path,
      );
      expect(normal.input, 'secondary input\n');
      expect(normal.savedSources['src/bin/inspect.rs'], secondaryEdit);
      expect(secondarySource.readAsStringSync(), secondaryEdit);
      expect(primarySource.readAsStringSync(), primarySaved);
      expect(primaryBuffer.dirty, isTrue);

      await tester.longPress(find.byTooltip(_runTooltip));
      await fixture.waitForRun(tester, 2);
      final active = fixture.runner.records[1];
      expect(active.root, fixture.secondary.path);
      expect(active.entry, secondarySource.path);
      expect(active.savedSources['src/bin/inspect.rs'], secondaryEdit);
      expect(active.input, 'secondary input\n');
      expect(primarySource.readAsStringSync(), primarySaved);
      expect(fixture.config(fixture.secondary).readAsStringSync(), config);
      expect(
        fixture.file(fixture.secondary, 'Cargo.toml').readAsStringSync(),
        cargo,
      );

      // Both roots remain open. Selecting the other tab changes the run owner
      // without replacing the editor with a different project session.
      editor.select(editor.files.indexOf(primaryBuffer));
      await tester.pump();
      await tester.tap(find.byTooltip(_runTooltip));
      await fixture.waitForRun(tester, 3);
      final primary = fixture.runner.records[2];
      expect(primary.root, fixture.primary.path);
      expect(primary.entry, primarySource.path);
      expect(primary.input, 'primary input\n');
      expect(primary.savedSources['src/main.rs'], primaryEdit);
      expect(primarySource.readAsStringSync(), primaryEdit);
      expect(editor.files, hasLength(2));
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'both Rust roots retain nested expansion across sidebar reopen and editor reconstruction',
    (tester) async {
      await fixture.mount(tester);
      await fixture.showExplorer(tester);
      await fixture.expand(tester, fixture.primary, 'src', 'nested');
      await fixture.expand(
        tester,
        fixture.primary,
        'nested',
        'primary_helper.rs',
      );
      await fixture.expand(tester, fixture.secondary, 'src', 'bin');
      await fixture.expand(tester, fixture.secondary, 'bin', 'inspect.rs');

      await tester.tap(find.byTooltip('收起文件树'));
      // Build the changed width factor before advancing its animation.
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 250));
      expect(
        fixture.entry(fixture.primary, 'primary_helper.rs').hitTestable(),
        findsNothing,
        reason: 'Sidebar close: the primary leaf must be hidden.',
      );
      expect(
        fixture.entry(fixture.secondary, 'inspect.rs').hitTestable(),
        findsNothing,
        reason: 'Sidebar close: the secondary leaf must be hidden.',
      );
      await fixture.showExplorer(
        tester,
        failureDetails: () => 'Sidebar reopen: both root rows must be visible.',
      );
      expect(
        fixture.entry(fixture.primary, 'primary_helper.rs').hitTestable(),
        findsOneWidget,
        reason: 'Sidebar reopen: the primary nested leaf must remain visible.',
      );
      expect(
        fixture.entry(fixture.secondary, 'inspect.rs').hitTestable(),
        findsOneWidget,
        reason: 'Sidebar reopen: the secondary nested leaf must remain visible.',
      );

      final saved = await fixture.readHistory(tester);
      expect(saved[0].workspaceRoots, [
        fixture.primary.path,
        fixture.secondary.path,
      ]);
      expect(saved[0].expandedDirs, containsAll(['src', 'src/nested']));
      expect(saved[1].expandedDirs, containsAll(['src', 'src/bin']));

      // Destroy FileExplorer and EditorPage: the next tree must read persisted
      // state, rather than inheriting the previous widget's expansion set.
      await fixture.unmount(tester);
      await fixture.mount(tester);
      await fixture.showExplorer(
        tester,
        failureDetails: () => 'Reconstruction: both root rows must be visible.',
      );
      await _pumpIoUntil(
        tester,
        () =>
            fixture
                .entry(fixture.primary, 'primary_helper.rs')
                .hitTestable()
                .evaluate()
                .isNotEmpty &&
            fixture
                .entry(fixture.secondary, 'inspect.rs')
                .hitTestable()
                .evaluate()
                .isNotEmpty,
        failureDetails: () => 'Reconstruction: both nested leaves must restore.',
      );
      expect(fixture.root(fixture.primary), findsOneWidget);
      expect(fixture.root(fixture.secondary), findsOneWidget);
      final editor = fixture.editor(tester);
      expect(editor.files.map((file) => file.projectRootPath), [
        fixture.primary.path,
        fixture.secondary.path,
      ]);
      expect(
        editor.current!.path,
        fixture.file(fixture.secondary, 'src/bin/inspect.rs').path,
      );
      expect(editor.current!.ownerProjectName, fixture.secondary.name);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'mobile drawer reopening retains both Rust roots and nested expansion',
    (tester) async {
      await fixture.mount(tester, viewport: const Size(600, 850));
      await fixture.showExplorer(tester);
      await fixture.expand(tester, fixture.primary, 'src', 'nested');
      await fixture.expand(
        tester,
        fixture.primary,
        'nested',
        'primary_helper.rs',
      );
      await fixture.expand(tester, fixture.secondary, 'src', 'bin');
      await fixture.expand(tester, fixture.secondary, 'bin', 'inspect.rs');

      final scaffold = Scaffold.of(
        tester.element(fixture.root(fixture.primary)),
      );
      expect(scaffold.isDrawerOpen, isTrue);
      scaffold.closeDrawer();
      await _pumpIoUntil(
        tester,
        () =>
            !scaffold.isDrawerOpen &&
            find.byTooltip('打开文件树').hitTestable().evaluate().length == 1,
      );
      await tester.pump(const Duration(milliseconds: 250));
      expect(
        fixture.entry(fixture.primary, 'primary_helper.rs').hitTestable(),
        findsNothing,
      );
      expect(
        fixture.entry(fixture.secondary, 'inspect.rs').hitTestable(),
        findsNothing,
      );

      String drawerDiagnostics() {
        String summarize(String label, Project project, String leaf) {
          final root = fixture.root(project);
          final src = fixture.entry(project, 'src');
          final leafEntry = fixture.entry(project, leaf);

          String counts(Finder finder) {
            final total = finder.evaluate().length;
            final hitTestable = finder.hitTestable().evaluate().length;
            return '$total/$hitTestable';
          }

          return '$label(root=${counts(root)}, src=${counts(src)}, '
              'leaf=${counts(leafEntry)})';
        }

        final roots = [
          summarize('primary', fixture.primary, 'primary_helper.rs'),
          summarize('secondary', fixture.secondary, 'inspect.rs'),
        ].join('; ');
        final toggle = find.byTooltip('打开文件树');
        final toggleTotal = toggle.evaluate().length;
        final toggleHitTestable = toggle.hitTestable().evaluate().length;
        return 'drawerOpen=${scaffold.isDrawerOpen}; '
            'toggle=$toggleTotal/$toggleHitTestable; $roots';
      }

      await fixture.showExplorer(tester, failureDetails: drawerDiagnostics);
      // Restoring a root schedules child directory reads after its src row is
      // visible. Wait for both nested leaves before checking the reopened tree.
      await _pumpIoUntil(
        tester,
        () =>
            fixture
                .entry(fixture.primary, 'primary_helper.rs')
                .hitTestable()
                .evaluate()
                .isNotEmpty &&
            fixture
                .entry(fixture.secondary, 'inspect.rs')
                .hitTestable()
                .evaluate()
                .isNotEmpty,
        failureDetails: drawerDiagnostics,
      );
      expect(scaffold.isDrawerOpen, isTrue);
      expect(fixture.root(fixture.primary), findsOneWidget);
      expect(fixture.root(fixture.secondary), findsOneWidget);
      expect(fixture.editor(tester).files.map((file) => file.projectRootPath), [
        fixture.primary.path,
        fixture.secondary.path,
      ]);
      final saved = await fixture.readHistory(tester);
      expect(saved[0].workspaceRoots, [
        fixture.primary.path,
        fixture.secondary.path,
      ]);
      expect(saved[0].expandedDirs, containsAll(['src', 'src/nested']));
      expect(saved[1].expandedDirs, containsAll(['src', 'src/bin']));
      expect(tester.takeException(), isNull);
    },
  );

  for (final width in [1100.0, 600.0]) {
    testWidgets(
      'named Rust workspace saves and reopens its own session at width $width',
      (tester) async {
        expect(StudioProfile.current!.supportsSavedWorkspaces, isTrue);
        await fixture.mount(tester, viewport: Size(width, 850));
        await fixture.showExplorer(tester);
        await fixture.expand(tester, fixture.primary, 'src', 'nested');
        await fixture.expand(
          tester,
          fixture.primary,
          'nested',
          'primary_helper.rs',
        );
        await fixture.expand(tester, fixture.secondary, 'src', 'bin');
        await fixture.expand(tester, fixture.secondary, 'bin', 'inspect.rs');
        final primarySource = fixture.file(fixture.primary, 'src/main.rs');
        final secondarySource = fixture.file(
          fixture.secondary,
          'src/bin/inspect.rs',
        );
        final primaryBytes = primarySource.readAsBytesSync();
        final secondaryBytes = secondarySource.readAsBytesSync();

        await tester.tap(find.byTooltip('工作区项目').hitTestable());
        final nameField = find.byKey(const ValueKey('workspace-name-field'));
        await _pumpIoUntil(tester, () => nameField.evaluate().isNotEmpty);
        expect(find.text('保存工作区'), findsOneWidget);
        for (final project in [fixture.primary, fixture.secondary]) {
          final choice = tester.widget<CheckboxListTile>(
            find.byKey(ValueKey('workspace-project-${project.id}')),
          );
          expect(choice.value, isTrue);
        }
        const name = 'Rust named workspace';
        await tester.enterText(nameField, name);
        await tester.tap(find.widgetWithText(FilledButton, '保存'));
        await _pumpIoUntil(
          tester,
          () =>
              fixture.workspaces.workspaces.length == 1 &&
              fixture.workspaces.workspaces.single.session.documents.length ==
                  2 &&
              find.byType(AlertDialog).evaluate().isEmpty &&
              find.text('$name · 2 个项目').evaluate().isNotEmpty,
        );
        final saved = fixture.workspaces.workspaces.single;
        expect(saved.name, name);
        expect(saved.memberPaths, [
          fixture.primary.path,
          fixture.secondary.path,
        ]);

        // Save a session distinct from the legacy two-tab project history.
        final editor = fixture.editor(tester);
        editor.closeAt(0);
        editor.current!.controller.selection =
            const CodeLineSelection.collapsed(index: 0, offset: 4);
        await tester.pump();
        await fixture.unmount(tester);
        final session = fixture.workspaces.byId(saved.id)!.session;
        expect(session.documents, hasLength(1));
        expect(session.documents.single.projectPath, fixture.secondary.path);
        expect(session.documents.single.relativePath, 'src/bin/inspect.rs');
        expect(session.documents.single.isActive, isTrue);
        expect(session.documents.single.cursor.baseOffset, 4);
        for (final project in [fixture.primary, fixture.secondary]) {
          final expanded = session.expandedDirs.entries.singleWhere(
            (entry) => p.equals(entry.key, project.path),
          );
          expect(
            expanded.value,
            containsAll([
              'src',
              project == fixture.primary ? 'src/nested' : 'src/bin',
            ]),
          );
        }

        await tester.runAsync(
          () => ProjectHistory.save(
            fixture.primary.path,
            cursors: const {},
            openFiles: const ['src/configured.rs'],
            activeFile: 'src/configured.rs',
            documents: [
              ProjectDocumentSession(
                projectPath: fixture.primary.path,
                relativePath: 'src/configured.rs',
                cursor: const FileCursor(
                  baseIndex: 0,
                  baseOffset: 0,
                  extentIndex: 0,
                  extentOffset: 0,
                ),
                isActive: true,
              ),
            ],
          ),
        );
        // A fresh store and fresh editor must restore the file on disk, rather
        // than a retained widget or the deliberately different project history.
        final reopened = WorkspaceStore(root: fixture.workspaceDirectory);
        addTearDown(() async {
          await fixture.unmount(tester, workspaceStore: reopened);
          reopened.dispose();
        });
        await tester.runAsync(() => reopened.load());
        expect(reopened.byId(saved.id)!.session.documents, hasLength(1));
        await fixture.mountWorkspaceHome(tester, reopened, name);
        await tester.tap(find.text(name));
        await _pumpIoUntil(
          tester,
          () =>
              find.byType(EditorProblemsBar).evaluate().isNotEmpty &&
              fixture.editor(tester).files.length == 1,
        );
        await tester.pump(const Duration(milliseconds: 250));
        final page = tester.widget<EditorPage>(find.byType(EditorPage));
        expect(page.workspace!.id, saved.id);
        final restored = fixture.editor(tester);
        expect(restored.current!.path, secondarySource.path);
        expect(restored.current!.projectRootPath, fixture.secondary.path);
        expect(restored.current!.controller.selection.baseOffset, 4);
        expect(restored.current!.dirty, isFalse);
        await fixture.showExplorer(tester);
        await _pumpIoUntil(
          tester,
          () =>
              fixture
                  .entry(fixture.primary, 'primary_helper.rs')
                  .hitTestable()
                  .evaluate()
                  .isNotEmpty &&
              fixture
                  .entry(fixture.secondary, 'inspect.rs')
                  .hitTestable()
                  .evaluate()
                  .isNotEmpty,
        );
        expect(fixture.root(fixture.primary), findsOneWidget);
        expect(fixture.root(fixture.secondary), findsOneWidget);
        expect(primarySource.readAsBytesSync(), primaryBytes);
        expect(secondarySource.readAsBytesSync(), secondaryBytes);
        await fixture.unmount(tester, workspaceStore: reopened);
        final history = await fixture.readHistory(tester);
        expect(
          history.first.documents.single.relativePath,
          'src/configured.rs',
        );
        expect(
          history.first.documents.single.projectPath,
          fixture.primary.path,
        );
        expect(tester.takeException(), isNull);
      },
    );
  }
}

class _RunRecord {
  const _RunRecord(this.root, this.entry, this.input, this.savedSources);
  final String root;
  final String entry;
  final String input;
  final Map<String, String> savedSources;
}

class _RecordingRunner implements ProgramRunner {
  final records = <_RunRecord>[];

  @override
  Future<ProgramRunResult?> run({
    required String projectPath,
    required String entryFile,
  }) async {
    if (p.extension(entryFile) != '.rs') return null;
    final root = p.normalize(p.absolute(projectPath));
    records.add(
      _RunRecord(
        root,
        p.normalize(p.absolute(entryFile)),
        File(p.join(root, 'input.txt')).readAsStringSync(),
        {
          for (final source in Directory(
            root,
          ).listSync(recursive: true).whereType<File>())
            if (p.extension(source.path) == '.rs')
              p.relative(source.path, from: root).replaceAll(r'\', '/'): source
                  .readAsStringSync(),
        },
      ),
    );
    return ProgramRunResult(
      title: rustRunTitle(root, entryFile),
      stdout: const Stream.empty(),
      stderr: const Stream.empty(),
      exitCode: Future.value(0),
    );
  }
}

class _WorkspaceFixture {
  _WorkspaceFixture(this.directory, this.store, this.primary, this.secondary);
  final Directory directory;
  final ProjectStore store;
  final Project primary;
  final Project secondary;
  final auth = AuthStore();
  final settings = SettingsStore();
  final runner = _RecordingRunner();
  Directory get workspaceDirectory =>
      Directory(p.join(directory.path, 'data', 'workspaces'));
  late final workspaces = WorkspaceStore(root: workspaceDirectory);
  bool _registeredCleanup = false;

  static Future<_WorkspaceFixture> create() async {
    final directory = Directory.systemTemp.createTempSync(
      'qfli_rust_workspace_',
    );
    final primary = Project.create(
      name: 'Rust primary',
      path: p.join(directory.path, 'primary'),
      type: 'rust',
      language: 'Rust',
    );
    final secondary = Project.create(
      name: 'Rust secondary',
      path: p.join(directory.path, 'secondary'),
      type: 'rust',
      language: 'Rust',
    );
    for (final project in [primary, secondary]) {
      Directory(p.join(project.path, 'src', 'bin')).createSync(recursive: true);
      Directory(p.join(project.path, 'src', 'nested')).createSync();
      File(
        p.join(project.path, 'src', 'main.rs'),
      ).writeAsStringSync('fn main() { println!("default"); }\n');
      File(
        p.join(project.path, 'src', 'configured.rs'),
      ).writeAsStringSync('fn main() { println!("configured"); }\n');
      File(
        p.join(project.path, 'src', 'bin', 'inspect.rs'),
      ).writeAsStringSync('fn main() { println!("inspect"); }\r\n');
      File(
        p.join(project.path, 'src', 'nested', 'primary_helper.rs'),
      ).writeAsStringSync('pub fn marker() -> u8 { 7 }\n');
      File(
        p.join(project.path, 'input.txt'),
      ).writeAsStringSync('${p.basename(project.path)} input\n');
      File(p.join(project.path, 'Cargo.toml')).writeAsStringSync('''
[package]
name = "${p.basename(project.path)}_workspace_fixture"
version = "0.1.0"
edition = "2021"
[[bin]]
name = "configured"
path = "src/configured.rs"
''');
      final config = File(ProjectConfig.configPath(project.path));
      config.parent.createSync(recursive: true);
      config.writeAsStringSync(
        jsonEncode({
          'version': 1,
          'entryFile': project == primary ? 'src/main.rs' : 'src/configured.rs',
        }),
      );
    }
    final registry = File(p.join(directory.path, 'projects.json'))
      ..writeAsStringSync(
        jsonEncode({
          'projects': [primary.toJson(), secondary.toJson()],
        }),
      );
    final store = ProjectStore(storageFile: registry);
    await store.load();
    const cursor = FileCursor(
      baseIndex: 0,
      baseOffset: 0,
      extentIndex: 0,
      extentOffset: 0,
    );
    await ProjectHistory.save(
      primary.path,
      cursors: const {},
      openFiles: const [],
      activeFile: null,
      documents: [
        ProjectDocumentSession(
          projectPath: primary.path,
          relativePath: 'src/main.rs',
          cursor: cursor,
        ),
        ProjectDocumentSession(
          projectPath: secondary.path,
          relativePath: 'src/bin/inspect.rs',
          cursor: cursor,
          isActive: true,
        ),
      ],
    );
    await ProjectHistory.saveWorkspaceRoots(primary.path, [
      primary.path,
      secondary.path,
    ]);
    return _WorkspaceFixture(directory, store, primary, secondary);
  }

  File file(Project project, String path) =>
      File(p.joinAll([project.path, ...path.split('/')]));
  File config(Project project) => File(ProjectConfig.configPath(project.path));
  Finder root(Project project) =>
      find.byKey(ValueKey('workspace-root-${project.path}'));
  Finder entry(Project project, String name) =>
      find.descendant(of: root(project), matching: find.text(name));
  EditorController editor(WidgetTester tester) => tester
      .widget<EditorProblemsBar>(find.byType(EditorProblemsBar))
      .analysis
      .editor;

  Future<void> mount(
    WidgetTester tester, {
    Size viewport = const Size(1100, 850),
  }) async {
    tester.view.physicalSize = viewport;
    tester.view.devicePixelRatio = 1;
    if (!_registeredCleanup) {
      _registeredCleanup = true;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      addTearDown(() async {
        await unmount(tester);
        auth.dispose();
        store.dispose();
        settings.dispose();
        workspaces.dispose();
        await tester.runAsync(() => directory.delete(recursive: true));
      });
    }
    await tester.pumpWidget(
      MaterialApp(
        home: EditorPage(
          project: primary,
          auth: auth,
          store: store,
          settings: settings,
          workspaceStore: workspaces,
        ),
      ),
    );
    await _pumpIoUntil(
      tester,
      () =>
          find.byType(EditorProblemsBar).evaluate().isNotEmpty &&
          editor(tester).files.length == 2,
    );
    await tester.pump(const Duration(milliseconds: 250));
  }

  Future<void> showExplorer(
    WidgetTester tester, {
    String Function()? failureDetails,
  }) async {
    if (root(primary).hitTestable().evaluate().isEmpty) {
      final toggle = find.byTooltip('打开文件树').hitTestable();
      expect(toggle, findsOneWidget, reason: failureDetails?.call());
      await tester.tap(toggle);
    }
    await tester.pump(const Duration(milliseconds: 250));
    await _pumpIoUntil(
      tester,
      () =>
          root(primary).evaluate().isNotEmpty &&
          root(secondary).evaluate().isNotEmpty &&
          entry(primary, 'src').hitTestable().evaluate().isNotEmpty &&
          entry(secondary, 'src').hitTestable().evaluate().isNotEmpty,
      failureDetails: failureDetails,
    );
  }

  Future<void> expand(
    WidgetTester tester,
    Project project,
    String folder,
    String child,
  ) async {
    await tester.tap(entry(project, folder));
    await _pumpIoUntil(
      tester,
      () => entry(project, child).hitTestable().evaluate().isNotEmpty,
    );
  }

  Future<void> waitForRun(WidgetTester tester, int count) async {
    await _pumpIoUntil(
      tester,
      () =>
          runner.records.length >= count &&
          find.byType(TerminalPane).evaluate().isNotEmpty &&
          !tester.state<TerminalPaneState>(find.byType(TerminalPane)).busy,
    );
    expect(runner.records, hasLength(count));
  }

  Future<List<ProjectSession>> readHistory(WidgetTester tester) async {
    List<ProjectSession>? saved;
    Object? failure;
    Future.wait([
      ProjectHistory.load(primary.path),
      ProjectHistory.load(secondary.path),
    ]).then(
      (value) => saved = value,
      onError: (Object error) => failure = error,
    );
    await _pumpIoUntil(tester, () => saved != null || failure != null);
    if (failure != null) throw failure!;
    return saved!;
  }

  Future<void> mountWorkspaceHome(
    WidgetTester tester,
    WorkspaceStore workspaceStore,
    String workspaceName,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SavedWorkspacesTab(
            store: store,
            auth: auth,
            settings: settings,
            workspaceStore: workspaceStore,
          ),
        ),
      ),
    );
    await _pumpIoUntil(
      tester,
      () => find.text(workspaceName).hitTestable().evaluate().isNotEmpty,
    );
  }

  Future<void> unmount(
    WidgetTester tester, {
    WorkspaceStore? workspaceStore,
  }) async {
    await tester.pumpWidget(const SizedBox.shrink());
    await readHistory(tester);
    var settled = false;
    Object? failure;
    Future.wait([
      (workspaceStore ?? workspaces).settle(),
      store.refresh(),
    ]).then(
      (_) => settled = true,
      onError: (Object error) {
        failure = error;
        settled = true;
      },
    );
    await _pumpIoUntil(tester, () => settled);
    if (failure != null) throw failure!;
  }
}

/// Keep every production field so the test follows the real Rust product's
/// offline, language, analysis and workspace branches; replace execution only.
StudioProfile _withRecordingRunner(ProgramRunner runner) => StudioProfile(
  id: rustProfile.id,
  appTitle: rustProfile.appTitle,
  templates: rustProfile.templates,
  runner: runner,
  codeAnalyzer: rustProfile.codeAnalyzer,
  debugger: rustProfile.debugger,
  webPreviewFactory: rustProfile.webPreviewFactory,
  toolsPageBuilder: rustProfile.toolsPageBuilder,
  toolsTabBuilder: rustProfile.toolsTabBuilder,
  documentToolBuilder: rustProfile.documentToolBuilder,
  terminalCommandDelegate: rustProfile.terminalCommandDelegate,
  contentRepositoryFactory: rustProfile.contentRepositoryFactory,
  editorFileTools: rustProfile.editorFileTools,
  entryFileNames: rustProfile.entryFileNames,
  isOffline: rustProfile.isOffline,
  offlineOnly: rustProfile.offlineOnly,
  productKey: rustProfile.productKey,
  showHomeTabs: rustProfile.showHomeTabs,
  supportsSavedWorkspaces: rustProfile.supportsSavedWorkspaces,
  runtimeKind: rustProfile.runtimeKind,
  runtimeStatus: rustProfile.runtimeStatus,
  supportedFileExtensions: rustProfile.supportedFileExtensions,
);

Future<void> _pumpIoUntil(
  WidgetTester tester,
  bool Function() condition, {
  String Function()? failureDetails,
}) async {
  for (var attempt = 0; attempt < 200; attempt++) {
    await tester.pump(const Duration(milliseconds: 20));
    if (condition()) return;
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 10)),
    );
  }
  final details = failureDetails?.call();
  expect(
    condition(),
    isTrue,
    reason: details == null
        ? 'Rust workspace operation did not finish.'
        : 'Rust workspace operation did not finish.\n$details',
  );
}
