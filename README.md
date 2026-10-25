# QFLI Rust

[简体中文](README.md) · [繁體中文](README.zh-TW.md) · [English](README.en.md)

## 项目定位

本仓库是一个独立的 Flutter 应用。

它只服务 Rust，不处理别的语言。

界面与其他 QFLI 应用共用内核。

应用只提供离线功能。

## 真实功能

编辑器、教程页与示例页共用一个内核。

编辑器内的 Rust 分析不运行你的程序。

分析器把未保存的代码写入临时项目副本。

它调用 `rustc` 的元数据模式取诊断。

Cargo、构建脚本与过程宏都不会启动。

分析失败时给出不可用原因。

它不会把分析失败显示为没有错误。

工具页直接提供 Rust 离线工具。

整数工具处理前缀、后缀与类型边界。

位运算先按所选类型转换。
结果按任意精度计算。

字符串工具区分字节数与 Unicode 标量数。

项目检查工具只读元数据，不编译。

桌面端检查调用真实的 `cargo metadata`。

移动端只读项目里的 `Cargo.toml`。

`rust run <文件.rs>` 在编辑器终端和独立终端都能运行。

桌面运行按钮按配置入口选择 Cargo 目标。

入口未注册时，它用 `rustc` 编译单个文件。

长按运行当前已保存文件。

长按不改变配置入口。

桌面终端的 `rustc` 和 `cargo` 是真实命令。

`input.txt` 存在时作为标准输入。

应用内置 166 篇教程与 166 个配对示例。

教程与示例的源文件在 `tool/rust_content/topics_*.json`。

应用内容目录是 `assets/content_rust/`。

其中 23 个主题附带 Cargo 项目文件。

从示例创建项目时，应用展开附带的项目文件。

单文件导入只取示例代码。

Rust 项目模板包含 `Cargo.toml`。

它同时忽略 `target/`。

已有 Rust 目录保持原样。
它也能按单文件运行。

## 桌面与移动端差异

桌面端要求系统里有官方 Rust 工具链。

`cargo` 和 `rustc` 需要在 `PATH` 上。

桌面端直接启动真实的编译器。

移动端依赖打包好的上游 rustc/Miri 引擎。

Android 与 OHOS 已有原生清单与打包脚本。

iOS 仅提供源码构建脚本。

iOS 的打包与设备验证待完成。

移动端不提供编译器命令行。

移动端会提示改用 `rust run`。

移动端分析经原生通道。

应用包必须包含匹配的原生分析扩展。

原生通道停在求值之前。

OHOS 上的实际分析验证尚未完成。

## 相邻目录 qfli_studio_core

本仓库是一个独立 Git 仓库。

它依赖相邻的 `qfli_studio_core`。

请把两个仓库检出到同级目录。

```text
checkout-parent/
  qfli_studio_core/
  qfli_rust/
```

共享编辑器补丁来自 `../qfli_studio_core/vendor/re_editor`。

`pubspec.yaml` 通过路径依赖接入这两处。

## 离线 Cargo 限制

Cargo 全程离线运行。

依赖必须已在缓存里，或是仓库内的本地路径依赖。

注册表登录、发布与其它在线操作都不可用。

## 安装与运行

先并排放好 `qfli_studio_core` 与 `qfli_rust`。

在 `qfli_rust` 目录运行：

```text
flutter pub get
flutter run
```

桌面端还要装官方 Rust 工具链。

把 `cargo` 和 `rustc` 放进 `PATH`。

桌面分析器可读取 `QFLI_RUSTC`。

它优先于仓库内的固定工具链。

## 内容检查

教程与示例一一配对，共 166 对。

作者源改动后跑这些命令：

```text
python scripts/generate_rust_content.py
python scripts/generate_rust_content.py --check
python scripts/verify_rust_content.py --report build/rust-content-verification.json
python -m unittest discover -s scripts -p test_rust_content.py
```

`verify_rust_content.py` 用真实主机编译器逐课编译。

它运行每个程序。

它再比对程序输出与声明输出。

它同时离线检查附带项目。

缺编译器时它会失败。

只有显式加 `--structure-only` 才跳过运行。

结构检查报告不作运行结论。

## 设备验证限制

主机检查不能证明 OHOS 上的运行。

当前仓库没有 OHOS 包内源码运行的证据。

未签名的 OHOS 构建不能证明安装或运行成功。

OHOS 物理设备需要匹配的 Rust 签名配置。

历史 Android 集成测试只覆盖代表性用例。

它没有覆盖全部目录。

移动端运行结果仍待补齐。

## 原生组件

见 [native/README.md](native/README.md)。

那里记录各平台构建、打包与 ABI 契约。