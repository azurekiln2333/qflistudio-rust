"""Pure regressions for patched compiler and adapter build provenance.

All library bytes are inert fixtures. These tests prove record consistency and
rejection behavior, never compiler execution, ABI compatibility or confinement.
"""

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import miri_build_support as support


HOST = "x86_64-unknown-linux-ohos"
PATCH_PATHS = {
    "rustc_builtin_macros/src/env.rs",
    "rustc_interface/src/interface.rs",
    "rustc_parse/src/lib.rs",
    "rustc_session/src/config.rs",
    "rustc_session/src/options.rs",
    "rustc_span/src/source_map.rs",
    "rustc_metadata/src/creader.rs",
    "rustc_metadata/src/locator.rs",
}


def digest(value):
    return hashlib.sha256(value).hexdigest()


class NoProcessTests(unittest.TestCase):
    def setUp(self):
        # Prohibit process execution even if a helper later adds a preflight.
        for name in ("run", "Popen", "call", "check_call", "check_output"):
            guard = patch.object(support.subprocess, name,
                                 side_effect=AssertionError("process execution forbidden"))
            guard.start()
            self.addCleanup(guard.stop)
        guard = patch.object(support, "run",
                             side_effect=AssertionError("compiler execution forbidden"))
        guard.start()
        self.addCleanup(guard.stop)


