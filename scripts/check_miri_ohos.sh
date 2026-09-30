#!/bin/sh
set -eu

if [ "$#" -ne 2 ]; then
  echo "Usage: $0 <Rust-1.98.1-Miri-source-directory> <OHOS-target-sysroot-directory>" >&2
  exit 2
fi

source_dir=$1
target_sysroot=$2
if [ ! -f "$source_dir/Cargo.toml" ] || [ ! -d "$target_sysroot/lib" ]; then
  echo 'Missing Miri source manifest or OHOS compiler-private library directory.' >&2
  exit 2
fi
build_root=/tmp/qfli-miri-cross-1.98.1
export RUSTUP_HOME="$build_root/rustup"
export CARGO_HOME="$build_root/cargo"
export PATH="$CARGO_HOME/bin:$PATH"
mkdir -p "$build_root"

if [ ! -x "$CARGO_HOME/bin/rustup" ]; then
  curl --fail --location --retry 2 \
    https://static.rust-lang.org/rustup/dist/x86_64-unknown-linux-gnu/rustup-init \
    --output "$build_root/rustup-init"
  chmod +x "$build_root/rustup-init"
  "$build_root/rustup-init" -y --no-modify-path --profile minimal \
    --default-toolchain 1.98.1 --component rustc-dev
fi
rustup toolchain install 1.98.1 --profile minimal --component rustc-dev

host_sysroot=$(rustc --print sysroot)
mkdir -p "$host_sysroot/lib/rustlib/aarch64-unknown-linux-ohos"
# Reuse the verified target libraries without mixing their shared source files
# into the host rustc-dev installation.
cp -R "$target_sysroot/lib" "$host_sysroot/lib/rustlib/aarch64-unknown-linux-ohos/"
if [ ! -f "$build_root/source/Cargo.toml" ]; then
  cp -R "$source_dir" "$build_root/source"
fi

export RUSTC_BOOTSTRAP=1
export CARGO_TARGET_AARCH64_UNKNOWN_LINUX_OHOS_RUSTFLAGS='-Zdual-proc-macros'
export CARGO_TARGET_DIR="$build_root/target"
rustc -vV
cargo -Zdual-proc-macros build --manifest-path "$build_root/source/Cargo.toml" \
  --target aarch64-unknown-linux-ohos --no-default-features \
  --features stack-cache --lib --locked
