import 'package:flutter/material.dart';
import 'package:path/path.dart' as p;
import 'package:qfli_studio_core/models/project.dart';
import 'package:qfli_studio_core/pages/tools_grid.dart';
import 'package:qfli_studio_core/store/project_store.dart';
import 'package:qfli_studio_core/widgets/tool_widgets.dart';

import 'rust_tool_utilities.dart';

/// The tools tab body; the shared application shell owns its Scaffold.
class RustToolsTab extends StatefulWidget {
  const RustToolsTab({
    super.key,
    required this.store,
    required this.onOpenTerminal,
    this.inspectorFactory,
  });

  final ProjectStore store;
  final VoidCallback onOpenTerminal;
  final RustProjectInspector Function()? inspectorFactory;

  @override
  State<RustToolsTab> createState() => _RustToolsTabState();
}

class _RustToolsTabState extends State<RustToolsTab>
    with AutomaticKeepAliveClientMixin {
  final _integer = TextEditingController(text: '0xff_u8');
  final _operand = TextEditingController(text: '1');
  final _string = TextEditingController(text: 'Hello, Rust 🦀');
  String _type = 'u8';
  int _pointerWidth = 64;
  String _operation = '&';
  RustStringInput _stringMode = RustStringInput.text;
  String? _projectId;
  bool _userSelectedProject = false;
  RustProjectInspector? _inspector;
  RustProjectInspection? _inspection;
  bool _inspecting = false;
  int _inspectionGeneration = 0;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    widget.store.addListener(_projectsChanged);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _projectsChanged();
    });
  }

  @override
  void didUpdateWidget(RustToolsTab oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.store != widget.store) {
      oldWidget.store.removeListener(_projectsChanged);
      widget.store.addListener(_projectsChanged);
      _projectId = null;
      _userSelectedProject = false;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _projectsChanged();
      });
    }
  }

  @override
  void dispose() {
    widget.store.removeListener(_projectsChanged);
    _inspector?.cancel();
    _integer.dispose();
    _operand.dispose();
    _string.dispose();
    super.dispose();
  }

  List<Project> get _projects => widget.store.projects
      .where((project) => !project.isCloud)
      .toList(growable: false);

  void _projectsChanged() {
    final projects = _projects;
    final ids = projects.map((project) => project.id).toSet();
    final remembered = widget.store.lastBrowsedProjectId;
    final next = !_userSelectedProject && ids.contains(remembered)
        ? remembered
        : ids.contains(_projectId)
        ? _projectId
        : projects.firstOrNull?.id;
    if (next != _projectId) {
      _projectId = next;
      _inspectProject();
    } else {
      setState(() {});
    }
  }

  Future<void> _inspectProject() async {
    final generation = ++_inspectionGeneration;
    _inspector?.cancel();
    final project = widget.store.projectById(_projectId);
    if (project == null || project.isCloud) {
      setState(() {
        _inspection = null;
        _inspecting = false;
      });
      return;
    }
    final inspector = widget.inspectorFactory?.call() ?? RustProjectInspector();
    _inspector = inspector;
    setState(() {
      _inspection = null;
      _inspecting = true;
    });
    final result = await inspector.inspect(project.path);
    if (!mounted || generation != _inspectionGeneration) return;
    setState(() {
      _inspection = result;
      _inspecting = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final remembered = widget.store.lastBrowsedProjectId;
    if (!_userSelectedProject &&
        remembered != _projectId &&
        _projects.any((project) => project.id == remembered)) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _projectsChanged();
      });
    }
    return LayoutBuilder(
      builder: (context, constraints) {
        final horizontal = ToolsTheme.horizontalPadding(constraints.maxWidth);
        Widget section(Widget child) => SliverPadding(
          padding: EdgeInsets.fromLTRB(horizontal, 20, horizontal, 0),
          sliver: SliverToBoxAdapter(
            child: Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(
                  maxWidth: ToolsTheme.contentMaxWidth,
                ),
                child: child,
              ),
            ),
          ),
        );
        return CustomScrollView(
          key: const PageStorageKey<String>('rust-tools-scroll'),
          slivers: [
            section(
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const ToolsSectionHeading(
                    icon: Icons.code,
                    title: 'Rust 离线工具',
                    subtitle: '整数、字符串与本地项目检查，直接在此页使用。',
                  ),
                  const SizedBox(height: 12),
                  OutlinedButton.icon(
                    key: const ValueKey('rust-tools-terminal'),
                    onPressed: widget.onOpenTerminal,
                    icon: const Icon(Icons.terminal),
                    label: const Text('打开终端'),
                  ),
                ],
              ),
            ),
            section(_integerSection()),
            section(_stringSection()),
            section(_projectSection()),
            section(
              const ToolsSectionHeading(
                icon: Icons.build_outlined,
                title: '通用离线工具',
              ),
            ),
            SliverPadding(
              padding: EdgeInsets.fromLTRB(horizontal, 12, horizontal, 32),
              sliver: ToolsGridSliver(tools: commonTools),
            ),
          ],
        );
      },
    );
  }

  Widget _integerSection() {
    RustIntegerLiteral? literal;
    RustIntegerView? view;
    String? error;
    String? suffixError;
    BigInt? bitResult;
    String? bitError;
    try {
      literal = parseRustInteger(_integer.text);
      view = RustIntegerView(
        value: literal.value,
        type: _type,
        pointerWidth: _pointerWidth,
      );
      if (literal.suffix case final suffix?) {
        final suffixView = RustIntegerView(
          value: literal.value,
          type: suffix,
          pointerWidth: _pointerWidth,
        );
        if (!suffixView.fits) {
          suffixError = '输入值超出字面量后缀 $suffix 的范围，Rust 会报告溢出。';
        }
      }
      try {
        bitResult = rustBitOperation(
          left: view,
          operation: _operation,
          right: _operation == '!'
              ? null
              : parseRustInteger(_operand.text).value,
        );
      } on FormatException catch (exception) {
        bitError = exception.message.toString();
      }
    } on FormatException catch (exception) {
      error = exception.message.toString();
    }
    return _ToolSection(
      icon: Icons.calculate_outlined,
      title: '整数、类型边界与位运算',
      subtitle: '精确处理 i128/u128；负数按一元负号解析。位模式及运算先按所选类型转换。',
      children: [
        TextField(
          key: const ValueKey('rust-integer-input'),
          controller: _integer,
          onChanged: (_) => setState(() {}),
          decoration: const InputDecoration(
            labelText: 'Rust 整数',
            hintText: '-128i8 / 0xff_u8 / 0b1010 / 1_000',
            border: OutlineInputBorder(),
          ),
        ),
        const SizedBox(height: 12),
        _ResponsiveFields(
          children: [
            DropdownButtonFormField<String>(
              key: const ValueKey('rust-integer-type'),
              initialValue: _type,
              isExpanded: true,
              decoration: const InputDecoration(
                labelText: '查看 / 转换类型',
                border: OutlineInputBorder(),
              ),
              items: [
                for (final type in rustIntegerTypes)
                  DropdownMenuItem(value: type, child: Text(type)),
              ],
              onChanged: (type) {
                if (type != null) setState(() => _type = type);
              },
            ),
            DropdownButtonFormField<int>(
              key: const ValueKey('rust-pointer-width'),
              initialValue: _pointerWidth,
              isExpanded: true,
              decoration: const InputDecoration(
                labelText: '指针位宽假设',
                border: OutlineInputBorder(),
              ),
              items: const [
                DropdownMenuItem(value: 32, child: Text('32 位')),
                DropdownMenuItem(value: 64, child: Text('64 位')),
              ],
              onChanged: (bits) {
                if (bits != null) setState(() => _pointerWidth = bits);
              },
            ),
          ],
        ),
        ToolError(error),
        ToolError(suffixError),
        if (literal != null && view != null) ...[
          const SizedBox(height: 8),
          _Value(label: '十进制', value: '${literal.value}'),
          _Value(
            label: '输入进制 / 后缀',
            value:
                '${literal.radix} / ${literal.suffix ?? '无（类型由 Rust 上下文推断）'}',
          ),
          _Value(label: '十六进制', value: _radix(literal.value, 16, '0x')),
          _Value(label: '八进制', value: _radix(literal.value, 8, '0o')),
          _Value(label: '二进制', value: _radix(literal.value, 2, '0b')),
          _Value(
            label: '$_type 范围',
            value: '${view.minimum} … ${view.maximum}',
          ),
          Text(
            view.fits
                ? '输入值在 $_type 范围内。'
                : '输入值超出 $_type 范围；下方展示显式 as 转换后的截断结果。',
          ),
          _Value(label: 'as $_type', value: '${view.wrapped}'),
          _Value(label: '${view.bits} 位补码', value: _groupBits(view.binary)),
          _Value(label: '位模式十六进制', value: view.hex),
          _Value(label: 'to_le_bytes()', value: view.littleEndian),
          _Value(label: 'to_be_bytes()', value: view.bigEndian),
        ],
        const SizedBox(height: 16),
        _ResponsiveFields(
          children: [
            DropdownButtonFormField<String>(
              key: const ValueKey('rust-bit-operation'),
              initialValue: _operation,
              isExpanded: true,
              decoration: const InputDecoration(
                labelText: '位运算',
                border: OutlineInputBorder(),
              ),
              items: [
                for (final operation in rustBitOperations)
                  DropdownMenuItem(value: operation, child: Text(operation)),
              ],
              onChanged: (operation) {
                if (operation != null) setState(() => _operation = operation);
              },
            ),
            TextField(
              key: const ValueKey('rust-bit-operand'),
              controller: _operand,
              enabled: _operation != '!',
              onChanged: (_) => setState(() {}),
              decoration: InputDecoration(
                labelText: _operation == '<<' || _operation == '>>'
                    ? '移位数'
                    : '右操作数',
                border: const OutlineInputBorder(),
              ),
            ),
          ],
        ),
        ToolError(bitError),
        if (bitResult != null)
          _Value(label: '位运算结果 ($_type)', value: '$bitResult'),
      ],
    );
  }

  Widget _stringSection() {
    RustStringView? view;
    String? error;
    try {
      view = inspectRustString(_string.text, _stringMode);
    } on FormatException catch (exception) {
      error = exception.message.toString();
    }
    return _ToolSection(
      icon: Icons.text_fields,
      title: 'UTF-8 与 Rust 字符串',
      subtitle: '区分 str::len() 字节数和 chars().count() 标量数；组合字符可包含多个标量。',
      children: [
        DropdownButtonFormField<RustStringInput>(
          key: const ValueKey('rust-string-mode'),
          initialValue: _stringMode,
          isExpanded: true,
          decoration: const InputDecoration(
            labelText: '输入内容',
            border: OutlineInputBorder(),
          ),
          items: const [
            DropdownMenuItem(value: RustStringInput.text, child: Text('普通文本')),
            DropdownMenuItem(
              value: RustStringInput.literal,
              child: Text('Rust 字面量'),
            ),
          ],
          onChanged: (mode) {
            if (mode != null) setState(() => _stringMode = mode);
          },
        ),
        const SizedBox(height: 12),
        TextField(
          key: const ValueKey('rust-string-input'),
          controller: _string,
          minLines: 2,
          maxLines: 6,
          onChanged: (_) => setState(() {}),
          decoration: const InputDecoration(
            labelText: '文本或完整字面量',
            alignLabelWithHint: true,
            border: OutlineInputBorder(),
          ),
        ),
        ToolError(error),
        if (view != null) ...[
          _Value(label: 'str::len() / UTF-8 字节', value: '${view.bytes.length}'),
          _Value(
            label: 'chars().count() / Unicode 标量',
            value: '${view.scalars.length}',
          ),
          _Value(label: 'UTF-16 单元数', value: '${view.utf16Length}'),
          _Value(label: 'UTF-8 字节（十六进制）', value: view.bytesHex),
          _Value(label: 'Rust 转义字面量', value: view.escapedLiteral),
          if (view.rawLiteral case final raw?)
            _Value(label: 'Rust raw string', value: raw)
          else
            const Text('此文本无法直接表示为 Rust raw string，请使用转义字面量。'),
          if (view.scalars.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(
              '标量与 UTF-8 字节位置',
              style: Theme.of(context).textTheme.titleSmall,
            ),
            for (final scalar in view.scalars.take(64))
              _Value(
                label: 'byte ${scalar.byteOffset} · ${scalar.codePoint}',
                value:
                    '${scalar.rustEscape} · ${formatRustBytes(scalar.bytes)}',
              ),
            if (view.scalars.length > 64)
              const Text('表格显示前 64 个标量；上方计数和可复制结果包含全部内容。'),
          ],
        ],
      ],
    );
  }

  Widget _projectSection() {
    final projects = _projects;
    final inspection = _inspection;
    final selected = projects.any((project) => project.id == _projectId)
        ? _projectId
        : null;
    return _ToolSection(
      icon: Icons.inventory_2_outlined,
      title: '本地 Cargo 项目检查',
      subtitle: '默认检查侧边栏当前项目。元数据检查不编译、不运行 build.rs；强制离线并锁定依赖清单。',
      children: [
        if (projects.isEmpty)
          const Text('尚无本地项目，请先在项目页创建或导入 Rust 项目。')
        else ...[
          DropdownButtonFormField<String>(
            key: ValueKey('rust-project-$selected'),
            initialValue: selected,
            isExpanded: true,
            decoration: const InputDecoration(
              labelText: '本地项目',
              border: OutlineInputBorder(),
            ),
            items: [
              for (final project in projects)
                DropdownMenuItem(
                  value: project.id,
                  child: Text(project.name, overflow: TextOverflow.ellipsis),
                ),
            ],
            onChanged: (id) {
              if (id == null) return;
              _userSelectedProject = true;
              _projectId = id;
              _inspectProject();
            },
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              OutlinedButton.icon(
                key: const ValueKey('rust-project-refresh'),
                onPressed: _inspecting ? null : _inspectProject,
                icon: const Icon(Icons.refresh),
                label: const Text('重新检查'),
              ),
              TextButton(
                onPressed: () {
                  _userSelectedProject = false;
                  _projectsChanged();
                },
                child: const Text('跟随当前项目'),
              ),
            ],
          ),
          if (_inspecting)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 12),
              child: LinearProgressIndicator(),
            ),
          if (inspection != null) ...[
            _Value(label: '项目目录', value: inspection.root),
            _Value(
              label: '入口源文件',
              value: inspection.entry == null
                  ? '未找到入口'
                  : p.relative(inspection.entry!, from: inspection.root),
            ),
            ToolError(inspection.error),
            if (inspection.targetMessage case final message?) Text(message),
            for (final target in inspection.targets) ...[
              const Divider(height: 24),
              _Value(
                label: '${target.packageName} · ${target.targetName}',
                value:
                    'kind: ${target.kinds.join(', ')}\n'
                    'crate types: ${target.crateTypes.join(', ')}\n'
                    '${target.isRunnable ? '可运行' : '不可作为 cargo run 入口'}\n'
                    '${p.relative(target.srcPath, from: inspection.root)}',
              ),
            ],
            if (inspection.manifest case final manifest?) ...[
              const SizedBox(height: 12),
              _Value(label: 'Cargo.toml', value: manifest),
            ],
          ],
        ],
      ],
    );
  }
}

