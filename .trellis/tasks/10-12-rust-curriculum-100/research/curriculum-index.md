# Rust curriculum index (166 lessons)

One row per lesson. IDs are fixed: `rust-tutorial-NNN` / `rust-example-NNN`
(NNN = 001..166). `Runtime` uses the label taxonomy in `design.md`:
`desktop` (plain `rustc`, no crates) · `cargo` (needs a manifest, possibly
crates) · `miri-candidate` (std-only, *possibly* runs on the packaged engine but
**unverified** until device/engine evidence exists) · `external` (needs absent
toolchain/crate; taught, not run here).

`Import` is the representation the importer must produce (see
`research/import-representation.md`):
- `single` — one `.rs` file written by `CodeImportService`, Cargo manifest added
  by `RustProjectStore` (`.qfli` custom `[[bin]]` when the file is not
  `src/main.rs`).
- `cargo-multi` — single entry `.rs` in `code`, plus a **`cargoFiles` bundle** in
  `inputFixtures` (documented convention) that the Rust importer expands after
  the shared single-file write.

Defaults: `Prereq` is the immediately preceding lesson ID unless a concept from
another lesson is required, in which case the specific ID is listed.

## Domain A — Toolchain, Cargo, first programs (001–014)

| ID | Title | Prereq | Example | Runtime | Import |
| --- | --- | --- | --- | --- | --- |
| 001 | Rust 与工具链概览：rustup/rustc/cargo 的职责 | — | 001 | desktop | single |
| 002 | 第一个程序：编译、运行与 `cargo run` | 001 | 002 | desktop | single |
| 003 | Cargo 项目结构：`Cargo.toml`、`src/`、`target/` | 002 | 003 | desktop | single |
| 004 | `cargo check` / `build` / `clippy` / `fmt` 工作流 | 003 | 004 | desktop | single |
| 005 | edition、profile 与 release 优化开关 | 003 | 005 | cargo | cargo-multi |
| 006 | 依赖与版本：语义化版本、`Cargo.lock`、feature 开关 | 005 | 006 | cargo | cargo-multi |
| 007 | workspace 与多 crate 布局 | 006 | 007 | cargo | cargo-multi |
| 008 | 条件编译：`cfg`、`cfg!(...)`、目标平台分支 | 004 | 008 | desktop | single |
| 009 | 环境变量与构建脚本 `build.rs` 基础 | 007 | 009 | cargo | cargo-multi |
| 010 | 文档注释与 `cargo doc` | 004 | 010 | desktop | single |
| 011 | 阅读编译器错误：E0xxx 分类与最小复现 | 004 | 011 | desktop | single |
| 012 | 单元测试与集成测试入口 | 004 | 012 | cargo | cargo-multi |
| 013 | 基准与性能测量：`criterion` 思路与手写计时 | 012 | 013 | cargo | cargo-multi |
| 014 | 发布与分发：`cargo publish` 前置检查 | 013 | 014 | cargo | cargo-multi |

## Domain B — Syntax, types, control flow (015–032)

| ID | Title | Prereq | Example | Runtime | Import |
| --- | --- | --- | --- | --- | --- |
| 015 | 标量与字面量：整数溢出、`as` 转换 | 002 | 015 | desktop | single |
| 016 | 元组、数组与解构 | 015 | 016 | desktop | single |
| 017 | 切片 `&[T]` 与子切片 | 016 | 017 | desktop | single |
| 018 | 字符串 `String` vs `&str`：编码与边界 | 016 | 018 | desktop | single |
| 019 | 变更性、遮蔽与作用域 | 015 | 019 | desktop | single |
| 020 | `if` / `else if` 作为表达式 | 019 | 020 | desktop | single |
| 021 | 三种循环：`loop`/`while`/`for` 与循环标签 | 020 | 021 | desktop | single |
| 022 | `match` 基础：穷尽性与通配 | 020 | 022 | desktop | single |
| 023 | `if let` / `while let` / `let else` | 022 | 023 | desktop | single |
| 024 | 函数、参数与返回类型 | 019 | 024 | desktop | single |
| 025 | 复合类型：struct 定义与实例化 | 024 | 025 | desktop | single |
| 026 | 方法、关联函数与 `impl` | 025 | 026 | desktop | single |
| 027 | 枚举与携带数据 | 026 | 027 | desktop | single |
| 028 | 类型别名、常量与静态变量 | 024 | 028 | desktop | single |
| 029 | 强类型新类型模式（newtype） | 027 | 029 | desktop | single |
| 030 | 运算符重载预告：`Add` 背后的 trait | 026 | 030 | desktop | single |
| 031 | 格式化输出：`Display`/`Debug`/格式说明符 | 025 | 031 | desktop | single |
| 032 | 实战：一个无依赖的命令行计算器 | 022 | 032 | desktop | single |

