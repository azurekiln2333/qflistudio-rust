# 全目标当前证据矩阵（只读审查，pi）

## 0. 本次范围与禁令

- 只读源码与既有报告。只写本报告一个文件。
- 未运行 SDK、native、WSL、构建、设备、Dart、Flutter、Python 脚本。
- 未运行任何 git 写操作。未提交。未推送。
- 未缩小范围。原附加需求全部保留在矩阵里。
- 未复用旧授权。历史交接与 556 授权记为已消费，不当作当前证据。
- 保留他人修改。工作区里 24 个已跟踪修改与 92 个未跟踪条目原样保留。
- 证据分级：
  - E1 已证实：已运行，且报告绑定当前字节。
  - E2 已证实但受限：已运行，范围有限或绑定较旧字节。
  - E3 仅源码：实现已存在，未运行。
  - E4 缺失：没有实现或没有证据。
  - E5 阻塞：外部条件未满足，本地无法推进。

## 1. 身份与基线

```text
仓库      D:/MyNewProjects/qfli_rust
分支      feat/rust-offline-ide-20261022（没有 upstream）
HEAD      553e13928bb4c9af3d1cccf615053c81bca91af5
核心仓库  D:/MyNewProjects/qfli_studio_core
核心 HEAD 2f9039a3ba95449679b17257b0313c1ee3644a2c
```

553e139 已提交的三语对象：

```text
README.md            df802cf1ee4ec8a05435f488dd3c8498227a4fa3
README.zh-TW.md      923fef24718e5e96afb10d151daec866007d05ed
README.en.md         ca332b9201e1568decd1dbbf4c81f03e3e08e8ee
scripts/ste-lint-zh.py  89ae07fb6ac419544dcefc8f3c62c221be632da3
.trellis/spec/guides/readme-language.md  （553e139 起进入版本控制）
```

工作区状态：24 个已跟踪修改，92 个未跟踪条目。

关键交付事实：**几乎全部新实现都在未跟踪文件里**。

```text
未跟踪的新源码（节选）
lib/native_miri_analyzer.dart          lib/rust_code_analyzer.dart
lib/rust_compiler_diagnostics.dart     lib/rust_debugger.dart
lib/rust_native_catalog.dart           lib/rust_native_catalog_audit.dart
lib/rust_native_feature_audit.dart     lib/rust_tool_utilities.dart
lib/rust_tools_tab.dart                lib/main_catalog_audit.dart
assets/content_rust/native_catalog.json
integration_test/rust_catalog_native_test.dart
native/miri_adapter/qfli_debug.h       native/miri_adapter/src/debug.rs
native/miri_adapter/debug_abi_test.c   native/miri_adapter/fs_abi_test.c
native/miri_adapter/analysis_abi_test.c
test/rust_debugger_test.dart           test/rust_native_feature_audit_test.dart
test/rust_workspace_integration_test.dart
```

已跟踪但未提交的修改（节选）：

```text
lib/main.dart                       +13 行：接入分析器与工具页
assets/content_rust/tutorials.json   已修改
assets/content_rust/examples.json    已修改
tool/rust_content/topics_001_084.json  已修改
tool/rust_content/topics_085_166.json  已修改
native/miri_adapter/src/lib.rs       已修改
native/miri_adapter/qfli_debug.h     未跟踪
ohos/entry/src/main/module.json5     已修改
```

含义：仓库历史只覆盖三语 README、linter 与语言契约。R1 到 R13 的实现与测试
都没有进入历史。全新检出拿不到当前工作区的功能。

## 2. 内容与调用的当前事实

```text
教程          166（rust-tutorial-001 到 166，每篇 1 课，课 id 唯一）
示例          166（rust-example-001 到 166）
配对          166/166。示例 sourceLessonId 全部命中课 id
Cargo 附带    23 个主题带 files。23 个都含 Cargo.toml 与 src/main.rs
示例附带      23 个示例带 cargoFiles
语言          language=rust，type=rust，单语言
等级          beginner 30，intermediate 58，advanced 78
运行标注      desktop 141，cargo 22，miri-candidate 2，external 1
新增主题      0 / 180
```

