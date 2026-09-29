# qfli_rust

This Flutter app is an independent Git repository. Check out `qfli_studio_core` next to it before resolving dependencies.

```text
checkout-parent/
  qfli_studio_core/
  qfli_rust/
```

Run `flutter pub get` here, then `flutter run` for the target device. The shared editor patch is provided by `../qfli_studio_core/vendor/re_editor`.

On Windows, macOS, and Linux, install the official Rust toolchain and make `cargo` and `rustc` available on `PATH`. The Run action uses `cargo run` for projects with `Cargo.toml`, and compiles a standalone `.rs` entry with `rustc` before executing it. A project-root `input.txt` supplies standard input when present. Compiler diagnostics and program output appear in the editor terminal. Mobile platforms still require an in-process Rust runtime; the desktop toolchain cannot execute inside their application sandbox.
