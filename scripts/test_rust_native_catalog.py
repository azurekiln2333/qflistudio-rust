"""Contract tests for the hash-bound native execution catalog.

These tests are host-only bookkeeping: they never execute Rust and never imply a
mobile engine pass. They exist so the device harness can trust its inventory.
"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from generate_rust_content import ContentError, load_topics
from generate_rust_native_catalog import (
    CATALOG_ASSETS,
    DESTINATION,
    SCHEMA_VERSION,
    build_native_catalog,
    encode_document,
    generate,
    verify_native_catalog,
    verify_paired_catalogs,
)

ROOT = Path(__file__).resolve().parents[1]
TOPICS = load_topics(ROOT / "tool/rust_content")


def catalog() -> dict:
    return json.loads(json.dumps(build_native_catalog(TOPICS), ensure_ascii=False))


def case(document: dict, identifier: str) -> dict:
    for entry in document["cases"]:
        if entry["id"] == identifier:
            return entry
    raise AssertionError(f"missing case {identifier}")


class NativeCatalogInventoryTests(unittest.TestCase):
    def test_every_authored_topic_contributes_one_example_and_one_answer(self):
        document = catalog()
        self.assertEqual(document["schemaVersion"], SCHEMA_VERSION)
        summary = document["catalog"]
        self.assertEqual(summary["lessonCount"], 166)
        self.assertEqual(summary["exampleCount"], 166)
        self.assertEqual(summary["answerCount"], 166)
        self.assertEqual(summary["bundleCount"], 23)
        self.assertEqual(summary["runCount"], 332)
        self.assertEqual(len(document["cases"]), 332)
        self.assertEqual(summary["topicIds"], list(range(1, 167)))

        ids = {entry["id"] for entry in document["cases"]}
        self.assertEqual(len(ids), 332)
        for topic_id in range(1, 167):
            for kind in ("example", "answer"):
                self.assertIn(f"rust-catalog-{topic_id:03d}-{kind}", ids)
            # Exactly one example and one answer per topic, never two of a kind.
            kinds = [
                entry["kind"]
                for entry in document["cases"]
                if entry["topicId"] == topic_id
            ]
            self.assertEqual(sorted(kinds), ["answer", "example"])

    def test_no_runtime_label_is_dropped_or_rewritten(self):
        """Every runtime label is retained; the harness must not filter by label."""
        document = catalog()
        labels: dict[str, int] = {}
        for entry in document["cases"]:
            labels[entry["runtime"]] = labels.get(entry["runtime"], 0) + 1
        self.assertEqual(labels["desktop"], 282)
        self.assertEqual(labels["cargo"], 44)
        self.assertEqual(labels["miri-candidate"], 4)
        self.assertEqual(labels["external"], 2)
        self.assertEqual(sum(labels.values()), 332)
        for entry in document["cases"]:
            self.assertEqual(
                entry["runtime"],
                next(t["runtime"] for t in TOPICS if t["id"] == entry["topicId"]),
            )

    def test_examples_bind_expected_stdout_and_answers_declare_the_gap(self):
        document = catalog()
        for entry in document["cases"]:
            topic = next(t for t in TOPICS if t["id"] == entry["topicId"])
            self.assertEqual(entry["expectedExitCode"], 0)
            if entry["kind"] == "example":
                self.assertTrue(entry["stdoutAsserted"])
                self.assertEqual(entry["expectedStdout"], topic["output"])
                self.assertEqual(entry["source"], topic["code"])
            else:
                # Answers have no authored stdout: the gap must stay explicit.
                self.assertFalse(entry["stdoutAsserted"])
                self.assertIsNone(entry["expectedStdout"])
                self.assertEqual(entry["source"], topic["exercise"]["answer"])

    def test_hashes_bind_exact_authored_bytes(self):
        import hashlib

        document = catalog()
        for entry in document["cases"]:
            expected = hashlib.sha256(entry["source"].encode("utf-8")).hexdigest()
            self.assertEqual(entry["sourceSha256"], expected)
            self.assertEqual(len(entry["sourceSha256"]), 64)
        for entry in document["cases"]:
            files = entry["files"]
            if files is None:
                self.assertIsNone(entry["filesSha256"])
                self.assertIsNone(entry["bundleVerify"])
                continue
            self.assertEqual(sorted(files), sorted(entry["filesSha256"]))
            for name, source in files.items():
                digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
                self.assertEqual(entry["filesSha256"][name], digest)
            self.assertEqual(files["src/main.rs"], entry["source"])
            self.assertEqual(entry["entryFile"], "src/main.rs")

    def test_standalone_cases_use_the_runner_entry_file(self):
        for entry in catalog()["cases"]:
            expected = "src/main.rs" if entry["files"] is not None else "main.rs"
            self.assertEqual(entry["entryFile"], expected)

    def test_bundles_keep_every_authored_file(self):
        document = catalog()
        bundled = {entry["topicId"]: entry for entry in document["cases"] if entry["files"]}
        self.assertEqual(document["catalog"]["bundleTopicIds"], sorted(bundled))
        for topic in TOPICS:
            files = topic.get("files")
            if files is None:
                continue
            entry = bundled[topic["id"]]
            self.assertEqual(entry["files"], dict(sorted(files.items())))
            self.assertEqual(entry["bundleVerify"], topic.get("verify"))
            self.assertIn("Cargo.toml", entry["files"])

    def test_catalog_is_deterministic_regardless_of_input_order(self):
        forward = encode_document(build_native_catalog(TOPICS))
        backward = encode_document(build_native_catalog(list(reversed(TOPICS))))
        self.assertEqual(forward, backward)
        self.assertTrue(forward.endswith("\n"))


class NativeCatalogVerificationTests(unittest.TestCase):
    def assertRejected(self, document: dict, pattern: str) -> None:
        with self.assertRaisesRegex(ContentError, pattern):
            verify_native_catalog(document, TOPICS)

    def test_missing_case_is_incomplete_not_a_pass(self):
        document = catalog()
        document["cases"] = [e for e in document["cases"] if e["id"] != "rust-catalog-007-answer"]
        self.assertRejected(document, "missing cases")

    def test_duplicate_and_unexpected_cases_are_rejected(self):
        document = catalog()
        document["cases"].append(deepcopy(document["cases"][0]))
        self.assertRejected(document, "duplicate case")
        document = catalog()
        extra = deepcopy(document["cases"][0])
        extra["id"] = "rust-catalog-999-example"
        document["cases"].append(extra)
        self.assertRejected(document, "unexpected case")

    def test_tampered_stdout_hash_or_schema_is_rejected(self):
        document = catalog()
        case(document, "rust-catalog-001-example")["expectedStdout"] = "fake\n"
        self.assertRejected(document, "expectedStdout")

        document = catalog()
        case(document, "rust-catalog-001-example")["sourceSha256"] = "0" * 64
        self.assertRejected(document, "sourceSha256")

        document = catalog()
        case(document, "rust-catalog-001-answer")["source"] += "\n"
        self.assertRejected(document, "sourceSha256|source")

        document = catalog()
        document["schemaVersion"] = SCHEMA_VERSION + 1
        self.assertRejected(document, "schemaVersion")

        document = catalog()
        case(document, "rust-catalog-001-answer")["stdoutAsserted"] = True
        self.assertRejected(document, "stdoutAsserted")

    def test_bundle_tampering_is_rejected(self):
        document = catalog()
        case(document, "rust-catalog-007-example")["files"].pop("crates/mathlib/src/lib.rs")
        self.assertRejected(document, "files")

        document = catalog()
        case(document, "rust-catalog-007-example")["files"]["src/main.rs"] = "fn main() {}"
        self.assertRejected(document, "files")

        document = catalog()
        case(document, "rust-catalog-007-example")["filesSha256"].pop("Cargo.toml")
        self.assertRejected(document, "filesSha256")

    def test_stale_counts_are_rejected(self):
        document = catalog()
        document["catalog"]["runCount"] = 331
        self.assertRejected(document, "catalog")
        document = catalog()
        document["catalog"]["sourceSha256"]["topics_001_084.json"] = "0" * 64
        self.assertRejected(document, "catalog")


class NativeCatalogDriftTests(unittest.TestCase):
    def test_generated_file_matches_authored_sources(self):
        summary = generate(ROOT, check=True)
        self.assertEqual(summary["runCount"], 332)
        on_disk = (ROOT / DESTINATION).read_text(encoding="utf-8")
        self.assertEqual(on_disk, encode_document(catalog()))

    def test_check_fails_when_the_catalog_is_stale_or_absent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tool/rust_content").mkdir(parents=True)
            for name in ("topics_001_084.json", "topics_085_166.json"):
                shutil.copy(ROOT / "tool/rust_content" / name, root / "tool/rust_content" / name)
            (root / "scripts").mkdir()
            for name in ("generate_rust_content.py",):
                shutil.copy(ROOT / "scripts" / name, root / "scripts" / name)
            for asset in CATALOG_ASSETS:
                (root / asset).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(ROOT / asset, root / asset)

            with self.assertRaisesRegex(ContentError, "missing"):
                generate(root, check=True)

            generate(root)
            generate(root, check=True)

            destination = root / DESTINATION
            destination.write_text(
                destination.read_text(encoding="utf-8").replace(
                    '"answerCount": 166', '"answerCount": 165'
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ContentError, "stale"):
                generate(root, check=True)

    def test_paired_catalog_disagreement_is_detected(self):
        document = catalog()
        verify_paired_catalogs(ROOT, document)
        tampered = catalog()
        case(tampered, "rust-catalog-002-answer")["source"] = "fn main() {}"
        with self.assertRaisesRegex(ContentError, "differs from the authored catalog"):
            verify_native_catalog(tampered, TOPICS)

    def test_ui_catalog_drift_is_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for asset in CATALOG_ASSETS:
                (root / asset).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(ROOT / asset, root / asset)
            document = catalog()
            verify_paired_catalogs(root, document)

            examples_path = root / CATALOG_ASSETS[1]
            examples = json.loads(examples_path.read_text(encoding="utf-8"))
            examples["entries"][0]["code"] = "fn main() { println!(\"drift\"); }"
            examples_path.write_text(
                json.dumps(examples, ensure_ascii=False), encoding="utf-8"
            )
            with self.assertRaisesRegex(ContentError, "code differs"):
                verify_paired_catalogs(root, document)

            tutorials_path = root / CATALOG_ASSETS[0]
            shutil.copy(ROOT / CATALOG_ASSETS[0], tutorials_path)
            examples_path.unlink()
            shutil.copy(ROOT / CATALOG_ASSETS[1], examples_path)
            tutorials = json.loads(tutorials_path.read_text(encoding="utf-8"))
            tutorials["entries"][0]["lessons"][0]["exercises"][0]["answer"] = "fn main() {}"
            tutorials_path.write_text(
                json.dumps(tutorials, ensure_ascii=False), encoding="utf-8"
            )
            with self.assertRaisesRegex(ContentError, "answer differs"):
                verify_paired_catalogs(root, document)


if __name__ == "__main__":
    unittest.main()