native 目录输入 `assets/content_rust/native_catalog.json`（未跟踪）：

```text
332 个用例 = 166 example + 166 answer
sourceSha256 绑定 tool/rust_content/topics_001_084.json
                      = d2fb3650b000f01377c552059662c66c6d735ae419cdb229dae43d346991901f
             绑定 tool/rust_content/topics_085_166.json
                      = 08ba5290964b63556aebb8abda4926cf0c39c86ac13821d6af1d83612f593f76
catalog 计数  lesson166，example166，answer166，bundle23，run332
guest 目标    x86_64-unknown-linux-gnu
stdout 断言   166 example 为 true。166 answer 为 false，expectedStdout 为 null
```

上面两个源文件哈希与当前工作区文件逐一相同。所以该输入绑定当前编写的主题源。

宿主报告 `build/offline-ide-audit/host-after-repairs.json`（10-23）：

```text
status            passed
scope             desktop host compilation；no mobile engine claim
compilerStatus    executed
passedLessons     166
attemptedPrograms 332
compiledPrograms  332
passedPrograms    332
mobileExecution   not_tested
inputSha256       与当前 topics_*.json 逐一相同
```

结论：宿主全量编译与运行有 E1 级证据，绑定当前编写源。移动端运行没有证据。

## 3. 需求矩阵

### 3.1 原始需求（umbrella R1 到 R13 与 Rust 本地 R1 到 R10）

```text
ID  需求                                当前证据                                     状态
R1  Trellis 与共享核专属写入            任务四件套齐；核心 2f9039a；写入按 C 单写者   E1
R2  全部既有示例/教程在当前 OHOS 跑通   宿主 332/332 通过；设备零运行                  E2/E5
R3  追加远超 100 条实质示例             166 基线不变；新增 0/180                      E4
R4  语言 chip 与标题语言圈              核心已实现过滤器与徽章；Rust 单语言无交集证据  E2
R5  语言独有工具平铺到工具页            RustToolsTab 已实现并接入；当前字节测试未跑    E3
R6  真实诊断、波浪线、Problems 导航     桌面分析器实现；移动分析器待跑；共享 UI 已实现 E3
R7  侧边栏展开保留与多根工作区          核心命名工作区已发布；Rust 消费回归未跑        E3
R8  可行离线调试与可用面板              核心面板已发布；Rust 调试器未接入且原生未打包  E3/E4
R9  各语言可用高亮                      核心 re_highlight 含 rust；Rust 消费证据缺失   E2
R10 C/C++ 自建头文件与混合编译           C 产物 200/200 宿主与 31 项桥接；设备未跑      E2/E5
R11 Python 沙箱模块与离线本地包          Python 1158/1158 宿主表示；设备未跑           E2/E5
R12 全部独立应用保持离线                 清单移除 INTERNET；离线门控审计通过           E1
R13 当前检查、标准提交与正常推送         HEAD 两个提交；4/5 远端哈希核验成功            E1/E5
```

### 3.2 用户点名的十组交付

```text
组  交付                    证据                                                          状态
1   OHOS 既有内容全量        native_catalog.json 332 用例已绑定源；设备报告不存在             E3/E5
2   180 新增门槛             0 条新增。门控在 R1 设备通过之后                                E4
3   平铺语言工具             lib/main.dart 已接 toolsTabBuilder；6 个工具测试未跑             E3
4   波浪线与 Problems        rust_code_analyzer + rust_compiler_diagnostics 已实现          E3
                            Problems 渲染属共享核，C 侧已发布
5   多根命名工作区与展开     核心 2f9039a 已发布；4 个 Rust 消费用例未跑                     E3
6   调试/面板/本地 Ports     核心 36697b0 已发布 6 类面板；调试器未接入                     E3/E4
                            原生调试 ABI 只在源码（16 个符号），不在任何库
7   高亮                     核心 rust 语法与主题存在；Rust 无消费者回归                    E2
8   跨产品分工               见第 4 节。每个产品自持运行时、内容与工具                     E2
9   离线                     module.json5 只留 READ_PASTEBOARD；面审计逐条门控             E1
10  标准提交与推送           2 个常规提交；4 个远端哈希核验。GitLab 未成功                  E1/E5
11  三语 README（追加）      三语对齐探针通过；linter 0 处发现                             E1
```

