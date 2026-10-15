# Research: Complete 166-lesson curriculum content review

- Query: Check every Rust topic for substantive title/code/explanation alignment, complete runnable exercises, duplicate/filler content, and genuine advanced/capstone implementations.
- Scope: internal; read-only review of the two authored topic arrays, generator semantics, and paired Cargo sources.
- Date: 2026-10-15
- Workspace: `D:/MyNewProjects/qfli_rust` only. Shared core and sibling language projects were not modified.
- Snapshot: final merged arrays are semantically accepted at the hashes in Current Acceptance Status. Detailed initial findings and follow-up sections below are preserved as revision history; they are not current open-item lists.
- Ownership: research artifact only. Real compilation/output comparison is assigned to the tooling agent and is deliberately not duplicated here.

## Current Acceptance Status

- **All 166 lessons semantically accepted.** Complete coverage found contiguous IDs, distinct substantive content, and no true unfinished placeholders. No reported source/content blocker remains in the reviewed final arrays.
- First array SHA-256: `487226f138b70fdb6b06843dfe83076ac52a4d9734fe52bd92a794cfbaf5e2ba`.
- Second array SHA-256: `22669421c29c3d3e89cecbe79c9074c3ab105f429ab8db2c2e1d79ede644f4b9`. Accepted async replacements 139/140/142/144/146 and capstones 164/165/166 exactly match their final merged records.
- Shared core: reviewed commit areas accepted; coordinator reports 61/61 focused regressions passing. See `shared-release-audit.md` for evidence boundaries.
- Coordinator reports final generation passed with 166 lessons/166 examples/23 Cargo bundles; full-catalog compiler verification is running. Final platform tests/builds and commits remain coordinator/tooling-owned. Source semantic acceptance does not claim those pending execution results.

## Findings

### Complete coverage and structural results

Read title, summary, explanation, full standalone code, exercise prompt and full exercise answer for **all IDs 001 through 166**. Re-read ranges omitted by tool output truncation (011–024, 057–058, 159–161). Also inspected the full paired source maps for the three capstones and relevant Cargo/module/test lessons.

At the reviewed snapshot:

- Exactly 166 records; integer IDs are exactly 1–166, with no gaps or duplicate IDs.
- All 166 titles, summaries, explanations and standalone source strings are individually unique.
- Exercise answers have no exact duplicates even after replacing numeric literals for the duplicate comparison.
- The lesson progression contains real, distinct Rust subjects. No generic numbered lesson filler was found in the main arrays.
- No actual `todo!`, `unimplemented!`, unfinished Chinese placeholder tutorial, or empty answer was found. `Todo::new` is a real Rust type path, and lesson 002's “占位符” describes `println!` formatting; neither is unfinished content.
- The current generator's `TODO:` detector is case sensitive and therefore does **not** mistake `Todo::` for a placeholder. An earlier potential case-insensitive false alarm was withdrawn.
- Initial distribution: 30 beginner / 58 intermediate / 78 advanced; 140 desktop / 21 cargo / 2 miri-candidate / 3 external. There are 23 bundled Cargo projects because optional bundle presence and runtime category are separate concepts.

Initial author SHA-256 values, useful for distinguishing later author updates:

- `topics_001_084.json`: `6d83043df2e84f00ea5d1fc1302ae0df2a8018893dd293d241cd191fc1db1240`.
- `topics_085_166.json`: `0f1a26943b79fe1b54152bb98e178c576aed2014b4b4625ca49f499b89dcd5ad`.

### P2: Future combinators do not implement their advertised behavior

**143**, `tool/rust_content/topics_085_166.json:1949`:

- `Join2::poll` stores only A's completed output. If A returns Pending and B returns Ready, it immediately calls `a_out.take().expect("a finished first")` and panics. A real join must store either completed output independently and return only when both exist. The always-ready demonstration does not expose the reverse-completion failure.
- `Select2` puts B in `_b`, but `poll` only polls A. Thus B can never win even when A stays Pending. This is a missing implementation, not just an intentionally simplified scheduler.
- Its exercise requests a Pair receiving two Future values; the answer instead accepts two integers and awaits immediately-ready functions sequentially. It does not exercise the advertised combinator API.

**Required evidence after correction:** A-pending/B-ready, B-pending/A-ready, both-pending-then-woken, and both-ready paths; neither completed child may be polled again.

### P2: Waker and executor lessons promise scheduling that their examples omit

