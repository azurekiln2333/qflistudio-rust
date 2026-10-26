/* QFLI Miri adapter: interactive debugging ABI.
 *
 * This is a *separate*, optional extension to the ABI-1 run/analysis surface.
 * It lives in its own header and its own shared-library symbols so that an
 * adapter without a debugger simply fails the symbol lookup, exactly like the
 * analysis extension does.
 *
 * Everything here is backed by real Miri interpreter state: the session drives
 * the pinned Miri `create_ecx` + `miri_step` loop and reports positions that
 * rustc's own `SourceMap` produced. There are no simulated breakpoints and no
 * invented variable values. A capability that cannot be implemented truthfully
 * is reported as unsupported rather than approximated.
 *
 * As with pinned Priroda, this public-API stepping loop does not perform Miri's
 * heap-leak validation at exit: the extra static-root set needed for a correct
 * check is private. Normal execution retains its own full termination checks.
 * Debugging still reports actual program exit codes, execution UB/errors,
 * abandoned threads, cancellation and resource limits.
 *
 * Layout guarantees:
 *   - No existing struct (`QfliConfig`, `QfliResult`, `QfliAnalysisConfig`) is
 *     modified. Every type below is new.
 *   - The debug session is an opaque type, distinct from `QfliSession`.
 */
#ifndef QFLI_DEBUG_H
#define QFLI_DEBUG_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Opaque interactive debug session. Never cast to/from QfliSession. */
typedef struct QfliDebugSession QfliDebugSession;

/* ---- configuration ---------------------------------------------------- */

enum QfliDebugCrateType {
    QFLI_DEBUG_CRATE_BIN = 0, /* crate root must define `main` */
    QFLI_DEBUG_CRATE_LIB = 1  /* analysed as a library; entry may be absent */
};

/* A source breakpoint. `file_path` must match what rustc reports for the
 * span (the adapter passes an absolute crate root, so project spans carry the
 * absolute path). Matching is by (file, line); `column == 0` means the whole
 * line. */
typedef struct {
    const char *file_path; /* absolute UTF-8, copied by create */
    uint32_t line;         /* 1-based */
    uint32_t column;       /* 1-based, 0 = whole line */
} QfliBreakpoint;

typedef struct {
    uint32_t abi_version;     /* must be 1 */
    const char *source_path;  /* absolute UTF-8 crate root, copied */
    const char *sysroot_path; /* absolute UTF-8 MIR-encoded sysroot, copied */
    const char *crate_name;   /* 1..=64 bytes of [A-Za-z0-9_] */
    uint32_t edition;         /* 2015, 2018, 2021 or 2024 */
    uint32_t crate_type;      /* enum QfliDebugCrateType */
    /* Wall-clock budget from compiler acquisition, including time paused.
     * Checked at phase/step boundaries and periodically while paused; cannot
     * preempt an in-flight compiler query. Creating an idle handle starts no
     * timer. A compiler-busy start does not consume the handle. */
    uint64_t timeout_ms;
    /* Hard budget of interpreter steps after reaching the entry function.
     * Runtime bootstrap is separately capped at one million transitions and
     * obeys the wall-clock budget. Must be > 0. */
    uint64_t max_steps;
    /* Combined bound for stdout/stderr/diagnostics, 1024 ..= 16 MiB. */
    size_t max_output_bytes;
    /* Breakpoints installed before the first step, so the entry point is never
     * silently executed past a breakpoint the caller asked for. May be NULL
     * when `breakpoint_count` is 0. */
    const QfliBreakpoint *breakpoints;
    size_t breakpoint_count;
} QfliDebugConfig;

/* ---- pause reporting -------------------------------------------------- */

/* Why the session is currently not running. Exactly one of these is reported
 * per pause, and each corresponds to a condition the stepping loop actually
 * observed. */
enum QfliDebugPauseReason {
    /* Reached the real entry frame before its first instruction. Standard
     * runtime setup/global constructors may have executed to reach it. */
    QFLI_DEBUG_PAUSE_ENTRY = 0,
    /* The current source line is a caller-supplied breakpoint. */
    QFLI_DEBUG_PAUSE_BREAKPOINT = 1,
    /* A step-in/over/out completed. */
    QFLI_DEBUG_PAUSE_STEP = 2,
    /* `qfli_miri_debug_pause` was requested. */
    QFLI_DEBUG_PAUSE_REQUESTED = 3,
    /* The interpreted program terminated normally (see `exit_code`). */
    QFLI_DEBUG_PAUSE_TERMINATED = 4,
    /* Miri reported an error/UB. The text is on the diagnostics channel. */
    QFLI_DEBUG_PAUSE_ERROR = 5,
    /* `max_steps`, the timeout, or the output bound was reached. */
    QFLI_DEBUG_PAUSE_LIMIT = 6,
    /* Explicit stop/cancel; exit_code == 130, never a fabricated user exit. */
    QFLI_DEBUG_PAUSE_CANCELLED = 7
};

