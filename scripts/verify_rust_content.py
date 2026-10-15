#!/usr/bin/env python3
"""Compile/run every Rust lesson and exercise, recording individual evidence."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

from generate_rust_content import ContentError, ROOT, generate, load_topics


def resolve_tool(name: str, explicit: str | None, root: Path, rustc: Path | None = None) -> Path | None:
    if explicit:
        path = shutil.which(explicit) or explicit
        return Path(path).resolve()
    if rustc is not None:
        sibling = rustc.with_name(name + (".exe" if os.name == "nt" else ""))
        if sibling.is_file():
            return sibling
    found = shutil.which(name)
    if found:
        return Path(found).resolve()
    bundled = root / "native/build/miri-windows/compiler/bin" / f"{name}.exe"
    return bundled if bundled.is_file() else None


def run_command(command: list[str], cwd: Path, timeout: float, env: dict[str, str]) -> dict:
    started = time.monotonic()
    try:
        result = subprocess.run(command, cwd=cwd, env=env, input="", capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=timeout)
        return dict(command=command, exitCode=result.returncode, stdout=result.stdout,
                    stderr=result.stderr, seconds=round(time.monotonic() - started, 3), timedOut=False)
    except subprocess.TimeoutExpired as error:
        def decoded(value: str | bytes | None) -> str:
            return value.decode("utf-8", "replace") if isinstance(value, bytes) else value or ""
        return dict(command=command, exitCode=None, stdout=decoded(error.stdout), stderr=decoded(error.stderr),
                    seconds=round(time.monotonic() - started, 3), timedOut=True)
    except OSError as error:
        return dict(command=command, exitCode=None, stdout="", stderr=str(error),
                    seconds=round(time.monotonic() - started, 3), timedOut=False)


def verify_program(source: str, path: Path, rustc: Path, timeout: float,
                   env: dict[str, str], expected: str | None, flags: list[str]) -> dict:
    path.mkdir(parents=True)
    entry = path / "main.rs"
    entry.write_text(source, encoding="utf-8")
    binary = path / ("sample.exe" if os.name == "nt" else "sample")
    compile_result = run_command([str(rustc), "--edition=2021", "--crate-name", "curriculum_sample",
                                  str(entry), "-C", "debuginfo=0", *flags, "-o", str(binary)], path, timeout, env)
    evidence = {"status": "failed", "sourceSha256": hashlib.sha256(source.encode("utf-8")).hexdigest(), "compile": compile_result}
    if compile_result["exitCode"] != 0:
        evidence["reason"] = "compile timeout" if compile_result["timedOut"] else "compile failed"
        return evidence
    run_result = run_command([str(binary)], path, timeout, env)
    evidence["run"] = run_result
    if run_result["exitCode"] != 0:
        evidence["reason"] = "execution timeout" if run_result["timedOut"] else "execution failed"
    elif expected is not None and run_result["stdout"].replace("\r\n", "\n") != expected.replace("\r\n", "\n"):
        evidence.update(reason="stdout mismatch", expectedOutput=expected)
    else:
        evidence["status"] = "passed"
    return evidence


def verify_topic(topic: dict, scratch: Path, rustc: Path, cargo: Path | None,
                 timeout: float, env: dict[str, str], flags: list[str]) -> dict:
    path = scratch / f"{topic['id']:03}"
    result = dict(id=topic["id"], title=topic["title"], domain=topic["domain"], runtime=topic["runtime"])
    result["example"] = verify_program(topic["code"], path / "example", rustc, timeout, env, topic["output"], flags)
    result["exercise"] = verify_program(topic["exercise"]["answer"], path / "exercise", rustc,
                                        timeout, env, topic["exercise"].get("output"), flags)
    if "files" in topic:
        if cargo is None:
            result["project"] = {"status": "failed", "reason": "cargo executable unavailable"}
        else:
            project = path / "project"
            for filename, source in topic["files"].items():
                file = project / filename
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(source, encoding="utf-8")
            operation = topic.get("verify", "run")
            project_output = topic.get("projectOutput", topic["output"])
            # Compile every supplied library/bin/test and workspace member, not
            # merely the default bin, before accepting an attached project.
            build_command = [str(cargo), "build", "--offline", "--quiet", "--workspace", "--all-targets", "--manifest-path", str(project / "Cargo.toml")]
            build = run_command(build_command, project, timeout, env)
            execution = None
            passed = build["exitCode"] == 0
            if passed and operation != "build":
                command = [str(cargo), operation, "--offline", "--quiet", "--manifest-path", str(project / "Cargo.toml")]
                if operation == "test":
                    command.extend(["--workspace", "--all-targets"])
                execution = run_command(command, project, timeout, env)
                passed = execution["exitCode"] == 0
                if operation == "run":
                    passed = passed and execution["stdout"].replace("\r\n", "\n") == project_output.replace("\r\n", "\n")
            result["project"] = {"status": "passed" if passed else "failed", "operation": operation,
                                 "filesSha256": {name: hashlib.sha256(source.encode("utf-8")).hexdigest() for name, source in topic["files"].items()},
                                 "buildAllTargets": build, "execution": execution}
            if not passed:
                result["project"]["expectedOutput"] = project_output if operation == "run" else None
    result["status"] = "passed" if all(result[key]["status"] == "passed" for key in ("example", "exercise", "project") if key in result) else "failed"
    return result


def write_report(path: Path | None, report: dict) -> None:
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--rustc", help="Host rustc executable (PATH, then bundled compiler by default)")
    parser.add_argument("--cargo", help="Host cargo executable (rustc sibling, then PATH by default)")
    parser.add_argument("--report", type=Path, help="Machine-readable per-program evidence")
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--structure-only", action="store_true", help="Explicitly skip execution; never produces a compiler pass")
    args = parser.parse_args()
    root = args.root.resolve()
    report = {"schemaVersion": 1, "scope": "desktop host compilation; no mobile engine claim", "status": "failed", "compilerStatus": "not_run", "results": []}
    try:
        report["catalog"] = generate(root, check=True)
        topics = load_topics(root / "tool/rust_content")
        report["inputSha256"] = {str(path.relative_to(root)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
                                 for path in sorted((root / "tool/rust_content").glob("topics_*.json"))}
        if args.structure_only:
            report.update(status="structure_only", compilerStatus="not_run", skippedPrograms=len(topics) * 2)
            write_report(args.report, report)
            print(json.dumps({key: value for key, value in report.items() if key != "results"}, ensure_ascii=False, indent=2))
            return 0
        if args.jobs < 1 or args.timeout <= 0:
            raise ContentError("--jobs and --timeout must be positive")
        rustc = resolve_tool("rustc", args.rustc, root)
        if rustc is None:
            raise ContentError("rustc unavailable; install a host compiler or request --structure-only explicitly")
        cargo = resolve_tool("cargo", args.cargo, root, rustc)
        env = dict(os.environ, RUSTC=str(rustc))
        env["PATH"] = str(rustc.parent) + os.pathsep + env.get("PATH", "")
        report["compiler"] = run_command([str(rustc), "--version", "--verbose"], root, args.timeout, env)
        if report["compiler"]["exitCode"] != 0:
            raise ContentError("host rustc failed its version check")
        encoded_flags = env.get("CARGO_ENCODED_RUSTFLAGS")
        flags = (encoded_flags.split("\x1f") if encoded_flags else []) if encoded_flags is not None else env.get("RUSTFLAGS", "").split()
        if os.name == "nt" and not env.get("RUSTFLAGS") and not env.get("CARGO_ENCODED_RUSTFLAGS"):
            host = next((line.removeprefix("host: ") for line in report["compiler"]["stdout"].splitlines() if line.startswith("host: ")), "")
            if host.endswith("-pc-windows-gnu"):
                sysroot = run_command([str(rustc), "--print", "sysroot"], root, args.timeout, env)
                linker = Path(sysroot["stdout"].strip()) / "lib/rustlib" / host / "bin/rust-lld.exe"
                if sysroot["exitCode"] == 0 and linker.is_file():
                    flags = ["-C", "linker-flavor=ld.lld", "-C", f"linker={linker}", "-C", "link-self-contained=yes"]
                    env["CARGO_ENCODED_RUSTFLAGS"] = "\x1f".join(flags)
        report["compilerFlags"] = flags
        with tempfile.TemporaryDirectory(prefix="qfli_rust_curriculum_") as temporary:
            scratch = Path(temporary)
            with ThreadPoolExecutor(max_workers=args.jobs) as pool:
                futures = [pool.submit(verify_topic, topic, scratch, rustc, cargo, args.timeout, env, flags) for topic in topics]
                for future in as_completed(futures):
                    result = future.result()
                    report["results"].append(result)
                    print(f"{result['id']:03} {result['status']}: {result['title']}", flush=True)
        report["results"].sort(key=lambda result: result["id"])
        failures = [result["id"] for result in report["results"] if result["status"] != "passed"]
        report.update(status="passed" if not failures else "failed", compilerStatus="executed",
                      passedLessons=len(topics) - len(failures), failedLessons=failures,
                      attemptedPrograms=len(topics) * 2,
                      compiledPrograms=sum(result[key]["compile"]["exitCode"] == 0 for result in report["results"] for key in ("example", "exercise")),
                      passedPrograms=sum(result[key]["status"] == "passed" for result in report["results"] for key in ("example", "exercise")),
                      mobileExecution="not_tested")
        write_report(args.report, report)
        print(json.dumps({key: value for key, value in report.items() if key not in {"results", "compiler"}}, ensure_ascii=False, indent=2))
        return 1 if failures else 0
    except (ContentError, OSError, ValueError) as error:
        report["error"] = str(error)
        write_report(args.report, report)
        print(f"Rust curriculum verification failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
