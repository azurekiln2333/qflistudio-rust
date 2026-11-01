import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:path/path.dart' as p;
import 'package:qfli_studio_core/services/runner_service.dart';

import 'cargo_targets.dart';
import 'rust_runner.dart' show resolveExecutableOnPath;

const rustIntegerTypes = [
  'i8',
  'u8',
  'i16',
  'u16',
  'i32',
  'u32',
  'i64',
  'u64',
  'i128',
  'u128',
  'isize',
  'usize',
];

/// A single Rust integer, optionally preceded by unary minus.
/// Values remain arbitrary precision, including values outside a Rust type.
class RustIntegerLiteral {
  const RustIntegerLiteral(this.value, this.radix, this.suffix);

  final BigInt value;
  final int radix;
  final String? suffix;
}

RustIntegerLiteral parseRustInteger(String input) {
  var source = input.trim();
  if (source.isEmpty) throw const FormatException('请输入 Rust 整数。');
  if (source.length > 4096) {
    throw const FormatException('整数输入最多 4096 个字符。');
  }
  final negative = source.startsWith('-');
  if (negative) source = source.substring(1);
  final suffixMatch = RegExp(
    r'(?:u|i)(?:128|64|32|16|8|size)$',
  ).firstMatch(source);
  final suffix = suffixMatch?.group(0);
  if (suffixMatch != null) source = source.substring(0, suffixMatch.start);
  var radix = 10;
  if (source.startsWith('0x')) {
    radix = 16;
  } else if (source.startsWith('0o')) {
    radix = 8;
  } else if (source.startsWith('0b')) {
    radix = 2;
  }
  final digits = radix == 10 ? source : source.substring(2);
  final pattern = switch (radix) {
    2 => RegExp(r'^[01_]+$'),
    8 => RegExp(r'^[0-7_]+$'),
    16 => RegExp(r'^[0-9a-fA-F_]+$'),
    _ => RegExp(r'^[0-9][0-9_]*$'),
  };
  final compact = digits.replaceAll('_', '');
  if (!pattern.hasMatch(digits) || compact.isEmpty) {
    throw const FormatException('请输入十进制、0x、0o 或 0b 整数，可带下划线和 Rust 整数类型后缀。');
  }
  final magnitude = BigInt.parse(compact, radix: radix);
  return RustIntegerLiteral(negative ? -magnitude : magnitude, radix, suffix);
}

class RustIntegerView {
  RustIntegerView({
    required this.value,
    required this.type,
    int pointerWidth = 64,
  }) {
    if (!rustIntegerTypes.contains(type)) {
      throw ArgumentError.value(type, 'type');
    }
    if (pointerWidth != 32 && pointerWidth != 64) {
      throw ArgumentError.value(pointerWidth, 'pointerWidth');
    }
    bits = type.endsWith('size') ? pointerWidth : int.parse(type.substring(1));
    signed = type.startsWith('i');
    modulus = BigInt.one << bits;
    minimum = signed ? -(BigInt.one << (bits - 1)) : BigInt.zero;
    maximum = signed
        ? (BigInt.one << (bits - 1)) - BigInt.one
        : modulus - BigInt.one;
    unsignedBits = value % modulus;
    wrapped = signed && unsignedBits > maximum
        ? unsignedBits - modulus
        : unsignedBits;
  }

  final BigInt value;
  final String type;
  late final int bits;
  late final bool signed;
  late final BigInt modulus;
  late final BigInt minimum;
  late final BigInt maximum;
  late final BigInt unsignedBits;
  late final BigInt wrapped;

  bool get fits => value >= minimum && value <= maximum;
  String get binary => unsignedBits.toRadixString(2).padLeft(bits, '0');
  String get hex =>
      '0x${unsignedBits.toRadixString(16).padLeft(bits ~/ 4, '0')}';
  String get littleEndian => _bytes(reversed: false);
  String get bigEndian => _bytes(reversed: true);

  String _bytes({required bool reversed}) {
    final bytes = [
      for (var index = 0; index < bits ~/ 8; index++)
        ((unsignedBits >> (index * 8)) & BigInt.from(255))
            .toRadixString(16)
            .padLeft(2, '0'),
    ];
    return (reversed ? bytes.reversed : bytes).join(' ');
  }
}

const rustBitOperations = ['&', '|', '^', '!', '<<', '>>'];

