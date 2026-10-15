# qfli_rust

This Flutter app is an independent Git repository. Check out `qfli_studio_core` next to it before resolving dependencies.

```text
checkout-parent/
  qfli_studio_core/
  qfli_rust/
```

Run `flutter pub get` here, then `flutter run` for the target device. The shared editor patch is provided by `../qfli_studio_core/vendor/re_editor`.

On Windows, macOS, and Linux, install the official Rust toolchain and make `cargo` and `rustc` available on `PATH`. The Run action selects the Cargo target for the configured entry, or compiles an unregistered standalone `.rs` file with `rustc`. Long press runs the current saved file without changing the configured entry. A project-root `input.txt` supplies standard input when present. Compiler diagnostics and program output appear in the editor terminal.

Both the editor terminal and the standalone terminal accept `rust run src/main.rs` (or `rust src/main.rs`) through the same runner. Desktop terminals additionally expose the real `rustc` and `cargo` commands. This product runs Cargo offline; dependencies must already be cached or bundled as local path dependencies. Registry login, publishing and other online Cargo actions are unavailable.

Android and OHOS use a packaged upstream rustc/Miri engine instead of launching a desktop compiler. Native libraries and the matching guest sysroot must be packaged for the target architecture; see [native/README.md](native/README.md). Android arm64 has passed the real device integration suite. An unsigned OHOS build does not prove application installation or device execution: those require a matching Rust signing profile. Raw compiler CLI commands on mobile report their limitation and point to `rust run`.

New Rust projects include `Cargo.toml` and ignore Cargo's `target/` directory. Existing Rust folders are left as they are and can still run as standalone source files.

The app ships 166 original Chinese tutorials and 166 paired examples, with complete exercises, in `assets/content_rust/`. Their authored sources are `tool/rust_content/topics_*.json`; the Rust profile loads these instead of the shared placeholder catalog. Other products' catalogs are unaffected. Regenerate and verify with:

```text
python scripts/generate_rust_content.py
python scripts/generate_rust_content.py --check
python scripts/verify_rust_content.py --report build/rust-content-verification.json
python -m unittest discover -s scripts -p test_rust_content.py
```

Verification compiles and runs every lesson and exercise answer with a real host compiler, compares declared output, and checks bundled Cargo projects offline. It fails when the compiler is missing unless `--structure-only` is explicitly requested; a structure-only report makes no execution claim. Single-file imports work in the editor and existing projects; additional Cargo project files are expanded only when creating a new project from a bundled example.
