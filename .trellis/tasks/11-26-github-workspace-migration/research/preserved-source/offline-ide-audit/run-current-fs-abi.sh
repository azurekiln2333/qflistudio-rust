#!/bin/sh
set -eu
repo=/mnt/d/MyNewProjects/qfli_rust
toolchain=/tmp/qfli-miri-cross-1.98.1/rustup/toolchains/1.98.1-x86_64-unknown-linux-gnu
scratch=$(mktemp -d /tmp/qfli-current-fs-abi.XXXXXX)
cc -std=c11 -Wall -Wextra -Werror "$repo/native/miri_adapter/fs_abi_test.c" -ldl -o "$scratch/fs_abi_test"
export LD_LIBRARY_PATH="$toolchain/lib"
export LD_PRELOAD="$toolchain/lib/librustc_driver-eaf3ed1d23ca5027.so"
"$scratch/fs_abi_test" /tmp/qfli-current-native-abi.KrAHXV/libqfli_miri.so \
  /tmp/qfli-miri-reference-1.98.1/sysroot "$repo/native/fixtures" - \
  "$repo/build/offline-ide-audit/fs-abi-catalog"
