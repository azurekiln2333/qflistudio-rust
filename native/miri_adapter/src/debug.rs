//! Interactive debugging: real Miri stepping behind a small C ABI.
//!
//! This module is a child of the adapter crate, so it reuses the parent's
//! private helpers (`lock`, `ffi_guard`, `path_string`, `resolve_backend`,
//! `claim_backend`, `crate_name_string`, `make_backend`, `DiagnosticWriter`,
//! `COMPILER_LOCK`) instead of duplicating them.
//!
//! Constraints that shaped this file, all verified against the pinned Miri
//! source:
//!
//! * `InterpCx<'tcx>` borrows the compiler session, so it can never be stored in
//!   the `'static` C session. The interpreter therefore lives entirely inside
//!   one `run_compiler` call on a dedicated worker thread; the C session holds
//!   only owned snapshots.
//! * `miri_step` must be driven by us: `eval_entry` owns its loop and cannot
//!   host a debugger.
//! * `Frame::locals[local].access()` raises `DeadLocal` UB for a local that is
//!   not live, so values are read only after `as_mplace_or_imm()` proves the
//!   local is live. Otherwise the local is reported uninitialized.
//! * A paused session keeps the compiler session alive and therefore holds
//!   `COMPILER_LOCK` for its whole lifetime. `qfli_miri_analyze` reports busy
//!   rather than queueing; a `run` waits. This is documented in the header.
//! * No lock is held across the control wait except the control mutex itself, so
//!   pause/cancel/resume from other threads always make progress.

use std::ffi::c_char;
use std::panic::{AssertUnwindSafe, catch_unwind};
use std::ptr;
use std::sync::atomic::{AtomicBool, AtomicU32, AtomicU64, Ordering};
use std::sync::{Arc, Condvar, Mutex, TryLockError};
use std::thread::JoinHandle;
use std::time::{Duration, Instant};

use miri::*;
use rustc_driver::Compilation;
use rustc_middle::mir::{Local, StatementKind, VarDebugInfoContents};
use rustc_middle::ty::TyCtxt;
use rustc_span::RemapPathScopeComponents;

use crate::{
    ABI_VERSION, COMPILER_LOCK, DiagnosticWriter, MAX_INPUT, SessionIo, claim_backend,
    crate_name_string, ffi_guard, lock, make_backend, new_session_io, path_string, resolve_backend,
};
use crate::compiler_boundary::CompilerBoundary;

// Session states. Numbered separately from the run/analysis states so a frontend
// cannot confuse a debug pause with a run result.
const NEW: u32 = 0;
const RUNNING: u32 = 1;
const PAUSED: u32 = 2;
const TERMINATED: u32 = 3;
const FAILED: u32 = 4;
const STOPPING: u32 = 5;
const DESTROYED: u32 = 1 << 31;

// Pause reasons, mirroring enum QfliDebugPauseReason.
const PAUSE_ENTRY: u32 = 0;
const PAUSE_BREAKPOINT: u32 = 1;
const PAUSE_STEP: u32 = 2;
const PAUSE_REQUESTED: u32 = 3;
const PAUSE_TERMINATED: u32 = 4;
const PAUSE_ERROR: u32 = 5;
const PAUSE_LIMIT: u32 = 6;
const PAUSE_CANCELLED: u32 = 7;

// Resume modes, mirroring enum QfliDebugResume.
const RESUME_CONTINUE: u32 = 0;
const RESUME_STEP_IN: u32 = 1;
const RESUME_STEP_OVER: u32 = 2;
const RESUME_STEP_OUT: u32 = 3;

const LOCAL_VALUE: u32 = 0;
const LOCAL_UNINITIALIZED: u32 = 1;
const LOCAL_UNSUPPORTED: u32 = 2;

/// Every capability advertised here is implemented below; nothing is claimed
/// optimistically. Bits mirror enum QfliDebugCapability.
const CAPABILITIES: u32 = (1 << 9) - 1;

const EDITIONS: [u32; 4] = [2015, 2018, 2021, 2024];
const MAX_BREAKPOINTS: usize = 1024;

#[repr(C)]
pub struct QfliDebugConfig {
    abi_version: u32,
    source_path: *const c_char,
    sysroot_path: *const c_char,
    crate_name: *const c_char,
    edition: u32,
    crate_type: u32,
    timeout_ms: u64,
    max_steps: u64,
    max_output_bytes: usize,
    breakpoints: *const QfliBreakpoint,
    breakpoint_count: usize,
}

#[repr(C)]
pub struct QfliBreakpoint {
    file_path: *const c_char,
    line: u32,
    column: u32,
}

#[repr(C)]
pub struct QfliDebugPause {
    reason: u32,
    frame_count: u32,
    steps: u64,
    exit_code: i32,
}

#[repr(C)]
pub struct QfliDebugStatus {
    state: u32,
    worker_exited: u32,
    pause_generation: u64,
    revision: u64,
}

#[repr(C)]
pub struct QfliFrame {
    index: u32,
    _pad: u32,
    file_path: *const c_char,
    line: u32,
    column: u32,
    function: *const c_char,
}

#[repr(C)]
pub struct QfliLocal {
    name: *const c_char,
    type_name: *const c_char,
    local: u32,
    state: u32,
    value: *const c_char,
}

/// A resolved source position, produced by rustc's own `SourceMap`.
#[derive(Clone, PartialEq, Eq)]
struct Position {
    file: String,
    line: u32,
    column: u32,
}

struct Breakpoint {
    file: String,
    line: u32,
    column: u32,
}

struct LocalSnapshot {
    name: String,
    type_name: String,
    local: u32,
    state: u32,
    value: String,
}

struct FrameSnapshot {
    file: String,
    line: u32,
    column: u32,
    function: String,
    locals: Vec<LocalSnapshot>,
}

/// Owned copy of one pause, so it survives the interpreter borrow that produced
/// it and can be read from another thread.
struct Snapshot {
    reason: u32,
    frame_count: u32,
    steps: u64,
    exit_code: i32,
    frames: Vec<FrameSnapshot>,
}

