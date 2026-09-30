import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:qfli_rust/main.dart' as application;
import 'package:qfli_studio_core/app.dart';
import 'package:qfli_studio_core/pages/home_page.dart';
import 'package:qfli_studio_core/splash_screen.dart';

void main() {
  testWidgets('OHOS releases its first frame after the home page is ready', (
    tester,
  ) async {
    final binding = tester.binding;
    binding.resetFirstFrameSent();
    debugDefaultTargetPlatformOverride = TargetPlatform.ohos;
    final directory = Directory.systemTemp.createTempSync('qfli_startup_');
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    final progress = <double>[];
    messenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (_) async => directory.path,
    );
    messenger.setMockMethodCallHandler(
      const MethodChannel('qflistudio/platform'),
      (call) async {
        if (call.method == 'startupProgress') {
          progress.add((call.arguments as Map)['progress'] as double);
        }
        return null;
      },
    );
    addTearDown(() async {
      await tester.pumpWidget(const SizedBox.shrink());
      debugDefaultTargetPlatformOverride = null;
      if (!binding.sendFramesToEngine) binding.allowFirstFrame();
      await directory.delete(recursive: true);
    });

    await application.main();
    expect(binding.sendFramesToEngine, isFalse);
    await tester.pump();
    expect(find.byType(SplashScreen), findsOneWidget);
    await tester.pump(const Duration(milliseconds: 160));
    final app = tester.widget<QfliApp>(find.byType(QfliApp));
    for (var attempt = 0; attempt < 100 && !app.ready!.value; attempt++) {
      await tester.runAsync(
        () => Future<void>.delayed(const Duration(milliseconds: 10)),
      );
      await tester.pump();
    }
    expect(app.ready!.value, isTrue);
    expect(progress, [1 / 3, 2 / 3, 1.0]);
    expect(find.byType(HomePage), findsOneWidget);
    expect(find.byType(SplashScreen), findsNothing);
    expect(binding.sendFramesToEngine, isFalse);

    await tester.pump(const Duration(milliseconds: 1100));
    await tester.pump();
    expect(binding.sendFramesToEngine, isTrue);
    expect(find.byType(HomePage), findsOneWidget);
    expect(tester.takeException(), isNull);
    debugDefaultTargetPlatformOverride = null;
  });
}
