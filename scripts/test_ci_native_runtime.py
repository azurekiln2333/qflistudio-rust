"""Exercise archive integrity and portable artifact layout without a compiler build."""

import json
import io
import functools
import http.server
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest import mock

from ci_native_runtime import (
    Runner, archive_tree, collect_package, prepare_adapter_cache, unpack_guest, workflow_matrix,
)
from miri_build_support import HOSTS, RUST_COMMIT, sha256


class NativeArtifactsTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_guest_archive_roundtrip_and_checksum_rejection(self):
        source = self.root / "guest"
        source.mkdir()
        (source / "miri-sysroot.json").write_text('{"encodedMir":true}', encoding="utf-8")
        archive = self.root / "guest.tar.gz"
        archive_tree(source, archive, "sysroot")
        guest = unpack_guest(archive, self.root / "unpacked")
        self.assertEqual((guest / "miri-sysroot.json").read_bytes(),
                         (source / "miri-sysroot.json").read_bytes())
        archive.write_bytes(archive.read_bytes() + b"changed")
        with self.assertRaisesRegex(ValueError, "checksum"):
            unpack_guest(archive, self.root / "rejected")

    def test_empty_guest_checksum_is_a_validation_error(self):
        archive = self.root / "guest.tar.gz"
        archive.write_bytes(b"not a tar archive")
        archive.with_suffix(".gz.sha256").write_text("", encoding="ascii")
        with self.assertRaisesRegex(ValueError, "checksum"):
            unpack_guest(archive, self.root / "rejected")

    def test_guest_archive_cannot_escape_extraction_directory(self):
        archive = self.root / "guest.tar.gz"
        with tarfile.open(archive, "w:gz") as bundle:
            entry = tarfile.TarInfo("../escaped")
            entry.size = 3
            bundle.addfile(entry, io.BytesIO(b"bad"))
        archive.with_suffix(".gz.sha256").write_text(
            f"{sha256(archive)}  {archive.name}\n", encoding="ascii")
        with self.assertRaises(tarfile.FilterError):
            unpack_guest(archive, self.root / "unpacked")
        self.assertFalse((self.root / "escaped").exists())

    def fixture(self, host="x86_64-unknown-linux-gnu"):
        package = self.root / "package"
        platform, architecture = HOSTS[host]
        key = f"{platform}-{architecture}"
        abi = "arm64-v8a" if architecture == "arm64" else "x86_64"
        relative = (Path("ohos/entry/libs") / abi if platform == "ohos"
                    else Path("native/build/runtime") / (host if platform == "ios" else key))
        native = package / relative
        native.mkdir(parents=True)
        library = native / "libqfli_miri.so"
        library.write_bytes(b"verified native fixture")
        if platform == "android":
            installed = package / "android/app/src/main/jniLibs" / abi
            installed.mkdir(parents=True)
            (installed / library.name).write_bytes(library.read_bytes())
        assets = package / "assets/miri"
        assets.mkdir(parents=True)
        asset = assets / "selected.bin"
        asset.write_bytes(b"MIR fixture")
        (assets / "unreferenced.bin").write_bytes(b"old file")
        manifest = {
            "nativeHost": host, "rustCommit": RUST_COMMIT,
            "nativeLibraries": [{"path": library.name, "size": library.stat().st_size,
                                  "sha256": sha256(library)}],
            "files": [{"asset": asset.name, "size": asset.stat().st_size, "sha256": sha256(asset)}],
        }
        if platform == "ohos":
            manifest["schemaVersion"] = 1
            manifest["nativeLibraries"] = [{"name": library.name, "sha256": sha256(library)}]
        (assets / f"manifest.{key}.json").write_text(json.dumps(manifest), encoding="utf-8")
        (native / "native-package.json").write_text(json.dumps(manifest), encoding="utf-8")
        record = self.root / "compiler.json"
        record.write_bytes(b'{"producerPath":"/original/runner/path"}\n')
        return package, asset, library, record

    def test_package_archive_preserves_layout_and_record_bytes(self):
        package, _, _, record = self.fixture()
        archive = collect_package(package, "x86_64-unknown-linux-gnu",
                                  {"compiler-build.json": record}, self.root / "output", "commit123")
        with tarfile.open(archive) as bundle:
            names = bundle.getnames()
            self.assertIn("native/build/runtime/linux-x64/libqfli_miri.so", names)
            self.assertIn("assets/miri/selected.bin", names)
            self.assertNotIn("assets/miri/unreferenced.bin", names)
            self.assertEqual(bundle.extractfile("build-info/compiler-build.json").read(), record.read_bytes())
            info = json.load(bundle.extractfile("build-info/ci-build.json"))
            self.assertEqual(info["sourceCommit"], "commit123")
            self.assertFalse(info["runtimeExecuted"])
            self.assertFalse(info["deviceExecuted"])

    def test_changed_asset_cannot_create_success_archive(self):
        package, asset, _, record = self.fixture()
        asset.write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "asset changed"):
            collect_package(package, "x86_64-unknown-linux-gnu",
                            {"compiler-build.json": record}, self.root / "output", "commit123")
        self.assertFalse(list((self.root / "output").glob("*.tar.gz")))

    def test_changed_native_library_cannot_create_success_archive(self):
        package, _, library, record = self.fixture()
        library.write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "library changed"):
            collect_package(package, "x86_64-unknown-linux-gnu",
                            {"compiler-build.json": record}, self.root / "output", "commit123")
        self.assertFalse(list((self.root / "output").glob("*.tar.gz")))

    def test_mobile_layouts_restore_platform_packaging_inputs(self):
        for host, native_path, manifest in [
            ("aarch64-linux-android", "android/app/src/main/jniLibs/arm64-v8a/libqfli_miri.so",
             "assets/miri/manifest.android-arm64.json"),
            ("aarch64-apple-ios", "native/build/runtime/aarch64-apple-ios/libqfli_miri.so",
             "assets/miri/manifest.ios-arm64.json"),
            ("aarch64-unknown-linux-ohos", "ohos/entry/libs/arm64-v8a/libqfli_miri.so",
             "assets/miri/manifest.json"),
        ]:
            with self.subTest(host=host), tempfile.TemporaryDirectory() as temporary:
                self.root = Path(temporary)
                package, _, _, record = self.fixture(host)
                archive = collect_package(package, host, {"compiler-build.json": record},
                                          self.root / "output", "commit123")
                with tarfile.open(archive) as bundle:
                    self.assertIn(native_path, bundle.getnames())
                    self.assertIn(manifest, bundle.getnames())

    def test_default_matrix_is_mobile_and_macos_is_opt_in(self):
        default = workflow_matrix()["include"]
        self.assertEqual({row["package"] for row in default},
                         {"android-arm64", "android-x64", "ohos-arm64", "ohos-x64", "ios-arm64"})
        self.assertEqual(len(workflow_matrix(True)["include"]), 6)
        mac = workflow_matrix(True)["include"][-1]
        self.assertEqual(mac["package"], "macos-x64")
        self.assertEqual(mac["os"], "macos-15-intel")
        ios = next(row for row in default if row["package"] == "ios-arm64")
        self.assertEqual(ios["build_host"], "x86_64-apple-darwin")
        self.assertEqual(ios["host"], "aarch64-apple-ios")

    def test_cross_build_installs_build_host_toolchain_and_target_std(self):
        runner = Runner(self.root / "work", self.root / "output")
        compiler = self.root / "toolchain/bin/rustc"
        with mock.patch.object(runner, "run") as run, \
                mock.patch("ci_native_runtime.subprocess.run", return_value=SimpleNamespace(stdout=str(compiler))), \
                mock.patch("ci_native_runtime.compiler_identity", return_value={"host": "x86_64-apple-darwin"}):
            runner.toolchain("x86_64-apple-darwin", target="aarch64-apple-ios")
        install = run.call_args_list[0].args[1]
        self.assertIn("1.98.1-x86_64-apple-darwin", install)
        self.assertNotIn("rustc-dev", install)
        self.assertEqual(run.call_args_list[1].args[1],
                         ["rustup", "target", "add", "--toolchain", "1.98.1-x86_64-apple-darwin", "aarch64-apple-ios"])

    def test_adapter_prefetch_covers_host_dependencies_for_offline_metadata(self):
        # A local sparse registry reproduces measureme's Linux-only dependency.
        # No network registry, target SDK, compiler download or compilation runs.
        rustup = shutil.which("rustup")
        if not rustup:
            self.skipTest("An installed Cargo toolchain is required")
        located = subprocess.run([rustup, "which", "cargo"], capture_output=True, text=True)
        if located.returncode:
            self.skipTest("An installed Cargo toolchain is required")
        cargo = Path(located.stdout.strip())
        toolchain = cargo.parent.parent
        rustc = cargo.with_name("rustc.exe" if os.name == "nt" else "rustc")
        registry = self.root / "registry"
        registry.mkdir()

        class QuietHandler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *_):
                pass

        handler = functools.partial(QuietHandler, directory=str(registry))
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        endpoint = f"http://127.0.0.1:{server.server_address[1]}"
        (registry / "config.json").write_text(json.dumps({"dl": endpoint + "/crates"}), encoding="utf-8")
        for name in ("qfli-fixture-host", "qfli-fixture-target"):
            archive = registry / "crates" / name / "1.0.0/download"
            archive.parent.mkdir(parents=True)
            with tarfile.open(archive, "w:gz") as bundle:
                for path, content in {
                    "Cargo.toml": f'[package]\nname = "{name}"\nversion = "1.0.0"\nedition = "2021"\n',
                    "src/lib.rs": "pub fn fixture() {}\n",
                }.items():
                    entry = tarfile.TarInfo(f"{name}-1.0.0/{path}")
                    data = content.encode()
                    entry.size = len(data)
                    bundle.addfile(entry, io.BytesIO(data))
            index = registry / name[:2] / name[2:4] / name
            index.parent.mkdir(parents=True, exist_ok=True)
            index.write_text(json.dumps({"name": name, "vers": "1.0.0", "deps": [],
                                         "cksum": sha256(archive), "features": {}, "yanked": False}) + "\n",
                             encoding="utf-8")
        project = self.root / "project"
        config = project / ".cargo/config.toml"
        config.parent.mkdir(parents=True)
        config.write_text('[source.crates-io]\nreplace-with = "fixture"\n[source.fixture]\n'
                          f'registry = "sparse+{endpoint}/"\n', encoding="utf-8")
        adapter = project / "native/miri_adapter"
        miri = project / "native/miri"
        for directory, name in ((adapter, "qfli_miri"), (miri, "miri")):
            (directory / "src").mkdir(parents=True)
            (directory / "src/lib.rs").write_text("", encoding="utf-8")
            (directory / "Cargo.toml").write_text(
                f'[package]\nname = "{name}"\nversion = "0.1.0"\nedition = "2021"\n', encoding="utf-8")
        with (adapter / "Cargo.toml").open("a", encoding="utf-8") as stream:
            stream.write('[dependencies]\nmiri = { path = "../miri" }\n')
        with (miri / "Cargo.toml").open("a", encoding="utf-8") as stream:
            stream.write('[target.\'cfg(target_os = "linux")\'.dependencies]\nqfli-fixture-host = "1.0.0"\n'
                         '[target.\'cfg(target_os = "android")\'.dependencies]\nqfli-fixture-target = "1.0.0"\n')
        runner = Runner(self.root / "work", self.root / "output")
        runner.env["RUSTC"] = str(rustc)

        def run(command):
            return subprocess.run([str(item) for item in command], cwd=project, env=runner.env,
                                  capture_output=True, text=True, timeout=30)

        generated = run([cargo, "generate-lockfile", "--manifest-path", adapter / "Cargo.toml"])
        self.assertEqual(generated.returncode, 0, generated.stderr)
        mobile = run([cargo, "fetch", "--locked", "--manifest-path", adapter / "Cargo.toml",
                      "--target", "x86_64-linux-android"])
        self.assertEqual(mobile.returncode, 0, mobile.stderr)
        metadata = [cargo, "metadata", "--locked", "--offline", "--format-version=1",
                    "--manifest-path", adapter / "Cargo.toml", "--filter-platform", "x86_64-unknown-linux-gnu"]
        missing = run(metadata)
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn("qfli-fixture-host", missing.stderr)
        with mock.patch("ci_native_runtime.ROOT", project):
            prepare_adapter_cache(runner, toolchain, miri)
        covered = run(metadata)
        self.assertEqual(covered.returncode, 0, covered.stderr)


if __name__ == "__main__":
    unittest.main()
