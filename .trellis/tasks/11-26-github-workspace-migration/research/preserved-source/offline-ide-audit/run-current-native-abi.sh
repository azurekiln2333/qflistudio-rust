#!/bin/sh
set -eu
repo=/mnt/d/MyNewProjects/qfli_rust
toolchain=/tmp/qfli-miri-cross-1.98.1/rustup/toolchains/1.98.1-x86_64-unknown-linux-gnu
adapter=/tmp/qfli-miri-debug-1.98.1/target/x86_64-unknown-linux-gnu/debug/libqfli_miri.so
sysroot=/tmp/qfli-miri-reference-1.98.1/sysroot
scratch=$(mktemp -d /tmp/qfli-current-native-abi.XXXXXX)
cp -R "$repo/native/fixtures" "$scratch/fixtures"
cp "$adapter" "$scratch/libqfli_miri.so"
sha256sum "$adapter" "$scratch/libqfli_miri.so"
for suite in abi_test analysis_abi_test debug_abi_test; do
  cc -std=c11 -Wall -Wextra -Werror -pthread \
    "$repo/native/miri_adapter/$suite.c" -o "$scratch/$suite" -ldl
done
export LD_LIBRARY_PATH="$toolchain/lib"
export LD_PRELOAD="$toolchain/lib/librustc_driver-eaf3ed1d23ca5027.so"
for suite in abi_test analysis_abi_test debug_abi_test; do
  "$scratch/$suite" "$scratch/libqfli_miri.so" "$sysroot" "$scratch/fixtures"
done
echo "Actual pinned native ABI validation passed; scratch=$scratch"
