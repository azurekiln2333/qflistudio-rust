import 'dart:convert';

import 'package:flutter/services.dart';

/// Asset holding the hash-bound inventory of every authored Rust program.
const String rustNativeCatalogAsset = 'assets/content_rust/native_catalog.json';

/// Legacy single-architecture manifest asset. Only read when the package does
/// not ship the per-target manifest, matching [NativeMiriTarget.loadManifest].
const String rustNativeLegacyManifestAsset = 'assets/miri/manifest.json';

/// Which authored program a catalog case runs.
enum RustNativeCaseKind {
  example('example'),
  answer('answer');

  const RustNativeCaseKind(this.wireName);

  final String wireName;

  static RustNativeCaseKind parse(Object? value) {
    for (final kind in values) {
      if (kind.wireName == value) return kind;
    }
    throw FormatException('Unknown native catalog case kind: $value');
  }
}

/// One program the packaged engine must execute.
///
/// [source] and [sourceSha256] are bound together: the harness writes exactly
/// [source] and re-verifies the digest before running it, so a report can never
/// describe text that was not the authored text.
class RustNativeCatalogCase {
  const RustNativeCatalogCase({
    required this.id,
    required this.topicId,
    required this.kind,
    required this.runtime,
    required this.level,
    required this.entryFile,
    required this.source,
    required this.sourceSha256,
    required this.expectedExitCode,
    required this.expectedStdout,
    required this.stdoutAsserted,
    required this.files,
    required this.filesSha256,
    required this.bundleVerify,
  });

  final String id;
  final int topicId;
  final RustNativeCaseKind kind;

  /// Authored runtime label. Retained for reporting only; the harness must never
  /// skip a case because of it.
  final String runtime;
  final String level;
  final String entryFile;
  final String source;
  final String sourceSha256;
  final int expectedExitCode;

  /// Exact expected stdout for examples. Null for answers, which have no
  /// authored expectation; [stdoutAsserted] keeps that gap explicit.
  final String? expectedStdout;
  final bool stdoutAsserted;

  /// Complete attached Cargo bundle, or null for a standalone program.
  final Map<String, String>? files;
  final Map<String, String>? filesSha256;

  /// Authored Cargo operation (`run`/`build`/`test`); Cargo-only evidence.
  final String? bundleVerify;

  bool get isBundle => files != null;

