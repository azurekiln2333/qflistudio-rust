"""Hermetic application-quality contracts; executed only by hosted cloud jobs."""

import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import app_quality as quality
from ci_support import CORE_DIRECTORY, CORE_REPOSITORY, read_json, sha256, write_json


SOURCE_SHA = "a" * 40
CORE_SHA = "b" * 40


def setUpModule():
    quality.require_hosted_runner()


class QualityFixtures(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.parent = Path(self.temporary.name).resolve()
        self.root = self.parent / "qflistudio-rust"
        self.core = self.parent / CORE_DIRECTORY
        self.scratch = self.parent / "runner-temp"
        self.sdk = self.scratch / "approved-flutter"
        self.args = quality.quality_args(self.root)
        for directory in (self.root, self.core, self.sdk, self.args.output, self.args.bootstrap):
            directory.mkdir(parents=True, exist_ok=True)
        self.write("lib/main.dart", "void main() {}\n")
        self.write("test/one_test.dart", "void main() {}\n")
        self.write("test/two_test.dart", "void main() {}\n")
        self.write("integration_test/device_test.dart", "void main() {}\n")
        self.write("analysis_options.yaml", "include: package:flutter_lints/flutter.yaml\n")
        self.write("pubspec.yaml", "name: qfli_rust\nversion: 1.0.0+1\ndependencies:\n"
                   "  qfli_studio_core:\n    path: ../qflistudio-core\n"
                   "dependency_overrides:\n  re_editor:\n    path: ../qflistudio-core/vendor/re_editor\n"
                   "  xterm:\n    path: ../qflistudio-core/vendor/xterm\n")
        self.write("pubspec.lock", "packages:\n  qfli_studio_core:\n    description:\n"
                   "      path: ../qflistudio-core\n      relative: true\n    source: path\n"
                   "  re_editor:\n    description:\n      path: ../qflistudio-core/vendor/re_editor\n"
                   "      relative: true\n    source: path\n"
                   "  xterm:\n    dependency: \"direct overridden\"\n    description:\n"
                   "      path: ../qflistudio-core/vendor/xterm\n      relative: true\n"
                   "    source: path\n    version: \"4.0.0\"\n")
        (self.core / "pubspec.yaml").write_text("name: qfli_studio_core\n", encoding="utf-8")
        for name in ("re_editor", "xterm"):
            vendor = self.core / "vendor" / name
            vendor.mkdir(parents=True)
            (vendor / "pubspec.yaml").write_text("name: " + name + "\n", encoding="utf-8")
        self.engine_files = {"engine.version": "1" * 40, "engine.ohos.version": "2" * 40,
                             "engine.ohos.har.version": "3" * 40}
        for name, value in self.engine_files.items():
            path = self.sdk / "bin/internal" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value + "\n", encoding="utf-8")
        self.flutter = self.sdk / "bin" / ("flutter.bat" if os.name == "nt" else "flutter")
        self.dart = self.sdk / "bin/cache/dart-sdk/bin" / ("dart.exe" if os.name == "nt" else "dart")
        for path in (self.flutter, self.dart):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"never executed fixture")
        lock = self.sdk / "packages/flutter_tools/pubspec.lock"
        lock.parent.mkdir(parents=True)
        lock.write_text("packages: {}\n", encoding="utf-8")
        self.tracked = ["analysis_options.yaml", "pubspec.yaml", "pubspec.lock", "lib/main.dart",
                        "test/one_test.dart", "test/two_test.dart", "integration_test/device_test.dart"]
        for name in sorted(quality.SAFE_DIFF_PATHS - {"pubspec.yaml", "pubspec.lock"}):
            self.write(name, "// generated fixture before restore\n")
            self.tracked.append(name)
        self.index_blobs = {}
        self.index_modes = {}
        self.tracked_status = ""
        environment = {"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted",
                       "RUNNER_TEMP": str(self.scratch), "GITHUB_SHA": SOURCE_SHA,
                       "GITHUB_REPOSITORY": "owner/rust", "GITHUB_RUN_ID": "100", "GITHUB_RUN_ATTEMPT": "2",
                       "GITHUB_REF": "refs/pull/7/merge", "GITHUB_EVENT_NAME": "pull_request",
                       "CORE_SHA": CORE_SHA, "APPROVED_CORE_SHA": CORE_SHA,
                       "CORE_SDK_CONTRACT": quality.app.SDK_CONTRACT, "QFLI_FLUTTER_ROOT": str(self.sdk)}
        self.environment = mock.patch.dict(os.environ, environment)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.git = mock.patch.object(quality.app, "git_value", side_effect=self.git_value)
        self.git.start()
        self.addCleanup(self.git.stop)
        self.app_root = mock.patch.object(quality.app, "ROOT", self.root)
        self.app_root.start()
        self.addCleanup(self.app_root.stop)
        bootstrap = quality.new_manifest(self.args)
        bootstrap.update(platform="linux", arch="x64", status="incomplete",
                         completedStages=sorted(quality.BOOTSTRAP_STAGES),
                         core={"repository": CORE_REPOSITORY, "commit": CORE_SHA,
                               "checkoutDirectory": CORE_DIRECTORY, "packageName": "qfli_studio_core",
                               "checkoutVerified": True, "sdkContract": quality.app.SDK_CONTRACT},
                         flutter={"repository": quality.app.FLUTTER_REPOSITORY,
                                  "commit": quality.app.FLUTTER_COMMIT, "tag": quality.app.FLUTTER_TAG,
                                  "sdkContract": quality.app.SDK_CONTRACT, "toolingOverride": None,
                                  "toolingOverridesApplied": False,
                                  "internalEngineFiles": self.engine_files,
                                  "toolingLocks": [{"file": "flutter-tools-pubspec.lock", "sha256": sha256(lock)}],
                                  "version": {"frameworkRevision": quality.app.FLUTTER_COMMIT,
                                              "frameworkVersion": quality.app.FLUTTER_TAG,
                                              "dartSdkVersion": "fixture-sdk-version"}})
        write_json(self.args.bootstrap / "manifest.json", bootstrap)
        write_json(self.root / ".dart_tool/package_config.json", {"packages": [
            {"name": "qfli_rust", "rootUri": "../"},
            {"name": "qfli_studio_core", "rootUri": "../../qflistudio-core"},
            {"name": "re_editor", "rootUri": "../../qflistudio-core/vendor/re_editor"},
            {"name": "xterm", "rootUri": "../../qflistudio-core/vendor/xterm"}]})

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def git_value(self, directory, *arguments):
        directory = Path(directory).resolve()
        if arguments == ("rev-parse", "HEAD"):
            return {self.root.resolve(): SOURCE_SHA, self.core.resolve(): CORE_SHA,
                    self.sdk.resolve(): quality.app.FLUTTER_COMMIT}[directory]
        if len(arguments) == 2 and arguments[0] == "rev-parse" and arguments[1].startswith("HEAD:"):
            self.assertIn(arguments[1][5:], quality.app.RUNTIME_INPUTS)
            return "e" * 40
        if arguments == ("ls-files", "--stage", "-z"):
            return "\0".join(f"{self.index_modes.get(name, '100644')} "
                             f"{self.index_blobs.get(name, 'd' * 40)} 0\t{name}" for name in self.tracked)
        if arguments[0] == "ls-files":
            names = self.tracked
            if "--" in arguments:
                roots = arguments[arguments.index("--") + 1:]
                names = [name for name in names
                         if any(name == root or name.startswith(root + "/") for root in roots)]
            return "\0".join(names)
        if arguments[0] == "status":
            return self.tracked_status if directory == self.root else ""
        if arguments[0] == "diff":
            self.assertEqual(directory, self.sdk)
            self.assertEqual(arguments, ("diff", "--name-only", "HEAD", "--"))
            return ""
        if arguments[0] == "show":
            return self.engine_files[arguments[1].split("/")[-1]]
        raise AssertionError(f"Unexpected Git fixture call: {directory}, {arguments}")

    def quality_manifest(self):
        """Explicit unit-test asset fixture, never producer or execution evidence."""
        manifest = quality.new_manifest(self.args)
        root = self.root / "assets/miri"
        root.mkdir(parents=True, exist_ok=True)
        for name, data in (("manifest.ohos-arm64.json", b'{"fixture":"arm64"}'),
                           ("manifest.ohos-x64.json", b'{"fixture":"x64"}'),
                           ("manifest.json", b'{"fixture":"arm64"}')):
            (root / name).write_bytes(data)
        selection = {"runId": "200", "runAttempt": "1", "sourceCommit": "c" * 40,
                     "qualitySource": copy.deepcopy(manifest["source"]),
                     "inputCompatibility": {"method": "exact_git_objects", "objects": quality.quality_runtime_inputs(self.args)},
                     "targets": list(quality.QUALITY_ASSET_TARGETS), "status": "verified_assets_only",
                     "scope": "packaged_asset_bytes_only", "nativeRuntimeExecuted": False, "deviceExecuted": False,
                     "artifacts": [{"id": index + 1, "name": "native-runtime-" + key}
                                   for index, key in enumerate(quality.QUALITY_ASSET_TARGETS)],
                     "files": quality.quality_asset_snapshot(self.root)}
        manifest["nativeAssetInputs"] = selection
        write_json(self.args.output / "reports/native-assets.json", selection)
        return manifest

    def prepared(self):
        manifest = self.quality_manifest()
        with mock.patch.object(quality, "run", return_value="fixture version"):
            quality.prepare(self.args, manifest)
        return manifest

    def protocol(self, *, skipped=False, failed=False, omit_second=False, done=True):
        events = []
        names = ["test/one_test.dart"] if omit_second else ["test/one_test.dart", "test/two_test.dart"]
        for index, name in enumerate(names):
            events += [{"type": "suite", "suite": {"id": index, "path": str(self.root / name)}},
                       {"type": "testStart", "test": {"id": index, "name": "native fixture" if index else "ordinary fixture"}},
                       {"type": "testDone", "testID": index,
                        "result": "failure" if failed and not index else "success",
                        "skipped": skipped and bool(index), "hidden": False}]
        if done:
            events.append({"type": "done", "success": not failed})
        return "".join(json.dumps(event) + "\n" for event in events)

    def write_machine_from_command(self, command, log, machine, **kwargs):
        self.assertEqual(list(map(str, command[1:])), ["test", "--no-pub", "--machine", "test"])
        machine.write_text(self.protocol(skipped=True), encoding="utf-8")
        Path(log).parent.mkdir(parents=True, exist_ok=True)
        Path(log).write_text("fixture log", encoding="utf-8")
        return "fixture"


