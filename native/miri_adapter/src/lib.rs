#![feature(rustc_private)]

extern crate anstream;
extern crate rustc_ast;
extern crate rustc_codegen_ssa;
extern crate rustc_errors;
extern crate rustc_driver;
extern crate rustc_interface;
extern crate rustc_middle;
extern crate rustc_session;

use std::ffi::{CStr, c_char};
use std::io::{self, Read, Write};
use std::panic::{AssertUnwindSafe, catch_unwind};
use std::path::{Path, PathBuf};
use std::ptr;
use std::sync::atomic::{AtomicBool, AtomicU32, AtomicU64, Ordering};
use std::sync::{Arc, Mutex, MutexGuard};
use std::time::{Duration, Instant};

use miri::{EmbeddedSession, MiriConfig};
use rustc_codegen_ssa::traits::CodegenBackend;
use rustc_driver::Compilation;
use rustc_errors::annotate_snippet_emitter_writer::AnnotateSnippetEmitter;
use rustc_errors::emitter::Destination;
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
const MAX_INPUT: usize = 16 * 1024 * 1024;
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
}

#[derive(Debug)]
struct SessionIo {
    stdin: Mutex<io::Cursor<Vec<u8>>>,
    output: Mutex<[Vec<u8>; 3]>,
    cancelled: AtomicBool,
    stopped: AtomicU32,
    stop_reason: Mutex<Option<&'static str>>,
    blocks: AtomicU64,
    memory: AtomicU64,
    peak_memory: AtomicU64,
    start: Mutex<Option<Instant>>,
    max_blocks: u64,
    timeout: Duration,
    max_output: usize,
    max_memory: u64,
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
        let total: usize = outputs.iter().map(Vec::len).sum();
        let bound = if channel == 2 { self.max_output } else { self.max_output - 512 };
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
        if self.blocks.load(Ordering::Relaxed) >= self.max_blocks {
            self.stop(LIMIT_REACHED, "session basic block limit reached");
        }
        if lock(&self.start).is_some_and(|start| start.elapsed() >= self.timeout) {
            self.stop(LIMIT_REACHED, "session time limit reached");
        }
        self.stopped.load(Ordering::Acquire) != 0
    }
}

impl EmbeddedSession for SessionIo {
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
        let bytes = bytes as u64;
        let reserved = self.memory.fetch_update(Ordering::AcqRel, Ordering::Acquire, |used| {
            used.checked_add(bytes).filter(|&next| next <= self.max_memory)
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
    ffi_guard(ptr::null_mut(), || unsafe { create_session(config, ptr::null()) })
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn qfli_miri_create_with_backend(
    config: *const QfliConfig, backend_path: *const c_char,
) -> *mut QfliSession {
    ffi_guard(ptr::null_mut(), || unsafe { create_session(config, backend_path) })
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

unsafe fn create_session(config: *const QfliConfig, backend_path: *const c_char) -> *mut QfliSession {
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
    let backend = if backend_path.is_null() {
        default_backend(Path::new(&sysroot))
    } else {
        unsafe { path_string(backend_path) }.and_then(|path| external_backend(Path::new(&path)))
    };
    let Some((backend_path, identity)) = backend else { return ptr::null_mut() };
    let input = if config.stdin_len == 0 { vec![] } else {
        unsafe { std::slice::from_raw_parts(config.stdin_data, config.stdin_len) }.to_vec()
    };
    // rustc caches the first backend factory globally, even across destroyed sessions.
    let mut selected_backend = lock(&COMPILER_BACKEND);
    if let Some(selected) = selected_backend.as_ref() {
        if selected != &identity { return ptr::null_mut(); }
    } else {
        *selected_backend = Some(identity);
    }
    Box::into_raw(Box::new(QfliSession {
        source, sysroot, backend_path,
        io: Arc::new(SessionIo {
            stdin: Mutex::new(io::Cursor::new(input)),
            output: Mutex::new([vec![], vec![], vec![]]),
            cancelled: AtomicBool::new(false), stopped: AtomicU32::new(0),
            stop_reason: Mutex::new(None), blocks: AtomicU64::new(0),
            memory: AtomicU64::new(0), peak_memory: AtomicU64::new(0), start: Mutex::new(None),
            max_blocks: config.max_basic_blocks,
            timeout: Duration::from_millis(config.timeout_ms),
            max_output: config.max_output_bytes,
            max_memory: config.max_guest_memory_bytes,
        }),
        result: Mutex::new(QfliResult { state: READY, exit_code: -1, basic_blocks: 0, peak_guest_memory_bytes: 0 }),
        started: AtomicBool::new(false),
    }))
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn qfli_miri_run(session: *mut QfliSession) -> i32 {
    ffi_guard(-1, || unsafe { run_session(session) })
}

unsafe fn run_session(session: *mut QfliSession) -> i32 {
    let Some(session) = (unsafe { session.as_ref() }) else { return -1 };
    if session.started.swap(true, Ordering::AcqRel) { return -1; }
    lock(&session.result).state = RUNNING;
    *lock(&session.io.start) = Some(Instant::now());
    let result = catch_unwind(AssertUnwindSafe(|| {
        let _guard = lock(&COMPILER_LOCK);
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
        if !session.is_null() { drop(unsafe { Box::from_raw(session) }); }
    });
}
