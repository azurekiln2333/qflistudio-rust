# -*- coding: utf-8 -*-
"""Aggregate the authored lesson modules into the owned JSON file.

This script is a scratch authoring aid (not shipped). It imports each
`_a1/_a2/_b*/_c*/_d*/_e*` module, concatenates LESSONS, sorts by id and writes
`topics_001_084.json`. Run: python tool/rust_content/_build.py
"""
import importlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
# Canonical output stays inside the product tree; scratch helpers live under build/.
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT_PATH = os.path.join(REPO, "tool", "rust_content", "topics_001_084.json")

MODULES = ["_a1", "_a2", "_b1", "_b2", "_c1", "_c2", "_c3", "_d1", "_d2", "_e1", "_e2"]

REQUIRED = [
    "id", "title", "level", "domain", "summary", "concepts", "objective",
    "prerequisites", "explain", "code", "output", "pitfalls", "exercise",
    "runtime",
]


def main():
    lessons = []
    for name in MODULES:
        path = os.path.join(HERE, name + ".py")
        if not os.path.exists(path):
            continue
        mod = importlib.import_module(name)
        lessons.extend(mod.LESSONS)

    lessons.sort(key=lambda x: x["id"])

    # Apply the final import convention: when a lesson provides `files`, its
    # `src/main.rs` must be byte-identical to `code` so the single-file detail
    # body and the optional project agree. Extra files (lib.rs, tests, extra
    # crates, workspace manifests) may then add real structure on top.
    for lesson in lessons:
        files = lesson.get("files")
        if files and "src/main.rs" in files:
            files["src/main.rs"] = lesson["code"]
        # When the project's default binary IS the lesson code, the
        # whole-project run stdout equals the single-file stdout, regardless of
        # whether verify is run/build/test.
        if files and files.get("src/main.rs") == lesson["code"]:
            lesson["projectOutput"] = lesson["output"]

    errors = []
    seen_ids = set()
    for lesson in lessons:
        lid = lesson.get("id")
        if lid in seen_ids:
            errors.append(f"duplicate id {lid}")
        seen_ids.add(lid)
        for field in REQUIRED:
            if field not in lesson:
                errors.append(f"lesson {lid}: missing {field}")
        if lesson.get("exercise"):
            for k in ("prompt", "hint", "answer"):
                if not lesson["exercise"].get(k):
                    errors.append(f"lesson {lid}: exercise missing {k}")
        files = lesson.get("files")
        if files:
            if "Cargo.toml" not in files:
                errors.append(f"lesson {lid}: files missing Cargo.toml")
            if "src/main.rs" in files and files["src/main.rs"] != lesson["code"]:
                errors.append(f"lesson {lid}: files['src/main.rs'] != code")
            if lesson.get("verify") not in ("run", "build", "test"):
                errors.append(f"lesson {lid}: files present but verify invalid")
            if not lesson.get("projectOutput"):
                errors.append(f"lesson {lid}: files present but projectOutput missing")

    out = OUT_PATH
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(lessons, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    ids = sorted(seen_ids)
    print(f"wrote {len(lessons)} lessons -> {out}")
    print(f"id range: {ids[0] if ids else '-'}..{ids[-1] if ids else '-'}")
    missing = [n for n in range(1, 85) if n not in seen_ids]
    if missing:
        print(f"missing ids: {missing}")
    if errors:
        print("ERRORS:")
        for e in errors:
            print("  " + e)
        sys.exit(1)


if __name__ == "__main__":
    main()