class QualityAssetInputTests(QualityFixtures):
    """Mocked producer seams test orchestration, never fabricate accepted inputs."""

    def selected(self):
        manifest = quality.new_manifest(self.args)
        manifest["nativeAssetInputs"] = {
            "runId": "200", "runAttempt": "1", "sourceCommit": "c" * 40,
            "qualitySource": copy.deepcopy(manifest["source"]),
            "inputCompatibility": {"method": "exact_git_objects",
                                   "objects": quality.quality_runtime_inputs(self.args)},
            "targets": list(quality.QUALITY_ASSET_TARGETS), "status": "selected_not_installed",
            "scope": "packaged_asset_bytes_only", "nativeRuntimeExecuted": False,
            "deviceExecuted": False,
            "artifacts": [{"id": index + 1, "name": "native-runtime-" + key}
                          for index, key in enumerate(quality.QUALITY_ASSET_TARGETS)]}
        self.args.run_id = "200"
        return manifest

    def downloads(self):
        self.args.source = self.scratch / "downloads"
        self.args.source.mkdir()
        (self.root / "assets/miri").mkdir(parents=True)
        (self.root / "assets/miri/.gitkeep").write_bytes(b"")
        for key in quality.QUALITY_ASSET_TARGETS:
            archive = self.args.source / f"native-runtime-{key}.tar.gz"
            archive.write_bytes(b"mock archive bytes, not a producer artifact")
            archive.with_suffix(".gz.sha256").write_text(sha256(archive) + "  " + archive.name, encoding="ascii")

    def extract_fixture(self, archive, destination):
        key = archive.name.removeprefix("native-runtime-").removesuffix(".tar.gz")
        assets = destination / "assets/miri"
        assets.mkdir(parents=True)
        data = {"id": "fixture-" + key, "rustVersion": "mock", "rustCommit": "mock"}
        write_json(assets / f"manifest.{key}.json", data)
        if key == "ohos-arm64":
            write_json(assets / "manifest.json", data)
        (assets / ("d" * 64 + ".bin")).write_bytes(b"mock shared guest asset")
        library = destination / "ohos/entry/libs" / key / "never-load.so"
        library.parent.mkdir(parents=True)
        library.write_bytes(b"must stay private")
        return data

    def verify_fixture(self, extracted, key, selection):
        self.assertEqual(selection["runId"], "200")
        self.assertEqual(selection["sourceCommit"], "c" * 40)
        self.assertEqual(selection["inputCompatibility"]["objects"], quality.quality_runtime_inputs(self.args))
        self.assertFalse((self.root / "assets/miri/manifest.json").exists())
        return read_json(extracted / "assets/miri" / f"manifest.{key}.json")

    def install(self, manifest):
        with mock.patch.object(quality.app, "extract_runtime", side_effect=self.extract_fixture), \
                mock.patch.object(quality.app, "verify_runtime_payload", side_effect=self.verify_fixture) as verify:
            quality.install_quality_assets(self.args, manifest)
        self.assertEqual([call.args[1] for call in verify.call_args_list], list(quality.QUALITY_ASSET_TARGETS))

    def test_selection_uses_both_targets_and_exact_input_object_validator(self):
        manifest = self.selected()
        selection = copy.deepcopy(manifest.pop("nativeAssetInputs"))
        record = {"id": 200}
        with mock.patch.object(quality.app, "api_json", return_value=record) as api, \
                mock.patch.object(quality.app, "validate_runtime_run", return_value=selection) as validator, \
                mock.patch.object(quality.app, "output_value") as outputs:
            quality.resolve_quality_assets(self.args, manifest)
        api.assert_called_once_with("/repos/owner/rust/actions/runs/200")
        validator.assert_called_once_with(record, "owner/rust", quality.quality_runtime_inputs(self.args),
                                          ("ohos-arm64", "ohos-x64"))
        self.assertEqual(outputs.call_args_list, [mock.call("run_id", "200"), mock.call("artifact_ids", "1,2")])
        self.assertEqual(manifest["nativeAssetInputs"]["status"], "selected_not_installed")
        self.assertFalse(manifest["prepared"])

    def test_actual_selection_validator_rejects_expired_missing_and_incompatible_inputs(self):
        record = {"id": 200, "run_attempt": 1, "html_url": "https://example.invalid/run/200",
                  "status": "completed", "conclusion": "success", "head_sha": "c" * 40,
                  "repository": {"full_name": "owner/rust"}, "head_repository": {"full_name": "owner/rust"},
                  "event": "push", "head_branch": "main", "path": quality.app.NATIVE_WORKFLOW}
        expected = quality.quality_runtime_inputs(self.args)
        artifacts = [{"id": index + 1, "name": "native-runtime-" + key, "size_in_bytes": 100,
                      "expired": False, "expires_at": "2099-01-01T00:00:00Z"}
                     for index, key in enumerate(quality.QUALITY_ASSET_TARGETS)]
        for reason in ("expired", "missing", "incompatible"):
            with self.subTest(reason=reason):
                manifest = quality.new_manifest(self.args)
                self.args.run_id = "200"
                rows = copy.deepcopy(artifacts)
                inputs = dict(expected)
                if reason == "expired":
                    rows[1]["expires_at"] = "2000-01-01T00:00:00Z"
                elif reason == "missing":
                    rows.pop()
                else:
                    inputs[quality.app.RUNTIME_INPUTS[0]] = "f" * 40
                with mock.patch.object(quality.app, "api_json", return_value=record), \
                        mock.patch.object(quality.app, "runtime_input_identity", return_value=inputs), \
                        mock.patch.object(quality.app, "runtime_artifacts", return_value=rows), \
                        mock.patch.object(quality.app, "output_value") as outputs:
                    with self.assertRaises(RuntimeError):
                        quality.resolve_quality_assets(self.args, manifest)
                self.assertNotIn("nativeAssetInputs", manifest)
                outputs.assert_not_called()

    def test_automatic_selection_skips_rejected_runs_without_weakening_validation(self):
        manifest = self.selected()
        selection = manifest.pop("nativeAssetInputs")
        self.args.run_id = None
        with mock.patch.dict(os.environ, {"RUNTIME_RUN_ID": ""}), \
                mock.patch.object(quality.app, "api_json", return_value={"workflow_runs": [{"id": 199}, {"id": 200}]}), \
                mock.patch.object(quality.app, "validate_runtime_run",
                                  side_effect=[RuntimeError("expired"), selection]) as validator, \
                mock.patch.object(quality.app, "output_value"):
            quality.resolve_quality_assets(self.args, manifest)
        self.assertEqual(validator.call_count, 2)
        self.assertEqual(manifest["nativeAssetInputs"]["runId"], "200")

    def test_selection_rejects_another_quality_run_object_set_or_target(self):
        original = self.selected()["nativeAssetInputs"]
        bootstrap = quality.verify_bootstrap(self.args)
        for mutation in ("source", "objects", "targets", "artifacts", "execution", "run"):
            with self.subTest(mutation=mutation):
                value = copy.deepcopy(original)
                if mutation == "source":
                    value["qualitySource"]["runAttempt"] = "9"
                elif mutation == "objects":
                    value["inputCompatibility"]["objects"]["scripts"] = "f" * 40
                elif mutation == "targets":
                    value["targets"].pop()
                elif mutation == "artifacts":
                    value["artifacts"][1]["id"] = value["artifacts"][0]["id"]
                elif mutation == "execution":
                    value["nativeRuntimeExecuted"] = True
                else:
                    value["sourceCommit"] = "main"
                with self.assertRaises(RuntimeError):
                    quality.validate_quality_asset_selection(self.args, value, bootstrap)

    def test_both_full_payloads_are_verified_before_only_assets_reach_checkout(self):
        manifest = self.selected()
        self.downloads()
        self.install(manifest)
        quality.verify_quality_assets(self.args, manifest, quality.verify_bootstrap(self.args))
        selection = manifest["nativeAssetInputs"]
        self.assertEqual(selection["status"], "verified_assets_only")
        self.assertEqual([row["target"] for row in selection["packages"]], list(quality.QUALITY_ASSET_TARGETS))
        self.assertEqual(selection["totalBytes"], sum(row["size"] for row in selection["files"]))
        self.assertEqual((self.root / "assets/miri/manifest.json").read_bytes(),
                         (self.root / "assets/miri/manifest.ohos-arm64.json").read_bytes())
        self.assertFalse((self.root / "ohos").exists())
        self.assertEqual(list(self.root.rglob("*.so")), [])
        self.assertEqual(list(self.args.output.rglob("*.bin")), [])
        self.assertEqual(list(self.scratch.glob("qfli-quality-assets-*")), [])
        self.assertFalse(selection["nativeRuntimeExecuted"])
        self.assertFalse(selection["deviceExecuted"])

    def test_second_payload_verification_failure_exposes_neither_architecture(self):
        manifest = self.selected()
        self.downloads()

        def reject_second(extracted, key, selection):
            data = self.verify_fixture(extracted, key, selection)
            if key == "ohos-x64":
                raise RuntimeError("producer byte chain differs")
            return data

        with mock.patch.object(quality.app, "extract_runtime", side_effect=self.extract_fixture), \
                mock.patch.object(quality.app, "verify_runtime_payload", side_effect=reject_second):
            with self.assertRaisesRegex(RuntimeError, "producer byte chain"):
                quality.install_quality_assets(self.args, manifest)
        self.assertEqual([path.name for path in (self.root / "assets/miri").iterdir()], [".gitkeep"])
        self.assertEqual(manifest["nativeAssetInputs"]["status"], "installation_incomplete")
        self.assertFalse((self.args.output / "reports/native-assets.json").exists())

    def test_missing_archive_and_checksum_mismatch_stop_before_extraction(self):
        manifest = self.selected()
        self.downloads()
        archive = self.args.source / "native-runtime-ohos-arm64.tar.gz"
        archive.unlink()
        with mock.patch.object(quality.app, "extract_runtime") as extract:
            with self.assertRaisesRegex(RuntimeError, "Expected one"):
                quality.install_quality_assets(self.args, manifest)
            manifest["nativeAssetInputs"]["status"] = "selected_not_installed"
            archive.write_bytes(b"changed bytes")
            with self.assertRaisesRegex(RuntimeError, "checksum differs"):
                quality.install_quality_assets(self.args, manifest)
        extract.assert_not_called()

    def test_downloads_outside_runner_temp_or_linked_are_rejected(self):
        manifest = self.selected()
        self.downloads()
        original = self.args.source
        self.args.source = self.root
        with self.assertRaisesRegex(RuntimeError, "below RUNNER_TEMP"):
            quality.install_quality_assets(self.args, manifest)
        self.args.source = original
        real_linked = quality.linked
        with mock.patch.object(quality, "linked", side_effect=lambda path: path == original or real_linked(path)):
            with self.assertRaisesRegex(RuntimeError, "below RUNNER_TEMP"):
                quality.install_quality_assets(self.args, manifest)
        self.assertEqual(manifest["nativeAssetInputs"]["status"], "selected_not_installed")

    def test_asset_publication_failure_cannot_leave_verified_status(self):
        manifest = self.selected()
        self.downloads()
        real_write = quality.write_json

        def fail_report(path, value):
            if Path(path).name == "native-assets.json":
                raise OSError("report disk denied")
            real_write(path, value)

        with mock.patch.object(quality, "write_json", side_effect=fail_report), \
                mock.patch.object(quality.app, "extract_runtime", side_effect=self.extract_fixture), \
                mock.patch.object(quality.app, "verify_runtime_payload", side_effect=self.verify_fixture):
            with self.assertRaisesRegex(OSError, "disk denied"):
                quality.install_quality_assets(self.args, manifest)
        self.assertEqual(manifest["nativeAssetInputs"]["status"], "installation_incomplete")
        with mock.patch.object(quality, "run") as command:
            with self.assertRaisesRegex(RuntimeError, "installation is incomplete"):
                quality.prepare(self.args, manifest)
        command.assert_not_called()

    def test_missing_assets_block_prepare_before_pub_get(self):
        manifest = quality.new_manifest(self.args)
        with mock.patch.object(quality, "run") as command:
            with self.assertRaisesRegex(RuntimeError, "another source or run"):
                quality.prepare(self.args, manifest)
        command.assert_not_called()
        self.assertFalse(manifest["prepared"])

    def test_asset_bytes_and_report_drift_block_checks_and_finalize(self):
        manifest = self.prepared()
        asset = self.root / "assets/miri/manifest.ohos-x64.json"
        original = asset.read_bytes()
        asset.write_bytes(b"changed")
        with mock.patch.object(quality, "run") as command:
            with self.assertRaisesRegex(RuntimeError, "assets changed"):
                quality.execute_check(self.args, manifest, "analyze")
        command.assert_not_called()
        with self.assertRaisesRegex(RuntimeError, "assets changed"):
            quality.finalize(self.args, manifest, "success")
        self.assertEqual(manifest["status"], "failed")
        asset.write_bytes(original)
        write_json(self.args.output / "reports/native-assets.json", {})
        with self.assertRaisesRegex(RuntimeError, "report changed"):
            quality.verify_prepared(self.args, manifest)

    def test_asset_changes_during_restore_leave_preparation_incomplete(self):
        manifest = self.quality_manifest()

        def mutate(*args, **kwargs):
            (self.root / "assets/miri/manifest.json").write_bytes(b"changed during pub get")
            return ""

        with mock.patch.object(quality, "run", side_effect=mutate):
            with self.assertRaisesRegex(RuntimeError, "assets changed"):
                quality.prepare(self.args, manifest)
        self.assertFalse(manifest["prepared"])

    def test_asset_inventory_bounds_and_unknown_files_reject(self):
        self.quality_manifest()
        with mock.patch.object(quality.app, "MAX_RUNTIME_BYTES", 1):
            with self.assertRaisesRegex(RuntimeError, "byte bound"):
                quality.quality_asset_snapshot(self.root)
        (self.root / "assets/miri/unreviewed.so").write_bytes(b"unexpected")
        with self.assertRaisesRegex(RuntimeError, "Unexpected quality"):
            quality.quality_asset_snapshot(self.root)


