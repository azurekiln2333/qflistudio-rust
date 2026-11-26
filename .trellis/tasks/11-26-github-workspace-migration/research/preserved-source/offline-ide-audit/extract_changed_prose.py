#!/usr/bin/env python3
"""Extract changed prose fields from tool/rust_content/*.json and separate
prose from Rust code / program output.

Read-only against the repository: it only runs `git show HEAD:<path>` and
reads the worktree file. It writes its own outputs under build/.

Outputs (all under build/offline-ide-audit/):
  changed-prose.md    NEW text of exactly the changed prose fields
  head-prose.md       prose of every topic at HEAD
  worktree-prose.md   prose of every topic in the worktree
  changed-prose.json  structured change list (field-level, prose vs code)
"""

from __future__ import annotations

import json
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "build" / "offline-ide-audit"

FILES = ["tool/rust_content/topics_001_084.json", "tool/rust_content/topics_085_166.json"]

# Prose the controlled-Chinese linter must judge.
PROSE_SCALAR = ("title", "summary", "objective", "explain")
PROSE_LIST = ("pitfalls",)
PROSE_EXERCISE = ("prompt", "hint")

# Rust code or program output: never judged as prose.
CODE_SCALAR = ("code", "output")
CODE_EXERCISE = ("answer", "output", "hint_expected")

# Structural / identifier fields.
META_SCALAR = ("id", "level", "domain", "runtime", "concepts", "prerequisites")


def head_text(path: str) -> str:
    out = subprocess.run(
        ["git", "show", f"HEAD:{path}"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    return out.stdout.decode("utf-8")


def load(text: str):
    return json.loads(text)


def by_id(topics):
    return {t["id"]: t for t in topics}


def prose_of(topic) -> dict[str, str]:
    """Flatten one topic's prose to {field: text}."""
    flat: dict[str, str] = {}
    for key in PROSE_SCALAR:
        value = topic.get(key)
        if isinstance(value, str):
            flat[key] = value
    for index, value in enumerate(topic.get("pitfalls") or []):
        if isinstance(value, str):
            flat[f"pitfalls[{index}]"] = value
    exercise = topic.get("exercise") or {}
    for key in PROSE_EXERCISE:
        value = exercise.get(key)
        if isinstance(value, str):
            flat[f"exercise.{key}"] = value
    return flat


def code_of(topic) -> dict[str, str]:
    flat: dict[str, str] = {}
    for key in CODE_SCALAR:
        value = topic.get(key)
        if isinstance(value, str):
            flat[key] = value
    exercise = topic.get("exercise") or {}
    for key in CODE_EXERCISE:
        value = exercise.get(key)
        if isinstance(value, str):
            flat[f"exercise.{key}"] = value
    return flat


def meta_of(topic) -> dict[str, object]:
    return {key: topic.get(key) for key in META_SCALAR}


def render(blocks) -> str:
    """Render [(label, text)] as Markdown the linter can read line by line."""
    parts: list[str] = []
    for label, text in blocks:
        parts.append(f"## {label}")
        # Keep the authored line breaks: the linter measures per line.
        for line in text.split("\n"):
            parts.append(line)
        parts.append("")
    return "\n".join(parts) + "\n"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    changes: list[dict] = []
    head_blocks: list[tuple[str, str]] = []
    work_blocks: list[tuple[str, str]] = []
    changed_blocks: list[tuple[str, str]] = []

    for path in FILES:
        old = by_id(load(head_text(path)))
        new = by_id(load(pathlib.Path(ROOT / path).read_text(encoding="utf-8")))

        for tid in sorted(set(old) | set(new)):
            old_topic = old.get(tid, {})
            new_topic = new.get(tid, {})
            old_prose = prose_of(old_topic) if old_topic else {}
            new_prose = prose_of(new_topic) if new_topic else {}

            for field, text in sorted(old_prose.items()):
                head_blocks.append((f"{path} id={tid} {field}", text))
            for field, text in sorted(new_prose.items()):
                work_blocks.append((f"{path} id={tid} {field}", text))

            for field in sorted(set(old_prose) | set(new_prose)):
                before = old_prose.get(field)
                after = new_prose.get(field)
                if before == after:
                    continue
                changes.append(
                    {
                        "file": path,
                        "id": tid,
                        "kind": "prose",
                        "field": field,
                        "before": before,
                        "after": after,
                    }
                )
                if after is not None:
                    changed_blocks.append((f"{path} id={tid} {field}", after))

            old_code = code_of(old_topic) if old_topic else {}
            new_code = code_of(new_topic) if new_topic else {}
            for field in sorted(set(old_code) | set(new_code)):
                if old_code.get(field) == new_code.get(field):
                    continue
                changes.append(
                    {
                        "file": path,
                        "id": tid,
                        "kind": "code-or-output",
                        "field": field,
                        "before_bytes": len(old_code.get(field) or ""),
                        "after_bytes": len(new_code.get(field) or ""),
                    }
                )

            if old_topic and new_topic:
                if meta_of(old_topic) != meta_of(new_topic):
                    changes.append(
                        {
                            "file": path,
                            "id": tid,
                            "kind": "meta",
                            "field": "meta",
                            "before": meta_of(old_topic),
                            "after": meta_of(new_topic),
                        }
                    )

    (OUT / "changed-prose.md").write_text(render(changed_blocks), encoding="utf-8")
    (OUT / "head-prose.md").write_text(render(head_blocks), encoding="utf-8")
    (OUT / "worktree-prose.md").write_text(render(work_blocks), encoding="utf-8")
    (OUT / "changed-prose.json").write_text(
        json.dumps(changes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    prose = [c for c in changes if c["kind"] == "prose"]
    code = [c for c in changes if c["kind"] == "code-or-output"]
    meta = [c for c in changes if c["kind"] == "meta"]
    print(f"changed prose fields : {len(prose)}")
    print(f"changed code/output  : {len(code)}")
    print(f"changed meta records : {len(meta)}")
    for c in prose:
        print(f"  PROSE {c['file']} id={c['id']} {c['field']}")
    for c in code:
        print(f"  CODE  {c['file']} id={c['id']} {c['field']} ({c['before_bytes']}->{c['after_bytes']})")
    for c in meta:
        print(f"  META  {c['file']} id={c['id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())