impl Snapshot {
    fn new() -> Self {
        Snapshot { reason: PAUSE_ENTRY, frame_count: 0, steps: 0, exit_code: 0, frames: Vec::new() }
    }
}

enum Command {
    Resume { mode: u32 },
    Terminate,
}

struct Control {
    command: Option<Command>,
    pause_requested: bool,
    cancelled: bool,
    /// The worker published a pause and is waiting for a command.
    paused: bool,
    /// The worker left the interpreter loop; no further resume is possible.
    finished: bool,
    worker_exited: bool,
    busy: bool,
    /// Compiler callbacks stage this result; it is published only after the
    /// compiler unwinds and releases its process-wide lease.
    terminal: Option<(u32, u32, i32)>,
}

/// Everything the C API and the worker share. The concrete interpreter cannot
/// live here (it borrows the compiler session), only owned snapshots.
struct Shared {
    source: String,
    sysroot: String,
    backend_path: Option<String>,
    crate_name: String,
    edition: u32,
    crate_type: u32,
    max_steps: u64,
    breakpoints: Vec<Breakpoint>,
    /// Low bits are NEW/RUNNING/PAUSED/TERMINATED/FAILED; bit 31 is DESTROYED.
    state: AtomicU32,
    started: AtomicBool,
    active_calls: AtomicU32,
    pause_generation: AtomicU64,
    revision: AtomicU64,
    io: Arc<SessionIo>,
    control: Mutex<Control>,
    control_cv: Condvar,
    snapshot: Mutex<Snapshot>,
    /// Owned `CString`s backing the pointers in `QfliFrame`/`QfliLocal`. Rebuilt
    /// before a pause is published, so readers never see a partial table.
    strings: Mutex<StringTable>,
    worker: Mutex<Option<JoinHandle<()>>>,
}

/// The C-visible handle. Deliberately a distinct type from `QfliSession`; it is
/// a thin pointer to the shared state held by the worker thread.
pub struct QfliDebugSession {
    shared: Arc<Shared>,
}

impl Shared {
    fn state(&self) -> u32 {
        self.state.load(Ordering::Acquire) & !DESTROYED
    }

    fn set_state(&self, state: u32) {
        // Preserve a concurrent destroy latch instead of losing it between a
        // separate load/store pair.
        self.state.fetch_update(Ordering::AcqRel, Ordering::Acquire, |previous| {
            Some(state | (previous & DESTROYED))
        }).unwrap();
        self.revision.fetch_add(1, Ordering::AcqRel);
    }
}

/// Owns the `CString`s the C structs point into. Rebuilt wholesale on publish.
#[derive(Default)]
struct StringTable {
    owned: Vec<std::ffi::CString>,
    files: Vec<*const c_char>,
    functions: Vec<*const c_char>,
    names: Vec<*const c_char>,
    types: Vec<*const c_char>,
    values: Vec<*const c_char>,
    /// Per frame: the range in `names`/`types`/`values` it occupies.
    locals: Vec<std::ops::Range<usize>>,
}

// The raw pointers only ever point into `owned`, which is never mutated while
// the table is published, and the table is replaced wholesale under a mutex.
unsafe impl Send for StringTable {}
unsafe impl Sync for StringTable {}

impl StringTable {
    fn build(snapshot: &Snapshot) -> Self {
        let mut table = StringTable::default();
        for frame in &snapshot.frames {
            let file = table.push(&frame.file);
            table.files.push(file);
            let function = table.push(&frame.function);
            table.functions.push(function);
            let start = table.names.len();
            for local in &frame.locals {
                let name = table.push(&local.name);
                table.names.push(name);
                let type_name = table.push(&local.type_name);
                table.types.push(type_name);
                let value = table.push(&local.value);
                table.values.push(value);
            }
            table.locals.push(start..table.names.len());
        }
        table
    }

    fn push(&mut self, text: &str) -> *const c_char {
        // rustc paths and rendered scalars cannot contain NUL, but be defensive
        // instead of assuming it.
        let sanitized = text.replace('\0', "\u{FFFD}");
        let owned = std::ffi::CString::new(sanitized).unwrap_or_default();
        let pointer = owned.as_ptr();
        self.owned.push(owned);
        pointer
    }
}

// ---------------------------------------------------------------------------
// Interpreter driver (runs entirely on the worker thread)
// ---------------------------------------------------------------------------

enum Outcome {
    Terminated,
    Cancelled,
    Limit,
    Error,
}

struct Debugger<'tcx> {
    ecx: MiriInterpCx<'tcx>,
    shared: Arc<Shared>,
    steps: u64,
    last_position: Option<Position>,
    exit_code: i32,
}

impl<'tcx> Debugger<'tcx> {
    /// Current source position from Miri's user-relevant span, so a
    /// macro-backed line resolves to the call site the user sees.
    fn current_position(&self) -> Option<Position> {
        let span = self.ecx.machine.current_user_relevant_span();
        if span.is_dummy() {
            return None;
        }
        Some(self.position_of(span))
    }

    fn position_of(&self, span: rustc_span::Span) -> Position {
        let span = span.source_callsite();
        let loc = self.ecx.tcx.sess.source_map().lookup_char_pos(span.lo());
        Position {
            file: loc.file.name.display(RemapPathScopeComponents::DIAGNOSTICS).to_string(),
            line: loc.line as u32,
            column: loc.col.0 as u32 + 1,
        }
    }

    fn depth(&self) -> usize {
        self.ecx.active_thread_stack().len()
    }

    fn hits_breakpoint(&self, position: &Position) -> bool {
        self.shared.breakpoints.iter().any(|breakpoint| {
            breakpoint.file == position.file
                && breakpoint.line == position.line
                && (breakpoint.column == 0 || breakpoint.column == position.column)
                && !self.last_position.as_ref().is_some_and(|previous| {
                    previous.file == position.file && previous.line == position.line
                        && (breakpoint.column == 0 || previous.column == position.column)
                })
        })
    }

