# Pinned compiler file and environment boundary

Research date: 2026-10-23. This document records source inspection and proposed
implementation choices. It does **not** establish compiler confinement in the
current adapter, a native execution pass, or an OHOS execution pass. Only this
research document was changed for this assignment; adapter, debugger, upstream
patch and sibling product ownership remain with their existing owners.

## Exact inspected compiler

The local executable reports `rustc 1.98.1 (48a229cea 2026-09-01)`, full commit
`48a229ceaefd4985c50990b14116b6d856af0985`, host
`x86_64-pc-windows-gnu`, LLVM `22.1.8`. Source references below are relative to:

`native/build/miri-windows/compiler/lib/rustlib/rustc-src/rust/compiler/`

| Inspected file | SHA-256 of the local file |
| --- | --- |
| `rustc_parse/src/lib.rs` | `ce147228b76250f4cd6d42ccfe3f8a10ebefee1f1949094334d0fca069865fd4` |
| `rustc_builtin_macros/src/env.rs` | `933cd6490e04050079d5381bd3be6b198aa379541ef033ed69197785a1becf5f` |
| `rustc_span/src/source_map.rs` | `3ba2f3090649e9a21666d572beb9860a9c31737e04b787cd4352085d09cfb777` |

These are pinned private-compiler interfaces, not a promise of compatibility
with another Rust revision.

## Configuration entry and covered source reads

`rustc_interface/src/interface.rs:314` exposes `Config`; its relevant fields are:

```rust
pub file_loader: Option<Box<dyn FileLoader + Send + Sync>>,
pub psess_created: Option<Box<dyn FnOnce(&mut ParseSess) + Send>>,
pub track_state: Option<Box<dyn FnOnce(&Session) + Send>>,
pub override_queries: Option<fn(&Session, &mut Providers)>,
```

`rustc_driver_impl/src/lib.rs:119` exposes `Callbacks::config(&mut Config)` before
creating the compiler. The adapter's run, analysis and debug implementations
each have their own `config` callback. All three must call one common boundary
installer so a future fix cannot leave another entry unrestricted. At inspection
time they are in `native/miri_adapter/src/lib.rs` (`CompilerCallbacks` and
`AnalysisCallbacks`) and `native/miri_adapter/src/debug.rs` (`DebugCallbacks`).

`interface.rs:404` takes `config.file_loader`, falling back to unrestricted
`RealFileLoader` only when the field is `None`, then builds the session's
`SourceMapInputs`. The exact public trait at `rustc_span/src/source_map.rs:81` is:

```rust
pub trait FileLoader {
    fn file_exists(&self, path: &Path) -> bool;
    fn read_file(&self, path: &Path) -> io::Result<String>;
    fn read_binary_file(&self, path: &Path) -> io::Result<Arc<[u8]>>;
    fn current_directory(&self) -> io::Result<PathBuf>;
}
```

`SourceMap::with_inputs` calls `current_directory` at line 219 and expects a
successful result. The custom loader should return the prevalidated, canonical,
absolute compilation root selected at session creation. It must not call
`std::env::set_current_dir`, or derive its directory from the guest's later
mutable runtime cwd. For analysis the compilation root is the immutable source
mirror, while diagnostic remapping maps that mirror back to the original files.

| Rust source operation | Actual pinned path |
| --- | --- |
| Root source and parsed files | `SourceMap::load_file`, `source_map.rs:246`, delegates to `FileLoader::read_file` |
| Default `mod foo;` discovery | `rustc_expand/src/module.rs:251`, probes both alternatives through `SourceMap::file_exists` |
| External module including `#[path]` | `module.rs:73`, calls `rustc_parse::new_parser_from_file` |
| `include!` expression/item forms | `rustc_builtin_macros/src/source_util.rs:144` and `:163`, call `new_parser_from_file` |
| `include_str!` / `include_bytes!` | `source_util.rs:218` / `:252`, common helper at `:264` calls `SourceMap::load_binary_file` at `:277` |
| Binary source-map input | `source_map.rs:256`, delegates to `read_binary_file` without BOM removal or text normalization |

## Parser retry bypass and two implementation choices

A loader that merely returns `PermissionDenied` is **insufficient**. The exact
fallback is in `rustc_parse::new_parser_from_file`, `rustc_parse/src/lib.rs:115`:

