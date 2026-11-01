# Pinned rustc compiler boundary patch: source-only preparation

> Superseded. This note describes an intermediate six-file revision of the
> patch (5659 bytes, `13d23e32…fee7`). The frozen patch is the eight-file
> revision (9083 bytes, `7236eff6…89ee`) described in
> `compiler-boundary-integration-current.md` and
> `compiler-build-provenance-current.md`. The facts below are kept unchanged as
> the record of that earlier revision; the applicability check they describe is
> not evidence about the frozen bytes.

Status: source-only work. No compiler build, no `cargo`, no C ABI execution, no
WSL/SDK/device invocation, no Flutter tooling and no target execution was
started for this assignment. The patch below is **not applied** by any current
build script, so the embedded boundary is **not active** in any existing
artifact, and no isolation is claimed. Everything here is source inspection plus
an applicability check of a generated diff.

Deliverables owned by this assignment:

- `native/patches/rustc-1.98.1-embedded-compiler-boundary.patch`
  (5659 bytes, SHA-256 `13d23e32d84073f8274ff60d8a144b490c3a3b5c1e56fc23f46e3ffa3fa837ee`)
- this report

No existing Miri patch, adapter source, build script, packaging script, shared
core file or README was modified.

## Exact inspected compiler

Local toolchain reports `rustc 1.98.1 (48a229cea 2026-09-01)`, commit
`48a229ceaefd4985c50990b14116b6d856af0985`. Source references below are relative
to:

`native/build/miri-windows/compiler/lib/rustlib/rustc-src/rust/compiler/`

| File touched by the patch | SHA-256 of the unpatched pinned file |
| --- | --- |
| `rustc_builtin_macros/src/env.rs` | `933cd6490e04050079d5381bd3be6b198aa379541ef033ed69197785a1becf5f` |
| `rustc_interface/src/interface.rs` | `b384892a54f1246337967696b7cf6d6fc6fa8e2acbb8f8077b195620b60d591c` |
| `rustc_parse/src/lib.rs` | `ce147228b76250f4cd6d42ccfe3f8a10ebefee1f1949094334d0fca069865fd4` |
| `rustc_session/src/config.rs` | `b5b69ed2d317e43324acd27bc836f035dfbb22656a014340c88f97add9417d95` |
| `rustc_session/src/options.rs` | `21177250c4f18c3b6f24ae196c6f1f14f697160a83a34a63a7c2fd50c31ef07d` |
| `rustc_span/src/source_map.rs` | `3ba2f3090649e9a21666d572beb9860a9c31737e04b787cd4352085d09cfb777` |

The `env.rs`, `rustc_parse/src/lib.rs` and `source_map.rs` hashes match the
earlier research in `research/native-compiler-boundary.md`, so this patch targets
the same revision that research inspected. These are compiler-private interfaces
and carry no compatibility promise for another revision.

## What the patch changes

One session-scoped switch, `Options::embedded_boundary`, plus the two code paths
that made the switch unenforceable. Default is `false`; ordinary `rustc` and
`cargo` behaviour is unchanged.

### 1. `rustc_session/src/options.rs` — the switch

Adds to the `top_level_options!` struct, next to `logical_env`:

```rust
embedded_boundary: bool [TRACKED],
```

`[TRACKED]` is deliberate: the value changes what `env!` expands to, so a
boundary-on session must not share a dep-tracking hash with a boundary-off one.

The field is `pub`, so an embedding sets it on `rustc_interface::Config.opts`
inside `Callbacks::config`, before the session exists. It has no command-line
flag and is not reachable from `-Z` or `-C`.

### 2. `rustc_session/src/config.rs` — both `Options` constructors

`Options` is built by two exhaustive literals: `impl Default for Options`
(line ~1467) and `build_session_options` (line ~2824). Both receive
`embedded_boundary: false`, which keeps the default off and keeps the literals
exhaustive. These are the only two `Options` literals in the compiler tree that
name `logical_env`, which is how the set was confirmed.

### 3. `rustc_builtin_macros/src/env.rs` — no ambient fallback

`lookup_env` keeps the existing `logical_env` lookup, then stops instead of
falling back to the process environment:

