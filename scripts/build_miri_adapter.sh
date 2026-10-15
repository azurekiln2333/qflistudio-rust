#!/bin/sh
set -eu

if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then
  echo "Usage: $0 <Rust-1.98.1-Miri-source> <matching-executable-toolchain> [native-host-triple]" >&2
  exit 2
fi
source_dir=$(CDPATH='' cd -- "$1" && pwd)
toolchain=$(CDPATH='' cd -- "$2" && pwd)
compiler_sysroot=${QFLI_COMPILER_SYSROOT:-$toolchain}
runtime_sysroot=${QFLI_RUNTIME_SYSROOT:-$compiler_sysroot}
repo_root=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
if [ ! -f "$source_dir/Cargo.toml" ] || [ ! -x "$toolchain/bin/rustc" ] || [ ! -x "$toolchain/bin/cargo" ]; then
  echo 'Miri source or matching rustc-dev toolchain is missing.' >&2
  exit 2
fi
compiler_version=$("$toolchain/bin/rustc" -vV)
if [ "$(printf '%s\n' "$compiler_version" | sed -n 's/^commit-hash: //p')" != '48a229ceaefd4985c50990b14116b6d856af0985' ] || \
   [ "$(printf '%s\n' "$compiler_version" | sed -n 's/^release: //p')" != '1.98.1' ]; then
  echo 'The adapter compiler must be pinned Rust 1.98.1.' >&2
  exit 2
fi
build_host=$(printf '%s\n' "$compiler_version" | sed -n 's/^host: //p')
target=${3:-$build_host}
build_root=${QFLI_ADAPTER_BUILD_ROOT:-${TMPDIR:-/tmp}/qfli-miri-adapter-1.98.1-$target}
target_lib="$compiler_sysroot/lib/rustlib/$target/lib"
if [ -z "$(find "$target_lib" -maxdepth 1 -name '*rustc_driver*' -print -quit 2>/dev/null)" ]; then
  echo "Missing matching compiler-private metadata for $target in $target_lib" >&2
  exit 2
fi
sh "$repo_root/scripts/check_miri_source.sh" "$source_dir"
mkdir -p "$build_root"
build_root=$(CDPATH='' cd -- "$build_root" && pwd)
stage=$(mktemp -d "$build_root/source.XXXXXX")
mkdir -p "$stage/miri" "$stage/adapter"
cp -R "$source_dir/." "$stage/miri/"
cp -R "$repo_root/native/miri_adapter/." "$stage/adapter/"
python3 - "$stage/miri" <<'PY'
from pathlib import Path
import sys
for path in Path(sys.argv[1]).rglob('*.rs'):
    content = path.read_bytes()
    if b'\r\n' in content:
        path.write_bytes(content.replace(b'\r\n', b'\n'))
PY
patch -F 0 -d "$stage/miri" -p1 < "$repo_root/native/patches/miri-1.98.1-embedded-session.patch"
export CARGO_HOME="${CARGO_HOME:-$build_root/cargo}"
export PATH="$toolchain/bin:$PATH"
export RUSTC_BOOTSTRAP=1
export CARGO_TARGET_DIR="$build_root/target"
case "$(uname -s)" in
  Darwin) export DYLD_LIBRARY_PATH="$toolchain/lib${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}" ;;
  *) export LD_LIBRARY_PATH="$toolchain/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" ;;
esac
unset RUSTC RUSTC_WRAPPER RUSTC_WORKSPACE_WRAPPER CARGO_ENCODED_RUSTFLAGS RUSTFLAGS
set -- "--sysroot=$compiler_sysroot" -Cprefer-dynamic -Zdual-proc-macros \
  -L "native=$runtime_sysroot/lib" -L "native=$target_lib"
