import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:path/path.dart' as p;

import '../editor/editor_fonts.dart';
import '../editor/editor_page.dart';
import '../i18n/studio_localizations.dart';
import '../models/project.dart';
import '../models/tutorial.dart';
import '../services/code_import_service.dart';
import '../services/file_service.dart';
import '../services/task_activity_service.dart';
import '../store/auth_store.dart';
import '../store/project_store.dart';
import '../store/settings_store.dart';

class CodeSnippetBlock extends StatelessWidget {
  const CodeSnippetBlock({
    super.key,
    required this.example,
    this.controller,
    this.store,
    this.auth,
    this.settings,
    this.importer = const CodeImportService(),
    this.actions = const [],
  });

  final ExampleCode example;
  final TextEditingController? controller;
  final ProjectStore? store;
  final AuthStore? auth;
  final SettingsStore? settings;
  final CodeImportService importer;
  final List<Widget> actions;

  String get _code => controller?.text ?? example.code;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = StudioLocalizations.of(context);
    final codeStyle = theme.textTheme.bodyMedium?.copyWith(
      fontFamily: EditorFonts.bundledFamily, height: 1.5, letterSpacing: 0,
    );
    return DecoratedBox(
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerLow,
        border: Border.all(color: theme.colorScheme.outlineVariant),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 4, 4, 0),
            child: Row(children: [
              Expanded(child: Text(CodeImportService.templateFor(example.type).label,
                  style: theme.textTheme.labelLarge)),
              ...actions,
              IconButton(
                tooltip: l10n.copyExample,
                icon: const Icon(Icons.copy_outlined),
                onPressed: () async {
                  await Clipboard.setData(ClipboardData(text: _code));
                  if (context.mounted) {
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(content: Text(l10n.exampleCopied)),
                    );
                  }
                },
              ),
            ]),
          ),
          const Divider(height: 1),
          if (controller != null)
            TextField(
              controller: controller, minLines: 4, maxLines: 16, style: codeStyle,
              decoration: const InputDecoration(
                border: InputBorder.none, enabledBorder: InputBorder.none,
                focusedBorder: InputBorder.none, contentPadding: EdgeInsets.all(12),
              ),
            )
          else
            Padding(
              padding: const EdgeInsets.all(12),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxHeight: 360),
                child: SingleChildScrollView(
                  child: SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    child: SelectableText(_code, style: codeStyle),
                  ),
                ),
              ),
            ),
          Padding(
            padding: const EdgeInsets.all(12),
            child: _CodeImportActions(
              example: example, code: () => _code, store: store, auth: auth,
              settings: settings, importer: importer,
            ),
          ),
        ],
      ),
    );
  }
}

class _CodeImportActions extends StatefulWidget {
  const _CodeImportActions({required this.example, required this.code,
    required this.store, required this.auth, required this.settings, required this.importer});
  final ExampleCode example;
  final String Function() code;
  final ProjectStore? store;
  final AuthStore? auth;
  final SettingsStore? settings;
  final CodeImportService importer;
  @override
  State<_CodeImportActions> createState() => _CodeImportActionsState();
}

class _CodeImportActionsState extends State<_CodeImportActions> {
  bool _busy = false;

  Future<void> _import(bool intoProject) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      final imported = await showDialog<ImportedCode>(
        context: context, barrierDismissible: false,
        builder: (_) => _CodeImportDialog(
          example: widget.example.copyWith(code: widget.code()),
          store: widget.store!, intoProject: intoProject, importer: widget.importer,
        ),
      );
      if (imported == null || !mounted) return;
      if (imported.registered) {
        widget.store!.touch(imported.project);
        if (imported.created) TaskActivityService.report(widget.auth!, 'create_project');
        TaskActivityService.report(widget.auth!, 'open_project');
      }
      await Navigator.of(context).push(MaterialPageRoute<void>(
        builder: (_) => EditorPage(
          project: imported.project, auth: widget.auth!, store: widget.store!,
          settings: widget.settings!, initialOpenPath: imported.filePath,
        ),
      ));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = StudioLocalizations.of(context);
    final enabled = !_busy && widget.store != null && widget.auth != null && widget.settings != null;
    return Wrap(spacing: 8, runSpacing: 8, children: [
      FilledButton.tonalIcon(
        onPressed: enabled ? () => _import(false) : null,
        icon: const Icon(Icons.edit_note), label: Text(l10n.importToEditor),
      ),
      OutlinedButton.icon(
        onPressed: enabled ? () => _import(true) : null,
        icon: const Icon(Icons.drive_file_move_outlined), label: Text(l10n.importToProject),
      ),
    ]);
  }
}

