# -*- coding: utf-8 -*-
"""Round-5 targeted verify: lessons 055/057/062/064/068 compile+run with 10s timeouts."""

import json
import os
import subprocess
import tempfile

REPO = os.path.abspath(".")
BIN = os.path.join(REPO, "native", "build", "miri-windows", "compiler", "bin")
RUSTC = os.path.join(BIN, "rustc.exe")
LLD = os.path.join(
    REPO, "native", "build", "miri-windows", "compiler", "lib", "rustlib",
    "x86_64-pc-windows-gnu", "bin", "rust-lld.exe",
)
TIMEOUT = 10

by = {l["id"]: l for l in json.load(open("tool/rust_content/topics_001_084.json", encoding="utf-8"))}


def compile_run(code):
    env = dict(os.environ)
    env["PATH"] = BIN + os.pathsep + env.get("PATH", "")
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "main.rs")
        open(src, "w", encoding="utf-8").write(code)
        exe = os.path.join(tmp, "p.exe")
        try:
            c = subprocess.run(
                [RUSTC, "--edition", "2021", "-C", "linker-flavor=ld.lld",
                 "-C", f"linker={LLD}", "-C", "link-self-contained=yes", src, "-o", exe],
                capture_output=True, text=True, env=env, encoding="utf-8",
                errors="replace", timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            return False, "compile timeout"
        if c.returncode != 0:
            return False, c.stderr
        try:
            r = subprocess.run([exe], capture_output=True, text=True, env=env,
                               encoding="utf-8", errors="replace", timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            return False, "run timeout"
        if r.returncode != 0:
            return False, r.stderr
        return True, r.stdout


fail = 0
for lid in (55, 57, 62, 64, 68):
    l = by[lid]
    ok, out = compile_run(l["code"])
    print(f"[{lid:>3}] code   {'ok' if ok else 'FAIL'}")
    if not ok:
        print(out[:400]); fail += 1
    elif lid == 68 and out != l["output"]:
        print("      code output mismatch!") ; fail += 1
        print("expected:", repr(l["output"]))
        print("got     :", repr(out))
    ok2, out2 = compile_run(l["exercise"]["answer"])
    print(f"[{lid:>3}] answer {'ok' if ok2 else 'FAIL'}")
    if not ok2:
        print(out2[:400]); fail += 1

print("targeted failures:", fail)
