import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../editor/editor_fonts.dart';

import '../content/asset_content_repository.dart';
import '../content/content_repository.dart';
import '../content/local_content_adapter.dart';
import '../i18n/studio_localizations.dart';
import '../models/tutorial.dart';
import '../services/studio_profile.dart';
import '../services/task_activity_service.dart';
import '../store/auth_store.dart';
import '../store/project_store.dart';
import '../services/example_code_store.dart';

/// 离线语言 App 的第二页：从随包 JSON 加载入门教程。
class LocalTutorialsTab extends StatefulWidget {
  const LocalTutorialsTab({super.key, required this.language, this.repository});

  final String language;
  final ContentRepository? repository;

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
          return _TutorialList(tutorial: tutorial);
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
    this.examples,
  });

  final String language;
  final ContentRepository? repository;
  final ProjectStore? store;
  final AuthStore? auth;
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
        oldWidget.repository != widget.repository) {
      _repository = widget.repository ?? AssetContentRepository();
      _examples = _loadExamples();
    }
  }

  Future<List<ExampleCode>> _loadExamples() => LocalContentAdapter.loadExamples(
    repository: _repository,
    language: widget.language,
    productKey: StudioProfile.current?.productKey,
  );

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
            examples: widget.examples,
          );
        },
      ),
    );
  }
}

class _TutorialList extends StatelessWidget {
  const _TutorialList({required this.tutorial});

  final Tutorial tutorial;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 32),
      children: [
        _RuntimeSummary(tutorial: tutorial),
        const SizedBox(height: 12),
        for (final chapter in tutorial.chapters) ...[
          Padding(
            padding: const EdgeInsets.fromLTRB(4, 12, 4, 4),
            child: Text(chapter.title, style: theme.textTheme.titleMedium),
          ),
          for (final lesson in chapter.lessons)
            Card(
              child: ListTile(
                leading: const Icon(Icons.menu_book_outlined),
                title: Text(lesson.title),
                subtitle: Text(lesson.summary),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (_) => _LessonPage(lesson: lesson),
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
    this.examples,
  });

  final List<ExampleCode> items;
  final ProjectStore? store;
  final AuthStore? auth;
  final ExampleCodeStore? examples;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = StudioLocalizations.of(context);
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 32),
      children: [
        Text(
          l10n.examplesCount(items.length),
          style: theme.textTheme.bodyMedium?.copyWith(
            color: theme.colorScheme.onSurfaceVariant,
          ),
        ),
        const SizedBox(height: 8),
        for (final example in items)
          _ExampleCodeCard(
            example: example,
            onTap: () => Navigator.of(context).push(
              MaterialPageRoute(
                builder: (_) => ExampleDetailPage(
                  example: example,
                  store: store,
                  auth: auth,
                  examples: examples,
                ),
              ),
            ),
          ),
      ],
    );
  }
}

class _ExampleCodeCard extends StatelessWidget {
  const _ExampleCodeCard({required this.example, this.onTap});

