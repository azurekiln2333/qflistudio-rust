import 'dart:convert';
import 'dart:ffi';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:path/path.dart' as p;
import 'package:qfli_studio_core/services/app_paths.dart';

const _rustVersion = '1.98.1';
const _rustCommit = '48a229ceaefd4985c50990b14116b6d856af0985';
const _guestTarget = 'x86_64-unknown-linux-gnu';
final _checksumPattern = RegExp(r'^[a-f0-9]{64}$');
final _nativeAssets = NativeMiriAssets();

class NativeMiriTarget {
  const NativeMiriTarget({required this.platform, required this.architecture});

  factory NativeMiriTarget.current() => NativeMiriTarget(
    platform: Platform.operatingSystem,
    architecture: Abi.current().toString().split('_').last,
  );

  final String platform;
  final String architecture;

  String get key => '$platform-$architecture';
  String get manifestAsset => platform == 'ohos'
      ? 'assets/miri/manifest.json'
      : 'assets/miri/manifest.$key.json';

  Set<String> get nativeHosts => switch ((platform, architecture)) {
    ('ohos', 'arm64') => {'aarch64-unknown-linux-ohos'},
    ('ohos', 'x64') => {'x86_64-unknown-linux-ohos'},
    ('android', 'arm64') => {'aarch64-linux-android'},
    ('android', 'x64') => {'x86_64-linux-android'},
    ('ios', 'arm64') => {'aarch64-apple-ios', 'aarch64-apple-ios-sim'},
    ('ios', 'x64') => {'x86_64-apple-ios'},
    ('macos', 'arm64') => {'aarch64-apple-darwin'},
    ('macos', 'x64') => {'x86_64-apple-darwin'},
    ('windows', 'arm64') => {'aarch64-pc-windows-msvc'},
    ('windows', 'x64') => {'x86_64-pc-windows-gnu', 'x86_64-pc-windows-msvc'},
    ('linux', 'arm64') => {
      'aarch64-unknown-linux-gnu',
      'aarch64-unknown-linux-musl',
    },
    ('linux', 'x64') => {
      'x86_64-unknown-linux-gnu',
      'x86_64-unknown-linux-musl',
    },
    _ => const {},
  };
}

class NativeMiriRuntime {
  const NativeMiriRuntime({
    required this.target,
    required this.nativeHost,
    required this.sysrootPath,
    required this.libraryPath,
    this.backendPath,
  });

  final NativeMiriTarget target;
  final String nativeHost;
  final String sysrootPath;
  final String libraryPath;
  final String? backendPath;
}

Future<NativeMiriRuntime> prepareNativeMiriAssets({NativeMiriTarget? target}) =>
    _nativeAssets.prepare(target: target);

/// Data assets are writable; executable libraries remain in the native bundle.
class NativeMiriAssets {
  NativeMiriAssets({
    AssetBundle? bundle,
    Future<String?> Function()? storageDirectory,
    Future<String?> Function()? nativeLibraryDirectory,
  }) : _bundle = bundle ?? rootBundle,
       _storageDirectory = storageDirectory ?? AppPaths.storageDirectory,
       _nativeLibraryDirectory = nativeLibraryDirectory;

  final AssetBundle _bundle;
  final Future<String?> Function() _storageDirectory;
  final Future<String?> Function()? _nativeLibraryDirectory;
  final Map<String, Future<NativeMiriRuntime>> _prepared = {};

  Future<NativeMiriRuntime> prepare({NativeMiriTarget? target}) {
    final selected = target ?? NativeMiriTarget.current();
    return _prepared.putIfAbsent(
      selected.key,
      () => _extract(selected).onError<Object>((error, stackTrace) {
        _prepared.remove(selected.key);
        Error.throwWithStackTrace(error, stackTrace);
      }),
    );
  }

  Future<NativeMiriRuntime> _extract(NativeMiriTarget target) async {
    if (target.nativeHosts.isEmpty) {
      throw UnsupportedError(
        'Rust native runtime is unavailable for ${target.key}',
      );
    }
    final manifest = _RuntimeManifest.decode(
      jsonDecode(await _bundle.loadString(target.manifestAsset)),
      target,
    );
    final storage = await _storageDirectory();
    if (storage == null) {
      throw const FileSystemException('Rust runtime storage is unavailable');
    }
    final directory = Directory(p.join(storage, 'rust_runtime', manifest.id));
    await directory.create(recursive: true);
    for (final entry in manifest.files) {
      final file = File(p.join(directory.path, entry.path));
      if (await file.exists() && await file.length() == entry.size) continue;
      final bytes = await _bundle.load('assets/miri/${entry.asset}');
      if (bytes.lengthInBytes != entry.size) {
        throw FormatException(
          'Rust runtime asset size mismatch: ${entry.path}',
        );
      }
      await file.parent.create(recursive: true);
      final temporary = File('${file.path}.part');
      await temporary.writeAsBytes(
        bytes.buffer.asUint8List(bytes.offsetInBytes, bytes.lengthInBytes),
        flush: true,
      );
      if (await file.exists()) await file.delete();
      await temporary.rename(file.path);
    }

    var library = manifest.libraryName;
    String? backend;
    if (manifest.schemaVersion == 2) {
      final nativeDirectory = await _resolveNativeDirectory(target);
      library = p.join(nativeDirectory, manifest.libraryName);
      await _requireNativeFile(library);
      for (final entry in manifest.nativeLibraries) {
        final path = p.join(nativeDirectory, entry.path);
        await _requireNativeFile(path);
        if (entry.role == 'backend') backend = path;
      }
    }
    return NativeMiriRuntime(
      target: target,
      nativeHost: manifest.nativeHost,
      sysrootPath: p.join(directory.path, 'sysroot'),
      libraryPath: library,
      backendPath: backend,
    );
  }

