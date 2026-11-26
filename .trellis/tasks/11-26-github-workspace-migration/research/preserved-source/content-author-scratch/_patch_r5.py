# -*- coding: utf-8 -*-
"""Round-5 alignment fixes: 055, 057, 062, 064, 068 (answers/prompts/output)."""

import io
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
HERE = os.path.join(REPO, "build", "content-author-scratch")


def run_rs(code):
    env = dict(os.environ)
    env["PATH"] = BIN + os.pathsep + env.get("PATH", "")
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "main.rs")
        io.open(src, "w", encoding="utf-8").write(code)
        exe = os.path.join(tmp, "p.exe")
        c = subprocess.run(
            [RUSTC, "--edition", "2021", "-C", "linker-flavor=ld.lld",
             "-C", f"linker={LLD}", "-C", "link-self-contained=yes", src, "-o", exe],
            capture_output=True, text=True, env=env, encoding="utf-8", errors="replace")
        if c.returncode != 0:
            raise SystemExit("compile failed:\n" + c.stderr)
        r = subprocess.run([exe], capture_output=True, text=True, env=env,
                           encoding="utf-8", errors="replace")
        if r.returncode != 0:
            raise SystemExit("run failed:\n" + r.stderr)
        return r.stdout


def replace_json_string(src, field, new_value, anchor):
    start = src.index(anchor)
    key = '"' + field + '": "'
    ks = src.index(key, start)
    vs = ks + len(key)
    i = vs
    while True:
        if src[i] == "\\":
            i += 2
            continue
        if src[i] == '"':
            break
        i += 1
    return src[:ks] + key + json.dumps(new_value, ensure_ascii=False)[1:-1] + src[i:]


def read_draft(name):
    with io.open(os.path.join(HERE, name), encoding="utf-8") as fh:
        return fh.read()


NEW_055_ANSWER = read_draft("_r5_055.rs")
NEW_057_ANSWER = read_draft("_r5_057.rs")
NEW_062_ANSWER = read_draft("_r5_062.rs")
NEW_064_ANSWER = read_draft("_r5_064.rs")
NEW_068_CODE = read_draft("_r5_068_code.rs")
NEW_068_ANSWER = read_draft("_r5_068_answer.rs")

NEW_057_PROMPT = (
    "写函数 `bucket(score: u32) -> &'static str`，用 `@` 绑定与 `if` 守卫共同实现："
    "0..=59 返回 \"F\"，60..=69 返回 \"D\"，70..=79 返回 \"C\"，80..=89 返回 \"B\"，90..=100 返回 \"A\"，"
    "其中当分数是整十（s % 10 == 0）时返回带“(整十)”后缀的等级（如 60 -> \"D(整十)\"、90 -> \"A(整十)\"），"
    "其他（如 120）返回 \"invalid\"；在 main 中测试 45、72、70、60、95、90、120。"
)

NEW_064_PROMPT = (
    "用显式状态机 `enum State { Outside, InWord, InNumber }` 实现简易词法扫描："
    "遇到字母进入 InWord，遇到数字进入 InNumber，遇到空白回到 Outside；"
    "每次状态切换（或遇到空白）时先发出已累积的 token，类别变化会切分同一个无空白片段，"
    "例如 `a1` 会切成 `word:a` 与 `number:1`。按空白与类别边界输出 `word:值` / `number:值`，"
    "对输入 `\"a1 23 bc\"` 打印 4 个 token。"
)

NEW_068_PROMPT = (
    "扩展解析器支持 `set k v` 与 `del k`：命令名之后 `set` 需要两个参数（键与值），值可含空格并拼回；"
    "`del` 需要恰好一个参数，多给也算错。写 `parse` 返回相应 Command 并在 main 中测试合法与非法各两条；"
    "另外让 `quit` 拒绝任何多余参数（命令名之后必须为零个参数）。"
)


def main():
    # ---- 055 answer
    p = os.path.join(HERE, "_d1.py")
    src = io.open(p, encoding="utf-8").read()
    src = replace_json_string(src, "answer", NEW_055_ANSWER, '"id": 55,')

    # ---- 057 prompt + answer
    src = replace_json_string(src, "prompt", NEW_057_PROMPT, '"id": 57,')
    src = replace_json_string(src, "answer", NEW_057_ANSWER, '"id": 57,')
    io.open(p, "w", encoding="utf-8").write(src)
    print("055 answer, 057 prompt+answer fixed in _d1.py")

    # ---- 062, 064, 068 in _d2.py
    p = os.path.join(HERE, "_d2.py")
    src = io.open(p, encoding="utf-8").read()

    # 062 explicit ref
    src = replace_json_string(src, "answer", NEW_062_ANSWER, '"id": 62,')

    # 064 prompt + answer
    src = replace_json_string(src, "prompt", NEW_064_PROMPT, '"id": 64,')
    src = replace_json_string(src, "answer", NEW_064_ANSWER, '"id": 64,')

    # 068 code (+output), prompt, answer
    out68 = run_rs(NEW_068_CODE)
    src = replace_json_string(src, "code", NEW_068_CODE, '"id": 68,')
    src = replace_json_string(src, "output", out68, '"id": 68,')
    src = replace_json_string(src, "prompt", NEW_068_PROMPT, '"id": 68,')
    src = replace_json_string(src, "answer", NEW_068_ANSWER, '"id": 68,')

    io.open(p, "w", encoding="utf-8").write(src)
    print("062 answer, 064 prompt+answer, 068 code+output+prompt+answer fixed in _d2.py")
    print("068 real code stdout:\n" + out68)


if __name__ == "__main__":
    main()