  final ExampleCode example;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = StudioLocalizations.of(context);
    return Card(
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(8),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 12, 14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      example.title,
                      style: theme.textTheme.titleSmall,
                    ),
                  ),
                  Text(example.type),
                  IconButton(
                    tooltip: l10n.copyExample,
                    icon: const Icon(Icons.copy_outlined),
                    onPressed: () async {
                      await Clipboard.setData(
                        ClipboardData(text: example.code),
                      );
                      if (!context.mounted) return;
                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(content: Text(l10n.exampleCopied)),
                      );
                    },
                  ),
                ],
              ),
              const SizedBox(height: 8),
              DecoratedBox(
                decoration: BoxDecoration(
                  color: theme.colorScheme.surfaceContainerHighest,
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    child: SelectableText(
                      example.code,
                      style: theme.textTheme.bodyMedium?.copyWith(
                        fontFamily: EditorFonts.bundledFamily,
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class ExampleDetailPage extends StatefulWidget {
  const ExampleDetailPage({
    super.key,
    required this.example,
    this.store,
    this.auth,
    this.examples,
  });

  final ExampleCode example;
  final ProjectStore? store;
  final AuthStore? auth;
  final ExampleCodeStore? examples;

  @override
  State<ExampleDetailPage> createState() => _ExampleDetailPageState();
}

class _ExampleDetailPageState extends State<ExampleDetailPage> {
  late final TextEditingController _code = TextEditingController(
    text: widget.example.code,
  );

  @override
  void dispose() {
    _code.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = StudioLocalizations.of(context);
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.example.title),
        actions: [
          IconButton(
            tooltip: l10n.copyExample,
            icon: const Icon(Icons.copy_outlined),
            onPressed: () => Clipboard.setData(ClipboardData(text: _code.text)),
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 32),
        children: [
          Text(widget.example.type),
          const SizedBox(height: 8),
          Text(widget.example.summary),
          const SizedBox(height: 16),
          TextField(
            controller: _code,
            minLines: 12,
            maxLines: 24,
            expands: false,
            style: const TextStyle(fontFamily: EditorFonts.bundledFamily),
            decoration: const InputDecoration(border: OutlineInputBorder()),
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
              FilledButton.icon(
                onPressed: widget.store == null ? null : _importProject,
                icon: const Icon(Icons.create_new_folder_outlined),
                label: Text(l10n.importExampleProject),
              ),
              OutlinedButton.icon(
                onPressed: _reset,
                icon: const Icon(Icons.restore),
                label: Text(l10n.restoreDefault),
              ),
              OutlinedButton.icon(
                onPressed: widget.examples == null ? null : _save,
                icon: const Icon(Icons.save_outlined),
                label: Text(l10n.saveExample),
              ),
            ],
          ),
        ],
      ),
    );
  }

  void _reset() => setState(() => _code.text = widget.example.code);

  Future<void> _save() async {
    await widget.examples!.upsert(widget.example.copyWith(code: _code.text));
  }

  Future<void> _importProject() async {
    final result = await widget.store!.createProjectFromExample(
      name: widget.example.title,
      example: widget.example.copyWith(code: _code.text),
    );
    if (result.error == null && widget.auth != null) {
      TaskActivityService.report(widget.auth!, 'create_project');
    }
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          result.error ?? StudioLocalizations.of(context).projectImported,
        ),
      ),
    );
  }
}

class _RuntimeSummary extends StatelessWidget {
  const _RuntimeSummary({required this.tutorial});

  final Tutorial tutorial;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = StudioLocalizations.of(context);
    final runtime = tutorial.runtime;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(tutorial.displayName, style: theme.textTheme.titleLarge),
            const SizedBox(height: 6),
            Text(l10n.runMode(runtime.engine)),
            if (runtime.limits case final limits? when limits.isNotEmpty) ...[
              const SizedBox(height: 4),
              Text(l10n.limits(limits)),
            ],
          ],
        ),
      ),
    );
  }
}

class _LessonPage extends StatelessWidget {
  const _LessonPage({required this.lesson});

  final TutorialLesson lesson;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = StudioLocalizations.of(context);
    return Scaffold(
      appBar: AppBar(title: Text(lesson.title)),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 32),
        children: [
          Text(lesson.summary, style: theme.textTheme.titleMedium),
          const SizedBox(height: 12),
          Text(lesson.explain),
          const SizedBox(height: 20),
          Text(l10n.sampleCode, style: theme.textTheme.titleMedium),
          const SizedBox(height: 8),
          _ExampleCodeCard(
            example: ExampleCode(
              id: lesson.id,
              type: lesson.type,
              title: lesson.title,
              summary: lesson.summary,
              code: lesson.code,
              output: lesson.output,
              sourceLessonId: lesson.id,
            ),
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
