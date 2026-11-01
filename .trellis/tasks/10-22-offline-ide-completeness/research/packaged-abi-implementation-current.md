# Packaged runtime ABI implementation — current

Implementation checkpoint for `.trellis/tasks/10-22-offline-ide-completeness`.
Owned paths: `scripts/inspect_rust_catalog_hap.py` and this document only.
Owner of `scripts/test_inspect_rust_catalog_hap.py` is p4 (`w2B:p4`).

## 0. Boundary

No external tool, native SDK, Rust/cargo build, HAP build, WSL, device command,
process control or heavy test was used. No source outside the two owned paths was
edited, nothing was committed or pushed, and no stale audit lock was reclaimed.
Current host slot is `C646` (sole), Rust holds no slot (`Rust654 DEFER`), so no
build/packaging/device step was attempted. Everything below is static analysis
plus pure-Python fixture checks.

## 1. Code written

`scripts/inspect_rust_catalog_hap.py`
sha256 `3f8d1eb83b0303d78a7c71f8ff2ff4e43a8757fce266ceaa5710d80bf5ee6112`
(38548 bytes). Six reviews in this slice added loader facts, one native-payload
rule, the compiler-provenance gate, the build-metadata binding, the runtime
inventory link and the artifact path rule:

- `STB_WEAK` definitions count as exports, and a definition whose nonreserved
  `st_shndx` lies past the section table is corrupt input (§4.3, §4.4).
- A regular non-`.so` file under `libs/<abi>/` is an unmanifested native payload
  and fails the inspection (§8.1).
- The packaged manifest must carry the exact reviewed compiler boundary, and its
  compiler/adapter record hashes must match explicit trusted record bytes that
  match the packaged bytes (§9).
- Audit `build.json` must name the record bytes the inspector consumed, so a
  record swapped during the HAP build cannot still be reported as the input (§10).
- Every adapter `compilerLibraries` row must match a runtime artifact in the
  compiler record by relative path and hash, and packaged rows must also match
  the packaged bytes, so one library is linked at all three layers (§11).
- A runtime artifact path must be a canonical relative path, so absolute,
  drive-rooted, drive-relative, UNC and NUL forms are rejected (§11.5).

Earlier revisions in this slice: `5ca4c416594ae6ba346c9fd90869d2063643a32eeca37ffea50b464d6624623c`
(runtime inventory link),
`64fac6588c9ad078ba733f52ac006e70b7875135cad96b12a3bfbccf4c812e6a`
(build metadata binding),
`6db7894f7e820a44456b03ae401e2e9fc268efbedd23f16952b649a369f188c2`
(compiler-provenance gate),
`89c2bba1a4a8399ef005ea7f69fdc144bc49c06a945edb20af7e14bef0014997`
(non-`.so` payload rejection),
`8ff7a5886a82e4e32df2759163a7f5d49782bc30bef8268f90fe23676a78c7f0`
(weak binding and section-index bounds),
`1b907959bec2ff0326c7c1b9e57c909f5839e35e40312412d01ae65bd22de23c`
(protected visibility + split missing/changed wording) and
`14ee30a6c3a38720b2072ec37d25cd23dc0844b5b3b744fcd213a483958bedc2`
(the revision p4 first reviewed with 53 tests green).

Public surface consumed by the repo suite:

```python
RUNTIME_SYMBOLS        # 9  qfli_miri.h ABI-1 run surface
ANALYSIS_SYMBOLS       # 2  qfli_miri.h analysis-only extension
DEBUGGER_SYMBOLS       # 16 qfli_debug.h optional extension
REQUIRED_RUNTIME_SYMBOLS       # 27 = the three tiers (the audit package gate)
ADAPTER_LIBRARY        # "libqfli_miri.so"
PROBE_LIBRARY          # "libqfli_native_probe.so"
PROBE_SYMBOLS          # ("qfli_native_probe",)
APPLICATION_LIBRARIES          # libflutter.so, libapp.so, libqfli_native_probe.so
REQUIRED_APPLICATION_LIBRARIES # libflutter.so, libapp.so
declared_symbols(header_text) -> tuple[str, ...]
read_elf_exports(data, library="<memory>") -> dict[str, ElfExport]
verify_exported_symbols(data, library, required) -> dict
verify_native_inventory(declared, packaged) -> dict
inspect(hap, architecture, root=ROOT) -> dict
```

