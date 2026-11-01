//! Shared read-only compiler boundary for the embedded run, analysis and debug
//! entry points.
//!
//! The embedded sessions compile learner source with the pinned rustc. Plain
//! rustc reads source through `RealFileLoader`, which follows symlinks, opens
//! FIFOs and reads any host path that `mod`, `#[path]`, `include!`,
//! `include_str!` or `include_bytes!` names. This module installs one
//! session-scoped replacement so all three entry points share a single policy.
//!
//! What the boundary enforces:
//!
//! * Two read roots only: the canonical project (or analysis mirror) root and
//!   the trusted packaged sysroot. Every other path is denied.
//! * Descriptor-relative `openat` traversal that never follows a symlink,
//!   rejects non-regular files (FIFO, device, socket) and bounds every read.
//! * A session working directory taken from the project root, so nothing reads
//!   or mutates the host process cwd.
//! * The patched `Options::embedded_boundary` switch, which also removes the
//!   ambient environment fallback of `env!`/`option_env!` and makes a missing
//!   `Config::file_loader` a fatal error instead of a silent downgrade.
//!
//! The boundary fails closed. A root that cannot be opened, an unsupported
//! host, or an argument surface this policy cannot cover stops the compiler
//! before the session exists. It never degrades to an unrestricted loader.
//!
//! What it deliberately is not: a process sandbox. Compiler metadata
//! (`--extern` libraries), codegen backend loading and generated output files
//! are separate host paths. See
//! `research/compiler-boundary-integration-current.md` for the exact gaps and
//! the gates that remain before any confinement claim.

use std::io;
use std::path::{Component, Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};

use rustc_interface::interface::Config;
use rustc_span::fatal_error::FatalError;
use rustc_span::source_map::FileLoader;

/// Largest single source file the compiler may read.
const MAX_FILE_BYTES: u64 = 8 * 1024 * 1024;
/// Largest total of source bytes one session may read across all files.
const MAX_TOTAL_BYTES: u64 = 64 * 1024 * 1024;

/// Whether this host has a verified `openat` flag layout.
///
/// The values are not generic across the architectures this product ships. The
/// OpenHarmony ARM-family and x86_64 userspace headers disagree:
///
/// * `aarch64-linux-ohos/bits/fcntl.h` and `arm-linux-ohos/bits/fcntl.h`
///   define `O_DIRECTORY 040000` and `O_NOFOLLOW 0100000`;
/// * `x86_64-linux-ohos/bits/fcntl.h` defines `O_DIRECTORY 0200000` and
///   `O_NOFOLLOW 0400000`.
///
/// Both keep `O_NONBLOCK 04000` and `O_CLOEXEC 02000000`, and both `fcntl.h`
/// files reach `bits/fcntl.h` through one `#include`.
///
/// Only a target whose userspace header was actually read is accepted. The
/// adapter builds for `aarch64-unknown-linux-ohos` and
/// `x86_64-unknown-linux-ohos`, both verified, and `armv7-unknown-linux-ohos`
/// inherits the same verified ARM header. `i686-linux-ohos` has no userspace
/// `bits/fcntl.h` in this SDK, and every non-OpenHarmony target is unverified,
/// so both are refused: an unverified constant must stop the session, never
/// silently weaken it.
///
/// OpenHarmony is identified by `target_env`, not by `target_os`. In the pinned
/// compiler `base::linux_ohos::opts()` sets `env: Env::Ohos` but inherits
/// `os: Os::Linux` from `base::linux::opts()`, so every `*-unknown-linux-ohos`
/// target reports `target_os = "linux"` with `target_env = "ohos"`. Checking
/// `target_os = "ohos"` would match nothing.
const fn host_supported() -> bool {
    cfg!(all(target_os = "linux", target_env = "ohos"))
        && cfg!(any(
            target_arch = "aarch64",
            target_arch = "arm",
            target_arch = "x86_64",
        ))
}

// An OpenHarmony architecture with no verified userspace header is a build-time
// refusal, not a runtime one: the flag constants below would be undefined, and
// guessing them is exactly what this module must never do.
#[cfg(all(
    target_env = "ohos",
    not(any(target_arch = "aarch64", target_arch = "arm", target_arch = "x86_64")),
))]
compile_error!("this OpenHarmony architecture has no verified `openat` flag layout");

/// A denial or limit failure the adapter reports as an explicit boundary
/// failure instead of a user-source verdict.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BoundaryFailure {
    pub reason: &'static str,
    pub path: Option<PathBuf>,
    /// Underlying OS error text, when the failure came from a syscall.
    pub detail: Option<String>,
}

