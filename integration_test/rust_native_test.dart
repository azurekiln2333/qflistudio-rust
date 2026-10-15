import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:path/path.dart' as p;
import 'package:qfli_rust/native_miri_assets.dart';
import 'package:qfli_rust/native_miri_runner.dart';
import 'package:qfli_rust/rust_runner.dart';
import 'package:qfli_rust/main.dart' show rustProfile;
import 'package:qfli_rust/rust_project_store.dart';
import 'package:qfli_studio_core/editor/editor_page.dart';
import 'package:qfli_studio_core/editor/terminal_pane.dart';
import 'package:qfli_studio_core/services/project_templates.dart';
import 'package:qfli_studio_core/services/studio_profile.dart';
import 'package:qfli_studio_core/store/auth_store.dart';
import 'package:qfli_studio_core/store/settings_store.dart';
import 'package:qfli_studio_core/terminal/shell/sandbox_shell_backend.dart';
import 'package:qfli_studio_core/terminal/shell/shell_backend.dart';
import 'package:qfli_studio_core/terminal/state/terminal_manager.dart';
import 'package:re_editor/re_editor.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  late Directory project;
  late String entry;
  late NativeMiriRuntime runtime;

  setUpAll(() async {
    expect(Platform.isAndroid, isTrue);
    runtime = await prepareNativeMiriAssets();
    expect(runtime.target.platform, 'android');
    expect(runtime.target.nativeHosts, contains(runtime.nativeHost));
    expect(runtime.libraryPath, contains('/lib/'));
    expect(runtime.libraryPath, contains('.integrationtest-'));
    expect(runtime.backendPath, isNotNull);
  });
  setUp(() {
    project = Directory.systemTemp.createTempSync('qfli_rust_android_');
    entry = p.join(project.path, 'main.rs');
  });
  tearDown(() => project.deleteSync(recursive: true));

  NativeMiriProgramRunner limitedRunner({
    int maxBasicBlocks = 10000000,
    int maxOutputBytes = 1024 * 1024,
    int maxGuestMemoryBytes = 64 * 1024 * 1024,
  }) => NativeMiriProgramRunner(
    sysrootPath: runtime.sysrootPath,
    libraryPath: runtime.libraryPath,
    backendPath: runtime.backendPath,
    maxBasicBlocks: maxBasicBlocks,
    maxOutputBytes: maxOutputBytes,
    maxGuestMemoryBytes: maxGuestMemoryBytes,
  );

  Future<(int, List<String>, List<String>)> run({
    ProgramRunner runner = const RustProgramRunner(),
  }) async {
    final result = await runner.run(
      projectPath: project.path,
      entryFile: entry,
    );
    expect(result, isNotNull);
    final output = result!.stdout.toList();
    final errors = result.stderr.toList();
    final code = await result.exitCode;
    return (code, await output, await errors);
  }

  testWidgets('automatic mobile runner executes modules and generics', (
    tester,
  ) async {
    File(p.join(project.path, 'data.rs')).writeAsStringSync(
      'pub fn twice<T: std::ops::Add<Output=T> + Copy>(value: T) -> T { value + value }',
    );
    File(entry).writeAsStringSync('''
mod data;
fn main() {
    let values = vec![1, 2, 3];
    let total: i32 = values.iter().map(|value| data::twice(*value)).sum();
    println!("total={}", total);
    eprintln!("items={}", values.len());
}
''');
    final (code, output, errors) = await run();
    expect(code, 0, reason: errors.join('\n'));
    expect(output, ['total=12']);
    expect(errors, ['items=3']);
  });

  testWidgets('stdin EOF UTF-8 and guest exit status survive native calls', (
    tester,
  ) async {
    File(entry).writeAsStringSync('''
use std::io::{self, Read};
fn main() {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input).unwrap();
    println!("{}", if input.is_empty() { "eof" } else { input.trim() });
    eprintln!("guest stderr");
    std::process::exit(23);
}
''');
    final (emptyCode, emptyOutput, emptyErrors) = await run();
    expect(emptyCode, 23, reason: emptyErrors.join('\n'));
    expect(emptyOutput, ['eof']);
    expect(emptyErrors, ['guest stderr']);
    File(
      p.join(project.path, 'input.txt'),
    ).writeAsStringSync('input \u4e2d\u6587\n');
    final (code, output, errors) = await run();
    expect(code, 23, reason: errors.join('\n'));
    expect(output, ['input \u4e2d\u6587']);
  });

  testWidgets('compiler errors retain diagnostics and clear previous output', (
    tester,
  ) async {
    File(entry).writeAsStringSync('fn main() { println!("valid"); }');
    final (firstCode, firstOutput, firstErrors) = await run();
    expect(firstCode, 0, reason: firstErrors.join('\n'));
    expect(firstOutput, ['valid']);
    File(entry).writeAsStringSync(
      'fn main() { let values = vec![1]; drop(values); println!("{:?}", values); }',
    );
    final (code, output, errors) = await run();
    expect(code, 1);
    expect(output, isEmpty);
    expect(errors.join('\n'), contains('borrow of moved value'));
  });

  testWidgets('execution output and guest memory limits are enforced', (
    tester,
  ) async {
    File(
      entry,
    ).writeAsStringSync('fn main() { loop { std::hint::black_box(1); } }');
    final (loopCode, _, loopErrors) = await run(
      runner: limitedRunner(maxBasicBlocks: 10000),
    );
    expect(loopCode, 124, reason: loopErrors.join('\n'));
    File(entry).writeAsStringSync(
      'fn main() { for _ in 0..10000 { println!("abcdefghijk"); } }',
    );
    final (outputCode, output, outputErrors) = await run(
      runner: limitedRunner(maxOutputBytes: 1024),
    );
    expect(outputCode, 124, reason: outputErrors.join('\n'));
    expect(output.join('\n').length, lessThanOrEqualTo(1024));
    File(entry).writeAsStringSync(
      'fn main() { let data = vec![1u8; 8 * 1024 * 1024]; println!("{}", data.len()); }',
    );
    final (memoryCode, _, memoryErrors) = await run(
      runner: limitedRunner(maxGuestMemoryBytes: 1024 * 1024),
    );
    expect(memoryCode, 124, reason: memoryErrors.join('\n'));
  });

  testWidgets(
    'stop completes native execution before a fresh run',
    (tester) async {
      File(entry).writeAsStringSync(
        'fn main() { println!("started"); loop { std::hint::black_box(1); } }',
      );
      final engine = limitedRunner(maxBasicBlocks: 1000000000);
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
      File(entry).writeAsStringSync('fn main() { println!("after stop"); }');
      final (code, nextOutput, nextErrors) = await run();
      expect(code, 0, reason: nextErrors.join('\n'));
      expect(nextOutput, ['after stop']);
    },
    timeout: const Timeout(Duration(minutes: 2)),
  );

  testWidgets(
    'shipped terminal delegate executes cancels and runs fresh native source',
    (tester) async {
      final previousProfile = StudioProfile.current;
      StudioProfile.current = rustProfile;
      addTearDown(() => StudioProfile.current = previousProfile);
      expect(rustProfile.terminalCommandDelegate, isNotNull);
      final manager = TerminalManager()
        ..commandDelegate = rustProfile.terminalCommandDelegate;
      addTearDown(manager.dispose);
      final session = manager.create(sandboxRoot: project.path);
      final backend = session.backend;
      expect(backend, isA<SandboxShellBackend>());
      final chunks = <ShellChunk>[];
      final started = Completer<void>();
      final subscription = backend.output.listen((chunk) {
        chunks.add(chunk);
        if (chunk.kind == OutputKind.stdout &&
            chunk.text.contains('terminal cancel ready') &&
            !started.isCompleted) {
          started.complete();
        }
      });
      addTearDown(subscription.cancel);

      String stdout() => chunks
          .where((chunk) => chunk.kind == OutputKind.stdout)
          .map((chunk) => chunk.text)
          .join();
      String stderr() => chunks
          .where((chunk) => chunk.kind == OutputKind.stderr)
          .map((chunk) => chunk.text)
          .join();

      File(
        entry,
      ).writeAsStringSync('fn main() { println!("terminal native marker"); }');
      await session
          .submit('rust run main.rs')
          .timeout(const Duration(seconds: 30));
      expect(backend.lastExitCode, 0, reason: stderr());
      expect(stdout(), contains('terminal native marker'));
      expect(
        session.lines.map((line) => line.text),
        contains('terminal native marker'),
      );

      File(entry).writeAsStringSync(
        'fn main() { println!("terminal cancel ready"); loop { std::hint::black_box(1); } }',
      );
      final execution = session.submit('rust run main.rs');
      try {
        await started.future.timeout(const Duration(seconds: 30));
      } finally {
        await backend.interrupt();
        await execution.timeout(const Duration(seconds: 30));
      }
      // The shared shell deliberately omits a cancelled process's status.
      // Native exit 130 is asserted separately by the runner cancellation test.
      expect(backend.lastExitCode, isNull);
      expect(
        chunks
            .where((chunk) => chunk.kind == OutputKind.system)
            .map((chunk) => chunk.text)
            .join(),
        contains('^C'),
      );
      expect(stderr(), contains('session cancelled'));
      expect(backend.busy, isFalse);

      chunks.clear();
      File(entry).writeAsStringSync(
        'fn main() { println!("terminal fresh native marker"); }',
      );
      await session
          .submit('rust run main.rs')
          .timeout(const Duration(seconds: 30));
      expect(backend.lastExitCode, 0, reason: stderr());
      expect(stdout(), contains('terminal fresh native marker'));
      expect(stdout(), isNot(contains('terminal cancel ready')));
      expect(session.history, List.filled(3, 'rust run main.rs'));
    },
    timeout: const Timeout(Duration(minutes: 2)),
  );

  testWidgets(
    'editor saves runs stops and runs fresh source',
    (tester) async {
      final previousProfile = StudioProfile.current;
      StudioProfile.current = rustProfile;
      final store = RustProjectStore(
        storageFile: File(p.join(project.path, 'projects.json')),
      );
      final auth = AuthStore(
        storageFile: File(p.join(project.path, 'auth.json')),
      );
      final settings = SettingsStore(
        storageFile: File(p.join(project.path, 'settings.json')),
      );
      addTearDown(() async {
        await tester.pumpWidget(const SizedBox.shrink());
        StudioProfile.current = previousProfile;
        store.dispose();
        auth.dispose();
        settings.dispose();
      });
      final created = await store.createProject(
        name: 'Android Rust editor',
        location: project.path,
        template: ProjectTemplate.rust,
      );
      expect(created.error, isNull);
      final editorProject = created.project!;
      final source = File(p.join(editorProject.path, 'src/main.rs'));
      source.writeAsStringSync('fn main() { println!("editor first run"); }');
      await tester.pumpWidget(
        MaterialApp(
          home: EditorPage(
            project: editorProject,
            auth: auth,
            store: store,
            settings: settings,
            initialOpenPath: source.path,
          ),
        ),
      );

      Future<void> waitFor(bool Function() ready) async {
        final deadline = DateTime.now().add(const Duration(seconds: 45));
        while (!ready() && DateTime.now().isBefore(deadline)) {
          await tester.pump(const Duration(milliseconds: 100));
        }
        expect(
          ready(),
          isTrue,
          reason: tester
              .widgetList<SelectableText>(find.byType(SelectableText))
              .map((widget) => widget.data)
              .join('\n'),
        );
      }

      bool ended() =>
          find.byType(TerminalPane).evaluate().isNotEmpty &&
          !tester.state<TerminalPaneState>(find.byType(TerminalPane)).busy;
      await waitFor(() => find.byType(CodeEditor).evaluate().isNotEmpty);
      await tester.tap(find.byTooltip('运行（长按运行当前文件）'));
      await waitFor(
        () => ended() && find.text('editor first run').evaluate().isNotEmpty,
      );

      final controller = tester
          .widget<CodeEditor>(find.byType(CodeEditor))
          .controller!;
      controller.text =
          'fn main() { println!("editor stop ready"); loop { std::hint::black_box(1); } }';
      await tester.pump();
      await tester.tap(find.byTooltip('运行（长按运行当前文件）'));
      await waitFor(() => find.text('editor stop ready').evaluate().isNotEmpty);
      await tester.tap(find.byTooltip('\u505c\u6b62'));
      await waitFor(
        () => ended() && find.textContaining('130').evaluate().isNotEmpty,
      );
      expect(find.textContaining('130'), findsOneWidget);
      expect(source.readAsStringSync(), controller.text);

      controller.text = 'fn main() { println!("editor fresh run"); }';
      await tester.pump();
      await tester.tap(find.byTooltip('运行（长按运行当前文件）'));
      await waitFor(
        () => ended() && find.text('editor fresh run').evaluate().isNotEmpty,
      );
      expect(source.readAsStringSync(), controller.text);
    },
    timeout: const Timeout(Duration(minutes: 3)),
  );
}
