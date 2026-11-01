# 编译器边界冻结态审查（loader / lib / debug）

## 审查范围

- 分支：`feat/rust-offline-ide-20261022`。
- 对象：`native/miri_adapter/src` 的 3 个文件。
- 这 3 个文件是 `compiler_boundary.rs`、`lib.rs`、`debug.rs`。
- 方式：只读源码与补丁文本。
- 本审查不运行构建。
- 本审查不读 `native/build`。
- 本审查不读 OHOS SDK。
- 本审查不用 WSL。
- 本审查不接设备。
- 本审查不创建子进程。
- 产物：本文件。
- 其他文件不改。

## 冻结身份

| 文件 | 字节 | SHA-256 |
| --- | --- | --- |
| `compiler_boundary.rs` | 28213 | `f5ed454e2fe4bf3556cd828d299ccc486c77c51ce1a40d81068eccda9bfbff42` |
| `lib.rs` | 37326 | `2bd562c164ddc973984f8b2f2678b14aa28f8ea46be62425f9c0de30b17b0ecb` |
| `debug.rs` | 50479 | `531962b102ceb9bf4c645acf9a75855f82d5ca7f767c0ec28fa057ec098ae357` |

- `lib.rs` 与 `debug.rs` 与前一次快照相同。
- 只有 `compiler_boundary.rs` 变化。
- 冻结后本审查又改该文件 1 行。
- 改动是 `ensure_refusal` 的接收者。
- 上表是该改动之后的最新哈希。

## 稳定性

- p2 落地 UTF-8 修复前，模块哈希为 `072380da…`。
- 那一段本审查不轮询。
- 收到 p2 完成通知后，取当前字节。
- 两次取样相隔 8 秒。
- 两次哈希一致。
- 判定：字节稳定，可作为冻结基线。

## 结论

| 编号 | 项目 | 状态 |
| --- | --- | --- |
| 1 | 无效 UTF-8 归类 | 已修复 |
| 2 | OpenHarmony 门控 | 通过 |
| 3 | 架构常量 | 通过 |
| 4 | 失败关闭 | 通过，已更正 |
| 5 | 调试入口接线 | 通过 |
| 6 | 主机工作目录 | 通过 |
| 7 | pinned API 绑定 | 通过，静态 |
| 8 | 导出 ABI 计数 | 27，与规范一致 |
| 9 | `ensure_refusal` 接收者 | 已修复 |

## 缺陷 1：无效 UTF-8 归类（已修复）

- 旧版本：`Loader::read_file` 在解码失败时调用 `deny(...)`。
- 旧版本同时还记录一个 `BoundaryFailure`。
- 后果：学习者的编码错误显示为内部错误。
- 后果：学习者丢失原有的 UTF-8 诊断。
- 现版本：`compiler_boundary.rs:658` 返回 `InvalidData`。
- 现版本：该分支不再调用 `deny`。
- 现版本：该分支不再调用 `record`。
- 现版本：`read()` 仍对真实拒绝调用 `deny(...)`。
- 证据：真实拒绝在 `:385`。
- 证据：真实拒绝在 `:391`。
- 证据：真实拒绝在 `:394`。
- 证据：真实拒绝在 `:401`。
- 证据：真实拒绝在 `:403`。
- 证据：新增注释写明原因。
- 证据：parser retry 仍走 `read_binary_file`。
- 判断：修复与本审查的建议一致。
- 判断：作用域只限 UTF-8 归类。
- 判断：路径策略拒绝仍然留痕。

## 缺陷 2：OpenHarmony 门控（已通过）

- 现版本用 `cfg!(all(target_os = "linux", target_env = "ohos"))`。
- 现版本 `target_env = "ohos"` 出现 20 次。
- 现版本只有 1 处 `target_os = "ohos"`。
- 该处只是注释。
- 该注释说明为何不能用它。
- 证据：说明在 `compiler_boundary.rs:69` 到 `:75`。
- 证据：`base/linux.rs:7` 设 `os: Os::Linux`。
- 证据：`linux_ohos.rs:5` 只设 `env: Env::Ohos`。
- 证据：`Os` 枚举没有 `Ohos` 变体。
- 判断：通过。

