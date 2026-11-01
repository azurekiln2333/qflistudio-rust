// Layout-only fixture: generated program output is not evidence of Rust compilation.
import 'dart:async';
import 'dart:io';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:qfli_studio_core/editor/editor_fonts.dart';
import 'package:qfli_studio_core/editor/terminal_pane.dart';
import 'package:qfli_studio_core/store/auth_store.dart';

Future<ByteData> fontBytes(String path) async =>
    ByteData.sublistView(await File(path).readAsBytes());

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() async {
    final mono = FontLoader(EditorFonts.bundledFamily)
      ..addFont(
        fontBytes(
          '../qfli_studio_core/assets/fonts/roboto_mono/static/RobotoMono-Regular.ttf',
        ),
      );
    final icons = FontLoader('MaterialIcons')
      ..addFont(
        fontBytes(
          'D:/ProgramFiles/flutter_ohos/bin/cache/artifacts/material_fonts/MaterialIcons-Regular.otf',
        ),
      );
    await Future.wait([mono.load(), icons.load()]);
  });

  for (final sample in [
    (
      name: 'desktop-dark',
      size: const Size(720, 300),
      brightness: Brightness.dark,
    ),
    (
      name: 'phone-dark',
      size: const Size(360, 300),
      brightness: Brightness.dark,
    ),
    (
      name: 'phone-light',
      size: const Size(360, 300),
      brightness: Brightness.light,
    ),
    (
      name: 'short-viewport',
      size: const Size(360, 120),
      brightness: Brightness.dark,
    ),
    (
      name: 'phone-long-path',
      size: const Size(360, 300),
      brightness: Brightness.dark,
    ),
  ]) {
    testWidgets('render ${sample.name}', (tester) async {
      tester.view.physicalSize = sample.size;
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final auth = AuthStore();
      final paneKey = GlobalKey<TerminalPaneState>();
      final captureKey = GlobalKey();
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData(
            useMaterial3: true,
            fontFamily: EditorFonts.bundledFamily,
            colorScheme: ColorScheme.fromSeed(
              seedColor: const Color(0xff536dfe),
              brightness: sample.brightness,
            ),
          ),
          home: Scaffold(
            body: RepaintBoundary(
              key: captureKey,
              child: SizedBox.expand(
                child: TerminalPane(
                  key: paneKey,
                  workingDirectory: sample.name == 'phone-long-path'
                      ? 'D:/projects/a-very-long-project-directory-name'
                      : 'D:/projects/hello',
                  auth: auth,
                  onlineEnabled: false,
                  onClose: () {},
                ),
              ),
            ),
          ),
        ),
      );
      Future<void> appendRun(String title, List<String> lines) async {
        final run = paneKey.currentState!.attachOutput(
          title: title,
          stdout: Stream<String>.fromIterable(lines),
          stderr: const Stream<String>.empty(),
          exitCode: Future<int>.value(0),
        );
        await tester.pump();
        await run;
        await tester.pumpAndSettle();
      }

      await appendRun('run src/main.rs', ['main.rs', 'Project entry']);
      await appendRun('run src/main2.rs', [
        'main2.rs',
        'Current file',
        'value = 42',
      ]);
      expect(tester.takeException(), isNull);
      final boundary =
          captureKey.currentContext!.findRenderObject()!
              as RenderRepaintBoundary;
      await tester.runAsync(() async {
        final picture = await boundary.toImage(pixelRatio: 2);
        final data = await picture.toByteData(format: ui.ImageByteFormat.png);
        final directory = Directory(
          '.trellis/tasks/10-09-terminal-run-controls/research/screenshots',
        )..createSync(recursive: true);
        await File(
          '${directory.path}/${sample.name}.png',
        ).writeAsBytes(data!.buffer.asUint8List());
        picture.dispose();
      });
      await tester.pumpWidget(const SizedBox.shrink());
      auth.dispose();
    });
  }
}

