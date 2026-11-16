"""Verify the portable OHOS packager rejects invalid guest data before writes."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from miri_build_support import GUEST_TARGET, RUST_COMMIT, RUST_VERSION, sha256


PWSH = shutil.which("pwsh")
SCRIPT = Path(__file__).resolve().parent / "package_miri_ohos.ps1"


@unittest.skipUnless(PWSH, "PowerShell 7 is required")
class OhosGuestValidationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.guest = self.root / "guest"
        libs = self.guest / "lib/rustlib" / GUEST_TARGET / "lib"
        libs.mkdir(parents=True)
        self.files = []
        for name in ("libstd-fixture.rlib", "libcore-fixture.rlib"):
            path = libs / name
            path.write_bytes(b"inert MIR fixture")
            self.files.append(path)
        self.record = self.guest / "miri-sysroot.json"
        self.info = {"schemaVersion": 2, "rustVersion": RUST_VERSION,
                     "rustCommit": RUST_COMMIT, "guestTarget": GUEST_TARGET, "encodedMir": True,
                     "files": [{"path": "sysroot/" + path.relative_to(self.guest).as_posix(),
                                "sha256": sha256(path)} for path in self.files]}
        suffix = ".exe" if os.name == "nt" else ""
        for name in ("llvm-readobj", "llvm-readelf"):
            path = self.root / "sdk/native/llvm/bin" / (name + suffix)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"inert tool placeholder, must never execute")
        for name in ("adapter.so", "adapter.json", "dependencies.json"):
            (self.root / name).write_text("{}")
        self.output = self.root / "package"

    def run_package(self):
        self.record.write_text(json.dumps(self.info), encoding="utf-8")
        result = subprocess.run([PWSH, "-NoProfile", "-File", str(SCRIPT),
                                 "-AdapterLibrary", str(self.root / "adapter.so"),
                                 "-AdapterBuildInfo", str(self.root / "adapter.json"),
                                 "-CompilerLibDirectory", str(self.root),
                                 "-GuestSysroot", str(self.guest), "-SdkRoot", str(self.root / "sdk"),
                                 "-RustSource", str(self.root),
                                 "-DependencyMetadata", str(self.root / "dependencies.json"),
                                 "-ProjectRoot", str(self.output)], capture_output=True,
                                text=True, encoding="utf-8")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.output.exists())
        return result.stdout + result.stderr

    def test_changed_guest_stops_before_native_inspection(self):
        self.files[0].write_bytes(b"tampered MIR")
        self.assertIn("Guest standard library differs", self.run_package())

    def test_wrong_guest_revision_stops_before_native_inspection(self):
        self.info["rustCommit"] = "0" * 40
        self.assertIn("Guest MIR identity", self.run_package())

    def test_plain_standard_library_record_rejected(self):
        self.info["encodedMir"] = False
        self.assertIn("Guest MIR identity", self.run_package())

    def test_missing_core_stops_before_native_inspection(self):
        self.files[1].unlink()
        self.assertIn("Guest MIR standard-library data is incomplete", self.run_package())


if __name__ == "__main__":
    unittest.main()