impl BoundaryFailure {
    fn new(reason: &'static str, path: Option<&Path>) -> Self {
        Self { reason, path: path.map(Path::to_path_buf), detail: None }
    }
}

impl std::fmt::Display for BoundaryFailure {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(formatter, "{}", self.reason)?;
        match &self.path {
            Some(path) => write!(formatter, ": {}", path.display())?,
            None => {}
        }
        if let Some(detail) = &self.detail {
            write!(formatter, " ({detail})")?;
        }
        Ok(())
    }
}

/// A policy denial. Always `PermissionDenied`, which is also the marker the
/// traversal uses to tell a policy refusal from an ordinary OS error.
fn denied(reason: &'static str) -> io::Error {
    io::Error::new(io::ErrorKind::PermissionDenied, reason)
}

/// Stops the session through the channel the adapter already catches with
/// `rustc_driver::catch_fatal_errors`.
fn fail_closed() -> ! {
    FatalError.raise()
}

/// One authorized read root, pinned by an open descriptor so a later rename of
/// the root path cannot redirect a read.
struct RootHandle {
    /// Canonical path of the root.
    path: PathBuf,
    #[cfg(target_env = "ohos")]
    directory: File,
}

impl RootHandle {
    fn open(path: &Path) -> io::Result<Self> {
        if !path.is_absolute() {
            return Err(denied("compiler read root must be absolute"));
        }
        // The root is chosen by the application, never by guest input, so this
        // single canonicalizing resolve is the only symlink that is followed.
        let path = path.canonicalize()?;
        if !path.is_dir() {
            return Err(denied("compiler read root is not a directory"));
        }
        #[cfg(target_env = "ohos")]
        {
            let directory = OpenOptions::new()
                .read(true)
                .custom_flags(O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
                .open(&path)?;
            Ok(Self { path, directory })
        }
        #[cfg(not(target_env = "ohos"))]
        {
            let _ = path;
            Err(denied("descriptor-relative traversal is unavailable on this host"))
        }
    }

    /// Fresh descriptor for the pinned root directory.
    #[cfg(target_env = "ohos")]
    fn clone_directory(&self) -> io::Result<File> {
        self.directory.try_clone()
    }
}

/// Per-session state: authorized roots, byte budget and the first failure.
///
/// A root is `None` only when it could not be pinned. That case always records
/// a failure, and `install` then stops the compiler before traversal can run.
pub struct CompilerBoundary {
    /// Canonical project path, also the session working directory. Kept even
    /// when the descriptor could not be pinned, so reporting stays specific.
    project_path: PathBuf,
    project: Option<RootHandle>,
    sysroot: Option<RootHandle>,
    consumed: Mutex<u64>,
    /// Separate from `consumed` so recording never contends with accounting.
    failure: Mutex<Option<BoundaryFailure>>,
    reads: AtomicU64,
}

impl CompilerBoundary {
    /// Boundary for an ordinary run session. `project` is the explicit project
    /// root when the caller supplied one, otherwise the entry source's parent.
    ///
    /// Never returns a skip: a root that cannot be opened is recorded as a
    /// failure and `install` then stops the compiler.
    pub fn for_run(project: Option<&Path>, source: &str, sysroot: &str) -> Arc<Self> {
        let project: PathBuf = match project {
            Some(root) => root.to_path_buf(),
            None => match Path::new(source).parent() {
                Some(parent) => parent.to_path_buf(),
                None => return Self::rejected("source path has no parent directory"),
            },
        };
        Self::open(&project, Path::new(sysroot))
    }

    /// Boundary for an analysis session. ABI 1 has no explicit project root for
    /// analysis, so the entry source's parent — the immutable mirror — is the
    /// only correct choice.
    pub fn for_analysis(source: &str, sysroot: &str) -> Arc<Self> {
        match Path::new(source).parent() {
            Some(project) => Self::open(project, Path::new(sysroot)),
            None => Self::rejected("analysis source path has no parent directory"),
        }
    }

    /// A boundary that can never be installed; always records a failure.
    fn rejected(reason: &'static str) -> Arc<Self> {
        Arc::new(Self {
            project_path: PathBuf::new(),
            project: None,
            sysroot: None,
            consumed: Mutex::new(0),
            failure: Mutex::new(Some(BoundaryFailure::new(reason, None))),
            reads: AtomicU64::new(0),
        })
    }