  factory RustNativeCatalogCase.fromJson(Object? value) {
    if (value is! Map) {
      throw const FormatException('Native catalog case must be an object');
    }
    final id = value['id'];
    if (id is! String || id.isEmpty) {
      throw const FormatException('Native catalog case requires an id');
    }
    final topicId = value['topicId'];
    if (topicId is! int || topicId <= 0) {
      throw FormatException(
        'Native catalog case $id requires a positive topicId',
      );
    }
    final runtime = value['runtime'];
    if (runtime is! String || runtime.isEmpty) {
      throw FormatException('Native catalog case $id requires a runtime label');
    }
    final level = value['level'];
    if (level is! String || level.isEmpty) {
      throw FormatException('Native catalog case $id requires a level');
    }
    final entryFile = value['entryFile'];
    if (entryFile is! String || entryFile.isEmpty) {
      throw FormatException('Native catalog case $id requires an entryFile');
    }
    final source = value['source'];
    if (source is! String || source.trim().isEmpty) {
      throw FormatException('Native catalog case $id requires source text');
    }
    final sourceSha256 = value['sourceSha256'];
    if (sourceSha256 is! String || !_sha256Pattern.hasMatch(sourceSha256)) {
      throw FormatException(
        'Native catalog case $id requires a SHA-256 digest',
      );
    }
    if (sha256Hex(source) != sourceSha256) {
      throw FormatException(
        'Native catalog case $id digest does not match its source',
      );
    }
    final expectedExitCode = value['expectedExitCode'];
    if (expectedExitCode is! int) {
      throw FormatException('Native catalog case $id requires an exit code');
    }
    final stdoutAsserted = value['stdoutAsserted'];
    if (stdoutAsserted is! bool) {
      throw FormatException(
        'Native catalog case $id requires an explicit stdoutAsserted flag',
      );
    }
    final expectedStdout = value['expectedStdout'];
    if (stdoutAsserted && expectedStdout is! String) {
      throw FormatException(
        'Native catalog case $id asserts stdout but has no expectation',
      );
    }
    if (!stdoutAsserted && expectedStdout != null) {
      throw FormatException(
        'Native catalog case $id has an expectation it does not assert',
      );
    }
    final files = _files(value['files'], id);
    final filesSha256 = _files(value['filesSha256'], id);
    if ((files == null) != (filesSha256 == null)) {
      throw FormatException(
        'Native catalog case $id must bind files and their digests together',
      );
    }
    if (files != null) {
      if (!files.containsKey('Cargo.toml') ||
          !files.containsKey('src/main.rs')) {
        throw FormatException(
          'Native catalog case $id requires Cargo.toml and src/main.rs',
        );
      }
      if (files['src/main.rs'] != source) {
        throw FormatException(
          'Native catalog case $id bundle entry differs from its source',
        );
      }
      if (entryFile != 'src/main.rs') {
        throw FormatException(
          'Native catalog case $id bundle must run src/main.rs',
        );
      }
      if (files.keys.any((name) => !filesSha256!.containsKey(name))) {
        throw FormatException(
          'Native catalog case $id has unhashed bundle files',
        );
      }
      for (final entry in filesSha256!.entries) {
        if (!files.containsKey(entry.key)) {
          throw FormatException(
            'Native catalog case $id hashes a missing bundle file',
          );
        }
        if (sha256Hex(files[entry.key]!) != entry.value) {
          throw FormatException(
            'Native catalog case $id bundle digest differs for ${entry.key}',
          );
        }
      }
    } else if (entryFile != 'main.rs') {
      throw FormatException(
        'Native catalog case $id standalone entry must be main.rs',
      );
    }
    final bundleVerify = value['bundleVerify'];
    if (files != null && bundleVerify is! String) {
      throw FormatException(
        'Native catalog case $id bundle requires its Cargo operation',
      );
    }
    if (files == null && bundleVerify != null) {
      throw FormatException(
        'Native catalog case $id is not a bundle but declares an operation',
      );
    }
    final kind = RustNativeCaseKind.parse(value['kind']);
    if (kind == RustNativeCaseKind.answer && stdoutAsserted) {
      throw FormatException(
        'Native catalog answer $id cannot assert an unauthored stdout',
      );
    }
    return RustNativeCatalogCase(
      id: id,
      topicId: topicId,
      kind: kind,
      runtime: runtime,
      level: level,
      entryFile: entryFile,
      source: source,
      sourceSha256: sourceSha256,
      expectedExitCode: expectedExitCode,
      expectedStdout: expectedStdout as String?,
      stdoutAsserted: stdoutAsserted,
      files: files == null ? null : Map.unmodifiable(files),
      filesSha256: filesSha256 == null ? null : Map.unmodifiable(filesSha256),
      bundleVerify: bundleVerify as String?,
    );
  }
}

final _sha256Pattern = RegExp(r'^[a-f0-9]{64}$');

Map<String, String>? _files(Object? value, String id) {
  if (value == null) return null;
  if (value is! Map) {
    throw FormatException('Native catalog case $id files must be an object');
  }
  final files = <String, String>{};
  for (final entry in value.entries) {
    final name = entry.key;
    final source = entry.value;
    if (name is! String || source is! String) {
      throw FormatException(
        'Native catalog case $id has an invalid file entry',
      );
    }
    files[name] = source;
  }
  if (files.isEmpty) {
    throw FormatException('Native catalog case $id has an empty bundle');
  }
  return files;
}

/// The complete native execution inventory plus its input identity.
class RustNativeCatalog {
  RustNativeCatalog({
    required this.schemaVersion,
    required this.guestTarget,
    required this.examples,
    required this.answers,
    required this.bundleCount,
    required this.runCount,
    required this.sourceSha256,
    required List<RustNativeCatalogCase> cases,
  }) : cases = List.unmodifiable(cases);

  static const int supportedSchemaVersion = 1;

  final int schemaVersion;

  /// Interpreted guest target the packaged adapter pins.
  final String guestTarget;
  final int examples;
  final int answers;
  final int bundleCount;
  final int runCount;

  /// SHA-256 of each authored `topics_*.json` input.
  final Map<String, String> sourceSha256;
  final List<RustNativeCatalogCase> cases;

  Iterable<String> get expectedIds => cases.map((entry) => entry.id);

  Iterable<RustNativeCatalogCase> get bundledCases =>
      cases.where((entry) => entry.isBundle);

  RustNativeCatalogCase? byId(String id) {
    for (final entry in cases) {
      if (entry.id == id) return entry;
    }
    return null;
  }

