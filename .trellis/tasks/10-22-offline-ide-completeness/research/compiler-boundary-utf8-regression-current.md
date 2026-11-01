# Invalid-UTF-8 ABI regression: authored, never executed

## Scope of this assignment

- Owned file, and the only file edited: `native/miri_adapter/analysis_abi_test.c`.
- This report.
- Frozen and untouched: `native/miri_adapter/src/compiler_boundary.rs`,
  `native/miri_adapter/src/lib.rs`, `native/miri_adapter/src/debug.rs`,
  `native/patches/*`, Dart, shared core, build and packaging scripts.
- Not done: no compile, no link, no adapter build, no SDK or NDK invocation, no
  WSL, no device, no `hdc`, no subprocess of any kind. No commit.

## Status: authored, not run

The new case is written. It has never been compiled and never been executed.
No part of this report is runtime evidence.

Specifically, this report does **not** show that:

- the invalid-UTF-8 fix works at run time,
- the boundary confines a compiler session,
- the packaged adapter behaves this way on any device.

It shows what the ABI is *specified* to return, where each part of that
specification comes from in the pinned compiler and the frozen adapter, and why
this workspace cannot execute the check.

## What the regression asserts

Fixture: the test writes 39 bytes itself, so the invalid offset is exact.

- bytes `0..24`: `// invalid byte follows\n`, all ASCII,
- byte `24`: `0xFF`, which cannot start a UTF-8 sequence,
- bytes `25..39`: `\nfn main() {}\n`.

`str::from_utf8` therefore reports `valid_up_to() == 24` and
`error_len() == Some(1)`. Written at run time to
`<fixture-directory>/utf8-regression/broken_utf8.rs`, because the harness may
not add files to `native/fixtures`.

For one analysis session the test requires all of:

1. `QfliResult.state == QFLI_FINISHED` and `exit_code == 0`.
2. `QFLI_STDOUT` and `QFLI_STDERR` are both empty.
3. The diagnostics channel is pure JSON Lines.
4. The diagnostics channel does **not** contain `qfli: compiler boundary:`.
5. It contains `"level":"error"`, so the crate is never reported clean.
6. It contains `couldn't read` and the source path, i.e. the compiler's own
   message survived.
7. It contains `not valid utf-8`, i.e. the encoding diagnosis survived.
8. The primary span has `byte_start == byte_end == 24`.

Then, in the same process:

9. A second session on the same file must return the same verdict. A sticky,
   process-wide failure would surface here as `INTERNAL_ERROR`.
10. A fresh session on `analysis_valid` must still analyse clean, proving the
    malformed file left no poisoned compiler state.

Assertions 1 and 4 are the regression proper: the defect recorded a sticky
boundary failure for a decode rejection, which forced `INTERNAL_ERROR` / `1` and
appended a policy line to the diagnostics channel.

## Why this is a source verdict, not an environment failure

Every step below was read in the pinned tree
(`native/build/miri-windows/compiler/lib/rustlib/rustc-src/rust/compiler/`,
rustc 1.98.1, commit `48a229ceaefd4985c50990b14116b6d856af0985`) or in the
frozen patch.

1. `rustc_span/src/source_map.rs:246-247`: `load_file` propagates the loader
   error with `self.file_loader.read_file(path)?`.
2. `rustc_parse/src/lib.rs:108-126`: `new_parser_from_file` catches it, opens
   `struct_fatal("couldn't read `<path>`: <error>")` at line 117, then retries
   the same bytes at line 118 and calls `utf8_error`.
3. Frozen patch, `rustc_parse/src/lib.rs` hunk: the retry reads through
   `sm.read_binary_for_diagnostic(path)` instead of `std::fs::read(path)`.
4. Frozen patch, `rustc_span/src/source_map.rs` hunk:
   `read_binary_for_diagnostic` calls `self.file_loader.read_binary_file(path)`,
   so the retry still cannot read a path the policy denied.
5. `rustc_parse/src/lib.rs:131-186`: `utf8_error` uses `valid_up_to()` and
   `error_len()`. With `error_len() == Some(1)` the label is
   ``byte `255` is not valid utf-8``; with `None` it falls back to the note
   ``invalid utf-8 at byte `24` ``.
