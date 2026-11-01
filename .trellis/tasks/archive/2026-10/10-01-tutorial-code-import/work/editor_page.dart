import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:path/path.dart' as p;
import 'package:re_editor/re_editor.dart';

import '../models/project.dart';
import '../pages/git_page.dart';
import '../store/auth_store.dart';
import '../store/project_store.dart';
import '../store/settings_store.dart';
import '../community/community_widgets.dart';
import 'editor_delete_fix.dart';
import 'editor_selection_toolbar.dart';
import '../services/cloud_sync_service.dart';
import '../services/file_encoding.dart';
import '../services/code_formatter.dart';
import '../services/local_web_server.dart';
import '../services/runner_service.dart';
import '../services/online_program.dart';
import '../services/share_service.dart';
import '../services/studio_profile.dart';
import '../services/task_activity_service.dart';
import '../widgets/retained_page.dart';
import 'editor_fonts.dart';
import 'code_minimap.dart';
import 'symbols_bar.dart';
import 'editor_controller.dart';
import 'editor_find_panel.dart';
import 'file_explorer.dart';
import 'highlight_themes.dart';
import 'open_file.dart';
import 'project_history.dart';
import 'terminal_pane.dart';
import '../pages/settings_page.dart';
import '../pages/content_tools_pages.dart';
import 'ai_panel.dart';

enum _BottomPanel { none, terminal, ai }

class SaveIntent extends Intent {
  const SaveIntent();
}

class FindIntent extends Intent {
  const FindIntent();
}

class GotoLineIntent extends Intent {
  const GotoLineIntent();
}

class FormatIntent extends Intent {
  const FormatIntent();
}

/// 编辑器页：左侧文件树卡片 + 可选文件标签栏 + re_editor 代码编辑区
/// + minimap 鸟瞰 + 本地终端面板 + 运行。
class EditorPage extends StatefulWidget {
  const EditorPage({
    super.key,
    required this.project,
    required this.auth,
    required this.store,
    required this.settings,
    this.initialOpenPath,
  });

  final Project project;
  final AuthStore auth;
  final ProjectStore store;
  final SettingsStore settings;

  /// 进入编辑器后自动打开的文件（新建项目模板的主文件）。
  final String? initialOpenPath;

  @override
  State<EditorPage> createState() => _EditorPageState();
}

class _EditorPageState extends State<EditorPage> with TickerProviderStateMixin {
  static const double _sidebarWidth = 280;
  static const double _cardMargin = 12;
  static const double _wideBreakpoint = 720;

  late final EditorController _editor;
  final GlobalKey<ScaffoldState> _scaffoldKey = GlobalKey<ScaffoldState>();
  final GlobalKey<TerminalPaneState> _terminalKey =
      GlobalKey<TerminalPaneState>();

  TabController? _tabController;

  bool? _explorerVisible;
  bool _terminalCollapsed = false;
  bool _runningFileTool = false;
  bool _terminalCreated = false;
  bool _runningProject = false;
  double _terminalHeight = 240;
  bool _aiCollapsed = false;
  _BottomPanel _bottomPanel = _BottomPanel.none;
  bool get _terminalVisible => _bottomPanel == _BottomPanel.terminal;
  WebPreviewSession? _previewServer;
  StreamSubscription<String>? _debugSub;
  Timer? _historyTimer;
  final Map<String, Timer> _activityTimers = {};
  final Map<String, int> _manualSaveGeneration = {};
  final Map<String, int> _autoEditGeneration = {};
  bool _leaving = false;

  // 双指缩放字号 + 滚动收键盘（raw pointer，不与编辑器手势竞争）。
  late double _fontSize;
  late double _savedFontSize;
  final Map<OpenFile, Widget> _codeViews = {};
  final Map<int, Offset> _activePointers = {};
  double? _pinchStartDistance;
  double? _pinchStartFontSize;

  /// 长按空行时强制显示选择工具栏（仅粘贴），点击关闭后复位。
  bool _pasteToolbarVisible = false;
  Timer? _longPressTimer;

  // 云端同步（仅云端项目）。
  CloudSyncService? _cloud;
  StreamSubscription<SyncState>? _cloudSub;
  SyncState _syncState = SyncState.idle;
  String? _syncError;