  /// Case ids the report never executed. Missing cases are incomplete, never
  /// passes.
  List<String> missingIds(Iterable<String> executed) {
    final done = executed.toSet();
    return [
      for (final entry in cases)
        if (!done.contains(entry.id)) entry.id,
    ];
  }

  factory RustNativeCatalog.fromJson(Object? value) {
    if (value is! Map) {
      throw const FormatException('Native catalog must be an object');
    }
    final schemaVersion = value['schemaVersion'];
    if (schemaVersion != supportedSchemaVersion) {
      throw FormatException(
        'Unsupported native catalog schema: $schemaVersion',
      );
    }
    final engine = value['engine'];
    if (engine is! Map) {
      throw const FormatException('Native catalog requires engine identity');
    }
    final guestTarget = engine['guestTarget'];
    if (guestTarget is! String || guestTarget.isEmpty) {
      throw const FormatException('Native catalog requires a guest target');
    }
    final catalog = value['catalog'];
    if (catalog is! Map) {
      throw const FormatException('Native catalog requires catalog counts');
    }
    final sourceSha256 = catalog['sourceSha256'];
    if (sourceSha256 is! Map || sourceSha256.isEmpty) {
      throw const FormatException('Native catalog requires input digests');
    }
    final digests = <String, String>{};
    for (final entry in sourceSha256.entries) {
      final name = entry.key;
      final digest = entry.value;
      if (name is! String ||
          digest is! String ||
          !_sha256Pattern.hasMatch(digest)) {
        throw const FormatException('Native catalog input digest is invalid');
      }
      digests[name] = digest;
    }
    final records = value['cases'];
    if (records is! List || records.isEmpty) {
      throw const FormatException('Native catalog requires cases');
    }
    final cases = <RustNativeCatalogCase>[];
    final seen = <String>{};
    for (final record in records) {
      final entry = RustNativeCatalogCase.fromJson(record);
      if (!seen.add(entry.id)) {
        throw FormatException('Duplicate native catalog case: ${entry.id}');
      }
      cases.add(entry);
    }
    final examples = cases
        .where((entry) => entry.kind == RustNativeCaseKind.example)
        .length;
    final answers = cases
        .where((entry) => entry.kind == RustNativeCaseKind.answer)
        .length;
    final bundles = cases.where((entry) => entry.isBundle).length;
    int declared(Object? name) {
      final count = catalog[name];
      if (count is! int || count < 0) {
        throw FormatException('Native catalog count $name is invalid');
      }
      return count;
    }

    if (declared('exampleCount') != examples ||
        declared('answerCount') != answers ||
        declared('bundleCount') != bundles ||
        declared('runCount') != cases.length) {
      throw const FormatException(
        'Native catalog counts disagree with its cases',
      );
    }
    final lessons = declared('lessonCount');
    if (lessons != examples || lessons != answers) {
      throw const FormatException(
        'Native catalog must pair every example with an answer',
      );
    }
    final topics = <int, Set<RustNativeCaseKind>>{};
    for (final entry in cases) {
      topics
          .putIfAbsent(entry.topicId, () => <RustNativeCaseKind>{})
          .add(entry.kind);
    }
    if (topics.length != lessons) {
      throw FormatException(
        'Native catalog covers ${topics.length} topics but declares $lessons',
      );
    }
    for (final entry in topics.entries) {
      if (entry.value.length != 2) {
        throw FormatException(
          'Native catalog topic ${entry.key} lacks an example or answer',
        );
      }
    }
    return RustNativeCatalog(
      schemaVersion: schemaVersion as int,
      guestTarget: guestTarget,
      examples: examples,
      answers: answers,
      bundleCount: bundles,
      runCount: cases.length,
      sourceSha256: Map.unmodifiable(digests),
      cases: cases,
    );
  }

  /// Loads and validates the packaged inventory.
  static Future<RustNativeCatalog> load({AssetBundle? bundle}) async {
    final source = await (bundle ?? rootBundle).loadString(
      rustNativeCatalogAsset,
    );
    return RustNativeCatalog.fromJson(jsonDecode(source));
  }
}

