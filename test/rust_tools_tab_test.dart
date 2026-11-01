import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:qfli_rust/rust_tool_utilities.dart';
import 'package:qfli_rust/rust_tools_tab.dart';
import 'package:qfli_studio_core/models/project.dart';
import 'package:qfli_studio_core/store/project_store.dart';

void main() {
  late _ToolStore store;
  setUp(() {
    store = _ToolStore();
  });
  tearDown(() {
    store.dispose();
  });

  Future<void> open(
    WidgetTester tester, {
    double width = 900,
    double textScale = 1,
    VoidCallback? terminal,
    RustProjectInspector Function()? inspector,
  }) async {
    tester.view.resetPhysicalSize();
    tester.view.physicalSize = Size(width, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(
      MaterialApp(
        home: MediaQuery(
          data: MediaQueryData(
            size: Size(width, 800),
            textScaler: TextScaler.linear(textScale),
          ),
          child: Scaffold(
            body: RustToolsTab(
              store: store,
              onOpenTerminal: terminal ?? () {},
              inspectorFactory: inspector ?? () => _ImmediateInspector(),
            ),
          ),
        ),
      ),
    );
    await tester.pump();
  }

  Future<void> reveal(
    WidgetTester tester,
    Finder finder, {
    double delta = 400,
  }) async {
    // Slivers outside the viewport are offstage. Scroll to create/layout the
    // requested section before ensureVisible tries to reveal its control.
    await tester.scrollUntilVisible(
      finder,
      delta,
      scrollable: find
          .descendant(
            of: find.byKey(const PageStorageKey<String>('rust-tools-scroll')),
            matching: find.byType(Scrollable),
          )
          .first,
      maxScrolls: 100,
    );
    await tester.pump();
    expect(finder, findsOneWidget);
  }

  testWidgets(
    'Rust tools are direct sections and common tools and terminal remain usable',
    (tester) async {
      var terminalOpened = false;
      await open(tester, terminal: () => terminalOpened = true);
      expect(find.byType(Scaffold), findsOneWidget);
      expect(find.byType(AppBar), findsNothing);
      expect(find.text('整数、类型边界与位运算'), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('rust-tools-terminal')));
      expect(terminalOpened, isTrue);
      for (final heading in ['UTF-8 与 Rust 字符串', '本地 Cargo 项目检查']) {
        await reveal(tester, find.text(heading));
        expect(find.byType(Scaffold), findsOneWidget);
        expect(find.byType(AppBar), findsNothing);
      }
      await reveal(tester, find.text('Base64'));
      await tester.tap(find.text('Base64'));
      await tester.pumpAndSettle();
      expect(find.byType(AppBar), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'exact integer results, errors and clipboard use current entered source',
    (tester) async {
      String? clipboard;
      tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        SystemChannels.platform,
        (call) async {
          if (call.method == 'Clipboard.setData') {
            clipboard = (call.arguments as Map)['text'] as String;
          }
          return null;
        },
      );
      await open(tester);
      await tester.enterText(
        find.byKey(const ValueKey('rust-integer-input')),
        '-2i16',
      );
      await tester.pump();
      expect(find.text('-2'), findsWidgets);
      expect(find.text('输入值超出 u8 范围；下方展示显式 as 转换后的截断结果。'), findsOneWidget);
      await tester.ensureVisible(find.byTooltip('复制十进制'));
      await tester.tap(find.byTooltip('复制十进制'));
      await tester.pump();
      expect(clipboard, '-2');
      await tester.ensureVisible(
        find.byKey(const ValueKey('rust-integer-input')),
      );
      await tester.enterText(
        find.byKey(const ValueKey('rust-integer-input')),
        '256u8',
      );
      await tester.pump();
      expect(find.text('输入值超出字面量后缀 u8 的范围，Rust 会报告溢出。'), findsOneWidget);
      await tester.enterText(
        find.byKey(const ValueKey('rust-integer-input')),
        '0b102',
      );
      await tester.pump();
      expect(find.textContaining('请输入十进制、0x'), findsOneWidget);
      expect(find.byTooltip('复制十进制'), findsNothing);
    },
  );

  testWidgets(
    'Rust literal mode parses Unicode and reports actual literal failures',
    (tester) async {
      await open(tester);
      await reveal(tester, find.byKey(const ValueKey('rust-string-mode')));
      await tester.tap(find.byKey(const ValueKey('rust-string-mode')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Rust 字面量').last);
      await tester.pumpAndSettle();
      await tester.ensureVisible(
        find.byKey(const ValueKey('rust-string-input')),
      );
      await tester.enterText(
        find.byKey(const ValueKey('rust-string-input')),
        r'"\u{1F980}"',
      );
      await tester.pump();
      expect(find.text('F0 9F A6 80'), findsOneWidget);
      expect(find.text(r'"🦀"'), findsOneWidget);
      await tester.enterText(
        find.byKey(const ValueKey('rust-string-input')),
        r'"\xFF"',
      );
      await tester.pump();
      expect(find.textContaining('值不超过 7F'), findsOneWidget);
    },
  );

  testWidgets(
    'local selection shows current project and stale responses cannot replace it',
    (tester) async {
      final first = Project.create(name: 'First', path: '/first');
      final second = Project.create(name: 'Second', path: '/second');
      store.items = [first, second];
      store.lastBrowsedProjectId = first.id;
      final pending = Completer<RustProjectInspection>();
      var probes = 0;
      await open(
        tester,
        inspector: () => probes++ == 0
            ? _PendingInspector(pending.future)
            : _ImmediateInspector(),
      );
      await reveal(tester, find.text('First'));
      await tester.tap(find.text('First'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      await tester.tap(find.text('Second').last);
      await tester.pumpAndSettle();
      expect(find.text('/second'), findsOneWidget);
      pending.complete(
        const RustProjectInspection(root: '/first', targetMessage: 'OLD'),
      );
      await tester.pumpAndSettle();
      expect(find.text('OLD'), findsNothing);
      expect(find.text('/second'), findsOneWidget);
    },
  );

  testWidgets(
    '320px and double text scale keep controls usable and preserve input on scroll',
    (tester) async {
      await open(tester, width: 320, textScale: 2);
      await tester.enterText(
        find.byKey(const ValueKey('rust-integer-input')),
        '0x7f',
      );
      await tester.pump();
      expect(tester.takeException(), isNull);
      for (final key in [
        'rust-pointer-width',
        'rust-bit-operand',
        'rust-string-input',
      ]) {
        await reveal(tester, find.byKey(ValueKey(key)));
        await tester.pump();
        expect(tester.takeException(), isNull, reason: key);
      }
      await reveal(tester, find.text('Base64'));
      await tester.pump();
      expect(tester.takeException(), isNull);
      await reveal(
        tester,
        find.byKey(const ValueKey('rust-integer-input')),
        delta: -500,
      );
      final field = tester.widget<TextField>(
        find.byKey(const ValueKey('rust-integer-input')),
      );
      expect(field.controller!.text, '0x7f');
      expect(tester.takeException(), isNull);
    },
  );
}

class _ToolStore extends ProjectStore {
  List<Project> items = [];

  @override
  List<Project> get projects => items;

  @override
  Project? projectById(String? id) =>
      items.where((item) => item.id == id).firstOrNull;
}

class _ImmediateInspector extends RustProjectInspector {
  @override
  Future<RustProjectInspection> inspect(String projectPath) async =>
      RustProjectInspection(root: projectPath, targetMessage: '本地检查完成');
}

class _PendingInspector extends RustProjectInspector {
  _PendingInspector(this.result);
  final Future<RustProjectInspection> result;

  @override
  Future<RustProjectInspection> inspect(String projectPath) => result;
}
