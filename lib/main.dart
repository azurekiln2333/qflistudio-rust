import 'dart:async';
import 'dart:ffi';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:qfli_studio_core/app.dart';
import 'package:qfli_studio_core/services/project_templates.dart';
import 'package:qfli_studio_core/services/studio_profile.dart';
import 'package:qfli_studio_core/splash_screen.dart';
import 'package:qfli_studio_core/store/auth_store.dart';
import 'package:qfli_studio_core/store/settings_store.dart';

import 'ohos_native_probe.dart';
import 'rust_content_repository.dart';
import 'rust_project_store.dart';
import 'rust_runner.dart';
import 'rust_terminal_commands.dart';

/// 本 App 的产品名。窗口标题、任务切换器和应用内顶栏都读它。
const String _appTitle = StudioProductCatalog.rustCore;

/// Rust 版档位：同一套内核 UI，收窄成只服务 Rust。
///
/// 单独提出来是为了让测试能直接断言档位，而不必为了一个常量去跑 `main()`。
final StudioProfile rustProfile = StudioProfile(
  id: 'rust',
  appTitle: _appTitle,
  templates: [ProjectTemplate.empty, ProjectTemplate.rust],
  isOffline: true,
  runner: RustProgramRunner(),
  terminalCommandDelegate: rustTerminalCommandDelegate,
  contentRepositoryFactory: RustContentRepository.new,
  productKey: StudioProductCatalog.rustCoreKey,
  showHomeTabs: false,
  runtimeKind: Platform.isAndroid ? 'rustc-miri' : 'Rust 工具链',
  runtimeStatus:
      Platform.isAndroid &&
          (Abi.current() == Abi.androidX64 || Abi.current() == Abi.androidArm64)
      ? 'available'
      : 'unavailable',
  supportedFileExtensions: ['.rs'],
  // main.rs 排在默认入口表前面，保证本版一定先命中它。
  entryFileNames: ['main.rs', 'src/main.rs'],
);

Future<void> main() async {
  final binding = WidgetsFlutterBinding.ensureInitialized();
  final nativeStartup = !kIsWeb && defaultTargetPlatform == TargetPlatform.ohos;
  if (nativeStartup) binding.deferFirstFrame();
  if (kDebugMode && defaultTargetPlatform == TargetPlatform.ohos) {
    try {
      debugPrint(
        'QFLI native ABI probe: ${verifyOhosNativeProbe().toRadixString(16)}',
      );
    } catch (error) {
      debugPrint('QFLI native ABI probe failed: $error');
    }
  }

  // 在 runApp 之前定档。
  StudioProfile.current = rustProfile;

  final store = RustProjectStore();
  final auth = AuthStore();
  final settings = SettingsStore();
  final ready = ValueNotifier<bool>(false);
  runApp(QfliApp(store: store, auth: auth, settings: settings, ready: ready));

  const platformChannel = MethodChannel('qflistudio/platform');
  Future<void> reportProgress(double progress) async {
    try {
      await platformChannel.invokeMethod<void>('startupProgress', {
        'progress': progress,
      });
    } on PlatformException catch (error) {
      debugPrint('Startup progress unavailable: ${error.code}');
    } on MissingPluginException {
      // Other platform shells use the Flutter startup screen.
    }
  }

  Future<void> completeStartup() async {
    try {
      final minimumDisplay = nativeStartup
          ? Future<void>.delayed(const Duration(milliseconds: 1100))
          : Future<void>.value();
      if (nativeStartup) {
        await Future<void>.delayed(const Duration(milliseconds: 160));
      }
      await AppBootstrap.run(
        store: store,
        auth: auth,
        settings: settings,
        ready: ready,
        onProgress: nativeStartup
            ? (progress) => unawaited(reportProgress(progress))
            : null,
      );
      await Future.wait([
        minimumDisplay,
        if (nativeStartup)
          Future<void>.delayed(const Duration(milliseconds: 320)),
      ]);
      // Keep the native splash until the home page is built and laid out.
      if (nativeStartup) await binding.endOfFrame;
    } finally {
      if (nativeStartup) binding.allowFirstFrame();
    }
  }

  binding.addPostFrameCallback((_) {
    unawaited(completeStartup());
  });
}
