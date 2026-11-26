# -*- coding: utf-8 -*-
"""Round-6 targeted verify: 057 and 068 compile+run (10s) + field assertions."""
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
for lid in (57, 68):
    l = by[lid]
    ok, out = compile_run(l["code"])
    print(f"[{lid:>3}] code   {'ok' if ok else 'FAIL'}")
    if not ok:
        print(out[:400]); fail += 1
    elif lid == 68 and out != l["output"]:
        print("      code output mismatch!"); fail += 1
    ok2, out2 = compile_run(l["exercise"]["answer"])
    print(f"[{lid:>3}] answer {'ok' if ok2 else 'FAIL'}")
    if not ok2:
        print(out2[:400]); fail += 1

# field assertions
a57 = by[57]["exercise"]["answer"]
a68 = by[68]["exercise"]["answer"]
checks = {
    "057 answer has F(整十) branch": '"F(整十)"' in a57,
    "057 answer asserts bucket(0)/(10)/(50)": all(s in a57 for s in ("bucket(0)", "bucket(10)", "bucket(50)")),
    "057 answer asserts non-round 55": 'bucket(55)' in a57,
    "068 answer Command has Quit": "Quit," in a68,
    "068 answer parses quit zero-arg success": "Ok(Command::Quit)" in a68,
    "068 answer rejects quit extra args": "quit now" in a68 and "expected: 0" in a68,
}
for k, v in checks.items():
    print(("PASS " if v else "FAIL ") + k)
    if not v:
        fail += 1

print("total failures:", fail)
