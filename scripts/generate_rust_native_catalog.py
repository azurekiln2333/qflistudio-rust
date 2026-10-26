#!/usr/bin/env python3
"""Generate the hash-bound native execution catalog for the Rust curriculum.

`assets/content_rust/native_catalog.json` is the authoritative inventory that a
packaged device harness iterates: for every authored topic it binds the exact
example program and exercise answer (plus every attached Cargo bundle file) to
their SHA-256 hashes, expected stdout and expected exit status.

Why a separate catalog: `assets/content_rust/tutorials.json` and `examples.json`
are UI catalogs. They cannot express "this program must exit 0 on the packaged
engine", they drop `exercise.output` (answers have none), and they cannot be
compared against a device report without duplicating hashing logic. This file is
derived purely from the authored sources, so `--check` fails on any drift.

Nothing here executes a program or claims an engine pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

from generate_rust_content import (
    ContentError,
    ROOT,
    TOPIC_FILES,
    load_topics,
)

SCHEMA_VERSION = 1
DESTINATION = "assets/content_rust/native_catalog.json"
CATALOG_ASSETS = (
    "assets/content_rust/tutorials.json",
    "assets/content_rust/examples.json",
)
KINDS = ("example", "answer")
# The native runner compiles exactly one file. Standalone programs are written as
# `main.rs`; bundles keep their authored `src/main.rs` so `mod` resolution and the
# learner's project layout stay identical.
STANDALONE_ENTRY = "main.rs"
BUNDLE_ENTRY = "src/main.rs"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _case_id(topic_id: int, kind: str) -> str:
    return f"rust-catalog-{topic_id:03d}-{kind}"


def build_native_catalog(topics: list[dict]) -> dict:
    """Build the deterministic native catalog document for validated topics."""
    ordered = sorted(topics, key=lambda topic: topic["id"])
    cases: list[dict] = []
    bundle_ids: list[int] = []
    for topic in ordered:
        files = topic.get("files")
        if files is not None:
            bundle_ids.append(topic["id"])
        # Examples assert stdout: `output` is authored for every topic.
        cases.append(
            {
                "id": _case_id(topic["id"], "example"),
                "topicId": topic["id"],
                "kind": "example",
                "runtime": topic["runtime"],
                "level": topic["level"],
                "entryFile": BUNDLE_ENTRY if files is not None else STANDALONE_ENTRY,
                "source": topic["code"],
                "sourceSha256": _sha256(topic["code"]),
                "expectedExitCode": 0,
                "expectedStdout": topic["output"],
                "stdoutAsserted": True,
                "files": dict(sorted(files.items())) if files is not None else None,
                "filesSha256": (
                    {name: _sha256(source) for name, source in sorted(files.items())}
                    if files is not None
                    else None
                ),
                "bundleVerify": topic.get("verify") if files is not None else None,
            }
        )
        # Answers have no authored stdout. Declaring "not asserted" keeps the
        # gap explicit instead of silently passing on an absent expectation.
        answer = topic["exercise"]["answer"]
        cases.append(
            {
                "id": _case_id(topic["id"], "answer"),
                "topicId": topic["id"],
                "kind": "answer",
                "runtime": topic["runtime"],
                "level": topic["level"],
                "entryFile": STANDALONE_ENTRY,
                "source": answer,
                "sourceSha256": _sha256(answer),
                "expectedExitCode": 0,
                "expectedStdout": None,
                "stdoutAsserted": False,
                "files": None,
                "filesSha256": None,
                "bundleVerify": None,
            }
        )
    return {
        "schemaVersion": SCHEMA_VERSION,
        "engine": {
            "guestTarget": "x86_64-unknown-linux-gnu",
            "runnerEntry": "NativeMiriProgramRunner",
            "sourceOfTruth": "tool/rust_content/topics_*.json",
        },
        "catalog": {
            "lessonCount": len(ordered),
            "exampleCount": sum(case["kind"] == "example" for case in cases),
            "answerCount": sum(case["kind"] == "answer" for case in cases),
            "bundleCount": len(bundle_ids),
            "runCount": len(cases),
            "topicIds": [topic["id"] for topic in ordered],
            "bundleTopicIds": bundle_ids,
            "sourceSha256": {
                name: hashlib.sha256((ROOT / "tool/rust_content" / name).read_bytes()).hexdigest()
                for name in TOPIC_FILES
            },
        },
        "cases": cases,
    }


def encode_document(document: dict) -> str:
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise ContentError(message)


def verify_paired_catalogs(root: Path, document: dict) -> None:
    """Prove the harness inventory equals the shipped UI catalogs.

    The native catalog embeds its own copy of every program so a device run needs
    no catalog parsing. That duplication is only safe if the UI catalogs carry the
    same bytes, so every run also cross-checks tutorials.json/examples.json.
    """
    try:
        examples = json.loads((root / CATALOG_ASSETS[1]).read_text(encoding="utf-8"))
        tutorials = json.loads((root / CATALOG_ASSETS[0]).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContentError(f"native_catalog: paired catalogs unreadable: {error}") from error
    example_entries = {
        entry.get("id"): entry
        for entry in examples.get("entries", [])
        if isinstance(entry, dict)
    }
    tutorial_entries = {
        entry.get("id"): entry
        for entry in tutorials.get("entries", [])
        if isinstance(entry, dict)
    }
    for case in document["cases"]:
        suffix = f"{case['topicId']:03d}"
        if case["kind"] == "example":
            entry = example_entries.get(f"rust-example-{suffix}")
            _expect(entry is not None, f"native_catalog: examples.json lacks {suffix}")
            _expect(
                entry.get("code") == case["source"],
                f"native_catalog: examples.json code differs for {suffix}",
            )
            _expect(
                entry.get("expectedOutput") == case["expectedStdout"],
                f"native_catalog: examples.json expectedOutput differs for {suffix}",
            )
            fixtures = entry.get("inputFixtures") or {}
            encoded = fixtures.get("cargoFiles")
            if case["files"] is None:
                _expect(
                    encoded is None,
                    f"native_catalog: examples.json has an unexpected bundle {suffix}",
                )
                continue
            _expect(encoded is not None, f"native_catalog: examples.json lost bundle {suffix}")
            try:
                bundled = json.loads(encoded)
            except json.JSONDecodeError as error:
                raise ContentError(
                    f"native_catalog: bundle {suffix} is not JSON: {error}"
                ) from error
            _expect(
                bundled == case["files"],
                f"native_catalog: examples.json bundle differs for {suffix}",
            )
            _expect(
                fixtures.get("cargoVerify") == case["bundleVerify"],
                f"native_catalog: examples.json cargoVerify differs for {suffix}",
            )
        else:
            entry = tutorial_entries.get(f"rust-tutorial-{suffix}")
            _expect(entry is not None, f"native_catalog: tutorials.json lacks {suffix}")
            exercises = entry.get("lessons", [{}])[0].get("exercises") or [{}]
            _expect(
                exercises[0].get("answer") == case["source"],
                f"native_catalog: tutorials.json answer differs for {suffix}",
            )


def verify_native_catalog(document: Any, topics: list[dict]) -> dict:
    """Validate an existing catalog document against the authored topics.

    Raises ContentError for any drift: missing/extra/duplicate case, wrong hash,
    wrong expected stdout, a bundle that lost a file, or an answer that pretends
    to have an authored expectation.
    """
    _expect(isinstance(document, dict), "native_catalog: expected an object")
    _expect(
        document.get("schemaVersion") == SCHEMA_VERSION,
        f"native_catalog: schemaVersion must be {SCHEMA_VERSION}",
    )
    cases = document.get("cases")
    _expect(isinstance(cases, list), "native_catalog.cases: expected an array")
    expected = build_native_catalog(topics)
    expected_by_id = {case["id"]: case for case in expected["cases"]}
    seen: set[str] = set()
    for index, case in enumerate(cases):
        path = f"native_catalog.cases[{index}]"
        _expect(isinstance(case, dict), f"{path}: expected an object")
        identifier = case.get("id")
        _expect(isinstance(identifier, str) and identifier, f"{path}.id: expected text")
        _expect(identifier not in seen, f"{path}.id: duplicate case {identifier}")
        seen.add(identifier)
        _expect(identifier in expected_by_id, f"{path}.id: unexpected case {identifier}")
        wanted = expected_by_id[identifier]
        for field in (
            "topicId",
            "kind",
            "runtime",
            "level",
            "entryFile",
            "source",
            "sourceSha256",
            "expectedExitCode",
            "expectedStdout",
            "stdoutAsserted",
            "files",
            "filesSha256",
            "bundleVerify",
        ):
            _expect(
                case.get(field) == wanted[field],
                f"{path}.{field}: differs from the authored catalog for {identifier}",
            )
        _expect(
            case["sourceSha256"] == _sha256(case["source"]),
            f"{path}.sourceSha256: does not match its source for {identifier}",
        )
        files = case.get("files")
        if files is not None:
            _expect(
                "Cargo.toml" in files and "src/main.rs" in files,
                f"{path}.files: Cargo.toml and src/main.rs are required",
            )
            _expect(
                files["src/main.rs"] == case["source"],
                f"{path}.files: src/main.rs must equal the example source",
            )
            _expect(
                sorted(files) == sorted(case["filesSha256"] or {}),
                f"{path}.filesSha256: bundle file list differs",
            )
    missing = sorted(set(expected_by_id) - seen)
    _expect(not missing, f"native_catalog: missing cases {missing[:8]}")
    _expect(
        len(cases) == expected["catalog"]["runCount"],
        f"native_catalog: expected {expected['catalog']['runCount']} cases, found {len(cases)}",
    )
    _expect(
        document.get("catalog") == expected["catalog"],
        "native_catalog.catalog: counts or input hashes are stale",
    )
    _expect(
        document.get("engine") == expected["engine"],
        "native_catalog.engine: engine identity is stale",
    )
    return expected["catalog"]


def generate(root: Path = ROOT, *, check: bool = False) -> dict:
    topics = load_topics(root / "tool/rust_content")
    document = build_native_catalog(topics)
    if document["catalog"]["runCount"] != len(topics) * 2:
        raise ContentError("native_catalog: every topic requires an example and an answer")
    destination = root / DESTINATION
    source = encode_document(document)
    if check:
        if not destination.exists():
            raise ContentError(f"{destination}: missing; run scripts/generate_rust_native_catalog.py")
        current = destination.read_text(encoding="utf-8")
        if current != source:
            raise ContentError(
                f"{destination}: stale; run scripts/generate_rust_native_catalog.py"
            )
        try:
            verify_native_catalog(json.loads(current), topics)
        except json.JSONDecodeError as error:
            raise ContentError(f"{destination}: invalid JSON: {error}") from error
        verify_paired_catalogs(root, document)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_text(source, encoding="utf-8", newline="\n")
        temporary.replace(destination)
    missing_assets = [name for name in CATALOG_ASSETS if not (root / name).exists()]
    if missing_assets:
        raise ContentError(f"native_catalog: missing paired catalogs {missing_assets}")
    return dict(document["catalog"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--check", action="store_true", help="Fail if the catalog is absent or stale"
    )
    args = parser.parse_args()
    try:
        summary = generate(args.root.resolve(), check=args.check)
    except ContentError as error:
        print(f"Native catalog validation failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
