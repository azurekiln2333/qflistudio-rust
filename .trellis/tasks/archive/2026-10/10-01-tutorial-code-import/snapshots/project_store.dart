import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:path/path.dart' as p;

import '../models/project.dart';
import '../models/tutorial.dart';
import '../services/app_paths.dart';
import '../services/file_service.dart';
import '../services/project_config.dart';
import '../services/project_templates.dart';
import '../services/recycle_bin.dart';

/// 创建/添加项目的结果：成功时 [error] 为 null。
typedef ProjectResult = ({String? error, Project? project});

({List<Project> projects, String? browsedId}) _readProjectRegistry(
  String path,
) {
  final file = File(path);
  if (!file.existsSync()) return (projects: <Project>[], browsedId: null);
  final data = jsonDecode(file.readAsStringSync());
  if (data is! Map || data['projects'] is! List) {
    throw const FormatException('项目列表格式不正确');
  }
  final projects = <Project>[];
  final ids = <String>{};
  for (final item in data['projects'] as List) {
    if (item is! Map) continue;
    try {
      final project = Project.fromJson(Map<String, dynamic>.from(item));
      if (!ids.add(project.id)) continue;
      if (!project.isCloud) {
        final metadata = ProjectConfig.readMetadata(project.path);
        project.name = metadata.name ?? project.name;
        project.language = metadata.language ?? project.language;
        project.type = metadata.type ?? project.type;
      }
      projects.add(project);
    } catch (_) {
      // 单条损坏不影响其他项目。
    }
  }
  return (
    projects: projects,
    browsedId: data['lastBrowsedProjectId'] as String?,
  );
}

/// 项目注册表管理身份、路径和列表状态；名称与语言优先读取项目配置。
class ProjectStore extends ChangeNotifier {
  ProjectStore({File? storageFile}) : _storageOverride = storageFile;

  final File? _storageOverride;
  final List<Project> _projects = [];
  File? _storage;
  bool _loaded = false;
  Future<void>? _writes;
  int _revision = 0;

  /// 文件树上一次浏览的项目（跨编辑器会话记忆）。
  String? lastBrowsedProjectId;

  bool get loaded => _loaded;

  /// 按最近打开时间倒序。
  List<Project> get projects {
    final list = [..._projects];
    list.sort((a, b) => b.lastOpenedAt.compareTo(a.lastOpenedAt));
    return list;
  }

  Future<void> load() async {
    try {
      await _reload();
    } catch (_) {
      // 配置文件损坏时保持空列表，避免应用无法启动。
    }
    _loaded = true;
    notifyListeners();
  }

  /// 重新读取注册表与项目元数据。重复刷新不追加记录，也不清理本地目录。
  Future<void> refresh() async {
    await _reload();
    notifyListeners();
  }

  Future<void> _reload() async {
    _storage ??= _storageOverride ?? await _resolveStorageFile();
    final pendingWrite = _writes;
    if (pendingWrite != null) await pendingWrite;
    final revision = _revision;
    final result = await compute(_readProjectRegistry, _storage!.path);
    // 读取期间发生了创建、收藏等操作时保留较新的内存状态。
    if (revision != _revision) return;
    _projects
      ..clear()
      ..addAll(result.projects);
    lastBrowsedProjectId = result.browsedId;
  }

  Future<File> _resolveStorageFile() async {
    final base = await AppPaths.storageDirectory();
    if (base == null) {
      throw const FileSystemException('未找到可写的存储目录');
    }
    return File(p.join(base, 'projects.json'));
  }

  Future<void> _persist() {
    _revision++;
    final file = _storage;
    if (file == null) return Future.value();
    final data = {
      'version': 1,
      'projects': _projects.map((e) => e.toJson()).toList(),
      if (lastBrowsedProjectId != null)
        'lastBrowsedProjectId': lastBrowsedProjectId,
    };
    final encoded = const JsonEncoder.withIndent('  ').convert(data);
    // 顺序落盘，避免收藏、最近打开与下拉刷新相互覆盖。
    Future<void> write() async {
      await file.parent.create(recursive: true);
      await file.writeAsString(encoded);
    }

    final previous = _writes;
    return _writes = previous == null
        ? write()
        : previous.catchError((Object _) {}).then((_) => write());
  }

