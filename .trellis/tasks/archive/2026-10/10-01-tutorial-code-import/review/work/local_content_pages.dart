import 'package:flutter/material.dart';

import '../content/asset_content_repository.dart';
import '../content/content_repository.dart';
import '../content/local_content_adapter.dart';
import '../i18n/studio_localizations.dart';
import '../models/tutorial.dart';
import '../services/studio_profile.dart';
import '../store/auth_store.dart';
import '../store/project_store.dart';
import '../store/settings_store.dart';
import '../services/example_code_store.dart';
import '../widgets/code_snippet.dart';

/// 离线语言 App 的第二页：从随包 JSON 加载入门教程。
class LocalTutorialsTab extends StatefulWidget {
  const LocalTutorialsTab({
    super.key,
    required this.language,
    this.repository,
    this.store,
    this.auth,
    this.settings,
  });

  final String language;
  final ContentRepository? repository;
  final ProjectStore? store;
  final AuthStore? auth;
  final SettingsStore? settings;

  @override
  State<LocalTutorialsTab> createState() => _LocalTutorialsTabState();
}

class _LocalTutorialsTabState extends State<LocalTutorialsTab> {
  late ContentRepository _repository;
  late Future<Tutorial?> _tutorial;

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? AssetContentRepository();
    _tutorial = _loadTutorial();
  }

  @override
  void didUpdateWidget(covariant LocalTutorialsTab oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.language != widget.language ||
        oldWidget.repository != widget.repository) {
      _repository = widget.repository ?? AssetContentRepository();
      _tutorial = _loadTutorial();
    }
  }

  Future<Tutorial?> _loadTutorial() => LocalContentAdapter.loadTutorial(
    repository: _repository,
    language: widget.language,
    displayName: _displayName(widget.language),
    productKey: StudioProfile.current?.productKey,
  );

  @override
  Widget build(BuildContext context) {
    final l10n = StudioLocalizations.of(context);
    return Scaffold(
      appBar: AppBar(
        title: Text('${_displayName(widget.language)} ${l10n.tutorial}'),
      ),
      body: FutureBuilder<Tutorial?>(
        future: _tutorial,
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          final tutorial = snapshot.data;
          if (tutorial == null) {
            return _LocalContentError(message: l10n.localTutorialMissing);
          }
          return _TutorialList(
            tutorial: tutorial,
            store: widget.store,
            auth: widget.auth,
            settings: widget.settings,
          );
        },
      ),
    );
  }
}

/// 离线语言 App 的第三页：展示教程 JSON 中的可复制示例代码。
class ExampleCodeTab extends StatefulWidget {
  const ExampleCodeTab({
    super.key,
    required this.language,
    this.repository,
    this.store,
    this.auth,
    this.settings,
    this.examples,
  });

  final String language;
  final ContentRepository? repository;
  final ProjectStore? store;
  final AuthStore? auth;
  final SettingsStore? settings;
  final ExampleCodeStore? examples;

  @override
  State<ExampleCodeTab> createState() => _ExampleCodeTabState();
}

class _ExampleCodeTabState extends State<ExampleCodeTab> {
  late ContentRepository _repository;
  late Future<List<ExampleCode>> _examples;

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? AssetContentRepository();
    _examples = _loadExamples();
  }

  @override
  void didUpdateWidget(covariant ExampleCodeTab oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.language != widget.language ||
        oldWidget.repository != widget.repository ||
        oldWidget.examples != widget.examples) {
      _repository = widget.repository ?? AssetContentRepository();
      _examples = _loadExamples();
    }
  }

  Future<List<ExampleCode>> _loadExamples() async {
    final store = widget.examples;
    final bundled = await LocalContentAdapter.loadExamples(
      repository: _repository,
      language: widget.language,
      productKey: StudioProfile.current?.productKey,
    );
    if (mounted) await store?.load(defaults: bundled);
    return bundled;
  }

  @override
  Widget build(BuildContext context) {
    final l10n = StudioLocalizations.of(context);
    return Scaffold(
      appBar: AppBar(
        title: Text('${_displayName(widget.language)} ${l10n.examples}'),
      ),
      body: FutureBuilder<List<ExampleCode>>(
        future: _examples,
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          final examples = snapshot.data;
          if (examples == null || examples.isEmpty) {
            return _LocalContentError(message: l10n.localExamplesMissing);
          }
          return _ExampleCodeList(
            items: examples,
            store: widget.store,
            auth: widget.auth,
            settings: widget.settings,
            examples: widget.examples,
          );
        },
      ),
    );
  }
}

