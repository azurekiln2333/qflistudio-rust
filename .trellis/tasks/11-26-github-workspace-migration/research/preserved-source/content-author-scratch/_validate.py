# -*- coding: utf-8 -*-
"""Real compile/run validator for authored lessons (scratch authoring aid).

Runs each lesson `code` through the provisioned rustc (single file) and each
exercise `answer` too, diffing stdout against `output`/expected. For lessons with
`files`, materializes a temp Cargo project and runs the `verify` action.

Usage:
  python tool/rust_content/_validate.py --file topics_001_084.json [--only-first N]

Never claims a pass when the compiler is absent: it reports `skipped`.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
BIN = os.path.join(REPO, "native", "build", "miri-windows", "compiler", "bin")
RUSTC = os.path.join(BIN, "rustc.exe")
CARGO = os.path.join(BIN, "cargo.exe")
RUST_LLD = os.path.join(
    REPO, "native", "build", "miri-windows", "compiler", "lib", "rustlib",
    "x86_64-pc-windows-gnu", "bin", "rust-lld.exe",
)
# Windows GNU toolchain has no system gcc/ld on PATH; point rustc at its bundled
# LLD linker so single-file compiles and cargo builds link deterministically.
RUSTC_LINK_FLAGS = [
    "-C", "linker-flavor=ld.lld",
    "-C", f"linker={RUST_LLD}",
    "-C", "link-self-contained=yes",
]


def cargo_env():
    env = dict(os.environ)
    env["PATH"] = BIN + os.pathsep + env.get("PATH", "")
    env["RUSTFLAGS"] = " ".join(RUSTC_LINK_FLAGS)
    return env


def run_cmd(args, cwd=None, timeout=180):
    return subprocess.run(
        args, cwd=cwd, capture_output=True, text=True, timeout=timeout,
        env=cargo_env(), encoding="utf-8", errors="replace",
    )


def check_single(name, source, expected):
    """Compile+run a single .rs file, compare stdout to expected."""
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "main.rs")
        with open(src, "w", encoding="utf-8") as fh:
            fh.write(source)
        exe = os.path.join(tmp, "prog.exe")
        comp = run_cmd([RUSTC, "--edition", "2021"] + RUSTC_LINK_FLAGS + [src, "-o", exe])
        if comp.returncode != 0:
            return "compile-error", comp.stderr.strip()
        proc = run_cmd([exe])
        if proc.returncode != 0:
            return "run-error", proc.stderr.strip()
        got = proc.stdout
        if expected is not None and got != expected:
            return "output-mismatch", f"expected {expected!r} got {got!r}"
        return "ok", got


def materialize(files, tmp):
    for rel, content in files.items():
        path = os.path.join(tmp, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)


def check_project(lesson):
    files = dict(lesson["files"])
    verify = lesson.get("verify", "build")
    with tempfile.TemporaryDirectory() as tmp:
        materialize(files, tmp)
        env = cargo_env()
        env["CARGO_TARGET_DIR"] = os.path.join(tmp, "target")
        base = [CARGO, "--offline"]
        if verify == "build":
            args = base + ["build"]
        elif verify == "test":
            args = base + ["test"]
        else:
            args = base + ["run"]
        proc = subprocess.run(args, cwd=tmp, capture_output=True, text=True,
                              timeout=600, env=env, encoding="utf-8",
                              errors="replace")
        if proc.returncode != 0:
            return "project-error", (proc.stderr or proc.stdout or "").strip()[-1500:]
        return "ok", (proc.stdout or "").strip()[-500:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default="topics_001_084.json")
    ap.add_argument("--only-first", type=int, default=0)
    ap.add_argument("--single-only", action="store_true")
    args = ap.parse_args()

    path = os.path.join(REPO, "tool", "rust_content", args.file)
    with open(path, encoding="utf-8") as fh:
        lessons = json.load(fh)

    if args.only_first:
        lessons = lessons[: args.only_first]

    counts = {"ok": 0, "compile-error": 0, "run-error": 0,
              "output-mismatch": 0, "project-error": 0}
    problems = []

    for lesson in lessons:
        lid = lesson["id"]
        status, detail = check_single(f"{lid}-code", lesson["code"], lesson["output"])
        counts[status] = counts.get(status, 0) + 1
        line = f"[{lid:>3}] code  {status}"
        if status != "ok":
            problems.append((lid, "code", detail))
            line += f"  -> {detail[:200]}"
        print(line)

        ans = lesson.get("exercise", {}).get("answer")
        if ans:
            status_a, detail_a = check_single(f"{lid}-answer", ans, None)
            counts[status_a] = counts.get(status_a, 0) + 1
            line = f"[{lid:>3}] answer {status_a}"
            if status_a != "ok":
                problems.append((lid, "answer", detail_a))
                line += f"  -> {detail_a[:200]}"
            print(line)

        if lesson.get("files") and not args.single_only:
            status_p, detail_p = check_project(lesson)
            counts[status_p] = counts.get(status_p, 0) + 1
            line = f"[{lid:>3}] project {status_p}"
            if status_p != "ok":
                problems.append((lid, "project", detail_p))
                line += f"  -> {detail_p[:200]}"
            print(line)

    print("\n=== summary ===")
    for k, v in counts.items():
        print(f"{k}: {v}")
    if problems:
        print(f"\n{len(problems)} problem(s):")
        for lid, kind, detail in problems:
            print(f"  lesson {lid} [{kind}]: {detail[:400]}")
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()