    fn open(project: &Path, sysroot: &Path) -> Arc<Self> {
        let project_root = RootHandle::open(project);
        let sysroot_root = RootHandle::open(sysroot);

        let failure = match (&project_root, &sysroot_root) {
            (Err(error), _) => Some(annotate(
                BoundaryFailure::new("compiler project read root cannot be opened", Some(project)),
                error,
            )),
            (_, Err(error)) => Some(annotate(
                BoundaryFailure::new("compiler sysroot read root cannot be opened", Some(sysroot)),
                error,
            )),
            _ => None,
        };

        let project_path = project_root
            .as_ref()
            .map(|root| root.path.clone())
            .unwrap_or_else(|_| project.to_path_buf());

        Arc::new(Self {
            project_path,
            project: project_root.ok(),
            sysroot: sysroot_root.ok(),
            consumed: Mutex::new(0),
            failure: Mutex::new(failure),
            reads: AtomicU64::new(0),
        })
    }

    /// The first boundary failure, for adapter-level reporting.
    pub fn failure(&self) -> Option<BoundaryFailure> {
        self.failure.lock().ok().and_then(|failure| failure.clone())
    }

    /// Source bytes this session has read so far.
    pub fn consumed_bytes(&self) -> u64 {
        self.consumed.lock().map(|consumed| *consumed).unwrap_or(0)
    }

    /// Session working directory. Never the host process cwd.
    fn working_directory(&self) -> PathBuf {
        self.project_path.clone()
    }

    fn record(&self, failure: BoundaryFailure) -> BoundaryFailure {
        if let Ok(mut slot) = self.failure.lock() {
            if slot.is_none() {
                *slot = Some(failure.clone());
            }
        }
        failure
    }

    fn deny(&self, reason: &'static str, path: Option<&Path>) -> io::Error {
        self.record(BoundaryFailure::new(reason, path));
        denied(reason)
    }

    fn charge(&self, bytes: u64) -> io::Result<()> {
        let mut consumed = self
            .consumed
            .lock()
            .map_err(|_| denied("compiler boundary accounting lock poisoned"))?;
        let next = consumed
            .checked_add(bytes)
            .ok_or_else(|| denied("compiler boundary byte accounting overflow"))?;
        if next > MAX_TOTAL_BYTES {
            return Err(self.deny("session source read limit reached", None));
        }
        *consumed = next;
        Ok(())
    }

    /// Installs the boundary into a session configuration.
    ///
    /// Call from `Callbacks::config`, before the session exists. Every path
    /// that cannot be confined stops the compiler here; none of them leaves the
    /// session running against the unrestricted default loader.
    pub fn install(self: &Arc<Self>, config: &mut Config) {
        // A boundary that could not establish its roots must not silently skip
        // installation: without this the session would run with
        // `RealFileLoader`, no flag and no confinement.
        if self.failure().is_some() {
            self.ensure_refusal(config);
            fail_closed();
        }
        if !host_supported() {
            self.record(BoundaryFailure::new("compiler boundary unsupported on this host", None));
            self.ensure_refusal(config);
            fail_closed();
        }
        // `file_path_mapping` resolves `-Zremap-cwd-prefix` against the host
        // process cwd. The embedded surface never sets it, so a value here means
        // the argument surface changed.
        if config.opts.unstable_opts.remap_cwd_prefix.is_some() {
            self.record(BoundaryFailure::new(
                "embedded compiler sessions do not remap a host working directory",
                None,
            ));
            self.ensure_refusal(config);
            fail_closed();
        }
        // These sessions never pass `--extern`, so a non-empty map means a
        // caller changed the argument surface; stop before a crate is loaded.
        if config.opts.externs.iter().next().is_some() {
            self.record(BoundaryFailure::new(
                "embedded compiler sessions do not load external crates",
                None,
            ));
            self.ensure_refusal(config);
            fail_closed();
        }
        // Library search paths are not inspected here: the adapter argument
        // surface never contains `-L`, and a proc-macro crate root reached by
        // any route is refused by the patched `register_crate` before `dlsym`.
        config.opts.embedded_boundary = true;
        config.file_loader = Some(Box::new(Loader { boundary: Arc::clone(self) }));
    }

    /// Marks the configuration as an embedded, confined session on a refusal
    /// path.
    ///
    /// The patched switch also makes the compiler refuse a session with no
    /// loader, so setting both here keeps the refusal double-sided: even if a
    /// caller swallowed the fatal error, the session could not start
    /// unrestricted. The loader can only deny, so installing it is safe.
    fn ensure_refusal(self: &Arc<Self>, config: &mut Config) {
        config.opts.embedded_boundary = true;
        if config.file_loader.is_none() {
            config.file_loader = Some(Box::new(Loader { boundary: Arc::clone(self) }));
        }
    }

