# README 三语与受控中文 linter 只读审查

## 审查范围与基线

- 审查对象：`README.md`、`README.zh-TW.md`、`README.en.md`、`scripts/ste-lint-zh.py`。
- 基线提交：`dd3343b docs: add trilingual README and controlled Chinese checks`。
- 仓库状态：四个路径与 HEAD 一致。工作区在这四个路径上没有改动。
- 规范依据：`.trellis/spec/guides/readme-language.md`。
- 方式：只读。我没有改动上述四个文件。
- 本次没有做：原生构建、SDK 测试、设备运行。三项都在范围之外。
- 报告位置：本文件写在 10-22 任务的 `research/` 下。若原指定任务不同，请告知，我移过去。

## 结论

1. 三语已经基本对齐。九个小节的散文行数逐节相同。
2. 还剩两处内容差异。一处是英文多一句话。一处是英文更具体。
3. 繁体版有两处保真偏差。简体口径更完整。
4. linter 有一个报告缺陷。另有一份规范文件不在仓库里。

## 事实验证

下表逐条给出证据。证据来自代码、脚本与内容目录。

```text
断言                                        证据
166 篇教程与 166 个示例                     assets/content_rust/tutorials.json entries=166
                                            assets/content_rust/examples.json entries=166
23 个主题附带 Cargo 项目文件                tool/rust_content/topics_*.json 共 166 个主题
                                            其中 23 个带 files 字段
                                            23 个都含 Cargo.toml 与 src/main.rs
                                            examples.json 里 23 个示例带 cargoFiles
桌面端检查调用真实的 cargo metadata         lib/rust_tool_utilities.dart:480 启动 cargo 的
                                            metadata 子命令
移动端只读项目里的 Cargo.toml               lib/rust_tool_utilities.dart:415 移动端没有 Cargo
                                            CLI，改读本地清单
桌面分析器可读取 QFLI_RUSTC                 lib/rust_code_analyzer.dart:56 读
                                            Platform.environment，优先级见 :51 注释
分析失败不会显示为没有错误                  同上文件：缺编译器时报不可用，不报干净
iOS 仅提供源码构建脚本                      本仓库找不到 iOS 单文件打包入口；见下文张力
```

上述断言与检出代码一致。

## 三语对齐

数法：只数散文行。跳过代码块、命令行与标题。

```text
小节                        简体   繁体   英文
1 项目定位                    4      4      4
2 真实功能                   32     32     32
3 桌面与移动端差异           13     13     13
4 相邻目录                    5      5      5
5 离线 Cargo 限制             3      3      3
6 安装与运行                  6      6      7   <- 差异
7 内容检查                    9      9      9
8 设备验证限制                7      7      7
9 原生组件                    2      2      2
```

结论：

- 命令块三语完全一致。四个命令逐字相同。
- 链接三语都指向同一组文件。`README.md`、`README.zh-TW.md`、`README.en.md`、`native/README.md` 都存在。
- 差异一：`README.en.md` 第 152 行多一句，说明 `QFLI_RUSTC` 只管桌面分析。中文两版没有这句。
- 差异二：`README.en.md` 第 189 行写 `An OHOS physical device`。中文两版只写物理设备。英文更具体。

## 中文规范检查

- 默认口径：两个中文文件都是 0 处发现。硬违规 0 处。
- 收紧口径：`--max-chars 25` 也没有发现。每句都在 25 字以内。
- 繁体人工扫描：我查了 28 个禁用词。含 無縫、強大、進行、相關、使用者、客戶。全部零命中。
- 术语统一：简体用 运行 15 次，没有用 `执行`。繁体用 `執行` 16 次，没有用 `運行`。
- 打包一词：简体全用 打包，繁体全用 封裝。两版各自统一。
- 一处不一致：`README.md` 第 156 行用了 跑。全篇其余地方用 运行。繁体同一行用 執行。
- 同一概念要用同一个词。建议简体的那一行改成 运行。

## 英文措辞（七处）

按严重度从低到高排列。都改一行，不动事实。

1. `README.en.md` 第 35 行：`Bit operations first convert by the selected type.` 缺宾语与介词。
   建议：`Bitwise operations first convert the operands to the selected type.`
2. 第 52 行：`Long press Run to run the current saved file.` 建议：`Long-press Run to run the current saved file.`
3. 第 54 行：`This keeps the configured entry unchanged.` 指代不明。
   建议：`Long-pressing Run does not change the configured entry.`
4. 第 29 行：`It never presents failed analysis as a result with no errors.`
   建议：`It never presents a failed analysis as a clean result.`
5. 第 101 行：`the matching native analysis extension`。这里的 extension 指原生库。
   建议：`the matching native analysis library`。
