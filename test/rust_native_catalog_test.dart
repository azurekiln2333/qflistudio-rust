import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:qfli_rust/rust_native_catalog.dart';

/// Serves catalog text without a real asset bundle.
class _MapBundle extends AssetBundle {
  _MapBundle(this.assets);

  final Map<String, String> assets;

  @override
  Future<ByteData> load(String key) async {
    final value = assets[key];
    if (value == null) throw StateError('missing asset $key');
    final bytes = utf8.encode(value);
    return ByteData.view(Uint8List.fromList(bytes).buffer);
  }

  @override
  Future<String> loadString(String key, {bool cache = true}) async {
    final value = assets[key];
    if (value == null) throw StateError('missing asset $key');
    return value;
  }
}

Map<String, Object?> _catalogJson() =>
    jsonDecode(File(rustNativeCatalogAsset).readAsStringSync())
        as Map<String, Object?>;

Map<String, Object?> _caseOf(Map<String, Object?> catalog, String id) {
  for (final entry in catalog['cases']! as List) {
    final record = entry as Map<String, Object?>;
    if (record['id'] == id) return record;
  }
  throw StateError('missing case $id');
}

Map<String, Object?> deepCopy(Map<String, Object?> value) =>
    jsonDecode(jsonEncode(value)) as Map<String, Object?>;

