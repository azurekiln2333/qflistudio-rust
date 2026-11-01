import 'package:flutter/widgets.dart';

/// 共享内核使用的轻量本地化层。
///
/// 产品名保持品牌原文；界面文案按系统语言切换，避免页面组件直接写死文本。
class StudioLocalizations {
  const StudioLocalizations(this.locale);

  final Locale locale;

  static const supportedLocales = <Locale>[
    Locale('zh', 'CN'),
    Locale('zh', 'TW'),
    Locale('en'),
  ];

  static const delegate = _StudioLocalizationsDelegate();

  static StudioLocalizations of(BuildContext context) =>
      Localizations.of<StudioLocalizations>(context, StudioLocalizations) ??
      const StudioLocalizations(Locale('zh', 'CN'));

  static Locale resolveLocale(Locale platform) {
    if (platform.languageCode == 'zh' &&
        const {'TW', 'HK', 'MO'}.contains(platform.countryCode)) {
      return const Locale('zh', 'TW');
    }
    if (platform.languageCode == 'en') return const Locale('en');
    return const Locale('zh', 'CN');
  }

  bool get isEnglish => locale.languageCode == 'en';
  bool get isTraditionalChinese =>
      locale.languageCode == 'zh' && locale.countryCode == 'TW';

  String _text(String key) {
    final values = isEnglish
        ? _en
        : isTraditionalChinese
        ? _zhTw
        : _zhCn;
    return values[key] ?? _zhCn[key] ?? key;
  }

  String get home => _text('home');
  String get functions => _text('functions');
  String get quickTools => _text('quickTools');
  String get examples => _text('examples');
  String get discussion => _text('discussion');
  String get profile => _text('profile');
  String get tutorial => _text('tutorial');
  String get tutorialSubtitle => _text('tutorialSubtitle');
  String get terminal => _text('terminal');
  String get terminalSubtitle => _text('terminalSubtitle');
  String get close => _text('close');
  String get execute => _text('execute');
  String get clear => _text('clear');
  String get copyTerminal => _text('copyTerminal');
  String get loading => _text('loading');
  String get noWorkingDirectory => _text('noWorkingDirectory');
  String get localTutorialMissing => _text('localTutorialMissing');
  String get localExamplesMissing => _text('localExamplesMissing');
  String get copyExample => _text('copyExample');
  String get exampleCopied => _text('exampleCopied');
  String get importExampleProject => _text('importExampleProject');
  String get restoreDefault => _text('restoreDefault');
  String get saveExample => _text('saveExample');
  String get projectImported => _text('projectImported');
  String get sampleCode => _text('sampleCode');
  String get expectedOutput => _text('expectedOutput');
  String get practice => _text('practice');
  String get exitSearch => _text('exitSearch');
  String get searchProjects => _text('searchProjects');
  String get more => _text('more');
  String get addExistingProject => _text('addExistingProject');
  String get newCloudProject => _text('newCloudProject');
  String get removeMissingProjects => _text('removeMissingProjects');
  String get createProject => _text('createProject');
  String get allProjects => _text('allProjects');
  String get historyProjects => _text('historyProjects');
  String get favoriteProjects => _text('favoriteProjects');
  String get cloudProjects => _text('cloudProjects');
  String get favoriteProjectHint => _text('favoriteProjectHint');
  String get cloudProjectHint => _text('cloudProjectHint');
  String get searchProjectHint => _text('searchProjectHint');
  String get allLanguages => _text('allLanguages');
  String get removeFromList => _text('removeFromList');
  String get backupAndDelete => _text('backupAndDelete');
  String get noMissingProjects => _text('noMissingProjects');
  String get removeMissingTitle => _text('removeMissingTitle');
  String get cancel => _text('cancel');
  String get remove => _text('remove');
  String get projectName => _text('projectName');
  String get projectType => _text('projectType');
  String get create => _text('create');
  String get invalidProjectName => _text('invalidProjectName');
  String get creatingCloudProject => _text('creatingCloudProject');
  String get cloudProjectCreated => _text('cloudProjectCreated');
  String get noMatchingProjects => _text('noMatchingProjects');
  String get searchProjectsHint => _text('searchProjectsHint');
  String get noProjects => _text('noProjects');
  String get desktopCreateProjectHint => _text('desktopCreateProjectHint');
  String get mobileCreateProjectHint => _text('mobileCreateProjectHint');
  String get importResource => _text('importResource');
  String get importPhoto => _text('importPhoto');
  String get replaceExistingResource => _text('replaceExistingResource');
  String importFinished(int count) =>
      _text('importFinished').replaceAll('{count}', '$count');
  String get replaceResource => _text('replaceResource');
  String get importFailed => _text('importFailed');

