#!/bin/sh
set -eu

if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then
  echo "Usage: $0 <Rust-1.98.1-Miri-source> <matching-Linux-toolchain> [target-triple]" >&2
  exit 2
fi
source_dir=$(realpath "$1")
toolchain=$(realpath "$2")
compiler_sysroot=${QFLI_COMPILER_SYSROOT:-$toolchain}
target=${3:-x86_64-unknown-linux-gnu}
repo_root=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
build_root=${QFLI_ADAPTER_BUILD_ROOT:-/tmp/qfli-miri-adapter-1.98.1}
if [ ! -f "$source_dir/Cargo.toml" ] || [ ! -x "$toolchain/bin/rustc" ] || [ ! -x "$toolchain/bin/cargo" ]; then
  echo 'Miri source or matching rustc-dev toolchain is missing.' >&2
  exit 2
fi
compiler_version=$("$toolchain/bin/rustc" -vV)
if [ "$(printf '%s\n' "$compiler_version" | sed -n 's/^commit-hash: //p')" != '48a229ceaefd4985c50990b14116b6d856af0985' ]; then
  echo 'The adapter compiler must be pinned Rust 1.98.1.' >&2
  exit 2
fi
sh "$repo_root/scripts/check_miri_source.sh" "$source_dir"
mkdir -p "$build_root/miri" "$build_root/adapter"
cp -R "$source_dir/." "$build_root/miri/"
cp -R "$repo_root/native/miri_adapter/." "$build_root/adapter/"
# Older patch invocations left backups beside the staged Rust sources.
find "$build_root/miri/src" -type f -name '*.rs.orig' -delete
sh "$repo_root/scripts/check_miri_source.sh" "$build_root/miri"
find "$build_root/miri/src" -type f -name '*.rs' -exec sed -i 's/\r$//' {} +
patch --fuzz=0 --no-backup-if-mismatch -d "$build_root/miri" -p1 < "$repo_root/native/patches/miri-1.98.1-embedded-session.patch"
export CARGO_HOME="${CARGO_HOME:-/tmp/qfli-miri-cross-1.98.1/cargo}"
export PATH="$toolchain/bin:$PATH"
export RUSTC_BOOTSTRAP=1
export CARGO_TARGET_DIR="$build_root/target"
export LD_LIBRARY_PATH="$toolchain/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
unset RUSTC RUSTC_WRAPPER RUSTC_WORKSPACE_WRAPPER CARGO_ENCODED_RUSTFLAGS
export RUSTFLAGS="--sysroot=$compiler_sysroot -L native=$toolchain/lib -Cprefer-dynamic"
case "$target" in
  x86_64-unknown-linux-gnu) ;;
  aarch64-unknown-linux-ohos|x86_64-unknown-linux-ohos)
    sdk=${QFLI_OHOS_SDK:-/mnt/d/ProgramFiles/Huawei/OpenHarmony/Sdk/23/native}
    if [ "$target" = aarch64-unknown-linux-ohos ]; then
      sdk_target=aarch64-linux-ohos
      export CARGO_TARGET_AARCH64_UNKNOWN_LINUX_OHOS_LINKER="${QFLI_OHOS_CLANG:-clang-18}"
    else
      sdk_target=x86_64-linux-ohos
      export CARGO_TARGET_X86_64_UNKNOWN_LINUX_OHOS_LINKER="${QFLI_OHOS_CLANG:-clang-18}"
    fi
    export RUSTFLAGS="--sysroot=$compiler_sysroot -Cprefer-dynamic -Zdual-proc-macros -L native=$compiler_sysroot/lib/rustlib/$target/lib -L native=$sdk/llvm/lib/$sdk_target -C link-arg=--target=$sdk_target -C link-arg=--sysroot=$sdk/sysroot -C link-arg=-resource-dir=$sdk/llvm/lib/clang/15.0.4 -C link-arg=-Wl,-rpath,\$ORIGIN"
    ;;
  *) echo "Unsupported adapter host target: $target" >&2; exit 2 ;;
esac
cargo -Zdual-proc-macros rustc --manifest-path "$build_root/adapter/Cargo.toml" \
  --target "$target" --locked --offline --lib
cargo metadata --manifest-path "$build_root/adapter/Cargo.toml" --locked \
  --offline --format-version=1 --filter-platform "$target" \
  > "$build_root/dependencies.json"
cp "$build_root/dependencies.json" "$build_root/dependencies-$target.json"
echo "Adapter: $build_root/target/$target/debug/libqfli_miri.so"
