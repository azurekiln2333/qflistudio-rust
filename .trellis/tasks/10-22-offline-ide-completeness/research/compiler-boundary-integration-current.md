# Compiler boundary integration: shared read-only loader

Date: 2026-10-24 (second revision). Source-only work. No compiler build, no
adapter build, no cargo/rustc invocation, no SDK, WSL, native, device or process
execution was started. Nothing here establishes that the boundary compiles or
confines anything. It records the implemented source, the inspection evidence
behind it, and the exact contracts that are still unresolved.

Owned by this assignment and changed:

- `native/miri_adapter/src/compiler_boundary.rs` (new)
- `native/miri_adapter/src/lib.rs` (callback structs, `config`, session outcomes)
- `native/miri_adapter/src/debug.rs` (callback struct, `config`, worker outcome)
- this report

Not touched: the pinned compiler patch, build and packaging scripts, the Miri
patch, shared core, sibling products, README, Dart. The working tree keeps every
existing edit.

## Compiler patch this code requires

`native/patches/rustc-1.98.1-embedded-compiler-boundary.patch`: 9083 bytes,
SHA-256 `7236eff645ddf45eb87e78865a7d805a3443234e23c0855bee7956882c9989ee`,
eight files. The frozen bytes are committed at `aa8594a`
(`build: bind native adapters to patched compiler provenance`) and match the
working tree exactly.

The only change since the 9085-byte revision `0972522b…e402` is provenance
hygiene: the trailing blank context line was dropped from the final hunk, whose
header went from `@@ -988,7 +999,7 @@` to `@@ -988,6 +999,6 @@`. No applied
source line changed, so the loader and patch behaviour in this note are
unchanged. The eight temporary pinned files passed `git apply --check` and
`git apply`, and the originals remain untouched.

| File | Change |
| --- | --- |
| `rustc_session/src/options.rs` | adds `embedded_boundary: bool [TRACKED]` |
| `rustc_session/src/config.rs` | both `Options` literals set `embedded_boundary: false` |
| `rustc_builtin_macros/src/env.rs` | `lookup_env` stops at `logical_env` when the flag is set |
| `rustc_interface/src/interface.rs` | `early_fatal` when the flag is set and `file_loader` is `None` |
| `rustc_span/src/source_map.rs` | new `read_binary_for_diagnostic` |
| `rustc_parse/src/lib.rs` | diagnostic retry reads through that method |
| `rustc_metadata/src/creader.rs` | refuses a proc-macro crate root after `get_root`, before `dlsym` |
| `rustc_metadata/src/locator.rs` | refuses `CrateFlavor::SDylib` before that interface runs a separate compiler |

Ordering in `register_crate` was verified against the untouched pinned source
(`rustc_metadata/src/creader.rs`): `get_root` at 608 is a lazy metadata decode,
the refusal sits directly after it, `resolve_crate_deps` is at 631 and
`host_dylib::dlsym_proc_macros` at 653. `get_root`
(`rustc_metadata/src/rmeta/decoder.rs:735`) decodes a `LazyValue<CrateRoot>` from
the metadata buffer: no `dlopen`, no `dlsym`, no user code. The refusal therefore
lands after metadata decode and before the only host-code path in that function,
which is why no `after_expansion` proc-macro scan is used or needed.

The `locator.rs` hunk adds an `embedded_boundary` field to `CrateLocator`, passes
it into `get_metadata_section` as a new seventh parameter, and returns
`MetadataError::LoadFailure` for `CrateFlavor::SDylib`. Two other call sites pass
`false`. Verified by text that exactly three call sites exist
(`locator.rs:608`, `:963`, `:991`) and that `CrateFlavor` derives `PartialEq`
(line 551 already compares it with `==`) and has an `SDylib` variant (line 287).

## What `compiler_boundary.rs` implements

One `CompilerBoundary` per session, installed from `Callbacks::config`. The
constructor always returns an `Arc<Self>`. A root that cannot be pinned is
recorded as a failure instead of yielding "no boundary". `install` then, in this
order:

1. stops the session when any failure is already recorded (a root could not be
   opened, or the source path had no parent). 
2. stops the session when the host cannot provide descriptor-relative traversal. 
3. stops the session when `unstable_opts.remap_cwd_prefix` is set, because
   `file_path_mapping()` resolves it against the host process cwd. 
4. stops the session when `opts.externs` is non-empty. 
5. otherwise sets `opts.embedded_boundary = true` and installs the loader.

