# Per-session embedded filesystem capability

Status: source implementation and strict patch application checked. Actual
pinned Miri compilation, C ABI execution, catalog re-run and signed OHOS
execution remain required. Do not count this document or host metadata checks
as an OHOS pass.

## Owned changes

- `native/patches/miri-1.98.1-embedded-session.patch` extends the existing stream,
  memory and cancellation patch. It adds `src/embedded_fs.rs`, optional session
  callbacks and narrowly selected Unix file shims. The original patch behavior
  remains present.
- `native/fixtures/fs_*.rs` supplies positive and negative runtime/compiler
  fixtures. The compiler fixtures expose a separate integration boundary; they
  are not claimed fixed by the Miri guest-file patch alone.
- The parent owns `native/miri_adapter/src/lib.rs`, C headers, Dart bindings,
  root selection, builds, packaging and catalog/device execution. No shared-core
  or sibling product source was edited for this change.

The base is Rust 1.98.1 commit
`48a229ceaefd4985c50990b14116b6d856af0985`. The untouched Unix fs shim read from
the actual WSL reference source and from the reversed Windows source patch has
the same SHA-256:
`2a6289ac2403b4465de31cbc1ce678d6a70eb2746ad169c7ca8fb7f7306113ae`.
Staging is under `build/offline-ide-audit/fs-patch-{base,source,check}`. No pinned
baseline source tree was overwritten.

## Additive Rust contract

```rust
pub struct EmbeddedFileSystem; // Debug, Send + Sync, owns a root descriptor
impl EmbeddedFileSystem {
    pub fn new(root: &Path) -> io::Result<Self>;
    pub fn root(&self) -> &Path;
    pub fn temporary_dir(&self) -> &Path;
    pub fn current_dir(&self) -> io::Result<PathBuf>;
    pub fn set_current_dir(&self, path: &Path) -> io::Result<()>;
}
pub trait EmbeddedSession {
    // Existing input/output/cancel/memory methods are unchanged.
    fn filesystem(&self) -> Option<&EmbeddedFileSystem> { None }
    fn system_time(&self) -> Option<SystemTime> { None }
}
```

The parent integration uses an explicit canonical absolute project root. It
must prove the source belongs to that root and preserve all C layout/ABI-1
contracts. The proposed additive create symbol is
`qfli_miri_create_with_project(config, backend_path, project_root)`; existing
create symbols can select the source parent as a limited backward-compatible
root. Never select the ambient host cwd, compiler/sysroot or filesystem `/`.
`new` itself rejects nonabsolute roots, filesystem `/` and nondirectories.

Constructors on Linux (including the OHOS target) and Android use a pinned
directory descriptor. Other hosts return `Unsupported` and still compile.
Legacy Windows pure-code runs must retain `None` instead of failing because a
new optional filesystem capability is unavailable. This patch does not claim a
Windows/Apple filesystem implementation.

## Runtime operations and confinement

- `MiriMachine::communicate()` and `isolated_op` are unchanged. Networking,
  subprocesses, ambient environment forwarding, symlink creation and unsupported
  host operations remain isolated.
- `open`, `stat/lstat/statx`, reads/writes/seek, descriptor sync/truncate/close,
  `mkdir`, `rmdir`, `unlink`, `rename`, directory streams and `realpath` use the
  explicit capability. `FileHandle::sandboxed` marks only handles opened by it;
  this avoids globally enabling host communication to satisfy old fd assertions.
- Relative paths resolve against a mutex-protected **session** cwd. `chdir`
  validates a directory and changes this value only. It never changes the process
  cwd. Absolute paths outside the authorized root and `..` escapes fail.
- Every parent directory is opened with descriptor-relative `openat` and
  `O_DIRECTORY | O_NOFOLLOW`; the final open also uses `O_NOFOLLOW`. Symbolic
  links are deliberately not traversed, including links to another in-root path.
  `lstat` may inspect a link itself, and unlink may remove a link without touching
  its target. Rename/unlink resolve pinned parent directories and do not follow
  their final entries.
- Existing directory descriptors are addressed through kernel-owned
  `/proc/self/fd/<fd>` paths while the descriptors remain alive. This is not a
  canonicalize-then-open check on mutable guest paths. If a target denies these
  descriptor paths, operations fail; device support must be established by
  running the fixtures. No unrestricted fallback is permitted.
- `O_NONBLOCK` avoids hanging while opening a preexisting FIFO. File metadata
  rejects special devices/FIFOs and permits regular files/directories plus
  no-follow link metadata. This is namespace confinement, not inode exclusivity
  against host-created hardlinks/mounts or a hostile external process relocating
  an already-authorized directory.
