"""Regression checks for curriculum integrity and truthful compiler evidence."""

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from generate_rust_content import ContentError, build_documents, validate_topics
from verify_rust_content import run_command, verify_topic


def topic(number: int = 1) -> dict:
    return {
        "id": number, "title": f"Rust 所有权示例 {number}", "level": "beginner", "domain": "ownership",
        "summary": f"第 {number} 课使用一个有明确输入输出的完整程序，解释 String 移动后原变量为何不能再次使用。",
        "concepts": ["String", "move"], "objective": "能够判断变量移动后是否仍可使用，并使用借用避免多余复制。",
        "prerequisites": [], "explain": (f"本课 {number} 观察堆上字符串的所有权流转。let 绑定把 String 的所有权交给新变量；" * 5),
        "code": f'fn main() {{ let value = String::from("lesson {number}"); println!("{{value}}"); }}',
        "output": f"lesson {number}\n", "pitfalls": ["移动后的绑定不能再次读取，克隆则会创建独立堆分配。"],
        "exercise": {"prompt": "创建一个 String 并借用两次，证明原绑定仍可访问。", "hint": "使用 &String 或 &str 参数。", "answer": 'fn main() { let value = String::from("borrow"); println!("{} {}", &value, &value); }'},
        "runtime": "desktop",
    }


class ContentContractTests(unittest.TestCase):
    def test_preserves_stable_ids_source_pairing_and_complete_exercise(self):
        records = validate_topics([topic()], expected_count=1)
        documents = build_documents(records)
        lesson = documents["tutorials.json"]["entries"][0]["lessons"][0]
        example = documents["examples.json"]["entries"][0]
        self.assertEqual(lesson["id"], "rust-tutorial-001-lesson")
        self.assertEqual(example["sourceLessonId"], lesson["id"])
        self.assertEqual(example["code"], lesson["code"])
        self.assertEqual(lesson["exercises"][0]["answer"], records[0]["exercise"]["answer"])
        self.assertIn("移动端", lesson["explain"])

    def test_rejects_missing_duplicate_and_reused_content(self):
        with self.assertRaisesRegex(ContentError, "missing"):
            validate_topics([topic()], expected_count=2)
        with self.assertRaisesRegex(ContentError, "duplicates"):
            validate_topics([topic(), topic()], expected_count=2)
        repeated = topic(2)
        repeated["code"] = topic()["code"]
        with self.assertRaisesRegex(ContentError, "code: duplicates"):
            validate_topics([topic(), repeated], expected_count=2)

    def test_rejects_placeholder_and_incomplete_exercise(self):
        for field in ("explain", "code"):
            record = topic()
            record[field] += " todo!()"
            with self.assertRaisesRegex(ContentError, "placeholder"):
                validate_topics([record], expected_count=1)
        record = topic()
        record["exercise"]["answer"] = "println!(\"not a complete program\");"
        with self.assertRaisesRegex(ContentError, "complete runnable program"):
            validate_topics([record], expected_count=1)

    def test_bundles_remain_offline_and_inside_new_project(self):
        record = topic()
        record["files"] = {
            "Cargo.toml": '[package]\nname="sample"\nversion="0.1.0"\n',
            "src/main.rs": record["code"],
            "src/lib.rs": "pub fn size() -> usize { 3 }",
        }
        validate_topics([record], expected_count=1)
        for invalid in ("../outside.rs", "/absolute.rs", r"C:\outside.rs", ".qfli/project.json"):
            unsafe = deepcopy(record)
            unsafe["files"][invalid] = "fn main() {}"
            with self.assertRaises(ContentError):
                validate_topics([unsafe], expected_count=1)
        network = deepcopy(record)
        network["files"]["Cargo.toml"] += '\n[dependencies]\nremote="1"\n'
        with self.assertRaisesRegex(ContentError, "only bundled path dependencies"):
            validate_topics([network], expected_count=1)

    def test_cargo_project_output_is_distinct_from_standalone_stdout(self):
        record = topic()
        record["files"] = {
            "Cargo.toml": '[package]\nname="sample"\nversion="0.1.0"\n',
            "src/main.rs": record["code"],
        }
        record["projectOutput"] = "cargo-specific stdout\n"
        validate_topics([record], expected_count=1)
        invalid = deepcopy(record)
        invalid["projectOutput"] = 7
        with self.assertRaisesRegex(ContentError, "projectOutput"):
            validate_topics([invalid], expected_count=1)
        for stdout, status in (("cargo-specific stdout\n", "passed"), (record["output"], "failed")):
            with tempfile.TemporaryDirectory() as directory:
                with patch("verify_rust_content.verify_program", return_value={"status": "passed"}):
                    with patch("verify_rust_content.run_command", side_effect=[
                        {"exitCode": 0, "stdout": ""}, {"exitCode": 0, "stdout": stdout}
                    ]) as command:
                        result = verify_topic(record, Path(directory), Path("rustc"), Path("cargo"), 1, {}, [])
                self.assertEqual(result["project"]["status"], status)
                self.assertIn("--offline", command.call_args.args[0])

    def test_rejects_null_bundles_and_file_directory_aliases(self):
        record = topic()
        record['files'] = None
        with self.assertRaises(ContentError):
            validate_topics([record], expected_count=1)
        files = {
            'Cargo.toml': '[package]\nname="sample"\nversion="0.1.0"\n',
            'src/main.rs': record['code'],
        }
        for extra in (
            {'src/conflict': 'file', 'src/conflict/child.rs': 'file'},
            {'src/Foo/a.rs': 'file', 'src/foo/b.rs': 'file'},
        ):
            record['files'] = dict(files, **extra)
            with self.assertRaises(ContentError):
                validate_topics([record], expected_count=1)

    def test_process_failures_and_timeouts_do_not_become_passes(self):
        import os
        import sys
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            error = run_command([sys.executable, "-c", "raise SystemExit(7)"], path, 5, dict(os.environ))
            self.assertEqual(error["exitCode"], 7)
            timeout = run_command([sys.executable, "-c", "import time; time.sleep(5)"], path, 0.1, dict(os.environ))
            self.assertTrue(timeout["timedOut"])
            self.assertIsNone(timeout["exitCode"])


if __name__ == "__main__":
    unittest.main()