/// Records enough engine identity for a report to be checkable after the fact.
///
/// Values come from the packaged manifest plus the resolved [NativeMiriRuntime],
/// so a Windows or Android host can never be described as an OHOS device.
class RustNativeRuntimeIdentity {
  const RustNativeRuntimeIdentity({
    required this.platform,
    required this.architecture,
    required this.targetKey,
    required this.nativeHost,
    required this.targetNativeHosts,
    required this.guestTarget,
    required this.libraryPath,
    required this.sysrootPath,
    required this.backendPath,
    required this.manifestAsset,
    required this.manifestId,
    required this.manifestNativeHost,
    required this.rustVersion,
    required this.rustCommit,
    required this.manifestGuestTarget,
  });

  final String platform;

  /// CPU architecture of the host running the harness, e.g. `arm64` or `x64`.
  final String architecture;

  final String targetKey;
  final String nativeHost;
  final Set<String> targetNativeHosts;
  final String guestTarget;
  final String libraryPath;
  final String sysrootPath;
  final String? backendPath;
  final String manifestAsset;
  final String manifestId;
  final String manifestNativeHost;
  final String rustVersion;
  final String rustCommit;
  final String manifestGuestTarget;

  /// True only when the manifest actually describes the running target.
  bool get manifestMatchesTarget =>
      targetNativeHosts.contains(manifestNativeHost) &&
      manifestNativeHost == nativeHost &&
      manifestGuestTarget == guestTarget;

  Map<String, Object?> toJson() => {
    'platform': platform,
    'architecture': architecture,
    'targetKey': targetKey,
    'nativeHost': nativeHost,
    'targetNativeHosts': targetNativeHosts.toList()..sort(),
    'guestTarget': guestTarget,
    'libraryPath': libraryPath,
    'sysrootPath': sysrootPath,
    'backendPath': backendPath,
    'manifest': {
      'asset': manifestAsset,
      'id': manifestId,
      'nativeHost': manifestNativeHost,
      'rustVersion': rustVersion,
      'rustCommit': rustCommit,
      'guestTarget': manifestGuestTarget,
    },
  };
}

enum RustNativeCaseStatus {
  passed('passed'),
  failed('failed'),
  error('error');

  const RustNativeCaseStatus(this.wireName);

  final String wireName;
}

/// One executed case. [stdout] is the captured stdout exactly as reported.
class RustNativeCaseResult {
  const RustNativeCaseResult({
    required this.id,
    required this.topicId,
    required this.kind,
    required this.runtime,
    required this.entryFile,
    required this.sourceSha256,
    required this.status,
    required this.exitCode,
    required this.expectedExitCode,
    required this.stdoutAsserted,
    this.expectedStdout,
    required this.stdout,
    required this.stderr,
    required this.durationMs,
    this.detail,
  });

  final String id;
  final int topicId;
  final RustNativeCaseKind kind;
  final String runtime;
  final String entryFile;
  final String sourceSha256;
  final RustNativeCaseStatus status;
  final int exitCode;

  /// The catalog's authored expectation, echoed so the report is self-checking.
  final int expectedExitCode;
  final bool stdoutAsserted;
  final String? expectedStdout;

  final String stdout;
  final String stderr;
  final int durationMs;
  final String? detail;

  Map<String, Object?> toJson() => {
    'id': id,
    'topicId': topicId,
    'kind': kind.wireName,
    'runtime': runtime,
    'entryFile': entryFile,
    'sourceSha256': sourceSha256,
    'status': status.wireName,
    'exitCode': exitCode,
    'expectedExitCode': expectedExitCode,
    'stdoutAsserted': stdoutAsserted,
    if (expectedStdout != null) 'expectedStdout': expectedStdout,
    'durationMs': durationMs,
    'stdout': stdout,
    'stderr': stderr,
    if (detail != null) 'detail': detail,
  };
}

/// Machine-readable evidence for one device run of the whole inventory.
class RustNativeCatalogReport {
  RustNativeCatalogReport({
    required this.identity,
    required this.catalog,
    required List<RustNativeCaseResult> results,
    required List<String> missingIds,
    required this.interrupted,
    required this.startedAt,
    required this.finishedAt,
  }) : results = List.unmodifiable(results),
       _declaredMissingIds = List.unmodifiable(missingIds);

  static const int schemaVersion = 1;

  final RustNativeRuntimeIdentity identity;
  final RustNativeCatalog catalog;
  final List<RustNativeCaseResult> results;

  final List<String> _declaredMissingIds;

  /// Derive coverage from the evidence rather than trusting the caller's list.
  List<String> get missingIds => {
    ...catalog.missingIds(results.map((result) => result.id)),
    ..._declaredMissingIds,
  }.toList();