/// Applies Rust-width bit operations after an explicit wrapping integer cast.
BigInt rustBitOperation({
  required RustIntegerView left,
  required String operation,
  BigInt? right,
}) {
  if (!rustBitOperations.contains(operation)) {
    throw ArgumentError.value(operation, 'operation');
  }
  if (operation != '!' && right == null) {
    throw const FormatException('请输入右操作数。');
  }
  if ((operation == '<<' || operation == '>>') &&
      (right! < BigInt.zero || right >= BigInt.from(left.bits))) {
    throw FormatException('移位数必须在 0 到 ${left.bits - 1} 之间。');
  }
  final result = switch (operation) {
    '&' => left.unsignedBits & right!,
    '|' => left.unsignedBits | right!,
    '^' => left.unsignedBits ^ right!,
    '!' => ~left.unsignedBits,
    '<<' => left.unsignedBits << right!.toInt(),
    '>>' => left.wrapped >> right!.toInt(),
    _ => throw StateError('Unreachable operation'),
  };
  return RustIntegerView(
    value: result,
    type: left.type,
    pointerWidth: left.bits == 32 ? 32 : 64,
  ).wrapped;
}

enum RustStringInput { text, literal }

class RustScalarInfo {
  RustScalarInfo(this.scalar, this.byteOffset)
    : bytes = utf8.encode(String.fromCharCode(scalar));

  final int scalar;
  final int byteOffset;
  final List<int> bytes;
  String get codePoint =>
      'U+${scalar.toRadixString(16).toUpperCase().padLeft(4, '0')}';
  String get rustEscape => '\\u{${scalar.toRadixString(16)}}';
}

class RustStringView {
  RustStringView(this.text) {
    _validateScalars(text);
    bytes = List.unmodifiable(utf8.encode(text));
    var offset = 0;
    scalars = List.unmodifiable([
      for (final scalar in text.runes)
        (() {
          final info = RustScalarInfo(scalar, offset);
          offset += info.bytes.length;
          return info;
        })(),
    ]);
  }

  final String text;
  late final List<int> bytes;
  late final List<RustScalarInfo> scalars;
  int get utf16Length => text.length;
  String get bytesHex => formatRustBytes(bytes);
  String get escapedLiteral {
    final out = StringBuffer('"');
    for (final scalar in text.runes) {
      out.write(switch (scalar) {
        0 => r'\0',
        9 => r'\t',
        10 => r'\n',
        13 => r'\r',
        34 => r'\"',
        92 => r'\\',
        < 32 || 127 => '\\u{${scalar.toRadixString(16)}}',
        _ => String.fromCharCode(scalar),
      });
    }
    return '$out"';
  }

  /// Raw source cannot contain a bare CR; a quoted escape is required.
  String? get rawLiteral {
    if (text.contains('\r')) return null;
    for (var count = 0; count < 256; count++) {
      final hashes = List.filled(count, '#').join();
      if (!text.contains('"$hashes')) return 'r$hashes"$text"$hashes';
    }
    return null;
  }
}

String formatRustBytes(Iterable<int> bytes) => bytes
    .map((byte) => byte.toRadixString(16).padLeft(2, '0').toUpperCase())
    .join(' ');

RustStringView inspectRustString(String input, RustStringInput mode) {
  if (input.length > 65536) {
    throw const FormatException('字符串输入最多 65536 个 UTF-16 单元。');
  }
  return RustStringView(
    mode == RustStringInput.text
        ? input
        : _decodeRustString(input.trim().replaceAll('\r\n', '\n')),
  );
}