class QualityIdentityTests(QualityFixtures):
    def test_helper_import_and_metadata_do_not_require_core(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(quality.CHECKS, ("format", "analyze", "test"))
            self.assertEqual(quality.new_manifest(self.args)["status"], "incomplete")
            with self.assertRaisesRegex(RuntimeError, "GitHub-hosted"):
                quality.require_hosted_runner()

    def test_fixture_git_identity_uses_resolved_checkout_paths(self):
        self.assertEqual(self.args.root, self.root.resolve())
        for directory, expected in ((self.root, SOURCE_SHA), (self.core, CORE_SHA),
                                    (self.sdk, quality.app.FLUTTER_COMMIT)):
            alias = directory / ".." / directory.name
            self.assertEqual(self.git_value(alias, "rev-parse", "HEAD"), expected)

    def test_bootstrap_requires_all_owner_and_sdk_stages(self):
        bootstrap = read_json(self.args.bootstrap / "manifest.json")
        bootstrap["completedStages"].remove("preflight")
        write_json(self.args.bootstrap / "manifest.json", bootstrap)
        with self.assertRaisesRegex(RuntimeError, "stages are incomplete"):
            quality.verify_bootstrap(self.args)

    def test_missing_owner_approval_runs_no_restore_or_quality_tool(self):
        manifest = quality.new_manifest(self.args)
        with mock.patch.dict(os.environ, {"APPROVED_CORE_SHA": ""}), mock.patch.object(quality, "run") as command:
            with self.assertRaisesRegex(RuntimeError, "owner approval"):
                quality.prepare(self.args, manifest)
        self.assertFalse(manifest["prepared"])
        command.assert_not_called()

    def test_wrong_sdk_contract_is_not_treated_as_a_skip(self):
        with mock.patch.dict(os.environ, {"CORE_SDK_CONTRACT": "unapproved"}):
            with self.assertRaisesRegex(RuntimeError, "SDK contract"):
                quality.verify_bootstrap(self.args)

    def test_mismatched_run_attempt_or_commit_is_rejected(self):
        for key, value in (("GITHUB_RUN_ATTEMPT", "3"), ("GITHUB_SHA", "c" * 40)):
            with self.subTest(key=key), mock.patch.dict(os.environ, {key: value}):
                with self.assertRaisesRegex(RuntimeError, "differs"):
                    quality.verify_bootstrap(self.args)

    def test_untracked_external_sdk_tooling_override_is_rejected(self):
        override = self.sdk / "packages/flutter_tools/pubspec_overrides.yaml"
        override.write_text("dependency_overrides: {}\n", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "Unapproved or changed SDK"):
            quality.verify_bootstrap(self.args)

    def test_unapproved_external_tooling_override_is_rejected(self):
        bootstrap = read_json(self.args.bootstrap / "manifest.json")
        bootstrap["flutter"]["toolingOverride"] = "other-code"
        write_json(self.args.bootstrap / "manifest.json", bootstrap)
        with self.assertRaisesRegex(RuntimeError, "override state"):
            quality.verify_bootstrap(self.args)

    def test_changed_engine_identity_is_rejected(self):
        (self.sdk / "bin/internal/engine.version").write_text("f" * 40, encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "engine file changed"):
            quality.verify_bootstrap(self.args)

    def test_prepare_binds_inputs_paths_sdk_bytes_and_host_tools(self):
        manifest = self.prepared()
        self.assertTrue(manifest["prepared"])
        self.assertEqual(manifest["rootTestFiles"], ["test/one_test.dart", "test/two_test.dart"])
        self.assertEqual(manifest["inputs"]["sha256"], quality.input_identity(quality.source_inputs(self.root)))
        self.assertEqual(set(manifest["sdkExecutableHashes"]), {"flutter", "dart"})
        self.assertEqual(set(manifest["hostRustTools"]), {"rustc", "cargo"})
        self.assertEqual(manifest["core"]["commit"], CORE_SHA)
        self.assertEqual(manifest["resolvedDependencies"]["packages"]["xterm"],
                         str(self.core / "vendor/xterm"))
        self.assertFalse((self.args.output / "reports/pub-get-input-delta.txt").exists())
        quality.verify_prepared(self.args, manifest)

    def test_restore_cannot_silently_rewrite_lockfile(self):
        manifest = self.quality_manifest()

        def mutate(command, log, **kwargs):
            self.write("pubspec.lock", "packages: {}\n")
            return ""

        with mock.patch.object(quality, "run", side_effect=mutate):
            with self.assertRaisesRegex(RuntimeError, "restore changed tracked"):
                quality.prepare(self.args, manifest)
        self.assertFalse(manifest["prepared"])

    def test_prepared_source_and_sdk_cannot_change(self):
        manifest = self.prepared()
        self.write("lib/main.dart", "void main() { print('changed'); }\n")
        with self.assertRaisesRegex(RuntimeError, "Tracked inputs changed"):
            quality.verify_prepared(self.args, manifest)
        self.write("lib/main.dart", "void main() {}\n")
        self.dart.write_bytes(b"replaced executable")
        with self.assertRaisesRegex(RuntimeError, "executable bytes changed"):
            quality.verify_prepared(self.args, manifest)

    def test_resolved_core_alias_must_match_new_sibling_directory(self):
        config = self.root / ".dart_tool/package_config.json"
        value = read_json(config)
        value["packages"][1]["rootUri"] = "../../qfli_studio_core"
        write_json(config, value)
        with self.assertRaisesRegex(RuntimeError, "Resolved package path differs"):
            quality.verify_resolved_paths(self.args)

    def test_resolved_xterm_must_be_present_and_use_the_core_vendor_root(self):
        path = self.root / ".dart_tool/package_config.json"
        baseline = read_json(path)
        for uri in (None, "../../hosted/pub.dev/xterm-4.0.0", "../../qflistudio-core/xterm",
                    "https://pub.dev/packages/xterm", "//remote/share/xterm",
                    (self.core / "vendor/xterm").as_uri().replace("file:///", "file://localhost/", 1)):
            with self.subTest(uri=uri):
                value = copy.deepcopy(baseline)
                if uri is None:
                    value["packages"] = [row for row in value["packages"] if row["name"] != "xterm"]
                else:
                    next(row for row in value["packages"] if row["name"] == "xterm")["rootUri"] = uri
                write_json(path, value)
                with self.assertRaisesRegex(RuntimeError, "xterm"):
                    quality.verify_resolved_paths(self.args)
        write_json(path, baseline)
        self.assertEqual(quality.verify_resolved_paths(self.args)["packages"]["xterm"],
                         str(self.core / "vendor/xterm"))

    def test_prepare_rejects_hosted_xterm_before_quality_checks(self):
        manifest = self.quality_manifest()
        config = self.root / ".dart_tool/package_config.json"
        value = read_json(config)
        next(row for row in value["packages"] if row["name"] == "xterm")["rootUri"] = "../../hosted/xterm-4.0.0"
        write_json(config, value)
        with mock.patch.object(quality, "run", return_value="") as command:
            with self.assertRaisesRegex(RuntimeError, "Resolved package path differs: xterm"):
                quality.prepare(self.args, manifest)
        self.assertEqual(command.call_count, 1)
        self.assertEqual(command.call_args.args[0][1:], ["pub", "get"])
        self.assertFalse(manifest["prepared"])
        self.assertTrue(all(row["status"] == "not_run" for row in manifest["checks"].values()))

    def test_command_environment_removes_read_tokens(self):
        with mock.patch.dict(os.environ, {"GH_TOKEN": "not-a-real-token", "GITHUB_TOKEN": "not-a-real-token",
                                          "ACTIONS_RUNTIME_TOKEN": "not-a-real-token"}):
            environment = quality.command_environment()
        for name in ("GH_TOKEN", "GITHUB_TOKEN", "ACTIONS_RUNTIME_TOKEN"):
            self.assertNotIn(name, environment)


class QualityRestoreDiagnosticTests(QualityFixtures):
    def reject_restore(self, mutate, message="restore changed tracked"):
        manifest = self.quality_manifest()
        with mock.patch.object(quality, "run", side_effect=mutate) as command, \
                mock.patch.object(quality, "print_untrusted") as printed, \
                mock.patch.object(quality, "annotate") as annotated:
            with self.assertRaisesRegex(RuntimeError, message):
                quality.prepare(self.args, manifest)
        self.assertFalse(manifest["prepared"])
        self.assertTrue(all(row["status"] == "not_run" for row in manifest["checks"].values()))
        self.assertEqual(command.call_count, 1)
        self.assertEqual(command.call_args.args[0][1:], ["pub", "get"])
        report = self.args.output / "reports/pub-get-input-delta.txt"
        diagnostic = report.read_bytes().decode("utf-8")
        self.assertLessEqual(report.stat().st_size, quality.MAX_TRACKED_DIAGNOSTIC_BYTES)
        printed.assert_called_once_with(diagnostic)
        self.assertEqual(annotated.call_args.args, ("error", diagnostic))
        return diagnostic

    def test_lock_delta_has_hashes_safe_hunks_and_no_arbitrary_source_values(self):
        name = "lib/main.dart"
        self.write(name, "before-arbitrary-sensitive-value\n")
        before_lock = sha256(self.root / "pubspec.lock")
        before_source = sha256(self.root / name)

        def mutate(command, log, **kwargs):
            self.write("pubspec.lock", "packages:\n  new_fixture:\n    version: \"2.0.0\"\n"
                       "    token: not-a-real-token\n    password: not-a-real-password\n"
                       "    url: https://user:fake-password@pub.dev/path?secret=fake-query\n")
            self.write("pubspec.yaml", (self.root / "pubspec.yaml").read_text(encoding="utf-8")
                       + "# ordinary dependency fixture\n")
            self.write(name, "after-arbitrary-sensitive-value\n")
            return ""

        diagnostic = self.reject_restore(mutate)
        self.assertIn("Changed tracked paths: 3", diagnostic)
        for path in ("pubspec.lock", "pubspec.yaml", name):
            self.assertIn(path, diagnostic)
        for value in (before_lock, before_source, sha256(self.root / "pubspec.lock"), sha256(self.root / name)):
            self.assertIn(value, diagnostic)
        self.assertIn("--- a/pubspec.lock", diagnostic)
        self.assertIn("+++ b/pubspec.lock", diagnostic)
        self.assertIn('+    version: "2.0.0"', diagnostic)
        self.assertIn("+# ordinary dependency fixture", diagnostic)
        for value in ("before-arbitrary-sensitive-value", "after-arbitrary-sensitive-value",
                      "not-a-real-token", "not-a-real-password", "fake-password", "fake-query"):
            self.assertNotIn(value, diagnostic)
        self.assertNotIn("--- a/lib/main.dart", diagnostic)

    def test_generated_only_delta_is_reported_and_rejected_with_unchanged_quality_inputs(self):
        before = quality.source_inputs(self.root)
        generated = sorted(quality.SAFE_DIFF_PATHS - {"pubspec.yaml", "pubspec.lock"})

        def mutate(command, log, **kwargs):
            for name in generated:
                self.write(name, "// generated fixture after restore\n")
            return ""

        diagnostic = self.reject_restore(mutate, "restore changed tracked repository inputs")
        self.assertEqual(quality.source_inputs(self.root), before)
        self.assertIn("Changed tracked paths: 7", diagnostic)
        for name in generated:
            self.assertIn("Safe literal diff for " + name, diagnostic)
            self.assertIn("+++ b/" + name, diagnostic)
        self.assertIn("+// generated fixture after restore", diagnostic)

    def test_diagnostic_fits_lock_additions_and_all_registrants_with_explicit_truncation(self):
        generated = sorted(quality.SAFE_DIFF_PATHS - {"pubspec.yaml", "pubspec.lock"})

        def mutate(command, log, **kwargs):
            lock = (self.root / "pubspec.lock").read_text(encoding="utf-8")
            additions = "".join(f"  fixture_{index}:\n    source: hosted\n    version: \"1.0.{index}\"\n"
                                for index in range(16))
            self.write("pubspec.lock", lock + additions)
            for name in generated:
                self.write(name, "// dependency registration after restore\n" * 3000)
            return ""

        diagnostic = self.reject_restore(mutate)
        self.assertIn("fixture_0:", diagnostic)
        self.assertIn("fixture_15:", diagnostic)
        for name in generated:
            self.assertIn("Safe literal diff for " + name, diagnostic)
        self.assertIn("[tracked input diagnostic truncated]", diagnostic)
        self.assertNotIn("ordinary secret", quality.bounded_diagnostic("password=ordinary secret\n" + "x" * 2000, 100))
        self.assertLessEqual(len(quality.bounded_diagnostic("字" * 200, 100).encode("utf-8")), 100)

    def test_redaction_precedes_hunks_even_when_key_header_is_far_from_changed_line(self):
        before = ("private_key: |\n" + "  fake-old-key-body\n" * 20
                  + "ordinary: before\n-----BEGIN PRIVATE KEY-----\n"
                  + "fake-old-pem-body\n" * 20 + "-----END PRIVATE KEY-----\n")
        after = before.replace("fake-old-key-body", "fake-new-key-body").replace("before", "after")
        after = after.replace("fake-old-pem-body", "fake-new-pem-body")
        self.write("pubspec.lock", before)

        def mutate(command, log, **kwargs):
            self.write("pubspec.lock", after)
            return ""

        # This case exercises restore diagnostics, not lock-schema validation.
        with mock.patch.object(quality.app, "verify_core"):
            diagnostic = self.reject_restore(mutate)
        self.assertIn("+ordinary: after", diagnostic)
        for secret in ("fake-old-key-body", "fake-new-key-body", "fake-old-pem-body", "fake-new-pem-body"):
            self.assertNotIn(secret, diagnostic)

    def test_arbitrary_tracked_removal_has_only_path_and_hash_data(self):
        name = "config/sensitive.env"
        self.write(name, "arbitrary-sensitive-value-must-never-print\n")
        self.tracked.append(name)
        before = sha256(self.root / name)

        def mutate(command, log, **kwargs):
            (self.root / name).unlink()
            return ""

        diagnostic = self.reject_restore(mutate, "restore changed tracked repository inputs")
        self.assertIn(name, diagnostic)
        self.assertIn(before, diagnostic)
        self.assertIn("after:  missing", diagnostic)
        self.assertNotIn("arbitrary-sensitive-value-must-never-print", diagnostic)
        self.assertNotIn("Safe literal diff for " + name, diagnostic)

    def test_git_status_only_change_keeps_original_whole_tree_rejection(self):
        def mutate(command, log, **kwargs):
            self.tracked_status = " M config/sensitive.env"
            return ""

        diagnostic = self.reject_restore(mutate, "Tracked application source changed")
        self.assertIn("Git tracked status (paths only):", diagnostic)
        self.assertIn("config/sensitive.env", diagnostic)

    def test_diagnostic_write_and_console_failures_cannot_replace_strict_rejection(self):
        original_write = Path.write_text

        def fail_report(path, *arguments, **kwargs):
            if path.name == "pub-get-input-delta.txt":
                raise OSError("arbitrary-diagnostic-error-value")
            return original_write(path, *arguments, **kwargs)

        def mutate(command, log, **kwargs):
            self.write("pubspec.lock", "packages: {}\n")
            return ""

        manifest = self.quality_manifest()
        with mock.patch.object(Path, "write_text", fail_report), \
                mock.patch.object(quality, "run", side_effect=mutate), \
                mock.patch.object(quality, "print_untrusted", side_effect=OSError("console failed")), \
                mock.patch.object(quality, "annotate", side_effect=OSError("annotation failed")):
            with self.assertRaisesRegex(RuntimeError, "restore changed tracked quality inputs"):
                quality.prepare(self.args, manifest)
        self.assertFalse(manifest["prepared"])

    def test_unsafe_or_oversized_allowlist_content_is_not_diffed(self):
        name = "linux/flutter/generated_plugins.cmake"
        before = quality.tracked_snapshot(self.root)
        self.write(name, "oversized-sensitive-value" * quality.MAX_SAFE_DIFF_FILE_BYTES)
        snapshot = quality.safe_diff_snapshot(self.root, before)
        self.assertEqual(snapshot[name]["state"], "oversized")
        self.assertNotIn("text", snapshot[name])
        with mock.patch.object(quality, "linked", side_effect=lambda path: Path(path).name == "pubspec.lock"):
            snapshot = quality.safe_diff_snapshot(self.root, before)
        self.assertEqual(snapshot["pubspec.lock"], {"state": "linked"})
        self.assertEqual(quality.safe_literal_diff("lib/main.dart", {}, {}), "")


class QualityCommandTests(QualityFixtures):
    def test_commands_cover_format_analysis_and_full_root_tests(self):
        commands = quality.commands(self.args)
        self.assertEqual(commands["format"][1:4], ["format", "--output=none", "--set-exit-if-changed"])
        self.assertEqual(commands["format"][4:], ["lib", "test", "integration_test"])
        self.assertEqual(commands["analyze"][1:], ["analyze", "--no-pub"])
        self.assertEqual(commands["test"][1:], ["test", "--no-pub", "--machine", "test"])
        for command in commands.values():
            self.assertNotIn("--update-goldens", command)
            self.assertNotIn("--exclude-tags", command)
            self.assertNotIn("--name", command)
            self.assertNotIn("build", command)

    def test_format_failure_has_failed_status_and_never_rewrites_source(self):
        manifest = self.prepared()
        before = (self.root / "lib/main.dart").read_bytes()
        with mock.patch.object(quality, "run", side_effect=RuntimeError("format drift")) as command:
            with self.assertRaisesRegex(RuntimeError, "format drift"):
                quality.execute_check(self.args, manifest, "format")
        self.assertEqual(manifest["checks"]["format"]["status"], "failed")
        self.assertEqual(manifest["checks"]["analyze"]["status"], "not_run")
        self.assertEqual(before, (self.root / "lib/main.dart").read_bytes())
        self.assertIn("--output=none", command.call_args.args[0])

    def test_successful_tool_exit_does_not_hide_source_mutation(self):
        manifest = self.prepared()

        def mutate(command, log, **kwargs):
            self.write("test/one_test.dart", "changed source\n")
            return ""

        with mock.patch.object(quality, "run", side_effect=mutate):
            with self.assertRaisesRegex(RuntimeError, "Tracked inputs changed"):
                quality.execute_check(self.args, manifest, "analyze")
        self.assertEqual(manifest["checks"]["analyze"]["status"], "failed")

    def test_full_test_protocol_records_skips_without_claiming_native_execution(self):
        manifest = self.prepared()
        with mock.patch.object(quality, "run_machine", side_effect=self.write_machine_from_command) as command:
            quality.execute_check(self.args, manifest, "test")
        result = manifest["checks"]["test"]
        self.assertEqual(result["status"], "passed_with_skips")
        self.assertEqual(result["summary"]["skipped"], 1)
        self.assertFalse(result["summary"]["nativeRuntimeExecuted"])
        self.assertFalse(result["summary"]["rawReportPublished"])
        self.assertEqual(result["summary"]["missingSuiteFiles"], [])
        self.assertEqual(command.call_args.args[0][-1], "test")
        self.assertIn("--machine", command.call_args.args[0])
        self.assertFalse(any(str(value).startswith("--file-reporter") for value in command.call_args.args[0]))
        self.assertTrue((self.args.output / "reports/root-tests.json").is_file())
        self.assertEqual(list(self.scratch.glob("qfli-quality-tests-*")), [])

    def test_test_process_failure_is_not_hidden_by_successful_protocol(self):
        manifest = self.prepared()

        def fail(command, log, machine, **kwargs):
            self.write_machine_from_command(command, log, machine, **kwargs)
            with machine.open("a", encoding="utf-8") as stream:
                stream.write('[{"event":"test.startedProcess","params":{"vmServiceUri":null}}]\n')
            raise RuntimeError("test process failed")

        with mock.patch.object(quality, "run_machine", side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, "test process failed"):
                quality.execute_check(self.args, manifest, "test")
        self.assertEqual(manifest["checks"]["test"]["status"], "failed")
        self.assertEqual(manifest["checks"]["test"]["summary"]["flutterStartedProcesses"], 1)
        self.assertTrue((self.args.output / "reports/root-tests.json").is_file())

    def test_missing_test_protocol_fails(self):
        manifest = self.prepared()
        with mock.patch.object(quality, "run_machine", return_value=""):
            with self.assertRaisesRegex(RuntimeError, "machine report is absent"):
                quality.execute_check(self.args, manifest, "test")
        self.assertEqual(manifest["checks"]["test"]["status"], "failed")

    def test_machine_capture_keeps_protocol_private_and_redacts_published_log(self):
        machine = self.scratch / "private-events.jsonl"
        log = self.args.output / "reports/test.log"
        raw = self.protocol() + json.dumps({"type": "print", "message": "token=not-a-real-token"}) + "\n"

        def process(command, **kwargs):
            self.assertEqual(command[1:], ["test", "--no-pub", "--machine", "test"])
            kwargs["stdout"].write(raw)
            kwargs["stderr"].write("password=not-a-real-password\n")
            return quality.subprocess.CompletedProcess(command, 0)

        with mock.patch.object(quality.subprocess, "run", side_effect=process):
            quality.run_machine(quality.commands(self.args)["test"], log, machine,
                                cwd=self.root, env=quality.command_environment())
        self.assertEqual(machine.read_text(encoding="utf-8"), raw)
        published = log.read_text(encoding="utf-8")
        self.assertNotIn("not-a-real-token", published)
        self.assertNotIn("not-a-real-password", published)
        self.assertLessEqual(log.stat().st_size, quality.LOG_LIMIT + 2000)

    def test_machine_capture_failure_preserves_nonzero_exit(self):
        machine = self.scratch / "private-events.jsonl"
        log = self.args.output / "reports/test.log"
        with mock.patch.object(quality.subprocess, "run", return_value=quality.subprocess.CompletedProcess([], 1)):
            with self.assertRaisesRegex(RuntimeError, "command failed"):
                quality.run_machine(quality.commands(self.args)["test"], log, machine,
                                    cwd=self.root, env=quality.command_environment())

    def test_check_before_prepare_cannot_pass(self):
        manifest = quality.new_manifest(self.args)
        with mock.patch.object(quality, "run") as command:
            with self.assertRaisesRegex(RuntimeError, "prepare did not complete"):
                quality.execute_check(self.args, manifest, "format")
        command.assert_not_called()


class QualityFormatDiagnosticTests(QualityFixtures):
    """Best-effort formatter context that can never weaken the strict failure."""

    APPROVED = "test/rust_code_analyzer_test.dart"

    def setUp(self):
        super().setUp()
        self.write(self.APPROVED, "void main() {}\n")
        self.tracked.append(self.APPROVED)
        self.manifest = self.prepared()
        self.command = quality.commands(self.args)["format"]

    def preview(self, outputs=None):
        calls = []

        def runner(command, **kwargs):
            calls.append((list(command), dict(kwargs)))
            return "void main() {}\n" if outputs is None else outputs[len(calls) - 1]

        return mock.patch.object(quality, "run_format_preview", side_effect=runner), calls

    def test_preview_uses_pinned_output_show_flags_and_no_write_flags(self):
        patcher, calls = self.preview()
        with patcher:
            diagnostic = quality.format_failure_diagnostic(self.args, self.command, RuntimeError("drift"))
        command = calls[0][0]
        self.assertEqual(command[1:5], ["format", "--output=show", "--show=none", "--summary=none"])
        self.assertEqual(command[5:], [self.APPROVED])
        self.assertEqual(command[0], str(self.command[0]))
        # A source-writing flag would defeat the --output=none contract.
        for forbidden in ("--set-exit-if-changed", "--output=write", "--show=all", "--summary=line"):
            self.assertNotIn(forbidden, command)
        self.assertEqual(calls[0][1]["cwd"], self.root.resolve())
        self.assertIn("Original failure: drift", diagnostic)
        self.assertIn("no textual delta", diagnostic)

    def test_redaction_precedes_the_published_diff(self):
        source = "// token=not-a-real-token\nvoid main() {}\n"
        formatted = "// token=not-a-real-token\nvoid main() { }\n"
        self.write(self.APPROVED, source)
        patcher, _ = self.preview(outputs=[formatted])
        with patcher:
            diagnostic = quality.format_failure_diagnostic(self.args, self.command, RuntimeError("drift"))
        self.assertIn("Safe formatter diff for " + self.APPROVED, diagnostic)
        self.assertNotIn("not-a-real-token", diagnostic)
        self.assertIn("void main() { }", diagnostic)

    def test_diff_keeps_full_lines_and_empty_inputs(self):
        before = {"text": "first\nlast line without newline"}
        diff = quality.format_diff("test/one_test.dart", before, "first\nlast line without newline changed")
        self.assertIn("last line without newline\n", diff)
        self.assertIn("last line without newline changed\n", diff)
        self.assertEqual(quality.format_diff("test/one_test.dart", {"text": ""}, ""), "")

    def test_oversized_preview_output_is_refused_by_the_runner(self):
        def fake_popen(command, **kwargs):
            class Process:
                returncode = 0

                def poll(self):
                    return 0

                def wait(self, timeout=None):
                    return 0

                def kill(self):
                    return None

            process = Process()
            kwargs["stdout"].write(b"x" * (quality.MAX_FORMAT_DIAGNOSTIC_OUTPUT_BYTES + 1))
            kwargs["stdout"].flush()
            return process

        with mock.patch.object(quality.subprocess, "Popen", side_effect=fake_popen):
            with self.assertRaisesRegex(RuntimeError, "exceeds or fails to finish its bound"):
                quality.run_format_preview(self.command, cwd=self.root, env={})
        self.assertEqual(list(self.scratch.glob("qfli-format-preview-*")), [])

    def test_private_file_capture_does_not_wait_for_inherited_open_handles(self):
        inherited = []
        process = mock.Mock()
        process.poll.return_value = 0
        process.wait.side_effect = AssertionError("must not wait for inherited stdout")

        def fake_popen(command, **kwargs):
            self.assertEqual(kwargs["stdin"], quality.subprocess.DEVNULL)
            self.assertEqual(kwargs["stderr"], quality.subprocess.DEVNULL)
            # Keep a separate descriptor open after the direct child has exited.
            child_output = os.fdopen(os.dup(kwargs["stdout"].fileno()), "wb", buffering=0)
            inherited.append(child_output)
            child_output.write(b"void main() {}\n")
            return process

        try:
            with mock.patch.object(quality.subprocess, "Popen", side_effect=fake_popen):
                result = quality.run_format_preview(self.command, cwd=self.root, env={})
            self.assertEqual(result, "void main() {}\n")
            self.assertEqual(len(inherited), 1)
            self.assertFalse(inherited[0].closed)
            process.wait.assert_not_called()
            process.stdout.read.assert_not_called()
            process.stdout.close.assert_not_called()
        finally:
            for handle in inherited:
                handle.close()

    def test_partial_preview_read_failure_is_rejected(self):
        class Process:
            returncode = 0

            def poll(self):
                return 0

            def wait(self, timeout=None):
                return 0

            def kill(self):
                return None

        def fake_popen(command, **kwargs):
            kwargs["stdout"].write(b"partial")
            kwargs["stdout"].flush()
            return Process()

        original_open = Path.open

        for failure_type in (OSError, ValueError):
            with self.subTest(failure_type=failure_type):
                read_sizes = []

                def broken_open(path, mode="r", *args, **kwargs):
                    handle = original_open(path, mode, *args, **kwargs)
                    if mode != "rb" or path.name != "stdout.log":
                        return handle

                    class BrokenRead:
                        def __enter__(self):
                            return self

                        def __exit__(self, *arguments):
                            return handle.__exit__(*arguments)

                        def read(self, size=-1):
                            read_sizes.append(size)
                            if len(read_sizes) == 1:
                                return handle.read(min(size, 2))
                            raise failure_type("simulated read failure after partial output")

                    return BrokenRead()

                with mock.patch.object(quality.subprocess, "Popen", side_effect=fake_popen), \
                        mock.patch.object(Path, "open", new=broken_open):
                    with self.assertRaisesRegex(RuntimeError, "could not be read"):
                        quality.run_format_preview(self.command, cwd=self.root, env={})
                self.assertEqual(len(read_sizes), 2)
                self.assertTrue(all(0 < size <= 8192 for size in read_sizes))

    def test_timeout_kills_the_preview_and_is_reported_not_raised(self):
        def sleep_and_report(command, **kwargs):
            raise quality.subprocess.TimeoutExpired(command, 1)

        with mock.patch.object(quality, "run_format_preview", side_effect=sleep_and_report):
            diagnostic = quality.format_failure_diagnostic(self.args, self.command, RuntimeError("drift"))
        self.assertEqual(diagnostic.count("preview timed out"), 1)

    def test_real_deadline_kills_the_child_and_raises_a_timeout(self):
        killed = []

        class Process:
            returncode = None

            def poll(self):
                return None

            def kill(self):
                killed.append(True)

            def wait(self, timeout=None):
                return 0

        with mock.patch.object(quality, "FORMAT_DIAGNOSTIC_TIMEOUT", 0), \
                mock.patch.object(quality.subprocess, "Popen", return_value=Process()):
            with self.assertRaises(quality.subprocess.TimeoutExpired):
                quality.run_format_preview(self.command, cwd=self.root, env={})
        self.assertTrue(killed)
        self.assertEqual(list(self.scratch.glob("qfli-format-preview-*")), [])

    def test_timeout_cleanup_errors_do_not_replace_the_timeout(self):
        for operation in ("kill", "wait"):
            with self.subTest(operation=operation):
                process = mock.Mock()
                process.poll.return_value = None
                if operation == "kill":
                    process.kill.side_effect = OSError("kill refused")
                else:
                    process.wait.side_effect = quality.subprocess.TimeoutExpired(self.command, 5)
                with mock.patch.object(quality, "FORMAT_DIAGNOSTIC_TIMEOUT", 0), \
                        mock.patch.object(quality.subprocess, "Popen", return_value=process):
                    with self.assertRaises(quality.subprocess.TimeoutExpired):
                        quality.run_format_preview(self.command, cwd=self.root, env={})
                process.kill.assert_called_once_with()
                if operation == "wait":
                    process.wait.assert_called_once_with(timeout=5)

    def test_nonzero_preview_exit_is_a_preview_failure_not_a_pass(self):
        class Process:
            returncode = 65

            def poll(self):
                return 65

            def kill(self):
                return None

            def wait(self, timeout=None):
                return 65

        with mock.patch.object(quality.subprocess, "Popen", return_value=Process()):
            with self.assertRaisesRegex(RuntimeError, "preview command failed"):
                quality.run_format_preview(self.command, cwd=self.root, env={})

    def test_nonzero_preview_exit_never_publishes_the_exception_value(self):
        with mock.patch.object(quality, "run_format_preview",
                               side_effect=RuntimeError("secret-source-fragment")):
            diagnostic = quality.format_failure_diagnostic(self.args, self.command, RuntimeError("drift"))
        self.assertIn("preview unavailable", diagnostic)
        self.assertNotIn("secret-source-fragment", diagnostic)

    def test_links_and_path_escapes_are_refused_before_any_preview(self):
        self.write(self.APPROVED, "void main() {}\n")
        with mock.patch.object(quality, "linked", side_effect=lambda path: Path(path).name == Path(self.APPROVED).name):
            with self.assertRaisesRegex(RuntimeError, "linked"):
                quality.format_diagnostic_paths(self.root)
        with mock.patch.object(quality, "FORMAT_DIAGNOSTIC_PATHS", {"test/../../outside_test.dart"}):
            with self.assertRaisesRegex(RuntimeError, "not a literal root test file"):
                quality.format_diagnostic_paths(self.root)
        with mock.patch.object(quality, "FORMAT_DIAGNOSTIC_PATHS", {"lib/main.dart"}):
            with self.assertRaisesRegex(RuntimeError, "not a literal root test file"):
                quality.format_diagnostic_paths(self.root)
        with self.assertRaisesRegex(RuntimeError, "not approved"):
            quality.format_preview_command(self.command[0], "lib/main.dart")

    def test_unsafe_source_state_is_omitted_without_diffing(self):
        for state in ("linked", "unsafe", "oversized"):
            with self.subTest(state=state):
                with mock.patch.object(quality, "_format_source_snapshot", return_value={"state": state}), \
                        mock.patch.object(quality, "run_format_preview") as runner:
                    diagnostic = quality.format_failure_diagnostic(self.args, self.command, RuntimeError("drift"))
                runner.assert_not_called()
                self.assertIn("preview omitted (" + state + ")", diagnostic)

    def test_diagnostic_is_bounded_and_redacted_before_publication(self):
        self.write(self.APPROVED, "// password=not-a-real-password\nvoid main() {}\n")
        patcher, _ = self.preview(outputs=["x" * 200])
        with patcher, \
                mock.patch.object(quality, "print_untrusted") as printed, \
                mock.patch.object(quality, "annotate") as annotated:
            report = quality.write_format_failure_diagnostic(self.args, self.command, RuntimeError("drift"))
        diagnostic = report.read_text(encoding="utf-8")
        self.assertLessEqual(len(diagnostic.encode()), quality.MAX_FORMAT_DIAGNOSTIC_BYTES)
        self.assertNotIn("not-a-real-password", diagnostic)
        published = printed.call_args.args[0]
        self.assertEqual(published, diagnostic)
        self.assertEqual(annotated.call_args.args[1], diagnostic)

    def test_diagnostic_failure_cannot_replace_the_strict_format_failure(self):
        before = (self.root / self.APPROVED).read_bytes()
        with mock.patch.object(quality, "run", side_effect=RuntimeError("format drift")), \
                mock.patch.object(quality, "format_failure_diagnostic", side_effect=OSError("preview broke")), \
                mock.patch.object(quality, "print_untrusted", side_effect=OSError("console failed")), \
                mock.patch.object(quality, "annotate", side_effect=OSError("annotation failed")):
            with self.assertRaisesRegex(RuntimeError, "format drift"):
                quality.execute_check(self.args, self.manifest, "format")
        self.assertEqual(self.manifest["checks"]["format"]["status"], "failed")
        self.assertEqual(self.manifest["checks"]["format"]["error"], "format drift")
        report = self.args.output / "reports/format-diagnostic.txt"
        self.assertEqual(report.read_text(encoding="utf-8"),
                         "Dart formatter diagnostic unavailable; original failure retained.\n")
        self.assertEqual(before, (self.root / self.APPROVED).read_bytes())

    def test_prepare_drift_skips_previews_and_keeps_the_original_failure(self):
        before = (self.root / self.APPROVED).read_bytes()

        def mutate(command, log, **kwargs):
            self.write(self.APPROVED, "void main() { }\n")
            raise RuntimeError("format drift")

        with mock.patch.object(quality, "run", side_effect=mutate), \
                mock.patch.object(quality, "run_format_preview") as preview:
            with self.assertRaisesRegex(RuntimeError, "format drift"):
                quality.execute_check(self.args, self.manifest, "format")
        # A drifted tree means the preview would describe other bytes.
        preview.assert_not_called()
        self.assertNotEqual(before, (self.root / self.APPROVED).read_bytes())
        self.assertEqual(self.manifest["checks"]["format"]["status"], "failed")

    def test_non_format_stage_has_no_formatter_preview(self):
        with mock.patch.object(quality, "run", side_effect=RuntimeError("analyze failed")), \
                mock.patch.object(quality, "write_format_failure_diagnostic") as preview:
            with self.assertRaisesRegex(RuntimeError, "analyze failed"):
                quality.execute_check(self.args, self.manifest, "analyze")
        preview.assert_not_called()


class QualityMachineSummaryPublicationTests(QualityFixtures):
    """Public failure detail without raw protocol publication or success change."""

    def summarize(self, content):
        path = self.scratch / "protocol.jsonl"
        path.write_text(content, encoding="utf-8")
        return quality.machine_summary(path, self.root, ["test/one_test.dart", "test/two_test.dart"])

    def framework_protocol(self, prints, *, failed=True):
        events = [json.loads(line) for line in self.protocol(failed=failed).splitlines()]
        result = []
        for event in events:
            if event.get("type") == "testDone":
                result.extend(prints.get(event["testID"], []))
            result.append(event)
        return "".join(json.dumps(event) + "\n" for event in result)

    def test_split_framework_block_keeps_failed_context_only_and_stops_at_border(self):
        def printed(identifier, text):
            return {"type": "print", "testID": identifier, "message": text}

        header = "══ " + quality.FRAMEWORK_EXCEPTION_HEADER + " ══"
        content = self.framework_protocol({0: [
            printed(0, "ordinary stdout before header"),
            printed(999, header + " unknown ID body"),
            printed(0, header), printed(0, "Expected one visible widget, found zero"),
            printed(0, "════════════════"), printed(0, "ordinary stdout after border")],
            1: [printed(1, header + "\nexpected exception in a passing test\n════════════════")]})
        result = self.summarize(content)
        self.assertFalse(result["success"])
        self.assertEqual(len(result["frameworkExceptions"]), 1)
        record = result["frameworkExceptions"][0]
        self.assertEqual(record["testId"], "0")
        self.assertIn("Expected one visible widget", record["text"])
        for excluded in ("ordinary stdout", "unknown ID", "passing test"):
            self.assertNotIn(excluded, json.dumps(result))
        baseline = self.summarize(self.protocol(failed=True))
        for key in ("passed", "failed", "completed", "skipped", "protocolDone", "success", "unfinishedTestIds"):
            self.assertEqual(result[key], baseline[key])

    def test_multiline_framework_block_has_same_body_and_stops_at_error_or_completion(self):
        header = quality.FRAMEWORK_EXCEPTION_HEADER
        for ending in ("error", "testDone"):
            with self.subTest(ending=ending):
                events = [{"type": "print", "testID": 0, "message": header + "\nUseful framework assertion"}]
                if ending == "error":
                    events += [{"type": "error", "testID": 0, "error": "See exception logs above"},
                               {"type": "print", "testID": 0, "message": "unrelated after error"}]
                result = self.summarize(self.framework_protocol({0: events}))
                self.assertIn("Useful framework assertion", result["frameworkExceptions"][0]["text"])
                self.assertNotIn("unrelated", json.dumps(result))
                self.assertFalse(result["success"])

    def test_framework_redaction_spans_print_events_before_truncation_and_omits_uris(self):
        header = quality.FRAMEWORK_EXCEPTION_HEADER
        messages = [header, "token=not-a-real-token", "-----BEGIN " + "PRIVATE KEY-----",
                    "synthetic private material " * 20, "-----END " + "PRIVATE KEY-----",
                    "vmServiceUri: http://127.0.0.1:1234/private-service",
                    "link ws://127.0.0.1:4321/private-stream", "Useful final assertion", "════════════"]
        prints = [{"type": "print", "testID": 0, "message": text} for text in messages]
        with mock.patch.object(quality, "MAX_FRAMEWORK_EXCEPTION_RECORD_BYTES", 240):
            result = self.summarize(self.framework_protocol({0: prints}))
        text = result["frameworkExceptions"][0]["text"]
        self.assertLessEqual(len(text.encode()), 240)
        for value in ("not-a-real-token", "synthetic private", "127.0.0.1", "private-service", "private-stream"):
            self.assertNotIn(value, text)
        self.assertIn("redacted", text)
        with mock.patch.object(quality, "print_untrusted"):
            public = quality.publish_machine_summary(result)
        self.assertNotIn("127.0.0.1", public)
        self.assertFalse(result["success"])

    def test_framework_capture_omits_overflowing_blocks_and_bounds_aggregate_text(self):
        header = quality.FRAMEWORK_EXCEPTION_HEADER
        messages = [header + "\n" + "x" * 20000 + "\n════════════", header + "\nsmall assertion\n════════════"]
        prints = [{"type": "print", "testID": 0, "message": text} for text in messages]
        result = self.summarize(self.framework_protocol({0: prints}))
        self.assertEqual(len(result["frameworkExceptions"]), 1)
        self.assertIn("small assertion", result["frameworkExceptions"][0]["text"])
        messages = [header + "\n" + "bounded body " * 10 + "\n════════════"] * 20
        prints = [{"type": "print", "testID": 0, "message": text} for text in messages]
        with mock.patch.object(quality, "MAX_FRAMEWORK_EXCEPTION_BYTES", 500):
            result = self.summarize(self.framework_protocol({0: prints}))
        self.assertLessEqual(sum(len(row["text"].encode()) for row in result["frameworkExceptions"]), 500)
        self.assertFalse(result["success"])

    def test_interleaved_redaction_reserves_the_other_active_block_budget(self):
        header = quality.FRAMEWORK_EXCEPTION_HEADER
        first = header + "\n" + "\n".join(["token=x"] * 8)
        second = header + "\nretained second assertion"
        # Both blocks fit as raw text, but redacting the first expands it.
        reserved = len(second.encode("utf-8")) + 1
        limit = len(first.encode("utf-8")) + 1 + reserved + 8
        self.assertGreater(len(quality.redact(first).encode("utf-8")), limit - reserved)
        events = [json.loads(line) for line in self.protocol(failed=True).splitlines()]
        starts = [event for event in events if event["type"] in ("suite", "testStart")]
        events = starts + [
            {"type": "print", "testID": 0, "message": first},
            {"type": "print", "testID": 1, "message": second},
            {"type": "error", "testID": 0, "error": "first failed"},
            {"type": "testDone", "testID": 0, "result": "failure", "hidden": False},
            {"type": "error", "testID": 1, "error": "second failed"},
            {"type": "testDone", "testID": 1, "result": "failure", "hidden": False},
            {"type": "done", "success": False}]
        captured = []
        original = quality.framework_exception_text

        def observe(message, budget):
            text = original(message, budget)
            captured.append((message, budget, len(text.encode("utf-8"))))
            return text

        with mock.patch.object(quality, "MAX_FRAMEWORK_EXCEPTION_BYTES", limit), \
                mock.patch.object(quality, "framework_exception_text", side_effect=observe):
            result = self.summarize("".join(json.dumps(event) + "\n" for event in events))
        self.assertEqual(len(captured), 2)
        self.assertEqual(captured[0][0], first)
        self.assertEqual(captured[0][1], limit - reserved)
        self.assertLessEqual(captured[0][2] + reserved, limit)
        self.assertEqual(result["frameworkExceptions"][1]["text"], second)
        self.assertLessEqual(sum(row[2] for row in captured), limit)
        self.assertEqual(result["failed"], 2)
        self.assertFalse(result["success"])

    def test_unterminated_framework_block_never_exposes_incomplete_private_key(self):
        content = self.framework_protocol({0: [{"type": "print", "testID": 0,
            "message": quality.FRAMEWORK_EXCEPTION_HEADER + "\n-----BEGIN " + "PRIVATE KEY-----\nsynthetic remainder"}]})
        result = self.summarize(content)
        self.assertNotIn("synthetic remainder", json.dumps(result))
        self.assertIn("incomplete private key redacted", result["frameworkExceptions"][0]["text"])

    def test_successful_tests_and_unmarked_stdout_never_gain_exception_evidence(self):
        event = {"type": "print", "testID": 0,
                 "message": quality.FRAMEWORK_EXCEPTION_HEADER + "\nexpected handled assertion"}
        result = self.summarize(self.framework_protocol({0: [event]}, failed=False))
        self.assertTrue(result["success"])
        self.assertEqual(result["frameworkExceptions"], [])
        event["message"] = "ordinary output even though test fails"
        result = self.summarize(self.framework_protocol({0: [event]}))
        self.assertFalse(result["success"])
        self.assertEqual(result["frameworkExceptions"], [])

    def test_public_framework_projection_revalidates_and_redacts_injected_fields(self):
        summary = {"success": False, "failed": 1, "frameworkExceptions": [
            {"testId": "not-numeric", "text": quality.FRAMEWORK_EXCEPTION_HEADER + " hidden invalid ID"},
            {"testId": "1", "text": "arbitrary stdout"},
            {"testId": "2", "text": quality.FRAMEWORK_EXCEPTION_HEADER
             + "\npassword=not-a-real-password\nws://127.0.0.1/private\n" + "z" * 20000,
             "rawProtocol": "do not copy"}]}
        public = quality.machine_summary_public(summary)
        text = json.dumps(public)
        self.assertEqual(len(public["frameworkExceptions"]), 1)
        self.assertEqual(public["frameworkExceptions"][0]["testId"], "2")
        for value in ("not-a-real-password", "127.0.0.1", "rawProtocol", "arbitrary stdout", "invalid ID"):
            self.assertNotIn(value, text)
        self.assertLessEqual(len(public["frameworkExceptions"][0]["text"].encode()),
                             quality.MAX_FRAMEWORK_EXCEPTION_RECORD_BYTES)
        self.assertFalse(public["success"])

    def test_summary_prints_bounded_redacted_counts_after_the_evidence_write(self):
        manifest = self.prepared()
        published = []

        def capture(text):
            published.append(text)

        with mock.patch.object(quality, "run_machine", side_effect=self.write_machine_from_command), \
                mock.patch.object(quality, "print_untrusted", side_effect=capture):
            quality.execute_check(self.args, manifest, "test")
        text = "".join(published)
        self.assertIn("Root test summary:", text)
        for field in ('"passed": 1', '"skipped": 1', '"failed": 0', '"protocolDone": true'):
            self.assertIn(field, text)
        self.assertIn('"rawReportPublished": false', text)
        # The evidence file stays authoritative and unchanged.
        evidence = read_json(self.args.output / "reports/root-tests.json")
        self.assertTrue(evidence["success"])
        self.assertEqual(manifest["checks"]["test"]["status"], "passed_with_skips")

    def test_failure_error_text_is_redacted_and_bounded_before_printing(self):
        summary = {"success": False, "passed": 1, "failed": 1, "errors":
                   ["token=not-a-real-token"] * 200 + ["x" * 10000]}
        with mock.patch.object(quality, "print_untrusted") as printed:
            text = quality.publish_machine_summary(summary)
        self.assertNotIn("not-a-real-token", text)
        self.assertEqual(text, printed.call_args.args[0]
                         .replace("Root test summary:\n", "", 1))
        self.assertLessEqual(len(text.encode()), quality.MAX_MACHINE_SUMMARY_BYTES)
        self.assertLessEqual(text.count("[sensitive diagnostic line redacted]"),
                             quality.MAX_MACHINE_SUMMARY_ERRORS)
        self.assertNotIn("x" * 10000, text)

    def test_publication_never_reraises_into_the_evidence_write(self):
        manifest = self.prepared()
        with mock.patch.object(quality, "run_machine", side_effect=self.write_machine_from_command), \
                mock.patch.object(quality, "publish_machine_summary", side_effect=RuntimeError("print broke")):
            quality.execute_check(self.args, manifest, "test")
        self.assertTrue(read_json(self.args.output / "reports/root-tests.json")["success"])
        self.assertEqual(manifest["checks"]["test"]["status"], "passed_with_skips")

    def test_publication_cannot_weaken_a_failing_protocol(self):
        manifest = self.prepared()

        def fail(command, log, machine, **kwargs):
            machine.write_text(self.protocol(failed=True), encoding="utf-8")
            Path(log).parent.mkdir(parents=True, exist_ok=True)
            Path(log).write_text("fixture log", encoding="utf-8")
            return "fixture"

        with mock.patch.object(quality, "run_machine", side_effect=fail), \
                mock.patch.object(quality, "print_untrusted") as printed:
            with self.assertRaises(RuntimeError):
                quality.execute_check(self.args, manifest, "test")
        self.assertIn('"success": false', printed.call_args.args[0])
        self.assertEqual(manifest["checks"]["test"]["status"], "failed")
        self.assertFalse(manifest["checks"]["test"]["summary"]["success"])

    def test_raw_protocol_fields_never_reach_the_public_text(self):
        summary = self.summarize(self.protocol())
        summary["skippedTestNames"] = ["private-uri-http://127.0.0.1:1/vm-service/"]
        summary["rawReportSha256"] = "f" * 64
        with mock.patch.object(quality, "print_untrusted") as printed:
            text = quality.publish_machine_summary(summary)
        self.assertEqual(text, printed.call_args.args[0].replace("Root test summary:\n", "", 1))
        self.assertNotIn("private-uri", text)
        self.assertNotIn("vm-service", text)
        self.assertNotIn("f" * 64, text)
        self.assertNotIn("native fixture", text)
        self.assertIn("test/one_test.dart", text)

    def test_non_record_summary_is_rejected_before_printing(self):
        with mock.patch.object(quality, "print_untrusted") as printed:
            with self.assertRaisesRegex(RuntimeError, "not a record"):
                quality.publish_machine_summary(["raw protocol"])
        printed.assert_not_called()


class QualityProtocolAndFinalizationTests(QualityFixtures):
    def completed(self):
        manifest = self.prepared()
        for stage in ("format", "analyze"):
            with mock.patch.object(quality, "run", return_value=""):
                quality.execute_check(self.args, manifest, stage)
        with mock.patch.object(quality, "run_machine", side_effect=self.write_machine_from_command):
            quality.execute_check(self.args, manifest, "test")
        return manifest

    def assert_publication_failed(self):
        saved = read_json(self.args.output / "manifest.json")
        self.assertEqual(saved["status"], "failed")
        self.assertEqual(saved["publication"]["status"], "failed")
        self.assertEqual(saved["core"]["compatibility"], "not_established_by_failed_quality_finalization")
        self.assertFalse((self.args.output / "SHA256SUMS").exists())
        self.assertFalse((self.args.output / ".SHA256SUMS.pending").exists())
        return saved

    def summarize(self, content):
        path = self.scratch / "protocol.jsonl"
        path.write_text(content, encoding="utf-8")
        return quality.machine_summary(path, self.root, ["test/one_test.dart", "test/two_test.dart"])

    def test_protocol_requires_every_root_suite_and_done_success(self):
        for content in (self.protocol(omit_second=True), self.protocol(done=False), self.protocol(failed=True)):
            with self.subTest(content=content):
                self.assertFalse(self.summarize(content)["success"])
        self.assertTrue(self.summarize(self.protocol())["success"])

    def test_flutter_started_process_notifications_preserve_real_test_evidence(self):
        null_frame = '[{"event":"test.startedProcess","params":{"vmServiceUri":null}}]\n'
        uri_frame = json.dumps([{"event": "test.startedProcess",
                                 "params": {"vmServiceUri": "http://127.0.0.1:1234/private-service/"}}]) + "\n"
        lines = self.protocol().splitlines(keepends=True)
        result = self.summarize("\n" + null_frame + "".join(lines[:3]) + uri_frame + "".join(lines[3:]))
        self.assertTrue(result["success"])
        self.assertEqual(result["flutterStartedProcesses"], 2)
        self.assertEqual(result["passed"], 2)
        self.assertEqual(result["suiteFiles"], ["test/one_test.dart", "test/two_test.dart"])
        self.assertNotIn("private-service", json.dumps(result))
        failed = self.summarize(null_frame + self.protocol(failed=True))
        self.assertFalse(failed["success"])
        self.assertEqual(failed["failed"], 1)
        self.assertEqual(failed["flutterStartedProcesses"], 1)
        self.assertFalse(failed["protocolDone"])

    def test_flutter_notifications_do_not_supply_test_or_completion_evidence(self):
        frame = '[{"event":"test.startedProcess","params":{"vmServiceUri":null}}]\n'
        for content in (frame, frame + '{"type":"done","success":true}\n',
                        frame + self.protocol(omit_second=True), frame + self.protocol(done=False)):
            with self.subTest(content=content):
                self.assertFalse(self.summarize(content)["success"])
        with mock.patch.object(quality, "MAX_TEST_EVENTS", 1):
            with self.assertRaisesRegex(RuntimeError, "event bounds"):
                self.summarize(frame + self.protocol())

    def test_flutter_notification_envelopes_reject_malformed_or_hidden_results(self):
        valid = {"event": "test.startedProcess", "params": {"vmServiceUri": None}}
        for frame in ([], [valid, valid], [None], [[valid]],
                      [{"type": "done", "success": True}],
                      [dict(valid, event="test.unknown")],
                      [dict(valid, type="done", success=True)],
                      [{"event": "test.startedProcess"}],
                      [dict(valid, params=None)], [dict(valid, params={})],
                      [dict(valid, params={"vmServiceUri": 1})],
                      [dict(valid, params={"vmServiceUri": False})],
                      [dict(valid, params={"vmServiceUri": None, "success": True})]):
            with self.subTest(frame=frame):
                with self.assertRaisesRegex(RuntimeError, "Flutter test notification"):
                    self.summarize(json.dumps(frame) + "\n" + self.protocol())

    def test_machine_summary_resolves_root_without_weakening_suite_confinement(self):
        path = self.scratch / "protocol.jsonl"
        path.write_text(self.protocol(), encoding="utf-8")
        alias = self.root / ".." / self.root.name
        expected = ["test/one_test.dart", "test/two_test.dart"]
        summary = quality.machine_summary(path, alias, expected)
        self.assertTrue(summary["success"])
        self.assertEqual(summary["suiteFiles"], expected)
        self.assertEqual(summary["missingSuiteFiles"], [])
        event = {"type": "suite", "suite": {"path": str(self.root / "test/../../outside_test.dart")}}
        path.write_text(json.dumps(event) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "outside root test"):
            quality.machine_summary(path, alias, expected)

    def test_all_skipped_protocol_is_not_a_pass(self):
        events = [json.loads(line) for line in self.protocol().splitlines()]
        for event in events:
            if event["type"] == "testDone":
                event["skipped"] = True
        result = self.summarize("".join(json.dumps(event) + "\n" for event in events))
        self.assertEqual(result["passed"], 0)
        self.assertFalse(result["success"])

    def test_error_event_and_unfinished_test_cannot_hide_behind_done_success(self):
        content = self.protocol()
        error = {"type": "error", "testID": 0, "error": "fixture failed", "isFailure": True}
        self.assertFalse(self.summarize(content + json.dumps(error) + "\n")["success"])
        start = {"type": "testStart", "test": {"id": 99, "name": "unfinished"}}
        result = self.summarize(content + json.dumps(start) + "\n")
        self.assertEqual(result["unfinishedTestIds"], ["99"])
        self.assertFalse(result["success"])

    def test_suite_path_outside_root_test_is_rejected(self):
        event = {"type": "suite", "suite": {"path": str(self.root / "integration_test/device_test.dart")}}
        with self.assertRaisesRegex(RuntimeError, "outside root test"):
            self.summarize(json.dumps(event) + "\n")

    def test_duplicate_test_completion_is_rejected(self):
        content = self.protocol()
        duplicate = {"type": "testDone", "testID": 0, "result": "success"}
        with self.assertRaisesRegex(RuntimeError, "Duplicate"):
            self.summarize(content + json.dumps(duplicate) + "\n")

    def test_machine_report_bound_is_enforced(self):
        with mock.patch.object(quality, "MAX_MACHINE_BYTES", 5):
            with self.assertRaisesRegex(RuntimeError, "exceeds its bound"):
                self.summarize(self.protocol())

    def test_missing_gate_finalizes_as_blocked_and_raises(self):
        manifest = quality.new_manifest(self.args)
        with self.assertRaisesRegex(RuntimeError, "did not complete"):
            quality.finalize(self.args, manifest, "failure")
        saved = read_json(self.args.output / "manifest.json")
        self.assertEqual(saved["status"], "blocked")
        self.assertTrue(all(row["status"] == "not_run" for row in saved["checks"].values()))
        self.assertFalse(saved["nativeRuntimeExecuted"])
        self.assertTrue((self.args.output / "reports/quality-finalize-failure.txt").is_file())
        self.assertEqual(saved["publication"]["status"], "failed")
        self.assertFalse((self.args.output / "SHA256SUMS").exists())

    def test_missing_required_check_never_finalizes_success(self):
        manifest = self.prepared()
        manifest["checks"]["format"] = {"status": "passed"}
        with self.assertRaisesRegex(RuntimeError, "did not pass"):
            quality.finalize(self.args, manifest, "success")
        self.assertEqual(manifest["status"], "failed")

    def test_finalize_preserves_skip_status_and_hashes_final_report(self):
        manifest = self.prepared()
        for stage in ("format", "analyze"):
            with mock.patch.object(quality, "run", return_value=""):
                quality.execute_check(self.args, manifest, stage)
        with mock.patch.object(quality, "run_machine", side_effect=self.write_machine_from_command):
            quality.execute_check(self.args, manifest, "test")
        quality.finalize(self.args, manifest, "success")
        saved = read_json(self.args.output / "manifest.json")
        self.assertEqual(saved["status"], "passed_with_skips")
        self.assertEqual(saved["core"]["compatibility"], "linux_host_quality_checks_only")
        self.assertIn(f"{sha256(self.args.output / 'manifest.json')}  manifest.json\n",
                      (self.args.output / "SHA256SUMS").read_text())

    def test_checksum_failure_revokes_previously_published_success(self):
        manifest = self.completed()
        quality.finalize(self.args, manifest, "success")
        self.assertTrue((self.args.output / "SHA256SUMS").is_file())
        with mock.patch.object(quality, "checksums", side_effect=OSError("checksum publication failed")):
            with self.assertRaisesRegex(RuntimeError, "checksum publication failed"):
                quality.finalize(self.args, manifest, "success")
        saved = self.assert_publication_failed()
        self.assertEqual(saved["checks"]["test"]["status"], "passed_with_skips")

    def test_checksum_hash_read_failure_is_inside_publication_boundary(self):
        manifest = self.completed()
        original_hash = quality.sha256

        def fail_report_hash(path):
            if Path(path) == self.args.output / "reports/root-tests.json":
                raise OSError("report checksum read failed")
            return original_hash(path)

        with mock.patch.object(quality, "sha256", side_effect=fail_report_hash):
            with self.assertRaisesRegex(RuntimeError, "report checksum read failed"):
                quality.finalize(self.args, manifest, "success")
        self.assert_publication_failed()

    def test_partial_checksum_and_diagnostic_failure_cannot_preserve_success(self):
        manifest = self.completed()

        def partial_checksums(args):
            (args.output / "SHA256SUMS").write_text("partial public checksum", encoding="utf-8")
            (args.output / ".SHA256SUMS.pending").write_text("partial pending checksum", encoding="utf-8")
            raise OSError("partial checksum failure")

        with mock.patch.object(quality, "checksums", side_effect=partial_checksums), \
                mock.patch.object(quality, "report_failure", side_effect=OSError("diagnostic write failed")):
            with self.assertRaisesRegex(RuntimeError, "partial checksum failure"):
                quality.finalize(self.args, manifest, "success")
        saved = self.assert_publication_failed()
        self.assertTrue(any("diagnostic write failed" in value for value in saved["recoveryErrors"]))

    def test_final_manifest_write_failure_recovers_failed_status(self):
        manifest = self.completed()
        original_save = quality.save
        calls = []

        def fail_candidate(args, value):
            original_save(args, value)
            calls.append(value["status"])
            if len(calls) == 1:
                raise OSError("manifest publication failed")

        with mock.patch.object(quality, "save", side_effect=fail_candidate):
            with self.assertRaisesRegex(RuntimeError, "manifest publication failed"):
                quality.finalize(self.args, manifest, "success")
        self.assert_publication_failed()
        self.assertEqual(calls, ["passed_with_skips", "failed"])

    def test_persistent_manifest_failure_removes_stale_success(self):
        manifest = self.completed()
        quality.finalize(self.args, manifest, "success")
        with mock.patch.object(quality, "save", side_effect=OSError("manifest unavailable")):
            with self.assertRaisesRegex(RuntimeError, "manifest unavailable"):
                quality.finalize(self.args, manifest, "success")
        self.assertFalse((self.args.output / "manifest.json").exists())
        self.assertFalse((self.args.output / "SHA256SUMS").exists())
        self.assertEqual(manifest["status"], "failed")

    def test_summary_failure_removes_completed_checksums(self):
        manifest = self.completed()
        with mock.patch.object(quality, "step_summary", side_effect=OSError("summary publication failed")):
            with self.assertRaisesRegex(RuntimeError, "summary publication failed"):
                quality.finalize(self.args, manifest, "success")
        self.assert_publication_failed()

    def test_changed_root_test_evidence_cannot_finalize_success(self):
        manifest = self.completed()
        write_json(self.args.output / "reports/root-tests.json", {"success": True})
        with self.assertRaisesRegex(RuntimeError, "evidence is missing or changed"):
            quality.finalize(self.args, manifest, "success")
        self.assert_publication_failed()

    def test_bootstrap_logs_are_bounded_and_redacted_before_publication(self):
        path = self.args.bootstrap / "reports/setup.log"
        path.parent.mkdir(parents=True)
        path.write_text("-----BEGIN PRIVATE KEY-----\nnot-a-real-secret\n-----END PRIVATE KEY-----\n"
                        "token=not-a-real-token\nordinary line\n", encoding="utf-8")
        quality.retain_bootstrap(self.args)
        published = (self.args.output / "reports/bootstrap/reports/setup.log").read_text()
        self.assertNotIn("not-a-real-secret", published)
        self.assertNotIn("not-a-real-token", published)
        self.assertIn("ordinary line", published)
        self.assertLessEqual(len(published.encode()), quality.LOG_LIMIT)

    def test_oversized_artifact_becomes_failure_report_not_a_success_upload(self):
        manifest = self.prepared()
        with mock.patch.object(quality, "MAX_REPORT_BYTES", 1):
            with self.assertRaises(RuntimeError):
                quality.finalize(self.args, manifest, "failure")
        self.assertEqual(read_json(self.args.output / "manifest.json")["status"], "failed")
        self.assertFalse((self.args.output / "reports/bootstrap").exists())

    def test_quality_output_cannot_overwrite_source_or_bootstrap(self):
        for output in (self.root, self.args.bootstrap):
            args = copy.copy(self.args)
            args.output = output
            with self.assertRaisesRegex(RuntimeError, "below build/app-quality"):
                quality.confined_output(args)

    def test_workflow_has_no_privileged_pr_or_secret_inputs_and_keeps_gate_failure_visible(self):
        workflow = Path(__file__).resolve().parents[2] / ".github/workflows/app-quality.yml"
        text = workflow.read_text(encoding="utf-8")
        operational = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
        self.assertIn("  pull_request:", operational)
        self.assertNotIn("pull_request_target:", operational)
        self.assertNotIn("secrets.", operational)
        self.assertNotIn("contents: write", operational)
        self.assertNotIn("id-token:", operational)
        self.assertNotIn("continue-on-error:", operational)
        self.assertIn("path: qflistudio-core", operational)
        self.assertIn("persist-credentials: false", operational)
        self.assertIn("python tool/ci/app_quality.py finalize", operational)
        self.assertIn("if: always()", operational)
        self.assertIn("branches: [main]", operational)
        self.assertIn("  workflow_dispatch:", operational)
        self.assertIn("contents: read", operational)
        self.assertIn("--platform linux --arch x64", operational)
        self.assertIn("build/app-artifacts/app-quality-linux-x64", operational)
        self.assertIn("qflistudio-rust/build/app-quality/linux-x64/", operational)
        self.assertIn("retention-days: 14", operational)
        self.assertNotIn("${{ runner.temp }}", operational)
        self.assertIn("PUB_CACHE=$RUNNER_TEMP/qfli-quality-pub-cache", operational)
        self.assertIn("GRADLE_USER_HOME=$RUNNER_TEMP/qfli-quality-gradle-cache", operational)
        self.assertIn('>> "$GITHUB_ENV"', operational)
        application = operational.split("  application-quality:\n", 1)[1]
        caches = application.index("- name: Configure runner-local dependency caches")
        self.assertLess(application.index("uses: actions/setup-python@"), caches)
        self.assertLess(caches, application.index("python tool/ci/app_build.py init"))
        self.assertIn("actions: read", application)
        self.assertNotIn("actions: write", operational)
        self.assertIn("QFLI_QUALITY_ASSET_SOURCE=$RUNNER_TEMP/qfli-quality-native-inputs", application)
        stages = [application.index(value) for value in (
            "python tool/ci/app_build.py setup-flutter", "python tool/ci/app_quality.py resolve-assets",
            "uses: actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333",
            "python tool/ci/app_quality.py install-assets", "python tool/ci/app_quality.py prepare",
            "python tool/ci/app_quality.py test")]
        self.assertEqual(stages, sorted(stages))
        self.assertIn("artifact-ids: ${{ steps.quality_assets.outputs.artifact_ids }}", application)
        self.assertIn("run-id: ${{ steps.quality_assets.outputs.run_id }}", application)
        self.assertIn("github-token: ${{ github.token }}", application)
        self.assertEqual(application.count("GH_TOKEN:"), 1)
        self.assertNotIn("needs:", operational)
        self.assertNotIn("if: ${{ vars.QFLI_APPROVED_CORE_SHA", operational)


if __name__ == "__main__":
    quality.require_hosted_runner()
    unittest.main()