## 缺陷 3：`ensure_refusal` 接收者类型（已修复）

- 该缺陷是真实编译阻断。
- 本审查先前漏掉了它。
- 先前报告把「失败关闭」判为通过。
- 该结论过宽，现在更正。
- 旧版本：`:357` 的接收者是 `&self`。
- 旧版本：`:360` 的 `Arc::clone(self)` 需要 `&Arc<Self>`。
- 后果：两者类型不匹配。
- 后果：该模块无法通过类型检查。
- 旁证：`:309` 的 `install` 用 `self: &Arc<Self>`。
- 旁证：`:347` 的 `Arc::clone(self)` 因此合法。
- 现版本：`:357` 改为 `self: &Arc<Self>`。
- 现版本：4 处调用点都不用改。
- 证据：调用点在 `:314`、`:319`、`:330`、`:340`。
- 证据：这 4 处都在 `install` 内。
- 证据：`ensure_refusal` 是私有项。
- 证据：外部没有调用者。
- 证据：`:360` 的 `Arc::clone(self)` 现在合法。
- 漏检原因：先前只检查控制流。
- 漏检原因：先前没检查接收者与函数体的配合。
- 来源：独立 pinned API 检查发现了该缺陷。
- 最终观察哈希：`f5ed454e2fe4bf3556cd828d299ccc486c77c51ce1a40d81068eccda9bfbff42`。
- 限制：本审查不编译。
- 限制：因此本条仍是静态判断。

## pinned rustc API 绑定

- 依据：`native/patches/rustc-1.98.1-embedded-compiler-boundary.patch`。
- 该文件 9083 字节。
- 该文件是 LF 行尾。
- 该文件 SHA-256 为 `7236eff6…`。
- 该哈希与 `compiler-build-provenance.md` 一致。
- 绑定一：`Options::embedded_boundary` 由 options.rs 新增。
- 绑定二：interface.rs 要求该标志必须有 `file_loader`。
- 绑定三：`read_binary_for_diagnostic` 走 `file_loader.read_binary_file`。
- 绑定四：parser retry 改用 `sm.read_binary_for_diagnostic`。
- 绑定五：creader.rs 拒绝 proc-macro crate。
- 绑定六：locator.rs 拒绝 SDylib。
- 绑定七：env.rs 拒绝环境变量回退。
- 模块侧：`config.opts.embedded_boundary = true` 出现 2 次。
- 模块侧：`Loader` 实现 4 个 `FileLoader` 方法。
- 判断：模块用到的 patched API 都在补丁内。
- 判断：补丁 hunk 行数自洽。
- 限制：本审查不应用补丁。
- 限制：本审查不构建。

## miri API 面

- 依据：`native/patches/miri-1.98.1-embedded-session.patch`。
- 该文件 51234 字节。
- 该文件 SHA-256 为 `7e22cbaf…`。
- lib.rs 用 `miri::entry_fn`。
- lib.rs 用 `miri::eval_entry`。
- lib.rs 用 `miri::sym::EXTRA_SYMBOLS`。
- debug.rs 用 `miri::create_ecx`。
- debug.rs 用 `miri::entry_fn`。
- debug.rs 用 `miri::Frame`。
- debug.rs 用 `miri::sym::EXTRA_SYMBOLS`。
- 该补丁新增 `create_ecx`、`entry_fn`、`eval_entry` 的再导出。
- 该补丁新增 `EmbeddedSession` 与 `EmbeddedFileSystem`。
- 判断：调试与运行都用补丁内的会话入口。
- 限制：本审查不读 miri 源树。

## 导出 ABI

- `lib.rs` 导出 10 个 C 符号。
- `debug.rs` 导出 15 个 C 符号。
- 另有 `qfli_miri_abi_version`，在 `lib.rs:378`。
- 另有 `qfli_miri_debug_capabilities`，在 `debug.rs:955`。
- 合计 27 个。
- 证据：`#[unsafe(no_mangle)]` 计数为 27。
- 证据：provenance 规范要求 27 个导出。
- 判断：数量一致。
- 限制：本审查不做 ELF 符号检查。

