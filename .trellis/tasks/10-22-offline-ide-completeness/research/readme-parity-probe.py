#!/usr/bin/env python3
"""Read-only trilingual parity probe for the root README set.

Compares section headings, prose-line counts, relative links, command blocks,
code identifiers and numbers across README.md, README.zh-TW.md and README.en.md.
It never writes to the repository and never starts a build.

Usage:
    python .trellis/tasks/10-22-offline-ide-completeness/research/readme-parity-probe.py
"""

from __future__ import annotations

import io
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[4]
EDITIONS = {"zh-Hans": "README.md", "zh-Hant": "README.zh-TW.md", "en": "README.en.md"}
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
IDENT_RE = re.compile(r"(?<!`)`([^`\n]+)`(?!`)")
NUM_RE = re.compile(r"\b\d+\b")
FENCE_RE = re.compile(r"```(?:text)?\n(.*?)```", re.S)


def sections(path: pathlib.Path):
    """Return [(heading, prose_lines)] skipping fences, headings and blank lines."""
    out = []
    heading, body = "(preamble)", []
    in_fence = False
    for raw in io.open(path, encoding="utf-8-sig").read().splitlines():
        line = raw.strip()
        if line.startswith("```") or line.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if line.startswith("## "):
            out.append((heading, body))
            heading, body = line[3:].strip(), []
            continue
        if line.startswith("# ") or not line:
            continue
        body.append(line)
    out.append((heading, body))
    return [item for item in out if item[0] != "(preamble)"]


def main() -> int:
    texts = {lang: io.open(ROOT / name, encoding="utf-8-sig").read()
             for lang, name in EDITIONS.items()}
    data = {lang: sections(ROOT / name) for lang, name in EDITIONS.items()}
    failures = 0

    print("sections:", {lang: len(secs) for lang, secs in data.items()})
    for index in range(max(len(secs) for secs in data.values())):
        counts = {lang: len(secs[index][1]) if index < len(secs) else -1
                  for lang, secs in data.items()}
        drift = len(set(counts.values())) > 1
        failures += int(drift)
        print(f"[{index}] {counts}{'  <-- prose-count drift' if drift else ''}")
        for lang, secs in data.items():
            print(f"    {lang:8} {secs[index][0] if index < len(secs) else '<missing>'}")

    print("\nlinks:")
    link_sets = {}
    for lang, text in texts.items():
        links = sorted(set(LINK_RE.findall(text)))
        link_sets[lang] = links
        missing = [t for t in links if not t.startswith("http") and not (ROOT / t).exists()]
        print(f"  {lang:8} {links} missing={missing}")
    if len({tuple(v) for v in link_sets.values()}) > 1:
        failures += 1
        print("  <-- link sets differ")

    print("\ncommand blocks:")
    blocks = {lang: [[c for c in block.splitlines() if c.strip()] for block in FENCE_RE.findall(text)]
              for lang, text in texts.items()}
    for index in range(max(len(b) for b in blocks.values())):
        rows = {lang: blocks[lang][index] if index < len(blocks[lang]) else [] for lang in texts}
        same = len({tuple(v) for v in rows.values()}) == 1
        failures += int(not same)
        print(f"  block {index} identical={same}")
        if not same:
            for lang, row in rows.items():
                print(f"    {lang:8} {row}")

    print("\nidentifiers and numbers:")
    for lang, text in texts.items():
        masked = FENCE_RE.sub("", text)
        idents = sorted({m for m in IDENT_RE.findall(masked) if " " not in m})
        nums = sorted(set(NUM_RE.findall(masked)))
        print(f"  {lang:8} ids={idents}")
        print(f"  {lang:8} nums={nums}")
    print("\ndrift findings:", failures)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())