```rust
let source_file = sm.load_file(path).unwrap_or_else(|e| {
    // Builds the normal couldn't-read diagnostic.
    if let Ok(contents) = std::fs::read(path)
        && let Err(utf8err) = std::str::from_utf8(&contents)
    {
        utf8_error(sm, &path.display().to_string(), sp, &mut err, utf8err, &contents);
    }
    // Emits the fatal diagnostic.
});
```

This directly reads a denied host path. For invalid UTF-8, `utf8_error` at line
131 converts the entire read result with `String::from_utf8_lossy`, inserts it
into `SourceMap`, and attaches a diagnostic span/label. This can expose outside
source snippets as well as violating a no-read boundary. A denied valid UTF-8
file is also read, even when that branch does not print its contents.

There are two concrete ways to close this fallback; neither was implemented or
executed by this research worker:

1. **Public fatal-abort path, without rebuilding rustc.** The loader's
   `read_file` must never return `Err`. On every failure from its bounded guarded
   reader, first store a session-owned boundary-failure record and then call
   `rustc_span::fatal_error::FatalError.raise()`. This includes access denials,
   missing files, invalid UTF-8, size limits and ordinary I/O errors: allowing
   any error to return would reenable rustc's raw-path retry, including races
   after a guarded lookup fails. `rustc_span/src/fatal_error.rs:15` implements
   `raise` with `resume_unwind(FatalErrorMarker)`; `catch_fatal_errors` in that
   module catches the marker. The existing adapter uses
   `rustc_driver::catch_fatal_errors` around run, analysis and debug compilation.
   Keep that catch inside the Rust worker, before returning through the C ABI.
   Do not use a generic panic or allow unwinding through FFI.

   The loader cannot retain a borrowed `DiagCtxtHandle` from `psess_created` in
   a `'static` boxed loader: that handle borrows the parse session. Use a shared
   owned failure record, with the adapter producing a bounded explicit failure
   through the existing channel/result contract. Analysis must become failed or
   unavailable, never checked-clean with zero diagnostics. Run/debug must end
   with a real failure before evaluation. This path intentionally loses rustc's
   ordinary source-read and invalid-UTF-8 diagnostics; verify the replacement
   error, cleanup and subsequent fresh session in the actual adapter. No
   process-global panic hook is required.

2. **Small pinned rustc parser patch.** Replace the direct `std::fs::read(path)`
   in the diagnostic fallback with `sm.load_binary_file(path)` and adapt the
   tuple result, or remove the retry snippet entirely. This ensures a retry is
   subject to the same loader policy and bounds. A denied retry produces only
   the original read failure; an allowed invalid-UTF-8 file can retain its useful
   snippet. This changes the compiler driver, so applying only the existing
   Miri-source patch cannot deliver it. Build the matched compiler/rustc-dev,
   Miri, adapter and backend artifacts through the normal pinned pipeline and
   regenerate/check package hashes.

The first choice is a fail-closed adaptation using the existing pinned public
interfaces, not a verified current guarantee. The second is the cleaner normal
error-path behavior if a compiler rebuild is undertaken for environment
isolation as well.

## Loader permissions and bounded I/O design

The loader needs read-only capabilities for the explicit project/mirror root and
the trusted, fixed packaged sysroot source root. It must choose the authorized
root lexically, walk pinned directory descriptors with no-follow semantics, and
open the final regular file through the same guarded descriptor path. A
`canonicalize`/`starts_with` check followed by an unrestricted path open has a
symlink race and is insufficient. `file_exists` must use the same guarded policy
and return false for an outside, special or forbidden symlink path, without
probing ambient host existence.

The staged runtime `EmbeddedFileSystem` implementation in
`build/offline-ide-audit/fs-patch-source/src/embedded_fs.rs` already walks pinned
descriptors, but `open` and `metadata` are `pub(crate)`. The adapter cannot call
them directly. Its public constructor also creates a guest temporary directory.
Do not instantiate a writable guest capability over the sysroot. Either factor
out a reusable read-only directory capability, or expose narrowly read-only
methods and provide a separate no-write sysroot constructor. The compiler's
immutable cwd and sysroot capability must remain separate from guest chdir and
guest writable-root privileges.