| ID and initial anchor | Verified issue |
| --- | --- |
| 138, second array:1784 | `cooperative_sum` calls `std::hint::spin_loop()`, which is a processor hint; it does not yield execution or return control to an executor. No task is interleaved. The explicit simulation comment should not be accompanied by a claim that this demonstrates task switching. |
| 139, second array:1817 | Explanation says polling after Ready is undefined behavior. Safe `Future::poll` may panic, block, or behave arbitrarily after completion but must not cause UB just for that call. `CountdownFuture` and answer return productive Pending without scheduling a wake. |
| 140, second array:1850 | Summary says real wakeup and explanation says the external event calls `wake()`. Main only stores a no-op Waker and changes the flag, then manually polls again; it never calls wake. |
| 144 | TicksAt/NeverDone are driven by unconditional polling. The ticking Future does not self-wake when more progress is immediately possible. Mark as a manual poll-budget simulation or implement the documented protocol. |
| 145, second array:2016 | Summary/explanation say Pending waits for a wake and then re-enters the ready queue. Actual loop unconditionally carries every Pending task into the next queue, never uses wake events, and prints `wakes=0`. CountingWake only increments a counter. |
| 146, second array:2049 | Claims a block_on/task-handle/timer model, but main runs two polling counters sequentially. There is no task handle, timer source, or concurrent scheduling; Delay returns Pending without wake. |

Lesson 142 explicitly limits its trivial driver to immediately-ready Futures; that limitation is legitimate when stated clearly. The same busy loop should not be presented elsewhere as a general executor, wake protocol, or I/O runtime.

### P2: Three capstones are thinner than the features promised

**164**, second array:2691, “multi-file CLI todo tool”:

- Summary promises persistent text storage and explanation promises a thin CLI parsing commands and calling the library.
- Neither standalone main nor the Cargo bundle parses process arguments, reads/writes a file, loads a serialized store, or reports command errors. The bin duplicates a private Todo implementation instead of calling the public library. A small fixed script adds/removes three hard-coded items.
- Exercise `parse` uses `splitn(3, ' ')` on `[ ] 3 review code`. Tokens are `"["`, `"]"`, `"3 review code"`; the parse silently becomes ID 0 with task `"3 review code"`. Printing only `len()==2` hides that corruption.
- It also converts malformed IDs to 0, accepts unvalidated marks, overwrites duplicate IDs, and increments `u32::MAX` without a checked error.
- Needed: real offline CLI commands, file load/save and error handling; a valid marker-aware parser; round-trip assertions comparing values/IDs/status/text, not just count; a library actually used by the Cargo bin.

**165**, second array:2732, “concurrent word count (threads + channels)”:

- Summary/title claim channels, but the code only spawns one thread per hard-coded document and joins them; it never creates a channel.
- The bin duplicates library functions, so testing the lib does not exercise the binary's copy.
- This is a real word-count demonstration, but it needs the stated message/worker pipeline and integration coverage to serve as the promised capstone. A bounded worker set and genuine result channel would also distinguish it from lesson 121's thread example.

**166**, second array:2773, “async task queue + safe FFI boundary”:

- Contains only one counter-style Future and a busy-poll block_on. No queue, multiple tasks, scheduling, or C ABI exists.
- `buf_get(&[u8], index)` performs checked pointer indexing in pure Rust; it is a valid local unsafe wrapper, but has no `extern "C"` boundary, ownership transfer, or external buffer contract.
- Main comments say three tasks while constructing exactly one. The Future returns Pending without wake, so a normal executor can leave it suspended.
- Its test files test only indexing/sum, not a queue or executor. The answer only writes one byte; it does not extend the advertised combined system.
- Needed: genuine queued/interleaved Futures, wake handling, at least a real local C ABI callable boundary and safe ownership contract, and tests for queue completion/order and error cases.

### P2: “External dependency required” substitutes ordinary functions for offline-capable features

| ID | Verified issue and offline correction direction |
| --- | --- |
| 150, second array:2187 | Says proc macros cannot be written with standard tooling alone and need syn/quote. Rust's compiler-supplied `proc_macro` API can implement simple macros without any registry dependency. Its bundle currently contains only a hand-written trait impl. Supply a real local proc-macro crate; syn/quote can be described as optional parsing helpers. |
| 151, second array:2226 | Describes an actual workspace, but the Cargo.toml has only commented workspace lines and main simulates crates with inline ordinary modules. A local workspace containing a proc-macro library and path-dependent consumer can compile offline. |
| 158, second array:2475 | Title/explanation/output say real FFI requires libc crate/network. `std::os::raw` / `core::ffi` plus a declared ABI can call supported system functions without libc crate. Existing main just scans a safe Rust slice. Clearly label a model as such, and include a real offline ABI example with platform link rules. |
| 159, second array:2514 | Says Rust panic crossing `extern "C"` is UB. Current Rust panics reaching a non-unwind C ABI boundary cause abort. Foreign unwinding into Rust through a non-unwind ABI has different safety rules; teach those cases distinctly. |

