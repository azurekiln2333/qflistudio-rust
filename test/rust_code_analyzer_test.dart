import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;
import 'package:qfli_rust/rust_code_analyzer.dart';
import 'package:qfli_studio_core/services/code_analysis.dart';

/// The pinned compiler produced by this repository's native build. Tests skip
/// (with an explicit reason) when it is missing instead of asserting clean code.
final _rustc = File(RustCodeAnalyzer.discoverRustc());
final _rustcAvailable = _rustc.existsSync();
final _skipReason = _rustcAvailable
    ? false
    : 'Pinned rustc is not available at ${_rustc.path}';

/// Records the job without running a compiler, so mirror and argument behaviour
/// can be asserted deterministically.
class _RecordingTransport implements RustAnalysisTransport {
  _RecordingTransport([this.output]);

  final RustAnalysisOutput? output;
  RustAnalysisJob? job;
  List<String> mirrorFiles = const [];
  Map<String, String> mirrorContents = const {};

  @override
  Future<RustAnalysisOutput> analyze(RustAnalysisJob job) async {
    this.job = job;
    final root = Directory(job.mirrorRoot);
    final files = <String>[];
    final contents = <String, String>{};
    if (root.existsSync()) {
      for (final entity in root.listSync(recursive: true)) {
        if (entity is! File) continue;
        final relative = p.relative(entity.path, from: job.mirrorRoot);
        files.add(p.posix.joinAll(p.split(relative)));
        contents[files.last] = utf8.decode(
          entity.readAsBytesSync(),
          allowMalformed: true,
        );
      }
    }
    mirrorFiles = files..sort();
    mirrorContents = contents;
    return output ??
        const RustAnalysisOutput(exitCode: 0, diagnosticsJsonl: '');
  }
}

/// Supplies native-style diagnostic data without invoking a compiler.
class _DiagnosticTransport implements RustAnalysisTransport {
  _DiagnosticTransport(this.records);

  final List<Map<String, Object?>> Function(RustAnalysisJob) records;

  @override
  Future<RustAnalysisOutput> analyze(RustAnalysisJob job) async =>
      RustAnalysisOutput(
        exitCode: 0,
        diagnosticsJsonl: records(job).map(jsonEncode).join('\n'),
      );
}

/// Transport that never answers in time.
class _HangingTransport implements RustAnalysisTransport {
  @override
  Future<RustAnalysisOutput> analyze(RustAnalysisJob job) =>
      Completer<RustAnalysisOutput>().future;
}

/// Byte offset of [needle] inside `utf8.encode(text)`, mirroring the compiler's
/// coordinate system so the test can prove the two differ.
int byteIndexOf(String text, String needle) {
  final haystack = utf8.encode(text);
  final pattern = utf8.encode(needle);
  for (var i = 0; i + pattern.length <= haystack.length; i++) {
    var match = true;
    for (var j = 0; j < pattern.length; j++) {
      if (haystack[i + j] != pattern[j]) {
        match = false;
        break;
      }
    }
    if (match) return i;
  }
  return -1;
}

CodeAnalysisRequest _request({
  required String project,
  required String active,
  List<({String path, String text, int revision})> documents = const [],
  String language = 'rust',
}) => CodeAnalysisRequest(
  projectPath: project,
  activeFilePath: active,
  language: language,
  revision: documents.isEmpty ? 0 : documents.last.revision,
  documents: [
    for (final document in documents)
      CodeDocumentSnapshot(
        path: document.path,
        text: document.text,
        revision: document.revision,
      ),
  ],
);

