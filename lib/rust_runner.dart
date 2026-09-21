import 'dart:async';

import 'package:path/path.dart' as p;
import 'package:qfli_studio_core/services/studio_profile.dart';

/// Rust 版 App 的运行后端。
///
/// 目标形态是**应用内 Rust 子集解释器（纯 Dart）**。
/// 之所以是解释而不是编译：鸿蒙的普通应用被 SELinux 挡在 `exec` 之外，既调不动
/// 设备上的编译器，也拉不起打包进 HAP 的可执行文件（HNP 那条路要求应用具备
/// 生产力应用资格）。但沙箱从来不限制应用解释自己的数据，所以「自带解释器、
/// 在当前进程里跑自己的源码」是普通应用唯一走得通的路。
///
/// C 版的 `qfli_c_runtime` 已经把这条路走通并交付（词法 → 预处理 → 语法 →
/// 解释，约 7000 行纯 Dart），本版是同一个模式的接入点。
///
/// 解释器落地之前，[run] 明确返回「还不能运行」，而不是给一个看起来像结果的
/// 东西——那比报错更糟。
///
/// **接入方式**：把 [_notReady] 换成真实解释器的调用（返回一个带
/// stdout/stderr/exitCode 的 [ProgramRunResult]）。档位、入口识别、终端输出、
/// 退出码这些接线都不用动。
class RustProgramRunner implements ProgramRunner {
  const RustProgramRunner();

  /// 本后端接管的源码后缀。
  static const Set<String> _sourceExtensions = {'.rs'};

  @override
  Future<ProgramRunResult?> run({
    required String projectPath,
    required String entryFile,
  }) async {
    // 不是本语言的文件交回内核（返回 null），内核会走自己的分流逻辑。
    if (!_sourceExtensions.contains(p.extension(entryFile).toLowerCase())) {
      return null;
    }
    return _notReady(p.basename(entryFile));
  }

  /// 解释器还没接上时的占位结果。
  ProgramRunResult _notReady(String fileName) {
    final controller = StreamController<String>();
    scheduleMicrotask(() {
      controller
        ..add('Rust 版的运行后端还在开发中（应用内纯 Dart 解释器）。')
        ..add('现在已经可用的：编辑器、语法高亮、项目模板、Rust 入门教程。')
        ..add('内置 Rust 解释器完成后即可在本 App 内运行这段代码。')
        ..close();
    });
    return ProgramRunResult(
      title: '运行 $fileName（Rust 解释器开发中）',
      stdout: controller.stream,
      stderr: const Stream<String>.empty(),
      exitCode: Future<int>.value(kProgramNotRunExitCode),
    );
  }
}
