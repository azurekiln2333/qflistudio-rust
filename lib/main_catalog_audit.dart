import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:path/path.dart' as p;

import 'rust_native_catalog_audit.dart';
import 'rust_native_feature_audit.dart';

/// Separate audit bundle entry point. The ordinary application never opens it.
void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const MaterialApp(home: _AuditPage()));
}

class _AuditPage extends StatefulWidget {
  const _AuditPage();

  @override
  State<_AuditPage> createState() => _AuditPageState();
}

class _AuditPageState extends State<_AuditPage> {
  final _report = File(
    p.join(Directory.systemTemp.path, 'rust_catalog_audit.json'),
  );
  final _featureReport = File(
    p.join(Directory.systemTemp.path, 'rust_native_feature_audit.json'),
  );
  String _status = '正在准备实际运行环境';
  String _current = '';
  int _completed = 0;
  int _total = 0;
  int _failed = 0;
  int _featuresCompleted = 0;
  int _featuresFailed = 0;
  RustNativeFeatureCleanupFailure? _cleanupFailure;
  bool _retryingCleanup = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => unawaited(_run()));
  }

  Future<void> _run() async {
    debugPrint('QFLI_RUST_AUDIT_REPORT ${_report.path}');
    debugPrint('QFLI_RUST_FEATURE_AUDIT_REPORT ${_featureReport.path}');
    try {
      // Catalog execution may be interrupted before the feature audit starts.
      // Invalidate its old success before the first fallible preparation too.
      final started = DateTime.now().toUtc();
      writeRustAuditReport(_featureReport, {
        'schemaVersion': 1,
        'scope': 'native_feature_providers',
        'runId': '${started.microsecondsSinceEpoch}-$pid-awaiting-catalog',
        'auditBuildId': const String.fromEnvironment(
          'QFLI_RUST_AUDIT_BUILD_ID',
        ),
        'startedAt': started.toIso8601String(),
        'phase': 'waiting_for_catalog',
        'interrupted': true,
        'cleanupComplete': false,
        'complete': false,
        'passed': false,
        'checks': <Object?>[],
      });
      final report = await runRustNativeCatalogAudit(
        reportFile: _report,
        onProgress: (result, completed, total) {
          debugPrint('QFLI_RUST_AUDIT_CASE ${result.id} ${result.status.name}');
          if (!mounted) return;
          setState(() {
            _completed = completed;
            _total = total;
            if (result.status.name != 'passed') _failed++;
            _status = '正在运行现有教程与示例';
            _current = '${result.id}: ${result.detail ?? result.status.name}';
          });
        },
      );
      debugPrint(
        'QFLI_RUST_AUDIT_DONE passed=${report.passed} '
        'executed=${report.results.length} failed=${report.failedIds.length}',
      );
      if (mounted) setState(() => _status = '正在检查原生分析、调试与离线入口');
      final features = await runRustNativeFeatureAudit(
        reportFile: _featureReport,
        onProgress: (result) {
          debugPrint(
            'QFLI_RUST_FEATURE_AUDIT_CHECK ${result.check.name} '
            '${result.status.name}',
          );
          if (!mounted) return;
          setState(() {
            _featuresCompleted++;
            if (result.status.name != 'passed') _featuresFailed++;
            _current =
                '${result.check.name}: ${result.detail ?? result.status.name}';
          });
        },
      );
      debugPrint(
        'QFLI_RUST_FEATURE_AUDIT_DONE passed=${features.passed} '
        'executed=${features.results.length} '
        'cleanupComplete=${features.cleanupComplete}',
      );
      if (mounted) {
        setState(
          () => _status = report.passed && features.passed
              ? '全部程序与原生功能通过'
              : '审计结束：存在失败',
        );
      }
    } on RustNativeFeatureCleanupFailure catch (error) {
      _cleanupFailure = error;
      debugPrint('QFLI_RUST_FEATURE_AUDIT_CLEANUP_PENDING $error');
      if (mounted) setState(() => _status = '审计中断：原生会话仍待清理');
    } catch (error) {
      // The shared pipeline replaces old evidence before preparation and keeps
      // this invocation's partial results on failure.
      debugPrint('QFLI_RUST_AUDIT_ERROR $error');
      if (mounted) setState(() => _status = '审计中断：$error');
    }
  }

  Future<void> _retryCleanup() async {
    final failure = _cleanupFailure;
    if (failure == null || _retryingCleanup) return;
    setState(() => _retryingCleanup = true);
    try {
      await failure.retryCleanup();
      _cleanupFailure = null;
      debugPrint('QFLI_RUST_FEATURE_AUDIT_CLEANUP_DONE');
      if (mounted) setState(() => _status = '原生会话已清理；本次审计仍为中断');
    } catch (error) {
      debugPrint('QFLI_RUST_FEATURE_AUDIT_CLEANUP_PENDING $error');
      if (mounted) setState(() => _status = '清理尚未完成：$error');
    } finally {
      if (mounted) setState(() => _retryingCleanup = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Rust 全量运行审计')),
    body: SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(_status, style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 16),
          LinearProgressIndicator(
            value: _total == 0 ? null : _completed / _total,
          ),
          const SizedBox(height: 12),
          Text('已执行 $_completed / $_total，失败 $_failed'),
          Text(
            '原生功能 $_featuresCompleted / '
            '${RustNativeFeatureCheck.values.length}，失败 $_featuresFailed',
          ),
          if (_cleanupFailure != null)
            FilledButton(
              onPressed: _retryingCleanup ? null : _retryCleanup,
              child: Text(_retryingCleanup ? '正在清理原生会话' : '重试清理原生会话'),
            ),
          const SizedBox(height: 12),
          SelectableText(_current),
          const SizedBox(height: 24),
          const Text(
            '逐项结果已保存。附带 Cargo 项目仅运行主入口；'
            'Cargo 构建及测试结果单独验收。',
          ),
          SelectableText(_report.path),
          SelectableText(_featureReport.path),
        ],
      ),
    ),
  );
}
