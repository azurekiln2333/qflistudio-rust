# HAP 检查器调用方与参数更新（只读）

日期：2026-10-26。分支：feat/rust-offline-ide-20261022。基线提交：aa8594a。
本轮只改 `scripts/build_rust_catalog_audit.ps1`（本轮归属）。其余只读。
本轮不编译。本轮不打包。本轮不调用设备。本轮不跑 WSL。本轮不提交。
本轮不编辑 p5 的检查器与套件。检查只用 PowerShell AST 解析。

## 检索方式

- 用 `rg` 检索，未做整仓递归 shell 扫描。
- 检索必须加 `--hidden --no-ignore`。`.trellis` 是隐藏目录。
- 关键词：`inspect_rust_catalog_hap`、`build_rust_catalog_audit`、`runtimeAbi`、`nativeInventory`、`probeAbi`。

## 本轮快照

p5 本轮在持续改两个文件。下表是逐个快照，不是定论。

| 文件 | sha256 前缀 | 字节数 | 时间 |
| --- | --- | --- | --- |
| scripts/inspect_rust_catalog_hap.py | 6DB7894F | 33029 | 10:40:18 |
| scripts/test_inspect_rust_catalog_hap.py | 111312FC | 987 行 | 10:47:57 |
| scripts/build_rust_catalog_audit.ps1 | 688c97fc | 6757（114 行） | 本轮已改 |

套件的三次只读快照如下。p5 正在改源，这些数字只记录快照时刻。

| 套件快照 | 用例数 | 结果 | 原因 |
| --- | --- | --- | --- |
| cd74281e | 59 | 39 过、20 错 | 20 处 `self.verify` 未定义 |
| 917275cc | 89 | 2 失败、6 错 | 夹具链未满足。断言文案与验证顺序不符 |
| 111312FC | 63 | 1 错 | `setUpClass` 抛 `NameError: name 'compiler' is not defined` |

这些快照都是进行中状态，不是最终结论。API 待 p5 冻结。
源码冻结前不再重跑套件。

## 调用脚本精确路径

全仓只有两处引用。第一处是唯一真实调用。

| 精确路径 | 行 | 形式 | 现状 |
| --- | --- | --- | --- |
| `scripts/build_rust_catalog_audit.ps1` | 90 | CLI 调用 | 本轮已改，两个记录均已转发 |
| `scripts/test_inspect_rust_catalog_hap.py` | 28 | 模块导入 | 直接调用 `inspect()`，p5 所有 |

第一处已实现的调用文本如下。

```powershell
    & python scripts/inspect_rust_catalog_hap.py --hap $artifact --architecture $Architecture `
        --compiler-record $compilerRecordPath --adapter-record $adapterRecordPath `
        --metadata $metadata --report (Join-Path $output 'inspection.json')
```

`build_rust_catalog_audit.ps1` 是唯一真实调用方。它的产物是 `inspection.json`。

## 拟增必填参数

p5 已实现 provenance 绑定。CLI 现有 6 个参数。
两个新参数都是必填。命名待 p5 冻结。

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `--hap` | 是 | 本轮检查的归档 |
| `--architecture` | 是 | 取值 ohos-x64 或 ohos-arm64 |
| `--compiler-record` | 是 | 可信补丁编译器构建记录，JSON 字节 |
| `--adapter-record` | 是 | 可信适配器构建记录，JSON 字节 |
| `--metadata` | 否 | 构建元数据 |
| `--report` | 是 | 报告输出 |

`inspect()` 的签名同步变化。

```python
inspect(hap, architecture, root=ROOT, *, compiler_record, adapter_record)
```

两个记录以字节传入，不以路径传入。

## 记录链设计

新函数是 `verify_compiler_provenance(runtime, compiler_record, adapter_record, adapter_bytes, native_host)`。

- 不解析记录路径。
- 不遍历编译器 sysroot。
- 全链是纯字节比对。
- 清单哈希选定记录。
- 记录须带已评审的边界身份。
- 适配器记录须指向包内适配器的精确字节。
- 结果写入 `report["compilerProvenance"]`。
- 该步放在最后。前面失败时保留自己的错误信息。

## 每个调用方的精确改法