library=libqfli_miri.so
case "$target" in
  x86_64-unknown-linux-gnu|aarch64-unknown-linux-gnu)
    set -- "$@" -C 'link-arg=-Wl,-rpath,$ORIGIN'
    ;;
  aarch64-unknown-linux-ohos|x86_64-unknown-linux-ohos)
    sdk=${QFLI_OHOS_SDK:-/mnt/d/ProgramFiles/Huawei/OpenHarmony/Sdk/23/native}
    if [ "$target" = aarch64-unknown-linux-ohos ]; then
      sdk_target=aarch64-linux-ohos
      export CARGO_TARGET_AARCH64_UNKNOWN_LINUX_OHOS_LINKER="${QFLI_OHOS_CLANG:-clang-18}"
    else
      sdk_target=x86_64-linux-ohos
      export CARGO_TARGET_X86_64_UNKNOWN_LINUX_OHOS_LINKER="${QFLI_OHOS_CLANG:-clang-18}"
    fi
    set -- "$@" -L "native=$sdk/llvm/lib/$sdk_target" \
      -C "link-arg=--target=$sdk_target" -C "link-arg=--sysroot=$sdk/sysroot" \
      -C "link-arg=-resource-dir=$sdk/llvm/lib/clang/15.0.4" -C 'link-arg=-Wl,-rpath,$ORIGIN'
    ;;
  aarch64-linux-android|x86_64-linux-android)
    : "${QFLI_ANDROID_NDK:?Set QFLI_ANDROID_NDK to the complete native-host NDK}"
    api=${QFLI_ANDROID_API:-21}
    case "$api" in ''|*[!0-9]*) echo 'QFLI_ANDROID_API must be an integer >= 21.' >&2; exit 2 ;; esac
    if [ "$api" -lt 21 ]; then echo 'Android 64-bit requires API >= 21.' >&2; exit 2; fi
    case "$(uname -s)" in
      Linux) ndk_host=linux-x86_64 ;;
      Darwin) ndk_host=darwin-x86_64 ;;
      *) echo 'Use the PowerShell adapter builder on Windows.' >&2; exit 2 ;;
    esac
    ndk_tools="$QFLI_ANDROID_NDK/toolchains/llvm/prebuilt/$ndk_host"
    linker="$ndk_tools/bin/$target$api-clang"
    if [ ! -x "$linker" ] || [ ! -f "$QFLI_ANDROID_NDK/source.properties" ]; then
      echo "Missing complete NDK linker: $linker" >&2; exit 2
    fi
    if [ "$target" = aarch64-linux-android ]; then
      export CARGO_TARGET_AARCH64_LINUX_ANDROID_LINKER="$linker"
    else
      export CARGO_TARGET_X86_64_LINUX_ANDROID_LINKER="$linker"
    fi
    set -- "$@" -C link-arg=-Wl,-z,max-page-size=16384 -C 'link-arg=-Wl,-rpath,$ORIGIN'
    export CC="$linker"
    export AR="$ndk_tools/bin/llvm-ar"
    ;;
  aarch64-apple-darwin|x86_64-apple-darwin|aarch64-apple-ios|aarch64-apple-ios-sim|x86_64-apple-ios)
    if [ "$(uname -s)" != Darwin ]; then echo 'Apple builds require macOS/Xcode.' >&2; exit 2; fi
    case "$target" in
      aarch64-apple-darwin) sdk_name=macosx; export MACOSX_DEPLOYMENT_TARGET="${QFLI_APPLE_DEPLOYMENT_TARGET:-11.0}" ;;
      x86_64-apple-darwin) sdk_name=macosx; export MACOSX_DEPLOYMENT_TARGET="${QFLI_APPLE_DEPLOYMENT_TARGET:-10.15}" ;;
      aarch64-apple-ios) sdk_name=iphoneos; export IPHONEOS_DEPLOYMENT_TARGET="${QFLI_APPLE_DEPLOYMENT_TARGET:-13.0}" ;;
      *) sdk_name=iphonesimulator; export IPHONEOS_DEPLOYMENT_TARGET="${QFLI_APPLE_DEPLOYMENT_TARGET:-13.0}" ;;
    esac
    export SDKROOT="$(xcrun --sdk "$sdk_name" --show-sdk-path)"
    export CC="$(xcrun --sdk "$sdk_name" --find clang)"
    export CXX="$(xcrun --sdk "$sdk_name" --find clang++)"
    export AR="$(xcrun --sdk "$sdk_name" --find ar)"
    set -- "$@" -C "linker=$CC" -C link-arg=-Wl,-rpath,@loader_path -C link-arg=-Wl,-headerpad_max_install_names
    library=libqfli_miri.dylib
    ;;
  *) echo "Unsupported adapter host target: $target" >&2; exit 2 ;;
esac
separator=$(printf '\037')
CARGO_ENCODED_RUSTFLAGS=''
for flag do
  if [ -n "$CARGO_ENCODED_RUSTFLAGS" ]; then
    CARGO_ENCODED_RUSTFLAGS="$CARGO_ENCODED_RUSTFLAGS$separator"
  fi
  CARGO_ENCODED_RUSTFLAGS="$CARGO_ENCODED_RUSTFLAGS$flag"
done
export CARGO_ENCODED_RUSTFLAGS
cargo -Zdual-proc-macros rustc --manifest-path "$stage/adapter/Cargo.toml" \
  --target "$target" --locked --offline --lib
cargo metadata --manifest-path "$stage/adapter/Cargo.toml" --locked \
  --offline --format-version=1 --filter-platform "$target" > "$build_root/dependencies-$target.json"
python3 "$repo_root/scripts/miri_build_support.py" --toolchain "$toolchain" \
  --compiler-sysroot "$compiler_sysroot" --runtime-sysroot "$runtime_sysroot" \
  --miri-source "$source_dir" --native-host "$target" \
  --adapter "$build_root/target/$target/debug/$library" \
  --dependency-metadata "$build_root/dependencies-$target.json" \
  --output "$build_root/adapter-build-$target.json"
echo "Adapter: $build_root/target/$target/debug/$library"
echo "Build record: $build_root/adapter-build-$target.json"