`ElfExport` carries `binding`, `type`, `visibility`, `section` and `as_dict()`.

## 2. What the inspection now proves that it did not before

Byte identity alone could not gate an audit package: a manifest regenerated from
a stale library still agrees with itself, so a library built before the project
constructor, the analysis extension or the debugger extension could pass.

Added gates, in the order they run inside `inspect()`:

1. **Manifest member presence is distinguished from member corruption.** A
   native library named by the runtime manifest but absent from the archive now
   reports `Missing manifest-covered native library in HAP: <name>`. Only a
   present-but-different member reports
   `Final HAP changed manifest-covered native bytes: <name>`.
2. **Native inventory completeness.** Every `libs/<abi>/*.so` member must be
   either manifest-declared or one of `libflutter.so`, `libapp.so`,
   `libqfli_native_probe.so`. Anything else fails with
   `Unexpected native library in HAP: [...]`. Any other regular file under
   `libs/<abi>/` fails with `Unmanifested native payload in HAP: <name>` (§8.1).
   `libflutter.so` and `libapp.so` remain mandatory
   (`Missing release Flutter/native runtime: [...]`). The probe
   is allow-listed, never required and never removed — it is a release-debug
   helper opened by `lib/ohos_native_probe.dart` only under `kDebugMode`.
3. **Adapter exhaustiveness.** All 27 required symbols must be exported by the
   packaged adapter, else
   `Stale Rust runtime ABI in libqfli_miri.so: missing exported [...]`.
4. **Probe ABI** (`qfli_native_probe`) is verified when the probe is packaged,
   and reported `{"library": ..., "packaged": false}` when it is not.
5. **Report fields** `runtimeAbi`, `probeAbi`, `nativeInventory` make the
   observed surface auditable rather than implicit. Existing keys (`catalog`,
   `catalogAssets`, `runtimeFiles`, `nativeLibraries`, `permissions`, `artifact`,
   `runtimeId`, `manifestSha256`, `bundleName`, `deviceExecuted`, `signed`) and
   the CLI contract are unchanged. The success line additionally prints the
   verified export count.

## 3. ELF reader contract

Pure `struct` parsing, no external tools, ELF64 little-endian only (OHOS
64-bit ABIs `62` x86-64 and `183` AArch64).

- A name counts only when **all** of these hold: `st_shndx != SHN_UNDEF`
  (defined), binding `STB_GLOBAL`, `STB_WEAK` or `STB_GNU_UNIQUE`, visibility
  `STV_DEFAULT` or `STV_PROTECTED`, type `STT_FUNC` or `STT_GNU_IFUNC`.
- A definition whose `st_shndx` is nonreserved (`< SHN_LORESERVE`, i.e. below
  `0xff00`) must index a section that exists in the section table. Otherwise the
  reader raises
  `Malformed ELF dynamic symbol table in <lib>: symbol <name> names section index <n> outside the table`.
  This runs before any binding/visibility filtering, so corruption cannot hide
  behind a local or hidden entry. Reserved values (`SHN_ABS` `0xfff1`,
  `SHN_COMMON` `0xfff2`, `SHN_XINDEX` `0xffff`, `0xff00`-`0xffff` generally) are
  not section indices and are deliberately left alone: rejecting `SHN_ABS` would
  be wrong for loaders, and resolving `SHN_XINDEX` through `SHT_SYMTAB_SHNDX`
  would be full loader emulation, which is out of scope.
- Rejected as not exported: undefined, local, `STV_INTERNAL`, `STV_HIDDEN`,
  `STT_OBJECT`, and any duplicate that is only present under a rejected
  combination (`setdefault` keeps the first accepted definition).
- Malformed input raises `ValueError` (never an uncaught `struct.error`): bad
  magic, non-64-bit, big-endian, truncated header, absent/truncated/oversized
  section table, non-`SHT_STRTAB` section-name table, section escaping the file,
  absent `.dynsym`, unaligned `sh_size`, `sh_link` not a string table, name
  offset past the string table, unterminated name, name longer than 512 bytes,
  non-ASCII name, more than 1,000,000 symbols.
- `SHT_NOBITS` sections are exempt from the file-bounds check because they carry
  no file content.