class _CodeImportDialog extends StatefulWidget {
  const _CodeImportDialog({required this.example, required this.store,
    required this.intoProject, required this.importer});
  final ExampleCode example;
  final ProjectStore store;
  final bool intoProject;
  final CodeImportService importer;
  @override
  State<_CodeImportDialog> createState() => _CodeImportDialogState();
}

class _CodeImportDialogState extends State<_CodeImportDialog> {
  final _form = GlobalKey<FormState>();
  late final TextEditingController _fileName;
  late final TextEditingController _projectName;
  late final List<Project> _projects;
  String _projectId = '';
  bool _saving = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _fileName = TextEditingController(text: CodeImportService.defaultFileName(widget.example.type));
    _fileName.selection = TextSelection(baseOffset: 0,
      extentOffset: p.basenameWithoutExtension(_fileName.text).length);
    _projectName = TextEditingController(text: widget.example.title
        .replaceAll(RegExp(r'[\\/:*?"<>|\x00-\x1f]'), ' ').trim());
    _projects = widget.store.projects.where((project) => !project.isCloud).toList();
    final last = widget.store.lastBrowsedProjectId;
    if (_projects.any((project) => project.id == last)) _projectId = last!;
  }

  @override
  void dispose() { _fileName.dispose(); _projectName.dispose(); super.dispose(); }

  Future<void> _submit() async {
    if (_saving || !_form.currentState!.validate()) return;
    setState(() { _saving = true; _error = null; });
    try {
      final result = widget.intoProject
          ? await widget.importer.importProject(
              store: widget.store, example: widget.example, fileName: _fileName.text,
              projectName: _projectName.text,
              project: _projectId.isEmpty ? null :
                  _projects.firstWhere((project) => project.id == _projectId),
            )
          : await widget.importer.openInEditor(example: widget.example, fileName: _fileName.text);
      if (mounted) Navigator.of(context).pop(result);
    } catch (error) {
      if (!mounted) return;
      final l10n = StudioLocalizations.of(context);
      setState(() {
        _saving = false;
        _error = switch (error) {
          CodeImportException(failure: CodeImportFailure.invalidName) => l10n.invalidFileName,
          CodeImportException(failure: CodeImportFailure.fileExists) => l10n.importFileExists,
          CodeImportException(failure: CodeImportFailure.projectMissing) => l10n.importProjectMissing,
          CodeImportException(failure: CodeImportFailure.noStorage) => l10n.importStorageMissing,
          FileSystemException(:final message) => '${l10n.importFailed}: $message',
          _ => '${l10n.importFailed}: $error',
        };
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = StudioLocalizations.of(context);
    return PopScope(canPop: !_saving, child: AlertDialog(
      scrollable: true,
      title: Text(widget.intoProject ? l10n.importToProject : l10n.importToEditor),
      content: SizedBox(width: 400, child: Form(key: _form, child: Column(
        mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (widget.intoProject) ...[
            DropdownButtonFormField<String>(
              initialValue: _projectId, isExpanded: true,
              decoration: InputDecoration(labelText: l10n.importTargetProject),
              items: [
                DropdownMenuItem(value: '', child: Text(l10n.createProject)),
                for (final project in _projects) DropdownMenuItem(
                  value: project.id, child: Text(project.name, overflow: TextOverflow.ellipsis)),
              ],
              onChanged: _saving ? null : (value) => setState(() {
                _projectId = value ?? ''; _error = null;
              }),
            ),
            if (_projectId.isEmpty) ...[
              const SizedBox(height: 16),
              TextFormField(controller: _projectName, enabled: !_saving,
                decoration: InputDecoration(labelText: l10n.projectName),
                validator: (value) => FileService.isValidEntryName(value ?? '')
                    ? null : l10n.invalidProjectName),
            ],
            const SizedBox(height: 16),
          ],
          TextFormField(controller: _fileName, autofocus: true, enabled: !_saving,
            decoration: InputDecoration(labelText: l10n.importFileName),
            onFieldSubmitted: (_) => _submit(),
            validator: (value) {
              try { CodeImportService.normalizeFileName(value ?? '', widget.example.type); return null; }
              on CodeImportException { return l10n.invalidFileName; }
            }),
          if (_error != null) ...[
            const SizedBox(height: 12),
            Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
          ],
        ],
      ))),
      actions: [
        TextButton(onPressed: _saving ? null : () => Navigator.of(context).pop(), child: Text(l10n.cancel)),
        FilledButton.icon(onPressed: _saving ? null : _submit,
          icon: _saving ? const SizedBox(width: 18, height: 18,
            child: CircularProgressIndicator(strokeWidth: 2)) : const Icon(Icons.file_download_outlined),
          label: Text(l10n.importCode)),
      ],
    ));
  }
}