typedef struct {
    uint32_t reason;     /* enum QfliDebugPauseReason */
    uint32_t frame_count;/* depth of the active thread's stack at the pause */
    uint64_t steps;      /* interpreter steps since reaching the entry frame */
    int32_t exit_code;   /* terminal: actual user exit, cancelled=130, limit=124 */
} QfliDebugPause;

enum QfliDebugState {
    QFLI_DEBUG_NEW = 0,
    QFLI_DEBUG_RUNNING = 1,
    QFLI_DEBUG_PAUSED = 2,
    QFLI_DEBUG_TERMINATED = 3,
    QFLI_DEBUG_FAILED = 4,
    QFLI_DEBUG_STOPPING = 5
};

typedef struct {
    uint32_t state;          /* enum QfliDebugState */
    /* Compiler callbacks have unwound and the process compiler lease is free.
     * qfli_miri_debug_wait/destroy additionally joins the actual OS worker. */
    uint32_t worker_exited;
    /* Increases at each actual pause, zero before entry. Only a paused state's
     * generation is a valid token for qfli_miri_debug_resume_at. */
    uint64_t pause_generation;
    /* Monotone observable-state revision, including output-only growth. */
    uint64_t revision;
} QfliDebugStatus;

/* One stack frame. `index == 0` is the innermost (current) frame. */
typedef struct {
    uint32_t index;
    uint32_t _pad;
    /* Absolute path of the current source position, or an empty string when
     * the frame has no source position (e.g. a synthetic frame). */
    const char *file_path;
    uint32_t line;    /* 1-based, 0 when unavailable */
    uint32_t column;  /* 1-based char column, 0 when unavailable */
    /* Mangled-free rendered function name, e.g. `qfli_fixture::add`. */
    const char *function;
} QfliFrame;

/* Availability of a local's value. Reported explicitly instead of omitting the
 * local, so a frontend can show "uninitialized" rather than silently hiding a
 * variable that exists in the source. */
enum QfliLocalState {
    QFLI_LOCAL_VALUE = 0,       /* `value` holds a rendering */
    QFLI_LOCAL_UNINITIALIZED = 1, /* not live yet, or already dead */
    QFLI_LOCAL_UNSUPPORTED = 2  /* live, but this adapter cannot render it */
};

typedef struct {
    /* Source name from debug info, or an empty string for an unnamed MIR local
     * (temporaries). */
    const char *name;
    /* Rust type as rustc prints it, e.g. `i32`, `&str`, `[i32; 3]`. */
    const char *type_name;
    uint32_t local;      /* MIR local index within the frame */
    uint32_t state;      /* enum QfliLocalState */
    /* Rendering when `state == QFLI_LOCAL_VALUE`, otherwise empty. Scalar
     * values are rendered exactly; aggregates are reported as UNSUPPORTED
     * rather than guessed. */
    const char *value;
} QfliLocal;

/* ---- lifecycle -------------------------------------------------------- */

enum QfliDebugResume {
    QFLI_DEBUG_CONTINUE = 0, /* run to the next breakpoint or termination */
    QFLI_DEBUG_STEP_IN = 1,  /* stop at the next visible source position */
    QFLI_DEBUG_STEP_OVER = 2,/* like STEP_IN, but do not descend into calls */
    QFLI_DEBUG_STEP_OUT = 3  /* run until the current frame returns */
};

/* Returns NULL on invalid input, a missing file, or a backend identity
 * conflict with an already-created session in this process. */
QfliDebugSession *qfli_miri_debug_create(const QfliDebugConfig *config,
                                        const char *backend_path);

/* Compiles the crate and runs to the first pause (the entry breakpoint).
 * Blocking: call on a worker thread. Returns
 *   0  paused or normally terminated/cancelled/limited; inspect status/reason
 *   2  compiler busy (another session holds it); nothing was consumed
 *  -1  invalid call or compiler/interpreter failure; inspect diagnostics
 * A successful start is single-use. A busy start is retryable. */
int32_t qfli_miri_debug_start(QfliDebugSession *session);

/* Resume from a pause. `mode` is one of enum QfliDebugResume. Same return codes
 * as `qfli_miri_debug_start`. Returns -1 if the session is not paused. */
int32_t qfli_miri_debug_resume(QfliDebugSession *session, uint32_t mode);