Deliberate dependency: symbol verification needs section headers. The packaged
adapter keeps them because `ohos/entry/build-profile.json5` excludes
`**/libqfli_miri.so` and `**/librustc_*.so` from `nativeLib.debugSymbol.strip`.
When section headers are absent the result is an explicit
`Malformed ELF section table ... absent, symbols unverifiable`, i.e. a loud
failure, never a silent pass.

## 4. Four decisions raised by p4

1. **`STV_PROTECTED` is exported. Accept it.** The dynamic loader resolves both
   `STV_DEFAULT` and `STV_PROTECTED` by name through `dlsym`, which is exactly
   what Dart's `DynamicLibrary.lookupFunction` uses. Only `STV_INTERNAL` and
   `STV_HIDDEN` are not exported. Rejecting `STV_PROTECTED` would false-reject a
   legitimate runtime and block a real release, so `_STV_LOADER_VISIBLE = (0, 3)`
   now replaces the former `visibility != _STV_DEFAULT` test.
   Consequence: `test_restricted_visibility_is_not_an_export` must assert
   `internal` is rejected and `protected` **is** exported.
2. **Missing vs changed wording is split.** A member absent from the archive is
   now `Missing manifest-covered native library in HAP: <name>`. A member whose
   bytes differ keeps `Final HAP changed manifest-covered native bytes: <name>`.
   Consequence: `test_missing_adapter_member_rejected` must match
   `Missing manifest-covered native library in HAP: libqfli_miri\.so`.

Both edits are confined to the owned script. No signature changed. Against the
p4 suite at `14ee30a6…` the only two failures were precisely those two
assertions (51/53 passed). After that, p4 updated both and added the two final-review
fixtures.

3. **`STB_WEAK` (2) is a loader-visible export. Accept it.** `dlsym` resolves a
   weak definition exactly like a global one, so a weak ABI entry satisfies the
   contract. Accepted bindings are now `STB_GLOBAL` (1), `STB_WEAK` (2) and
   `STB_GNU_UNIQUE` (10). Undefined, local, hidden and internal stay excluded.
   p4's fixture: `test_weak_binding_is_a_loader_visible_export`
   (`st_info = 0x22`, asserts `binding == 2` and the full 27-symbol pass).
4. **A nonreserved `st_shndx` must name a real section.** Previously any nonzero
   index passed, so a symbol claiming section 99 in a 5-section file counted as
   defined. The index is now validated against the section table, and the message
   keeps p4's expected literal substring `section index`. p4's fixture:
   `test_definition_index_outside_the_section_table_rejected` (indices
   `SECTION_COUNT`, `SECTION_COUNT + 4`, `99`). Reserved indices stay accepted by
   design (§3), so no fixture asserts their rejection.

## 5. Real-package evidence (static only)

Read-only application of the final reader to the actual bytes on disk:

| Artifact | sha256 (prefix) | exported `qfli_miri_*` | missing of 27 |
| --- | --- | --- | --- |
| `ohos/entry/libs/arm64-v8a/libqfli_miri.so` | `3499632c08bbb25f` | 10 | 17 |
| `ohos/entry/libs/x86_64/libqfli_miri.so` | `3cfdfc66cceb4a7f` | 10 | 17 |
| HAP `libs/arm64-v8a/libqfli_miri.so` (2026-10-17) | `d409527a6c5bba8c` | 8 | 19 |

Missing everywhere: `qfli_miri_create_with_project` and all 16
`qfli_miri_debug_*` entries. The HAP library additionally lacks
`qfli_miri_create_analysis` and `qfli_miri_analyze`. The probe libraries do
export `qfli_native_probe` with global/default visibility.

Therefore any current audit HAP built from these libraries fails the new gate on
the symbol check, not on a hash check. That is the intended behaviour: the
packaged runtime is stale relative to `native/miri_adapter/qfli_miri.h` and
`native/miri_adapter/qfli_debug.h`.

## 6. Verification performed

- Header drift: `declared_symbols()` over `native/miri_adapter/qfli_miri.h`
  yields 11 prototypes and over `qfli_debug.h` yields 16, matching
  `RUNTIME_SYMBOLS + ANALYSIS_SYMBOLS` and `DEBUGGER_SYMBOLS` exactly.