String _radix(BigInt value, int radix, String prefix) =>
    '${value.isNegative ? '-' : ''}$prefix${value.abs().toRadixString(radix)}';

String _groupBits(String bits) => [
  for (var start = 0; start < bits.length; start += 8)
    bits.substring(start, start + 8),
].join(' ');

class _ToolSection extends StatelessWidget {
  const _ToolSection({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.children,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) => Container(
    width: double.infinity,
    padding: const EdgeInsets.all(16),
    decoration: ToolsTheme.cardDecoration(Theme.of(context).colorScheme),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        ToolsSectionHeading(icon: icon, title: title, subtitle: subtitle),
        const SizedBox(height: 16),
        ...children,
      ],
    ),
  );
}

/// Stack field groups on phones and when accessibility scaling needs room.
class _ResponsiveFields extends StatelessWidget {
  const _ResponsiveFields({required this.children});
  final List<Widget> children;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, size) {
      final wide =
          size.maxWidth >= 640 &&
          MediaQuery.textScalerOf(context).scale(14) <= 21;
      if (wide) {
        return Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            for (var index = 0; index < children.length; index++) ...[
              if (index > 0) const SizedBox(width: 12),
              Expanded(child: children[index]),
            ],
          ],
        );
      }
      return Column(
        children: [
          for (var index = 0; index < children.length; index++) ...[
            if (index > 0) const SizedBox(height: 12),
            children[index],
          ],
        ],
      );
    },
  );
}

/// Vertical labels leave the result its full width at large text scales.
class _Value extends StatelessWidget {
  const _Value({required this.label, required this.value});
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 6),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Wrap(
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            Text(label, style: Theme.of(context).textTheme.labelMedium),
            IconButton(
              tooltip: '复制$label',
              visualDensity: VisualDensity.compact,
              onPressed: () => Copy.copy(context, value),
              icon: const Icon(Icons.copy_all_outlined, size: 18),
            ),
          ],
        ),
        SelectableText(
          value.isEmpty ? '（空）' : value,
          style: const TextStyle(
            fontFamily: 'monospace',
            fontSize: 13,
            height: 1.4,
          ),
        ),
      ],
    ),
  );
}
