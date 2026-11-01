#![feature(rustc_private)]

extern crate anstream;
extern crate rustc_ast;
extern crate rustc_codegen_ssa;
extern crate rustc_errors;
extern crate rustc_driver;
extern crate rustc_interface;
extern crate rustc_middle;
extern crate rustc_session;
extern crate rustc_span;

mod debug;
mod compiler_boundary;

use std::ffi::{CStr, c_char};
use std::io::{self, Read, Write};
use std::panic::{AssertUnwindSafe, catch_unwind};
use std::path::{Path, PathBuf};
use std::ptr;
use std::sync::atomic::{AtomicBool, AtomicU32, AtomicU64, Ordering};
use std::sync::{Arc, Mutex, MutexGuard};
use std::time::{Duration, Instant};

use miri::{EmbeddedFileSystem, EmbeddedSession, MiriConfig};
use compiler_boundary::CompilerBoundary;
use rustc_codegen_ssa::traits::CodegenBackend;
use rustc_driver::Compilation;
use rustc_errors::annotate_snippet_emitter_writer::AnnotateSnippetEmitter;
use rustc_errors::emitter::{ColorConfig, Destination, HumanReadableErrorType};
use rustc_errors::json::JsonEmitter;
use rustc_interface::util::DummyCodegenBackend;
use rustc_middle::ty::TyCtxt;
use rustc_session::{EarlyDiagCtxt, Session};

const ABI_VERSION: u32 = 1;
const READY: u32 = 0;
const RUNNING: u32 = 1;
const FINISHED: u32 = 2;
const CANCELLED: u32 = 3;
const LIMIT_REACHED: u32 = 4;
const INTERNAL_ERROR: u32 = 5;
// Analysis-only: the `qfli_miri_analyze` *return code* for "another run/analyze
// holds the compiler". Deliberately never written to `QfliResult.state`, which
// carries session status only; a transient call outcome must not overwrite it.
const BUSY_RETURN: i32 = 2;
const MAX_INPUT: usize = 16 * 1024 * 1024;
const MAX_CRATE_NAME: usize = 64;
static COMPILER_LOCK: Mutex<()> = Mutex::new(());
static COMPILER_BACKEND: Mutex<Option<BackendIdentity>> = Mutex::new(None);

#[derive(PartialEq, Eq)]
enum BackendIdentity {
    Default,
    DefaultSysroot(PathBuf),
    External(PathBuf),
}

#[repr(C)]
pub struct QfliConfig {
    abi_version: u32,
    source_path: *const c_char,
    sysroot_path: *const c_char,
    stdin_data: *const u8,
    stdin_len: usize,
    max_basic_blocks: u64,
    timeout_ms: u64,
    max_output_bytes: usize,
    max_guest_memory_bytes: u64,
}

/// Additive ABI-1 analysis configuration. `QfliConfig` is unchanged.
#[repr(C)]
pub struct QfliAnalysisConfig {
    abi_version: u32,
    source_path: *const c_char,
    sysroot_path: *const c_char,
    crate_name: *const c_char,
    edition: u32,
    crate_type: u32,
    timeout_ms: u64,
    max_output_bytes: usize,
}

#[repr(C)]
pub struct QfliResult {
    state: u32,
    exit_code: i32,
    basic_blocks: u64,
    peak_guest_memory_bytes: u64,
}

pub struct QfliSession {
    source: String,
    sysroot: String,
    backend_path: Option<String>,
    io: Arc<SessionIo>,
    result: Mutex<QfliResult>,
    started: AtomicBool,
    /// Owner count plus a destroy latch, in one word so `begin` and `destroy`
    /// cannot interleave into a use-after-free.
    ///
    /// Bits 0..=30 count in-flight `run`/`analyze` calls; bit 31 is set by
    /// `destroy` before it stops accepting new calls. `begin` fails atomically
    /// once the latch is set, so a call can never start on a session that
    /// `destroy` is already tearing down.
    owners: AtomicU32,
    /// `Some` only for sessions created by `qfli_miri_create_analysis`.
    analysis: Option<AnalysisOptions>,
}

/// Bit 31 of `QfliSession::owners`. See the field docs.
const DESTROYED: u32 = 1 << 31;

/// Analysis-only compilation options. Session-scoped so concurrent analysis
/// sessions cannot observe each other's crate name/edition/crate type.
struct AnalysisOptions {
    crate_name: String,
    edition: u32,
    crate_type: u32,
}