Every refusal path also calls `ensure_refusal`, which sets the flag and installs
the loader before raising. That makes the stop double-sided: the patched
`interface.rs` refuses a session with the flag set and no loader, so even a
caller that swallowed the fatal error could not start an unrestricted session.

"Stop" means `rustc_span::fatal_error::FatalError.raise()`, which the adapter
already catches with `rustc_driver::catch_fatal_errors` in all three entry
points. There is no path where a boundary problem leaves the session running
against `RealFileLoader`.

### Read roots

Exactly two, both absolute and canonical:

- the project root — the explicit project directory for a run session, otherwise
  the entry source's parent. The mirror directory's parent for analysis. 
- the trusted packaged sysroot.

Each root is opened once with `O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC` and held as
a descriptor, so a later rename of the root path cannot redirect a read. A path
outside both roots is denied. `locate` normalizes lexically: `..` that would
leave the root is rejected. `canonicalize` is deliberately not used for the
guest-supplied path, because it follows the very symlink the traversal must
reject.

### Traversal: genuine `openat`

The earlier `/proc/self/fd/<fd>` re-derivation is gone. Each component is opened
with `openat(2)` on the parent descriptor, declared as its own FFI symbol:

```rust
unsafe extern "C" {
    fn openat(directory: c_int, path: *const c_char, flags: c_int, ...) -> c_int;
}
```

`mode` is variadic and never supplied, because `O_CREAT` and `O_TMPFILE` are
never set. Each component name is checked to be non-empty, to contain no `/`
separator, and to contain no NUL before it reaches the kernel.

Policy per component:

- intermediate component: `O_DIRECTORY | O_NOFOLLOW`. A non-directory fails with
  `ENOTDIR`, a symlink fails with `ELOOP`. The opened descriptor is then
  `fstat`-checked to be a directory.
- final component: `O_NOFOLLOW | O_NONBLOCK`. A symlink fails with `ELOOP`. A
  FIFO opens without blocking, and the descriptor is then refused because it is
  not a regular file. Size is checked against `MAX_FILE_BYTES` before reading.

All classification happens on the opened descriptor. No host path is re-derived
after the root is pinned.

### Flag constants: verified per architecture

`std` exposes `custom_flags` but not the values, and this crate depends only on
`miri`, so the `libc` crate is unavailable. The values are therefore declared
locally, and they are **not** the same across architectures.

The primary evidence is the userspace header set shipped with the pinned local
OpenHarmony SDK. Each architecture has its own `bits/fcntl.h`, reached from
`fcntl.h` through a single `#include <bits/fcntl.h>` at line 22 of
`<sysroot>/usr/include/fcntl.h` (4897 bytes, SHA-256
`ea90e0d85136139de418021cba80f51195bee20bbbf899811af35a36d5947c5d`), so the
per-architecture file is what a compile actually uses.

Base path: `D:/ProgramFiles/Huawei/OpenHarmony/Sdk/23/native/sysroot/usr/include`

| Header | Size | SHA-256 | `O_DIRECTORY` | `O_NOFOLLOW` |
| --- | --- | --- | --- | --- |
| `aarch64-linux-ohos/bits/fcntl.h` | 839 | `66c37030b995805fb951315d3b0935d5fb6d0c3e1ddcf651ddf42c6e418b61b7` | `040000` (line 10) | `0100000` (line 11) |
| `arm-linux-ohos/bits/fcntl.h` | 842 | `61ef448ccdc6b93b0f95530fe2d11406e3b7982afc2a570bdb94e674165a9829` | `040000` (line 10) | `0100000` (line 11) |
| `x86_64-linux-ohos/bits/fcntl.h` | 940 | `3526dbb894665ab3b155a60d730c8527edce4fa597b3d5e51364a345d0cbdaeb` | `0200000` (line 10) | `0400000` (line 11) |

`O_NONBLOCK 04000` (line 6) and `O_CLOEXEC 02000000` (line 12) are identical in
all three files. For reference, `asm-generic/fcntl.h` in the same sysroot defines
`O_DIRECTORY 00200000` (line 58) and `O_NOFOLLOW 00400000` (line 61): the
x86_64 header agrees with it, while the ARM-family headers deliberately override
it with the ARM layout.

Encoded values:

| Architecture | `O_DIRECTORY` | `O_NOFOLLOW` |
| --- | --- | --- |
| `aarch64`, `arm` | `0o40000` | `0o100000` |
| `x86_64` | `0o200000` | `0o400000` |

`O_NONBLOCK` is `0o4000` and `O_CLOEXEC` is `0o2000000` for every architecture
above.