The issue is a false necessity claim or a missing real bundled implementation. Honest explanation of an optional external ecosystem is useful, and runtime markers alone are not placeholders.

### P2: Concrete textbook/API statements need correction

| ID and initial anchor | Initial statement / correction |
| --- | --- |
| 006, first array:167 | The generic `caret_allows` only compares equal major plus lower bound. That describes the given nonzero-major example; it is wrong for Cargo caret constraints on 0.x.y. Constrain its name/contract or implement pre-1.0 caret compatibility. |
| 007, first array:205 | Shared workspace Cargo.lock/target are said to prevent multiple dependency versions and incompatible types. A lockfile may contain multiple semver-incompatible versions. |
| 009, first array:279 | Missing `rerun-if-changed` is said to make generated results stale. Cargo defaults to scanning package files; explicit directives narrow the tracked change set. |
| 012, first array:383 | Says test functions have no return value. Tests may return types implementing Termination, notably `Result<(), E>` (also correctly taught by 108). |
| 015, first array:498 | Describes out-of-range float `as` integer as version-dependent UB/saturation. Current safe Rust casts saturate; NaN converts to zero. Do not teach UB for a current safe cast. |
| 025, first array:818 | Says repr(Rust) fields follow declaration order. Rust may reorder fields; lesson 160 correctly states the opposite. |
| 048, first array:1556 | Says Cell only works for Copy. Only `get()` requires Copy; `set`, `replace`, `take`, `into_inner` permit suitable non-Copy values. |
| 049, first array:1588 | Says `HashMap::entry(key)` only borrows key. It accepts K by value; the sample uses Copy `&str`, masking ownership transfer. Also `remove` returns Option but removes the map entry; it does not leave None in that slot. |
| 079, first array:2549 | Teaches lossless From but its `From<&str> for UserId` maps every equal-length text to the same number. Use a transparent string wrapper or an obvious value-preserving conversion instead of calling length a lossless conversion. |
| 081, first array:2613 | Exercise implements `PartialEq` by absolute difference <0.5. It violates transitivity: 20.0≈20.3 and 20.3≈20.6, but 20.0≉20.6. Provide an explicit `approx_eq` method or a true equivalence relation. |
| 094, second array:297 | Says `sort_by_key` accepts Fn; actual bound is FnMut. FnOnce is a capability to call at least once, not necessarily a closure that consumes captures on every call. |
| 121, second array:1222 | Says capturing Arc satisfies Send without stating inner bounds. `Arc<T>` is Send/Sync only with the relevant T: Send+Sync bounds; Arc does not make Rc/RefCell thread safe. |
| 123, second array:1288 | Again says Cell requires Copy; apply the same correction as 048. Lesson 120 partially qualifies it, but later says values only copy, overlooking moves via replace/take. |

### P2: Exercise answers or generic helper inputs contradict the lesson contract

| ID | Concrete mismatch |
| --- | --- |
| 032, first array:1042 | Exercise asks to extend the preceding precedence calculator with unary negation. The answer replaces it with a +/- parser and drops multiplication/division; `2 + 3 * 4` now attempts to parse `*` as a number. Implement the extension without dropping the covered operators, or clearly revise the exercise scope. |
| 047, first array:1523 | `tail(text, n)` uses direct string slicing at byte len−n; `tail("你好",1)` panics on a non-UTF-8 boundary. Implement character-aware behavior or document/validate byte-boundary input. |
| 060, first array:1941 | Renderer truncates with `&text[..width-1]` based on bytes, panicking for ordinary multibyte text. Width zero also returns an ellipsis exceeding the requested width. Use chars/display-width semantics appropriate to the stated scope. |
| 065, first array:2101 | Prompt requires i128 checked_div; answer implements i64. |
| 076, first array:2453 | Prompt requests InMemory implementation of merge; answer inherits a no-op default (`let _ = other`). Supply meaningful merging and demonstrate it; an intentionally optional default should be named/documented as such. |
| 084, first array:2709 | JSON string escape handles only backslash/quote; a name with newline/control characters emits invalid JSON. CsvCodec writes names containing comma/quote/newline without quoting. These are advertised format encoders, so either implement the needed escaping or explicitly reject unsupported values. |
| 106, second array:698 | Says thin bin reuses lib, but bundled bin contains a copied implementation in `mod lib_logic` and does not use the bundled library. Similar duplication exists in 164–166. The current exact src/main/standalone contract makes this easy to miss; use genuine shared-module reuse without breaking standalone imports. |
| 118, second array:1123 | Prompt says add 4 and 5 and print sum 9; answer starts with [1,2,3], then adds 4/5 and prints 15. |
| 129, second array:1486 | Prompt says first/second half sums for [1,2,3,4] are 6 and 10. Actual halves sum to 3 and 7, which the answer computes. |
| 132, second array:1584 | `transfer(&m, &m, amount)` locks the same non-reentrant Mutex twice and can deadlock forever. Detect pointer equality and return/no-op or reject same-account transfers before locking. |
| 161, second array:2586 | `hash_not_slower` compares measured duration and expects true in exact stdout. Timing order is not deterministic; compare algorithm results and describe/report timing separately without an exact boolean speed guarantee. |

