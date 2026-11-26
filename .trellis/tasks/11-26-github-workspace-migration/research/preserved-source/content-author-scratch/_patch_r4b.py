# -*- coding: utf-8 -*-
"""Round-4 completion: 079 main code, 081 answer comment, 048 first sentence."""

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


def run_rs(code):
    env = dict(os.environ)
    env["PATH"] = BIN + os.pathsep + env.get("PATH", "")
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "main.rs")
        with io.open(src, "w", encoding="utf-8") as fh:
            fh.write(code)
        exe = os.path.join(tmp, "p.exe")
        c = subprocess.run(
            [RUSTC, "--edition", "2021", "-C", "linker-flavor=ld.lld",
             "-C", f"linker={LLD}", "-C", "link-self-contained=yes", src, "-o", exe],
            capture_output=True, text=True, env=env, encoding="utf-8", errors="replace")
        if c.returncode != 0:
            raise SystemExit("compile failed:\n" + c.stderr + "\n---\n" + code)
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


NEW079_CODE = r'''use std::convert::TryFrom;

// 1) 可失败转换用 TryFrom：范围校验，失败返回原因。
#[derive(Debug, PartialEq)]
struct Percentage(u8);

impl TryFrom<i64> for Percentage {
    type Error = String;

    fn try_from(value: i64) -> Result<Self, Self::Error> {
        if (0..=100).contains(&value) {
            Ok(Percentage(value as u8))
        } else {
            Err(format!("{} 不在 0..=100", value))
        }
    }
}

// 2) 无损转换用 From：UserId 原样保存字符串，绝不丢信息。
#[derive(Debug, PartialEq, Eq)]
struct UserId(String);

impl From<String> for UserId {
    fn from(value: String) -> Self {
        UserId(value) // 原样保留全部文本
    }
}

impl From<&str> for UserId {
    fn from(value: &str) -> Self {
        UserId(value.to_string()) // 原样保留全部文本
    }
}

// label 接收 impl Into<String>，&str 与 String 都能无成本传入。
fn label(value: impl Into<String>) -> String {
    format!("<{}>", value.into())
}

fn main() {
    // TryFrom：范围校验
    assert_eq!(Percentage::try_from(42), Ok(Percentage(42)));
    assert!(Percentage::try_from(150).is_err());
    println!("{:?}", Percentage::try_from(42));
    println!("{:?}", Percentage::try_from(150));

    // From 无损：原文本完整保留
    let a: UserId = "user-中文-01".into();
    let b: UserId = String::from("keep me exactly").into();
    assert_eq!(a, UserId(String::from("user-中文-01")));
    assert_eq!(b, UserId(String::from("keep me exactly")));
    println!("a = {:?}", a);
    println!("b = {:?}", b);

    // 关键：长度相同但内容不同的两个 id 必须仍然不相等（证明没有按长度退化）
    let x: UserId = "abcd".into();
    let y: UserId = "wxyz".into();
    assert_ne!(x, y, "同样长度、不同文本的 id 必须不相等");
    assert_eq!(x.0.len(), y.0.len());
    println!("x = {:?}, y = {:?}, x == y: {}", x, y, x == y);

    println!("{}", label("static str"));
    println!("{}", label(String::from("owned")));
}
'''

# 081: wrong comment about PartialEq reflexivity
OLD81_COMMENT = "// PartialEq 必须是等价关系：自反、对称、传递。这里做逐字段精确相等。"
NEW81_COMMENT = ("// PartialEq 的契约是【对称性 + 传递性】（并不要求自反；自反是 Eq 的额外要求）。\n"
                 "// 这里做逐字段精确相等：sensor 相等，且 celsius 的二进制位相同（to_bits）。")

# 048: first sentence must note take needs Default
OLD48 = ("`Cell<T>` 对**任意** `T` 都提供 `set`/`replace`/`take`/`into_inner`"
         "（这些只需移动或返回拥有值）；只有 `get` 要求 `T: Copy`")
NEW48 = ("`Cell<T>` 的 `set`/`replace`/`into_inner` 对**任意** `T` 可用，"
         "`take` 需要 `T: Default`（它把内部值取走并留下 `T::default()`）；"
         "只有 `get` 要求 `T: Copy`")


def main():
    # 079 main code + output
    p = "tool/rust_content/_e2.py"
    with io.open(p, encoding="utf-8") as fh:
        src = fh.read()
    out79 = run_rs(NEW079_CODE)
    src = replace_json_string(src, "code", NEW079_CODE, '"id": 79,')
    src = replace_json_string(src, "output", out79, '"id": 79,')

    # 081 answer comment
    if OLD81_COMMENT not in src:
        raise SystemExit("081 comment not found")
    src = src.replace(OLD81_COMMENT, NEW81_COMMENT, 1)
    with io.open(p, "w", encoding="utf-8") as fh:
        fh.write(src)
    print("079 code+output fixed; real stdout:\n" + out79)
    print("081 answer comment fixed")

    # 048 first sentence
    p = "tool/rust_content/_c3.py"
    with io.open(p, encoding="utf-8") as fh:
        src = fh.read()
    if OLD48 not in src:
        raise SystemExit("048 fragment not found")
    src = src.replace(OLD48, NEW48, 1)
    with io.open(p, "w", encoding="utf-8") as fh:
        fh.write(src)
    print("048 first sentence fixed")


if __name__ == "__main__":
    main()
