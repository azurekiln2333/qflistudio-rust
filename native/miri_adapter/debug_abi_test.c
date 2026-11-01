// Interactive debugging ABI test.
//
// Every assertion here is about *real* Miri state: the session compiles the
// fixture with the pinned rustc, then steps the pinned Miri interpreter. Stop
// lines and local values below are the ones the fixtures were written to
// produce (see the line map at the top of each native/fixtures/debug_*.rs).
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0600
#endif
#else
#define _POSIX_C_SOURCE 200809L
#endif
#include "qfli_debug.h"

#undef NDEBUG
#include <assert.h>
#include <inttypes.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#include <windows.h>
typedef HMODULE NativeLibrary;
#else
#include <dlfcn.h>
#include <pthread.h>
#include <time.h>
typedef void *NativeLibrary;
#endif

// ABI conformance with the Rust #[repr(C)] definitions, measured from the Rust
// side with the pinned rustc. A field reorder on either side breaks the build.
_Static_assert(sizeof(void *) == 8 && sizeof(size_t) == 8,
               "the adapter only supports 64-bit hosts");
_Static_assert(sizeof(QfliBreakpoint) == 16, "QfliBreakpoint size");
_Static_assert(sizeof(QfliDebugConfig) == 80, "QfliDebugConfig size");
_Static_assert(offsetof(QfliDebugConfig, breakpoints) == 64, "breakpoints offset");
_Static_assert(offsetof(QfliDebugConfig, breakpoint_count) == 72, "breakpoint_count offset");
_Static_assert(sizeof(QfliDebugPause) == 24, "QfliDebugPause size");
_Static_assert(offsetof(QfliDebugPause, steps) == 8, "steps offset");
_Static_assert(offsetof(QfliDebugPause, exit_code) == 16, "exit_code offset");
_Static_assert(sizeof(QfliDebugStatus) == 24, "QfliDebugStatus size");
_Static_assert(offsetof(QfliDebugStatus, pause_generation) == 8, "generation offset");
_Static_assert(offsetof(QfliDebugStatus, revision) == 16, "revision offset");
_Static_assert(sizeof(QfliFrame) == 32, "QfliFrame size");
_Static_assert(offsetof(QfliFrame, file_path) == 8, "file_path offset");
_Static_assert(offsetof(QfliFrame, line) == 16, "line offset");
_Static_assert(offsetof(QfliFrame, function) == 24, "function offset");
_Static_assert(sizeof(QfliLocal) == 32, "QfliLocal size");
_Static_assert(offsetof(QfliLocal, local) == 16, "local offset");
_Static_assert(offsetof(QfliLocal, state) == 20, "state offset");
_Static_assert(offsetof(QfliLocal, value) == 24, "value offset");

static uint32_t (*capabilities)(void);
static QfliDebugSession *(*create_debug)(const QfliDebugConfig *, const char *);
static int32_t (*start_debug)(QfliDebugSession *);
static int32_t (*resume_debug)(QfliDebugSession *, uint32_t);
static int32_t (*resume_at)(QfliDebugSession *, uint32_t, uint64_t);
static int32_t (*debug_status)(const QfliDebugSession *, QfliDebugStatus *);
static int32_t (*wait_debug)(QfliDebugSession *);
static void (*pause_debug)(QfliDebugSession *);
static void (*cancel_debug)(QfliDebugSession *);
static void (*destroy_debug)(QfliDebugSession *);
static int32_t (*pause_info)(const QfliDebugSession *, QfliDebugPause *);
static size_t (*frame_count)(const QfliDebugSession *);
static int32_t (*frame_at)(const QfliDebugSession *, size_t, QfliFrame *);
static size_t (*locals_at)(const QfliDebugSession *, size_t, QfliLocal *, size_t);
static size_t (*copy_debug_output)(const QfliDebugSession *, uint8_t *, size_t);
static size_t (*copy_channel)(const QfliDebugSession *, uint32_t, uint8_t *, size_t);

static void sleep_millis(unsigned milliseconds) {
#ifdef _WIN32
    Sleep(milliseconds);
#else
    struct timespec wait = { (time_t)(milliseconds / 1000),
                             (long)(milliseconds % 1000) * 1000000L };
    while (nanosleep(&wait, &wait) != 0) {}
#endif
}

typedef struct {
    QfliDebugSession *session;
    int32_t result;
} ResumeCall;

