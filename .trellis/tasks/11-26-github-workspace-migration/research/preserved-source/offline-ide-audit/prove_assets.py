#!/usr/bin/env python3
"""Prove the generated assets changed only in prose-bearing fields.

Compares the pristine snapshot taken before the prose fix against the freshly
generated assets and classifies every diff.
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = ROOT / "build" / "offline-ide-audit"

PAIRS = [
    ("assets/content_rust/tutorials.json", "pristine-tutorials.json"),
    ("assets/content_rust/examples.json", "pristine-examples.json"),
    ("assets/content_rust/native_catalog.json", "pristine-native_catalog.json"),
]

# Fields that carry teaching prose. Everything else must be byte-identical.
PROSE_KEYS = {
    "explain",
    "summary",
    "objective",
    "title",
    "pitfalls",
    "hint",
    "prompt",
}
# Fields that carry Rust source, program output or project bundles.
CODE_KEYS = {"code", "answer", "output", "files", "bundle", "bundles", "program", "sources"}


def load(path: pathlib.Path):
    return json.loads(path.read_text(encoding="utf-8"))


def walk_diff(old, new, path="", out=None):
    """Collect (path, kind) leaves that differ."""
    if out is None:
        out = []
    if type(old) is not type(new):
        out.append((path, "type"))
        return out
    if isinstance(old, dict):
        if list(old) != list(new):
            out.append((path, "key-order-or-set"))
        for key in old:
            if key in new:
                walk_diff(old[key], new[key], f"{path}/{key}", out)
    elif isinstance(old, list):
        if len(old) != len(new):
            out.append((path, "length"))
        for index, (a, b) in enumerate(zip(old, new)):
            walk_diff(a, b, f"{path}[{index}]", out)
    else:
        if old != new:
            out.append((path, "value"))
    return out


def classify(path: str) -> str:
    # A derived input hash is expected to move when prose moves. It is not a
    # program identity: inspect `catalog/cases` separately for that.
    if path.endswith("/sourceSha256/topics_001_084.json") or path.endswith(
        "/sourceSha256/topics_085_166.json"
    ):
        return "DERIVED-HASH"
    segments = [s for s in path.replace("[", "/").replace("]", "").split("/") if s]
    keys = [s for s in segments if not s.isdigit()]
    leaf = keys[-1] if keys else ""
    for key in reversed(keys):
        if key in CODE_KEYS:
            return "CODE"
    for key in reversed(keys):
        if key in PROSE_KEYS:
            return "PROSE"
    return "OTHER"


def main() -> int:
    failures = []
    for new_name, pristine_name in PAIRS:
        old = load(HERE / pristine_name)
        new = load(ROOT / new_name)
        diffs = walk_diff(old, new)
        buckets = {"PROSE": 0, "CODE": 0, "OTHER": 0, "DERIVED-HASH": 0}
        detail = []
        for path, kind in diffs:
            bucket = classify(path)
            buckets[bucket] += 1
            if bucket not in ("PROSE", "DERIVED-HASH"):
                detail.append((bucket, path, kind))
        print(f"{new_name}: diffs={len(diffs)} prose={buckets['PROSE']} "
              f"code={buckets['CODE']} other={buckets['OTHER']} "
              f"derived-hash={buckets['DERIVED-HASH']}")
        for bucket, path, kind in detail[:20]:
            print(f"    {bucket} {kind} {path}")
            failures.append(f"{new_name} {bucket} {path}")

    print()
    print("=== engine / schema / source hashes ===")
    old = load(HERE / "pristine-native_catalog.json")
    new = load(ROOT / "assets/content_rust/native_catalog.json")
    print("engine identical:", old.get("engine") == new.get("engine"))
    print("schemaVersion identical:", old.get("schemaVersion") == new.get("schemaVersion"))
    print("catalog identical:", old.get("catalog") == new.get("catalog"))
    print("sourceSha256 before:", old.get("catalog", {}).get("sourceSha256"))
    print("sourceSha256 after :", new.get("catalog", {}).get("sourceSha256"))

    print()
    old_cat = old.get("catalog") or {}
    new_cat = new.get("catalog") or {}
    strip = lambda d: {k: v for k, v in d.items() if k != "sourceSha256"}
    print("catalog without sourceSha256 identical:", strip(old_cat) == strip(new_cat))
    old_cases = strip(old_cat).get("cases")
    new_cases = strip(new_cat).get("cases")
    print("case inventory identical:", old_cases == new_cases)
    if strip(old_cat) != strip(new_cat):
        failures.append("native_catalog catalog changed beyond sourceSha256")

    print()
    if failures:
        print(f"NON-PROSE ASSET DIFFS: {len(failures)}")
        return 1
    print("ASSETS: prose-only diffs, all code/answer/output/bundle fields identical")
    return 0


if __name__ == "__main__":
    sys.exit(main())