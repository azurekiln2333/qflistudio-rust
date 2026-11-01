# Packaged OHOS runtime readiness — current inventory vs new native interface

Research-only checkpoint for `.trellis/tasks/10-22-offline-ide-completeness`.
Owner: PI researcher slice `packaged-runtime-readiness-pi-current.md`.

## 0. Boundary and non-execution statement

No SDK, WSL, native/cargo/rustc build, HAP build, Dart/Flutter command, device
command or large test was started. No file outside this research document was
written, no shared-core or README file was touched, nothing was committed or
pushed. Every hash, symbol and archive fact below is a read-only static
observation of local bytes; none of it is packaged-device evidence, and none of
it may be reported as a device pass.

Read-only checks actually run (pure Python, no compiler, no SDK, no device):

| Command | Result |
| --- | --- |
| `python scripts/check_native_packaging.py --ohos-assets assets/miri --ohos-libraries ohos/entry/libs` | exit 0. arm64 id `942da7d8…`, 97 files, 3 libs; x64 id `8bb95194…`, 98 files, 3 libs; "packaged-device execution remains a separate gate" |
| `python scripts/generate_rust_native_catalog.py --check` | exit 0. 166 lessons / 166 examples / 166 answers / 23 bundles / 332 runs |
| `python scripts/generate_rust_content.py --check` | exit 0. 166 / 166; runtimes cargo 22, desktop 141, external 1, miri-candidate 2 |

Additional read-only evidence used: raw ELF dynamic-symbol scan, raw byte
string scan of each candidate `libqfli_miri.so`, ZIP member inspection of the
existing HAP artifacts, `git ls-files`/`git check-ignore`, and source/spec reads.
Because the symbol scan is a hand-rolled parser plus decisive byte counts, each
negative result was controlled against a committed string that is known present
(`miri_write_to_stdout`, `session guest memory limit reached`, `CheckAlignment`).

## 1. Current OHOS inventory actually on disk

Working-tree state, all of it untracked/ignored (`git check-ignore` confirms):

- `assets/miri/*` → ignored by `.gitignore:75`
- `ohos/entry/libs/**` → ignored by `.gitignore:67`
- `native/build/**` → ignored by `.gitignore:70`

So the "current OHOS inventory" exists only as this machine's local artifacts;
it cannot be reproduced or verified from git.

### 1.1 Asset manifests and flattened guest data

| File | id / SHA-256 | size | mtime |
| --- | --- | --- | --- |
| `assets/miri/manifest.json` | `942da7d84754906a38ce4806af64080f1624550860dd6b1e422cd6efd8550fa7` | 32294 | 2026-10-23 00:14:41 |
| `assets/miri/manifest.ohos-arm64.json` | same `942da7d8…` (byte-equal to legacy `manifest.json`) | 32294 | 2026-10-23 00:14:41 |
| `assets/miri/manifest.ohos-x64.json` | `8bb951941b7088b5f920ebb4e77305022494c3a801164b75e21ea29085b150c4` | 32629 | 2026-10-23 00:03:10 |
| `assets/miri/manifest.android-arm64.json` | `002f82c0…` (schema 2) | 31902 | — |
| `assets/miri/manifest.android-x64.json` | schema 2 | 31899 | — |

- Both OHOS manifests are schema 1, `rustVersion 1.98.1`,
  `rustCommit 48a229ceaefd4985c50990b14116b6d856af0985`,
  `guestTarget x86_64-unknown-linux-gnu`.
- Guest data: 70 `.bin` files, 127,190,872 bytes; **0 orphan `.bin`** (every
  file on disk is referenced by a manifest).
- arm64 native libraries: `libqfli_miri.so` `3499632c…`,
  `librustc_driver-2224b02d479e9414.so` `acf961fd…`, `libc++_shared.so` `d1a368b5…`.
  No codegen backend is packaged for arm64 (the interpreter path needs none).
- x64 native libraries: `libqfli_miri.so` `3cfdfc66…`,
  `librustc_codegen_cranelift.so` `8dc097c1…`, `librustc_driver-2223f3b215a042ae.so`
  `41de5b50…`. The cranelift bytes are additionally mapped inside the guest
  sysroot at `sysroot/lib/rustlib/x86_64-unknown-linux-ohos/codegen-backends/librustc_codegen_cranelift.so`
  (single match, which `default_backend` in `native/miri_adapter/src/lib.rs:417`
  requires).

### 1.2 OHOS native library directories

