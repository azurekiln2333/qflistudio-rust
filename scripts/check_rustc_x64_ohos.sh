#!/bin/bash
set -euo pipefail

if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then
  echo "Usage: $0 <OHOS-native-SDK-directory> <Linux-Rust-1.98.1-toolchain-directory> [Rust-1.98.1-source-directory]" >&2
  exit 2
fi

sdk_dir=$(realpath "$1")
stage0_dir=$(realpath "$2")
build_root=${QFLI_RUSTC_BUILD_ROOT:-/tmp/qfli-rustc-x64-ohos}
jobs=${QFLI_RUSTC_BUILD_JOBS:-4}
source_sha=be1816e7f6c40abb90245ad6e024bed2a7e88d7dda4561e4d5470207df616b9f
source_commit=48a229ceaefd4985c50990b14116b6d856af0985
source_archive="$build_root/rustc-1.98.1-src.tar.xz"
source_dir=${3:-"$build_root/rustc-1.98.1-src"}
resource_dir="$sdk_dir/llvm/lib/clang/15.0.4"

for tool in curl tar sha256sum python3 clang clang++ ld.lld llvm-ar-18 llvm-ranlib-18 readelf; do
  command -v "$tool" >/dev/null || { echo "Missing required tool: $tool" >&2; exit 2; }
done
if [ ! -f "$sdk_dir/sysroot/usr/lib/x86_64-linux-ohos/libc.so" ] || \
   [ ! -f "$resource_dir/lib/x86_64-linux-ohos/libclang_rt.builtins.a" ] || \
   [ ! -x "$stage0_dir/bin/rustc" ] || [ ! -x "$stage0_dir/bin/cargo" ]; then
  echo 'Missing OHOS SDK runtime resources or Linux stage0 toolchain.' >&2
  exit 2
fi
case "$jobs" in
  ''|*[!0-9]*|0) echo 'QFLI_RUSTC_BUILD_JOBS must be a positive integer.' >&2; exit 2 ;;
esac
if ! "$stage0_dir/bin/rustc" -vV | \
  awk -v commit="$source_commit" '
    /^release: / { version = ($2 == "1.98.1") }
    /^commit-hash: / { matches = ($2 == commit) }
    /^host: / { host = ($2 == "x86_64-unknown-linux-gnu") }
    END { exit !(version && matches && host) }'; then
  echo 'Stage0 must be official Rust 1.98.1 for x86_64-unknown-linux-gnu.' >&2
  exit 2
fi
if [ -z "$(find "$stage0_dir/lib/rustlib/x86_64-unknown-linux-ohos/lib" \
  -maxdepth 1 -name 'libcore-*.rlib' -print -quit 2>/dev/null)" ]; then
  echo 'Stage0 must include the official Rust 1.98.1 x64 OHOS rust-std target.' >&2
  echo 'Install it with: rustup target add --toolchain 1.98.1 x86_64-unknown-linux-ohos' >&2
  exit 2
fi

mkdir -p "$build_root/bin" "$build_root/cargo"
build_root=$(realpath "$build_root")
if [ "$#" -eq 2 ]; then
  if [ ! -f "$source_archive" ]; then
    curl --fail --location --retry 2 --silent --show-error \
      https://static.rust-lang.org/dist/rustc-1.98.1-src.tar.xz \
      --output "$source_archive.download"
    mv "$source_archive.download" "$source_archive"
  fi
  printf '%s  %s\n' "$source_sha" "$source_archive" | sha256sum --check
  if [ ! -f "$source_dir/compiler/rustc_driver/Cargo.toml" ]; then
    tar -xf "$source_archive" -C "$build_root"
  fi
fi
if [ -f "$source_dir/git-commit-hash" ]; then
  actual_commit=$(cat "$source_dir/git-commit-hash")
else
  actual_commit=$(git -C "$source_dir" rev-parse HEAD)
