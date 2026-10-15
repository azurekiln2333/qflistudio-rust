import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:path/path.dart' as p;
import 'package:qfli_studio_core/content/content_repository.dart';

/// Rust-owned catalog, using the shared content model and product filters.
class RustContentRepository implements ContentRepository {
  RustContentRepository({AssetBundle? bundle}) : _bundle = bundle ?? rootBundle;

  static const tutorialAsset = 'assets/content_rust/tutorials.json';
  static const exampleAsset = 'assets/content_rust/examples.json';

  final AssetBundle _bundle;
  Future<ContentCatalog>? _catalog;

  @override
  Future<ContentCatalog> load() => _catalog ??= _load();

  Future<ContentCatalog> _load() async {
    try {
      final sources = await Future.wait([
        _bundle.loadString(tutorialAsset),
        _bundle.loadString(exampleAsset),
      ]);
      return await compute(_parseCatalog, sources);
    } catch (_) {
      // A failed asset read must not poison a repository for its lifetime.
      _catalog = null;
      rethrow;
    }
  }

  @override
  Future<List<TutorialContent>> tutorials({
    ContentFilter filter = const ContentFilter(),
  }) async => (await load()).tutorials.where(filter.matches).toList();

  @override
  Future<List<ExampleContent>> examples({
    ContentFilter filter = const ContentFilter(),
  }) async => (await load()).examples.where(filter.matches).toList();

  /// Shared ExampleCode intentionally carries editable source only. Resolve a
  /// bundled project by its stable catalog ID before creating a new project.
  Future<RustExampleProject?> projectForExample(String id) async {
    for (final example in (await load()).examples) {
      if (example.id != id) continue;
      final encoded = example.inputFixtures['cargoFiles'];
      if (encoded == null) return null;
      return RustExampleProject.fromJson(jsonDecode(encoded));
    }
    return null;
  }
}

ContentCatalog _parseCatalog(List<String> sources) => ContentCatalog.fromJson(
  tutorialsSource: sources[0],
  examplesSource: sources[1],
);

/// A complete offline Cargo project. Paths are relative to a newly owned root.
class RustExampleProject {
  RustExampleProject._(this.files);

  factory RustExampleProject.fromJson(Object? value) {
    if (value is! Map) {
      throw const FormatException('Cargo project files must be an object');
    }
    final files = <String, String>{};
    final normalized = <String>{};
    final directories = <String, String>{};
    for (final entry in value.entries) {
      final path = entry.key;
      final source = entry.value;
      if (path is! String || source is! String || !_validPath(path)) {
        throw FormatException('Invalid bundled Cargo project path: $path');
      }
      if (!normalized.add(path.toLowerCase())) {
        throw FormatException('Duplicate bundled Cargo project path: $path');
      }
      final segments = path.split('/');
      for (var index = 1; index < segments.length; index++) {
        final directory = segments.take(index).join('/');
        final previous = directories[directory.toLowerCase()];
        if (previous != null && previous != directory) {
          throw FormatException('Conflicting Cargo directory case: $directory');
        }
        directories[directory.toLowerCase()] = directory;
      }
      files[path] = source;
    }
    if (normalized.any(directories.containsKey)) {
      throw const FormatException('A Cargo path is both a file and directory');
    }
    if (!files.containsKey('Cargo.toml') || !files.containsKey('src/main.rs')) {
      throw const FormatException('Cargo.toml and src/main.rs are required');
    }
    return RustExampleProject._(Map.unmodifiable(files));
  }

  final Map<String, String> files;

  /// Custom entries accept canonical explicit target paths only. Unsupported
  /// implicit/aliased declarations fail before a new project is created.
  String manifestForEntry(String entry, String fallbackPackage) {
    final source = files['Cargo.toml']!;
    if (entry == 'src/main.rs') return source;
    final lines = source.split('\n');
    final names = <String>{};
    var package = fallbackPackage;
    var section = '';
    var binHasPath = true;
    var rootBins = 0;
    for (var index = 0; index < lines.length; index++) {
      final line = lines[index];
      final trimmed = line.trim();
      if (trimmed.startsWith('[')) {
        if (!binHasPath) {
          throw const FormatException(
            'Explicit Cargo bins require a path for custom entries',
          );
        }
        section = trimmed.split('#').first.trim();
        binHasPath = section != '[[bin]]';
        continue;
      }
      final name = RegExp(
        r'''^\s*name\s*=\s*(?:"([^"]+)"|'([^']+)')\s*(?:#.*)?$''',
      ).firstMatch(line);
      final value = name?.group(1) ?? name?.group(2);
      if (section == '[package]' && value != null) package = value;
      if (section != '[[bin]]') continue;
      if (value != null) names.add(value);
      if (!RegExp(r'^\s*path\s*=').hasMatch(line)) continue;
      final pathMatch = RegExp(
        r'''^\s*path\s*=\s*(?:"([^"]+)"|'([^']+)')\s*(?:#.*)?$''',
      ).firstMatch(line);
      final path = pathMatch?.group(1) ?? pathMatch?.group(2);
      if (path == null ||
          p.posix.normalize(path) == 'src/main.rs' && path != 'src/main.rs') {
        throw const FormatException(
          'Cargo bin path must use its canonical bundled path',
        );
      }
      binHasPath = true;
      if (path == 'src/main.rs') {
        rootBins++;
        lines[index] = 'path = ${jsonEncode(entry)}';
      }
    }
    if (!binHasPath || rootBins > 1) {
      throw const FormatException(
        'Cargo bin ownership is ambiguous for a custom entry',
      );
    }
    if (rootBins == 1) return lines.join('\n');
    if (names.contains(package)) {
      throw const FormatException(
        'Cargo package bin already owns another source',
      );
    }
    return '$source\n[[bin]]\nname = ${jsonEncode(package)}\npath = ${jsonEncode(entry)}\n';
  }

  static bool _validPath(String path) {
    if (path.isEmpty ||
        path.startsWith('/') ||
        RegExp(r'[\\:\x00-\x1f<>"|?*]').hasMatch(path)) {
      return false;
    }
    return path
        .split('/')
        .every(
          (part) =>
              part.isNotEmpty &&
              !{
                '.',
                '..',
                '.qfli',
                '.git',
                'target',
              }.contains(part.toLowerCase()),
        );
  }
}
