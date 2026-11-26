#!/usr/bin/env python3
"""Compare controlled-Chinese findings across HEAD prose, worktree prose,
changed prose and code/output fields.

Read-only. Writes only under build/offline-ide-audit/.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
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
    # A dataclass needs its module registered before class creation.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


LINT = load_linter()


def lint_block(label: str, text: str):
    """Findings for one field's text, keyed by (rule, match, line, col)."""
    findings = LINT.analyze(text, label, LINT.Options())
    out = []
    for f in findings:
        out.append(
            {
                "label": label,
                "rule": f.rule,
                "severity": f.severity,
                "match": f.match,
                "line": f.line,
                "col": f.col,
            }
        )
    return out


def corpora():
    """Return dict: name -> list[(label, text)]."""
    head: list[tuple[str, str]] = []
    work: list[tuple[str, str]] = []
    code: list[tuple[str, str]] = []
    for path in ex.FILES:
        old = ex.by_id(ex.load(ex.head_text(path)))
        new = ex.by_id(ex.load(pathlib.Path(ROOT / path).read_text(encoding="utf-8")))
        for tid in sorted(set(old) | set(new)):
            ot = old.get(tid, {})
            nt = new.get(tid, {})
            for field, text in sorted(ex.prose_of(ot).items()):
                head.append((f"{path} id={tid} {field}", text))
            for field, text in sorted(ex.prose_of(nt).items()) if nt else []:
                work.append((f"{path} id={tid} {field}", text))
            for field, text in sorted(ex.code_of(nt).items()) if nt else []:
                code.append((f"{path} id={tid} {field}", text))
    changed: list[tuple[str, str]] = []
    for path in ex.FILES:
        old = ex.by_id(ex.load(ex.head_text(path)))
        new = ex.by_id(ex.load(pathlib.Path(ROOT / path).read_text(encoding="utf-8")))
        for tid in sorted(set(old) | set(new)):
            op = ex.prose_of(old.get(tid, {}))
            np_ = ex.prose_of(new.get(tid, {}))
            for field in sorted(set(op) | set(np_)):
                if op.get(field) != np_.get(field) and np_.get(field) is not None:
                    changed.append((f"{path} id={tid} {field}", np_[field]))
    return {"head": head, "worktree": work, "changed": changed, "code": code}


def run():
    data = corpora()
    (HERE / "head-prose.md").write_text(ex.render(data["head"]), encoding="utf-8")
    (HERE / "worktree-prose.md").write_text(ex.render(data["worktree"]), encoding="utf-8")
    (HERE / "changed-prose.md").write_text(ex.render(data["changed"]), encoding="utf-8")
    (HERE / "code-fields.md").write_text(ex.render(data["code"]), encoding="utf-8")

    result = {}
    for name in ("head", "worktree", "changed", "code"):
        findings = []
        for label, text in data[name]:
            findings.extend(lint_block(label, text))
        result[name] = findings

    def key(f):
        return (f["label"], f["rule"], f["match"], f["line"], f["col"])

    head_keys = {key(f) for f in result["head"]}
    work_keys = {key(f) for f in result["worktree"]}
    changed_keys = {key(f) for f in result["changed"]}

    def summarize(fs):
        hard = sum(1 for f in fs if f["severity"] == "hard")
        adv = sum(1 for f in fs if f["severity"] == "advisory")
        return {"total": len(fs), "hard": hard, "advisory": adv}

    summary = {name: summarize(result[name]) for name in result}
    new_in_worktree = [f for f in result["worktree"] if key(f) not in head_keys]
    gone_from_head = [f for f in result["head"] if key(f) not in work_keys]
    changed_findings = [f for f in result["changed"]]

    report = {
        "summary": summary,
        "changed_prose_fields": len(data["changed"]),
        "new_in_worktree": new_in_worktree,
        "gone_from_head": gone_from_head,
        "changed_findings": changed_findings,
        "new_by_rule": {},
        "changed_by_rule": {},
    }
    for f in new_in_worktree:
        report["new_by_rule"].setdefault(f["rule"], []).append(
            {"label": f["label"], "match": f["match"], "line": f["line"]}
        )
    for f in changed_findings:
        report["changed_by_rule"].setdefault(f["rule"], []).append(
            {"label": f["label"], "match": f["match"], "line": f["line"]}
        )

    (HERE / "prose-findings.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    for name in ("head", "worktree", "changed", "code"):
        s = summary[name]
        print(f"{name:9s} total={s['total']:5d} hard={s['hard']:5d} advisory={s['advisory']:5d}")
    print(f"changed prose fields: {len(data['changed'])}")
    print(f"NEW in worktree vs HEAD: {len(new_in_worktree)}")
    print(f"gone from HEAD: {len(gone_from_head)}")
    print("new by rule:", {k: len(v) for k, v in report["new_by_rule"].items()})
    print("changed-field findings by rule:", {k: len(v) for k, v in report["changed_by_rule"].items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(run())