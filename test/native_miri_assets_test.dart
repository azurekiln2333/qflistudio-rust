import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;
import 'package:qfli_rust/native_miri_assets.dart';

const _contentId =
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _assetHash =
    'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory storage;
  late Directory native;
  late _MemoryBundle bundle;

  setUp(() {
    storage = Directory.systemTemp.createTempSync('qfli_miri_assets_');
    native = Directory(p.join(storage.path, 'installed_native'))..createSync();
    bundle = _MemoryBundle();
  });

  tearDown(() => storage.deleteSync(recursive: true));

  Map<String, Object?> manifest({
    String platform = 'windows',
    String architecture = 'x64',
    String nativeHost = 'x86_64-pc-windows-gnu',
    String libraryName = 'qfli_miri.dll',
    String? backend,
    int schemaVersion = 2,
  }) => {
    'schemaVersion': schemaVersion,
    'platform': platform,
    'architecture': architecture,
    'rustVersion': '1.98.1',
    'rustCommit': '48a229ceaefd4985c50990b14116b6d856af0985',
    'nativeHost': nativeHost,
    'guestTarget': 'x86_64-unknown-linux-gnu',
    'id': _contentId,
    'libraryName': libraryName,
    'nativeLibraries': [
      {'role': 'adapter', 'path': libraryName},
      if (backend != null) {'role': 'backend', 'path': backend},
    ],
    'files': [
      {
        'path': 'sysroot/lib/rustlib/x86_64-unknown-linux-gnu/lib/libstd.rlib',
        'asset': '$_assetHash.bin',
        'sha256': _assetHash,
        'size': 3,
      },
    ],
  };

  void install(String relative) {
    final file = File(p.join(native.path, relative));
    file.parent.createSync(recursive: true);
    file.writeAsBytesSync([1]);
  }

  void putManifest(Map<String, Object?> value, NativeMiriTarget target) {
    bundle.assets[target.manifestAsset] = utf8.encode(jsonEncode(value));
    bundle.assets['assets/miri/$_assetHash.bin'] = [1, 2, 3];
  }

  NativeMiriAssets assets({Future<String?> Function()? nativeDirectory}) =>
      NativeMiriAssets(
        bundle: bundle,
        storageDirectory: () async => storage.path,
        nativeLibraryDirectory: nativeDirectory ?? () async => native.path,
      );

  const windows = NativeMiriTarget(platform: 'windows', architecture: 'x64');

  test(
    'extracts guest data and keeps executable paths in the installation',
    () async {
      putManifest(manifest(backend: 'codegen.dll'), windows);
      install('qfli_miri.dll');
      install('codegen.dll');
      final preparer = assets();
      final first = preparer.prepare(target: windows);
      final second = preparer.prepare(target: windows);
      expect(identical(first, second), isTrue);
      final runtime = await first;
      expect(runtime.libraryPath, p.join(native.path, 'qfli_miri.dll'));
      expect(runtime.backendPath, p.join(native.path, 'codegen.dll'));
      expect(runtime.nativeHost, 'x86_64-pc-windows-gnu');
      expect(
        await File(
          p.join(
            runtime.sysrootPath,
            'lib/rustlib/x86_64-unknown-linux-gnu/lib/libstd.rlib',
          ),
        ).readAsBytes(),
        [1, 2, 3],
      );
      expect(
        File(p.join(runtime.sysrootPath, 'codegen.dll')).existsSync(),
        isFalse,
      );
      expect(bundle.loads[windows.manifestAsset], 1);
    },
  );

  test('preserves schema-1 OHOS loader name and sysroot layout', () async {
    const target = NativeMiriTarget(platform: 'ohos', architecture: 'x64');
    putManifest(
      manifest(
        schemaVersion: 1,
        platform: 'ohos',
        nativeHost: 'x86_64-unknown-linux-ohos',
      ),
      target,
    );
    final runtime = await assets().prepare(target: target);
    expect(runtime.libraryPath, 'libqfli_miri.so');
    expect(runtime.backendPath, isNull);
    expect(Directory(runtime.sysrootPath).existsSync(), isTrue);
    expect(bundle.loads['assets/miri/manifest.json'], 1);
  });

  for (final (platform, architecture, host, library, backend) in [
    (
      'android',
      'arm64',
      'aarch64-linux-android',
      'libqfli_miri.so',
      'libcodegen.so',
    ),
    (
      'android',
      'x64',
      'x86_64-linux-android',
      'libqfli_miri.so',
      'libcodegen.so',
    ),
    (
      'ios',
      'arm64',
      'aarch64-apple-ios',
      'qfli_miri.framework/qfli_miri',
      'codegen.framework/codegen',
    ),
    (
      'ios',
      'arm64',
      'aarch64-apple-ios-sim',
      'qfli_miri.framework/qfli_miri',
      'codegen.framework/codegen',
    ),
    (
      'ios',
      'x64',
      'x86_64-apple-ios',
      'qfli_miri.framework/qfli_miri',
      'codegen.framework/codegen',
    ),
    (
      'macos',
      'arm64',
      'aarch64-apple-darwin',
      'qfli_miri.framework/qfli_miri',
      'codegen.framework/codegen',
    ),
  ]) {
    test('$host uses the platform native directory', () async {
      final target = NativeMiriTarget(
        platform: platform,
        architecture: architecture,
      );
      putManifest(
        manifest(
          platform: platform,
          architecture: architecture,
          nativeHost: host,
          libraryName: library,
          backend: backend,
        ),
        target,
      );
      install(library);
      install(backend);
      final calls = <MethodCall>[];
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(const MethodChannel('qflistudio/runtime'), (
            call,
          ) async {
            calls.add(call);
            return native.path;
          });
      addTearDown(
        () => TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
            .setMockMethodCallHandler(
              const MethodChannel('qflistudio/runtime'),
              null,
            ),
      );
      final runtime = await NativeMiriAssets(
        bundle: bundle,
        storageDirectory: () async => storage.path,
      ).prepare(target: target);
      expect(runtime.libraryPath, p.join(native.path, library));
      expect(runtime.backendPath, p.join(native.path, backend));
      expect(calls.single.method, 'getRuntimeLibraryDirectory');
    });
  }

  for (final (field, value) in <(String, Object?)>[
    ('platform', 'android'),
    ('architecture', 'arm64'),
    ('nativeHost', 'aarch64-linux-android'),
    ('rustVersion', '1.0.0'),
    ('rustCommit', '0000000000000000000000000000000000000000'),
    ('guestTarget', 'x86_64-pc-windows-gnu'),
    ('schemaVersion', 1),
    ('schemaVersion', 2.0),
    ('libraryName', '../qfli_miri.dll'),
    ('libraryName', r'C:\qfli_miri.dll'),
  ]) {
    test(
      'rejects an incompatible manifest $field=$value before extraction',
      () async {
        putManifest(manifest()..[field] = value, windows);
        await expectLater(
          assets().prepare(target: windows),
          throwsFormatException,
        );
        expect(
          Directory(p.join(storage.path, 'rust_runtime')).existsSync(),
          isFalse,
        );
      },
    );
  }

  for (final path in [
    '../escaped',
    '/absolute',
    r'sysroot\escaped',
    'sysroot/C:escaped',
  ]) {
    test('rejects unsafe data path $path', () async {
      final value = manifest();
      ((value['files'] as List).single as Map)['path'] = path;
      putManifest(value, windows);
      await expectLater(
        assets().prepare(target: windows),
        throwsFormatException,
      );
    });
  }

  test(
    'retries after extraction failure and replaces the failed future',
    () async {
      putManifest(manifest(), windows);
      install('qfli_miri.dll');
      bundle.assets['assets/miri/$_assetHash.bin'] = [1];
      final preparer = assets();
      await expectLater(
        preparer.prepare(target: windows),
        throwsFormatException,
      );
      bundle.assets['assets/miri/$_assetHash.bin'] = [1, 2, 3];
      final runtime = await preparer.prepare(target: windows);
      expect(Directory(runtime.sysrootPath).existsSync(), isTrue);
      expect(bundle.loads[windows.manifestAsset], 2);
    },
  );

  test(
    'retries missing native libraries without reloading completed data',
    () async {
      putManifest(manifest(), windows);
      final preparer = assets();
      await expectLater(
        preparer.prepare(target: windows),
        throwsA(isA<FileSystemException>()),
      );
      install('qfli_miri.dll');
      final runtime = await preparer.prepare(target: windows);
      expect(runtime.libraryPath, p.join(native.path, 'qfli_miri.dll'));
      expect(bundle.loads['assets/miri/$_assetHash.bin'], 1);
    },
  );

  test(
    'does not fall back to a data directory for missing native installation',
    () async {
      putManifest(manifest(), windows);
      await expectLater(
        assets(nativeDirectory: () async => null).prepare(target: windows),
        throwsA(isA<FileSystemException>()),
      );
    },
  );

  test('rejects two conflicting backend entries', () async {
    final value = manifest(backend: 'first.dll');
    (value['nativeLibraries'] as List).add({
      'role': 'backend',
      'path': 'second.dll',
    });
    putManifest(value, windows);
    await expectLater(assets().prepare(target: windows), throwsFormatException);
  });

  test('rejects native libraries with unknown roles', () async {
    final value = manifest();
    ((value['nativeLibraries'] as List).single as Map)['role'] = 'unknown';
    putManifest(value, windows);
    await expectLater(assets().prepare(target: windows), throwsFormatException);
  });

  test('unsupported architectures cannot load an unrelated manifest', () async {
    const target = NativeMiriTarget(platform: 'android', architecture: 'arm');
    await expectLater(assets().prepare(target: target), throwsUnsupportedError);
    expect(bundle.loads, isEmpty);
  });
}

class _MemoryBundle extends CachingAssetBundle {
  final Map<String, List<int>> assets = {};
  final Map<String, int> loads = {};

  @override
  Future<ByteData> load(String key) async {
    loads.update(key, (count) => count + 1, ifAbsent: () => 1);
    final bytes = assets[key];
    if (bytes == null) throw StateError('Missing fixture asset $key');
    return ByteData.sublistView(Uint8List.fromList(bytes));
  }

  @override
  Future<String> loadString(String key, {bool cache = true}) async =>
      utf8.decode((await load(key)).buffer.asUint8List());
}
