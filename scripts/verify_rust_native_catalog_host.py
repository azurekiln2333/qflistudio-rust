#!/usr/bin/env python3
"""Run every catalog main/answer through host ABI-1 Miri, never claiming OHOS acceptance."""

from __future__ import annotations

import argparse
import base64
import ctypes
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import signal
import subprocess
import sys
import tempfile
import time

from generate_rust_content import ContentError, ROOT, load_topics
from generate_rust_native_catalog import DESTINATION, verify_native_catalog, verify_paired_catalogs
from miri_build_support import GUEST_TARGET, RUST_COMMIT, RUST_VERSION, sha256

TOOLCHAIN = Path("/tmp/qfli-miri-cross-1.98.1/rustup/toolchains/1.98.1-x86_64-unknown-linux-gnu")
DEFAULT_LIBRARY = Path("/tmp/qfli-miri-adapter-1.98.1/target/x86_64-unknown-linux-gnu/debug/libqfli_miri.so")
DEFAULT_SYSROOT = Path("/tmp/qfli-miri-reference-1.98.1/sysroot")
DEFAULT_DRIVER = TOOLCHAIN / "lib/librustc_driver-eaf3ed1d23ca5027.so"


class QfliConfig(ctypes.Structure):
    _fields_ = [
        ("abi_version", ctypes.c_uint32),
        ("source_path", ctypes.c_char_p),
        ("sysroot_path", ctypes.c_char_p),
        ("stdin_data", ctypes.POINTER(ctypes.c_uint8)),
        ("stdin_len", ctypes.c_size_t),
        ("max_basic_blocks", ctypes.c_uint64),
        ("timeout_ms", ctypes.c_uint64),
        ("max_output_bytes", ctypes.c_size_t),
        ("max_guest_memory_bytes", ctypes.c_uint64),
    ]


class QfliResult(ctypes.Structure):
    _fields_ = [("state", ctypes.c_uint32), ("exit_code", ctypes.c_int32),
                ("basic_blocks", ctypes.c_uint64), ("peak_guest_memory_bytes", ctypes.c_uint64)]


