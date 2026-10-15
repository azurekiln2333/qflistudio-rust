import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;
import 'package:qfli_rust/main.dart' show rustProfile;
import 'package:qfli_rust/native_miri_runner.dart';
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

  bool windowsGnuAvailable() {
    if (!Platform.isWindows) return false;
    try {
      final result = Process.runSync('rustc', ['-vV']);
      return result.exitCode == 0 &&
          (result.stdout as String).contains('host: x86_64-pc-windows-gnu');
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

  Future<void> expectStartupFailure(
    ProgramRunResult result,
    String diagnostic,
  ) async {
    final output = result.stdout.toList();
    final errors = result.stderr.toList();
    expect(await result.exitCode, kProgramNotRunExitCode);
    expect(await output, isEmpty);
    expect((await errors).join('\n'), contains(diagnostic));
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

    test('Cargo 项目按选中的备用入口运行，而不是默认 main', () async {
      write('Cargo.toml', '''
[package]
name = "qfli_multi"
version = "0.1.0"
edition = "2021"

[[bin]]
name = "primary"
path = "src/main.rs"

[[bin]]
name = "secondary"
path = "src/alt.rs"
''');
      write('src/main.rs', 'fn main() { println!("primary-target"); }');
      write('src/alt.rs', 'fn main() { println!("secondary-target"); }');
      final (code, output, errors) = await runRust('src/alt.rs');
      expect(code, 0, reason: errors.join('\n'));
      expect(output, ['secondary-target']);
    }, skip: !toolAvailable('cargo'));

    test('Cargo 项目按自定义 target 名与路径运行 example', () async {
      write('Cargo.toml', '''
[package]
name = "qfli_example"
version = "0.1.0"
edition = "2021"

[[example]]
name = "named_demo"
path = "examples/named_demo.rs"
''');
      write('src/main.rs', 'fn main() {}');
      write(
        'examples/named_demo.rs',
        'fn main() { println!("example-target"); }',
      );
      final (code, output, errors) = await runRust('examples/named_demo.rs');
      expect(code, 0, reason: errors.join('\n'));
      expect(output, ['example-target']);
    }, skip: !toolAvailable('cargo'));

    test(
      'Cargo 项目中未注册的普通 .rs 走单文件 rustc 路线',
      () async {
        write('Cargo.toml', '''
[package]
name = "qfli_unregistered"
version = "0.1.0"
edition = "2021"
''');
        write('src/main.rs', 'fn main() { println!("default-main"); }');
        write('main2.rs', 'fn main() { println!("standalone-main2"); }');
        final (code, output, errors) = await runRust('main2.rs');
        expect(code, 0, reason: errors.join('\n'));
        expect(output, ['standalone-main2']);
        expect(errors.join('\n'), isNot(contains('default-main')));
      },
      skip: !toolAvailable('cargo') || !toolAvailable('rustc'),
    );

    test('Cargo metadata 不可用时明确失败，不回跑默认 main', () async {
      write('Cargo.toml', 'this is not valid toml =');
      write('src/main.rs', 'fn main() { println!("should-not-run"); }');
      final (code, output, errors) = await runRust('src/main.rs');
      expect(code, kProgramNotRunExitCode);
      expect(output, isEmpty);
      expect(errors.join('\n'), contains('cargo metadata'));
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

    test(
      'explicit RUSTC environment selects the configured compiler',
      () async {
        write('main.rs', 'fn main() {}');
        final (code, output, errors) = await runRust(
          'main.rs',
          runner: const RustProgramRunner(
            environment: {'RUSTC': 'qfli_missing_configured_rustc'},
          ),
        );
        expect(code, kProgramNotRunExitCode);
        expect(output, isEmpty);
        expect(errors.join('\n'), contains('qfli_missing_configured_rustc'));
      },
    );

    test(
      'explicit encoded linker flags are preserved for direct rustc',
      () async {
        write('main.rs', 'fn main() {}');
        final (code, output, errors) = await runRust(
          'main.rs',
          runner: const RustProgramRunner(
            environment: {
              'CARGO_ENCODED_RUSTFLAGS':
                  '-C\u001flinker=qfli_missing_explicit_linker.exe',
            },
          ),
        );
        expect(code, isNot(0));
        expect(code, isNot(kProgramNotRunExitCode));
        expect(output, isEmpty);
        expect(errors.join('\n'), contains('qfli_missing_explicit_linker.exe'));
      },
      skip: !windowsGnuAvailable(),
    );

    test(
      'Cargo linker TOML configuration is not overwritten by bundled flags',
      () async {
        write('Cargo.toml', '''
[package]
name = "qfli_configured_linker"
version = "0.1.0"
edition = "2021"
''');
        write('.cargo/config.toml', '''
[target.x86_64-pc-windows-gnu]
linker = "qfli_missing_cargo_linker.exe"
''');
        write('src/main.rs', 'fn main() {}');
        final (code, output, errors) = await runRust('src/main.rs');
        expect(code, isNot(0));
        expect(code, isNot(kProgramNotRunExitCode));
        expect(output, isEmpty);
        expect(errors.join('\n'), contains('qfli_missing_cargo_linker.exe'));
      },
      skip: !windowsGnuAvailable() || !toolAvailable('cargo'),
    );

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

  group('运行标题', () {
    test('桌面路线标题是简洁的 run <项目相对路径>', () async {
      write('src/main.rs', 'fn main() {}');
      final result =
          await const RustProgramRunner(
            rustcExecutable: 'qfli_missing_rustc_for_title',
          ).run(
            projectPath: project.path,
            entryFile: p.join(project.path, 'src/main.rs'),
          );
      expect(result, isNotNull);
      expect(result!.title, 'run src/main.rs');
      expect(result.title, isNot(contains('运行')));
      expect(result.title, isNot(contains('Rust')));
      await expectStartupFailure(result, 'qfli_missing_rustc_for_title');
    });

    test('嵌入式路线标题同为 run <项目相对路径>，无 Miri 后缀', () async {
      final sysroot = (Directory(
        p.join(project.path, 'sysroot'),
      )..createSync()).path;
      write('main2.rs', 'fn main() {}');
      final result =
          await RustProgramRunner(
            executionMode: RustExecutionMode.embedded,
            embeddedRunner: NativeMiriProgramRunner(
              sysrootPath: sysroot,
              libraryPath: p.join(project.path, 'missing_native_library'),
            ),
          ).run(
            projectPath: project.path,
            entryFile: p.join(project.path, 'main2.rs'),
          );
      expect(result, isNotNull);
      // The failure title still goes through the shared concise contract.
      expect(result!.title, 'run main2.rs');
      expect(result.title, isNot(contains('Miri')));
      await expectStartupFailure(result, 'missing_native_library');
    });

    test('含空格的项目相对路径在标题中被引号包裹', () async {
      write('src/my file.rs', 'fn main() {}');
      final result =
          await const RustProgramRunner(
            rustcExecutable: 'qfli_missing_rustc_for_title',
          ).run(
            projectPath: project.path,
            entryFile: p.join(project.path, 'src/my file.rs'),
          );
      expect(result, isNotNull);
      expect(result!.title, 'run "src/my file.rs"');
      expect(result.title, isNot(contains('运行')));
      await expectStartupFailure(result, 'qfli_missing_rustc_for_title');
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
      expect(result.title, 'run main.rs');
      expect(await result.stdout!.toList(), ['through runner']);
      expect(await result.stderr!.toList(), isEmpty);
      expect(await result.exitCode, 0);
    }, skip: !toolAvailable('rustc'));
  });
}