  String replaceResourceMessage(String name) =>
      _text('replaceResourceMessage').replaceAll('{name}', name);

  String missingProjectPath(String path) =>
      '${_text('missingProjectPath')}$path';
  String deletedProject(String name) =>
      _text('deletedProject').replaceAll('{name}', name);
  String removeMissingMessage(int count, String names) =>
      _text('removeMissingMessage')
          .replaceAll('{count}', '$count')
          .replaceAll('{names}', names);
  String cloudRefreshFailed(String message) =>
      _text('cloudRefreshFailed').replaceAll('{message}', message);
  String get refreshProjectsFailed => _text('refreshProjectsFailed');

  String examplesCount(int count) =>
      _text('examplesCount').replaceAll('{count}', count.toString());

  String runMode(String engine) => '${_text('runMode')}$engine';
  String limits(String value) => '${_text('limits')}$value';
  String hint(String value) => '${_text('hint')}$value';
  String reference(String value) => '${_text('reference')}$value';

  String terminalStarted(String cwd) => isEnglish
      ? 'Local shell. Working directory: $cwd'
      : isTraditionalChinese
      ? '本機終端機。工作目錄：$cwd'
      : '本地终端。工作目录：$cwd';

  String terminalShellHint(String commandExample) =>
      '${_text('shellHintPrefix')}$commandExample';

  String get terminalCollapsed => _text('terminalCollapsed');
  String get terminalHeader => _text('terminalHeader');
  String get newTerminal => _text('newTerminal');
  String get jsonTools => _text('jsonTools');
  String get jsonSource => _text('jsonSource');
  String get jsonFormat => _text('jsonFormat');
  String get jsonValidate => _text('jsonValidate');
  String get jsonValid => _text('jsonValid');
  String get jsonInvalid => _text('jsonInvalid');
  String get jsonRootType => _text('jsonRootType');
  String get jsonStructure => _text('jsonStructure');
  String get markdownTools => _text('markdownTools');
  String get markdownEdit => _text('markdownEdit');
  String get markdownPreview => _text('markdownPreview');
  String get markdownSource => _text('markdownSource');
  String get sqlTools => _text('sqlTools');
  String get sqlSource => _text('sqlSource');
  String get executeQuery => _text('executeQuery');
  String get applyToEditor => _text('applyToEditor');
  String exitCode(int code) => _text('exitCode').replaceAll('{code}', '$code');
  String runEnded(int code) => _text('runEnded').replaceAll('{code}', '$code');
  String unableToExecute(String message) =>
      '${_text('unableToExecute')}$message';

