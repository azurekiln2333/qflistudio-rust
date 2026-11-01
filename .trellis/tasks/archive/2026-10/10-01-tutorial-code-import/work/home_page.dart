import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';

import '../editor/editor_page.dart';
import '../models/project.dart';
import '../services/app_paths.dart';
import '../services/api_client.dart';
import '../services/cloud_sync_service.dart';
import '../services/project_templates.dart';
import '../services/studio_profile.dart';
import '../services/task_activity_service.dart';
import '../store/auth_store.dart';
import '../store/project_store.dart';
import '../store/settings_store.dart';
import 'local_content_pages.dart';
import 'quick_tools_page.dart';
import 'terminax_terminal_page.dart';
import '../i18n/studio_localizations.dart';
import 'community/post_list_page.dart';
import '../widgets/project_card.dart';
import '../widgets/project_dialogs.dart';
import '../widgets/retained_page.dart';
import 'profile_page.dart';

/// 应用外壳：功能、教程、示例和个人页均为独立页面。
class HomePage extends StatefulWidget {
  const HomePage({
    super.key,
    required this.store,
    required this.auth,
    required this.settings,
  });

  final ProjectStore store;
  final AuthStore auth;
  final SettingsStore settings;

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  final _currentIndex = ValueNotifier<int>(0);
  late final PageController _pageController;
  final Map<int, Widget> _pages = {};
  late Widget _pageView;

  @override
  void initState() {
    super.initState();
    _pageController = PageController();
    _pageView = _createPageView();
  }

  @override
  void didUpdateWidget(covariant HomePage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.store != widget.store ||
        oldWidget.auth != widget.auth ||
        oldWidget.settings != widget.settings) {
      _pages.clear();
      _pageView = _createPageView();
    }
  }

  Widget _createPageView() => PageView.builder(
    key: const ValueKey('home-page-view'),
    controller: _pageController,
    itemCount: 4,
    onPageChanged: (index) => _currentIndex.value = index,
    itemBuilder: (context, index) => _pages.putIfAbsent(index, () {
      final profile = StudioProfile.current;
      return RetainedPage(
        key: ValueKey('home-page-$index'),
        child: ValueListenableBuilder<int>(
          valueListenable: _currentIndex,
          child: _buildPage(
            this.context,
            index,
            profile?.isOffline == true,
            profile,
          ),
          builder: (context, selected, child) =>
              TickerMode(enabled: selected == index, child: child!),
        ),
      );
    }),
  );

  @override
  void dispose() {
    _pageController.dispose();
    _currentIndex.dispose();
    super.dispose();
  }

  void _selectPage(int index) {
    if (!_pageController.hasClients) return;
    final page = _pageController.page ?? _currentIndex.value.toDouble();
    if ((page - index).abs() < 0.001) return;
    if ((page - index).abs() > 1) {
      _pageController.jumpToPage(index);
      return;
    }
    _pageController.animateToPage(
      index,
      duration: const Duration(milliseconds: 220),
      curve: Curves.easeOutCubic,
    );
  }

  @override
  Widget build(BuildContext context) {
    final profile = StudioProfile.current;
    final offline = profile?.isOffline == true;
    final l10n = StudioLocalizations.of(context);
    final wide = MediaQuery.sizeOf(context).width >= 900;
    final extendedRail = MediaQuery.sizeOf(context).width >= 1200;
    final destinations = [
      NavigationDestination(
        icon: const Icon(Icons.home_outlined),
        selectedIcon: const Icon(Icons.home),
        label: l10n.home,
      ),
      NavigationDestination(
        icon: const Icon(Icons.apps_outlined),
        selectedIcon: const Icon(Icons.apps),
        label: l10n.functions,
      ),
      NavigationDestination(
        icon: const Icon(Icons.menu_book_outlined),
        selectedIcon: const Icon(Icons.menu_book),
        label: l10n.tutorial,
      ),
      NavigationDestination(
        icon: Icon(offline ? Icons.code_outlined : Icons.person_outline),
        selectedIcon: Icon(offline ? Icons.code : Icons.person),
        label: offline ? l10n.examples : l10n.profile,
      ),
    ];
    return Scaffold(
      body: Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (wide) ...[
            ValueListenableBuilder<int>(
              valueListenable: _currentIndex,
              builder: (context, selected, _) => NavigationRail(
                selectedIndex: selected,
                onDestinationSelected: _selectPage,
                extended: extendedRail,
                labelType: extendedRail
                    ? NavigationRailLabelType.none
                    : NavigationRailLabelType.all,
                groupAlignment: -0.7,
                destinations: [
                  for (final destination in destinations)
                    NavigationRailDestination(
                      icon: destination.icon,
                      selectedIcon: destination.selectedIcon,
                      label: Text(destination.label),
                    ),
                ],
              ),
            ),
            const VerticalDivider(width: 1, thickness: 1),
          ],
          Expanded(child: _pageView),
        ],
      ),
      bottomNavigationBar: wide
          ? null
          : ValueListenableBuilder<int>(
              valueListenable: _currentIndex,
              builder: (context, selected, _) => NavigationBar(
                selectedIndex: selected,
                onDestinationSelected: _selectPage,
                destinations: destinations,
              ),
            ),
    );
  }

  Widget _buildPage(
    BuildContext context,
    int index,
    bool offline,
    StudioProfile? profile,
  ) {
    return switch (index) {
      0 => HomeTab(
        store: widget.store,
        auth: widget.auth,
        settings: widget.settings,
      ),
      1 => FunctionsTab(
        onOpenTerminal: () => Navigator.of(context).push(
          MaterialPageRoute(
            builder: (_) => TerminaxTerminalPage(store: widget.store),
          ),
        ),
        onOpenContentTool: _isContentProduct
            ? () => Navigator.of(context).push(
                MaterialPageRoute(
                  builder: (_) => ContentToolsPage(store: widget.store),
                ),
              )
            : null,
      ),
      2 =>
        offline
            ? LocalTutorialsTab(
                language: profile!.id,
                store: widget.store,
                auth: widget.auth,
                settings: widget.settings,
              )
            : TutorialsTab(auth: widget.auth),
      3 =>
        offline
            ? ExampleCodeTab(
                language: profile!.id,
                store: widget.store,
                auth: widget.auth,
                settings: widget.settings,
              )
            : ProfileTab(
                auth: widget.auth,
                settings: widget.settings,
                store: widget.store,
              ),
      _ => const SizedBox.shrink(),
    };
  }

  bool get _isContentProduct =>
      StudioProfile.current?.toolsPageBuilder != null ||
      switch (StudioProfile.current?.productKey) {
        StudioProductCatalog.jsonKey ||
        StudioProductCatalog.noteKey ||
        StudioProductCatalog.sqlabKey => true,
        _ => false,
      };
}

