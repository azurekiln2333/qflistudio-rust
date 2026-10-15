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
/* No calls may be active when destroy is invoked. */
void qfli_miri_destroy(QfliSession *session);

#ifdef __cplusplus
}
#endif
#endif