  static const _zhCn = <String, String>{
    'home': '主页',
    'functions': '功能',
    'quickTools': '快捷功能',
    'examples': '示例代码',
    'discussion': '讨论',
    'profile': '我的',
    'tutorial': '教程',
    'tutorialSubtitle': '打开当前版本的教程内容',
    'terminal': '内置终端',
    'terminalSubtitle': '在本地工作目录执行命令',
    'close': '关闭',
    'execute': '执行',
    'clear': '清屏',
    'copyTerminal': '复制终端内容',
    'loading': '正在加载…',
    'noWorkingDirectory': '没有可用的本地工作目录。',
    'localTutorialMissing': '本地教程文件不存在或无法读取。',
    'localExamplesMissing': '本地示例代码不存在或无法读取。',
    'copyExample': '复制示例代码',
    'exampleCopied': '示例代码已复制',
    'importExampleProject': '导入新建项目',
    'restoreDefault': '恢复默认',
    'saveExample': '保存示例',
    'projectImported': '示例已导入新项目',
    'sampleCode': '示例代码',
    'expectedOutput': '预期输出',
    'practice': '练习',
    'exitSearch': '退出搜索',
    'searchProjects': '搜索项目',
    'more': '更多',
    'addExistingProject': '添加现有项目',
    'newCloudProject': '新建云端项目',
    'removeMissingProjects': '移除失效项目',
    'createProject': '新建项目',
    'allProjects': '全部项目',
    'historyProjects': '历史项目',
    'favoriteProjects': '收藏项目',
    'cloudProjects': '云端项目',
    'favoriteProjectHint': '在项目卡片菜单中选择「收藏」',
    'cloudProjectHint': '登录后在更多菜单中「新建云端项目」，源码自动同步到服务器',
    'searchProjectHint': '搜索项目名称或路径',
    'allLanguages': '全部语言',
    'removeFromList': '从列表移除',
    'backupAndDelete': '正在压缩备份并删除…',
    'noMissingProjects': '没有失效项目，列表一切正常',
    'removeMissingTitle': '移除失效项目？',
    'cancel': '取消',
    'remove': '移除',
    'projectName': '项目名称',
    'projectType': '项目类型',
    'create': '创建',
    'invalidProjectName': r'名称不能包含 \\ / : * ? " < > |',
    'creatingCloudProject': '正在创建云端项目…',
    'cloudProjectCreated': '云端项目已创建，编辑内容将自动同步到服务器',
    'noMatchingProjects': '未找到匹配的项目',
    'searchProjectsHint': '换个关键词试试，支持按名称和路径搜索',
    'noProjects': '还没有项目',
    'desktopCreateProjectHint': '创建一个新项目，或添加磁盘上已有的文件夹',
    'mobileCreateProjectHint': '点击下方按钮，创建你的第一个项目',
    'importResource': '从文件导入资源',
    'importPhoto': '从相册导入图片',
    'replaceExistingResource': '资源已存在',
    'replaceResource': '覆盖',
    'replaceResourceMessage': '“{name}”已存在，是否覆盖？',
    'importFinished': '已导入 {count} 个资源',
    'importFailed': '部分资源导入失败：',
    'missingProjectPath': '项目目录不存在：',
    'deletedProject': '已删除“{name}”，备份可在应用数据 recyclebin/projects_bin 找回',
    'removeMissingMessage': '以下 {count} 个项目的目录已不存在，将仅从列表移除：\n\n{names}',
    'cloudRefreshFailed': '云端列表刷新失败：{message}',
    'refreshProjectsFailed': '暂时无法刷新项目列表，请重试',
    'examplesCount': '来自本地教程的 {count} 个示例',
    'runMode': '运行方式：',
    'limits': '限制：',
    'hint': '提示：',
    'reference': '参考：',
    'shellHintPrefix': '输入命令，回车执行（如 ',
    'terminalCollapsed': '本地终端（已收起，点击展开）',
    'terminalHeader': '本地终端（沙箱）',
    'newTerminal': '新建终端',
    'exitCode': '（退出码 {code}）',
    'runEnded': '（运行结束，退出码 {code}）',
    'unableToExecute': '无法执行：',
    'jsonTools': 'JSON 工具',
    'jsonSource': 'JSON 内容',
    'jsonFormat': '格式化 JSON',
    'jsonValidate': '校验 JSON',
    'jsonValid': 'JSON 有效',
    'jsonInvalid': 'JSON 无效',
    'jsonRootType': '根类型',
    'jsonStructure': '结构预览',
    'markdownTools': 'Markdown 编辑与预览',
    'markdownEdit': '编辑',
    'markdownPreview': '预览',
    'markdownSource': 'Markdown 内容',
    'sqlTools': 'SQL 查询',
    'sqlSource': 'SQL 语句',
    'executeQuery': '执行查询',
    'applyToEditor': '应用到编辑器',
  };