- Reader. A synthetic ELF64 accepts all 27 required symbols. Hidden, local and
  undefined variants are rejected with the stale-ABI message. Truncated, absent
  section table, empty, bad magic, ELF32 and big-endian inputs are rejected with
  descriptive `ValueError`s.
- Loader facts. A `STB_WEAK` definition is exported with `binding == 2` and the
  full 27-symbol ABI passes. Section indices `0xfff1`/`0xfff2`/`0xffff` are
  accepted without rejection. A nonreserved index past the table raises the
  `section index` error.
- Archive level. A full-surface adapter passes `inspect()` (332-run inventory).
  A run-surface-only adapter whose manifest was regenerated to match is rejected
  with `Stale Rust runtime ABI`. A truncated adapter with a matching manifest is
  rejected with `Malformed ELF ...`. An extra unmanifested library is rejected.
  A missing probe is accepted and reported as not packaged. A missing
  `libflutter.so` is rejected.
- `python -m unittest test_inspect_rust_catalog_hap`: **56 tests, all pass**
  (the two final-review fixtures are green).
- Real bytes re-checked after the change: both
  `ohos/entry/libs/{arm64-v8a,x86_64}/libqfli_miri.so` still export 10 of 27 and
  the probe still exports `qfli_native_probe`, so the new rules did not alter any
  verdict on actual artifacts.
- Hand-built synthetic fixtures in `%TEMP%` are retired and deleted. The repo
  suite (`build_elf`/`patch_header`/`patch_section`/`symbol_index`) is the single
  fixture owner.

## 7. Truthful remaining gates

Not proven, and not claimed by this change:

1. **No audit HAP exists for the current runtime.** No archive anywhere packages
   the current 27-symbol adapter, so the new gate has only ever run against
   synthetic fixtures and the stale 2026-10-17 HAP.
2. **The adapter is still stale on device.** Rebuilding `libqfli_miri.so` for
   `aarch64-unknown-linux-ohos` and `x86_64-unknown-linux-ohos`, repackaging
   `ohos/entry/libs/<abi>` and regenerating `assets/miri/manifest.ohos-*.json`
   remain open native-build work owned elsewhere. Both need their own
   authorization.
3. **No packaged execution.** Zero of the 332 catalog runs and none of the six
   native provider checks have executed on OHOS. Static archive evidence is
   metadata only. `deviceExecuted` stays `false`.
4. **Device path.** No reachable target and no signature binding
   `com.azurekiln.qfli.rust`. Unsigned emulator evidence — with recorded
   emulator identity and installer success — remains the only feasible route.
5. **Adjacent checks still unverified here.** `check_native_packaging.py` still
   audits both ABIs irrespective of `--architecture` and does not perform symbol
   verification. The archive inspector is the only symbol gate. Extending that
   script is outside this slice.

## 8. Final review, 2026-10-26

Independent review of the inspector, followed by one fix that the review found.

- `scripts/inspect_rust_catalog_hap.py` sha256
  `89c2bba1a4a8399ef005ea7f69fdc144bc49c06a945edb20af7e14bef0014997`
  (22032 bytes).
- `scripts/test_inspect_rust_catalog_hap.py` sha256
  `cf245971877ef62657efb41baf3b4921a8111c889bdf8e40e4fd40222cb1e8f9`
  (31135 bytes).
- Inspector module: `python -m unittest test_inspect_rust_catalog_hap` reports
  **59 tests, all pass** (56 before this fix plus three new archive cases).
- Whole Python suite: `python -m unittest discover -s scripts -p test_*.py`
  reports **185 tests, all pass**.
- Malformed ELF bounds: 1736 truncations plus 3472 single-byte mutations (every
  offset set to `0xFF` and to `0x00`) were parsed in memory. Every case raised
  `ValueError` or returned a dict. No `struct.error`, `IndexError` or other
  exception type escaped, so the reader checks each bound before use.
- 27 ABI symbols: `REQUIRED_RUNTIME_SYMBOLS` holds 9 run-surface, 2 analysis and
  16 debugger names. `declared_symbols()` over `qfli_miri.h` and `qfli_debug.h`
  reproduces the same set, so the constants still match the shipped headers.
- Manifest complete inventory: every manifest-declared library must be present
  with matching bytes. Every other packaged native member must be allow-listed.
  `libflutter.so` and `libapp.so` must exist.
