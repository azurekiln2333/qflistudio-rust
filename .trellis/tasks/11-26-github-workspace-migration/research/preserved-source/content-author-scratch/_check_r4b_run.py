# -*- coding: utf-8 -*-
"""Targeted compile+run for the round-4 completion lessons (048, 079, 081)."""
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

by = {l["id"]: l for l in json.load(open("tool/rust_content/topics_001_084.json", encoding="utf-8"))}


def compile_run(code):
    env = dict(os.environ)
    env["PATH"] = BIN + os.pathsep + env.get("PATH", "")
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "main.rs")
        open(src, "w", encoding="utf-8").write(code)
        exe = os.path.join(tmp, "p.exe")
        c = subprocess.run(
            [RUSTC, "--edition", "2021", "-C", "linker-flavor=ld.lld",
             "-C", f"linker={LLD}", "-C", "link-self-contained=yes", src, "-o", exe],
            capture_output=True, text=True, env=env, encoding="utf-8", errors="replace")
        if c.returncode != 0:
            return False, c.stderr
        r = subprocess.run([exe], capture_output=True, text=True, env=env,
                           encoding="utf-8", errors="replace")
        if r.returncode != 0:
            return False, r.stderr
        return True, r.stdout


fail = 0
for lid in (48, 79, 81):
    l = by[lid]
    ok, out = compile_run(l["code"])
    stat = "ok" if ok else "FAIL"
    if ok and lid in (79,) and out != l["output"]:
        ok, stat = False, "output-mismatch"
    print(f"[{lid:>3}] code  {stat}")
    if not ok:
        print(out[:500])
        fail += 1
    ok2, out2 = compile_run(l["exercise"]["answer"])
    print(f"[{lid:>3}] answer {'ok' if ok2 else 'FAIL'}")
    if not ok2:
        print(out2[:500])
        fail += 1

print("targeted failures:", fail)
