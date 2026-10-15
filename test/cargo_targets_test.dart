import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;
import 'package:qfli_rust/cargo_targets.dart';

/// Focused decoding/selection tests for the Cargo metadata seam.
///
/// These run without a Rust toolchain, so they are the real regression for
/// selected-source routing: multiple binaries, custom target names/paths,
/// unregistered sources, non-runnable targets, ambiguity and malformed
/// metadata. The reported contract is "which Cargo identity runs", which is
/// exactly the behavior the old `cargo run` implementation got wrong.
void main() {
  const projectRoot = '/work/project';
  String absolute(String relative) => p.join(projectRoot, relative);

  Map<String, Object?> package({
    required String name,
    required List<Map<String, Object?>> targets,
    String? manifestPath,
  }) => {
    'name': name,
    'manifest_path': manifestPath ?? p.join(projectRoot, 'Cargo.toml'),
    'targets': targets,
  };

  Map<String, Object?> target({
    required String name,
    required String srcPath,
    required List<String> kind,
    List<String> crateTypes = const ['bin'],
  }) => {
    'name': name,
    'src_path': srcPath,
    'kind': kind,
    'crate_types': crateTypes,
  };

  String metadata(List<Map<String, Object?>> packages) =>
      jsonEncode({'packages': packages, 'target_directory': '/work/target'});

  group('decodeCargoTargets', () {
    test('keeps every target and marks only runnable kinds runnable', () {
      final targets = decodeCargoTargets(
        metadata([
          package(
            name: 'app',
            targets: [
              target(
                name: 'app',
                srcPath: absolute('src/main.rs'),
                kind: ['bin'],
              ),
              target(
                name: 'demo',
                srcPath: absolute('examples/demo.rs'),
                kind: ['example'],
              ),
              target(
                name: 'app',
                srcPath: absolute('src/lib.rs'),
                kind: ['lib'],
                crateTypes: ['lib'],
              ),
              target(
                name: 'it',
                srcPath: absolute('tests/it.rs'),
                kind: ['test'],
              ),
              target(
                name: 'bench',
                srcPath: absolute('benches/bench.rs'),
                kind: ['bench'],
              ),
              target(
                name: 'build',
                srcPath: absolute('build.rs'),
                kind: ['custom-build'],
              ),
            ],
          ),
        ]),
      );
      expect(targets.map((t) => t.targetName), [
        'app',
        'demo',
        'app',
        'it',
        'bench',
        'build',
      ]);
      expect(targets.where((t) => t.isRunnable).map((t) => t.targetName), [
        'app',
        'demo',
      ]);
    });

    test('a library-shaped example is not runnable', () {
      final targets = decodeCargoTargets(
        metadata([
          package(
            name: 'app',
            targets: [
              target(
                name: 'helper',
                srcPath: absolute('examples/helper.rs'),
                kind: ['example'],
                crateTypes: ['lib'],
              ),
            ],
          ),
        ]),
      );
      expect(targets.single.isRunnable, isFalse);
    });

    test('rejects metadata that is not a JSON object', () {
      expect(
        () => decodeCargoTargets('not-json'),
        throwsA(isA<FormatException>()),
      );
      expect(() => decodeCargoTargets('[]'), throwsA(isA<FormatException>()));
      expect(
        () => decodeCargoTargets('{"packages": "no"}'),
        throwsA(isA<FormatException>()),
      );
    });

    test('rejects a package without a manifest path', () {
      expect(
        () => decodeCargoTargets(
          jsonEncode({
            'packages': [
              {
                'name': 'app',
                'targets': [
                  target(
                    name: 'app',
                    srcPath: absolute('main.rs'),
                    kind: ['bin'],
                  ),
                ],
              },
            ],
          }),
        ),
        throwsA(isA<FormatException>()),
      );
    });

    test('a non-list target kind is a FormatException, not a TypeError', () {
      expect(
        () => decodeCargoTargets(
          jsonEncode({
            'packages': [
              {
                'name': 'app',
                'manifest_path': p.join(projectRoot, 'Cargo.toml'),
                'targets': [
                  {
                    'name': 'app',
                    'src_path': absolute('src/main.rs'),
                    'kind': 'bin',
                    'crate_types': ['bin'],
                  },
                ],
              },
            ],
          }),
        ),
        throwsA(isA<FormatException>()),
      );
    });

    test('a non-object package is a FormatException', () {
      expect(
        () => decodeCargoTargets(
          jsonEncode({
            'packages': ['not-a-package'],
          }),
        ),
        throwsA(isA<FormatException>()),
      );
    });
  });

  group('selectCargoTarget', () {
    test('matches an alternate binary by its custom name and path', () {
      final targets = decodeCargoTargets(
        metadata([
          package(
            name: 'app',
            targets: [
              target(
                name: 'app',
                srcPath: absolute('src/main.rs'),
                kind: ['bin'],
              ),
              target(
                name: 'tool',
                srcPath: absolute('src/tool.rs'),
                kind: ['bin'],
              ),
            ],
          ),
        ]),
      );
      final lookup = selectCargoTarget(
        targets: targets,
        entryFile: absolute('src/tool.rs'),
      );
      expect(lookup, isA<CargoTargetMatch>());
      final match = lookup as CargoTargetMatch;
      expect(match.target.targetName, 'tool');
      expect(match.target.packageName, 'app');
      expect(match.target.kindFlag, '--bin');
      expect(cargoRunArguments(match.target.manifestPath, match.target), [
        'run',
        '--manifest-path',
        p.join(projectRoot, 'Cargo.toml'),
        '--package',
        'app',
        '--bin',
        'tool',
      ]);
    });

    test('matches an example with the example selector', () {
      final targets = decodeCargoTargets(
        metadata([
          package(
            name: 'app',
            targets: [
              target(
                name: 'demo',
                srcPath: absolute('examples/demo.rs'),
                kind: ['example'],
              ),
            ],
          ),
        ]),
      );
      final match =
          selectCargoTarget(
                targets: targets,
                entryFile: absolute('examples/demo.rs'),
              )
              as CargoTargetMatch;
      expect(match.target.kindFlag, '--example');
      expect(cargoRunArguments(match.target.manifestPath, match.target), [
        'run',
        '--manifest-path',
        p.join(projectRoot, 'Cargo.toml'),
        '--package',
        'app',
        '--example',
        'demo',
      ]);
    });

    test('uses the package that owns the source in a workspace', () {
      final targets = decodeCargoTargets(
        metadata([
          package(
            name: 'first',
            manifestPath: p.join(projectRoot, 'first/Cargo.toml'),
            targets: [
              target(
                name: 'first',
                srcPath: absolute('first/src/main.rs'),
                kind: ['bin'],
              ),
            ],
          ),
          package(
            name: 'second',
            manifestPath: p.join(projectRoot, 'second/Cargo.toml'),
            targets: [
              target(
                name: 'second',
                srcPath: absolute('second/src/main.rs'),
                kind: ['bin'],
              ),
            ],
          ),
        ]),
      );
      final match =
          selectCargoTarget(
                targets: targets,
                entryFile: absolute('second/src/main.rs'),
              )
              as CargoTargetMatch;
      expect(match.target.packageName, 'second');
      expect(
        cargoRunArguments(match.target.manifestPath, match.target),
        contains(p.join(projectRoot, 'second/Cargo.toml')),
      );
    });

    test('a source no Cargo target owns is unregistered', () {
      final targets = decodeCargoTargets(
        metadata([
          package(
            name: 'app',
            targets: [
              target(
                name: 'app',
                srcPath: absolute('src/main.rs'),
                kind: ['bin'],
              ),
            ],
          ),
        ]),
      );
      expect(
        selectCargoTarget(targets: targets, entryFile: absolute('main2.rs')),
        isA<CargoTargetUnregistered>(),
      );
    });

    test('a source owned by two runnable targets is ambiguous', () {
      final targets = decodeCargoTargets(
        metadata([
          package(
            name: 'app',
            targets: [
              target(
                name: 'one',
                srcPath: absolute('src/main.rs'),
                kind: ['bin'],
              ),
              target(
                name: 'two',
                srcPath: absolute('src/main.rs'),
                kind: ['bin'],
              ),
            ],
          ),
        ]),
      );
      expect(
        selectCargoTarget(targets: targets, entryFile: absolute('src/main.rs')),
        isA<CargoTargetAmbiguous>(),
      );
    });

    test('a library source is registered but not runnable', () {
      final targets = decodeCargoTargets(
        metadata([
          package(
            name: 'app',
            targets: [
              target(
                name: 'app',
                srcPath: absolute('src/main.rs'),
                kind: ['bin'],
              ),
              target(
                name: 'app',
                srcPath: absolute('src/lib.rs'),
                kind: ['lib'],
                crateTypes: ['lib'],
              ),
            ],
          ),
        ]),
      );
      final lookup = selectCargoTarget(
        targets: targets,
        entryFile: absolute('src/lib.rs'),
      );
      // lib.rs is Cargo-known but cannot be run; it must be rejected rather
      // than silently replaced with src/main.rs through the rustc fallback.
      expect(lookup, isA<CargoTargetNotRunnable>());
      expect(
        (lookup as CargoTargetNotRunnable).targets.single.targetName,
        'app',
      );
    });

    test('a library-shaped example source is registered but not runnable', () {
      final targets = decodeCargoTargets(
        metadata([
          package(
            name: 'app',
            targets: [
              target(
                name: 'helper',
                srcPath: absolute('examples/helper.rs'),
                kind: ['example'],
                crateTypes: ['lib'],
              ),
            ],
          ),
        ]),
      );
      expect(
        selectCargoTarget(
          targets: targets,
          entryFile: absolute('examples/helper.rs'),
        ),
        isA<CargoTargetNotRunnable>(),
      );
    });

    test('matching is path-canonical, not string-equal', () {
      final targets = decodeCargoTargets(
        metadata([
          package(
            name: 'app',
            targets: [
              target(
                name: 'tool',
                srcPath: p.join(projectRoot, 'src', 'tool.rs'),
                kind: ['bin'],
              ),
            ],
          ),
        ]),
      );
      final lookup = selectCargoTarget(
        targets: targets,
        entryFile: p.join(projectRoot, 'src', '..', 'src', 'tool.rs'),
      );
      expect(lookup, isA<CargoTargetMatch>());
    });
  });
}