| Path | size | SHA-256 | in manifest? |
| --- | --- | --- | --- |
| `ohos/entry/libs/arm64-v8a/libqfli_miri.so` | 16126584 | `3499632c…` | yes |
| `ohos/entry/libs/arm64-v8a/librustc_driver-2224b02d479e9414.so` | 282735328 | `acf961fd…` | yes |
| `ohos/entry/libs/arm64-v8a/libc++_shared.so` | 1262248 | `d1a368b5…` | yes |
| `ohos/entry/libs/arm64-v8a/libqfli_native_probe.so` | 4728000 | `8fd7f099…` | **no — extra** |
| `ohos/entry/libs/arm64-v8a/libapp.so` | 12977072 | `537d84e2…` | **no — Flutter app** |
| `ohos/entry/libs/x86_64/libqfli_miri.so` | 16247760 | `3cfdfc66…` | yes |
| `ohos/entry/libs/x86_64/librustc_codegen_cranelift-1.98.1.so` | 15807056 | `8dc097c1…` | **no — duplicate of next row** |
| `ohos/entry/libs/x86_64/librustc_codegen_cranelift.so` | 15807056 | `8dc097c1…` | yes |
| `ohos/entry/libs/x86_64/librustc_driver-2223f3b215a042ae.so` | 139920288 | `41de5b50…` | yes |
| `ohos/entry/libs/x86_64/libqfli_native_probe.so` | 4609504 | `ee4c2e26…` | **no — extra** |

All the manifest-declared libraries match the current manifests, and both
manifest library sets match the checked-out files, so this specific
`check_native_packaging.py` invocation passes. That is asset consistency, not
runtime proof.

### 1.3 Orphan / contradictory artifacts

`native/build/runtime/ohos-x64/manifest.json` (mtime **2026-09-30 17:05:29**,
32643 bytes) declares `id b8c4f32546e3863ce26d0b649bb91e9f1c6aa49cc449a79454259428b5603c68`
and `libqfli_miri.so eabe127c2e0ce9d554a8f857d0190d57c190f2a8f37bf2873b564b3bfb7bc917`,
plus `librustc_codegen_cranelift-1.98.1.so`. No file on disk has hash `eabe127c`.
This directory contains no libraries at all, only this stale manifest.

- `scripts/check_native_packaging.py` and `scripts/inspect_rust_catalog_hap.py`
  read the `assets/miri` manifests, so this orphan is not currently consumed as
  the OHOS expected inventory.
- It is however a second, contradictory x64 identity naming a different adapter
  hash and a different backend file name. Nothing currently deletes or refreshes
  it, and `scripts/package_miri_runtime.py:402` resolves
  `native/build/runtime` for the non-OHOS packaging path. Treat it as an
  inventory-integrity defect, not as the OHOS truth.

## 2. The only packaged artifacts are the 2026-10-17 HAPs

| File | bytes | bundle | notes |
| --- | --- | --- | --- |
| `ohos/entry/build/default/outputs/default/entry-default-signed.hap` | 468889439 | `com.azurekiln.qfli.rust` | 2026-10-17 17:50 |
| `ohos/entry/build/default/outputs/default/entry-default-unsigned.hap` | 466156516 | `com.azurekiln.qfli.rust` | 2026-10-17 17:50 |
| `build/ohos/hap/entry-default-signed.hap` | 468889439 | (copied) | — |
| `build/ohos/hap/entry-default-unsigned.hap` | 467773128 | `com.azurekiln.qfli.rustcore` | 2026-10-17 16:01, older identity |

Read-only inspection of the signed HAP:

- `resources/rawfile/flutter_assets/assets/miri/manifest.json` → id
  `1e31884bf8e09a4a2c7741b01b973efdaa1b50039577aebb45a9df3dcb3845b8`, arm64 host,
  97 files, nativeLibraries `libqfli_miri.so d409527a…`, `librustc_driver-2224b02d479e9414.so acf961fd…`,
  `libc++_shared.so d1a368b5…`.
- Only `manifest.json`, `manifest.android-arm64.json`, `manifest.android-x64.json`
  are packaged. **No `manifest.ohos-arm64.json` / `manifest.ohos-x64.json`.**
- Native libraries: arm64 only (`libapp.so`, `libc++_shared.so`, `libflutter.so`,
  `libqfli_miri.so d409527a… 16002848 bytes`, `libqfli_native_probe.so`,
  `librustc_driver-2224b02d479e9414.so`). x86_64 is excluded by the current
  `ohos/entry/build-profile.json5` filter.
