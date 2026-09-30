#!/bin/sh
set -eu

if [ "$#" -ne 0 ]; then
  echo "Usage: $0" >&2
  exit 2
fi

project_dir=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
fixtures="$project_dir/native/fixtures"
reference_root=/tmp/qfli-miri-reference-1.98.1
toolchain=/tmp/qfli-miri-cross-1.98.1/rustup/toolchains/1.98.1-x86_64-unknown-linux-gnu
export MIRI_SYSROOT="$reference_root/sysroot"
export RUSTC_BOOTSTRAP=1
export LD_LIBRARY_PATH="$toolchain/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
miri="$reference_root/target/debug/miri"
if [ ! -x "$miri" ] || [ ! -d "$MIRI_SYSROOT/lib/rustlib/x86_64-unknown-linux-gnu/lib" ]; then
  echo 'Run prepare_miri_sysroot.sh before the reference validation.' >&2
  exit 2
fi
sh "$project_dir/scripts/check_miri_source.sh" "$reference_root/source"
compiler_version=$("$miri" -vV)
if [ "$(printf '%s\n' "$compiler_version" | sed -n 's/^commit-hash: //p')" != '48a229ceaefd4985c50990b14116b6d856af0985' ]; then
  echo 'The reference Miri binary must use the pinned Rust 1.98.1 compiler.' >&2
  exit 2
fi

results=$(mktemp -d "$reference_root/validation.XXXXXX")
run_fixture() {
  name=$1
  expected_exit=$2
  shift 2
  actual_exit=0
  "$miri" "$fixtures/$name.rs" --edition=2024 \
    --target x86_64-unknown-linux-gnu --sysroot "$MIRI_SYSROOT" "$@" \
    >"$results/$name.stdout" 2>"$results/$name.stderr" || actual_exit=$?
  if [ "$actual_exit" -ne "$expected_exit" ]; then
    cat "$results/$name.stderr" >&2
    echo "$name: expected exit $expected_exit, got $actual_exit" >&2
    exit 1
  fi
}

run_fixture modules_generics 0
cmp "$fixtures/modules_generics.stdout" "$results/modules_generics.stdout"
cmp "$fixtures/modules_generics.stderr" "$results/modules_generics.stderr"
run_fixture stdin 0 -Zmiri-disable-isolation <"$fixtures/stdin.input"
cmp "$fixtures/stdin.stdout" "$results/stdin.stdout"
test ! -s "$results/stdin.stderr"
run_fixture nonzero 7
cmp "$fixtures/nonzero.stdout" "$results/nonzero.stdout"
test ! -s "$results/nonzero.stderr"
run_fixture invalid_borrow 1
test ! -s "$results/invalid_borrow.stdout"
grep -F 'E0502' "$results/invalid_borrow.stderr" >/dev/null
run_fixture invalid_type 1
test ! -s "$results/invalid_type.stdout"
grep -F 'E0308' "$results/invalid_type.stderr" >/dev/null
echo "Five upstream CLI fixtures passed. Results: $results"
