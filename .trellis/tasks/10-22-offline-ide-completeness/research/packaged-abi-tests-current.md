# 打包 ABI 测试现状（只读）

日期：2026-10-26。分支：feat/rust-offline-ide-20261022。基线提交：553e139。
本轮只读源码。本轮不编译。本轮不调用设备。本轮不提交。

## 绑定

- 测试文件 scripts/test_inspect_rust_catalog_hap.py
  - sha256：`ec1d6e1d9670b4c94440b72b4c514d409b2a027e1435d420cecde8dfbfc3590a`
  - 行数：622
  - 用例数：56
- 本轮读取的脚本 scripts/inspect_rust_catalog_hap.py
  - sha256：`8ff7a5886a82e4e32df2759163a7f5d49782bc30bef8268f90fe23676a78c7f0`
  - 字节数：21225
  - 归属：p5
  - 哈希只绑定本轮。p5 仍可改动该文件。

## 事实基线

- 必需符号 27 个。运行面 9 个。分析面 2 个。调试面 16 个。
- qfli_miri.h 声明 11 个原型。qfli_debug.h 声明 16 个原型。
- 两个头文件的并集正好等于 27 个必需符号。
- 绑定判定接受 `_STB_GLOBAL`、`_STB_WEAK`、`_STB_GNU_UNIQUE`。
- `_STV_LOADER_VISIBLE` 等于 `(0, 3)`。
- STV_DEFAULT 与 STV_PROTECTED 都是可解析的导出。
- STV_INTERNAL 与 STV_HIDDEN 都不是导出。
- 保留节号从 `_SHN_LORESERVE` 起算。该常量等于 `0xFF00`。
- 节号小于 0xFF00 且越出节表，就是畸形。
- 允许但不必声明清单的成员：libflutter.so、libapp.so、libqfli_native_probe.so。
- 必须由清单声明的成员：libqfli_miri.so。
- 必须存在且清单不覆盖的成员：libflutter.so 与 libapp.so。

## 新回归分层

| 测试类 | 用例数 | 覆盖 |
| --- | --- | --- |
| ElfExportReadingTest | 15 | 导出判定与必需面 |
| MalformedElfTest | 17 | ELF 边界与格式 |
| NativeInventoryTest | 4 | 清单策略 |
| RequiredAbiConstantsTest | 3 | 常量与头文件对齐 |
| InspectRustCatalogHapTest | 17 | 归档集成 |

夹具全是纯 Python 合成 ELF。夹具不依赖编译器。夹具不依赖 SDK。夹具不依赖设备。
集成夹具按 `TARGETS` 生成两种机器码。x64 用 62。arm64 用 183。

## 逐项映射

### 缺失 project / analysis / debug 导出

- test_missing_project_export_rejected 覆盖 qfli_miri_create_with_project。
- test_missing_analysis_exports_rejected 覆盖 qfli_miri_create_analysis。
- test_missing_debug_exports_rejected 覆盖 qfli_miri_debug_capabilities。
- test_run_surface_only_adapter_rejected 覆盖只有运行面的适配器。
- test_run_surface_only_adapter_rejected_by_the_archive 在归档层覆盖同一缺陷。

### 假导出不能算满足

- 未定义符号：test_undefined_symbol_is_not_an_export。
- 本地绑定：test_local_binding_is_not_an_export。
- 隐藏可见性：test_hidden_visibility_is_not_an_export。
- 内部可见性：test_internal_visibility_is_not_an_export。
- 受保护可见性仍算导出：test_protected_visibility_is_still_an_export。
- 数据符号：test_data_symbol_is_not_a_callable_export。
- 重复定义：test_repeat_definitions_collapse_to_one_export。
- 接受 GNU_UNIQUE 与 IFUNC：test_unique_and_ifunc_bindings_are_exports。
- 弱绑定仍算导出：test_weak_binding_is_a_loader_visible_export。
- 非保留节号越出节表：test_definition_index_outside_the_section_table_rejected。

### ELF 边界与格式

十七个用例。列表如下。

- 头截断、magic 不符、ELF32、大端。
- 节表缺失、节表截断、节项大小不符、节名索引越界。
- 节名表不是字符串表、节越出文件。
- dynsym 未对齐、dynsym 无字符串表、无 dynsym 节。
- 名称偏移越界、名称未终止、名称含非 ASCII 字节。

### 两种架构

- test_current_catalog_and_final_hashes_pass_static_inspection 覆盖 ohos-x64。
- test_arm64_archive_passes_static_inspection 覆盖 ohos-arm64。
- test_arm64_archive_rejects_x64_adapter 拒绝错架构的适配器。
- 该用例用 62 机器码的库冒充 arm64 库。

### 清单缺失、多余与允许成员

- 清单有而 HAP 无：test_missing_adapter_member_rejected。
- 该用例断言“Missing manifest-covered native library in HAP”。
- 字节改变：test_transformed_native_library_rejected。
- 该用例断言“Final HAP changed manifest-covered native bytes”。
- HAP 多出未声明库：test_unexpected_native_library_rejected。
- 适配器必须由清单声明：test_adapter_must_be_manifest_declared。
- 缺 Flutter 或应用库：test_missing_application_library_rejected。
- 探针免声明：test_probe_library_allowed_without_a_manifest_entry。
- 探针缺自身符号：test_probe_library_must_export_its_symbol。
- 探针缺席如实上报：test_absent_probe_is_reported_as_unpackaged。
- 裸 64 字节假 ELF：test_bare_elf_header_rejected_by_the_archive。