  Future<String> _resolveNativeDirectory(NativeMiriTarget target) async {
    String? directory;
    final override = _nativeLibraryDirectory;
    if (override != null) {
      directory = await override();
    } else if (target.platform == 'android' ||
        target.platform == 'ios' ||
        target.platform == 'macos') {
      directory = await const MethodChannel(
        'qflistudio/runtime',
      ).invokeMethod<String>('getRuntimeLibraryDirectory');
    } else {
      directory = p.dirname(Platform.resolvedExecutable);
      if (target.platform == 'linux') directory = p.join(directory, 'lib');
    }
    if (directory == null ||
        !p.isAbsolute(directory) ||
        !await Directory(directory).exists()) {
      throw const FileSystemException(
        'Rust native library directory is unavailable',
      );
    }
    return directory;
  }

  Future<void> _requireNativeFile(String path) async {
    if (!await File(path).exists()) {
      throw FileSystemException('Rust native library is not installed', path);
    }
  }
}

class _RuntimeManifest {
  _RuntimeManifest({
    required this.schemaVersion,
    required this.id,
    required this.nativeHost,
    required this.libraryName,
    required this.files,
    required this.nativeLibraries,
  });

  factory _RuntimeManifest.decode(Object? value, NativeMiriTarget target) {
    if (value is! Map<String, dynamic> ||
        value['schemaVersion'] is! int ||
        (value['schemaVersion'] != 1 && value['schemaVersion'] != 2) ||
        value['rustVersion'] != _rustVersion ||
        value['rustCommit'] != _rustCommit ||
        value['guestTarget'] != _guestTarget ||
        !target.nativeHosts.contains(value['nativeHost']) ||
        value['id'] is! String ||
        !_checksumPattern.hasMatch(value['id'] as String) ||
        value['files'] is! List) {
      throw const FormatException('Invalid Rust runtime asset manifest');
    }
    final schemaVersion = value['schemaVersion'] as int;
    if (schemaVersion == 1 && target.platform != 'ohos' ||
        schemaVersion == 2 &&
            (value['platform'] != target.platform ||
                value['architecture'] != target.architecture ||
                value['nativeLibraries'] is! List)) {
      throw const FormatException(
        'Rust runtime manifest does not match this host',
      );
    }
    final paths = <String>{};
    final files = <_RuntimeFile>[];
    for (final entry in value['files'] as List) {
      if (entry is! Map<String, dynamic> ||
          !_isRelativePath(entry['path']) ||
          entry['asset'] is! String ||
          !RegExp(r'^[a-f0-9]{64}\.bin$').hasMatch(entry['asset'] as String) ||
          entry['sha256'] is! String ||
          !_checksumPattern.hasMatch(entry['sha256'] as String) ||
          entry['asset'] != '${entry['sha256']}.bin' ||
          entry['size'] is! int ||
          (entry['size'] as int) < 0 ||
          !paths.add(entry['path'] as String)) {
        throw const FormatException('Invalid Rust runtime asset entry');
      }
      files.add(
        _RuntimeFile(
          path: entry['path'] as String,
          asset: entry['asset'] as String,
          size: entry['size'] as int,
        ),
      );
    }
    var libraryName = 'libqfli_miri.so';
    final nativeLibraries = <_NativeLibrary>[];
    if (schemaVersion == 2) {
      if (!_isRelativePath(value['libraryName'])) {
        throw const FormatException('Invalid Rust native library path');
      }
      libraryName = value['libraryName'] as String;
      final nativePaths = <String>{};
      var hasBackend = false;
      for (final entry in value['nativeLibraries'] as List) {
        if (entry is! Map<String, dynamic> ||
            !_isRelativePath(entry['path']) ||
            !const {
              'adapter',
              'backend',
              'dependency',
            }.contains(entry['role']) ||
            !nativePaths.add(entry['path'] as String) ||
            entry['role'] == 'backend' && hasBackend) {
          throw const FormatException('Invalid Rust native library entry');
        }
        hasBackend |= entry['role'] == 'backend';
        nativeLibraries.add(
          _NativeLibrary(
            path: entry['path'] as String,
            role: entry['role'] as String,
          ),
        );
      }
    }
    return _RuntimeManifest(
      schemaVersion: schemaVersion,
      id: value['id'] as String,
      nativeHost: value['nativeHost'] as String,
      libraryName: libraryName,
      files: files,
      nativeLibraries: nativeLibraries,
    );
  }

  final int schemaVersion;
  final String id;
  final String nativeHost;
  final String libraryName;
  final List<_RuntimeFile> files;
  final List<_NativeLibrary> nativeLibraries;
}

bool _isRelativePath(Object? value) =>
    value is String &&
    !value.contains(r'\') &&
    !value.contains(':') &&
    !value.contains('\u0000') &&
    !p.posix.isAbsolute(value) &&
    value
        .split('/')
        .every((part) => part.isNotEmpty && part != '.' && part != '..');

class _RuntimeFile {
  const _RuntimeFile({
    required this.path,
    required this.asset,
    required this.size,
  });

  final String path;
  final String asset;
  final int size;
}

class _NativeLibrary {
  const _NativeLibrary({required this.path, required this.role});

  final String path;
  final String role;
}