#[derive(Debug)]
struct SessionIo {
    filesystem: Option<EmbeddedFileSystem>,
    stdin: Mutex<io::Cursor<Vec<u8>>>,
    output: Mutex<[Vec<u8>; 3]>,
    cancelled: AtomicBool,
    stopped: AtomicU32,
    stop_reason: Mutex<Option<&'static str>>,
    blocks: AtomicU64,
    memory: AtomicU64,
    peak_memory: AtomicU64,
    start: Mutex<Option<Instant>>,
    /// `None` when this session kind has no block budget at all (analysis).
    /// Expressed as absence rather than a sentinel so a future `check_stop`
    /// cannot silently turn "no limit" into "limit reached".
    max_blocks: Option<u64>,
    timeout: Duration,
    max_output: usize,
    /// See `max_blocks`: `None` means guest memory is not bounded (analysis).
    max_memory: Option<u64>,
}

fn lock<T>(mutex: &Mutex<T>) -> MutexGuard<'_, T> {
    mutex.lock().unwrap_or_else(|poison| poison.into_inner())
}

fn ffi_guard<T>(fallback: T, call: impl FnOnce() -> T) -> T {
    catch_unwind(AssertUnwindSafe(call)).unwrap_or(fallback)
}

impl SessionIo {
    fn stop(&self, state: u32, reason: &'static str) {
        if self.stopped.compare_exchange(0, state, Ordering::AcqRel, Ordering::Acquire).is_ok() {
            *lock(&self.stop_reason) = Some(reason);
        }
    }

    fn append(&self, channel: usize, bytes: &[u8]) -> io::Result<usize> {
        let mut outputs = lock(&self.output);
        // Combined budget across all channels, exactly as the run path has
        // always accounted for it. Only the subtraction is defensive:
        // `max_output` is validated >= 1024, but this must never underflow.
        let total: usize = outputs.iter().map(Vec::len).sum();
        let bound = if channel == 2 {
            self.max_output
        } else {
            self.max_output.saturating_sub(512)
        };
        let available = bound.saturating_sub(total);
        outputs[channel].extend_from_slice(&bytes[..bytes.len().min(available)]);
        if bytes.len() > available {
            self.stop(LIMIT_REACHED, "session output limit reached");
            return Err(io::Error::other("session output limit reached"));
        }
        Ok(bytes.len())
    }

    fn check_stop(&self) -> bool {
        if self.cancelled.load(Ordering::Acquire) {
            self.stop(CANCELLED, "session cancelled");
            return true;
        }
        if self
            .max_blocks
            .is_some_and(|max_blocks| self.blocks.load(Ordering::Relaxed) >= max_blocks)
        {
            self.stop(LIMIT_REACHED, "session basic block limit reached");
        }
        if lock(&self.start).is_some_and(|start| start.elapsed() >= self.timeout) {
            self.stop(LIMIT_REACHED, "session time limit reached");
        }
        self.stopped.load(Ordering::Acquire) != 0
    }
}

impl EmbeddedSession for SessionIo {
    fn filesystem(&self) -> Option<&EmbeddedFileSystem> {
        self.filesystem.as_ref()
    }

    fn system_time(&self) -> Option<std::time::SystemTime> {
        self.filesystem.as_ref().map(|_| std::time::SystemTime::now())
    }

    fn read_stdin(&self, buffer: &mut [u8]) -> io::Result<usize> {
        lock(&self.stdin).read(buffer)
    }

    fn write_output(&self, stderr: bool, buffer: &[u8]) -> io::Result<usize> {
        self.append(usize::from(stderr), buffer)
    }

    fn before_basic_block(&self) -> bool {
        if self.check_stop() {
            return false;
        }
        self.blocks.fetch_add(1, Ordering::Relaxed);
        true
    }

    fn reserve_memory(&self, bytes: usize) -> bool {
        if self.check_stop() { return false; }
        let Some(max_memory) = self.max_memory else {
            // Unbounded session kind (analysis): account only, never refuse.
            let bytes = bytes as u64;
            let previous = self.memory.fetch_add(bytes, Ordering::AcqRel);
            self.peak_memory.fetch_max(previous + bytes, Ordering::Relaxed);
            return true;
        };
        let bytes = bytes as u64;
        let reserved = self.memory.fetch_update(Ordering::AcqRel, Ordering::Acquire, |used| {
            used.checked_add(bytes).filter(|&next| next <= max_memory)
        });
        match reserved {
            Ok(previous) => {
                self.peak_memory.fetch_max(previous + bytes, Ordering::Relaxed);
                true
            }
            Err(_) => {
                self.stop(LIMIT_REACHED, "session guest memory limit reached");
                false
            }
        }
    }

    fn release_memory(&self, bytes: usize) {
        self.memory.fetch_sub(bytes as u64, Ordering::AcqRel);
    }
}

struct DiagnosticWriter(Arc<SessionIo>);

impl Write for DiagnosticWriter {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        // Preserve bounded diagnostics without provoking a rustc emitter I/O panic.
        let _ = self.0.append(2, bytes);
        Ok(bytes.len())
    }

    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

