import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;
import 'package:qfli_rust/rust_tool_utilities.dart';

void main() {
  group('Rust integers', () {
    test('parses Rust radices, underscores, unary minus and suffixes', () {
      final value = parseRustInteger('-0x_80_i8');
      expect(value.value, BigInt.from(-128));
      expect(value.radix, 16);
      expect(value.suffix, 'i8');
      expect(parseRustInteger('0b_1010_u128').value, BigInt.from(10));
      expect(parseRustInteger('0o7_7usize').value, BigInt.from(63));
      expect(parseRustInteger('1_000_').value, BigInt.from(1000));
      expect(parseRustInteger('0xff32').value, BigInt.from(0xff32));
    });

    test('rejects Rust-invalid numeric tokens', () {
      for (final input in [
        '',
        '+1',
        '0x',
        '0b_',
        '0b102',
        '0o8',
        '0XFF',
        '_1',
        '1.0',
        '1e3',
        '2u7',
        '--2',
        '- 2',
        '2 + 3',
      ]) {
        expect(
          () => parseRustInteger(input),
          throwsFormatException,
          reason: input,
        );
      }
    });

    test('preserves the full u128 range and signed boundaries exactly', () {
      final max = parseRustInteger(
        '340282366920938463463374607431768211455u128',
      );
      final unsigned = RustIntegerView(value: max.value, type: 'u128');
      expect(unsigned.fits, isTrue);
      expect(unsigned.hex, '0xffffffffffffffffffffffffffffffff');
      expect(unsigned.binary, List.filled(128, '1').join());
      expect(unsigned.maximum, max.value);
      final signed = RustIntegerView(value: max.value, type: 'i128');
      expect(signed.fits, isFalse);
      expect(signed.wrapped, -BigInt.one);
      final minimum = parseRustInteger(
        '-170141183460469231731687303715884105728i128',
      );
      expect(RustIntegerView(value: minimum.value, type: 'i128').fits, isTrue);
      expect(
        RustIntegerView(value: minimum.value - BigInt.one, type: 'i128').fits,
        isFalse,
      );
    });

    test('wrapping casts, endian bytes and explicit pointer assumptions', () {
      final negative = RustIntegerView(value: BigInt.from(-2), type: 'i16');
      expect(negative.hex, '0xfffe');
      expect(negative.littleEndian, 'fe ff');
      expect(negative.bigEndian, 'ff fe');
      expect(
        RustIntegerView(value: BigInt.from(256), type: 'u8').wrapped,
        BigInt.zero,
      );
      final value = BigInt.one << 40;
      expect(
        RustIntegerView(value: value, type: 'usize', pointerWidth: 32).fits,
        isFalse,
      );
      expect(
        RustIntegerView(value: value, type: 'usize', pointerWidth: 64).fits,
        isTrue,
      );
      expect(
        RustIntegerView(
          value: -BigInt.one,
          type: 'isize',
          pointerWidth: 32,
        ).bits,
        32,
      );
    });

    test(
      'fixed-width operations respect signed shifts and reject bad shifts',
      () {
        final signed = RustIntegerView(value: BigInt.from(-128), type: 'i8');
        expect(
          rustBitOperation(
            left: signed,
            operation: '>>',
            right: BigInt.from(2),
          ),
          BigInt.from(-32),
        );
        expect(
          rustBitOperation(left: signed, operation: '<<', right: BigInt.one),
          BigInt.zero,
        );
        expect(
          rustBitOperation(left: signed, operation: '!'),
          BigInt.from(127),
        );
        final byte = RustIntegerView(value: BigInt.from(0xf0), type: 'u8');
        expect(
          rustBitOperation(
            left: byte,
            operation: '&',
            right: BigInt.from(0xaa),
          ),
          BigInt.from(0xa0),
        );
        expect(
          rustBitOperation(
            left: byte,
            operation: '|',
            right: BigInt.from(0x0f),
          ),
          BigInt.from(255),
        );
        expect(
          rustBitOperation(
            left: byte,
            operation: '^',
            right: BigInt.from(0xff),
          ),
          BigInt.from(15),
        );
        for (final shift in [-1, 8, 128]) {
          expect(
            () => rustBitOperation(
              left: byte,
              operation: '>>',
              right: BigInt.from(shift),
            ),
            throwsFormatException,
          );
        }
      },
    );
  });

  group('Rust strings', () {
    test('distinguishes UTF-8 bytes, scalar values and UTF-16 units', () {
      final view = inspectRustString('A🦀e\u0301', RustStringInput.text);
      expect(view.bytes.length, 8);
      expect(view.scalars.length, 4);
      expect(view.utf16Length, 5);
      expect(view.scalars.map((scalar) => scalar.byteOffset), [0, 1, 5, 6]);
      expect(view.scalars[1].codePoint, 'U+1F980');
      expect(view.bytesHex, '41 F0 9F A6 80 65 CC 81');
    });

    test('decodes Rust escapes and source CRLF normalization', () {
      final view = inspectRustString(
        r'''"a\n\t\0\x7F\u{1_F980}\"\\\'"''',
        RustStringInput.literal,
      );
      expect(view.text, 'a\n\t\x00\x7f🦀"\\\'');
      expect(
        inspectRustString('"a\r\nb"', RustStringInput.literal).text,
        'a\nb',
      );
      expect(
        inspectRustString('"a\\\r\n \t\nb"', RustStringInput.literal).text,
        'ab',
      );
    });

    test('raw strings preserve backslashes and generate safe delimiters', () {
      final view = inspectRustString(
        'r##"a"#\\n🦀"##',
        RustStringInput.literal,
      );
      expect(view.text, 'a"#\\n🦀');
      expect(view.rawLiteral, 'r##"a"#\\n🦀"##');
      expect(
        inspectRustString(view.rawLiteral!, RustStringInput.literal).text,
        view.text,
      );
      final cr = inspectRustString('a\rb', RustStringInput.text);
      expect(cr.rawLiteral, isNull);
      expect(cr.escapedLiteral, r'"a\rb"');
    });

    test('generated escaped literals round trip every escape and Unicode', () {
      const text = '\x00\x01\t\n\r"\\\u007f中🦀';
      final view = inspectRustString(text, RustStringInput.text);
      expect(
        inspectRustString(view.escapedLiteral, RustStringInput.literal).text,
        text,
      );
      expect(inspectRustString('', RustStringInput.text).escapedLiteral, '""');
    });

    test(
      'rejects malformed literals, invalid scalars and unsupported escapes',
      () {
        for (final input in [
          r'"\x80"',
          r'"\u{D800}"',
          r'"\u{110000}"',
          r'"\u{_1}"',
          r'"\u{}"',
          r'"\u{0000000}"',
          r'"\z"',
          '"open',
          '"x"tail',
          'r#"x"##',
          'r"x""',
          '"a\rb"',
          'b"abc"',
        ]) {
          expect(
            () => inspectRustString(input, RustStringInput.literal),
            throwsFormatException,
            reason: input,
          );
        }
        expect(
          () => inspectRustString(
            String.fromCharCode(0xd800),
            RustStringInput.text,
          ),
          throwsFormatException,
        );
        expect(
          () => inspectRustString(
            String.fromCharCode(0xdc00),
            RustStringInput.text,
          ),
          throwsFormatException,
        );
      },
    );
  });

  group('local Rust project inspection', () {
    late Directory directory;
    final bundledCargo = p.absolute(
      'native',
      'build',
      'miri-windows',
      'compiler',
      'bin',
      'cargo.exe',
    );

    setUp(() {
      directory = Directory.systemTemp.createTempSync('rust_tools_test');
    });
    tearDown(() {
      directory.deleteSync(recursive: true);
    });

    void project() {
      Directory(p.join(directory.path, 'src')).createSync();
      File(
        p.join(directory.path, 'src', 'main.rs'),
      ).writeAsStringSync('fn main() {}');
      File(p.join(directory.path, 'Cargo.toml')).writeAsStringSync(
        '[package]\nname = "demo"\nversion = "0.1.0"\nedition = "2021"\n',
      );
      Directory(p.join(directory.path, '.qfli')).createSync();
      File(
        p.join(directory.path, '.qfli', 'project.json'),
      ).writeAsStringSync(jsonEncode({'entryFile': 'src/main.rs'}));
    }

    String metadata({
      String kind = 'bin',
      List<String> names = const ['demo'],
    }) => jsonEncode({
      'packages': [
        {
          'name': 'demo',
          'manifest_path': p.join(directory.path, 'Cargo.toml'),
          'targets': [
            for (final name in names)
              {
                'name': name,
                'src_path': p.join(directory.path, 'src', 'main.rs'),
                'kind': [kind],
                'crate_types': [kind == 'lib' ? 'lib' : 'bin'],
              },
          ],
        },
      ],
    });

    test(
      'uses the existing Cargo target decoder and real entry identity',
      () async {
        project();
        final inspector = RustProjectInspector(
          metadataProbe: (root) async {
            expect(root, directory.path);
            return metadata(names: ['custom-name']);
          },
        );
        final before = File(
          p.join(directory.path, 'Cargo.toml'),
        ).readAsBytesSync();
        final result = await inspector.inspect(directory.path);
        expect(result.error, isNull);
        expect(result.targets.single.targetName, 'custom-name');
        expect(result.targetMessage, contains('--bin custom-name'));
        expect(
          File(p.join(directory.path, 'Cargo.toml')).readAsBytesSync(),
          before,
        );
        expect(
          Directory(p.join(directory.path, 'target')).existsSync(),
          isFalse,
        );
        expect(
          File(p.join(directory.path, 'Cargo.lock')).existsSync(),
          isFalse,
        );
      },
    );

    test('retains nonrunnable and ambiguous target explanations', () async {
      project();
      final library = await RustProjectInspector(
        metadataProbe: (_) async => metadata(kind: 'lib'),
      ).inspect(directory.path);
      expect(library.targetMessage, contains('不可运行'));
      expect(library.targets.single.isRunnable, isFalse);
      final ambiguous = await RustProjectInspector(
        metadataProbe: (_) async => metadata(names: ['a', 'b']),
      ).inspect(directory.path);
      expect(ambiguous.targetMessage, contains('多个可运行目标'));
    });

    test(
      'mobile remains useful without pretending to have Cargo target data',
      () async {
        project();
        final result = await RustProjectInspector(
          allowCargoMetadata: false,
        ).inspect(directory.path);
        expect(result.error, isNull);
        expect(result.manifest, contains('[package]'));
        expect(result.entry, p.join(directory.path, 'src', 'main.rs'));
        expect(result.targets, isEmpty);
        expect(result.targetMessage, contains('不提供 Cargo CLI'));
      },
    );

    test(
      'actual Cargo metadata never executes build.rs or writes build output',
      () async {
        project();
        File(p.join(directory.path, 'build.rs')).writeAsStringSync(
          'fn main() { std::fs::write("BUILD_SCRIPT_RAN", "bad").unwrap(); }',
        );
        final result = await RustProjectInspector(
          cargoExecutable: bundledCargo,
          allowCargoMetadata: true,
        ).inspect(directory.path);
        expect(result.error, isNull);
        expect(
          result.targets.map((target) => target.kinds.single),
          containsAll(['bin', 'custom-build']),
        );
        expect(result.targetMessage, contains('--bin demo'));
        expect(
          File(p.join(directory.path, 'BUILD_SCRIPT_RAN')).existsSync(),
          isFalse,
        );
        expect(
          File(p.join(directory.path, 'Cargo.lock')).existsSync(),
          isFalse,
        );
        expect(
          Directory(p.join(directory.path, 'target')).existsSync(),
          isFalse,
        );
      },
      skip: !Platform.isWindows || !File(bundledCargo).existsSync(),
    );

    test('a missing desktop Cargo remains an explicit failure', () async {
      project();
      final result = await RustProjectInspector(
        allowCargoMetadata: true,
        cargoExecutable: p.join(directory.path, 'cargo-does-not-exist'),
      ).inspect(directory.path);
      expect(result.error, contains('Cargo 不可用'));
      expect(result.manifest, contains('[package]'));
      expect(result.targets, isEmpty);
    });

    test(
      'malformed metadata and cancellation cannot report target success',
      () async {
        project();
        final malformed = await RustProjectInspector(
          metadataProbe: (_) async => '{"packages":42}',
        ).inspect(directory.path);
        expect(malformed.error, contains('package list'));
        final cancelled = RustProjectInspector(
          metadataProbe: (_) async => metadata(),
        );
        cancelled.cancel();
        final result = await cancelled.inspect(directory.path);
        expect(result.error, contains('取消'));
        expect(result.targets, isEmpty);
      },
    );

    test(
      'standalone and missing project paths have distinct results',
      () async {
        File(
          p.join(directory.path, 'main.rs'),
        ).writeAsStringSync('fn main() {}');
        final result = await RustProjectInspector(
          allowCargoMetadata: false,
        ).inspect(directory.path);
        expect(result.error, isNull);
        expect(result.targetMessage, contains('没有 Cargo.toml'));
        final missing = await RustProjectInspector(
          allowCargoMetadata: false,
        ).inspect(p.join(directory.path, 'missing'));
        expect(missing.error, contains('目录不存在'));
      },
    );
  });
}