fi
if [ "$actual_commit" != "$source_commit" ] || \
   [ ! -f "$source_dir/compiler/rustc_driver/Cargo.toml" ] || \
   [ ! -f "$source_dir/library/backtrace/Cargo.toml" ]; then
  echo 'Source must be pinned Rust 1.98.1 with compiler and backtrace sources present.' >&2
  exit 2
fi

# Linux clang links OHOS binaries using the Windows SDK's platform-neutral
# headers, CRT objects and libraries; clang.exe cannot consume Linux /tmp paths.
cat > "$build_root/bin/ohos-clang" <<EOF
#!/bin/sh
exec /usr/bin/clang --target=x86_64-linux-ohos \\
  --sysroot='$sdk_dir/sysroot' -resource-dir '$resource_dir' \\
  -L'$sdk_dir/llvm/lib/x86_64-linux-ohos' -D__MUSL__ -fuse-ld=lld "\$@"
EOF
cat > "$build_root/bin/ohos-clang++" <<EOF
#!/bin/sh
exec /usr/bin/clang++ --target=x86_64-linux-ohos \\
  --sysroot='$sdk_dir/sysroot' -resource-dir '$resource_dir' \\
  -L'$sdk_dir/llvm/lib/x86_64-linux-ohos' -D__MUSL__ -fuse-ld=lld "\$@"
EOF
chmod +x "$build_root/bin/ohos-clang" "$build_root/bin/ohos-clang++"
printf 'int main(void) { return 0; }\n' | "$build_root/bin/ohos-clang" \
  -x c - -o "$build_root/ohos-link-check"

cat > "$build_root/bootstrap.toml" <<EOF
change-id = "ignore"

[build]
build = "x86_64-unknown-linux-gnu"
host = ["x86_64-unknown-linux-ohos"]
target = ["x86_64-unknown-linux-ohos"]
build-dir = "$build_root/build"
rustc = "$stage0_dir/bin/rustc"
cargo = "$stage0_dir/bin/cargo"
jobs = $jobs
submodules = false
local-rebuild = true
optimized-compiler-builtins = false
sanitizers = false
profiler = false

[rust]
channel = "stable"
download-rustc = false
codegen-backends = ["cranelift"]
jemalloc = false
llvm-tools = false
llvm-bitcode-linker = false
lld = false
lto = "off"
llvm-libunwind = "no"
debuginfo-level = 0

[llvm]
download-ci-llvm = false

[target.x86_64-unknown-linux-ohos]
cc = "$build_root/bin/ohos-clang"
cxx = "$build_root/bin/ohos-clang++"
linker = "$build_root/bin/ohos-clang"
ar = "/usr/bin/llvm-ar-18"
ranlib = "/usr/bin/llvm-ranlib-18"
EOF

export CARGO_HOME="$build_root/cargo"
export RUSTC_BOOTSTRAP=1
export LD_LIBRARY_PATH="$stage0_dir/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
unset RUSTC RUSTC_WRAPPER RUSTC_WORKSPACE_WRAPPER RUSTFLAGS CARGO_ENCODED_RUSTFLAGS
"$stage0_dir/bin/rustc" -vV
python3 "$source_dir/x.py" build --config "$build_root/bootstrap.toml" \
  --stage 1 --host x86_64-unknown-linux-ohos \
  --target x86_64-unknown-linux-ohos compiler/rustc_driver \
  2>&1 | tee "$build_root/rustc-driver-build.log"
python3 "$source_dir/x.py" build --config "$build_root/bootstrap.toml" \
  --stage 1 --host x86_64-unknown-linux-ohos \
  --target x86_64-unknown-linux-ohos compiler \
  2>&1 | tee "$build_root/compiler-assembly-build.log"

stage1_dir="$build_root/build/x86_64-unknown-linux-ohos/stage1"
backend="$stage1_dir/lib/rustlib/x86_64-unknown-linux-ohos/codegen-backends/librustc_codegen_cranelift-1.98.1.so"
readelf -h "$backend"
printf 'OHOS runtime sysroot: %s\n' "$stage1_dir"
printf 'Build-time compiler-private sysroot: %s\n' \
  "$build_root/build/x86_64-unknown-linux-gnu/stage0-sysroot"
