/* Real POSIX dlopen regression suite for the additive ABI-1 project root.
 *
 * cc -std=c11 -Wall -Wextra -Werror native/miri_adapter/fs_abi_test.c \
 *    -ldl -o /tmp/qfli-fs-abi-test
 * /tmp/qfli-fs-abi-test <adapter.so> <MIR-sysroot> <fixture-directory> \
 *                     [backend.so|-] [exported-catalog-directory|-]
 *
 * Exit 0: runtime and compiler confinement checks passed.
 * Exit 1: runtime/invariant failure. Exit 2: setup/usage failure.
 * Exit 3: additive symbol absent (NOT a pass).
 * Exit 4: runtime checks passed, compiler include/env boundary REMAINS OPEN.
 *
 * No runtime stub is linked. The adapter/compiler must remain loaded until
 * process exit. This is host evidence, never packaged OHOS execution evidence.
 */
#define _POSIX_C_SOURCE 200809L
#define _XOPEN_SOURCE 700
#include "qfli_miri.h"

#include <arpa/inet.h>
#include <dirent.h>
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <poll.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <unistd.h>

#ifndef PATH_MAX
#define PATH_MAX 4096
#endif

static uint32_t (*abi_version)(void);
static QfliSession *(*create_project)(const QfliConfig *, const char *, const char *);
static int32_t (*run_session)(QfliSession *);
static size_t (*copy_output)(const QfliSession *, uint32_t, uint8_t *, size_t);
static int32_t (*get_result)(const QfliSession *, QfliResult *);
static void (*destroy_session)(QfliSession *);
static int failures;

typedef struct { char *data; size_t length; } Bytes;
typedef struct { QfliResult result; Bytes out, err, diag; } Outcome;
typedef struct { size_t count; char paths[8][PATH_MAX]; } Temporaries;
typedef struct { const char *name; char *value; } HostEnvironment;

static HostEnvironment host_environment[] = {
    { "HOME", NULL }, { "PATH", NULL }, { "LD_LIBRARY_PATH", NULL },
    { "DYLD_LIBRARY_PATH", NULL }, { "USERPROFILE", NULL },
    { "QFLI_SANDBOX_HOST_SECRET", NULL },
};
static const char *outside_bytes = "outside-unchanged";
static const char *host_secret = "qfli-fs-compiler-private-sentinel-74291";
static char suite_root[PATH_MAX], project_root[PATH_MAX], outside_directory[PATH_MAX];
static char host_cwd[PATH_MAX];
static const char *sysroot_path, *fixture_directory, *backend_path;

static void remove_owned_tree(const char *path);

static void fatal(const char *message) {
    fprintf(stderr, "SETUP ERROR: %s (errno=%d: %s)\n", message, errno, strerror(errno));
    exit(2);
}

static void require(int condition, const char *message) {
    if (!condition) fatal(message);
}

static void check(int condition, const char *message) {
    if (!condition) { fprintf(stderr, "FAIL %s\n", message); failures++; }
}

static void format(char *destination, size_t capacity, const char *pattern, ...) {
    va_list arguments;
    va_start(arguments, pattern);
    int written = vsnprintf(destination, capacity, pattern, arguments);
    va_end(arguments);
    require(written >= 0 && (size_t)written < capacity, "test path/output is too long");
}

static void join(char destination[PATH_MAX], const char *root, const char *name) {
    format(destination, PATH_MAX, "%s/%s", root, name);
}

static Bytes read_file(const char *path) {
    FILE *file = fopen(path, "rb");
    require(file != NULL, path);
    require(fseek(file, 0, SEEK_END) == 0, "seek input file");
    long length = ftell(file);
    require(length >= 0 && length < 16 * 1024 * 1024, "invalid input file length");
    rewind(file);
    Bytes bytes = { calloc((size_t)length + 1, 1), (size_t)length };
    require(bytes.data != NULL, "allocate file bytes");
    require(fread(bytes.data, 1, bytes.length, file) == bytes.length, "read complete file");
    require(fclose(file) == 0, "close input file");
    return bytes;
}

static void write_bytes(const char *path, const char *bytes, size_t length) {
    FILE *file = fopen(path, "wb");
    require(file != NULL, path);
    require(fwrite(bytes, 1, length, file) == length, "write complete test file");
    require(fclose(file) == 0, "close test file");
}