/// 主页 Tab：项目列表 + 搜索 + 更多操作。
/// 内部 4 个子页签：最近打开 / 全部项目 / 收藏 / 云端。
class HomeTab extends StatefulWidget {
  const HomeTab({
    super.key,
    required this.store,
    required this.auth,
    required this.settings,
  });

  final ProjectStore store;
  final AuthStore auth;
  final SettingsStore settings;

  @override
  State<HomeTab> createState() => _HomeTabState();
}

enum _ProjectScope { all, history, favorite, cloud }

class _HomeTabState extends State<HomeTab>
    with TickerProviderStateMixin, AutomaticKeepAliveClientMixin {
  final _searchController = TextEditingController();
  bool _searchOpen = false;
  String _query = '';
  String _languageFilter = '';
  late bool _loggedIn;
  Future<void>? _refreshRequest;
  late final List<_ProjectScope> _scopes =
      StudioProfile.current?.showHomeTabs == false
      ? const [_ProjectScope.all]
      : StudioProfile.current?.isOffline == true
      ? const [_ProjectScope.all, _ProjectScope.history, _ProjectScope.favorite]
      : _ProjectScope.values;
  late final TabController _projectTabs = TabController(
    length: _scopes.length,
    vsync: this,
  );

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _loggedIn = widget.auth.isLoggedIn;
    widget.auth.addListener(_onAuthChanged);
    if (_loggedIn) {
      unawaited(TaskActivityService.instance.refreshIfDue(widget.auth));
    }
  }

  @override
  void didUpdateWidget(covariant HomeTab oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.auth != widget.auth) {
      oldWidget.auth.removeListener(_onAuthChanged);
      widget.auth.addListener(_onAuthChanged);
      _loggedIn = widget.auth.isLoggedIn;
    }
  }

  void _onAuthChanged() {
    final loggedIn = widget.auth.isLoggedIn;
    if (mounted && loggedIn != _loggedIn) {
      setState(() => _loggedIn = loggedIn);
      if (loggedIn) {
        unawaited(TaskActivityService.instance.refreshIfDue(widget.auth));
      }
    }
  }

  @override
  void dispose() {
    widget.auth.removeListener(_onAuthChanged);
    _searchController.dispose();
    _projectTabs.dispose();
    super.dispose();
  }

  void _openSearch() {
    setState(() {
      _searchOpen = true;
      _query = '';
      _languageFilter = '';
      _searchController.clear();
    });
  }

  void _closeSearch() {
    setState(() {
      _searchOpen = false;
      _query = '';
      _searchController.clear();
    });
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final l10n = StudioLocalizations.of(context);
    return Scaffold(
      appBar: AppBar(
        leading: _searchOpen
            ? IconButton(
                tooltip: l10n.exitSearch,
                icon: const Icon(Icons.arrow_back),
                onPressed: _closeSearch,
              )
            : null,
        automaticallyImplyLeading: false,
        centerTitle: false,
        title: _searchOpen
            ? _buildSearchField()
            : Text(
                StudioProfile.current?.appTitle ?? 'QFLIStudio+',
                style: Theme.of(context).textTheme.titleLarge?.copyWith(
                  color: Theme.of(context).colorScheme.primary,
                ),
              ),
        actions: _searchOpen
            ? const [SizedBox(width: 8)]
            : [
                IconButton(
                  tooltip: l10n.searchProjects,
                  icon: const Icon(Icons.search),
                  onPressed: _openSearch,
                ),
                PopupMenuButton<String>(
                  tooltip: l10n.more,
                  icon: const Icon(Icons.more_vert),
                  onSelected: (value) {
                    switch (value) {
                      case 'add_existing':
                        showAddExistingDialog(context, widget.store);
                      case 'remove_missing':
                        _removeMissingProjects(context);
                      case 'new_cloud':
                        _createCloudProject(context);
                    }
                  },
                  itemBuilder: (context) => [
                    if (AppPaths.isDesktop)
                      PopupMenuItem(
                        value: 'add_existing',
                        child: Row(
                          children: [
                            Icon(Icons.folder_open_outlined, size: 20),
                            SizedBox(width: 12),
                            Text(l10n.addExistingProject),
                          ],
                        ),
                      ),
                    if (StudioProfile.current?.isOffline != true &&
                        widget.auth.isLoggedIn)
                      PopupMenuItem(
                        value: 'new_cloud',
                        child: Row(
                          children: [
                            Icon(Icons.cloud_upload_outlined, size: 20),
                            SizedBox(width: 12),
                            Text(l10n.newCloudProject),
                          ],
                        ),
                      ),
                    PopupMenuItem(
                      value: 'remove_missing',
                      child: Row(
                        children: [
                          Icon(Icons.folder_delete_outlined, size: 20),
                          SizedBox(width: 12),
                          Text(l10n.removeMissingProjects),
                        ],
                      ),
                    ),
                  ],
                ),
                const SizedBox(width: 8),
              ],
      ),
      floatingActionButton: _searchOpen
          ? null
          : FloatingActionButton.extended(
              onPressed: () => _createProject(context),
              icon: const Icon(Icons.create_new_folder_outlined),
              label: Text(l10n.createProject),
            ),
      body: ListenableBuilder(
        listenable: widget.store,
        builder: (context, _) {
          if (_searchOpen) {
            return _buildProjectList(
              context,
              scope: _ProjectScope.all,
              keyword: _query,
            );
          }
          return Column(
            children: [
              if (StudioProfile.current?.showHomeTabs ?? true)
                TabBar(
                  controller: _projectTabs,
                  isScrollable: true,
                  tabAlignment: TabAlignment.start,
                  dividerColor: Colors.transparent,
                  labelPadding: const EdgeInsets.symmetric(horizontal: 12),
                  tabs: [
                    Tab(
                      height: 36,
                      child: Center(child: Text(l10n.allProjects)),
                    ),
                    Tab(
                      height: 36,
                      child: Center(child: Text(l10n.historyProjects)),
                    ),
                    Tab(
                      height: 36,
                      child: Center(child: Text(l10n.favoriteProjects)),
                    ),
                    if (_scopes.contains(_ProjectScope.cloud))
                      Tab(
                        height: 36,
                        child: Center(child: Text(l10n.cloudProjects)),
                      ),
                  ],
                ),
              Expanded(
                child: TabBarView(
                  controller: _projectTabs,
                  children: [
                    for (final scope in _scopes)
                      _buildProjectList(context, scope: scope),
                  ],
                ),
              ),
            ],
          );
        },
      ),
    );
  }

  Widget _buildSearchField() {
    final scheme = Theme.of(context).colorScheme;
    final l10n = StudioLocalizations.of(context);
    return TextField(
      controller: _searchController,
      autofocus: true,
      textAlign: TextAlign.center,
      onChanged: (value) => setState(() => _query = value),
      style: Theme.of(context).textTheme.bodyLarge,
      decoration: InputDecoration(
        hintText: l10n.searchProjectHint,
        suffixIcon: _query.isEmpty
            ? null
            : IconButton(
                tooltip: l10n.clear,
                icon: const Icon(Icons.close, size: 20),
                onPressed: () {
                  _searchController.clear();
                  setState(() => _query = '');
                },
              ),
        border: InputBorder.none,
        enabledBorder: InputBorder.none,
        focusedBorder: InputBorder.none,
        contentPadding: EdgeInsets.zero,
        hintStyle: TextStyle(color: scheme.onSurfaceVariant),
      ),
    );
  }

  /// 按页签取项目列表。
  List<Project> _projectsFor(_ProjectScope scope) {
    final all = widget.store.projects
        .where(
          (project) =>
              StudioProfile.current?.isOffline != true || !project.isCloud,
        )
        .toList();
    switch (scope) {
      case _ProjectScope.all:
        final list = [
          ...all,
        ]..sort((a, b) => a.name.toLowerCase().compareTo(b.name.toLowerCase()));
        return list;
      case _ProjectScope.history:
        return [...all];
      case _ProjectScope.favorite:
        return all.where((p) => p.favorite).toList();
      case _ProjectScope.cloud:
        return all.where((p) => p.isCloud).toList();
    }
  }

  /// 语言筛选芯片的候选：语言专属 App 只列出自己那一门语言。
  List<String> get _languageChips {
    final profile = StudioProfile.current;
    final source = ProjectLanguages.all.where((l) => l != '空项目');
    if (profile == null) return source.toList(growable: false);
    return profile.filterLanguages(source);
  }

  Widget _buildProjectList(
    BuildContext context, {
    required _ProjectScope scope,
    String keyword = '',
  }) {
    var projects = _projectsFor(scope);
    final searching = keyword.isNotEmpty;
    if (searching) {
      final k = keyword.trim().toLowerCase();
      projects = projects
          .where(
            (p) =>
                p.name.toLowerCase().contains(k) ||
                p.path.toLowerCase().contains(k),
          )
          .toList();
    }
    if (scope == _ProjectScope.all) {
      // 语言筛选 chips（全部项目页签），始终显示全部语言。
      final chipList = [
        Padding(
          padding: const EdgeInsets.only(right: 4),
          child: FilterChip(
            label: Text(StudioLocalizations.of(context).allLanguages),
            selected: _languageFilter.isEmpty,
            visualDensity: VisualDensity.compact,
            materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
            onSelected: (_) => setState(() => _languageFilter = ''),
          ),
        ),
        for (final lang in _languageChips)
          Padding(
            padding: const EdgeInsets.only(right: 4),
            child: FilterChip(
              label: Text(lang),
              selected: _languageFilter == lang,
              visualDensity: VisualDensity.compact,
              materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
              onSelected: (_) => setState(() {
                _languageFilter = _languageFilter == lang ? '' : lang;
              }),
            ),
          ),
      ];
      if (_languageFilter.isNotEmpty) {
        projects = projects
            .where((p) => p.language == _languageFilter)
            .toList();
      }
      final body = projects.isEmpty
          ? _emptyScrollable(
              searching || _languageFilter.isNotEmpty
                  ? const _EmptySearchResult()
                  : _EmptyState(onCreate: () => _createProject(context)),
            )
          : _buildGridOrList(context, projects);
      // The main app also has a profile; use its homepage-tab setting.
      final showLanguageChips =
          (StudioProfile.current?.showHomeTabs ?? true) && chipList.length > 1;
      return Column(
        children: [
          if (showLanguageChips)
            // 高度随内容收缩；左右 12 与卡片外边距、TabBar labelPadding 对齐。
            // 下边距为 0：下方列表自带 8 的顶部内边距，避免叠成 16 的双倍空隙。
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
              child: Row(children: chipList),
            ),
          Expanded(child: _refreshable(scope, body)),
        ],
      );
    }
    if (projects.isEmpty) {
      final empty = switch (scope) {
        _ProjectScope.favorite => _buildSimpleEmpty(
          context,
          Icons.star_border_outlined,
          StudioLocalizations.of(context).favoriteProjects,
          StudioLocalizations.of(context).favoriteProjectHint,
        ),
        _ProjectScope.cloud => _buildSimpleEmpty(
          context,
          Icons.cloud_outlined,
          StudioLocalizations.of(context).cloudProjects,
          StudioLocalizations.of(context).cloudProjectHint,
        ),
        _ =>
          searching
              ? const _EmptySearchResult()
              : _EmptyState(onCreate: () => _createProject(context)),
      };
      return _refreshable(scope, _emptyScrollable(empty));
    }
    return _refreshable(scope, _buildGridOrList(context, projects));
  }

  Widget _refreshable(_ProjectScope scope, Widget child) =>
      RefreshIndicator(onRefresh: () => _refreshProjects(scope), child: child);

  Widget _emptyScrollable(Widget child) => CustomScrollView(
    physics: const AlwaysScrollableScrollPhysics(),
    slivers: [
      SliverFillRemaining(
        hasScrollBody: false,
        child: Padding(padding: const EdgeInsets.all(24), child: child),
      ),
    ],
  );

  Future<void> _refreshProjects(_ProjectScope scope) async {
    if (_refreshRequest != null) return _refreshRequest;
    final request = _reloadProjects(scope);
    _refreshRequest = request;
    try {
      await request;
    } finally {
      if (identical(_refreshRequest, request)) _refreshRequest = null;
    }
  }

  Future<void> _reloadProjects(_ProjectScope scope) async {
    try {
      await widget.store.refresh();
      if (StudioProfile.current?.isOffline == true) return;
      final token = widget.auth.token;
      if (token == null ||
          (scope != _ProjectScope.cloud && scope != _ProjectScope.all)) {
        return;
      }
      final remote = await ApiClient.instance.cloudProjects(token);
      if (!mounted || widget.auth.token != token) return;
      final projects = <Project>[];
      for (final item in remote) {
        final id = item['id'] as String?;
        final name = item['name'] as String?;
        if (id == null || id.isEmpty || name == null) continue;
        final legacyId = item['legacyId'] as String?;
        if (legacyId != null) await widget.store.remapCloudId(legacyId, id);
        final existing = widget.store.projects.where(
          (project) => project.cloudId == id,
        );
        final mirror = await CloudSyncService.open(
          cloudId: id,
          name: name,
          cachePath: existing.isEmpty ? null : existing.first.path,
        );
        projects.add(
          Project.create(name: name, path: mirror.localPath, cloudId: id),
        );
        mirror.dispose();
      }
      if (!mounted || widget.auth.token != token) return;
      await widget.store.mergeCloudProjects(projects);
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            error is ApiException
                ? StudioLocalizations.of(
                    context,
                  ).cloudRefreshFailed(error.message)
                : StudioLocalizations.of(context).refreshProjectsFailed,
          ),
        ),
      );
    }
  }

  Widget _buildSimpleEmpty(
    BuildContext context,
    IconData icon,
    String title,
    String subtitle,
  ) {
    final theme = Theme.of(context);
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            icon,
            size: 56,
            color: theme.colorScheme.onSurfaceVariant.withValues(alpha: 0.5),
          ),
          const SizedBox(height: 12),
          Text(title, style: theme.textTheme.titleMedium),
          const SizedBox(height: 6),
          Text(
            subtitle,
            textAlign: TextAlign.center,
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildGridOrList(BuildContext context, List<Project> projects) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final wide = constraints.maxWidth > 720;
        const padding = EdgeInsets.fromLTRB(12, 8, 12, 96);
        if (wide) {
          final scale = MediaQuery.textScalerOf(context).scale(1);
          final itemExtent = (24 + 38 * scale).clamp(90.0, 180.0).toDouble();
          return Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 1360),
              child: GridView.builder(
                physics: const AlwaysScrollableScrollPhysics(),
                padding: padding,
                gridDelegate: SliverGridDelegateWithMaxCrossAxisExtent(
                  maxCrossAxisExtent: 420,
                  mainAxisSpacing: 8,
                  crossAxisSpacing: 8,
                  mainAxisExtent: itemExtent,
                ),
                itemCount: projects.length,
                itemBuilder: (context, i) => _buildCard(context, projects[i]),
              ),
            ),
          );
        }
        return ListView.builder(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: padding,
          itemCount: projects.length,
          itemBuilder: (context, i) => Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: _buildCard(context, projects[i]),
          ),
        );
      },
    );
  }

  Widget _buildCard(BuildContext context, Project project) {
    return ProjectCard(
      project: project,
      onOpen: () => _openProject(context, project),
      onRemove: () => _deleteProject(context, project),
      onToggleFavorite: (value) => widget.store.setFavorite(project, value),
    );
  }

  Future<void> _createProject(BuildContext context) async {
    final result = await showCreateProjectDialog(context, widget.store);
    if (result != null && context.mounted) {
      TaskActivityService.report(widget.auth, 'create_project');
      await _openProject(
        context,
        result.project,
        initialOpenFile: result.openFile,
      );
    }
  }

  Future<void> _openProject(
    BuildContext context,
    Project project, {
    String? initialOpenFile,
  }) async {
    if (!project.isCloud && !Directory(project.path).existsSync()) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            StudioLocalizations.of(context).missingProjectPath(project.path),
          ),
          action: SnackBarAction(
            label: StudioLocalizations.of(context).removeFromList,
            onPressed: () => widget.store.remove(project),
          ),
        ),
      );
      return;
    }
    widget.store.touch(project);
    TaskActivityService.report(widget.auth, 'open_project');
    if (!context.mounted) return;
    await Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => EditorPage(
          project: project,
          auth: widget.auth,
          store: widget.store,
          settings: widget.settings,
          initialOpenPath: initialOpenFile,
        ),
      ),
    );
  }

  Future<void> _deleteProject(BuildContext context, Project project) async {
    final confirmed = await showDeleteProjectConfirm(context, project);
    if (!confirmed || !context.mounted) return;
    // 压缩备份可能耗时，显示进度提示。
    showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (context) {
        final l10n = StudioLocalizations.of(context);
        return AlertDialog(
          content: Row(
            children: [
              const CircularProgressIndicator(),
              const SizedBox(width: 20),
              Expanded(child: Text(l10n.backupAndDelete)),
            ],
          ),
        );
      },
    );
    final error = await widget.store.deleteProject(project);
    if (!context.mounted) return;
    Navigator.of(context, rootNavigator: true).pop();
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          error ?? StudioLocalizations.of(context).deletedProject(project.name),
        ),
      ),
    );
  }

  /// 批量移除目录已不存在的项目记录（不涉及磁盘删除）。
  Future<void> _removeMissingProjects(BuildContext context) async {
    final missing = widget.store.projects
        .where((p) => !p.isCloud && !Directory(p.path).existsSync())
        .toList();
    if (missing.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(StudioLocalizations.of(context).noMissingProjects),
        ),
      );
      return;
    }
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) {
        final l10n = StudioLocalizations.of(context);
        return AlertDialog(
          title: Text(l10n.removeMissingTitle),
          content: Text(
            l10n.removeMissingMessage(
              missing.length,
              missing.map((p) => '· ${p.name}').join('\n'),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: Text(l10n.cancel),
            ),
            FilledButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: Text(l10n.remove),
            ),
          ],
        );
      },
    );
    if (confirmed == true) {
      for (final project in missing) {
        widget.store.remove(project);
      }
    }
  }

  Future<void> _createCloudProject(BuildContext context) async {
    final picked = await showDialog<(String, ProjectTemplate)>(
      context: context,
      builder: (context) {
        final l10n = StudioLocalizations.of(context);
        var template = defaultTemplate();
        final controller = TextEditingController();
        return StatefulBuilder(
          builder: (context, setState) => AlertDialog(
            title: Text(l10n.newCloudProject),
            content: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(
                  controller: controller,
                  autofocus: true,
                  decoration: InputDecoration(
                    labelText: l10n.projectName,
                    prefixIcon: Icon(Icons.cloud_upload_outlined),
                  ),
                ),
                const SizedBox(height: 16),
                DropdownMenu<ProjectTemplate>(
                  initialSelection: template,
                  expandedInsets: EdgeInsets.zero,
                  label: Text(l10n.projectType),
                  onSelected: (value) {
                    if (value != null) setState(() => template = value);
                  },
                  dropdownMenuEntries: [
                    for (final t in availableTemplates())
                      DropdownMenuEntry(
                        value: t,
                        label: t.label,
                        leadingIcon: Icon(t.icon, size: 20),
                      ),
                  ],
                ),
              ],
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(context).pop(),
                child: Text(l10n.cancel),
              ),
              FilledButton(
                onPressed: () => Navigator.of(context).pop(
                  controller.text.trim().isEmpty
                      ? null
                      : (controller.text.trim(), template),
                ),
                child: Text(l10n.create),
              ),
            ],
          ),
        );
      },
    );
    if (picked == null || !context.mounted) return;
    final (name, template) = picked;
    if (RegExp(r'[\\/:*?"<>|]').hasMatch(name)) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(StudioLocalizations.of(context).invalidProjectName),
        ),
      );
      return;
    }
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(StudioLocalizations.of(context).creatingCloudProject),
        duration: Duration(seconds: 1),
      ),
    );
    final created = await CloudSyncService.createCloudProject(
      token: widget.auth.token!,
      name: name,
      template: template,
    );
    if (!context.mounted) return;
    if (created.error != null) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(created.error!)));
      return;
    }
    final service = await CloudSyncService.open(
      cloudId: created.id!,
      name: name,
    );
    final registered = await widget.store.addCloudProject(
      name: name,
      cloudId: '${created.id}',
      cachePath: service.localPath,
      language: template.language,
    );
    service.dispose();
    if (!context.mounted) return;
    if (registered.error != null) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(registered.error!)));
      return;
    }
    TaskActivityService.report(widget.auth, 'create_project');
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(StudioLocalizations.of(context).cloudProjectCreated),
      ),
    );
  }
}