    /// Whether the current MIR location is a statement worth stopping on.
    /// Storage bookkeeping is not a user-visible step (proven priroda filter).
    fn at_visible_statement(&self) -> bool {
        let Some(frame) = self.ecx.active_thread_stack().last() else { return false };
        let Either::Left(location) = frame.current_loc() else { return false };
        let block = &frame.body().basic_blocks[location.block];
        match block.statements.get(location.statement_index) {
            // The terminator is always a real step.
            None => true,
            Some(statement) => !matches!(
                statement.kind,
                StatementKind::StorageLive(_) | StatementKind::StorageDead(_) | StatementKind::Nop
            ),
        }
    }

    fn frame_position(
        &self,
        frame: &miri::Frame<'tcx, Provenance, FrameExtra<'tcx>>,
    ) -> (String, u32, u32) {
        let Either::Left(location) = frame.current_loc() else {
            return (String::new(), 0, 0);
        };
        let span = frame.body().source_info(location).span;
        if span.is_dummy() {
            return (String::new(), 0, 0);
        }
        let position = self.position_of(span);
        (position.file, position.line, position.column)
    }

    /// Renders a scalar exactly. Aggregates, pointers and unions are reported as
    /// unsupported instead of guessed: the pinned source offers no public
    /// pretty-printer for an `OpTy`.
    fn render_local(
        &self,
        frame: &miri::Frame<'tcx, Provenance, FrameExtra<'tcx>>,
        local: Local,
    ) -> Option<String> {
        let op = self.ecx.local_at_frame_to_op(frame, local, None).discard_err()?;
        let ty = op.layout.ty;
        let size = op.layout.size;
        // OpTy can be indirect. Its value must be read through InterpCx;
        // to_scalar_int is an ImmTy method, not an OpTy method in this pin.
        if !(ty.is_bool() || ty.is_char() || ty.is_integral() || ty.is_floating_point()) {
            return None;
        }
        let scalar = self.ecx.read_scalar(&op).discard_err()?;
        if ty.is_bool() {
            return Some(scalar.to_bool().discard_err()?.to_string());
        }
        if ty.is_char() {
            return Some(format!("{:?}", scalar.to_char().discard_err()?));
        }
        if ty.is_integral() {
            // Unsigned high bits must not be sign-extended (u128::MAX must
            // remain 340282366920938463463374607431768211455, never -1).
            return Some(if ty.is_signed() {
                scalar.to_int(size).discard_err()?.to_string()
            } else {
                scalar.to_uint(size).discard_err()?.to_string()
            });
        }
        if ty.is_floating_point() {
            let bits = scalar.to_bits(size).discard_err()?;
            return match size.bytes() {
                4 => Some(format!("{:?}", f32::from_bits(bits as u32))),
                8 => Some(format!("{:?}", f64::from_bits(bits as u64))),
                // Do not reinterpret f16/f128 as f64.
                _ => None,
            };
        }
        None
    }

    fn frame_locals(
        &self,
        frame: &miri::Frame<'tcx, Provenance, FrameExtra<'tcx>>,
    ) -> Vec<LocalSnapshot> {
        let body = frame.body();
        let mut names: Vec<Option<String>> = vec![None; body.local_decls.len()];
        for info in &body.var_debug_info {
            if let VarDebugInfoContents::Place(place) = info.value
                && let Some(local) = place.as_local()
                && names[local.as_usize()].is_none()
            {
                names[local.as_usize()] = Some(info.name.to_string());
            }
        }

        let mut locals = Vec::with_capacity(body.local_decls.len());
        for (local, declaration) in body.local_decls.iter_enumerated() {
            let name = names[local.as_usize()].clone().unwrap_or_default();
            let type_name = declaration.ty.to_string();
            // Never read a dead local: `access()` throws `DeadLocal` UB.
            let raw = frame.locals[local].as_mplace_or_imm();
            let (state, value) = if matches!(raw, None | Some(Either::Right(Immediate::Uninit))) {
                (LOCAL_UNINITIALIZED, String::new())
            } else {
                match self.render_local(frame, local) {
                    Some(value) => (LOCAL_VALUE, value),
                    None => (LOCAL_UNSUPPORTED, String::new()),
                }
            };
            locals.push(LocalSnapshot { name, type_name, local: local.as_u32(), state, value });
        }
        locals
    }

    fn snapshot(&self, reason: u32) -> Snapshot {
        let stack = self.ecx.active_thread_stack();
        let mut frames = Vec::with_capacity(stack.len());
        // Innermost frame first, which is index 0.
        for frame in stack.iter().rev() {
            let (file, line, column) = self.frame_position(frame);
            frames.push(FrameSnapshot {
                file,
                line,
                column,
                function: frame.instance().to_string(),
                locals: self.frame_locals(frame),
            });
        }
        Snapshot {
            reason,
            frame_count: frames.len() as u32,
            steps: self.steps,
            exit_code: self.exit_code,
            frames,
        }
    }

    /// Publishes the pause and blocks until the API thread sends a command.
    /// Only the control mutex is held across the wait.
    fn publish_and_wait(&self, reason: u32) -> Command {
        let snapshot = self.snapshot(reason);
        // Build the string table first so the snapshot is never visible with a
        // stale or partial table.
        let table = StringTable::build(&snapshot);
        *lock(&self.shared.snapshot) = snapshot;
        *lock(&self.shared.strings) = table;
        let mut control = lock(&self.shared.control);
        self.shared.pause_generation.fetch_add(1, Ordering::AcqRel);
        self.shared.set_state(PAUSED);
        control.paused = true;
        self.shared.control_cv.notify_all();
        loop {
            if control.cancelled || self.shared.io.check_stop() {
                control.paused = false;
                self.shared.control_cv.notify_all();
                return Command::Terminate;
            }
            if let Some(command) = control.command.take() {
                control.paused = false;
                self.shared.control_cv.notify_all();
                self.shared.set_state(RUNNING);
                return command;
            }
            // A wall-clock limit applies even while paused. Periodic wakeups
            // also avoid silently holding the compiler lease after timeout.
            let (next, _) = self
                .shared
                .control_cv
                .wait_timeout(control, Duration::from_millis(25))
                .unwrap_or_else(|poison| poison.into_inner());
            control = next;
        }
    }