## 4. 跨产品分工与状态

分工依据：umbrella PRD（`qfli_c/.trellis/tasks/10-22-offline-standalone-ide/prd.md`）
与协调台账（`D:/MyNewProjects/qfli-core-release-sync.md`）。

```text
产品      任务目录                                     归属范围                          记录状态
C/C++     10-22-offline-standalone-ide                共享核单写者；内容、工具、头文件   宿主 200/200；+160 未编写；设备未跑
Rust      10-22-offline-ide-completeness              Rust 运行时/内容/工具/调试/分析   166 基线；+180 未编写；设备未跑
Python    10-22-python-offline-modules 等 5 个任务    模块、本地包、工具、分析器        宿主 1158/1158；签名 x64 HAP 为构建证据
Java      10-22-offline-ide-completeness              Java 运行时、内容、工具、分析     宿主 280/280；真机 x86_64 280/280 通过
JSON      10-22-offline-json-ide                       内容、工具、结构导航              340 示例（+240）；116/116 宿主；无产品远端
Dart      10-22-offline-ide-completeness              运行时、内容、工具                宿主 240 检查；打包 OHOS 未跑
Web       10-22-standalone-offline-ide                 运行时、内容、工具                481 语义目录；QuickJS 诊断 2/2；设备未跑
Go/Lua    10-22-* 等                                   各自运行时与内容                  本会话未核验
SQL/Note  10-22-*                                       各自运行时与内容                  本会话未核验
```

共享核分工的硬边界：

- 过滤器、徽章、explorer、工作区、分析器 API、高亮语法、面板归 C 单写者。
- 语言产物各产品自持。Rust 不改 C 源。C 不改 Rust 源。
- 设备窗口按队列轮转。Rust 当前没有设备窗口。
  当前排队记录：SQL122 之后 SQL527。目标 `192.168.68.207:46551` 报 TCP Offline，
  `COM3/COM4` UART Ready 为 unknown。没有任何可达目标。

## 5. 逐组细节

### 5.1 OHOS 既有内容全量（第 1 组）

- 编写源 166 主题。生成内容目录 166 教程与 166 示例。配对 166/166。
- 设备台账输入已写：332 用例，逐个带 sourceSha256、filesSha256、
  expectedExitCode 与 expectedStdout。
- 宿主运行记录 332/332 通过，且明确写 mobileExecution 为 not_tested。
- 设备侧报告文件不存在。工作区里搜不到 rust_catalog_audit.json。
- 阻塞：没有可达 OHOS 目标，没有签名配置窗口。
- 当前 `lib/main.dart` 只有 Android 把 runtimeStatus 标为 available。
  在 OHOS 上该值仍是 unavailable。这会决定内容页的状态标签。

### 5.2 180 新增门槛（第 2 组）

- 当前 166 主题。新增 0 条。
- 门控顺序正确：先完成既有内容设备通过，再追加 180 对。
- 未提前发布新主题。这一点与计划一致。

### 5.3 平铺语言工具（第 3 组）

- `lib/rust_tools_tab.dart` 已实现整数、位运算、字符串、Cargo 项目检查。
- `lib/main.dart` 当前工作区已接 toolsTabBuilder。改动未提交。
- 工具沿用共享核 ToolsGridSliver，没有二级页面。
- 测试文件已写：`test/rust_tools_tab_test.dart`、`test/rust_tool_utilities_test.dart`。
- 这两个测试在当前字节上未运行。