- Real artifacts, read-only: `ohos/entry/libs/arm64-v8a/libqfli_miri.so` and
  `ohos/entry/libs/x86_64/libqfli_miri.so` still export 10 of 27 names. Both
  probes export `qfli_native_probe`.

### 8.1 Non-`.so` payload under `libs/<abi>/`

The review found a real bypass. The member loop kept only names ending in `.so`,
so a regular file such as `libs/arm64-v8a/config.bin` entered the archive without
reaching the manifest check, the allow-list or the symbol gate. The promised
complete native inventory therefore did not hold for that directory.

Evidence that the rejection is safe, gathered before the change:

| Source | `libs/` content |
| --- | --- |
| `ohos/entry/libs/arm64-v8a` | six `.so` files only |
| `ohos/entry/libs/x86_64` | five `.so` files only |
| `build/ohos/hap/entry-default-unsigned.hap` | six `.so` members, no directory entry |
| `ohos/entry/build/.../entry-default-unsigned.hap` | same six `.so` members |
| `scripts/package_miri_ohos.ps1` | copies `nativeFiles` (shared objects) into `libs/<abi>` |

Licences and dependency notices are packaged as hash-named `.bin` files under
`assets/miri/`, never under `libs/`, so nothing established is rejected.

Rule now enforced: under `libs/`, every regular file must be exactly
`libs/<selected-abi>/<name>.so`. Any other regular file fails with
`Unmanifested native payload in HAP: <name>; only .so libraries directly under libs/<abi>/ are allowed`.
This covers the selected ABI directory, a foreign ABI directory and `libs/`
itself. Directory entries are skipped because they carry no payload. Replaying
the classification over the member lists of all three real HAPs produced zero
false rejections.

A `.so` outside `libs/<selected-abi>/` is still rejected as
`Wrong native architecture`.

Residual gaps kept open, none of them a pass:

1. Extended section numbering (`shnum` 0 with the real count in section 0) is
   rejected as malformed rather than parsed. Real adapters do not use it, so
   this is a false-negative risk only for exotic input.
2. The inspector proves the 27 names are exported. It cannot prove the ABI
   version function returns 1, because that needs execution.
3. No archive packages the current 27-symbol adapter. The gate has run on
   fixtures and on the stale 2026-10-17 HAP only.

## 9. Compiler provenance gate, 2026-10-26

The second independent review found that every compiler-provenance field was
optional, so a stock compiler, a wrongly patched compiler, a truncated boundary
or a malformed hash all passed. The gate below closes that.

### 9.1 Exact boundary identity

The packaged manifest must carry `compilerBoundary` equal to the reviewed
identity. `verify_compiler_boundary()` requires:

- `kind` equals `COMPILER_BOUNDARY_KIND` from `miri_build_support`.
- `patchSha256` equals `COMPILER_BOUNDARY_PATCH_SHA256`.
- `sourceCommit` equals `RUST_COMMIT`.
- `inputTree` and `patchedTree` carry a 64-hex `sha256` and a positive integer
  `fileCount`.
- `patchedFiles` lists exactly the paths derived from
  `compiler_patch_hunks(compiler_boundary_patch())`, with 64-hex `beforeSha256`
  and `afterSha256`.

A stock compiler fails on `kind`. A differently patched compiler fails on
`patchSha256` or on the patched-file list.

### 9.2 Trusted record bytes

The operator supplies two record files. The inspector never resolves a path
from record JSON and never walks a compiler sysroot. `verify_compiler_provenance()`
runs this chain:

1. Manifest `compilerBuildSha256` equals sha256 of the supplied compiler record
   bytes. Both hashes are also required to be well-formed 64-hex.
2. Manifest `adapterBuildSha256` equals sha256 of the supplied adapter record
   bytes.
3. Compiler record: `schemaVersion` 2, `status` `built`, pinned `rustVersion` and
   `rustCommit`, `nativeHost` equal to the target host, the reviewed boundary,
   and at least one `compilerArtifacts` row whose `root` is `compiler` or
   `runtime`, with a positive `size` and a 64-hex `sha256`.
4. Adapter record: `schemaVersion` 1, pinned revision and host, and
   `adapter.sha256` equal to the sha256 of the packaged `libqfli_miri.so` bytes.