static void write_text(const char *path, const char *text) {
    write_bytes(path, text, strlen(text));
}

static int bytes_equal(const Bytes *bytes, const char *expected) {
    return bytes->length == strlen(expected) && !memcmp(bytes->data, expected, bytes->length);
}

static int bytes_contain(const Bytes *bytes, const char *expected) {
    size_t length = strlen(expected);
    if (length > bytes->length) return 0;
    for (size_t i = 0; i <= bytes->length - length; i++) {
        if (!memcmp(bytes->data + i, expected, length)) return 1;
    }
    return 0;
}

static void unchanged_file(const char *path, const char *expected) {
    struct stat state;
    if (lstat(path, &state) != 0 || !S_ISREG(state.st_mode)) {
        check(0, "outside/retained sentinel is missing or no longer a regular file");
        return;
    }
    Bytes bytes = read_file(path);
    check(bytes_equal(&bytes, expected), "outside/retained sentinel bytes changed");
    free(bytes.data);
}

static int entry_exists(const char *path) {
    struct stat state;
    if (lstat(path, &state) == 0) return 1;
    require(errno == ENOENT, "inspect test entry");
    return 0;
}

static void check_host_invariants(void) {
    char current[PATH_MAX], path[PATH_MAX];
    require(getcwd(current, sizeof current) != NULL, "read host cwd");
    check(!strcmp(current, host_cwd), "guest changed host process cwd");
    for (size_t i = 0; i < sizeof host_environment / sizeof host_environment[0]; i++) {
        const char *value = getenv(host_environment[i].name);
        check(value && !strcmp(value, host_environment[i].value), "adapter changed host environment");
    }
    join(path, suite_root, "qfli-outside-sentinel.txt");
    unchanged_file(path, outside_bytes);
    join(path, outside_directory, "sentinel.txt");
    unchanged_file(path, outside_bytes);
    join(path, suite_root, "qfli-outside-created.txt");
    check(!entry_exists(path), "guest created a file above its project");
    join(path, suite_root, "qfli-outside-directory");
    check(!entry_exists(path), "guest created a directory above its project");
    join(path, outside_directory, "new-directory");
    check(!entry_exists(path), "guest created a directory through an outside symlink");
    join(path, project_root, "keep.txt");
    unchanged_file(path, "ordinary-project-file");
}

static Temporaries temporaries(void) {
    Temporaries found = {0};
    DIR *directory = opendir(project_root);
    require(directory != NULL, "list project temporaries");
    struct dirent *entry;
    while ((entry = readdir(directory))) {
        if (strncmp(entry->d_name, ".qfli-miri-tmp-", strlen(".qfli-miri-tmp-"))) continue;
        require(found.count < sizeof found.paths / sizeof found.paths[0], "too many temporary directories");
        join(found.paths[found.count], project_root, entry->d_name);
        struct stat state;
        require(lstat(found.paths[found.count], &state) == 0, "inspect temporary directory");
        check(S_ISDIR(state.st_mode) && (state.st_mode & 0777) == 0700,
              "session temporary is not a private mode-0700 directory");
        found.count++;
    }
    require(closedir(directory) == 0, "close project directory");
    return found;
}

static void no_temporaries(void) {
    check(temporaries().count == 0, "destroy leaked a session temporary directory");
}

static void copy_fixture(const char *name, char source[PATH_MAX]) {
    char fixture[PATH_MAX];
    join(fixture, fixture_directory, name);
    join(source, project_root, "main.rs");
    Bytes bytes = read_file(fixture);
    write_bytes(source, bytes.data, bytes.length);
    Bytes written = read_file(source);
    require(written.length == bytes.length && !memcmp(written.data, bytes.data, bytes.length),
            "fixture bytes changed while copying into project");
    free(written.data);
    free(bytes.data);
}

static QfliConfig config_for(const char *source) {
    return (QfliConfig) {
        .abi_version = 1, .source_path = source, .sysroot_path = sysroot_path,
        .max_basic_blocks = 100000000, .timeout_ms = 120000,
        .max_output_bytes = 1048576, .max_guest_memory_bytes = 64 * 1024 * 1024,
    };
}

