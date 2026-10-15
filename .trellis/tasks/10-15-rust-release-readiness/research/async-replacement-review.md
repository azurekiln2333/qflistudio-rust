# Research: Async lesson replacement review

- Query: Review complete replacement lessons 139, 140, 142, 144 and 146 for lost wakes, deterministic synchronization, correct exercises, and honest runtime claims.
- Scope: internal; read-only review of isolated replacement JSON and implementation-owner verification evidence.
- Date: 2026-10-15
- Workspace: `D:/MyNewProjects/qfli_rust` only.

## Findings

### Acceptance

All five replacement lessons are semantically accepted at `build/async-replacements.json` SHA-256 `6b9aa3632ed67ba39d147ed89b1f8fc0a59bee770589e9ad63f9a4373b57f222`. Read each complete explanation, main program, prompt, hint and answer; also read 146's manifest, embedded tests and companion file equality. Coordinator has merged these replacements: all five complete records exactly match the final second array at SHA-256 `22669421c29c3d3e89cecbe79c9074c3ab105f429ab8db2c2e1d79ede644f4b9`. Final catalog execution verification remains coordinator-owned.

### Files Found and Code Patterns

- `build/async-replacements.json:20`, `:54`, `:88`, `:122`, `:156`: complete main programs for 139/140/142/144/146. Each uses one `Mutex<EventState<T>>` for both result readiness and current Waker. The producer sets the value and takes the Waker while holding that same lock, then wakes after unlocking. The old check/register race is removed.
- `build/async-replacements.json:28`, `:62`, `:96`, `:130`, `:164`: complete exercises. The affected wake-based answers use the same corrected protocol. The immediate-only factorial answer accurately expects one poll and zero wakes; it does not pretend CPU calculation becomes concurrent through async syntax.
- Every event Future sends its one-time first-Pending handshake through `sync_channel(1)` after registering under the event lock. The producer cannot publish before registration. The capacity-one first send has an initially empty buffer, so it does not wait for the producer while holding the event lock. The producer then needs the same event lock; the first poll therefore returns Pending before the completion can be observed.
- `Notify::signal` sets a Mutex-protected predicate before notifying the Condvar. `Notify::wait` checks the predicate in a loop and clears it while holding the same lock. A wake before wait is retained, and a spurious Condvar wake cannot cause another poll. For these one-event demos, one completion and the first-Pending handshake give exactly two polls/one wake. The producers are explicitly joined before final main-thread assertions.
- 139 accurately distinguishes violating the post-Ready poll contract from undefined behavior in safe implementations. 140 replaces a stored Waker on every Pending poll and explains notification rather than direct execution.
- 144 performs a real timeout via `recv_timeout` on a live, empty channel after registration. Its biased selector first polls the timer, then the incomplete work; the first Pending call records consumed progress. The winning branch leads to dropping the boxed selector and loser, with asserted `consumed=1 cancelled=1`. This is observable cancellation without pretending side effects roll back. The exercise honestly substitutes an external flag rather than claiming elapsed time.
- 146's exact prompt and answer agree on `fn block_on_all<F: Future>(futures: Vec<F>) -> (Vec<F::Output>, usize)`. It is explicitly a sequential collector with a fresh Notify per Future. Both timer threads are retained, each starts its own deadline only after its own first-Pending handshake, and both handles are joined. B therefore cannot finish early before its first poll. The explanation makes no concurrent `join_all`, Tokio implementation, or shared-reactor claim.
- `build/async-replacements.json:171`: 146 Cargo bundle has no external dependency. `src/main.rs` is exactly equal to the reviewed standalone main. The commented Tokio manifest sketch is clearly labeled for a real project rather than an active dependency. Embedded tests cover completion before first poll, duplicate completion rejection, replacing an old Waker, and 32 registered completion iterations. The exercise additionally includes empty and immediately-ready generic collection tests.

### Verification Evidence

Read and summarized `build/async-verification.json`, whose `replacementSha256` exactly matches the reviewed source. It reports host `rustc 1.98.1` (`x86_64-pc-windows-gnu`) compilation and execution success for all ten main/answer programs, plus ten successful repeated runs for each program (100 repeated runs), with a ten-second deadline per child and no timeout. The 146 Cargo project build of all targets succeeded; its three embedded tests passed. The implementation owner separately reports the generic exercise collection test passing. No duplicate compilation was run by the researcher.

### Related Specs

- Current task `design.md`: complete runnable lesson and answer, exact output evidence, and honest offline/runtime capability descriptions.
- `.trellis/spec/backend/native-runtime.md`: host compilation is not mobile runtime support evidence.
- `.trellis/workflow.md`: persist research and acceptance evidence in the current task.

### External References

- Rust `Future::poll` contract: https://doc.rust-lang.org/std/future/trait.Future.html
- Rust `Condvar`: https://doc.rust-lang.org/std/sync/struct.Condvar.html
- Rust bounded channel: https://doc.rust-lang.org/std/sync/mpsc/fn.sync_channel.html

## Caveats / Not Found

- No new source blocker was found in these replacements. The old lost-wake findings are closed for the exact reviewed replacement hash.
- One OS thread per timer and explicit producer joins are teaching choices. Cancellation of a Future does not terminate a producer thread; the lessons disclose this limit and do not present a complete shutdown protocol.
- The source-array merge is confirmed by complete-record equality. Final full-catalog verification remains with coordinator/tooling owners. Other second-array corrections are accepted in the final curriculum report.
- Research only: no source/config/generated-asset edits, Git operations, Flutter commands, or compilation were performed.
