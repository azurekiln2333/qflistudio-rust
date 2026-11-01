/// Decoding of `rustc --error-format=json` output into project-relative source
/// positions.
///
/// This library is deliberately dependency-free (only `dart:convert` and
/// `dart:typed_data`) so it can be unit tested without Flutter and reused by
/// any transport that can run the compiler. It never decides *whether* a file
/// may be reported; the caller owns path policy.
///
/// ## Verified compiler coordinates
///
/// Measured against the pinned compiler (rustc 1.98.1, commit
/// 48a229ceaefd4985c50990b14116b6d856af0985). Every claim below was observed,
/// not inferred:
///
/// * `spans[].byte_start`/`byte_end` are **raw UTF-8 byte offsets into the file
///   as it exists on disk**, with `\r\n` counted as two bytes and a UTF-8 BOM
///   counted as three. A CRLF file therefore does *not* shift spans the way
///   line-normalised offsets would.
/// * `spans[].column_start`/`column_end` are 1-based counts of **characters**
///   (Unicode scalar values) inside the line, so they are neither bytes nor
///   UTF-16 code units. They are only used for tests and diagnostics messages
///   here, never for mapping.
/// * An insertion point is a valid span with `byte_start == byte_end`.
/// * Module files reached from an absolute crate root are reported with
///   absolute paths, so `--remap-path-prefix` (or the caller's prefix mapping)
///   is what puts them back into project coordinates.
/// * Messages without a span (for example `aborting due to 1 previous error`
///   and the trailing `failure-note`) carry no position and are dropped.
library;

import 'dart:convert';
import 'dart:typed_data';

/// One compiler message that does carry a source span.
///
/// Offsets are still in compiler byte coordinates; convert them with
/// [Utf8ByteIndex] before handing them to the editor.
class RustcDiagnostic {
  const RustcDiagnostic({
    required this.level,
    required this.message,
    required this.code,
    required this.filePath,
    required this.byteStart,
    required this.byteEnd,
    required this.isPrimary,
    required this.label,
  });

  /// `error`, `warning`, `note`, `help` or `failure-note`.
  final String level;
  final String message;
  final String code;
  final String filePath;
  final int byteStart;
  final int byteEnd;
  final bool isPrimary;
  final String label;

  @override
  String toString() =>
      'RustcDiagnostic($level, $code, $filePath:$byteStart..$byteEnd)';
}

/// Result of decoding one stderr stream of compiler messages.
class RustcDiagnosticStream {
  const RustcDiagnosticStream({
    required this.diagnostics,
    required this.reported,
    required this.unparsedLines,
    this.fatalMessage,
    this.hasErrors = false,
  });

  final List<RustcDiagnostic> diagnostics;

  /// Number of `$message_type: "diagnostic"` records seen, including the ones
  /// without spans that [diagnostics] intentionally drops.
  final int reported;

  /// Lines that were neither valid JSON nor empty.
  final int unparsedLines;

  /// Error/fatal records remain significant even when they have no source span.
  /// Native analysis reports compiler errors as data with an exit code of zero.
  final bool hasErrors;

  /// First non-diagnostic record's message, for example a panic or an internal
  /// compiler error. `null` when the stream was well formed.
  final String? fatalMessage;

  /// True when the compiler produced structured output at all. An empty but
  /// well-formed stream is the only honest "no problems found" signal.
  bool get decoded => reported > 0;
}

/// Decodes a JSONL compiler stream.
///
/// `rendered` and `code.explanation` can contain dozens of lines, but they are
/// JSON strings, so their newlines are escaped and splitting the raw text on
/// `\n` is safe. Lines that fail to parse are counted instead of being silently
/// discarded, so a truncated stream cannot masquerade as a clean compile.
RustcDiagnosticStream parseRustcDiagnostics(String output) {
  final diagnostics = <RustcDiagnostic>[];
  var reported = 0;
  var unparsed = 0;
  var hasErrors = false;
  String? fatal;
  for (final line in const LineSplitter().convert(output)) {
    if (line.trim().isEmpty) continue;
    Object? decoded;
    try {
      decoded = jsonDecode(line);
    } on FormatException {
      unparsed++;
      continue;
    }
    if (decoded is! Map<String, dynamic>) {
      unparsed++;
      continue;
    }
    final type = decoded[r'$message_type'];
    if (type != null && type != 'diagnostic') {
      // Newer compilers may emit `artifact` and similar records; they never
      // describe source positions.
      continue;
    }
    final message = decoded['message'];
    if (message is! String) {
      unparsed++;
      continue;
    }
    if (type == null) {
      fatal ??= message;
      continue;
    }
    reported++;
    final level = decoded['level'];
    if (level == 'error' || level == 'fatal') hasErrors = true;
    final code = decoded['code'];
    final spans = decoded['spans'];
    if (level is! String || spans is! List) continue;
    final selected = _selectSpan(spans);
    if (selected == null) continue;
    final start = selected['byte_start'];
    final end = selected['byte_end'];
    final file = selected['file_name'];
    if (start is! int || end is! int || file is! String) continue;
    final label = selected['label'];
    diagnostics.add(
      RustcDiagnostic(
        level: level,
        message: message,
        code: code is Map<String, dynamic> && code['code'] is String
            ? code['code'] as String
            : '',
        filePath: file,
        byteStart: start,
        byteEnd: end,
        isPrimary: selected['is_primary'] == true,
        label: label is String ? label : '',
      ),
    );
  }
  return RustcDiagnosticStream(
    diagnostics: List.unmodifiable(diagnostics),
    reported: reported,
    unparsedLines: unparsed,
    fatalMessage: fatal,
    hasErrors: hasErrors,
  );
}