  /// True when the run stopped early (abort, timeout, unhandled error).
  final bool interrupted;
  final DateTime startedAt;
  final DateTime finishedAt;

  List<String> get failedIds => {
    for (final result in results)
      if (result.status != RustNativeCaseStatus.passed ||
          !_matchesCase(result) ||
          compareNativeStdout(
                testCase: catalog.byId(result.id)!,
                stdout: result.stdout,
                exitCode: result.exitCode,
              ) !=
              null)
        result.id,
  }.toList();

  List<String> get duplicateIds {
    final seen = <String>{};
    return {
      for (final result in results)
        if (!seen.add(result.id)) result.id,
    }.toList();
  }

  List<String> get unexpectedIds => {
    for (final result in results)
      if (catalog.byId(result.id) == null) result.id,
  }.toList();

  List<String> get mismatchedIds => {
    for (final result in results)
      if (!_matchesCase(result)) result.id,
  }.toList();

  bool _matchesCase(RustNativeCaseResult result) {
    final expected = catalog.byId(result.id);
    return expected != null &&
        result.topicId == expected.topicId &&
        result.kind == expected.kind &&
        result.runtime == expected.runtime &&
        result.entryFile == expected.entryFile &&
        result.sourceSha256 == expected.sourceSha256 &&
        result.expectedExitCode == expected.expectedExitCode &&
        result.stdoutAsserted == expected.stdoutAsserted &&
        result.expectedStdout == expected.expectedStdout &&
        result.durationMs >= 0;
  }

  /// Complete only when every inventoried case ran and nothing was skipped.
  /// A single missing or interrupted case keeps the whole run incomplete.
  bool get complete =>
      !interrupted &&
      results.length == catalog.runCount &&
      missingIds.isEmpty &&
      duplicateIds.isEmpty &&
      unexpectedIds.isEmpty &&
      mismatchedIds.isEmpty;

  bool get passed =>
      complete &&
      identity.manifestMatchesTarget &&
      identity.guestTarget == catalog.guestTarget &&
      failedIds.isEmpty;

  Map<String, Object?> toJson() => {
    'schemaVersion': schemaVersion,
    'complete': complete,
    'passed': passed,
    'interrupted': interrupted,
    'startedAt': startedAt.toUtc().toIso8601String(),
    'finishedAt': finishedAt.toUtc().toIso8601String(),
    'runtime': identity.toJson(),
    'catalog': {
      'asset': rustNativeCatalogAsset,
      'runCount': catalog.runCount,
      'exampleCount': catalog.examples,
      'answerCount': catalog.answers,
      'bundleCount': catalog.bundleCount,
      'guestTarget': catalog.guestTarget,
      'sourceSha256': catalog.sourceSha256,
    },
    'executed': results.length,
    'missingIds': missingIds,
    'duplicateIds': duplicateIds,
    'unexpectedIds': unexpectedIds,
    'mismatchedIds': mismatchedIds,
    'failedIds': failedIds,
    'cases': [for (final result in results) result.toJson()],
  };
}

/// Compare captured output with an expected stdout using the catalog's
/// CRLF-tolerant contract. Returns null on success or a human-readable reason.
String? compareNativeStdout({
  required RustNativeCatalogCase testCase,
  required String stdout,
  required int exitCode,
}) {
  if (exitCode != testCase.expectedExitCode) {
    return 'exit $exitCode != expected ${testCase.expectedExitCode}';
  }
  if (!testCase.stdoutAsserted) return null;
  // The audit captures native bytes before the terminal's LineSplitter. A
  // missing terminator or an extra blank line is therefore a real mismatch.
  final expected = testCase.expectedStdout!.replaceAll('\r\n', '\n');
  final actual = stdout.replaceAll('\r\n', '\n');
  if (actual == expected) return null;
  return 'stdout mismatch: expected ${jsonEncode(expected)} '
      'got ${jsonEncode(actual)}';
}

/// Dependency-free SHA-256 so the harness can bind authored bytes without
/// adding a package dependency. FIPS 180-4.
String sha256Hex(String input) => _sha256HexBytes(utf8.encode(input));