#ifdef _WIN32
static DWORD WINAPI continue_on_thread(void *argument) {
#else
static void *continue_on_thread(void *argument) {
#endif
    ResumeCall *call = argument;
    call->result = resume_debug(call->session, QFLI_DEBUG_CONTINUE);
#ifdef _WIN32
    return 0;
#else
    return NULL;
#endif
}

static NativeLibrary open_library(const char *path) {
#ifdef _WIN32
    int count = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, path, -1, NULL, 0);
    if (!count) { fprintf(stderr, "Invalid UTF-8 library path\n"); return NULL; }
    wchar_t *wide = calloc((size_t)count, sizeof(wchar_t));
    assert(wide);
    assert(MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, path, -1, wide, count));
    NativeLibrary library = LoadLibraryW(wide);
    free(wide);
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

static char *fixture_path(const char *directory, const char *name) {
    static char buffer[8][4096];
    static int slot = 0;
    char *path = buffer[slot];
    slot = (slot + 1) % 8;
    snprintf(path, sizeof(buffer[0]), "%s/%s.rs", directory, name);
    return path;
}

static QfliDebugConfig debug_config(const char *source, const char *sysroot) {
    return (QfliDebugConfig) {
        .abi_version = 1,
        .source_path = source,
        .sysroot_path = sysroot,
        .crate_name = "qfli_debug_fixture",
        .edition = 2024,
        .crate_type = QFLI_DEBUG_CRATE_BIN,
        .timeout_ms = 120000,
        .max_steps = 200000,
        .max_output_bytes = 1048576,
        .breakpoints = NULL,
        .breakpoint_count = 0,
    };
}

static QfliDebugSession *open_debug(const char *directory, const char *sysroot,
                                   const char *name) {
    QfliDebugConfig config = debug_config(fixture_path(directory, name), sysroot);
    QfliDebugSession *session = create_debug(&config, NULL);
    if (!session) {
        fprintf(stderr, "create_debug failed for %s\n", name);
        abort();
    }
    return session;
}

static QfliDebugPause current_pause(QfliDebugSession *session) {
    QfliDebugPause pause;
    assert(pause_info(session, &pause) == 0);
    return pause;
}

static QfliDebugStatus current_status(QfliDebugSession *session) {
    QfliDebugStatus status;
    assert(debug_status(session, &status) == 0);
    return status;
}

static uint32_t marker_line(const char *source, const char *marker) {
    FILE *file = fopen(source, "rb");
    assert(file);
    char line[4096];
    uint32_t number = 0, found = 0;
    while (fgets(line, sizeof(line), file)) {
        number++;
        if (strstr(line, marker) && strstr(line, "let ")) { found = number; break; }
    }
    fclose(file);
    assert(found);
    return found;
}

static QfliFrame current_frame(QfliDebugSession *session) {
    QfliFrame frame;
    memset(&frame, 0, sizeof(frame));
    assert(frame_at(session, 0, &frame) == 0);
    return frame;
}

// Finds a local by source name. Returns 0 when absent, so a missing variable is
// a test failure rather than a silently skipped assertion.
static int find_local(QfliDebugSession *session, const char *name, QfliLocal *out) {
    size_t count = locals_at(session, 0, NULL, 0);
    if (count == 0) { return 0; }
    QfliLocal *locals = calloc(count, sizeof(QfliLocal));
    assert(locals);
    size_t written = locals_at(session, 0, locals, count);
    assert(written == count);
    int found = 0;
    for (size_t index = 0; index < count; index++) {
        if (locals[index].name && !strcmp(locals[index].name, name)) {
            *out = locals[index];
            found = 1;
            break;
        }
    }
    free(locals);
    return found;
}

static void expect_local_value(QfliDebugSession *session, const char *name,
                               const char *expected) {
    QfliLocal local;
    if (!find_local(session, name, &local)) {
        fprintf(stderr, "local `%s` not reported\n", name);
        abort();
    }
    if (local.state != QFLI_LOCAL_VALUE || !local.value || strcmp(local.value, expected)) {
        fprintf(stderr, "local `%s`: state=%u value=\"%s\", expected \"%s\"\n", name,
                local.state, local.value ? local.value : "(null)", expected);
        abort();
    }
}

static void expect_local_state(QfliDebugSession *session, const char *name,
                               uint32_t expected_state) {
    QfliLocal local;
    if (!find_local(session, name, &local)) {
        fprintf(stderr, "local `%s` not reported\n", name);
        abort();
    }
    if (local.state != expected_state) {
        fprintf(stderr, "local `%s`: state=%u, expected %u (value=\"%s\")\n", name,
                local.state, expected_state, local.value ? local.value : "");
        abort();
    }
}

// --- checks ---------------------------------------------------------------

