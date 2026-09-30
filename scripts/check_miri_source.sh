#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 <Rust-1.98.1-Miri-source-directory>" >&2
  exit 2
fi

cd -- "$1"
file_list=$(mktemp)
manifest=$(mktemp)
normalized=$(mktemp)
trap 'rm -f "$file_list" "$manifest" "$normalized"' 0

# Hash build inputs by relative path after normalizing Windows checkout CRLF.
find src cargo-miri/src -type f >"$file_list"
printf '%s\n' Cargo.toml Cargo.lock cargo-miri/Cargo.toml \
  cargo-miri/Cargo.lock cargo-miri/build.rs >>"$file_list"
if [ -e build.rs ]; then
  printf '%s\n' build.rs >>"$file_list"
fi
LC_ALL=C sort "$file_list" -o "$file_list"
while IFS= read -r file; do
  sed 's/\r$//' "$file" >"$normalized"
  checksum=$(sha256sum "$normalized")
  printf '%s  %s\n' "${checksum%% *}" "$file" >>"$manifest"
done <"$file_list"
checksum=$(sha256sum "$manifest")
actual_digest=${checksum%% *}
# Rust 1.98.1 commit 48a229ceaefd4985c50990b14116b6d856af0985.
expected_digest=92f51c0345496c6ef1edbba009985c84b612630dd5c7e81ea2cdd826d0d85764
if [ "$actual_digest" != "$expected_digest" ]; then
  echo "Miri source differs from pinned Rust 1.98.1 inputs: $actual_digest" >&2
  exit 2
fi