  /// 在 [location] 下按语言创建项目目录；显示名称独立保存在项目配置中。
  /// [template] 决定写入哪些初始 demo 文件。
  Future<ProjectResult> createProject({
    required String name,
    required String location,
    ProjectTemplate template = ProjectTemplate.empty,
  }) async {
    return _createProject(
      name: name,
      location: location,
      template: template,
      cloudId: null,
    );
  }

  /// Creates a real registered project and places an example in its entry file.
  Future<ProjectResult> createProjectFromExample({
    required String name,
    required ExampleCode example,
    String? location,
  }) async {
    final root = location ?? await AppPaths.projectsRoot(create: true);
    if (root == null) {
      return (error: '未找到可写的项目目录', project: null);
    }
    final template =
        ProjectTemplate.fromType(example.type) ??
        ProjectTemplate.fromType(
          example.type == 'html' ? 'web' : example.type,
        ) ??
        ProjectTemplate.empty;
    final result = await createProject(
      name: name,
      location: root,
      template: template,
    );
    final project = result.project;
    final mainFile = template.mainFile;
    if (project == null || mainFile == null) return result;
    try {
      await File(p.join(project.path, mainFile)).writeAsString(example.code);
    } on FileSystemException catch (error) {
      return (error: '写入示例代码失败：${error.message}', project: project);
    }
    return result;
  }

  Future<ProjectResult> _createProject({
    required String name,
    required String location,
    required ProjectTemplate template,
    required String? cloudId,
  }) async {
    final trimmed = name.trim();
    if (trimmed.isEmpty) return (error: '请输入项目名称', project: null);
    if (!FileService.isValidEntryName(trimmed) || trimmed.contains('\u0000')) {
      return (error: '项目名称不能包含 \\ / : * ? " < > | 等字符', project: null);
    }
    final locationPath = location.trim();
    final dir = Directory(locationPath);
    if (locationPath.isEmpty || !dir.existsSync()) {
      return (error: '位置目录不存在：$locationPath', project: null);
    }
    late final String fullPath;
    try {
      fullPath = AppPaths.createProjectDirectory(
        location: dir.path,
        name: trimmed,
        type: template.type,
        language: template.language,
      ).path;
      await Directory(p.join(fullPath, 'src')).create(recursive: true);
      for (final file in template.files) {
        await File(
          p.join(fullPath, file.path),
        ).writeAsString(file.content, flush: true);
      }
      await ProjectConfig.write(
        projectRoot: fullPath,
        name: trimmed,
        language: template.language,
        type: template.type,
        strict: true,
      );
    } on FileSystemException catch (e) {
      return (error: '创建项目失败：${e.message}', project: null);
    }
    final project = Project.create(
      name: trimmed,
      path: fullPath,
      cloudId: cloudId,
      language: template.language,
      type: template.type,
    );
    _projects.add(project);
    await _persist();
    notifyListeners();
    return (error: null, project: project);
  }

  /// 注册一个磁盘上已存在的文件夹。
  Future<ProjectResult> addExisting(String rawPath) async {
    final path = rawPath.trim().replaceAll('"', '');
    if (path.isEmpty) return (error: '请输入项目路径', project: null);
    final dir = Directory(path);
    if (!dir.existsSync()) return (error: '目录不存在：$path', project: null);
    final normalized = p.normalize(dir.absolute.path);
    if (_projects.any(
      (e) => p.canonicalize(e.path) == p.canonicalize(normalized),
    )) {
      return (error: '该项目已在列表中', project: null);
    }
    final metadata = ProjectConfig.readMetadata(normalized);
    var name = metadata.name ?? p.basename(normalized);
    if (name.isEmpty) name = normalized; // 盘符根目录
    // 语言优先取项目配置文件（.qfli/project.json），没有才做扩展名检测。
    final configLanguage = metadata.language ?? '';
    final language = configLanguage.isNotEmpty
        ? configLanguage
        : detectLanguage(normalized);
    final configType =
        metadata.type ?? ProjectTemplate.fromLanguage(language)?.type ?? '';
    await ProjectConfig.write(
      projectRoot: normalized,
      name: name,
      language: language,
      type: configType,
    );
    final project = Project.create(
      name: name,
      path: normalized,
      language: language,
      type: configType,
    );
    _projects.add(project);
    await _persist();
    notifyListeners();
    return (error: null, project: project);
  }