static void symbols_and_nulls(void) {
    assert(capabilities() != 0);
    // Every capability the header defines must be advertised, because each is
    // implemented by the stepping loop.
    uint32_t required = QFLI_DEBUG_CAP_BREAKPOINTS | QFLI_DEBUG_CAP_STEP_IN
                        | QFLI_DEBUG_CAP_STEP_OVER | QFLI_DEBUG_CAP_STEP_OUT
                        | QFLI_DEBUG_CAP_LOCALS | QFLI_DEBUG_CAP_MACRO_CALLSITE;
    if ((capabilities() & required) != required) {
        fprintf(stderr, "capabilities 0x%x missing 0x%x\n", capabilities(),
                required & ~capabilities());
        abort();
    }
    assert(!create_debug(NULL, NULL));
    assert(start_debug(NULL) == -1);
    assert(resume_debug(NULL, QFLI_DEBUG_CONTINUE) == -1);
    assert(resume_at(NULL, QFLI_DEBUG_CONTINUE, 1) == -1);
    assert(wait_debug(NULL) == -1);
    QfliDebugStatus status;
    assert(debug_status(NULL, &status) == -1);
    pause_debug(NULL);
    cancel_debug(NULL);
    destroy_debug(NULL);
    QfliDebugPause pause;
    assert(pause_info(NULL, &pause) == -1);
    assert(frame_count(NULL) == 0);
    QfliFrame frame;
    assert(frame_at(NULL, 0, &frame) == -1);
    assert(locals_at(NULL, 0, NULL, 0) == 0);
    assert(copy_debug_output(NULL, NULL, 0) == 0);
    assert(copy_channel(NULL, 0, NULL, 0) == 0);
    puts("PASS debug symbols and null handling");
}

static void invalid_config(const char *directory, const char *sysroot) {
    char *source = fixture_path(directory, "debug_basic");
    QfliDebugConfig base = debug_config(source, sysroot);
    assert(!create_debug(NULL, NULL));

    QfliDebugConfig bad = base; bad.abi_version = 2;
    assert(!create_debug(&bad, NULL));
    bad = base; bad.edition = 2019;
    assert(!create_debug(&bad, NULL));
    bad = base; bad.crate_type = 2;
    assert(!create_debug(&bad, NULL));
    bad = base; bad.max_steps = 0;
    assert(!create_debug(&bad, NULL));
    bad = base; bad.timeout_ms = 0;
    assert(!create_debug(&bad, NULL));
    bad = base; bad.max_output_bytes = 512;
    assert(!create_debug(&bad, NULL));
    bad = base; bad.crate_name = "";
    assert(!create_debug(&bad, NULL));
    bad = base; bad.crate_name = "bad-name";
    assert(!create_debug(&bad, NULL));
    bad = base; bad.source_path = "relative.rs";
    assert(!create_debug(&bad, NULL));
    // Breakpoint validation: count without an array, and a zero line.
    bad = base; bad.breakpoint_count = 1; bad.breakpoints = NULL;
    assert(!create_debug(&bad, NULL));
    QfliBreakpoint zero_line = { .file_path = source, .line = 0, .column = 0 };
    bad = base; bad.breakpoints = &zero_line; bad.breakpoint_count = 1;
    assert(!create_debug(&bad, NULL));
    QfliBreakpoint relative = { .file_path = "relative.rs", .line = 1, .column = 0 };
    bad = base; bad.breakpoints = &relative; bad.breakpoint_count = 1;
    assert(!create_debug(&bad, NULL));
    puts("PASS debug config validation");
}

// Optional bounded evidence for diagnosing actual entry/step locations.
static void trace_pause(QfliDebugSession *session, const char *label) {
    if (!getenv("QFLI_DEBUG_ABI_TRACE")) return;
    QfliDebugPause pause = current_pause(session);
    fprintf(stderr, "TRACE %s reason=%u steps=%" PRIu64 " frames=%zu\n",
            label, pause.reason, pause.steps, frame_count(session));
    if (!frame_count(session)) return;
    QfliFrame frame = current_frame(session);
    fprintf(stderr, "TRACE location=%s:%u:%u function=%s\n",
            frame.file_path ? frame.file_path : "", frame.line, frame.column,
            frame.function ? frame.function : "");
    QfliLocal locals[32];
    size_t count = locals_at(session, 0, locals, 32);
    for (size_t index = 0; index < count && index < 32; index++) {
        fprintf(stderr, "TRACE local=%s state=%u value=%s\n",
                locals[index].name ? locals[index].name : "", locals[index].state,
                locals[index].value ? locals[index].value : "");
    }
}

