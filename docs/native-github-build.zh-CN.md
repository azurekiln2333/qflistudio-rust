# GitHub native 构建

GitHub Actions 负责编译 native 运行库。
本地只需下载匹配平台的产物。
云端构建不会清理本地旧文件。

## 构建范围

| 平台 | 架构 | 原生库形式 |
| --- | --- | --- |
| Linux | x64 | `.so` 及配套依赖 |
| Windows | x64 GNU | `.dll` 及配套依赖 |
| macOS | arm64 | framework 及配套依赖 |

这些产物供 Flutter 应用打包使用。
它们不是可直接安装的应用。
本工作流不生成 APK、HAP 或桌面安装包。

编译器固定为 Rust 1.98.1。
构建过程应用项目的编译器补丁。
脚本校验源码、补丁和编译产物。
普通 `rustc-dev` 不能替代补丁版编译器。

## 下载产物

1. 打开仓库的 **Actions** 页面。
2. 选择 **Native runtime** 工作流。
3. 打开所需提交对应的运行记录。
4. 在 **Artifacts** 区域下载目标平台包。
5. 解压 GitHub 下载的 ZIP 文件。
6. 校验包内的 SHA-256 清单。
7. 将运行库压缩包解压到仓库根目录。

下载时需登录 GitHub。
构建失败时，请下载诊断日志。
失败任务不会上传可用运行库。
请勿混用不同提交或平台的库。

| 下载项 | 对应平台 |
| --- | --- |
| `native-runtime-linux-x64` | Linux x64 |
| `native-runtime-windows-x64` | Windows x64 GNU |
| `native-runtime-macos-arm64` | macOS arm64 |

平台包和日志保留 14 天。
每个下载项包含 `.tar.gz` 和校验文件。
GitHub 下载的 ZIP 文件包含这两个文件。

在压缩包所在目录运行校验命令：

```sh
sha256sum -c native-runtime-linux-x64.tar.gz.sha256
```

macOS 可使用 `shasum -a 256`。
Windows 可使用 `Get-FileHash`。
请将结果与 `.sha256` 文件逐字比较。

从仓库根目录解压目标平台包：

```sh
tar -xzf <下载目录>/native-runtime-linux-x64.tar.gz
```

请替换命令中的平台名和下载路径。

## 产物内容

| 内容 | 用途 |
| --- | --- |
| `native/build/runtime/<平台>-<架构>/` | 原生库、依赖和包清单 |
| `assets/miri/manifest.<平台>-<架构>.json` | Flutter 运行库清单 |
| `assets/miri/*.bin` | MIR 标准库和许可证 |
| `native/include/` | C 接口声明 |
| `build-info/` | 固定版本、补丁和文件校验信息 |
| SHA-256 清单 | 下载后的完整性校验 |

运行库需要完整的依赖和 MIR 数据。
仅复制适配器 DLL 或 SO 无法满足要求。
macOS framework 使用临时签名。
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
确认云端产物可用后，再决定是否移除。

本地应用打包仍需要 native 产物。
请保留所需平台库和 `assets/miri/`。
云端构建可省去本地编译器中间文件。
Flutter 应用构建仍会生成本地缓存。