6. 第 3 行：英文版把自身写成纯文本 `English`。中文两版把自身写成链接。
   三种版本的自身链接样式要统一。
7. 第 66 行：`23 topics include Cargo project files.`
   可选更精确写法：`23 topics include a Cargo.toml and a src/main.rs.` 改与不改都要与中文两版同步。

## 繁体保真（两处）

繁体与简体事实一致，但两处丢了限定词。

1. `README.zh-TW.md` 第 42 行写 用 `cargo metadata` 取得中繼資料。
   简体 `README.md` 第 42 行写 调用真实的 `cargo metadata`。
   繁体丢了 真实 一词。这个词在这里是证据边界，不能丢。
2. `README.zh-TW.md` 第 169 行写 比對每個程式的宣告輸出。
   简体 `README.md` 第 169 行写 比对程序输出与声明输出。
   繁体丢了程序输出这一侧。两侧都在，才算完整。

建议繁体补回这两处限定。

## linter 审查（六条）

1. 繁体覆盖是已知限制。规范已经写明 linter 主要识别简体词。
   我的探针确认：繁体样本 無縫、強大、進行分析、相關 都零命中。简体同类样本命中。
   这是设计限制，不是缺陷。前提是繁体继续人工复核。
2. 英文不参与检查。linter 对 `README.en.md` 给出 0 处发现。
   英文里能命中的只有分号规则。所以英文的干净结果没有含义。
3. baseline 报告有缺陷（建议修）。第 417 行按文件单独比 baseline。第 431 行退出码比总数。
   两个文件各 1 处硬违规、`--baseline 1` 时，逐文件消息写 未超过 baseline，退出码却是 1。
   消息与结论矛盾。建议统一口径。
4. 没有接入自动化。仓库里没有测试或钩子调用这个脚本。
   全仓库搜不到 `ste-lint` 的调用点，只有规范文档手动调用。
5. 没有三语对齐检查。规范要求功能状态、平台限制、命令、目录数量等效。
   这次两处差异只能人工发现。建议加一个小检查：按节比较标题列表与散文行数，
   再比较行内代码标识符与数字集合。本目录的 `readme-parity-probe.py` 就是最小实现。
6. 建议类规则永不失败。`passive-voice`、`vague-word`、`compound-aspect`、`halfwidth-punct`、`dash-join` 只报告。
   规范要求主动语态，也要求去掉含糊词。这两条目前没有门槛。

## 仓库层面的两个阻塞项

1. `.trellis/spec/guides/readme-language.md` 不在仓库里。
   `.gitignore` 第 98 行忽略整个 `.trellis/spec/`。已有的 7 个 spec 文件是强制加入的，所以还在。
   `guides/` 是新增目录，仓库看不到它。
   后果：全新检出与其它代理读不到这份语言契约。
2. 结尾换行不一致。HEAD 里 `README.md` 与 `README.en.md` 结尾没有换行符。
   `README.zh-TW.md` 与 linter 脚本结尾有换行符。

## 相邻文档的张力（两条，请确认）

这两条不在三语文件内，但会互相打脸，所以列出。

1. `native/README.md` 新增 arm64-only 一句，同时保留 2026-09-30 的 x86_64 模拟器通过记录。
   两句并列会让人误读。建议给旧记录加时间前提。
2. 根 README 三语都写 iOS 的打包与设备验证待完成。
   `native/README.md` 记载 Apple 打包流程已经写完，只是没在 Windows 上跑过。
   待完成 与 已经写完但未验证 是两件事。请确认当前口径。

## 建议顺序

1. 把 `readme-language.md` 加入版本控制。
2. 补两处繁体限定词。
3. 决定 `QFLI_RUSTC` 那句是否回流中文两版。
4. 统一自身链接样式与结尾换行。
5. 修 linter 的 baseline 报告。
6. 收尾英文措辞七处。

## 复现命令

```text
python scripts/ste-lint-zh.py README.md README.zh-TW.md
python scripts/ste-lint-zh.py --max-chars 25 README.md README.zh-TW.md
python scripts/ste-lint-zh.py --json README.en.md
python scripts/ste-lint-zh.py --selftest
python .trellis/tasks/10-22-offline-ide-completeness/research/readme-parity-probe.py
```

前三条给出上面各节的结果。第四条是 linter 自检，结果 OK。

## 未覆盖范围

- 我没有验证 OHOS 包内源码运行。也没有验证设备安装与运行。
- 我没有逐条验证 `native/README.md` 的技术断言。只看了三语文件涉及的两处张力。
- 我没有改任何文件，也没有跑任何构建。