// Optional ABI-1 analysis-only extension test.
//
// Exercises qfli_miri_create_analysis / qfli_miri_analyze against a real built
// adapter. It never interprets user code for the analysis assertions: the
// point is that analysis produces structured diagnostics without execution.
//
// Expected diagnostics were recorded from the pinned rustc 1.98.1
// (commit 48a229ceaefd4985c50990b14116b6d856af0985) over native/fixtures.
//
// The invalid-UTF-8 case near the end is AUTHORED BUT NOT YET EXECUTED. It
// cannot run on this host: the compiler boundary refuses every non-OpenHarmony
// target, so analysis never reaches the parser here. See
// .trellis/tasks/10-22-offline-ide-completeness/research/
// compiler-boundary-utf8-regression-current.md for the exact blocker and the
// device prerequisites.
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
#include <direct.h>
typedef HMODULE NativeLibrary;
typedef HANDLE NativeThread;
#else
#include <dlfcn.h>
#include <pthread.h>
#include <sys/stat.h>
#include <time.h>
typedef void *NativeLibrary;
typedef pthread_t NativeThread;
#endif
#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// ABI conformance: the C layout must match the Rust `#[repr(C)]`
// `QfliAnalysisConfig` (size 56, offsets 0/8/16/24/32/36/40/48 on 64-bit).
// If a field is added or reordered on either side, this fails to compile.
_Static_assert(sizeof(void *) == 8 && sizeof(size_t) == 8,
               "the adapter only supports 64-bit hosts");
_Static_assert(sizeof(QfliAnalysisConfig) == 56, "QfliAnalysisConfig size");
_Static_assert(offsetof(QfliAnalysisConfig, abi_version) == 0, "abi_version offset");
_Static_assert(offsetof(QfliAnalysisConfig, source_path) == 8, "source_path offset");
_Static_assert(offsetof(QfliAnalysisConfig, sysroot_path) == 16, "sysroot_path offset");
_Static_assert(offsetof(QfliAnalysisConfig, crate_name) == 24, "crate_name offset");
_Static_assert(offsetof(QfliAnalysisConfig, edition) == 32, "edition offset");
_Static_assert(offsetof(QfliAnalysisConfig, crate_type) == 36, "crate_type offset");
_Static_assert(offsetof(QfliAnalysisConfig, timeout_ms) == 40, "timeout_ms offset");
_Static_assert(offsetof(QfliAnalysisConfig, max_output_bytes) == 48, "max_output_bytes offset");
_Static_assert(sizeof(QfliResult) == 24, "QfliResult layout must stay unchanged");
_Static_assert(QFLI_BUSY == 6 && QFLI_ANALYSIS_CRATE_BIN == 0
               && QFLI_ANALYSIS_CRATE_LIB == 1, "analysis constants");

static QfliSession *(*create_session)(const QfliConfig *);
static QfliSession *(*create_analysis)(const QfliAnalysisConfig *, const char *);
static int32_t (*run_session)(QfliSession *);
static int32_t (*analyze_session)(QfliSession *);
static void (*cancel_session)(QfliSession *);
static size_t (*copy_output)(const QfliSession *, uint32_t, uint8_t *, size_t);
static int32_t (*get_result)(const QfliSession *, QfliResult *);
static void (*destroy_session)(QfliSession *);

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