/* Generation-checked resume. Rejects stale pause tokens with -1 without
 * advancing the interpreter. Invalidate the token as soon as resume begins. */
int32_t qfli_miri_debug_resume_at(QfliDebugSession *session, uint32_t mode,
                                 uint64_t pause_generation);

/* Read-only polling, safe during start/resume. No terminal state is published
 * while the compiler lock is held. A busy start returns NEW/worker_exited=1. */
int32_t qfli_miri_debug_status(const QfliDebugSession *session,
                              QfliDebugStatus *status);

/* Requests a pause at the next step boundary. Safe from any thread, including
 * while the session is running. Takes effect at the next boundary; a program
 * blocked inside a single long step is not interrupted. */
void qfli_miri_debug_pause(QfliDebugSession *session);

/* Cancels the session. Safe from any thread. A paused session wakes up and
 * reports QFLI_DEBUG_PAUSE_CANCELLED; a running session stops at the next
 * boundary. */
void qfli_miri_debug_cancel(QfliDebugSession *session);

/* Blocks until actual worker exit and joins it, returning 0. Call after a stop
 * request or terminal status, with no start/resume in flight. Returns -1 for
 * NULL, an unstarted/busy-retry handle, or an overlapping blocking call. */
int32_t qfli_miri_debug_wait(QfliDebugSession *session);

/* Cancels, joins the worker, and frees the session. Blocking: invoke on a
 * worker. Must not be called while any other ABI call is in flight;
 * such a session is latched and leaked instead of being freed under the
 * worker. */
void qfli_miri_debug_destroy(QfliDebugSession *session);

/* ---- snapshot readers (valid while paused) --------------------------- */

/* Copies the current pause into `*pause`. Returns 0 on success, -1 on invalid
 * arguments. */
int32_t qfli_miri_debug_pause_info(const QfliDebugSession *session,
                                  QfliDebugPause *pause);

/* Number of frames on the active thread's stack, or 0. */
size_t qfli_miri_debug_frame_count(const QfliDebugSession *session);

/* Copies frame `index` into `*frame`. The strings it points to stay valid until
 * the next resume/destroy, including across automatic paused timeout. Returns
 * 0, or -1 for a bad index/argument or a nonpaused session. */
int32_t qfli_miri_debug_frame(const QfliDebugSession *session, size_t index,
                             QfliFrame *frame);

/* Copies up to `capacity` locals of frame `frame_index` into `buffer` and
 * returns the total number of locals available (which may exceed `capacity`).
 * Returns 0 on invalid arguments. Strings stay valid until the next
 * resume/destroy. */
size_t qfli_miri_debug_locals(const QfliDebugSession *session,
                             size_t frame_index, QfliLocal *buffer,
                             size_t capacity);

/* Diagnostics / Miri output for this session (channel 2). Same contract as
 * `qfli_miri_copy_output`: returns the full length and copies
 * min(capacity, length) bytes. */
size_t qfli_miri_debug_copy_output(const QfliDebugSession *session,
                                  uint8_t *buffer, size_t capacity);

/* Live output for a channel: 0 stdout, 1 stderr, 2 diagnostics. Invalid channel
 * returns 0. Buffers are retained append-only up to the combined configured
 * budget; read status/reason to distinguish resource limits from clean exit. */
size_t qfli_miri_debug_copy_output_channel(const QfliDebugSession *session,
                                          uint32_t channel, uint8_t *buffer,
                                          size_t capacity);

/* ---- capability discovery -------------------------------------------- */

/* Bit set of enum QfliDebugCapability. A frontend must check this before
 * offering a control; the adapter reports only what it can really do. */
enum QfliDebugCapability {
    QFLI_DEBUG_CAP_BREAKPOINTS = 1u << 0,
    QFLI_DEBUG_CAP_STEP_IN = 1u << 1,
    QFLI_DEBUG_CAP_STEP_OVER = 1u << 2,
    QFLI_DEBUG_CAP_STEP_OUT = 1u << 3,
    QFLI_DEBUG_CAP_LOCALS = 1u << 4,
    /* Source breakpoints match on the call site of a macro expansion. */
    QFLI_DEBUG_CAP_MACRO_CALLSITE = 1u << 5,
    QFLI_DEBUG_CAP_PAUSE = 1u << 6,
    QFLI_DEBUG_CAP_LIVE_OUTPUT = 1u << 7,
    QFLI_DEBUG_CAP_GENERATIONAL_COMMANDS = 1u << 8
};

uint32_t qfli_miri_debug_capabilities(void);

#ifdef __cplusplus
}
#endif

#endif /* QFLI_DEBUG_H */