## Domain C — Ownership, borrowing, lifetimes (033–052)

| ID | Title | Prereq | Example | Runtime | Import |
| --- | --- | --- | --- | --- | --- |
| 033 | 所有权三原则与 move 语义 | 018 | 033 | desktop | single |
| 034 | `Clone` 与 `Copy`：何时自动复制 | 033 | 034 | desktop | single |
| 035 | 函数中的所有权转移与返还 | 033 | 035 | desktop | single |
| 036 | 引用与借用规则（可变/不可变） | 033 | 036 | desktop | single |
| 037 | 借用检查器与 NLL 直觉 | 036 | 037 | desktop | single |
| 038 | 悬垂引用与生命周期引入 | 036 | 038 | desktop | single |
| 039 | 生命周期标注：函数签名 | 038 | 039 | desktop | single |
| 040 | 结构体中的借用与生命周期参数 | 039 | 040 | desktop | single |
| 041 | 生命周期省略规则 | 039 | 041 | desktop | single |
| 042 | `'static` 与字符串字面量 | 041 | 042 | desktop | single |
| 043 | 切片 API 与借用拆分 | 037 | 043 | desktop | single |
| 044 | 可变借用的独占性与别名禁令 | 037 | 044 | desktop | single |
| 045 | 迭代式修改：借用与索引的取舍 | 043 | 045 | desktop | single |
| 046 | `split_at_mut` 与安全拆分借用 | 044 | 046 | desktop | single |
| 047 | 生命周期与返回引用：常见错误修复 | 040 | 047 | desktop | single |
| 048 | 内部可变性预告：为何需要 `RefCell` | 044 | 048 | desktop | single |
| 049 | 所有权在集合中的传播 | 045 | 049 | desktop | single |
| 050 | `Cow` 与按需借用 | 042 | 050 | desktop | single |
| 051 | 借用检查器实战：重构一段报错代码 | 047 | 051 | desktop | single |
| 052 | 实战：不带依赖的词频统计（借用优化版） | 049 | 052 | desktop | single |

## Domain D — Structs, enums, pattern matching (053–068)

| ID | Title | Prereq | Example | Runtime | Import |
| --- | --- | --- | --- | --- | --- |
| 053 | `Debug`/`PartialEq`/`Clone` 派生 | 025 | 053 | desktop | single |
| 054 | `Default` 与构建器模式 | 053 | 054 | desktop | single |
| 055 | 枚举建模状态机 | 027 | 055 | desktop | single |
| 056 | `match` 解构：结构体、枚举、嵌套 | 055 | 056 | desktop | single |
| 057 | 匹配守卫与 `@` 绑定 | 056 | 057 | desktop | single |
| 058 | `Option<T>` 的完整处理 | 056 | 058 | desktop | single |
| 059 | `Result<T, E>` 的完整处理 | 058 | 059 | desktop | single |
| 060 | 用枚举替代布尔与魔法值 | 055 | 060 | desktop | single |
| 061 | 递归数据结构与 `Box` 预告 | 055 | 061 | desktop | single |
| 062 | 模式匹配中的引用与 `ref` | 056 | 062 | desktop | single |
| 063 | `matches!` 与谓词风格 | 056 | 063 | desktop | single |
| 064 | 状态机实战：交通灯 / 词法扫描 | 060 | 064 | desktop | single |
| 065 | 错误建模：领域错误枚举 | 059 | 065 | desktop | single |
| 066 | 不可变更新：结构体更新语法 | 054 | 066 | desktop | single |
| 067 | 密封模式与 `#[non_exhaustive]` 概念 | 055 | 067 | desktop | single |
| 068 | 实战：命令解析器（枚举 + 匹配） | 064 | 068 | desktop | single |