static QfliSession *new_session(const char *source) {
    char *source_copy = strdup(source), *root_copy = strdup(project_root);
    char *sysroot_copy = strdup(sysroot_path);
    char *backend_copy = backend_path ? strdup(backend_path) : NULL;
    require(source_copy && root_copy && sysroot_copy && (!backend_path || backend_copy),
            "copy ABI input strings");
    QfliConfig config = config_for(source_copy);
    config.sysroot_path = sysroot_copy;
    QfliSession *session = create_project(&config, backend_copy, root_copy);
    // No pointer passed by the host survives create. Actual run must still use
    // the copied source/sysroot/root/backend values after these are destroyed.
    memset(source_copy, 0, strlen(source_copy)); free(source_copy);
    memset(root_copy, 0, strlen(root_copy)); free(root_copy);
    memset(sysroot_copy, 0, strlen(sysroot_copy)); free(sysroot_copy);
    if (backend_copy) { memset(backend_copy, 0, strlen(backend_copy)); free(backend_copy); }
    check(session != NULL, "create_with_project rejected a valid explicit project");
    check_host_invariants();
    return session;
}

static Bytes output(QfliSession *session, uint32_t channel) {
    size_t length = copy_output(session, channel, NULL, 0);
    require(length <= 1048576, "native output exceeded configured byte bound");
    Bytes bytes = { calloc(length + 1, 1), length };
    require(bytes.data != NULL, "allocate native output");
    require(copy_output(session, channel, (uint8_t *)bytes.data, length) == length,
            "native output changed after blocking run completed");
    return bytes;
}

static Outcome run(QfliSession *session) {
    Outcome captured = { .result = { .state = UINT32_MAX, .exit_code = -1 } };
    if (run_session(session) != 0) {
        check(0, "native run was not accepted");
        exit(1);
    }
    if (get_result(session, &captured.result) != 0
        || captured.result.state == QFLI_READY || captured.result.state == QFLI_RUNNING) {
        check(0, "blocking native run did not return a final result");
        exit(1);
    }
    captured.out = output(session, QFLI_STDOUT);
    captured.err = output(session, QFLI_STDERR);
    captured.diag = output(session, QFLI_DIAGNOSTICS);
    check(run_session(session) == -1, "completed session accepted a second run");
    check_host_invariants();
    return captured;
}

static void release_output(Outcome *captured) {
    free(captured->out.data); free(captured->err.data); free(captured->diag.data);
}

static void expect_success_bytes(const char *name, Outcome *captured,
                                 const char *expected, size_t expected_length) {
    int okay = captured->result.state == QFLI_FINISHED && captured->result.exit_code == 0
        && captured->result.basic_blocks > 0 && captured->err.length == 0
        && (!expected || (captured->out.length == expected_length
                         && !memcmp(captured->out.data, expected, expected_length)));
    if (!okay) {
        fprintf(stderr, "FAIL %s state=%u exit=%d blocks=%llu\nstdout: %s\nstderr: %s\ndiag: %s\n",
                name, captured->result.state, captured->result.exit_code,
                (unsigned long long)captured->result.basic_blocks,
                captured->out.data, captured->err.data, captured->diag.data);
        failures++;
    }
}

static void expect_success(const char *name, Outcome *captured, const char *expected) {
    expect_success_bytes(name, captured, expected, expected ? strlen(expected) : 0);
}

static void fixture(const char *name, const char *expected) {
    int before = failures;
    char source[PATH_MAX];
    copy_fixture(name, source);
    QfliSession *session = new_session(source);
    if (!session) return;
    check(temporaries().count == 1, "one new session must own one temporary directory");
    Outcome captured = run(session);
    expect_success(name, &captured, expected);
    release_output(&captured);
    destroy_session(session);
    no_temporaries();
    check_host_invariants();
    if (before == failures) printf("PASS %s\n", name);
}

static int contains_isolation(const Outcome *captured) {
    return strstr(captured->diag.data, "isolation") || strstr(captured->err.data, "isolation")
        || strstr(captured->diag.data, "isolated") || strstr(captured->err.data, "isolated");
}

static void expect_socket_denial(const char *name, const char *source) {
    int before = failures;
    QfliSession *session = new_session(source);
    if (!session) return;
    Outcome captured = run(session);
    check(captured.result.state == QFLI_FINISHED && captured.result.exit_code != 0
          && captured.result.basic_blocks > 0 && captured.out.length == 0
          && contains_isolation(&captured)
          && (strstr(captured.diag.data, "socket") || strstr(captured.err.data, "socket")),
          "network denial needs a real socket isolation diagnostic, not any nonzero exit");
    if (before != failures) {
        fprintf(stderr, "network diagnostic: %s\n%s\n", captured.err.data, captured.diag.data);
    }
    release_output(&captured);
    destroy_session(session);
    no_temporaries();
    if (before == failures) printf("PASS %s\n", name);
}

