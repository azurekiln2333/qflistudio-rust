#define _POSIX_C_SOURCE 200809L
#include "qfli_miri.h"

#include <assert.h>
#include <dlfcn.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static QfliSession *(*create_session)(const QfliConfig *);
static int32_t (*run_session)(QfliSession *);
static void (*cancel_session)(QfliSession *);
static size_t (*copy_output)(const QfliSession *, uint32_t, uint8_t *, size_t);
static int32_t (*get_result)(const QfliSession *, QfliResult *);
static void (*destroy_session)(QfliSession *);

static char *output(QfliSession *session, uint32_t channel) {
    size_t length = copy_output(session, channel, NULL, 0);
    char *text = calloc(length + 1, 1);
    assert(text);
    assert(copy_output(session, channel, (uint8_t *)text, length) == length);
    return text;
}

static QfliSession *new_session(const char *source, const char *sysroot,
                              const char *input, uint64_t blocks, size_t bytes) {
    QfliConfig config = {
        .abi_version = 1, .source_path = source, .sysroot_path = sysroot,
        .stdin_data = (const uint8_t *)input, .stdin_len = strlen(input),
        .max_basic_blocks = blocks, .timeout_ms = 30000,
        .max_output_bytes = bytes,
        .max_guest_memory_bytes = 32 * 1024 * 1024,
    };
    QfliSession *session = create_session(&config);
    assert(session);
    return session;
}

static void fixture(const char *directory, const char *sysroot, const char *name,
                    const char *input, const char *expected_stdout,
                    const char *expected_stderr, int exit_code, const char *diagnostic) {
    char source[4096];
    snprintf(source, sizeof(source), "%s/%s.rs", directory, name);
    QfliSession *session = new_session(source, sysroot, input, 10000000, 1048576);
    assert(run_session(session) == 0);
    QfliResult result;
    assert(get_result(session, &result) == 0);
    char *out = output(session, QFLI_STDOUT);
    char *err = output(session, QFLI_STDERR);
    char *diag = output(session, QFLI_DIAGNOSTICS);
    if (result.state != QFLI_FINISHED || result.exit_code != exit_code
        || strcmp(out, expected_stdout) || strcmp(err, expected_stderr)
        || (diagnostic && !strstr(diag, diagnostic))) {
        fprintf(stderr, "%s failed state=%u exit=%d blocks=%llu\nstdout: %s\nstderr: %s\ndiag: %s\n",
                name, result.state, result.exit_code,
                (unsigned long long)result.basic_blocks, out, err, diag);
        abort();
    }
    assert(run_session(session) == -1);
    free(out); free(err); free(diag);
    destroy_session(session);
    printf("PASS %s\n", name);
}

static void *run_thread(void *session) {
    assert(run_session(session) == 0);
    return NULL;
}

static void interruption(const char *directory, const char *sysroot, int cancel) {
    char source[4096];
    snprintf(source, sizeof(source), "%s/cancel.rs", directory);
    QfliSession *session = new_session(source, sysroot, "", cancel ? UINT64_MAX : 2000, 1048576);
    pthread_t thread;
    assert(pthread_create(&thread, NULL, run_thread, session) == 0);
    if (cancel) {
        QfliResult current;
        struct timespec delay = { .tv_nsec = 1000000 };
        struct timespec deadline;
        clock_gettime(CLOCK_MONOTONIC, &deadline);
        deadline.tv_sec += 30;
        do {
            nanosleep(&delay, NULL);
            assert(get_result(session, &current) == 0);
            struct timespec now;
            clock_gettime(CLOCK_MONOTONIC, &now);
            assert(now.tv_sec < deadline.tv_sec);
        } while (current.basic_blocks < 2000
                 && (current.state == QFLI_READY || current.state == QFLI_RUNNING));
        assert(current.state == QFLI_RUNNING && current.basic_blocks >= 2000);
        cancel_session(session);
    }
    assert(pthread_join(thread, NULL) == 0);
    QfliResult result;
    assert(get_result(session, &result) == 0);
    if (result.state != (cancel ? QFLI_CANCELLED : QFLI_LIMIT_REACHED)
        || result.exit_code != (cancel ? 130 : 124)) {
        char *diag = output(session, QFLI_DIAGNOSTICS);
        fprintf(stderr, "interrupt failed state=%u exit=%d diag=%s\n", result.state, result.exit_code, diag);
        abort();
    }
    destroy_session(session);
    puts(cancel ? "PASS concurrent cancellation" : "PASS basic block limit");
}

