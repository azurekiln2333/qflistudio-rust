import 'dart:io';

import 'package:path/path.dart' as p;

import '../models/project.dart';
import '../models/tutorial.dart';
import '../store/project_store.dart';
import 'app_paths.dart';
import 'file_service.dart';
import 'project_templates.dart';

enum CodeImportFailure { invalidName, fileExists, projectMissing, noStorage }

class CodeImportException implements Exception {
  const CodeImportException(this.failure);
  final CodeImportFailure failure;
}

class ImportedCode {
  const ImportedCode({
    required this.project,
    required this.filePath,
    this.registered = false,
    this.created = false,
  });

  final Project project;
  final String filePath;
  final bool registered;
  final bool created;
}

/// Imports real source files without replacing an existing project's files.
class CodeImportService {
  const CodeImportService({this.storageRoot});

  final String? storageRoot;

  static ProjectTemplate templateFor(String type) =>
      ProjectTemplate.fromType(type == 'html' ? 'web' : type) ??
      ProjectTemplate.empty;

  static String defaultFileName(String type) =>
      p.basename(templateFor(type).mainFile ?? 'main.txt');

  static String normalizeFileName(String raw, String type) {
    final name = raw.trim();
    if (!FileService.isValidEntryName(name) ||
        RegExp(r'[\x00-\x1f]').hasMatch(name) || name.endsWith('.')) {
      throw const CodeImportException(CodeImportFailure.invalidName);
    }
    return p.extension(name).isEmpty
        ? '$name${p.extension(defaultFileName(type))}'
        : name;
  }

  static String projectFilePath(Project project, String type, String fileName) {
    final main = templateFor(type).mainFile ?? 'src/main.txt';
    return p.join(project.path, p.dirname(main), normalizeFileName(fileName, type));
  }

  Future<ImportedCode> openInEditor({
    required ExampleCode example,
    required String fileName,
  }) async {
    final name = normalizeFileName(fileName, example.type);
    final storage = storageRoot ?? await AppPaths.storageDirectory();
    if (storage == null) {
      throw const CodeImportException(CodeImportFailure.noStorage);
    }
    final root = await Directory(p.join(storage, 'code_imports')).create(recursive: true);
    final directory = await root.createTemp('snippet_');
    final file = File(p.join(directory.path, name));
    await file.writeAsString(example.code, flush: true);
    final template = templateFor(example.type);
    return ImportedCode(
      project: Project.create(
        name: name,
        path: directory.path,
        language: template.language,
        type: template.type,
      ),
      filePath: file.path,
    );
  }

  Future<ImportedCode> importProject({
    required ProjectStore store,
    required ExampleCode example,
    required String fileName,
    Project? project,
    String? projectName,
  }) async {
    final name = normalizeFileName(fileName, example.type);
    if (project == null) {
      String? location;
      if (storageRoot != null) {
        location = (await Directory(p.join(storageRoot!, 'projects'))
            .create(recursive: true)).path;
      }
      final result = await store.createProjectFromExample(
        name: projectName ?? example.title,
        example: example,
        fileName: name,
        location: location,
      );
      if (result.error != null || result.project == null) {
        throw FileSystemException(result.error ?? 'Project creation failed');
      }
      return ImportedCode(
        project: result.project!,
        filePath: projectFilePath(result.project!, example.type, name),
        registered: true,
        created: true,
      );
    }

    if (project.isCloud || !await Directory(project.path).exists()) {
      throw const CodeImportException(CodeImportFailure.projectMissing);
    }
    final file = File(projectFilePath(project, example.type, name));
    if (await FileSystemEntity.type(file.path, followLinks: false) !=
        FileSystemEntityType.notFound) {
      throw const CodeImportException(CodeImportFailure.fileExists);
    }
    await file.parent.create(recursive: true);
    try {
      await file.create(exclusive: true);
    } on FileSystemException {
      if (await FileSystemEntity.type(file.path, followLinks: false) !=
          FileSystemEntityType.notFound) {
        throw const CodeImportException(CodeImportFailure.fileExists);
      }
      rethrow;
    }
    await file.writeAsString(example.code, flush: true);
    return ImportedCode(project: project, filePath: file.path, registered: true);
  }
}