    /// Resolves `path` to a root and a lexically normalized relative path.
    ///
    /// Normalization is lexical on purpose: `canonicalize` would follow the very
    /// symlink the traversal has to reject. No failure is recorded here, so an
    /// existence probe can answer "no" without poisoning the session.
    fn locate(&self, path: &Path) -> io::Result<(&RootHandle, PathBuf)> {
        let absolute =
            if path.is_absolute() { path.to_path_buf() } else { self.project_path.join(path) };
        for root in [self.project.as_ref(), self.sysroot.as_ref()].into_iter().flatten() {
            if let Ok(relative) = absolute.strip_prefix(&root.path) {
                return Ok((root, normalize(relative)?));
            }
        }
        Err(denied("path is outside the compiler read roots"))
    }

    /// Reads one authorized file under the per-file and total byte budgets.
    #[cfg(target_env = "ohos")]
    fn read(&self, path: &Path) -> io::Result<Vec<u8>> {
        let (root, relative) = self
            .locate(path)
            .map_err(|_| self.deny("path is outside the compiler read roots", Some(path)))?;
        let file = self.walk(root, &relative, true)?;
        let remaining = self
            .consumed
            .lock()
            .map(|consumed| MAX_TOTAL_BYTES.saturating_sub(*consumed))
            .map_err(|_| self.deny("compiler boundary accounting lock poisoned", Some(path)))?;
        let bound = remaining.min(MAX_FILE_BYTES);
        if bound == 0 {
            return Err(self.deny("session source read limit reached", Some(path)));
        }
        // At most one byte past the bound proves growth without trusting the
        // metadata length that was observed earlier.
        let mut bytes = Vec::new();
        file.take(bound + 1)
            .read_to_end(&mut bytes)
            .map_err(|_| self.deny("source file cannot be read", Some(path)))?;
        if bytes.len() as u64 > bound {
            return Err(self.deny("source read limit reached", Some(path)));
        }
        self.charge(bytes.len() as u64)?;
        self.reads.fetch_add(1, Ordering::Relaxed);
        Ok(bytes)
    }

    #[cfg(not(target_env = "ohos"))]
    fn read(&self, path: &Path) -> io::Result<Vec<u8>> {
        Err(self.deny("descriptor-relative reads are unavailable on this host", Some(path)))
    }

    /// `file_exists` through the same policy, without charging the byte budget
    /// and without recording a failure when the answer is simply "no".
    #[cfg(target_env = "ohos")]
    fn exists(&self, path: &Path) -> bool {
        let Ok((root, relative)) = self.locate(path) else { return false };
        self.walk(root, &relative, false).is_ok()
    }

    #[cfg(not(target_env = "ohos"))]
    fn exists(&self, _path: &Path) -> bool {
        false
    }

    /// Walks `relative` from the pinned root descriptor, one `openat` per
    /// component, and returns the opened regular file.
    ///
    /// `report` is false for existence probes. A `NotFound` is never recorded:
    /// it is the ordinary answer to "does this optional file exist", not a
    /// boundary violation.
    #[cfg(target_env = "ohos")]
    fn walk(&self, root: &RootHandle, relative: &Path, report: bool) -> io::Result<File> {
        let mut directory = root.clone_directory()?;
        let mut components = relative.components().peekable();
        while let Some(component) = components.next() {
            let Component::Normal(name) = component else {
                return Err(self.fail(report, "source path is not a plain relative path", Some(relative)));
            };
            if components.peek().is_some() {
                directory = self.open_component_directory(&directory, name, relative, report)?;
            } else {
                return self.open_component_file(&directory, name, relative, report);
            }
        }
        Err(self.fail(report, "source path resolves to a directory", Some(relative)))
    }

    /// Records a policy denial, unless `report` is false or the entry is simply
    /// missing.
    fn fail(&self, report: bool, reason: &'static str, path: Option<&Path>) -> io::Error {
        if report {
            self.record(BoundaryFailure::new(reason, path));
        }
        denied(reason)
    }

