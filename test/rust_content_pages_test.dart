import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;
import 'package:qfli_rust/main.dart' show rustProfile;
import 'package:qfli_rust/rust_project_store.dart';
import 'package:qfli_studio_core/content/content_repository.dart';
import 'package:qfli_studio_core/editor/editor_fonts.dart';
import 'package:qfli_studio_core/i18n/studio_localizations.dart';
import 'package:qfli_studio_core/pages/local_content_pages.dart';
import 'package:qfli_studio_core/services/studio_profile.dart';
import 'package:qfli_studio_core/store/auth_store.dart';
import 'package:qfli_studio_core/store/settings_store.dart';
import 'package:qfli_studio_core/theme/app_theme.dart';
import 'package:qfli_studio_core/widgets/code_snippet.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late ContentCatalog catalog;
  late Directory temporary;
  StudioProfile? previousProfile;

  setUpAll(() async {
    temporary = await Directory.systemTemp.createTemp('qfli_rust_content_');
    final config = File('.dart_tool/package_config.json').absolute;
    final packages =
        (jsonDecode(await config.readAsString()) as Map)['packages'] as List;
    final shared = packages.cast<Map>().singleWhere(
      (package) => package['name'] == 'qfli_studio_core',
    );
    final directory = config.uri
        .resolve(shared['rootUri'] as String)
        .toFilePath();
    catalog = ContentCatalog.fromJson(
      tutorialsSource: await File(
        p.join(directory, 'assets/content/tutorials.json'),
      ).readAsString(),
      examplesSource: await File(
        p.join(directory, 'assets/content/examples.json'),
      ).readAsString(),
    );
    if (Platform.environment['QFLI_UI_SCREENSHOTS'] != null) {
      final flutter = packages.cast<Map>().singleWhere(
        (package) => package['name'] == 'flutter',
      );
      final flutterDirectory = config.uri
          .resolve(flutter['rootUri'] as String)
          .toFilePath();
      await _loadFont(
        'MaterialIcons',
        File(
          p.join(
            flutterDirectory,
            '../../bin/cache/artifacts/material_fonts/MaterialIcons-Regular.otf',
          ),
        ),
      );
      final mono = File(
        p.join(
          directory,
          'assets/fonts/roboto_mono/static/RobotoMono-Regular.ttf',
        ),
      );
      await _loadFont(EditorFonts.bundledFamily, mono);
      final windowsFonts = Platform.environment['WINDIR'];
      final sans = windowsFonts == null
          ? mono
          : File(p.join(windowsFonts, 'Fonts', 'msyh.ttc'));
      await _loadFont('Roboto', await sans.exists() ? sans : mono);
    }
  });

  setUp(() {
    previousProfile = StudioProfile.current;
    StudioProfile.current = rustProfile;
  });
  tearDown(() => StudioProfile.current = previousProfile);
  tearDownAll(() => temporary.delete(recursive: true));

  for (final size in [const Size(390, 844), const Size(1280, 900)]) {
    for (final examplesPage in [false, true]) {
      final page = examplesPage ? 'examples' : 'tutorials';
      final width = size.width.toInt();
      testWidgets('real Rust $page catalog, detail and dialog fit $width px', (
        tester,
      ) async {
        tester.view.physicalSize = size;
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);
        final directory = temporary.createTempSync('case_');
        final store = RustProjectStore(
          storageFile: File(p.join(directory.path, 'projects.json')),
        );
        final auth = AuthStore(
          storageFile: File(p.join(directory.path, 'auth.json')),
        );
        final settings = SettingsStore(
          storageFile: File(p.join(directory.path, 'settings.json')),
        );
        await tester.runAsync(
          () => Future.wait([store.load(), auth.load(), settings.load()]),
        );
        addTearDown(() async {
          await tester.pumpWidget(const SizedBox.shrink());
          store.dispose();
          auth.dispose();
          settings.dispose();
        });
        final repository = _CatalogRepository(catalog);
        final filter = ContentFilter.forProduct(rustProfile.productKey);
        final title = examplesPage
            ? catalog.examples.firstWhere(filter.matches).title
            : catalog.tutorials.firstWhere(filter.matches).lessons.first.title;
        const boundary = ValueKey('content-screenshot');
        await tester.pumpWidget(
          RepaintBoundary(
            key: boundary,
            child: MaterialApp(
              debugShowCheckedModeBanner: false,
              locale: const Locale('en'),
              localizationsDelegates: const [StudioLocalizations.delegate],
              theme: AppTheme.light,
              home: examplesPage
                  ? ExampleCodeTab(
                      language: 'rust',
                      repository: repository,
                      store: store,
                      auth: auth,
                      settings: settings,
                    )
                  : LocalTutorialsTab(
                      language: 'rust',
                      repository: repository,
                      store: store,
                      auth: auth,
                      settings: settings,
                    ),
            ),
          ),
        );
        await tester.pumpAndSettle();
        expect(find.text(title), findsOneWidget);
        expect(find.byType(CodeSnippet), findsNothing);
        expect(find.byType(SelectableText), findsNothing);
        expect(
          tester.getSize(find.byType(ListView)).width,
          lessThanOrEqualTo(960),
        );
        expect(tester.takeException(), isNull);
        await _capture(tester, boundary, '$page-$width-catalog');

        await tester.tap(find.text(title));
        await tester.pumpAndSettle();
        expect(find.byType(CodeSnippet), findsOneWidget);
        final l10n = StudioLocalizations.of(
          tester.element(find.byType(CodeSnippet)),
        );
        expect(find.byTooltip(l10n.importCodeEditor), findsOneWidget);
        expect(find.byTooltip(l10n.importCodeProject), findsOneWidget);
        expect(tester.takeException(), isNull);
        await _capture(tester, boundary, '$page-$width-detail');

        final command = find.byTooltip(l10n.importCodeProject);
        await tester.ensureVisible(command);
        await tester.pumpAndSettle();
        await tester.tap(command);
        await tester.pumpAndSettle();
        expect(find.byKey(const ValueKey('import-file-name')), findsOneWidget);
        expect(
          find.byKey(const ValueKey('import-project-name')),
          findsOneWidget,
        );
        final button = tester.getRect(
          find.byKey(const ValueKey('import-code-confirm')),
        );
        expect(button.left, greaterThanOrEqualTo(0));
        expect(button.right, lessThanOrEqualTo(size.width));
        expect(button.bottom, lessThanOrEqualTo(size.height));
        expect(tester.takeException(), isNull);
        await _capture(tester, boundary, '$page-$width-dialog');
      });
    }
  }
}