// Entry pause, single stepping, and real scalar locals.
static void entry_and_steps(const char *directory, const char *sysroot) {
    char *source = fixture_path(directory, "debug_basic");
    QfliDebugConfig config = debug_config(source, sysroot);
    QfliDebugSession *session = create_debug(&config, NULL);
    assert(session);
    assert(start_debug(session) == 0);

    // The current line describes the instruction that has not executed yet.
    // Entry is already line 9; resuming before checking it skips that pause.
    // Check each exact transition rather than searching later pauses for an
    // entry line that the interpreter has correctly finished executing.
    const uint32_t expected_lines[] = {9, 10, 11};
    size_t depth = frame_count(session);
    assert(depth > 0);
    uint64_t previous_steps = 0, previous_generation = 0, previous_revision = 0;
    for (size_t index = 0; index < sizeof(expected_lines) / sizeof(expected_lines[0]); index++) {
        if (index > 0) {
            assert(resume_debug(session, QFLI_DEBUG_STEP_IN) == 0);
        }
        QfliDebugPause pause = current_pause(session);
        QfliDebugStatus status = current_status(session);
        trace_pause(session, index == 0 ? "entry" : "step-in");
        assert(status.state == QFLI_DEBUG_PAUSED && !status.worker_exited);
        assert(status.pause_generation > previous_generation);
        assert(status.revision > previous_revision);
        assert(frame_count(session) == depth && pause.frame_count == depth);
        assert(pause.reason == (index == 0 ? QFLI_DEBUG_PAUSE_ENTRY : QFLI_DEBUG_PAUSE_STEP));
        assert(index == 0 ? pause.steps == 0 : pause.steps > previous_steps);
        QfliFrame frame = current_frame(session);
        if (!frame.file_path || strcmp(frame.file_path, source)
            || frame.line != expected_lines[index] || frame.column == 0
            || !frame.function || !strstr(frame.function, "main")) {
            fprintf(stderr, "basic pause %zu: %s:%u:%u function=%s, expected %s:%u in main\n",
                    index, frame.file_path ? frame.file_path : "", frame.line, frame.column,
                    frame.function ? frame.function : "", source, expected_lines[index]);
            abort();
        }

        if (index == 0) {
            expect_local_state(session, "a", QFLI_LOCAL_UNINITIALIZED);
        } else {
            expect_local_value(session, "a", "1");
        }
        if (index < 2) {
            expect_local_state(session, "b", QFLI_LOCAL_UNINITIALIZED);
        } else {
            expect_local_value(session, "b", "2");
        }
        expect_local_state(session, "sum", QFLI_LOCAL_UNINITIALIZED);
        previous_steps = pause.steps;
        previous_generation = status.pause_generation;
        previous_revision = status.revision;
    }
    cancel_debug(session);
    destroy_debug(session);
    puts("PASS debug entry pause and step-in");
}

// A source breakpoint must stop on the exact line, and the stack must show the
// frame that is actually executing.
static void breakpoint(const char *directory, const char *sysroot) {
    char *source = fixture_path(directory, "debug_breakpoint");
    QfliBreakpoint point = { .file_path = source, .line = 15, .column = 0 };
    QfliDebugConfig config = debug_config(source, sysroot);
    config.breakpoints = &point;
    config.breakpoint_count = 1;
    QfliDebugSession *session = create_debug(&config, NULL);
    assert(session);
    assert(start_debug(session) == 0);
    // Continue from the entry pause to the breakpoint.
    assert(resume_debug(session, QFLI_DEBUG_CONTINUE) == 0);

    QfliDebugPause pause = current_pause(session);
    if (pause.reason != QFLI_DEBUG_PAUSE_BREAKPOINT) {
        fprintf(stderr, "breakpoint pause reason=%u (expected %u)\n", pause.reason,
                QFLI_DEBUG_PAUSE_BREAKPOINT);
        abort();
    }
    QfliFrame frame = current_frame(session);
    if (frame.line != 15) {
        fprintf(stderr, "breakpoint stopped on line %u, expected 15\n", frame.line);
        abort();
    }
    if (!frame.file_path || !strstr(frame.file_path, "debug_breakpoint.rs")) {
        fprintf(stderr, "breakpoint file=\"%s\"\n", frame.file_path ? frame.file_path : "");
        abort();
    }
    // `value` is initialized to 21 before the call on line 15.
    expect_local_value(session, "value", "21");

    // Step-in must descend into `double`, whose body is line 10.
    assert(resume_debug(session, QFLI_DEBUG_STEP_IN) == 0);
    int descended = 0;
    for (int guard = 0; guard < 50; guard++) {
        QfliDebugPause step = current_pause(session);
        if (step.reason == QFLI_DEBUG_PAUSE_TERMINATED || step.reason == QFLI_DEBUG_PAUSE_ERROR) {
            break;
        }
        QfliFrame inner = current_frame(session);
        if (inner.line == 10) {
            descended = 1;
            // Inside `double`, the parameter is bound to the argument.
            expect_local_value(session, "value", "21");
            break;
        }
        if (resume_debug(session, QFLI_DEBUG_STEP_IN) != 0) { break; }
    }
    if (!descended) {
        fprintf(stderr, "step-in never entered `double` (line 10)\n");
        abort();
    }
    cancel_debug(session);
    destroy_debug(session);
    puts("PASS debug breakpoint and step-in into a call");
}

