"""Hermetic orchestration contracts. Execute this suite only on GitHub runners."""

import argparse
import contextlib
import copy
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import app_build as app
import ci_support as support
from miri_build_support import compiler_boundary_patch, compiler_patch_hunks


def setUpModule():
    support.require_hosted_runner()


class OrchestrationContracts(unittest.TestCase):
    def test_import_and_target_selection_do_not_require_core_sha(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(support.TARGETS["android", "arm64-x64"], ("android-arm64", "android-x64"))
            self.assertEqual(len(support.PACKAGE_NAMES["android", "arm64-x64"]), 2)
            parser = argparse.ArgumentParser()
            support.add_target_arguments(parser)
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                support.resolve_target(parser.parse_args(["--platform", "android", "--arch", "all"]), parser)

    def test_android_split_build_uses_only_supported_abis_without_duplicate_filters(self):
        args = argparse.Namespace(platform="android", arch="arm64-x64", flutter_root=Path("flutter"))
        command = app.release_command(args, {})
        self.assertEqual(command[command.index("--target-platform") + 1], "android-arm64,android-x64")
        self.assertEqual(command.count("--split-per-abi"), 1)
        self.assertNotIn("android-arm,", command[command.index("--target-platform") + 1])

        gradle = (app.ROOT / "android/app/build.gradle.kts").read_text(encoding="utf-8")
        self.assertIn('mapOf("android-arm64" to "arm64-v8a", "android-x64" to "x86_64")', gradle)
        self.assertIn('providers.gradleProperty("split-per-abi").orNull == "true"', gradle)
        self.assertEqual(gradle.count("if (!splitPerAbi) {"), 2)
        self.assertEqual(gradle.count("abiFilters.clear()"), 2)
        self.assertEqual(gradle.count("abiFilters += rustAbis"), 2)

    def test_ios_release_build_requests_verbose_unsigned_diagnostics_and_runner_python(self):
        args = argparse.Namespace(platform="ios", arch="arm64", flutter_root=Path("flutter"))
        runner_path = os.environ.get("PATH", "")
        env = {"PATH": runner_path}
        command = list(map(str, app.release_command(args, env)))

        self.assertEqual(command[1:3], ["build", "ios"])
        self.assertIn("--verbose", command)
        self.assertIn("--no-codesign", command)
        self.assertNotIn("--codesign", command)
        self.assertNotIn("--no-pub", command)
        self.assertEqual(env["PATH"], runner_path)
        self.assertEqual(env["FLUTTER_XCODE_PATH"], os.pathsep.join(
            part for part in (str(Path(sys.executable).resolve().parent), runner_path) if part))

    def test_non_ios_release_builds_do_not_override_xcode_script_path(self):
        for platform, arch in (("android", "arm64-x64"), ("ohos", "arm64"), ("macos", "arm64")):
            with self.subTest(platform=platform):
                env = {"PATH": os.environ.get("PATH", "")}
                args = argparse.Namespace(platform=platform, arch=arch, flutter_root=Path("flutter"))
                app.release_command(args, env)
                self.assertNotIn("FLUTTER_XCODE_PATH", env)

    def test_linux_installer_runner_installs_secret_service_development_headers(self):
        workflow = (app.ROOT / ".github/workflows/app-installers.yml").read_text(encoding="utf-8")
        install = next(line for line in workflow.splitlines() if "apt-get install --no-install-recommends" in line)
        self.assertIn("libsecret-1-dev", install)

    def test_process_execution_rejects_local_runner_before_writing(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(support.subprocess, "run") as command:
            with self.assertRaisesRegex(RuntimeError, "GitHub-hosted"):
                support.run(["must-not-run"], Path("must-not-write.log"))
            command.assert_not_called()

    def test_missing_core_approval_is_preflight_not_import_requirement(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(RuntimeError, "final immutable handoff"):
            app.preflight(None, {"core": {}})

    def test_superseded_core_pin_is_rejected(self):
        sha = "ee83f1c" + "0" * 33
        with patch.dict(os.environ, {"CORE_SHA": sha, "APPROVED_CORE_SHA": sha}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "superseded"):
                app.preflight(None, {"core": {}})

    def core_dependency_fixture(self, temporary):
        root = Path(temporary) / "consumer workspace" / "qflistudio-rust"
        core = root.parent / "qflistudio-core"
        root.mkdir(parents=True)
        core.mkdir()
        (core / "pubspec.yaml").write_text("name: qfli_studio_core\n", encoding="utf-8")
        paths = {"qfli_studio_core": "../qflistudio-core",
                 "re_editor": "../qflistudio-core/vendor/re_editor",
                 "xterm": "../qflistudio-core/vendor/xterm"}
        for name in ("re_editor", "xterm"):
            vendor = core / "vendor" / name
            vendor.mkdir(parents=True)
            (vendor / "pubspec.yaml").write_text("name: " + name + "\n", encoding="utf-8")
        pubspec = ("name: qfli_rust\ndependencies:\n  qfli_studio_core:\n    path: ../qflistudio-core\n"
                   "dependency_overrides:\n  re_editor:\n    path: ../qflistudio-core/vendor/re_editor\n"
                   "  xterm:\n    path: ../qflistudio-core/vendor/xterm\n")
        (root / "pubspec.yaml").write_text(pubspec, encoding="utf-8")
        versions = {"qfli_studio_core": "1.0.0+1", "re_editor": "0.10.0", "xterm": "4.0.0"}
        blocks = {name: f'  {name}:\n    description:\n      path: "{relative}"\n      relative: true\n'
                        f'    source: path\n    version: "{versions[name]}"\n'
                  for name, relative in paths.items()}
        lock = "packages:\n" + "".join(blocks.values())
        (root / "pubspec.lock").write_text(lock, encoding="utf-8")
        config = {"configVersion": 2, "packages": [
            {"name": name, "rootUri": (root / relative).resolve().as_uri() + "/"}
            for name, relative in paths.items()]}
        support.write_json(root / ".dart_tool/package_config.json", config)
        args = argparse.Namespace(output=root / "build/report", flutter_root=root / "flutter",
                                  platform="linux", arch="x64")
        (args.output / "reports").mkdir(parents=True)
        return SimpleNamespace(root=root, core=core, paths=paths, pubspec=pubspec, lock=lock, blocks=blocks,
                               config=config, manifest={"core": {"commit": "b" * 40, "compatibility": "not_verified"}},
                               args=args)

    def test_core_contract_accepts_both_root_vendor_overrides(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.core_dependency_fixture(temporary)
            self.assertEqual(app.CORE_DEPENDENCY_PATHS, fixture.paths)
            with patch.object(app, "ROOT", fixture.root), patch.object(app, "git_value", return_value="b" * 40):
                app.verify_core(fixture.args, fixture.manifest)
            self.assertIs(fixture.manifest["core"]["checkoutVerified"], True)

    def test_core_contract_rejects_missing_wrong_or_misnamed_vendor_overrides(self):
        for name in ("re_editor", "xterm"):
            for mutation in ("missing", "wrong_path", "misnamed"):
                with self.subTest(name=name, mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                    fixture = self.core_dependency_fixture(temporary)
                    block = f"  {name}:\n    path: {fixture.paths[name]}\n"
                    replacement = {"missing": "", "wrong_path": block.replace("vendor/", "other/"),
                                   "misnamed": block.replace(name + ":", "other:")}[mutation]
                    (fixture.root / "pubspec.yaml").write_text(fixture.pubspec.replace(block, replacement), encoding="utf-8")
                    with patch.object(app, "ROOT", fixture.root), patch.object(app, "git_value", return_value="b" * 40):
                        with self.assertRaisesRegex(RuntimeError, "root dependency_overrides path for " + name):
                            app.verify_core(fixture.args, fixture.manifest)

    def test_core_contract_rejects_noncanonical_lock_sources(self):
        for name in ("qfli_studio_core", "re_editor", "xterm"):
            for mutation in ("missing", "hosted", "absolute", "wrong_path"):
                with self.subTest(name=name, mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                    fixture = self.core_dependency_fixture(temporary)
                    block = fixture.blocks[name]
                    replacement = {"missing": "", "hosted": block.replace("source: path", "source: hosted"),
                                   "absolute": block.replace("relative: true", "relative: false"),
                                   "wrong_path": block.replace(fixture.paths[name], "../other-core")}[mutation]
                    (fixture.root / "pubspec.lock").write_text(fixture.lock.replace(block, replacement), encoding="utf-8")
                    with patch.object(app, "ROOT", fixture.root), patch.object(app, "git_value", return_value="b" * 40):
                        with self.assertRaisesRegex(RuntimeError, "lockfile path/source for " + name):
                            app.verify_core(fixture.args, fixture.manifest)

    def test_core_contract_rejects_absent_vendor_source(self):
        for name in ("re_editor", "xterm"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                fixture = self.core_dependency_fixture(temporary)
                (fixture.core / "vendor" / name / "pubspec.yaml").unlink()
                with patch.object(app, "ROOT", fixture.root), patch.object(app, "git_value", return_value="b" * 40):
                    with self.assertRaisesRegex(RuntimeError, "vendor/" + name + " is absent"):
                        app.verify_core(fixture.args, fixture.manifest)

    def test_release_accepts_vendor_roots_and_records_their_identities(self):
        for uri_kind in ("file", "relative"):
            with self.subTest(uri_kind=uri_kind), tempfile.TemporaryDirectory() as temporary:
                fixture = self.core_dependency_fixture(temporary)
                if uri_kind == "relative":
                    for row in fixture.config["packages"]:
                        row["rootUri"] = "../" + fixture.paths[row["name"]] + "/"
                    support.write_json(fixture.root / ".dart_tool/package_config.json", fixture.config)
                def identity(directory, *arguments):
                    return app.FLUTTER_COMMIT if directory == fixture.args.flutter_root else "b" * 40
                with patch.object(app, "ROOT", fixture.root), patch.object(app, "git_value", side_effect=identity), \
                        patch.object(app, "run") as command, patch.object(app, "retain_intermediates"):
                    app.build_release(fixture.args, fixture.manifest)
                self.assertEqual(command.call_count, 2)
                self.assertNotIn("--no-pub", command.call_args_list[1].args[0])
                evidence = support.read_json(fixture.args.output / "reports/resolved-core.json")
                self.assertEqual(evidence["packages"], {name: str((fixture.root / path).resolve())
                                                       for name, path in fixture.paths.items()})
                self.assertEqual(evidence["packageConfigSha256"], support.sha256(fixture.root / ".dart_tool/package_config.json"))
                self.assertEqual(evidence["packageConfigSha256BeforeBuild"], evidence["packageConfigSha256"])
                self.assertEqual(evidence["lockfileSha256BeforeBuild"], evidence["lockfileSha256"])
                self.assertEqual(evidence["lockfileSha256"], support.sha256(fixture.root / "pubspec.lock"))

    def test_release_rejects_missing_hosted_wrong_or_remote_xterm_roots_before_build(self):
        for mutation in ("missing", "hosted", "wrong_root", "remote", "unsupported_scheme"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                fixture = self.core_dependency_fixture(temporary)
                row = next(row for row in fixture.config["packages"] if row["name"] == "xterm")
                if mutation == "missing":
                    fixture.config["packages"].remove(row)
                else:
                    row["rootUri"] = {"hosted": (fixture.root / ".pub-cache/hosted/pub.dev/xterm-4.0.0").as_uri(),
                                      "wrong_root": (fixture.core / "vendor/re_editor").as_uri(),
                                      "remote": "file://remote.example/vendor/xterm",
                                      "unsupported_scheme": "https://example.invalid/xterm"}[mutation]
                support.write_json(fixture.root / ".dart_tool/package_config.json", fixture.config)
                def identity(directory, *arguments):
                    return app.FLUTTER_COMMIT if directory == fixture.args.flutter_root else "b" * 40
                with patch.object(app, "ROOT", fixture.root), patch.object(app, "git_value", side_effect=identity), \
                        patch.object(app, "run") as command:
                    with self.assertRaisesRegex(RuntimeError, "(?:URI|path differs): xterm"):
                        app.build_release(fixture.args, fixture.manifest)
                command.assert_called_once()
                self.assertEqual(fixture.manifest["core"]["compatibility"], "not_verified")

    def test_release_rechecks_lock_source_after_restore(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.core_dependency_fixture(temporary)
            def identity(directory, *arguments):
                return app.FLUTTER_COMMIT if directory == fixture.args.flutter_root else "b" * 40
            def restore(*arguments, **keywords):
                block = fixture.blocks["xterm"]
                (fixture.root / "pubspec.lock").write_text(
                    fixture.lock.replace(block, block.replace("source: path", "source: hosted")), encoding="utf-8")
            with patch.object(app, "ROOT", fixture.root), patch.object(app, "git_value", side_effect=identity), \
                    patch.object(app, "run", side_effect=restore) as command:
                with self.assertRaisesRegex(RuntimeError, "lockfile path/source for xterm"):
                    app.build_release(fixture.args, fixture.manifest)
            command.assert_called_once()

    def test_release_rejects_post_build_xterm_path_drift_before_compatibility(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.core_dependency_fixture(temporary)
            calls = 0

            def identity(directory, *arguments):
                return app.FLUTTER_COMMIT if directory == fixture.args.flutter_root else "b" * 40

            def command(arguments, *args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 2:
                    config_path = fixture.root / ".dart_tool/package_config.json"
                    config = support.read_json(config_path)
                    row = next(row for row in config["packages"] if row["name"] == "xterm")
                    row["rootUri"] = (fixture.core / "vendor/re_editor").as_uri() + "/"
                    support.write_json(config_path, config)

            with patch.object(app, "ROOT", fixture.root):
                with patch.object(app, "git_value", side_effect=identity):
                    with patch.object(app, "run", side_effect=command) as run_command:
                        with patch.object(app, "retain_intermediates"):
                            with self.assertRaisesRegex(RuntimeError, "Resolved dependency path differs: xterm"):
                                app.build_release(fixture.args, fixture.manifest)

            self.assertEqual(calls, 2)
            self.assertNotIn("--no-pub", run_command.call_args_list[1].args[0])
            self.assertEqual(fixture.manifest["core"]["compatibility"], "not_verified")
            self.assertFalse((fixture.args.output / "reports/intermediate-inventory.json").exists())

    def test_release_rejects_post_build_lockfile_drift_before_compatibility(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.core_dependency_fixture(temporary)
            calls = 0

            def identity(directory, *arguments):
                return app.FLUTTER_COMMIT if directory == fixture.args.flutter_root else "b" * 40

            def command(arguments, *args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 2:
                    lock_path = fixture.root / "pubspec.lock"
                    lock_path.write_text(fixture.lock.replace("vendor/xterm", "vendor/re_editor"),
                                         encoding="utf-8")

            with patch.object(app, "ROOT", fixture.root):
                with patch.object(app, "git_value", side_effect=identity):
                    with patch.object(app, "run", side_effect=command) as run_command:
                        with patch.object(app, "retain_intermediates"):
                            with self.assertRaisesRegex(RuntimeError, "Flutter build changed pubspec.lock"):
                                app.build_release(fixture.args, fixture.manifest)

            self.assertEqual(calls, 2)
            self.assertNotIn("--no-pub", run_command.call_args_list[1].args[0])
            self.assertEqual(fixture.manifest["core"]["compatibility"], "not_verified")
            self.assertFalse((fixture.args.output / "reports/intermediate-inventory.json").exists())

    def test_release_accepts_package_config_metadata_change_and_records_final_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.core_dependency_fixture(temporary)
            config_path = fixture.root / ".dart_tool/package_config.json"
            config_before = support.sha256(config_path)
            calls = 0

            def identity(directory, *arguments):
                return app.FLUTTER_COMMIT if directory == fixture.args.flutter_root else "b" * 40

            def command(arguments, *args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 2:
                    config = support.read_json(config_path)
                    config["generatorVersion"] = "2.0"
                    support.write_json(config_path, config)

            with patch.object(app, "ROOT", fixture.root):
                with patch.object(app, "git_value", side_effect=identity):
                    with patch.object(app, "run", side_effect=command) as run_command:
                        with patch.object(app, "retain_intermediates"):
                            app.build_release(fixture.args, fixture.manifest)

            evidence = support.read_json(fixture.args.output / "reports/resolved-core.json")
            self.assertEqual(calls, 2)
            self.assertNotIn("--no-pub", run_command.call_args_list[1].args[0])
            self.assertEqual(fixture.manifest["core"]["compatibility"],
                             "this_platform_release_build_only")
            self.assertEqual(evidence["packageConfigSha256BeforeBuild"], config_before)
            self.assertNotEqual(evidence["packageConfigSha256"], config_before)
            self.assertEqual(evidence["packageConfigSha256"], support.sha256(config_path))
            self.assertEqual(evidence["lockfileSha256BeforeBuild"], evidence["lockfileSha256"])
            self.assertEqual(evidence["lockfileSha256"], support.sha256(fixture.root / "pubspec.lock"))
            self.assertEqual(set(evidence["packages"]), set(app.CORE_DEPENDENCY_PATHS))

    def test_canonical_safe_paths(self):
        for value in ("../outside", "/absolute", "C:/drive", "a\\b", "a//b", "a/./b", "a\nb", ""):
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                app.safe_relative(value)
        self.assertEqual(app.safe_relative("build-info/ci-build.json").as_posix(), "build-info/ci-build.json")

    def test_runtime_tar_confinement_and_no_links(self):
        for name, kind in (("../outside", tarfile.REGTYPE), ("native/link", tarfile.SYMTYPE),
                           ("unrelated/file", tarfile.REGTYPE), ("assets//bad", tarfile.REGTYPE)):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                archive = root / "runtime.tar.gz"
                with tarfile.open(archive, "w:gz") as bundle:
                    member = tarfile.TarInfo(name)
                    member.type = kind
                    member.linkname = "../../outside"
                    bundle.addfile(member)
                destination = root / "payload"
                destination.mkdir()
                with self.assertRaises(RuntimeError):
                    app.extract_runtime(archive, destination)
                self.assertEqual(list(destination.iterdir()), [])

    def test_bounded_log_redacts_private_keys_and_tokens(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "raw.log"
            path.write_text("-----BEGIN PRIVATE KEY-----\nsecret-key-payload\n-----END PRIVATE KEY-----\n"
                            "token=hidden\nnormal diagnostic\n", encoding="utf-8")
            result = support.bounded_log(path)
            self.assertNotIn("secret-key-payload", result)
            self.assertNotIn("hidden", result)
            self.assertIn("normal diagnostic", result)
            path.write_text("x" * 70000 + "\nlast diagnostic\n", encoding="utf-8")
            result = support.bounded_log(path)
            self.assertIn("oversized", result)
            self.assertIn("last diagnostic", result)
            self.assertNotIn("x" * 100, result)

    def runtime_run(self):
        return {"id": 42, "run_attempt": 1, "status": "completed", "conclusion": "success",
                "repository": {"full_name": "owner/app"}, "head_repository": {"full_name": "owner/app"},
                "event": "push", "head_branch": "main", "path": app.NATIVE_WORKFLOW,
                "head_sha": "a" * 40, "html_url": "https://github.com/owner/app/actions/runs/42"}

    def runtime_artifact(self):
        return {"id": 123, "name": "native-runtime-ohos-arm64", "expired": False,
                "size_in_bytes": 100, "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()}

    def test_runtime_selection_requires_exact_source_inputs(self):
        inputs = {"native": "n", "scripts": "s", app.NATIVE_WORKFLOW: "w"}
        with patch.object(app, "runtime_input_identity", return_value=inputs), \
                patch.object(app, "runtime_artifacts", return_value=[self.runtime_artifact()]):
            result = app.validate_runtime_run(self.runtime_run(), "owner/app", inputs, ["ohos-arm64"])
            self.assertEqual(result["runId"], "42")
            self.assertEqual(result["inputCompatibility"]["method"], "exact_git_objects")
            with self.assertRaisesRegex(RuntimeError, "Git objects differ"):
                app.validate_runtime_run(self.runtime_run(), "owner/app", {**inputs, "native": "different"}, ["ohos-arm64"])

    def test_runtime_selection_rejects_fork_or_expired_artifacts(self):
        inputs = {"native": "n"}
        run = self.runtime_run()
        run["head_repository"] = {"full_name": "fork/app"}
        with self.assertRaisesRegex(RuntimeError, "not a fork"):
            app.validate_runtime_run(run, "owner/app", inputs, ["ohos-arm64"])
        artifact = {**self.runtime_artifact(), "expired": True}
        with patch.object(app, "runtime_input_identity", return_value=inputs), \
                patch.object(app, "runtime_artifacts", return_value=[artifact]), self.assertRaisesRegex(RuntimeError, "expired"):
            app.validate_runtime_run(self.runtime_run(), "owner/app", inputs, ["ohos-arm64"])

    def runtime_fixture(self, root, source, platform="ohos"):
        host = {"ohos": "aarch64-unknown-linux-ohos", "android": "aarch64-linux-android",
                "ios": "aarch64-apple-ios"}[platform]
        key = platform + "-arm64"
        schema = 1 if platform == "ohos" else 2
        suffix = ".dylib" if platform == "ios" else ".so"
        names = {"adapter": "libqfli_miri" + suffix, "driver": "librustc_driver-test" + suffix,
                 "backend": "librustc_codegen_cranelift-test" + suffix, "std": "libstd-test" + suffix}
        originals = {}
        paths = {}
        rows = []
        native = (root / "ohos/entry/libs/arm64-v8a" if platform == "ohos"
                  else root / "native/build/runtime" / (host if platform == "ios" else key))
        for role, name in names.items():
            original = root.parent / (root.name + "-producer") / name
            original.parent.mkdir(parents=True, exist_ok=True)
            original.write_bytes((role + "-source").encode())
            originals[role] = original
            framework = app.framework_name(name)
            relative = f"{framework}.framework/{framework}" if platform == "ios" else name
            path = native / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(original.read_bytes() + (b"-rewritten-signed" if platform == "ios" else b""))
            paths[role] = path
            row = {"name": name, "sha256": support.sha256(path)}
            if schema == 2:
                row.update(path=relative, role=role if role in ("adapter", "backend") else "dependency",
                           size=path.stat().st_size, sourceSha256=support.sha256(original))
            rows.append(row)
            if platform == "android":
                duplicate = root / "android/app/src/main/jniLibs/arm64-v8a" / name
                duplicate.parent.mkdir(parents=True, exist_ok=True)
                duplicate.write_bytes(path.read_bytes())
        boundary = {"kind": app.COMPILER_BOUNDARY_KIND, "patchSha256": app.COMPILER_BOUNDARY_PATCH_SHA256,
                    "sourceCommit": app.RUST_COMMIT, "inputTree": {"sha256": "1" * 64, "fileCount": 1},
                    "patchedTree": {"sha256": "2" * 64, "fileCount": 1},
                    "patchedFiles": [{"path": "compiler/" + relative, "beforeSha256": "3" * 64,
                                      "afterSha256": "4" * 64}
                                     for relative, _ in compiler_patch_hunks(compiler_boundary_patch())]}
        runtime_root = "Z:/foreign-producer/runtime"
        artifacts = [{"root": "runtime", "path": "lib/" + names[role],
                      "sha256": support.sha256(originals[role]), "size": originals[role].stat().st_size}
                     for role in ("driver", "backend", "std")]
        compiler = {"schemaVersion": 2, "status": "built", "nativeHost": host,
                    "rustVersion": app.RUST_VERSION, "rustCommit": app.RUST_COMMIT,
                    "runtimeSysroot": runtime_root, "compilerSysroot": "Z:/foreign-producer/private",
                    "compilerBoundary": copy.deepcopy(boundary), "compilerArtifacts": artifacts}
        adapter = {"schemaVersion": 1, "nativeHost": host, "rustVersion": app.RUST_VERSION,
                   "rustCommit": app.RUST_COMMIT, "compilerBoundary": copy.deepcopy(boundary),
                   "adapter": {"path": "Z:/foreign-producer/adapter/" + names["adapter"],
                               "sha256": support.sha256(originals["adapter"])},
                   "compilerBuild": {"path": "Z:/foreign-producer/compiler-build.json",
                                     "compilerBoundary": copy.deepcopy(boundary)},
                   "compilerLibraries": [{"name": names[role], "path": runtime_root + "/lib/" + names[role],
                                          "sha256": support.sha256(originals[role])}
                                         for role in ("driver", "backend", "std")]}
        assets = root / "assets/miri"
        assets.mkdir(parents=True)
        guest_asset = assets / "guest.bin"
        guest_asset.write_bytes(b"MIR std")
        guest_row = {"path": f"sysroot/lib/rustlib/{app.GUEST_TARGET}/lib/libstd-test.rlib",
                     "asset": guest_asset.name, "size": guest_asset.stat().st_size,
                     "sha256": support.sha256(guest_asset)}
        files = [guest_row]
        if platform == "ohos":
            backend_asset = assets / "backend.bin"
            backend_asset.write_bytes(originals["backend"].read_bytes())
            files.append({"path": f"sysroot/lib/rustlib/{host}/codegen-backends/{names['backend']}",
                          "asset": backend_asset.name, "size": backend_asset.stat().st_size,
                          "sha256": support.sha256(backend_asset)})
        info = root / "build-info"
        support.write_json(info / "miri-sysroot.json", {"schemaVersion": 2, "encodedMir": True,
                           "rustVersion": app.RUST_VERSION, "rustCommit": app.RUST_COMMIT,
                           "guestTarget": app.GUEST_TARGET, "files": [guest_row]})
        support.write_json(info / "ci-build.json", {"schemaVersion": 1, "status": "packaged",
                           "nativeHost": host, "rustVersion": app.RUST_VERSION, "rustCommit": app.RUST_COMMIT,
                           "runId": "42", "runAttempt": "1", "sourceCommit": "a" * 40,
                           "nativeLibraries": len(rows), "guestAndLicenseFiles": len(files)})
        manifest = {"schemaVersion": schema, "nativeHost": host, "rustVersion": app.RUST_VERSION,
                    "rustCommit": app.RUST_COMMIT, "guestTarget": app.GUEST_TARGET,
                    "compilerBoundary": copy.deepcopy(boundary), "nativeLibraries": rows, "files": files}
        if schema == 2:
            manifest.update(platform=platform, architecture="arm64", libraryName=rows[0]["path"])
        for name in ("qfli_miri.h", "qfli_debug.h"):
            (root / "native/include").mkdir(parents=True, exist_ok=True)
            (source / "native/miri_adapter").mkdir(parents=True, exist_ok=True)
            (root / "native/include" / name).write_text("fixture header\n")
            (source / "native/miri_adapter" / name).write_text("fixture header\n")
        fixture = SimpleNamespace(root=root, source=source, platform=platform, key=key, native=native,
                                  compiler=compiler, adapter=adapter, manifest=manifest, paths=paths,
                                  selection={"runId": "42", "runAttempt": "1", "sourceCommit": "a" * 40})
        self.bind_runtime_records(fixture)
        return fixture

    def write_runtime_manifest(self, fixture):
        assets = fixture.root / "assets/miri"
        support.write_json(assets / f"manifest.{fixture.key}.json", fixture.manifest)
        if fixture.platform == "ohos":
            support.write_json(assets / "manifest.json", fixture.manifest)
        else:
            support.write_json(fixture.native / "native-package.json", fixture.manifest)

    def bind_runtime_records(self, fixture):
        info = fixture.root / "build-info"
        support.write_json(info / "compiler-build.json", fixture.compiler)
        fixture.adapter.setdefault("compilerBuild", {})["sha256"] = support.sha256(info / "compiler-build.json")
        support.write_json(info / "adapter-build.json", fixture.adapter)
        if fixture.platform == "ohos":
            fixture.manifest.update(compilerBuildSha256=support.sha256(info / "compiler-build.json"),
                                    adapterBuildSha256=support.sha256(info / "adapter-build.json"))
        else:
            fixture.manifest.update(compilerBuild=copy.deepcopy(fixture.adapter["compilerBuild"]),
                                    adapterBuild={"sha256": support.sha256(info / "adapter-build.json")})
        self.write_runtime_manifest(fixture)

    def test_realistic_schema_payloads_accept_foreign_producer_paths_without_resolving(self):
        for platform in ("ohos", "android", "ios"):
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                fixture = self.runtime_fixture(root / "payload", root / "app", platform)
                with patch.object(app, "ROOT", fixture.source), patch.object(Path, "resolve", side_effect=AssertionError("producer paths must stay lexical")):
                    data = app.verify_runtime_payload(fixture.root, fixture.key, fixture.selection)
                self.assertEqual(data["schemaVersion"], 1 if platform == "ohos" else 2)

    def test_android_runtime_payload_rejects_unselected_abi_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = self.runtime_fixture(root / "payload", root / "app", "android")
            extra = fixture.root / "android/app/src/main/jniLibs/armeabi-v7a/libunexpected.so"
            extra.parent.mkdir(parents=True)
            extra.write_bytes(b"unselected ABI payload")
            with patch.object(app, "ROOT", fixture.source), self.assertRaisesRegex(RuntimeError, "outside the verified selected payload"):
                app.verify_runtime_payload(fixture.root, fixture.key, fixture.selection)

    def test_native_bytes_and_manifest_mutation_cannot_replace_producer_records(self):
        for platform in ("ohos", "android"):
            for role in ("adapter", "driver", "backend"):
                with self.subTest(platform=platform, role=role), tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    fixture = self.runtime_fixture(root / "payload", root / "app", platform)
                    path = fixture.paths[role]
                    path.write_bytes(b"mutated-native-bytes")
                    row = next(row for row in fixture.manifest["nativeLibraries"] if row["name"] == path.name)
                    row["sha256"] = support.sha256(path)
                    if platform == "android":
                        row.update(size=path.stat().st_size, sourceSha256=row["sha256"])
                        (fixture.root / "android/app/src/main/jniLibs/arm64-v8a" / path.name).write_bytes(path.read_bytes())
                    self.write_runtime_manifest(fixture)
                    with patch.object(app, "ROOT", fixture.source), self.assertRaisesRegex(RuntimeError, "producer bytes"):
                        app.verify_runtime_payload(fixture.root, fixture.key, fixture.selection)

    def test_missing_producer_inventories_fail_even_when_outer_record_hashes_are_rebound(self):
        mutations = (lambda fixture: fixture.adapter.pop("adapter"),
                     lambda fixture: fixture.adapter.pop("compilerLibraries"),
                     lambda fixture: fixture.compiler.pop("compilerArtifacts"),
                     lambda fixture: fixture.compiler.update(compilerArtifacts=[]),
                     lambda fixture: fixture.adapter["compilerLibraries"].pop())
        for index, mutate in enumerate(mutations):
            with self.subTest(mutation=index), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                fixture = self.runtime_fixture(root / "payload", root / "app")
                mutate(fixture)
                self.bind_runtime_records(fixture)
                with patch.object(app, "ROOT", fixture.source), self.assertRaises(RuntimeError):
                    app.verify_runtime_payload(fixture.root, fixture.key, fixture.selection)

    def test_compiler_inventory_and_adapter_inventory_must_agree(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = self.runtime_fixture(root / "payload", root / "app")
            fixture.compiler["compilerArtifacts"][0]["sha256"] = "f" * 64
            self.bind_runtime_records(fixture)
            with patch.object(app, "ROOT", fixture.source), self.assertRaisesRegex(RuntimeError, "inventories disagree"):
                app.verify_runtime_payload(fixture.root, fixture.key, fixture.selection)

    def test_strict_patched_file_inventory_is_required(self):
        for mutation in ("missing", "truncated", "malformed_hash"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                fixture = self.runtime_fixture(root / "payload", root / "app")
                boundary = copy.deepcopy(fixture.manifest["compilerBoundary"])
                if mutation == "missing":
                    boundary.pop("patchedFiles")
                elif mutation == "truncated":
                    boundary["patchedFiles"] = boundary["patchedFiles"][:-1]
                else:
                    boundary["patchedFiles"][0]["afterSha256"] = "invalid"
                for record in (fixture.manifest, fixture.compiler, fixture.adapter, fixture.adapter["compilerBuild"]):
                    record["compilerBoundary"] = copy.deepcopy(boundary)
                self.bind_runtime_records(fixture)
                with patch.object(app, "ROOT", fixture.source), self.assertRaises(ValueError):
                    app.verify_runtime_payload(fixture.root, fixture.key, fixture.selection)

    def test_apple_source_hash_and_transformed_final_hash_are_separate_gates(self):
        for mutation in ("source_hash", "final_bytes"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                fixture = self.runtime_fixture(root / "payload", root / "app", "ios")
                row = fixture.manifest["nativeLibraries"][0]
                self.assertNotEqual(row["sourceSha256"], row["sha256"])
                if mutation == "source_hash":
                    row["sourceSha256"] = "f" * 64
                    self.write_runtime_manifest(fixture)
                else:
                    fixture.paths["adapter"].write_bytes(b"swapped-transformed-framework")
                with patch.object(app, "ROOT", fixture.source), self.assertRaises(RuntimeError):
                    app.verify_runtime_payload(fixture.root, fixture.key, fixture.selection)

    def test_checksum_written_after_manifest_update(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            support.write_json(root / "manifest.json", {"status": "incomplete"})
            app.write_checksums(root)
            first = (root / "SHA256SUMS").read_bytes()
            support.write_json(root / "manifest.json", {"status": "failed"})
            app.write_checksums(root)
            final = (root / "SHA256SUMS").read_text(encoding="utf-8")
            self.assertNotEqual(first, final.encode("utf-8"))
            self.assertEqual(final, f"{support.sha256(root / 'manifest.json')}  manifest.json\n")

    def test_failed_job_removes_verified_packages_and_keeps_truthful_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            (output / "packages").mkdir()
            (output / "packages/stale.apk").write_bytes(b"stale")
            (output / ".verified-packages").mkdir()
            (output / ".verified-packages/partial.apk").write_bytes(b"partial")
            support.write_json(output / "reports/packages.json", {"packages": []})
            manifest = {"completedStages": [], "packages": [{"file": "stale.apk"}], "core": {"commit": None},
                        "source": {"commit": "a" * 40}, "packageStatus": "verified",
                        "packageCoverage": {"complete": False, "blockers": [app.ARMV7_BLOCKER]}}
            args = argparse.Namespace(output=output, platform="android", arch="arm64-x64", job_status="failure")
            with patch.object(app, "step_summary"):
                app.finalize(args, manifest)
            self.assertEqual(manifest["status"], "failed")
            self.assertEqual(manifest["packageStatus"], "failed")
            self.assertEqual(manifest["packages"], [])
            self.assertIs(manifest["deviceReady"], False)
            self.assertEqual(manifest["deviceTests"], "not_run")
            self.assertFalse((output / "packages").exists())
            self.assertFalse((output / ".verified-packages").exists())
            self.assertFalse(manifest["packageCoverage"]["complete"])
            self.assertTrue(manifest["packageCoverage"]["blockers"])
            self.assertFalse((output / "reports/packages.json").exists())
            self.assertTrue((output / "SHA256SUMS").is_file())

    def test_verified_desktop_finalization_checks_bytes_and_preserves_device_limits(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            package = output / "packages" / support.PACKAGE_NAMES["linux", "x64"][0]
            package.parent.mkdir()
            package.write_bytes(b"verified-package-placeholder")
            row = {"file": package.name, "format": "deb", "sha256": support.sha256(package),
                   "size": package.stat().st_size, "validation": ["apt-install", "apt-remove"],
                   "installVerified": True, "deviceReady": False, "signing": support.SIGNING["linux"]}
            support.write_json(output / "reports/packages.json", {"schemaVersion": 1, "platform": "linux",
                               "arch": "x64", "packages": [row], "deviceTests": "not_run",
                               "applicationUiVerified": False})
            manifest = {"completedStages": ["init", "preflight", "verify-core", "setup-flutter", "build", "package"],
                        "packageStatus": "verified", "core": {"commit": "b" * 40}, "source": {"commit": "a" * 40}}
            args = argparse.Namespace(output=output, platform="linux", arch="x64", job_status="success")
            with patch.object(app, "step_summary"):
                app.finalize(args, manifest)
            self.assertEqual(manifest["status"], "success")
            self.assertIs(manifest["deviceReady"], False)
            self.assertEqual(manifest["deviceTests"], "not_run")
            self.assertFalse(manifest["applicationUiVerified"])
            self.assertTrue(package.is_file())
            self.assertIn(support.sha256(output / "manifest.json"), (output / "SHA256SUMS").read_text())

    def finalization_fixture(self, output):
        platform, arch = "android", "arm64-x64"
        rows = []
        (output / "packages").mkdir()
        for name in support.PACKAGE_NAMES[platform, arch]:
            package = output / "packages" / name
            package.write_bytes(b"verified-package-placeholder")
            rows.append({"file": name, "format": "apk", "sha256": support.sha256(package),
                         "size": package.stat().st_size, "validation": ["apksigner-verify"],
                         "installVerified": False, "deviceReady": False, "signing": support.SIGNING[platform]})
        (output / ".verified-packages").mkdir()
        (output / ".verified-packages/partial.apk").write_bytes(b"partial")
        support.write_json(output / "reports/packages.json", {"schemaVersion": 1, "platform": platform,
                           "arch": arch, "packages": rows, "deviceTests": "not_run", "applicationUiVerified": False})
        manifest = {"status": "incomplete", "completedStages": ["init", "preflight", "verify-core", "setup-flutter",
                    "resolve-runtime", "install-runtime", "build", "package"], "packageStatus": "verified",
                    "core": {"commit": "b" * 40}, "source": {"commit": "a" * 40},
                    "signing": support.SIGNING[platform], "blockers": [app.ARMV7_BLOCKER],
                    "packageCoverage": {"complete": False, "blockers": [app.ARMV7_BLOCKER]},
                    "nativeRuntime": {"status": "verified", "sourceCommit": "c" * 40}}
        support.write_json(output / "manifest.json", manifest)
        app.write_checksums(output)
        return argparse.Namespace(output=output, platform=platform, arch=arch, job_status="success"), manifest

    def test_final_checksum_failure_removes_valid_packages_and_stale_success(self):
        for recovery_writable in (True, False):
            with self.subTest(recovery_writable=recovery_writable), tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary)
                args, manifest = self.finalization_fixture(output)
                evidence = {key: copy.deepcopy(manifest[key])
                            for key in ("signing", "blockers", "packageCoverage", "nativeRuntime", "completedStages")}

                def fail_checksums(directory):
                    self.assertEqual(directory, output)
                    self.assertEqual(support.read_json(output / "manifest.json")["status"], "success")
                    self.assertEqual(len(app.validate_packages(args)), 2)
                    (directory / "SHA256SUMS").write_bytes(b"partial-success-checksums\n")
                    raise OSError("simulated final checksum publication failure")

                def write_manifest(path, value):
                    if path == output / "manifest.json" and value["status"] == "failed" and not recovery_writable:
                        raise OSError("simulated failed-status persistence failure")
                    support.write_json(path, value)

                with patch.object(app, "write_checksums", side_effect=fail_checksums) as checksums, \
                        patch.object(app, "write_json", side_effect=write_manifest), \
                        patch.object(support, "annotate"), patch.object(app, "step_summary") as summary:
                    with self.assertRaisesRegex(OSError, "final checksum publication failure"):
                        app.finalize(args, manifest)
                checksums.assert_called_once_with(output)
                summary.assert_not_called()
                self.assertEqual(manifest["status"], "failed")
                self.assertEqual(manifest["stage"], "finalize")
                self.assertEqual(manifest["packageStatus"], "failed")
                self.assertEqual(manifest["packages"], [])
                self.assertIs(manifest["deviceReady"], False)
                self.assertEqual(manifest["deviceTests"], "not_run")
                self.assertIs(manifest["applicationUiVerified"], False)
                for name in ("packages", ".verified-packages", "reports/packages.json", "SHA256SUMS"):
                    self.assertFalse((output / name).exists(), name)
                for key, value in evidence.items():
                    self.assertEqual(manifest[key], value, key)
                signing = (output / "SIGNING.txt").read_text(encoding="utf-8")
                self.assertIn(support.SIGNING["android"], signing)
                self.assertIn(app.ARMV7_BLOCKER, signing)
                self.assertIn("final checksum publication failure",
                              (output / "reports/finalize-failure.txt").read_text(encoding="utf-8"))
                if recovery_writable:
                    self.assertEqual(support.read_json(output / "manifest.json"), manifest)
                else:
                    self.assertFalse((output / "manifest.json").exists())

    def test_final_manifest_or_signing_publication_failure_invalidates_packages(self):
        for publication in ("manifest", "signing"):
            with self.subTest(publication=publication), tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary)
                args, manifest = self.finalization_fixture(output)
                original_write_text = Path.write_text

                def write_manifest(path, value):
                    if publication == "manifest" and path == output / "manifest.json" and value["status"] == "success":
                        raise OSError("simulated manifest publication failure")
                    support.write_json(path, value)

                def write_text(path, *arguments, **keywords):
                    if publication == "signing" and path == output / "SIGNING.txt":
                        raise OSError("simulated signing publication failure")
                    return original_write_text(path, *arguments, **keywords)

                with patch.object(app, "write_json", side_effect=write_manifest), \
                        patch.object(Path, "write_text", autospec=True, side_effect=write_text), \
                        patch.object(support, "annotate"), patch.object(app, "step_summary") as summary:
                    with self.assertRaisesRegex(OSError, publication + " publication failure"):
                        app.finalize(args, manifest)
                summary.assert_not_called()
                self.assertEqual(support.read_json(output / "manifest.json")["status"], "failed")
                self.assertEqual(manifest["packageStatus"], "failed")
                self.assertEqual(manifest["packages"], [])
                self.assertFalse(manifest["packageCoverage"]["complete"])
                self.assertEqual(manifest["signing"], support.SIGNING["android"])
                for name in ("packages", ".verified-packages", "reports/packages.json", "SHA256SUMS"):
                    self.assertFalse((output / name).exists(), name)
                self.assertIn(publication + " publication failure",
                              (output / "reports/finalize-failure.txt").read_text(encoding="utf-8"))

    def test_ohos_build_uses_typed_no_sign_config_and_restores_both_files(self):
        for fails in (False, True):
            with self.subTest(fails=fails), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                profile = {"app": {"signingConfigs": [], "products": [{"name": "default", "targetSdkVersion": "24"}]},
                           "modules": [{"name": "entry"}]}
                config = {"modelVersion": "5.1.0", "properties": {"otherFlag": True}}
                profile_path = root / "ohos/build-profile.json5"
                config_path = root / "ohos/hvigor/hvigor-config.json5"
                support.write_json(profile_path, profile)
                support.write_json(config_path, config)
                originals = {path: path.read_bytes() for path in (profile_path, config_path)}
                args = argparse.Namespace(platform="ohos", arch="arm64", flutter_root=root / "flutter")
                def release(arguments, manifest):
                    self.assertIs(support.read_json(config_path)["properties"]["enableSignTask"], False)
                    self.assertIs(support.read_json(config_path)["properties"]["otherFlag"], True)
                    self.assertEqual(support.read_json(profile_path)["app"]["signingConfigs"], [])
                    command = list(map(str, app.release_command(arguments, {})))
                    self.assertIn("hap", command)
                    self.assertIn("--no-codesign", command)
                    self.assertIn("ohos-arm64", command)
                    if fails:
                        raise RuntimeError("simulated compiler failure")
                with patch.object(app, "ROOT", root), patch.object(app, "git_value", return_value=""), \
                        patch.object(app, "require_hosted_runner"), patch.object(app, "build_release", side_effect=release), \
                        patch.dict(sys.modules, {"json5": SimpleNamespace(loads=json.loads)}):
                    if fails:
                        with self.assertRaisesRegex(RuntimeError, "simulated"):
                            app.build(args, {})
                    else:
                        app.build(args, {})
                for path, original in originals.items():
                    self.assertEqual(path.read_bytes(), original)

    def test_selected_flutter_output_archive_contains_real_bytes_not_caches(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / "build/linux/x64/release/bundle"
            (bundle / "lib").mkdir(parents=True)
            (bundle / "qfli_rust").write_bytes(b"flutter-executable")
            (bundle / "lib/libapp.so").write_bytes(b"aot-snapshot")
            cache = root / ".dart_tool/cache"
            cache.parent.mkdir(parents=True)
            cache.write_bytes(b"must-not-retain")
            archive = root / "inputs.tar.gz"
            args = argparse.Namespace(platform="linux", arch="x64")
            with patch.object(app, "ROOT", root):
                selection = app.archive_packaging_inputs(app.packaging_inputs(args), archive)
            self.assertGreater(selection["uncompressedBytes"], 0)
            self.assertEqual(selection["archiveSha256"], support.sha256(archive))
            with tarfile.open(archive) as package:
                names = package.getnames()
                self.assertFalse(any(".dart_tool" in name for name in names))
                self.assertEqual(package.extractfile("payload/build/linux/x64/release/bundle/qfli_rust").read(),
                                 b"flutter-executable")
            rows = {row["path"]: row for row in selection["files"]}
            self.assertEqual(rows["build/linux/x64/release/bundle/lib/libapp.so"]["sha256"],
                             support.sha256(bundle / "lib/libapp.so"))

    def test_selected_flutter_outputs_fail_on_size_bound(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            apk = root / "build/app.apk"
            apk.parent.mkdir()
            apk.write_bytes(b"too-large")
            with patch.object(app, "ROOT", root), patch.object(app, "MAX_INTERMEDIATE_BYTES", 1):
                with self.assertRaisesRegex(RuntimeError, "bound"):
                    app.archive_packaging_inputs([apk], root / "inputs.tar.gz")

    def test_owner_sdk_recipe_is_exact_and_does_not_apply_old_tooling_override(self):
        self.assertEqual(app.FLUTTER_TAG, "3.41.10-ohos-1.0.1")
        self.assertEqual(app.FLUTTER_COMMIT, "adaf911c35c9136a7d18fc424d714c9ec7724e60")
        self.assertEqual(app.FLUTTER_REPOSITORY, "https://gitcode.com/openharmony-tpc/flutter_flutter.git")
        self.assertIn(app.FLUTTER_COMMIT, app.SDK_CONTRACT)
        self.assertFalse(hasattr(app, "TOOLING_COMMIT"))

    def test_ohos_identity_is_source_specific(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            support.write_json(root / "ohos/AppScope/app.json5", {"app": {"bundleName": "com.azurekiln.qfli.rust"}})
            with patch.object(app, "ROOT", root):
                self.assertEqual(app.application_id("ohos"), "com.azurekiln.qfli.rust")
                self.assertEqual(app.application_id("android"), support.APP_ID)


if __name__ == "__main__":
    unittest.main()