  static const _zhTw = <String, String>{
    'home': '首頁',
    'functions': '功能',
    'quickTools': '快速功能',
    'examples': '範例程式碼',
    'discussion': '討論',
    'profile': '我的',
    'tutorial': '教學',
    'tutorialSubtitle': '開啟目前版本的教學內容',
    'terminal': '內建終端機',
    'terminalSubtitle': '在本機工作目錄執行指令',
    'close': '關閉',
    'execute': '執行',
    'clear': '清除畫面',
    'copyTerminal': '複製終端內容',
    'loading': '載入中…',
    'noWorkingDirectory': '沒有可用的本機工作目錄。',
    'localTutorialMissing': '本機教學檔案不存在或無法讀取。',
    'localExamplesMissing': '本機範例程式碼不存在或無法讀取。',
    'copyExample': '複製範例程式碼',
    'exampleCopied': '範例程式碼已複製',
    'importExampleProject': '匯入並建立專案',
    'restoreDefault': '還原預設',
    'saveExample': '儲存範例',
    'projectImported': '範例已匯入新專案',
    'sampleCode': '範例程式碼',
    'expectedOutput': '預期輸出',
    'practice': '練習',
    'exitSearch': '離開搜尋',
    'searchProjects': '搜尋專案',
    'more': '更多',
    'addExistingProject': '加入現有專案',
    'newCloudProject': '建立雲端專案',
    'removeMissingProjects': '移除失效專案',
    'createProject': '建立專案',
    'allProjects': '全部專案',
    'historyProjects': '歷史專案',
    'favoriteProjects': '收藏專案',
    'cloudProjects': '雲端專案',
    'favoriteProjectHint': '在專案卡片選單中選擇「收藏」',
    'cloudProjectHint': '登入後在更多選單中「建立雲端專案」，原始碼會自動同步到伺服器',
    'searchProjectHint': '搜尋專案名稱或路徑',
    'allLanguages': '全部語言',
    'removeFromList': '從清單移除',
    'backupAndDelete': '正在壓縮備份並刪除…',
    'noMissingProjects': '沒有失效專案，清單一切正常',
    'removeMissingTitle': '移除失效專案？',
    'cancel': '取消',
    'remove': '移除',
    'projectName': '專案名稱',
    'projectType': '專案類型',
    'create': '建立',
    'invalidProjectName': r'名稱不能包含 \\ / : * ? " < > |',
    'creatingCloudProject': '正在建立雲端專案…',
    'cloudProjectCreated': '雲端專案已建立，編輯內容會自動同步到伺服器',
    'noMatchingProjects': '找不到符合的專案',
    'searchProjectsHint': '換個關鍵字試試，支援依名稱和路徑搜尋',
    'noProjects': '還沒有專案',
    'desktopCreateProjectHint': '建立新專案，或加入磁碟上已有的資料夾',
    'mobileCreateProjectHint': '點擊下方按鈕，建立你的第一個專案',
    'importResource': '從檔案匯入資源',
    'importPhoto': '從相簿匯入圖片',
    'replaceExistingResource': '資源已存在',
    'replaceResource': '覆蓋',
    'replaceResourceMessage': '「{name}」已存在，是否覆蓋？',
    'importFinished': '已匯入 {count} 個資源',
    'importFailed': '部分資源匯入失敗：',
    'missingProjectPath': '專案目錄不存在：',
    'deletedProject': '已刪除「{name}」，備份可在應用程式資料 recyclebin/projects_bin 找回',
    'removeMissingMessage': '以下 {count} 個專案的目錄已不存在，只會從清單移除：\n\n{names}',
    'cloudRefreshFailed': '雲端清單更新失敗：{message}',
    'refreshProjectsFailed': '暫時無法更新專案清單，請重試',
    'examplesCount': '來自本機教學的 {count} 個範例',
    'runMode': '執行方式：',
    'limits': '限制：',
    'hint': '提示：',
    'reference': '參考：',
    'shellHintPrefix': '輸入指令，按 Enter 執行（例如 ',
    'terminalCollapsed': '本機終端機（已收起，點擊展開）',
    'terminalHeader': '本機終端機（沙盒）',
    'newTerminal': '新增終端機',
    'exitCode': '（結束碼 {code}）',
    'runEnded': '（執行結束，結束碼 {code}）',
    'unableToExecute': '無法執行：',
    'jsonTools': 'JSON 工具',
    'jsonSource': 'JSON 內容',
    'jsonFormat': '格式化 JSON',
    'jsonValidate': '驗證 JSON',
    'jsonValid': 'JSON 有效',
    'jsonInvalid': 'JSON 無效',
    'jsonRootType': '根類型',
    'jsonStructure': '結構預覽',
    'markdownTools': 'Markdown 編輯與預覽',
    'markdownEdit': '編輯',
    'markdownPreview': '預覽',
    'markdownSource': 'Markdown 內容',
    'sqlTools': 'SQL 查詢',
    'sqlSource': 'SQL 語句',
    'executeQuery': '執行查詢',
    'applyToEditor': '套用到編輯器',
  };

