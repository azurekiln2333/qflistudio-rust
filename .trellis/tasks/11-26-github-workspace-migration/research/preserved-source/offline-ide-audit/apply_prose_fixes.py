#!/usr/bin/env python3
"""Apply exact prose-only fixes to the changed `explain` fields.

Rules enforced by the replacements:
  * no full-width semicolon
  * no sentence over 40 counted chars
  * no vague word 若干
  * keeps every inline-code span and every modality word unchanged

Only the `explain` value of the six changed topics is touched. Writes bytes so
the file keeps LF line endings. Records before/after snapshots for the
unchanged-field proof.
"""

from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "build" / "offline-ide-audit"

FILES = ["tool/rust_content/topics_001_084.json", "tool/rust_content/topics_085_166.json"]

# (file, id, [ (old, new), ... ]). Each `old` must occur exactly once.
EDITS: list[tuple[str, int, list[tuple[str, str]]]] = [
    (
        "tool/rust_content/topics_001_084.json",
        13,
        [
            (
                "记录单调时钟，但若编译器发现结果未被使用，会把整个计算优化掉，因此要用",
                "记录单调时钟。编译器若发现结果未被使用，会把整个计算优化掉。因此要用",
            ),
            (
                "会做自动预热、多轮采样、统计显著性检验与异常值剔除；它的核心方法论可以手工近似：先跑若干次预热让缓存与分支预测进入稳态，再采集多轮样本，报告最小值或中位数而非单次值。",
                "会做自动预热、多轮采样、统计显著性检验与异常值剔除。它的核心方法论可以手工近似：先跑多次预热让缓存与分支预测进入稳态。再采集多轮样本。报告最小值或中位数而非单次值。",
            ),
            (
                "还要固定输入规模、记录构建档（debug 与 release 差距往往数倍）、避免在计时区间里做 I/O。",
                "还要固定输入规模。还要记录构建档（debug 与 release 差距往往数倍）。还要避免在计时区间里做 I/O。",
            ),
            (
                "不能用它评价手机硬件性能；正式测量应在桌面原生 release 构建中扩大输入规模并记录环境。",
                "不能用它评价手机硬件性能。正式测量应在桌面原生 release 构建中扩大输入规模，并记录环境。",
            ),
        ],
    ),
    (
        "tool/rust_content/topics_085_166.json",
        157,
        [
            (
                "当前 Rust 2024 要求将导出符号属性写为 #[unsafe(no_mangle)]，外部声明块写为 unsafe extern \"C\"；符号唯一性和函数签名仍需由作者保证。",
                "当前 Rust 2024 要求将导出符号属性写为 #[unsafe(no_mangle)]。外部声明块要写为 unsafe extern \"C\"。符号唯一性和函数签名仍需由作者保证。",
            )
        ],
    ),
    (
        "tool/rust_content/topics_085_166.json",
        158,
        [
            (
                "并不需要任何第三方 crate：标准库的",
                "并不需要任何第三方 crate。标准库的",
            ),
            (
                "已提供 c_char/c_int 等 C 兼容类型，配合 extern \"C\" 就能声明与定义 C ABI 函数；#[link] 只在需要链接真正的外部库时才用。",
                "已提供 c_char/c_int 等 C 兼容类型。配合 extern \"C\" 就能声明与定义 C ABI 函数。#[link] 只在需要链接真正的外部库时才用。",
            ),
            (
                "本课完全离线：在同文件中用 extern \"C\" 定义并调用一个 C 风格字符串长度函数，并可额外声明同一符号。",
                "本课完全离线。本课在同一文件中用 extern \"C\" 定义并调用一个 C 风格字符串长度函数。本课还可额外声明同一符号。",
            ),
            (
                "当前 Rust 2024 要求将导出符号属性写为 #[unsafe(no_mangle)]，外部声明块写为 unsafe extern \"C\"；符号唯一性和函数签名仍需由作者保证。",
                "当前 Rust 2024 要求将导出符号属性写为 #[unsafe(no_mangle)]。外部声明块要写为 unsafe extern \"C\"。符号唯一性和函数签名仍需由作者保证。",
            ),
        ],
    ),
    (
        "tool/rust_content/topics_085_166.json",
        159,
        [
            (
                "panic 试图跨过这个边界时**不会**展开到 C（不是 UB 到 C 侧），而是被运行时捕获并**中止进程（abort）**；这与‘外部异常（foreign unwind）跨越到 Rust’是两回事（后者才是未定义行为）。",
                "panic 试图跨过这个边界时**不会**展开到 C（不是 UB 到 C 侧）。运行时会捕获 panic 并**中止进程（abort）**。这与‘外部异常（foreign unwind）跨越到 Rust’是两回事。后者才是未定义行为。",
            ),
            (
                "当前 Rust 2024 要求将导出符号属性写为 #[unsafe(no_mangle)]，外部声明块写为 unsafe extern \"C\"；符号唯一性和函数签名仍需由作者保证。",
                "当前 Rust 2024 要求将导出符号属性写为 #[unsafe(no_mangle)]。外部声明块要写为 unsafe extern \"C\"。符号唯一性和函数签名仍需由作者保证。",
            ),
        ],
    ),
    (
        "tool/rust_content/topics_085_166.json",
        161,
        [
            (
                "可测量代码段耗时；为降低噪声，应多次运行取最快/中位数，并在 release 模式（opt-level=3）下测。",
                "可测量代码段耗时。为降低噪声，应多次运行并取最快值或中位数。测量应在 release 模式（opt-level=3）下做。",
            ),
            (
                "且优化要服务于真实瓶颈；本课比较",
                "且优化要服务于真实瓶颈。本课比较",
            ),
            (
                "移动端用 200 个输入、20 个不同值展示去重过程，练习用 1000 个元素比较求和，保留两种算法与确定性断言。",
                "移动端用 200 个输入、20 个不同值展示去重过程。练习用 1000 个元素比较求和。两种算法与确定性断言都保留。",
            ),
            (
                "不适合得出性能排名；实际基准",
                "不适合得出性能排名。实际基准",
            ),
        ],
    ),
    (
        "tool/rust_content/topics_085_166.json",
        166,
        [
            (
                "spawn 将任务固定到 Pin<Box<dyn Future>>，安排一次初始轮询；任务返回 Pending 后，执行器阻塞在 ready_rx.recv，只有外部事件通过 Waker 安排就绪通知才再次 poll。",
                "spawn 将任务固定到 Pin<Box<dyn Future>>，并安排一次初始轮询。任务返回 Pending 后，执行器阻塞在 ready_rx.recv。只有外部事件通过 Waker 安排就绪通知，才再次 poll。",
            ),
            (
                "用 AtomicBool 合并重复通知；在 poll 前清除 queued，让轮询过程中到达的新事件仍能重新排队。",
                "用 AtomicBool 合并重复通知。它在 poll 前把 queued 复位。轮询过程中到达的新事件仍能重新排队。",
            ),
            (
                "已经完成任务的陈旧通知会被安全忽略。",
                "执行器会安全忽略已完成任务的陈旧通知。",
            ),
            (
                "第一次 Pending 的确认后才发布值或取消；自检因而能验证",
                "第一次 Pending 的确认。确认之后它才发布值或取消。自检因而能验证",
            ),
            (
                "不能被后续值覆盖；执行器把它与正常值一起从任务表移除。",
                "后续值不能覆盖取消。执行器把它与正常值一起从任务表移除。",
            ),
            (
                "最终完成或取消；生产环境还需要关闭协议、截止时间及全局停止策略。",
                "最终完成或取消。生产环境还需要关闭协议、截止时间及全局停止策略。",
            ),
            (
                "任何非空输出指针都必须满足对齐、有效和独占写入的调用契约；safe wrapper 只传递自己的栈上 i32，并检查返回码后才暴露结果。",
                "任何非空输出指针都必须满足对齐与有效。输出指针还必须保证独占写入。safe wrapper 只传递自己的栈上 i32。safe wrapper 检查返回码后才暴露结果。",
            ),
            (
                "当前 Rust 2024 要求将导出符号属性写为 #[unsafe(no_mangle)]，外部声明块写为 unsafe extern \"C\"；符号唯一性和函数签名仍需由作者保证。",
                "当前 Rust 2024 要求将导出符号属性写为 #[unsafe(no_mangle)]。外部声明块要写为 unsafe extern \"C\"。符号唯一性和函数签名仍需由作者保证。",
            ),
        ],
    ),
]


