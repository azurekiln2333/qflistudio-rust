import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;
import 'package:qfli_rust/main.dart' show rustProfile;
import 'package:qfli_rust/rust_runner.dart';
import 'package:qfli_studio_core/services/project_templates.dart';
import 'package:qfli_studio_core/services/runner_service.dart';
import 'package:qfli_studio_core/services/studio_profile.dart';

/// Rust 版 App 的接线测试。
///
/// 覆盖的正是「一个语言一个 App」的全部接缝：内核怎么知道该显示哪个模板、
/// 该跑哪个入口文件、以及运行后端有没有正确接管/交回。
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late Directory project;
  late StudioProfile? previousProfile;

  setUp(() {
    previousProfile = StudioProfile.current;
    StudioProfile.current = rustProfile;
    project = Directory.systemTemp.createTempSync('qfli_rust_app_test');
  });

  tearDown(() {
    StudioProfile.current = previousProfile;
    if (project.existsSync()) project.deleteSync(recursive: true);
  });

  void write(String relative, String content) {
    final file = File(p.join(project.path, relative));
    file.parent.createSync(recursive: true);
    file.writeAsStringSync(content);
  }

  bool toolAvailable(String executable) {
    try {
      return Process.runSync(executable, ['--version']).exitCode == 0;
    } on ProcessException {
      return false;
    }
  }

  Future<(int, List<String>, List<String>)> runRust(
    String entry, {
    RustProgramRunner runner = const RustProgramRunner(),
  }) async {
    final result = await runner.run(
      projectPath: project.path,
      entryFile: p.join(project.path, entry),
    );
    expect(result, isNotNull);
    final output = result!.stdout.toList();
    final errors = result.stderr.toList();
    final code = await result.exitCode;
    return (code, await output, await errors);
  }

  group('档位收窄', () {
    test('新建项目只放行「空项目」和 Rust', () {
      expect(rustProfile.filterTemplates(ProjectTemplate.values), [
        ProjectTemplate.empty,
        ProjectTemplate.rust,
      ]);
    });

    test('默认模板是 Rust 而不是空项目', () {
      expect(rustProfile.defaultTemplate, ProjectTemplate.rust);
    });

    test('语言筛选芯片只剩 Rust', () {
      // 首页传给档位的候选本来就不含「空项目」——它不是一门语言。
      const all = [
        'Rust',
        'Go',
        'SQL',
        'JSON',
        'Markdown',
        'C++',
        'Lua',
        'Web',
        'Python',
        'Java',
        'Dart',
      ];
      expect(rustProfile.filterLanguages(all), ['Rust']);
    });

    test('产品名带 Rust 版后缀', () {
      expect(rustProfile.appTitle, 'QFLIRustCore');
    });

    test('档位只使用本地能力', () {
      expect(rustProfile.isOffline, isTrue);
    });
  });

  group('入口文件识别', () {
    test('优先命中 main.rs', () {
      write('main.rs', '// .rs');
      write('other.txt', 'x');
      expect(
        RunnerService.findEntry(project.path),
        p.join(project.path, 'main.rs'),
      );
    });

    test('入口表覆盖了模板自带的入口文件', () {
      // 这是「一个语言一个 App」最容易出错的地方：模板统一把源码放在 src/ 下，
      // 而入口表要是只写了根目录的文件名，新建项目后点运行就会找不到入口。
      final mainFile = ProjectTemplate.rust.mainFile;
      expect(mainFile, isNotNull, reason: '模板里没有文件');
      expect(rustProfile.entryFileNames, contains(mainFile));
    });

    test('模板把源码放在 src/ 下时也能找到入口', () {
      final mainFile = ProjectTemplate.rust.mainFile!;
      write(mainFile, '// 示例');
      expect(
        RunnerService.findEntry(project.path),
        p.join(project.path, mainFile),
      );
    });
  });

  group('运行后端', () {
    test('rustc 编译并运行，保留 stdout、stderr 和程序退出码', () async {
      write('main.rs', '''
fn main() {
    println!("ready");
    eprintln!("warning");
    std::process::exit(23);
}
''');
      final (code, output, errors) = await runRust('main.rs');
      expect(code, 23);
      expect(output, ['ready']);
      expect(errors, ['warning']);
      expect(Directory(p.join(project.path, 'target')).existsSync(), isFalse);
    }, skip: !toolAvailable('rustc'));

    test('Cargo 项目运行并返回程序退出码', () async {
      write('Cargo.toml', '''
[package]
name = "qfli_test"
version = "0.1.0"
edition = "2021"
''');
      write('src/main.rs', '''
fn main() {
    println!("cargo-ready");
    std::process::exit(17);
}
''');
      final (code, output, errors) = await runRust('src/main.rs');
      expect(code, 17, reason: errors.join('\n'));
      expect(output, ['cargo-ready']);
      expect(Directory(p.join(project.path, 'target')).existsSync(), isTrue);
      final (secondCode, secondOutput, secondErrors) = await runRust(
        'src/main.rs',
      );
      expect(secondCode, 17, reason: secondErrors.join('\n'));
      expect(secondOutput, ['cargo-ready']);
    }, skip: !toolAvailable('cargo'));

    test('编译失败显示 rustc 诊断，不运行旧程序', () async {
      write('main.rs', 'fn main() { println!("old executable"); }');
      final (firstCode, firstOutput, _) = await runRust('main.rs');
      expect(firstCode, 0);
      expect(firstOutput, ['old executable']);

      write('main.rs', 'fn main() { let value = ; }');
      final (code, output, errors) = await runRust('main.rs');
      expect(code, isNot(0));
      expect(code, isNot(kProgramNotRunExitCode));
      expect(output, isEmpty);
      expect(errors.join('\n'), contains('error'));
    }, skip: !toolAvailable('rustc'));

    test('将 input.txt 送入 stdin，缺少输入时发送 EOF', () async {
      write('main.rs', '''
use std::io::{self, Read};
fn main() {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input).unwrap();
    println!("{}", if input.is_empty() { "eof" } else { input.trim() });
}
''');
      var (code, output, errors) = await runRust(
        'main.rs',
      ).timeout(const Duration(seconds: 15));
      expect(code, 0, reason: errors.join('\n'));
      expect(output, ['eof']);

      write('input.txt', 'from input file\n');
      (code, output, errors) = await runRust('main.rs');
      expect(code, 0, reason: errors.join('\n'));
      expect(output, ['from input file']);
    }, skip: !toolAvailable('rustc'));

    test('找不到工具链时提供可操作错误', () async {
      write('main.rs', 'fn main() {}');
      const runner = RustProgramRunner(
        rustcExecutable: 'qfli_nonexistent_rustc_for_test',
      );
      final (code, output, errors) = await runRust('main.rs', runner: runner);
      expect(code, kProgramNotRunExitCode);
      expect(output, isEmpty);
      expect(errors.join('\n'), contains('PATH'));
    });

    test('找不到 Rust 源文件时不启动工具链', () async {
      final (code, output, errors) = await runRust('missing.rs');
      expect(code, kProgramNotRunExitCode);
      expect(output, isEmpty);
      expect(errors.join('\n'), contains('源文件不存在'));
    });

    test('取消正在运行的程序并返回非零状态', () async {
      write('main.rs', '''
fn main() {
    println!("started");
    std::thread::sleep(std::time::Duration::from_secs(30));
}
''');
      final result = await rustProfile.runner!.run(
        projectPath: project.path,
        entryFile: p.join(project.path, 'main.rs'),
      );
      expect(result, isNotNull);
      expect(await result!.stdout.first, 'started');
      await result.cancel!().timeout(const Duration(seconds: 10));
      expect(await result.exitCode, 130);
    }, skip: !toolAvailable('rustc'));

    test('取消运行同时结束 Rust 创建的子进程', () async {
      write('main.rs', '''
use std::process::{Command, Stdio};
fn main() {
    let child = Command::new("cmd")
        .args(["/C", "ping -n 30 127.0.0.1 > NUL"])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .unwrap();
    println!("{}", child.id());
    std::thread::sleep(std::time::Duration::from_secs(30));
}
''');
      final result = await rustProfile.runner!.run(
        projectPath: project.path,
        entryFile: p.join(project.path, 'main.rs'),
      );
      expect(result, isNotNull);
      final childPid = int.parse(await result!.stdout.first);
      await result.cancel!().timeout(const Duration(seconds: 10));
      expect(await result.exitCode, 130);
      expect(Process.killPid(childPid, ProcessSignal.sigkill), isFalse);
    }, skip: !Platform.isWindows || !toolAvailable('rustc'));

    test('别的语言文件交回内核', () async {
      write('main.py', 'x');
      final result = await rustProfile.runner!.run(
        projectPath: project.path,
        entryFile: p.join(project.path, 'main.py'),
      );
      expect(result, isNull);
    });
  });

  group('运行按钮分流', () {
    test('点运行走 Rust 后端并执行源码', () async {
      write('main.rs', 'fn main() { println!("through runner"); }');
      final result = await RunnerService.runProject(
        projectPath: project.path,
        entryFile: p.join(project.path, 'main.rs'),
      );
      expect(result, isNotNull);
      expect(result!.hint, isNull, reason: '后端接管了就不该走兜底提示');
      expect(result.title, contains('Rust'));
      expect(await result.stdout!.toList(), ['through runner']);
      expect(await result.stderr!.toList(), isEmpty);
      expect(await result.exitCode, 0);
    }, skip: !toolAvailable('rustc'));
  });
}
