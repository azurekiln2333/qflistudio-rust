import contextlib
import io
import os
import sys
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


class NativeToolConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.build = self.root / "owned build"
        (self.build / "bin").mkdir(parents=True)
        self.local = {}
        for key, name in (("cc", "clang"), ("cxx", "clang++"), ("ar", "llvm-ar"),
                          ("ranlib", "llvm-ranlib"), ("ld_lld", "ld.lld")):
            path = self.root / "local tools" / name
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(b"fixture, not an executable")
            self.local[key] = path
        for method in ("run", "Popen"):
            guard = patch.object(bootstrap.subprocess, method,
                                 side_effect=AssertionError("No subprocess in configuration tests"))
            guard.start()
            self.addCleanup(guard.stop)

    def args(self, host, sdk=None, explicit=True):
        args = SimpleNamespace(native_host=host, build_root=self.build, toolchain=self.root,
                               jobs=2, ohos_sdk=sdk, ohos_resource_dir=None, linux_sysroot=None)
        for key, path in self.local.items():
            setattr(args, key, path if explicit else None)
        return args

    def sdk(self, host):
        sdk = self.root / ("sdk-" + host)
        target = host.replace("-unknown", "")
        libc = sdk / "sysroot/usr/lib" / target / "libc.so"
        libc.parent.mkdir(parents=True)
        libc.write_bytes(b"fixture libc")
        (sdk / "llvm/lib" / target).mkdir(parents=True)
        self.builtins(sdk, target, "15.0.4")
        for local in self.local.values():
            path = sdk / "llvm/bin" / local.name
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(b"fixture SDK tool")
        return sdk

    def builtins(self, sdk, target, version):
        resource = sdk / "llvm/lib/clang" / version
        builtin = resource / "lib" / target / "libclang_rt.builtins.a"
        builtin.parent.mkdir(parents=True)
        builtin.write_bytes(b"fixture builtins")
        return resource

    def config(self, args, tools):
        config = tomllib.loads(bootstrap.bootstrap_config(args, "x86_64-unknown-linux-gnu", tools))
        self.assertEqual(config["build"]["host"], [args.native_host])
        self.assertEqual(config["build"]["target"], [args.native_host])
        self.assertEqual(config["rust"]["codegen-backends"], ["cranelift"])
        self.assertFalse(config["rust"]["download-rustc"])
        self.assertFalse(config["llvm"]["download-ci-llvm"])
        self.assertEqual(Path(config["target"][args.native_host]["linker"]), tools["linker"])
        return config

    def test_cli_supports_both_linux_and_ohos_architectures(self):
        for host in ("x86_64-unknown-linux-gnu", "aarch64-unknown-linux-gnu",
                     "x86_64-unknown-linux-ohos", "aarch64-unknown-linux-ohos"):
            self.assertIn(host, bootstrap.BOOTSTRAP_HOSTS)

    def test_linux_native_config_uses_explicit_llvm_tools(self):
        args = self.args("x86_64-unknown-linux-gnu")
        tools = bootstrap.native_tools(args, "x86_64-unknown-linux-gnu")
        self.config(args, tools)
        wrapper = tools["linker"].read_text()
        self.assertIn("--target=x86_64-unknown-linux-gnu", wrapper)
        self.assertIn(str(self.local["ld_lld"].resolve()), wrapper)
        self.assertEqual(tools["ar"], self.local["ar"].resolve())

    def test_linux_aarch64_cross_config_binds_sysroot(self):
        args = self.args("aarch64-unknown-linux-gnu")
        args.linux_sysroot = self.root / "arm64 sysroot"
        (args.linux_sysroot / "usr/include").mkdir(parents=True)
        tools = bootstrap.native_tools(args, "x86_64-unknown-linux-gnu")
        self.config(args, tools)
        wrapper = tools["cc"].read_text()
        self.assertIn("--target=aarch64-unknown-linux-gnu", wrapper)
        self.assertIn("--sysroot=" + str(args.linux_sysroot.resolve()), wrapper)

    def test_linux_arm64_native_does_not_require_cross_sysroot(self):
        args = self.args("aarch64-unknown-linux-gnu")
        tools = bootstrap.native_tools(args, "aarch64-unknown-linux-gnu")
        self.assertEqual(tools["compilerTarget"], args.native_host)

    def test_linux_cross_config_requires_sysroot(self):
        with self.assertRaisesRegex(ValueError, "requires --linux-sysroot"):
            bootstrap.linux_tools(self.args("aarch64-unknown-linux-gnu"), "x86_64-unknown-linux-gnu")

    def test_linux_missing_headers_rejects_sysroot(self):
        args = self.args("aarch64-unknown-linux-gnu")
        args.linux_sysroot = self.root / "missing"
        with self.assertRaisesRegex(ValueError, "usr/include"):
            bootstrap.linux_tools(args, "x86_64-unknown-linux-gnu")

    def test_linux_missing_tools_has_no_path_fallback(self):
        args = self.args("x86_64-unknown-linux-gnu", explicit=False)
        with patch.object(bootstrap.shutil, "which", side_effect=AssertionError("No PATH fallback")):
            with self.assertRaisesRegex(ValueError, "Supply --cc"):
                bootstrap.linux_tools(args, "x86_64-unknown-linux-gnu")

    def test_ohos_both_architectures_use_matching_sdk_resources(self):
        for host in ("x86_64-unknown-linux-ohos", "aarch64-unknown-linux-ohos"):
            with self.subTest(host=host):
                sdk = self.sdk(host)
                args = self.args(host, sdk=sdk, explicit=False)
                tools = bootstrap.native_tools(args, "x86_64-unknown-linux-gnu")
                self.config(args, tools)
                text = tools["linker"].read_text()
                self.assertIn("--target=" + host.replace("-unknown", ""), text)
                self.assertIn("--sysroot=" + str((sdk / "sysroot").resolve()), text)
                self.assertIn("-resource-dir", text)
                self.assertIn("-D__MUSL__", text)
                self.assertIn("-Wl,-z,max-page-size=16384", text)
                self.assertEqual(tools["ar"], (sdk / "llvm/bin/llvm-ar").resolve())

    def test_ohos_requires_explicit_sdk(self):
        with self.assertRaisesRegex(ValueError, "require --ohos-sdk"):
            bootstrap.ohos_tools(self.args("x86_64-unknown-linux-ohos"), "x86_64-unknown-linux-gnu")

    def test_ohos_missing_target_libc_is_rejected(self):
        args = self.args("aarch64-unknown-linux-ohos", sdk=self.root / "missing sdk")
        with self.assertRaisesRegex(ValueError, "missing aarch64-linux-ohos/libc.so"):
            bootstrap.ohos_tools(args, "x86_64-unknown-linux-gnu")

    def test_ohos_missing_tool_has_no_system_fallback(self):
        host = "x86_64-unknown-linux-ohos"
        sdk = self.sdk(host)
        (sdk / "llvm/bin/clang").unlink()
        args = self.args(host, sdk=sdk, explicit=False)
        with patch.object(bootstrap.shutil, "which", side_effect=AssertionError("No PATH fallback")):
            with self.assertRaisesRegex(ValueError, "Missing executable"):
                bootstrap.ohos_tools(args, "x86_64-unknown-linux-gnu")

    def test_ohos_local_tool_overrides_support_sdk_with_foreign_executables(self):
        host = "x86_64-unknown-linux-ohos"
        sdk = self.sdk(host)
        (sdk / "llvm/bin/clang").unlink()
        args = self.args(host, sdk=sdk)
        tools = bootstrap.ohos_tools(args, "x86_64-unknown-linux-gnu")
        self.assertIn(str(self.local["cc"].resolve()), tools["cc"].read_text())
        self.assertEqual(tools["ar"], self.local["ar"].resolve())

    def test_ohos_ambiguous_resource_versions_require_explicit_selection(self):
        host = "x86_64-unknown-linux-ohos"
        sdk = self.sdk(host)
        selected = self.builtins(sdk, "x86_64-linux-ohos", "18.0.0")
        args = self.args(host, sdk=sdk)
        with self.assertRaisesRegex(ValueError, "Select --ohos-resource-dir"):
            bootstrap.ohos_tools(args, "x86_64-unknown-linux-gnu")
        args.ohos_resource_dir = selected
        self.assertEqual(bootstrap.ohos_tools(args, "x86_64-unknown-linux-gnu")["resourceDir"],
                         str(selected.resolve()))

    def test_ohos_resource_must_have_matching_target_builtins(self):
        host = "aarch64-unknown-linux-ohos"
        sdk = self.sdk(host)
        args = self.args(host, sdk=sdk)
        args.ohos_resource_dir = sdk / "llvm/lib/clang/missing"
        with self.assertRaisesRegex(ValueError, "lacks matching SDK builtins"):
            bootstrap.ohos_tools(args, "x86_64-unknown-linux-gnu")

    def test_linux_and_ohos_require_linux_build_host(self):
        for host, method in (("x86_64-unknown-linux-gnu", bootstrap.linux_tools),
                             ("x86_64-unknown-linux-ohos", bootstrap.ohos_tools)):
            with self.subTest(host=host):
                with self.assertRaisesRegex(ValueError, "requires a Linux GNU build host"):
                    method(self.args(host), "x86_64-pc-windows-gnu")

    def test_mobile_dispatch_is_preserved(self):
        for host, name in (("aarch64-linux-android", "android_tools"),
                           ("aarch64-apple-ios", "apple_tools")):
            with patch.object(bootstrap, name, return_value={"fixture": host}) as selected:
                args = self.args(host)
                self.assertEqual(bootstrap.native_tools(args, "fixture-host"), {"fixture": host})
                selected.assert_called_once_with(args, "fixture-host")


class BuildRootIsolationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.toolchain = self.root / "inputs/toolchain"
        self.source = self.root / "inputs/source"
        for path in (self.toolchain, self.source):
            path.mkdir(parents=True)
            (path / "preserved.txt").write_bytes(b"preserve input bytes")
        for method in ("run", "Popen"):
            guard = patch.object(bootstrap.subprocess, method,
                                 side_effect=AssertionError("No subprocess before path isolation"))
            guard.start()
            self.addCleanup(guard.stop)

    def snapshot(self):
        result = []
        for path in sorted(self.root.rglob("*")):
            name = path.relative_to(self.root).as_posix()
            if path.is_symlink():
                result.append((name, "link", str(path.readlink())))
            elif path.is_file():
                result.append((name, "file", path.read_bytes()))
            else:
                result.append((name, "directory", None))
        return result

    def assert_rejected_without_effects(self, build, selected=None):
        selected = selected or {}
        flags = {"toolchain": self.toolchain, "source": self.source, **selected}
        argv = ["build_rustc_host.py", "--native-host", "x86_64-unknown-linux-gnu",
                "--build-root", str(build), "--configure-only"]
        for key, value in flags.items():
            argv += ["--" + key.replace("_", "-"), str(value)]
        before = self.snapshot()
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(sys, "argv", argv))
            errors = stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
            identity = stack.enter_context(patch.object(bootstrap, "compiler_identity",
                                  side_effect=AssertionError("Compiler identity must not run")))
            native = stack.enter_context(patch.object(bootstrap, "native_tools",
                                  side_effect=AssertionError("Native tools must not write wrappers")))
            source = stack.enter_context(patch.object(bootstrap, "complete_source",
                                  side_effect=AssertionError("Source preparation must not start")))
            for method in ("mkdir", "write_text", "write_bytes", "rename", "replace"):
                stack.enter_context(patch.object(Path, method,
                                    side_effect=AssertionError("No filesystem mutations on overlap")))
            with self.assertRaises(SystemExit) as raised:
                bootstrap.main()
            self.assertEqual(raised.exception.code, 2)
            self.assertIn("--build-root overlaps", errors.getvalue())
            identity.assert_not_called()
            native.assert_not_called()
            source.assert_not_called()
        self.assertEqual(self.snapshot(), before)

    def test_main_rejects_all_directory_input_overlaps_in_both_directions(self):
        for key in ("toolchain", "source", "ndk", "ohos_sdk", "ohos_resource_dir", "linux_sysroot"):
            for direction in ("equal", "output-inside-input", "input-inside-output"):
                with self.subTest(key=key, direction=direction):
                    case = self.root / "cases" / key / direction
                    input_root = case / "input"
                    input_root.mkdir(parents=True)
                    (input_root / "preserved").write_bytes(b"input")
                    if direction == "equal":
                        build = input_root
                    elif direction == "output-inside-input":
                        build = input_root / "output"
                    else:
                        build = case
                    self.assert_rejected_without_effects(build, {key: input_root})

    def test_main_rejects_local_tool_parent_overlaps_in_both_directions(self):
        for key in ("cc", "cxx", "ar", "ranlib", "ld_lld"):
            for direction in ("equal", "output-inside-input", "input-inside-output"):
                with self.subTest(key=key, direction=direction):
                    case = self.root / "tools" / key / direction
                    parent = case / "installed"
                    parent.mkdir(parents=True)
                    tool = parent / "tool"
                    tool.write_bytes(b"preinstalled tool bytes")
                    if direction == "equal":
                        build = parent
                    elif direction == "output-inside-input":
                        build = parent / "output"
                    else:
                        build = case
                    self.assert_rejected_without_effects(build, {key: tool})

    def test_main_resolves_dotdot_before_overlap_check(self):
        child = self.toolchain / "child"
        child.mkdir()
        self.assert_rejected_without_effects(child / "..")

    @unittest.skipUnless(os.name == "nt", "Windows case semantics")
    def test_main_rejects_windows_case_alias(self):
        self.assert_rejected_without_effects(Path(str(self.toolchain).swapcase()))

    def test_main_resolves_directory_symlink_aliases_where_supported(self):
        alias = self.root / "toolchain-alias"
        try:
            alias.symlink_to(self.toolchain, target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"Directory symlink unavailable: {error}")
        self.assert_rejected_without_effects(alias)
        self.assert_rejected_without_effects(alias / "output")
        self.assert_rejected_without_effects(self.toolchain, {"toolchain": alias})
        ancestor = self.root / "ancestor"
        nested = ancestor / "sdk"
        nested.mkdir(parents=True)
        sdk_alias = self.root / "sdk-alias"
        sdk_alias.symlink_to(nested, target_is_directory=True)
        self.assert_rejected_without_effects(ancestor, {"ohos_sdk": sdk_alias})

    def test_main_protects_selected_parent_of_a_tool_file_symlink(self):
        installed = self.root / "installed-tools"
        installed.mkdir()
        real_tool = installed / "clang"
        real_tool.write_bytes(b"preinstalled tool")
        selected_parent = self.root / "selected-tools"
        selected_parent.mkdir()
        alias = selected_parent / "clang"
        try:
            alias.symlink_to(real_tool)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"File symlink unavailable: {error}")
        self.assert_rejected_without_effects(selected_parent / "output", {"cc": alias})
        self.assert_rejected_without_effects(installed / "output", {"cc": alias})

    def test_disjoint_sibling_build_reaches_identity_without_writing(self):
        argv = ["build_rustc_host.py", "--native-host", "x86_64-unknown-linux-gnu",
                "--build-root", str(self.root / "owned-output"),
                "--toolchain", str(self.toolchain), "--source", str(self.source)]
        before = self.snapshot()
        with patch.object(sys, "argv", argv), patch.object(bootstrap, "compiler_identity",
                side_effect=ValueError("identity sentinel reached")) as identity:
            with self.assertRaisesRegex(ValueError, "identity sentinel reached"):
                bootstrap.main()
            identity.assert_called_once_with(self.toolchain.resolve())
        self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
