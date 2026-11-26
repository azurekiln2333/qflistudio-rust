# -*- coding: utf-8 -*-
"""Final convention + integrity audit for topics_001_084.json (scratch aid)."""
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))

FILLER = ["TODO", "unimplemented!()", "todo!()", "FIXME", "placeholder",
          "lorem", "数据建模与不变量", "weighted="]


def main():
    with open(os.path.join(REPO, "tool", "rust_content", "topics_001_084.json"), encoding="utf-8") as fh:
        lessons = json.load(fh)

    problems = []
    ids = [l["id"] for l in lessons]
    if ids != list(range(1, 85)):
        problems.append(f"ids not 1..84: {ids}")

    for field in ("title", "explain", "code", "output", "summary"):
        vals = [l[field] for l in lessons]
        dup = [v for v, c in Counter(vals).items() if c > 1]
        if dup:
            problems.append(f"duplicate {field}: {dup[:3]}")

    prompts = [l["exercise"]["prompt"] for l in lessons]
    dup_p = [v for v, c in Counter(prompts).items() if c > 1]
    if dup_p:
        problems.append(f"duplicate exercise prompts: {dup_p[:3]}")

    for l in lessons:
        lid = l["id"]
        for f in ("title", "level", "domain", "summary", "objective", "explain",
                  "code", "output", "runtime"):
            if not l.get(f):
                problems.append(f"lesson {lid}: empty {f}")
        if not l.get("concepts") or not l.get("pitfalls"):
            problems.append(f"lesson {lid}: empty concepts/pitfalls")
        if lid != 1 and not l.get("prerequisites"):
            problems.append(f"lesson {lid}: empty prerequisites")
        if "fn main" not in l["code"]:
            problems.append(f"lesson {lid}: code lacks main")
        if "fn main" not in l["exercise"]["answer"]:
            problems.append(f"lesson {lid}: answer lacks main")
        blob = json.dumps(l, ensure_ascii=False)
        for marker in FILLER:
            if marker in blob:
                problems.append(f"lesson {lid}: filler marker {marker!r}")
        if l["code"].count("\n") < 3:
            problems.append(f"lesson {lid}: code looks too short")
        files = l.get("files")
        if files:
            if "src/main.rs" in files and files["src/main.rs"] != l["code"]:
                problems.append(f"lesson {lid}: main.rs != code")
            if not l.get("projectOutput"):
                problems.append(f"lesson {lid}: missing projectOutput")
            if l.get("verify") not in ("run", "build", "test"):
                problems.append(f"lesson {lid}: bad verify")
        if l["runtime"] == "cargo" and not files:
            problems.append(f"lesson {lid}: cargo runtime but no files")

    levels = Counter(l["level"] for l in lessons)
    domains = Counter(l["domain"] for l in lessons)
    runtimes = Counter(l["runtime"] for l in lessons)
    print(f"lessons: {len(lessons)}")
    print(f"levels: {dict(levels)}")
    print(f"domains: {dict(domains)}")
    print(f"runtimes: {dict(runtimes)}")
    with_files = [l["id"] for l in lessons if l.get("files")]
    print(f"lessons with files: {with_files}")

    all_ok = True
    for l in lessons:
        f = l.get("files")
        if f and "src/main.rs" in f and f["src/main.rs"] != l["code"]:
            all_ok = False
    print(f"main.rs == code for all: {all_ok}")

    if problems:
        print(f"\n{len(problems)} problem(s):")
        for p in problems[:50]:
            print("  " + p)
        sys.exit(1)
    print("\nall convention/integrity checks passed")


if __name__ == "__main__":
    main()