### 1. scripts/build_rust_catalog_audit.ps1（本轮已完成）

本轮已改该脚本。新哈希 688c97fc。AST 解析 0 错。

参数块已加两项必填参数。

```powershell
param(
    [ValidateSet('ohos-x64', 'ohos-arm64')][string]$Architecture = 'ohos-x64',
    [Parameter(Mandatory = $true)][string]$CompilerRecord,
    [Parameter(Mandatory = $true)][string]$AdapterRecord,
    [string]$Json5Module = '...'
)
```

前置检查放在所有变更之前。顺序由 AST 证实。

1. 定义 `Resolve-TrustedRecord`。
2. 解析并检查编译器记录。
3. 解析并检查适配器记录。
4. 算两个记录的 sha256。
5. 才创建输出目录。
6. 才取构建锁。
7. 才进入 try，才做源文件快照与改写。

`Resolve-TrustedRecord` 做三件事。

- 用 `Resolve-Path -LiteralPath` 取绝对路径。路径不存在即失败。
- 要求目标是文件。目录即失败。
- 要求文件非空。空文件即失败。

因此缺记录时脚本立即退出。此时没有建目录。此时没有取锁。此时没有改源文件。

记录哈希的精确语义如下。

- 两个 `Get-FileHash` 都读解析后的绝对路径。
- 哈希只算一次，在脚本开头。
- 脚本内没有一处写记录文件。
- 第 90 行转发的是同一对解析后路径。
- 所以 `build.json` 里的两个哈希就是初始记录字节的哈希。
- 该哈希也等于检查器消费的那份字节。
- 例外只有一个：若外部进程在脚本运行中改写记录文件，哈希会滞后。此时检查器看到新字节，p5 的比对会失败。这是安全失败。

两个记录的哈希已写入 `build.json`。字段名是 `compilerRecordSha256` 与 `adapterRecordSha256`。
符合 p5 的消费方比对：写入的哈希对消费的精确字节。

### 本轮 AST 证据

只用 PowerShell AST 解析。未运行脚本。未编译。未打包。

| 检查项 | 结果 |
| --- | --- |
| `ParseFile` 语法错误 | 0 |
| `CompilerRecord` 必填 | 是（Mandatory=True） |
| `AdapterRecord` 必填 | 是（Mandatory=True） |
| `Architecture` / `Json5Module` | 仍非必填 |
| 语句序（解析） | 下标 3、4 |
| 语句序（建目录） | 下标 8 |
| 语句序（取锁） | 下标 9 |
| 语句序（try 入口） | 下标 19 |
| 写记录文件的操作 | 0 处 |
| 提记录路径的唯一行 | 第 90 行，作为检查器入参 |
| `build.json` 字段名 | 逐字匹配 |

本轮未做签名配置的源文件暂存。`ohos/` 下无本轮写入。

未改动的部分。

- 签名隔离的 node 编辑未改。`bundleName` 隔离、native `excludes`、`enableSignTask: false` 三处保留原样。
- 源文件原字节快照与 `finally` 恢复逻辑未改。
- 并发编辑时写 `original-$index.backup` 的分支未改。
- 锁释放与 `Pop-Location` 未改。

该脚本不得伪造记录。缺记录即失败。

### 2. scripts/test_inspect_rust_catalog_hap.py

p5 拥有该文件。该文件需要一份惰性记录夹具。

- 记录用 JSON 字节造，不碰真实构建。
- 覆盖缺参数、哈希不同、边界不同三类拒绝。
- 覆盖通过时报告含 `compilerProvenance`。

### 3. .trellis/spec/backend/catalog-audit.md

第 14 行签名改为。

```text
python scripts/inspect_rust_catalog_hap.py --hap <file> --architecture ohos-x64 \
  --compiler-record <compiler-build.json> --adapter-record <adapter-build.json> \
  --metadata <build.json> --report <json>
```

第 13 行脚本签名同步加 `-CompilerRecord` 与 `-AdapterRecord`。

第 3 节新增契约条目。

- 检查器消费两个可信构建记录，以字节传入。
- 报告必须绑定记录身份与编译器边界。

第 4 节错误矩阵新增三行。

