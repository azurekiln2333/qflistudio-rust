import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;
import 'package:qfli_rust/main.dart' show rustProfile;
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

  group('档位收窄', () {
    test('新建项目只放行「空项目」和 Rust', () {
      expect(
        rustProfile.filterTemplates(ProjectTemplate.values),
        [ProjectTemplate.empty, ProjectTemplate.rust],
      );
    });

    test('默认模板是 Rust 而不是空项目', () {
      expect(rustProfile.defaultTemplate,
          ProjectTemplate.rust);
    });

    test('语言筛选芯片只剩 Rust', () {
      // 首页传给档位的候选本来就不含「空项目」——它不是一门语言。
      const all = ['Rust', 'Go', 'SQL', 'JSON', 'Markdown', 'C++', 'Lua', 'Web', 'Python', 'Java', 'Dart'];
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
    test('本语言文件被接管，并说明解释器还在开发中', () async {
      write('main.rs', '// 示例');
      final result = await rustProfile.runner!.run(
        projectPath: project.path,
        entryFile: p.join(project.path, 'main.rs'),
      );
      expect(result, isNotNull, reason: '运行后端没有接管本语言文件');
      expect(result!.title, contains('Rust 解释器开发中'));
      expect(await result.stdout.toList(), isNotEmpty);
      expect(await result.exitCode, kProgramNotRunExitCode);
    });

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
    test('点运行拿到结果，而不是掉进「移动端跑不了」的兜底提示', () async {
      write('main.rs', '// 示例');
      final result = await RunnerService.runProject(
        projectPath: project.path,
        entryFile: p.join(project.path, 'main.rs'),
      );
      expect(result, isNotNull);
      expect(result!.hint, isNull, reason: '后端接管了就不该走兜底提示');
      expect(result.title, contains('Rust 解释器开发中'));
    });
  });
}
