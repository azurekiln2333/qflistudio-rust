import 'dart:convert';

import 'package:path/path.dart' as p;

/// One Cargo target decoded from `cargo metadata`.
///
/// The manifest/package/target identity comes from Cargo itself; callers must
/// not invent a target name from a file name. Targets that own an entry source
/// but cannot be executed by `cargo run` (library, test, bench, build script,
/// or a library-shaped example) are retained so selection can reject them
/// explicitly instead of pretending the source is unregistered.
class CargoTarget {
  const CargoTarget({
    required this.manifestPath,
    required this.packageName,
    required this.targetName,
    required this.srcPath,
    required this.kinds,
    required this.crateTypes,
    required this.isRunnable,
    required this.isExample,
  });

  final String manifestPath;
  final String packageName;
  final String targetName;
  final String srcPath;

  /// The raw `kind` list (`bin`, `lib`, `example`, `test`, ...).
  final List<String> kinds;

  /// The raw `crate_types` list (`bin`, `lib`, `proc-macro`, ...).
  final List<String> crateTypes;

  /// `true` when `cargo run` can execute this target: a binary, or an example
  /// that actually builds a binary crate.
  final bool isRunnable;

  /// `true` when the run selector must be `--example` rather than `--bin`.
  final bool isExample;

  /// The explicit selector flag for a runnable target.
  String get kindFlag => isExample ? '--example' : '--bin';

  /// Short identity used in diagnostics.
  String get label =>
      '${isExample
          ? 'example'
          : kinds.isEmpty
          ? 'target'
          : kinds.first} '
      '$targetName ($packageName)';
}

/// Outcome of matching an entry source against Cargo's target list.
sealed class CargoTargetLookup {
  const CargoTargetLookup();
}

/// Exactly one runnable target owns the requested source.
class CargoTargetMatch extends CargoTargetLookup {
  const CargoTargetMatch(this.target);

  final CargoTarget target;
}

/// Cargo metadata is valid and no target at all owns the source.
///
/// The caller falls back to the standalone rustc route; the source must be
/// independently compilable and does not inherit external Cargo dependencies.
class CargoTargetUnregistered extends CargoTargetLookup {
  const CargoTargetUnregistered();
}

/// Cargo metadata is valid but the source belongs to a non-runnable target
/// (library, test, bench, build script, library-shaped example).
///
/// The caller must fail with diagnostics; it must not fall back to rustc and
/// must never run a different source.
class CargoTargetNotRunnable extends CargoTargetLookup {
  const CargoTargetNotRunnable(this.targets);

  final List<CargoTarget> targets;
}

/// Cargo metadata is valid but several runnable targets share the source.
class CargoTargetAmbiguous extends CargoTargetLookup {
  const CargoTargetAmbiguous(this.targets);

  final List<CargoTarget> targets;
}

/// Decodes `cargo metadata --no-deps --format-version 1` output.
///
/// Throws [FormatException] for malformed JSON or an unexpected schema shape.
/// The caller turns that into an actionable diagnostic; malformed metadata
/// must never be treated as "source is unregistered" and must never run a
/// different file.
List<CargoTarget> decodeCargoTargets(String metadataJson) {
  final Object? root;
  try {
    root = jsonDecode(metadataJson);
  } on FormatException {
    throw const FormatException('cargo metadata did not return valid JSON');
  }
  if (root is! Map<String, Object?>) {
    throw const FormatException('cargo metadata did not return a JSON object');
  }
  final packages = root['packages'];
  if (packages is! List) {
    throw const FormatException('cargo metadata omitted the package list');
  }
  final targets = <CargoTarget>[];
  for (final package in packages) {
    if (package is! Map<String, Object?>) {
      throw const FormatException(
        'cargo metadata returned a non-object package',
      );
    }
    final packageName = package['name'];
    final manifestPath = package['manifest_path'];
    if (packageName is! String || manifestPath is! String) {
      throw const FormatException(
        'cargo metadata returned a package without a name or manifest path',
      );
    }
    final packageTargets = package['targets'];
    if (packageTargets is! List) {
      throw const FormatException(
        'cargo metadata returned a package without a target list',
      );
    }
    for (final target in packageTargets) {
      if (target is! Map<String, Object?>) {
        throw const FormatException(
          'cargo metadata returned a non-object target',
        );
      }
      final name = target['name'];
      final srcPath = target['src_path'];
      if (name is! String || srcPath is! String) {
        throw const FormatException(
          'cargo metadata returned a target without a name or source path',
        );
      }
      final kinds = _stringList(target['kind'], 'target kind');
      final crateTypes = _stringList(target['crate_types'], 'crate types');
      final isBinKinds = kinds.contains('bin');
      final isExampleKinds = kinds.contains('example');
      // A library-shaped example has no binary crate to execute; only
      // examples whose crate_types include `bin` can be run.
      final exampleRunnable = isExampleKinds && crateTypes.contains('bin');
      final runnable = isBinKinds || exampleRunnable;
      targets.add(
        CargoTarget(
          manifestPath: manifestPath,
          packageName: packageName,
          targetName: name,
          srcPath: srcPath,
          kinds: kinds,
          crateTypes: crateTypes,
          // `example` wins for a target advertising both, because the example
          // selector is the more specific request.
          isExample: isExampleKinds,
          isRunnable: runnable,
        ),
      );
    }
  }
  return targets;
}

List<String> _stringList(Object? value, String label) {
  if (value is! List) {
    throw FormatException('cargo metadata returned $label that is not a list');
  }
  return value
      .map((entry) {
        if (entry is! String) {
          throw FormatException(
            'cargo metadata returned a non-string $label entry',
          );
        }
        return entry;
      })
      .toList(growable: false);
}

/// Selects the target that owns [entryFile] and reports its runnability.
CargoTargetLookup selectCargoTarget({
  required List<CargoTarget> targets,
  required String entryFile,
}) {
  final entry = p.normalize(p.absolute(entryFile));
  final owners = targets
      .where(
        (target) => p.equals(p.normalize(p.absolute(target.srcPath)), entry),
      )
      .toList(growable: false);
  if (owners.isEmpty) return const CargoTargetUnregistered();
  final runnable = owners.where((target) => target.isRunnable).toList();
  if (runnable.isEmpty) return CargoTargetNotRunnable(owners);
  if (runnable.length > 1) return CargoTargetAmbiguous(runnable);
  return CargoTargetMatch(runnable.single);
}

/// Actionable message for a source that Cargo knows but cannot run.
String cargoNotRunnableMessage(
  String relativeSource,
  List<CargoTarget> targets,
) {
  final owners = targets.map((target) => target.label).join(', ');
  return 'Cargo 项目中 $relativeSource 属于不可运行的目标（$owners）。'
      '只有 bin 或二进制 example 可以运行，未回退到其他入口。';
}

/// Actionable message for several runnable targets sharing one source.
String cargoAmbiguousMessage(String relativeSource, List<CargoTarget> targets) {
  final owners = targets.map((target) => target.label).join(', ');
  return 'Cargo 项目中 $relativeSource 对应多个可运行目标（$owners）。'
      '请在 Cargo.toml 中声明唯一的显式目标后重试。';
}

/// Builds the `cargo run` argument list for [target].
///
/// The manifest path binds the run to the package that owns the source, and the
/// package name disambiguates workspaces that reuse a target name.
List<String> cargoRunArguments(String manifestPath, CargoTarget target) =>
    <String>[
      'run',
      '--manifest-path',
      manifestPath,
      '--package',
      target.packageName,
      target.kindFlag,
      target.targetName,
    ];
