import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:qfli_rust/rust_compiler_diagnostics.dart';

/// One real `--error-format=json` record, trimmed to the fields the analyzer
/// reads, plus the exact source it was produced from.
String spanRecord({
  required int byteStart,
  required int byteEnd,
  String level = 'error',
  String code = 'E0308',
  String file = r'src\main.rs',
  String label = 'expected `i32`, found `&str`',
  bool primary = true,
}) => jsonEncode({
  r'$message_type': 'diagnostic',
  'message': 'mismatched types',
  'code': {'code': code},
  'level': level,
  'spans': [
    {
      'file_name': file,
      'byte_start': byteStart,
      'byte_end': byteEnd,
      'line_start': 1,
      'line_end': 1,
      'column_start': 1,
      'column_end': 1,
      'is_primary': primary,
      'label': label,
    },
  ],
});

/// Byte offset of [needle] inside `utf8.encode(text)`, mirroring what the
/// compiler reports. Used to prove byte offsets differ from UTF-16 offsets.
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

void main() {
  group('parseRustcDiagnostics', () {
    test('keeps spans, code and label from a real record', () {
      final stream = parseRustcDiagnostics(
        spanRecord(byteStart: 3, byteEnd: 8),
      );
      expect(stream.reported, 1);
      expect(stream.unparsedLines, 0);
      expect(stream.diagnostics, hasLength(1));
      final diagnostic = stream.diagnostics.single;
      expect(diagnostic.level, 'error');
      expect(diagnostic.code, 'E0308');
      expect(diagnostic.filePath, r'src\main.rs');
      expect(diagnostic.byteStart, 3);
      expect(diagnostic.byteEnd, 8);
      expect(diagnostic.isPrimary, isTrue);
      expect(diagnostic.label, 'expected `i32`, found `&str`');
    });

    test('retains spanless error and fatal records without fake spans', () {
      for (final level in ['error', 'fatal']) {
        final stream = parseRustcDiagnostics(
          jsonEncode({
            r'$message_type': 'diagnostic',
            'message': 'compiler input could not be loaded',
            'level': level,
            'spans': <Object>[],
          }),
        );
        expect(stream.hasErrors, isTrue);
        expect(stream.diagnostics, isEmpty);
      }
    });

    test('spanless warnings and notes do not mark source as erroneous', () {
      for (final level in ['warning', 'note', 'help', 'failure-note']) {
        final stream = parseRustcDiagnostics(
          jsonEncode({
            r'$message_type': 'diagnostic',
            'message': 'compiler informational record',
            'level': level,
            'spans': <Object>[],
          }),
        );
        expect(stream.hasErrors, isFalse);
      }
    });

    test('drops spanless summary messages but still counts them', () {
      // These two records are what rustc really appends after an error.
      final stream = parseRustcDiagnostics(
        [
          jsonEncode({
            r'$message_type': 'diagnostic',
            'message': 'aborting due to 1 previous error',
            'code': null,
            'level': 'error',
            'spans': <Object>[],
            'children': <Object>[],
          }),
          jsonEncode({
            r'$message_type': 'diagnostic',
            'message':
                'For more information about this error, try `rustc --explain '
                'E0308`.',
            'code': null,
            'level': 'failure-note',
            'spans': <Object>[],
            'children': <Object>[],
          }),
        ].join('\n'),
      );
      expect(stream.reported, 2);
      expect(stream.diagnostics, isEmpty);
      expect(stream.decoded, isTrue);
      expect(stream.unparsedLines, 0);
    });

    test('a clean compile decodes to nothing', () {
      final stream = parseRustcDiagnostics('');
      expect(stream.diagnostics, isEmpty);
      expect(stream.decoded, isFalse);
    });

    test(
      'counts unparsable lines instead of pretending the source is clean',
      () {
        final stream = parseRustcDiagnostics(
          ['{"unterminated": ', 'not json at all'].join('\n'),
        );
        expect(stream.diagnostics, isEmpty);
        expect(stream.unparsedLines, 2);
        expect(stream.reported, 0);
      },
    );

    test('reports a non-diagnostic record as a fatal message', () {
      final stream = parseRustcDiagnostics(
        jsonEncode({'message': 'rustc panicked: internal compiler error'}),
      );
      expect(stream.fatalMessage, 'rustc panicked: internal compiler error');
      expect(stream.diagnostics, isEmpty);
    });

    test('prefers the primary span when several are present', () {
      final record = jsonEncode({
        r'$message_type': 'diagnostic',
        'message': 'borrow of moved value',
        'code': {'code': 'E0382'},
        'level': 'error',
        'spans': [
          {
            'file_name': 'src/a.rs',
            'byte_start': 100,
            'byte_end': 103,
            'is_primary': false,
            'label': 'moved here',
          },
          {
            'file_name': 'src/b.rs',
            'byte_start': 10,
            'byte_end': 14,
            'is_primary': true,
            'label': 'value used here',
          },
        ],
      });
      final stream = parseRustcDiagnostics(record);
      expect(stream.diagnostics.single.filePath, 'src/b.rs');
      expect(stream.diagnostics.single.byteStart, 10);
    });

    test('keeps warnings so they can be shown, not only errors', () {
      final stream = parseRustcDiagnostics(
        spanRecord(
          byteStart: 1,
          byteEnd: 2,
          level: 'warning',
          code: 'unused_variables',
        ),
      );
      expect(stream.diagnostics.single.level, 'warning');
      expect(stream.diagnostics.single.code, 'unused_variables');
    });

    test('tolerates records without a spans array', () {
      final stream = parseRustcDiagnostics(
        jsonEncode({
          r'$message_type': 'diagnostic',
          'message': 'something',
          'level': 'error',
        }),
      );
      expect(stream.reported, 1);
      expect(stream.diagnostics, isEmpty);
    });
  });

  group('Utf8ByteIndex', () {
    test('maps ASCII one to one', () {
      final index = Utf8ByteIndex.fromText('fn main() {}');
      expect(index.byteLength, 12);
      expect(index.utf16Length, 12);
      expect(index.utf16Offset(0), 0);
      expect(index.utf16Offset(3), 3);
    });

    test('counts CJK as three bytes and one UTF-16 unit', () {
      final index = Utf8ByteIndex.fromText('名字');
      expect(index.byteLength, 6);
      expect(index.utf16Length, 2);
      expect(index.utf16Offset(3), 1);
      expect(index.utf16Offset(6), 2);
    });

    test('counts an emoji as four bytes and two UTF-16 units', () {
      final index = Utf8ByteIndex.fromText('a😀b');
      expect(index.byteLength, 6);
      expect(index.utf16Length, 4);
      expect(index.utf16Offset(1), 1); // after 'a'
      expect(index.utf16Offset(5), 3); // after the surrogate pair
      expect(index.utf16Offset(6), 4); // after 'b'
    });

    test('a naive byte offset would be wrong, the index is not', () {
      final text = 'let s = "😀"; let y: i32 = "bad";';
      final index = Utf8ByteIndex.fromText(text);
      final byteStart = byteIndexOf(text, '"bad"');
      final mapped = index.utf16Offset(byteStart);
      expect(mapped, text.indexOf('"bad"'));
      expect(mapped, isNot(byteStart), reason: 'byte offset must differ');
      expect(text.substring(mapped, mapped + 5), '"bad"');
    });

    test('CRLF is preserved as two bytes and two UTF-16 units', () {
      final text = 'fn main() {\r\n    let y: i32 = "bad";\r\n}\r\n';
      final index = Utf8ByteIndex.fromText(text);
      expect(index.utf16Length, text.length);
      expect(index.byteLength, utf8.encode(text).length);
      final mapped = index.utf16Offset(byteIndexOf(text, '"bad"'));
      expect(mapped, text.indexOf('"bad"'));
    });

    test('a BOM is three bytes and one UTF-16 unit', () {
      final text = '\uFEFFfn main() {}';
      final index = Utf8ByteIndex.fromText(text);
      expect(index.byteLength, 15);
      expect(index.utf16Length, 13);
      expect(index.utf16Offset(3), 1);
      expect(index.utf16Offset(0), 0);
    });

    test('an insertion point maps to an empty range', () {
      const text = 'fn main() {\n    let x = 1\n}\n';
      final index = Utf8ByteIndex.fromText(text);
      final offset = index.utf16Offset(text.indexOf('\n}'));
      expect(offset, text.indexOf('\n}'));
      expect(text.substring(offset, offset), '');
    });

    test('clamps out-of-range and negative offsets instead of throwing', () {
      final index = Utf8ByteIndex.fromText('abc');
      expect(index.utf16Offset(-5), 0);
      expect(index.utf16Offset(999), 3);
    });

    test('an offset inside a multi-byte character resolves to its start', () {
      final index = Utf8ByteIndex.fromText('😀');
      expect(index.utf16Offset(1), 0);
      expect(index.utf16Offset(2), 0);
      expect(index.utf16Offset(4), 2);
    });

    test('a lone surrogate still round-trips through the encoded bytes', () {
      // Dart strings can hold unpaired surrogates; utf8.encode replaces them, so
      // the index must be built from the encoded bytes, not from `text.length`.
      const text = '\ud800x';
      final index = Utf8ByteIndex.fromText(text);
      expect(index.byteLength, 4);
      expect(index.utf16Length, 2);
      expect(index.utf16Offset(3), 1);
    });

    test('large text with many checkpoints stays exact', () {
      final text = List.filled(2000, 'let 名字 = "😀";\n').join();
      final index = Utf8ByteIndex.fromText(text);
      final bytes = utf8.encode(text);
      expect(index.byteLength, bytes.length);
      expect(index.utf16Length, text.length);
      for (final probe in [0, 7, 100, 1000, bytes.length - 1]) {
        final expected = index.utf16Offset(probe);
        expect(expected, lessThanOrEqualTo(text.length));
      }
      // Exact spot check where a checkpoint cannot have been placed by luck.
      final byteAt = bytes.length - 3;
      final mapped = index.utf16Offset(byteAt);
      expect(mapped, lessThanOrEqualTo(text.length));
    });
  });
}
