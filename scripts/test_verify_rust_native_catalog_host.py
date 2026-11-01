#!/usr/bin/env python3
"""Failure, isolation and evidence contracts for the host-only embedded runner."""

import ctypes
from contextlib import redirect_stderr
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from generate_rust_content import ContentError, ROOT, load_topics
from generate_rust_native_catalog import DESTINATION, verify_native_catalog, verify_paired_catalogs
from verify_rust_native_catalog_host import (QfliConfig, QfliResult, assess_case,
                                            channel_record, main, materialize_case,
                                            refresh_report, run_native, run_process,
                                            text_hash, worker, write_json)


def sample_case(*, bundle=False, asserted=True):
    source = 'fn main() { println!("你好"); }\r\n'
    files = {"Cargo.toml": '[package]\nname="fixture"\nversion="0.1.0"\n',
             "src/main.rs": source, "src/helper.rs": "pub fn value() -> u8 { 1 }\n"} if bundle else None
    return {"id": "rust-catalog-001-example", "topicId": 1, "kind": "example", "runtime": "cargo",
            "entryFile": "src/main.rs" if bundle else "main.rs", "source": source,
            "sourceSha256": text_hash(source), "files": files,
            "filesSha256": {name: text_hash(code) for name, code in files.items()} if files else None,
            "bundleVerify": "test" if bundle else None, "expectedExitCode": 0,
            "expectedStdout": "你好\n" if asserted else None, "stdoutAsserted": asserted}


def native_result(case, stdout="你好\n".encode("utf-8")):
    root = (Path(tempfile.gettempdir()) / "qfli-native-fixture" / case["id"]).resolve()
    return {"id": case["id"], "sourceSha256": case["sourceSha256"], "abiVersion": 1,
            "filesSha256": case["filesSha256"] or {case["entryFile"]: case["sourceSha256"]},
            "session": {"constructor": "qfli_miri_create_with_project", "projectRoot": str(root),
                        "sourcePath": str(root / case["entryFile"]), "backendPath": None,
                        "filesystemRoot": str(root), "filesystemRootMode": "explicit_project"},
            "nativeRunReturn": 0, "nativeResultReturn": 0, "state": 2, "exitCode": 0,
            "channels": {name: channel_record(stdout if name == "stdout" else b"")
                         for name in ("stdout", "stderr", "diagnostics")}}


def successful_process():
    return {"exitCode": 0, "timedOut": False, "seconds": 0.1,
            "stdout": channel_record(b""), "stderr": channel_record(b"")}


def native_library(*, with_project=True, rejected=False):
    """A callable ABI fixture, including copied C result/output buffers."""
    channels = ["你好\n".encode("utf-8"), b"", b"warning: fixture warning\n"]

    def copy_output(_session, channel, buffer, capacity):
        data = channels[channel]
        if buffer is not None:
            ctypes.memmove(buffer, data, min(capacity, len(data)))
        return len(data)

    def read_result(_session, pointer):
        pointer._obj.state = 2
        pointer._obj.exit_code = 0
        return 0

    result = SimpleNamespace(qfli_miri_abi_version=Mock(return_value=1),
                             qfli_miri_create=Mock(return_value=0 if rejected else 1),
                             qfli_miri_create_with_backend=Mock(return_value=0 if rejected else 1),
                             qfli_miri_run=Mock(return_value=0), qfli_miri_result=Mock(side_effect=read_result),
                             qfli_miri_copy_output=Mock(side_effect=copy_output), qfli_miri_destroy=Mock())
    if with_project:
        result.qfli_miri_create_with_project = Mock(return_value=0 if rejected else 1)
    return result


def native_job(case, directory, backend=None):
    return {"case": case, "directory": str(directory), "library": "fixture-adapter",
            "sysroot": str(directory.parent / "sysroot"), "backend": backend,
            "result": str(directory.parent / "result.json"),
            "limits": {"maxBasicBlocks": 1000, "nativeTimeoutMs": 1000,
                       "maxOutputBytes": 1024, "maxGuestMemoryBytes": 1024 * 1024}}