    /// Classifies a failed `openat`: a missing entry stays an ordinary OS error
    /// so rustc reports its normal "file not found" diagnostic, while a symlink,
    /// wrong type or denied path is recorded as a boundary failure.
    fn classify(&self, report: bool, error: io::Error, reason: &'static str, path: &Path) -> io::Error {
        if error.kind() == io::ErrorKind::NotFound {
            return error;
        }
        if report {
            let mut failure = BoundaryFailure::new(reason, Some(path));
            failure.detail = Some(error.to_string());
            self.record(failure);
        }
        denied(reason)
    }

    #[cfg(target_env = "ohos")]
    fn open_component_directory(
        &self,
        parent: &File,
        name: &OsStr,
        relative: &Path,
        report: bool,
    ) -> io::Result<File> {
        // `O_DIRECTORY` makes a non-directory fail with ENOTDIR and
        // `O_NOFOLLOW` makes a symlink fail with ELOOP, so a swapped entry is
        // refused by the kernel instead of by a preceding metadata lookup.
        let directory = descriptor::open(parent, name, O_DIRECTORY | O_NOFOLLOW)
            .map_err(|error| self.classify(report, error, "source path component is not a directory", relative))?;
        // Re-check the opened descriptor. `O_DIRECTORY` is the primary guard;
        // this makes a wrong constant value visible instead of silent.
        let metadata = directory.metadata().map_err(|error| {
            self.classify(report, error, "source directory metadata is unavailable", relative)
        })?;
        if !metadata.is_dir() {
            return Err(self.fail(report, "source path component is not a directory", Some(relative)));
        }
        Ok(directory)
    }

    #[cfg(target_env = "ohos")]
    fn open_component_file(
        &self,
        parent: &File,
        name: &OsStr,
        relative: &Path,
        report: bool,
    ) -> io::Result<File> {
        // `O_NONBLOCK` keeps a FIFO from blocking the open; the descriptor is
        // then classified and refused below.
        let file = descriptor::open(parent, name, O_NOFOLLOW | O_NONBLOCK)
            .map_err(|error| self.classify(report, error, "source file cannot be opened", relative))?;
        let metadata = file.metadata().map_err(|error| {
            self.classify(report, error, "source file metadata is unavailable", relative)
        })?;
        // Rejects FIFO, socket and device entries after a non-blocking open,
        // without ever re-deriving a host path.
        if !metadata.is_file() {
            return Err(self.fail(report, "source entry is not a regular file", Some(relative)));
        }
        if metadata.len() > MAX_FILE_BYTES {
            return Err(self.fail(report, "source file exceeds the read limit", Some(relative)));
        }
        Ok(file)
    }
}

/// Attaches the underlying OS error text to a root failure.
fn annotate(mut failure: BoundaryFailure, error: &io::Error) -> BoundaryFailure {
    failure.detail = Some(error.to_string());
    failure
}

/// Lexical normalization: rejects any `..` that would leave the root.
fn normalize(relative: &Path) -> io::Result<PathBuf> {
    let mut normalized = PathBuf::new();
    for component in relative.components() {
        match component {
            Component::Normal(name) => normalized.push(name),
            Component::CurDir => {}
            Component::ParentDir => {
                if !normalized.pop() {
                    return Err(denied("source path escapes its read root"));
                }
            }
            Component::RootDir | Component::Prefix(_) => {
                return Err(denied("source path is not relative to its read root"));
            }
        }
    }
    Ok(normalized)
}

/// Genuine `openat(2)` on a directory descriptor.
///
/// A `/proc/self/fd/N` path is not used: that re-derives a host path and then
/// reopens it, which is both slower and weaker than an `openat` on the same
/// descriptor.
#[cfg(target_env = "ohos")]
mod descriptor {
    use std::ffi::{CString, OsStr};
    use std::fs::File;
    use std::io;
    use std::os::fd::{AsRawFd, FromRawFd};
    use std::os::raw::{c_char, c_int};
    use std::os::unix::ffi::OsStrExt;

    // Declared here because this crate depends only on `miri`, so the `libc`
    // crate is unavailable, and `std` exposes `custom_flags` without the values.
    //
    // Verified against the pinned OpenHarmony SDK userspace headers, which the
    // integration report records with their sizes and SHA-256 digests. The
    // layout is architecture-specific, so the values are too. An architecture
    // with no verified header is refused by `host_supported` and by a
    // `compile_error!`, so no unverified constant can be compiled.

    /// `O_NONBLOCK` and `O_CLOEXEC` agree across every shipped architecture.
    pub(super) const O_NONBLOCK: c_int = 0o4000;
    pub(super) const O_CLOEXEC: c_int = 0o2000000;

