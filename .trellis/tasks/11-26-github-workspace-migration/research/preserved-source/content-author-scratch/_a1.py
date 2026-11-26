# -*- coding: utf-8 -*-
"""Lessons 001..007 (Domain A, part 1)."""

LESSONS = [
{
    "id": 1,
    "title": "Rust 与工具链概览：rustup / rustc / cargo 的职责",
    "level": "beginner",
    "domain": "toolchain-cargo",
    "summary": "用三个命令行工具串起 Rust 的日常开发闭环，理解谁负责安装、谁负责编译、谁负责工程管理。",
    "concepts": ["rustup", "rustc", "cargo", "toolchain", "edition 2021"],
    "objective": "能说清 rustup、rustc、cargo 各自的边界，并用一段标准库程序在脑中验证 rustc 的角色。",
    "prerequisites": [],
    "explain": "rustup 是工具链管理器：它下载并切换 stable/beta/nightly、安装目标平台的标准库、维护 doc 与 clippy 等组件。rustc 是单文件编译器：它把 .rs 源码编译成可执行文件，一次只处理一个 crate 根，掌管 edition、codegen 与诊断输出。cargo 是工程管理器：它读取 Cargo.toml，解析依赖、调用 rustc、组织 target/ 目录、运行测试与发布。三者关系是 rustup 提供 rustc+cargo，cargo 调度 rustc。日常你几乎总是敲 cargo，但理解 rustc 才能读懂单个退出码和错误编号。edition 是逐 crate 的语言版本开关，2021 版本引入了闭包捕获不透明化、数组 IntoIterator 等变化；编译单文件时用 `rustc --edition 2021 file.rs` 显式指定最安全。",
    "code": "// 单文件程序：由 rustc --edition 2021 直接编译，不经过 cargo。\n// 输出固定，不依赖任何环境探测。\n\nfn toolchain_roles() -> [(&'static str, &'static str); 3] {\n    [\n        (\"rustup\", \"下载并切换工具链、目标与组件\"),\n        (\"rustc\", \"把单个 crate 根编译成目标产物\"),\n        (\"cargo\", \"读取 Cargo.toml，调度 rustc 完成构建\"),\n    ]\n}\n\nfn main() {\n    println!(\"Rust 工具链三层职责:\");\n    for (i, (tool, role)) in toolchain_roles().iter().enumerate() {\n        println!(\"{}. {:<7} -> {}\", i + 1, tool, role);\n    }\n    println!(\"调用链: rustup 安装 -> cargo 编排 -> rustc 编译\");\n}\n",
    "output": "Rust 工具链三层职责:\n1. rustup  -> 下载并切换工具链、目标与组件\n2. rustc   -> 把单个 crate 根编译成目标产物\n3. cargo   -> 读取 Cargo.toml，调度 rustc 完成构建\n调用链: rustup 安装 -> cargo 编排 -> rustc 编译\n",
    "pitfalls": [
        "把 cargo 当成编译器：cargo 自己不编译，它只是 rustc 的调度器，报错编号仍来自 rustc。",
        "忘记 edition：默认 edition 可能与教程不一致，单文件编译请显式 `--edition 2021`。",
        "混淆工具链与组件：clippy、rust-analyzer、rustfmt 是可加装的组件，由 rustup 管理而非 cargo。"
    ],
    "exercise": {
        "prompt": "写一个单文件程序，用数组描述 rustup/rustc/cargo，并给每个工具加一段“它不负责什么”的说明，最后打印工具总数。",
        "hint": "用三元组数组 (工具, 负责, 不负责)，遍历时按固定宽度对齐输出。",
        "answer": "fn main() {\n    let rows = [\n        (\"rustup\", \"工具链/组件/目标\", \"编译代码\"),\n        (\"rustc\", \"单 crate 编译\", \"管理依赖\"),\n        (\"cargo\", \"工程与依赖编排\", \"下载工具链\"),\n    ];\n    for (tool, does, not) in rows {\n        println!(\"{:<7} 负责 {:<14} 不负责 {}\", tool, does, not);\n    }\n    println!(\"count={}\", rows.len());\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 2,
    "title": "第一个程序：编译、运行与 `cargo run`",
    "level": "beginner",
    "domain": "toolchain-cargo",
    "summary": "从 `fn main` 出发，比较 rustc 直接编译与 cargo run 两条路径，建立“编译产物在哪、为什么能跑”的具体印象。",
    "concepts": ["fn main", "可执行产物", "rustc 编译", "cargo run", "退出码"],
    "objective": "能独立写出并解释一个最小 Rust 程序的编译与运行过程，知道产物默认位置和 main 的签名要求。",
    "prerequisites": ["001"],
    "explain": "任何可执行 Rust 程序都从 `fn main()` 开始，它的返回类型是 `()`，或者实现了 Termination 的类型（如 `Result`）。`println!` 是标准库宏，末尾自动换行；字符串里的 `{}` 是占位符。rustc 直接编译时产物落在当前目录（默认文件名为源文件名去掉 .rs），cargo 则把产物放进 `target/debug/`。两者差异只在目录组织与依赖解析，语言语义完全一致。程序正常结束时进程退出码是 0；如果 main 返回 `Result::Err`，退出码非 0 并把错误打印到 stderr。先跑通并理解这条最短路径，后面所有课程都建立在它之上。",
    "code": "// 最小可执行程序：main 是入口，println! 是标准库宏。\n\nfn greeting(name: &str) -> String {\n    format!(\"你好，{}！\", name)\n}\n\nfn main() {\n    let message = greeting(\"Rustacean\");\n    println!(\"{}\", message);\n    println!(\"字符数 = {}\", message.chars().count());\n}\n",
    "output": "你好，Rustacean！\n字符数 = 13\n",
    "pitfalls": [
        "把 main 写成 `fn main() -> i32`：Rust 的入口不返回 i32，要表达失败请返回 `Result<(), E>`。",
        "以为 `$` 是占位符：Rust 用的是 `{}`/`{:?}`，`$` 是 shell 语法。",
        "在 cargo 项目里找不到产物：它在 `target/debug/<包名>`，不是源文件旁边。"
    ],
    "exercise": {
        "prompt": "写一个程序，定义函数 `double(n: i32) -> i32`，打印 `double(21)` 的结果，并额外打印一行说明该程序正常退出时退出码为 0。",
        "hint": "函数与 main 分开写，main 里先调用再打印结果行与说明行。",
        "answer": "fn double(n: i32) -> i32 {\n    n * 2\n}\n\nfn main() {\n    println!(\"double(21) = {}\", double(21));\n    println!(\"正常结束时退出码 = 0\");\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 3,
    "title": "Cargo 项目结构：`Cargo.toml`、`src/`、`target/`",
    "level": "beginner",
    "domain": "toolchain-cargo",
    "summary": "拆开一个 cargo 项目，讲清清单文件、源码目录和构建输出目录各自的职责，以及为什么不要提交 target。",
    "concepts": ["Cargo.toml", "src/main.rs", "target/", "package 元数据", ".gitignore"],
    "objective": "能解释 `cargo new` 生成的三块目录结构，指出可提交与不可提交的部分，并读懂最小清单的字段。",
    "prerequisites": ["002"],
    "explain": "`cargo new 项目名` 生成的最小项目有三部分：`Cargo.toml` 是清单，包含 `[package]` 段（name、version、edition）与 `[dependencies]` 段；`src/` 是源码目录，默认入口是 `src/main.rs`（二进制）或 `src/lib.rs`（库）；`target/` 是构建输出，包含编译产物、增量缓存和生成文件，属于可再生成内容，因此默认被 `.gitignore` 忽略。清单里 `version` 遵循语义化版本，`edition` 决定语言版本开关。`[dependencies]` 为空的包仍然成立——它只是不需要外部 crate。理解这套约定后，你就能读懂任何 Rust 仓库的顶层布局，并在新增文件时有明确的落点。",
    "code": "// 用单文件方式解析一个最小 Cargo.toml 的关键字段，\n// 把清单结构变成可观察输出（无需真实 manifest 也能运行）。\n\n#[derive(Debug)]\nstruct Manifest {\n    name: &'static str,\n    version: &'static str,\n    edition: &'static str,\n}\n\nfn main() {\n    let manifest = Manifest {\n        name: \"hello_qfli\",\n        version: \"0.1.0\",\n        edition: \"2021\",\n    };\n    println!(\"[package]\");\n    println!(\"name = {:?}\", manifest.name);\n    println!(\"version = {:?}\", manifest.version);\n    println!(\"edition = {:?}\", manifest.edition);\n    println!(\"目录职责: Cargo.toml=清单, src/=源码, target/=可再生成的构建产物\");\n}\n",
    "output": "[package]\nname = \"hello_qfli\"\nversion = \"0.1.0\"\nedition = \"2021\"\n目录职责: Cargo.toml=清单, src/=源码, target/=可再生成的构建产物\n",
    "pitfalls": [
        "把 `target/` 提交进版本库：它是可再生成的，体积大且含绝对路径，应始终忽略。",
        "在 `src/` 下乱放入口：默认识别 `main.rs`/`lib.rs`，自定义入口需要对应配置或额外 bin 声明。",
        "手改 version 却忽略它参与依赖解析：破坏语义化版本会让下游解析出错。"
    ],
    "exercise": {
        "prompt": "写程序读取（硬编码的）三个 crate 名称与版本，判断它们的版本号是否都符合 `major.minor.patch` 三段式并打印结论。",
        "hint": "用 `split('.')` 计数，`len() == 3` 且每段能 `parse::<u32>()` 即为合规。",
        "answer": "fn is_semver(v: &str) -> bool {\n    let parts: Vec<&str> = v.split('.').collect();\n    parts.len() == 3 && parts.iter().all(|p| p.parse::<u32>().is_ok())\n}\n\nfn main() {\n    let crates = [(\"serde\", \"1.0.200\"), (\"anyhow\", \"1.0\"), (\"rand\", \"0.8.5\")];\n    for (name, version) in crates {\n        println!(\"{:<8} {:<8} semver={}\", name, version, is_semver(version));\n    }\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 4,
    "title": "`cargo check` / `build` / `clippy` / `fmt` 工作流",
    "level": "beginner",
    "domain": "toolchain-cargo",
    "summary": "把日常开发的四个命令串成节奏：先快检类型、再构建、再静态建议、最后统一格式。",
    "concepts": ["cargo check", "cargo build", "clippy", "rustfmt", "增量编译"],
    "objective": "能按“快检→构建→建议→格式化”的顺序组织日常命令，并解释 `check` 比 `build` 快在哪。",
    "prerequisites": ["003"],
    "explain": "`cargo check` 只做类型检查与借用检查，不生成最终机器码，因此比 `build` 快很多，适合保存即跑；`cargo build` 生成调试产物到 `target/debug/`；`cargo build --release` 生成优化产物到 `target/release/`。`cargo clippy` 在编译基础上叠加 lint 静态建议，能发现低效或易错的惯用法，例如多余 clone、可简化判断；`cargo fmt` 用 rustfmt 统一代码风格，消除团队内的格式争论。推荐循环是：写代码时 `cargo check`，阶段性 `cargo clippy -- -D warnings`，提交前 `cargo fmt`，需要运行时 `cargo run`，发布时 `--release`。这些命令共享增量编译缓存，所以顺序执行并不会重复全部工作。",
    "code": "// 用一个小函数演示 check/build 的共同检查对象：类型与借用。\n// 代码被设计成 clippy 友好（无多余 clone、无不必要分配）。\n\nfn sum_even(numbers: &[i32]) -> i32 {\n    numbers.iter().filter(|n| *n % 2 == 0).sum()\n}\n\nfn describe(stage: &str, note: &str) {\n    println!(\"{:<18} {}\", stage, note);\n}\n\nfn main() {\n    describe(\"cargo check\", \"只做类型/借用检查，最快\");\n    describe(\"cargo build\", \"生成 target/debug 可执行文件\");\n    describe(\"cargo clippy\", \"追加静态建议 lint\");\n    describe(\"cargo fmt\", \"统一格式，不改语义\");\n    let data = [1, 2, 3, 4, 5, 6];\n    println!(\"偶数之和 = {}\", sum_even(&data));\n}\n",
    "output": "cargo check        只做类型/借用检查，最快\ncargo build        生成 target/debug 可执行文件\ncargo clippy       追加静态建议 lint\ncargo fmt          统一格式，不改语义\n偶数之和 = 12\n",
    "pitfalls": [
        "用 `cargo build` 当快速反馈：它对大项目明显更慢，日常保存后应先 `cargo check`。",
        "把 clippy 警告当噪音：`-D warnings` 能把它升级为错误，避免建议被长期忽略。",
        "以为 `cargo fmt` 会改逻辑：它只改排版，但运行前仍应先看 diff 或提交。"
    ],
    "exercise": {
        "prompt": "写函数 `is_sorted_desc(xs: &[i32]) -> bool` 判断序列是否严格降序，并在 main 中演示两个结果；要求实现不产生多余分配。",
        "hint": "用 `windows(2).all(|w| w[0] > w[1])`，对长度 0/1 自动返回 true。",
        "answer": "fn is_sorted_desc(xs: &[i32]) -> bool {\n    xs.windows(2).all(|w| w[0] > w[1])\n}\n\nfn main() {\n    println!(\"{}\", is_sorted_desc(&[9, 7, 5, 3]));\n    println!(\"{}\", is_sorted_desc(&[1, 3, 2]));\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 5,
    "title": "edition、profile 与 release 优化开关",
    "level": "beginner",
    "domain": "toolchain-cargo",
    "summary": "用 profile 控制调试与发布两套构建设置，理解 opt-level、debug、lto 对速度与体积的取舍。",
    "concepts": ["edition", "[profile.release]", "opt-level", "lto", "codegen-units"],
    "objective": "能写出一个 release profile 配置，并解释每个开关影响的维度（速度/体积/编译时间/调试信息）。",
    "prerequisites": ["003"],
    "explain": "edition 是语言层开关，逐 crate 生效，不会影响依赖行为；profile 是构建层开关，按 dev/release（以及自定义名）组织。`[profile.release]` 默认 `opt-level = 3`、`debug = false`。把 `opt-level` 调到 `\"s\"` 或 `\"z\"` 会优先减小体积；`lto = true` 启用链接时优化，常能再快一点但显著增加链接时间；`codegen-units = 1` 让每个 crate 用更少并行单元换取更好优化；`panic = \"abort\"` 去掉展开逻辑以减小体积，但会丢失 panic 时的栈展开与跨 FFI 边界的展开安全。理解这些旋钮，才能针对“发布包要小”与“桌面计算要快”两类目标分别调参。",
    "code": "// 单文件演示：不同“优化档位”影响的维度。\n// 真实开关写在下方 Cargo 项目的 Cargo.toml 里。\n\nfn knobs() -> [(&'static str, &'static str, &'static str); 4] {\n    [\n        (\"opt-level\", \"0/1/2/3/s/z\", \"越高越快，s/z 偏向小体积\"),\n        (\"lto\", \"false/true/thin\", \"链接时优化，编译更慢\"),\n        (\"codegen-units\", \"1..256\", \"越少越利于优化\"),\n        (\"panic\", \"unwind/abort\", \"abort 更小但不可恢复\"),\n    ]\n}\n\nfn main() {\n    println!(\"release profile 关键开关:\");\n    for (name, values, effect) in knobs() {\n        println!(\"- {:<14} {:<14} {}\", name, values, effect);\n    }\n    let mut sum: u64 = 0;\n    for i in 1..=1000u64 {\n        sum += i;\n    }\n    println!(\"固定计算 sum(1..=1000) = {}\", sum);\n}\n",
    "output": "release profile 关键开关:\n- opt-level      0/1/2/3/s/z    越高越快，s/z 偏向小体积\n- lto            false/true/thin 链接时优化，编译更慢\n- codegen-units  1..256         越少越利于优化\n- panic          unwind/abort   abort 更小但不可恢复\n固定计算 sum(1..=1000) = 500500\n",
    "pitfalls": [
        "以为改 edition 会改变依赖行为：edition 逐 crate 生效，依赖用它们自己的 edition 编译。",
        "盲目开 `panic = \"abort\"`：它让 panic 无法被捕获，也会影响与 C 的互操作边界。",
        "把 `lto = true` 当万能提速：它常增加大量链接时间，需与收益权衡。"
    ],
    "exercise": {
        "prompt": "写程序计算 1..=n 的平方和与和的平方，并打印两者之差（n=10），用以观察优化对纯计算的影响基线。",
        "hint": "分别用 map+sum 与先求和再平方，再用 i64 相减。",
        "answer": "fn main() {\n    let n: i64 = 10;\n    let sum_sq: i64 = (1..=n).map(|x| x * x).sum();\n    let sq_sum: i64 = (1..=n).sum::<i64>().pow(2);\n    println!(\"sum_sq = {}\", sum_sq);\n    println!(\"sq_sum = {}\", sq_sum);\n    println!(\"diff   = {}\", sq_sum - sum_sq);\n}\n"
    },
    "runtime": "cargo",
    "files": {
        "Cargo.toml": "[package]\nname = \"lesson-005-profiles\"\nversion = \"0.1.0\"\nedition = \"2021\"\n\n[profile.release]\nopt-level = 3\nlto = \"thin\"\ncodegen-units = 1\n",
        "src/main.rs": "fn main() {\n    let n: i64 = 10;\n    let sum_sq: i64 = (1..=n).map(|x| x * x).sum();\n    let sq_sum: i64 = (1..=n).sum::<i64>().pow(2);\n    println!(\"sum_sq = {}\", sum_sq);\n    println!(\"sq_sum = {}\", sq_sum);\n    println!(\"diff   = {}\", sq_sum - sum_sq);\n}\n"
    },
    "projectOutput": "PLACEHOLDER_005",
    "verify": "run"
},
{
    "id": 6,
    "title": "依赖与版本：语义化版本、`Cargo.lock`、feature 开关",
    "level": "beginner",
    "domain": "toolchain-cargo",
    "summary": "讲清依赖声明中 ^/~ 的语义、lock 文件的可复现作用，以及 feature 如何做到按需编译。",
    "concepts": ["语义化版本", "Cargo.lock", "default-features", "feature 联合", "可选依赖"],
    "objective": "能解读 `\"1.2\"` 一类版本约束的实际范围，并说明为何二进制项目要提交 lock 文件。",
    "prerequisites": ["005"],
    "explain": "Cargo 的版本要求是“兼容范围”而非精确版本。`^` 默认语义是“允许与要求版本兼容的更新”，但“哪一位是不兼容位”取决于版本号：当 major>0 时 `^1.2.3` 允许 `>=1.2.3, <2.0.0`；当 major==0 且 minor>0 时（pre-1.0）`^0.2.3` 允许 `>=0.2.3, <0.3.0`，因为 0.x 的 minor 才是破坏位；当 major==0 且 minor==0 时 `^0.0.3` 允许 `>=0.0.3, <0.0.4`，只有 patch 位。`~1.2.3` 允许 `>=1.2.3, <1.3.0`（锁定 minor）；`\"=1.2.3\"` 才精确锁死。解析结果写进 `Cargo.lock`，记录每个依赖的精确版本与校验和，保证团队与 CI 构建一致——二进制（应用）应提交 lock，库通常不提交以便下游统一解析。feature 是编译期开关：依赖可定义若干 feature，`default-features = false` 关闭默认集，再用 `features = [\"x\"]` 精确开启，从而裁剪代码与依赖体积。feature 还有联合语义：同一依赖被多处以不同 feature 引用时取并集。",
    "code": "// 单文件“版本范围判定器”：把 Cargo 的 ^ 语义变成可运行逻辑。\n// Cargo 的 `^` 兼容规则（关键：0.x 与 0.0.x 的 breaking 组件不同）：\n//   ^1.2.3 -> >=1.2.3, <2.0.0   （major>0：major 是不兼容位）\n//   ^0.2.3 -> >=0.2.3, <0.3.0   （major==0：minor 是不兼容位）\n//   ^0.0.3 -> >=0.0.3, <0.0.4   （major==0,minor==0：patch 是不兼容位）\n// 所以不能只比较“主版本相等 + 不低于最小版本”。\n\nfn parse(s: &str) -> (u64, u64, u64) {\n    let mut it = s.split('.').map(|p| p.parse::<u64>().unwrap_or(0));\n    (it.next().unwrap_or(0), it.next().unwrap_or(0), it.next().unwrap_or(0))\n}\n\nfn caret_upper_bound(req: (u64, u64, u64)) -> (u64, u64, u64) {\n    let (maj, min, pat) = req;\n    if maj > 0 {\n        (maj + 1, 0, 0)\n    } else if min > 0 {\n        (0, min + 1, 0)\n    } else {\n        (0, 0, pat + 1)\n    }\n}\n\nfn caret_allows(req: &str, candidate: &str) -> bool {\n    let r = parse(req);\n    let c = parse(candidate);\n    let upper = caret_upper_bound(r);\n    c >= r && c < upper\n}\n\nfn main() {\n    for (req, candidates) in [\n        (\"1.2.3\", [\"1.2.3\", \"1.9.0\", \"2.0.0\", \"1.2.2\"]),\n        (\"0.2.3\", [\"0.2.3\", \"0.2.9\", \"0.3.0\", \"0.2.2\"]),\n        (\"0.0.3\", [\"0.0.3\", \"0.0.4\", \"0.0.2\", \"0.1.0\"]),\n    ] {\n        for cand in candidates {\n            println!(\"^{} 允许 {} -> {}\", req, cand, caret_allows(req, cand));\n        }\n    }\n}\n",
    "output": "^1.2.3 允许 1.2.3 -> true\n^1.2.3 允许 1.9.0 -> true\n^1.2.3 允许 2.0.0 -> false\n^1.2.3 允许 1.2.2 -> false\n^0.2.3 允许 0.2.3 -> true\n^0.2.3 允许 0.2.9 -> true\n^0.2.3 允许 0.3.0 -> false\n^0.2.3 允许 0.2.2 -> false\n^0.0.3 允许 0.0.3 -> true\n^0.0.3 允许 0.0.4 -> false\n^0.0.3 允许 0.0.2 -> false\n^0.0.3 允许 0.1.0 -> false\n",
    "pitfalls": [
        "以为 `\"1.2\"` 就是 1.2.x：它允许到 `<2.0.0`，是向后兼容的宽范围。",
        "库项目提交 Cargo.lock：库应让下游统一解析版本；而应用项目应提交 lock 以复现构建。",
        "忽略 feature 联合：多个依赖方开启同名 feature 时会取并集，可能意外引入较重依赖。"
    ],
    "exercise": {
        "prompt": "写函数 `tilde_allows(req, candidate)` 实现 `~1.2.3` 语义（主次版本相同、补丁不低于要求），并用三个候选值验证。",
        "hint": "解析出 (major, minor, patch)，要求 candidate 前两段等于 req 前两段且 patch >= req.patch。",
        "answer": "fn parse(s: &str) -> (u32, u32, u32) {\n    let mut it = s.split('.').map(|p| p.parse::<u32>().unwrap_or(0));\n    (it.next().unwrap_or(0), it.next().unwrap_or(0), it.next().unwrap_or(0))\n}\n\nfn tilde_allows(req: &str, candidate: &str) -> bool {\n    let (rmaj, rmin, rpat) = parse(req);\n    let (cmaj, cmin, cpat) = parse(candidate);\n    cmaj == rmaj && cmin == rmin && cpat >= rpat\n}\n\nfn main() {\n    for c in [\"1.2.3\", \"1.2.9\", \"1.3.0\", \"1.2.0\"] {\n        println!(\"~1.2.3 -> {} => {}\", c, tilde_allows(\"1.2.3\", c));\n    }\n}\n"
    },
    "runtime": "cargo",
    "files": {
        "Cargo.toml": "[package]\nname = \"lesson-006-deps\"\nversion = \"0.1.0\"\nedition = \"2021\"\n\n[dependencies]\n# 演示用的真实依赖声明（构建本包时需要联网拉取）:\n# serde = { version = \"1\", default-features = false, features = [\"derive\"] }\n",
        "src/main.rs": "fn parse(s: &str) -> (u32, u32, u32) {\n    let mut it = s.split('.').map(|p| p.parse::<u32>().unwrap_or(0));\n    (it.next().unwrap_or(0), it.next().unwrap_or(0), it.next().unwrap_or(0))\n}\n\nfn caret_allows(req: &str, candidate: &str) -> bool {\n    let (rmaj, rmin, rpat) = parse(req);\n    let (cmaj, cmin, cpat) = parse(candidate);\n    cmaj == rmaj && (cmin, cpat) >= (rmin, rpat)\n}\n\nfn main() {\n    for c in [\"1.2.3\", \"1.9.0\", \"2.0.0\", \"1.2.2\"] {\n        println!(\"^1.2.3 允许 {} -> {}\", c, caret_allows(\"1.2.3\", c));\n    }\n}\n"
    },
    "projectOutput": "^1.2.3 允许 1.2.3 -> true\n^1.2.3 允许 1.9.0 -> true\n^1.2.3 允许 2.0.0 -> false\n^1.2.3 允许 1.2.2 -> false\n",
    "verify": "build"
},
{
    "id": 7,
    "title": "workspace 与多 crate 布局",
    "level": "intermediate",
    "domain": "toolchain-cargo",
    "summary": "用一个虚拟 workspace 把库与二进制拆开，理解共享 Cargo.lock 与相对依赖路径的协作方式。",
    "concepts": ["workspace", "[workspace] members", "虚拟清单", "path 依赖", "共享 lock"],
    "objective": "能设计一个 workspace 顶层清单，让 lib 与 bin 共享依赖解析，并说清 members 与 path 依赖的关系。",
    "prerequisites": ["006"],
    "explain": "workspace 是多个 crate 的构建单元集合。顶层 `Cargo.toml` 用 `[workspace] members = [\"crates/a\", \"crates/b\"]` 声明成员；顶层也可以是“虚拟清单”，即不含 `[package]`，只做聚合。成员间用 `path` 依赖互相引用，例如 `mylib = { path = \"../mylib\" }`。整个 workspace 共享一个 `Cargo.lock` 与一个 `target/`，因此同一份依赖解析结果在整个 workspace 内一致，避免不同成员各自解析出不同版本而带来的重复构建与特性不一致。但要注意：共享 lock 并不会阻止同一依赖在依赖图中以多个不兼容版本共存——Cargo 允许 `foo 1.x` 与 `foo 2.x` 同时存在（只要没有把它们当同一种类型使用）；若两个 crate 分别依赖同一 crate 的不同主版本，且需要互相传递该类型的值，就会出现“类型不兼容”的编译错误，此时应统一版本或做转换。`default-members` 可指定默认构建集合。多 crate 布局的价值在于：把可测试的纯逻辑放进 lib，把入口与 I/O 放进 bin，二者边界清晰、编译更快、以后也可发布到 crates.io。",
    "code": "// 单文件版本：演示“库逻辑 + 二进制入口”的分层语义。\n// 真实 workspace 的清单见下方 files 映射。\n\nmod mathlib {\n    pub fn gcd(mut a: u64, mut b: u64) -> u64 {\n        while b != 0 {\n            let t = a % b;\n            a = b;\n            b = t;\n        }\n        a\n    }\n\n    pub fn lcm(a: u64, b: u64) -> u64 {\n        if a == 0 || b == 0 { 0 } else { a / gcd(a, b) * b }\n    }\n}\n\nfn main() {\n    println!(\"gcd(48, 18)  = {}\", mathlib::gcd(48, 18));\n    println!(\"lcm(4, 6)    = {}\", mathlib::lcm(4, 6));\n    println!(\"分层: lib 放纯逻辑, bin 只做输入输出\");\n}\n",
    "output": "gcd(48, 18)  = 6\nlcm(4, 6)    = 12\n分层: lib 放纯逻辑, bin 只做输入输出\n",
    "pitfalls": [
        "成员 crate 各自带 target/ 与 lock：workspace 应共享它们，重复会拖慢构建并产生版本漂移。",
        "把业务逻辑写进 bin：逻辑放进 lib 才能被单元测试与复用，bin 应尽量薄。",
        "path 依赖写错相对路径：path 相对的是声明它的 Cargo.toml 所在目录，而非仓库根。"
    ],
    "exercise": {
        "prompt": "写单文件程序，定义一个 `mathlib` 模块提供 `is_prime(u32) -> bool`，在 main 中打印 2..=20 中的所有素数。",
        "hint": "试除到 n 的平方根，用 `i * i <= n` 控制循环即可。",
        "answer": "mod mathlib {\n    pub fn is_prime(n: u32) -> bool {\n        if n < 2 { return false; }\n        let mut i = 2;\n        while i * i <= n {\n            if n % i == 0 { return false; }\n            i += 1;\n        }\n        true\n    }\n}\n\nfn main() {\n    let primes: Vec<u32> = (2..=20).filter(|n| mathlib::is_prime(*n)).collect();\n    println!(\"{:?}\", primes);\n}\n"
    },
    "runtime": "cargo",
    "files": {
        "Cargo.toml": "[package]\nname = \"lesson-007-workspace\"\nversion = \"0.1.0\"\nedition = \"2021\"\n\n[[bin]]\nname = \"lesson-007-workspace\"\npath = \"src/main.rs\"\n\n[workspace]\nmembers = [\"crates/mathlib\", \"crates/cli\"]\ndefault-members = [\".\"]\nresolver = \"2\"\n",
        "src/main.rs": "PLACEHOLDER_MAIN_007",
        "crates/mathlib/Cargo.toml": "[package]\nname = \"mathlib\"\nversion = \"0.1.0\"\nedition = \"2021\"\n",
        "crates/mathlib/src/lib.rs": "pub fn gcd(mut a: u64, mut b: u64) -> u64 {\n    while b != 0 {\n        let t = a % b;\n        a = b;\n        b = t;\n    }\n    a\n}\n\npub fn lcm(a: u64, b: u64) -> u64 {\n    if a == 0 || b == 0 { 0 } else { a / gcd(a, b) * b }\n}\n",
        "crates/cli/Cargo.toml": "[package]\nname = \"cli\"\nversion = \"0.1.0\"\nedition = \"2021\"\n\n[dependencies]\nmathlib = { path = \"../mathlib\" }\n",
        "crates/cli/src/main.rs": "// 子 crate 的入口：演示跨 crate 的 path 依赖（非默认成员，需 --package cli 运行）。\nfn main() {\n    println!(\"gcd(48, 18)  = {}\", mathlib::gcd(48, 18));\n    println!(\"lcm(4, 6)    = {}\", mathlib::lcm(4, 6));\n}\n"
    },
    "projectOutput": "gcd(48, 18)  = 6\nlcm(4, 6)    = 12\n分层: lib 放纯逻辑, bin 只做输入输出\n",
    "verify": "run"
},
]
