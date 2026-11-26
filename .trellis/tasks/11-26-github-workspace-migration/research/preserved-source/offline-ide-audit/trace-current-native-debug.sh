#!/bin/sh
set -eu
ulimit -c 0
repo=/mnt/d/MyNewProjects/qfli_rust
toolchain=/tmp/qfli-miri-cross-1.98.1/rustup/toolchains/1.98.1-x86_64-unknown-linux-gnu
adapter=/tmp/qfli-current-native-abi.KrAHXV/libqfli_miri.so
sysroot=/tmp/qfli-miri-reference-1.98.1/sysroot
scratch=$(mktemp -d /tmp/qfli-current-debug-trace.XXXXXX)
cc -std=c11 -Wall -Wextra -Werror -pthread \
  "$repo/native/miri_adapter/debug_abi_test.c" -o "$scratch/debug_abi_test" -ldl
export LD_LIBRARY_PATH="$toolchain/lib"
export LD_PRELOAD="$toolchain/lib/librustc_driver-eaf3ed1d23ca5027.so"
export QFLI_DEBUG_ABI_TRACE=1
"$scratch/debug_abi_test" "$adapter" "$sysroot" "$repo/native/fixtures"