### Which hosts are accepted

`host_supported()` accepts only `target_os = "linux"` with
`target_env = "ohos"` on `aarch64`, `arm` or `x86_64`, which is exactly the set
whose userspace header was read. The adapter builds for
`aarch64-unknown-linux-ohos` and `x86_64-unknown-linux-ohos`, so both shipped
hosts are covered. `armv7-unknown-linux-ohos` is accepted too, because it shares
the verified ARM-family header, and `loongarch64-unknown-linux-ohos` is refused.

OpenHarmony is identified by `target_env`, not by `target_os`. Verified in the
pinned compiler source: `rustc_target/src/spec/base/linux_ohos.rs:5` sets
`env: Env::Ohos`, and `linux_ohos::opts()` takes `os` from
`base::linux::opts()`, which sets `os: Os::Linux` (`base/linux.rs:7`).
`Env::Ohos` is `"ohos"` (`rustc_target/src/spec/mod.rs`). So every
`*-unknown-linux-ohos` target reports `target_os = "linux"` and
`target_env = "ohos"`. A `target_os = "ohos"` check would match nothing and
the boundary would refuse every real OpenHarmony build. An earlier revision of
this module made exactly that mistake and was caught by this source inspection,
not by a build.

Everything else is refused, in two places so neither can silently win:

- at compile time, `compile_error!` fires for any OpenHarmony architecture
  without a verified header, so a missing constant can never be guessed. 
- at run time, `host_supported() == false` makes `install` record
  "compiler boundary unsupported on this host" and stop the session.

`i686-linux-ohos` is refused even though the SDK ships an `i686-linux-ohos/`
directory: it contains only kernel UAPI headers, whose `asm/fcntl.h` is a
bionic-generated shim that just includes `asm-generic/fcntl.h` (1006 bytes,
SHA-256 `d7939eed8a447e1759d81f57d7dd93332502fe4f38fbfb20156c058a37692cd5`). It
has no userspace `bits/fcntl.h`, and the adapter does not build for it.

Every non-OpenHarmony target is unverified and refused at run time, including the
Windows desktop build. That build therefore cannot run a session at all. See the
behaviour-change section.

The `fstat` re-check after each open makes a wrong `O_DIRECTORY` value visible
rather than silent. A wrong `O_NOFOLLOW` value is not runtime-detectable by this
code, which is why the table above is the gate rather than a comment.

### Budgets

Per file 8 MiB, per session 64 MiB across all reads. Reads take at most
`remaining + 1` bytes, so growth is proven rather than trusted from the earlier
metadata length. Exceeding either bound records a boundary failure.

A file whose text decode fails is charged twice: once for the `read_file` attempt
that produced the `InvalidData` error, and once for the diagnostic retry through
`read_binary_file`. Both charges are bounded by the same per-file and per-session
limits, so the worst case is a project of invalid-UTF-8 sources exhausting 64 MiB
at half the file count. This is the double-charge p3 listed as a low-risk
observation. It is not fixed here, because avoiding it needs either a cached
read or a non-charging probe path, and both change loader behaviour beyond this
defect.

### Working directory

`FileLoader::current_directory` returns the canonical project root. Nothing reads
`std::env::current_dir()` and nothing calls `set_current_dir`.

`Options::working_dir` is deliberately **not** set, for two verified reasons:

1. the field carries `#[rustc_lint_opt_deny_field_access]`
   (`rustc_session/src/options.rs:407`), enforced by the Deny-level
   `rustc::BAD_OPT_ACCESS` lint (`rustc_lint/src/internal.rs:497-522`), which
   reads the field attribute from metadata and therefore fires in a downstream
   crate. Assigning it from the adapter fails the adapter build. 
2. the field has **no readers**. A repository-wide search finds only its
   declaration and `SourceMap::working_dir`'s own field. `rustc_interface`
   builds the source map from `SourceMapInputs { file_loader, .. }`
   (`interface.rs:414`), and `SourceMap::with_inputs`
   (`rustc_span/src/source_map.rs:217-222`) takes the working directory from
   `file_loader.current_directory()`. Every consumer
   (`metadata.rs:910`, `session.rs:226`, `config.rs:1043`, `write.rs:237`)
   reads `source_map().working_dir()`.

So the effective working directory is already the session root, through the
loader, which is the only mechanism that reaches `SourceMap::working_dir`. The
one remaining host-cwd reader is `file_path_mapping()` resolving
`-Zremap-cwd-prefix`, and `install` now refuses that option.

