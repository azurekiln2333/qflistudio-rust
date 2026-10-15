#!/usr/bin/env python3
"""Validate the authored Rust curriculum and build the app-local catalogs."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import posixpath
from pathlib import Path, PurePosixPath
import re
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[1]
TOPIC_FILES = ("topics_001_084.json", "topics_085_166.json")
LESSON_COUNT = 166
LEVELS = {"beginner", "intermediate", "advanced"}
RUNTIMES = {"desktop", "cargo", "miri-candidate", "external"}
PLACEHOLDER = re.compile(r"\b(?:todo|unimplemented)!\s*\(|\bTODO\s*[:：]|待补充|待完善|占位(?:代码|教程)|此处省略")
RUNTIME_NOTES = {
    "desktop": "运行条件：示例使用 Rust 标准库，可用桌面 rustc 编译运行。移动端执行能力以当前工具链实际支持为准。",
    "cargo": "运行条件：本课讲解 Cargo 工程；代码块提供可独立编译的标准库版本。完整项目如有附带，可通过新建项目导入，使用桌面 Cargo 离线构建。",
    "miri-candidate": "运行条件：示例可用桌面 rustc 编译。是否能由移动端 Miri 执行仍需对应设备验证。",
    "external": "运行条件：本课说明外部工具或 ABI 的使用边界；代码块是可独立编译的标准库演示，完整外部集成需要另行准备桌面环境。",
}


class ContentError(ValueError):
    """Authored or generated content violates the release contract."""


def _text(value: object, path: str, minimum: int = 1) -> str:
    if not isinstance(value, str) or len(value.strip()) < minimum:
        raise ContentError(f"{path}: expected substantive text (minimum {minimum} characters)")
    if PLACEHOLDER.search(value):
        raise ContentError(f"{path}: unfinished placeholder text or Rust macro")
    return value


def _strings(value: object, path: str, *, minimum: int = 1) -> list[str]:
    if not isinstance(value, list) or len(value) < minimum:
        raise ContentError(f"{path}: expected an array with at least {minimum} entries")
    for index, item in enumerate(value):
        _text(item, f"{path}[{index}]")
    if len(set(value)) != len(value):
        raise ContentError(f"{path}: duplicate entries")
    return value


def validate_project_path(path: object) -> str:
    if not isinstance(path, str) or not path or "\\" in path or ":" in path:
        raise ContentError(f"files: invalid project-relative path {path!r}")
    parts = PurePosixPath(path).parts
    if path.startswith("/") or any(part.casefold() in {".", "..", ".qfli", ".git", "target"} for part in path.split("/")):
        raise ContentError(f"files: unsafe project-relative path {path!r}")
    if not parts or any(not part or re.search(r'[\x00-\x1f<>"|?*]', part) for part in path.split("/")):
        raise ContentError(f"files: invalid project-relative path {path!r}")
    return path


def _validate_manifest(source: str, path: str) -> None:
    try:
        document = tomllib.loads(source)
    except tomllib.TOMLDecodeError as error:
        raise ContentError(f"{path}: invalid TOML: {error}") from error
    # These bundled projects must build without retrieving registry/Git crates.
    dependency_tables = [(key, document.get(key, {})) for key in ("dependencies", "dev-dependencies", "build-dependencies")]
    for target, config in document.get("target", {}).items():
        dependency_tables.extend((f"target.{target}.{key}", config.get(key, {})) for key in ("dependencies", "dev-dependencies", "build-dependencies"))
    dependency_tables.append(("workspace.dependencies", document.get("workspace", {}).get("dependencies", {})))
    for key, dependencies in dependency_tables:
        for name, dependency in dependencies.items():
            if isinstance(dependency, dict) and dependency.get("workspace") is True:
                continue
            if not isinstance(dependency, dict) or not isinstance(dependency.get("path"), str):
                raise ContentError(f"{path}.{key}.{name}: only bundled path dependencies are allowed")
            dependency_path = dependency["path"]
            if PurePosixPath(dependency_path).is_absolute() or ":" in dependency_path or "\\" in dependency_path:
                raise ContentError(f"{path}.{key}.{name}: dependency must remain inside the bundled project")
            manifest_name = path.split(".files.", 1)[-1]
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(manifest_name), dependency_path))
            if resolved == ".." or resolved.startswith("../"):
                raise ContentError(f"{path}.{key}.{name}: dependency escapes the bundled project")


def validate_topics(topics: object, *, expected_count: int = LESSON_COUNT) -> list[dict]:
    if not isinstance(topics, list):
        raise ContentError("curriculum must be an array")
    ids: list[int] = []
    unique: dict[str, dict[str, int]] = {field: {} for field in ("title", "summary", "explain", "code")}
    for index, topic in enumerate(topics):
        path = f"topics[{index}]"
        if not isinstance(topic, dict):
            raise ContentError(f"{path}: expected an object")
        lesson_id = topic.get("id")
        if type(lesson_id) is not int:
            raise ContentError(f"{path}.id: expected integer")
        ids.append(lesson_id)
        for field, minimum in (("title", 4), ("domain", 1), ("summary", 20), ("objective", 10), ("explain", 100), ("code", 20)):
            value = _text(topic.get(field), f"{path}.{field}", minimum)
            if field in unique:
                normalized = value.strip()
                previous = unique[field].get(normalized)
                if previous is not None:
                    raise ContentError(f"{path}.{field}: duplicates lesson {previous:03}")
                unique[field][normalized] = lesson_id
        if topic.get("level") not in LEVELS:
            raise ContentError(f"{path}.level: expected one of {sorted(LEVELS)}")
        if topic.get("runtime") not in RUNTIMES:
            raise ContentError(f"{path}.runtime: expected one of {sorted(RUNTIMES)}")
        _strings(topic.get("concepts"), f"{path}.concepts", minimum=2)
        _strings(topic.get("prerequisites"), f"{path}.prerequisites", minimum=0)
        _strings(topic.get("pitfalls"), f"{path}.pitfalls")
        if not re.search(r"\bfn\s+main\s*\(", topic["code"]):
            raise ContentError(f"{path}.code: a complete standalone main function is required")
        if not isinstance(topic.get("output"), str):
            raise ContentError(f"{path}.output: exact stdout string is required (may be empty)")
        exercise = topic.get("exercise")
        if not isinstance(exercise, dict):
            raise ContentError(f"{path}.exercise: expected an object")
        for field, minimum in (("prompt", 10), ("hint", 6), ("answer", 20)):
            _text(exercise.get(field), f"{path}.exercise.{field}", minimum)
        if not re.search(r"\bfn\s+main\s*\(", exercise["answer"]):
            raise ContentError(f"{path}.exercise.answer: a complete runnable program is required")
        files = topic.get("files")
        if files is not None:
            if not isinstance(files, dict) or not {"Cargo.toml", "src/main.rs"}.issubset(files):
                raise ContentError(f"{path}.files: Cargo.toml and src/main.rs are required")
            folded: set[str] = set()
            for filename, source in files.items():
                validate_project_path(filename)
                if filename.casefold() in folded:
                    raise ContentError(f"{path}.files: case-insensitive duplicate path {filename}")
                folded.add(filename.casefold())
                _text(source, f"{path}.files.{filename}")
                if filename.endswith("Cargo.toml"):
                    _validate_manifest(source, f"{path}.files.{filename}")
            if files["src/main.rs"].strip() != topic["code"].strip():
                raise ContentError(f"{path}.files.src/main.rs: must match the independently runnable code block")
            if topic.get("verify", "run") not in {"run", "build", "test"}:
                raise ContentError(f"{path}.verify: expected run, build or test")
    expected_ids = list(range(1, expected_count + 1))
    if sorted(ids) != expected_ids:
        duplicates = sorted(number for number, count in Counter(ids).items() if count > 1)
        missing = sorted(set(expected_ids) - set(ids))
        extra = sorted(set(ids) - set(expected_ids))
        raise ContentError(f"IDs must be exactly 001..{expected_count:03}; missing={missing}, duplicate={duplicates}, extra={extra}")
    return sorted(topics, key=lambda topic: topic["id"])


def load_topics(source_dir: Path = ROOT / "tool/rust_content") -> list[dict]:
    topics = []
    for filename in TOPIC_FILES:
        path = source_dir / filename
        try:
            records = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as error:
            raise ContentError(f"{path}: {error}") from error
        if not isinstance(records, list):
            raise ContentError(f"{path}: expected a JSON array")
        topics.extend(records)
    return validate_topics(topics)


def build_documents(topics: list[dict]) -> dict[str, dict]:
    tutorials, examples = [], []
    for topic in topics:
        suffix = f"{topic['id']:03}"
        lesson_id = f"rust-tutorial-{suffix}-lesson"
        metadata = dict(
            language="rust", type="rust", locale="zh-CN", level=topic["level"],
            title=topic["title"], summary=topic["summary"], concepts=topic["concepts"],
            source="QFLI original Rust curriculum", license="CC0-1.0", updatedAt="2026-10-15",
            domain=topic["domain"], runtime=topic["runtime"],
        )
        lesson = {
            field: topic[field]
            for field in ("title", "summary", "concepts", "objective", "prerequisites", "code", "output", "pitfalls")
        }
        lesson.update(id=lesson_id, explain=f"{topic['explain']}\n\n{RUNTIME_NOTES[topic['runtime']]}", exercises=[topic["exercise"]])
        tutorials.append(dict(metadata, id=f"rust-tutorial-{suffix}", lessons=[lesson]))
        fixtures = {}
        if "files" in topic:
            fixtures = {"cargoFiles": json.dumps(topic["files"], ensure_ascii=False, sort_keys=True), "cargoVerify": topic.get("verify", "run")}
        examples.append(dict(metadata, id=f"rust-example-{suffix}", code=topic["code"],
                             expectedOutput=topic["output"], inputFixtures=fixtures,
                             templateType="rust", sourceLessonId=lesson_id))
    return {"tutorials.json": {"schemaVersion": 1, "entries": tutorials},
            "examples.json": {"schemaVersion": 1, "entries": examples}}


def encode_document(document: dict) -> str:
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def generate(root: Path = ROOT, *, check: bool = False) -> dict:
    topics = load_topics(root / "tool/rust_content")
    documents = build_documents(topics)
    destination = root / "assets/content_rust"
    for filename, document in documents.items():
        path = destination / filename
        source = encode_document(document)
        if check:
            if not path.exists() or path.read_text(encoding="utf-8") != source:
                raise ContentError(f"{path}: missing or stale; run scripts/generate_rust_content.py")
        else:
            destination.mkdir(parents=True, exist_ok=True)
            path.write_text(source, encoding="utf-8", newline="\n")
    return {"tutorials": len(topics), "examples": len(topics),
            "domains": dict(sorted(Counter(topic["domain"] for topic in topics).items())),
            "levels": dict(sorted(Counter(topic["level"] for topic in topics).items())),
            "runtimes": dict(sorted(Counter(topic["runtime"] for topic in topics).items())),
            "cargoProjects": sum("files" in topic for topic in topics)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--check", action="store_true", help="Fail if generated catalogs are absent or stale")
    args = parser.parse_args()
    try:
        print(json.dumps(generate(args.root.resolve(), check=args.check), ensure_ascii=False, indent=2))
        return 0
    except ContentError as error:
        print(f"Content validation failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