static void network_denial(void) {
    char source[PATH_MAX], probe[1024];
    copy_fixture("fs_network_denied.rs", source);
    expect_socket_denial("fs_network_denied.rs", source);

    int listener = socket(AF_INET, SOCK_STREAM, 0);
    require(listener >= 0, "create host loopback observation listener");
    require(fcntl(listener, F_SETFD, FD_CLOEXEC) == 0, "mark host observation socket close-on-exec");
    struct sockaddr_in address = { .sin_family = AF_INET, .sin_addr.s_addr = htonl(INADDR_LOOPBACK) };
    require(bind(listener, (struct sockaddr *)&address, sizeof address) == 0, "bind host loopback listener");
    require(listen(listener, 4) == 0, "listen for forbidden guest connection");
    socklen_t length = sizeof address;
    require(getsockname(listener, (struct sockaddr *)&address, &length) == 0, "read ephemeral loopback port");
    format(probe, sizeof probe,
           "fn main() { let _ = std::net::TcpStream::connect(\"127.0.0.1:%u\"); "
           "println!(\"network-operation-returned\"); }\n", (unsigned)ntohs(address.sin_port));
    write_text(source, probe);
    expect_socket_denial("loopback socket denial", source);
    struct pollfd watched = { .fd = listener, .events = POLLIN };
    int ready;
    do { ready = poll(&watched, 1, 0); } while (ready < 0 && errno == EINTR);
    require(ready >= 0, "poll forbidden connection observer");
    check(ready == 0, "guest established a real host loopback connection");
    require(close(listener) == 0, "close host loopback observation listener");
    check_host_invariants();
}

static void invalid_roots(void) {
    int before = failures;
    char inside[PATH_MAX], outside[PATH_MAX], linked[PATH_MAX], missing[PATH_MAX];
    copy_fixture("fs_environment.rs", inside);
    join(outside, suite_root, "outside-source.rs");
    write_text(outside, "fn main() { panic!(\"outside source executed\"); }\n");
    join(linked, project_root, "linked-source.rs");
    require(symlink(outside, linked) == 0, "create out-of-root source symlink");
    join(missing, suite_root, "missing-root");
    const char *sources[] = { outside, linked, inside, inside, inside, inside, inside };
    const char *roots[] = { project_root, project_root, NULL, "relative-root", "/", missing, outside };
    for (size_t i = 0; i < sizeof sources / sizeof sources[0]; i++) {
        QfliConfig config = config_for(sources[i]);
        QfliSession *session = create_project(&config, backend_path, roots[i]);
        check(session == NULL, "invalid root/out-of-root canonical source was accepted");
        if (session) destroy_session(session);
        no_temporaries();
    }
    unchanged_file(outside, "fn main() { panic!(\"outside source executed\"); }\n");
    require(unlink(linked) == 0, "remove source symlink");
    check_host_invariants();
    if (before == failures) puts("PASS invalid roots and out-of-root/symlink source rejection");
}

static void symlink_denial(void) {
    char link[PATH_MAX], target[PATH_MAX];
    join(link, project_root, "escape-dir");
    require(symlink(outside_directory, link) == 0, "create outside directory symlink");
    join(link, project_root, "escape-file");
    join(target, outside_directory, "sentinel.txt");
    require(symlink(target, link) == 0, "create outside file symlink");
    fixture("fs_symlink_escape.rs", "filesystem-symlink-escape-denied\n");
    check(!entry_exists(link), "guest did not remove the link itself");
    if (entry_exists(link)) require(unlink(link) == 0, "remove leftover file symlink");
    join(link, project_root, "escape-dir");
    require(unlink(link) == 0, "remove directory symlink without following it");
    check_host_invariants();
}

