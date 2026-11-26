#!/usr/bin/env python3
"""Verify the prose-only fix.

1. Lint each rewritten `explain` field at 40 and 25 counted chars.
2. Prove every non-prose field is byte-identical to the pristine snapshot.
3. Prove fenced Rust code and program output are untouched.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = ROOT / "build" / "offline-ide-audit"

spec = importlib.util.spec_from_file_location("ste_lint_zh", ROOT / "scripts" / "ste-lint-zh.py")
LINT = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = LINT
spec.loader.exec_module(LINT)

FILES = {
    "tool/rust_content/topics_001_084.json": "pristine-001_084.json",
    "tool/rust_content/topics_085_166.json": "pristine-085_166.json",
}
TARGETS = {
    "tool/rust_content/topics_001_084.json": [13],
    "tool/rust_content/topics_085_166.json": [157, 158, 159, 161, 166],
}
PROSE = {"title", "summary", "objective", "explain", "pitfalls", "exercise"}
VAGUE = ("相关", "有关", "若干", "一些", "适当", "酌情", "必要时", "等等", "之类", "大致", "差不多")
MARKETING = ("无缝", "强大", "赋能", "闭环", "极致", "丝滑", "一站式", "全方位", "颠覆", "领先", "完美")


def load(path: pathlib.Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sentences(text: str):
    out = []
    for line in text.split("\n"):
        if not line.strip():
            continue
        masked = LINT.mask_line(line)
        start = 0
        for match in LINT.SENT_END_RE.finditer(masked):
            out.append(line[start:match.end()])
            start = match.end()
        if masked[start:].strip():
            out.append(line[start:])
    return out


def main() -> int:
    failures = []

    print("=== rewritten explain fields ===")
    for path, ids in TARGETS.items():
        data = {t["id"]: t for t in load(ROOT / path)}
        for tid in ids:
            text = data[tid]["explain"]
            over40 = over25 = semi = 0
            for sentence in sentences(text):
                masked = LINT.mask_line(sentence)
                n = LINT.count_chars(masked)
                if n > 40:
                    over40 += 1
                    failures.append(f"{path} id={tid} long40: {sentence[:60]}")
                if n > 25:
                    over25 += 1
                if "；" in masked or ";" in masked:
                    semi += 1
                    failures.append(f"{path} id={tid} semicolon: {sentence[:60]}")
            vague = [w for w in VAGUE if w in text]
            marketing = [w for w in MARKETING if w in text]
            findings = LINT.analyze(text, f"{path} id={tid}", LINT.Options())
            hard = [f for f in findings if f.severity == "hard"]
            print(
                f"{path.split('/')[-1]} id={tid:3d} sentences={len(sentences(text)):2d} "
                f">40={over40} >25={over25} semi={semi} hard={len(hard)} "
                f"vague={vague} marketing={marketing}"
            )
            if vague:
                failures.append(f"{path} id={tid} vague {vague}")
            if marketing:
                failures.append(f"{path} id={tid} marketing {marketing}")

    print()
    print("=== non-prose field equality vs pristine ===")
    for path, pristine_name in FILES.items():
        old = {t["id"]: t for t in load(HERE / pristine_name)}
        new = {t["id"]: t for t in load(ROOT / path)}
        if list(old) != list(new):
            failures.append(f"{path} topic id set changed")
        diffs = []
        for tid in old:
            for key in old[tid]:
                if key in PROSE:
                    continue
                if old[tid][key] != new[tid][key]:
                    diffs.append((tid, key))
        print(f"{path.split('/')[-1]}: non-prose diffs={len(diffs)}")
        for tid, key in diffs:
            failures.append(f"{path} id={tid} non-prose field {key} changed")

    print()
    print("=== code / answer / output byte identity ===")
    for path, pristine_name in FILES.items():
        old = {t["id"]: t for t in load(HERE / pristine_name)}
        new = {t["id"]: t for t in load(ROOT / path)}
        checked = 0
        for tid in old:
            for key in ("code", "output"):
                if old[tid].get(key) != new[tid].get(key):
                    failures.append(f"{path} id={tid} {key} changed")
                checked += 1
            for key in ("answer", "output"):
                if old[tid]["exercise"].get(key) != new[tid]["exercise"].get(key):
                    failures.append(f"{path} id={tid} exercise.{key} changed")
                checked += 1
        print(f"{path.split('/')[-1]}: compared {checked} code/answer/output values")

    print()
    if failures:
        print(f"FAILURES {len(failures)}")
        for item in failures[:40]:
            print("  ", item)
        return 1
    print("ALL CHECKS PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())