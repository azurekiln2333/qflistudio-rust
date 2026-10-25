"""Consumer entry-point checks using inert local records and no native tools."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import package_miri_runtime as package
import miri_build_support as support


class NoProcessConsumerTests(unittest.TestCase):
    def setUp(self):
        for name in ("run", "Popen", "call", "check_call", "check_output"):
            guard = patch.object(support.subprocess, name,
                                 side_effect=AssertionError("process execution forbidden"))
            guard.start()
            self.addCleanup(guard.stop)
        for module in (support, package):
            guard = patch.object(module, "run",
                                 side_effect=AssertionError("native tool execution forbidden"))
            guard.start()
            self.addCleanup(guard.stop)


class CompilerProvenanceConsumerTests(NoProcessConsumerTests):
    def setUp(self):
        super().setUp()
        temporary = tempfile.TemporaryDirectory(prefix="compiler-consumer-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.project = self.root / "project"
        self.project.mkdir()
        self.sentinel = self.project / "preserved.txt"
        self.sentinel.write_bytes(b"unchanged project bytes")
        self.adapter = self.root / "libqfli_miri.so"
        self.adapter.write_bytes(b"inert legacy adapter fixture")
        self.dependencies = self.root / "dependencies.json"
        self.dependencies.write_text(json.dumps({"packages": [], "resolve": {"nodes": []}}),
                                     encoding="utf-8")
        self.info = self.root / "adapter-build.json"
        self.info.write_text(json.dumps({
            "schemaVersion": 1,
            "rustVersion": support.RUST_VERSION,
            "rustCommit": support.RUST_COMMIT,
            "nativeHost": "x86_64-unknown-linux-gnu",
            "adapter": {"path": str(self.adapter),
                        "sha256": hashlib.sha256(self.adapter.read_bytes()).hexdigest()},
            "dependencyMetadata": {
                "path": str(self.dependencies),
                "sha256": hashlib.sha256(self.dependencies.read_bytes()).hexdigest()},
            "compilerLibraries": [],
            # Legacy records have no rebuilt compilerBuild/compilerBoundary.
        }), encoding="utf-8")
        self.downstream = []
        for name in ("collect_libraries", "guest_files", "license_files", "package_frameworks"):
            guard = patch.object(package, name,
                                 side_effect=AssertionError("legacy record reached " + name))
            self.downstream.append(guard.start())
            self.addCleanup(guard.stop)
        for name in ("copy2", "copytree"):
            guard = patch.object(package.shutil, name,
                                 side_effect=AssertionError("legacy record reached file copy"))
            self.downstream.append(guard.start())
            self.addCleanup(guard.stop)

    def assert_legacy_record_stops_before_packaging(self, validate_only):
        arguments = ["package_miri_runtime.py", "--build-info", str(self.info),
                     "--guest-sysroot", str(self.root / "guest"),
                     "--rust-source", str(self.root / "source"),
                     "--project-root", str(self.project)]
        if validate_only:
            arguments.append("--validate-only")
        with patch.object(package.sys, "argv", arguments):
            with self.assertRaisesRegex(ValueError, "lacks patched compiler provenance"):
                package.main()
        for mocked in self.downstream:
            mocked.assert_not_called()
        self.assertEqual(self.sentinel.read_bytes(), b"unchanged project bytes")
        self.assertEqual(list(self.project.iterdir()), [self.sentinel])

    def test_package_rejects_legacy_pinned_record_before_any_packaging_step(self):
        self.assert_legacy_record_stops_before_packaging(validate_only=False)

    def test_validate_only_rejects_legacy_record_before_dependency_collection(self):
        self.assert_legacy_record_stops_before_packaging(validate_only=True)


class VerifiedNativeCopyTests(NoProcessConsumerTests):
    def setUp(self):
        super().setUp()
        temporary = tempfile.TemporaryDirectory(prefix="verified-native-copy-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.source = self.root / "libqfli_miri.so"
        self.source.write_bytes(b"inert native library observed during collection")
        self.destination = self.root / "staged.so"
        self.observed = self.source.read_bytes()
        self.row = {"source": self.source, "name": self.source.name,
                    "sha256": hashlib.sha256(self.observed).hexdigest()}

    def test_unchanged_observed_native_bytes_are_copied_exactly(self):
        package.copy_verified_native(self.row, self.destination)
        self.assertEqual(self.destination.read_bytes(), self.observed)
        self.assertEqual(self.source.read_bytes(), self.observed)

    def test_source_changed_after_collection_cannot_be_packaged(self):
        self.source.write_bytes(b"replacement after the recorded observation")
        with self.assertRaisesRegex(ValueError, "Native input changed during packaging"):
            package.copy_verified_native(self.row, self.destination)

    def test_corrupted_destination_is_rejected_even_when_source_is_unchanged(self):
        real_copy = package.shutil.copy2

        def corrupted_copy(source, destination):
            result = real_copy(source, destination)
            Path(destination).write_bytes(b"corrupted copied artifact")
            return result

        with patch.object(package.shutil, "copy2", side_effect=corrupted_copy):
            with self.assertRaisesRegex(ValueError, "Native input changed during packaging"):
                package.copy_verified_native(self.row, self.destination)
        self.assertEqual(self.source.read_bytes(), self.observed)


if __name__ == "__main__":
    unittest.main()