### Failure record

`BoundaryFailure { reason, path, detail }` keeps a stable static label, the
offending path and the underlying OS error text. `CompilerBoundary::failure()`
returns the first one. `consumed_bytes()` is implemented but still unused.

## Callback wiring

### `lib.rs`

| Location | Change |
| --- | --- |
| 14 / 26 | `mod compiler_boundary;`, `use compiler_boundary::CompilerBoundary;` |
| 267-274 | `CompilerCallbacks.boundary: Arc<CompilerBoundary>` (not optional) |
| 322 | `CompilerCallbacks::config` calls `install` unconditionally |
| 561-565 | `run_session` builds the boundary before `catch_unwind` |
| 582 | `CompilerCallbacks` receives `Arc::clone(&boundary)` |
| 597-605 | run outcome: a recorded failure becomes `INTERNAL_ERROR` |
| 751-758 | `AnalysisCallbacks.boundary: Arc<CompilerBoundary>` |
| 771 | `AnalysisCallbacks::config` calls `install` unconditionally |
| 884 | `analyze_session` builds the boundary |
| 899 | `AnalysisCallbacks` receives `Arc::clone(&boundary)` |
| 916-924 | analysis outcome: a recorded failure becomes `INTERNAL_ERROR` |

### `debug.rs`

| Location | Change |
| --- | --- |
| 44 | `use crate::compiler_boundary::CompilerBoundary;` |
| 657-662 | `DebugCallbacks.boundary: Arc<CompilerBoundary>` |
| 682 | `DebugCallbacks::config` calls `install` unconditionally |
| 816-820 | `spawn_worker` builds the boundary before `catch_unwind` |
| 840 | `DebugCallbacks` receives `Arc::clone(&boundary)` |
| 862-868 | worker outcome: a recorded failure becomes `FAILED` + `PAUSE_ERROR` |

`debug.rs` reaches `shared.io.filesystem` directly: `SessionIo` lives in the
crate root and `debug` is a descendant module, so the private field is visible,
exactly as `shared.io.cancelled` already is.

## What "surfacing the failure" means now

All three entry points read `boundary.failure()` after the compiler unwinds and
before publishing an outcome:

- run: `INTERNAL_ERROR`, exit code 1, and
  `qfli: compiler boundary: <reason>` on stderr.
- analysis: `INTERNAL_ERROR`, exit code 1, same stderr line. This branch is
  placed before `Ok(true)` on purpose: a denial that happened to emit a
  diagnostic must not be reported as a completed, "checked clean" analysis.
- debug: `FAILED` with reason `PAUSE_ERROR`, exit code 1, same stderr line,
  evaluated before the generic "compiler errored" branch.

Cancellation and resource limits still take precedence, because those arms come
first and must not be relabelled as boundary failures.

Classification detail: a `NotFound` from `openat` is never recorded. It stays an
ordinary OS error so rustc emits its normal "file not found" diagnostic for a
user's missing `include_str!` target, instead of turning a user mistake into an
environment failure. Symlinks (`ELOOP`), wrong entry types, denied paths, root
failures, the read budgets and the argument-surface refusals are recorded.

A source file that is not valid UTF-8 is also never recorded. `Loader::read_file`
returns `io::ErrorKind::InvalidData` and leaves the sticky failure untouched,
because the pinned compiler turns that error into a real diagnostic rather than
an environment failure:

- `rustc_span/src/source_map.rs:247` propagates the loader error out of
  `load_file`. 
- `rustc_parse/src/lib.rs:114-124` catches it, opens
  `struct_fatal("couldn't read `<path>`: <error>")`, retries the same bytes
  through `read_binary_for_diagnostic`, and calls `utf8_error`, which emits
  "invalid utf-8 at byte N" and names the offending byte or byte run. 
- the frozen patch is what makes that retry go through the loader instead of
  `std::fs::read`, so a denied path still cannot be read twice.

`read_binary_file` never decodes, so the retry succeeds on the same authorized
bytes and the precise diagnostic survives. Recording a policy failure on the
decode branch would have forced those bytes to `INTERNAL_ERROR` and discarded the
diagnostic the module's own comment promised to keep. p3 raised exactly that as
defect 1 in `research/compiler-loader-review-current.md`.

## Behaviour change to review

