# Cargo-ready Rust Projects

`RustProjectStore` extends the shared `ProjectStore` and overrides only `createProject`. It delegates project registration and template writing to the existing store, then adds Cargo's manifest and a `target/` ignore rule for the Rust template. The app constructs this store in `main`, so existing create and example flows use it without shared-core changes.

The package name is an ASCII Cargo-compatible slug from the display name. A deterministic suffix derived from the Unicode code points distinguishes names with no ASCII slug. The manifest uses the 2021 edition for broad stable-toolchain compatibility. The operation does not rewrite projects loaded from disk.

Verify the generated files and `cargo metadata`, then use the existing `RustProgramRunner` to compile and execute a newly created project. Keep storage and source paths inside a temporary test directory.
