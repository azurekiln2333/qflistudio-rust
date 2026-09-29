import 'dart:convert';
import 'dart:io';

import 'package:path/path.dart' as p;
import 'package:qfli_studio_core/services/project_templates.dart';
import 'package:qfli_studio_core/store/project_store.dart';

/// Adds Cargo project files to Rust projects created by the shared store.
class RustProjectStore extends ProjectStore {
  RustProjectStore({super.storageFile});

  @override
  Future<ProjectResult> createProject({
    required String name,
    required String location,
    ProjectTemplate template = ProjectTemplate.empty,
  }) async {
    final result = await super.createProject(
      name: name,
      location: location,
      template: template,
    );
    final project = result.project;
    if (project == null || template != ProjectTemplate.rust) return result;

    try {
      final manifest = File(p.join(project.path, 'Cargo.toml'));
      if (!await manifest.exists()) {
        final package = cargoPackageName(project.name);
        await manifest.writeAsString('''[package]
name = "$package"
version = "0.1.0"
edition = "2021"
''', flush: true);
      }

      final ignore = File(p.join(project.path, '.gitignore'));
      final existing = await ignore.exists() ? await ignore.readAsString() : '';
      if (!RegExp(r'^/?target/?$', multiLine: true).hasMatch(existing)) {
        final separator = existing.isEmpty || existing.endsWith('\n')
            ? ''
            : '\n';
        await ignore.writeAsString(
          '$existing$separator/target/\n',
          flush: true,
        );
      }
    } on FileSystemException catch (error) {
      return (error: 'Cargo 项目文件写入失败：${error.message}', project: project);
    }
    return result;
  }
}

/// Cargo package names are ASCII identifiers even when display names are not.
String cargoPackageName(String displayName) {
  final slug = displayName
      .toLowerCase()
      .replaceAll(RegExp(r'[^a-z0-9]+'), '_')
      .replaceAll(RegExp(r'^_+|_+$'), '');
  final base = slug.isEmpty
      ? 'rust'
      : RegExp(r'^[a-z]').hasMatch(slug)
      ? slug
      : 'rust_$slug';
  if (slug.isNotEmpty && !RegExp(r'[^\x00-\x7F]').hasMatch(displayName)) {
    return base;
  }

  var hash = 0x811c9dc5;
  for (final byte in utf8.encode(displayName)) {
    hash = ((hash ^ byte) * 0x01000193) & 0xffffffff;
  }
  return '${base}_${hash.toRadixString(16).padLeft(8, '0')}';
}
