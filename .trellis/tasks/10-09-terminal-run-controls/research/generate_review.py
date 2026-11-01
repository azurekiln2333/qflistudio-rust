from pathlib import Path
import difflib
import hashlib
import json

root = Path.cwd().resolve()
task = root / '.trellis/tasks/10-09-terminal-run-controls'
baseline = task / 'research/baseline'
existing = [
    'lib/rust_runner.dart', 'lib/native_miri_runner.dart',
    'test/rust_app_test.dart', 'test/native_miri_runner_test.dart',
]
added = [
    'lib/cargo_targets.dart', 'lib/rust_run_title.dart',
    'test/cargo_targets_test.dart', 'test/cargo_process_wiring_test.dart',
    'test/rust_editor_run_test.dart',
]
patch = []
summary = []
for relative in existing + added:
    current = root / relative
    original = baseline / relative
    before = original.read_text(encoding='utf-8-sig') if original.exists() else ''
    after = current.read_text(encoding='utf-8-sig')
    if before == after:
        continue
    patch.extend(difflib.unified_diff(
        before.splitlines(keepends=True), after.splitlines(keepends=True),
        fromfile='a/' + relative if original.exists() else '/dev/null',
        tofile='b/' + relative,
    ))
    summary.append({
        'file': relative,
        'base': 'pre-task snapshot' if original.exists() else 'new in task',
        'sha256': hashlib.sha256(current.read_bytes()).hexdigest(),
    })
(task / 'research/task-only.patch').write_text(''.join(patch), encoding='utf-8')
(task / 'research/changed-files.json').write_text(
    json.dumps(summary, indent=2) + '\n', encoding='utf-8',
)
print(json.dumps({'changedFiles': len(summary), 'files': summary}, indent=2))
