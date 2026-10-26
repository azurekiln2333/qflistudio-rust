# Patched compiler build provenance

Apply this contract to compiler bootstrap, adapter builders and runtime packagers.
It supplements `native-runtime.md`. Source checks do not prove a working runtime.

## Compiler identity

Rust stays pinned to version 1.98.1 and commit
`48a229ceaefd4985c50990b14116b6d856af0985`.
The compiler boundary patch is
`native/patches/rustc-1.98.1-embedded-compiler-boundary.patch`.
Its reviewed SHA-256 is
`7236eff645ddf45eb87e78865a7d805a3443234e23c0855bee7956882c9989ee`.
Keep the patch in LF form. A matching upstream version does not identify this patch.

The patch controls ambient environment macro fallback and requires a FileLoader.
It routes invalid-UTF-8 diagnostic retries through that loader.
Embedded compiler sessions reject procedure-macro crates before dynamic loading.
They reject SDylib interfaces before the locator starts a compiler subprocess.
The standalone rust-analyzer procedure-macro API is outside this contract.
Do not call that API from an embedded adapter.
Metadata discovery and backend loading remain separate trusted-artifact boundaries.

## Build and verification

`scripts/build_rustc_host.py` copies complete pinned source into an owned tree.
It applies exact patch hunks without fuzz and preserves input source.
It records original and patched tree identities and every patched-file hash.
No generated output or cache may overwrite a protected compiler input.
Use `ensure_disjoint_build_root` before writing wrappers or staging source.
The guard rejects equal paths and ancestry in both directions.
Resolve aliases before comparison. Windows comparisons follow Windows path semantics.

A successful compiler record uses schema 2 and status `built`.
It binds the native host, source commit, boundary kind, patch hash and all selected
compiler-private metadata and runtime library hashes.
A configured-only output is not a successful build record.
Never substitute an official rustc-dev archive for rebuilt private metadata.

Adapter schema 1 includes the compiler-record path and hash, boundary identity,
actual adapter hash, complete compiler runtime library inventory and dependency
metadata hash. Builders verify the compiler before staging or Cargo.
Packagers verify the adapter and compiler records before copying native libraries.
Copied compiler dependencies and selected backend must match verified hashes.
A native copy must match its observed hash before platform transformations.
Apple framework rewriting and signing happen after this check.
Their manifests bind both the source hash and the final transformed hash.

The shared commands are:

```text
python scripts/miri_build_support.py check-build-root --build-root <output> --input-root <input>
python scripts/miri_build_support.py check-compiler --compiler-build-info <record> --compiler-sysroot <private> --runtime-sysroot <runtime> --native-host <host>
python scripts/miri_build_support.py verify-adapter --adapter-build-info <record> --adapter <library> --native-host <host>
```

The shell builder accepts `QFLI_COMPILER_BUILD_INFO`.
The Windows builder requires `CompilerSysroot`, `RuntimeSysroot` and
`CompilerBuildInfo`. It has no official-archive fallback.
The OHOS packager requires `AdapterBuildInfo`.
Its explicit `WslDistro` maps producer paths for local record and artifact reads.
Path mapping does not rewrite producer records or start a WSL command.
The consumer still verifies every mapped byte against the original records.

## Static archive gate

The audit HAP inspector verifies 27 required adapter exports against ELF dynamic
symbols. A manifest checksum alone cannot establish ABI availability.
Defined global, weak or unique callable symbols may use default or protected
visibility. Undefined, local, internal and hidden symbols cannot satisfy the ABI.
All native members require manifest coverage or the explicit Flutter/app/probe
allowlist. The optional native probe must export its own ABI.
Every regular member under libs/ must use the selected ABI and a direct .so name.
The archive inspector requires explicit trusted compiler and adapter record bytes.
It compares manifest record hashes, the complete compiler boundary identity,
adapter bytes and packaged compiler libraries. Adapter compiler-library entries
must also match the compiler record runtime artifact inventory.
Inspection never resolves producer paths from those records.
The audit builder captures both initial record hashes in build.json.
Metadata inspection compares them with the exact consumed record bytes.
The inspector names these inputs --compiler-record and --adapter-record.
The builder names them CompilerRecord and AdapterRecord.
These checks keep `deviceExecuted` false.

## Verification limits

Pure fixture regressions cover record tampering, artifact changes, path mapping,
input/output overlap, Linux/OHOS configuration and malformed ELF tables.
Run a real compiler bootstrap separately under a fresh named runtime grant.
Then rebuild the adapter, verify native negative cases and package both OHOS ABIs.
Execute every existing catalog case and native feature check on the actual target.
Only those later results can establish runtime and device acceptance.
