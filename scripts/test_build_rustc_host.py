import io
from pathlib import Path
import tarfile
import tempfile
import tomllib
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import build_rustc_host as bootstrap


class BootstrapInputTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source_name = f"rustc-{bootstrap.RUST_VERSION}-src"
        archive = self.root / f"{self.source_name}.tar.xz"
        files = {
            name: b"fixture\n" for name in (
                "x.py", "Cargo.toml", "src/bootstrap/Cargo.toml", "library/Cargo.toml",
                "library/std/Cargo.toml", "library/backtrace/Cargo.toml",
                "compiler/rustc_driver/Cargo.toml", "compiler/rustc_codegen_cranelift/Cargo.toml",
            )
        }
        files["git-commit-hash"] = bootstrap.RUST_COMMIT.encode()
        with tarfile.open(archive, "w:xz") as bundle:
            for name, data in files.items():
                entry = tarfile.TarInfo(f"{self.source_name}/{name}")
                entry.size = len(data)
                bundle.addfile(entry, io.BytesIO(data))
        self.digest = bootstrap.sha256(archive)
        self.checksum = patch.object(bootstrap, "SOURCE_SHA256", self.digest)
        self.checksum.start()
        self.addCleanup(self.checksum.stop)
        self.args = SimpleNamespace(source=None, build_root=self.root, download_source=False)

    def test_recovers_interrupted_extraction_and_preserves_previous_input(self):
        previous = self.root / self.source_name
        previous.mkdir()
        (previous / "unfinished").write_text("retained")
        prepared = bootstrap.complete_source(self.args)
        self.assertTrue((prepared / "library/backtrace/Cargo.toml").is_file())
        self.assertEqual((prepared / ".qfli-source-sha256").read_text().strip(), self.digest)
        saved = list(self.root.glob(f"{self.source_name}.incomplete-*"))
        self.assertEqual(len(saved), 1)
        self.assertEqual((saved[0] / "unfinished").read_text(), "retained")

    def test_failed_extraction_does_not_publish_partial_source(self):
        def interrupted(bundle, destination, **kwargs):
            (Path(destination) / self.source_name).mkdir()
            raise OSError("interrupted extraction")
        with patch.object(tarfile.TarFile, "extractall", interrupted):
            with self.assertRaisesRegex(OSError, "interrupted extraction"):
                bootstrap.complete_source(self.args)
        self.assertFalse((self.root / self.source_name).exists())
        self.assertTrue(bootstrap.complete_source(self.args).is_dir())

    def test_verified_source_is_reused(self):
        prepared = bootstrap.complete_source(self.args)
        with patch.object(tarfile.TarFile, "extractall", side_effect=AssertionError("re-extracted")):
            self.assertEqual(bootstrap.complete_source(self.args), prepared)

    def test_rejects_missing_target_bootstrap_library(self):
        with self.assertRaisesRegex(ValueError, "x86_64-linux-android rust-std"):
            bootstrap.require_bootstrap_inputs(self.root, "x86_64-linux-android", "x86_64-unknown-linux-gnu")

    def test_rejects_precompiled_private_metadata_before_bootstrap(self):
        target = self.root / "lib/rustlib/x86_64-linux-android/lib"
        target.mkdir(parents=True)
        (target / "libcore-fixture.rlib").write_bytes(b"fixture")
        (target / "libstd-fixture.rlib").write_bytes(b"fixture")
        private = self.root / "lib/rustlib/x86_64-unknown-linux-gnu/lib"
        private.mkdir(parents=True)
        (private / "librustc_driver_impl-fixture.rmeta").write_bytes(b"fixture")
        with self.assertRaisesRegex(ValueError, "without rustc-dev"):
            bootstrap.require_bootstrap_inputs(self.root, "x86_64-linux-android", "x86_64-unknown-linux-gnu")

    def test_source_archive_compiler_keeps_guest_metadata_identity(self):
        args = SimpleNamespace(native_host="x86_64-linux-android", build_root=self.root,
                               toolchain=self.root, jobs=1)
        tools = {name: self.root / name for name in ("cc", "cxx", "linker", "ar", "ranlib")}
        config = tomllib.loads(bootstrap.bootstrap_config(args, "x86_64-unknown-linux-gnu", tools))
        self.assertEqual(config["build"]["description"], "")


if __name__ == "__main__":
    unittest.main()