static void limit(const char *directory, const char *sysroot, const char *name,
                  size_t output_bytes, uint64_t timeout_ms, const char *reason) {
    char source[4096];
    snprintf(source, sizeof(source), "%s/%s.rs", directory, name);
    QfliConfig config = {
        .abi_version = 1, .source_path = source, .sysroot_path = sysroot,
        .max_basic_blocks = 10000000, .timeout_ms = timeout_ms,
        .max_output_bytes = output_bytes, .max_guest_memory_bytes = 32 * 1024 * 1024,
    };
    QfliSession *session = create_session(&config);
    assert(session && run_session(session) == 0);
    QfliResult result;
    assert(get_result(session, &result) == 0);
    char *diag = output(session, QFLI_DIAGNOSTICS);
    if (result.state != QFLI_LIMIT_REACHED || result.exit_code != 124 || !strstr(diag, reason)) {
        fprintf(stderr, "%s limit failed state=%u exit=%d diag=%s\n", name, result.state, result.exit_code, diag);
        abort();
    }
    assert(result.peak_guest_memory_bytes <= config.max_guest_memory_bytes);
    free(diag);
    destroy_session(session);
    printf("PASS %s limit\n", reason);
}

int main(int argc, char **argv) {
    if (argc != 4) {
        fprintf(stderr, "Usage: %s <adapter.so> <MIR-sysroot> <fixture-directory>\n", argv[0]);
        return 2;
    }
    void *library = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
    if (!library) { fprintf(stderr, "%s\n", dlerror()); return 1; }
    uint32_t (*version)(void) = dlsym(library, "qfli_miri_abi_version");
    assert(version && version() == 1);
    create_session = dlsym(library, "qfli_miri_create");
    run_session = dlsym(library, "qfli_miri_run");
    cancel_session = dlsym(library, "qfli_miri_cancel");
    copy_output = dlsym(library, "qfli_miri_copy_output");
    get_result = dlsym(library, "qfli_miri_result");
    destroy_session = dlsym(library, "qfli_miri_destroy");
    assert(create_session && run_session && cancel_session && copy_output && get_result && destroy_session);
    assert(!create_session(NULL));
    assert(run_session(NULL) == -1);
    assert(get_result(NULL, NULL) == -1);
    cancel_session(NULL);
    destroy_session(NULL);
    fixture(argv[3], argv[2], "modules_generics", "", "total=12\n", "items=3\n", 0, NULL);
    fixture(argv[3], argv[2], "stdin", "rust\n", "input=rust\n", "", 0, NULL);
    fixture(argv[3], argv[2], "nonzero", "", "before-exit\n", "", 7, NULL);
    fixture(argv[3], argv[2], "invalid_borrow", "", "", "", 1, "E0502");
    fixture(argv[3], argv[2], "invalid_type", "", "", "", 1, "E0308");
    interruption(argv[3], argv[2], 0);
    interruption(argv[3], argv[2], 1);
    limit(argv[3], argv[2], "limit_memory", 1048576, 30000, "guest memory");
    limit(argv[3], argv[2], "limit_output", 1024, 30000, "output");
    limit(argv[3], argv[2], "cancel", 1048576, 1, "time");
    fixture(argv[3], argv[2], "memory_reuse", "", "reused\n", "", 0, NULL);
    fixture(argv[3], argv[2], "modules_generics", "", "total=12\n", "items=3\n", 0, NULL);
    // rustc/LLVM process-global state remains live; do not dlclose the compiler.
    return 0;
}