### 5.4 波浪线与 Problems（第 4 组）

- `lib/rust_code_analyzer.dart` 用 rustc 元数据模式取诊断，不运行程序。
- `lib/rust_compiler_diagnostics.dart` 做 UTF-16 半开区间映射。
- 移动端经 `lib/native_miri_analyzer.dart`。它要求 `qfli_miri_create_analysis`
  与 `qfli_miri_analyze` 两个符号。
- 打包的 OHOS 库确实导出这两个符号。见 5.8。
- 波浪线绘制与 Problems 列表由共享核负责。C 侧已发布对应实现。
- 当前字节的分析器测试、诊断测试与真机证据都未运行。

### 5.5 多根命名工作区与展开保留（第 5 组）

- 共享核已发布两层：`daddce2` 多根历史，`36697b0` 调试面板与保留工作区，
  `2f9039a` 命名会话默认开启与元数据刷新。
- `test/rust_workspace_integration_test.dart` 已写 4 个测试项，覆盖 5 个用例。
  含 1100 与 600 两个宽度下的命名保存与重开。
- 未运行。打包应用内操作无证据。
- 早前独立审查记录过一个次根运行缺陷（次根文件不能运行）。
  修复归属共享核。当前是否已修，本会话未核验。

### 5.6 调试、面板与本地 Ports（第 6 组）

共享核侧（`qfli_studio_core/lib/editor/editor_page.dart`）：

```text
_BottomPanel 现有值：none, terminal, ai, problems, debug,
                     output, debugConsole, ports
对应面板：EditorDebugPanel, EditorOutputPanel,
          EditorDebugConsolePanel, EditorPortsPanel
```

Rust 侧：

```text
lib/rust_debugger.dart（未跟踪）已实现，约 45 KB
它打开运行时库并要求 qfli_miri_debug_* 符号
lib/main.dart 没有设置 StudioProfile 的 debugger 字段
```

原生侧：

```text
native/miri_adapter/src/debug.rs     16 个 #[unsafe(no_mangle)] 导出（未跟踪）
native/miri_adapter/qfli_debug.h     16 个函数声明（未跟踪）
native/miri_adapter/debug_abi_test.c 用例（未跟踪）
```

打包的库不含任何 `qfli_miri_debug_*` 符号。见 5.8 的逐库字节扫描。

结论：面板容器已就绪。真实调试能力缺两环。一环是 Rust 档位接入，
另一环是原生调试库的构建与打包。两者都未完成。

本地 Ports：产品侧没有监听流程。共享核面板已存在。
早前审计记录：适配器运行在 Miri 默认隔离下，socket 调用直接失败。启用需三步：
放开隔离、提供产品流程、在 OHOS 恢复 INTERNET 权限。三步都未做。

### 5.7 高亮（第 7 组）

- 共享核 `lib/editor/highlight_themes.dart` 引入 `re_highlight` 的 rust 语言。
- 语法与主题归 C 单写者。C 已发布缺失语法补充（`43d145d` 系列）。
- Rust 仓库没有高亮消费者回归。`test/rust_content_pages_test.dart` 只写入
  language 字段，不断言徽章或 chip 渲染。
- 所以 Rust 侧高亮证据缺失。按 umbrella R9，这一项仍打开。

### 5.8 打包与原生字节（5.1、5.4、5.6 的共同前置）