struct CompilerCallbacks {
    io: Arc<SessionIo>,
    backend_path: Option<String>,
    exit_code: i32,
    interpreted: bool,
    /// Shared compiler read boundary. Never optional: a boundary that could not
    /// be established stops the session inside `install`.
    boundary: Arc<CompilerBoundary>,
}

fn make_backend(sess: &Session, backend_path: Option<&str>, io: &SessionIo) -> Box<dyn CodegenBackend> {
    let early_dcx = EarlyDiagCtxt::new(sess.opts.error_format);
    // rustc loads the backend before psess_created installs our diagnostic emitter.
    let backend = catch_unwind(AssertUnwindSafe(|| {
        let backend = rustc_interface::util::get_codegen_backend(
            &early_dcx, &sess.opts.sysroot, backend_path, &sess.target,
        );
        backend.init(sess);
        backend
    })).unwrap_or_else(|error| {
        let name = backend_path.unwrap_or("compiler default");
        let _ = io.append(2, format!("failed to initialize native codegen backend: {name}\n").as_bytes());
        std::panic::resume_unwind(error)
    });
    Box::new(DummyCodegenBackend {
        target_config_override: Some(Box::new(move |sess| {
            let mut config = backend.target_config(sess);
            config.has_reliable_f16 = true;
            config.has_reliable_f128 = true;
            config.has_reliable_f16_math = false;
            config.has_reliable_f128_math = false;
            config
        })),
    })
}

impl rustc_driver::Callbacks for CompilerCallbacks {
    fn config(&mut self, config: &mut rustc_interface::interface::Config) {
        let backend_path = self.backend_path.clone();
        let backend_io = self.io.clone();
        config.make_codegen_backend = Some(Box::new(move |sess| {
            make_backend(sess, backend_path.as_deref(), &backend_io)
        }));
        config.extra_symbols = miri::sym::EXTRA_SYMBOLS.into();
        // Apply the pinned upstream MIRI_DEFAULT_ARGS through structured options.
        let opts = &mut config.opts.unstable_opts;
        opts.always_encode_mir = true;
        opts.extra_const_ub_checks = true;
        opts.mir_preserve_ub = true;
        opts.mir_opt_level = Some(0);
        opts.deduplicate_diagnostics = false;
        opts.mir_enable_passes = ["CheckAlignment", "CheckNull", "CheckEnums", "ReferencePropagation", "GVN"]
            .into_iter().map(|name| (name.to_owned(), false)).collect();
        config.crate_cfg.push("miri".into());
        // Unconditional: `install` fails closed when the boundary is not usable.
        self.boundary.install(config);
        let io = self.io.clone();
        config.psess_created = Some(Box::new(move |psess| {
            let writer: Box<dyn Write + Send> = Box::new(DiagnosticWriter(io));
            let destination = Destination::new(writer, anstream::ColorChoice::Never);
            let emitter = AnnotateSnippetEmitter::new(destination)
                .sm(Some(psess.clone_source_map()));
            psess.dcx().set_emitter(Box::new(emitter));
        }));
    }

    fn after_crate_root_parsing(
        &mut self,
        _: &rustc_interface::interface::Compiler,
        _: &mut rustc_ast::Crate,
    ) -> Compilation {
        if self.io.check_stop() { Compilation::Stop } else { Compilation::Continue }
    }

    fn after_expansion<'tcx>(
        &mut self,
        _: &rustc_interface::interface::Compiler,
        _: TyCtxt<'tcx>,
    ) -> Compilation {
        if self.io.check_stop() { Compilation::Stop } else { Compilation::Continue }
    }

    fn after_analysis<'tcx>(
        &mut self,
        _: &rustc_interface::interface::Compiler,
        tcx: TyCtxt<'tcx>,
    ) -> Compilation {
        tcx.dcx().emit_stashed_diagnostics();
        tcx.dcx().abort_if_errors();
        tcx.dcx().flush_delayed();
        if self.io.check_stop() {
            return Compilation::Stop;
        }
        let (entry_id, entry_type) = miri::entry_fn(tcx);
        let config = MiriConfig {
            args: vec![tcx.sess.io.input.filestem().to_string()],
            embedded_session: Some(self.io.clone()),
            short_fd_operations: false,
            // Safe Rust may intentionally retain allocations (for example Box::leak).
            // The session still enforces its live guest-memory limit.
            ignore_leaks: true,
            ..MiriConfig::default()
        };
        self.interpreted = true;
        self.exit_code = miri::eval_entry(tcx, entry_id, entry_type, &config, None)
            .err().map_or(0, |code| code.get());
        Compilation::Stop
    }
}

#[unsafe(no_mangle)]
pub extern "C" fn qfli_miri_abi_version() -> u32 {
    ABI_VERSION
}