### Secondary teaching limitations worth tightening

- 055 asks for a Task structure, but its exercise demonstrates only a status/action function. 057 asks for guards plus @, but its answer only uses @. 062 asks for explicit ref, but answer relies on implicit match ergonomics. These are small prompt/answer alignment gaps.
- 064's scanner exercise says whitespace-delimited tokens and explicit Outside/InWord/InNumber states; answer splits `a1` into a word and a number using a bool. State the actual token grammar and implement the requested enum if that is the learning goal.
- 068 does not reject arguments after quit despite describing per-command arity validation. Its exercise says set has “three parameters” but key/value are two arguments after the command; clarify counting.
- 099/101 division helpers handle zero but may still panic for i32::MIN / -1. Unlike arbitrary huge arithmetic examples, a lesson explicitly discussing recoverable division errors benefits from checked_div and a matching overflow variant.
- 112 correctly handles the shown single-line CSV subset, but accepts quotes inside unquoted fields and text after a closing quote; its block exercise splits newlines and therefore cannot parse embedded quoted newlines mentioned in the introduction. Clearly document a single-line subset or use stricter state transitions. The explanation's claimed signature also omits Result.
- 130 RefCell<T>: Send requires T: Send. 133/134 “SeqCst is the slowest” is an architecture-dependent performance generalization, not a universal guarantee.
- 135 version-packing comment says low bits are version while code puts version in high bits. It assumes 64-bit usize; state that restriction or use a suitable fixed-width atomic with target gating.
- 146 answer requests block_on_all but writes three separate calls and never defines that function. 147 max_of and 148 sum_and_print evaluate supplied expressions multiple times; 149 my_vec![expr;n] reevaluates expr each iteration instead of evaluating once then cloning. Show a captured local value so side effects match the advertised vec-style semantics.
- 157's rust_abs overflows on i32::MIN at a C ABI boundary; choose checked/saturating/unsigned output or document a restricted domain. 153–155 omit explicit unsafe blocks inside unsafe fn under edition 2021; valid there, but explicit blocks support current edition practices.
- 154's raw-parts explanation should explicitly require a single allocation containing initialized valid T elements and no mutation (except permitted interior mutability) for the shared slice lifetime. The Vec demonstration itself satisfies these conditions.

## Files Found / Code Patterns

- `tool/rust_content/topics_001_084.json`: IDs 001–084, primary author input. Initial issue anchors are listed above.
- `tool/rust_content/topics_085_166.json`: IDs 085–166 including async/macros/FFI/capstones, primary author input.
- `scripts/generate_rust_content.py:21`: placeholder detector; catches true unfinished macros/text without rejecting Todo type names.
- `scripts/generate_rust_content.py`: schema/type/uniqueness checks and generation; schema validation alone cannot establish textbook semantics or truthful feature claims.
- `scripts/verify_rust_content.py`: real compiler/Cargo/output boundary, owned by tooling verification; good fixed examples do not expose missing generic branches such as 143's B-first case.
- `research/content-cross-review.md`: separate repository/import/generator review; use its resolution notes independently of curriculum issues.

## Related Specs

- `.trellis/tasks/10-15-rust-release-readiness/design.md`: complete runnable standalone example and answer per lesson, 166 substantive topics, offline paired Cargo projects, exact output verification, and no fabricated success.
- `.trellis/spec/frontend/content-imports.md`: new-project Cargo import, actual editable source, custom entry filenames, and failure semantics.
- `.trellis/spec/backend/native-runtime.md`: desktop compilation does not establish mobile engine support; source content review must not make mobile runtime claims.
- `.trellis/workflow.md`: persist research and review evidence before final release acceptance.

## External References

Reference contracts for the identified API/language facts (standard documentation; no network request or external build was performed by this research agent):