  @override
  void initState() {
    super.initState();
    _fontSize = _savedFontSize = widget.settings.editorFontSize;
    _editor = EditorController(
      project: widget.project,
      onContentChanged: _onFileContentChanged,
    );
    _editor.addListener(_syncTabController);
    _editor.addListener(_onEditorChanged);
    widget.settings.addListener(_onSettingsChanged);
    if (widget.project.isCloud && StudioProfile.current?.isOffline != true) {
      CloudSyncService.open(
        cloudId: widget.project.cloudId!,
        cachePath: widget.project.path,
        name: widget.project.name,
      ).then((service) {
        if (!mounted) return;
        setState(() => _cloud = service);
        _cloudSub = service.stateStream.listen((state) {
          if (mounted) setState(() => _syncState = state);
        });
        _pullInitial();
      });
    }
    // 会话恢复：优先恢复上次打开的文件与光标；无历史时打开模板主文件。
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _restoreSession();
    });
  }

  Future<void> _restoreSession() async {
    final session = await ProjectHistory.load(widget.project.path);
    final opened = <String>[];
    for (final rel in session.openFiles) {
      final abs = p.isAbsolute(rel) ? rel : p.join(widget.project.path, rel);
      if (!File(abs).existsSync()) continue;
      final error = await _editor.openPath(abs, cursor: session.cursors[rel]);
      if (error == null) opened.add(rel);
    }
    // Explicit navigation (including a code import) selects its file first.
    final initialPath = widget.initialOpenPath;
    if (initialPath != null) {
      await _openInitialFile(initialPath);
      return;
    }
    if (opened.isNotEmpty) {
      final activeRel = session.activeFile;
      if (activeRel != null) {
        final idx = _editor.files.indexWhere((f) {
          final rel = p.isWithin(widget.project.path, f.path)
              ? p
                    .relative(f.path, from: widget.project.path)
                    .replaceAll('\\', '/')
              : null;
          return rel == activeRel;
        });
        if (idx >= 0) {
          _editor.select(idx);
          return;
        }
      }
      return;
    }
  }

  /// 保存会话（光标 + 打开列表）到项目内 history.json。
  Future<void> _saveHistory() async {
    final cursors = <String, FileCursor>{};
    final openFiles = <String>[];
    String? activeRel;
    for (final f in _editor.files) {
      if (f.readOnly) continue;
      if (!p.isWithin(widget.project.path, f.path)) continue;
      final rel = p
          .relative(f.path, from: widget.project.path)
          .replaceAll('\\', '/');
      openFiles.add(rel);
      final sel = f.controller.selection;
      cursors[rel] = FileCursor(
        baseIndex: sel.baseIndex,
        baseOffset: sel.baseOffset,
        extentIndex: sel.extentIndex,
        extentOffset: sel.extentOffset,
      );
      if (identical(f, _editor.current)) activeRel = rel;
    }
    await ProjectHistory.save(
      widget.project.path,
      cursors: cursors,
      openFiles: openFiles,
      activeFile: activeRel,
    );
  }

  @override
  void dispose() {
    _leaving = true;
    for (final timer in _activityTimers.values) {
      timer.cancel();
      TaskActivityService.report(widget.auth, 'save_file');
    }
    _activityTimers.clear();
    _saveHistory(); // 离开编辑器时保存现场（异步落盘）
    widget.settings.removeListener(_onSettingsChanged);
    _editor.removeListener(_syncTabController);
    _editor.removeListener(_onEditorChanged);
    _longPressTimer?.cancel();
    _historyTimer?.cancel();
    _cloudSub?.cancel();
    _debugSub?.cancel();
    _cloud?.dispose();
    _tabController?.dispose();
    _editor.dispose();
    _previewServer?.stop();
    super.dispose();
  }

  Future<void> _pullInitial() async {
    final token = widget.auth.token;
    if (token == null) {
      setState(() => _syncError = '云端项目需要登录（我的页）');
      return;
    }
    final cacheEmpty = !_cloud!.existsAnyFile();
    final result = await _cloud!.pullAll(
      token: token,
      onlyIfMissing: !cacheEmpty,
    );
    if (!mounted) return;
    if (result.error != null) {
      setState(() => _syncError = result.error);
    } else if (result.pulled > 0) {
      setState(() => _syncError = null);
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('已从云端拉取 ${result.pulled} 个文件')));
    }
  }

  void _onSettingsChanged() {
    if (!mounted) return;
    setState(() {
      if (_savedFontSize != widget.settings.editorFontSize) {
        _fontSize = _savedFontSize = widget.settings.editorFontSize;
      }
      _codeViews.clear();
    });
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _codeViews.clear();
  }

  void _onEditorChanged() {
    if (_editor.current?.readOnly == true) return; // 历史快照只读
    _scheduleHistorySave();
  }

  void _scheduleHistorySave() {
    _historyTimer?.cancel();
    _historyTimer = Timer(const Duration(milliseconds: 1500), () {
      unawaited(_saveHistory());
    });
  }

  void _onFileContentChanged(OpenFile open) {
    _scheduleHistorySave();
    if (!widget.settings.autoSave && !widget.project.isCloud) return;
    _activityTimers.remove(open.path)?.cancel();
    final editGeneration = (_autoEditGeneration[open.path] ?? 0) + 1;
    _autoEditGeneration[open.path] = editGeneration;
    final bytes = TextCodec.byName(open.encoding).encode(open.controller.text);
    final save = _editor.saveFile(
      open,
      backup: widget.settings.backupEnabled,
      bytes: bytes,
    );
    unawaited(_finishAutoSave(open.path, bytes, save, widget.auth.token,
        _manualSaveGeneration[open.path] ?? 0, editGeneration));
  }

  Future<void> _finishAutoSave(
    String path,
    List<int> bytes,
    Future<String?> save,
    String? token,
    int manualGeneration,
    int editGeneration,
  ) async {
    final error = await save;
    if (error != null) {
      if (mounted) _showSnack('自动保存失败：$error');
      return;
    }
    if ((_manualSaveGeneration[path] ?? 0) == manualGeneration &&
        _autoEditGeneration[path] == editGeneration) {
      if (_leaving) {
        TaskActivityService.report(widget.auth, 'save_file');
      } else {
        _activityTimers.remove(path)?.cancel();
        _activityTimers[path] = Timer(const Duration(seconds: 2), () {
          _activityTimers.remove(path);
          TaskActivityService.report(widget.auth, 'save_file');
        });
      }
    }
    final cloud = _cloud;
    if (cloud == null || token == null || widget.auth.token != token) return;
    final syncError = await cloud.pushBytes(token, path, bytes);
    if (mounted && _syncError != syncError) {
      setState(() => _syncError = syncError);
    }
  }

  Future<void> _pullFromCloud() async {
    final token = widget.auth.token;
    if (token == null || _cloud == null) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('从云端拉取？'),
        content: const Text('服务器文件将覆盖本地镜像中已存在的同名文件（未同步的本地修改会丢失）。'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('拉取'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    final result = await _cloud!.pullAll(token: token);
    if (!mounted) return;
    if (result.error != null) {
      setState(() => _syncError = result.error);
    } else {
      setState(() => _syncError = null);
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('已更新 ${result.pulled} 个文件')));
    }
  }

  void _openGit() {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => GitPage(project: widget.project, auth: widget.auth),
      ),
    );
  }

  /// 顶栏副标题：当前打开文件的路径（过长时省略中段）。
  String _currentFileSubtitle() {
    final open = _editor.current;
    if (open == null) return '未打开文件';
    final relative = p.isWithin(widget.project.path, open.path)
        ? p.relative(open.path, from: widget.project.path)
        : open.path;
    if (relative.length <= 36) return relative;
    return '…${p.separator}${p.basename(open.path)}';
  }

  void _undoCurrent() {
    final open = _editor.current;
    if (open == null) return;
    open.controller.undo();
  }

  // ---- 双指缩放字号 + 滚动收键盘（raw pointer 监听，不参与手势竞技场）----

  void _handlePointerDown(PointerDownEvent event) {
    // 触摸编辑器区域时收起已显示的粘贴工具栏。
    if (_pasteToolbarVisible) {
      setState(() => _pasteToolbarVisible = false);
    }
    _activePointers[event.pointer] = event.position;
    if (_activePointers.length == 2) {
      _longPressTimer?.cancel();
      _longPressTimer = null;
      final points = _activePointers.values.toList();
      _pinchStartDistance = (points[0] - points[1]).distance;
      _pinchStartFontSize = _fontSize;
    } else if (_activePointers.length == 1) {
      // 单指按下：启动长按计时器，500ms 后弹出粘贴工具栏。
      _longPressTimer?.cancel();
      _longPressTimer = Timer(const Duration(milliseconds: 500), () {
        if (mounted && !_pasteToolbarVisible) {
          setState(() => _pasteToolbarVisible = true);
        }
      });
    }
  }

  void _handlePointerMove(PointerMoveEvent event) {
    final start = _activePointers[event.pointer];
    if (_activePointers.containsKey(event.pointer)) {
      _activePointers[event.pointer] = event.position;
    }
    // 手指移动超过阈值：取消长按计时器。
    if (_longPressTimer != null && start != null) {
      if ((start - event.position).distance > 14) {
        _longPressTimer!.cancel();
        _longPressTimer = null;
      }
    }
    if (_activePointers.length >= 2 && _pinchStartDistance != null) {
      final points = _activePointers.values.toList();
      final distance = (points[0] - points[1]).distance;
      if (_pinchStartDistance! > 0) {
        setState(() {
          _fontSize = (_pinchStartFontSize! * distance / _pinchStartDistance!)
              .clamp(EditorFonts.minSize, EditorFonts.maxSize);
          _codeViews.clear();
        });
      }
      return;
    }
  }

  void _handlePointerUp(PointerEvent event) {
    _longPressTimer?.cancel();
    _longPressTimer = null;
    _activePointers.remove(event.pointer);
    if (_activePointers.length < 2) {
      if (_pinchStartFontSize != null) {
        unawaited(widget.settings.setEditorFont(size: _fontSize));
      }
      _pinchStartDistance = null;
      _pinchStartFontSize = null;
    }
  }

  Future<void> _openInitialFile(String path) async {
    // 模板主文件是相对路径（如 src/main.py），必须拼到项目根下。
    final abs = p.isAbsolute(path) ? path : p.join(widget.project.path, path);
    final error = await _editor.openPath(abs);
    if (error != null && mounted) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(error)));
    }
  }

  /// 标签页数量变化时同步 TabController。
  void _syncTabController() {
    if (!mounted) return;
    final count = _editor.files.length;
    _codeViews.removeWhere((file, _) => !_editor.files.contains(file));
    final old = _tabController;
    if (old != null && old.length == count) {
      if (old.index != _editor.currentIndex &&
          _editor.currentIndex >= 0 &&
          count > 0) {
        old.index = _editor.currentIndex;
      }
      return;
    }
    final initial = _editor.currentIndex.clamp(0, count > 0 ? count - 1 : 0);
    old?.dispose();
    if (count == 0) {
      _tabController = null;
    } else {
      _tabController = TabController(
        length: count,
        vsync: this,
        initialIndex: initial,
      );
      _tabController!.addListener(() {
        if (!_tabController!.indexIsChanging &&
            _tabController!.index != _editor.currentIndex) {
          _editor.select(_tabController!.index);
        }
      });
    }
    unawaited(_saveHistory()); // 打开/关闭标签后保存会话
    setState(() {});
  }

  void _toggleExplorer() {
    final wide = MediaQuery.sizeOf(context).width >= _wideBreakpoint;
    if (wide) {
      // 侧栏默认隐藏，第一次点击为展开。
      setState(() => _explorerVisible = !(_explorerVisible ?? false));
    } else {
      _scaffoldKey.currentState?.openDrawer();
    }
  }

  void _closeDrawer() {
    _scaffoldKey.currentState?.closeDrawer();
  }

  // ---- 编辑动作 ----

  Future<void> _saveCurrent() async {
    final open = _editor.current;
    if (open == null || open.readOnly) return;
    final wasDirty = open.dirty;
    final token = widget.auth.token;
    final bytes = TextCodec.byName(open.encoding).encode(open.controller.text);
    final error = await _editor.saveFile(open, bytes: bytes);
    if (error != null) {
      if (mounted) _showSnack(error);
      return;
    }
    if (wasDirty) {
      _manualSaveGeneration[open.path] =
          (_manualSaveGeneration[open.path] ?? 0) + 1;
      _activityTimers.remove(open.path)?.cancel();
      TaskActivityService.report(widget.auth, 'save_file');
    }
    if (_cloud != null && token != null && widget.auth.token == token) {
      final syncError = await _cloud!.pushBytes(token, open.path, bytes);
      if (mounted) setState(() => _syncError = syncError);
    }
  }

  void _openFind() {
    final open = _editor.current;
    if (open == null) return;
    open.findController.findMode();
  }

  void _showGotoLineDialog() {
    final open = _editor.current;
    if (open == null) return;
    final controller = TextEditingController();
    showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('跳转到行'),
        content: TextField(
          controller: controller,
          autofocus: true,
          keyboardType: TextInputType.number,
          inputFormatters: [FilteringTextInputFormatter.digitsOnly],
          decoration: InputDecoration(
            labelText: '行号（1 - ${open.controller.codeLines.length}）',
            prefixIcon: const Icon(Icons.pin),
          ),
          onSubmitted: (_) => Navigator.of(context).pop(),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('跳转'),
          ),
        ],
      ),
    ).then((_) {
      final value = int.tryParse(controller.text);
      if (value == null || value < 1) return;
      final index = (value - 1).clamp(0, open.controller.codeLines.length - 1);
      open.controller.selection = CodeLineSelection.collapsed(
        index: index,
        offset: 0,
      );
      open.scrollController.makeVisible(
        CodeLinePosition(index: index, offset: 0),
      );
    });
  }

  void _formatCurrent() {
    final open = _editor.current;
    if (open == null) return;
    final result = CodeFormatter.format(open.name, open.controller.text);
    if (result.changed) {
      open.controller.text = result.text;
    }
  }

  Future<void> _runEditorTool(String id) async {
    final open = _editor.current;
    final tool = StudioProfile.current?.editorFileTools
        .where((tool) => tool.id == id)
        .firstOrNull;
    if (_runningFileTool || open == null || open.readOnly || tool == null) return;
    if (!tool.extensions.contains(p.extension(open.path).toLowerCase())) return;
    setState(() => _runningFileTool = true);
    try {
      await _saveCurrent();
      if (!mounted || !_editor.files.contains(open) || open.dirty) return;
      final EditorFileToolResult result;
      try {
        result = await tool.run(open.path, open.projectRootPath);
      } catch (error) {
        if (mounted) _showSnack('${tool.label}失败：$error');
        return;
      }
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        builder: (context) => AlertDialog(
          title: Text('${tool.label}${result.success ? '完成' : '失败'}'),
          content: SingleChildScrollView(child: SelectableText(result.message)),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('关闭'),
            ),
          ],
        ),
      );
    } finally {
      if (mounted) setState(() => _runningFileTool = false);
    }
  }

  void _openContentTool() {
    final open = _editor.current;
    if (open == null) return;
    final extension = p.extension(open.name).toLowerCase();
    if (extension != '.json' &&
        extension != '.md' &&
        extension != '.markdown') {
      return;
    }
    final page = extension == '.json'
        ? JsonToolPage(
            initialText: open.controller.text,
            onApply: (value) => setState(() => open.controller.text = value),
          )
        : MarkdownToolPage(
            initialText: open.controller.text,
            onApply: (value) => setState(() => open.controller.text = value),
          );
    Navigator.of(context).push(MaterialPageRoute(builder: (_) => page));
  }

  Future<void> _runProject() async {
    if (_runningProject) return;
    setState(() {
      _runningProject = true;
      _terminalCreated = true;
      _terminalCollapsed = false;
      _bottomPanel = _BottomPanel.terminal;
    });
    await WidgetsBinding.instance.endOfFrame;
    if (!mounted) return;
    final pane = _terminalKey.currentState;
    if (pane == null) {
      setState(() => _runningProject = false);
      return;
    }
    pane.expand();
    var preparing = false;
    try {
      if (pane.busy) return;
      pane.beginPreparation('保存文件并初始化运行环境...');
      preparing = true;
      for (final open in List<OpenFile>.of(_editor.files)) {
        final error = await _editor.saveFile(open);
        if (!mounted || !pane.mounted) return;
        if (error != null) {
          pane.appendSystem(error);
          return;
        }
      }
      final entry = RunnerService.findEntry(widget.project.path);
      if (entry == null) {
        final hint = StudioProfile.current?.entryFileNames;
        pane.appendSystem(
          hint == null || hint.isEmpty
              ? '未找到可运行的入口文件（index.html / main.py / Main.java 等）'
              : '未找到可运行的入口文件（${hint.join(' / ')}）',
        );
        return;
      }
      final ext = p.extension(entry).toLowerCase();
      if (pane.onlineSelected && ext != '.html' && ext != '.htm') {
        pane.finishPreparation();
        await pane.runOnlineProject(widget.project.path, entry);
        return;
      }

      if (ext == '.html' || ext == '.htm') {
        await _previewServer?.stop();
        try {
          final server = await (StudioProfile.current?.webPreviewFactory?.call(
                widget.project.path,
              ) ??
              LocalWebServer.start(widget.project.path));
          if (!mounted) {
            await server.stop();
            return;
          }
          _previewServer = server;
          // 页面 console 日志转发到终端面板（Web 调试）。
          _debugSub?.cancel();
          _debugSub = server.debugStream.listen((line) {
            _terminalKey.currentState?.appendDebug(line);
          });
          await RunnerService.openUrl(server.url);
          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: Text('预览服务已启动：${server.url}'),
                action: SnackBarAction(
                  label: '复制地址',
                  onPressed: () =>
                      Clipboard.setData(ClipboardData(text: server.url)),
                ),
              ),
            );
          }
        } on SocketException catch (e) {
          _showSnack('启动预览服务失败：${e.message}');
        }
        return;
      }

      pane.appendSystem('初始化本地运行时：${p.basename(entry)}');
      final result = await RunnerService.runProject(
        projectPath: widget.project.path,
        entryFile: entry,
      );
      if (!mounted || !pane.mounted) {
        await result?.cancel?.call();
        await result?.managedProcess?.cancel();
        result?.process?.kill();
        return;
      }
      pane.finishPreparation();
      final hint = result?.hint;
      if (hint != null) {
        pane.appendSystem(hint);
        if (StudioProfile.current?.isOffline != true &&
            OnlineProgram.supports(entry)) {
          await pane.runOnlineProject(widget.project.path, entry);
        }
        return;
      }
      // 应用内运行时（语言 App 注入）：直接接管输出流。
      final stdout = result?.stdout;
      final stderr = result?.stderr;
      final exitCode = result?.exitCode;
      if (result != null &&
          stdout != null &&
          stderr != null &&
          exitCode != null) {
        final code = await pane.attachOutput(
          title: result.title,
          stdout: stdout,
          stderr: stderr,
          exitCode: exitCode,
          cancel: result.cancel,
        );
        if (code == kProgramNotRunExitCode &&
            mounted &&
            pane.mounted &&
            StudioProfile.current?.isOffline != true &&
            OnlineProgram.supports(entry)) {
          pane.appendSystem('本地运行时不可用，转入在线运行');
          await pane.runOnlineProject(widget.project.path, entry);
        }
        return;
      }
      final managedProcess = result?.managedProcess;
      if (managedProcess != null) {
        pane.attachManagedProcess(result!.title, managedProcess);
        return;
      }
      final process = result?.process;
      if (process != null) {
        pane.attachProcess(result!.title, process);
      }
    } catch (error) {
      if (mounted && pane.mounted) pane.appendSystem('运行失败：$error');
    } finally {
      if (pane.mounted && preparing) pane.finishPreparation();
      if (mounted) setState(() => _runningProject = false);
    }
  }

  Future<void> _openOnlineTerminal() async {
    setState(() {
      _terminalCreated = true;
      _terminalCollapsed = false;
      _bottomPanel = _BottomPanel.terminal;
    });
    await WidgetsBinding.instance.endOfFrame;
    if (mounted) await _terminalKey.currentState?.showOnline();
  }

  void _showSnack(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(message)));
  }

  // ---- UI ----

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final wide = MediaQuery.sizeOf(context).width >= _wideBreakpoint;
    final sidebarVisible = _explorerVisible ?? false;
    return Shortcuts(
      shortcuts: const {
        SingleActivator(LogicalKeyboardKey.keyS, control: true): SaveIntent(),
        SingleActivator(LogicalKeyboardKey.keyS, meta: true): SaveIntent(),
        SingleActivator(LogicalKeyboardKey.keyF, control: true): FindIntent(),
        SingleActivator(LogicalKeyboardKey.keyF, meta: true): FindIntent(),
        SingleActivator(LogicalKeyboardKey.keyG, control: true):
            GotoLineIntent(),
        SingleActivator(LogicalKeyboardKey.keyI, control: true): FormatIntent(),
      },
      child: Actions(
        actions: {
          SaveIntent: CallbackAction<SaveIntent>(
            onInvoke: (_) {
              _saveCurrent();
              return null;
            },
          ),
          FindIntent: CallbackAction<FindIntent>(
            onInvoke: (_) {
              _openFind();
              return null;
            },
          ),
          GotoLineIntent: CallbackAction<GotoLineIntent>(
            onInvoke: (_) {
              _showGotoLineDialog();
              return null;
            },
          ),
          FormatIntent: CallbackAction<FormatIntent>(
            onInvoke: (_) {
              _formatCurrent();
              return null;
            },
          ),
        },
        child: Focus(
          autofocus: true,
          child: Scaffold(
            key: _scaffoldKey,
            drawerScrimColor: scheme.surface,
            appBar: PreferredSize(
              preferredSize: const Size.fromHeight(kToolbarHeight),
              child: SelectionToolbarScope(
                editor: _editor,
                controllerBuilder: () => _editor.current?.controller,
                builder: (context, controller) {
                  // 选区非空时 leading / actions 必须传 null：AppBar 的 leading
                  // 槽位是定宽的，换成 0 宽的 widget 仍会占 56px。两者归零加上
                  // titleSpacing: 0，title 槽位才等于屏幕宽度。
                  final hasSelection =
                      controller != null &&
                      !controller.selection.isCollapsed &&
                      controller.selectedText.isNotEmpty;
                  final selected = hasSelection || _pasteToolbarVisible
                      ? controller
                      : null;
                  return AppBar(
                    backgroundColor: selected != null
                        ? scheme.surfaceContainerHigh
                        : null,
                    systemOverlayStyle: selected != null
                        ? SystemUiOverlayStyle(
                            statusBarColor: scheme.surfaceContainerHigh,
                            statusBarIconBrightness:
                                scheme.brightness == Brightness.dark
                                ? Brightness.light
                                : Brightness.dark,
                            statusBarBrightness: scheme.brightness,
                          )
                        : null,
                    leading: selected != null
                        ? null
                        : IconButton(
                            tooltip: sidebarVisible ? '收起文件树' : '打开文件树',
                            onPressed: _toggleExplorer,
                            icon: const Icon(Icons.menu),
                          ),
                    automaticallyImplyLeading: false,
                    titleSpacing: 0,
                    title: selected != null
                        ? SelectionToolbarBar(
                            controller: selected,
                            pasteOnly: !hasSelection,
                            onDismiss: _pasteToolbarVisible
                                ? () => setState(
                                    () => _pasteToolbarVisible = false,
                                  )
                                : null,
                          )
                        : _buildProjectTitle(context, scheme),
                    actions: selected != null
                        ? null
                        : [
                            Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                IconButton(
                                  tooltip: '撤销 (Ctrl+Z)',
                                  onPressed: _editor.current == null
                                      ? null
                                      : _undoCurrent,
                                  icon: const Icon(Icons.undo),
                                ),
                                IconButton(
                                  tooltip: '运行',
                                  onPressed: _runningProject
                                      ? null
                                      : _runProject,
                                  icon: const Icon(Icons.play_arrow),
                                ),
                                PopupMenuButton<String>(
                                  tooltip: '更多',
                                  icon: const Icon(Icons.more_vert),
                                  onSelected: (value) {
                                    if (value.startsWith('file_tool:')) {
                                      unawaited(
                                        _runEditorTool(value.substring(10)),
                                      );
                                      return;
                                    }
                                    switch (value) {
                                      case 'save':
                                        _saveCurrent();
                                      case 'find':
                                        _openFind();
                                      case 'goto':
                                        _showGotoLineDialog();
                                      case 'format':
                                        _formatCurrent();
                                      case 'content_tool':
                                        _openContentTool();
                                      case 'minimap':
                                        widget.settings.setMinimap(
                                          !widget.settings.minimap,
                                        );
                                      case 'terminal':
                                        _terminalCreated = true;
                                        setState(
                                          () => _bottomPanel =
                                              _bottomPanel ==
                                                  _BottomPanel.terminal
                                              ? _BottomPanel.none
                                              : _BottomPanel.terminal,
                                        );
                                      case 'settings':
                                        Navigator.of(context).push(
                                          MaterialPageRoute(
                                            builder: (_) => SettingsPage(
                                              settings: widget.settings,
                                              auth: widget.auth,
                                              store: widget.store,
                                              showAi:
                                                  StudioProfile
                                                      .current
                                                      ?.isOffline !=
                                                  true,
                                            ),
                                          ),
                                        );
                                      case 'ai':
                                        setState(
                                          () => _bottomPanel =
                                              _bottomPanel == _BottomPanel.ai
                                              ? _BottomPanel.none
                                              : _BottomPanel.ai,
                                        );
                                      case 'online_terminal':
                                        unawaited(_openOnlineTerminal());
                                      case 'git':
                                        _openGit();
                                      case 'cloud_pull':
                                        _pullFromCloud();
                                    }
                                  },
                                  itemBuilder: (context) => [
                                    for (final tool
                                        in StudioProfile
                                                .current
                                                ?.editorFileTools ??
                                            const <EditorFileTool>[])
                                      if (tool.extensions.contains(
                                        p
                                            .extension(
                                              _editor.current?.name ?? '',
                                            )
                                            .toLowerCase(),
                                      ))
                                        PopupMenuItem(
                                          value: 'file_tool:${tool.id}',
                                          enabled:
                                              !_runningFileTool &&
                                              _editor.current?.readOnly != true,
                                          child: Row(
                                            children: [
                                              Icon(tool.icon, size: 20),
                                              const SizedBox(width: 12),
                                              Text(tool.label),
                                            ],
                                          ),
                                        ),
                                    const PopupMenuItem(
                                      value: 'save',
                                      child: Row(
                                        children: [
                                          Icon(Icons.save_outlined, size: 20),
                                          SizedBox(width: 12),
                                          Text('保存 (Ctrl+S)'),
                                        ],
                                      ),
                                    ),
                                    const PopupMenuItem(
                                      value: 'find',
                                      child: Row(
                                        children: [
                                          Icon(Icons.search, size: 20),
                                          SizedBox(width: 12),
                                          Text('查找替换 (Ctrl+F)'),
                                        ],
                                      ),
                                    ),
                                    const PopupMenuItem(
                                      value: 'goto',
                                      child: Row(
                                        children: [
                                          Icon(Icons.pin, size: 20),
                                          SizedBox(width: 12),
                                          Text('跳转到行 (Ctrl+G)'),
                                        ],
                                      ),
                                    ),
                                    const PopupMenuItem(
                                      value: 'format',
                                      child: Row(
                                        children: [
                                          Icon(
                                            Icons.format_align_left,
                                            size: 20,
                                          ),
                                          SizedBox(width: 12),
                                          Text('格式化 (Ctrl+I)'),
                                        ],
                                      ),
                                    ),
                                    if (p
                                                .extension(
                                                  _editor.current?.name ?? '',
                                                )
                                                .toLowerCase() ==
                                            '.json' ||
                                        p
                                                .extension(
                                                  _editor.current?.name ?? '',
                                                )
                                                .toLowerCase() ==
                                            '.md' ||
                                        p
                                                .extension(
                                                  _editor.current?.name ?? '',
                                                )
                                                .toLowerCase() ==
                                            '.markdown')
                                      const PopupMenuItem(
                                        value: 'content_tool',
                                        child: Row(
                                          children: [
                                            Icon(
                                              Icons.preview_outlined,
                                              size: 20,
                                            ),
                                            SizedBox(width: 12),
                                            Text('内容工具'),
                                          ],
                                        ),
                                      ),
                                    PopupMenuItem(
                                      value: 'minimap',
                                      child: Row(
                                        children: [
                                          Icon(
                                            widget.settings.minimap
                                                ? Icons.visibility_off_outlined
                                                : Icons.visibility_outlined,
                                            size: 20,
                                          ),
                                          const SizedBox(width: 12),
                                          Text(
                                            widget.settings.minimap
                                                ? '隐藏代码鸟瞰'
                                                : '显示代码鸟瞰',
                                          ),
                                        ],
                                      ),
                                    ),
                                    PopupMenuItem(
                                      value: 'terminal',
                                      child: Row(
                                        children: [
                                          Icon(
                                            _terminalVisible
                                                ? Icons.terminal_outlined
                                                : Icons.terminal,
                                            size: 20,
                                          ),
                                          const SizedBox(width: 12),
                                          Text(
                                            _terminalVisible ? '关闭终端' : '打开终端',
                                          ),
                                        ],
                                      ),
                                    ),
                                    const PopupMenuItem(
                                      value: 'git',
                                      child: Row(
                                        children: [
                                          Icon(
                                            Icons.account_tree_outlined,
                                            size: 20,
                                          ),
                                          SizedBox(width: 12),
                                          Text('Git'),
                                        ],
                                      ),
                                    ),
                                    if (widget.project.isCloud)
                                      const PopupMenuItem(
                                        value: 'cloud_pull',
                                        child: Row(
                                          children: [
                                            Icon(
                                              Icons.cloud_download_outlined,
                                              size: 20,
                                            ),
                                            SizedBox(width: 12),
                                            Text('从云端拉取'),
                                          ],
                                        ),
                                      ),
                                    const PopupMenuItem(
                                      value: 'settings',
                                      child: Row(
                                        children: [
                                          Icon(
                                            Icons.settings_outlined,
                                            size: 20,
                                          ),
                                          SizedBox(width: 12),
                                          Text('设置'),
                                        ],
                                      ),
                                    ),
                                    if (StudioProfile.current?.isOffline !=
                                        true)
                                      PopupMenuItem(
                                        value: 'ai',
                                        child: Row(
                                          children: [
                                            Icon(
                                              _bottomPanel == _BottomPanel.ai
                                                  ? Icons.auto_awesome_outlined
                                                  : Icons.auto_awesome,
                                              size: 20,
                                            ),
                                            const SizedBox(width: 12),
                                            Text(
                                              _bottomPanel == _BottomPanel.ai
                                                  ? '关闭 AI 助手'
                                                  : 'AI 助手',
                                            ),
                                          ],
                                        ),
                                      ),
                                    if (StudioProfile.current?.isOffline !=
                                        true)
                                      const PopupMenuItem(
                                        value: 'online_terminal',
                                        child: Row(
                                          children: [
                                            Icon(
                                              Icons.cloud_outlined,
                                              size: 20,
                                            ),
                                            SizedBox(width: 12),
                                            Text('在线终端（服务器执行）'),
                                          ],
                                        ),
                                      ),
                                  ],
                                ),
                                const SizedBox(width: 8),
                              ],
                            ),
                          ],
                  );
                },
              ),
            ),
            drawer: wide
                ? null
                : Drawer(
                    width: _sidebarWidth + _cardMargin * 2,
                    elevation: 0,
                    shape: const RoundedRectangleBorder(),
                    backgroundColor: scheme.surface,
                    child: SafeArea(
                      child: Padding(
                        padding: const EdgeInsets.all(_cardMargin),
                        child: _buildExplorerCard(
                          context,
                          onFileOpened: _closeDrawer,
                        ),
                      ),
                    ),
                  ),
            body: LayoutBuilder(
              builder: (context, constraints) {
                final bodyHeight = constraints.maxHeight;
                final collapsedPanelHeight = bodyHeight < 36
                    ? bodyHeight
                    : 36.0;
                final maxPanelHeight = (bodyHeight * 0.7)
                    .clamp(collapsedPanelHeight, bodyHeight)
                    .toDouble();
                final compactPanel = maxPanelHeight < 112;
                final terminalPanelHeight = _terminalCollapsed || compactPanel
                    ? collapsedPanelHeight
                    : _terminalHeight
                          .clamp(collapsedPanelHeight, maxPanelHeight)
                          .toDouble();
                final aiPanelHeight = _aiCollapsed || compactPanel
                    ? collapsedPanelHeight
                    : 320.0
                          .clamp(collapsedPanelHeight, maxPanelHeight)
                          .toDouble();
                return ListenableBuilder(
                  listenable: _editor,
                  builder: (context, _) {
                    _syncTabControllerIfNeeded();
                    return Column(
                      children: [
                        Expanded(
                          child: Row(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              if (wide) ...[
                                ClipRect(
                                  child: AnimatedAlign(
                                    duration: const Duration(milliseconds: 200),
                                    curve: Curves.easeOutCubic,
                                    alignment: Alignment.centerLeft,
                                    widthFactor: sidebarVisible ? 1.0 : 0.0,
                                    child: Padding(
                                      padding: const EdgeInsets.all(
                                        _cardMargin,
                                      ),
                                      child: SizedBox(
                                        width: _sidebarWidth,
                                        child: _buildExplorerCard(context),
                                      ),
                                    ),
                                  ),
                                ),
                              ],
                              Expanded(child: _buildEditorArea(context)),
                            ],
                          ),
                        ),
                        if (_terminalCreated)
                          Offstage(
                            offstage:
                                _bottomPanel != _BottomPanel.terminal ||
                                bodyHeight < 36,
                            child: AnimatedContainer(
                              duration: const Duration(milliseconds: 150),
                              height: terminalPanelHeight,
                              child: TerminalPane(
                                key: _terminalKey,
                                workingDirectory: widget.project.path,
                                auth: widget.auth,
                                onlineEnabled:
                                    StudioProfile.current?.isOffline != true,
                                compact: compactPanel,
                                onCollapseChanged: (collapsed) {
                                  if (mounted) {
                                    setState(
                                      () => _terminalCollapsed = collapsed,
                                    );
                                  }
                                },
                                onResizeDelta: (delta) {
                                  if (!mounted) return;
                                  final minHeight = maxPanelHeight < 150
                                      ? maxPanelHeight
                                      : 150.0;
                                  setState(() {
                                    _terminalHeight = (_terminalHeight + delta)
                                        .clamp(minHeight, maxPanelHeight)
                                        .toDouble();
                                  });
                                },
                                onClose: () {
                                  _debugSub?.cancel();
                                  _debugSub = null;
                                  if (mounted) {
                                    setState(() {
                                      _bottomPanel = _BottomPanel.none;
                                      _terminalCollapsed = false;
                                      _terminalCreated = false;
                                    });
                                  }
                                },
                              ),
                            ),
                          ),
                        if (_bottomPanel == _BottomPanel.ai && bodyHeight >= 36)
                          AnimatedContainer(
                            duration: const Duration(milliseconds: 150),
                            height: aiPanelHeight,
                            child: AiPanel(
                              projectPath: widget.project.path,
                              projectName: widget.project.name,
                              language: widget.project.language,
                              settings: widget.settings,
                              compact: compactPanel,
                              onCollapseChanged: (collapsed) {
                                if (mounted) {
                                  setState(() => _aiCollapsed = collapsed);
                                }
                              },
                              onClose: () {
                                if (mounted) {
                                  setState(() {
                                    _bottomPanel = _BottomPanel.none;
                                    _aiCollapsed = false;
                                  });
                                }
                              },
                              onFileCreated: (path) {
                                _editor.openPath(path);
                              },
                            ),
                          ),
                      ],
                    );
                  },
                );
              },
            ),
          ),
        ),
      ),
    );
  }

  /// 防止在 build 外的监听回调中漏同步（不在 build 期间 setState）。
  void _syncTabControllerIfNeeded() {
    final count = _editor.files.length;
    if (_tabController == null && count > 0) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && _tabController == null && _editor.files.isNotEmpty) {
          _syncTabController();
        }
      });
    }
  }

  /// 文件树卡片：圆角 + 细描边、无阴影（对应原生的卡片式抽屉主体）。
  Widget _buildExplorerCard(
    BuildContext context, {
    VoidCallback? onFileOpened,
  }) {
    final scheme = Theme.of(context).colorScheme;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: scheme.surfaceContainerLow,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: scheme.outlineVariant, width: 1),
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(12),
        child: FileExplorer(
          project: widget.project,
          editor: _editor,
          store: widget.store,
          settings: widget.settings,
          onFileOpened: onFileOpened,
          onEntryDeleted: _cloud == null
              ? null
              : (path) async {
                  final token = widget.auth.token;
                  if (token == null) return;
                  final error = await _cloud!.pushDelete(token, path);
                  if (mounted) setState(() => _syncError = error);
                },
        ),
      ),
    );
  }

  Widget _buildProjectTitle(BuildContext context, ColorScheme scheme) {
    // AppBar 的 titleSpacing 为 0，这里补回标题原本的 16px 起始间距。
    return Padding(
      padding: const EdgeInsetsDirectional.only(start: 16),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            widget.project.name,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: Theme.of(
              context,
            ).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w600),
          ),
          Text(
            _currentFileSubtitle(),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: Theme.of(
              context,
            ).textTheme.labelSmall?.copyWith(color: scheme.onSurfaceVariant),
          ),
        ],
      ),
    );
  }

  Widget _buildEditorArea(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final open = _editor.current;
    if (open == null || _tabController == null) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.note_add_outlined,
              size: 64,
              color: scheme.onSurfaceVariant.withValues(alpha: 0.5),
            ),
            const SizedBox(height: 16),
            Text(
              '在左侧选择要编辑的文件',
              style: Theme.of(
                context,
              ).textTheme.bodyLarge?.copyWith(color: scheme.onSurfaceVariant),
            ),
          ],
        ),
      );
    }
    return Column(
      children: [
        if (widget.settings.showEditorTabs) _buildTabBar(context),
        Expanded(
          child: TabBarView(
            controller: _tabController,
            children: [
              for (final file in _editor.files)
                TickerMode(
                  key: ObjectKey(file),
                  enabled: identical(file, open),
                  child: _codeViews.putIfAbsent(
                    file,
                    () => RetainedPage(child: _buildCodeView(context, file)),
                  ),
                ),
            ],
          ),
        ),
        SymbolsBar(
          language: languageForFileName(open.name).isNotEmpty
              ? languageForFileName(open.name)
              : widget.project.language,
          controller: open.controller,
          symbols: _symbolsFor(open),
          onSymbolsEdited: (tokens) {
            final lang = languageForFileName(open.name).isNotEmpty
                ? languageForFileName(open.name)
                : widget.project.language;
            widget.settings.setSymbolBar(lang, tokens.join(' '));
            setState(() {});
          },
        ),
        _buildStatusBar(context, open),
      ],
    );
  }

  Widget _buildTabBar(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      decoration: BoxDecoration(
        color: scheme.surface,
        border: Border(bottom: BorderSide(color: scheme.outlineVariant)),
      ),
      child: TabBar(
        controller: _tabController,
        isScrollable: true,
        tabAlignment: TabAlignment.start,
        dividerColor: Colors.transparent,
        indicatorSize: TabBarIndicatorSize.tab,
        tabs: [for (final file in _editor.files) _buildTab(context, file)],
      ),
    );
  }

  Widget _buildTab(BuildContext context, OpenFile open) {
    final scheme = Theme.of(context).colorScheme;
    final tab = Tab(
      height: 44,
      child: Center(
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              open.timeLabel != null ? Icons.history : _iconFor(open.name),
              size: 16,
              color: scheme.primary,
            ),
            const SizedBox(width: 8),
            Text(open.tabLabel(widget.project.name)),
            const SizedBox(width: 8),
            if (open.dirty)
              Container(
                width: 7,
                height: 7,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: scheme.primary,
                ),
              )
            else
              GestureDetector(
                onTap: () => _closeTab(_editor.files.indexOf(open)),
                child: Icon(
                  Icons.close,
                  size: 15,
                  color: scheme.onSurfaceVariant,
                ),
              ),
          ],
        ),
      ),
    );
    // 长按 / 右键：标签操作菜单。
    return GestureDetector(
      onLongPressStart: (details) => _showTabMenu(open, details.globalPosition),
      onSecondaryTapUp: (details) => _showTabMenu(open, details.globalPosition),
      child: tab,
    );
  }

  Future<void> _showTabMenu(OpenFile open, Offset position) async {
    final index = _editor.files.indexOf(open);
    final action = await showMenu<String>(
      context: context,
      position: RelativeRect.fromLTRB(
        position.dx,
        position.dy,
        position.dx + 1,
        position.dy + 1,
      ),
      items: const [
        PopupMenuItem(value: 'share', child: Text('分享文件')),
        PopupMenuItem(value: 'copy_name', child: Text('复制文件名')),
        PopupMenuDivider(),
        PopupMenuItem(value: 'close_this', child: Text('关闭当前标签')),
        PopupMenuItem(value: 'close_others', child: Text('关闭其他标签')),
        PopupMenuItem(value: 'close_all', child: Text('关闭所有标签')),
      ],
    );
    if (!mounted || action == null) return;
    switch (action) {
      case 'share':
        final shared = await ShareService.shareText(
          title: open.name,
          text: open.controller.text,
        );
        if (!shared && mounted) {
          copyWithToast(context, '【${open.name}】\n${open.controller.text}');
        }
      case 'copy_name':
        copyWithToast(context, open.name);
      case 'close_this':
        await _closeTab(index);
      case 'close_others':
        if (await _confirmDiscardDirty(except: open)) {
          _editor.closeAll(keep: open);
        }
      case 'close_all':
        if (await _confirmDiscardDirty()) {
          _editor.closeAll();
        }
    }
  }

  /// 批量关闭前确认未保存内容。
  Future<bool> _confirmDiscardDirty({OpenFile? except}) async {
    final dirty = _editor.files
        .where((f) => f.dirty && (except == null || !identical(f, except)))
        .toList();
    if (dirty.isEmpty) return true;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('有未保存的更改'),
        content: Text('\${dirty.length} 个文件未保存，丢弃并继续吗？'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('丢弃'),
          ),
        ],
      ),
    );
    return confirmed == true;
  }

  Future<void> _closeTab(int index) async {
    final open = _editor.files[index];
    if (open.dirty) {
      final action = await showDialog<String>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('未保存的更改'),
          content: Text('“${open.name}”有未保存的更改，保存后再关闭吗？'),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop('cancel'),
              child: const Text('取消'),
            ),
            TextButton(
              onPressed: () => Navigator.of(context).pop('discard'),
              child: const Text('不保存'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(context).pop('save'),
              child: const Text('保存'),
            ),
          ],
        ),
      );
      if (!mounted || action == null || action == 'cancel') return;
      if (action == 'save') {
        final error = await _editor.saveAt(index);
        if (error != null) {
          _showSnack(error);
          return;
        }
      }
    }
    _editor.closeAt(index);
  }

  Widget _buildCodeView(BuildContext context, OpenFile open) {
    final scheme = Theme.of(context).colorScheme;
    final textStyle = widget.settings.editorTextStyle;
    final theme = HighlightThemes.themeFor(
      context,
      open.name,
      null,
      settings: widget.settings,
    );
    return Row(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Expanded(
          child: Listener(
            onPointerDown: _handlePointerDown,
            onPointerMove: _handlePointerMove,
            onPointerUp: _handlePointerUp,
            onPointerCancel: _handlePointerUp,
            child: CodeEditor(
              controller: open.controller,
              focusNode: open.focusNode,
              scrollController: open.scrollController,
              findController: open.findController,
              shortcutOverrideActions: editorShortcutOverrides(open.controller),
              style: CodeEditorStyle(
                fontSize: _fontSize,
                fontFamily: textStyle.fontFamily,
                fontFamilyFallback: textStyle.fontFamilyFallback,
                fontWeight: textStyle.fontWeight,
                fontStyle: textStyle.fontStyle,
                fontHeight: textStyle.height,
                backgroundColor:
                    theme?.theme['root']?.backgroundColor ?? scheme.surface,
                textColor: theme?.theme['root']?.color ?? scheme.onSurface,
                cursorColor:
                    HighlightThemes.editorColor(
                      widget.settings,
                      'editorCursor.foreground',
                    ) ??
                    scheme.primary,
                selectionColor:
                    HighlightThemes.editorColor(
                      widget.settings,
                      'editor.selectionBackground',
                    ) ??
                    scheme.primary.withValues(alpha: 0.25),
                highlightColor: scheme.primaryContainer.withValues(alpha: 0.4),
                cursorLineColor:
                    HighlightThemes.editorColor(
                      widget.settings,
                      'editor.lineHighlightBackground',
                    ) ??
                    scheme.surfaceContainerHighest,
                chunkIndicatorColor: scheme.outlineVariant,
                codeTheme: theme,
              ),
              wordWrap: false,
              autofocus: false,
              readOnly: open.readOnly,
              indicatorBuilder:
                  (context, editingController, chunkController, notifier) {
                    return Row(
                      children: [
                        DefaultCodeLineNumber(
                          controller: editingController,
                          notifier: notifier,
                          minNumberCount: 1,
                          textStyle: textStyle.copyWith(
                            color: scheme.onSurfaceVariant.withValues(
                              alpha: 0.55,
                            ),
                            fontSize: _fontSize,
                          ),
                          focusedTextStyle: textStyle.copyWith(
                            color: scheme.primary,
                            fontSize: _fontSize,
                          ),
                        ),
                        DefaultCodeChunkIndicator(
                          width: 18,
                          controller: chunkController,
                          notifier: notifier,
                        ),
                      ],
                    );
                  },
              findBuilder: (context, controller, readOnly) =>
                  EditorFindReplacePanel(
                    controller: controller,
                    readOnly: readOnly,
                  ),
            ),
          ),
        ),
        VerticalDivider(width: 1, thickness: 1, color: scheme.outlineVariant),
        if (widget.settings.minimap)
          CodeMinimap(
            controller: open.controller,
            scrollController: open.scrollController,
          ),
      ],
    );
  }

  Future<void> _showEncodingDialog(OpenFile open) async {
    final index = _editor.currentIndex;
    final picked = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('文件编码'),
        content: Text(
          '当前：${open.encoding}\n'
          '选择新编码后文件将以该编码重新打开，下次保存时写盘也使用它。',
          style: Theme.of(context).textTheme.bodySmall,
        ),
        contentPadding: const EdgeInsets.fromLTRB(24, 16, 24, 0),
        actionsPadding: const EdgeInsets.only(bottom: 8),
        actions: [
          for (final name in TextCodec.names)
            ListTile(
              dense: true,
              title: Text(name),
              trailing: open.encoding == name ? const Icon(Icons.check) : null,
              onTap: () => Navigator.of(context).pop(name),
            ),
        ],
      ),
    );
    if (picked == null || picked == open.encoding || !mounted) return;
    final error = await _editor.reopenWithEncoding(index, picked);
    if (!mounted) return;
    if (error != null) _showSnack(error);
  }

  /// 当前文件的快捷符号集：用户自定义优先，否则按语言默认。
  List<String> _symbolsFor(OpenFile open) {
    final lang = languageForFileName(open.name).isNotEmpty
        ? languageForFileName(open.name)
        : widget.project.language;
    final custom = widget.settings.symbolBars[lang];
    if (custom != null) {
      final value = custom.trim();
      if (value.isEmpty) return const [];
      return value.split(RegExp(r'\s+')).where((s) => s.isNotEmpty).toList();
    }
    return kDefaultSymbolSets[lang] ??
        const [';', ':', '(', ')', '[', ']', '"', "'", '=', '<', '>'];
  }

  Widget _buildStatusBar(BuildContext context, OpenFile open) {
    final scheme = Theme.of(context).colorScheme;
    return ListenableBuilder(
      listenable: Listenable.merge([open.controller, widget.settings]),
      builder: (context, _) {
        final selection = open.controller.selection;
        final line = selection.extentIndex + 1;
        final column = selection.extentOffset + 1;
        final totalLines = open.controller.codeLines.length;
        String modifiedLabel = '';
        final modified = open.modifiedAt;
        if (modified != null) {
          final now = DateTime.now();
          final m = modified;
          modifiedLabel =
              (m.year == now.year && m.month == now.month && m.day == now.day)
              ? '修改于 ${m.hour.toString().padLeft(2, '0')}:${m.minute.toString().padLeft(2, '0')}'
              : '修改于 ${m.month}/${m.day}';
        }
        return Container(
          height: 30,
          padding: const EdgeInsets.symmetric(horizontal: 12),
          decoration: BoxDecoration(
            color: scheme.surfaceContainerLow,
            border: Border(top: BorderSide(color: scheme.outlineVariant)),
          ),
          child: LayoutBuilder(
            builder: (context, constraints) => Row(
              children: [
                // 编码 chip：点击弹出编码选择，重新解码文件（保存时应用）。
                InkWell(
                  borderRadius: BorderRadius.circular(6),
                  onTap: () => _showEncodingDialog(open),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 6,
                      vertical: 2,
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          Icons.abc_outlined,
                          size: 13,
                          color: scheme.primary,
                        ),
                        const SizedBox(width: 4),
                        Text(
                          open.encoding,
                          style: Theme.of(context).textTheme.labelSmall
                              ?.copyWith(
                                color: scheme.primary,
                                fontWeight: FontWeight.w600,
                              ),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(width: 10),
                if (constraints.maxWidth >= 520 &&
                    modifiedLabel.isNotEmpty) ...[
                  Text(
                    modifiedLabel,
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: scheme.onSurfaceVariant,
                    ),
                  ),
                  const SizedBox(width: 10),
                ],
                Flexible(
                  child: Text(
                    '第 $line 行，第 $column 列 · 共 $totalLines 行',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: scheme.onSurfaceVariant,
                    ),
                  ),
                ),
                if (widget.project.isCloud) ...[
                  const SizedBox(width: 12),
                  Icon(
                    switch (_syncState) {
                      SyncState.syncing => Icons.cloud_sync_outlined,
                      SyncState.synced => Icons.cloud_done_outlined,
                      SyncState.offline => Icons.cloud_off_outlined,
                      SyncState.idle => Icons.cloud_outlined,
                    },
                    size: 14,
                    color: switch (_syncState) {
                      SyncState.offline => scheme.error,
                      _ => scheme.primary,
                    },
                  ),
                  if (_syncError != null) ...[
                    const SizedBox(width: 4),
                    Expanded(
                      child: Text(
                        _syncError!,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: Theme.of(
                          context,
                        ).textTheme.bodySmall?.copyWith(color: scheme.error),
                      ),
                    ),
                  ],
                ],
                if (open.dirty && !widget.project.isCloud) ...[
                  const SizedBox(width: 12),
                  Text(
                    '未保存',
                    style: Theme.of(
                      context,
                    ).textTheme.bodySmall?.copyWith(color: scheme.primary),
                  ),
                ],
              ],
            ),
          ),
        );
      },
    );
  }

  IconData _iconFor(String fileName) {
    final ext = p.extension(fileName).toLowerCase();
    return switch (ext) {
      '.dart' => Icons.flutter_dash,
      '.json' => Icons.data_object,
      '.html' || '.htm' => Icons.web_outlined,
      '.md' || '.txt' => Icons.article_outlined,
      _ => Icons.code_outlined,
    };
  }
}