static void independent_sessions(void) {
    int before = failures;
    char first_source[PATH_MAX], second_source[PATH_MAX], work[PATH_MAX], marker[PATH_MAX];
    char temporary_source[PATH_MAX], expected[PATH_MAX * 2 + 64];
    copy_fixture("fs_session_first.rs", temporary_source);
    join(first_source, project_root, "first.rs");
    require(rename(temporary_source, first_source) == 0, "retain first session source");
    copy_fixture("fs_session_second.rs", temporary_source);
    join(second_source, project_root, "second.rs");
    require(rename(temporary_source, second_source) == 0, "retain second session source");
    join(work, project_root, "session-work");
    require(mkdir(work, 0700) == 0, "create session-local cwd target");
    QfliSession *first = new_session(first_source);
    if (!first) return;
    Temporaries one = temporaries();
    require(one.count == 1, "first session temporary inventory");
    QfliSession *second = new_session(second_source);
    if (!second) { destroy_session(first); return; }
    Temporaries two = temporaries();
    require(two.count == 2, "second session temporary inventory");
    const char *second_temporary = !strcmp(two.paths[0], one.paths[0]) ? two.paths[1] : two.paths[0];
    check(strcmp(one.paths[0], second_temporary) != 0, "sessions reused a temporary directory");
    join(marker, second_temporary, "owned-marker");
    write_text(marker, "second-temporary-retained");

    Outcome captured = run(first);
    format(expected, sizeof expected, "temporary=%s\ncwd=%s\n", one.paths[0], work);
    expect_success("first independent cwd", &captured, expected);
    release_output(&captured);
    captured = run(second);
    format(expected, sizeof expected, "temporary=%s\ncwd=%s\n", second_temporary, project_root);
    expect_success("second independent cwd", &captured, expected);
    release_output(&captured);

    destroy_session(first);
    check(!entry_exists(one.paths[0]), "destroy did not remove its own temporary directory");
    check(entry_exists(second_temporary), "destroy removed another session's temporary directory");
    unchanged_file(marker, "second-temporary-retained");
    check(temporaries().count == 1, "destroy of first session removed too much or too little");
    destroy_session(second);
    no_temporaries();
    join(marker, work, "session-first.txt");
    unchanged_file(marker, "first-session-file");
    join(marker, project_root, "session-second.txt");
    unchanged_file(marker, "second-session-file");
    check_host_invariants();
    if (before == failures) puts("PASS distinct session temps/cwd and owned-only destroy cleanup");
    fixture("fs_environment.rs", "filesystem-environment-isolated\n");
}

static void temporary_replacement_cleanup(void) {
    int before = failures;
    char source[PATH_MAX], retained[PATH_MAX], retained_marker[PATH_MAX];
    char moved[PATH_MAX], moved_marker[PATH_MAX], replacement_marker[PATH_MAX];
    join(retained, project_root, "retained-cleanup-directory");
    require(mkdir(retained, 0700) == 0, "create ordinary cleanup-replacement directory");
    join(retained_marker, retained, "sentinel.txt");
    write_text(retained_marker, "ordinary-project-directory-retained");
    join(moved, project_root, "renamed-owned-temporary");
    check(!entry_exists(moved), "renamed temporary destination unexpectedly exists");
    copy_fixture("fs_temp_replace.rs", source);
    QfliSession *session = new_session(source);
    if (!session) return;
    Temporaries original = temporaries();
    require(original.count == 1, "cleanup-replacement session temporary inventory");
    join(replacement_marker, original.paths[0], "sentinel.txt");
    join(moved_marker, moved, "owned-marker.txt");

    Outcome captured = run(session);
    expect_success("guest temporary-directory replacement", &captured,
                   "filesystem-temporary-replaced\n");
    release_output(&captured);
    check(!entry_exists(retained), "guest did not move the ordinary directory onto the temporary name");
    unchanged_file(replacement_marker, "ordinary-project-directory-retained");
    unchanged_file(moved_marker, "original-session-temporary");

    destroy_session(session);
    // Cleanup must never recursively remove a replacement directory merely
    // because it has the remembered name, or chase the renamed original by a
    // guest-chosen path. Both are left for this harness's owned-suite cleanup.
    check(entry_exists(original.paths[0]), "destroy removed a replacement temporary entry");
    unchanged_file(replacement_marker, "ordinary-project-directory-retained");
    unchanged_file(moved_marker, "original-session-temporary");
    check_host_invariants();
    if (entry_exists(original.paths[0])) remove_owned_tree(original.paths[0]);
    if (entry_exists(moved)) remove_owned_tree(moved);
    no_temporaries();
    if (before == failures) puts("PASS replacement temp preserved and renamed original not chased");
}

