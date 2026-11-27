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

    def prepared(self):
        manifest = quality.new_manifest(self.args)
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
        manifest = quality.new_manifest(self.args)

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
        manifest = quality.new_manifest(self.args)
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
        manifest = quality.new_manifest(self.args)
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

        manifest = quality.new_manifest(self.args)
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
        self.assertNotIn("needs:", operational)
        self.assertNotIn("if: ${{ vars.QFLI_APPROVED_CORE_SHA", operational)


if __name__ == "__main__":
    quality.require_hosted_runner()
    unittest.main()