## Domain E — Traits, generics, trait objects (069–084)

| ID | Title | Prereq | Example | Runtime | Import |
| --- | --- | --- | --- | --- | --- |
| 069 | 定义与实现 trait | 026 | 069 | desktop | single |
| 070 | 默认方法与方法解析 | 069 | 070 | desktop | single |
| 071 | 泛型函数与单态化 | 070 | 071 | desktop | single |
| 072 | trait 约束（bound）语法 | 071 | 072 | desktop | single |
| 073 | `where` 子句与可读性 | 072 | 073 | desktop | single |
| 074 | `impl Trait` 参数与返回值 | 072 | 074 | desktop | single |
| 075 | trait 对象 `dyn Trait` 与动态分发 | 074 | 075 | desktop | single |
| 076 | 对象安全（object safety）规则 | 075 | 076 | desktop | single |
| 077 | `Box<dyn Trait>` 与异构集合 | 075 | 077 | desktop | single |
| 078 | 关联类型 vs 泛型参数 | 073 | 078 | desktop | single |
| 079 | 常用标准 trait：`From`/`Into`/`TryFrom` | 074 | 079 | desktop | single |
| 080 | `Display`/`Debug`/`FromStr` 协同 | 079 | 080 | desktop | single |
| 081 | 派生宏与 `derive` 的边界 | 080 | 081 | desktop | single |
| 082 | blanket impl 概念与 coherence | 079 | 082 | desktop | single |
| 083 | 扩展 trait（extension trait）模式 | 070 | 083 | desktop | single |
| 084 | 实战：可插拔的序列化抽象（无外部 crate） | 077 | 084 | desktop | single |

## Domain F — Collections, iterators, closures (085–098)

| ID | Title | Prereq | Example | Runtime | Import |
| --- | --- | --- | --- | --- | --- |
| 085 | `Vec<T>`：容量、增长与切片 | 017 | 085 | desktop | single |
| 086 | `HashMap` / `BTreeMap` 选型 | 085 | 086 | desktop | single |
| 087 | `HashSet` / `BTreeSet` | 086 | 087 | desktop | single |
| 088 | 迭代器协议：`Iterator` 与 `next` | 085 | 088 | desktop | single |
| 089 | 适配器：`map`/`filter`/`flat_map`/`zip` | 088 | 089 | desktop | single |
| 090 | 消费器：`fold`/`collect`/`sum`/`any`/`all` | 089 | 090 | desktop | single |
| 091 | `collect` 到多种目标类型 | 090 | 091 | desktop | single |
| 092 | 惰性求值与迭代器链性能 | 089 | 092 | desktop | single |
| 093 | 闭包：捕获与环境 | 088 | 093 | desktop | single |
| 094 | `Fn` / `FnMut` / `FnOnce` | 093 | 094 | desktop | single |
| 095 | 自定义迭代器：`Iterator` 实现 | 090 | 095 | desktop | single |
| 096 | `VecDeque` / `BinaryHeap` 使用场景 | 086 | 096 | desktop | single |
| 097 | 排序、去重与自定义比较 | 087 | 097 | desktop | single |
| 098 | 实战：日志聚合与 Top-K 统计 | 096 | 098 | desktop | single |

## Domain G — Errors, modules, crates, testing (099–112)

