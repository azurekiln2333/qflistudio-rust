#!/usr/bin/env python3
"""Per-field multiset diff of controlled-Chinese findings for the changed
catalog prose fields.

Read-only against tool/rust_content/. Writes only under build/offline-ide-audit/.
Line/column keys are deliberately NOT used for the delta: a rewritten paragraph
shifts every column, so a positional key would report old findings as new. The
delta is computed on (rule, match) counts inside one field.
"""

from __future__ import annotations

import collections
import importlib.util
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]

sys.path.insert(0, str(HERE))
import extract_changed_prose as ex  # noqa: E402


def load_linter():
    spec = importlib.util.spec_from_file_location(
        "ste_lint_zh", ROOT / "scripts" / "ste-lint-zh.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


LINT = load_linter()
SENT_RE = re.compile(r"[^。！？!?]*[。！？!?]?")


def lint_text(text: str):
    return LINT.analyze(text, "<field>", LINT.Options())


def counter_of(text: str):
    return collections.Counter(
        (f.rule, f.severity, f.match) for f in lint_text(text or "")
    )


def sentence_at(text: str, line: int, col: int) -> str:
    """Sentence containing the finding, for human judgement."""
    lines = text.split("\n")
    if not 1 <= line <= len(lines):
        return ""
    row = LINT.mask_line(lines[line - 1])
    start = 0
    for match in LINT.SENT_END_RE.finditer(row):
        end = match.end()
        if start <= col - 1 < end or (col - 1 >= start and end >= col - 1):
            return lines[line - 1][start:end].strip()
        start = end
    return lines[line - 1].strip()


def main() -> int:
    rows = []
    totals = collections.Counter()

    for path in ex.FILES:
        old = ex.by_id(ex.load(ex.head_text(path)))
        new = ex.by_id(ex.load(pathlib.Path(ROOT / path).read_text(encoding="utf-8")))
        for tid in sorted(set(old) | set(new)):
            op = ex.prose_of(old.get(tid, {}))
            np_ = ex.prose_of(new.get(tid, {}))
            for field in sorted(set(op) | set(np_)):
                before = op.get(field)
                after = np_.get(field)
                if before == after:
                    continue
                bc = counter_of(before)
                ac = counter_of(after)
                added = ac - bc
                removed = bc - ac
                kept = ac & bc
                if not added and not removed:
                    continue
                detail = []
                for (rule, severity, match), count in sorted(added.items()):
                    for _ in range(count):
                        detail.append(
                            {
                                "direction": "added",
                                "rule": rule,
                                "severity": severity,
                                "match": match,
                            }
                        )
                for (rule, severity, match), count in sorted(removed.items()):
                    for _ in range(count):
                        detail.append(
                            {
                                "direction": "removed",
                                "rule": rule,
                                "severity": severity,
                                "match": match,
                            }
                        )
                for (rule, severity, match), count in sorted(added.items()):
                    totals[("added", severity, rule)] += count
                for (rule, severity, match), count in sorted(removed.items()):
                    totals[("removed", severity, rule)] += count
                rows.append(
                    {
                        "file": path,
                        "id": tid,
                        "field": field,
                        "before_chars": len(before or ""),
                        "after_chars": len(after or ""),
                        "kept": sum(kept.values()),
                        "added": sum(added.values()),
                        "removed": sum(removed.values()),
                        "detail": detail,
                        "new_sentences": [sentence_at(after or "", 1, 1)],
                    }
                )

    out = {"fields": rows, "totals": {f"{a}/{b}/{c}": v for (a, b, c), v in totals.items()}}
    (HERE / "prose-field-delta.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"changed prose fields with a finding delta: {len(rows)}")
    for (direction, severity, rule), count in sorted(totals.items()):
        print(f"  {direction:7s} {severity:8s} {rule:18s} {count}")
    print()
    for row in rows:
        print(f"{row['file']} id={row['id']} {row['field']} "
              f"({row['before_chars']}->{row['after_chars']} chars) "
              f"added={row['added']} removed={row['removed']} kept={row['kept']}")
        for d in row["detail"]:
            print(f"    {d['direction']:7s} {d['severity']:8s} {d['rule']:18s} {d['match']!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())