    fn stopped_outcome(&mut self) -> Outcome {
        if lock(&self.shared.control).cancelled
            || self.shared.io.cancelled.load(Ordering::Acquire)
        {
            self.exit_code = 130;
            Outcome::Cancelled
        } else {
            self.exit_code = 124;
            Outcome::Limit
        }
    }

    fn advance(&mut self) -> Result<(), Outcome> {
        let Err(error) = self.ecx.miri_step().report_err() else { return Ok(()) };
        if self.shared.io.check_stop() {
            return Err(self.stopped_outcome());
        }
        let Some((code, leak_check)) = report_result(&self.ecx, error) else {
            self.exit_code = 1;
            return Err(Outcome::Error);
        };
        // Preserve the public thread-termination check. Heap-leak validation
        // requires MiriMachine::static_roots, which is private in this pin;
        // passing an empty root list to take_leaked_allocations would wrongly
        // report leaked TLS and miri_static_root memory as errors. Like the
        // public Priroda loop, debugging does not perform that heap-leak check.
        if leak_check {
            if !self.ecx.have_all_terminated() {
                self.ecx.tcx.dcx().err("the debugged main thread exited without waiting for other threads");
                self.exit_code = 1;
                return Err(Outcome::Error);
            }
        }
        self.exit_code = code;
        Err(Outcome::Terminated)
    }