Future<void> _loadFont(String family, File file) async {
  final font = FontLoader(family)
    ..addFont(Future.value(ByteData.sublistView(await file.readAsBytes())));
  await font.load();
}

Future<void> _capture(WidgetTester tester, Key key, String name) async {
  final destination = Platform.environment['QFLI_UI_SCREENSHOTS'];
  if (destination == null) return;
  final boundary = tester.renderObject<RenderRepaintBoundary>(find.byKey(key));
  await tester.runAsync(() async {
    final image = await boundary.toImage();
    try {
      final data = (await image.toByteData(format: ui.ImageByteFormat.png))!;
      final file = File(p.join(destination, '$name.png'));
      await file.parent.create(recursive: true);
      await file.writeAsBytes(data.buffer.asUint8List());
    } finally {
      image.dispose();
    }
  });
}

class _CatalogRepository implements ContentRepository {
  const _CatalogRepository(this.catalog);
  final ContentCatalog catalog;

  @override
  Future<ContentCatalog> load() async => catalog;
  @override
  Future<List<TutorialContent>> tutorials({
    ContentFilter filter = const ContentFilter(),
  }) async => catalog.tutorials.where(filter.matches).toList();
  @override
  Future<List<ExampleContent>> examples({
    ContentFilter filter = const ContentFilter(),
  }) async => catalog.examples.where(filter.matches).toList();
}