| ID | Title | Prereq | Example | Runtime | Import |
| --- | --- | --- | --- | --- | --- |
| 099 | `panic!` vs `Result`：边界与策略 | 059 | 099 | desktop | single |
| 100 | `?` 运算符与错误传播 | 099 | 100 | desktop | single |
| 101 | 自定义错误类型（手写，无非派生 crate） | 100 | 101 | desktop | single |
| 102 | `From` 转换与错误聚合 | 101 | 102 | desktop | single |
| 103 | `Box<dyn Error>` 与动态错误 | 101 | 103 | desktop | single |
| 104 | 模块系统：`mod`、`pub`、路径 | 012 | 104 | desktop | single |
| 105 | 文件即模块与 `mod.rs` 演进 | 104 | 105 | cargo | cargo-multi |
| 106 | crate 与库/二进制双目标 | 105 | 106 | cargo | cargo-multi |
| 107 | 单元测试 vs 集成测试 vs 文档测试 | 105 | 107 | cargo | cargo-multi |
| 108 | 测试组织：夹具、辅助模块、`#[should_panic]` | 107 | 108 | desktop | single |
| 109 | 断言与快照式期望输出 | 108 | 109 | desktop | single |
| 110 | 公共 API 设计与 semver 影响 | 106 | 110 | cargo | cargo-multi |
| 111 | 文档即测试与示例可运行性 | 107 | 111 | cargo | cargo-multi |
| 112 | 实战：可测试的 CSV 解析库（std-only） | 109 | 112 | cargo | cargo-multi |

## Domain H — Smart pointers, interior mutability (113–124)

| ID | Title | Prereq | Example | Runtime | Import |
| --- | --- | --- | --- | --- | --- |
| 113 | `Box<T>`：堆分配与递归类型 | 061 | 113 | desktop | single |
| 114 | `Deref` 与 `DerefMut` | 113 | 114 | desktop | single |
| 115 | `Drop` 与 RAII 清理 | 114 | 115 | desktop | single |
| 116 | `Rc<T>` 共享所有权 | 113 | 116 | desktop | single |
| 117 | `RefCell<T>` 运行时借用检查 | 048 | 117 | desktop | single |
| 118 | `Rc<RefCell<T>>` 组合与循环引用风险 | 117 | 118 | desktop | single |
| 119 | `Weak<T>` 打破循环 | 118 | 119 | desktop | single |
| 120 | `Cell<T>` 与 `Copy` 内部可变性 | 117 | 120 | desktop | single |
| 121 | `Arc<T>` 与跨线程共享 | 116 | 121 | desktop | single |
| 122 | `Mutex<T>` / `RwLock<T>` 基础 | 121 | 122 | desktop | single |
| 123 | 内部可变性设计取舍 | 120 | 123 | desktop | single |
| 124 | 实战：观察者/共享缓存（`Rc<RefCell>` 版） | 119 | 124 | desktop | single |

## Domain I — Concurrency: threads, channels, Send + Sync (125–137)

| ID | Title | Prereq | Example | Runtime | Import |
| --- | --- | --- | --- | --- | --- |
| 125 | `thread::spawn` 与 `join` | 024 | 125 | desktop | single |
| 126 | `move` 闭包与线程所有权 | 125 | 126 | desktop | single |
| 127 | 通道 `mpsc`：发送与接收 | 126 | 127 | desktop | single |
| 128 | 多生产者与消息协议设计 | 127 | 128 | desktop | single |
| 129 | 作用域线程 `thread::scope` | 127 | 129 | desktop | single |
| 130 | `Send` 与 `Sync` 的含义 | 128 | 130 | desktop | single |
| 131 | 共享状态：`Arc<Mutex<T>>` 模式 | 122 | 131 | desktop | single |
| 132 | 死锁、锁顺序与粒度 | 131 | 132 | desktop | single |
| 133 | 原子类型与内存顺序入门 | 130 | 133 | desktop | single |
| 134 | `Ordering` 语义：Relaxed/Acquire/Release/SeqCst | 133 | 134 | miri-candidate | single |
| 135 | 无锁计数器与 ABA 概念 | 134 | 135 | desktop | single |
| 136 | 线程池与任务队列（std-only） | 132 | 136 | desktop | single |
| 137 | 实战：并行文件处理管线（无外部 crate） | 136 | 137 | desktop | single |

## Domain J — Async / Future (138–146)

| ID | Title | Prereq | Example | Runtime | Import |
| --- | --- | --- | --- | --- | --- |
| 138 | 异步模型与同步阻塞的区别 | 130 | 138 | desktop | single |
| 139 | `Future` trait 与 `poll` 手写实现 | 138 | 139 | desktop | single |
| 140 | `Context`、`Waker` 与唤醒协议 | 139 | 140 | desktop | single |
| 141 | `Pin`/`Unpin`：自引用与移动安全 | 140 | 141 | desktop | single |
| 142 | `async`/`await` 脱糖与状态机 | 141 | 142 | desktop | single |
| 143 | 组合 Future：手写 `join`/`select` | 142 | 143 | desktop | single |
| 144 | 取消与超时：`select` 语义与取消安全 | 143 | 144 | desktop | single |
| 145 | 简易执行器（单线程 reactor 骨架） | 144 | 145 | desktop | single |
| 146 | 异步运行时生态与 tokio 概念（需依赖，标注） | 145 | 146 | cargo | cargo-multi |