  static const _en = <String, String>{
    'home': 'Home',
    'functions': 'Functions',
    'quickTools': 'Quick tools',
    'examples': 'Examples',
    'discussion': 'Discussion',
    'profile': 'Profile',
    'tutorial': 'Tutorials',
    'tutorialSubtitle': 'Open tutorials for this product',
    'terminal': 'Built-in terminal',
    'terminalSubtitle': 'Run commands in a local working directory',
    'close': 'Close',
    'execute': 'Run',
    'clear': 'Clear',
    'copyTerminal': 'Copy terminal output',
    'loading': 'Loading…',
    'noWorkingDirectory': 'No local working directory is available.',
    'localTutorialMissing': 'The local tutorial file is missing or unreadable.',
    'localExamplesMissing': 'Local examples are missing or unreadable.',
    'copyExample': 'Copy example code',
    'exampleCopied': 'Example code copied',
    'importExampleProject': 'Import into new project',
    'restoreDefault': 'Restore default',
    'saveExample': 'Save example',
    'projectImported': 'Example imported into a new project',
    'sampleCode': 'Example code',
    'expectedOutput': 'Expected output',
    'practice': 'Practice',
    'exitSearch': 'Exit search',
    'searchProjects': 'Search projects',
    'more': 'More',
    'addExistingProject': 'Add existing project',
    'newCloudProject': 'New cloud project',
    'removeMissingProjects': 'Remove missing projects',
    'createProject': 'New project',
    'allProjects': 'All projects',
    'historyProjects': 'Recent projects',
    'favoriteProjects': 'Favorite projects',
    'cloudProjects': 'Cloud projects',
    'favoriteProjectHint': 'Choose “Favorite” from a project card menu',
    'cloudProjectHint': 'Sign in, then create a cloud project from More; source syncs automatically.',
    'searchProjectHint': 'Search project name or path',
    'allLanguages': 'All languages',
    'removeFromList': 'Remove from list',
    'backupAndDelete': 'Compressing a backup and deleting…',
    'noMissingProjects': 'No missing projects. The list is healthy.',
    'removeMissingTitle': 'Remove missing projects?',
    'cancel': 'Cancel',
    'remove': 'Remove',
    'projectName': 'Project name',
    'projectType': 'Project type',
    'create': 'Create',
    'invalidProjectName': r'Name cannot contain \\ / : * ? " < > |',
    'creatingCloudProject': 'Creating cloud project…',
    'cloudProjectCreated': 'Cloud project created. Edits will sync to the server automatically.',
    'noMatchingProjects': 'No matching projects',
    'searchProjectsHint': 'Try another keyword. Names and paths are supported.',
    'noProjects': 'No projects yet',
    'desktopCreateProjectHint': 'Create a project or add a folder already on disk',
    'mobileCreateProjectHint': 'Tap the button below to create your first project',
    'importResource': 'Import resource from files',
    'importPhoto': 'Import image from photos',
    'replaceExistingResource': 'Resource already exists',
    'replaceResource': 'Replace',
    'replaceResourceMessage': '“{name}” already exists. Replace it?',
    'importFinished': 'Imported {count} resources',
    'importFailed': 'Some resources failed to import: ',
    'missingProjectPath': 'Project directory does not exist: ',
    'deletedProject': 'Deleted “{name}”. The backup is in app data at recyclebin/projects_bin.',
    'removeMissingMessage': 'The directories for these {count} projects no longer exist. Only remove them from the list:\n\n{names}',
    'cloudRefreshFailed': 'Cloud project refresh failed: {message}',
    'refreshProjectsFailed': 'Unable to refresh projects. Please try again.',
    'examplesCount': '{count} examples from the bundled tutorial',
    'runMode': 'Runtime: ',
    'limits': 'Limits: ',
    'hint': 'Hint: ',
    'reference': 'Reference: ',
    'shellHintPrefix': 'Enter a command and press Enter (for example ',
    'terminalCollapsed': 'Local terminal (collapsed, tap to expand)',
    'terminalHeader': 'Local terminal (sandbox)',
    'newTerminal': 'New terminal',
    'exitCode': '(exit code {code})',
    'runEnded': '(finished, exit code {code})',
    'unableToExecute': 'Unable to execute: ',
    'jsonTools': 'JSON tools',
    'jsonSource': 'JSON source',
    'jsonFormat': 'Format JSON',
    'jsonValidate': 'Validate JSON',
    'jsonValid': 'Valid JSON',
    'jsonInvalid': 'Invalid JSON',
    'jsonRootType': 'Root type',
    'jsonStructure': 'Structure preview',
    'markdownTools': 'Markdown editor and preview',
    'markdownEdit': 'Edit',
    'markdownPreview': 'Preview',
    'markdownSource': 'Markdown source',
    'sqlTools': 'SQL query',
    'sqlSource': 'SQL statement',
    'executeQuery': 'Run query',
    'applyToEditor': 'Apply to editor',
  };
}

class _StudioLocalizationsDelegate
    extends LocalizationsDelegate<StudioLocalizations> {
  const _StudioLocalizationsDelegate();

  @override
  bool isSupported(Locale locale) => {'zh', 'en'}.contains(locale.languageCode);

  @override
  Future<StudioLocalizations> load(Locale locale) async =>
      StudioLocalizations(StudioLocalizations.resolveLocale(locale));

  @override
  bool shouldReload(_StudioLocalizationsDelegate old) => false;
}
