# HAP 检查器依赖审查（只读）

日期：2026-10-26。分支：feat/rust-offline-ide-20261022。基线提交：aa8594a。
本轮只读源码。本轮不编译。本轮不打包。本轮不调用设备。本轮不提交。

## 范围

审查对象是两个文件。

- scripts/inspect_rust_catalog_hap.py
- scripts/test_inspect_rust_catalog_hap.py

审查目标有三项。

- 求出两个文件的依赖闭包。
- 定出最小安全一致提交集。
- 检查新增题目是否越过 OHOS 基线门禁。

## 基线

- 检查器 sha256：`89c2bba1a4a8399ef005ea7f69fdc144bc49c06a945edb20af7e14bef0014997`
- 检查器字节数：22032
- 套件 sha256：`cf245971877ef62657efb41baf3b4921a8111c889bdf8e40e4fd40222cb1e8f9`
- 套件行数：642
- 套件用例数：59
- 两个文件都未跟踪。

## 脚本闭包

闭包由静态 AST 求得。本轮不导入这些模块。

| 文件 | 行数 | 本地依赖 | git 状态 | 需提交 |
| --- | --- | --- | --- | --- |
| generate_rust_content.py | 247 | 无 | 已跟踪、干净 | 否 |
| miri_build_support.py | 441 | 无 | 已跟踪、干净 | 否 |
| package_miri_runtime.py | 479 | miri_build_support | 已跟踪、干净 | 否 |
| generate_rust_native_catalog.py | 338 | generate_rust_content | 未跟踪 | 是 |
| inspect_rust_catalog_hap.py | 433 | 上述四项 | 未跟踪 | 是 |
| test_inspect_rust_catalog_hap.py | 642 | generate_rust_content、inspect、miri_build_support | 未跟踪 | 是 |

三个已跟踪脚本在 HEAD 中已存在且工作区干净。它们不需要进入本次提交。
生成器 generate_rust_native_catalog.py 未跟踪。检查器与套件都导入它。

## 数据依赖

| 路径 | 角色 | git 状态 | 需提交 |
| --- | --- | --- | --- |
| tool/rust_content/topics_001_084.json | 作者输入 | 已跟踪、已修改 | 是 |
| tool/rust_content/topics_085_166.json | 作者输入 | 已跟踪、已修改 | 是 |
| assets/content_rust/examples.json | 生成目录 | 已跟踪、已修改 | 是 |
| assets/content_rust/tutorials.json | 生成目录 | 已跟踪、已修改 | 是 |
| assets/content_rust/native_catalog.json | 生成清单 | 未跟踪 | 是 |
| native/miri_adapter/qfli_miri.h | 契约头文件 | 已跟踪、已修改 | 是 |
| native/miri_adapter/qfli_debug.h | 契约头文件 | 未跟踪 | 是 |
| assets/miri/manifest.ohos-*.json | 运行时清单 | gitignore 覆盖 | 否 |
| ohos/entry/libs/* | 打包库 | gitignore 覆盖 | 否 |

`.gitignore` 第 75 行的 `/assets/miri/*` 覆盖运行时清单。清单由打包生成，随架构变化。
`ohos/entry/libs/` 同样不跟踪。两者都不进入提交。

## 当前内容规模

- 作者题目 166 条。编号从 1 到 166。
- examples 目录 166 条。tutorials 目录 166 条。
- native_catalog 332 个用例。
- guestTarget 为 x86_64-unknown-linux-gnu。
- 新增题目 0 条。

## 门禁检查

设计文档要求：OHOS 基线通过之前不得发布新题目。

- 新增题目为 0。编号上限仍是 166。
- 修改都落在既有题目内。共三处。
  - 第 013 课把基准输入从 10000 降到 100，并补了解释。
  - 第 056 课补了默认绑定模式的解释。
  - 第 156 与 157 课把 FFI 写法改为 `#[unsafe(no_mangle)]` 与 `unsafe extern "C"`。
- 宿主报告 `build/offline-ide-audit/host-after-repairs.json` 的 inputSha256 与当前 topics 完全一致。
- 该报告状态为 passed。332 个程序全部通过。mobileExecution 为 not_tested。
- 旧报告 `host-baseline.json` 的 inputSha256 已过期。
- OHOS 基线仍未通过。当前内容没有越过该门禁，因为没有新题目。

## 最小安全一致提交集

共 10 个路径。分四组。

### 检查器与套件

- scripts/inspect_rust_catalog_hap.py
- scripts/test_inspect_rust_catalog_hap.py

### 生成器

- scripts/generate_rust_native_catalog.py

### 内容与生成目录

- tool/rust_content/topics_001_084.json
- tool/rust_content/topics_085_166.json
- assets/content_rust/examples.json
- assets/content_rust/tutorials.json
- assets/content_rust/native_catalog.json

### 契约头文件

- native/miri_adapter/qfli_miri.h
- native/miri_adapter/qfli_debug.h

四组必须同一次提交。原因如下。

- 生成清单由 topics 派生。两者不同步时 `--check` 失败。
- 生成目录由 topics 派生。两者不同步时配对检查失败。
- 套件的常量用例读取两个头文件。缺任一个即报错。

### 头文件契约说明

两个头文件是源码契约，不是运行时证据。

- qfli_miri.h 现在声明 11 个原型。
- qfli_debug.h 声明 16 个原型。
- 两者合计 27 个，与检查器的必需集合相等。
- 提交这两个头文件只声明契约。它不表示打包库已导出这些符号。
- 按 p5 记录的静态观察，当前打包库只导出 10/27。运行时可用的结论仍需真机运行。

## 验证证据

### 充分性

临时树的做法如下。

- 先取 HEAD 版本的三个已跟踪脚本。
- 再叠加候选集的 10 个路径。
- 然后在临时树内跑套件与两项生成检查。

结果：

- 套件 Ran 59 tests，OK。
- `generate_rust_content.py --check` 退出码 0。
- `generate_rust_native_catalog.py --check` 退出码 0。

### 必要性

三项逐一抽掉后都失败。

- 去掉 native_catalog.json：setUpClass 报错。
- 只用 HEAD 头文件且无 qfli_debug.h：test_required_abi_matches_the_adapter_headers 报错。
- 去掉生成器：导入即报错。

## 纯检查命令

```powershell
cd scripts
python -m unittest test_inspect_rust_catalog_hap
cd ..
python scripts/generate_rust_content.py --check
python scripts/generate_rust_native_catalog.py --check
```

扩大范围时可加 scripts 下的纯 Python 模块。全部不调用编译器与设备。

```powershell
cd scripts
python -m unittest test_build_rustc_host test_miri_build_support test_rust_content `
  test_rust_native_catalog test_verify_rust_native_catalog_host test_inspect_rust_catalog_hap
```

## 观察

1. 本轮开始后他人更新了这两个目标文件。
   - 检查器时间 10:01:37。套件时间 10:02:49。
   - 套件新增 3 个用例：目录项放行、嵌套负载拒绝、未声明负载拒绝。
   - 本轮保留这些改动，未做任何还原。
2. 目录项放行改动了清单判定的边界。
   - 现在 `libs/` 下的目录项不算原生库。
   - 只允许 `.so` 出现在 `libs/<abi>/` 内。
3. 生成清单必须与 topics 同源提交。
   - 清单记录 sourceSha256。
   - topics 一改，清单必须重生成。

## 未证实项

- 未在真机运行。
- 未检查真实 HAP。
- 未编译。未打包。未签名。
- 未提交。未推送。
- 打包库是否已导出 27 个符号，本轮未实测。