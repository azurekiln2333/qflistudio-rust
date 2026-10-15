import 'dart:convert';
import 'dart:io';

import 'package:path/path.dart' as p;
import 'package:qfli_studio_core/models/tutorial.dart';
import 'package:qfli_studio_core/services/project_templates.dart';
import 'package:qfli_studio_core/store/project_store.dart';

import 'rust_content_repository.dart';

/// Adds Cargo project files to Rust projects created by the shared store.
class RustProjectStore extends ProjectStore {
  RustProjectStore({
    super.storageFile,
    RustContentRepository? contentRepository,
  }) : _contentRepository = contentRepository ?? RustContentRepository();

  final RustContentRepository _contentRepository;

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
    return _addCargoFiles(result);
  }

  @override
  Future<ProjectResult> createProjectFromExample({
    required String name,
    required ExampleCode example,
    String? location,
    String? fileName,
  }) async {
    // Resolve only stable bundled IDs. User-created/imported examples keep the
    // ordinary shared single-source path and do not depend on asset loading.
    final RustExampleProject? bundle;
    final String? bundledManifest;
    try {
      bundle =
          example.type == 'rust' &&
              RegExp(r'^rust-example-\d{3}$').hasMatch(example.id)
          ? await _contentRepository.projectForExample(example.id)
          : null;
      bundledManifest = bundle?.manifestForEntry(
        'src/${fileName ?? 'main.rs'}',
        cargoPackageName(name),
      );
    } on FormatException catch (error) {
      return (error: '示例项目格式错误：${error.message}', project: null);
    }
    if (bundle != null && fileName != null && fileName != 'main.rs') {
      final selectedPath = 'src/$fileName'.toLowerCase();
      if (bundle.files.keys.any((path) => path.toLowerCase() == selectedPath)) {
        return (error: '示例项目中已存在该文件，请选择其他入口文件名', project: null);
      }
    }
    final result = await super.createProjectFromExample(
      name: name,
      example: example,
      location: location,
      fileName: fileName,
    );
    final project = result.project;
    if (project == null || project.type != ProjectTemplate.rust.type) {
      return result;
    }
    final entry = p
        .join(
          p.dirname(ProjectTemplate.rust.mainFile!),
          fileName ?? p.basename(ProjectTemplate.rust.mainFile!),
        )
        .replaceAll('\\', '/');
    return _addCargoFiles(
      result,
      entryFile: entry,
      bundle: bundle,
      bundledManifest: bundledManifest,
    );
  }

  Future<ProjectResult> _addCargoFiles(
    ProjectResult result, {
    String? entryFile,
    RustExampleProject? bundle,
    String? bundledManifest,
  }) async {
    final project = result.project!;

    try {
      if (bundle != null) {
        for (final file in bundle.files.entries) {
          // The shared store has already written the controller's current code
          // to its chosen entry, so the catalog must never overwrite it.
          if (file.key == 'src/main.rs') continue;
          final target = File(p.join(project.path, file.key));
          await target.parent.create(recursive: true);
          await target.create(exclusive: true);
          final source = file.key == 'Cargo.toml'
              ? bundledManifest ?? file.value
              : file.value;
          await target.writeAsString(source, flush: true);
        }
      }
      final manifest = File(p.join(project.path, 'Cargo.toml'));
      if (!await manifest.exists()) {
        final package = cargoPackageName(project.name);
        final binary = entryFile == null || entryFile == 'src/main.rs'
            ? ''
            : '\n[[bin]]\nname = "$package"\npath = ${jsonEncode(entryFile)}\n';
        await manifest.writeAsString('''[package]
name = "$package"
version = "0.1.0"
edition = "2021"
$binary''', flush: true);
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
      // Only the fresh directory returned by our own create call enters here.
      // Existing-project import and addExisting never use this rollback path.
      try {
        await Directory(project.path).delete(recursive: true);
        await super.deleteProject(project);
      } on FileSystemException {
        return (
          error: 'Cargo 项目文件写入失败且清理失败：${error.message}',
          project: project,
        );
      }
      return (error: 'Cargo 项目文件写入失败：${error.message}', project: null);
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
  var base = slug.isEmpty
      ? 'rust'
      : RegExp(r'^[a-z]').hasMatch(slug)
      ? slug
      : 'rust_$slug';
  // Cargo accepts these package names, but their implicit binary targets cannot
  // be copied to target/debug/<name>.exe on Windows. Display names stay intact.
  if (RegExp(r'^(con|prn|aux|nul|com[1-9]|lpt[1-9])$').hasMatch(base)) {
    base = 'rust_$base';
  }
  if (slug.isNotEmpty && !RegExp(r'[^\x00-\x7F]').hasMatch(displayName)) {
    return base;
  }

  var hash = 0x811c9dc5;
  for (final byte in utf8.encode(displayName)) {
    hash = ((hash ^ byte) * 0x01000193) & 0xffffffff;
  }
  return '${base}_${hash.toRadixString(16).padLeft(8, '0')}';
}
