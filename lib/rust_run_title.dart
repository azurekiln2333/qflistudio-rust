import 'package:path/path.dart' as p;

/// Concise terminal title shared by every Rust execution route.
///
/// `run <project-relative source>` with a portable separator and no localized
/// boilerplate or backend suffix (`(Rust)`, `(Rust / Miri)`, `(jdk)`, ...).
/// A path containing whitespace is quoted so the command line stays readable
/// and copy-pasteable: `run "src/my file.rs"`. Falls back to the entry file
/// name when the source is outside the project root; callers reject such
/// sources separately.
String rustRunTitle(String projectRoot, String entryFile) {
  final root = p.normalize(p.absolute(projectRoot));
  final entry = p.normalize(p.absolute(entryFile));
  final relative = p.isWithin(root, entry)
      ? p.relative(entry, from: root)
      : p.basename(entry);
  final display = p.posix.joinAll(p.split(relative));
  return 'run ${_quoteIfNeeded(display)}';
}

/// Wraps [value] in double quotes when it contains whitespace, escaping any
/// embedded double quote. Non-whitespace paths are returned unchanged.
String _quoteIfNeeded(String value) {
  if (!value.contains(RegExp(r'\s'))) return value;
  final escaped = value.replaceAll(r'\', r'\\').replaceAll('"', r'\"');
  return '"$escaped"';
}