Required reader behavior:

- Reject roots selected from ambient cwd, filesystem root, or arbitrary guest
  input; validate the entry source belongs to the project/mirror root.
- Reject symlinks in parent and final components, including links to an in-root
  target, to match the current runtime policy. Reject special files and open with
  a nonblocking policy before checking metadata so a FIFO cannot hang compilation.
- Enforce explicit per-file and total input-byte limits. Do not trust metadata
  length alone: bound reads with at most `remaining_limit + 1` bytes and reject
  growth beyond the limit. Handle arithmetic overflow before allocating.
- Preserve binary bytes and BOM in `read_binary_file`; decode UTF-8 only for
  `read_file`. Let rustc apply its normal text-source normalization afterward.
- Keep any cache bounded and session-owned; use immutable mirror bytes for
  analysis. Missing source is a failure, never a successful empty virtual file.
- Return the explicit compiler cwd from `current_directory` without host cwd
  mutation. If the platform cannot provide the required guarded operations,
  report that capability unavailable; an unrestricted fallback is not evidence
  of confinement.

This is namespace confinement, with the same hardlink, mount and hostile
external-directory-relocation limits documented in `native-sandbox-fs.md`.
Compiler metadata, native codegen library loading, proc macro loading and output
files are separate host I/O paths. Keep their paths fixed to validated packaged
artifacts or an owned output directory; do not accept arbitrary `--extern`,
library-search paths, Cargo/build.rs or user proc macros as part of analysis.
FileLoader alone is not a general process sandbox.

## Compile-time environment: override is not isolation

`rustc_builtin_macros/src/env.rs:21` implements both `env!` and `option_env!`
through this private helper:

```rust
fn lookup_env(cx: &ExtCtxt<'_>, var: Symbol) -> Result<Symbol, VarError> {
    let var = var.as_str();
    if let Some(value) = cx.sess.opts.logical_env.get(var) {
        return Ok(Symbol::intern(value));
    }
    Ok(Symbol::intern(&std::env::var(var)?))
}
```

The actual file imports `std::env` and calls `env::var`; the fully qualified call
above makes the fallback explicit. `Options.logical_env` is an
`FxIndexMap<String, String>` (`rustc_session/src/options.rs:327`).
`--env-set=NAME=VALUE` populates it via `config.rs:2437`. It can supply a deliberate
session value, but has no absent/deny marker and no no-fallback mode. Providing
only allowed keys does not block unknown host keys. Mapping host keys to empty
strings changes `option_env!` into `Some("")` and cannot cover newly introduced
keys safely.

Both macros call `lookup_env` **before** inserting the value into
`sess.env_depinfo` (`env.rs:55` and `:134`). Therefore `Config.track_state`, clearing
that set, prepopulating it, or inspecting it after expansion cannot prevent the
read. In particular, `compile_error!(env!("QFLI_SANDBOX_HOST_SECRET"))` can expose a
secret while expansion is still running, before `after_expansion` is reached.

There is an `env_var_os` query provider (`rustc_interface/src/passes.rs:485`,
registered at `:897`), but builtin `lookup_env` calls `std::env` directly instead
of that query. Overriding the provider does not isolate these macros.

The inspected public `Config` and `Callbacks` provide no small session-level
environment resolver hook for these builtins:

- `psess_created` receives `&mut ParseSess`, which has source-map/diagnostic
  state but no builtin environment resolver.
- `track_state` tracks already used dependencies, as its own documentation says.
- `register_builtin_macros` is called inside private
  `configure_and_expand` (`passes.rs:134` and `:152`). Registering `env` again is
  not an override mechanism: `rustc_resolve/src/macros.rs:202` reports a compiler
  bug on duplicate builtin registration.
- Replacing the whole `resolver_for_lowering_raw` query would need to reproduce
  private resolver/expansion integration and is not a small supported hook.
- Text/initial-AST filtering is incomplete: local included files, declarative
  macro expansion, reexports and qualified `core::env!`/`std::env!` calls can
  introduce the builtin later.

Do not implement isolation by temporarily clearing, setting or removing the
process environment. The compiler lock does not stop other Flutter/native
threads from reading it, and restoring it later does not make that safe. Do not
change process cwd either.

### Smallest robust environment change