class _EmptySearchResult extends StatelessWidget {
  const _EmptySearchResult();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = StudioLocalizations.of(context);
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            Icons.search_off,
            size: 64,
            color: theme.colorScheme.onSurfaceVariant.withValues(alpha: 0.6),
          ),
          const SizedBox(height: 16),
          Text(l10n.noMatchingProjects, style: theme.textTheme.titleMedium),
          const SizedBox(height: 8),
          Text(
            l10n.searchProjectsHint,
            style: theme.textTheme.bodyMedium?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
        ],
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState({required this.onCreate});

  final VoidCallback onCreate;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = StudioLocalizations.of(context);
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            Icons.folder_off_outlined,
            size: 72,
            color: theme.colorScheme.onSurfaceVariant.withValues(alpha: 0.6),
          ),
          const SizedBox(height: 16),
          Text(l10n.noProjects, style: theme.textTheme.headlineSmall),
          const SizedBox(height: 8),
          Text(
            AppPaths.isDesktop
                ? l10n.desktopCreateProjectHint
                : l10n.mobileCreateProjectHint,
            style: theme.textTheme.bodyMedium?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
          const SizedBox(height: 24),
          FilledButton.icon(
            onPressed: onCreate,
            icon: const Icon(Icons.create_new_folder_outlined),
            label: Text(l10n.createProject),
          ),
        ],
      ),
    );
  }
}

/// 教程 Tab：社区教程内容（专区/标签/搜索/点赞/评论/分享）。
class TutorialsTab extends StatelessWidget {
  const TutorialsTab({super.key, required this.auth});

  final AuthStore auth;

  @override
  Widget build(BuildContext context) {
    return PostListPage(type: 'tutorial', auth: auth);
  }
}

/// 讨论 Tab：社区讨论内容。
class DiscussionTab extends StatelessWidget {
  const DiscussionTab({super.key, required this.auth});

  final AuthStore auth;

  @override
  Widget build(BuildContext context) {
    return PostListPage(type: 'discussion', auth: auth);
  }
}
