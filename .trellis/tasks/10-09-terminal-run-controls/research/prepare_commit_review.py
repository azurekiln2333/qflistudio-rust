from pathlib import Path
import subprocess

root = Path.cwd()
task = root / '.trellis/tasks/10-09-terminal-run-controls'
owned = {
    'lib/rust_runner.dart', 'lib/native_miri_runner.dart',
    'lib/cargo_targets.dart', 'lib/rust_run_title.dart',
    'test/rust_app_test.dart', 'test/cargo_targets_test.dart',
    'test/cargo_process_wiring_test.dart', 'test/rust_editor_run_test.dart',
}
status = subprocess.run(
    ['git', '-c', 'core.quotepath=false', 'status', '--porcelain=v1', '-uall'],
    check=True, capture_output=True, text=True, encoding='utf-8',
).stdout
unknown = []
for line in status.splitlines():
    path = line[3:]
    if path in owned or path.startswith('.trellis/tasks/10-09-terminal-run-controls/'):
        continue
    unknown.append(line)
lines = [
    '# Commit review', '',
    'The product changes and verification are ready for review. No files have been staged or committed by this task.', '',
    '## Recommended handling', '',
    'Keep this task uncommitted until the pre-existing Rust runtime work is committed or explicitly included in an approved batch. The task-only patch is saved in research/task-only.patch.', '',
    'Reason: lib/native_miri_runner.dart was already an untracked runtime implementation before this task; this task changes its import/title only. lib/rust_runner.dart also already depended on that unfinished runtime migration. Staging entire edited files would include previous work outside this task. Staging an isolated title change to a file absent from HEAD is not a valid standalone code commit.', '',
    '## Candidate work commit after the dependency baseline is settled', '',
    '`fix(runner): honor selected Rust sources and simplify terminal titles`', '',
]
lines.extend('- ' + path for path in sorted(owned))
lines.extend([
    '', 'The current task PRD/design/execution plan and reviewed evidence can be recorded with the work commit. .trellis/spec is intentionally ignored by .gitignore:98; its locally updated run-control contract is not force-added.', '',
    '## Other existing dirty paths (excluded from this proposed scope)', '',
])
lines.extend('- `' + path + '`' for path in unknown)
(task / 'research/commit-review.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
print(f'Wrote commit-review.md; {len(owned)} owned paths, {len(unknown)} other dirty entries.')
