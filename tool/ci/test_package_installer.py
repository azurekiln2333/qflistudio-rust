"""Hermetic packaging regressions. Execute only in the GitHub check jobs.

External platform tools are mocked here. Real hosted installer checks remain
mandatory and are not replaced by these tests.
"""

import hashlib
import io
import json
import os
from pathlib import Path
import plistlib
import stat
import tempfile
import unittest
from unittest import mock
import zipfile

import package_installer as packaging
from ci_support import APP_ID, PACKAGE_NAMES, SIGNING, read_json, sha256, write_json
from miri_build_support import GUEST_TARGET, RUST_COMMIT, RUST_VERSION


HOSTED = {"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted"}


def setUpModule():
    # unittest discovery does not execute the __main__ block.
    packaging.require_hosted_runner()


class PackagingFixtures(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.output = self.root / "build/app-artifacts/app-installer-ios-arm64"
        self.output.mkdir(parents=True)
        self.environment = mock.patch.dict(os.environ, {**HOSTED, "RUNNER_TEMP": str(self.root)})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def initialize(self, platform="ios", arch="arm64"):
        manifest = {"schemaVersion": 1, "platform": platform, "arch": arch,
                    "status": "incomplete", "completedStages": ["init", "build"],
                    "source": {"commit": "app-commit", "runId": "123"},
                    "core": {"commit": "core-commit"}}
        write_json(self.output / "manifest.json", manifest)
        return manifest

    def runtime(self, platform="ohos", arch="arm64"):
        host = {("ohos", "arm64"): "aarch64-unknown-linux-ohos",
                ("ios", "arm64"): "aarch64-apple-ios",
                ("android", "arm64"): "aarch64-linux-android",
                ("android", "x64"): "x86_64-linux-android"}[(platform, arch)]
        asset = b"MIR fixture"
        digest = hashlib.sha256(asset).hexdigest()
        libraries = [("libqfli_miri.so", b"adapter"), ("librustc_driver.so", b"driver"),
                     ("librustc_codegen_cranelift.so", b"backend")]
        if platform == "ios":
            libraries = [("qfli_miri.framework/qfli_miri", b"adapter"),
                         ("qfli_rustc_driver.framework/qfli_rustc_driver", b"driver"),
                         ("qfli_codegen_cranelift.framework/qfli_codegen_cranelift", b"backend")]
        manifest = {"schemaVersion": 1 if platform == "ohos" else 2,
                    "nativeHost": host, "rustVersion": RUST_VERSION, "rustCommit": RUST_COMMIT,
                    "guestTarget": GUEST_TARGET, "id": "runtime-fixture",
                    "nativeLibraries": [], "files": [
                        {"asset": digest + ".bin", "size": len(asset), "sha256": digest}]}
        if platform != "ohos":
            manifest.update(platform=platform, architecture=arch)
        for name, data in libraries:
            row = {"name" if platform == "ohos" else "path": name,
                   "sha256": hashlib.sha256(data).hexdigest()}
            if platform != "ohos":
                row["size"] = len(data)
            manifest["nativeLibraries"].append(row)
        path = self.root / "assets/miri" / f"manifest.{platform}-{arch}.json"
        write_json(path, manifest)
        assets = {"assets/miri/" + path.name: path.read_bytes(),
                  "assets/miri/" + digest + ".bin": asset}
        if platform == "ohos":
            legacy = path.with_name("manifest.json")
            legacy.write_bytes(path.read_bytes())
            assets["assets/miri/manifest.json"] = legacy.read_bytes()
        return manifest, assets, dict(libraries)

    def zip_bytes(self, entries):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as bundle:
            for name, data in entries.items():
                bundle.writestr(name, data)
        stream.seek(0)
        return stream


class PathAndArchiveTests(PackagingFixtures):
    def test_local_and_self_hosted_execution_are_rejected(self):
        for environment in ({}, {"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "self-hosted"},
                            {"GITHUB_ACTIONS": "false", "RUNNER_ENVIRONMENT": "github-hosted"}):
            with self.subTest(environment=environment), mock.patch.dict(os.environ, environment, clear=True):
                with self.assertRaisesRegex(RuntimeError, "GitHub-hosted"):
                    packaging.require_hosted_runner()

    def test_noncanonical_paths_are_rejected(self):
        for value in ("", "../escape", "/absolute", "C:/drive", "a\\b", "a//b", "./a", "a/../b", "a\nb", None):
            with self.subTest(value=value):
                with self.assertRaises(RuntimeError):
                    packaging.safe_relative(value)
        self.assertEqual(str(packaging.safe_relative("Payload/Runner.app/Info.plist")),
                         "Payload/Runner.app/Info.plist")

    def test_archive_rejects_traversal_and_case_collisions(self):
        for entries in ({"../escape": b"x"}, {"File": b"one", "file": b"two"}):
            with zipfile.ZipFile(self.zip_bytes(entries)) as bundle:
                with self.assertRaises(RuntimeError):
                    packaging.archive_index(bundle)

    def test_archive_rejects_symbolic_links(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as bundle:
            entry = zipfile.ZipInfo("Payload/Runner.app/link")
            entry.create_system = 3
            entry.external_attr = (stat.S_IFLNK | 0o777) << 16
            bundle.writestr(entry, "../../outside")
        stream.seek(0)
        with zipfile.ZipFile(stream) as bundle:
            with self.assertRaisesRegex(RuntimeError, "links"):
                packaging.archive_index(bundle)

    def test_mobile_zip_is_stable_across_source_mtime_and_creation_order(self):
        source = self.root / "app"
        source.mkdir()
        (source / "z").write_bytes(b"last")
        (source / "a").write_bytes(b"first")
        first, second = self.root / "first.ipa", self.root / "second.ipa"
        packaging.zip_tree(source, first, "Payload/Runner.app")
        os.utime(source / "a", (100000, 100000))
        packaging.zip_tree(source, second, "Payload/Runner.app")
        self.assertEqual(first.read_bytes(), second.read_bytes())
        with zipfile.ZipFile(first) as bundle:
            self.assertEqual(bundle.namelist(), ["Payload/Runner.app/a", "Payload/Runner.app/z"])
            self.assertTrue(all(row.date_time == (1980, 1, 1, 0, 0, 0) for row in bundle.infolist()))

    def test_artifact_checksum_inventory_covers_all_regular_files(self):
        (self.output / "packages").mkdir()
        (self.output / "packages/file.ipa").write_bytes(b"package")
        (self.output / "SIGNING.txt").write_bytes(b"unsigned")
        packaging.write_checksums(self.output)
        expected = (f"{sha256(self.output / 'SIGNING.txt')}  SIGNING.txt\n"
                    f"{sha256(self.output / 'packages/file.ipa')}  packages/file.ipa\n")
        self.assertEqual((self.output / "SHA256SUMS").read_text(), expected)
        packaging.write_checksums(self.output)
        self.assertEqual((self.output / "SHA256SUMS").read_text(), expected)

    def test_relative_bundle_symlink_is_preserved_or_explicitly_unsupported_by_host(self):
        source = self.root / "bundle"
        source.mkdir()
        (source / "real").write_bytes(b"payload")
        try:
            (source / "link").symlink_to("real")
        except OSError:
            self.skipTest("The hosted user lacks symlink privileges")
        copied = self.root / "copied"
        expected = packaging.copy_bundle(source, copied)
        self.assertEqual(expected["link"], {"link": "real"})
        self.assertTrue((copied / "link").is_symlink())
        (source / "link").unlink()
        (source / "link").symlink_to("../outside")
        (self.root / "outside").write_bytes(b"outside")
        with self.assertRaisesRegex(RuntimeError, "escapes"):
            packaging.tree_entries(source)


class RuntimeArchiveTests(PackagingFixtures):
    def test_ohos_schema1_does_not_require_schema2_fields(self):
        manifest, assets, libraries = self.runtime()
        self.assertNotIn("platform", manifest)
        self.assertNotIn("architecture", manifest)
        entries = {"resources/rawfile/flutter_assets/" + name: data for name, data in assets.items()}
        entries.update({"libs/arm64-v8a/" + name: data for name, data in libraries.items()})
        with zipfile.ZipFile(self.zip_bytes(entries)) as bundle:
            result = packaging.verify_runtime_members(bundle, packaging.archive_index(bundle), self.root,
                     "ohos", "arm64", "resources/rawfile/flutter_assets/", "libs/arm64-v8a/")
        self.assertEqual(set(result), set(libraries))

    def test_tampered_ohos_library_fails_even_when_manifest_is_present(self):
        _, assets, libraries = self.runtime()
        entries = {"resources/rawfile/flutter_assets/" + name: data for name, data in assets.items()}
        entries.update({"libs/arm64-v8a/" + name: data for name, data in libraries.items()})
        entries["libs/arm64-v8a/libqfli_miri.so"] = b"tampered"
        with zipfile.ZipFile(self.zip_bytes(entries)) as bundle:
            with self.assertRaisesRegex(RuntimeError, "native library differs"):
                packaging.verify_runtime_members(bundle, packaging.archive_index(bundle), self.root,
                     "ohos", "arm64", "resources/rawfile/flutter_assets/", "libs/arm64-v8a/")

    def test_stale_guest_asset_fails(self):
        _, assets, libraries = self.runtime("android")
        entries = {"assets/flutter_assets/" + name: data for name, data in assets.items()}
        entries.update({"lib/arm64-v8a/" + name: data for name, data in libraries.items()})
        asset = next(name for name in entries if name.endswith(".bin"))
        entries[asset] = b"bad MIR"
        with zipfile.ZipFile(self.zip_bytes(entries)) as bundle:
            with self.assertRaisesRegex(RuntimeError, "runtime asset differs"):
                packaging.verify_runtime_members(bundle, packaging.archive_index(bundle), self.root,
                     "android", "arm64", "assets/flutter_assets/", "lib/arm64-v8a/")

    def test_wrong_ohos_native_host_is_not_inferred_from_filename(self):
        manifest, _, _ = self.runtime()
        manifest["nativeHost"] = "x86_64-unknown-linux-ohos"
        write_json(self.root / "assets/miri/manifest.ohos-arm64.json", manifest)
        with self.assertRaisesRegex(RuntimeError, "nativeHost"):
            packaging.runtime_manifest(self.root, "ohos", "arm64")

    def test_missing_runtime_backend_is_rejected(self):
        manifest, _, _ = self.runtime()
        manifest["nativeLibraries"] = manifest["nativeLibraries"][:2]
        write_json(self.root / "assets/miri/manifest.ohos-arm64.json", manifest)
        with self.assertRaisesRegex(RuntimeError, "codegen backend"):
            packaging.runtime_manifest(self.root, "ohos", "arm64")

    def test_armv7_is_an_explicit_blocker(self):
        with self.assertRaisesRegex(RuntimeError, "armeabi-v7a"):
            packaging.runtime_manifest(self.root, "android", "armv7")
        with self.assertRaisesRegex(RuntimeError, "three-ABI"):
            packaging.package_android(self.root, self.root, self.output, "all")

    def test_hap_uses_real_source_bundle_identity_not_generic_app_id(self):
        manifest, assets, libraries = self.runtime()
        bundle_id = "com.azurekiln.qfli.rust"
        self.assertNotEqual(bundle_id, APP_ID)
        write_json(self.root / "ohos/AppScope/app.json5", {"app": {"bundleName": bundle_id}})
        folder = self.root / "ohos/entry/build/default/outputs/default"
        folder.mkdir(parents=True)
        entries = {"resources/rawfile/flutter_assets/" + name: data for name, data in assets.items()}
        entries.update({"libs/arm64-v8a/" + name: data for name, data in libraries.items()})
        entries.update({"libs/arm64-v8a/libflutter.so": b"engine", "libs/arm64-v8a/libapp.so": b"snapshot",
                        "module.json": json.dumps({"app": {"bundleName": bundle_id}, "module": {"type": "entry"}}).encode()})
        (folder / "entry-default-unsigned.hap").write_bytes(self.zip_bytes(entries).getvalue())
        stage = self.root / "stage"
        stage.mkdir()
        rows = packaging.package_ohos(self.root, stage, self.output, "arm64")
        self.assertEqual(rows[0][2]["bundleIdentifier"], bundle_id)
        self.assertFalse(rows[0][2]["signatureVerified"])
        self.assertFalse(rows[0][2]["installVerified"])
        self.assertEqual(manifest["schemaVersion"], 1)

    def test_ios_records_transformed_final_native_hashes_but_still_checks_guest(self):
        _, assets, libraries = self.runtime("ios")
        prefix = "Payload/Runner.app/Frameworks/"
        entries = {prefix + "App.framework/flutter_assets/" + name: data for name, data in assets.items()}
        entries.update({prefix + name: data + b"ad-hoc-signature-change" for name, data in libraries.items()})
        with zipfile.ZipFile(self.zip_bytes(entries)) as bundle:
            result = packaging.verify_runtime_members(bundle, packaging.archive_index(bundle), self.root,
                     "ios", "arm64", prefix + "App.framework/flutter_assets/", prefix,
                     transformed_native=True)
        self.assertEqual(result["qfli_miri.framework/qfli_miri"],
                         hashlib.sha256(b"adapterad-hoc-signature-change").hexdigest())

    def test_android_rejects_extra_abi_before_external_tools(self):
        apk = self.root / "bad.apk"
        apk.write_bytes(self.zip_bytes({"lib/arm64-v8a/libapp.so": b"arm64",
                                       "lib/x86_64/libapp.so": b"x64"}).getvalue())
        with mock.patch.object(packaging, "run") as command:
            with self.assertRaisesRegex(RuntimeError, "ABI set"):
                packaging.verify_android(apk, self.root, "arm64", self.output)
        command.assert_not_called()


class DesktopContractTests(PackagingFixtures):
    def bundle(self, platform):
        folder = (self.root / "build/linux/x64/release/bundle" if platform == "linux"
                  else self.root / "build/windows/x64/runner/Release")
        files = (["qfli_rust", "lib/libflutter_linux_gtk.so", "data/icudtl.dat"]
                 if platform == "linux" else ["qfli_rust.exe", "flutter_windows.dll", "data/icudtl.dat"])
        for relative in files:
            path = folder / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"fixture")
        (folder / "data/flutter_assets").mkdir()
        return folder

    def test_desktop_bundle_requires_engine_and_assets(self):
        for platform in ("linux", "windows"):
            folder = self.bundle(platform)
            self.assertEqual(packaging.desktop_bundle(self.root, platform, "x64"), folder)
            (folder / "data/icudtl.dat").unlink()
            with self.assertRaisesRegex(RuntimeError, "icudtl"):
                packaging.desktop_bundle(self.root, platform, "x64")

    def test_windows_rejects_non_pe_before_inno_or_installer(self):
        self.bundle("windows")
        with mock.patch.object(packaging, "run") as command:
            with self.assertRaisesRegex(RuntimeError, "not PE"):
                packaging.package_windows(self.root, self.root, self.output, "x64")
        command.assert_not_called()

    def test_windows_wait_uses_start_process_wait_without_launching_app(self):
        with mock.patch.object(packaging, "run", return_value="") as command:
            packaging.windows_wait(["C:/path with space/setup.exe", "/DIR=C:/path with space/app", "/VERYSILENT"],
                                   self.output / "installer.log")
        arguments = command.call_args.args[0]
        self.assertEqual(arguments[:4], ["pwsh", "-NoProfile", "-NonInteractive", "-Command"])
        self.assertIn("Start-Process", arguments[4])
        self.assertIn("-Wait -PassThru", arguments[4])
        self.assertIn("setup.exe", arguments[4])

    def test_macos_verifies_architecture_signature_and_ad_hoc_state(self):
        app = self.root / "Test.app"
        (app / "Contents/MacOS").mkdir(parents=True)
        (app / "Contents/MacOS/qfli_rust").write_bytes(b"fixture")
        (app / "Contents/Info.plist").write_bytes(plistlib.dumps(
            {"CFBundleIdentifier": APP_ID, "CFBundleExecutable": "qfli_rust"}))
        with mock.patch.object(packaging, "run", side_effect=["", "", "Signature=adhoc\n"]) as command:
            packaging.verify_macos(app, "arm64", self.output, "fixture")
        calls = [call.args[0] for call in command.call_args_list]
        self.assertEqual(calls[0][:4], ["xcrun", "lipo", "-verify_arch", "arm64"])
        self.assertEqual(calls[1][:4], ["codesign", "--verify", "--deep", "--strict"])
        with mock.patch.object(packaging, "run", side_effect=["", "", "Authority=Developer ID"]):
            with self.assertRaisesRegex(RuntimeError, "ad hoc"):
                packaging.verify_macos(app, "x64", self.output, "fixture")

    def test_apple_info_rejects_another_bundle_id(self):
        app = self.root / "Test.app"
        app.mkdir()
        (app / "Info.plist").write_bytes(plistlib.dumps(
            {"CFBundleIdentifier": "other.app", "CFBundleExecutable": "Runner"}))
        with self.assertRaisesRegex(RuntimeError, "identifier"):
            packaging.app_info(app, "ios")


class PublicationTests(PackagingFixtures):
    def fake_packager(self, root, stage, reports, arch):
        path = stage / PACKAGE_NAMES[("ios", arch)][0]
        path.write_bytes(b"verified IPA fixture")
        return [(path, "ipa", {"validation": ["fixture-only"], "installVerified": False})]

    def test_success_is_stage_success_not_overall_or_device_success(self):
        original = self.initialize()
        with mock.patch.object(packaging.sys, "platform", "darwin"), \
                mock.patch.dict(packaging.PACKAGERS, {"ios": self.fake_packager}):
            rows = packaging.package_target("ios", "arm64", self.output, root=self.root)
        result = read_json(self.output / "manifest.json")
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["packageStatus"], "verified")
        self.assertEqual(result["source"], original["source"])
        self.assertEqual(result["core"], original["core"])
        self.assertFalse(result["deviceReady"])
        self.assertFalse(result["applicationUiVerified"])
        self.assertEqual(result["deviceTests"], "not_run")
        self.assertEqual(result["signing"], SIGNING["ios"])
        self.assertEqual(result["packages"], rows)
        self.assertIn("package", result["completedStages"])
        report = read_json(self.output / "reports/packages.json")
        self.assertEqual(report["packages"], rows)
        sums = (self.output / "SHA256SUMS").read_text()
        self.assertIn("manifest.json", sums)
        self.assertIn("reports/packages.json", sums)
        self.assertIn("SIGNING.txt", sums)
        self.assertIn("packages/" + rows[0]["file"], sums)
        self.assertIn("Unsigned IPA", (self.output / "SIGNING.txt").read_text())
        self.assertEqual(list(self.root.glob("qfli-package-*")), [])

    def test_second_package_failure_removes_stale_published_outputs(self):
        self.initialize("android", "arm64-x64")
        stale = self.output / "packages/stale.apk"
        stale.parent.mkdir()
        stale.write_bytes(b"old success")
        write_json(self.output / "reports/packages.json", {"packages": ["old"]})

        def fail_after_first(root, stage, reports, arch):
            (stage / PACKAGE_NAMES[("android", arch)][0]).write_bytes(b"partial")
            raise RuntimeError("second ABI verification failed")

        with mock.patch.object(packaging.sys, "platform", "linux"), \
                mock.patch.dict(packaging.PACKAGERS, {"android": fail_after_first}):
            with self.assertRaisesRegex(RuntimeError, "second ABI"):
                packaging.package_target("android", "arm64-x64", self.output, root=self.root)
        self.assertFalse((self.output / "packages").exists())
        self.assertFalse((self.output / "reports/packages.json").exists())
        result = read_json(self.output / "manifest.json")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["packages"], [])
        self.assertFalse(result["packageCoverage"]["complete"])
        self.assertIn("three-ABI", result["packageCoverage"]["blockers"][0])
        self.assertIn("second ABI", (self.output / "reports/package-failure.txt").read_text())
        self.assertNotIn("packages/", (self.output / "SHA256SUMS").read_text())
        self.assertEqual(list(self.root.glob("qfli-package-*")), [])

    def test_failure_after_promotion_removes_packages_and_report(self):
        self.initialize()
        with mock.patch.object(packaging.sys, "platform", "darwin"), \
                mock.patch.dict(packaging.PACKAGERS, {"ios": self.fake_packager}), \
                mock.patch.object(packaging, "write_checksums", side_effect=[RuntimeError("checksum write failed"), None]):
            with self.assertRaisesRegex(RuntimeError, "checksum write failed"):
                packaging.package_target("ios", "arm64", self.output, root=self.root)
        self.assertFalse((self.output / "packages").exists())
        self.assertFalse((self.output / "reports/packages.json").exists())
        self.assertEqual(read_json(self.output / "manifest.json")["packages"], [])

    def test_missing_validation_evidence_never_promotes(self):
        self.initialize()

        def missing(root, stage, reports, arch):
            path = stage / PACKAGE_NAMES[("ios", arch)][0]
            path.write_bytes(b"unchecked fixture")
            return [(path, "ipa", {"installVerified": False})]

        with mock.patch.object(packaging.sys, "platform", "darwin"), \
                mock.patch.dict(packaging.PACKAGERS, {"ios": missing}):
            with self.assertRaisesRegex(RuntimeError, "verification evidence"):
                packaging.package_target("ios", "arm64", self.output, root=self.root)
        self.assertFalse((self.output / "packages").exists())

    def test_wrong_filename_never_promotes(self):
        self.initialize()

        def wrong(root, stage, reports, arch):
            path = stage / "wrong.ipa"
            path.write_bytes(b"bad name")
            return [(path, "ipa", {})]

        with mock.patch.object(packaging.sys, "platform", "darwin"), \
                mock.patch.dict(packaging.PACKAGERS, {"ios": wrong}):
            with self.assertRaisesRegex(RuntimeError, "filenames"):
                packaging.package_target("ios", "arm64", self.output, root=self.root)
        self.assertFalse((self.output / "packages").exists())

    def test_cancellation_cleans_packages(self):
        self.initialize()
        with mock.patch.object(packaging.sys, "platform", "darwin"), \
                mock.patch.dict(packaging.PACKAGERS, {"ios": mock.Mock(side_effect=KeyboardInterrupt)}):
            with self.assertRaises(KeyboardInterrupt):
                packaging.package_target("ios", "arm64", self.output, root=self.root)
        self.assertEqual(read_json(self.output / "manifest.json")["status"], "cancelled")
        self.assertFalse((self.output / "packages").exists())

    def test_failed_retry_removes_package_from_completed_stages(self):
        manifest = self.initialize()
        manifest["completedStages"].append("package")
        write_json(self.output / "manifest.json", manifest)
        with mock.patch.object(packaging.sys, "platform", "darwin"), \
                mock.patch.dict(packaging.PACKAGERS, {"ios": mock.Mock(side_effect=RuntimeError("retry failed"))}):
            with self.assertRaisesRegex(RuntimeError, "retry failed"):
                packaging.package_target("ios", "arm64", self.output, root=self.root)
        self.assertNotIn("package", read_json(self.output / "manifest.json")["completedStages"])

    def test_host_mismatch_fails_with_diagnostic_not_a_package(self):
        self.initialize()
        with mock.patch.object(packaging.sys, "platform", "linux"), \
                mock.patch.dict(packaging.PACKAGERS, {"ios": mock.Mock()}) as packagers:
            with self.assertRaisesRegex(RuntimeError, "darwin hosted runner"):
                packaging.package_target("ios", "arm64", self.output, root=self.root)
            packagers["ios"].assert_not_called()
        self.assertEqual(read_json(self.output / "manifest.json")["status"], "failed")

    def test_output_path_cannot_point_to_source(self):
        self.initialize()
        with self.assertRaisesRegex(RuntimeError, "target below"):
            packaging.package_target("ios", "arm64", self.root, root=self.root)
        self.assertTrue((self.output / "manifest.json").exists())

    def test_failed_manifest_requires_reinitialization(self):
        manifest = self.initialize()
        manifest["status"] = "failed"
        write_json(self.output / "manifest.json", manifest)
        with self.assertRaisesRegex(RuntimeError, "Reinitialize"):
            packaging.package_target("ios", "arm64", self.output, root=self.root)

    def test_signing_notes_never_claim_device_readiness(self):
        for platform in packaging.PACKAGERS:
            text = packaging.signing_note(platform)
            self.assertIn(SIGNING[platform], text)
            self.assertIn("Device ready: false", text)
        self.assertIn("not notarized", packaging.signing_note("macos"))
        self.assertIn("signing key", packaging.signing_note("ohos"))

    def test_publication_copy_failure_cleans_hidden_and_visible_outputs(self):
        self.initialize()
        with mock.patch.object(packaging.sys, "platform", "darwin"), \
                mock.patch.dict(packaging.PACKAGERS, {"ios": self.fake_packager}), \
                mock.patch.object(packaging.shutil, "copy2", side_effect=OSError("copy failed")):
            with self.assertRaisesRegex(OSError, "copy failed"):
                packaging.package_target("ios", "arm64", self.output, root=self.root)
        self.assertFalse((self.output / ".verified-packages").exists())
        self.assertFalse((self.output / "packages").exists())
        self.assertEqual(read_json(self.output / "manifest.json")["status"], "failed")

    def test_missing_runner_temp_fails_before_publishing(self):
        self.initialize()
        with mock.patch.object(packaging.sys, "platform", "darwin"), \
                mock.patch.dict(os.environ, {"RUNNER_TEMP": ""}):
            with self.assertRaisesRegex(RuntimeError, "GitHub-hosted"):
                packaging.package_target("ios", "arm64", self.output, root=self.root)
        self.assertFalse((self.output / "packages").exists())

    def test_missing_completed_build_stage_is_rejected(self):
        manifest = self.initialize()
        manifest["completedStages"] = ["init"]
        write_json(self.output / "manifest.json", manifest)
        with self.assertRaisesRegex(RuntimeError, "completed build stage"):
            packaging.package_target("ios", "arm64", self.output, root=self.root)
        self.assertFalse((self.output / "packages").exists())

    def test_windows_inno_source_does_not_launch_or_require_admin(self):
        source = Path(packaging.__file__).with_name("windows_installer.iss").read_text()
        self.assertIn("PrivilegesRequired=lowest", source)
        self.assertIn("x64compatible", source)
        self.assertNotIn("\n[Run]\n", source)


if __name__ == "__main__":
    packaging.require_hosted_runner()
    unittest.main()
