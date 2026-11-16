"""Check SDK archive selection and path preservation without SDK downloads."""

import io
import json
import os
from pathlib import Path
import stat
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import ci_ohos_sdk as sdk


class OhosSdkTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def component(self, entries):
        path = self.root / "component.zip"
        with zipfile.ZipFile(path, "w") as bundle:
            for name, content, mode in entries:
                entry = zipfile.ZipInfo(name)
                entry.create_system = 3
                entry.external_attr = mode << 16
                bundle.writestr(entry, content)
        return path

    def test_selects_only_linux_native_component(self):
        archive = self.root / "sdk.tar.gz"
        with tarfile.open(archive, "w:gz") as bundle:
            for name, data in (("windows/native-windows.zip", b"windows"),
                               ("linux/ets-linux.zip", b"ets"),
                               ("linux/native-linux-x64-6.1.0.zip", b"native")):
                entry = tarfile.TarInfo(name)
                entry.size = len(data)
                bundle.addfile(entry, io.BytesIO(data))
        output = self.root / "native.zip"
        sdk.native_component(archive, output)
        self.assertEqual(output.read_bytes(), b"native")

    def test_component_escape_rejected_before_file_writes(self):
        component = self.component([("native/ok", b"good", stat.S_IFREG | 0o644),
                                    ("native/../../outside", b"bad", stat.S_IFREG | 0o644)])
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            sdk.unpack_native(component, self.root / "unpacked")
        self.assertEqual(list((self.root / "unpacked").iterdir()), [])
        self.assertFalse((self.root / "outside").exists())

    @unittest.skipIf(os.name == "nt", "Linux SDK links require a Linux runner")
    def test_llvm_executable_modes_and_internal_links_survive(self):
        component = self.component([("native/llvm/bin/clang-15", b"clang", stat.S_IFREG | 0o755),
                                    ("native/llvm/bin/clang", b"clang-15", stat.S_IFLNK | 0o777)])
        root = self.root / "unpacked"
        sdk.unpack_native(component, root)
        self.assertTrue((root / "native/llvm/bin/clang").is_symlink())
        self.assertEqual((root / "native/llvm/bin/clang").read_bytes(), b"clang")
        self.assertTrue(os.access(root / "native/llvm/bin/clang", os.X_OK))

    def test_external_link_rejected(self):
        component = self.component([("native/escape", b"../../outside", stat.S_IFLNK | 0o777)])
        with self.assertRaisesRegex(ValueError, "escapes"):
            sdk.unpack_native(component, self.root / "unpacked")

    def test_download_checksum_mismatch_cannot_be_published(self):
        destination = self.root / "sdk.tar.gz"
        with patch.object(sdk.urllib.request, "urlopen", side_effect=lambda *a, **kw: io.BytesIO(b"bad")):
            with self.assertRaisesRegex(ValueError, "checksum differs"):
                sdk.download_archive(destination)
        self.assertFalse(destination.exists())

    def test_real_resource_layout_is_discovered(self):
        native = self.root / "sdk/native"
        native.mkdir(parents=True)
        (native / "oh-uni-package.json").write_text(json.dumps({"version": "6.1.0", "apiVersion": 23}))
        for name in ("clang", "clang++", "llvm-ar", "llvm-ranlib", "llvm-readobj", "llvm-readelf", "ld.lld"):
            path = native / "llvm/bin" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"fixture")
            path.chmod(0o755)
        for target in sdk.TARGETS:
            for path in (native / "sysroot/usr/lib" / target / "libc.so",
                         native / "llvm/lib/clang/18/lib" / target / "libclang_rt.builtins.a"):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"fixture")
        record = sdk.inspect_sdk(self.root / "sdk")
        self.assertEqual(record["resourceDir"], str(native / "llvm/lib/clang/18"))
        self.assertEqual(record["nativeSdk"], str(native))
        self.assertEqual(record["apiVersion"], 23)

    def test_install_refuses_existing_directory_without_download(self):
        with patch.object(sdk, "download_archive") as download:
            with self.assertRaisesRegex(ValueError, "fresh"):
                sdk.install_sdk(self.root)
        download.assert_not_called()


if __name__ == "__main__":
    unittest.main()
