# -*- coding: utf-8 -*-
"""Lessons 008..014 (Domain A, part 2)."""

LESSONS = [
{
    "id": 8,
    "title": "条件编译：`cfg`、`cfg!(...)`、目标平台分支",
    "level": "beginner",
    "domain": "toolchain-cargo",
    "summary": "用 cfg 属性把平台相关代码隔离在编译期，理解 target_os / target_arch / debug_assertions 的作用。",
    "concepts": ["#[cfg]", "cfg!()", "target_os", "target_arch", "debug_assertions"],
    "objective": "能写出按目标平台选择实现的条件编译代码，并区分属性式 `#[cfg]` 与表达式宏 `cfg!` 的用途。",
    "prerequisites": ["004"],
    "explain": "`#[cfg(...)]` 是编译期属性：条件为假时，被标注的项根本不会进入 AST，因此里面的代码即使在本平台不可用也不会报错。`cfg!` 是表达式宏：两边的代码仍会被编译，只是运行时选择常量分支，适合两分支都能编译的场景。常用谓词包括 `target_os = \"linux\"/\"windows\"/\"macos\"`、`target_arch = \"x86_64\"/\"aarch64\"`、`target_pointer_width`、`debug_assertions`（debug 构建为真）。组合用 `all()`、`any()`、`not()`。注意 `#[cfg(test)]` 会自动在 `cargo test` 时开启，是编写单元测试的标准手法。条件编译让同一份源码服务多个平台，但也要求你为每个分支实际构建验证，避免只测了当前平台。",
    "code": "// 条件编译：平台分支用 #[cfg] 隔离，调试开关用 cfg! 观察。\n\n#[cfg(target_pointer_width = \"64\")]\nfn pointer_bits() -> u32 { 64 }\n\n#[cfg(not(target_pointer_width = \"64\"))]\nfn pointer_bits() -> u32 { 32 }\n\nfn main() {\n    let profile = if cfg!(debug_assertions) { \"debug\" } else { \"release\" };\n    println!(\"指针宽度 = {} 位\", pointer_bits());\n    println!(\"当前构建档 = {}\", profile);\n    println!(\"条件编译在编译期裁剪, cfg! 保留两侧代码\");\n}\n",
    "output": "指针宽度 = 64 位\n当前构建档 = debug\n条件编译在编译期裁剪, cfg! 保留两侧代码\n",
    "pitfalls": [
        "在 `cfg!` 分支里写只有某平台才编译得过的代码：`cfg!` 两侧都会被编译，平台专属代码必须用 `#[cfg]`。",
        "忘记条件编译分支也会被 lint：不同平台可能给出不同警告，需实际在目标平台跑一遍。",
        "把运行期判断当编译期判断：`cfg!` 的值在编译期已知，不要用它替代真正的运行时配置。"
    ],
    "exercise": {
        "prompt": "写函数 `arch_name()`，在 x86_64 上返回 \"x86_64\"、aarch64 返回 \"aarch64\"、其他返回 \"unknown\"（用条件编译），并在 main 中打印。",
        "hint": "用三个以 `#[cfg(target_arch = \"...\")]` 分别标注的同名函数实现。",
        "answer": "#[cfg(target_arch = \"x86_64\")]\nfn arch_name() -> &'static str { \"x86_64\" }\n\n#[cfg(target_arch = \"aarch64\")]\nfn arch_name() -> &'static str { \"aarch64\" }\n\n#[cfg(not(any(target_arch = \"x86_64\", target_arch = \"aarch64\")))]\nfn arch_name() -> &'static str { \"unknown\" }\n\nfn main() {\n    println!(\"arch = {}\", arch_name());\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 9,
    "title": "环境变量与构建脚本 `build.rs` 基础",
    "level": "intermediate",
    "domain": "toolchain-cargo",
    "summary": "用 build.rs 在编译前生成代码，并理解 CARGO_* 环境变量与 rerun-if 指令的语义。",
    "concepts": ["build.rs", "CARGO_PKG_VERSION", "cargo:rerun-if-changed", "OUT_DIR", "env!"],
    "objective": "能解释 build.rs 的执行时机、如何把生成文件写到 OUT_DIR，以及为什么必须声明重跑条件。",
    "prerequisites": ["007"],
    "explain": "`build.rs` 是包的构建脚本：cargo 在编译包本身之前先编译并运行它。它常用于生成代码、链接本地库、探测环境。脚本通过 `println!(\"cargo:...\")` 向 cargo 传递指令，例如 `cargo:rustc-env=KEY=VALUE` 把值注入 `env!(\"KEY\")`。关于重跑（rerun）语义要准确：当 build.rs 没有输出任何 `cargo:rerun-if-changed` 或 `cargo:rerun-if-env-changed` 时，cargo 的默认行为是“包内任意文件变化就重跑构建脚本”；一旦输出了具体的 `rerun-if-changed`/`rerun-if-env-changed`，默认全量监控便被关闭，cargo 只按你声明的路径/环境变量决定重跑。因此“缺少它”并非导致陈旧产物，而是回退到更保守的全量重跑；真正会因缺声明而陈旧的是已声明部分路径却漏掉另一依赖的情况。生成的文件写到环境变量 `OUT_DIR` 指向的目录，再用 `include!(concat!(env!(\"OUT_DIR\"), \"/gen.rs\"))` 引入。编译期常量通过 `env!` 拿到，例如 `CARGO_PKG_VERSION`。注意 build.rs 在宿主平台运行，其依赖要写在 `[build-dependencies]`。",
    "code": "// 单文件对照版：演示代码如何消费“编译期注入的版本字符串”。\n// 真实 build.rs + Cargo 工程见 files 映射。\n\nconst PKG_VERSION: &str = \"0.1.0\";\n\nfn banner(name: &str, version: &str) -> String {\n    format!(\"{} v{}\", name, version)\n}\n\nfn main() {\n    // 真实工程中这一行来自 env!(\"CARGO_PKG_VERSION\") 或 build.rs 的 rustc-env。\n    println!(\"{}\", banner(\"lesson-009-build\", PKG_VERSION));\n    println!(\"build.rs 在编译本包前由 cargo 运行，写文件到 OUT_DIR\");\n}\n",
    "output": "lesson-009-build v0.1.0\nbuild.rs 在编译本包前由 cargo 运行，写文件到 OUT_DIR\n",
    "pitfalls": [
        "只声明部分重跑依赖：一旦输出了 `rerun-if-changed`，默认全量监控关闭，漏掉的路径变化便不会触发重跑，可能复用陈旧产物；要么完整声明，要么全部不声明使用默认。",
        "把 build.rs 的普通依赖写进 `[dependencies]`：它们必须放到 `[build-dependencies]`。",
        "在 build.rs 里做运行期才该做的事（联网探测、读用户配置）：它应只负责确定性生成与探测。"
    ],
    "exercise": {
        "prompt": "写一个函数 `generate_consts(version: &str) -> String` 返回一段 Rust 源码文本 `pub const VERSION: &str = \"...\";`，并在 main 中打印该文本，模拟 build.rs 生成代码。",
        "hint": "用 `format!` 拼出带转义引号的源码字符串即可。",
        "answer": "fn generate_consts(version: &str) -> String {\n    format!(\"pub const VERSION: &str = {:?};\", version)\n}\n\nfn main() {\n    let generated = generate_consts(\"0.1.0\");\n    println!(\"生成代码: {}\", generated);\n    println!(\"该文本会写入 OUT_DIR 再由 include! 引入\");\n}\n"
    },
    "runtime": "cargo",
    "files": {
        "Cargo.toml": "[package]\nname = \"lesson-009-build\"\nversion = \"0.1.0\"\nedition = \"2021\"\nbuild = \"build.rs\"\ndefault-run = \"lesson-009-build\"\n",
        "build.rs": "use std::env;\nuse std::fs;\nuse std::path::PathBuf;\n\nfn main() {\n    let version = env::var(\"CARGO_PKG_VERSION\").unwrap_or_else(|_| \"0.0.0\".into());\n    let out_dir = PathBuf::from(env::var(\"OUT_DIR\").expect(\"OUT_DIR\"));\n    let code = format!(\"pub const VERSION: &str = {:?};\\n\", version);\n    fs::write(out_dir.join(\"version.rs\"), code).expect(\"write generated\");\n    println!(\"cargo:rerun-if-changed=build.rs\");\n}\n",
        "src/main.rs": "PLACEHOLDER_MAIN_009",
        "src/bin/generated.rs": "// 单独的 bin 演示 build.rs 写入 OUT_DIR 后由 include! 消费。\n// 默认 bin 仍是 src/main.rs（与课程 code 一致）。\ninclude!(concat!(env!(\"OUT_DIR\"), \"/version.rs\"));\n\nfn main() {\n    println!(\"generated to: {}\", VERSION);\n}\n"
    },
    "projectOutput": "lesson-009-build v0.1.0\nbuild.rs 在编译本包前由 cargo 运行，写文件到 OUT_DIR\n",
    "verify": "run"
},
{
    "id": 10,
    "title": "文档注释与 `cargo doc`",
    "level": "beginner",
    "domain": "toolchain-cargo",
    "summary": "用 `///` 与 `//!` 写出可生成的 API 文档，并让文档示例通过 doctest 验证正确性。",
    "concepts": ["/// 文档注释", "//! 模块文档", "cargo doc", "doctest", "文档内代码块"],
    "objective": "能为函数与模块写出结构化文档注释，理解文档代码块会成为可运行的 doctest。",
    "prerequisites": ["004"],
    "explain": "文档注释有两种：`///` 附着在紧随其后的项上，`//!` 描述所在模块或 crate 本身。cargo doc 会把它们渲染为 HTML；`cargo doc --open` 直接打开。文档中的围栏代码块默认会被 `cargo test` 当作 doctest 编译并运行（可加 `no_run`、`ignore`、`should_panic` 标注行为）。这意味着文档示例必须真的能编译，否则测试失败——把示例当作契约是 Rust 的一大优势。文档注释支持 Markdown，惯例是先一句摘要、再 `# Examples`、`# Panics`、`# Errors`、`# Safety` 等小节。对库而言，模块级 `//!` 通常是入口文档，应说明用途、边界与快速上手示例。",
    "code": "// 文档注释演示：/// 描述函数，main 里复用同一逻辑验证输出。\n// 在真实库 crate 中，下方注释会渲染进 cargo doc 并作为 doctest 运行。\n\n/// 返回 `value` 落在闭区间 `[low, high]` 内时的比例位置（0.0..=1.0）。\n///\n/// # Examples\n///\n/// ```\n/// assert_eq!(position(5, 0, 10), 0.5);\n/// ```\nfn position(value: i32, low: i32, high: i32) -> f64 {\n    if high == low {\n        return 0.0;\n    }\n    (value - low) as f64 / (high - low) as f64\n}\n\nfn main() {\n    println!(\"position(5, 0, 10) = {}\", position(5, 0, 10));\n    println!(\"position(0, 0, 10) = {}\", position(0, 0, 10));\n    println!(\"文档内代码块会被 cargo test 当作 doctest 运行\");\n}\n",
    "output": "position(5, 0, 10) = 0.5\nposition(0, 0, 10) = 0\n文档内代码块会被 cargo test 当作 doctest 运行\n",
    "pitfalls": [
        "文档示例随手写而无法编译：doctest 会执行它们，错的示例等于测试失败。",
        "用 `///` 描述模块：模块头应放在模块声明前，或改用模块内的 `//!`。",
        "写得过于笼统：文档应说明边界、可 panic 条件与错误返回，而不是重复函数名。"
    ],
    "exercise": {
        "prompt": "为函数 `clamp(value, low, high)` 编写文档注释（含摘要与 `# Examples` 代码块，示例要能通过），并写 main 打印 `clamp(15, 0, 10)` 的结果。",
        "hint": "文档代码块里用 `assert_eq!` 断言，正文实现用 `value.max(low).min(high)`。",
        "answer": "/// 把 `value` 限制到 `[low, high]` 区间内。\n///\n/// # Examples\n///\n/// ```\n/// assert_eq!(clamp(15, 0, 10), 10);\n/// assert_eq!(clamp(-3, 0, 10), 0);\n/// ```\nfn clamp(value: i32, low: i32, high: i32) -> i32 {\n    value.max(low).min(high)\n}\n\nfn main() {\n    println!(\"{}\", clamp(15, 0, 10));\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 11,
    "title": "阅读编译器错误：E0xxx 分类与最小复现",
    "level": "beginner",
    "domain": "toolchain-cargo",
    "summary": "建立“读错误→抽最小复现→定点修复”的流程，认识借用、类型、所有权三类常见错误码。",
    "concepts": ["E0502", "E0382", "E0308", "最小复现", "编译器建议"],
    "objective": "能根据错误编号快速定位问题类别，并写出最小复现来隔离原因。",
    "prerequisites": ["004"],
    "explain": "rustc 的错误编号按类别组织：E0308 是类型不匹配，E0382 是使用已移动的值，E0502/E0499 是借用规则冲突，E0106 是缺少生命周期。读错误时先看最后一行 summary，再看下方 `note` 与 `help` 的修复建议，注意箭头标注的冲突点是“谁先借用、谁后借用”。最有效的调试手段是最小复现：删掉与错误无关的代码，直到剩下 5~10 行仍能复现，此时原因往往一目了然。许多借用错误本质是“别名 + 可变”同时存在，修复方向通常是缩小借用范围、先复制、或重构为分阶段处理。养成不猜、按编号分类的习惯，能显著缩短排错时间。",
    "code": "// 本程序演示三类常见报错的“正确版本”：\n//   E0382 使用已移动的值 -> 改为借用\n//   E0502 可变与不可变借用冲突 -> 先取值再可变操作\n//   E0308 类型不匹配 -> 显式转换\n\nfn sum_len(words: &[String]) -> usize {\n    words.iter().map(|w| w.len()).sum()\n}\n\nfn main() {\n    let words = vec![String::from(\"rust\"), String::from(\"ownership\")];\n    // E0382 修复：传引用而非移动\n    println!(\"total_len = {}\", sum_len(&words));\n\n    // E0502 修复：先取出长度，结束不可变借用后再可变操作\n    let first_len = words[0].len();\n    let mut counts = vec![first_len];\n    counts.push(words[1].len());\n    println!(\"counts = {:?}\", counts);\n\n    // E0308 修复：显式 as 转换\n    let ratio = counts[1] as f64 / counts[0] as f64;\n    println!(\"ratio = {:.2}\", ratio);\n}\n",
    "output": "total_len = 13\ncounts = [4, 9]\nratio = 2.25\n",
    "pitfalls": [
        "只看第一行不看 help：`help:` 行通常直接给出可行修复，先读它再决定方案。",
        "在完整大文件里猜错误：不先做最小复现，会浪费大量时间在无关代码上。",
        "用 clone 粗暴绕过借用错误：能用借用表达就别复制，否则掩盖设计问题并带来性能损失。"
    ],
    "exercise": {
        "prompt": "下面的意图是“统计字符串数组总长度并在之后继续使用该数组”。写出不会触发 E0382 的正确程序并打印总长度与首元素长度。",
        "hint": "把 `&[String]` 作为参数，调用处传引用，避免所有权被移走。",
        "answer": "fn total_len(words: &[String]) -> usize {\n    words.iter().map(|w| w.len()).sum()\n}\n\nfn main() {\n    let words = vec![String::from(\"rust\"), String::from(\"borrow\")];\n    println!(\"total_len = {}\", total_len(&words));\n    println!(\"first_len = {}\", words[0].len());\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 12,
    "title": "单元测试与集成测试入口",
    "level": "beginner",
    "domain": "toolchain-cargo",
    "summary": "用 `#[cfg(test)] mod tests` 写单元测试，用 `tests/` 目录写集成测试，理解二者可见性差异。",
    "concepts": ["#[test]", "#[cfg(test)]", "tests/ 目录", "cargo test", "可见性"],
    "objective": "能分别写出单元测试与集成测试，并说清为什么集成测试只能访问 crate 的公开 API。",
    "prerequisites": ["004"],
    "explain": "单元测试写在被测代码同一文件里的 `#[cfg(test)] mod tests { ... }` 中，用 `use super::*;` 引入父模块项，因此可以测试私有函数；`#[cfg(test)]` 保证它们只在测试构建中存在。集成测试放在 crate 根目录的 `tests/` 下，每个文件是一个独立 crate，通过 `use 包名::...` 调用公开 API，用来验证外部使用者的真实视角。`cargo test` 会依次运行单元测试、集成测试和 doctest；`#[test]` 函数**不带参数**，返回值是 `()`，或者返回实现了 `Termination` 的类型（常用 `Result<(), E>`，返回 `Err` 即判定失败）；失败也可用 `assert!`/`assert_eq!`/`panic!` 表达。测试名应描述行为而非实现细节，例如 `rejects_empty_input`。一个良好的测试集合同时覆盖正常路径、边界值和错误路径。",
    "code": "// 单文件版：把单元测试和可运行输出放在一起。\n// 真实项目里集成测试位于 tests/ 目录（见 files 映射）。\n\nfn digits_sum(text: &str) -> Option<u32> {\n    let mut sum = 0u32;\n    let mut seen = false;\n    for c in text.chars() {\n        if let Some(d) = c.to_digit(10) {\n            sum += d;\n            seen = true;\n        }\n    }\n    if seen { Some(sum) } else { None }\n}\n\nfn main() {\n    println!(\"digits_sum(\\\"a1b2c3\\\") = {:?}\", digits_sum(\"a1b2c3\"));\n    println!(\"digits_sum(\\\"abc\\\")    = {:?}\", digits_sum(\"abc\"));\n    println!(\"cargo test 会同时跑单元/集成/文档测试\");\n}\n\n#[cfg(test)]\nmod tests {\n    use super::*;\n\n    #[test]\n    fn sums_all_digits() {\n        assert_eq!(digits_sum(\"a1b2c3\"), Some(6));\n    }\n\n    #[test]\n    fn returns_none_without_digits() {\n        assert_eq!(digits_sum(\"abc\"), None);\n    }\n}\n",
    "output": "digits_sum(\"a1b2c3\") = Some(6)\ndigits_sum(\"abc\")    = None\ncargo test 会同时跑单元/集成/文档测试\n",
    "pitfalls": [
        "在集成测试里访问私有项：集成测试是外部 crate，只能看到 `pub` API。",
        "测试之间共享可变全局状态：测试可能并行执行，共享状态会造成随机失败。",
        "只测正常路径：应同时覆盖边界（空输入）与错误路径，否则回归无人发现。"
    ],
    "exercise": {
        "prompt": "写函数 `max_of(xs: &[i32]) -> Option<i32>`，并写一个单元测试模块验证 `max_of(&[3,1,4,1,5])` 与 `max_of(&[])`。",
        "hint": "用 `xs.iter().copied().max()`；空切片自然返回 None。",
        "answer": "fn max_of(xs: &[i32]) -> Option<i32> {\n    xs.iter().copied().max()\n}\n\nfn main() {\n    println!(\"{:?}\", max_of(&[3, 1, 4, 1, 5]));\n    println!(\"{:?}\", max_of(&[]));\n}\n\n#[cfg(test)]\nmod tests {\n    use super::*;\n\n    #[test]\n    fn finds_max() {\n        assert_eq!(max_of(&[3, 1, 4, 1, 5]), Some(5));\n    }\n\n    #[test]\n    fn empty_is_none() {\n        assert_eq!(max_of(&[]), None);\n    }\n}\n"
    },
    "runtime": "cargo",
    "files": {
        "Cargo.toml": "[package]\nname = \"lesson-012-tests\"\nversion = \"0.1.0\"\nedition = \"2021\"\n",
        "src/main.rs": "PLACEHOLDER_MAIN_012",
        "tests/integration.rs": "// 集成测试：作为外部使用者，通过运行编译出的二进制并校验 stdout。\nuse std::process::Command;\n\n#[test]\nfn binary_prints_expected_digits() {\n    let exe = env!(\"CARGO_BIN_EXE_lesson-012-tests\");\n    let out = Command::new(exe).output().expect(\"run binary\");\n    let stdout = String::from_utf8_lossy(&out.stdout);\n    assert!(stdout.contains(\"Some(6)\"));\n    assert!(stdout.contains(\"None\"));\n}\n"
    },
    "projectOutput": "digits_sum(\"a1b2c3\") = Some(6)\ndigits_sum(\"abc\")    = None\ncargo test 会同时跑单元/集成/文档测试\n",
    "verify": "test"
},
{
    "id": 13,
    "title": "基准与性能测量：`criterion` 思路与手写计时",
    "level": "intermediate",
    "domain": "toolchain-cargo",
    "summary": "在没有外部基准库时，用 `Instant` 手写可重复的计时框架，理解预热、重复与统计口径。",
    "concepts": ["Instant", "black_box", "预热", "中位数", "基准陷阱"],
    "objective": "能写一个确定性可重复的计时函数，并解释为什么需要预热与多次采样取最小值。",
    "prerequisites": ["012"],
    "explain": "性能测量最怕噪声与优化消除。标准库提供 `std::time::Instant` 记录单调时钟，但若编译器发现结果未被使用，会把整个计算优化掉，因此要用 `std::hint::black_box` 强制保留。专业基准库（如 criterion）会做自动预热、多轮采样、统计显著性检验与异常值剔除；它的核心方法论可以手工近似：先跑若干次预热让缓存与分支预测进入稳态，再采集多轮样本，报告最小值或中位数而非单次值。还要固定输入规模、记录构建档（debug 与 release 差距往往数倍）、避免在计时区间里做 I/O。基准结论必须带“环境 + 档位 + 输入规模”三个前提，否则不可信。",
    "code": "use std::hint::black_box;\nuse std::time::Instant;\n\nfn sum_of_squares(n: u64) -> u64 {\n    let mut acc = 0u64;\n    for i in 1..=n {\n        acc += i * i;\n    }\n    acc\n}\n\nfn bench(label: &str, rounds: usize, mut f: impl FnMut() -> u64) {\n    // 预热：让缓存与分支预测进入稳态\n    for _ in 0..3 {\n        black_box(f());\n    }\n    let mut best = u128::MAX;\n    for _ in 0..rounds {\n        let start = Instant::now();\n        black_box(f());\n        let elapsed = start.elapsed().as_nanos();\n        if elapsed < best {\n            best = elapsed;\n        }\n    }\n    println!(\"{}: {} 轮采样完成\", label, rounds);\n    let _ = best;\n}\n\nfn main() {\n    bench(\"sum_of_squares(10000)\", 5, || sum_of_squares(10_000));\n    println!(\"verify(sum_of_squares(1000)) = {}\", sum_of_squares(1000));\n    println!(\"计时取最小值, 输入与档位固定才可比较\");\n}\n",
    "output": "sum_of_squares(10000): 5 轮采样完成\nverify(sum_of_squares(1000)) = 333833500\n计时取最小值, 输入与档位固定才可比较\n",
    "pitfalls": [
        "不写 black_box：优化器可能删除未使用的计算，测出的是 0 ns 假象。",
        "只测一次就下结论：单次结果受调度与缓存影响极大，至少要预热后多轮取最小值或中位数。",
        "用不同档位混比：debug 与 release 结论不可混用，必须注明构建参数。"
    ],
    "exercise": {
        "prompt": "写函数 `fib_loop(n: u64) -> u64`（迭代法），并用与示例相同的 bench 结构测量它，最后打印 fib_loop(30) 的结果。",
        "hint": "迭代维护两个变量 (a, b)，循环 n 次更新。计时区间里只放计算与 black_box。",
        "answer": "use std::hint::black_box;\nuse std::time::Instant;\n\nfn fib_loop(n: u64) -> u64 {\n    let (mut a, mut b) = (0u64, 1u64);\n    for _ in 0..n {\n        let t = a + b;\n        a = b;\n        b = t;\n    }\n    a\n}\n\nfn bench(label: &str, rounds: usize, mut f: impl FnMut() -> u64) {\n    for _ in 0..3 { black_box(f()); }\n    let mut best = u128::MAX;\n    for _ in 0..rounds {\n        let start = Instant::now();\n        black_box(f());\n        best = best.min(start.elapsed().as_nanos());\n    }\n    println!(\"{}: {} 轮采样完成\", label, rounds);\n    let _ = best;\n}\n\nfn main() {\n    bench(\"fib_loop(30)\", 5, || fib_loop(30));\n    println!(\"fib_loop(30) = {}\", fib_loop(30));\n}\n"
    },
    "runtime": "cargo",
    "files": {
        "Cargo.toml": "[package]\nname = \"lesson-013-bench\"\nversion = \"0.1.0\"\nedition = \"2021\"\n",
        "src/main.rs": "use std::hint::black_box;\nuse std::time::Instant;\n\nfn sum_of_squares(n: u64) -> u64 {\n    let mut acc = 0u64;\n    for i in 1..=n {\n        acc += i * i;\n    }\n    acc\n}\n\nfn bench(label: &str, rounds: usize, mut f: impl FnMut() -> u64) {\n    for _ in 0..3 {\n        black_box(f());\n    }\n    let mut best = u128::MAX;\n    for _ in 0..rounds {\n        let start = Instant::now();\n        black_box(f());\n        let elapsed = start.elapsed().as_nanos();\n        if elapsed < best {\n            best = elapsed;\n        }\n    }\n    println!(\"{}: {} 轮采样完成\", label, rounds);\n    let _ = best;\n}\n\nfn main() {\n    bench(\"sum_of_squares(10000)\", 5, || sum_of_squares(10_000));\n    println!(\"verify(sum_of_squares(1000)) = {}\", sum_of_squares(1000));\n}\n"
    },
    "projectOutput": "verify(sum_of_squares(1000)) = 333833500\n",
    "verify": "build"
},
{
    "id": 14,
    "title": "发布与分发：`cargo publish` 前置检查",
    "level": "intermediate",
    "domain": "toolchain-cargo",
    "summary": "梳理发布一个 crate 前的完整清单：元数据、许可证、文档、版本与 dry-run 验证。",
    "concepts": ["cargo publish", "cargo package", "元数据", "许可证", "版本不可撤回"],
    "objective": "能列出一份可执行的发布检查清单，并解释 `cargo package` 与 `cargo publish --dry-run` 的差异。",
    "prerequisites": ["013"],
    "explain": "发布到 crates.io 是不可撤销的：同一个版本号一旦上传就不能删除重发（只能 yank）。因此发布前必须：`cargo package --list` 检查会打包哪些文件（.gitignore 覆盖的内容不进包），补全 `description`/`license`（或 `license-file`）/`repository`/`keywords`/`categories` 等元数据，确认版本号遵循语义化版本并相对上次有实质变化，运行 `cargo test --all-features` 与 `cargo doc` 确认无警告，再用 `cargo publish --dry-run` 走一遍打包与校验流程。依赖若来自本地 `path`，发布前需同时指定 `version`，否则别人无法解析。对内部二进制不发布时，也应保持这些纪律，方便 `cargo install --path` 与后续拆分。",
    "code": "// 单文件：把发布检查清单变成可运行的自检输出。\n// 真实发布命令与元数据见 files 映射中的 Cargo.toml。\n\n#[derive(Debug, Clone, Copy, PartialEq)]\nenum Bump {\n    Major,\n    Minor,\n    Patch,\n}\n\nfn next_version(current: &str, bump: Bump) -> String {\n    let mut parts: Vec<u32> = current.split('.').map(|p| p.parse().unwrap_or(0)).collect();\n    while parts.len() < 3 {\n        parts.push(0);\n    }\n    match bump {\n        Bump::Major => { parts[0] += 1; parts[1] = 0; parts[2] = 0; }\n        Bump::Minor => { parts[1] += 1; parts[2] = 0; }\n        Bump::Patch => { parts[2] += 1; }\n    }\n    format!(\"{}.{}.{}\", parts[0], parts[1], parts[2])\n}\n\nfn main() {\n    let current = \"0.1.0\";\n    println!(\"patch: {} -> {}\", current, next_version(current, Bump::Patch));\n    println!(\"minor: {} -> {}\", current, next_version(current, Bump::Minor));\n    println!(\"major: {} -> {}\", current, next_version(current, Bump::Major));\n    println!(\"发布前: package --list, test --all-features, doc, publish --dry-run\");\n}\n",
    "output": "patch: 0.1.0 -> 0.1.1\nminor: 0.1.0 -> 0.2.0\nmajor: 0.1.0 -> 1.0.0\n发布前: package --list, test --all-features, doc, publish --dry-run\n",
    "pitfalls": [
        "以为上传后还能改：同一版本不可重传，只能 yank；发错版本号就得发新版本。",
        "path 依赖不带 version 就发布：下游无法解析该依赖，注册表会在校验时拒绝或运行时报错。",
        "忽略 `package --list`：被 .gitignore 或 exclude 误伤的文件不会进包，可能导致编译失败。"
    ],
    "exercise": {
        "prompt": "写函数 `is_prerelease(version: &str) -> bool`，判断版本号是否含 `-` 预发布段（如 `1.0.0-beta.1`），并检验三个样本。",
        "hint": "直接 `version.split_once('-').is_some()`；同时可顺便检查主干是否三段式。",
        "answer": "fn is_prerelease(version: &str) -> bool {\n    version.split_once('-').is_some()\n}\n\nfn main() {\n    for v in [\"1.0.0\", \"1.0.0-beta.1\", \"2.3.4-rc.2\"] {\n        println!(\"{:<12} prerelease={}\", v, is_prerelease(v));\n    }\n}\n"
    },
    "runtime": "cargo",
    "files": {
        "Cargo.toml": "[package]\nname = \"lesson-014-publish\"\nversion = \"0.1.0\"\nedition = \"2021\"\ndescription = \"QFLI Rust curriculum lesson 014: publish checklist demo\"\nlicense = \"CC-BY-4.0\"\nrepository = \"https://example.invalid/qfli\"\nkeywords = [\"curriculum\", \"qfli\"]\ncategories = [\"development-tools\"]\n\n[[bin]]\nname = \"lesson-014-publish\"\npath = \"src/main.rs\"\n",
        "src/main.rs": "fn is_prerelease(version: &str) -> bool {\n    version.split_once('-').is_some()\n}\n\nfn main() {\n    for v in [\"1.0.0\", \"1.0.0-beta.1\", \"2.3.4-rc.2\"] {\n        println!(\"{:<12} prerelease={}\", v, is_prerelease(v));\n    }\n}\n"
    },
    "projectOutput": "1.0.0        prerelease=false\n1.0.0-beta.1 prerelease=true\n2.3.4-rc.2   prerelease=true\n",
    "verify": "build"
},
]