def text_hash(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8", newline="\n")
    temporary.replace(path)


def safe_path(name: str) -> PurePosixPath:
    if (not isinstance(name, str) or not name or "\\" in name or ":" in name
            or any(ord(char) < 32 for char in name)
            or any(part in ("", ".", "..") for part in name.split("/"))):
        raise ContentError(f"Unsafe catalog file path: {name!r}")
    relative = PurePosixPath(name)
    if relative.is_absolute():
        raise ContentError(f"Absolute catalog file path: {name!r}")
    return relative


def materialize_case(case: dict, directory: Path) -> tuple[Path, dict]:
    """Write only into a fresh owned root; compile its main entry, never Cargo."""
    if text_hash(case["source"]) != case["sourceSha256"]:
        raise ContentError(f"Source digest mismatch: {case['id']}")
    entry = safe_path(case["entryFile"])
    files = case["files"] if case["files"] is not None else {case["entryFile"]: case["source"]}
    expected = case["filesSha256"] if case["files"] is not None else {case["entryFile"]: case["sourceSha256"]}
    if not isinstance(files, dict) or not isinstance(expected, dict) or set(files) != set(expected):
        raise ContentError(f"Bundle digest inventory mismatch: {case['id']}")
    if files.get(case["entryFile"]) != case["source"]:
        raise ContentError(f"Bundle entry differs from current source: {case['id']}")
    paths = {}
    for name, source in files.items():
        relative = safe_path(name)
        if not isinstance(source, str) or text_hash(source) != expected[name]:
            raise ContentError(f"Bundle file digest mismatch: {name}")
        folded = name.casefold()
        if folded in paths:
            raise ContentError(f"Conflicting bundle file case: {name}")
        paths[folded] = relative
    for name in paths:
        if any(parent.as_posix().casefold() in paths for parent in paths[name].parents
               if parent != PurePosixPath(".")):
            raise ContentError(f"Bundle file also used as directory: {name}")
    directory.mkdir(parents=True, exist_ok=False)
    actual = {}
    for name, source in sorted(files.items()):
        target = directory.joinpath(*safe_path(name).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(source.encode("utf-8"))
        actual[name] = sha256(target)
    return directory.joinpath(*entry.parts).resolve(), actual


def channel_record(data: bytes) -> dict:
    return {"text": data.decode("utf-8", "replace"), "base64": base64.b64encode(data).decode("ascii"),
            "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def run_native(job: dict) -> dict:
    case = job["case"]
    directory = Path(job["directory"]).resolve()
    source, files_hashes = materialize_case(case, directory)
    os.chdir(directory)
    library = ctypes.CDLL(job["library"])
    library.qfli_miri_abi_version.argtypes = []
    library.qfli_miri_abi_version.restype = ctypes.c_uint32
    abi = library.qfli_miri_abi_version()
    if abi != 1:
        raise ContentError(f"Adapter ABI is {abi}, expected 1")
    library.qfli_miri_create.argtypes = [ctypes.POINTER(QfliConfig)]
    library.qfli_miri_create.restype = ctypes.c_void_p
    library.qfli_miri_run.argtypes = [ctypes.c_void_p]
    library.qfli_miri_run.restype = ctypes.c_int32
    library.qfli_miri_result.argtypes = [ctypes.c_void_p, ctypes.POINTER(QfliResult)]
    library.qfli_miri_result.restype = ctypes.c_int32
    library.qfli_miri_copy_output.argtypes = [ctypes.c_void_p, ctypes.c_uint32,
                                           ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t]
    library.qfli_miri_copy_output.restype = ctypes.c_size_t
    library.qfli_miri_destroy.argtypes = [ctypes.c_void_p]
    library.qfli_miri_destroy.restype = None
    limits = job["limits"]
    config = QfliConfig(1, str(source).encode("utf-8"), job["sysroot"].encode("utf-8"), None, 0,
                        limits["maxBasicBlocks"], limits["nativeTimeoutMs"],
                        limits["maxOutputBytes"], limits["maxGuestMemoryBytes"])
    backend = job.get("backend")
    create_with_project = getattr(library, "qfli_miri_create_with_project", None)
    session_evidence = {"projectRoot": str(directory), "sourcePath": str(source),
                        "backendPath": backend, "filesystemRoot": str(directory),
                        "filesystemRootMode": "explicit_project"}
    evidence = {"id": case["id"], "sourceSha256": sha256(source), "filesSha256": files_hashes,
                "abiVersion": abi, "session": session_evidence}
    if create_with_project is not None:
        create_with_project.argtypes = [ctypes.POINTER(QfliConfig), ctypes.c_char_p, ctypes.c_char_p]
        create_with_project.restype = ctypes.c_void_p
        session_evidence["constructor"] = "qfli_miri_create_with_project"
        session = create_with_project(ctypes.byref(config), backend.encode("utf-8") if backend else None,
                                      str(directory).encode("utf-8"))
    elif backend:
        library.qfli_miri_create_with_backend.argtypes = [ctypes.POINTER(QfliConfig), ctypes.c_char_p]
        library.qfli_miri_create_with_backend.restype = ctypes.c_void_p
        session_evidence["constructor"] = "qfli_miri_create_with_backend"
        session = library.qfli_miri_create_with_backend(ctypes.byref(config), backend.encode("utf-8"))
    else:
        session_evidence["constructor"] = "qfli_miri_create"
        session = library.qfli_miri_create(ctypes.byref(config))
    if create_with_project is None:
        session_evidence.update(filesystemRoot=str(source.parent), filesystemRootMode="legacy_source_parent")
    if not session:
        return {**evidence, "error": "Native adapter rejected the session configuration"}
    try:
        run_return = library.qfli_miri_run(session)
        result = QfliResult()
        result_return = library.qfli_miri_result(session, ctypes.byref(result))
        channels = {}
        for index, name in enumerate(("stdout", "stderr", "diagnostics")):
            length = library.qfli_miri_copy_output(session, index, None, 0)
            if length > limits["maxOutputBytes"]:
                raise ContentError(f"Invalid native {name} length: {length}")
            buffer = (ctypes.c_uint8 * length)()
            if library.qfli_miri_copy_output(session, index, buffer, length) != length:
                raise ContentError(f"Native {name} changed after completion")
            channels[name] = channel_record(bytes(buffer))
        return {**evidence, "sourceSha256": sha256(source),
                "nativeRunReturn": run_return, "nativeResultReturn": result_return,
                "state": result.state, "exitCode": result.exit_code, "basicBlocks": result.basic_blocks,
                "peakGuestMemoryBytes": result.peak_guest_memory_bytes, "channels": channels}
    finally:
        # Run is synchronous: no native call remains active before destroy.
        library.qfli_miri_destroy(session)


def worker(job_path: Path) -> int:
    job = json.loads(job_path.read_text(encoding="utf-8"))
    try:
        result = run_native(job)
    except Exception as error:
        write_json(Path(job["result"]), {"id": job["case"]["id"], "error": f"{type(error).__name__}: {error}"})
        return 2
    write_json(Path(job["result"]), result)
    return 2 if result.get("error") else 0


def run_process(command: list[str], *, cwd: Path, env: dict, timeout: float) -> dict:
    started = time.monotonic()
    process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               start_new_session=os.name != "nt")
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except (subprocess.TimeoutExpired, KeyboardInterrupt) as error:
        if os.name == "nt":
            process.kill()
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        stdout, stderr = process.communicate()
        if isinstance(error, KeyboardInterrupt):
            raise
        timed_out = True
    return {"exitCode": process.returncode, "timedOut": timed_out,
            "seconds": round(time.monotonic() - started, 3),
            "stdout": channel_record(stdout), "stderr": channel_record(stderr)}


def assess_case(case: dict, native: dict | None, process: dict, *,
                project_root: Path | None = None, backend: Path | None = None) -> dict:
    bundle = case["files"] is not None
    result = {"id": case["id"], "topicId": case["topicId"], "kind": case["kind"],
              "runtimeLabel": case["runtime"], "entryFile": case["entryFile"],
              "sourceSha256": case["sourceSha256"], "expectedFilesSha256": case["filesSha256"],
              "expectedExitCode": case["expectedExitCode"], "expectedStdout": case["expectedStdout"],
              "stdoutAsserted": case["stdoutAsserted"], "status": "failed", "process": process,
              "bundleVerification": {"hasBundle": bundle, "requestedOperation": case["bundleVerify"],
                                     "scope": "main entry only", "cargoBuildAllTargets": "not_run",
                                     "cargoTest": "not_run", "cargoOperation": "not_run"}}
    if process["timedOut"]:
        result.update(status="timed_out", reason="worker wall-clock timeout; native result unproven")
        return result
    result["native"] = native
    if process["exitCode"] != 0 or not isinstance(native, dict) or native.get("error"):
        result["reason"] = "worker failed, crashed, or produced no native result"
        return result
    expected_files = case["filesSha256"] or {case["entryFile"]: case["sourceSha256"]}
    if (native.get("id") != case["id"] or native.get("sourceSha256") != case["sourceSha256"]
            or native.get("filesSha256") != expected_files or native.get("abiVersion") != 1):
        result["reason"] = "worker result identity differs from catalog or ABI"
        return result
    try:
        session = native["session"]
        constructor = session["constructor"]
        root = Path(session["projectRoot"])
        source = Path(session["sourcePath"])
        filesystem_root = Path(session["filesystemRoot"])
        expected_source = root.joinpath(*safe_path(case["entryFile"]).parts)
        if (not root.is_absolute() or not source.is_absolute() or not filesystem_root.is_absolute()
                or source != expected_source or (project_root is not None and root != project_root.resolve())
                or session["backendPath"] != (str(backend) if backend else None)
                or (session["backendPath"] is not None and not Path(session["backendPath"]).is_absolute())):
            raise ValueError("source, project root or backend differs from the materialized job")
        if constructor == "qfli_miri_create_with_project":
            if session["filesystemRootMode"] != "explicit_project" or filesystem_root != root:
                raise ValueError("explicit constructor did not use the complete project root")
        elif constructor in ("qfli_miri_create", "qfli_miri_create_with_backend"):
            if (session["filesystemRootMode"] != "legacy_source_parent" or filesystem_root != source.parent
                    or (constructor == "qfli_miri_create") != (session["backendPath"] is None)):
                raise ValueError("legacy constructor root or backend evidence differs")
        else:
            raise ValueError("unknown native session constructor")
    except (KeyError, TypeError, ValueError, ContentError) as error:
        result["reason"] = f"native session/root evidence missing or malformed: {error}"
        return result
    if (native.get("nativeRunReturn") != 0 or native.get("nativeResultReturn") != 0
            or native.get("state") != 2 or native.get("exitCode") != case["expectedExitCode"]):
        result["reason"] = "native execution failed, was cancelled, or reached a limit"
        return result
    try:
        decoded = {}
        for name in ("stdout", "stderr", "diagnostics"):
            channel = native["channels"][name]
            data = base64.b64decode(channel["base64"], validate=True)
            if (channel["bytes"] != len(data) or channel["sha256"] != hashlib.sha256(data).hexdigest()
                    or channel["text"] != data.decode("utf-8", "replace")):
                raise ValueError(f"{name} byte count, checksum or text differs")
            decoded[name] = data
        stdout = decoded["stdout"]
        stdout.decode("utf-8")
    except (KeyError, ValueError, TypeError) as error:
        result["reason"] = f"native stdout evidence missing or malformed: {error}"
        return result
    matched = (stdout.replace(b"\r\n", b"\n") == case["expectedStdout"].encode("utf-8").replace(b"\r\n", b"\n")
               if case["stdoutAsserted"] else None)
    result["stdoutMatched"] = matched
    result["stdoutComparison"] = "exact UTF-8 bytes; CRLF normalized only" if case["stdoutAsserted"] else "not asserted; no authored answer stdout"
    if matched is False:
        result["reason"] = "stdout mismatch"
    else:
        result["status"] = "passed"
    return result


def refresh_report(report: dict, cases: list[dict]) -> None:
    inventory = {case["id"]: case for case in cases}
    counts = {}
    invalid = []
    verified = []
    for index, result in enumerate(report["results"]):
        identifier = result.get("id") if isinstance(result, dict) else None
        if not isinstance(identifier, str):
            invalid.append(f"<invalid-result-{index}>")
            continue
        counts[identifier] = counts.get(identifier, 0) + 1
        if identifier not in inventory:
            continue
        try:
            native = result.get("native")
            session = native.get("session") if isinstance(native, dict) else None
            backend = session.get("backendPath") if isinstance(session, dict) else None
            assessed = assess_case(inventory[identifier], native, result["process"],
                                   backend=Path(backend) if backend is not None else None)
            metadata = ("id", "topicId", "kind", "runtimeLabel", "entryFile", "sourceSha256",
                        "expectedFilesSha256", "expectedExitCode", "expectedStdout", "stdoutAsserted",
                        "status", "stdoutMatched")
            if any(result.get(key) != assessed.get(key) for key in metadata):
                invalid.append(identifier)
            elif assessed["status"] == "passed":
                verified.append(identifier)
        except (KeyError, TypeError, ValueError, AttributeError):
            invalid.append(identifier)
    report["missingIds"] = [identifier for identifier in inventory if identifier not in counts]
    report["duplicateIds"] = [identifier for identifier, count in counts.items() if count != 1]
    report["unexpectedIds"] = [identifier for identifier in counts if identifier not in inventory]
    report["invalidEvidenceIds"] = list(dict.fromkeys(invalid))
    passed = {identifier for identifier in verified if counts[identifier] == 1 and identifier not in invalid}
    report["attemptedCases"] = len(report["results"])
    report["passedCases"] = len(passed)
    report["failedCases"] = [identifier for identifier in counts if identifier not in passed]
    report["failedCases"].extend(identifier for identifier in invalid if identifier not in counts)
    report["executionComplete"] = bool(cases) and not any(
        report[key] for key in ("missingIds", "duplicateIds", "unexpectedIds", "invalidEvidenceIds"))
    report["status"] = ("incomplete" if not cases or report["missingIds"] else
                        "failed" if report["failedCases"] else "passed")


def sysroot_identity(sysroot: Path) -> dict:
    folder = sysroot / "lib/rustlib" / GUEST_TARGET / "lib"
    files = [{"path": path.relative_to(sysroot).as_posix(), "size": path.stat().st_size,
              "sha256": sha256(path)} for path in sorted(folder.glob("*.rlib"))]
    if not files or not any(Path(entry["path"]).name.startswith("libstd-") for entry in files):
        raise ContentError(f"Pinned guest MIR sysroot is absent: {folder}")
    encoded = json.dumps(files, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {"path": str(sysroot), "files": files, "sha256": hashlib.sha256(encoded).hexdigest()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--library", type=Path, default=DEFAULT_LIBRARY)
    parser.add_argument("--sysroot", type=Path, default=DEFAULT_SYSROOT)
    parser.add_argument("--compiler-lib", type=Path, default=TOOLCHAIN / "lib")
    parser.add_argument("--preload-driver", type=Path, default=DEFAULT_DRIVER)
    parser.add_argument("--rustc", type=Path, default=TOOLCHAIN / "bin/rustc")
    parser.add_argument("--backend", type=Path)
    parser.add_argument("--report", type=Path, default=ROOT / "build/offline-ide-audit/native-host-catalog.json")
    parser.add_argument("--timeout", type=float, default=60, help="Outer worker timeout in seconds")
    parser.add_argument("--native-timeout", type=float, default=30)
    parser.add_argument("--max-basic-blocks", type=int, default=10_000_000)
    parser.add_argument("--max-output-bytes", type=int, default=1024 * 1024)
    parser.add_argument("--max-guest-memory-bytes", type=int, default=64 * 1024 * 1024)
    parser.add_argument("--worker", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        return worker(args.worker.resolve())
    report = {"schemaVersion": 1, "scope": "HOST embedded-Miri source preflight only",
              "mobileExecution": "not_tested", "ohosAcceptance": "not_established",
              "status": "incomplete", "results": [], "executionComplete": False}
    cases = []
    try:
        root = args.root.resolve(strict=True)
        report_path = args.report.resolve()
        if (args.timeout <= 0 or args.native_timeout <= 0 or args.timeout <= args.native_timeout
                or args.max_basic_blocks <= 0 or args.max_guest_memory_bytes <= 0
                or not 1024 <= args.max_output_bytes <= 16 * 1024 * 1024):
            raise ContentError("Limits must be positive; worker timeout must exceed native timeout; output 1 KiB..16 MiB")
        catalog_path = (args.catalog or root / DESTINATION).resolve(strict=True)
        document = json.loads(catalog_path.read_text(encoding="utf-8"))
        verify_native_catalog(document, load_topics(root / "tool/rust_content"))
        verify_paired_catalogs(root, document)
        cases = sorted(document["cases"], key=lambda case: (case["topicId"], 0 if case["kind"] == "example" else 1))
        report.update(catalog={"path": str(catalog_path), "sha256": sha256(catalog_path), **document["catalog"]},
                      expectedCases=len(cases), cargoBundles={"count": document["catalog"]["bundleCount"],
                      "status": "unverified", "cargoBuildAllTargets": "not_run", "cargoTests": "not_run",
                      "reason": "This harness invokes only the embedded main entry, never Cargo"})
        refresh_report(report, cases)
        write_json(report_path, report)
        if sys.platform != "linux" or platform.machine().lower() not in ("x86_64", "amd64"):
            raise ContentError("This reference harness requires an actual Linux x86_64 host; use WSL explicitly")
        library = args.library.resolve(strict=True)
        sysroot = args.sysroot.resolve(strict=True)
        compiler_lib = args.compiler_lib.resolve(strict=True)
        driver = args.preload_driver.resolve(strict=True)
        rustc = args.rustc.resolve(strict=True)
        backend = args.backend.resolve(strict=True) if args.backend else None
        env = dict(os.environ)
        env["LD_LIBRARY_PATH"] = str(compiler_lib) + (os.pathsep + env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else "")
        env["LD_PRELOAD"] = str(driver)
        env["CARGO_NET_OFFLINE"] = "true"
        compiler = run_process([str(rustc), "--version", "--verbose"], cwd=root, env=env, timeout=args.timeout)
        observed = dict(line.split(": ", 1) for line in compiler["stdout"]["text"].splitlines() if ": " in line)
        if (compiler["timedOut"] or compiler["exitCode"] != 0 or observed.get("release") != RUST_VERSION
                or observed.get("commit-hash") != RUST_COMMIT):
            raise ContentError("Host rustc version/commit does not match the pinned adapter contract")
        initial_sysroot = sysroot_identity(sysroot)
        report["engine"] = {"platform": sys.platform, "architecture": platform.machine(), "abiVersion": 1,
                            "guestTarget": GUEST_TARGET, "rustc": compiler, "library": str(library),
                            "librarySha256": sha256(library), "driver": str(driver), "driverSha256": sha256(driver),
                            "sysroot": initial_sysroot, "backend": str(backend) if backend else None,
                            "backendSha256": sha256(backend) if backend else None,
                            "LD_LIBRARY_PATH": env["LD_LIBRARY_PATH"], "LD_PRELOAD": env["LD_PRELOAD"]}
        limits = {"workerTimeoutSeconds": args.timeout, "nativeTimeoutMs": int(args.native_timeout * 1000),
                  "maxBasicBlocks": args.max_basic_blocks, "maxOutputBytes": args.max_output_bytes,
                  "maxGuestMemoryBytes": args.max_guest_memory_bytes, "stdinBytes": 0}
        report["limits"] = limits
        with tempfile.TemporaryDirectory(prefix="qfli-native-catalog-host-") as folder:
            scratch = Path(folder)
            snapshot = scratch / library.name
            shutil.copy2(library, snapshot)
            if sha256(snapshot) != report["engine"]["librarySha256"]:
                raise ContentError("Adapter changed while its immutable run snapshot was copied")
            for case in cases:
                report["currentCase"] = case["id"]
                write_json(report_path, report)
                job_path = scratch / f"{case['id']}.job.json"
                result_path = scratch / f"{case['id']}.result.json"
                case_directory = scratch / case["id"]
                write_json(job_path, {"case": case, "directory": str(case_directory),
                                     "library": str(snapshot), "sysroot": str(sysroot),
                                     "backend": str(backend) if backend else None, "limits": limits,
                                     "result": str(result_path)})
                try:
                    process = run_process([sys.executable, str(Path(__file__).resolve()), "--worker", str(job_path)],
                                          cwd=root, env=env, timeout=args.timeout)
                except OSError as error:
                    process = {"exitCode": None, "timedOut": False, "seconds": 0,
                               "stdout": channel_record(b""), "stderr": channel_record(str(error).encode("utf-8"))}
                native = None
                if result_path.exists():
                    try:
                        native = json.loads(result_path.read_text(encoding="utf-8"))
                    except (OSError, ValueError) as error:
                        native = {"error": f"Invalid worker result: {error}"}
                result = assess_case(case, native, process, project_root=case_directory, backend=backend)
                report["results"].append(result)
                report.pop("currentCase", None)
                refresh_report(report, cases)
                write_json(report_path, report)
                print(f"{case['id']} {result['status']} ({process['seconds']:.3f}s)", flush=True)
        report["engine"]["sysrootUnchanged"] = sysroot_identity(sysroot) == initial_sysroot
        report["engine"]["driverUnchanged"] = sha256(driver) == report["engine"]["driverSha256"]
        report["engine"]["backendUnchanged"] = not backend or sha256(backend) == report["engine"]["backendSha256"]
        if not all(report["engine"][key] for key in ("sysrootUnchanged", "driverUnchanged", "backendUnchanged")):
            report.update(status="failed", error="Compiler/sysroot/backend bytes changed during the host run")
        write_json(report_path, report)
        print(json.dumps({key: report[key] for key in ("status", "expectedCases", "attemptedCases", "passedCases",
                                                     "failedCases", "missingIds", "mobileExecution")}, indent=2))
        return 0 if report["status"] == "passed" else 1
    except (ContentError, OSError, ValueError, KeyboardInterrupt) as error:
        if cases:
            refresh_report(report, cases)
        report.update(status="interrupted" if isinstance(error, KeyboardInterrupt) else "failed",
                      error=f"{type(error).__name__}: {error}")
        write_json(args.report.resolve(), report)
        print(report["error"], file=sys.stderr)
        return 130 if isinstance(error, KeyboardInterrupt) else 2


if __name__ == "__main__":
    raise SystemExit(main())