5. `compilerBuild` is the exact identity object `verify_compiler_build` returns,
   so its key set is exactly `path`, `sha256`, `compilerBoundary`. Its `sha256`
   equals the compiler record hash and its boundary equals the reviewed boundary.
6. The adapter record's own `compilerBoundary` equals the reviewed boundary.
7. The runtime inventory is derived from `compilerArtifacts` rows whose `root`
   is `runtime`, keyed by normalized runtime-relative path.
8. Every adapter `compilerLibraries` row must name a path under the recorded
   `runtimeSysroot`, resolve to a runtime-relative path present in that
   inventory, carry the same hash, and have a name equal to the last path
   component.
9. Every recorded `compilerLibraries` entry whose name is packaged must match the
   packaged bytes. The `rustc_driver` and `rustc_codegen` components must each be
   recorded and actually packaged.

Step 7 is the one that survives a regenerated manifest. An attacker who swaps a
packaged compiler library and rewrites the manifest `nativeLibraries` hash still
fails, because the trusted adapter record names the original hash.

### 9.3 CLI contract

```text
python scripts/inspect_rust_catalog_hap.py --hap <file> --architecture <abi> \
  --compiler-record <compiler-build.json> --adapter-record <adapter-build.json> \
  [--metadata <build.json>] --report <json>
```

Both record arguments are `required=True`. The Python API is
`inspect(hap, architecture, root=ROOT, *, compiler_record, adapter_record)`,
where both records are bytes. Missing records fail with
`Compiler and adapter build records are required to establish provenance`.
Provenance runs last so a stale adapter still reports its missing symbols rather
than the record mismatch a regenerated package would also show.

### 9.4 Tests

- Inspector module: `python -m unittest test_inspect_rust_catalog_hap` reports
  **121 tests, all pass**.
- Whole Python suite: `python -m unittest discover -s scripts -p test_*.py`
  reports **247 tests, all pass**.
- `scripts/test_inspect_rust_catalog_hap.py` sha256
  `b0e52f2a8b84c6e413429255bd0f7fe75cb6600ff1772a535347b07a6d020a85`
  (66052 bytes).
- New negative cases cover a missing boundary, a stock compiler boundary, a wrong
  patch hash, a malformed manifest hash, a compiler and adapter record hash
  mismatch, a failed or stock compiler record, a record without artifacts, a
  foreign host, a wrong adapter identity, a foreign compiler link, a broken
  `compilerBuild` shape, a boundary mismatch, a missing recorded runtime library,
  a malformed library hash, a truncated patched-file list, a bad tree count,
  malformed JSON bytes and absent bytes.
- Two corruption cases prove the linkage: a swapped packaged compiler with a
  regenerated manifest hash is rejected, and a recorded compiler library absent
  from the package is rejected.
- Old-style fixtures without provenance stay as negative cases: an archive with
  no records is rejected, and a manifest without the three fields is rejected.

### 9.5 Real manifests are now correctly rejected

Both `assets/miri/manifest.ohos-x64.json` and `manifest.ohos-arm64.json` contain
none of `compilerBoundary`, `compilerBuildSha256` and `adapterBuildSha256`. They
were produced before `package_miri_ohos.ps1` wrote those fields, so
`verify_compiler_boundary` rejects them with
`Compiler boundary is missing from the packaged manifest`. This is the intended
behaviour for a stale package, not a regression. The fields already exist in the
current packaging script at lines 183 to 185, so repackaging plus manifest
regeneration restores them.

### 9.6 Caller closure, resolved by p4

`scripts/build_rust_catalog_audit.ps1` was the only real CLI caller and used to
pass four arguments, so argparse rejected the two required records. p4 owns that
script and closed it. Verified read-only at sha256
`688c97fcda2570943fd1d3bcdfe4b206639514e6d0bf778495f415ed4f6ee053` (114 lines):

- The param block declares `-CompilerRecord` and `-AdapterRecord` as mandatory.
- `Resolve-TrustedRecord` rejects a non-file or empty record and returns an
  absolute path.
- Both records are resolved and hashed before the output directory is created,
  before the build lock and before `ohos` sources are rewritten, so a missing
  record mutates nothing.
- `build.json` gains `compilerRecordSha256` and `adapterRecordSha256`.
- The call at line 90 forwards `--compiler-record $compilerRecordPath` and
  `--adapter-record $adapterRecordPath`.