- `module.json` requests `ohos.permission.INTERNET` **and**
  `ohos.permission.READ_PASTEBOARD`.
- `assets/content_rust/` contains only `examples.json` (424639 bytes) and
  `tutorials.json` (857755 bytes); **no `native_catalog.json`**.

Current source for comparison: `assets/content_rust/examples.json` 424798 bytes,
`tutorials.json` 859446 bytes, plus `native_catalog.json` (582481 bytes).
Current `ohos/entry/src/main/module.json5` (uncommitted edit) no longer requests
INTERNET.

Conclusions that follow directly:

1. **No packaged artifact reflects the current runtime.** The newest HAP
   (2026-10-17) predates the 2026-10-22 adapter rebuild, the 2026-10-23 OHOS
   per-architecture manifests, and the 2026-10-23 content edits.
2. That HAP's adapter is a third identity, `d409527a…` (16002848 bytes), which
   matches neither the current arm64 `3499632c…` nor any other on-disk library.
3. That HAP cannot run the 332-entry audit inventory at all: the audit entry
   requires the packaged `native_catalog.json` and the packaged
   `assets/miri/manifest.<arch>.json`.
4. INTERNET is present in the only signed package; removing it in source is not
   evidence until a HAP is rebuilt and re-inspected.

## 3. New native interface vs every packaged library (per ABI)

Expected surface from source: `qfli_miri.h` declares 10 run/analysis entries
(abi_version, create, create_with_backend, create_with_project, run, cancel,
copy_output, result, destroy, create_analysis, analyze); `qfli_debug.h` declares
16 debug entries (capabilities, create, start, resume, resume_at, pause, cancel,
destroy, wait, status, pause_info, frame_count, frame, locals, copy_output,
copy_output_channel). Total = 26 exported symbols in the current source.

Actual exports (raw ELF dynsym plus decisive byte counts):

| Library | mtime | run core | analysis | project ctor | debug (16) | total qfli exports |
| --- | --- | --- | --- | --- | --- | --- |
| `ohos/entry/libs/arm64-v8a/libqfli_miri.so` `3499632c…` | 2026-10-22 23:57 | yes | yes | **absent** | **absent** | 10 |
| `ohos/entry/libs/x86_64/libqfli_miri.so` `3cfdfc66…` | 2026-10-22 23:52 | yes | yes | **absent** | **absent** | 10 |
| HAP `libqfli_miri.so` `d409527a…` | 2026-10-15 | yes | **absent** | **absent** | **absent** | 8 |
| `native/build/runtime/android-arm64/libqfli_miri.so` | — | yes | **absent** | **absent** | **absent** | 8 |
| `native/build/runtime/android-x64/libqfli_miri.so` | — | yes | **absent** | **absent** | **absent** | 8 |

Guest filesystem capability: the working-tree patch
`native/patches/miri-1.98.1-embedded-session.patch` (mtime 2026-10-23 10:32:24)
adds `src/embedded_fs.rs` (`EmbeddedFileSystem`, session cwd/temp, no-follow
teardown). `git show HEAD:<patch>` contains **zero** `embedded_fs` references.
A byte scan for patch-unique strings (`path is outside the embedded project or
uses a symlink`, `.qfli-miri-tmp-`, `embedded cwd lock poisoned`,
`embedded filesystem requires descriptor-relative host access`) returns **0** in
both current OHOS libraries and in the HAP library. Therefore **no packaged OHOS
adapter contains the guest filesystem capability**.

Why this is exactly the observed state: `native/miri_adapter/src/lib.rs` mtime
2026-10-23 01:54:58 (adds `create_with_project`), `src/debug.rs` and
`qfli_debug.h` mtime 2026-10-23 03:24:59, patch mtime 2026-10-23 10:32:24 — all
after the 2026-10-22 23:52/23:57 library builds that produced the current libs.

ABI compatibility of what remains is intact: the working-tree diff of
`qfli_miri.h` only adds enums, the `QfliAnalysisConfig` and the new prototypes;
`QfliConfig`/`QfliResult` layouts are unchanged, so the current Dart
`_NativeConfig` (`lib/native_miri_runner.dart:340`) still matches the Oct-22
adapter. The only behavioural drift is the newer `destroy` latching rule, absent
from the packaged build.

