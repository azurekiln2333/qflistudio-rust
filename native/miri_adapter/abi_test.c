#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0600
#endif
#else
#define _POSIX_C_SOURCE 200809L
#endif
#include "qfli_miri.h"

#undef NDEBUG
#include <assert.h>
#include <inttypes.h>
#ifdef _WIN32
#include <windows.h>
typedef HMODULE NativeLibrary;
typedef HANDLE NativeThread;
#else
#include <dlfcn.h>
#include <pthread.h>
#include <time.h>
typedef void *NativeLibrary;
typedef pthread_t NativeThread;
#endif
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static QfliSession *(*create_session)(const QfliConfig *);
static QfliSession *(*create_with_backend)(const QfliConfig *, const char *);
static int32_t (*run_session)(QfliSession *);
static void (*cancel_session)(QfliSession *);
static size_t (*copy_output)(const QfliSession *, uint32_t, uint8_t *, size_t);
static int32_t (*get_result)(const QfliSession *, QfliResult *);
static void (*destroy_session)(QfliSession *);
static const char *backend_path;

static NativeLibrary open_library(const char *path) {
#ifdef _WIN32
    int count = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, path, -1, NULL, 0);
    if (!count) { fprintf(stderr, "Invalid UTF-8 library path\n"); return NULL; }
    wchar_t *wide_path = calloc((size_t)count, sizeof(wchar_t));
    assert(wide_path);
    assert(MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, path, -1, wide_path, count));
    NativeLibrary library = LoadLibraryW(wide_path);
    free(wide_path);
    if (!library) { fprintf(stderr, "LoadLibrary failed: %lu\n", GetLastError()); }
#else
    NativeLibrary library = dlopen(path, RTLD_NOW | RTLD_LOCAL);
    if (!library) { fprintf(stderr, "%s\n", dlerror()); }
#endif
    return library;
}

static void *library_symbol(NativeLibrary library, const char *name) {
#ifdef _WIN32
    return (void *)GetProcAddress(library, name);
#else
    return dlsym(library, name);
#endif
}

static uint64_t monotonic_ms(void) {
#ifdef _WIN32
    return GetTickCount64();
#else
    struct timespec now;
    assert(clock_gettime(CLOCK_MONOTONIC, &now) == 0);
    return (uint64_t)now.tv_sec * 1000 + (uint64_t)now.tv_nsec / 1000000;
#endif
}

static void poll_delay(void) {
#ifdef _WIN32
    Sleep(1);
#else
    struct timespec delay = { .tv_nsec = 1000000 };
    nanosleep(&delay, NULL);
#endif
}

static char *copy_text(const char *text) {
    size_t length = strlen(text) + 1;
    char *copy = malloc(length);
    assert(copy);
    memcpy(copy, text, length);
    return copy;
}

static QfliSession *create_config(const QfliConfig *config) {
    if (!backend_path) { return create_session(config); }
    char *path_copy = copy_text(backend_path);
    QfliSession *session = create_with_backend(config, path_copy);
    memset(path_copy, 0, strlen(path_copy));
    free(path_copy);
    return session;
}

static char *output(QfliSession *session, uint32_t channel) {
    size_t length = copy_output(session, channel, NULL, 0);
    char *text = calloc(length + 1, 1);
    assert(text);
    assert(copy_output(session, channel, (uint8_t *)text, length) == length);
    return text;
}

static QfliSession *new_session(const char *source, const char *sysroot,
                              const char *input, uint64_t blocks, size_t bytes) {
    char *source_copy = copy_text(source);
    char *sysroot_copy = copy_text(sysroot);
    char *input_copy = copy_text(input);
    QfliConfig config = {
        .abi_version = 1, .source_path = source_copy, .sysroot_path = sysroot_copy,
        .stdin_data = (const uint8_t *)input_copy, .stdin_len = strlen(input_copy),
        .max_basic_blocks = blocks, .timeout_ms = 30000,
        .max_output_bytes = bytes,
        .max_guest_memory_bytes = 32 * 1024 * 1024,
    };
    QfliSession *session = create_config(&config);
    memset(source_copy, 0, strlen(source_copy));
    memset(sysroot_copy, 0, strlen(sysroot_copy));
    memset(input_copy, 0, strlen(input_copy));
    free(source_copy); free(sysroot_copy); free(input_copy);
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
        fprintf(stderr, "%s failed state=%u exit=%d blocks=%" PRIu64 "\nstdout: %s\nstderr: %s\ndiag: %s\n",
                name, result.state, result.exit_code,
                result.basic_blocks, out, err, diag);
        abort();
    }
    assert(run_session(session) == -1);
    free(out); free(err); free(diag);
    destroy_session(session);
    printf("PASS %s\n", name);
}

