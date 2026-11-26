# GitHub native 构建

GitHub 托管运行器负责编译运行库。
构建、测试和校验只在云端运行。
本地仅编辑源码并盘点文件。
不要向工作目录下载或解压产物。
云端构建不会清理本地旧文件。

运行边界见[云端策略](../.trellis/spec/guides/cloud-only-workspace.md)。

## 构建范围

| 平台 | 架构 | 原生库形式 |
| --- | --- | --- |
| Android | arm64、x64 | `.so` 及配套依赖 |
| OHOS | arm64、x64 | `.so` 及配套依赖 |
| iOS 设备 | arm64 | framework 及配套依赖 |
| macOS（手动可选） | x64 | framework 及配套依赖 |

Linux 和 macOS 充当构建机器。
构建机器使用官方预编译工具链。
工作流不生成 Linux 或 Windows 运行库。

这些产物供 Flutter 应用打包使用。
它们不是可直接安装的应用。
本工作流不生成 APK、HAP 或桌面安装包。

编译器固定为 Rust 1.98.1。
构建过程应用项目的编译器补丁。
脚本校验源码、补丁和编译产物。
普通 `rustc-dev` 不能替代补丁版编译器。

## 触发构建

当前工作流位于 `main` 分支。
向 `main` 推送构建文件会自动触发构建。
仅改文档不会触发构建。

可选 macOS 构建使用手动触发。
手动触发使用 `workflow_dispatch` 事件。

按以下步骤启动 macOS 构建：

1. 打开 **Native runtime** 工作流。
2. 点击 **Run workflow**。
3. 选择 `main` 分支。
4. 勾选 `include_macos`。
5. 点击 **Run workflow**。

## 已验证的构建

2026-11-17，以下五个目标已构建成功：

- Android arm64、x64。
- OHOS arm64、x64。
- iOS arm64 设备。

成功运行：[43946596992](https://github.com/azurekiln2333/qflistudio-rust/actions/runs/43946596992)。
构建提交为 `76289a0`。
产物位于该页面的 **Artifacts** 区域。
本轮未构建可选 macOS 目标。

## 云端消费产物

1. 打开仓库的 **Actions** 页面。
2. 选择 **Native runtime** 工作流。
3. 打开所需提交对应的运行记录。
4. 记录任务结果和产物有效期。
5. 在消费工作流中选择匹配输入。
6. 在托管运行器校验 SHA-256。
7. 在运行器工作目录解压运行库。

产物下载和解压仅在云端运行。
不要下载到 D 盘或 E 盘工作目录。
失败时通过 GitHub 查看诊断日志。
失败任务不会上传可用运行库。
请勿混用不同提交或平台的库。

| 下载项 | 对应平台 |
| --- | --- |
| `native-runtime-android-arm64` | Android arm64 |
| `native-runtime-android-x64` | Android x64 |
| `native-runtime-ohos-arm64` | OHOS arm64 |
| `native-runtime-ohos-x64` | OHOS x64 |
| `native-runtime-ios-arm64` | iOS arm64 设备 |
| `native-runtime-macos-x64` | macOS x64（手动可选） |

平台包和日志保留 14 天。
每个产物包含 `.tar.gz` 和校验文件。
GitHub 产物 ZIP 包含这两个文件。

以下命令仅供 GitHub 托管运行器使用。
在运行器的产物目录校验文件：

```sh
sha256sum -c native-runtime-android-arm64.tar.gz.sha256
```

macOS 运行器可用 `shasum -a 256`。
Windows 运行器可用 `Get-FileHash`。
请将结果与 `.sha256` 文件逐字比较。

从运行器仓库根目录解压平台包：

```sh
tar -xzf <下载目录>/native-runtime-android-arm64.tar.gz
```

请替换命令中的平台名和云端路径。
记录运行编号、源码提交和输入身份。
不要仅选择最近一次成功产物。

## 产物内容

| 内容 | 用途 |
| --- | --- |
| `native/build/runtime/<平台>-<架构>/` | Android、macOS 原生库和包清单 |
| `native/build/runtime/aarch64-apple-ios/` | iOS framework 和包清单 |
| `android/app/src/main/jniLibs/<ABI>/` | Android 打包库 |
| `ohos/entry/libs/<ABI>/` | OHOS 打包库 |
| `assets/miri/manifest.<平台>-<架构>.json` | Flutter 运行库清单 |
| `assets/miri/*.bin` | MIR 标准库和许可证 |
| `native/include/` | C 接口声明 |
| `build-info/` | 固定版本、补丁和文件校验信息 |
| SHA-256 清单 | 下载后的完整性校验 |

运行库需要完整的依赖和 MIR 数据。
仅复制适配器 DLL 或 SO 无法满足要求。
Apple framework 使用临时签名。
应用发布时仍需使用应用签名。

构建成功只证明产物已生成。
应用运行验证仍需在目标平台开展。
OHOS 设备验证不由桌面构建替代。

## 本地空间

以下数据来自 2026-11-17 的盘点。
大小按 GiB 计算。
本仓库合计约 14.89 GiB。
Git 跟踪文件合计约 8.98 MiB。

| 路径 | 大小 | 内容 |
| --- | ---: | --- |
| `build/app/` | 4.20 GiB | Android 构建输出 |
| `build/ohos/` | 1.23 GiB | OHOS 构建输出 |
| `ohos/entry/build/` | 2.66 GiB | OHOS 模块构建输出 |
| `ohos/build/` | 0.60 GiB | OHOS 工程构建输出 |
| `.dart_tool/flutter_build/` | 1.17 GiB | Flutter 构建缓存 |
| `native/build/` | 3.33 GiB | 固定工具链和 native 产物 |

表中前五项合计约 9.86 GiB。
它们可以通过重新构建生成。
清理前，请保存需要保留的 APK 和 HAP。
不要直接清空整个 `build/`。
该目录还存有审计记录和截图。

`native/build/miri-windows/` 约占 2.60 GiB。
该目录包含本地固定版本编译器。
它不属于纯临时文件。
确认云端产物可用后，再决定是否删除。

GitHub 托管运行器负责应用打包。
运行器恢复匹配的库和 `assets/miri/`。
D 盘和 E 盘不再打包应用。
保留旧产物，直到替代证据确认。
先盘点源码、补丁、报告和截图。
不要按目录名直接删除整个目录。
共享 WSL 空间须由所属产品确认。