class _TutorialList extends StatelessWidget {
  const _TutorialList({
    required this.tutorial,
    this.store,
    this.auth,
    this.settings,
  });

  final Tutorial tutorial;
  final ProjectStore? store;
  final AuthStore? auth;
  final SettingsStore? settings;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return _ContentList(
      padding: const EdgeInsets.only(top: 8, bottom: 32),
      children: [
        for (final chapter in tutorial.chapters) ...[
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
            child: Text(
              chapter.title,
              style: theme.textTheme.titleSmall?.copyWith(
                color: theme.colorScheme.primary,
              ),
            ),
          ),
          for (final lesson in chapter.lessons)
            ListTile(
              contentPadding: const EdgeInsets.symmetric(horizontal: 16),
              leading: const Icon(Icons.menu_book_outlined),
              title: Text(
                lesson.title,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
              subtitle: Text(
                lesson.summary,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
              trailing: const Icon(Icons.chevron_right),
              onTap: () => Navigator.of(context).push(
                MaterialPageRoute(
                  builder: (_) => _LessonPage(
                    lesson: lesson,
                    store: store,
                    auth: auth,
                    settings: settings,
                  ),
                ),
              ),
            ),
        ],
      ],
    );
  }
}

class _ExampleCodeList extends StatelessWidget {
  const _ExampleCodeList({
    required this.items,
    this.store,
    this.auth,
    this.settings,
    this.examples,
  });

  final List<ExampleCode> items;
  final ProjectStore? store;
  final AuthStore? auth;
  final SettingsStore? settings;
  final ExampleCodeStore? examples;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = StudioLocalizations.of(context);
    return _ContentList(
      padding: const EdgeInsets.only(top: 8, bottom: 32),
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
          child: Text(
            l10n.examplesCount(items.length),
            style: theme.textTheme.bodyMedium?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
        ),
        for (final example in items)
          ListTile(
            contentPadding: const EdgeInsets.symmetric(horizontal: 16),
            leading: const Icon(Icons.code_outlined),
            title: Text(
              example.title,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
            subtitle: Text(
              example.summary,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => Navigator.of(context).push(
              MaterialPageRoute(
                builder: (_) => ExampleDetailPage(
                  example: example,
                  store: store,
                  auth: auth,
                  settings: settings,
                  examples: examples,
                ),
              ),
            ),
          ),
      ],
    );
  }
}

class ExampleDetailPage extends StatefulWidget {
  const ExampleDetailPage({
    super.key,
    required this.example,
    this.store,
    this.auth,
    this.settings,
    this.examples,
  });

  final ExampleCode example;
  final ProjectStore? store;
  final AuthStore? auth;
  final SettingsStore? settings;
  final ExampleCodeStore? examples;

  @override
  State<ExampleDetailPage> createState() => _ExampleDetailPageState();
}