#ifdef _WIN32
static DWORD WINAPI run_thread(void *session) {
#else
static void *run_thread(void *session) {
#endif
    assert(run_session(session) == 0);
#ifdef _WIN32
    return 0;
#else
    return NULL;
#endif
}

static NativeThread start_run(QfliSession *session) {
#ifdef _WIN32
    NativeThread thread = CreateThread(NULL, 0, run_thread, session, 0, NULL);
    assert(thread);
#else
    NativeThread thread;
    assert(pthread_create(&thread, NULL, run_thread, session) == 0);
#endif
    return thread;
}

static void join_run(NativeThread thread) {
#ifdef _WIN32
    assert(WaitForSingleObject(thread, INFINITE) == WAIT_OBJECT_0);
    assert(CloseHandle(thread));
#else
    assert(pthread_join(thread, NULL) == 0);
#endif
}

static void interruption(const char *directory, const char *sysroot, int cancel) {
    char source[4096];
    snprintf(source, sizeof(source), "%s/cancel.rs", directory);
    QfliSession *session = new_session(source, sysroot, "", cancel ? UINT64_MAX : 2000, 1048576);
    NativeThread thread = start_run(session);
    if (cancel) {
        QfliResult current;
        uint64_t deadline = monotonic_ms() + 30000;
        do {
            poll_delay();
            assert(get_result(session, &current) == 0);
            assert(monotonic_ms() < deadline);
        } while (current.basic_blocks < 2000
                 && (current.state == QFLI_READY || current.state == QFLI_RUNNING));
        assert(current.state == QFLI_RUNNING && current.basic_blocks >= 2000);
        cancel_session(session);
    }
    join_run(thread);
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
    QfliSession *session = create_config(&config);
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

static QfliConfig backend_config(const char *directory, const char *sysroot, char *source, size_t capacity) {
    snprintf(source, capacity, "%s/modules_generics.rs", directory);
    return (QfliConfig) {
        .abi_version = 1, .source_path = source, .sysroot_path = sysroot,
        .max_basic_blocks = 10000000, .timeout_ms = 30000,
        .max_output_bytes = 1048576, .max_guest_memory_bytes = 32 * 1024 * 1024,
    };
}

static void backend_validation(const char *directory, const char *sysroot, int after_run) {
    char source[4096];
    QfliConfig config = backend_config(directory, sysroot, source, sizeof(source));
    assert(!create_with_backend(&config, "relative-backend.so"));
    char missing[4096];
    snprintf(missing, sizeof(missing), "%s/missing-backend.so", directory);
    assert(!create_with_backend(&config, missing));
    if (after_run) {
        // An existing file with a different identity must not reuse the cached factory.
        assert(!create_with_backend(&config, source));
        QfliSession *same = create_with_backend(&config, backend_path);
        assert(same);
        destroy_session(same);
        puts("PASS backend identity and copied configuration");
    }
}

static void backend_failure(const char *directory, const char *sysroot) {
    char source[4096];
    QfliConfig config = backend_config(directory, sysroot, source, sizeof(source));
    // A Rust source is an existing file but never a loadable compiler backend.
    QfliSession *session = create_with_backend(&config, source);
    assert(session && run_session(session) == 0);
    QfliResult result;
    assert(get_result(session, &result) == 0);
    char *diag = output(session, QFLI_DIAGNOSTICS);
    assert(result.exit_code == 1);
    assert(result.state == QFLI_FINISHED || result.state == QFLI_INTERNAL_ERROR);
    assert(copy_output(session, QFLI_STDOUT, NULL, 0) == 0);
    assert(strstr(diag, "codegen backend"));
    free(diag);
    destroy_session(session);
    puts("PASS backend load failure diagnostics");
}

int main(int argc, char **argv) {
    if (argc != 4 && argc != 5) {
        fprintf(stderr, "Usage: %s <adapter-library> <MIR-sysroot> <fixture-directory> [backend-library|--backend-failure]\n", argv[0]);
        return 2;
    }
    NativeLibrary library = open_library(argv[1]);
    if (!library) { return 1; }
    uint32_t (*version)(void) = library_symbol(library, "qfli_miri_abi_version");
    assert(version && version() == 1);
    create_session = library_symbol(library, "qfli_miri_create");
    create_with_backend = library_symbol(library, "qfli_miri_create_with_backend");
    run_session = library_symbol(library, "qfli_miri_run");
    cancel_session = library_symbol(library, "qfli_miri_cancel");
    copy_output = library_symbol(library, "qfli_miri_copy_output");
    get_result = library_symbol(library, "qfli_miri_result");
    destroy_session = library_symbol(library, "qfli_miri_destroy");
    assert(create_session && create_with_backend && run_session && cancel_session
           && copy_output && get_result && destroy_session);
    assert(!create_session(NULL));
    assert(!create_with_backend(NULL, NULL));
    assert(run_session(NULL) == -1);
    assert(get_result(NULL, NULL) == -1);
    cancel_session(NULL);
    destroy_session(NULL);
    backend_validation(argv[3], argv[2], 0);
    if (argc == 5 && !strcmp(argv[4], "--backend-failure")) {
        backend_failure(argv[3], argv[2]);
        return 0;
    }
    backend_path = argc == 5 ? argv[4] : NULL;
    fixture(argv[3], argv[2], "modules_generics", "", "total=12\n", "items=3\n", 0, NULL);
    backend_validation(argv[3], argv[2], 1);
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
    // rustc/backend process-global state remains live; do not unload the compiler.
    return 0;
}
