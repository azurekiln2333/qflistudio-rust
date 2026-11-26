#!/bin/sh
# Invoke only after a fresh named coordinator grant. No installs or global kills.
set -eu
ulimit -c 0
script_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
if ! command -v python3 >/dev/null 2>&1; then
  echo 'NATIVE_UNAVAILABLE python3 absent; no native process group was started.' >&2
  exit 3
fi
exec python3 "$script_dir/native-group-supervisor.py" "$@"