// Step-over must not descend into the call: it stays in `main`.
static void step_over(const char *directory, const char *sysroot) {
    char *source = fixture_path(directory, "debug_breakpoint");
    QfliBreakpoint point = { .file_path = source, .line = 15, .column = 0 };
    QfliDebugConfig config = debug_config(source, sysroot);
    config.breakpoints = &point;
    config.breakpoint_count = 1;
    QfliDebugSession *session = create_debug(&config, NULL);
    assert(session);
    assert(start_debug(session) == 0);
    assert(resume_debug(session, QFLI_DEBUG_CONTINUE) == 0);
    QfliFrame before = current_frame(session);
    assert(before.line == 15);
    size_t depth_before = frame_count(session);

    assert(resume_debug(session, QFLI_DEBUG_STEP_OVER) == 0);
    QfliDebugPause pause = current_pause(session);
    if (pause.reason == QFLI_DEBUG_PAUSE_TERMINATED || pause.reason == QFLI_DEBUG_PAUSE_ERROR) {
        fprintf(stderr, "step-over ended the program unexpectedly\n");
        abort();
    }
    QfliFrame after = current_frame(session);
    // Step-over must not have entered `double`: same stack depth and a line in
    // `main`, never the callee body on line 10.
    if (after.line == 10) {
        fprintf(stderr, "step-over descended into `double`\n");
        abort();
    }
    if (frame_count(session) != depth_before) {
        fprintf(stderr, "step-over changed depth %zu -> %zu\n", depth_before, frame_count(session));
        abort();
    }
    assert(after.line == 16);
    cancel_debug(session);
    destroy_debug(session);
    puts("PASS debug step-over stays in the caller");
}

// Locals must report exact scalar renderings and honest states for the rest.
static void locals(const char *directory, const char *sysroot) {
    QfliDebugSession *session = open_debug(directory, sysroot, "debug_locals");
    assert(start_debug(session) == 0);
    // Step to the last assignment line (18) where every local is live.
    int reached = 0;
    for (int guard = 0; guard < 300 && !reached; guard++) {
        if (resume_debug(session, QFLI_DEBUG_STEP_IN) != 0) { break; }
        QfliDebugPause step = current_pause(session);
        if (step.reason == QFLI_DEBUG_PAUSE_TERMINATED || step.reason == QFLI_DEBUG_PAUSE_ERROR) {
            break;
        }
        QfliFrame frame = current_frame(session);
        if (frame.line == 18) {
            reached = 1;
        }
    }
    if (!reached) {
        fprintf(stderr, "never reached line 18 of debug_locals\n");
        abort();
    }
    // Exact scalar renderings.
    expect_local_value(session, "small", "-1");
    expect_local_value(session, "letter", "'A'");
    expect_local_value(session, "flag", "true");
    // Aggregates and references are reported as unsupported, never guessed.
    expect_local_state(session, "pair", QFLI_LOCAL_UNSUPPORTED);
    expect_local_state(session, "text", QFLI_LOCAL_UNSUPPORTED);
    // `later` is declared but not yet assigned on this line.
    expect_local_state(session, "later", QFLI_LOCAL_UNINITIALIZED);

    // Types come from rustc, so they are exact.
    QfliLocal local = {0};
    if (!find_local(session, "small", &local) || !local.type_name
        || strcmp(local.type_name, "i8")) {
        fprintf(stderr, "small type=\"%s\"\n", local.type_name ? local.type_name : "");
        abort();
    }
    cancel_debug(session);
    destroy_debug(session);
    puts("PASS debug locals values and states");
}