static int compiler_boundary(const char *name, int environment) {
    char source[PATH_MAX];
    copy_fixture(name, source);
    QfliSession *session = new_session(source);
    if (!session) return 0;
    Outcome captured = run(session);
    const char *secret = environment ? host_secret : outside_bytes;
    int disclosed = bytes_contain(&captured.out, secret) || bytes_contain(&captured.err, secret)
        || bytes_contain(&captured.diag, secret);
    int diagnostic = environment
        ? (strstr(captured.diag.data, "QFLI_SANDBOX_HOST_SECRET")
           && (strstr(captured.diag.data, "not defined") || strstr(captured.diag.data, "denied")
               || strstr(captured.diag.data, "not available")))
        : (strstr(captured.diag.data, "qfli-outside-sentinel")
           && (strstr(captured.diag.data, "denied") || strstr(captured.diag.data, "not permitted")
               || strstr(captured.diag.data, "not allowed"))
           && !strstr(captured.diag.data, "No such file")
           && !strstr(captured.diag.data, "not found"));
    int confined = captured.result.state == QFLI_FINISHED && captured.result.exit_code != 0
        && captured.result.basic_blocks == 0 && captured.out.length == 0 && !disclosed && diagnostic;
    printf("%s compiler boundary %s: state=%u exit=%d interpreted_blocks=%llu "
           "disclosed=%s relevant_diagnostic=%s (all output redacted)\n",
           confined ? "PASS" : "REMAINING", name, captured.result.state,
           captured.result.exit_code, (unsigned long long)captured.result.basic_blocks,
           disclosed ? "yes" : "no", diagnostic ? "yes" : "no");
    release_output(&captured);
    destroy_session(session);
    no_temporaries();
    check_host_invariants();
    return confined;
}

static void authored_capstones(const char *directory) {
    if (!directory) {
        puts("NOT_RUN authored164/165: provide an exported native_catalog case directory; "
             "full332 hash-bound catalog verification remains separate");
        return;
    }
    for (int topic = 164; topic <= 165; topic++) {
        for (int answer = 0; answer <= 1; answer++) {
            int before = failures;
            char name[80], input[PATH_MAX], source[PATH_MAX], expected_path[PATH_MAX];
            format(name, sizeof name, "rust-catalog-%03d-%s", topic, answer ? "answer" : "example");
            format(input, sizeof input, "%s/%s.rs", directory, name);
            join(source, project_root, "main.rs");
            Bytes authored = read_file(input);
            write_bytes(source, authored.data, authored.length);
            Bytes copied = read_file(source);
            require(copied.length == authored.length && !memcmp(copied.data, authored.data, authored.length),
                    "authored source changed during project overlay");
            free(copied.data); free(authored.data);
            Bytes expected = {0};
            if (!answer) {
                format(expected_path, sizeof expected_path, "%s/%s.stdout", directory, name);
                expected = read_file(expected_path);
            }
            QfliSession *session = new_session(source);
            if (!session) { free(expected.data); continue; }
            Outcome captured = run(session);
            expect_success_bytes(name, &captured, expected.data, expected.length);
            release_output(&captured); free(expected.data);
            destroy_session(session);
            no_temporaries();
            check_host_invariants();
            if (before == failures) printf("PASS %s stdout=%s\n", name, answer ? "unasserted-authored-contract" : "exact");
        }
    }
}

static void remove_owned_tree(const char *path) {
    struct stat state;
    require(lstat(path, &state) == 0, "inspect owned cleanup entry");
    if (S_ISDIR(state.st_mode)) {
        DIR *directory = opendir(path);
        require(directory != NULL, "open owned cleanup directory");
        struct dirent *entry;
        while ((entry = readdir(directory))) {
            if (!strcmp(entry->d_name, ".") || !strcmp(entry->d_name, "..")) continue;
            char child[PATH_MAX];
            join(child, path, entry->d_name);
            remove_owned_tree(child);
        }
        require(closedir(directory) == 0 && rmdir(path) == 0, "remove owned directory");
    } else {
        require(unlink(path) == 0, "remove owned file/link without following it");
    }
}

static void load_symbol(void *library, const char *name, void *destination, size_t size) {
    void *address = dlsym(library, name);
    require(address != NULL && size == sizeof address, name);
    memcpy(destination, &address, size);
}