class _ExampleDetailPageState extends State<ExampleDetailPage> {
  late final TextEditingController _code;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    final saved = widget.examples?.items.firstWhere(
      (example) => example.id == widget.example.id,
      orElse: () => widget.example,
    );
    _code = TextEditingController(text: saved?.code ?? widget.example.code);
  }

  @override
  void dispose() {
    _code.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = StudioLocalizations.of(context);
    return Scaffold(
      appBar: AppBar(title: Text(widget.example.title)),
      body: _ContentList(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 32),
        children: [
          Text(widget.example.summary),
          const SizedBox(height: 16),
          CodeSnippet(
            example: widget.example,
            controller: _code,
            store: widget.store,
            auth: widget.auth,
            settings: widget.settings,
          ),
          const SizedBox(height: 16),
          Text(l10n.expectedOutput),
          const SizedBox(height: 6),
          SelectableText(widget.example.output),
          const SizedBox(height: 16),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              IconButton.filledTonal(
                tooltip: l10n.restoreDefault,
                onPressed: _saving ? null : _reset,
                icon: const Icon(Icons.restore),
              ),
              IconButton.filledTonal(
                tooltip: l10n.saveExample,
                onPressed: widget.examples == null || _saving ? null : _save,
                icon: _saving
                    ? const SizedBox.square(
                        dimension: 20,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.save_outlined),
              ),
            ],
          ),
        ],
      ),
    );
  }

  void _reset() => setState(() => _code.text = widget.example.code);

  Future<void> _save() async {
    final store = widget.examples;
    if (_saving || store == null) return;
    final example = widget.example.copyWith(code: _code.text);
    setState(() => _saving = true);
    try {
      await store.upsert(example);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(StudioLocalizations.of(context).exampleSaved)),
      );
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(error.toString())));
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }
}

class _LessonPage extends StatelessWidget {
  const _LessonPage({
    required this.lesson,
    this.store,
    this.auth,
    this.settings,
  });

  final TutorialLesson lesson;
  final ProjectStore? store;
  final AuthStore? auth;
  final SettingsStore? settings;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = StudioLocalizations.of(context);
    return Scaffold(
      appBar: AppBar(title: Text(lesson.title)),
      body: _ContentList(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 32),
        children: [
          Text(lesson.summary, style: theme.textTheme.titleMedium),
          const SizedBox(height: 12),
          Text(lesson.explain),
          const SizedBox(height: 20),
          Text(l10n.sampleCode, style: theme.textTheme.titleMedium),
          const SizedBox(height: 8),
          CodeSnippet(
            example: ExampleCode(
              id: lesson.id,
              type: lesson.type,
              title: lesson.title,
              summary: lesson.summary,
              code: lesson.code,
              output: lesson.output,
              sourceLessonId: lesson.id,
            ),
            store: store,
            auth: auth,
            settings: settings,
          ),
          const SizedBox(height: 16),
          Text(l10n.expectedOutput, style: theme.textTheme.titleMedium),
          const SizedBox(height: 8),
          SelectableText(lesson.output),
          if (lesson.tasks.isNotEmpty) ...[
            const SizedBox(height: 20),
            Text(l10n.practice, style: theme.textTheme.titleMedium),
            for (final task in lesson.tasks)
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.task_alt_outlined),
                title: Text(task.prompt),
                subtitle: Text(
                  '${l10n.hint(task.hint)}\n${l10n.reference(task.answer)}',
                ),
              ),
          ],
        ],
      ),
    );
  }
}

class _ContentList extends StatelessWidget {
  const _ContentList({required this.padding, required this.children});

  final EdgeInsetsGeometry padding;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) => Align(
    alignment: Alignment.topCenter,
    child: ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 960),
      child: ListView(padding: padding, children: children),
    ),
  );
}

class _LocalContentError extends StatelessWidget {
  const _LocalContentError({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) => Center(
    child: Padding(
      padding: const EdgeInsets.all(24),
      child: Text(message, textAlign: TextAlign.center),
    ),
  );
}

String _displayName(String language) {
  final profile = StudioProfile.current;
  if (profile?.isOffline == true) {
    return profile!.appTitle;
  }
  final product = StudioProductCatalog.forLanguage(language);
  return product == StudioProductCatalog.qfliStudio
      ? language.toUpperCase()
      : product;
}