// A paused session must release control: cancel wakes it and no lock deadlocks.
static void cancel_while_paused(const char *directory, const char *sysroot) {
    QfliDebugSession *session = open_debug(directory, sysroot, "debug_basic");
    assert(start_debug(session) == 0);
    QfliDebugPause entry = current_pause(session);
    assert(entry.reason == QFLI_DEBUG_PAUSE_ENTRY);
    // While paused, the snapshot readers must work without touching the worker.
    assert(frame_count(session) >= 1);
    // Cancel a paused session: it must terminate rather than hang.
    cancel_debug(session);
    assert(wait_debug(session) == 0);
    QfliDebugPause pause = current_pause(session);
    assert(pause.reason == QFLI_DEBUG_PAUSE_CANCELLED && pause.exit_code == 130);
    QfliDebugStatus status = current_status(session);
    assert(status.state == QFLI_DEBUG_TERMINATED && status.worker_exited);
    assert(frame_count(session) == 0);
    destroy_debug(session);
    puts("PASS debug cancel while paused");
}

// The step budget must be enforced and reported as a limit, not as success.
static void step_limit(const char *directory, const char *sysroot) {
    char *source = fixture_path(directory, "debug_basic");
    QfliDebugConfig config = debug_config(source, sysroot);
    config.max_steps = 2;
    QfliDebugSession *session = create_debug(&config, NULL);
    assert(session);
    assert(start_debug(session) == 0);
    QfliDebugPause pause = current_pause(session);
    assert(pause.reason == QFLI_DEBUG_PAUSE_ENTRY);
    // Run with a 2-step budget: the loop must stop on the limit.
    assert(resume_debug(session, QFLI_DEBUG_CONTINUE) == 0);
    pause = current_pause(session);
    if (pause.reason != QFLI_DEBUG_PAUSE_LIMIT || pause.steps > 2) {
        fprintf(stderr, "step limit reason=%u steps=%" PRIu64 "\n", pause.reason, pause.steps);
        abort();
    }
    assert(pause.exit_code == 124);
    assert(current_status(session).worker_exited);
    destroy_debug(session);
    puts("PASS debug step budget");
}

// A source error must be reported as an error pause, not a silent stop.
static void source_error(const char *directory, const char *sysroot) {
    char *source = fixture_path(directory, "debug_type_error");
    QfliDebugConfig config = debug_config(source, sysroot);
    QfliDebugSession *session = create_debug(&config, NULL);
    assert(session);
    // The compile fails, so start reports a terminal (non-paused) state.
    assert(start_debug(session) == -1);
    QfliDebugPause pause = current_pause(session);
    if (pause.reason != QFLI_DEBUG_PAUSE_ERROR) {
        fprintf(stderr, "source error reason=%u\n", pause.reason);
        abort();
    }
    size_t length = copy_debug_output(session, NULL, 0);
    if (length == 0) {
        fprintf(stderr, "source error produced no diagnostics\n");
        abort();
    }
    char *text = calloc(length + 1, 1);
    assert(text);
    assert(copy_debug_output(session, (uint8_t *)text, length) == length);
    if (!strstr(text, "E0308")) {
        fprintf(stderr, "diagnostics missing E0308: %s\n", text);
        abort();
    }
    free(text);
    destroy_debug(session);
    puts("PASS debug source error reports an error pause");
}

static void pause_generations(const char *directory, const char *sysroot) {
    QfliDebugSession *session = open_debug(directory, sysroot, "debug_basic");
    assert(start_debug(session) == 0);
    QfliDebugStatus before = current_status(session);
    assert(before.state == QFLI_DEBUG_PAUSED && before.pause_generation > 0);
    assert(resume_at(session, QFLI_DEBUG_STEP_IN, before.pause_generation + 1) == -1);
    assert(current_status(session).pause_generation == before.pause_generation);
    assert(current_pause(session).steps == 0);
    assert(resume_at(session, QFLI_DEBUG_STEP_IN, before.pause_generation) == 0);
    QfliDebugStatus after = current_status(session);
    assert(after.state == QFLI_DEBUG_PAUSED);
    assert(after.pause_generation > before.pause_generation);
    assert(after.revision > before.revision);
    assert(current_pause(session).steps > 0);
    assert(resume_at(session, QFLI_DEBUG_STEP_IN, before.pause_generation) == -1);
    assert(current_status(session).pause_generation == after.pause_generation);
    assert(start_debug(session) == -1);
    destroy_debug(session);
    puts("PASS debug commands reject stale pause generations");
}