    /// Drives Miri until the next pause, termination, or limit.
    fn run(&mut self, mut mode: u32) -> Outcome {
        // Capture depth and source position before the first instruction of a
        // resume command. Capturing these after stepping has already entered a
        // call makes step-over behave like step-in and step-out stop too soon.
        let mut origin_depth = self.depth();
        let mut origin = self.current_position();
        self.last_position = origin.clone();
        loop {
            if self.shared.io.check_stop() {
                return self.stopped_outcome();
            }
            if self.steps >= self.shared.max_steps {
                self.exit_code = 124;
                return Outcome::Limit;
            }
            {
                let mut control = lock(&self.shared.control);
                if control.cancelled {
                    drop(control);
                    return self.stopped_outcome();
                }
                if control.pause_requested {
                    control.pause_requested = false;
                    drop(control);
                    match self.publish_and_wait(PAUSE_REQUESTED) {
                        Command::Terminate => return self.stopped_outcome(),
                        Command::Resume { mode: next } => {
                            mode = next;
                            origin_depth = self.depth();
                            origin = self.current_position();
                            self.last_position = origin.clone();
                            continue;
                        }
                    }
                }
            }

            if let Err(outcome) = self.advance() {
                return outcome;
            }
            self.steps += 1;

            let depth = self.depth();
            let Some(position) = self.current_position() else { continue };
            let source_changed = !origin.as_ref().is_some_and(|previous| {
                previous.file == position.file && previous.line == position.line
            });
            // Explicit breakpoints take precedence over manual stepping, even
            // at an otherwise hidden MIR bookkeeping statement.
            let pause_reason = if self.hits_breakpoint(&position) {
                Some(PAUSE_BREAKPOINT)
            } else {
                match mode {
                    RESUME_CONTINUE => None,
                    RESUME_STEP_IN if source_changed && self.at_visible_statement() =>
                        Some(PAUSE_STEP),
                    RESUME_STEP_OVER if depth <= origin_depth && source_changed
                        && self.at_visible_statement() => Some(PAUSE_STEP),
                    RESUME_STEP_OUT if depth < origin_depth && self.at_visible_statement() =>
                        Some(PAUSE_STEP),
                    RESUME_STEP_IN | RESUME_STEP_OVER | RESUME_STEP_OUT => None,
                    _ => {
                        self.exit_code = 1;
                        return Outcome::Error;
                    }
                }
            };

            self.last_position = Some(position);
            if let Some(reason) = pause_reason {
                match self.publish_and_wait(reason) {
                    Command::Terminate => return self.stopped_outcome(),
                    Command::Resume { mode: next } => {
                        mode = next;
                        origin_depth = self.depth();
                        origin = self.current_position();
                        self.last_position = origin.clone();
                    }
                }
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Worker plumbing
// ---------------------------------------------------------------------------

/// Compiler callbacks whose `after_analysis` hosts the whole debug session.
struct DebugCallbacks {
    shared: Arc<Shared>,
    /// Shared compiler read boundary. Never optional: a boundary that could not
    /// be established stops the session inside `install`.
    boundary: Arc<CompilerBoundary>,
}

impl rustc_driver::Callbacks for DebugCallbacks {
    fn config(&mut self, config: &mut rustc_interface::interface::Config) {
        let backend_path = self.shared.backend_path.clone();
        let backend_io = self.shared.io.clone();
        config.make_codegen_backend = Some(Box::new(move |sess| {
            make_backend(sess, backend_path.as_deref(), &backend_io)
        }));
        // The run path's interpretation flags, kept identical so the debugger
        // sees exactly the program the interpreter would.
        config.extra_symbols = miri::sym::EXTRA_SYMBOLS.into();
        let opts = &mut config.opts.unstable_opts;
        opts.always_encode_mir = true;
        opts.extra_const_ub_checks = true;
        opts.mir_preserve_ub = true;
        opts.mir_opt_level = Some(0);
        opts.deduplicate_diagnostics = false;
        config.crate_cfg.push("miri".into());
        // Unconditional: `install` fails closed when the boundary is not usable.
        self.boundary.install(config);
        let io = self.shared.io.clone();
        config.psess_created = Some(Box::new(move |psess| {
            let writer: Box<dyn std::io::Write + Send> = Box::new(DiagnosticWriter(io));
            let destination =
                rustc_errors::emitter::Destination::new(writer, anstream::ColorChoice::Never);
            let emitter =
                rustc_errors::annotate_snippet_emitter_writer::AnnotateSnippetEmitter::new(
                    destination,
                )
                .sm(Some(psess.clone_source_map()));
            psess.dcx().set_emitter(Box::new(emitter));
        }));
    }

    fn after_crate_root_parsing(
        &mut self,
        _: &rustc_interface::interface::Compiler,
        _: &mut rustc_ast::Crate,
    ) -> Compilation {
        if self.shared.io.check_stop() { Compilation::Stop } else { Compilation::Continue }
    }

    fn after_expansion<'tcx>(
        &mut self,
        _: &rustc_interface::interface::Compiler,
        _: TyCtxt<'tcx>,
    ) -> Compilation {
        if self.shared.io.check_stop() { Compilation::Stop } else { Compilation::Continue }
    }

    fn after_analysis<'tcx>(
        &mut self,
        _: &rustc_interface::interface::Compiler,
        tcx: TyCtxt<'tcx>,
    ) -> Compilation {
        tcx.dcx().emit_stashed_diagnostics();
        if tcx.dcx().has_errors().is_some() {
            // A source error is an error pause, not a silent stop.
            tcx.dcx().flush_delayed();
            self.finish(FAILED, PAUSE_ERROR, -1);
            return Compilation::Stop;
        }
        tcx.dcx().flush_delayed();
        if self.shared.io.check_stop() {
            if self.shared.io.cancelled.load(Ordering::Acquire) {
                self.finish(TERMINATED, PAUSE_CANCELLED, 130);
            } else {
                self.finish(TERMINATED, PAUSE_LIMIT, 124);
            }
            return Compilation::Stop;
        }

        let (entry_id, entry_type) = miri::entry_fn(tcx);
        let config = MiriConfig {
            args: vec![tcx.sess.io.input.filestem().to_string()],
            embedded_session: Some(self.shared.io.clone()),
            short_fd_operations: false,
            ..MiriConfig::default()
        };
        let ecx = match miri::create_ecx(tcx, entry_id, entry_type, &config, None).report_err() {
            Ok(ecx) => ecx,
            Err(_) => {
                self.finish(FAILED, PAUSE_ERROR, -1);
                return Compilation::Stop;
            }
        };

        let mut debugger = Debugger {
            ecx,
            shared: self.shared.clone(),
            steps: 0,
            last_position: None,
            exit_code: 0,
        };
        // create_ecx installs an on-stack-empty callback; it does not yet have
        // a frame. Drive the real runtime setup until the requested entry is
        // active, before any of that function's instructions execute. Reporting
        // an invented main frame over the initially empty stack would be false.
        let mut bootstrap_steps = 0u64;
        let bootstrap_outcome = loop {
            if debugger.shared.io.check_stop() {
                break Some(debugger.stopped_outcome());
            }
            if debugger.ecx.active_thread_stack().last().is_some_and(|frame| {
                frame.instance().def_id() == entry_id
            }) {
                break None;
            }
            if bootstrap_steps >= 1_000_000 {
                debugger.exit_code = 124;
                break Some(Outcome::Limit);
            }
            if let Err(outcome) = debugger.advance() {
                break Some(outcome);
            }
            bootstrap_steps += 1;
        };
        let outcome = match bootstrap_outcome {
            Some(outcome) => outcome,
            None => match debugger.publish_and_wait(PAUSE_ENTRY) {
                Command::Terminate => debugger.stopped_outcome(),
                Command::Resume { mode } => debugger.run(mode),
            },
        };
        let exit_code = debugger.exit_code;
        lock(&self.shared.snapshot).steps = debugger.steps;
        // Dropping the debugger releases the interpreter borrow before the
        // session publishes its terminal state.
        drop(debugger);
        match outcome {
            Outcome::Terminated => self.finish(TERMINATED, PAUSE_TERMINATED, exit_code),
            Outcome::Cancelled => self.finish(TERMINATED, PAUSE_CANCELLED, 130),
            Outcome::Limit => self.finish(TERMINATED, PAUSE_LIMIT, exit_code),
            Outcome::Error => self.finish(FAILED, PAUSE_ERROR, exit_code),
        }
        Compilation::Stop
    }
}

impl DebugCallbacks {
    fn finish(&self, state: u32, reason: u32, exit_code: i32) {
        let mut control = lock(&self.shared.control);
        control.terminal = Some((state, reason, exit_code));
        control.paused = false;
    }
}

/// Runs the compiler on a worker thread and blocks until the entry pause. The
/// compiler lock is taken *inside* the worker so the API thread never holds it.
fn spawn_worker(shared: Arc<Shared>) -> std::io::Result<JoinHandle<()>> {
    std::thread::Builder::new().name("qfli-miri-debug".into()).spawn(move || {
        // Built before the compiler starts so the terminal state below can still
        // report a boundary failure when the compiler aborts on it.
        let boundary = CompilerBoundary::for_run(
            shared.io.filesystem.as_ref().map(|filesystem| filesystem.root()),
            &shared.source, &shared.sysroot,
        );
        let compiled = catch_unwind(AssertUnwindSafe(|| {
        let guard = match COMPILER_LOCK.try_lock() {
            Ok(guard) => guard,
            Err(TryLockError::Poisoned(poison)) => poison.into_inner(),
            Err(TryLockError::WouldBlock) => return None,
        };
        *lock(&shared.io.start) = Some(Instant::now());
        let args = vec![
            "qfli-debug".to_owned(),
            shared.source.clone(),
            "--sysroot".into(),
            shared.sysroot.clone(),
            "--target=x86_64-unknown-linux-gnu".into(),
            format!("--edition={}", shared.edition),
            format!("--crate-name={}", shared.crate_name),
            format!("--crate-type={}", if shared.crate_type == 1 { "lib" } else { "bin" }),
            "--color=never".into(),
        ];
        let mut callbacks = DebugCallbacks {
            shared: shared.clone(),
            boundary: Arc::clone(&boundary),
        };
        let result = rustc_driver::catch_fatal_errors(|| {
            rustc_driver::run_compiler(&args, &mut callbacks)
        });
        // Terminal state is not observable until the compiler has unwound and
        // its process-wide lease is released. `wait`/destroy joins the thread.
        drop(guard);
        Some(result.is_ok())
        }));
        // If the compile never reached `after_analysis`, nobody published a
        // terminal state; do it here so the API thread never waits forever.
        let mut control = lock(&shared.control);
        if matches!(compiled, Ok(None)) {
            control.busy = true;
            shared.started.store(false, Ordering::Release);
            shared.set_state(NEW);
        } else {
            let (state, reason, exit_code) = if shared.io.cancelled.load(Ordering::Acquire) {
                (TERMINATED, PAUSE_CANCELLED, 130)
            } else if shared.io.check_stop() {
                (TERMINATED, PAUSE_LIMIT, 124)
            } else if let Some(failure) = boundary.failure() {
                // Not a pause and not a user verdict: the program was never
                // evaluated inside the declared read boundary.
                let message = format!("qfli: compiler boundary: {failure}\n");
                let _ = shared.io.append(2, message.as_bytes());
                (FAILED, PAUSE_ERROR, 1)
            } else if compiled.is_err() || matches!(compiled, Ok(Some(false))) {
                (FAILED, PAUSE_ERROR, 1)
            } else {
                control.terminal.take().unwrap_or((FAILED, PAUSE_ERROR, 1))
            };
            let mut snapshot = lock(&shared.snapshot);
            snapshot.reason = reason;
            snapshot.exit_code = exit_code;
            // Frames/tokens are valid only at a real pause. A terminal event
            // must not expose stale frames from the previous stop.
            snapshot.frames.clear();
            snapshot.frame_count = 0;
            // Retain the backing strings until destroy: a timeout may happen
            // asynchronously while a caller is copying a just-read C string.
            shared.set_state(state);
        }
        control.finished = true;
        control.worker_exited = true;
        control.paused = false;
        shared.control_cv.notify_all();
    })
}

/// Blocks until the worker reaches a pause or a terminal state.
fn wait_for_pause(shared: &Shared) -> i32 {
    let mut control = lock(&shared.control);
    loop {
        if control.paused {
            return 0;
        }
        if control.finished {
            return if control.busy { 2 } else if shared.state() == FAILED { -1 } else { 0 };
        }
        control = shared.control_cv.wait(control).unwrap_or_else(|poison| poison.into_inner());
    }
}

fn join_worker(shared: &Shared) {
    if let Some(worker) = lock(&shared.worker).take() {
        // Worker panics are contained and published above. Still consume a
        // JoinHandle error defensively rather than unwinding through the ABI.
        let _ = worker.join();
    }
}

struct ActiveCall(Arc<Shared>);

impl ActiveCall {
    fn acquire(shared: Arc<Shared>) -> Option<Self> {
        if shared.active_calls.compare_exchange(0, 1, Ordering::AcqRel, Ordering::Acquire).is_err() {
            return None;
        }
        Some(Self(shared))
    }
}

impl Drop for ActiveCall {
    fn drop(&mut self) {
        self.0.active_calls.store(0, Ordering::Release);
    }
}

// ---------------------------------------------------------------------------
// C ABI
// ---------------------------------------------------------------------------

fn breakpoints_from(config: &QfliDebugConfig) -> Option<Vec<Breakpoint>> {
    if config.breakpoint_count == 0 {
        return Some(Vec::new());
    }
    if config.breakpoints.is_null() || config.breakpoint_count > MAX_BREAKPOINTS {
        return None;
    }
    let raw =
        unsafe { std::slice::from_raw_parts(config.breakpoints, config.breakpoint_count) };
    let mut breakpoints = Vec::with_capacity(raw.len());
    for entry in raw {
        let file = unsafe { path_string(entry.file_path) }?;
        if entry.line == 0 {
            return None;
        }
        breakpoints.push(Breakpoint { file, line: entry.line, column: entry.column });
    }
    Some(breakpoints)
}

#[unsafe(no_mangle)]
pub extern "C" fn qfli_miri_debug_capabilities() -> u32 {
    CAPABILITIES
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn qfli_miri_debug_create(
    config: *const QfliDebugConfig, backend_path: *const c_char,
) -> *mut QfliDebugSession {
    ffi_guard(ptr::null_mut(), || unsafe { create(config, backend_path) })
}

unsafe fn create(
    config: *const QfliDebugConfig, backend_path: *const c_char,
) -> *mut QfliDebugSession {
    let Some(config) = (unsafe { config.as_ref() }) else { return ptr::null_mut() };
    if config.abi_version != ABI_VERSION
        || config.timeout_ms == 0
        || config.max_steps == 0
        || config.max_output_bytes < 1024
        || config.max_output_bytes > MAX_INPUT
        || !EDITIONS.contains(&config.edition)
        || config.crate_type > 1
    {
        return ptr::null_mut();
    }
    let Some(source) = (unsafe { path_string(config.source_path) }) else {
        return ptr::null_mut();
    };
    let Some(sysroot) = (unsafe { path_string(config.sysroot_path) }) else {
        return ptr::null_mut();
    };
    let Some(crate_name) = (unsafe { crate_name_string(config.crate_name) }) else {
        return ptr::null_mut();
    };
    if !std::path::Path::new(&source).is_file()
        || !std::path::Path::new(&sysroot).is_dir()
    {
        return ptr::null_mut();
    }
    let Some(breakpoints) = breakpoints_from(config) else { return ptr::null_mut() };
    let Some((backend_path, identity)) = resolve_backend(backend_path, &sysroot) else {
        return ptr::null_mut();
    };
    if !claim_backend(identity) { return ptr::null_mut(); }
    // Execution limits are absent for a debug session (`None`): the step budget
    // and timeout are enforced by the debugger loop, not by the I/O layer, so a
    // zero or magic limit can never masquerade as a reached limit.
    let io = new_session_io(
        Vec::new(),
        None,
        config.timeout_ms,
        config.max_output_bytes,
        None,
    );
    Box::into_raw(Box::new(QfliDebugSession {
        shared: Arc::new(Shared {
            source,
            sysroot,
            backend_path,
            crate_name,
            edition: config.edition,
            crate_type: config.crate_type,
            max_steps: config.max_steps,
            breakpoints,
            state: AtomicU32::new(NEW),
            started: AtomicBool::new(false),
            active_calls: AtomicU32::new(0),
            pause_generation: AtomicU64::new(0),
            revision: AtomicU64::new(0),
            io,
            control: Mutex::new(Control {
                command: None,
                pause_requested: false,
                cancelled: false,
                paused: false,
                finished: false,
                worker_exited: false,
                busy: false,
                terminal: None,
            }),
            control_cv: Condvar::new(),
            snapshot: Mutex::new(Snapshot::new()),
            strings: Mutex::new(StringTable::default()),
            worker: Mutex::new(None),
        }),
    }))
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn qfli_miri_debug_start(session: *mut QfliDebugSession) -> i32 {
    ffi_guard(-1, || unsafe { start(session) })
}

unsafe fn start(session: *mut QfliDebugSession) -> i32 {
    let Some(session) = (unsafe { session.as_ref() }) else { return -1 };
    let Some(call) = ActiveCall::acquire(session.shared.clone()) else { return -1 };
    let shared = &call.0;
    if shared.state.load(Ordering::Acquire) & DESTROYED != 0 {
        return -1;
    }
    if shared.started.swap(true, Ordering::AcqRel) {
        return -1;
    }
    join_worker(shared);
    {
        let mut control = lock(&shared.control);
        control.finished = false;
        control.worker_exited = false;
        control.busy = false;
        control.terminal = None;
    }
    shared.set_state(RUNNING);
    match spawn_worker(shared.clone()) {
        Ok(worker) => *lock(&shared.worker) = Some(worker),
        Err(error) => {
            let _ = shared.io.append(2, format!("unable to start debug worker: {error}\n").as_bytes());
            {
                let mut snapshot = lock(&shared.snapshot);
                snapshot.reason = PAUSE_ERROR;
                snapshot.exit_code = 1;
            }
            shared.set_state(FAILED);
            let mut control = lock(&shared.control);
            control.finished = true;
            control.worker_exited = true;
            return -1;
        }
    }
    let result = wait_for_pause(shared);
    if result != 0 || lock(&shared.control).finished {
        join_worker(shared);
    }
    result
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn qfli_miri_debug_resume(
    session: *mut QfliDebugSession, mode: u32,
) -> i32 {
    ffi_guard(-1, || unsafe { resume(session, mode, None) })
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn qfli_miri_debug_resume_at(
    session: *mut QfliDebugSession, mode: u32, pause_generation: u64,
) -> i32 {
    ffi_guard(-1, || unsafe { resume(session, mode, Some(pause_generation)) })
}

unsafe fn resume(session: *mut QfliDebugSession, mode: u32, generation: Option<u64>) -> i32 {
    let Some(session) = (unsafe { session.as_ref() }) else { return -1 };
    let Some(call) = ActiveCall::acquire(session.shared.clone()) else { return -1 };
    let shared = &call.0;
    if shared.state.load(Ordering::Acquire) & DESTROYED != 0 {
        return -1;
    }
    if mode > RESUME_STEP_OUT {
        return -1;
    }
    {
        let mut control = lock(&shared.control);
        // Only a paused session can resume; anything else is a caller bug and
        // must not silently start execution.
        if !control.paused || control.finished {
            return -1;
        }
        if generation.is_some_and(|generation| {
            generation != shared.pause_generation.load(Ordering::Acquire)
        }) {
            return -1;
        }
        // Invalidate the old pause before notifying the worker. Otherwise the
        // waiting caller can observe `paused == true` and return stale data
        // before even one instruction of its resume command has run.
        control.paused = false;
        control.command = Some(Command::Resume { mode });
        shared.set_state(RUNNING);
        shared.control_cv.notify_all();
    }
    let result = wait_for_pause(shared);
    if lock(&shared.control).finished {
        join_worker(shared);
    }
    result
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn qfli_miri_debug_pause(session: *mut QfliDebugSession) {
    ffi_guard((), || {
        let Some(session) = (unsafe { session.as_ref() }) else { return };
        let shared = &session.shared;
        let mut control = lock(&shared.control);
        if !control.finished && !control.paused {
            control.pause_requested = true;
        }
        shared.control_cv.notify_all();
    });
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn qfli_miri_debug_cancel(session: *mut QfliDebugSession) {
    ffi_guard((), || {
        let Some(session) = (unsafe { session.as_ref() }) else { return };
        let shared = &session.shared;
        shared.io.cancelled.store(true, Ordering::Release);
        let mut control = lock(&shared.control);
        control.cancelled = true;
        if shared.started.load(Ordering::Acquire) && !control.finished {
            shared.set_state(STOPPING);
        }
        shared.control_cv.notify_all();
    });
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn qfli_miri_debug_destroy(session: *mut QfliDebugSession) {
    ffi_guard((), || {
        let Some(session) = (unsafe { session.as_ref() }) else { return };
        let shared = &session.shared;
        // Latch first so no further call can begin.
        if shared.state.fetch_or(DESTROYED, Ordering::AcqRel) & DESTROYED != 0 {
            return;
        }
        {
            let mut control = lock(&shared.control);
            control.cancelled = true;
            shared.io.cancelled.store(true, Ordering::Release);
            shared.control_cv.notify_all();
        }
        // The documented precondition is no in-flight blocking API call. Keep
        // a misused handle allocated instead of freeing underneath that call.
        if shared.active_calls.load(Ordering::Acquire) != 0 {
            return;
        }
        // Cancellation alone is not completion. Join before releasing this
        // handle, source mirror ownership or the frontend's runtime lease.
        join_worker(shared);
        drop(unsafe { Box::from_raw(session as *const QfliDebugSession as *mut QfliDebugSession) });
    });
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn qfli_miri_debug_wait(session: *mut QfliDebugSession) -> i32 {
    ffi_guard(-1, || {
        let Some(session) = (unsafe { session.as_ref() }) else { return -1 };
        let Some(call) = ActiveCall::acquire(session.shared.clone()) else { return -1 };
        let shared = &call.0;
        if !shared.started.load(Ordering::Acquire) {
            return -1;
        }
        let mut control = lock(&shared.control);
        while !control.worker_exited {
            control = shared.control_cv.wait(control).unwrap_or_else(|poison| poison.into_inner());
        }
        drop(control);
        join_worker(shared);
        0
    })
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn qfli_miri_debug_status(
    session: *const QfliDebugSession, status: *mut QfliDebugStatus,
) -> i32 {
    ffi_guard(-1, || {
        let Some(session) = (unsafe { session.as_ref() }) else { return -1 };
        if status.is_null() { return -1; }
        let shared = &session.shared;
        let control = lock(&shared.control);
        let outputs = lock(&shared.io.output);
        // Output buffers are append-only. Adding their total retained length
        // to the transition counter yields a monotone revision for output-only
        // updates without a callback from SessionIo into this module.
        let bytes: u64 = outputs.iter().map(|output| output.len() as u64).sum();
        unsafe {
            status.write(QfliDebugStatus {
                state: shared.state(),
                worker_exited: u32::from(control.worker_exited),
                pause_generation: shared.pause_generation.load(Ordering::Acquire),
                revision: shared.revision.load(Ordering::Acquire).saturating_add(bytes),
            });
        }
        0
    })
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn qfli_miri_debug_pause_info(
    session: *const QfliDebugSession, pause: *mut QfliDebugPause,
) -> i32 {
    ffi_guard(-1, || {
        let Some(session) = (unsafe { session.as_ref() }) else { return -1 };
        if pause.is_null() {
            return -1;
        }
        let _control = lock(&session.shared.control);
        let snapshot = lock(&session.shared.snapshot);
        unsafe {
            pause.write(QfliDebugPause {
                reason: snapshot.reason,
                frame_count: snapshot.frame_count,
                steps: snapshot.steps,
                exit_code: snapshot.exit_code,
            });
        }
        0
    })
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn qfli_miri_debug_frame_count(
    session: *const QfliDebugSession,
) -> usize {
    ffi_guard(0, || {
        let Some(session) = (unsafe { session.as_ref() }) else { return 0 };
        let control = lock(&session.shared.control);
        if !control.paused { return 0; }
        lock(&session.shared.snapshot).frame_count as usize
    })
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn qfli_miri_debug_frame(
    session: *const QfliDebugSession, index: usize, frame: *mut QfliFrame,
) -> i32 {
    ffi_guard(-1, || {
        let Some(session) = (unsafe { session.as_ref() }) else { return -1 };
        if frame.is_null() {
            return -1;
        }
        let control = lock(&session.shared.control);
        if !control.paused { return -1; }
        let snapshot = lock(&session.shared.snapshot);
        let Some(entry) = snapshot.frames.get(index) else { return -1 };
        let strings = lock(&session.shared.strings);
        // Keep the borrow of `strings` alive while the pointers are read.
        let (Some(&file), Some(&function)) =
            (strings.files.get(index), strings.functions.get(index))
        else {
            return -1;
        };
        unsafe {
            frame.write(QfliFrame {
                index: index as u32,
                _pad: 0,
                file_path: file,
                line: entry.line,
                column: entry.column,
                function,
            });
        }
        0
    })
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn qfli_miri_debug_locals(
    session: *const QfliDebugSession, frame_index: usize, buffer: *mut QfliLocal,
    capacity: usize,
) -> usize {
    ffi_guard(0, || {
        let Some(session) = (unsafe { session.as_ref() }) else { return 0 };
        if buffer.is_null() && capacity != 0 {
            return 0;
        }
        let control = lock(&session.shared.control);
        if !control.paused { return 0; }
        let snapshot = lock(&session.shared.snapshot);
        let Some(entry) = snapshot.frames.get(frame_index) else { return 0 };
        let strings = lock(&session.shared.strings);
        let Some(range) = strings.locals.get(frame_index) else { return 0 };
        let count = entry.locals.len();
        for (offset, local) in entry.locals.iter().take(capacity).enumerate() {
            let index = range.start + offset;
            let (Some(&name), Some(&type_name), Some(&value)) = (
                strings.names.get(index),
                strings.types.get(index),
                strings.values.get(index),
            ) else {
                return 0;
            };
            unsafe {
                buffer.add(offset).write(QfliLocal {
                    name,
                    type_name,
                    local: local.local,
                    state: local.state,
                    value,
                });
            }
        }
        count
    })
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn qfli_miri_debug_copy_output(
    session: *const QfliDebugSession, buffer: *mut u8, capacity: usize,
) -> usize {
    unsafe { qfli_miri_debug_copy_output_channel(session, 2, buffer, capacity) }
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn qfli_miri_debug_copy_output_channel(
    session: *const QfliDebugSession, channel: u32, buffer: *mut u8, capacity: usize,
) -> usize {
    ffi_guard(0, || {
        let Some(session) = (unsafe { session.as_ref() }) else { return 0 };
        let outputs = lock(&session.shared.io.output);
        let Some(output) = outputs.get(channel as usize) else { return 0 };
        if !buffer.is_null() && capacity != 0 {
            unsafe { ptr::copy_nonoverlapping(output.as_ptr(), buffer, capacity.min(output.len())) };
        }
        output.len()
    })
}