| 条件 | 应有结果 |
| --- | --- |
| 缺构建记录 | 静态检查失败 |
| 适配器字节与记录不同 | 静态检查失败 |
| 编译器边界与记录不同 | 静态检查失败 |

第 6 节测试清单新增 provenance 消费者回归。

### 4. .trellis/spec/backend/native-runtime.md

第 3 节新增一条：HAP 静态检查消费适配器构建记录，记录绑定编译器边界。
该检查不证明运行时可用性。

### 5. 命名分歧

仓库既有消费者用 `--adapter-build-info`。

- scripts/package_miri_ohos.ps1:69
- scripts/miri_build_support.py verify-adapter

检查器现在用 `--adapter-record`。两套名字并存会让调用方误用。
建议二选一。若保留 `--adapter-record`，请在规范里写明两者关系。

## 阻塞项

### B1 套件当前未全绿（最高优先）

现象按快照递进。

- 快照 cd74281e：20 处调用 `self.verify(...)`，而该类没有 `verify`。
- 快照 917275cc：`verify` 已补上，新增 `CompilerProvenanceTest`。
  - 余下 2 个失败是断言文案与验证顺序不符。
  - 实际先抛 `Compiler boundary source commit differs from the pinned revision`。
  - 用例期待的是 `compilerBuild boundary differs from the compiler record`。
  - 余下 6 个错误发生在 `verify_compiler_provenance` 内部，夹具记录链尚未满足真实链。
- 快照 111312FC：`setUpClass` 调用 `runtime_for` 时抛 `NameError: name 'compiler' is not defined`。

判断：这是改到一半的状态。p5 拥有该文件。
需要：先修 `runtime_for` 的名字错误，再对齐记录夹具与断言文案。

### B2 审计脚本已修复（本轮）

本轮已改 `build_rust_catalog_audit.ps1`。该脚本旧版只传 4 个参数。

- 新哈希 688c97fc。PowerShell AST 解析 0 错。
- 两个必填参数已加，且已转发给检查器。
- 两个记录在所有变更之前解析、检查并哈希。
- 两个记录哈希已写入 `build.json`。
- 未运行该脚本。未编译。未打包。
- 该修复是否符合真实构建链，待冻结后由 p5 的套件与一次真实审计运行确认。

### B3 已消解的两项旧阻塞

早前提出的两项阻塞已由 p5 的设计消解。

- 路径相等阻塞：记录以字节传入，无路径比较。
- sysroot 遍历阻塞：该设计不遍历编译器树。

## 陈旧验收断言

| 位置 | 断言 | 为何陈旧 |
| --- | --- | --- |
| catalog-audit.md:14 | 检查器签名只有四个参数 | 现在有 6 个，且两个必填 |
| catalog-audit.md:13 | 脚本签名 | 本轮已加两个参数，规范尚未同步 |
| catalog-audit.md 第 3 节 | 最终归档检查只列六项 | 缺 27 符号导出、缺清单允许表、缺 provenance |
| catalog-audit.md:106 | 测试清单 | 缺 provenance 消费者回归 |
| packaged-runtime-readiness-pi-current.md:282 | “唯一的产物绑定在 inspect_rust_catalog_hap.py 内” | 符号、清单与 provenance 均未计入 |
| packaged-abi-implementation-current.md:201 | 56 个用例全过 | 当前套件已超 59 个用例，且未全绿 |
| packaged-abi-tests-current.md（本人早前） | 56 个用例、哈希 ec1d6e1d | 套件已重写，用例数与哈希均变 |
| hap-inspector-dependency-review-current.md（本人早前） | 四参数 CLI、59 用例全过 | 参数已变，套件未全绿 |
| research/acceptance.md R1 行 | 未记 provenance 门禁 | 验收台账缺一项 |

补充：`build/` 下没有检查器报告产物。检索 `runtimeAbi` 只命中脚本与文档。
因此不存在需要撤回的假通过报告。

## 未证实项

- 未运行检查器。
- 未运行审计脚本。
- 未构建 HAP。
- 未验证任何真实构建记录。
- provenance 是否真正成立，本轮只读源码，未实测。
- 打包库是否已导出 27 个符号，本轮未实测。
- 参数名 `--compiler-record` 与 `--adapter-record` 取自 p5 当前源码。API 冻结前可能再变。