## 通过项

### 失败关闭

- `install` 在 `compiler_boundary.rs:309` 检查 4 类输入。
- 输入一：根无法打开。
- 输入二：主机不支持。
- 输入三：`remap_cwd_prefix` 非空。
- 输入四：`externs` 非空。
- 每类输入都记失败。
- 每类输入都调用 `fail_closed()`。
- `ensure_refusal` 在 `:357` 设 `embedded_boundary`。
- `ensure_refusal` 同时装入只读 `Loader`。
- 补丁让缺 `file_loader` 的会话报致命错误。
- 判断：控制流通过。
- 更正：接收者类型先前不通过，见缺陷 3。
- 更正：修复后本条才成立。
- 限制：类型检查未运行。

### 路径遍历

- 根描述符用 `O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC`。
- 中间分量在 `:476` 用 `O_DIRECTORY | O_NOFOLLOW`。
- 末分量在 `:500` 用 `O_NOFOLLOW | O_NONBLOCK`。
- 末分量紧接 `fstat`。
- 非普通文件一律拒绝。
- FIFO 因 `O_NONBLOCK` 不阻塞，随后立即拒绝。
- 单文件上限 8 MiB，见 `:42`。
- 单会话上限 64 MiB，见 `:44`。
- 读取用 `take(bound + 1)` 探测增长。
- 元数据长度不可信，`take` 才是判据。
- 路径分量自带分隔符时立即拒绝。
- 词法归一化拒绝越根的 `..`。
- 判断：通过。

### 初始化竞态

- 根路径先 `canonicalize`，再 `open`。
- 两步之间有一个窗口。
- 窗口内若换成符号链接，`O_NOFOLLOW` 让 `open` 失败。
- 窗口内若换成另一个目录，`open` 成功并锁住该目录。
- 根由应用选择，不由学习者输入。
- 判断：风险低。
- 判断：该风险未经运行时验证。
- 建议：加 `dev` 与 `ino` 检查。
- 建议：或改用 `openat2` 与 `RESOLVE_NO_SYMLINKS`。

### 分析不会误报干净

- `lib.rs:918` 让边界失败排在「干净」之前。
- `lib.rs:929` 让无诊断的静默中止记为内部错误。
- `lib.rs:771` 无条件调用 `install`。
- `lib.rs:884` 用 `CompilerBoundary::for_analysis`。
- 判断：通过。

### 调试入口接线

- `debug.rs:682` 无条件调用 `install`。
- `debug.rs:816` 用 `CompilerBoundary::for_run`。
- `debug.rs:862` 优先报告边界失败。
- `debug.rs` 没有自带的常量副本。
- 判断：通过。

### 主机工作目录

- 全仓搜索无 `set_current_dir`。
- 全仓搜索无 `env::set_var`。
- 全仓搜索无 `env::remove_var`。
- `working_directory` 在 `:271` 返回项目根。
- `Loader::current_directory` 用它当工作目录。
- 判断：通过。

## 架构常量

- 本次沿用既有 SDK 证据，不重读 SDK。
- aarch64 与 arm 用 ARM 布局。
- x86_64 用 asm-generic 布局。
- 内核侧与 libc 侧一致。
- 源码解析确认了 `openat` 符号。
- 证据：`build/offline-ide-audit/sdk-libc-openat-source-evidence.json`。
- 该解析只读 ELF64 小端表。
- 该解析不运行 SDK 里的程序。
- 该解析不启动原生进程。
- aarch64：表是 `SHT_DYNSYM`。
- aarch64：绑定是 `GLOBAL`。
- aarch64：类型是 `FUNC`。
- aarch64：可见性是 `DEFAULT`。
- aarch64：节号是 13。
- x86_64：表是 `SHT_DYNSYM`。
- x86_64：绑定是 `GLOBAL`。
- x86_64：类型是 `FUNC`。
- x86_64：可见性是 `DEFAULT`。
- x86_64：节号是 12。
- 判断：两架构都把 `openat` 公布为默认可见函数。
- 意义：模块的 `extern "C"` 声明有导出目标。
- 限制：本次未做链接检查。
- 限制：本次未做目标运行时检查。