- Rust standard `Future` poll contract: https://doc.rust-lang.org/std/future/trait.Future.html
- Rust standard `Cell`: https://doc.rust-lang.org/std/cell/struct.Cell.html
- Rust standard `PartialEq` transitivity contract: https://doc.rust-lang.org/std/cmp/trait.PartialEq.html
- Rust standard `HashMap::entry`: https://doc.rust-lang.org/std/collections/struct.HashMap.html#method.entry
- Rust standard `slice::sort_by_key`: https://doc.rust-lang.org/std/primitive.slice.html#method.sort_by_key
- Rust standard `Arc` thread-safety bounds: https://doc.rust-lang.org/std/sync/struct.Arc.html#thread-safety
- Rust standard `hint::spin_loop`: https://doc.rust-lang.org/std/hint/fn.spin_loop.html
- Rust Reference type layout: https://doc.rust-lang.org/reference/type-layout.html
- Rust Reference float-to-integer cast semantics: https://doc.rust-lang.org/reference/expressions/operator-expr.html#numeric-cast
- Rust Reference procedural macros: https://doc.rust-lang.org/reference/procedural-macros.html
- Cargo build script change detection: https://doc.rust-lang.org/cargo/reference/build-scripts.html#change-detection
- Rust Nomicon FFI unwinding: https://doc.rust-lang.org/nomicon/ffi.html#ffi-and-unwinding

## Caveats / Not Found

- This is a complete semantic read of the authored draft, not a compiler, mobile engine, OHOS device, Android device, or UI test pass. Those remain with the coordinator/tooling owners.
- Compilation/output comparison can pass every fixed sample while the documented generic API is incomplete, as in Join2/Select2 and the todo parser; add targeted behavior evidence where the correction merits it.
- Authors are actively fixing files. All confirmed issue groups were immediately sent to `/root` so original owners can amend their own ranges. Re-read changed records before treating any initial issue as a final release blocker.
- No deletion/regeneration, source edits, generated asset updates, Git operations, Flutter commands, or shared-core mutations were performed in this research subtask.


## Revision Review: first author corrections and replacement capstones

The coordinator requested continued review. The following observations supersede relevant initial-draft issues above; they are semantic review results, not compilation evidence.

### First-array snapshot `15d346a679ed75034e2ea795d487ebe6529ef0b68162e55408522d6a2cd6c1b7`

Re-read corrected fields and full affected implementations:

- Resolved in substance: 007 workspace caveat, 009 Cargo rerun defaults, 025 repr(Rust), 032 neg extension preserving multiplication/division and precedence, 047 character-based tail, 060 Unicode-aware truncation/zero width, 065 matching i64 prompt, 076 real default merge with sorted entries and demonstration, 084 complete JSON control-character/CSV field quoting.
- 048 now correctly distinguishes Copy-only get from moving operations; explicitly note that take additionally requires Default rather than claiming every operation is available for arbitrary T.
- Still present at that snapshot: 006 general caret helper lacks 0.x compatibility, 012 tests are said to have no return value, 079 lossy text-length From example, 049 remove is said to leave None in the original position.
- New correction error in 015: float-to-float conversion is called saturating; f64 to f32 can round to positive/negative infinity on overflow. The added “non-number to float is NaN” wording is also ambiguous; remove it and teach the actual numeric cast cases.
- 081 moved approximate comparison to an explicit method and uses bitwise equality for Eq, which is a valid chosen equality. Its new comment incorrectly says PartialEq requires reflexivity/full equivalence: PartialEq requires a partial equivalence relation (symmetry/transitivity), while Eq adds reflexivity. Explain the chosen bitwise semantics, including distinguishing +0/-0 and comparing NaN encodings, instead of confusing that choice with mandatory PartialEq requirements.

All remaining/new issues above were sent promptly to the coordinator for the first-range author.

### Replacement capstone source `build/capstone-replacements.json`

Read each replacement's complete code, full exercise changes, explanation, Cargo manifest, companion library, integration tests, and README.

- **164 semantic acceptance:** now implements actual CLI parsing, positive IDs, escaped TSV disk persistence, invalid-store errors, checked ID allocation, same-directory temporary-file save, real cross-process integration tests, and remove exercise preserving existing IDs. The explanation correctly limits concurrency/crash-consistency claims. The companion library is honestly described as a test-output helper rather than a false business-logic library. This resolves the initial placeholder-like capstone problem.
- **166 semantic acceptance:** now implements a real ready channel and Waker-based requeue; Pending tasks are not busy-polled. Event readiness/waker registration occur under one mutex, waking happens after releasing it, cancellation is terminal, duplicate IDs are rejected, and real pending events are driven by producer threads. It exports and reimports an actual C ABI symbol with null/overflow status codes and explicit pointer contract; the safe wrapper supplies a valid owned slot. Exercise adds the promised fourth overflow task. No new blocker was found in this read.
- **165 substantive implementation, one confirmed remaining blocker:** fixed-size workers, bounded task channel, independent producer, result messages, real file I/O, Unicode token normalization, deterministic merge, and invalid-UTF8/missing-file errors are real. However, `worker` uses `path.file_name().ok_or("missing filename")?`, which exits a worker without an Event for root paths. The pipeline retains its original Arc containing the Receiver. With more root-path jobs than workers+capacity (e.g. eight Windows drive roots for workers=3/capacity=2), every worker can exit, leaving producer blocked on sync_channel::send because the unused original Receiver is still alive; main then blocks forever joining producer. Convert bad path metadata into an Event error, and drop the unused original queue after workers clone it. This was sent directly to both coordinator and content_plumbing; re-read the corrected branch and require a timeout-bounded behavior regression before closing it.