```text
ohos/entry/libs/arm64-v8a/libqfli_miri.so
  sha256 3499632c08bbb25f6300d9ce9121d34d2fbd5d15279bc0b054bbc7765ad5af15
  mtime 2026-10-22 23:57
  与 assets/miri/manifest.json 的 nativeLibraries 项哈希相同
  导出：abi_version, create, create_with_backend, create_analysis,
        analyze, run, cancel, copy_output, result, destroy
  不导出：create_with_project, qfli_miri_debug_*

ohos/entry/libs/x86_64/libqfli_miri.so
  sha256 3cfdfc66cceb4a7f079715ff2d600bb3457f618c46d724f801cdfd6710846d83
  导出：同 arm64 的十个符号
  不在 manifest 里。HAP 只打 arm64。

android/app/src/main/jniLibs/arm64-v8a/libqfli_miri.so
  sha256 6c280fc7c89d1dc55e99a8145621ee030a74ebd531d95afd9f82ce59d4bf6714
  mtime 2026-10-02
  导出：无 create_analysis 与 analyze
  不导出：create_analysis, analyze, create_with_project, qfli_miri_debug_*

native/build/device/ohos-arm64/libqfli_miri.so
  sha256 d409527a6c5bba8c203fea862db98a16441429bfcff550c7407ecd16c40fd60b
  mtime 2026-10-15
  导出：无 create_analysis、analyze、create_with_project、qfli_miri_debug_*
```

要点：

- 分析扩展已进 OHOS 打包库。这一环有 E1 级字节证据。
- 项目根构造函数 `qfli_miri_create_with_project` 只在头文件与源码里。
  打包库不含它。规范与产物不一致。见 `native-runtime.md` 的加法构造约定。
- 调试符号不在任何已查库中。源码文件 mtime 晚于打包时间。
- Android 库停在 10-02，缺分析符号。
- `native/build/device/ohos-arm64` 里的库比打包库旧。

### 5.9 离线（第 9 组）

```text
ohos/entry/src/main/module.json5：requestPermissions 只剩 READ_PASTEBOARD
  第 37 行注释记录离线不变量与恢复条件
审查报告 .trellis/tasks/10-22-offline-ide-completeness/research/
        rust-offline-surface-audit.md 逐条列出可达面并给出门控证据
lib/main.dart：isOffline 为 true
lib/rust_terminal_commands.dart：拒绝联网 Cargo 命令
```

结论：离线审计为 E1 级源码证据。设备侧未复核。
注意：打包 HAP 需要重建后才会去掉 INTERNET。中间产物仍可能是旧的。

### 5.10 标准提交与推送（第 10 组）

```text
78fb7b1 之后新增两个提交
dd3343b docs: add trilingual README and controlled Chinese checks
553e139 docs: align README terminology and platform limits
```

推送证据目录：`build/offline-ide-audit/readme-push-553e13928bb4/`。

```text
远端      推送          核验             exactHashVerified
GitHub    exit 0        ls-remote 命中    true
Gitee     exit 0        ls-remote 命中    true
GitCode   exit 0        ls-remote 命中    true
CNB       exit 0        ls-remote 命中    true
GitLab    exit 128      exit 2            false
GitLab SSH exit 124     超时              false
```

GitLab 推送失败原因是凭据不可交互：日志写 `Cannot prompt because user
interactivity has been disabled` 与 `unable to get password`。
SSH 备用通道超时。鉴权处理仍在进行。

所以当前是 **4 个远端确认成功，1 个未成功**。不得声称五个远端全部成功。
分支也没有配置 upstream。

### 5.11 三语 README（追加要求）

553e139 已落实上一轮审查的多数结论：

```text
已落实
英文：It never presents a failed analysis as a clean result.
英文：Bitwise operations first convert the operands to the selected type.
英文：Long-press Run ... / Long-pressing Run does not change ...
英文：iOS packaging 措辞不再与简体冲突
简体：新增「该变量不配置程序运行器。」
简体：跑 → 运行
繁体：桌面端檢查呼叫真實的 cargo metadata
繁体：它再比對程式輸出與宣告輸出
三语：文件结尾补换行
readme-language.md 进入版本控制
```

当前核验结果：

```text
三语对齐探针：九节行数逐节相同（4/32/13/5/3/6-6-6/9/7/2）
命令块三语逐字相同
链接集合三语一致，目标都存在
代码标识符与数字集合三语一致
linter：README.md 与 README.zh-TW.md 均 0 处发现
繁体禁用词人工扫描：零命中
```