`install` now stops the session on any host outside the supported set. The only
accepted hosts are the OpenHarmony targets `aarch64-unknown-linux-ohos`,
`x86_64-unknown-linux-ohos` and `arm-linux-ohos`, which are exactly the ones
with a verified userspace header. The Windows desktop build therefore cannot
run, analyse or debug a session at all: it fails closed with "compiler boundary
unsupported on this host" instead of running unconfined. That is the requested
behaviour, and it must be reflected wherever a desktop build is described. The
previous revision silently ran such sessions unconfined, which is exactly the
fail-open this revision removes.

This also corrects a wrong earlier decision. An earlier revision used the
OpenHarmony ARM-family directory and no-follow values on every host, and a later
revision replaced them with the generic `asm-generic` values everywhere. Both
were wrong for at least one shipped architecture. The ARM and x86_64 values now
come from their own verified headers.

## Exact unresolved contracts and gates

1. **Rebuild required.** The adapter does not compile without the patched
   `Options::embedded_boundary`. Patching Miri alone and linking an official
   driver cannot satisfy this. The driver, `rustc-dev`, the codegen backend and
   the guest libraries must all come from the single patched tree.
2. **Flag constants are verified, but only for three architectures.** The
   values come from the pinned local SDK headers recorded above, each with size
   and SHA-256. A host or architecture with no such header is refused at compile
   time and at run time. Gate: if a fourth OpenHarmony architecture is ever
   built, read its `bits/fcntl.h`, record its digest, and extend both the
   constant table and `host_supported` before it can run.
3. **`openat` export is proven statically, not at packaged runtime.** The symbol
   is used through a locally declared FFI binding. p3 verified, in
   `research/compiler-loader-review-current.md` under `架构常量独立检查`, that
   `openat` is exported by the SDK `libc.so` for both aarch64 and x86_64, and that
   the coded flag values match the SDK headers byte-for-byte.

   That evidence is *static*. An exported dynamic symbol in the sysroot
   `libc.so` shows the link-time name exists for the two shipped architectures. It
   does not show that the `libc.so` actually loaded inside the packaged HAP
   exports it at that application's API level, and it does not show the device
   runtime is the same libc build as the SDK sysroot. Static export is therefore
   satisfied. Packaged runtime availability stays unproven.
4. **`Options::working_dir` cannot be set** from the adapter (Deny-level
   `rustc::BAD_OPT_ACCESS`) and would be dead work if it could be: it has no
   readers. The session root reaches `SourceMap::working_dir` through
   `FileLoader::current_directory`, which this module returns. If a future
   compiler release starts reading the option, a compiler patch extension is
   required, not an adapter change.
5. **`FileLoader` covers source only.** Compiler metadata and `--extern`
   libraries, `SDylib` interfaces, the codegen backend and generated output
   files are separate host I/O paths. Mitigations are the empty `--extern`
   surface, the refused `remap_cwd_prefix`, the trusted sysroot root and the two
   patch refusals. The loader does not cover them.
6. **Analysis has no explicit project root in ABI 1.** The mirror's entry-source
   parent is used. A broader root needs an ABI field.
7. **The `-L` surface is not inspected.** The adapter never passes `-L`. A
   proc-macro crate root reached by any route is refused by the patched
   `register_crate` before `dlsym`, and an SDylib interface is refused by the
   patched locator.
8. **`consumed_bytes()` is unused.** It exists for reporting but no call site
   consumes it yet.
9. **The frontend contract is unverified.** `INTERNAL_ERROR` and `FAILED` must be
   presented as "not evaluated", never as a language verdict or a clean analysis.
   The Dart side was not inspected in this assignment.

## Evidence actually collected

- Patch identity and both new hunks read from the patch file: 9083 bytes, SHA-256
  `7236eff6…89ee`, eight files. Final hunk header `@@ -988,6 +999,6 @@`.
- `creader.rs` ordering: `get_root` 608, refusal inserted after it,
  `resolve_crate_deps` 631, `dlsym_proc_macros` 653.
- `rmeta/decoder.rs:735`: `get_root` is a lazy metadata decode.
- `locator.rs`: `CrateFlavor` at 274 with `SDylib` at 287 and `==` comparison at
  551. Exactly three `get_metadata_section` call sites at 608, 963, 991.
- `rustc_lint/src/internal.rs:497-522`: `rustc::BAD_OPT_ACCESS` is `Deny` and
  reads `RustcLintOptDenyFieldAccess` from the accessed field.
- `rustc_session/src/options.rs:407`: `working_dir` carries that attribute.
- `rustc_span/src/source_map.rs:217-222`: `SourceMap::with_inputs` derives the
  working directory from `file_loader.current_directory()`.