The paired capstones no longer need to be judged by the original small hard-coded demos above. Remaining publication evidence is their actual build/test run plus the 165 shutdown fix.


### First-array round-4 follow-up (`3a9beb360cd1852dcab26b531a74e7205476a20a85fa5ed39ec42af6ca497108`)

Author report `curriculum-a-fixes-1.md` claims round-4 completion. Direct source reread confirms 006, 012, 015 and 049 are now corrected. Two report-versus-source gaps remain and were sent to coordinator:

- 079 explanation and exercise may be corrected, but the **main lesson code** still defines `UserId(u64)` and implements `From<&str>` by `value.len() as u64`, with expected `UserId(4)`. This still contradicts the newly explicit lossless conversion rule; the main program must change too.
- 081 explanation now correctly distinguishes PartialEq from Eq, but the **exercise answer comment** still says PartialEq must be reflexive/full equivalence. Change that exact comment to describe this implementation's deliberate bitwise Eq choice.
- Minor 048 wording: `take` is not available for every T; it requires T: Default. The next sentence hints at that but the blanket first claim should be precise.

Do not substitute the author's passing output run for this source-level alignment check.


### Capstone 165 shutdown fix: accepted

Re-read the updated replacement. Missing filename now yields a normal `Event` carrying `Err("missing-filename")`; workers do not exit early. The unused original queue Arc is dropped after spawning worker clones, so sender disconnection is observable. Both code and answer contain the correction. The default selfcheck exercises eight root jobs against workers=3/capacity=2. The Cargo regression `root_paths_exceeding_workers_and_queue_capacity_finish_with_errors` starts a real process, uses the platform root path eight times, bounds completion by ten seconds, kills/reaps on timeout, and requires nonzero/8 errors/no panic. The implementation agent supplied refreshed `build/capstone-verification.json` with all six standalone/answer runs and all three Cargo projects passing. The reported deadlock blocker is closed; all three replacement capstones are semantically acceptable for coordinator merge.

### Second-array correction snapshot `c9a1b633f6b94addd102086619e8aa9e53c71a4ac0edf9699c601794d5fd4439`

Read the actual modified main code, answer and companion files rather than relying on author completion claims.

Resolved initial issues: 118 now starts empty and prints 9; 129 prompt says 3/7; 121/123 clarify Arc/Cell bounds; 132 same-lock transfer guard and demonstration; 143 caches both child outputs and Select polls both branches; 145 really requeues via self-wake; 147 exercise, 148 main, 149 main evaluate each relevant expression once; 150 contains a real offline proc-macro dependency and test; 157 exercise handles MIN with documented wrapping_abs; 158 provides an actual self-export/imported C ABI; 161 removes timing-order output.

**New P2 blocker in wake corrections (139, 140, 142, 144, 146, including affected answers):** readiness is an AtomicBool checked before locking the separate waker slot. The producer can store ready and take an empty slot between that read and waker registration. The Future then returns Pending and the executor waits forever, because the only wake was lost. Sleep(5/10/60ms) does not establish synchronization. If producer completes before first poll instead, counts vary (one poll/zero wakes), violating exact expected output. 146 starts both timer threads before driving them sequentially, making the second timer's lost-count case particularly plausible. Required correction: atomic readiness/waker registration via one mutex or a carefully proven register-and-recheck scheme, plus first-Pending handshake and joined producers for deterministic counts. Capstone 166 already shows a sound same-lock/handshake pattern. All affected IDs were sent promptly to coordinator.

**151 remains a false implementation claim:** explanation says true proc-macro workspace; root manifest has no workspace table, dependency manifest has no `[lib] proc-macro=true`, and `macros/src/lib.rs` is still an ordinary public String function. Its test merely calls that function. Implement an actual local proc-macro/consumer or revise the topic honestly; do not accept the current promise as fulfilled.

**159 remains factually wrong:** explanation still says a Rust panic crossing a non-unwind C ABI is UB; current Rust aborts. Different foreign-exception cases need distinct wording.

Remaining lesser alignment items were also sent: 120 Cell copy-only wording; 130 conditional RefCell<T>:Send; 135 reversed packing comment/64-bit assumption; 106 duplicated bin/lib despite reuse narrative; 143 missing join_values function requested by prompt; 146 prompt/answer function signature mismatch; 099/101 recoverable division MIN/-1 overflow; 112 Result signature/single-line CSV subset disclosure. They are not equivalent in severity to the wake deadlock or false proc-macro project, but final evidence should not silently claim every reported statement is fixed.