Dart already treats the gaps honestly instead of faking them:
`_MiriBindings` (`lib/native_miri_runner.dart:405`) binds `create_with_project`
only when `providesSymbol` succeeds; `native_miri_analyzer.dart:349` raises
`RustAnalysisUnavailable` when `create_analysis`/`analyze` are missing;
`rust_debugger.dart:1248` throws
`'当前 Rust 运行库未包含完整的 Miri 离线调试扩展'` when the 16 debug symbols
are incomplete; `rust_native_feature_audit.dart:191` states missing optional
analysis/debug symbols fail the check rather than being skipped. With the current
packaged libraries the OHOS feature audit therefore cannot reach `passed=true`.

## 4. Gap against 166 tutorials / 166 examples / 332 programs

Current authored inventory (generator `--check` passes; source
`topics_001_084.json` `d2fb3650…`, `topics_085_166.json` `08ba5290…`): 166
lessons, 166 examples, 166 answers, 23 Cargo bundles, 332 catalog runs, 23
bundles, runtimes desktop 141 / cargo 22 / external 1 / miri-candidate 2.

| Gap | Detail |
| --- | --- |
| Adapter interface | 2 of 3 optional extensions missing in the packaged libs (project ctor, 16 debug symbols); analysis present but in no shipped HAP. |
| Guest filesystem | Embedded capability absent. `rust-catalog-164-*` and `rust-catalog-165-*` (4 runs) use `std::fs`, `std::env::temp_dir`, `std::process::id`; under Miri isolation with no capability these fail. `rust-catalog-166-*` uses only `process::exit` + an unsafe write. |
| Bundle program root | Without `create_with_project`, the runner falls back to `create`/`create_with_backend` and the guest root is the source parent (`<project>/src`). All 23 bundle runs use `entryFile src/main.rs`; project-root files (`Cargo.toml`, `tests/**`, `crates/**`) are then outside the guest root. Per the existing catalog plan the bundle files are Cargo-only and the device run covers `code` only; that contract must be re-asserted, not assumed. |
| Packaging | The HAP does not contain `native_catalog.json`, so the audit entry cannot enumerate the 332-run inventory from the installed package; the packaged catalogs are also older bytes than source. |
| Offline permission | The packaged HAP requests INTERNET; the source edit removing it is unverified in any archive. |
| Evidence transferability | `host-baseline.json` `status=passed` is 332/332 through the **real rustc** (`rustc --edition=2021`, `mobileExecution: "not_tested"`). The packaged engine instead interprets Miri with an adapter that hardcodes `--edition=2024` and a pinned `x86_64-unknown-linux-gnu` guest. Host pass is not a device prediction, and edition drift is already an identified content issue. |
| Device | No reachable target: `hdc list targets` empty; SQL527 records old `127.0.0.1:5555` absent and `192.168.68.207:46551` TCP Offline. |

So the honest current state of R1 is: **0 of 332 runs have any packaged-OHOS
execution evidence, and the current packaged libraries cannot satisfy the debug
or guest-filesystem requirements.** The 332-count itself matches source; the
`check_native_packaging.py` pass is host/static only.

## 5. Audit build script review — identity restore and offline coverage

Reviewed `scripts/build_rust_catalog_audit.ps1`, `scripts/check_native_packaging.py`,
`scripts/inspect_rust_catalog_hap.py`, `scripts/package_miri_ohos.ps1`,
`scripts/build_miri_adapter.sh`, `scripts/check_miri_ohos.sh`.

What the audit script does correctly today:

- Saves exact original bytes of exactly three mutated files —
  `ohos/AppScope/app.json5`, `ohos/entry/build-profile.json5`,
  `ohos/hvigor/hvigor-config.json5` (lines 11–15) — and restores them in
  `finally` (lines 77–89), preserving a concurrent edit as
  `original-N.backup` and failing loudly.
- Sets the isolated bundle `com.azurekiln.qfli.rust.audit`, excludes the other
  ABI through `nativeLib.filter.excludes`, and disables signing with the typed
  `properties.enableSignTask=false` rather than the non-working
  `-p enableSignTask=false` or `--no-codesign`.
- Keeps production signing material untouched: the script never opens
  `ohos/build-profile.json5` or any `.p12`/`.p7b`/`.cer`, so no signing restore
  is required. That is correct and should stay documented as deliberate.
- Names the artifact by digest, writes `build.json`, and re-inspects the HAP.

Coverage defects (all read-only findings; each is a candidate fix, not a claim):

