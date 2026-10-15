#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 <Rust-1.98.1-Miri-source-directory>" >&2
  exit 2
fi

source_dir=$(realpath "$1")
script_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
if [ ! -f "$source_dir/Cargo.toml" ] || [ ! -f "$source_dir/cargo-miri/Cargo.lock" ]; then
  echo 'Missing Miri and cargo-miri source manifests/lockfile.' >&2
  exit 2
fi
sh "$script_dir/check_miri_source.sh" "$source_dir"

build_root=/tmp/qfli-miri-reference-1.98.1
export RUSTUP_HOME=/tmp/qfli-miri-cross-1.98.1/rustup
export CARGO_HOME=/tmp/qfli-miri-cross-1.98.1/cargo
export PATH="$CARGO_HOME/bin:$PATH"
export RUSTUP_TOOLCHAIN=1.98.1
export RUSTC_BOOTSTRAP=1
export CARGO_TARGET_DIR="$build_root/target"
export CARGO_BUILD_JOBS=2

rustc -vV
if [ "$(rustc -vV | sed -n 's/^commit-hash: //p')" != '48a229ceaefd4985c50990b14116b6d856af0985' ]; then
  echo 'The reference compiler must be Rust 1.98.1 from the pinned commit.' >&2
  exit 2
fi
rustup component add rust-src --toolchain 1.98.1
host_sysroot=$(rustc --print sysroot)
export LD_LIBRARY_PATH="$host_sysroot/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
mkdir -p "$build_root"
if [ ! -f "$build_root/source/Cargo.toml" ]; then
  cp -R "$source_dir" "$build_root/source"
fi
sh "$script_dir/check_miri_source.sh" "$build_root/source"

cargo rustc --manifest-path "$build_root/source/Cargo.toml" \
  --no-default-features --features stack-cache --bin miri --locked \
  -- -L "native=$host_sysroot/lib"
cargo build --manifest-path "$build_root/source/cargo-miri/Cargo.toml" --locked

# The interpreted target is independent of the architecture of the native host.
export MIRI="$CARGO_TARGET_DIR/debug/miri"
export MIRI_SYSROOT="$build_root/sysroot"
"$CARGO_TARGET_DIR/debug/cargo-miri" miri setup --target x86_64-unknown-linux-gnu
python3 "$script_dir/miri_build_support.py" record-guest --toolchain "$host_sysroot" \
  --miri-source "$source_dir" --guest-sysroot "$MIRI_SYSROOT"
echo "MIR sysroot: $MIRI_SYSROOT"