### First array final acceptance — 2026-10-15

- Coordinator-supplied final author freeze: `c193d466d69c39e770689a97e74df676b54c3032`.
- Actual `tool/rust_content/topics_001_084.json` SHA-256: `1c0eaf0de699d51f97a6562506d4c7e7c3ea96dd846e3fdce473814b9f14ea6b`.
- 048: final explanation correctly separates unrestricted `set`/`replace`/`into_inner`, `take` requiring `Default`, and `get` requiring `Copy`.
- 079: final main uses `UserId(String)`; `From<String>` preserves the owned text and `From<&str>` copies it. Equal-length distinct strings remain distinct, and Chinese text is retained. Expected output matches the stored values.
- 081: final answer comment correctly attributes symmetry/transitivity to `PartialEq` and reflexivity to `Eq`; its selected bitwise equality is consistently described separately from approximate comparison.
- All three outstanding first-array findings are closed. Together with the earlier complete semantic review, the first array is accepted. This is source/content acceptance; the coordinator and tooling owner retain compilation/output verification ownership.


### Async replacement acceptance — 2026-10-15

Full code/answer review accepted isolated replacements 139/140/142/144/146 at SHA-256 `6b9aa3632ed67ba39d147ed89b1f8fc0a59bee770589e9ad63f9a4373b57f222`. Same-lock readiness/Waker registration, first-Pending handshakes, predicate-based Condvar wait, and explicit producer joins close the previously reported lost-wake/determinism blockers. 144 now demonstrates real elapsed timeout plus observable cancellation progress; 146's sequential collection signature and narrative agree. Exact reviewed code, synchronization reasoning, companion-file equality and owner-supplied ten-program/100-repeat/Cargo evidence are persisted in `async-replacement-review.md`. Coordinator owns merge and final complete-array verification.


### First-array secondary exercise reread — 2026-10-15

- Coordinator-supplied frozen blob: `58bc24405ac4bb5bc785cf65041bbc3d6b6af020`. Researcher did not run Git to inspect object identity.
- Actual `tool/rust_content/topics_001_084.json` SHA-256 at reread: `8f2a5129182b28b8c60d2067cb9c1b6027a835e9b24d580a671f49c1f613f7b2`.
- Scope: read complete summary, explanation, main code/output, exercise prompt/hint/answer for only 055/057/062/064/068. No new-topic expansion or duplicate compilation.
- 055 accepted: answer now defines Task with name/status and a transition method. Todo->Done, Done->Todo, Done->Archived and terminal Archived behavior match the requested model. Main demonstrates legal completion/archive and rejected reopen after archive.
- 062 accepted: answer explicitly uses ref bindings, returns the first name slice with correct borrowed lifetime, and demonstrates a nonempty slice plus empty input.
- 064 accepted: answer implements the requested Outside/InWord/InNumber state enum and flushes on category or whitespace boundaries. The requested a1 23 bc sample yields the promised four tokens. Non-letter punctuation is outside the specified sample grammar; this reread does not expand that scope.
- **057 still misaligned:** prompt says whole-ten scores receive a grade suffix, without excluding 0..=59. Answer handles that entire F range first without a guard, so bucket(0), bucket(10), and bucket(50) all return F rather than F(整十). Either implement the missing F-range guard or explicitly narrow the prompt's suffix rule to 60..=100. Existing demonstrations omit those F-range boundaries, so their passing output cannot close the gap.
- **068 still misaligned:** prompt explicitly also requires quit to reject excess arguments, but answer's Command enum contains only Set/Del and its match has no quit branch. Both quit and quit now return Unknown. Add a real Quit variant, exact-zero-argument rule, and relevant demonstration/assertions; the answer currently does not implement this requested part.
- Both exact remaining gaps were sent immediately to the coordinator for the original owner. First-array secondary closure remains pending those corrections; accepted primary findings are unchanged.


### Second-array final-author reread (seq18rust-release-1015) — 2026-10-15