The forwarded flag names match the live argparse declarations at
`inspect_rust_catalog_hap.py:586` and `:588` exactly, so no rename is pending and
the caller needs no further edit. The two `build.json` record hashes are advisory
for now. The authoritative binding stays manifest to records to packaged bytes,
because `build.json` is itself only bound to the artifact hash.

p4 did not run the script, because that needs a real HAP build. End-to-end
execution of the records therefore remains open and is not claimed here.

### 9.7 Naming divergence for p4

The CLI uses `--compiler-record` and `--adapter-record`. Repo precedent uses
`--compiler-build-info` and `--adapter-build-info` (`miri_build_support.py`
`check-compiler` and `verify-adapter`, and `package_miri_ohos.ps1:69`). The names
were left as landed because p4 has already recorded them. p4 may rename them in
the doc, or ask for a rename, which is a two-line change in `main()`.

### 9.8 Snapshots p4 should discard

Two test snapshots are stale and neither is a defect:

| Snapshot | Report | Current truth |
| --- | --- | --- |
| `cd74281e` | 39 pass, 20 `AttributeError: verify` | helper landed, 89 pass |
| `111312FC` | 63 tests, 1 `NameError: compiler` | same edit window, 89 pass |

Both readings were taken while `runtime_for` and the `verify` helper were being
written. The current test file is `bd3d30d0…` with 89 tests green, and the whole
`scripts` suite is 215 green.

No device, compiler, SDK, HAP build or WSL step was used. Nothing was committed.

## 10. Build metadata binding, 2026-10-26

The caller writes `build.json` from its pre-build inputs, so the two record
hashes it records name the bytes it handed over. Comparing them with the hashes
the inspector actually consumed closes a record swap that happens during the HAP
build, which the packaged manifest alone cannot see: a manifest regenerated from
the swapped record still agrees with itself.

### 10.1 Contract

`verify_build_metadata(metadata, report)` runs when `--metadata` is supplied and
requires, in this order:

1. The metadata is a JSON object.
2. `sha256` equals `report.artifact.sha256`.
3. `bundleName`, `architecture`, `target` and `signed` match the audit identity.
4. `compilerRecordSha256` is a well-formed 64-hex string and equals
   `report.compilerProvenance.compilerBuildSha256`.
5. `adapterRecordSha256` is a well-formed 64-hex string and equals
   `report.compilerProvenance.adapterBuildSha256`.
6. `buildId` is a non-empty string.

Steps 4 and 5 are the new binding. They distinguish three failures that used to
be silent: a missing field, a malformed field, and a field naming different
record bytes than the ones consumed.

### 10.2 Fail-safe direction

p4 confirmed by AST scan that the audit script hashes both records once at start
and never writes a record path, so `build.json` and the inspector normally see
the same bytes. If an external process rewrites a record mid-run, `build.json`
keeps the earlier hash and the inspector sees the later bytes, so the comparison
fails. That is fail-safe, not fail-open. No re-hash after the build was added,
because that would blur which bytes are the declared inputs.

### 10.3 Tests

- Pure helper cases: bound metadata accepted, missing compiler field, missing
  adapter field, malformed compiler field, malformed adapter field (uppercase
  hex), swapped compiler hash, swapped adapter hash, HAP hash mismatch, identity
  mismatch, signed metadata, missing build id, non-object metadata.
- Archive integration: metadata bound to a real inspection report passes, and a
  swapped record hash fails with
  `compilerRecordSha256 differs from the consumed build record`.
- CLI end-to-end through `main()` with real record and metadata files on disk:
  bound metadata returns status 0 with `PASS`, while a metadata naming another
  adapter record returns status 1 with the mismatch error, and a metadata
  missing the compiler hash returns status 1 with
  `Build metadata lacks a well-formed compilerRecordSha256`. The CLI has no
  `--root` flag, so these cases point the fixture root at the suite copy through
  a scoped patch of `inspect`.

No device, compiler, SDK, HAP build or WSL step was used. Nothing was committed.

## 11. Runtime inventory link, 2026-10-26

