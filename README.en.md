# QFLI Rust

[简体中文](README.md) · [繁體中文](README.zh-TW.md) · [English](README.en.md)

## Project overview

This repository is an independent Flutter app.

It serves Rust only. It does not handle other languages.

The UI shares its core with other QFLI apps.

The app provides offline features only.

## What the app actually does

The editor, the tutorial page and the example page share one core.

The Rust analysis inside the editor does not run your program.

The analyzer writes unsaved code into a temporary copy of the project.

It calls `rustc` in metadata mode to collect diagnostics.

It never starts Cargo, build scripts or proc macros.

When analysis fails, it reports the reason it is unavailable.

It never presents failed analysis as a result with no errors.

The tools page provides Rust offline tools directly.

The integer tools handle prefixes, suffixes and type bounds.

Bit operations first convert by the selected type.
The results use arbitrary precision.

The string tools distinguish byte count from Unicode scalar count.

The project inspection tool reads metadata only. It does not compile.

On desktop, project inspection calls real `cargo metadata`.

On mobile, it only reads the project's `Cargo.toml`.

`rust run <file.rs>` works in both the editor terminal and the standalone terminal.

On desktop, Run selects the Cargo target for the configured entry.

For an unregistered entry, it compiles a standalone file with `rustc`.

Long press Run to run the current saved file.

This keeps the configured entry unchanged.

In the desktop terminal, `rustc` and `cargo` are real commands.

`input.txt` supplies standard input when it exists.

The app bundles 166 tutorials and 166 paired examples.

The tutorial and example sources are in `tool/rust_content/topics_*.json`.

The generated catalogs are in `assets/content_rust/`.

23 topics include Cargo project files.

When you create a project from an example, the app expands its bundled project files.

Single-file imports use only the example code.

The Rust project template adds a `Cargo.toml`.

It also ignores `target/`.

Existing Rust directories stay as they are.
They can also run as single files.

## Desktop and mobile differences

Desktop requires the official Rust toolchain on the system.

`cargo` and `rustc` must be on `PATH`.

Desktop launches the real compiler directly.

Mobile depends on a packaged upstream rustc/Miri engine.

Android and OHOS have native manifests and packaging scripts.

iOS has source build scripts only.

iOS packaging and device verification remain pending.

Mobile provides no compiler command line.

Mobile points you to `rust run` instead.

Mobile analysis uses the native channel.

The app package must contain the matching native analysis extension.

The native channel stops before evaluation.

Actual analysis verification on OHOS remains pending.

## Adjacent directory qfli_studio_core

This repository is an independent Git repository.

It depends on the adjacent `qfli_studio_core`.

Check out both repositories into sibling directories.

```text
checkout-parent/
  qfli_studio_core/
  qfli_rust/
```

The shared editor patch comes from `../qfli_studio_core/vendor/re_editor`.

`pubspec.yaml` wires both of them through path dependencies.

## Offline Cargo restrictions

Cargo runs fully offline.

Dependencies must already be in the cache, or be local path dependencies inside the repository.

Registry login, publishing and other online operations are unavailable.

## Setup and run

Place `qfli_studio_core` and `qfli_rust` side by side first.

Run these commands in the `qfli_rust` directory:

```text
flutter pub get
flutter run
```

Desktop also needs the official Rust toolchain installed.

Put `cargo` and `rustc` on `PATH`.

The desktop analyzer can read `QFLI_RUSTC`.

It takes priority over the pinned toolchain in the repository.

`QFLI_RUSTC` applies to desktop analysis only. It does not configure running your program.

## Content verification

Tutorials and examples pair one to one, 166 pairs in total.

After you change the authored sources, run these commands:

```text
python scripts/generate_rust_content.py
python scripts/generate_rust_content.py --check
python scripts/verify_rust_content.py --report build/rust-content-verification.json
python -m unittest discover -s scripts -p test_rust_content.py
```

`verify_rust_content.py` compiles every lesson with a real host compiler.

It runs every program.

It then compares the actual output with the declared output.

It also checks the attached projects offline.

It fails when the compiler is missing.

It skips execution only when you explicitly add `--structure-only`.

A structure-only report makes no execution claim.

## Device verification limitations

A host check cannot prove execution on OHOS.

This repository currently has no evidence of in-package source execution on OHOS.

An unsigned OHOS build cannot prove successful installation or execution.

An OHOS physical device needs a matching Rust signing configuration.

Historical Android integration tests cover representative cases only.

It does not cover the whole catalog.

Mobile execution results remain pending.

## Native components

See [native/README.md](native/README.md).

It records the per-platform builds, packaging and the ABI contract.