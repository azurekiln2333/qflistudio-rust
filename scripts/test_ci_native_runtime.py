"""Exercise archive integrity and portable artifact layout without a compiler build."""

import json
import io
from pathlib import Path
import tarfile
import tempfile
import unittest

from ci_native_runtime import archive_tree, collect_package, unpack_guest
from miri_build_support import RUST_COMMIT, sha256


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

    def fixture(self):
        package = self.root / "package"
        native = package / "native/build/runtime/linux-x64"
        native.mkdir(parents=True)
        library = native / "libqfli_miri.so"
        library.write_bytes(b"verified native fixture")
        assets = package / "assets/miri"
        assets.mkdir(parents=True)
        asset = assets / "selected.bin"
        asset.write_bytes(b"MIR fixture")
        (assets / "unreferenced.bin").write_bytes(b"old file")
        manifest = {
            "nativeHost": "x86_64-unknown-linux-gnu", "rustCommit": RUST_COMMIT,
            "nativeLibraries": [{"path": library.name, "size": library.stat().st_size,
                                  "sha256": sha256(library)}],
            "files": [{"asset": asset.name, "size": asset.stat().st_size, "sha256": sha256(asset)}],
        }
        (assets / "manifest.linux-x64.json").write_text(json.dumps(manifest), encoding="utf-8")
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


if __name__ == "__main__":
    unittest.main()