def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def dump_bytes(data) -> bytes:
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    before = {}
    after = {}

    for path in FILES:
        data = load(path)
        before[path] = json.loads(json.dumps(data))  # deep copy

    for path, tid, pairs in EDITS:
        data = load(path)
        topic = next(t for t in data if t["id"] == tid)
        text = topic["explain"]
        for old, new in pairs:
            count = text.count(old)
            if count != 1:
                raise SystemExit(f"FAIL {path} id={tid}: occurrence {count} for {old[:40]!r}")
            text = text.replace(old, new)
        topic["explain"] = text
        (ROOT / path).write_bytes(dump_bytes(data))

    # Round-trip check: the writer must reproduce the file byte for byte.
    for path in FILES:
        raw = (ROOT / path).read_bytes()
        if dump_bytes(json.loads(raw.decode("utf-8"))) != raw:
            raise SystemExit(f"FAIL round-trip {path}")

    for path in FILES:
        after[path] = load(path)

    changed_fields = []
    for path in FILES:
        old_by_id = {t["id"]: t for t in before[path]}
        new_by_id = {t["id"]: t for t in after[path]}
        if [t["id"] for t in before[path]] != [t["id"] for t in after[path]]:
            raise SystemExit(f"FAIL topic order changed in {path}")
        for tid in old_by_id:
            old_topic = old_by_id[tid]
            new_topic = new_by_id[tid]
            if list(old_topic) != list(new_topic):
                raise SystemExit(f"FAIL key order changed id={tid}")
            for key in old_topic:
                if old_topic[key] != new_topic[key]:
                    changed_fields.append((path, tid, key))

    for path, tid, key in changed_fields:
        print(f"changed {path} id={tid} field={key}")
    bad = [c for c in changed_fields if not (c[2] == "explain" and c[1] in (13, 62, 157, 158, 159, 161, 166))]
    print(f"unexpected fields changed: {len(bad)}")
    if bad:
        for item in bad:
            print("  UNEXPECTED", item)
        return 2

    (OUT / "prose-fix-before.json").write_text(
        json.dumps(before, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUT / "prose-fix-after.json").write_text(
        json.dumps(after, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())