- Repository-wide search for readers of the option: none.
- `O_DIRECTORY`/`O_NOFOLLOW` sources in-repo: only Miri's own `libc::` uses and
  this module. The values come from the SDK userspace headers, not from a `libc`
  crate source tree, which is not vendored in this repository.
- p3 independently read the same three SDK headers and confirmed the coded values
  byte-for-byte, including the line numbers, and confirmed `openat` is a dynamic
  symbol in the SDK `libc.so` for aarch64 and x86_64. Source:
  `research/compiler-loader-review-current.md`, section
  `架构常量独立检查`.
- `base/linux_ohos.rs:5` sets `env: Env::Ohos`.  `base/linux.rs:7` sets
  `os: Os::Linux`.  `rustc_target/src/spec/mod.rs` maps `Ohos` to `"ohos"`.
- The three OpenHarmony userspace headers read directly from
  `D:/ProgramFiles/Huawei/OpenHarmony/Sdk/23/native/sysroot/usr/include`, with
  sizes and SHA-256 recorded in the flag table above, plus the top-level
  `fcntl.h` include line 22 and the `asm-generic/fcntl.h` values used as a
  cross-check.
- Text-only structural check: bracket balance of `compiler_boundary.rs`,
  `lib.rs` and `debug.rs` (`balanced`), plus grep verification of every wiring
  line listed above and of the single construction site of each callbacks
  struct.

No compiler was run, so none of this is a type check. The specific risks that
only a build can settle are: the FFI declaration of a variadic `openat`, the
`pub(super)` visibility of the flag constants across the `descriptor` module,
`Arc::clone(&boundary)` being borrowed rather than moved inside the
`AssertUnwindSafe` closures, and edition-2024 `unsafe extern "C"` syntax.

## Source snapshot

Frozen adapter module for p3 re-review. Other owned files are listed for context. 
their last recorded review hashes are in
`research/compiler-loader-review-current.md`.

| File | Bytes | SHA-256 |
| --- | --- | --- |
| `native/miri_adapter/src/compiler_boundary.rs` | 28202 | `5ae3c511dd04709faba948d30c6ef504262b1a46d6c3d5f2fc82a77fe1f21a87` |

The only change since p3's reviewed snapshot (`27633` bytes,
`072380da617e4fb523e37eac801faac0a426788412372c0561a74645a779187c`) is defect 1:
the invalid-UTF-8 decode branch now returns `InvalidData` and no longer calls
`deny`/`record`. No other statement, constant, threshold or outcome mapping in
this module changed.

## Required before any confinement claim

1. Apply the boundary patch and rebuild driver, `rustc-dev`, backend and guest
   libraries from that tree. Fix any build error above.
2. Confirm `openat` resolves at packaged runtime on a real device. The static
   side is already verified: p3 found the symbol exported in the aarch64 and
   x86_64 SDK `libc.so`. The packaged side is not.
3. Extend the constant table only by reading a header, never by copying another
   architecture's values.
4. Run the negative fixtures from `research/native-compiler-boundary.md` on a
   packaged OpenHarmony adapter build for `aarch64-unknown-linux-ohos` and for
   `x86_64-unknown-linux-ohos`, with prepared outside sentinels, a symlink, a
   FIFO and a growing file. The two architectures exercise two different flag
   tables, so both must pass.
5. Confirm the Dart side renders `INTERNAL_ERROR`/`FAILED` as "not evaluated".
6. Only then describe any entry point as confined.

## Later source correction

The independent cross-layer reviewer found an Arc receiver type mismatch.
Pi p3 changed `ensure_refusal(&self, ...)` to `ensure_refusal(self: &Arc<Self>, ...)`.
This matches `Arc::clone(self)` and all four callers inside `install`.
Current module: 28213 bytes, SHA-256
`f5ed454e2fe4bf3556cd828d299ccc486c77c51ce1a40d81068eccda9bfbff42`.
The earlier frozen table is retained as historical review input.
Actual compilation remains unrun.

The root independently read the two SDK libc.so ELF dynamic symbol tables.
Both contain a defined GLOBAL FUNC DEFAULT `openat` symbol.
The aarch64 libc.so hash is
`298fb33338d06f07552606ff1ef2adbe42202e4ced3ab9400f26fe90bc38887c`.
The x86_64 libc.so hash is
`7a176e07e120b888ed1547401134e84b385775f9312ae1d40112d8c2f9051a4a`.
This was a pure byte read. No SDK executable ran.
It does not verify the library loaded on a device.
