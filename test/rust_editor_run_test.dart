import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;
import 'package:qfli_rust/main.dart' show rustProfile;
import 'package:qfli_rust/rust_run_title.dart';
import 'package:qfli_studio_core/editor/editor_page.dart';
import 'package:qfli_studio_core/editor/terminal_pane.dart';
import 'package:qfli_studio_core/models/project.dart';
import 'package:qfli_studio_core/services/project_config.dart';
import 'package:qfli_studio_core/services/studio_profile.dart';
import 'package:qfli_studio_core/store/auth_store.dart';
import 'package:qfli_studio_core/store/project_store.dart';
import 'package:qfli_studio_core/store/settings_store.dart';
import 'package:re_editor/re_editor.dart';

const _runTooltip = '运行（长按运行当前文件）';

/// Rust profile gesture seam: tap runs the configured entry, long press runs
/// the active source, and the configured entry / Cargo manifest stay intact.
///
/// The shared editor already owns the gesture wiring; this test pins the Rust
/// product contract (entry file names, `.rs` runnability, selected-source
/// routing) against the real `rustProfile` object rather than a Java fixture.
void main() {
  late _RustEditorFixture fixture;
  late StudioProfile? previousProfile;

  setUp(() {
    previousProfile = StudioProfile.current;
    fixture = _RustEditorFixture();
  });

  tearDown(() async {
    StudioProfile.current = previousProfile;
    await fixture.dispose();
  });

  testWidgets('tap, long press, tap run main.rs, main2.rs, main.rs', (
    tester,
  ) async {
    await fixture.mount(tester);
    final config = File(ProjectConfig.configPath(fixture.project.path));
    final originalConfig = config.readAsStringSync();
    final cargo = File(p.join(fixture.project.path, 'Cargo.toml'));
    final originalCargo = cargo.readAsStringSync();
    final run = find.byTooltip(_runTooltip);

    await tester.tap(run);
    await _waitForRun(tester, fixture.runner, 1);
    expect(fixture.runner.entries, [fixture.source('main.rs').path]);

    await tester.longPress(run);
    await _waitForRun(tester, fixture.runner, 2);
    expect(fixture.runner.entries, [
      fixture.source('main.rs').path,
      fixture.source('main2.rs').path,
    ]);

    await tester.tap(run);
    await _waitForRun(tester, fixture.runner, 3);
    expect(fixture.runner.entries, [
      fixture.source('main.rs').path,
      fixture.source('main2.rs').path,
      fixture.source('main.rs').path,
    ]);
    expect(config.readAsStringSync(), originalConfig);
    expect(cargo.readAsStringSync(), originalCargo);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'long press saves edits to the active Rust source before running',
    (tester) async {
      await fixture.mount(tester);
      final editor = tester.widget<CodeEditor>(find.byType(CodeEditor));
      const edited = 'fn main() { println!("saved main2"); }\n';
      editor.controller!.text = edited;
      await tester.pump();
      expect(fixture.source('main2.rs').readAsStringSync(), isNot(edited));

      await tester.longPress(find.byTooltip(_runTooltip));
      await _waitForRun(tester, fixture.runner, 1);

      expect(fixture.runner.entries, [fixture.source('main2.rs').path]);
      expect(fixture.runner.savedSources.single['main2.rs'], edited);
      expect(fixture.source('main2.rs').readAsStringSync(), edited);
    },
  );

  testWidgets(
    'the terminal shows a concise run title without backend suffixes',
    (tester) async {
      await fixture.mount(tester);
      await tester.tap(find.byTooltip(_runTooltip));
      await _waitForRun(tester, fixture.runner, 1);

      final pane = tester.state<TerminalPaneState>(find.byType(TerminalPane));
      expect(pane.busy, isFalse);
      final transcript = tester
          .widgetList<SelectableText>(find.byType(SelectableText))
          .map((widget) => widget.data!)
          .toList();
      expect(transcript, contains('${fixture.prompt} run main.rs'));
      expect(transcript.any((line) => line.contains('（Rust）')), isFalse);
      expect(transcript.any((line) => line.contains('Miri')), isFalse);
      expect(transcript.any((line) => line.contains('exit code 0')), isFalse);
    },
  );
}

Future<void> _waitForRun(
  WidgetTester tester,
  _RecordingRustRunner runner,
  int count,
) async {
  await _pumpIoUntil(
    tester,
    () =>
        runner.entries.length >= count &&
        find.byType(TerminalPane).evaluate().isNotEmpty &&
        !tester.state<TerminalPaneState>(find.byType(TerminalPane)).busy,
  );
  await tester.pump();
  expect(runner.entries, hasLength(count));
}

Future<void> _pumpIoUntil(
  WidgetTester tester,
  bool Function() condition,
) async {
  for (var attempt = 0; attempt < 200; attempt++) {
    await tester.pump(const Duration(milliseconds: 20));
    if (condition()) return;
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 10)),
    );
  }
  expect(condition(), isTrue, reason: 'The editor operation did not finish.');
}