/// Picks the span that should carry the squiggle: the primary one when present,
/// otherwise the first reported span.
///
/// A derive or macro failure can carry spans from the standard library and from
/// the invocation site; the caller filters by path afterwards, so a
/// non-project primary span still wins here and is dropped later rather than
/// silently moving the squiggle onto unrelated project text.
Map<String, dynamic>? _selectSpan(List<dynamic> spans) {
  final mapped = spans.whereType<Map<String, dynamic>>().toList();
  for (final span in mapped) {
    if (span['is_primary'] == true) return span;
  }
  return mapped.isEmpty ? null : mapped.first;
}

/// Maps raw UTF-8 byte offsets to UTF-16 code-unit offsets.
///
/// Byte offsets are decoded against the **exact bytes given to the compiler**,
/// so CRLF pairs, a BOM and non-BMP characters all keep their real widths. The
/// index stores a checkpoint every [checkpointStride] bytes and walks at most
/// that many bytes per lookup, which keeps 4 MiB buffers cheap while remaining
/// exact.
class Utf8ByteIndex {
  Utf8ByteIndex._(this.bytes, this._checkpointBytes, this._checkpointUnits);

  /// Builds an index for [bytes] exactly as the compiler saw them.
  factory Utf8ByteIndex.fromBytes(List<int> bytes) {
    final data = bytes is Uint8List ? bytes : Uint8List.fromList(bytes);
    final checkpointBytes = <int>[0];
    final checkpointUnits = <int>[0];
    var byte = 0;
    var unit = 0;
    while (byte < data.length) {
      final length = _sequenceLength(data, byte);
      byte += length;
      unit += length == 4 ? 2 : 1;
      if (byte - checkpointBytes.last >= checkpointStride) {
        checkpointBytes.add(byte);
        checkpointUnits.add(unit);
      }
    }
    return Utf8ByteIndex._(
      data,
      Uint32List.fromList(checkpointBytes),
      Uint32List.fromList(checkpointUnits),
    );
  }

  /// Builds an index for [text] by encoding it the same way the mirror writer
  /// does, so the offsets and the compiled bytes cannot drift apart.
  factory Utf8ByteIndex.fromText(String text) =>
      Utf8ByteIndex.fromBytes(utf8.encode(text));

  static const int checkpointStride = 256;

  final Uint8List bytes;
  final Uint32List _checkpointBytes;
  final Uint32List _checkpointUnits;

  int get byteLength => bytes.length;

  /// Total length in UTF-16 code units of the indexed text.
  int get utf16Length => utf16Offset(byteLength);

  /// Converts a byte offset into a UTF-16 offset, clamped to the buffer.
  ///
  /// An offset inside a multi-byte character resolves to the character start,
  /// which never happens for compiler spans but keeps malformed input bounded.
  int utf16Offset(int byteOffset) {
    final target = byteOffset < 0
        ? 0
        : (byteOffset > bytes.length ? bytes.length : byteOffset);
    // Last checkpoint at or before [target].
    var low = 0;
    var high = _checkpointBytes.length - 1;
    while (low < high) {
      final middle = (low + high + 1) >> 1;
      if (_checkpointBytes[middle] <= target) {
        low = middle;
      } else {
        high = middle - 1;
      }
    }
    var byte = _checkpointBytes[low];
    var unit = _checkpointUnits[low];
    while (byte < target) {
      final length = _sequenceLength(bytes, byte);
      if (byte + length > target) break;
      byte += length;
      unit += length == 4 ? 2 : 1;
    }
    return unit;
  }

  /// UTF-8 sequence length implied by [lead].
  ///
  /// Invalid lead bytes and truncated tails count as one byte so that a
  /// malformed buffer still maps monotonically instead of throwing.
  static int _sequenceLength(Uint8List data, int index) {
    final lead = data[index];
    final int length;
    if (lead < 0x80) {
      length = 1;
    } else if (lead >= 0xc2 && lead <= 0xdf) {
      length = 2;
    } else if (lead >= 0xe0 && lead <= 0xef) {
      length = 3;
    } else if (lead >= 0xf0 && lead <= 0xf4) {
      length = 4;
    } else {
      return 1;
    }
    if (index + length > data.length) return 1;
    return length;
  }
}