6. `rustc_interface/src/passes.rs:58-63`: the crate root is parsed with
   `sp = None`, so `utf8_error` takes the `else` branch and calls
   `err.span(span)` plus `err.span_label(span, msg)` on a real, zero-width span
   at byte 24. The label is attached, and the span is primary.
7. `rustc_errors/src/lib.rs:988`: `struct_fatal` returns
   `Diag<'a, FatalAbort>`. `FatalAbort::EmitResult` is `!`
   (`rustc_errors/src/diagnostic.rs:68-75`), and
   `emit_producing_guarantee` calls `emit_producing_nothing()` first and then
   `FatalError.raise()`. So the diagnostic reaches the emitter before the
   unwind.
8. `rustc_errors/src/lib.rs:1371`: the emitter is called before any error
   bookkeeping, and there is no Fatal-specific skip. The JSON is therefore
   written.
9. `rustc_errors/src/lib.rs:1664-1672`: `Level::to_str` maps
   `Fatal | Error` to `"error"`, so the JSON carries `"level":"error"`.
10. `rustc_errors/src/json.rs:494-495`: `byte_start` and `byte_end` come from
    `original_relative_byte_pos`, so they are the original byte offsets, here
    `24` and `24`.

Adapter side, frozen `lib.rs` analysis outcome:

- `stopped != 0` → `CANCELLED` / `124`,
- `boundary.failure().is_some()` → `INTERNAL_ERROR` / `1`,
- `Ok(true)` → `FINISHED` / `0`,
- `Ok(false) | Err(_)` with diagnostics already emitted → `FINISHED` / `0`,
- `Ok(false) | Err(_)` with none → `INTERNAL_ERROR` / `1`.

A parse fatal stops before `after_analysis`, so `analysed` stays `false`, but
the fatal diagnostic was already emitted, so the fourth arm applies. That is
`FINISHED` / `0`. With the sticky failure present the second arm wins instead,
which is exactly the regression.

## Correction to my earlier report

`compiler-boundary-integration-current.md` said the boundary failure message is
written to stderr. That is wrong, and the error matters for this test.

`SessionIo::append` takes a channel index, and `write_output(stderr, ..)` maps
only `0` to stdout and `1` to stderr. The diagnostics writer
(`DiagnosticWriter::write`) appends to channel `2`, and the boundary refusal in
the analysis outcome also calls `session.io.append(2, ..)`. So the refusal line
lands in the **diagnostics** channel, not stderr.

Two consequences:

- this regression must look for the policy line in the diagnostics channel, and
  it does;
- a boundary failure injects a non-JSON line into the JSON Lines channel, which
  breaks the documented contract that channel 2 is JSON Lines only. That is a
  real defect in the frozen `lib.rs`. It is recorded here and **not** fixed,
  because `lib.rs` is outside this assignment.

## Portability blocker: why this cannot run in this workspace

1. `compiler_boundary.rs:72` gates on
   `cfg!(all(target_os = "linux", target_env = "ohos"))` plus an architecture
   check. The adapter built here is a Windows build, so `host_supported()` is
   `false`.
2. `install` then records `compiler boundary unsupported on this host` and calls
   `fail_closed()`, which raises `FatalError` inside `Callbacks::config`, before
   the crate root is ever parsed.
3. Independently, `Loader::read` has a `#[cfg(not(target_env = "ohos"))]` body
   that returns
   `Err(self.deny("descriptor-relative reads are unavailable on this host", ..))`,
   and `exists` returns `false`. So even if the gate in (1) were bypassed, no
   read could succeed.
4. Consequence: no analysis case in this harness can pass on Windows or on a
   `*-linux-gnu` Linux host. The whole file is now device-only, and the desktop
   path that used to prove it is gone by design.

To actually execute it, all of the following are required:

1. An adapter built for `aarch64-unknown-linux-ohos` or
   `x86_64-unknown-linux-ohos`.
2. This harness built with the OHOS NDK clang for the same triple, linking
   `dlopen`/`dlsym` and `pthread`, both of which live in OHOS libc.
3. The adapter `.so` plus its `NEEDED` libraries (`libc.so`, and
   `libc++_shared.so` where used) resolvable through a `$ORIGIN` runpath at an
   absolute path.