void main() {
  group('sha256Hex', () {
    test('matches the FIPS 180-4 vectors', () {
      expect(
        sha256Hex(''),
        'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
      );
      expect(
        sha256Hex('abc'),
        'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad',
      );
      expect(
        sha256Hex('abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq'),
        '248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1',
      );
      expect(
        sha256Hex('a' * 200),
        'c2a908d98f5df987ade41b5fce213067efbcc21ef2240212a41e54b5e7c28ae5',
      );
    });

    test('hashes UTF-8 bytes, not code units', () {
      // The packaged catalog is full of CJK source; the loader re-verifies every
      // digest, so a code-unit hashing bug fails the real-asset test below.
      expect(sha256Hex('\u4e2d\u6587'), hasLength(64));
      expect(sha256Hex('\u4e2d\u6587'), isNot(equals(sha256Hex(''))));
      expect(
        sha256Hex('\u4e2d\u6587'),
        sha256OfUtf8OfCjk,
        reason: 'UTF-8 encoding must match hashlib over the same bytes',
      );
    });
  });

  group('RustNativeCatalog', () {
    test('loads the packaged inventory with the complete paired set', () async {
      final bundle = _MapBundle({
        rustNativeCatalogAsset: File(rustNativeCatalogAsset).readAsStringSync(),
      });
      final catalog = await RustNativeCatalog.load(bundle: bundle);
      expect(catalog.schemaVersion, RustNativeCatalog.supportedSchemaVersion);
      expect(catalog.examples, 166);
      expect(catalog.answers, 166);
      expect(catalog.runCount, 332);
      expect(catalog.bundleCount, 23);
      expect(catalog.cases, hasLength(332));
      expect(catalog.sourceSha256.keys, contains('topics_001_084.json'));
      expect(catalog.sourceSha256.keys, contains('topics_085_166.json'));
      for (final digest in catalog.sourceSha256.values) {
        expect(digest, matches(RegExp(r'^[a-f0-9]{64}$')));
      }
      expect(catalog.expectedIds.toSet(), hasLength(332));
      expect(catalog.missingIds(catalog.expectedIds), isEmpty);
      expect(catalog.bundledCases, hasLength(23));
    });

    test('binds every case to its authored bytes and expectation', () {
      final catalog = RustNativeCatalog.fromJson(_catalogJson());
      for (final entry in catalog.cases) {
        expect(entry.sourceSha256, sha256Hex(entry.source));
        expect(entry.expectedExitCode, 0);
        if (entry.kind == RustNativeCaseKind.example) {
          expect(entry.stdoutAsserted, isTrue);
          expect(entry.expectedStdout, isNotNull);
          expect(entry.entryFile, entry.isBundle ? 'src/main.rs' : 'main.rs');
        } else {
          expect(
            entry.stdoutAsserted,
            isFalse,
            reason: 'answers have no authored stdout',
          );
          expect(entry.expectedStdout, isNull);
          expect(entry.isBundle, isFalse);
        }
      }
    });

    test('retains every runtime label without filtering', () {
      final catalog = RustNativeCatalog.fromJson(_catalogJson());
      final labels = <String, int>{};
      for (final entry in catalog.cases) {
        labels[entry.runtime] = (labels[entry.runtime] ?? 0) + 1;
      }
      expect(labels, {
        'desktop': 282,
        'cargo': 44,
        'miri-candidate': 4,
        'external': 2,
      });
    });

    test('keeps complete multi-file bundles with hashed files', () {
      final catalog = RustNativeCatalog.fromJson(_catalogJson());
      final bundled = catalog.byId('rust-catalog-007-example')!;
      expect(bundled.isBundle, isTrue);
      expect(bundled.entryFile, 'src/main.rs');
      expect(bundled.files!.keys, contains('Cargo.toml'));
      expect(bundled.files!.keys, contains('crates/mathlib/src/lib.rs'));
      expect(bundled.files!['src/main.rs'], bundled.source);
      expect(bundled.bundleVerify, isNotNull);
      for (final entry in bundled.filesSha256!.entries) {
        expect(entry.value, sha256Hex(bundled.files![entry.key]!));
      }
    });

    test('rejects a case whose digest does not match its source', () {
      final tampered = deepCopy(_catalogJson());
      final record = _caseOf(tampered, 'rust-catalog-001-example');
      record['source'] = '${record['source'] as String}\n';
      expect(
        () => RustNativeCatalog.fromJson(tampered),
        throwsA(isA<FormatException>()),
      );
    });

    test('rejects missing, duplicate and mismatched cases', () {
      final missing = deepCopy(_catalogJson());
      (missing['cases']! as List).removeWhere(
        (entry) => (entry as Map)['id'] == 'rust-catalog-166-answer',
      );
      expect(
        () => RustNativeCatalog.fromJson(missing),
        throwsA(isA<FormatException>()),
      );

      final duplicate = deepCopy(_catalogJson());
      final cases = duplicate['cases']! as List;
      cases.add(deepCopy(cases.first as Map<String, Object?>));
      expect(
        () => RustNativeCatalog.fromJson(duplicate),
        throwsA(isA<FormatException>()),
      );

      final counts = deepCopy(_catalogJson());
      (counts['catalog']! as Map)['runCount'] = 331;
      expect(
        () => RustNativeCatalog.fromJson(counts),
        throwsA(isA<FormatException>()),
      );
    });

    test('rejects an answer that pretends to assert stdout', () {
      final tampered = deepCopy(_catalogJson());
      final answer = _caseOf(tampered, 'rust-catalog-002-answer');
      answer['stdoutAsserted'] = true;
      answer['expectedStdout'] = 'invented\n';
      expect(
        () => RustNativeCatalog.fromJson(tampered),
        throwsA(isA<FormatException>()),
      );
    });

    test('rejects a bundle whose entry differs from its source', () {
      final tampered = deepCopy(_catalogJson());
      final bundle = _caseOf(tampered, 'rust-catalog-005-example');
      (bundle['files']! as Map<String, Object?>)['src/main.rs'] =
          'fn main() {}';
      expect(
        () => RustNativeCatalog.fromJson(tampered),
        throwsA(isA<FormatException>()),
      );
    });

    test('rejects an unsupported schema version', () {
      final tampered = deepCopy(_catalogJson());
      tampered['schemaVersion'] = 2;
      expect(
        () => RustNativeCatalog.fromJson(tampered),
        throwsA(isA<FormatException>()),
      );
    });
  });

  group('compareNativeStdout', () {
    test('accepts exact stdout and tolerates CRLF conversion only', () {
      final catalog = RustNativeCatalog.fromJson(_catalogJson());
      final example = catalog.byId('rust-catalog-001-example')!;
      expect(
        compareNativeStdout(
          testCase: example,
          stdout: example.expectedStdout!,
          exitCode: 0,
        ),
        isNull,
      );
      expect(
        compareNativeStdout(
          testCase: example,
          stdout: example.expectedStdout!.replaceAll('\n', '\r\n'),
          exitCode: 0,
        ),
        isNull,
      );
    });

    test('rejects missing terminators and extra native blank lines', () {
      final catalog = RustNativeCatalog.fromJson(_catalogJson());
      final example = catalog.byId('rust-catalog-001-example')!;
      final expected = example.expectedStdout!;
      expect(
        compareNativeStdout(
          testCase: example,
          stdout: expected.substring(0, expected.length - 1),
          exitCode: 0,
        ),
        contains('stdout mismatch'),
      );
      expect(
        compareNativeStdout(
          testCase: example,
          stdout: '$expected\n',
          exitCode: 0,
        ),
        contains('stdout mismatch'),
        reason: 'one extra blank line must not disappear during comparison',
      );
      expect(
        compareNativeStdout(
          testCase: example,
          stdout: '$expected\n\n',
          exitCode: 0,
        ),
        contains('stdout mismatch'),
        reason: 'an extra blank line is real output, not a formatting quirk',
      );
    });

    test('reports stdout, exit and unasserted-answer differences', () {
      final catalog = RustNativeCatalog.fromJson(_catalogJson());
      final example = catalog.byId('rust-catalog-001-example')!;
      expect(
        compareNativeStdout(testCase: example, stdout: 'wrong\n', exitCode: 0),
        contains('stdout mismatch'),
      );
      expect(
        compareNativeStdout(
          testCase: example,
          stdout: example.expectedStdout!,
          exitCode: 1,
        ),
        contains('exit 1'),
      );
      final answer = catalog.byId('rust-catalog-001-answer')!;
      expect(
        compareNativeStdout(
          testCase: answer,
          stdout: 'anything the answer prints\n',
          exitCode: 0,
        ),
        isNull,
        reason: 'answers are exit-status-only evidence',
      );
      expect(
        compareNativeStdout(testCase: answer, stdout: '', exitCode: 2),
        contains('exit 2'),
      );
    });
  });

  group('RustNativeCatalogReport', () {
    RustNativeCatalog catalog() => RustNativeCatalog.fromJson(_catalogJson());

    RustNativeRuntimeIdentity identity({
      String nativeHost = 'aarch64-unknown-linux-ohos',
    }) => RustNativeRuntimeIdentity(
      platform: 'ohos',
      architecture: 'arm64',
      targetKey: 'ohos-arm64',
      nativeHost: nativeHost,
      targetNativeHosts: const {'aarch64-unknown-linux-ohos'},
      guestTarget: 'x86_64-unknown-linux-gnu',
      libraryPath: '/lib/libqfli_miri.so',
      sysrootPath: '/runtime/sysroot',
      backendPath: null,
      manifestAsset: 'assets/miri/manifest.ohos-arm64.json',
      manifestId:
          '1e31884bf8e09a4a2c7741b01b973efdaa1b50039577aebb45a9df3dcb3845b8',
      manifestNativeHost: 'aarch64-unknown-linux-ohos',
      rustVersion: '1.98.1',
      rustCommit: '48a229ceaefd4985c50990b14116b6d856af0985',
      manifestGuestTarget: 'x86_64-unknown-linux-gnu',
    );

    RustNativeCaseResult result(
      RustNativeCatalogCase testCase, {
      String? id,
      String? sourceSha256,
      String? stdout,
      int exitCode = 0,
    }) => RustNativeCaseResult(
      id: id ?? testCase.id,
      topicId: testCase.topicId,
      kind: testCase.kind,
      runtime: testCase.runtime,
      entryFile: testCase.entryFile,
      sourceSha256: sourceSha256 ?? testCase.sourceSha256,
      status: RustNativeCaseStatus.passed,
      exitCode: exitCode,
      expectedExitCode: testCase.expectedExitCode,
      stdoutAsserted: testCase.stdoutAsserted,
      expectedStdout: testCase.expectedStdout,
      stdout: stdout ?? testCase.expectedStdout ?? '',
      stderr: '',
      durationMs: 12,
    );

    RustNativeCatalogReport report({
      Iterable<RustNativeCaseResult>? results,
      List<String> missingIds = const [],
      bool interrupted = false,
    }) {
      final inventory = catalog();
      final executed = (results ?? inventory.cases.map(result)).toList();
      return RustNativeCatalogReport(
        identity: identity(),
        catalog: inventory,
        results: executed,
        missingIds: missingIds,
        interrupted: interrupted,
        startedAt: DateTime.utc(2026, 10, 22, 10),
        finishedAt: DateTime.utc(2026, 10, 22, 11),
      );
    }

    test('a run missing, interrupted or failing any case is not complete', () {
      final inventory = catalog();
      final full = report();
      expect(full.complete, isTrue);
      expect(full.passed, isTrue);

      expect(report(missingIds: ['rust-catalog-005-answer']).complete, isFalse);
      expect(report(missingIds: ['rust-catalog-005-answer']).passed, isFalse);
      expect(report(interrupted: true).complete, isFalse);

      final failed = report(
        results: [
          for (final testCase in inventory.cases)
            if (testCase.id == 'rust-catalog-042-example')
              RustNativeCaseResult(
                id: testCase.id,
                topicId: testCase.topicId,
                kind: testCase.kind,
                runtime: testCase.runtime,
                entryFile: testCase.entryFile,
                sourceSha256: testCase.sourceSha256,
                status: RustNativeCaseStatus.failed,
                exitCode: 1,
                expectedExitCode: testCase.expectedExitCode,
                stdoutAsserted: testCase.stdoutAsserted,
                expectedStdout: testCase.expectedStdout,
                stdout: '',
                stderr: 'the evaluated program leaked memory',
                durationMs: 30,
                detail: 'exit 1 != expected 0',
              )
            else
              result(testCase),
        ],
      );
      expect(failed.complete, isTrue);
      expect(failed.passed, isFalse);
      expect(failed.failedIds, ['rust-catalog-042-example']);
    });

    test('derives missing coverage even when the caller omits it', () {
      final empty = report(results: const []);
      expect(empty.complete, isFalse);
      expect(empty.passed, isFalse);
      expect(empty.missingIds, hasLength(332));
      expect(empty.toJson()['missingIds'], hasLength(332));

      final inventory = catalog();
      final partial = report(results: [result(inventory.cases.first)]);
      expect(partial.complete, isFalse);
      expect(partial.missingIds, hasLength(331));
    });

    test('a duplicate cannot replace an unexecuted case at the same count', () {
      final inventory = catalog();
      final duplicated = report(
        results: [
          ...inventory.cases.take(inventory.runCount - 1).map(result),
          result(inventory.cases.first),
        ],
      );
      expect(duplicated.results, hasLength(inventory.runCount));
      expect(duplicated.complete, isFalse);
      expect(duplicated.passed, isFalse);
      expect(duplicated.missingIds, [inventory.cases.last.id]);
      expect(duplicated.duplicateIds, [inventory.cases.first.id]);
    });

    test('rejects unexpected IDs and evidence for different source bytes', () {
      final inventory = catalog();
      final unknown = report(
        results: [
          ...inventory.cases.skip(1).map(result),
          result(inventory.cases.first, id: 'not-in-the-inventory'),
        ],
      );
      expect(unknown.complete, isFalse);
      expect(unknown.passed, isFalse);
      expect(unknown.unexpectedIds, ['not-in-the-inventory']);

      final altered = report(
        results: [
          result(inventory.cases.first, sourceSha256: '0' * 64),
          ...inventory.cases.skip(1).map(result),
        ],
      );
      expect(altered.complete, isFalse);
      expect(altered.passed, isFalse);
      expect(altered.mismatchedIds, [inventory.cases.first.id]);
    });

    test('rechecks exit and stdout instead of trusting a passed status', () {
      final inventory = catalog();
      for (final incorrect in [
        result(inventory.cases.first, stdout: 'wrong\n'),
        result(inventory.cases.first, exitCode: 7),
      ]) {
        final forged = report(
          results: [incorrect, ...inventory.cases.skip(1).map(result)],
        );
        expect(forged.complete, isTrue);
        expect(forged.passed, isFalse);
        expect(forged.failedIds, [inventory.cases.first.id]);
      }
    });

    test(
      'serializes runtime, manifest, catalog identity and per-case evidence',
      () {
        final json = report().toJson();
        expect(json['schemaVersion'], RustNativeCatalogReport.schemaVersion);
        expect(json['complete'], isTrue);
        expect(json['executed'], 332);
        final runtime = json['runtime']! as Map<String, Object?>;
        expect(runtime['platform'], 'ohos');
        expect(runtime['nativeHost'], 'aarch64-unknown-linux-ohos');
        expect(runtime['guestTarget'], 'x86_64-unknown-linux-gnu');
        final manifest = runtime['manifest']! as Map<String, Object?>;
        expect(
          manifest['rustCommit'],
          '48a229ceaefd4985c50990b14116b6d856af0985',
        );
        expect(manifest['rustVersion'], '1.98.1');
        expect(manifest['nativeHost'], 'aarch64-unknown-linux-ohos');
        final catalogJson = json['catalog']! as Map<String, Object?>;
        expect(catalogJson['runCount'], 332);
        expect((catalogJson['sourceSha256']! as Map), hasLength(2));
        final cases = json['cases']! as List;
        expect(cases, hasLength(332));
        final first = cases.first as Map<String, Object?>;
        expect(first['id'], 'rust-catalog-001-example');
        expect(first['sourceSha256'], hasLength(64));
        expect(first['status'], 'passed');
      },
    );

    test('an OHOS identity never matches a foreign or mismatched manifest', () {
      expect(identity().manifestMatchesTarget, isTrue);
      final android = RustNativeRuntimeIdentity(
        platform: 'ohos',
        architecture: 'x64',
        targetKey: 'ohos-x64',
        nativeHost: 'x86_64-unknown-linux-ohos',
        targetNativeHosts: const {'x86_64-unknown-linux-ohos'},
        guestTarget: 'x86_64-unknown-linux-gnu',
        libraryPath: '/lib/libqfli_miri.so',
        sysrootPath: '/runtime/sysroot',
        backendPath: null,
        manifestAsset: 'assets/miri/manifest.ohos-x64.json',
        manifestId: 'x',
        manifestNativeHost: 'aarch64-unknown-linux-ohos',
        rustVersion: '1.98.1',
        rustCommit: '48a229ceaefd4985c50990b14116b6d856af0985',
        manifestGuestTarget: 'x86_64-unknown-linux-gnu',
      );
      expect(
        android.manifestMatchesTarget,
        isFalse,
        reason: 'an x64 host must not accept the arm64 manifest',
      );
    });
  });

  // The device harness can only be trusted if the packaged manifests it will
  // select are themselves complete. These checks are host-side and prove the
  // wiring, not engine execution: they never claim a program passed.
  group('packaged OHOS manifests', () {
    Map<String, Object?> manifest(String key) =>
        jsonDecode(File('assets/miri/manifest.$key.json').readAsStringSync())
            as Map<String, Object?>;

    const hosts = {
      'ohos-arm64': 'aarch64-unknown-linux-ohos',
      'ohos-x64': 'x86_64-unknown-linux-ohos',
    };

    for (final entry in hosts.entries) {
      test('${entry.key} declares its own host and bundles every payload', () {
        final decoded = manifest(entry.key);
        expect(decoded['nativeHost'], entry.value);
        expect(decoded['guestTarget'], 'x86_64-unknown-linux-gnu');
        expect(decoded['rustVersion'], '1.98.1');
        expect(
          decoded['rustCommit'],
          '48a229ceaefd4985c50990b14116b6d856af0985',
        );
        final files = decoded['files']! as List;
        expect(files, isNotEmpty);
        final paths = <String>{};
        for (final raw in files) {
          final file = raw as Map<String, Object?>;
          final asset = file['asset']! as String;
          expect(
            File('assets/miri/$asset').existsSync(),
            isTrue,
            reason: '${entry.key} references a missing payload: $asset',
          );
          expect(paths.add(file['path']! as String), isTrue);
        }
      });
    }

    test('both archives exist and one manifest is the arm64 alias', () {
      final arm = manifest('ohos-arm64');
      final legacy =
          jsonDecode(File(rustNativeLegacyManifestAsset).readAsStringSync())
              as Map<String, Object?>;
      expect(legacy['id'], arm['id']);
      expect(legacy['nativeHost'], arm['nativeHost']);
      expect(
        manifest('ohos-x64')['id'],
        isNot(arm['id']),
        reason:
            'the x64 runtime must be a distinct build, not a relabelled one',
      );
    });
  });
}

/// SHA-256 of the UTF-8 bytes of U+4E2D U+6587, computed by Python `hashlib`
/// over the same encoded bytes and pinned here as an independent vector.
const String sha256OfUtf8OfCjk =
    '72726d8818f693066ceb69afa364218b692e62ea92b385782363780f47529c21';