## Domain K — Macros (147–152)

| ID | Title | Prereq | Example | Runtime | Import |
| --- | --- | --- | --- | --- | --- |
| 147 | 声明宏 `macro_rules!` 入门 | 024 | 147 | desktop | single |
| 148 | 宏片段、重复与卫生性 | 147 | 148 | desktop | single |
| 149 | 用宏消除样板：`vec!` 风格实现 | 148 | 149 | desktop | single |
| 150 | 属性宏与派生宏概念（需 proc-macro crate） | 149 | 150 | cargo | cargo-multi |
| 151 | `proc-macro` 工程布局与依赖（标注，不在此环境运行） | 150 | 151 | external | cargo-multi |
| 152 | 调试宏展开：`cargo expand` 思路 | 148 | 152 | cargo | cargo-multi |

## Domain L — Unsafe, FFI, performance, capstones (153–166)

| ID | Title | Prereq | Example | Runtime | Import |
| --- | --- | --- | --- | --- | --- |
| 153 | `unsafe` 的边界与安全不变式 | 113 | 153 | desktop | single |
| 154 | 原始指针与 `from_raw_parts` | 153 | 154 | miri-candidate | single |
| 155 | `unsafe fn` 契约与文档化不变式 | 154 | 155 | desktop | single |
| 156 | 安全抽象封装 unsafe（`split_at_mut` 复刻） | 155 | 156 | desktop | single |
| 157 | FFI 基础：`extern "C"` 与 ABI | 155 | 157 | cargo | cargo-multi |
| 158 | 调用 C 函数与 `#[link]`（需 libc，标注） | 157 | 158 | external | cargo-multi |
| 159 | 从 C 调用 Rust：`#[no_mangle]` 与导出 | 157 | 159 | cargo | cargo-multi |
| 160 | `repr(C)` 与结构体布局 | 157 | 160 | desktop | single |
| 161 | 性能剖析：测量、热点与优化取舍 | 092 | 161 | cargo | cargo-multi |
| 162 | 零拷贝与 `&[u8]` 解析 | 161 | 162 | desktop | single |
| 163 | 缓存友好与数据布局 | 161 | 163 | desktop | single |
| 164 | 综合项目一：多文件 CLI 待办工具 | 112 | 164 | cargo | cargo-multi |
| 165 | 综合项目二：并发词频统计（线程 + 通道） | 137 | 165 | cargo | cargo-multi |
| 166 | 综合项目三：异步任务队列 + 安全 FFI 边界 | 146 | 166 | cargo | cargo-multi |

## Totals

- Lessons: **166** (`001..166`), well above the 120 minimum, giving async,
  macros, unsafe/FFI, performance and the three capstones independent slots.
- Examples: **166**, one per lesson, `sourceLessonId` == lesson id.
- Domains: 12; every domain ≥ 12 lessons.
- Runtime tally: `desktop` = 140, `cargo` = 22, `miri-candidate` = 2,
  `external` = 2.
- Import tally: `single` = 142, `cargo-multi` = 24 (examples only; every lesson
  is `single` — see `research/import-representation.md`).

## Compatibility with the replaced IDs

The current shared catalog already uses `rust-tutorial-001..100` and
`rust-example-001..100` (contiguous, no gaps; lesson ids
`rust-tutorial-NNN-lesson`). The new curriculum **retains that exact ID space**
and extends it: for NNN `001..100` the same ID strings are kept while their
content is replaced by the new curriculum, and `101..166` are appended. No ID is
renamed or removed from the shared catalog, so any external bookmark to
`rust-tutorial-0NN` still resolves. See `design.md §9 ID compatibility` for the
validator rule (ids exactly `001..166`, gap-free, duplicate-free).