/// Records which absolute source the Rust profile received and returns a quiet,
/// successful run so the gesture assertions stay focused on selection.
class _RecordingRustRunner implements ProgramRunner {
  final entries = <String>[];
  final savedSources = <Map<String, String>>[];

  @override
  Future<ProgramRunResult?> run({
    required String projectPath,
    required String entryFile,
  }) async {
    if (p.extension(entryFile).toLowerCase() != '.rs') return null;
    entries.add(p.normalize(p.absolute(entryFile)));
    savedSources.add({
      for (final file in Directory(projectPath).listSync().whereType<File>())
        p.basename(file.path): file.readAsStringSync(),
    });
    return ProgramRunResult(
      title: rustRunTitle(projectPath, entryFile),
      stdout: Stream.value('ran ${p.basename(entryFile)}'),
      stderr: const Stream.empty(),
      exitCode: Future.value(0),
    );
  }
}

class _RustEditorFixture {
  _RustEditorFixture() {
    final projectDirectory = Directory(p.join(directory.path, 'project'))
      ..createSync();
    project = Project.create(
      name: 'rust gesture project',
      path: projectDirectory.path,
    );
    source('main.rs').writeAsStringSync('fn main() { println!("main"); }\n');
    source('main2.rs').writeAsStringSync('fn main() { println!("main2"); }\n');
    File(p.join(project.path, 'Cargo.toml')).writeAsStringSync('''
[package]
name = "qfli_gesture"
version = "0.1.0"
edition = "2021"
''');
    final config = File(ProjectConfig.configPath(project.path));
    config.parent.createSync();
    config.writeAsStringSync(
      jsonEncode({'version': 1, 'entryFile': 'main.rs'}),
    );
  }

  final directory = Directory.systemTemp.createTempSync('qfli_rust_gesture_');
  final runner = _RecordingRustRunner();
  final auth = AuthStore();
  final store = ProjectStore();
  final settings = SettingsStore();
  late final Project project;

  String get prompt {
    final name = p.basename(p.normalize(project.path));
    return Platform.isWindows ? '$name>' : '$name\$';
  }

  File source(String name) => File(p.join(project.path, name));

  Future<void> mount(WidgetTester tester) async {
    StudioProfile.current = _rustTestProfile(runner);
    tester.view.physicalSize = const Size(1100, 850);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(() async {
      await tester.pumpWidget(const SizedBox.shrink());
      if (!_disposed) {
        _disposed = true;
        auth.dispose();
        store.dispose();
        settings.dispose();
      }
      await _disposeFixtureTree(tester, directory);
    });
    await tester.pumpWidget(
      MaterialApp(
        home: EditorPage(
          project: project,
          auth: auth,
          store: store,
          settings: settings,
          initialOpenPath: 'main2.rs',
        ),
      ),
    );
    await _pumpIoUntil(
      tester,
      () => find.byType(CodeEditor).evaluate().isNotEmpty,
    );
    await tester.pump(const Duration(milliseconds: 200));
  }

  var _disposed = false;

  Future<void> dispose() async {
    if (_disposed) return;
    _disposed = true;
    auth.dispose();
    store.dispose();
    settings.dispose();
  }
}

/// A Rust profile whose runner is the recording fake; every other product
/// field (entry names, extension filter, offline mode) stays identical to the
/// shipped `rustProfile`.
StudioProfile _rustTestProfile(ProgramRunner runner) => StudioProfile(
  id: rustProfile.id,
  appTitle: rustProfile.appTitle,
  templates: rustProfile.templates,
  isOffline: rustProfile.isOffline,
  runner: runner,
  productKey: rustProfile.productKey,
  showHomeTabs: rustProfile.showHomeTabs,
  supportedFileExtensions: rustProfile.supportedFileExtensions,
  entryFileNames: rustProfile.entryFileNames,
);

Future<void> _disposeFixtureTree(
  WidgetTester tester,
  Directory directory,
) async {
  // `EditorPage.dispose()` schedules an unawaited history.json write. Inside
  // `testWidgets` it runs in the FakeAsync zone; alternate both zones until the
  // open file handle is released, matching the shared editor test convention.
  const maxRounds = 50;
  FileSystemException? lastError;
  for (var round = 0; round < maxRounds; round++) {
    try {
      if (directory.existsSync()) await directory.delete(recursive: true);
      return;
    } on FileSystemException catch (error) {
      lastError = error;
      await tester.pump(const Duration(milliseconds: 20));
      await tester.runAsync(
        () => Future<void>.delayed(const Duration(milliseconds: 20)),
      );
    }
  }
  throw lastError!;
}