class ProvenanceFixture(NoProcessTests):
    def setUp(self):
        super().setUp()
        temporary = tempfile.TemporaryDirectory(prefix="compiler-provenance-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.private = self.root / "private"
        self.runtime = self.root / "runtime"
        self.metadata = []
        for component in ("rustc_driver", "rustc_interface", "rustc_session"):
            self.metadata.append(self.write(
                self.private / f"lib/rustlib/{HOST}/lib/lib{component}-fixture.rmeta",
                (component + " private metadata").encode()))
        self.driver = self.write(self.runtime / "lib/librustc_driver-fixture.so",
                                 b"inert patched driver fixture")
        self.backend = self.write(
            self.runtime / f"lib/rustlib/{HOST}/codegen-backends/librustc_codegen_cranelift.so",
            b"inert patched backend fixture")
        self.adapter = self.write(self.root / "adapter/libqfli_miri.so", b"inert adapter fixture")
        self.compiler_record = self.root / "compiler-build.json"
        hunks = support.compiler_patch_hunks(support.compiler_boundary_patch())
        self.boundary = {
            "kind": support.COMPILER_BOUNDARY_KIND,
            "patchSha256": support.COMPILER_BOUNDARY_PATCH_SHA256,
            "sourceCommit": support.RUST_COMMIT,
            "inputTree": {"sha256": digest(b"original source tree"), "fileCount": 8},
            "patchedTree": {"sha256": digest(b"patched source tree"), "fileCount": 8},
            "patchedFiles": [
                {"path": "compiler/" + relative,
                 "beforeSha256": digest((relative + " original").encode()),
                 "afterSha256": digest((relative + " patched").encode())}
                for relative, _ in hunks
            ],
        }
        self.compiler = {
            "schemaVersion": 2,
            "status": "built",
            "rustVersion": support.RUST_VERSION,
            "rustCommit": support.RUST_COMMIT,
            "nativeHost": HOST,
            "compilerSysroot": str(self.private),
            "runtimeSysroot": str(self.runtime),
            "compilerBoundary": copy.deepcopy(self.boundary),
            "compilerArtifacts": support.compiler_artifacts(self.private, self.runtime),
        }
        self.save(self.compiler_record, self.compiler)
        binding = self.verify_compiler()
        self.adapter_record = self.root / "adapter-build.json"
        self.adapter_info = {
            "schemaVersion": 1,
            "rustVersion": support.RUST_VERSION,
            "rustCommit": support.RUST_COMMIT,
            "nativeHost": HOST,
            "adapter": {"path": str(self.adapter), "sha256": support.sha256(self.adapter)},
            "compilerBuild": binding,
            "compilerBoundary": copy.deepcopy(self.boundary),
            "compilerLibraries": support.compiler_libraries(self.runtime),
        }
        self.save(self.adapter_record, self.adapter_info)

    @staticmethod
    def write(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    @staticmethod
    def save(path, value):
        path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")

    def verify_compiler(self, **overrides):
        return support.verify_compiler_build(
            self.compiler_record, overrides.get("private", self.private),
            overrides.get("runtime", self.runtime), overrides.get("host", HOST))

    def verify_adapter(self, **overrides):
        return support.verify_adapter_build(
            self.adapter_record, overrides.get("adapter", self.adapter),
            overrides.get("private"), overrides.get("runtime"), overrides.get("host", HOST))


class CompilerProvenanceTests(ProvenanceFixture):
    def test_valid_patched_record_binds_exact_record_and_boundary(self):
        result = self.verify_compiler()
        self.assertEqual(result, {
            "path": str(self.compiler_record), "sha256": support.sha256(self.compiler_record),
            "compilerBoundary": self.boundary,
        })

    def test_stock_and_unbuilt_records_are_rejected(self):
        mutations = ({"schemaVersion": 1}, {"status": "configured"},
                     {"status": None}, {"compilerBoundary": {}},
                     {"rustVersion": "1.98.0"}, {"rustCommit": "0" * 40})
        for change in mutations:
            with self.subTest(change=change):
                self.save(self.compiler_record, self.compiler | change)
                with self.assertRaisesRegex(ValueError, "successfully built patched"):
                    self.verify_compiler()

    def test_missing_built_status_is_rejected(self):
        value = copy.deepcopy(self.compiler)
        del value["status"]
        self.save(self.compiler_record, value)
        with self.assertRaisesRegex(ValueError, "successfully built patched"):
            self.verify_compiler()

    def test_stale_patch_hash_is_rejected(self):
        value = copy.deepcopy(self.compiler)
        value["compilerBoundary"]["patchSha256"] = "0" * 64
        self.save(self.compiler_record, value)
        with self.assertRaisesRegex(ValueError, "successfully built patched"):
            self.verify_compiler()

    def test_wrong_native_host_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "successfully built patched"):
            self.verify_compiler(host="aarch64-unknown-linux-ohos")

    def test_selected_sysroots_cannot_change(self):
        for root in ("private", "runtime"):
            with self.subTest(root=root):
                with self.assertRaisesRegex(ValueError, "selected sysroot"):
                    self.verify_compiler(**{root: self.root / (root + "-other")})

    def test_missing_or_invalid_source_tree_identity_is_rejected(self):
        for key in ("inputTree", "patchedTree"):
            for identity in ({}, {"sha256": "not a digest", "fileCount": 8},
                             {"sha256": "a" * 64, "fileCount": 0}):
                with self.subTest(key=key, identity=identity):
                    value = copy.deepcopy(self.compiler)
                    value["compilerBoundary"][key] = identity
                    self.save(self.compiler_record, value)
                    with self.assertRaisesRegex(ValueError, "source-tree identities"):
                        self.verify_compiler()

    def test_incomplete_or_reordered_patch_file_proof_is_rejected(self):
        changes = self.compiler["compilerBoundary"]["patchedFiles"]
        for rows in (changes[:-1], list(reversed(changes))):
            with self.subTest(rows=rows):
                value = copy.deepcopy(self.compiler)
                value["compilerBoundary"]["patchedFiles"] = rows
                self.save(self.compiler_record, value)
                with self.assertRaisesRegex(ValueError, "patched source-file hashes"):
                    self.verify_compiler()

    def test_changed_private_metadata_driver_or_backend_is_rejected(self):
        for path in (self.metadata[1], self.driver, self.backend):
            with self.subTest(path=path.name):
                original = path.read_bytes()
                try:
                    path.write_bytes(original + b" changed after recording")
                    with self.assertRaisesRegex(ValueError, "private libraries differ"):
                        self.verify_compiler()
                finally:
                    path.write_bytes(original)

    def test_missing_and_extra_artifacts_are_rejected(self):
        original = self.metadata[0].read_bytes()
        self.metadata[0].unlink()
        with self.assertRaisesRegex(ValueError, "private libraries differ"):
            self.verify_compiler()
        self.metadata[0].write_bytes(original)
        self.write(self.runtime / "lib/unrecorded.so", b"unexpected library")
        with self.assertRaisesRegex(ValueError, "private libraries differ"):
            self.verify_compiler()

    def test_empty_artifact_record_is_rejected(self):
        self.save(self.compiler_record, self.compiler | {"compilerArtifacts": []})
        with self.assertRaisesRegex(ValueError, "no private-library hashes"):
            self.verify_compiler()

    def test_recomputed_inventory_does_not_hide_missing_required_metadata(self):
        self.metadata[2].unlink()
        value = self.compiler | {
            "compilerArtifacts": support.compiler_artifacts(self.private, self.runtime)}
        self.save(self.compiler_record, value)
        with self.assertRaisesRegex(ValueError, "metadata missing: rustc_session"):
            self.verify_compiler()

    def test_recomputed_inventory_does_not_hide_missing_backend(self):
        self.backend.unlink()
        value = self.compiler | {
            "compilerArtifacts": support.compiler_artifacts(self.private, self.runtime)}
        self.save(self.compiler_record, value)
        with self.assertRaisesRegex(ValueError, "runtime missing: rustc_codegen"):
            self.verify_compiler()


class AdapterProvenanceTests(ProvenanceFixture):
    def test_valid_adapter_defaults_to_recorded_roots(self):
        self.assertEqual(self.verify_adapter(), self.adapter_info)
        self.assertEqual(self.verify_adapter(private=self.private, runtime=self.runtime),
                         self.adapter_info)

    def test_legacy_adapter_record_is_rejected(self):
        value = copy.deepcopy(self.adapter_info)
        del value["compilerBuild"]
        self.save(self.adapter_record, value)
        with self.assertRaisesRegex(ValueError, "lacks patched compiler provenance"):
            self.verify_adapter()

    def test_adapter_target_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "pinned compiler/host"):
            self.verify_adapter(host="aarch64-unknown-linux-ohos")

    def test_changed_compiler_record_is_rejected_even_if_still_valid(self):
        self.compiler_record.write_text(self.compiler_record.read_text() + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Compiler build record differs"):
            self.verify_adapter()

    def test_adapter_boundary_must_match_compiler_record(self):
        for location in ("compilerBoundary", "compilerBuild"):
            with self.subTest(location=location):
                value = copy.deepcopy(self.adapter_info)
                boundary = (value[location] if location == "compilerBoundary"
                            else value[location]["compilerBoundary"])
                boundary["patchSha256"] = "0" * 64
                self.save(self.adapter_record, value)
                with self.assertRaisesRegex(ValueError, "boundary differs"):
                    self.verify_adapter()

    def test_changed_adapter_bytes_are_rejected(self):
        self.adapter.write_bytes(b"different adapter")
        with self.assertRaisesRegex(ValueError, "Adapter differs"):
            self.verify_adapter()

    def test_same_adapter_bytes_at_different_path_are_rejected(self):
        other = self.write(self.root / "other/libqfli_miri.so", self.adapter.read_bytes())
        with self.assertRaisesRegex(ValueError, "Adapter differs"):
            self.verify_adapter(adapter=other)

    def test_adapter_selected_root_override_cannot_bypass_compiler_record(self):
        with self.assertRaisesRegex(ValueError, "selected sysroot"):
            self.verify_adapter(runtime=self.root / "other-runtime")

    def test_adapter_compiler_library_binding_must_be_complete(self):
        for libraries in ([], self.adapter_info["compilerLibraries"][:-1]):
            with self.subTest(libraries=libraries):
                self.save(self.adapter_record, self.adapter_info | {"compilerLibraries": libraries})
                with self.assertRaisesRegex(ValueError, "compiler libraries differ"):
                    self.verify_adapter()


class MappedProvenanceTests(ProvenanceFixture):
    """Producer aliases locate local fixture bytes without network/WSL access."""

    def setUp(self):
        super().setUp()
        self.producer_root = "/producer/qfli-build"
        self.compiler["compilerSysroot"] = self.producer_path(self.private)
        self.compiler["runtimeSysroot"] = self.producer_path(self.runtime)
        self.save(self.compiler_record, self.compiler)
        self.adapter_info["compilerBuild"]["path"] = self.producer_path(self.compiler_record)
        self.adapter_info["compilerBuild"]["sha256"] = support.sha256(self.compiler_record)
        self.adapter_info["adapter"]["path"] = self.producer_path(self.adapter)
        for row in self.adapter_info["compilerLibraries"]:
            row["path"] = self.producer_path(Path(row["path"]))
        self.save(self.adapter_record, self.adapter_info)
        self.mapped_values = []

    def producer_path(self, path):
        return self.producer_root + "/" + path.relative_to(self.root).as_posix()

    def mapped_path(self, value):
        value = str(value)
        self.mapped_values.append(value)
        if value == self.producer_root:
            return self.root
        prefix = self.producer_root + "/"
        if value.startswith(prefix):
            return self.root / value[len(prefix):]
        return Path(value)

    def verify_mapped_compiler(self, **overrides):
        return support.verify_compiler_build(
            self.producer_path(self.compiler_record),
            overrides.get("private", self.producer_path(self.private)),
            overrides.get("runtime", self.producer_path(self.runtime)), HOST,
            path_mapper=overrides.get("mapper", self.mapped_path))

    def verify_mapped_adapter(self, **overrides):
        return support.verify_adapter_build(
            self.producer_path(self.adapter_record),
            overrides.get("adapter", self.producer_path(self.adapter)),
            native_host=HOST, path_mapper=overrides.get("mapper", self.mapped_path))

    def test_mapped_compiler_accepts_the_same_hash_bound_fixture_bytes(self):
        result = self.verify_mapped_compiler()
        self.assertEqual(result["path"], str(self.compiler_record))
        self.assertEqual(result["sha256"], support.sha256(self.compiler_record))
        self.assertEqual(result["compilerBoundary"], self.boundary)
        self.assertIn(self.producer_path(self.private), self.mapped_values)
        self.assertIn(self.producer_path(self.runtime), self.mapped_values)

    def test_mapped_adapter_preserves_all_producer_paths_in_returned_record(self):
        before = copy.deepcopy(self.adapter_info)
        result = self.verify_mapped_adapter()
        self.assertEqual(result, before)
        self.assertEqual(result["compilerBuild"]["path"],
                         self.producer_path(self.compiler_record))
        self.assertEqual(result["adapter"]["path"], self.producer_path(self.adapter))
        self.assertTrue(all(row["path"].startswith(self.producer_root + "/")
                            for row in result["compilerLibraries"]))
        self.assertEqual(json.loads(self.adapter_record.read_text()), before)
        self.assertIn(self.producer_path(self.driver), self.mapped_values)
        self.assertIn(self.producer_path(self.backend), self.mapped_values)
        # A consumer may select the mapped local adapter path explicitly.
        self.assertEqual(self.verify_mapped_adapter(adapter=self.adapter), before)

    def test_wrong_mapped_root_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "selected sysroot"):
            self.verify_mapped_compiler(runtime=self.producer_root + "/wrong-runtime")

    def test_changed_mapped_compiler_record_is_rejected(self):
        self.compiler_record.write_text(self.compiler_record.read_text() + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Compiler build record differs"):
            self.verify_mapped_adapter()

    def test_changed_mapped_artifact_is_rejected_by_both_entry_points(self):
        self.driver.write_bytes(b"changed after producer record")
        for verify in (self.verify_mapped_compiler, self.verify_mapped_adapter):
            with self.subTest(entry=verify.__name__):
                with self.assertRaisesRegex(ValueError, "private libraries differ"):
                    verify()

    def test_wrong_mapped_library_location_is_not_accepted_for_identical_bytes(self):
        other = self.write(self.root / "outside/librustc_driver-fixture.so", self.driver.read_bytes())
        producer_driver = self.producer_path(self.driver)

        def wrong_library(value):
            return other if str(value) == producer_driver else self.mapped_path(value)

        with self.assertRaisesRegex(ValueError, "compiler libraries differ"):
            self.verify_mapped_adapter(mapper=wrong_library)

    def test_wrong_mapped_adapter_location_is_rejected(self):
        other = self.write(self.root / "outside/libqfli_miri.so", self.adapter.read_bytes())
        with self.assertRaisesRegex(ValueError, "Adapter differs"):
            self.verify_mapped_adapter(adapter=other)


class WindowsWslPathMapperTests(NoProcessTests):
    def test_drive_mount_unc_mount_and_native_paths_map_without_access(self):
        # Replace the path factory with an inert string recorder. This checks
        # mapping syntax on every test host without constructing/accessing UNC.
        with patch.object(support.os, "name", "nt"), patch.object(support, "Path", side_effect=str):
            mapper = support.windows_wsl_path_mapper("qfli-java-build")
            self.assertEqual(mapper("/mnt/d/projects/compiler-build.json"),
                             "D:/projects/compiler-build.json")
            self.assertEqual(mapper("/mnt/C/compiler/lib"), "C:/compiler/lib")
            self.assertEqual(mapper("/home/dev/compiler"),
                             "//wsl.localhost/qfli-java-build/home/dev/compiler")
            self.assertEqual(mapper("relative.json"), "relative.json")
            self.assertEqual(mapper("D:/local/adapter.dll"), "D:/local/adapter.dll")

    def test_distribution_names_cannot_inject_mount_components(self):
        with patch.object(support.os, "name", "nt"):
            for distro in ("", "../other", "bad/name", "bad name", ".hidden", "x\\other"):
                with self.subTest(distro=distro):
                    with self.assertRaisesRegex(ValueError, "explicit distribution"):
                        support.windows_wsl_path_mapper(distro)

    def test_non_windows_host_rejects_wsl_mapping(self):
        with patch.object(support.os, "name", "posix"):
            with self.assertRaisesRegex(ValueError, "requires Windows"):
                support.windows_wsl_path_mapper("qfli-java-build")


class DisjointBuildRootTests(NoProcessTests):
    def setUp(self):
        super().setUp()
        temporary = tempfile.TemporaryDirectory(prefix="build-root-relation-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.protected = self.root / "ProtectedCompiler"
        self.protected.mkdir()

    def assert_overlap_rejected(self, output, *inputs):
        with self.assertRaisesRegex(ValueError, "overlaps protected input"):
            support.ensure_disjoint_build_root(output, *inputs)

    def local_link(self):
        alias = self.root / "compiler-alias"
        try:
            alias.symlink_to(self.protected, target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            self.skipTest("Local directory links unavailable: " + str(error))
        return alias

    def test_input_and_output_equal_is_rejected(self):
        self.assert_overlap_rejected(self.protected, self.protected)

    def test_output_inside_input_is_rejected_before_creating_output(self):
        output = self.protected / "build/stage-not-created"
        self.assert_overlap_rejected(output, self.protected)
        self.assertFalse(output.exists())

    def test_input_inside_output_is_rejected(self):
        self.assert_overlap_rejected(self.root, self.protected)

    def test_disjoint_sibling_output_is_accepted_without_creating_it(self):
        output = self.root / "ProtectedCompiler-build"
        self.assertEqual(support.ensure_disjoint_build_root(output, self.protected),
                         output.resolve())
        self.assertFalse(output.exists())

    def test_overlap_in_any_of_multiple_inputs_is_rejected(self):
        unrelated = self.root / "miri-source"
        unrelated.mkdir()
        self.assert_overlap_rejected(self.protected / "build", unrelated, self.protected)

    def test_parent_components_cannot_disguise_equal_path(self):
        self.assert_overlap_rejected(self.protected / "uncreated/..", self.protected)

    @unittest.skipUnless(support.os.name == "nt", "Windows case aliases require Windows")
    def test_windows_case_alias_is_rejected(self):
        alias = Path(str(self.protected).swapcase())
        self.assert_overlap_rejected(alias, self.protected)
        self.assert_overlap_rejected(alias / "nested-output", self.protected)

    def test_resolved_directory_link_cannot_disguise_equal_output(self):
        self.assert_overlap_rejected(self.local_link(), self.protected)

    def test_resolved_directory_link_cannot_hide_output_inside_input(self):
        alias = self.local_link()
        self.assert_overlap_rejected(alias / "uncreated-output", self.protected)

    def test_resolved_input_link_cannot_hide_input_inside_output(self):
        self.assert_overlap_rejected(self.protected, self.local_link())


class CompilerPatchParserTests(NoProcessTests):
    def parse(self, text):
        with tempfile.TemporaryDirectory(prefix="compiler-patch-test-") as directory:
            path = Path(directory) / "change.patch"
            path.write_text(text, encoding="utf-8")
            return support.compiler_patch_hunks(path)

    def test_reviewed_patch_has_exact_eight_required_paths(self):
        rows = support.compiler_patch_hunks(support.compiler_boundary_patch())
        self.assertEqual(len(rows), 8)
        self.assertEqual({relative for relative, _ in rows}, PATCH_PATHS)
        for relative, hunks in rows:
            with self.subTest(relative=relative):
                self.assertTrue(hunks)

    def test_valid_existing_file_hunk_preserves_before_and_after(self):
        rows = self.parse("diff --git a/a.rs b/a.rs\n--- a/a.rs\n+++ b/a.rs\n"
                          "@@ -2,2 +2,2 @@\n context\n-before\n+after\n")
        self.assertEqual(rows, [("a.rs", [(1, 1, ["context", "before"], ["context", "after"])])])

    def test_path_escape_rename_and_duplicate_paths_are_rejected(self):
        valid = "diff --git a/a.rs b/a.rs\n@@ -1 +1 @@\n-old\n+new\n"
        cases = (valid.replace("a/a.rs", "a/../a.rs").replace("b/a.rs", "b/../a.rs"),
                 valid.replace("b/a.rs", "b/b.rs"), valid + valid)
        for text in cases:
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    self.parse(text)

    def test_incomplete_and_mismatched_hunks_are_rejected(self):
        cases = ("", "diff --git a/a.rs b/a.rs\n",
                 "diff --git a/a.rs b/a.rs\n@@ -1,2 +1 @@\n-old\n+new\n")
        for text in cases:
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    self.parse(text)

    def test_changed_reviewed_patch_bytes_are_rejected(self):
        with tempfile.TemporaryDirectory(prefix="compiler-patch-hash-test-") as directory:
            changed = Path(directory) / "changed.patch"
            changed.write_bytes(support.COMPILER_BOUNDARY_PATCH.read_bytes() + b"\n")
            with patch.object(support, "COMPILER_BOUNDARY_PATCH", changed):
                with self.assertRaisesRegex(ValueError, "reviewed SHA-256"):
                    support.compiler_boundary_patch()


if __name__ == "__main__":
    unittest.main()