- Each capability exclusively creates a fresh mode-0700
  `.qfli-miri-tmp-N` within its root. Miri inserts only that path as `TMPDIR`.
  `Drop` attempts to remove only that owned temporary entry through the pinned
  root descriptor. The parent must destroy/drop after worker completion as
  required by the existing ABI lifecycle. Project root and ordinary project
  files are not recursively cleaned by this mechanism.
- `system_time()` separately authorizes real wall-clock reads for
  `clock_gettime(REALTIME)` and `gettimeofday`. Other clock/localtime isolation
  guards are unchanged. The existing isolated process id is 1000; no host PID
  callback or ambient process identity was added.
- Stream routing, block/time/guest-memory limits and cancellation hooks remain
  present. Existing compiler-memory/nonpreemptive-query limitations still apply;
  this patch adds no disk quota and does not claim hard preemption of filesystem
  operations.

## Required real execution checks

Use the actual pinned adapter, not a signature-compatible stub. Create a fresh
project directory and a distinct outside directory; retain their initial bytes
and the host process cwd before running.

| Fixture/check | Required evidence |
| --- | --- |
| `fs_roundtrip.rs` | Exit 0, exact `filesystem-roundtrip-ok\n`; real UTF-8 file write/read/append, seek, metadata, sync, rename, directory traversal, canonicalize, recursive cleanup; host cwd unchanged |
| `fs_escape.rs` | Exit 0, exact `filesystem-escape-denied\n`; outside sentinel unchanged, no outside file/directory created; failed rename preserves local bytes |
| `fs_symlink_escape.rs` | Harness creates `escape-dir` and `escape-file` pointing outside; exit 0 and exact `filesystem-symlink-escape-denied\n`; outside sentinel remains `outside-unchanged` and no new outside directory |
| `fs_environment.rs` | Exit 0 and exact `filesystem-environment-isolated\n`; no ambient HOME/PATH/library-path/user-profile; TMPDIR exists below project and PID is isolated |
| `fs_network_denied.rs` | Nonzero isolation failure at `socket`; no success output and no host socket/connection created |
| Two sessions with same project | Distinct temporary directories, independent cwd, process cwd unchanged; dropping one capability removes only its own temporary directory |
| Existing old ABI stream/limit/cancel suite | All prior semantics and subsequent fresh execution still pass |
| Topics 164/165, examples and answers | Run exact authored files without replacing persistent file teaching; compare exact authored expected stdout |
| Full baseline catalog | Re-run all 332 programs after final native changes, preserving hashes and per-case results; then current signed OHOS package independently |

There are also two unit tests in the new upstream module. They use real disk
I/O and assert outside-file invariants. A small Linux host check can compile the
module directly with pinned rustc `--edition=2024 --test` plus the matching
`--extern libc=<rlib>` and run it before the larger Miri build.

## Separate compiler boundary requiring parent integration

The Miri runtime filesystem capability does not intercept rustc's own source
loading or builtin macro expansion. `include_str!`, `include_bytes!`, `include!`
and module `#[path]` must be checked through a project/sysroot-restricted compiler
file loader. `env!` and `option_env!` must not inherit arbitrary host environment
values. Do not use a global process `chdir` or temporary global environment
mutation to implement that restriction.

- `fs_compile_include_escape.rs`: copy to `<project>/main.rs` and create a real
  outside sentinel at the exact relative path it names. The compiler must reject
  access, without disclosing the bytes. A missing-file error without a sentinel
  does not prove confinement.
- `fs_compile_env_escape.rs`: the harness sets `QFLI_SANDBOX_HOST_SECRET` only in
  its host environment. Guest compilation must reject the `env!` access without
  exposing the value.

These are explicit remaining integration checks, not runtime-patch passes.

## Checks completed in this worker

- Read the actual attachment, task PRD/design/plan and applicable native spec.
- Exact source comparison with WSL reference Unix fs shim passed.
- `git apply --check --whitespace=error` and actual application of the complete
  regenerated patch to a reversed pristine staging tree passed. All resulting
  source files match the staged intended source after CRLF normalization.
- Pinned Windows rustc 1.98.1 compiled the standalone capability module as a
  library. Only expected standalone dead-code warnings remain.
- Pinned Windows rustc metadata-only compilation passed for all five runtime
  fixtures. They were **not executed by the host compiler**. The two compiler
  negative fixtures intentionally need prepared outside data/host environment
  and a real restricted adapter harness.
- No WSL build, Flutter process, device change, runtime rebuild or catalog
  execution was started by this worker.
