#ifndef QFLI_MIRI_H
#define QFLI_MIRI_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct QfliSession QfliSession;

enum QfliState {
    QFLI_READY = 0,
    QFLI_RUNNING = 1,
    QFLI_FINISHED = 2,
    QFLI_CANCELLED = 3,
    QFLI_LIMIT_REACHED = 4,
    QFLI_INTERNAL_ERROR = 5
};

enum QfliOutput { QFLI_STDOUT = 0, QFLI_STDERR = 1, QFLI_DIAGNOSTICS = 2 };

typedef struct {
    uint32_t abi_version;
    const char *source_path;
    const char *sysroot_path;
    const uint8_t *stdin_data;
    size_t stdin_len;
    uint64_t max_basic_blocks;
    uint64_t timeout_ms;
    size_t max_output_bytes;
    /* Live Miri allocation payload bytes, including interpreter globals. */
    uint64_t max_guest_memory_bytes;
} QfliConfig;

typedef struct {
    uint32_t state;
    int32_t exit_code;
    uint64_t basic_blocks;
    uint64_t peak_guest_memory_bytes;
} QfliResult;

/* Legacy reserved value retained for source compatibility. Never emitted as
 * a session status or return code. qfli_miri_analyze returns 2 when busy. */
enum QfliAnalysisState { QFLI_BUSY = 6 };

enum QfliAnalysisCrateType {
    QFLI_ANALYSIS_CRATE_BIN = 0,
    QFLI_ANALYSIS_CRATE_LIB = 1
};

uint32_t qfli_miri_abi_version(void);
/* Inputs are copied. Paths must exist and be absolute; output limit >=1024. */
QfliSession *qfli_miri_create(const QfliConfig *config);
/* Optional ABI-1 extension. NULL backend_path uses the original default.
 * Non-NULL is an absolute UTF-8 native library/framework executable path,
 * copied by create. Invalid paths or a conflicting process backend return NULL.
 * The first successful create fixes the backend for the process; destroying a
 * session does not reset it. Load/init errors appear in diagnostics during run.
 * Keep the adapter and its compiler/backend libraries loaded until process exit. */
QfliSession *qfli_miri_create_with_backend(const QfliConfig *config,
                                         const char *backend_path);
/* Optional ABI-1 extension. Explicit absolute project root, copied by create;
 * the canonical source must be contained in it. Guest filesystem operations
 * stay inside this root, with session-local cwd/temp and no network access.
 * Linux/Android/OHOS implement disk I/O; other hosts retain isolated execution.
 * The older create functions use the source's containing directory as root.
 * No process-wide chdir occurs. backend_path may be NULL. */
QfliSession *qfli_miri_create_with_project(const QfliConfig *config,
                                         const char *backend_path,
                                         const char *project_root);
/* Blocking: invoke on a worker. 0 means accepted, -1 means invalid/busy. */
int32_t qfli_miri_run(QfliSession *session);
/* Concurrent-safe. Checks at rustc phase callbacks and MIR block terminators.
 * Final exit codes: cancellation=130, resource limit=124, internal error=1.
 * Limits do not cap rustc host memory or preempt an active compiler query. */
void qfli_miri_cancel(QfliSession *session);
/* Returns full byte length; copies min(capacity, length), without a NUL. */
size_t qfli_miri_copy_output(const QfliSession *session, uint32_t channel,
                           uint8_t *buffer, size_t capacity);
int32_t qfli_miri_result(const QfliSession *session, QfliResult *result);
/* No calls may be active when destroy is invoked. `destroy` latches the
 * session first, so a `run`/`analyze` that has not started yet is rejected
 * instead of racing; a session with a call already in flight is not freed
 * (it leaks) rather than being erased under the worker. */
void qfli_miri_destroy(QfliSession *session);

/* ---- Analysis-only ABI-1 extension ------------------------------------
 * Additive: the layouts and behaviour above are unchanged. Look these symbols
 * up optionally; their absence means this build has no analysis backend.
 * Analysis compiles the crate with the pinned rustc and stops before Miri
 * evaluation. It never executes user code, cargo, build scripts or proc
 * macros, never sets `cfg(miri)`, and writes no files.
 */

typedef struct {
    uint32_t abi_version;     /* must be 1 */
    const char *source_path;  /* absolute UTF-8 crate root, copied */
    const char *sysroot_path; /* absolute UTF-8 guest sysroot, copied */
    /* 1..=64 bytes of [A-Za-z0-9_]. Affects hygiene/crate-path diagnostics. */
    const char *crate_name;
    uint32_t edition;    /* 2015, 2018, 2021 or 2024 */
    uint32_t crate_type; /* enum QfliAnalysisCrateType */
    /* Includes time spent waiting for the compiler to become available. */
    uint64_t timeout_ms;
    /* Diagnostics channel bound, 1024 ..= 16 MiB. */
    size_t max_output_bytes;
} QfliAnalysisConfig;

/* Same validation, copying and backend identity rules as qfli_miri_create.
 * NULL backend_path uses the default backend resolution. Returns NULL on
 * invalid input, missing files, or a backend identity conflict. */
QfliSession *qfli_miri_create_analysis(const QfliAnalysisConfig *config,
                                      const char *backend_path);
/* Blocking: invoke on a worker. Diagnostics are JSON Lines on QFLI_DIAGNOSTICS.
 * Returns 0 when the session reached a terminal state, 2 when another
 * run/analyze holds the compiler (session not consumed and may be retried;
 * `QfliResult.state` is left untouched by a busy answer), and -1 for a null,
 * already-used, destroying or rejected session.
 * Completed analysis reports state FINISHED and exit 0 even when the source has
 * errors: read the diagnostics, not the exit status. Cancelled = state 3 /
 * exit 130, limit or timeout = state 4 / exit 124, and a compiler abort that
 * produced no diagnostics at all = state 5 / exit 1. */
int32_t qfli_miri_analyze(QfliSession *session);

#ifdef __cplusplus
}
#endif
#endif