1. **Stale lock aborts with no recovery.** `$lock = [IO.File]::Open($lockPath,
   [IO.FileMode]::CreateNew, …)` is at line 10, *before* the `try` at line 22. A
   run killed after creating `build/offline-ide-audit/.hap-build-lock` leaves the
   file behind; the next run throws an unhandled `IOException` with no
   diagnostic and no cleanup. Needs stale-lock detection plus explicit
   ownership/age reporting.
2. **Leftover audit identity is unrecoverable.** The Node edit (line 40) throws
   `'Expected the Rust production bundle before isolation'` when
   `AppScope/app.json5` is not exactly `com.azurekiln.qfli.rust`. If a previous
   run is hard-killed between line 43 and the `finally`, every later run fails
   until a human edits the file. The script must self-heal its own audit
   identity (recognize `com.azurekiln.qfli.rust.audit` and restore the recorded
   production value), not merely refuse.
3. **Restore set is narrower than the mutation surface.** Only the three files
   are restored. The audit build also rewrites
   `ohos/entry/src/main/resources/rawfile/flutter_assets/**`,
   `ohos/entry/src/main/resources/rawfile/buildinfo.json5` (not verified either
   way), and `ohos/entry/libs/**`, and it consumes the uncommitted
   `ohos/entry/src/main/module.json5`. These are ignored build outputs, but the
   resulting on-disk state is an audit-flavored package, and nothing records
   that. The script should either restore/record them or state explicitly that
   they are disposable.
4. **Offline check coverage is narrower than "complete directory".**
   `inspect_rust_catalog_hap.py` asserts `ohos.permission.INTERNET` is absent and
   the bundle name is the audit one, but it does not reject other network or
   network-capable permissions, does not require every native member to be
   manifest-declared, and does not verify the adapter's ABI surface. Concretely,
   `libqfli_native_probe.so`, `libapp.so`, `libflutter.so` and the duplicate
   `librustc_codegen_cranelift-1.98.1.so` pass the native loop without being
   manifest-covered, and a stale adapter lacking analysis/debug/project symbols
   passes the archive audit silently — the failure only appears later as an
   "unavailable" feature check or a failing case. The unused `libc++_shared.so`
   class of extras is the same shape.
5. **`check_native_packaging.py` audits both ABIs regardless of `$Architecture`.**
   Passing `--ohos-assets assets/miri --ohos-libraries ohos/entry/libs` validates
   the other architecture's manifests and `libs/<abi>` directory too, and never
   binds that inventory to the HAP under test. A stale or wrong other-ABI
   directory therefore still yields a pass next to the artifact being audited.
   The only artifact binding is inside `inspect_rust_catalog_hap.py`.
6. **No adapter-build provenance in the audit.** The audit script never runs
   `check_miri_source.sh` or reapplies
   `native/patches/miri-1.98.1-embedded-session.patch`; it trusts whatever
   `ohos/entry/libs/<abi>` already holds. Since those libraries are ignored and
   were last built before the project-constructor, debug and filesystem changes,
   the audit has no way to detect that the adapter is stale. This is the
   mechanism behind §3.
7. **The OHOS helper build path is not offline.**
   `scripts/check_miri_ohos.sh` downloads `rustup-init` over the network
   (`curl https://static.rust-lang.org/...`). The audit path does not call it, so
   audit offline coverage is unaffected, but the documented OHOS build helper is
   network-dependent and conflicts with the "no online dependency installs"
   constraint. `scripts/build_miri_adapter.sh` itself is offline
   (`--locked --offline`) and requires a preinstalled pinned toolchain.
8. **Signing identity cannot be restored because none matches.** The preserved
   comment in `ohos/build-profile.json5` states the local `.p7b` binds
   `com.azurekiln.qfli.forge`, and
   `.trellis/tasks/10-15-rust-release-readiness/research/platform-builds.md:195`
   records the device install rejection `9568320 / no signature file` with "the
   configured signing store file does not exist" and no profile binding the Rust
   application ID. Nothing in the repo can restore a *matching* signature,
   because no matching signature exists. The audit path correctly stays unsigned;
   physical-device acceptance remains externally blocked, and unsigned
   emulator evidence — which also needs a reachable emulator — must be labelled
   unsigned.

## 6. Necessary fixes, with source locations

Ordered; each requires its own explicit authorization window. No step below was
performed here.