    // ARM family: `aarch64-linux-ohos/bits/fcntl.h:10-11` and
    // `arm-linux-ohos/bits/fcntl.h:10-11`.
    #[cfg(any(target_arch = "aarch64", target_arch = "arm"))]
    pub(super) const O_DIRECTORY: c_int = 0o40000;
    #[cfg(any(target_arch = "aarch64", target_arch = "arm"))]
    pub(super) const O_NOFOLLOW: c_int = 0o100000;

    // x86_64: `x86_64-linux-ohos/bits/fcntl.h:10-11`.
    #[cfg(target_arch = "x86_64")]
    pub(super) const O_DIRECTORY: c_int = 0o200000;
    #[cfg(target_arch = "x86_64")]
    pub(super) const O_NOFOLLOW: c_int = 0o400000;

    unsafe extern "C" {
        /// POSIX `openat`. `mode` is variadic and is never supplied because
        /// `O_CREAT` and `O_TMPFILE` are never set.
        fn openat(directory: c_int, path: *const c_char, flags: c_int, ...) -> c_int;
    }

    pub(super) fn open(parent: &File, name: &OsStr, flags: c_int) -> io::Result<File> {
        let bytes = name.as_bytes();
        if bytes.is_empty() {
            return Err(io::Error::new(io::ErrorKind::InvalidInput, "empty path component"));
        }
        // A component must never carry a separator: the kernel would then walk
        // a path this traversal did not chdir-check.
        if bytes.contains(&b'/') {
            return Err(io::Error::new(io::ErrorKind::InvalidInput, "path component contains a separator"));
        }
        let name = CString::new(bytes)
            .map_err(|_| io::Error::new(io::ErrorKind::InvalidInput, "path component contains NUL"))?;
        // SAFETY: `parent` is an open directory descriptor, `name` is a valid
        // NUL-terminated string, and no variadic argument is required because
        // the flag set never contains `O_CREAT` or `O_TMPFILE`.
        let descriptor = unsafe { openat(parent.as_raw_fd(), name.as_ptr(), flags | O_CLOEXEC) };
        if descriptor < 0 {
            return Err(io::Error::last_os_error());
        }
        // SAFETY: a successful `openat` returns a descriptor this call owns.
        Ok(unsafe { File::from_raw_fd(descriptor) })
    }
}

#[cfg(target_env = "ohos")]
use std::ffi::OsStr;
#[cfg(target_env = "ohos")]
use std::fs::{File, OpenOptions};
#[cfg(target_env = "ohos")]
use std::io::Read;
#[cfg(target_env = "ohos")]
use std::os::unix::fs::OpenOptionsExt;

#[cfg(target_env = "ohos")]
use descriptor::{O_CLOEXEC, O_DIRECTORY, O_NOFOLLOW, O_NONBLOCK};

/// The `FileLoader` rustc uses for every source read in this session.
struct Loader {
    boundary: Arc<CompilerBoundary>,
}

impl FileLoader for Loader {
    fn file_exists(&self, path: &Path) -> bool {
        self.boundary.exists(path)
    }

    fn read_file(&self, path: &Path) -> io::Result<String> {
        let bytes = self.boundary.read(path)?;
        // Text reads decode strictly. The patched parser retry reads the same
        // bytes through `read_binary_file`, so an authorized invalid-UTF-8 file
        // keeps its precise diagnostic without a second raw host read.
        //
        // A decode rejection is a user encoding error, not a boundary violation.
        // `new_parser_from_file` reports it as "couldn't read `<path>`", then
        // retries through `read_binary_for_diagnostic` so `utf8_error` can emit
        // the exact "invalid utf-8 at byte N" diagnostic. Recording it as a
        // policy failure would convert that diagnostic into INTERNAL_ERROR, so
        // this returns `InvalidData` and leaves the sticky failure untouched.
        // The read itself already recorded any real policy denial.
        String::from_utf8(bytes)
            .map_err(|_| io::Error::new(io::ErrorKind::InvalidData, "source file is not valid UTF-8"))
    }

    fn read_binary_file(&self, path: &Path) -> io::Result<Arc<[u8]>> {
        // Bytes are preserved exactly: no BOM removal and no lossy decoding, so
        // `include_bytes!` sees the real authorized file contents.
        Ok(Arc::from(self.boundary.read(path)?))
    }

    fn current_directory(&self) -> io::Result<PathBuf> {
        // `SourceMap::with_inputs` takes its working directory from here, and
        // never falls back to the host process cwd.
        Ok(self.boundary.working_directory())
    }
}