static void compiler_busy(const char *directory, const char *sysroot) {
    QfliDebugSession *first = open_debug(directory, sysroot, "debug_basic");
    QfliDebugSession *second = open_debug(directory, sysroot, "debug_basic");
    assert(start_debug(first) == 0);
    // A paused compiler owns its real lease. A second foreground start must
    // fail fast instead of blocking until the first user resumes or stops.
    assert(start_debug(second) == 2);
    QfliDebugStatus status = current_status(second);
    assert(status.state == QFLI_DEBUG_NEW && status.worker_exited);
    assert(status.pause_generation == 0);
    destroy_debug(first); // joins and releases the real compiler lease
    assert(start_debug(second) == 0); // same unconsumed busy handle is retryable
    destroy_debug(second);
    puts("PASS debug busy start retries after joined cleanup");
}

static void step_out(const char *directory, const char *sysroot) {
    char *source = fixture_path(directory, "debug_breakpoint");
    QfliBreakpoint point = { .file_path = source, .line = 10, .column = 0 };
    QfliDebugConfig config = debug_config(source, sysroot);
    config.breakpoints = &point;
    config.breakpoint_count = 1;
    QfliDebugSession *session = create_debug(&config, NULL);
    assert(session && start_debug(session) == 0);
    assert(resume_debug(session, QFLI_DEBUG_CONTINUE) == 0);
    assert(current_frame(session).line == 10);
    size_t depth = frame_count(session);
    assert(resume_debug(session, QFLI_DEBUG_STEP_OUT) == 0);
    assert(current_pause(session).reason == QFLI_DEBUG_PAUSE_STEP);
    assert(frame_count(session) < depth);
    assert(current_frame(session).line != 10);
    assert(strstr(current_frame(session).function, "main"));
    destroy_debug(session);
    puts("PASS debug step-out returns to the actual caller");
}

static void unsigned_scalars(const char *directory, const char *sysroot) {
    char *source = fixture_path(directory, "debug_scalars");
    QfliBreakpoint point = {
        .file_path = source, .line = marker_line(source, "SCALAR_BREAKPOINT"), .column = 0
    };
    QfliDebugConfig config = debug_config(source, sysroot);
    config.breakpoints = &point;
    config.breakpoint_count = 1;
    QfliDebugSession *session = create_debug(&config, NULL);
    assert(session && start_debug(session) == 0);
    assert(resume_debug(session, QFLI_DEBUG_CONTINUE) == 0);
    assert(current_pause(session).reason == QFLI_DEBUG_PAUSE_BREAKPOINT);
    expect_local_value(session, "high8", "255");
    expect_local_value(session, "high64", "18446744073709551615");
    expect_local_value(session, "high128", "340282366920938463463374607431768211455");
    expect_local_value(session, "signed_min", "-170141183460469231731687303715884105728");
    expect_local_value(session, "floating", "1.5");
    expect_local_value(session, "negative_zero", "-0.0");
    expect_local_value(session, "escaped", "'\\n'");
    expect_local_value(session, "emoji", "'\xF0\x9F\x98\x80'");
    expect_local_value(session, "borrowed", "42");
    expect_local_state(session, "address", QFLI_LOCAL_UNSUPPORTED);
    destroy_debug(session);
    puts("PASS debug wide unsigned, indirect and escaped scalar values");
}

static void live_output(const char *directory, const char *sysroot) {
    char *source = fixture_path(directory, "debug_output");
    QfliBreakpoint point = {
        .file_path = source, .line = marker_line(source, "OUTPUT_BREAKPOINT"), .column = 0
    };
    QfliDebugConfig config = debug_config(source, sysroot);
    config.breakpoints = &point;
    config.breakpoint_count = 1;
    QfliDebugSession *session = create_debug(&config, NULL);
    assert(session && start_debug(session) == 0);
    uint64_t revision = current_status(session).revision;
    assert(resume_debug(session, QFLI_DEBUG_CONTINUE) == 0);
    assert(current_pause(session).reason == QFLI_DEBUG_PAUSE_BREAKPOINT);
    assert(current_status(session).revision > revision);
    char output[128] = {0}, errors[128] = {0};
    size_t length = copy_channel(session, 0, (uint8_t *)output, sizeof(output) - 1);
    assert(length == strlen("debug stdout \xF0\x9F\x98\x80\n"));
    assert(!strcmp(output, "debug stdout \xF0\x9F\x98\x80\n"));
    length = copy_channel(session, 1, (uint8_t *)errors, sizeof(errors) - 1);
    assert(length == strlen("debug stderr\n") && !strcmp(errors, "debug stderr\n"));
    assert(copy_channel(session, 3, NULL, 0) == 0);
    assert(resume_debug(session, QFLI_DEBUG_CONTINUE) == 0);
    assert(current_status(session).state == QFLI_DEBUG_TERMINATED);
    assert(current_status(session).worker_exited);
    assert(current_pause(session).reason == QFLI_DEBUG_PAUSE_TERMINATED);
    assert(current_pause(session).exit_code == 0);
    assert(wait_debug(session) == 0);
    destroy_debug(session);
    puts("PASS debug retained live stdout/stderr and real exit");
}