```rust
if cx.sess.opts.embedded_boundary {
    return Err(VarError::NotPresent);
}
```

Resulting semantics are ordinary Rust semantics, not a special case:

- `env!("NAME")` for a name outside `logical_env` is a normal missing-variable
  compiler error, including the existing Cargo-typo suggestions.
- `option_env!("NAME")` is `None`.
- A value present in `logical_env` still wins, including an empty string, which
  stays `Some("")`.
- `core::env!`, `std::env!` and the `option_env!` variants all reach the same
  builtin, so qualification does not bypass the policy.

`env_depinfo` is still recorded after the lookup with `None` for an absent name,
so dependency tracking keeps its existing meaning.

No host variable is enumerated, read, cleared, set or restored. The process
environment is untouched, which matters because other Flutter and native threads
share this process and a temporary mutation would race with them.

### 4. `rustc_interface/src/interface.rs` — the boundary cannot silently degrade

`run_compiler` used to fall back to `RealFileLoader` whenever
`Config.file_loader` was `None`. With the switch on, that fallback is now a fatal
error:

```rust
if config.opts.embedded_boundary && config.file_loader.is_none() {
    early_dcx.early_fatal(
        "embedded compiler boundary requires an explicit `FileLoader` in `Config`",
    );
}
```

This is what makes the switch a shared boundary rather than a per-entry
convenience: an entry point that sets the flag but forgets the loader fails
before compilation instead of compiling with unrestricted source reads.

### 5. `rustc_span/src/source_map.rs` — a loader-only read for diagnostics

Adds one method, so a diagnostic path can read bytes under the same policy
without registering a `SourceFile`:

```rust
pub fn read_binary_for_diagnostic(&self, path: &Path) -> io::Result<Arc<[u8]>> {
    self.file_loader.read_binary_file(path)
}
```

Registration is intentionally skipped: `new_source_file` deduplicates by stable
id, so registering a binary read first would make the later lossy-text
registration return the earlier empty record and lose the snippet.

### 6. `rustc_parse/src/lib.rs` — closes the direct host read

`new_parser_from_file` retried a failed `SourceMap::load_file` with
`std::fs::read(path)`. That retry bypassed `FileLoader` completely: a denied path
was opened anyway, and for invalid UTF-8 the bytes were pushed through
`utf8_error`, which renders them into a diagnostic snippet. The patch routes the
retry through the loader:

```rust
if let Ok(contents) = sm.read_binary_for_diagnostic(path)
    && let Err(utf8err) = std::str::from_utf8(&contents)
```

Consequences:

- A denied path is never opened a second time, so no outside bytes can reach a
  diagnostic, a span or `SourceFile` text.
- An authorised invalid-UTF-8 file keeps its useful "byte N is not valid utf-8"
  diagnostic, now built from loader-approved bytes.
- The remaining `std::fs::read` call in this function is gone; there is no
  second raw read to re-enable.

This closes the parser retry only. The `FileLoader` implementation itself is
still the adapter owner's work, and a loader that returns `Err` for every denial
is now sufficient, because nothing retries outside it.

## Why the rejected shapes are not used

| Rejected shape | Why it cannot satisfy the requirement |
| --- | --- |
| Temporarily clearing or rewriting the process environment | Mutates shared process state, races with other threads, and restoring afterwards does not undo a read that already happened. |
| Changing process cwd | Same global-state problem, and the compiler's cwd is per-session. |
| Scanning source text for `env!` / `include!` | Local `include!` files, declarative macro expansion, reexports and qualified paths introduce the builtin after any text scan. |
| `Config.track_state` / `after_expansion` cleanup | Both run after expansion, so `compile_error!(env!("SECRET"))` can already have read and printed the value. |
| `psess_created` alone | `ParseSess` carries source-map and diagnostic state, not a builtin environment resolver. |
| Re-registering the `env` builtin | `rustc_resolve` reports a compiler bug on duplicate builtin registration. |
| `--env-set` allow-list only | Has no absent/deny marker and no no-fallback mode, so unknown host keys still resolve. |
| Overriding the `env_var_os` query provider | Builtin `lookup_env` calls `std::env` directly and never consults that query. |