## 断言与夹具修正

### 第 2 轮：两处断言

起因：p5 更新了实现语义。两处用例随之失败。

- 修正一：受保护可见性改为正例。
  - 旧断言：STV_PROTECTED 算缺符号。
  - 新断言：STV_PROTECTED 算导出。
  - 用例：test_protected_visibility_is_still_an_export。
- 修正二：缺成员文案换成新文案。
  - 旧断言：命中“manifest-covered native bytes”。
  - 新断言：命中“Missing manifest-covered native library in HAP”。
  - 用例：test_missing_adapter_member_rejected。

### 第 3 轮：两个夹具

起因：Root 定下两条最终语义。p5 负责实现。本轮只加夹具。

- 夹具一：弱绑定必须算导出。
  - 构造：st_info 取 0x22，即 STB_WEAK 与 STT_FUNC。
  - 构造：其余字段取默认，节号指向 .text。
  - 断言：binding 等于 2，且 27 个符号全通过。
  - 用例：test_weak_binding_is_a_loader_visible_export。
- 夹具二：非保留节号越出节表必须失败。
  - 构造：一个可调用的全局符号，节号取 5、9、99。
  - 断言：read_elf_exports 抛 ValueError，文案含“section index”。
  - 用例：test_definition_index_outside_the_section_table_rejected。

保留节号边界没有加断言。Root 只限定非保留节号。p5 的实现接受 0xFF00 及以上。
两轮修正都没有删除用例。用例数从 53 变为 54，再变为 56。

## 测试有效性证据

主命令与结果：

```
cd scripts
python -m unittest test_inspect_rust_catalog_hap -v
```

结果：Ran 56 tests。OK。

全量纯 Python 套件：

```
cd scripts
python -m unittest test_build_rustc_host test_miri_build_support test_rust_content \
  test_rust_native_catalog test_verify_rust_native_catalog_host test_inspect_rust_catalog_hap
```

- scripts 六个模块合计 150 个用例。全部通过。
- build/offline-ide-audit/test_runner_controls_pure.py 有 58 个用例。全部通过。
- 纯 Python 合计 208 个用例。
- 本轮未运行 native、SDK、设备上的用例。

反证实验在临时目录进行。仓库保持不变。

- 步骤：复制 scripts 与所需数据到临时树。
- 步骤：删除临时副本里的清单校验调用与符号校验调用。
- 步骤：保留字节一致性校验。
- 结果：56 个用例里 9 个失败。47 个通过。

失败清单：

- ERROR test_absent_probe_is_reported_as_unpackaged
- ERROR test_arm64_archive_passes_static_inspection
- ERROR test_current_catalog_and_final_hashes_pass_static_inspection
- ERROR test_probe_library_allowed_without_a_manifest_entry
- FAIL test_bare_elf_header_rejected_by_the_archive
- FAIL test_missing_application_library_rejected
- FAIL test_probe_library_must_export_its_symbol
- FAIL test_run_surface_only_adapter_rejected_by_the_archive
- FAIL test_unexpected_native_library_rejected

结论：这 9 个用例只依赖新能力。单元级 47 个用例与旧实现无关。

关键反例是 test_run_surface_only_adapter_rejected_by_the_archive。

- 该用例让清单与陈旧适配器字节一致。
- 旧的字节一致性校验会放行。
- 新的符号校验会拒绝。
- 这证明该用例有牙齿。

## 对 p5 的观察（本轮已校验）

1. 缺成员与字节改变已分开。
   - 现状：两条文案各自独立。
   - 结论：第 2 轮的文案问题已解决。
   - 覆盖：两条文案各有用例。
2. STV_PROTECTED 已按导出处理。
   - 现状：`_STV_LOADER_VISIBLE` 含 3。
   - 结论：早前的观察有误。受保护符号可经 dlsym 解析。
   - 覆盖：test_protected_visibility_is_still_an_export。
3. 弱绑定已按导出处理。
   - 现状：判定集合含 `_STB_WEAK`。
   - 覆盖：test_weak_binding_is_a_loader_visible_export。
4. 节号已有上限校验。
   - 现状：低于 0xFF00 且越界即报错。
   - 文案：含“names section index … outside the table”。
   - 覆盖：test_definition_index_outside_the_section_table_rejected。
5. 符号名长度上限 512 字节。
   - 现状：`_MAX_SYMBOL_NAME` 等于 512。
   - 影响：正常符号名远短于该值。
6. 探针可以缺席。
   - 现状：probeAbi 返回 packaged=False。
   - 影响：探针缺席不导致校验失败。
   - 待确认：这是有意设计，还是待收紧。

## 未证实项

- 未在真机运行。
- 未校验真实 HAP。
- 未校验真实 libqfli_miri.so。
- 未编译。未签名。未打包。
- 探针是否随包发布，本轮未查证。