1. **Rebuild the adapter for both OHOS ABIs from the current source and patch.**
   Sources: `native/miri_adapter/src/lib.rs`, `native/miri_adapter/src/debug.rs`,
   `native/miri_adapter/qfli_miri.h`, `native/miri_adapter/qfli_debug.h`,
   `native/patches/miri-1.98.1-embedded-session.patch`; builder
   `scripts/build_miri_adapter.sh <pinned-miri-source> <toolchain> <target>` with
   `QFLI_OHOS_SDK`/`QFLI_OHOS_CLANG`. Required outcome: the fresh
   `libqfli_miri.so` exports all 26 symbols and contains the embedded filesystem
   strings, for `aarch64-unknown-linux-ohos` and `x86_64-unknown-linux-ohos`.
2. **Repackage and regenerate the OHOS inventory.** `scripts/package_miri_ohos.ps1`
   for `-Architecture arm64` and `x64` must refresh `ohos/entry/libs/<abi>/**`,
   `assets/miri/manifest.ohos-<arch>.json` and the legacy
   `assets/miri/manifest.json` (arm64 only). It must also remove now-unlisted
   files it previously copied, so `librustc_codegen_cranelift-1.98.1.so` and the
   `libqfli_native_probe.so` extras cannot linger unmanifested.
3. **Add static ABI-surface and completeness verification.**
   `scripts/check_native_packaging.py` should require, per OHOS library:
   `create`, `create_with_backend`, `create_with_project`, `create_analysis`,
   `analyze`, the run core, and the full debug set; and should reject any
   `libs/<abi>/*.so` that is not manifest-declared (excluding only the Flutter
   engine/app members it explicitly allows). Extend
   `scripts/inspect_rust_catalog_hap.py` to require `native_catalog.json` and the
   per-architecture manifest for the target ABI, and to fail on unmanifested
   native members.
4. **Rebuild the content and audit packages after the content freeze.**
   The HAP must package `assets/content_rust/examples.json`,
   `tutorials.json` and `native_catalog.json` at the current hashes; the audit
   entry then owns the 332-run inventory.
5. **Verify the offline permission in a built archive.** `ohos.permission.INTERNET`
   must be absent from `module.json` inside the rebuilt production and audit
   HAPs (`ohos/entry/src/main/module.json5` already omits it).
6. **Harden `scripts/build_rust_catalog_audit.ps1`.** Stale-lock recovery and
   audit-identity self-heal (items 1–2 in §5), plus an explicit, recorded
   decision on the ignored `flutter_assets`/`libs` mutation surface (item 3).
7. **Delete or refresh the orphan `native/build/runtime/ohos-x64/manifest.json`**
   under its owning slice so one contradictory x64 identity stops competing with
   the authoritative `assets/miri/manifest.ohos-x64.json`.
8. **Device acceptance last.** Either obtain signature material binding
   `com.azurekiln.qfli.rust`, or install the unsigned audit HAP on an emulator
   with recorded emulator identity and installer success, then execute the full
   332-run inventory plus the six native feature checks. Absent a reachable
   target, this gate stays open and must not be represented as passed.

## 7. Verification performed vs not run

Performed (read-only): the three checks in §0; ELF dynamic-symbol extraction for
five libraries; raw byte string scans for 11 needles across four OHOS/HAP
libraries with committed-string controls; ZIP enumeration and member hashing of
two HAP archives; manifest JSON parsing and cross-hash comparison; `.bin` orphan
set computation; `git ls-files` / `git check-ignore`; source, header, patch and
script reads.

Not run, and not claimed: any native/cargo/rustc build; any HAP build; any Dart
or Flutter command; `check_native_packaging.py --toolchain/--ndk`; `debug_abi_test.c`,
`analysis_abi_test.c`, `fs_abi_test.c`; `verify_rust_native_catalog_host.py`;
any device install or execution; any commit or push.

## 8. Open risks

- The authoritative OHOS inventory is untracked local state; a clean checkout
  cannot reproduce the manifests or libraries that `check_native_packaging.py`
  just approved.
- `native/build/runtime/android-*/libqfli_miri.so` predate `create_with_backend`
  in the same way; the Android runtime path is outside this Rust-OHOS slice but
  shares the stale-adapter pattern.
- `scripts/check_miri_ohos.sh`'s network download is a build-path offline
  violation distinct from the product-offline guarantee; it should be replaced
  with a preinstalled pinned toolchain requirement like
  `build_miri_adapter.sh`.
- Emulator/device availability and any unsigned-install acceptance remain
  unresolved (SQL527); no Rust device mutation window is owned by this slice.