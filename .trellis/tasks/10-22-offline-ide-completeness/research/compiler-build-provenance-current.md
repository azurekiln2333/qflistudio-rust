# Current patched compiler build provenance

Status: source implementation and pure fixtures only.
No patched compiler, adapter or device artifact has been built in this work.

## Source contract

The reviewed compiler patch changes eight files.
SHA-256: `7236eff645ddf45eb87e78865a7d805a3443234e23c0855bee7956882c9989ee`.
It removes ambient environment fallback from embedded macro expansion.
It requires a session FileLoader and uses it for diagnostic retry reads.
It refuses procedure-macro crates before executable loading.
It refuses SDylib interfaces before the locator starts a host compiler.
The standalone procedure-macro API remains outside the adapter contract.
Metadata search, backend loading and output paths remain separate boundaries.

The producer copies complete pinned source into an owned directory.
It applies exact hunks without fuzz and preserves the input source.
It binds input and patched tree hashes and every changed-file hash.
Linux GNU, OHOS, Android and iOS configurations are supported in source.
Linux/OHOS accept explicit local tool inputs without a PATH fallback.
Actual bootstrap compatibility remains unrun for these changes.
There is no patched Windows producer in this script.

Compiler schema 2 requires status built, the patch identity and selected host.
It records the exact compiler-private metadata and runtime artifact inventory.
An adapter record binds that compiler record, adapter and compiler-library hashes.
A version string alone cannot satisfy either verifier.
The Windows adapter builder requires explicit rebuilt sysroots and their record.
It no longer extracts an official rustc-dev archive as a fallback.
The shell builder requires the same record before staging and Cargo.

All builders use the shared disjoint-root guard before generated writes.
It rejects equal paths and ancestry in both directions.
It resolves aliases and follows Windows case semantics on Windows.
Explicit adapter Cargo caches follow the same protected-input rule.
The compiler producer also protects selected SDKs and local tool parents.

Python and OHOS packagers verify adapter provenance before native copies.
OHOS also checks dependency metadata, selected backend and compiler dependencies.
Copied native bytes retain their observed checksums.
Runtime manifests preserve the compiler boundary and build-record hashes.
The explicit Windows WSL mapper locates producer paths through the chosen distro.
It preserves producer record content and does not invoke a WSL command.
Mapping fixtures access only local temporary files.

## Verification

Pure tests prohibit subprocess APIs and use inert artifact bytes.
They cover record tampering, missing metadata, changed driver/backend/adapter,
wrong roots and hosts, artifact inventory changes, path aliases and path mapping.
Bootstrap configuration tests cover both Linux/OHOS architectures and local tools.
Main-entry overlap regressions require zero generated writes and no tool calls.
PowerShell consumers pass static AST parsing.
The eight-file patch passes application checks on temporary pinned source copies.
Original compiler source remains unchanged.

The authoritative regression files are:

- scripts/test_build_rustc_host.py
- scripts/test_miri_build_support.py
- scripts/test_compiler_provenance_consumers.py

Counts must come from the final test run rather than this evolving note.
The executable contract is .trellis/spec/backend/compiler-build-provenance.md.

## Remaining acceptance

A fresh named grant is required before compiler/native/SDK execution.
Actual bootstrap, matching adapter and backend builds remain unrun.
The current OHOS libraries are stale and cannot satisfy the new ABI gate.
Both target packages need rebuilding and final archive inspection.
All 332 existing catalog cases and six native feature checks remain unrun on OHOS.
The full all-product goal stays active.
No device, signed release or runtime confinement success is claimed.