#define LOAD(name, symbol) load_symbol(library, symbol, &name, sizeof name)

int main(int argc, char **argv) {
    if (argc < 4 || argc > 6) {
        fprintf(stderr, "Usage: %s <adapter.so> <MIR-sysroot> <fixtures> [backend.so|-] [catalog-case-dir|-]\n", argv[0]);
        return 2;
    }
    sysroot_path = argv[2];
    fixture_directory = argv[3];
    backend_path = argc >= 5 && strcmp(argv[4], "-") ? argv[4] : NULL;
    const char *catalog_directory = argc >= 6 && strcmp(argv[5], "-") ? argv[5] : NULL;
    require(getcwd(host_cwd, sizeof host_cwd) != NULL, "capture original host cwd");
    for (size_t i = 0; i < sizeof host_environment / sizeof host_environment[0]; i++) {
        const char *name = host_environment[i].name;
        if (!strcmp(name, "QFLI_SANDBOX_HOST_SECRET")) {
            require(setenv(name, host_secret, 1) == 0, "seed host-only compiler secret");
        } else if (!getenv(name) || !*getenv(name)) {
            require(setenv(name, "qfli-host-only-environment", 1) == 0, "seed absent host environment");
        }
        host_environment[i].value = strdup(getenv(name));
        require(host_environment[i].value != NULL, "copy host environment sentinel");
    }
    void *library = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
    if (!library) { fprintf(stderr, "dlopen failed: %s\n", dlerror()); return 2; }
    if (!dlsym(library, "qfli_miri_create_with_project")) {
        fputs("NOT_RUN project filesystem ABI extension is absent\n", stderr);
        return 3;
    }
    LOAD(abi_version, "qfli_miri_abi_version");
    LOAD(create_project, "qfli_miri_create_with_project");
    LOAD(run_session, "qfli_miri_run");
    LOAD(copy_output, "qfli_miri_copy_output");
    LOAD(get_result, "qfli_miri_result");
    LOAD(destroy_session, "qfli_miri_destroy");
    require(abi_version() == 1, "native ABI version must remain1");

    char pattern[] = "/tmp/qfli-miri-fs-XXXXXX";
    char *created = mkdtemp(pattern);
    require(created != NULL, "create exclusively owned suite directory");
    require(realpath(created, suite_root) != NULL, "canonicalize owned suite directory");
    join(project_root, suite_root, "project");
    join(outside_directory, suite_root, "outside");
    require(mkdir(project_root, 0700) == 0 && mkdir(outside_directory, 0700) == 0, "create test boundaries");
    printf("FS_ABI_SUITE %s\n", suite_root);
    char path[PATH_MAX];
    join(path, suite_root, "qfli-outside-sentinel.txt"); write_text(path, outside_bytes);
    join(path, outside_directory, "sentinel.txt"); write_text(path, outside_bytes);
    join(path, project_root, "keep.txt"); write_text(path, "ordinary-project-file");

    invalid_roots();
    fixture("fs_roundtrip.rs", "filesystem-roundtrip-ok\n");
    fixture("fs_escape.rs", "filesystem-escape-denied\n");
    symlink_denial();
    fixture("fs_environment.rs", "filesystem-environment-isolated\n");
    network_denial();
    independent_sessions();
    temporary_replacement_cleanup();
    authored_capstones(catalog_directory);
    int include_confined = compiler_boundary("fs_compile_include_escape.rs", 0);
    int env_confined = compiler_boundary("fs_compile_env_escape.rs", 1);
    check_host_invariants();
    no_temporaries();
    remove_owned_tree(suite_root);
    for (size_t i = 0; i < sizeof host_environment / sizeof host_environment[0]; i++) free(host_environment[i].value);
    // Do not dlclose: the pinned rustc/backend process-global state is live.
    if (failures) {
        fprintf(stderr, "FS_ABI_RESULT runtime_failures=%d compiler_boundaries=%s\n", failures,
                include_confined && env_confined ? "passed" : "remaining");
        return 1;
    }
    if (!include_confined || !env_confined) {
        puts("FS_ABI_RESULT runtime=passed compiler_boundaries=remaining");
        return 4;
    }
    puts("FS_ABI_RESULT runtime=passed compiler_boundaries=passed");
    return 0;
}