## How run, analysis and debug share one boundary

The patch exposes exactly one switch and makes it self-enforcing. An embedding
therefore has one shared installer that must:

1. set `config.opts.embedded_boundary = true`;
2. set `config.file_loader` to the bounded loader;
3. populate `config.opts.logical_env` with only the values the session intends
   to expose.

Calling that installer from `CompilerCallbacks::config` (run),
`AnalysisCallbacks::config` (analysis) and `DebugCallbacks::config` (debug) is
what produces one boundary for all three entries. Those three callbacks live in
`native/miri_adapter/src/lib.rs` and `native/miri_adapter/src/debug.rs`, which are
**not** touched by this patch and remain with their existing owner. Until that
wiring exists, the switch stays `false` and nothing changes.

Analysis must additionally treat a boundary abort as failure. Because the abort
is a fatal error raised before evaluation, `RustCodeAnalyzer` must surface
`unavailableReason` rather than an empty diagnostic list; a checked-clean result
on a boundary abort would be a false claim.

## Deployment boundary: this needs a compiler rebuild, not a Miri-only patch

The changed crates are driver crates, not Miri. `rustc_session`,
`rustc_builtin_macros`, `rustc_parse`, `rustc_interface` and `rustc_span` all link
into `rustc_driver`, and `Options` is part of the compiler-private interface.
Therefore:

- Apply the patch to the complete pinned Rust source **before** `rustc_driver`
  and `rustc_codegen_cranelift` are built. The driver, its private metadata,
  `rustc-dev` and the host proc macros must all come from that one build. A
  patched Miri tree linked against an official unmodified driver is not a valid
  combination.
- Patching only `src/tools/miri` and linking the official driver cannot deliver
  this boundary. The existing `miri-1.98.1-embedded-session.patch` is exactly
  that shape: it is applied with `-p1` to the Miri source root only, so it cannot
  add a compiler `Options` field, change `lookup_env`, or close the parser retry.
- A half-applied state is a hard build error, not a silent fallback. If the
  adapter sets `config.opts.embedded_boundary` while the driver was built without
  this patch, the field does not exist and the adapter fails to compile. No
  configuration accepts the flag and then ignores it.
- `rustc-dev` must be rebuilt and repackaged from the same build. Reusing the
  official `rustc-dev` metadata against a patched driver is rejected by the
  existing revision and metadata checks, and would be unsound regardless.
- Guest MIR libraries and packaged manifest hashes must be regenerated, because
  compiler-private identity changes. Existing packaged libraries, including the
  OHOS schema-1 set, were built without this patch and still contain the parser
  retry bypass.

Follow-up work that is **not** done here and **not** owned by this assignment:

| Follow-up | Current state | Owner |
| --- | --- | --- |
| Apply the new patch to the pinned source and rebuild driver, backend, `rustc-dev` and guest libraries | `build_rustc_host.py` has no reference to this patch. Only `build_miri_adapter.ps1` / `.sh` apply the Miri patch, and only to the Miri root | compiler pipeline owner |
| Set `embedded_boundary` and install the bounded `FileLoader` from all three callbacks | `CompilerCallbacks`, `AnalysisCallbacks` and `DebugCallbacks` set neither today | adapter owner |
| Repackage per-platform manifests and hashes | unchanged | packaging owner |
| Exercise the negative cases on a real build and on packaged OHOS | not started | runtime and device owner |

No isolation is claimed. Until the first two follow-ups land, the switch is
`false` in every shipped artifact and the compiler boundary stays open.

## Applicability evidence

Patch file facts: 5659 bytes, SHA-256
`13d23e32d84073f8274ff60d8a144b490c3a3b5c1e56fc23f46e3ffa3fa837ee`, LF-only
(0 CR bytes out of 5659), with `a/`…`b/` paths relative to the `compiler/` root.

Generation: the diff came from the real pinned files. Copies were rewritten with
exact anchors that must occur exactly once, then `git diff` produced the unified
diff. A missing or duplicated anchor aborts generation, so no hunk is written by
hand and no line number is guessed.