  /// 注册一个云端项目（本地镜像目录 + 服务器 cloudId）。
  Future<ProjectResult> addCloudProject({
    required String name,
    required String cloudId,
    required String cachePath,
    String language = '',
  }) async {
    if (_projects.any((e) => e.cloudId == cloudId)) {
      return (error: '该云端项目已在列表中', project: null);
    }
    final project = Project.create(
      name: name,
      path: cachePath,
      cloudId: cloudId,
      language: language,
    );
    _projects.add(project);
    await _persist();
    notifyListeners();
    return (error: null, project: project);
  }

  /// 合并云端目录信息；保留本地收藏、最近打开时间和未同步文件。
  Future<void> remapCloudId(String oldId, String newId) async {
    for (final project in _projects) {
      if (project.cloudId == oldId) project.cloudId = newId;
    }
    await _persist();
    notifyListeners();
  }

  Future<void> mergeCloudProjects(Iterable<Project> projects) async {
    for (final project in projects) {
      if (!project.isCloud) continue;
      final existing = _projects.where(
        (item) => item.cloudId == project.cloudId,
      );
      if (existing.isEmpty) {
        _projects.add(project);
      } else {
        existing.first.name = project.name;
      }
    }
    await _persist();
    notifyListeners();
  }

  /// 仅从列表移除，不删除磁盘文件（适用于目录已失效的项目）。
  void remove(Project project) {
    _projects.removeWhere((e) => e.id == project.id);
    unawaited(_persist());
    notifyListeners();
  }

  /// 删除项目：先压缩整个文件夹备份到回收站 projects_bin，再从磁盘删除
  /// 并移出列表。返回错误信息，null 表示成功。
  Future<String?> deleteProject(Project project) async {
    if (project.isCloud) return '云端项目请在云端管理中删除';
    final dir = Directory(project.path);
    if (dir.existsSync()) {
      final backupError = await RecycleBin.backupProject(
        dir,
        projectName: project.name,
      );
      if (backupError != null) return backupError;
      try {
        await dir.delete(recursive: true);
      } on FileSystemException catch (e) {
        return '删除项目文件夹失败：${e.message}';
      }
    }
    _projects.removeWhere((e) => e.id == project.id);
    await _persist();
    notifyListeners();
    return null;
  }

  /// 按 ID 查找项目。
  Project? projectById(String? id) {
    if (id == null) return null;
    for (final p in _projects) {
      if (p.id == id) return p;
    }
    return null;
  }

  /// 记录文件树当前浏览的项目（持久化）。
  void setBrowsedProject(Project project) {
    if (lastBrowsedProjectId == project.id) return;
    lastBrowsedProjectId = project.id;
    unawaited(_persist());
  }

  /// 切换收藏状态。
  Future<void> setFavorite(Project project, bool value) async {
    project.favorite = value;
    await _persist();
    notifyListeners();
  }

  /// 目录语言检测：按扩展名统计，取出现最多的一类。
  static String detectLanguage(String dirPath) {
    const extToLang = {
      '.py': 'Python',
      '.java': 'Java',
      '.c': 'C',
      '.h': 'C',
      '.cpp': 'C++',
      '.hpp': 'C++',
      '.cc': 'C++',
      '.html': 'Web',
      '.htm': 'Web',
      '.dart': 'Dart',
      '.lua': 'Lua',
      '.js': 'JavaScript',
      '.mjs': 'JavaScript',
      '.ts': 'TypeScript',
      '.tsx': 'TypeScript',
      '.kt': 'Kotlin',
      '.go': 'Go',
      '.rs': 'Rust',
      '.cs': 'C#',
      '.php': 'PHP',
      '.rb': 'Ruby',
    };
    final counts = <String, int>{};
    void scan(Directory dir) {
      for (final e in dir.listSync(followLinks: false)) {
        if (e is Directory) {
          if (p.basename(e.path) == 'src') scan(e);
        } else {
          final lang = extToLang[p.extension(e.path).toLowerCase()];
          if (lang != null) counts[lang] = (counts[lang] ?? 0) + 1;
        }
      }
    }

    try {
      scan(Directory(dirPath));
    } on FileSystemException {
      return '';
    }
    String? best;
    var bestCount = 0;
    counts.forEach((lang, n) {
      if (n > bestCount) {
        best = lang;
        bestCount = n;
      }
    });
    return best ?? '';
  }

  /// 更新最近打开时间并持久化。
  void touch(Project project) {
    project.lastOpenedAt = DateTime.now();
    unawaited(_persist());
    notifyListeners();
  }
}