class HostCatalogTests(unittest.TestCase):
    def test_current_inventory_contains_every_authored_main_and_answer(self):
        catalog = json.loads((ROOT / DESTINATION).read_text(encoding="utf-8"))
        counts = verify_native_catalog(catalog, load_topics(ROOT / "tool/rust_content"))
        verify_paired_catalogs(ROOT, catalog)
        self.assertEqual(counts["runCount"], counts["lessonCount"] * 2)
        self.assertEqual(len(catalog["cases"]), counts["runCount"])

    @unittest.skipUnless(ctypes.sizeof(ctypes.c_void_p) == 8, "ABI reference is 64-bit")
    def test_ctypes_layout_matches_the_unchanged_abi1_c_header(self):
        self.assertEqual(ctypes.sizeof(QfliConfig), 72)
        self.assertEqual(QfliConfig.source_path.offset, 8)
        self.assertEqual(QfliConfig.stdin_len.offset, 32)
        self.assertEqual(QfliConfig.max_guest_memory_bytes.offset, 64)
        self.assertEqual(ctypes.sizeof(QfliResult), 24)
        self.assertEqual(QfliResult.basic_blocks.offset, 8)

    def test_safe_bundle_materialization_preserves_exact_source_and_all_files(self):
        case = sample_case(bundle=True)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "fresh"
            entry, hashes = materialize_case(case, root)
            self.assertEqual(entry, root.resolve() / "src/main.rs")
            self.assertEqual(entry.read_bytes(), case["source"].encode("utf-8"))
            self.assertEqual(hashes, case["filesSha256"])
            self.assertTrue((root / "src/helper.rs").is_file())
            with self.assertRaises(FileExistsError):
                materialize_case(case, root)

    def test_unsafe_bundle_paths_reject_before_creating_the_owned_directory(self):
        for name in ("../escape.rs", "/tmp/escape.rs", r"C:\escape.rs", "src/../escape.rs",
                     "src//escape.rs", "src/./escape.rs", "src/\x00escape.rs"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                case = sample_case(bundle=True)
                case["files"][name] = "source"
                case["filesSha256"][name] = text_hash("source")
                root = Path(temporary) / "fresh"
                with self.assertRaises(ContentError):
                    materialize_case(case, root)
                self.assertFalse(root.exists())

    def test_stale_source_or_bundle_hash_never_reaches_execution(self):
        for field in ("source", "bundle"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                case = sample_case(bundle=True)
                if field == "source":
                    case["source"] += "// changed"
                else:
                    case["files"]["src/helper.rs"] += "// changed"
                root = Path(temporary) / "fresh"
                with self.assertRaises(ContentError):
                    materialize_case(case, root)
                self.assertFalse(root.exists())

    def test_project_constructor_receives_complete_materialized_root_and_optional_backend(self):
        for backend_name in (None, "backend.so"):
            with self.subTest(backend=backend_name), tempfile.TemporaryDirectory() as temporary:
                case = sample_case(bundle=True)
                directory = Path(temporary) / "fresh"
                backend = str((Path(temporary) / backend_name).resolve()) if backend_name else None
                library = native_library()
                with patch("verify_rust_native_catalog_host.ctypes.CDLL", return_value=library), \
                        patch("verify_rust_native_catalog_host.os.chdir"):
                    result = run_native(native_job(case, directory, backend))
                arguments = library.qfli_miri_create_with_project.call_args.args
                self.assertEqual(arguments[0]._obj.source_path, str(directory.resolve() / "src/main.rs").encode("utf-8"))
                self.assertEqual(arguments[1], backend.encode("utf-8") if backend else None)
                self.assertEqual(arguments[2], str(directory.resolve()).encode("utf-8"))
                self.assertEqual(len(library.qfli_miri_create_with_project.argtypes), 3)
                library.qfli_miri_create.assert_not_called()
                library.qfli_miri_create_with_backend.assert_not_called()
                library.qfli_miri_destroy.assert_called_once_with(1)
                self.assertEqual(result["session"]["filesystemRoot"], str(directory.resolve()))
                self.assertEqual(result["session"]["filesystemRootMode"], "explicit_project")
                self.assertEqual(assess_case(case, result, successful_process(), project_root=directory,
                                             backend=Path(backend) if backend else None)["status"], "passed")

    def test_old_adapters_report_source_parent_fallback_without_claiming_full_root(self):
        for backend_name in (None, "backend.so"):
            with self.subTest(backend=backend_name), tempfile.TemporaryDirectory() as temporary:
                case = sample_case(bundle=True)
                directory = Path(temporary) / "fresh"
                backend = str((Path(temporary) / backend_name).resolve()) if backend_name else None
                library = native_library(with_project=False)
                with patch("verify_rust_native_catalog_host.ctypes.CDLL", return_value=library), \
                        patch("verify_rust_native_catalog_host.os.chdir"):
                    result = run_native(native_job(case, directory, backend))
                constructor = "qfli_miri_create_with_backend" if backend else "qfli_miri_create"
                self.assertEqual(result["session"]["constructor"], constructor)
                self.assertEqual(result["session"]["projectRoot"], str(directory.resolve()))
                self.assertEqual(result["session"]["filesystemRoot"], str(directory.resolve() / "src"))
                self.assertEqual(result["session"]["filesystemRootMode"], "legacy_source_parent")
                getattr(library, constructor).assert_called_once()
                self.assertEqual(assess_case(case, result, successful_process(), project_root=directory,
                                             backend=Path(backend) if backend else None)["status"], "passed")

    def test_project_constructor_rejection_preserves_evidence_and_never_falls_back(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "fresh"
            job = native_job(sample_case(bundle=True), directory)
            job_path = Path(temporary) / "job.json"
            write_json(job_path, job)
            library = native_library(rejected=True)
            with patch("verify_rust_native_catalog_host.ctypes.CDLL", return_value=library), \
                    patch("verify_rust_native_catalog_host.os.chdir"):
                self.assertEqual(worker(job_path), 2)
            result = json.loads(Path(job["result"]).read_text(encoding="utf-8"))
            self.assertIn("rejected", result["error"])
            self.assertEqual(result["session"]["constructor"], "qfli_miri_create_with_project")
            self.assertEqual(result["session"]["projectRoot"], str(directory.resolve()))
            library.qfli_miri_create.assert_not_called()
            library.qfli_miri_create_with_backend.assert_not_called()
            library.qfli_miri_run.assert_not_called()
            library.qfli_miri_destroy.assert_not_called()

    def test_wrong_or_missing_constructor_root_evidence_cannot_pass(self):
        case = sample_case(bundle=True)
        for field, value in (("constructor", "unknown"), ("projectRoot", "relative"),
                             ("sourcePath", str(Path(tempfile.gettempdir()).resolve() / "outside.rs")),
                             ("filesystemRoot", str(Path(tempfile.gettempdir()).resolve())),
                             ("filesystemRootMode", "legacy_source_parent"),
                             ("backendPath", str(Path(tempfile.gettempdir()).resolve() / "other.so"))):
            with self.subTest(field=field):
                native = native_result(case)
                native["session"][field] = value
                self.assertEqual(assess_case(case, native, successful_process())["status"], "failed")
        native = native_result(case)
        del native["session"]
        self.assertEqual(assess_case(case, native, successful_process())["status"], "failed")
        native = native_result(case)
        wrong_root = Path(native["session"]["projectRoot"]).parent / "another-job"
        self.assertEqual(assess_case(case, native, successful_process(), project_root=wrong_root)["status"], "failed")

    def test_only_crlf_normalization_is_allowed_in_exact_stdout(self):
        case = sample_case()
        for stdout, passed in (("你好\r\n".encode("utf-8"), True),
                               ("你好 \n".encode("utf-8"), False),
                               (b"\xff\n", False)):
            with self.subTest(stdout=stdout):
                result = assess_case(case, native_result(case, stdout), successful_process())
                self.assertEqual(result["status"] == "passed", passed)

    def test_no_authored_answer_output_is_explicitly_unasserted(self):
        case = sample_case(asserted=False)
        result = assess_case(case, native_result(case, b"some answer output"), successful_process())
        self.assertEqual(result["status"], "passed")
        self.assertIsNone(result["stdoutMatched"])
        self.assertFalse(result["stdoutAsserted"])

    def test_unasserted_stdout_still_requires_valid_utf8(self):
        case = sample_case(asserted=False)
        result = assess_case(case, native_result(case, b"\xff"), successful_process())
        self.assertEqual(result["status"], "failed")

    def test_diagnostics_warnings_are_retained_and_corrupt_channel_evidence_fails(self):
        case = sample_case()
        native = native_result(case)
        native["channels"]["diagnostics"] = channel_record(b"warning: fixture warning\n")
        self.assertEqual(assess_case(case, native, successful_process())["status"], "passed")
        for field, value in (("text", "hidden diagnostic"), ("bytes", 1), ("sha256", "0" * 64),
                             ("base64", "not base64!")):
            with self.subTest(field=field):
                corrupted = native_result(case)
                corrupted["channels"]["diagnostics"][field] = value
                self.assertEqual(assess_case(case, corrupted, successful_process())["status"], "failed")

    def test_main_entry_pass_does_not_claim_cargo_builds_or_tests(self):
        case = sample_case(bundle=True)
        result = assess_case(case, native_result(case), successful_process())
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["bundleVerification"]["requestedOperation"], "test")
        self.assertEqual(result["bundleVerification"]["cargoBuildAllTargets"], "not_run")
        self.assertEqual(result["bundleVerification"]["cargoTest"], "not_run")

    def test_native_failure_limit_wrong_exit_and_identity_cannot_pass(self):
        case = sample_case()
        for field, value in (("state", 4), ("exitCode", 9), ("nativeRunReturn", -1),
                             ("nativeResultReturn", -1), ("id", "another-case"), ("abiVersion", 2)):
            with self.subTest(field=field):
                native = native_result(case)
                native[field] = value
                self.assertEqual(assess_case(case, native, successful_process())["status"], "failed")

    def test_missing_malformed_and_corrupt_worker_evidence_fail(self):
        case = sample_case()
        corrupt = native_result(case)
        corrupt["channels"]["stdout"]["sha256"] = "0" * 64
        for native in (None, [], {"error": "loader failed"}, corrupt):
            with self.subTest(native=native):
                self.assertEqual(assess_case(case, native, successful_process())["status"], "failed")

    def test_timeout_is_reaped_and_followed_by_a_fresh_successful_worker(self):
        with tempfile.TemporaryDirectory() as temporary:
            cwd = Path(temporary)
            first = run_process([sys.executable, "-c", "import time; time.sleep(30)"],
                                cwd=cwd, env=dict(os.environ), timeout=0.1)
            self.assertTrue(first["timedOut"])
            self.assertIsNotNone(first["exitCode"])
            second = run_process([sys.executable, "-c", "print('fresh marker')"],
                                 cwd=cwd, env=dict(os.environ), timeout=5)
            self.assertFalse(second["timedOut"])
            self.assertEqual(second["exitCode"], 0)
            self.assertIn("fresh marker", second["stdout"]["text"])

    def test_partial_reports_keep_missing_cases_and_do_not_hide_worker_crash(self):
        first = sample_case()
        second = {**first, "id": "rust-catalog-001-answer", "kind": "answer"}
        report = {"results": [], "mobileExecution": "not_tested", "ohosAcceptance": "not_established"}
        process = successful_process()
        process["exitCode"] = -11
        report["results"].append(assess_case(first, None, process))
        refresh_report(report, [first, second])
        self.assertEqual(report["status"], "incomplete")
        self.assertEqual(report["missingIds"], [second["id"]])
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "partial.json"
            write_json(path, report)
            self.assertEqual(json.loads(path.read_text())["missingIds"], [second["id"]])
            self.assertFalse(path.with_suffix(".json.tmp").exists())
        report["results"].append(assess_case(second, native_result(second), successful_process()))
        refresh_report(report, [first, second])
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["attemptedCases"], 2)
        self.assertEqual(report["passedCases"], 1)
        self.assertEqual(report["mobileExecution"], "not_tested")
        self.assertEqual(report["ohosAcceptance"], "not_established")

    def test_reports_reject_duplicate_unexpected_or_forged_pass_evidence(self):
        case = sample_case()
        for corruption in ("duplicate", "unexpected", "metadata", "native", "status"):
            with self.subTest(corruption=corruption):
                result = assess_case(case, native_result(case), successful_process())
                report = {"results": [result]}
                if corruption == "duplicate":
                    report["results"].append(result.copy())
                elif corruption == "unexpected":
                    report["results"].append({**result, "id": "unknown-case"})
                elif corruption == "metadata":
                    result["sourceSha256"] = "0" * 64
                elif corruption == "native":
                    result["native"]["exitCode"] = 9
                else:
                    result["status"] = "failed"
                refresh_report(report, [case])
                self.assertEqual(report["status"], "failed")
                self.assertFalse(report["executionComplete"])
                self.assertTrue(report["failedCases"])

    def test_report_rechecks_actual_stdout_even_when_result_claims_passed(self):
        case = sample_case()
        result = assess_case(case, native_result(case), successful_process())
        result["native"]["channels"]["stdout"] = channel_record("你好\n\n".encode("utf-8"))
        report = {"results": [result]}
        refresh_report(report, [case])
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["passedCases"], 0)
        self.assertEqual(report["invalidEvidenceIds"], [case["id"]])

    def test_empty_inventory_or_malformed_results_never_pass(self):
        report = {"results": []}
        refresh_report(report, [])
        self.assertEqual(report["status"], "incomplete")
        self.assertFalse(report["executionComplete"])
        case = sample_case()
        for result in (None, [], {"id": case["id"]}):
            with self.subTest(result=result):
                report = {"results": [result]}
                refresh_report(report, [case])
                self.assertNotEqual(report["status"], "passed")
                self.assertFalse(report["executionComplete"])

    def test_unsupported_host_preserves_the_entire_unexecuted_inventory(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "reference.json"
            with patch.object(sys, "argv", ["host-preflight", "--report", str(path)]), \
                    patch.object(sys, "platform", "unsupported"), redirect_stderr(io.StringIO()):
                self.assertEqual(main(), 2)
            report = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["attemptedCases"], 0)
            self.assertEqual(len(report["missingIds"]), report["expectedCases"])
            self.assertFalse(report["executionComplete"])
            self.assertEqual(report["mobileExecution"], "not_tested")
            self.assertEqual(report["cargoBundles"]["status"], "unverified")


if __name__ == "__main__":
    unittest.main()