unsafe fn path_string(value: *const c_char) -> Option<String> {
    if value.is_null() {
        return None;
    }
    let path = unsafe { CStr::from_ptr(value) }.to_str().ok()?;
    if path.is_empty() || !Path::new(path).is_absolute() {
        return None;
    }
    Some(path.to_owned())
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn qfli_miri_create(config: *const QfliConfig) -> *mut QfliSession {
    ffi_guard(ptr::null_mut(), || unsafe { create_session(config, ptr::null(), ptr::null()) })
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn qfli_miri_create_with_backend(
    config: *const QfliConfig, backend_path: *const c_char,
) -> *mut QfliSession {
    ffi_guard(ptr::null_mut(), || unsafe { create_session(config, backend_path, ptr::null()) })
}

/// Additive ABI-1 entry: project-relative guest I/O uses this explicit root.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn qfli_miri_create_with_project(
    config: *const QfliConfig, backend_path: *const c_char, project_root: *const c_char,
) -> *mut QfliSession {
    if project_root.is_null() { return ptr::null_mut(); }
    ffi_guard(ptr::null_mut(), || unsafe { create_session(config, backend_path, project_root) })
}

fn external_backend(path: &Path) -> Option<(Option<String>, BackendIdentity)> {
    if !path.is_file() { return None; }
    let canonical = path.canonicalize().ok()?;
    // Upstream recognizes an explicit backend filename by the presence of '.'.
    let load_path = canonical.parent()?.join(".").join(canonical.file_name()?);
    let load_path = load_path.to_str()?;
    if !load_path.contains('.') { return None; }
    Some((Some(load_path.to_owned()), BackendIdentity::External(canonical)))
}

fn default_backend(sysroot: &Path) -> Option<(Option<String>, BackendIdentity)> {
    if cfg!(all(target_env = "ohos", target_arch = "x86_64")) {
        let directory = sysroot.join("lib/rustlib")
            .join(rustc_session::config::host_tuple()).join("codegen-backends");
        let names = ["librustc_codegen_cranelift-1.98.1.so", "librustc_codegen_cranelift.so"];
        let mut matches = names.into_iter().map(|name| directory.join(name)).filter(|path| path.is_file());
        let path = matches.next()?;
        if matches.next().is_some() { return None; }
        return external_backend(&path);
    }
    // Mobile source builds may use an external default backend in this sysroot.
    let identity = if cfg!(any(target_os = "android", target_os = "ios")) {
        BackendIdentity::DefaultSysroot(sysroot.canonicalize().ok()?)
    } else {
        BackendIdentity::Default
    };
    Some((None, identity))
}

/// Resolves the codegen backend exactly like `create_session` always has. Shared
/// by the run and analysis paths so both agree on backend identity.
fn resolve_backend(
    backend_path: *const c_char, sysroot: &str,
) -> Option<(Option<String>, BackendIdentity)> {
    if backend_path.is_null() {
        default_backend(Path::new(sysroot))
    } else {
        unsafe { path_string(backend_path) }.and_then(|path| external_backend(Path::new(&path)))
    }
}

/// rustc caches the first backend factory globally, even across destroyed
/// sessions. Returns false when an existing identity conflicts.
fn claim_backend(identity: BackendIdentity) -> bool {
    let mut selected_backend = lock(&COMPILER_BACKEND);
    if let Some(selected) = selected_backend.as_ref() {
        if selected != &identity { return false; }
    } else {
        *selected_backend = Some(identity);
    }
    true
}

fn new_session_io(
    input: Vec<u8>, max_blocks: Option<u64>, timeout_ms: u64, max_output: usize,
    max_memory: Option<u64>,
) -> Arc<SessionIo> {
    new_session_io_with_fs(input, max_blocks, timeout_ms, max_output, max_memory, None)
}

fn new_session_io_with_fs(
    input: Vec<u8>, max_blocks: Option<u64>, timeout_ms: u64, max_output: usize,
    max_memory: Option<u64>, filesystem: Option<EmbeddedFileSystem>,
) -> Arc<SessionIo> {
    Arc::new(SessionIo {
        filesystem,
        stdin: Mutex::new(io::Cursor::new(input)),
        output: Mutex::new([vec![], vec![], vec![]]),
        cancelled: AtomicBool::new(false), stopped: AtomicU32::new(0),
        stop_reason: Mutex::new(None), blocks: AtomicU64::new(0),
        memory: AtomicU64::new(0), peak_memory: AtomicU64::new(0), start: Mutex::new(None),
        max_blocks,
        timeout: Duration::from_millis(timeout_ms),
        max_output,
        max_memory,
    })
}

unsafe fn create_session(
    config: *const QfliConfig, backend_path: *const c_char, project_root: *const c_char,
) -> *mut QfliSession {
    let Some(config) = (unsafe { config.as_ref() }) else { return ptr::null_mut() };
    if config.abi_version != ABI_VERSION || config.stdin_len > MAX_INPUT
        || (config.stdin_len != 0 && config.stdin_data.is_null())
        || config.max_basic_blocks == 0 || config.timeout_ms == 0
        || config.max_output_bytes < 1024 || config.max_output_bytes > MAX_INPUT
        || config.max_guest_memory_bytes == 0
    {
        return ptr::null_mut();
    }
    let Some(source) = (unsafe { path_string(config.source_path) }) else { return ptr::null_mut() };
    let Some(sysroot) = (unsafe { path_string(config.sysroot_path) }) else { return ptr::null_mut() };
    if !Path::new(&source).is_file() || !Path::new(&sysroot).is_dir() {
        return ptr::null_mut();
    }
    let Some(canonical_source) = Path::new(&source).canonicalize().ok() else {
        return ptr::null_mut();
    };
    let root = if project_root.is_null() {
        canonical_source.parent().map(Path::to_path_buf)
    } else {
        unsafe { path_string(project_root) }.and_then(|root| Path::new(&root).canonicalize().ok())
    };
    let Some(root) = root.filter(|root| root.is_dir() && canonical_source.starts_with(root)) else {
        return ptr::null_mut();
    };
    let filesystem = match EmbeddedFileSystem::new(&root) {
        Ok(filesystem) => Some(filesystem),
        // Unsupported hosts retain the pre-existing isolated pure-code runner.
        Err(error) if error.kind() == io::ErrorKind::Unsupported => None,
        Err(_) => return ptr::null_mut(),
    };
    let Some((backend_path, identity)) = resolve_backend(backend_path, &sysroot) else {
        return ptr::null_mut();
    };
    let input = if config.stdin_len == 0 { vec![] } else {
        unsafe { std::slice::from_raw_parts(config.stdin_data, config.stdin_len) }.to_vec()
    };
    if !claim_backend(identity) { return ptr::null_mut(); }
    Box::into_raw(Box::new(QfliSession {
        source, sysroot, backend_path,
        io: new_session_io_with_fs(
            input, Some(config.max_basic_blocks), config.timeout_ms,
            config.max_output_bytes, Some(config.max_guest_memory_bytes), filesystem,
        ),
        result: Mutex::new(QfliResult { state: READY, exit_code: -1, basic_blocks: 0, peak_guest_memory_bytes: 0 }),
        started: AtomicBool::new(false),
        owners: AtomicU32::new(0),
        analysis: None,
    }))
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn qfli_miri_run(session: *mut QfliSession) -> i32 {
    ffi_guard(-1, || unsafe { run_session(session) })
}

unsafe fn run_session(session: *mut QfliSession) -> i32 {
    let Some(session) = (unsafe { session.as_ref() }) else { return -1 };
    // Claim the callback slot and the lifetime in one ordered step: `begin`
    // fails if `destroy` already latched, so a call never starts on a session
    // that is being freed.
    let Some(_active) = ActiveCall::begin(&session.owners) else { return -1 };
    if session.started.swap(true, Ordering::AcqRel) { return -1; }
    lock(&session.result).state = RUNNING;
    // Built before the compiler starts so the outcome below can still report a
    // boundary failure when the compiler aborts on it.
    let boundary = CompilerBoundary::for_run(
        session.io.filesystem.as_ref().map(|filesystem| filesystem.root()),
        &session.source, &session.sysroot,
    );
    let result = catch_unwind(AssertUnwindSafe(|| {
        let _guard = lock(&COMPILER_LOCK);
        // Start the clock only once the compiler is actually ours: time spent
        // queueing behind another session must not be charged as run time, or a
        // queued run reports `LIMIT_REACHED` without executing anything.
        *lock(&session.io.start) = Some(Instant::now());
        if session.io.check_stop() { return 1; }
        let args = vec![
            "qfli-miri".to_owned(), session.source.clone(),
            "--sysroot".into(), session.sysroot.clone(),
            "--target=x86_64-unknown-linux-gnu".into(),
            "--edition=2024".into(), "--crate-name=qfli_user_program".into(),
            "--color=never".into(),
        ];
        let mut callbacks = CompilerCallbacks {
            io: session.io.clone(), backend_path: session.backend_path.clone(),
            exit_code: 1, interpreted: false,
            boundary: Arc::clone(&boundary),
        };
        let compiler_exit = rustc_driver::catch_fatal_errors(|| rustc_driver::run_compiler(&args, &mut callbacks));
        if compiler_exit.is_err() || !callbacks.interpreted { 1 } else { callbacks.exit_code }
    }));
    let stopped = session.io.stopped.load(Ordering::Acquire);
    let (state, exit_code) = match result {
        _ if stopped != 0 => {
            if let Some(reason) = *lock(&session.io.stop_reason) {
                let _ = session.io.append(2, format!("{reason}\n").as_bytes());
            }
            (stopped, if stopped == CANCELLED { 130 } else { 124 })
        }
        // A boundary failure is never a user-source verdict: the program was not
        // evaluated inside the declared read boundary.
        _ if boundary.failure().is_some() => {
            if let Some(failure) = boundary.failure() {
                let message = format!("qfli: compiler boundary: {failure}\n");
                let _ = session.io.append(2, message.as_bytes());
            }
            (INTERNAL_ERROR, 1)
        }
        Ok(code) => (FINISHED, code),
        Err(_) => {
            let _ = session.io.append(2, b"native Rust interpreter failed internally\n");
            (INTERNAL_ERROR, 1)
        }
    };
    *lock(&session.result) = QfliResult {
        state, exit_code, basic_blocks: session.io.blocks.load(Ordering::Relaxed),
        peak_guest_memory_bytes: session.io.peak_memory.load(Ordering::Relaxed),
    };
    0
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn qfli_miri_cancel(session: *mut QfliSession) {
    ffi_guard((), || unsafe { cancel_session(session) });
}

unsafe fn cancel_session(session: *mut QfliSession) {
    if let Some(session) = unsafe { session.as_ref() } {
        session.io.cancelled.store(true, Ordering::Release);
    }
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn qfli_miri_copy_output(
    session: *const QfliSession, channel: u32, buffer: *mut u8, capacity: usize,
) -> usize {
    ffi_guard(0, || unsafe { session_output(session, channel, buffer, capacity) })
}

unsafe fn session_output(session: *const QfliSession, channel: u32, buffer: *mut u8, capacity: usize) -> usize {
    let Some(session) = (unsafe { session.as_ref() }) else { return 0 };
    let outputs = lock(&session.io.output);
    let Some(output) = outputs.get(channel as usize) else { return 0 };
    if !buffer.is_null() && capacity != 0 {
        unsafe { ptr::copy_nonoverlapping(output.as_ptr(), buffer, capacity.min(output.len())) };
    }
    output.len()
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn qfli_miri_result(session: *const QfliSession, result: *mut QfliResult) -> i32 {
    ffi_guard(-1, || unsafe { session_result(session, result) })
}

unsafe fn session_result(session: *const QfliSession, result: *mut QfliResult) -> i32 {
    let Some(session) = (unsafe { session.as_ref() }) else { return -1 };
    if result.is_null() { return -1; }
    let current = lock(&session.result);
    unsafe { result.write(QfliResult {
        state: current.state, exit_code: current.exit_code,
        basic_blocks: session.io.blocks.load(Ordering::Relaxed),
        peak_guest_memory_bytes: session.io.peak_memory.load(Ordering::Relaxed),
    }) };
    0
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn qfli_miri_destroy(session: *mut QfliSession) {
    ffi_guard((), || {
        if session.is_null() { return; }
        // Latch first: once the DESTROYED bit is observable, no new call can
        // begin, so the remaining count can only fall to zero.
        let Some(session_ref) = (unsafe { session.as_ref() }) else { return };
        let owners = &session_ref.owners;
        let previous = owners.fetch_or(DESTROYED, Ordering::AcqRel);
        // An earlier destroy already latched, or a call is still in flight:
        // freeing now would erase memory a worker still dereferences.
        if previous & DESTROYED != 0 || owners.load(Ordering::Acquire) != DESTROYED {
            return;
        }
        drop(unsafe { Box::from_raw(session) });
    });
}

// ---------------------------------------------------------------------------
// Analysis-only ABI-1 extension.
//
// Compiles the crate with the pinned rustc and stops at the end of analysis.
// It never interprets, never sets `cfg(miri)`, never runs Cargo/build.rs/proc
// macros and writes no output files. Diagnostics are JSON Lines on channel 2.
// ---------------------------------------------------------------------------

/// Marks an in-flight call and clears it on every exit path, including panics.
/// `begin` returns `None` once `destroy` has latched, so no call can start on a
/// session that is already being torn down.
struct ActiveCall<'a>(&'a AtomicU32);

impl<'a> ActiveCall<'a> {
    fn begin(counter: &'a AtomicU32) -> Option<Self> {
        counter
            .fetch_update(Ordering::AcqRel, Ordering::Acquire, |owners| {
                (owners & DESTROYED == 0).then(|| owners + 1)
            })
            .ok()?;
        Some(ActiveCall(counter))
    }
}

impl Drop for ActiveCall<'_> {
    fn drop(&mut self) {
        self.0.fetch_sub(1, Ordering::AcqRel);
    }
}

/// Non-blocking compiler acquisition. Recovers poisoned locks like `lock`.
fn try_compiler() -> Option<MutexGuard<'static, ()>> {
    match COMPILER_LOCK.try_lock() {
        Ok(guard) => Some(guard),
        Err(std::sync::TryLockError::Poisoned(poison)) => Some(poison.into_inner()),
        Err(std::sync::TryLockError::WouldBlock) => None,
    }
}

const EDITIONS: [u32; 4] = [2015, 2018, 2021, 2024];

unsafe fn crate_name_string(value: *const c_char) -> Option<String> {
    if value.is_null() {
        return None;
    }
    let name = unsafe { CStr::from_ptr(value) }.to_str().ok()?;
    if name.is_empty() || name.len() > MAX_CRATE_NAME {
        return None;
    }
    if !name.bytes().all(|byte| byte.is_ascii_alphanumeric() || byte == b'_') {
        return None;
    }
    Some(name.to_owned())
}

/// Installs the structured JSON emitter used by the analysis path only. The run
/// path keeps its annotated-snippet emitter, so its output is unchanged.
fn install_json_emitter(psess: &mut rustc_session::parse::ParseSess, io: Arc<SessionIo>) {
    let writer: Box<dyn Write + Send> = Box::new(DiagnosticWriter(io));
    // `short` keeps `rendered` compact and suppresses the long error-code
    // explanation, which keeps the output bound meaningful.
    let emitter = JsonEmitter::new(
        writer,
        Some(psess.clone_source_map()),
        false,
        HumanReadableErrorType { short: true, unicode: false },
        ColorConfig::Never,
    );
    psess.dcx().set_emitter(Box::new(emitter));
}

struct AnalysisCallbacks {
    io: Arc<SessionIo>,
    backend_path: Option<String>,
    /// Set once `after_analysis` ran, i.e. analysis actually completed.
    analysed: bool,
    /// Shared compiler read boundary. Never optional: a boundary that could not
    /// be established stops the session inside `install`.
    boundary: Arc<CompilerBoundary>,
}

impl rustc_driver::Callbacks for AnalysisCallbacks {
    fn config(&mut self, config: &mut rustc_interface::interface::Config) {
        let backend_path = self.backend_path.clone();
        let backend_io = self.io.clone();
        config.make_codegen_backend = Some(Box::new(move |sess| {
            make_backend(sess, backend_path.as_deref(), &backend_io)
        }));
        // Deliberately no `extra_symbols`, no `cfg(miri)`, no MIR/UB flags:
        // analysis must see the same program plain rustc sees.
        // Unconditional: `install` fails closed when the boundary is not usable.
        self.boundary.install(config);
        let emitter_io = self.io.clone();
        config.psess_created = Some(Box::new(move |psess| {
            install_json_emitter(psess, emitter_io);
        }));
    }

    fn after_crate_root_parsing(
        &mut self,
        _: &rustc_interface::interface::Compiler,
        _: &mut rustc_ast::Crate,
    ) -> Compilation {
        if self.io.check_stop() { Compilation::Stop } else { Compilation::Continue }
    }

    fn after_expansion<'tcx>(
        &mut self,
        _: &rustc_interface::interface::Compiler,
        _: TyCtxt<'tcx>,
    ) -> Compilation {
        if self.io.check_stop() { Compilation::Stop } else { Compilation::Continue }
    }

    fn after_analysis<'tcx>(
        &mut self,
        _: &rustc_interface::interface::Compiler,
        tcx: TyCtxt<'tcx>,
    ) -> Compilation {
        tcx.dcx().emit_stashed_diagnostics();
        tcx.dcx().flush_delayed();
        // No `abort_if_errors`: errors are already emitted as JSON data.
        // Enforce the timeout that may have elapsed while type checking, so an
        // over-budget analysis is reported as a limit rather than as complete.
        if self.io.check_stop() { return Compilation::Stop; }
        // Returning Stop here is what keeps Miri from ever evaluating the crate.
        self.analysed = true;
        Compilation::Stop
    }
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn qfli_miri_create_analysis(
    config: *const QfliAnalysisConfig, backend_path: *const c_char,
) -> *mut QfliSession {
    ffi_guard(ptr::null_mut(), || unsafe { create_analysis_session(config, backend_path) })
}

unsafe fn create_analysis_session(
    config: *const QfliAnalysisConfig, backend_path: *const c_char,
) -> *mut QfliSession {
    let Some(config) = (unsafe { config.as_ref() }) else { return ptr::null_mut() };
    if config.abi_version != ABI_VERSION || config.timeout_ms == 0
        || config.max_output_bytes < 1024 || config.max_output_bytes > MAX_INPUT
        || !EDITIONS.contains(&config.edition) || config.crate_type > 1
    {
        return ptr::null_mut();
    }
    let Some(source) = (unsafe { path_string(config.source_path) }) else { return ptr::null_mut() };
    let Some(sysroot) = (unsafe { path_string(config.sysroot_path) }) else { return ptr::null_mut() };
    let Some(crate_name) = (unsafe { crate_name_string(config.crate_name) }) else {
        return ptr::null_mut();
    };
    if !Path::new(&source).is_file() || !Path::new(&sysroot).is_dir() {
        return ptr::null_mut();
    }
    let Some((backend_path, identity)) = resolve_backend(backend_path, &sysroot) else {
        return ptr::null_mut();
    };
    if !claim_backend(identity) { return ptr::null_mut(); }
    Box::into_raw(Box::new(QfliSession {
        source, sysroot, backend_path,
        io: new_session_io(Vec::new(), None, config.timeout_ms, config.max_output_bytes, None),
        result: Mutex::new(QfliResult { state: READY, exit_code: -1, basic_blocks: 0, peak_guest_memory_bytes: 0 }),
        started: AtomicBool::new(false),
        owners: AtomicU32::new(0),
        analysis: Some(AnalysisOptions {
            crate_name, edition: config.edition, crate_type: config.crate_type,
        }),
    }))
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn qfli_miri_analyze(session: *mut QfliSession) -> i32 {
    ffi_guard(-1, || unsafe { analyze_session(session) })
}

unsafe fn analyze_session(session: *mut QfliSession) -> i32 {
    let Some(session) = (unsafe { session.as_ref() }) else { return -1 };
    // Reject a reused or already-running session before touching any state, so a
    // duplicate call cannot overwrite the running analysis' status.
    if session.started.load(Ordering::Acquire) { return -1; }
    // Acquire the compiler before consuming the session so a busy answer can be
    // retried instead of burning the single analysis attempt.
    let Some(_guard) = try_compiler() else {
        // `2` is the whole busy answer. Deliberately no write to
        // `result.state`: that field is the session's status, and a transient
        // call outcome must not overwrite it (nor race a concurrent destroy).
        return BUSY_RETURN;
    };
    // Take the lifetime slot before claiming `started`, so a session that
    // `destroy` already latched is rejected instead of half-claimed.
    let Some(_active) = ActiveCall::begin(&session.owners) else { return -1 };
    if session.started.swap(true, Ordering::AcqRel) { return -1; }
    lock(&session.result).state = RUNNING;
    *lock(&session.io.start) = Some(Instant::now());
    let Some(options) = session.analysis.as_ref() else {
        // Only analysis-created sessions carry options. The attempt is spent.
        *lock(&session.result) = QfliResult {
            state: INTERNAL_ERROR, exit_code: 1, basic_blocks: 0, peak_guest_memory_bytes: 0,
        };
        return 0;
    };
    let crate_type = if options.crate_type == 1 { "lib" } else { "bin" };
    let boundary = CompilerBoundary::for_analysis(&session.source, &session.sysroot);
    let analysed = catch_unwind(AssertUnwindSafe(|| {
        if session.io.check_stop() { return false; }
        let args = vec![
            "qfli-analysis".to_owned(), session.source.clone(),
            format!("--sysroot={}", session.sysroot),
            "--target=x86_64-unknown-linux-gnu".into(),
            format!("--edition={}", options.edition),
            format!("--crate-name={}", options.crate_name),
            format!("--crate-type={crate_type}"),
            "--color=never".into(),
        ];
        let mut callbacks = AnalysisCallbacks {
            io: session.io.clone(), backend_path: session.backend_path.clone(),
            analysed: false,
            boundary: Arc::clone(&boundary),
        };
        let _ = rustc_driver::catch_fatal_errors(|| {
            rustc_driver::run_compiler(&args, &mut callbacks)
        });
        callbacks.analysed
    }));
    let stopped = session.io.stopped.load(Ordering::Acquire);
    let emitted = lock(&session.io.output)[2].len();
    let (state, exit_code) = match analysed {
        _ if stopped != 0 => {
            if let Some(reason) = *lock(&session.io.stop_reason) {
                let _ = session.io.append(2, format!("{reason}\n").as_bytes());
            }
            (stopped, if stopped == CANCELLED { 130 } else { 124 })
        }
        // A completed analysis is data, with or without error diagnostics.
        // A boundary failure takes precedence: the mirror was not read inside
        // the declared boundary, so "checked clean" would be a false verdict.
        _ if boundary.failure().is_some() => {
            if let Some(failure) = boundary.failure() {
                let message = format!("qfli: compiler boundary: {failure}\n");
                let _ = session.io.append(2, message.as_bytes());
            }
            (INTERNAL_ERROR, 1)
        }
        Ok(true) => (FINISHED, 0),
        // rustc stopped early. That is only a user-source verdict if it actually
        // reported something: a silent abort before `after_analysis`, with no
        // diagnostics and no panic, is a broken compiler and must not be
        // reported as a clean result.
        Ok(false) | Err(_) if emitted > 0 => (FINISHED, 0),
        Ok(false) | Err(_) => (INTERNAL_ERROR, 1),
    };
    *lock(&session.result) = QfliResult {
        state, exit_code, basic_blocks: 0,
        peak_guest_memory_bytes: 0,
    };
    0
}