void main() {
  late Directory project;

  setUp(() {
    project = Directory.systemTemp.createTempSync('qfli_rust_analyzer_');
  });

  tearDown(() {
    if (project.existsSync()) project.deleteSync(recursive: true);
  });

  String write(String relative, String contents) {
    final file = File(p.joinAll([project.path, ...p.split(relative)]));
    file.parent.createSync(recursive: true);
    file.writeAsStringSync(contents);
    return file.path;
  }

  Map<String, String> snapshotTree() {
    final result = <String, String>{};
    for (final entity in project.listSync(recursive: true)) {
      if (entity is! File) continue;
      result[p.relative(entity.path, from: project.path)] = base64Encode(
        entity.readAsBytesSync(),
      );
    }
    return result;
  }

  group('contract and unavailable states', () {
    test('a non-Rust file is reported as not checked', () async {
      final entry = write('main.py', 'print(1)\n');
      final result = await RustCodeAnalyzer(transport: _RecordingTransport())
          .analyze(
            _request(project: project.path, active: entry, language: 'python'),
          );
      expect(result.diagnostics, isEmpty);
      expect(result.unavailableReason, isNotNull);
    });

    for (final level in ['error', 'fatal']) {
      test('native spanless $level is unavailable with exit zero', () async {
        final entry = write('src/main.rs', 'fn main() {}\n');
        final result = await RustCodeAnalyzer(
          transport: _DiagnosticTransport((_) => [
            {
              r'$message_type': 'diagnostic',
              'message': 'compiler input could not be loaded',
              'level': level,
              'spans': <Object>[],
            },
          ]),
        ).analyze(_request(project: project.path, active: entry));
        expect(result.diagnostics, isEmpty);
        expect(result.unavailableReason, isNotNull);
      });
    }

    for (final includeError in [false, true]) {
      test(
        'mapped warning preserves spanless error status $includeError',
        () async {
          final entry = write('src/main.rs', 'fn main() {}\n');
          final result = await RustCodeAnalyzer(
            transport: _DiagnosticTransport((job) => [
              {
                r'$message_type': 'diagnostic',
                'message': 'source warning',
                'level': 'warning',
                'spans': [
                  {
                    'file_name': job.entryPath,
                    'byte_start': 0,
                    'byte_end': 2,
                    'is_primary': true,
                  },
                ],
              },
              {
                r'$message_type': 'diagnostic',
                'message': 'compiler input record',
                'level': includeError ? 'error' : 'note',
                'spans': <Object>[],
              },
            ]),
          ).analyze(_request(project: project.path, active: entry));
          if (includeError) {
            expect(result.unavailableReason, isNotNull);
          } else {
            expect(result.unavailableReason, isNull);
            expect(
              result.diagnostics.single.severity,
              CodeDiagnosticSeverity.warning,
            );
          }
        },
      );
    }

    for (final level in ['error', 'fatal']) {
      test('mapped $level preserves the spanless abort summary', () async {
        final entry = write('src/main.rs', 'fn main() {}\n');
        final result = await RustCodeAnalyzer(
          transport: _DiagnosticTransport((job) => [
            {
              r'$message_type': 'diagnostic',
              'message': 'source error',
              'level': level,
              'spans': [
                {
                  'file_name': job.entryPath,
                  'byte_start': 0,
                  'byte_end': 2,
                  'is_primary': true,
                },
              ],
            },
            {
              r'$message_type': 'diagnostic',
              'message': 'aborting due to 1 previous error',
              'level': 'error',
              'spans': <Object>[],
            },
          ]),
        ).analyze(_request(project: project.path, active: entry));
        expect(result.unavailableReason, isNull);
        expect(
          result.diagnostics.single.severity,
          CodeDiagnosticSeverity.error,
        );
      });
    }

    test('a missing compiler is unavailable, never clean', () async {
      final entry = write('src/main.rs', 'fn main() {}\n');
      final result = await RustCodeAnalyzer(
        rustcPath: p.join(project.path, 'no-such-rustc'),
      ).analyze(_request(project: project.path, active: entry));
      expect(result.diagnostics, isEmpty);
      expect(result.unavailableReason, contains('编译器'));
    });

    test(
      'a hanging transport times out with an explicit reason',
      () async {
        final entry = write('src/main.rs', 'fn main() {}\n');
        final result = await RustCodeAnalyzer(
          transport: _HangingTransport(),
          timeout: const Duration(milliseconds: 200),
        ).analyze(_request(project: project.path, active: entry));
        expect(result.diagnostics, isEmpty);
        expect(result.unavailableReason, isNotNull);
      },
      timeout: const Timeout(Duration(seconds: 30)),
    );

    test('truncated compiler output is unavailable, not partial', () async {
      final entry = write('src/main.rs', 'fn main() {}\n');
      final result = await RustCodeAnalyzer(
        transport: _RecordingTransport(
          const RustAnalysisOutput(
            exitCode: 0,
            diagnosticsJsonl: '',
            truncated: true,
          ),
        ),
      ).analyze(_request(project: project.path, active: entry));
      expect(result.diagnostics, isEmpty);
      expect(result.unavailableReason, contains('上限'));
    });

    test('unparsable output is unavailable instead of clean', () async {
      final entry = write('src/main.rs', 'fn main() {}\n');
      final result = await RustCodeAnalyzer(
        transport: _RecordingTransport(
          const RustAnalysisOutput(
            exitCode: 1,
            diagnosticsJsonl: 'segmentation fault',
          ),
        ),
      ).analyze(_request(project: project.path, active: entry));
      expect(result.diagnostics, isEmpty);
      expect(result.unavailableReason, isNotNull);
    });

    test('an internal compiler error is unavailable', () async {
      final entry = write('src/main.rs', 'fn main() {}\n');
      final result = await RustCodeAnalyzer(
        transport: _RecordingTransport(
          RustAnalysisOutput(
            exitCode: 101,
            diagnosticsJsonl: jsonEncode({
              'message': 'internal compiler error',
            }),
          ),
        ),
      ).analyze(_request(project: project.path, active: entry));
      expect(result.unavailableReason, contains('内部错误'));
    });

    test(
      'an empty well-formed stream from a clean compile is reported clean',
      () async {
        final entry = write('src/main.rs', 'fn main() {}\n');
        final result = await RustCodeAnalyzer(
          transport: _RecordingTransport(),
        ).analyze(_request(project: project.path, active: entry));
        expect(result.diagnostics, isEmpty);
        expect(result.unavailableReason, isNull);
      },
    );
  });

  group('manifest gates', () {
    test('external dependencies are refused instead of faked', () async {
      write('Cargo.toml', '''
[package]
name = "demo"
edition = "2021"

[dependencies]
serde = "1"
''');
      final entry = write('src/main.rs', 'fn main() {}\n');
      final result = await RustCodeAnalyzer(
        transport: _RecordingTransport(),
      ).analyze(_request(project: project.path, active: entry));
      expect(result.diagnostics, isEmpty);
      expect(result.unavailableReason, contains('外部依赖'));
    });

    test('a build script is refused instead of run', () async {
      write('Cargo.toml', '[package]\nname = "demo"\nedition = "2021"\n');
      write('build.rs', 'fn main() { println!("cargo:rustc-env=KEY=1"); }\n');
      final entry = write('src/main.rs', 'fn main() {}\n');
      final transport = _RecordingTransport();
      final result = await RustCodeAnalyzer(
        transport: transport,
      ).analyze(_request(project: project.path, active: entry));
      expect(result.diagnostics, isEmpty);
      expect(result.unavailableReason, contains('build.rs'));
      expect(transport.job, isNull, reason: 'nothing should be compiled');
    });

    test('an empty [dependencies] table is not a dependency', () async {
      write('Cargo.toml', '''
[package]
name = "demo"
edition = "2021"

[dependencies]
''');
      final entry = write('src/main.rs', 'fn main() {}\n');
      final transport = _RecordingTransport();
      final result = await RustCodeAnalyzer(
        transport: transport,
      ).analyze(_request(project: project.path, active: entry));
      expect(result.unavailableReason, isNull);
      expect(transport.job, isNotNull);
    });
  });

  group('crate target selection', () {
    test('a library root is analyzed as a lib, not a bin', () async {
      write('Cargo.toml', '[package]\nname = "demo"\nedition = "2021"\n');
      final lib = write('src/lib.rs', 'pub fn util() -> i32 { 1 }\n');
      final transport = _RecordingTransport();
      await RustCodeAnalyzer(
        transport: transport,
      ).analyze(_request(project: project.path, active: lib));
      expect(transport.job!.crateType, 'lib');
      expect(transport.job!.crateName, 'demo');
    });

    test('a main root is analyzed as a bin', () async {
      write('Cargo.toml', '[package]\nname = "demo"\nedition = "2021"\n');
      final main = write('src/main.rs', 'fn main() {}\n');
      final transport = _RecordingTransport();
      await RustCodeAnalyzer(
        transport: transport,
      ).analyze(_request(project: project.path, active: main));
      expect(transport.job!.crateType, 'bin');
    });

    test(
      'a module file is analyzed through the target that declares it',
      () async {
        write('Cargo.toml', '[package]\nname = "demo"\nedition = "2021"\n');
        write('src/main.rs', 'mod helper;\nfn main() { helper::run(); }\n');
        final helper = write('src/helper.rs', 'pub fn run() {}\n');
        final transport = _RecordingTransport();
        await RustCodeAnalyzer(
          transport: transport,
        ).analyze(_request(project: project.path, active: helper));
        expect(
          p.normalize(transport.job!.entryPath),
          p.normalize(p.join(transport.job!.mirrorRoot, 'src', 'main.rs')),
        );
        expect(transport.job!.crateType, 'bin');
      },
    );

    test(
      'an unreferenced standalone file in no project analyzes itself',
      () async {
        final entry = write('scratch.rs', 'fn main() {}\n');
        final transport = _RecordingTransport();
        await RustCodeAnalyzer(
          transport: transport,
        ).analyze(_request(project: project.path, active: entry));
        expect(transport.job!.crateType, 'bin');
        expect(
          p.normalize(transport.job!.entryPath),
          p.normalize(p.join(transport.job!.mirrorRoot, 'scratch.rs')),
        );
      },
    );

    test('a manifest edition overrides the default', () async {
      write('Cargo.toml', '[package]\nname = "demo"\nedition = "2018"\n');
      final entry = write('src/main.rs', 'fn main() {}\n');
      final transport = _RecordingTransport();
      await RustCodeAnalyzer(
        transport: transport,
      ).analyze(_request(project: project.path, active: entry));
      expect(transport.job!.edition, '2018');
      expect(transport.job!.arguments, contains('--edition=2018'));
    });
  });

  group('mirror', () {
    test('overlays unsaved buffers and leaves the project untouched', () async {
      write('Cargo.toml', '[package]\nname = "demo"\nedition = "2021"\n');
      final main = write('src/main.rs', 'mod helper;\nfn main() {}\n');
      final helper = write('src/helper.rs', 'pub fn run() {}\n');
      final before = snapshotTree();
      final transport = _RecordingTransport();
      await RustCodeAnalyzer(transport: transport).analyze(
        _request(
          project: project.path,
          active: main,
          documents: [
            (
              path: main,
              text: 'mod helper;\nfn main() { helper::unsaved_only(); }\n',
              revision: 2,
            ),
            (path: helper, text: 'pub fn run() {}\n// unsaved\n', revision: 1),
          ],
        ),
      );
      expect(transport.mirrorContents['src/main.rs'], contains('unsaved_only'));
      expect(transport.mirrorContents['src/helper.rs'], contains('// unsaved'));
      expect(transport.mirrorFiles, contains('Cargo.toml'));
      expect(snapshotTree(), before, reason: 'project files must not change');
      expect(
        Directory(transport.job!.mirrorRoot).existsSync(),
        isFalse,
        reason: 'the temporary mirror is cleaned up',
      );
    });

    test('a new unsaved file that is not on disk is still analyzed', () async {
      final main = write('src/main.rs', 'fn main() {}\n');
      final transport = _RecordingTransport();
      await RustCodeAnalyzer(transport: transport).analyze(
        _request(
          project: project.path,
          active: main,
          documents: [
            (path: main, text: 'mod fresh;\nfn main() {}\n', revision: 1),
            (
              path: p.join(project.path, 'src', 'fresh.rs'),
              text: 'pub fn fresh() {}\n',
              revision: 1,
            ),
          ],
        ),
      );
      expect(transport.mirrorFiles, contains('src/fresh.rs'));
      expect(transport.mirrorContents['src/fresh.rs'], contains('fresh'));
    });

    test('generated directories are not mirrored', () async {
      final main = write('src/main.rs', 'fn main() {}\n');
      write('target/debug/junk.rs', 'fn junk() {}\n');
      write('.git/config', '[core]\n');
      final transport = _RecordingTransport();
      await RustCodeAnalyzer(
        transport: transport,
      ).analyze(_request(project: project.path, active: main));
      expect(transport.mirrorFiles, isNot(contains('target/debug/junk.rs')));
      expect(transport.mirrorFiles, isNot(contains('.git/config')));
    });

    test(
      'an oversized project is unavailable instead of partially analyzed',
      () async {
        final main = write('src/main.rs', 'fn main() {}\n');
        write('src/other.rs', 'pub fn other() {}\n');
        final result = await RustCodeAnalyzer(
          transport: _RecordingTransport(),
          maxFiles: 1,
        ).analyze(_request(project: project.path, active: main));
        expect(result.diagnostics, isEmpty);
        expect(result.unavailableReason, contains('超出'));
      },
    );
  });

  group('real compiler', () {
    test(
      'a valid program is clean, does not run, and does not rewrite sources',
      () async {
        final marker = p.join(project.path, 'PROGRAM_RAN');
        // Forward slashes keep the Rust path literal valid, so if analysis ever
        // executed `main` the marker really would be created and this test
        // would fail instead of passing vacuously.
        final rustPath = marker.replaceAll(r'\', '/');
        final main = write('src/main.rs', '''
fn main() {
    std::fs::write("$rustPath", "ran").unwrap();
    println!("this must never appear");
    let mut child = std::process::Command::new("cmd").spawn().unwrap();
    let _ = child.wait();
}
''');
        final before = snapshotTree();
        final result = await RustCodeAnalyzer(
          rustcPath: _rustc.path,
        ).analyze(_request(project: project.path, active: main));
        expect(result.unavailableReason, isNull);
        expect(result.diagnostics, isEmpty);
        expect(
          File(marker).existsSync(),
          isFalse,
          reason: 'analysis must not execute the program',
        );
        expect(
          snapshotTree(),
          before,
          reason: 'analysis must not write sources',
        );
        expect(
          Directory(
            project.path,
          ).listSync().whereType<File>().map((f) => p.basename(f.path)),
          isNot(contains('libmain.rmeta')),
          reason: 'metadata output must stay in the temporary mirror',
        );
      },
      skip: _skipReason,
      timeout: const Timeout(Duration(minutes: 2)),
    );

    test(
      'a type error maps to the exact UTF-16 range in a CRLF file',
      () async {
        final main = write(
          'src/main.rs',
          'fn main() {\r\n    let y: i32 = "bad";\r\n}\r\n',
        );
        final result = await RustCodeAnalyzer(
          rustcPath: _rustc.path,
        ).analyze(_request(project: project.path, active: main));
        expect(result.unavailableReason, isNull);
        final diagnostic = result.diagnostics.singleWhere(
          (d) => d.code == 'E0308',
        );
        final text = File(main).readAsStringSync();
        expect(
          text.substring(diagnostic.startOffset, diagnostic.endOffset),
          '"bad"',
        );
        expect(diagnostic.filePath, p.normalize(main));
        expect(diagnostic.severity, CodeDiagnosticSeverity.error);
      },
      skip: _skipReason,
      timeout: const Timeout(Duration(minutes: 2)),
    );

    test(
      'an emoji before the error does not shift the squiggle',
      () async {
        final main = write(
          'src/main.rs',
          'fn main() {\n    let s = "😀🎉";\n    let y: i32 = "bad";\n}\n',
        );
        final result = await RustCodeAnalyzer(
          rustcPath: _rustc.path,
        ).analyze(_request(project: project.path, active: main));
        final diagnostic = result.diagnostics.singleWhere(
          (d) => d.code == 'E0308',
        );
        final text = File(main).readAsStringSync();
        expect(
          text.substring(diagnostic.startOffset, diagnostic.endOffset),
          '"bad"',
        );
        expect(diagnostic.startOffset, text.indexOf('"bad"'));
        expect(
          diagnostic.startOffset,
          isNot(byteIndexOf(text, '"bad"')),
          reason: 'byte and UTF-16 offsets must not be confused',
        );
      },
      skip: _skipReason,
      timeout: const Timeout(Duration(minutes: 2)),
    );

    test(
      'an unsaved module edit is analyzed, and the disk copy is untouched',
      () async {
        final main = write(
          'src/main.rs',
          'mod helper;\nfn main() { helper::run(); }\n',
        );
        final helper = write('src/helper.rs', 'pub fn run() {}\n');
        final before = File(helper).readAsStringSync();
        const unsaved = 'pub fn run() {\n    let v: u8 = 300;\n}\n';
        final result = await RustCodeAnalyzer(rustcPath: _rustc.path).analyze(
          _request(
            project: project.path,
            active: helper,
            documents: [
              (
                path: main,
                text: 'mod helper;\nfn main() { helper::run(); }\n',
                revision: 1,
              ),
              (path: helper, text: unsaved, revision: 2),
            ],
          ),
        );
        expect(result.unavailableReason, isNull);
        final diagnostic = result.diagnostics.singleWhere(
          (d) => d.code == 'overflowing_literals',
        );
        expect(diagnostic.filePath, p.normalize(helper));
        expect(
          unsaved.substring(diagnostic.startOffset, diagnostic.endOffset),
          '300',
        );
        expect(File(helper).readAsStringSync(), before);
      },
      skip: _skipReason,
      timeout: const Timeout(Duration(minutes: 2)),
    );

    test(
      'a library target without main is clean instead of E0601',
      () async {
        write('Cargo.toml', '[package]\nname = "demo"\nedition = "2021"\n');
        final lib = write('src/lib.rs', 'pub fn util() -> i32 { 1 }\n');
        final result = await RustCodeAnalyzer(
          rustcPath: _rustc.path,
        ).analyze(_request(project: project.path, active: lib));
        expect(result.unavailableReason, isNull);
        expect(result.diagnostics, isEmpty);
      },
      skip: _skipReason,
      timeout: const Timeout(Duration(minutes: 2)),
    );

    test(
      'warnings are surfaced with their own severity',
      () async {
        final main = write(
          'src/main.rs',
          'fn main() {\n    let unused = 1;\n}\n',
        );
        final result = await RustCodeAnalyzer(
          rustcPath: _rustc.path,
        ).analyze(_request(project: project.path, active: main));
        expect(result.unavailableReason, isNull);
        final warning = result.diagnostics.singleWhere(
          (d) => d.code == 'unused_variables',
        );
        expect(warning.severity, CodeDiagnosticSeverity.warning);
        final text = File(main).readAsStringSync();
        expect(
          text.substring(warning.startOffset, warning.endOffset),
          'unused',
        );
      },
      skip: _skipReason,
      timeout: const Timeout(Duration(minutes: 2)),
    );

    test(
      'a remapped diagnostic path still resolves to the real project file',
      () async {
        // The compiler reports the remapped prefix with the separator it was
        // given and the relative tail with forward slashes, so the mapping must
        // not depend on one exact spelling.
        final main = write(
          'src/main.rs',
          'fn main() {\n    let y: i32 = "bad";\n}\n',
        );
        final result = await RustCodeAnalyzer(
          rustcPath: _rustc.path,
        ).analyze(_request(project: project.path, active: main));
        expect(
          result.unavailableReason,
          isNull,
          reason: 'a project diagnostic must never be treated as foreign',
        );
        final diagnostic = result.diagnostics.singleWhere(
          (d) => d.code == 'E0308',
        );
        expect(diagnostic.filePath, p.normalize(main));
        expect(p.isWithin(project.path, diagnostic.filePath), isTrue);
      },
      skip: _skipReason,
      timeout: const Timeout(Duration(minutes: 2)),
    );

    test(
      'a project in a non-ASCII directory maps offsets by UTF-8 bytes',
      () async {
        final local = Directory(p.join(project.path, '本地项目'))..createSync();
        final main = p.join(local.path, 'main.rs');
        const source = 'fn main() {\n    let y: i32 = "坏";\n}\n';
        File(main).writeAsStringSync(source);
        final result = await RustCodeAnalyzer(
          rustcPath: _rustc.path,
        ).analyze(_request(project: project.path, active: main));
        expect(result.unavailableReason, isNull);
        final diagnostic = result.diagnostics.singleWhere(
          (d) => d.code == 'E0308',
        );
        expect(diagnostic.filePath, p.normalize(main));
        expect(
          source.substring(diagnostic.startOffset, diagnostic.endOffset),
          '"坏"',
          reason: 'multi-byte paths must not shift the reported range',
        );
      },
      skip: _skipReason,
      timeout: const Timeout(Duration(minutes: 2)),
    );
  });
}