4. A guest MIR sysroot at an absolute path, passed as `argv[2]`.
5. A **writable** fixture directory, because the new case creates
   `<dir>/utf8-regression/broken_utf8.rs` itself.
6. `native/fixtures` present on the device for the pre-existing cases.

One prerequisite is easy to miss: analysis hard-codes
`--target=x86_64-unknown-linux-gnu` in the frozen `lib.rs` argument list. So the
sysroot on device must contain `x86_64-unknown-linux-gnu` MIR libraries even on
an aarch64 device. This affects every analysis case, not just this one.

The harness already skips cleanly in two situations: missing run symbols
(`return 1`) and a missing optional analysis extension (`return 3`). The new
`boundary_host_supported` probe extends that convention: if the very first
analysis returns `INTERNAL_ERROR` / `1` with a boundary line naming
`unsupported on this host` or `unavailable on this host`, `main` prints a SKIP
and returns `3`. Any other failure still aborts, so a genuine boundary
regression cannot be mistaken for an unsupported host.

## Static checks actually performed

No compiler was invoked, so these are text checks only.

- Preprocessor-branch-aware brace balance: balanced for both branch selections.
  The file contains one `#ifdef/#else` split function definition
  (`run_thread`), which defeats naive brace counters and made two earlier
  balancers report false imbalances.
- The fixture initializer has 39 tokens, index 24 is `0xFF`, and the first 24
  tokens are the ASCII prefix.
- No duplicate function definitions except the intentional `run_thread` pair.
- Every new function is defined after all functions it calls.
- One portability defect was found and removed during authoring: the fixture
  check was first written as
  `_Static_assert(INVALID_UTF8_SOURCE[24] == 0xFF, ..)`. In C11 the value of a
  `static const` array element is not an integer constant expression, so OHOS
  clang would reject it. It is now a runtime `assert`, and only
  `sizeof(INVALID_UTF8_SOURCE) == 39` remains a static assertion.

## Expectations a device run may need to adjust

These are the only parts of the assertion set that are inferred rather than
directly read off a string constant. The state, exit code, level and message
assertions do not depend on them.

- `byte_start == byte_end == 24` assumes the lossy-decoded copy keeps positions
  before the invalid byte unchanged and that `original_relative_byte_pos` maps
  back to `24`. If the pinned compiler normalizes differently, this one
  assertion needs adjusting.
- `not valid utf-8` assumes `error_len() == Some(1)`, which holds for a lone
  `0xFF`. A truncated multi-byte sequence at end of file would instead take the
  note branch, whose text is ``invalid utf-8 at byte `24` ``.
- `contains(diag, source)` assumes a POSIX path, so no backslash escaping in the
  JSON message. That is true on OpenHarmony.

Unchanged and not exercised here: an invalid-UTF-8 file is charged twice against
the read budget, once for the failed text read and once for the diagnostic
retry. Both charges stay under the 8 MiB per-file and 64 MiB per-session limits.

## Files

| File | Bytes | SHA-256 |
| --- | --- | --- |
| `native/miri_adapter/analysis_abi_test.c` | 32327 | `8ead88d9537ae329521e0e2e3e8b0ee4c2c353cdc0b566c99389b271f9ec3d71` |

`analysis_abi_test.c` is untracked in this branch, so there is no committed
baseline to diff against. The pre-existing cases were preserved unchanged; the
additions are the fixture, `ensure_directory`, `write_bytes`,
`new_analysis_source`, `boundary_host_supported`, `check_invalid_utf8`,
`invalid_utf8_source`, one probe call and one case call in `main`, plus the
platform includes.

## Observation: the loader changed after my freeze

`compiler_boundary.rs` is now 28213 bytes,
SHA-256 `f5ed454e2fe4bf3556cd828d299ccc486c77c51ce1a40d81068eccda9bfbff42`.
I froze it at 28202 bytes, SHA-256
`5ae3c511dd04709faba948d30c6ef504262b1a46d6c3d5f2fc82a77fe1f21a87`, so another
owner edited it afterwards. The hash published to p3 for re-review is therefore
stale. Recorded, not reverted, and not edited by me.

`lib.rs` is unchanged at 37326 bytes,
SHA-256 `2bd562c164ddc973984f8b2f2678b14aa28f8ea46be62425f9c0de30b17b0ecb`,
matching p3's reviewed snapshot.