String _decodeRustString(String source) {
  if (source.startsWith('r')) {
    final start = RegExp(r'^r(#{0,255})"').firstMatch(source);
    if (start == null) throw const FormatException('raw string 的起始定界符无效。');
    final close = '"${start.group(1)}';
    final end = source.indexOf(close, start.end);
    if (end < 0 || end + close.length != source.length) {
      throw const FormatException('raw string 定界符不匹配，或结束后存在其他内容。');
    }
    final body = source.substring(start.end, end);
    if (body.contains('\r')) {
      throw const FormatException('Rust raw string 不能包含单独的 CR。');
    }
    return body;
  }
  if (!source.startsWith('"')) {
    throw const FormatException('请输入完整的 "..." 或 r#"..."# 字符串字面量。');
  }
  final out = StringBuffer();
  var index = 1;
  while (index < source.length) {
    final char = source[index++];
    if (char == '"') {
      if (index != source.length) {
        throw const FormatException('字符串结束后存在其他内容。');
      }
      return out.toString();
    }
    if (char == '\r') {
      throw const FormatException('Rust 字符串不能包含单独的 CR，请使用 \\r。');
    }
    if (char != r'\') {
      out.write(char);
      continue;
    }
    if (index >= source.length) break;
    final escape = source[index++];
    switch (escape) {
      case 'n':
        out.write('\n');
      case 'r':
        out.write('\r');
      case 't':
        out.write('\t');
      case '0':
        out.write('\x00');
      case r'\':
        out.write(r'\');
      case '"':
        out.write('"');
      case "'":
        out.write("'");
      case '\n':
        while (index < source.length && ' \t\n\r'.contains(source[index])) {
          index++;
        }
      case 'x':
        if (index + 2 > source.length ||
            !RegExp(
              r'^[0-7][0-9a-fA-F]$',
            ).hasMatch(source.substring(index, index + 2))) {
          throw const FormatException('\\x 必须后接两位十六进制数，且值不超过 7F。');
        }
        out.writeCharCode(
          int.parse(source.substring(index, index + 2), radix: 16),
        );
        index += 2;
      case 'u':
        if (index >= source.length || source[index] != '{') {
          throw const FormatException('Unicode 转义格式为 \\u{1F980}。');
        }
        final end = source.indexOf('}', index + 1);
        if (end < 0) throw const FormatException('Unicode 转义缺少右花括号。');
        final digits = source.substring(index + 1, end);
        final compact = digits.replaceAll('_', '');
        if (!RegExp(r'^[0-9a-fA-F][0-9a-fA-F_]*$').hasMatch(digits) ||
            compact.length > 6) {
          throw const FormatException('Unicode 转义需要 1 到 6 位十六进制数，下划线不能在开头。');
        }
        final scalar = int.parse(compact, radix: 16);
        if (!_isScalar(scalar)) {
          throw const FormatException('Unicode 转义不是有效的标量值。');
        }
        out.writeCharCode(scalar);
        index = end + 1;
      default:
        throw FormatException('Rust 字符串不支持转义 \\$escape。');
    }
  }
  throw const FormatException('字符串缺少结束双引号。');
}

bool _isScalar(int scalar) =>
    scalar <= 0x10ffff && !(scalar >= 0xd800 && scalar <= 0xdfff);

void _validateScalars(String source) {
  for (var index = 0; index < source.length; index++) {
    final unit = source.codeUnitAt(index);
    if (unit >= 0xd800 && unit <= 0xdbff && index + 1 < source.length) {
      final low = source.codeUnitAt(index + 1);
      if (low >= 0xdc00 && low <= 0xdfff) {
        index++;
        continue;
      }
    } else if (unit < 0xd800 || unit > 0xdfff) {
      continue;
    }
    throw const FormatException('文本含未配对的 UTF-16 代理项，无法表示 Rust str。');
  }
}

typedef RustCargoMetadataProbe = Future<String> Function(String projectRoot);

class RustProjectInspection {
  const RustProjectInspection({
    required this.root,
    this.entry,
    this.manifest,
    this.targets = const [],
    this.targetMessage,
    this.error,
  });

  final String root;
  final String? entry;
  final String? manifest;
  final List<CargoTarget> targets;
  final String? targetMessage;
  final String? error;
}

/// Reads project files and Cargo's authoritative target list, never builds.
/// Each instance owns at most one metadata process and supports cancellation.
class RustProjectInspector {
  RustProjectInspector({
    this.metadataProbe,
    this.cargoExecutable = 'cargo',
    this.environment,
    this.timeout = const Duration(seconds: 10),
    bool? allowCargoMetadata,
  }) : allowCargoMetadata =
           allowCargoMetadata ??
           (Platform.isWindows || Platform.isLinux || Platform.isMacOS);

  final RustCargoMetadataProbe? metadataProbe;
  final String cargoExecutable;
  final Map<String, String>? environment;
  final Duration timeout;
  final bool allowCargoMetadata;
  Process? _process;
  bool _cancelled = false;

  void cancel() {
    _cancelled = true;
    _process?.kill(ProcessSignal.sigkill);
  }

  Future<RustProjectInspection> inspect(String projectPath) async {
    final root = p.normalize(p.absolute(projectPath));
    String? entry;
    String? manifest;
    try {
      if (!await Directory(root).exists()) {
        throw const FileSystemException('项目目录不存在。');
      }
      entry = RunnerService.findEntry(root);
      final manifestFile = File(p.join(root, 'Cargo.toml'));
      if (!await manifestFile.exists()) {
        return RustProjectInspection(
          root: root,
          entry: entry,
          targetMessage: '没有 Cargo.toml；这是独立 Rust 源文件项目。',
        );
      }
      if (await manifestFile.length() > 1024 * 1024) {
        throw const FormatException('Cargo.toml 超过 1 MiB，未加载。');
      }
      manifest = await manifestFile.readAsString();
      if (_cancelled) throw const FormatException('检查已取消。');
      if (!allowCargoMetadata && metadataProbe == null) {
        return RustProjectInspection(
          root: root,
          entry: entry,
          manifest: manifest,
          targetMessage: '当前移动运行库不提供 Cargo CLI。已读取本地清单；完整 Cargo 目标需在桌面工具链检查。',
        );
      }
      final json = await (metadataProbe?.call(root) ?? _readMetadata(root));
      if (_cancelled) throw const FormatException('检查已取消。');
      final targets = decodeCargoTargets(json);
      final message = entry == null
          ? '未找到项目入口。'
          : switch (selectCargoTarget(targets: targets, entryFile: entry)) {
              CargoTargetMatch(:final target) =>
                '入口对应 ${target.label}，可用 ${target.kindFlag} ${target.targetName} 选择。',
              CargoTargetUnregistered() =>
                '入口未注册为 Cargo 目标；独立 rustc 路径不会继承 Cargo 依赖。',
              CargoTargetNotRunnable(:final targets) => cargoNotRunnableMessage(
                p.relative(entry, from: root),
                targets,
              ),
              CargoTargetAmbiguous(:final targets) => cargoAmbiguousMessage(
                p.relative(entry, from: root),
                targets,
              ),
            };
      return RustProjectInspection(
        root: root,
        entry: entry,
        manifest: manifest,
        targets: List.unmodifiable(targets),
        targetMessage: message,
      );
    } on FileSystemException catch (error) {
      return RustProjectInspection(
        root: root,
        entry: entry,
        manifest: manifest,
        error: '无法读取本地项目：${error.message}',
      );
    } on FormatException catch (error) {
      return RustProjectInspection(
        root: root,
        entry: entry,
        manifest: manifest,
        error: error.message.toString(),
      );
    } on ProcessException catch (error) {
      return RustProjectInspection(
        root: root,
        entry: entry,
        manifest: manifest,
        error: '本机 Cargo 不可用：${error.message}',
      );
    } on TimeoutException {
      return RustProjectInspection(
        root: root,
        entry: entry,
        manifest: manifest,
        error: 'Cargo 元数据检查超时。',
      );
    }
  }

  Future<String> _readMetadata(String root) async {
    final childEnvironment = {
      ...Platform.environment,
      ...?environment,
      'CARGO_NET_OFFLINE': 'true',
      'RUSTUP_AUTO_INSTALL': '0',
      'RUSTUP_NO_UPDATE_CHECK': '1',
    };
    if (_cancelled) throw const FormatException('检查已取消。');
    final process = await Process.start(
      resolveExecutableOnPath(cargoExecutable, childEnvironment),
      [
        '--offline',
        '--locked',
        'metadata',
        '--no-deps',
        '--format-version',
        '1',
        '--manifest-path',
        p.join(root, 'Cargo.toml'),
      ],
      workingDirectory: root,
      environment: childEnvironment,
      runInShell: false,
    );
    _process = process;
    if (_cancelled) process.kill(ProcessSignal.sigkill);
    unawaited(process.stdin.close());
    final stdout = <int>[];
    final stderr = <int>[];
    var exceeded = false;
    void collect(List<int> buffer, List<int> bytes) {
      if (stdout.length + stderr.length + bytes.length > 4 * 1024 * 1024) {
        exceeded = true;
        process.kill(ProcessSignal.sigkill);
      } else {
        buffer.addAll(bytes);
      }
    }

    final outDone = process.stdout.forEach((bytes) => collect(stdout, bytes));
    final errDone = process.stderr.forEach((bytes) => collect(stderr, bytes));
    var timedOut = false;
    final timer = Timer(timeout, () {
      timedOut = true;
      process.kill(ProcessSignal.sigkill);
    });
    try {
      final exit = await process.exitCode;
      await Future.wait([outDone, errDone]);
      if (_cancelled) throw const FormatException('检查已取消。');
      if (timedOut) throw TimeoutException('Cargo metadata');
      if (exceeded) throw const FormatException('Cargo 元数据输出超过 4 MiB。');
      if (exit != 0) {
        throw FormatException(
          'Cargo 元数据检查失败（退出码 $exit）：\n${utf8.decode(stderr, allowMalformed: true).trim()}',
        );
      }
      return utf8.decode(stdout);
    } finally {
      timer.cancel();
      _process = null;
    }
  }
}
