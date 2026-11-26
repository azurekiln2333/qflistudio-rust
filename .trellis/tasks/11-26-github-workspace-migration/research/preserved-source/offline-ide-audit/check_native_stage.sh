#!/bin/sh
set -u
toolchain=/tmp/qfli-miri-cross-1.98.1/rustup/toolchains/1.98.1-x86_64-unknown-linux-gnu
export PATH="$toolchain/bin:$PATH"
export LD_LIBRARY_PATH="$toolchain/lib"
export RUSTC_BOOTSTRAP=1
export CARGO_HOME=/tmp/qfli-miri-cross-1.98.1/cargo
export CARGO_TARGET_DIR=/tmp/qfli-miri-debug-1.98.1/target
export CARGO_BUILD_JOBS=1
export RUSTFLAGS="--sysroot=$toolchain -Cprefer-dynamic -Zdual-proc-macros -Lnative=$toolchain/lib -Lnative=$toolchain/lib/rustlib/x86_64-unknown-linux-gnu/lib"
unset CARGO_ENCODED_RUSTFLAGS RUSTC RUSTC_WRAPPER RUSTC_WORKSPACE_WRAPPER
cargo -Zdual-proc-macros check --manifest-path /tmp/qfli-miri-debug-1.98.1/source.PUw20U/adapter/Cargo.toml --target x86_64-unknown-linux-gnu --locked --offline --lib
result=$?
echo "CHECK_EXIT=$result"
exit "$result"