String _sha256HexBytes(List<int> bytes) {
  const mask = 0xFFFFFFFF;
  int rotateRight(int value, int bits) =>
      ((value >> bits) | (value << (32 - bits))) & mask;

  const k = <int>[
    0x428a2f98,
    0x71374491,
    0xb5c0fbcf,
    0xe9b5dba5,
    0x3956c25b,
    0x59f111f1,
    0x923f82a4,
    0xab1c5ed5,
    0xd807aa98,
    0x12835b01,
    0x243185be,
    0x550c7dc3,
    0x72be5d74,
    0x80deb1fe,
    0x9bdc06a7,
    0xc19bf174,
    0xe49b69c1,
    0xefbe4786,
    0x0fc19dc6,
    0x240ca1cc,
    0x2de92c6f,
    0x4a7484aa,
    0x5cb0a9dc,
    0x76f988da,
    0x983e5152,
    0xa831c66d,
    0xb00327c8,
    0xbf597fc7,
    0xc6e00bf3,
    0xd5a79147,
    0x06ca6351,
    0x14292967,
    0x27b70a85,
    0x2e1b2138,
    0x4d2c6dfc,
    0x53380d13,
    0x650a7354,
    0x766a0abb,
    0x81c2c92e,
    0x92722c85,
    0xa2bfe8a1,
    0xa81a664b,
    0xc24b8b70,
    0xc76c51a3,
    0xd192e819,
    0xd6990624,
    0xf40e3585,
    0x106aa070,
    0x19a4c116,
    0x1e376c08,
    0x2748774c,
    0x34b0bcb5,
    0x391c0cb3,
    0x4ed8aa4a,
    0x5b9cca4f,
    0x682e6ff3,
    0x748f82ee,
    0x78a5636f,
    0x84c87814,
    0x8cc70208,
    0x90befffa,
    0xa4506ceb,
    0xbef9a3f7,
    0xc67178f2,
  ];

  final hash = <int>[
    0x6a09e667,
    0xbb67ae85,
    0x3c6ef372,
    0xa54ff53a,
    0x510e527f,
    0x9b05688c,
    0x1f83d9ab,
    0x5be0cd19,
  ];

  final padded = List<int>.from(bytes)..add(0x80);
  while (padded.length % 64 != 56) {
    padded.add(0);
  }
  final bitLength = bytes.length * 8;
  for (var shift = 56; shift >= 0; shift -= 8) {
    padded.add((bitLength >> shift) & 0xFF);
  }

  final w = List<int>.filled(64, 0);
  for (var offset = 0; offset < padded.length; offset += 64) {
    for (var index = 0; index < 16; index++) {
      final base = offset + index * 4;
      w[index] =
          (padded[base] << 24) |
          (padded[base + 1] << 16) |
          (padded[base + 2] << 8) |
          padded[base + 3];
    }
    for (var index = 16; index < 64; index++) {
      final s0 =
          rotateRight(w[index - 15], 7) ^
          rotateRight(w[index - 15], 18) ^
          (w[index - 15] >> 3);
      final s1 =
          rotateRight(w[index - 2], 17) ^
          rotateRight(w[index - 2], 19) ^
          (w[index - 2] >> 10);
      w[index] = (w[index - 16] + s0 + w[index - 7] + s1) & mask;
    }
    var a = hash[0];
    var b = hash[1];
    var c = hash[2];
    var d = hash[3];
    var e = hash[4];
    var f = hash[5];
    var g = hash[6];
    var h = hash[7];
    for (var index = 0; index < 64; index++) {
      final s1 = rotateRight(e, 6) ^ rotateRight(e, 11) ^ rotateRight(e, 25);
      final ch = (e & f) ^ (~e & g);
      final temp1 = (h + s1 + ch + k[index] + w[index]) & mask;
      final s0 = rotateRight(a, 2) ^ rotateRight(a, 13) ^ rotateRight(a, 22);
      final maj = (a & b) ^ (a & c) ^ (b & c);
      final temp2 = (s0 + maj) & mask;
      h = g;
      g = f;
      f = e;
      e = (d + temp1) & mask;
      d = c;
      c = b;
      b = a;
      a = (temp1 + temp2) & mask;
    }
    hash[0] = (hash[0] + a) & mask;
    hash[1] = (hash[1] + b) & mask;
    hash[2] = (hash[2] + c) & mask;
    hash[3] = (hash[3] + d) & mask;
    hash[4] = (hash[4] + e) & mask;
    hash[5] = (hash[5] + f) & mask;
    hash[6] = (hash[6] + g) & mask;
    hash[7] = (hash[7] + h) & mask;
  }
  final buffer = StringBuffer();
  for (final value in hash) {
    buffer.write(value.toRadixString(16).padLeft(8, '0'));
  }
  return buffer.toString();
}