仍未处理的次要项：

```text
README.en.md 第 101 行：native analysis extension
  可改为 native analysis library。与代码语义更贴。
ste-lint-zh.py 第 417 与第 431 行：baseline 逐文件消息与总退出码口径不一致
  两文件各 1 处硬违规、--baseline 1 时，消息说未超过，退出码却是 1
linter 未接入任何测试或钩子。全仓库没有调用点。
linter 不检查英文散文。英文的干净结果没有含义。
```

探针脚本 `research/readme-parity-probe.py` 已写。它未跟踪。

## 6. 字节绑定与陈旧性

```text
证据文件                              绑定状态
host-after-repairs.json               绑定当前 topics 源（哈希相同）
assets/content_rust/native_catalog.json 绑定当前 topics 源（哈希相同）
生成内容目录的聚合分布                 与 10-23 报告一致（等级、运行标注、领域）
打包 arm64 qfli_miri.so               与 assets/miri/manifest.json 哈希相同
native/build/device/ohos-arm64/*.so   旧于打包库
Android jniLibs                       停在 10-02，落后于当前分析路径
readiness-20261026*.json              记录 HEAD 78fb7b1，早于两个 README 提交
```

未运行清单（当前字节）：Dart 格式化、Dart 分析、Flutter 测试、原生 ABI 套件、
文件系统 ABI 套件、编译隔离探针、8 项原生打包检查、两个 OHOS 原生重建、
打包 332 用例、62 个聚焦回归（调试 42、功能审计 15、工作区 5）。

## 7. 可声称与不可声称

可以声称：

- 编写源与生成目录一致，配对 166/166，附带 23 个 Cargo 项目。
- 宿主上 332 个程序全部编译并运行通过，且报告绑定当前源。
- OHOS 打包库含分析扩展符号，且哈希与 manifest 一致。
- 共享核已发布命名工作区与 6 类面板。
- 三语 README 对齐，受控中文 linter 在中文两版上零发现。
- 离线不变量在源码层面成立，清单已移除 INTERNET。
- 4 个远端在 553e139 上哈希核验成功。

不可以声称：

- 任何示例或教程在 OHOS 上跑通。没有设备报告。
- 180 条新增。当前 0 条。
- 真实断点调试。原生库无调试符号，档位未接入。
- 本地 Ports 可用。
- Android 当前分析路径可用。库缺分析符号。
- 全语言高亮已验收。
- 五个远端全部推送成功。GitLab 未成功。
- 任何实现已进入仓库历史。实现几乎全在未跟踪文件里。

## 8. 打开的门（有序）

```text
1  设备窗口与签名：拿到可达 OHOS 目标，跑 332 用例设备台账
2  把未跟踪实现纳入提交：分析器、工具、调试器、目录台账、集成测试
3  提交并跑 62 个聚焦回归与完整根 Flutter 套件（新命名窗口）
4  重建两个 OHOS 原生库并打包，让调试 ABI 进入产物
5  接入 Rust 档位 debugger 字段，并补真实调试证据
6  解决 create_with_project 规范与产物的不一致
7  刷新 Android 库，把分析符号带入
8  设备通过后追加 180 对主题，再全量复核
9  处理 GitLab 鉴权，完成第 5 个远端推送
10 补 Rust 侧高亮与 chip/徽章消费者证据
11 共享核侧：次根运行缺陷、面板接缝与本地 Ports 决策
```

## 9. 本次未做的检查

- 未启动 SDK、native、WSL、构建、设备、Dart、Flutter、Python 脚本。
- 未运行任何测试、格式或分析命令。
- 未做 git 写操作、提交或推送。
- 未核验 Go、Lua、SQL、Note 四个产品的最新状态。
- 未逐条核验 `native/README.md` 的技术断言。只核验三语文件与打包字节两部分。
- 未改动任何审查对象。他人修改全部保留。