static void pause_running(const char *directory, const char *sysroot) {
    char *source = fixture_path(directory, "debug_spin");
    QfliDebugConfig config = debug_config(source, sysroot);
    config.max_steps = 100000000;
    QfliDebugSession *session = create_debug(&config, NULL);
    assert(session && start_debug(session) == 0);
    ResumeCall call = { .session = session, .result = -99 };
#ifdef _WIN32
    HANDLE thread = CreateThread(NULL, 0, continue_on_thread, &call, 0, NULL);
    assert(thread);
#else
    pthread_t thread;
    assert(pthread_create(&thread, NULL, continue_on_thread, &call) == 0);
#endif
    int running = 0;
    for (int guard = 0; guard < 5000; guard++) {
        if (current_status(session).state == QFLI_DEBUG_RUNNING) { running = 1; break; }
        sleep_millis(1);
    }
    assert(running);
    pause_debug(session);
#ifdef _WIN32
    assert(WaitForSingleObject(thread, 10000) == WAIT_OBJECT_0);
    CloseHandle(thread);
#else
    assert(pthread_join(thread, NULL) == 0);
#endif
    assert(call.result == 0);
    assert(current_status(session).state == QFLI_DEBUG_PAUSED);
    assert(current_pause(session).reason == QFLI_DEBUG_PAUSE_REQUESTED);
    cancel_debug(session);
    assert(wait_debug(session) == 0);
    assert(current_pause(session).reason == QFLI_DEBUG_PAUSE_CANCELLED);
    destroy_debug(session);
    puts("PASS debug asynchronous pause and joined stop");
}

int main(int argc, char **argv) {
    if (argc != 4) {
        fprintf(stderr, "Usage: %s <adapter-library> <MIR-sysroot> <fixture-directory>\n", argv[0]);
        return 2;
    }
    NativeLibrary library = open_library(argv[1]);
    if (!library) { return 1; }
    capabilities = library_symbol(library, "qfli_miri_debug_capabilities");
    create_debug = library_symbol(library, "qfli_miri_debug_create");
    start_debug = library_symbol(library, "qfli_miri_debug_start");
    resume_debug = library_symbol(library, "qfli_miri_debug_resume");
    resume_at = library_symbol(library, "qfli_miri_debug_resume_at");
    debug_status = library_symbol(library, "qfli_miri_debug_status");
    wait_debug = library_symbol(library, "qfli_miri_debug_wait");
    pause_debug = library_symbol(library, "qfli_miri_debug_pause");
    cancel_debug = library_symbol(library, "qfli_miri_debug_cancel");
    destroy_debug = library_symbol(library, "qfli_miri_debug_destroy");
    pause_info = library_symbol(library, "qfli_miri_debug_pause_info");
    frame_count = library_symbol(library, "qfli_miri_debug_frame_count");
    frame_at = library_symbol(library, "qfli_miri_debug_frame");
    locals_at = library_symbol(library, "qfli_miri_debug_locals");
    copy_debug_output = library_symbol(library, "qfli_miri_debug_copy_output");
    copy_channel = library_symbol(library, "qfli_miri_debug_copy_output_channel");
    // The debugger is an optional extension: report a skip, not a pass.
    if (!capabilities || !create_debug || !start_debug || !resume_debug || !pause_debug
        || !cancel_debug || !destroy_debug || !pause_info || !frame_count || !frame_at
        || !locals_at || !copy_debug_output || !resume_at || !debug_status
        || !wait_debug || !copy_channel) {
        fprintf(stderr, "SKIP debug extension is not present in this adapter build\n");
        return 3;
    }

    symbols_and_nulls();
    invalid_config(argv[3], argv[2]);
    entry_and_steps(argv[3], argv[2]);
    breakpoint(argv[3], argv[2]);
    step_over(argv[3], argv[2]);
    step_out(argv[3], argv[2]);
    locals(argv[3], argv[2]);
    cancel_while_paused(argv[3], argv[2]);
    step_limit(argv[3], argv[2]);
    source_error(argv[3], argv[2]);
    pause_generations(argv[3], argv[2]);
    compiler_busy(argv[3], argv[2]);
    unsigned_scalars(argv[3], argv[2]);
    live_output(argv[3], argv[2]);
    pause_running(argv[3], argv[2]);
    // The compiler stays live for the process; do not unload it.
    return 0;
}
