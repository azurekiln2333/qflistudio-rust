import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:path/path.dart' as p;
import 'package:qfli_studio_core/services/app_paths.dart';

Future<String>? _preparedSysroot;

Future<String> prepareOhosMiriAssets() => _preparedSysroot ??=
    _extractOhosMiriAssets().onError<Object>((error, stackTrace) {
      _preparedSysroot = null;
      Error.throwWithStackTrace(error, stackTrace);
    });

Future<String> _extractOhosMiriAssets() async {
  final json = jsonDecode(
    await rootBundle.loadString('assets/miri/manifest.json'),
  );
  if (json is! Map<String, dynamic> ||
      json['schemaVersion'] != 1 ||
      json['guestTarget'] != 'x86_64-unknown-linux-gnu' ||
      json['id'] is! String ||
      !RegExp(r'^[a-f0-9]{64}$').hasMatch(json['id'] as String) ||
      json['files'] is! List) {
    throw const FormatException('Invalid Rust runtime asset manifest');
  }
  final storage = await AppPaths.storageDirectory();
  if (storage == null) {
    throw const FileSystemException('Rust runtime storage is unavailable');
  }
  final directory = Directory(
    p.join(storage, 'rust_runtime', json['id'] as String),
  );
  await directory.create(recursive: true);
  for (final entry in json['files'] as List) {
    if (entry is! Map<String, dynamic> ||
        entry['path'] is! String ||
        entry['asset'] is! String ||
        !RegExp(r'^[a-f0-9]{64}\.bin$').hasMatch(entry['asset'] as String) ||
        entry['size'] is! int ||
        (entry['size'] as int) < 0) {
      throw const FormatException('Invalid Rust runtime asset entry');
    }
    final relative = entry['path'] as String;
    if (relative.contains(r'\') ||
        relative
            .split('/')
            .any((part) => part.isEmpty || part == '..' || part == '.') ||
        p.isAbsolute(relative)) {
      throw const FormatException('Invalid Rust runtime asset path');
    }
    final file = File(p.join(directory.path, relative));
    if (await file.exists() && await file.length() == entry['size']) continue;
    final bytes = await rootBundle.load('assets/miri/${entry['asset']}');
    if (bytes.lengthInBytes != entry['size']) {
      throw FormatException('Rust runtime asset size mismatch: $relative');
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
  return p.join(directory.path, 'sysroot');
}