- Actual `tool/rust_content/topics_085_166.json` SHA-256 at start of this final-author reread: `35e34c44be26d91383f3974bfa8a053d6f918b57d43166ccfa3f7b87576ecdee`. Coordinator is separately merging the already accepted async replacements, which will change the overall array hash without changing these findings.
- Scope: only previously reported remaining IDs 099/101/106/112/120/130/135/143/151/159. Read full main/answer/description for each, plus all 106 and 151 companion files. No unrelated-topic expansion, Git operations or repeat compilation.
- 099 accepted: `checked_div` now covers both zero divisor and MIN/-1 overflow and the main demonstrates both failures.
- 101 accepted: prompt and answer add Overflow, distinguish DivByZero first, and use checked_div for the signed overflow branch.
- 112 accepted: explanation now promises single-line CSV only, explicitly excludes multiline quoted records, and gives the actual Result-returning signature; block exercise propagates row errors.
- 120 accepted: explanation correctly separates get:Copy, set/replace without Copy, take:Default and consuming into_inner, with a real Cell<String> take demonstration.
- 130 accepted: RefCell<T>:Send is conditional on T:Send, and its lack of Sync is correctly explained.
- 143 scoped prompt alignment accepted: answer actually defines and calls join_values() with Join2(value(5),value(6)). Earlier accepted independent output caching and polling both Select branches remain intact.
- 159 accepted: explanation correctly describes a Rust panic at non-unwinding extern C as aborting, and distinguishes foreign exception cases.
- **106 remains:** description claims files/src/main.rs is the thin library consumer, but that file still contains the complete inline lib_logic duplicate. The newly added bin/thin.rs calls prime_app correctly, but it is outside Cargo's automatically discovered src/bin directory and Cargo.toml has no explicit bin path. Thus the advertised real thin binary is not a Cargo target at all. Register it explicitly as a target/default target or provide a real library-using main within the catalog's standalone/main constraints, and describe the actual final files accurately. A passing library test does not exercise the duplicated binary logic.
- **135 remains, small exact correction:** explanation now correctly says high32=version/low32=value and discloses its64-bit platform assumption. Main's original adjacent source comment still says low32=version/high32=value, opposite the implementation. Fix that comment; no wider redesign requested by this reread.
- **151 partial acceptance:** macros/Cargo.toml now has [lib] proc-macro=true; macros/src/lib.rs uses the real compiler proc_macro TokenStream and #[proc_macro_derive(Describe)]; tests/derive.rs really derives Describe for Widget and checks the generated method. Those fake-macro findings are closed for the demonstrated simple named-field struct. However, the root manifest still lacks [workspace]/members despite the title and explanation claiming an actual multi-package workspace. Add an explicit workspace containing macros (for example members=["macros"], resolver="2"). This does not require an external dependency or a change to the deliberately labeled standalone simulation.
- These exact three remaining items were sent promptly to coordinator for author correction. Other reported items in this ten-ID final-author reread are closed.


### First-array final secondary acceptance — 2026-10-15

- Coordinator-supplied frozen blob: `abd15ee20fa7a290f13fd112e8b1ab78c345755b`.
- Actual `tool/rust_content/topics_001_084.json` SHA-256: `487226f138b70fdb6b06843dfe83076ac52a4d9734fe52bd92a794cfbaf5e2ba`.
- 057 accepted: answer now places an explicit F(整十) guarded branch before ordinary F, with assertions for 0/10/50 plus 55 and other grade/invalid cases. The suffix rule now covers every requested grade range.
- 068 accepted: main and answer both implement real Quit and exact-zero-argument validation. Answer asserts quit succeeds, quit now returns the expected arity error, and set/del retain their valid/invalid behavior.
- These final two secondary findings are closed. Earlier accepted first-array items are unchanged; the first array is now semantically accepted with no remaining reported source/content blocker. No repeat compilation was performed by the researcher.


### Final merged-array acceptance — 2026-10-15

Re-read the final three scoped corrections and accepted them:

- 106: Cargo.toml explicitly registers name=thin/path=bin/thin.rs and sets default-run=prime_app. The true thin binary calls the public library. The explanation now accurately distinguishes the standalone/main duplicate used for direct rustc from the registered thin library consumer; it no longer falsely describes src/main.rs as the thin source.
- 151: root Cargo.toml now declares [workspace], members=["macros"] and resolver="2", alongside the actual path dependency. The macro crate retains [lib] proc-macro=true and the earlier reviewed genuine derive implementation and consuming integration test. The explicit workspace claim is fulfilled.
- 135: main's packed-CAS comment now agrees with code and explanation: high32 stores version; low32 stores value.

Final actual source hashes:

- `tool/rust_content/topics_001_084.json`: `487226f138b70fdb6b06843dfe83076ac52a4d9734fe52bd92a794cfbaf5e2ba`.
- `tool/rust_content/topics_085_166.json`: `22669421c29c3d3e89cecbe79c9074c3ab105f429ab8db2c2e1d79ede644f4b9`.

Compared complete JSON records of already-reviewed replacements against the actual merged second array: all five async records exactly equal build/async-replacements.json, and all three capstones exactly equal build/capstone-replacements.json. No repeat source review or compilation was necessary for those identical records. All previously reported content/source issues are closed at these final hashes. Coordinator owns the running complete-catalog verification and final platform evidence.