| 架构 | 头文件 | 字节 | `O_DIRECTORY` | `O_NOFOLLOW` |
| --- | --- | --- | --- | --- |
| aarch64 | `bits/fcntl.h` | 839 | `040000` | `0100000` |
| arm | `bits/fcntl.h` | 842 | `040000` | `0100000` |
| x86_64 | `bits/fcntl.h` | 940 | `0200000` | `0400000` |

| 架构 | `libc.so` 字节 | `openat` 节 | 绑定 | 类型 | 可见性 |
| --- | --- | --- | --- | --- | --- |
| aarch64 | 72144 | 13 | `GLOBAL` | `FUNC` | `DEFAULT` |
| x86_64 | 84840 | 12 | `GLOBAL` | `FUNC` | `DEFAULT` |

- 代码取值见 `compiler_boundary.rs:576` 到 `:590`。
- `O_NONBLOCK` 是 `04000`。
- `O_CLOEXEC` 是 `02000000`。
- 判断：代码与头文件一致。

## 低风险观察

- 重复读同一文件会重复计入预算。
- 一个 8 MiB 文件读 8 次即用尽 64 MiB。
- parser retry 会再读一次同一文件。
- `locate` 的错误文本覆盖原始原因。
- `host_supported()` 的运行时检查排在根检查之后。
- 非 OHOS 主机的错误文本因此指向根。
- 代码两次装入 `O_CLOEXEC`，无害。
- `O_DIRECTORY` 有 `fstat` 检查。
- `O_NOFOLLOW` 没有运行时检查手段。
- 这些观察不构成阻断。

## 静态与实际构建的分界

- 本审查只读文本。
- 类型检查：未运行。
- 链接检查：未运行。
- 目标运行时检查：未运行。
- 运行时检查：未运行。
- 补丁应用：未运行。
- 以下结论不在本审查范围。
- 一：模块是否编译通过。
- 二：`openat` 是否链接成功。
- 三：运行时是否真正关闭。
- 四：设备上是否真正生效。
- 这些结论需要真实构建。
- 这些结论需要真实设备。
- 本审查不主张以上任何一项。

## 待办

- 本模块无阻塞项。
- p2 若再改本模块，需重跑本审查。
- 报告侧改动由 p2 负责。

## 证据

- 集成报告：`compiler-boundary-integration-current.md`。
- 编译器补丁：`rustc-1.98.1-embedded-compiler-boundary.patch`。
- miri 补丁：`miri-1.98.1-embedded-session.patch`。

| 文件 | 字节 | SHA-256 |
| --- | --- | --- |
| `compiler_boundary.rs` | 28213 | `f5ed454e2fe4bf3556cd828d299ccc486c77c51ce1a40d81068eccda9bfbff42` |
| `lib.rs` | 37326 | `2bd562c164ddc973984f8b2f2678b14aa28f8ea46be62425f9c0de30b17b0ecb` |
| `debug.rs` | 50479 | `531962b102ceb9bf4c645acf9a75855f82d5ca7f767c0ec28fa057ec098ae357` |
| `rustc-…-boundary.patch` | 9083 | `7236eff645ddf45eb87e78865a7d805a3443234e23c0855bee7956882c9989ee` |
| `miri-…-session.patch` | 51234 | `7e22cbafc2a0e1b0b93c1ff381b58c78e077e2724a9cc81cdcfd89337742d5a9` |
| `aarch64/bits/fcntl.h` | 839 | `66c37030b995805fb951315d3b0935d5fb6d0c3e1ddcf651ddf42c6e418b61b7` |
| `x86_64/bits/fcntl.h` | 940 | `3526dbb894665ab3b155a60d730c8527edce4fa597b3d5e51364a345d0cbdaeb` |
| `aarch64/libc.so` | 72144 | `298fb33338d06f07552606ff1ef2adbe42202e4ced3ab9400f26fe90bc38887c` |
| `x86_64/libc.so` | 84840 | `7a176e07e120b888ed1547401134e84b385775f9312ae1d40112d8c2f9051a4a` |