An independent commit-gate review found a real hole. The adapter record's
`compilerLibraries` was checked only against the packaged bytes, never against
the compiler record that owns those libraries. The positive fixture itself
showed it: the adapter named the driver with hash `777` while the compiler
record's runtime artifact named `666`, and the codegen library was absent from
`compilerArtifacts` entirely. The verifier still passed.

### 11.1 Link now enforced

The runtime inventory is derived from `compilerArtifacts` rows whose `root` is
`runtime`, keyed by normalized runtime-relative path. Each adapter
`compilerLibraries` row must then:

1. Carry a single-component `name` and a well-formed hash.
2. Name a path that normalizes under the record's `runtimeSysroot`.
3. Reduce to a runtime-relative path present in the inventory.
4. Carry exactly the hash that inventory records for that path.
5. Use a `name` equal to the last component of that path.

Conflicts are rejected, not merged: two rows for one name with different
hashes, or two runtime artifacts for one path with different hashes, both fail.
A compiler record with no runtime artifacts, or no `runtimeSysroot`, fails.

A packaged recorded library is therefore linked to all three layers: the
adapter record, the compiler record artifacts, and the packaged bytes.

### 11.2 Path normalization without a filesystem

Producer `compilerLibraries` paths are absolute under `compiler.runtimeSysroot`.
The inspector normalizes both separators, drops empty and `.` components, and
rejects `..`. It then strips the recorded `runtimeSysroot` prefix by string
comparison. No path is resolved, so a record produced on Windows can be checked
against a record produced through WSL without touching either filesystem.

### 11.3 Fixture correction and regressions

The positive fixture is now consistent at every layer: the compiler record
carries runtime artifacts `lib/librustc_driver-fixture.so` and
`lib/librustc_codegen_fixture.so` with hashes `777` and `888`, and the adapter
rows name the same two paths under `/build/runtime` with the same hashes. The
archive fixtures feed the real hashes of their synthetic libraries into both
records, so the suite links actual bytes rather than placeholders.

New regressions:

- Adapter runtime hash conflicts with the compiler artifact.
- Adapter runtime library absent from the compiler artifacts.
- Adapter runtime path outside the runtime sysroot.
- Adapter runtime path containing a parent reference.
- Adapter library name disagreeing with its recorded path.
- Adapter conflicting duplicate library rows.
- Compiler record conflicting duplicate runtime artifacts.
- Compiler record with no runtime artifacts.
- Compiler record with no runtime sysroot.
- Windows and POSIX separator chain links successfully.
- Absolute POSIX paths link to the runtime inventory and to the package.

Replaying the reviewer's original broken fixture now fails with
`Compiler artifacts disagree with the adapter build record on lib/librustc_driver-fixture.so`.

### 11.4 Scope kept

Only the link the review named was added. A packaged native library that no
record declares, such as the system C++ runtime, is still allowed, because the
adapter record only describes libraries the compiler produced. Tightening that
would be a separate contract decision and was not taken here.

### 11.5 Artifact path must be relative

Runtime artifact paths are canonical paths relative to their root, because the
producer writes `path.relative_to(root).as_posix()`. The shared path splitter
dropped empty components, so a rooted path collapsed into a relative one:

| Recorded artifact path | Before | After |
| --- | --- | --- |
| `/lib/x.so` | accepted as `lib/x.so` | rejected, not relative |
| `C:/lib/x.so` | accepted as `C:/lib/x.so` | rejected, not relative |
| `C:lib/x.so` | accepted as `C:lib/x.so` | rejected, not relative |
| `//server/share/lib/x.so` | accepted as `server/share/lib/x.so` | rejected, not relative |
| `lib/\0x.so` | accepted | rejected, contains a NUL byte |
| `lib/x.so` | accepted | accepted |

The first and fourth rows are the dangerous ones, because the collapsed result is
indistinguishable from a genuine relative artifact path.

`_relative_artifact_path()` now rejects a leading separator (which also covers a
UNC share after separator normalization), a drive prefix in either rooted or
drive-relative form, a NUL byte, an empty value, and parent references.

Absolute producer paths are untouched by this rule. `runtimeSysroot` and every
`compilerLibraries` path remain absolute by contract and are handled by the
separate prefix-strip logic in §11.2, so the Windows and POSIX normalization case
still passes.

Regressions added: rooted forms listed above, a NUL byte, an empty path, and a
positive case proving absolute producer paths stay accepted.