static void poll_delay(void) {
#ifdef _WIN32
    Sleep(1);
#else
    struct timespec delay = { .tv_nsec = 1000000 };
    nanosleep(&delay, NULL);
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

static char *output(QfliSession *session, uint32_t channel) {
    size_t length = copy_output(session, channel, NULL, 0);
    char *text = calloc(length + 1, 1);
    assert(text);
    assert(copy_output(session, channel, (uint8_t *)text, length) == length);
    return text;
}

static void join_run(NativeThread thread) {
#ifdef _WIN32
    assert(WaitForSingleObject(thread, INFINITE) == WAIT_OBJECT_0);
    assert(CloseHandle(thread));
#else
    assert(pthread_join(thread, NULL) == 0);
#endif
}

#ifdef _WIN32
static DWORD WINAPI run_thread(void *session) {
#else
static void *run_thread(void *session) {
#endif
    assert(run_session((QfliSession *)session) == 0);
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

static QfliAnalysisConfig analysis_config(
    const char *source, const char *sysroot, uint32_t crate_type,
    size_t bytes, uint64_t timeout_ms) {
    return (QfliAnalysisConfig) {
        .abi_version = 1, .source_path = source, .sysroot_path = sysroot,
        .crate_name = "qfli_fixture", .edition = 2024,
        .crate_type = crate_type, .timeout_ms = timeout_ms,
        .max_output_bytes = bytes,
    };
}

static char *fixture_path(const char *directory, const char *name) {
    static char buffer[8][4096];
    static int slot = 0;
    char *path = buffer[slot];
    slot = (slot + 1) % 8;
    snprintf(path, sizeof(buffer[0]), "%s/%s.rs", directory, name);
    return path;
}

static QfliSession *new_analysis(const char *directory, const char *sysroot,
                                const char *name, uint32_t crate_type) {
    char *source = fixture_path(directory, name);
    QfliAnalysisConfig config = analysis_config(source, sysroot, crate_type, 1048576, 60000);
    QfliSession *session = create_analysis(&config, NULL);
    if (!session) {
        fprintf(stderr, "create_analysis failed for %s\n", name);
        abort();
    }
    return session;
}

static int contains(const char *haystack, const char *needle) {
    return haystack && needle && strstr(haystack, needle) != NULL;
}

// Every non-empty diagnostics line must be one JSON object starting with
// {"$message_type": — the channel must not carry annotated human text.
static int is_json_lines(const char *text) {
    if (!text || !*text) { return 1; }
    const char *line = text;
    while (*line) {
        if (!strncmp(line, "{\"$message_type\":", 17)) {
            const char *newline = strchr(line, '\n');
            if (!newline) { return 1; }
            line = newline + 1;
            continue;
        }
        return 0;
    }
    return 1;
}

static long json_integer(const char *text, const char *key) {
    char pattern[64];
    snprintf(pattern, sizeof(pattern), "\"%s\":", key);
    const char *found = strstr(text, pattern);
    if (!found) { return -1; }
    found += strlen(pattern);
    long value = 0;
    int digits = 0;
    while (*found >= '0' && *found <= '9') {
        value = value * 10 + (*found - '0');
        found++;
        digits++;
    }
    return digits ? value : -1;
}

// Decodes the UTF-8 bytes at [start, end) of `path` and compares to `expected`.
static void assert_span_text(const char *path, long start, long end, const char *expected) {
    FILE *file = fopen(path, "rb");
    assert(file);
    assert(start >= 0 && end > start);
    char bytes[4096] = {0};
    assert((size_t)end <= sizeof(bytes) - 1);
    assert(fseek(file, 0, SEEK_END) == 0);
    long length = ftell(file);
    assert(length >= end);
    assert(fseek(file, start, SEEK_SET) == 0);
    size_t read = fread(bytes, 1, (size_t)(end - start), file);
    fclose(file);
    bytes[read] = '\0';
    if (strcmp(bytes, expected)) {
        fprintf(stderr, "span %ld..%ld = \"%s\", expected \"%s\"\n", start, end, bytes, expected);
        abort();
    }
}

static void expect_diagnostic(const char *directory, const char *sysroot,
                             const char *name, uint32_t crate_type,
                             const char *code, const char *expected_span,
                             long expected_byte_start) {
    char *source = fixture_path(directory, name);
    QfliSession *session = new_analysis(directory, sysroot, name, crate_type);
    assert(analyze_session(session) == 0);
    QfliResult result;
    assert(get_result(session, &result) == 0);
    char *diag = output(session, QFLI_DIAGNOSTICS);
    char *out = output(session, QFLI_STDOUT);
    char *err = output(session, QFLI_STDERR);
    int ok = result.state == QFLI_FINISHED && result.exit_code == 0
             && !*out && !*err && is_json_lines(diag)
             && contains(diag, "\"level\":\"error\"")
             && (!code || contains(diag, code));
    if (ok && expected_span) {
        long start = json_integer(diag, "byte_start");
        long end = json_integer(diag, "byte_end");
        if (expected_byte_start >= 0 && start != expected_byte_start) {
            fprintf(stderr, "%s: byte_start %ld, expected %ld\n", name, start, expected_byte_start);
            ok = 0;
        }
        if (ok) { assert_span_text(source, start, end, expected_span); }
        ok = ok && contains(diag, "\"is_primary\":true");
    }
    if (!ok) {
        fprintf(stderr, "%s failed state=%u exit=%d\nstdout: %s\nstderr: %s\ndiag: %s\n",
                name, result.state, result.exit_code, out, err, diag);
        abort();
    }
    free(diag); free(out); free(err);
    destroy_session(session);
    printf("PASS analysis diagnostic %s\n", name);
}

static void clean(const char *directory, const char *sysroot,
                  const char *name, uint32_t crate_type) {
    QfliSession *session = new_analysis(directory, sysroot, name, crate_type);
    assert(analyze_session(session) == 0);
    QfliResult result;
    assert(get_result(session, &result) == 0);
    char *diag = output(session, QFLI_DIAGNOSTICS);
    char *out = output(session, QFLI_STDOUT);
    char *err = output(session, QFLI_STDERR);
    if (result.state != QFLI_FINISHED || result.exit_code != 0
        || *out || *err || !is_json_lines(diag)
        || contains(diag, "\"level\":\"error\"")
        || contains(diag, "\"level\":\"warning\"")) {
        fprintf(stderr, "%s expected clean state=%u exit=%d\nstdout: %s\nstderr: %s\ndiag: %s\n",
                name, result.state, result.exit_code, out, err, diag);
        abort();
    }
    free(diag); free(out); free(err);
    destroy_session(session);
    printf("PASS analysis clean %s\n", name);
}

static void invalid_config(const char *directory, const char *sysroot) {
    char *source = fixture_path(directory, "analysis_valid");

    QfliAnalysisConfig config = analysis_config(source, sysroot, QFLI_ANALYSIS_CRATE_BIN, 1048576, 60000);
    assert(!create_analysis(NULL, NULL));

    QfliAnalysisConfig bad = config; bad.abi_version = 2;
    assert(!create_analysis(&bad, NULL));
    bad = config; bad.edition = 2019;
    assert(!create_analysis(&bad, NULL));
    bad = config; bad.crate_type = 2;
    assert(!create_analysis(&bad, NULL));
    bad = config; bad.crate_name = "";
    assert(!create_analysis(&bad, NULL));
    bad = config; bad.crate_name = "bad-name";
    assert(!create_analysis(&bad, NULL));
    bad = config; bad.crate_name = NULL;
    assert(!create_analysis(&bad, NULL));
    bad = config; bad.max_output_bytes = 512;
    assert(!create_analysis(&bad, NULL));
    bad = config; bad.timeout_ms = 0;
    assert(!create_analysis(&bad, NULL));
    bad = config; bad.source_path = "relative.rs";
    assert(!create_analysis(&bad, NULL));
    bad = config; bad.sysroot_path = "relative-sysroot";
    assert(!create_analysis(&bad, NULL));
    char missing[4096];
    snprintf(missing, sizeof(missing), "%s/does-not-exist.rs", directory);
    bad = config; bad.source_path = missing;
    assert(!create_analysis(&bad, NULL));
    // A non-NULL backend path must be absolute and loadable, like the run path.
    assert(!create_analysis(&config, "relative-backend.so"));
    assert(analyze_session(NULL) == -1);

    // The valid base config still creates a session.
    QfliSession *session = create_analysis(&config, NULL);
    assert(session);
    assert(analyze_session(session) == 0);
    // One analysis per session.
    assert(analyze_session(session) == -1);
    destroy_session(session);
    puts("PASS analysis config validation and single use");
}

static void missing_main(const char *directory, const char *sysroot) {
    // The same source is clean as a library and an error as a binary: proves the
    // crate type is really applied rather than defaulted.
    QfliSession *session = new_analysis(directory, sysroot, "analysis_library", QFLI_ANALYSIS_CRATE_BIN);
    assert(analyze_session(session) == 0);
    QfliResult result;
    assert(get_result(session, &result) == 0);
    char *diag = output(session, QFLI_DIAGNOSTICS);
    if (result.state != QFLI_FINISHED || result.exit_code != 0 || !contains(diag, "E0601")
        || !is_json_lines(diag)) {
        fprintf(stderr, "missing main failed state=%u diag=%s\n", result.state, diag);
        abort();
    }
    free(diag);
    destroy_session(session);
    puts("PASS analysis crate type selects main requirement");
}

static void nonexecution(const char *directory, const char *sysroot) {
    QfliSession *session = new_analysis(directory, sysroot, "analysis_nonexecution", QFLI_ANALYSIS_CRATE_BIN);
    assert(analyze_session(session) == 0);
    QfliResult result;
    assert(get_result(session, &result) == 0);
    char *out = output(session, QFLI_STDOUT);
    char *err = output(session, QFLI_STDERR);
    char *diag = output(session, QFLI_DIAGNOSTICS);
    // The fixture would print EXECUTED and exit 7 if it were interpreted.
    if (result.state != QFLI_FINISHED || result.exit_code != 0 || *out || *err
        || contains(out, "EXECUTED") || contains(err, "EXECUTED") || contains(diag, "EXECUTED")) {
        fprintf(stderr, "nonexecution failed state=%u exit=%d\nstdout: %s\nstderr: %s\n",
                result.state, result.exit_code, out, err);
        abort();
    }
    free(out); free(err); free(diag);
    destroy_session(session);
    puts("PASS analysis does not execute the program");
}

static void cancellation(const char *directory, const char *sysroot) {
    QfliSession *session = new_analysis(directory, sysroot, "analysis_valid", QFLI_ANALYSIS_CRATE_BIN);
    // Cancelled before the first phase checkpoint: deterministic and proves the
    // cancel flag survives into analysis.
    cancel_session(session);
    assert(analyze_session(session) == 0);
    QfliResult result;
    assert(get_result(session, &result) == 0);
    if (result.state != QFLI_CANCELLED || result.exit_code != 130) {
        char *diag = output(session, QFLI_DIAGNOSTICS);
        fprintf(stderr, "cancel failed state=%u exit=%d diag=%s\n", result.state, result.exit_code, diag);
        abort();
    }
    destroy_session(session);
    puts("PASS analysis cancellation");
}

static void output_bound(const char *directory, const char *sysroot) {
    // The bound must actually be exceeded for this check to mean anything.
    // `analysis_syntax` emits only ~890 bytes, which is UNDER a 1024 bound, so
    // it would finish cleanly and the test would fail for the wrong reason.
    // `analysis_type` emits ~2 KB because a coded diagnostic (E0308) carries
    // the full `code.explanation` string, so a 1024 bound truncates reliably.
    char *source = fixture_path(directory, "analysis_type");
    QfliAnalysisConfig config = analysis_config(source, sysroot, QFLI_ANALYSIS_CRATE_BIN, 1024, 60000);
    QfliSession *session = create_analysis(&config, NULL);
    assert(session);
    assert(analyze_session(session) == 0);
    QfliResult result;
    assert(get_result(session, &result) == 0);
    char *diag = output(session, QFLI_DIAGNOSTICS);
    // Truncation must be visible as a limit, never reported as a clean result.
    // The stop *reason text* is deliberately not asserted: when the diagnostics
    // channel is what filled up, the reason append (adapter) has zero room left
    // and is itself truncated, so the text is legitimately absent. The
    // observable contract is the state, the exit code, and a bounded length.
    if (result.state != QFLI_LIMIT_REACHED || result.exit_code != 124
        || copy_output(session, QFLI_DIAGNOSTICS, NULL, 0) > config.max_output_bytes
        || strlen(diag) > config.max_output_bytes) {
        fprintf(stderr, "output bound failed state=%u exit=%d len=%zu\n%s\n",
                result.state, result.exit_code, strlen(diag), diag);
        abort();
    }
    free(diag);
    destroy_session(session);
    puts("PASS analysis output bound");
}

// Regression: analysis sessions used to be created with a zero block budget, so
// the shared `check_stop` tripped "basic block limit reached" before rustc was
// ever invoked and every analysis returned state 4 / exit 124. Analysis must
// have no block limit at all, and must never report a block-limit stop.
static void no_block_limit(const char *directory, const char *sysroot) {
    QfliSession *session = new_analysis(directory, sysroot, "analysis_valid", QFLI_ANALYSIS_CRATE_BIN);
    assert(analyze_session(session) == 0);
    QfliResult result;
    assert(get_result(session, &result) == 0);
    char *diag = output(session, QFLI_DIAGNOSTICS);
    if (result.state != QFLI_FINISHED || result.exit_code != 0
        || result.basic_blocks != 0
        || contains(diag, "basic block limit")) {
        fprintf(stderr, "no_block_limit failed state=%u exit=%d blocks=%" PRIu64 "\n%s\n",
                result.state, result.exit_code, result.basic_blocks, diag);
        abort();
    }
    free(diag);
    destroy_session(session);
    puts("PASS analysis has no block budget");
}

static void compiler_busy(const char *directory, const char *sysroot) {
    // Hold the compiler with a long-running interpretation session.
    char *loop_source = fixture_path(directory, "cancel");
    QfliConfig run_config = {
        .abi_version = 1, .source_path = loop_source, .sysroot_path = sysroot,
        .max_basic_blocks = UINT64_MAX, .timeout_ms = 60000,
        .max_output_bytes = 1048576, .max_guest_memory_bytes = 32 * 1024 * 1024,
    };
    QfliSession *runner = create_session(&run_config);
    assert(runner);
    QfliSession *analysis = new_analysis(directory, sysroot, "analysis_valid", QFLI_ANALYSIS_CRATE_BIN);
    NativeThread thread = start_run(runner);
    QfliResult current;
    uint64_t deadline = monotonic_ms() + 60000;
    do {
        poll_delay();
        assert(get_result(runner, &current) == 0);
        assert(monotonic_ms() < deadline);
    } while (current.basic_blocks < 2000
             && (current.state == QFLI_READY || current.state == QFLI_RUNNING));
    assert(current.state == QFLI_RUNNING);

    // Analysis must answer immediately instead of queueing behind the run.
    uint64_t started = monotonic_ms();
    int32_t code = analyze_session(analysis);
    uint64_t elapsed = monotonic_ms() - started;
    QfliResult busy;
    assert(get_result(analysis, &busy) == 0);
    // The busy answer is the return code alone. `result.state` is session
    // status and must stay READY: a transient call outcome must not overwrite
    // it, and writing it would race a concurrent destroy.
    if (code != 2 || busy.state != QFLI_READY || busy.exit_code != -1 || elapsed > 5000) {
        fprintf(stderr, "busy failed code=%d state=%u exit=%d elapsed=%" PRIu64 "\n",
                code, busy.state, busy.exit_code, elapsed);
        abort();
    }

    cancel_session(runner);
    join_run(thread);
    QfliResult finished;
    assert(get_result(runner, &finished) == 0);
    assert(finished.state == QFLI_CANCELLED);

    // The busy answer did not consume the analysis session.
    assert(analyze_session(analysis) == 0);
    QfliResult retried;
    assert(get_result(analysis, &retried) == 0);
    assert(retried.state == QFLI_FINISHED && retried.exit_code == 0);

    destroy_session(runner);
    destroy_session(analysis);
    puts("PASS analysis compiler busy and retry");
}

// ---- invalid UTF-8 source regression -------------------------------------
//
// Regression: `Loader::read_file` used to record a boundary failure when a
// source file did not decode as UTF-8. That turned a learner's encoding error
// into INTERNAL_ERROR and discarded the compiler's own diagnostic. The contract
// is: a decode rejection is a *source* verdict, while root, symlink, wrong
// entry type, budget and argument-surface refusals stay policy failures.
//
// Why this path is a source verdict rather than an environment failure, in the
// pinned compiler:
//   * `SourceMap::load_file` propagates the loader error;
//   * `new_parser_from_file` catches it, opens
//     `struct_fatal("couldn't read `<path>`: <error>")`, then retries the same
//     bytes through `read_binary_for_diagnostic` and calls `utf8_error`;
//   * the frozen boundary patch is what routes that retry through the loader,
//     so the retry still cannot read a denied path;
//   * `struct_fatal` is a `FatalAbort` diagnostic, so it is written to the
//     emitter before `FatalError` unwinds. Analysis therefore stops before
//     `after_analysis` with diagnostics present, which maps to FINISHED / 0.
//
// The fixture is written by this test instead of living in native/fixtures so
// that the exact invalid byte offset is part of the assertion.
#define INVALID_UTF8_OFFSET 24

// 24 valid ASCII bytes, then a lone 0xFF that cannot start a UTF-8 sequence, so
// `str::from_utf8` reports valid_up_to() == 24 and error_len() == Some(1).
// rustc's `utf8_error` then labels byte 24, and the ABI diagnostic must carry
// byte_start == byte_end == 24 on a primary span.
static const unsigned char INVALID_UTF8_SOURCE[] = {
    '/', '/', ' ', 'i', 'n', 'v', 'a', 'l', 'i', 'd', ' ', 'b', 'y', 't',
    'e', ' ', 'f', 'o', 'l', 'l', 'o', 'w', 's', '\n',
    0xFF,
    '\n', 'f', 'n', ' ', 'm', 'a', 'i', 'n', '(', ')', ' ', '{', '}', '\n',
};
_Static_assert(sizeof(INVALID_UTF8_SOURCE) == 39, "invalid UTF-8 fixture length");
// The element value is checked at run time below: in C11 a `static const` array
// element is not an integer constant expression, so `_Static_assert` on it is
// not portable to every C compiler.

static void ensure_directory(const char *path) {
#ifdef _WIN32
    int made = _mkdir(path);
#else
    int made = mkdir(path, 0777);
#endif
    if (made != 0 && errno != EEXIST) {
        fprintf(stderr, "cannot create %s: %s\n", path, strerror(errno));
        abort();
    }
}

static void write_bytes(const char *path, const unsigned char *bytes, size_t length) {
    FILE *file = fopen(path, "wb");
    if (!file) {
        fprintf(stderr, "cannot write %s: %s\n", path, strerror(errno));
        abort();
    }
    if (fwrite(bytes, 1, length, file) != length) {
        fclose(file);
        fprintf(stderr, "short write to %s\n", path);
        abort();
    }
    if (fclose(file) != 0) {
        fprintf(stderr, "cannot close %s: %s\n", path, strerror(errno));
        abort();
    }
}

static QfliSession *new_analysis_source(const char *source, const char *sysroot) {
    QfliAnalysisConfig config =
        analysis_config(source, sysroot, QFLI_ANALYSIS_CRATE_BIN, 1048576, 60000);
    QfliSession *session = create_analysis(&config, NULL);
    if (!session) {
        fprintf(stderr, "create_analysis failed for %s\n", source);
        abort();
    }
    return session;
}

// A boundary refusal is appended to the *diagnostics* channel as a plain line,
// not to stderr: `DiagnosticWriter` and the refusal path both use channel 2.
// This probe distinguishes "this build cannot confine on this host" from a real
// regression, so a desktop run reports a skip instead of a false failure.
static int boundary_host_supported(const char *directory, const char *sysroot) {
    QfliSession *session = new_analysis(directory, sysroot, "analysis_valid", QFLI_ANALYSIS_CRATE_BIN);
    assert(analyze_session(session) == 0);
    QfliResult result;
    assert(get_result(session, &result) == 0);
    char *diag = output(session, QFLI_DIAGNOSTICS);
    int unsupported = result.state == QFLI_INTERNAL_ERROR && result.exit_code == 1
                      && contains(diag, "qfli: compiler boundary:")
                      && (contains(diag, "unsupported on this host")
                          || contains(diag, "unavailable on this host"));
    if (unsupported) {
        fprintf(stderr,
                "SKIP analysis needs an OpenHarmony adapter build; this host cannot "
                "confine a compiler session: %s",
                diag);
    }
    free(diag);
    destroy_session(session);
    return !unsupported;
}

// Asserts the whole invalid-UTF-8 contract for one analysis session and then
// destroys it.
static void check_invalid_utf8(QfliSession *session, const char *source, const char *label) {
    assert(analyze_session(session) == 0);
    QfliResult result;
    assert(get_result(session, &result) == 0);
    char *diag = output(session, QFLI_DIAGNOSTICS);
    char *out = output(session, QFLI_STDOUT);
    char *err = output(session, QFLI_STDERR);
    // 1. FINISHED / 0 is the contract for any erroneous source. The regression
    //    returned INTERNAL_ERROR / 1 here.
    // 2. No policy failure may be reported: that line would land in the
    //    diagnostics channel and break the JSON Lines contract.
    // 3. The compiler's real diagnostic must survive: the parse fatal names the
    //    path and the UTF-8 reason, and it is an error, never a clean result.
    int ok = result.state == QFLI_FINISHED && result.exit_code == 0
             && !*out && !*err
             && is_json_lines(diag)
             && !contains(diag, "qfli: compiler boundary:")
             && contains(diag, "\"level\":\"error\"")
             && contains(diag, "couldn't read")
             && contains(diag, "not valid utf-8")
             && contains(diag, source);
    if (ok) {
        long start = json_integer(diag, "byte_start");
        long end = json_integer(diag, "byte_end");
        if (start != INVALID_UTF8_OFFSET || end != INVALID_UTF8_OFFSET) {
            fprintf(stderr, "%s: invalid-UTF-8 span %ld..%ld, expected %d..%d\n",
                    label, start, end, INVALID_UTF8_OFFSET, INVALID_UTF8_OFFSET);
            ok = 0;
        } else if (!contains(diag, "\"is_primary\":true")) {
            fprintf(stderr, "%s: invalid-UTF-8 span is not primary\n", label);
            ok = 0;
        }
    }
    if (!ok) {
        fprintf(stderr,
                "%s failed state=%u exit=%d\nstdout: %s\nstderr: %s\ndiag: %s\n",
                label, result.state, result.exit_code, out, err, diag);
        abort();
    }
    free(diag);
    free(out);
    free(err);
    destroy_session(session);
    printf("PASS analysis invalid UTF-8 stays a source verdict (%s)\n", label);
}

static void invalid_utf8_source(const char *directory, const char *sysroot) {
    // The fixture directory must be writable on device; the malformed source is
    // created here rather than shipped, so the invalid offset is exact.
    static char scratch[4096];
    static char source[4096];
    assert(INVALID_UTF8_SOURCE[INVALID_UTF8_OFFSET] == 0xFF);
    snprintf(scratch, sizeof(scratch), "%s/utf8-regression", directory);
    ensure_directory(scratch);
    snprintf(source, sizeof(source), "%s/broken_utf8.rs", scratch);
    write_bytes(source, INVALID_UTF8_SOURCE, sizeof(INVALID_UTF8_SOURCE));

    // First session: the regression itself.
    check_invalid_utf8(new_analysis_source(source, sysroot), source, "first session");
    // Second session: repeating it must give the same verdict. A sticky,
    // process-wide failure would surface here as INTERNAL_ERROR.
    check_invalid_utf8(new_analysis_source(source, sysroot), source, "repeated session");
    // A fresh valid crate must still analyse cleanly, proving the invalid file
    // left no poisoned compiler state behind.
    clean(directory, sysroot, "analysis_valid", QFLI_ANALYSIS_CRATE_BIN);
    puts("PASS analysis invalid UTF-8 leaves the compiler usable");
}

int main(int argc, char **argv) {
    if (argc != 4) {
        fprintf(stderr, "Usage: %s <adapter-library> <MIR-sysroot> <fixture-directory>\n", argv[0]);
        return 2;
    }
    NativeLibrary library = open_library(argv[1]);
    if (!library) { return 1; }
    uint32_t (*version)(void) = library_symbol(library, "qfli_miri_abi_version");
    create_session = library_symbol(library, "qfli_miri_create");
    create_analysis = library_symbol(library, "qfli_miri_create_analysis");
    run_session = library_symbol(library, "qfli_miri_run");
    analyze_session = library_symbol(library, "qfli_miri_analyze");
    cancel_session = library_symbol(library, "qfli_miri_cancel");
    copy_output = library_symbol(library, "qfli_miri_copy_output");
    get_result = library_symbol(library, "qfli_miri_result");
    destroy_session = library_symbol(library, "qfli_miri_destroy");
    // The analysis symbols are an optional extension: report a skip, not a pass.
    if (!version || !create_session || !run_session || !cancel_session
        || !copy_output || !get_result || !destroy_session) {
        fprintf(stderr, "Required ABI-1 run symbols are missing\n");
        return 1;
    }
    assert(version() == 1);
    if (!create_analysis || !analyze_session) {
        fprintf(stderr, "SKIP analysis extension is not present in this adapter build\n");
        return 3;
    }
    // Report an unsupported host as a skip, never as a pass or a false failure.
    if (!boundary_host_supported(argv[3], argv[2])) { return 3; }

    assert(!create_analysis(NULL, NULL));
    assert(analyze_session(NULL) == -1);
    cancel_session(NULL);
    destroy_session(NULL);
    puts("PASS analysis symbols and null handling");

    invalid_config(argv[3], argv[2]);
    // The primary span is the string literal *including* its quotes: bytes
    // 33..47 of the fixture, i.e. the 14 bytes `"not a number"`. The quotes are
    // part of the expression rustc points at, so the expectation must include
    // them; asserting the bare contents silently compares 12 of 14 bytes.
    expect_diagnostic(argv[3], argv[2], "analysis_type", QFLI_ANALYSIS_CRATE_BIN,
                      "E0308", "\"not a number\"", 33);
    expect_diagnostic(argv[3], argv[2], "analysis_syntax", QFLI_ANALYSIS_CRATE_BIN,
                      NULL, NULL, -1);
    // Byte offsets must survive 3-byte CJK and a 4-byte emoji before the token.
    expect_diagnostic(argv[3], argv[2], "analysis_unicode", QFLI_ANALYSIS_CRATE_BIN,
                      "E0308", "label", 99);
    clean(argv[3], argv[2], "analysis_valid", QFLI_ANALYSIS_CRATE_BIN);
    clean(argv[3], argv[2], "analysis_library", QFLI_ANALYSIS_CRATE_LIB);
    // Analysis must not enable cfg(miri); this fixture would fail if it did.
    clean(argv[3], argv[2], "analysis_cfg_miri", QFLI_ANALYSIS_CRATE_BIN);
    missing_main(argv[3], argv[2]);
    nonexecution(argv[3], argv[2]);
    output_bound(argv[3], argv[2]);
    no_block_limit(argv[3], argv[2]);
    cancellation(argv[3], argv[2]);
    compiler_busy(argv[3], argv[2]);
    // Authored but never executed in this workspace: analysis needs an
    // OpenHarmony adapter build. See
    // research/compiler-boundary-utf8-regression-current.md.
    invalid_utf8_source(argv[3], argv[2]);
    // rustc/backend process-global state remains live; do not unload the compiler.
    return 0;
}
