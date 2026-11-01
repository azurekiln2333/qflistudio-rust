# Full embedded-Miri host reference preflight

This is Linux x86_64 HOST evidence only. It cannot satisfy R1's signed packaged
OHOS execution gate and cannot authorize catalog expansion. The parent report
always records `mobileExecution: not_tested` and `ohosAcceptance: not_established`.

## Inputs and execution

`scripts/verify_rust_native_catalog_host.py` validates the generated native
catalog against authored topics and both shipped UI catalogs before execution.
It runs every example and answer in deterministic topic/example/answer order,
including desktop-, Cargo- and external-labeled cases. The current inventory has
332 cases. There is no runtime-label skip or subset option.

Each case receives a fresh process and newly owned temporary project directory.
All bundled files are written exclusively with exact UTF-8 bytes after path and
digest checks; only the main entry is passed to ABI-1 `qfli_miri_run`. Cargo,
build.rs and Cargo test/build operations are never invoked. A bundled main pass
therefore leaves workspace/all-target builds and Cargo tests explicitly
`not_run`/`unverified` in individual and parent records.

The worker binds the actual C config/result layouts from `qfli_miri.h` through
ctypes, verifies ABI 1, captures all three byte channels, reads terminal native
state/exit/limits and destroys only after the synchronous run returns. Native
stdout comparison is exact UTF-8 bytes with CRLF normalization only. Answers
without authored output remain explicitly unasserted. Raw output base64, sizes
and SHA-256 accompany display text.

The defaults match `NativeMiriProgramRunner`: 10,000,000 basic blocks, 30 seconds
native time, 1 MiB output and 64 MiB guest memory. A 60-second outer timeout kills
and reaps the worker process/group before continuing. The report is atomically
saved before each worker and after every terminal result. Interrupted/missing
cases remain incomplete; a crash, loader failure or timeout cannot become a pass.

## Pinned reference command

The main session owns WSL/native execution and serialized builds. Run this inside
the existing Linux build environment, from the mounted Rust repository:

```sh
python3 scripts/verify_rust_native_catalog_host.py \
  --library /tmp/qfli-miri-adapter-1.98.1/target/x86_64-unknown-linux-gnu/debug/libqfli_miri.so \
  --sysroot /tmp/qfli-miri-reference-1.98.1/sysroot \
  --compiler-lib /tmp/qfli-miri-cross-1.98.1/rustup/toolchains/1.98.1-x86_64-unknown-linux-gnu/lib \
  --preload-driver /tmp/qfli-miri-cross-1.98.1/rustup/toolchains/1.98.1-x86_64-unknown-linux-gnu/lib/librustc_driver-eaf3ed1d23ca5027.so \
  --rustc /tmp/qfli-miri-cross-1.98.1/rustup/toolchains/1.98.1-x86_64-unknown-linux-gnu/bin/rustc \
  --report build/offline-ide-audit/native-host-catalog.json
```

The parent sets each worker's `LD_LIBRARY_PATH` to include that compiler library
directory and sets `LD_PRELOAD` to the exact pinned driver before Python starts.
It first checks `rustc --version --verbose` for release 1.98.1 and commit
`48a229ceaefd4985c50990b14116b6d856af0985`. It snapshots the adapter bytes for the
whole run, records adapter/driver/backend hashes and every guest `.rlib` hash,
and checks guest/driver/backend bytes again after execution. A changed reference
input invalidates the run. The report binds catalog and authored input digests.

## Validation ownership

`python -m unittest discover -s scripts -p test_verify_rust_native_catalog_host.py`
covers exact materialized bytes, path/digest rejection before writes, ABI layout,
byte stdout comparison, honest unasserted answers/Cargo gaps, native failures,
missing/corrupt evidence, actual subprocess timeout/reaping followed by a fresh
worker, and atomically persisted incomplete reports.

The implementer runs only those host-independent Python checks. The main session
runs the actual 332-case Linux adapter preflight and owns the resulting evidence;
successful unit checks alone do not establish any compiler/interpreter execution.

Implementation validation on 2026-10-22: all 13 focused Python tests passed,
including rejection on an unsupported host while retaining every case as missing.
The CLI `--help` path also passed. Actual Linux adapter/catalog execution remains
owned by the main session and was not run by this implementer.