Add an opt-in **session-scoped** no-ambient-environment policy in the pinned
compiler, defaulting off for normal compiler behavior. For example, add a boolean
option that embedding callbacks can set before session creation. Keep deliberate
values in the existing `logical_env` map; change `lookup_env` to return
`Err(VarError::NotPresent)` for a missing key when that policy is enabled, before
calling `env::var`. This gives ordinary Rust semantics: missing `env!` is a
compiler error, and missing `option_env!` is `None`. No host key is enumerated or
mutated. Document the chosen option name and dependency-tracking treatment in
the actual patch; `embedded_env_only` here would be a proposed name, not an
existing field.

Enable the policy from the same shared boundary installer in run, analysis and
debug. Reject user proc macros in these modes: proc macro code executes in the
host and can access its process environment independently of these two builtins.
The `injected_env_var` proc-macro bridge at
`rustc_expand/src/proc_macro_server.rs:474` only reads `logical_env`; it does not
provide a general host-environment sandbox for arbitrary proc macro code.

An isolated compiler helper process with an explicit cleared/allowlisted child
environment is a genuine alternative on platforms supporting that architecture.
It is not the current in-process OHOS adapter and cannot be assumed available.
Until one of these is implemented and exercised, compile-time environment
isolation remains open even if runtime `std::env` isolation passes.

## Meaningful acceptance checks

Run against the actual pinned adapter and later the matching packaged OHOS
engine. Keep separate evidence for native source/API inspection, Linux reference
execution and packaged target execution. Each negative test needs an existing
outside sentinel or host value; an absent file/variable proves nothing.

| Case | Required assertion |
| --- | --- |
| Local root/nested modules, nested `#[path]`, local `include!` | Compile successfully using the exact project or unsaved mirror files |
| Local `include_str!` and non-UTF-8 `include_bytes!` | Exact expected text/bytes, preserving BOM and binary contents |
| Existing `fs_compile_include_escape.rs` | Prepare the named outside sentinel, reject compilation before evaluation; its bytes never appear in output/diagnostics |
| Absolute and parent escapes through each include form and module `#[path]` | Reject; no outside content in any diagnostic channel or dependency record |
| Outside invalid-UTF-8 `include!`/`#[path]` with a distinctive printable secret on the invalid line | No direct parser fallback read and no secret snippet; use syscall tracing/instrumentation on the Linux reference to establish no outside `open`/`read`, since unchanged file bytes alone cannot prove no read |
| Parent/final symlinks to outside and in-root files, including replacement races | Reject consistently without an unrestricted retry; no outside reads |
| Missing/invalid-UTF-8/oversized authorized source with fatal-abort choice | Explicit failure, never empty successful analysis; no parser raw-path retry, safe unwind/cleanup and a fresh subsequent session succeeds |
| FIFO/special files and oversized/growing input | Bounded failure; no blocking FIFO open or unbounded allocation |
| Trusted sysroot snippets plus std-only programs | Normal compilation/diagnostics remain useful; no writable sysroot capability or new sysroot temporary entries |
| Existing `fs_compile_env_escape.rs` with host-only `QFLI_SANDBOX_HOST_SECRET` | `env!` fails; the distinctive host value appears nowhere in stdout/stderr/diagnostics or dependency output |
| `option_env!` for that same host-only key | Evaluates to `None`, including `core::option_env!` and `std::option_env!` paths |
| Env calls generated by nested declarative macros, a local included file, `concat!`, and `compile_error!(env!(...))` | Same isolation; expansion cannot leak the host value before a later callback |
| Deliberately allowed session values, empty values and unknown names | Exact map values; empty allowed values remain `Some("")`; unknown `option_env!` stays `None` and unknown `env!` fails |
| Two live sessions with distinct allowed maps and compilation roots | No cross-session values/cwd; host environment and process cwd unchanged before/after, including cancel/failure paths |
| Run, analysis and debug entry points | All install the same boundary and fail before evaluation on each negative fixture; analysis never reports checked clean on boundary abort |

No native build, C ABI execution, Flutter tooling, device mutation or target
execution was started for this research. Completed checks were pinned compiler
identity output, local-source call-path inspection, source SHA-256 calculation,
and review of the existing capability visibility and negative fixtures.
