import 'native_miri_assets.dart';

/// Preserves the schema-1 OHOS asset preparation entry point.
Future<String> prepareOhosMiriAssets() async {
  final target = NativeMiriTarget(
    platform: 'ohos',
    architecture: NativeMiriTarget.current().architecture,
  );
  return (await prepareNativeMiriAssets(target: target)).sysrootPath;
}