Dry run actually executed. `patch` is not on this machine's `PATH`, so
`git apply --check` was used against untouched copies of the six pinned files:

```text
$tmp = <temp dir>   # copies of the six unpatched pinned files

git -C $tmp init -q

git -C $tmp apply --check --stat native/patches/rustc-1.98.1-embedded-compiler-boundary.patch

 rustc_builtin_macros/src/env.rs  |    8 ++++++++
 rustc_interface/src/interface.rs |    8 ++++++++
 rustc_parse/src/lib.rs           |    5 ++++-
 rustc_session/src/config.rs      |    2 ++
 rustc_session/src/options.rs     |    8 ++++++++
 rustc_span/src/source_map.rs     |    9 +++++++++
 6 files changed, 39 insertions(+), 1 deletion(-)

APPLY_CHECK_EXIT=0
```

`--check` writes nothing. The temporary copies were discarded afterwards. This
proves the diff applies to the exact pinned bytes listed above. It proves nothing
about compilation.

Intended application, once the pipeline owner adds it:

```sh
patch -p1 -d <pinned-rust>/compiler \
  -i <repo>/native/patches/rustc-1.98.1-embedded-compiler-boundary.patch
```

## Residual gaps, stated plainly

1. **Not compiled.** No `rustc` build was run, so the patch is checked for
   applicability, not for type-checking. `read_binary_for_diagnostic` relies on
   deref coercion from `&Arc<[u8]>` to `&[u8]` at both call sites; a compiler run
   is still required to confirm it. `embedded_boundary` is `pub` and read from
   `ExtCtxt::sess.opts`, matching how `logical_env` is already read in the same
   function, but that is inspection, not a build result.
2. **Not wired.** No adapter callback sets the switch. The three entry points
   stay unconfined until the adapter owner installs the shared installer.
3. **Loader still required.** This patch removes the compiler-side bypasses; it
   does not implement the bounded reader. Descriptor-relative no-follow walking,
   per-file and total byte limits, FIFO refusal and symlink rejection remain to be
   delivered in the adapter, and `current_directory` must return the session's
   prevalidated root without touching host cwd.
4. **Proc macros remain a hole.** Arbitrary proc-macro code executes in the host
   and can read the process environment directly. The `injected_env_var` bridge
   already returns `None` for names outside `logical_env`, but that does not
   sandbox proc-macro code. These modes must reject user proc macros.
5. **Other host I/O paths are outside this patch.** Compiler metadata lookup,
   native codegen library loading and output files are separate paths. They must
   stay pinned to validated packaged artifacts or an owned output directory.
6. **Rebuild cost is real and blocks a Miri-only deployment.** The changed
   crates link into `rustc_driver`, so the driver, its private metadata,
   `rustc-dev`, the backend, Miri and the guest libraries must be rebuilt from
   one patched source tree and repackaged with new hashes. Applying this patch
   only to the Miri source and continuing to link the official unmodified driver
   cannot work: the new `Options` field would not exist. See the deployment
   boundary section above.
7. **No execution or device evidence.** Nothing here shows confinement at
   runtime. The negative cases in `research/native-compiler-boundary.md` still
   need an actual adapter build, Linux reference runs and, separately, packaged
   OHOS runs with prepared outside sentinels. Until then the compiler boundary
   remains open.
8. **Behaviour loss to accept deliberately.** A boundary-on session no longer
   reproduces rustc's ordinary read-failure detail for denied paths; it reports
   the loader's own error. That is the intended trade for fail-closed behaviour,
   and it must be visible in the adapter's failure text rather than presented as
   a clean analysis.

## Checks actually performed

- Pinned source presence, revision and per-file SHA-256.
- Source inspection of every touched region and of the call paths that reach it
  (`SourceMap::load_file`, `load_binary_file`, `new_parser_from_file`,
  `lookup_env`, `run_compiler`).
- Confirmation that only two `Options` literals exist, via `logical_env`.
- Patch generation with single-occurrence anchors and `git diff`.
- `git apply --check --stat` on untouched copies; LF-only verification.

No compile, link, ABI, device, packaging or process-control test was run.
