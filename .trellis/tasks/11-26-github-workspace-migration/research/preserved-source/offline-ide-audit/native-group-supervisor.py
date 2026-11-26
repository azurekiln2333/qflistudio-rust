"""Bound a granted native gate, retaining exact Linux process-group ownership.

The worker remains the session/group leader after work ends, preventing group
ID reuse during cleanup. Only its group receives TERM/KILL. Ambiguous ownership
is an incomplete cleanup result, never permission to release a host lane.
"""

import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
import uuid


ROOT = Path(__file__).resolve().parents[2]
TOOLCHAIN = Path('/tmp/qfli-miri-cross-1.98.1/rustup/toolchains/1.98.1-x86_64-unknown-linux-gnu')
MIRI = Path('/tmp/qfli-miri-reference-1.98.1/source')
SYSROOT = Path('/tmp/qfli-miri-reference-1.98.1/sysroot')
BUILD = Path('/tmp/qfli-miri-debug-1.98.1')
DRIVER = TOOLCHAIN / 'lib/librustc_driver-eaf3ed1d23ca5027.so'
TARGET = 'x86_64-unknown-linux-gnu'
SUITES = ('abi_test', 'analysis_abi_test', 'debug_abi_test', 'fs_abi_test')


def utc():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    temporary.replace(path)


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def proc(pid):
    try:
        fields = Path('/proc', str(pid), 'stat').read_text().rsplit(')', 1)[1].split()
        return {'pid': int(pid), 'state': fields[0], 'ppid': int(fields[1]),
                'pgid': int(fields[2]), 'sid': int(fields[3]), 'startTicks': int(fields[19])}
    except (FileNotFoundError, ProcessLookupError):
        return None


def processes():
    result = []
    for entry in Path('/proc').iterdir():
        if entry.name.isdecimal():
            value = proc(int(entry.name))
            if value is not None:
                result.append(value)
    return result


def owns_group(identity, members, run_id):
    if identity['pid'] != identity['pgid'] or identity['pid'] != identity['sid']:
        return False
    anchor = proc(identity['pid'])
    if anchor and all(anchor[key] == identity[key] for key in ('pid', 'pgid', 'sid', 'startTicks')):
        return True
    # A crashed anchor may leave children. Verify their original session and
    # inherited unique token before signaling an otherwise unanchored group.
    if not members:
        return False
    verified = 0
    expected = ('QFLI_NATIVE_RUN_ID=' + run_id).encode()
    for member in members:
        if member['sid'] != identity['sid'] or member['startTicks'] < identity['startTicks']:
            return False
        try:
            environment = Path('/proc', str(member['pid']), 'environ').read_bytes().split(b'\0')
        except FileNotFoundError:
            continue
        except OSError:
            return False
        if expected not in environment:
            return False
        verified += 1
    return verified > 0


def source_paths():
    result = [ROOT / 'scripts' / name for name in
              ('build_miri_adapter.sh', 'check_miri_source.sh', 'miri_build_support.py',
               'generate_rust_content.py', 'generate_rust_native_catalog.py')]
    result += [ROOT / 'native/patches/miri-1.98.1-embedded-session.patch',
               Path(__file__).resolve(), ROOT / 'build/offline-ide-audit/run-native-validation-current.sh']
    result += [ROOT / 'tool/rust_content' / name for name in ('topics_001_084.json', 'topics_085_166.json')]
    result += [ROOT / 'assets/content_rust' / name for name in
               ('native_catalog.json', 'examples.json', 'tutorials.json')]
    for directory in ('native/miri_adapter', 'native/fixtures'):
        result += [item for item in (ROOT / directory).rglob('*') if item.is_file()]
    return sorted(set(result))


def source_map(paths):
    return {str(path.relative_to(ROOT)): digest(path) if path.is_file() else None for path in paths}


def export_capstones(snapshot, output):
    # Reuse the authored/catalog validators rather than trusting old exports.
    sys.path.insert(0, str(snapshot / 'scripts'))
    import generate_rust_native_catalog as catalog
    topics = catalog.load_topics(snapshot / 'tool/rust_content')
    document = json.loads((snapshot / catalog.DESTINATION).read_text(encoding='utf-8'))
    catalog.verify_native_catalog(document, topics)
    catalog.verify_paired_catalogs(snapshot, document)
    output.mkdir()
    selected = [case for case in document['cases'] if case['topicId'] in (164, 165)]
    if len(selected) != 4:
        raise RuntimeError('expected exact authored164/165 example+answer inventory')
    for case in selected:
        (output / (case['id'] + '.rs')).write_bytes(case['source'].encode('utf-8'))
        if case['stdoutAsserted']:
            (output / (case['id'] + '.stdout')).write_bytes(case['expectedStdout'].encode('utf-8'))
    hashes = {path.name: digest(path) for path in sorted(output.iterdir())}
    write_json(output / 'export.json', {'topicSourceSha256': document['catalog']['sourceSha256'],
                                      'cases': selected, 'exportSha256': hashes})
    return {path.name: digest(path) for path in sorted(output.iterdir())}


def worker(run_dir):
    # Exec resets caught signals for each child. This anchor survives TERM so
    # its group ID remains owned while native tools unwind.
    signal.signal(signal.SIGTERM, lambda *_: None)
    signal.signal(signal.SIGINT, lambda *_: None)
    state = {'status': 'running', 'exitCode': 2, 'phases': [], 'workerStartedAt': utc(),
             'sourceBefore': {}, 'sourceAfter': {}, 'sourceDrift': None, 'library': None,
             'snapshotBefore': {}, 'snapshotAfter': {},
             'exportedSourcesBefore': {}, 'exportedSourcesAfter': {}}
    result_path = run_dir / 'worker.json'
    write_json(run_dir / 'anchor.json', proc(os.getpid()))
    paths = []

    def phase(name, command, environment):
        record = {'name': name, 'command': [str(item) for item in command], 'startedAt': utc()}
        state['phases'].append(record)
        with (run_dir / (name + '.log')).open('wb') as log:
            child = subprocess.Popen(record['command'], env=environment, stdout=log, stderr=subprocess.STDOUT)
            record['process'] = proc(child.pid)
            write_json(result_path, state)
            record['exitCode'] = child.wait()
        record['finishedAt'] = utc()
        write_json(result_path, state)
        return record['exitCode']

    try:
        required = [TOOLCHAIN / 'bin/rustc', TOOLCHAIN / 'bin/cargo', DRIVER,
                    MIRI / 'Cargo.toml', SYSROOT / 'lib/rustlib' / TARGET / 'lib']
        missing = [str(path) for path in required if not path.exists()]
        compiler = shutil.which('cc')
        if compiler is None:
            missing.append('cc executable')
        if missing:
            state.update(status='unavailable', exitCode=3, unavailable=missing)
        else:
            paths = source_paths()
            state['sourceBefore'] = source_map(paths)
            snapshot = run_dir / 'source'
            for path in paths:
                destination = snapshot / path.relative_to(ROOT)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)
                if digest(destination) != state['sourceBefore'][str(path.relative_to(ROOT))]:
                    raise RuntimeError('source changed during snapshot: ' + str(path))
            state['snapshotBefore'] = dict(state['sourceBefore'])
            capstones = run_dir / 'fs-abi-catalog'
            state['exportedSourcesBefore'] = export_capstones(snapshot, capstones)
            state['phases'].append({'name': 'catalog-export', 'exitCode': 0,
                                    'finishedAt': utc(), 'source': 'verified frozen authored/native/UI catalogs'})
            environment = dict(os.environ, QFLI_ADAPTER_BUILD_ROOT=str(BUILD),
                               CARGO_HOME='/tmp/qfli-miri-cross-1.98.1/cargo',
                               CARGO_BUILD_JOBS='1', CARGO_INCREMENTAL='0')
            build_exit = phase('build', ['/bin/sh', snapshot / 'scripts/build_miri_adapter.sh',
                                         MIRI, TOOLCHAIN, TARGET], environment)
            state['exitCode'] = build_exit
            if build_exit == 0:
                library = run_dir / 'libqfli_miri.so'
                shutil.copy2(BUILD / 'target' / TARGET / 'debug/libqfli_miri.so', library)
                library.chmod(0o444)
                shutil.copy2(BUILD / ('adapter-build-' + TARGET + '.json'), run_dir / 'build.json')
                state['library'] = {'path': str(library), 'sha256': digest(library)}
                compiled = all(phase('compile-' + suite,
                                    [compiler, '-std=c11', '-Wall', '-Wextra', '-Werror', '-pthread',
                                     snapshot / 'native/miri_adapter' / (suite + '.c'),
                                     '-o', run_dir / suite, '-ldl'], environment) == 0 for suite in SUITES)
                if not compiled:
                    state['exitCode'] = 2
                else:
                    environment.update(LD_LIBRARY_PATH=str(TOOLCHAIN / 'lib'), LD_PRELOAD=str(DRIVER))
                    overall = 0
                    for suite in SUITES:
                        command = [run_dir / suite, library, SYSROOT, snapshot / 'native/fixtures']
                        if suite == 'fs_abi_test':
                            command += ['-', capstones]
                        result = phase(suite, command, environment)
                        if result and overall in (0, 4):
                            overall = result
                    state['exitCode'] = overall
            state['sourceAfter'] = source_map(source_paths())
            state['snapshotAfter'] = {name: digest(snapshot / name) for name in state['snapshotBefore']}
            state['exportedSourcesAfter'] = {path.name: digest(path) for path in sorted(capstones.iterdir())}
            state['sourceDrift'] = (state['sourceBefore'] != state['sourceAfter']
                                    or state['snapshotBefore'] != state['snapshotAfter']
                                    or state['exportedSourcesBefore'] != state['exportedSourcesAfter'])
            if state['sourceDrift']:
                state['exitCode'] = 2
            state['status'] = 'passed' if state['exitCode'] == 0 else 'failed'
    except Exception as error:
        state.update(status='failed', exitCode=2, error=repr(error))
        if paths:
            try:
                state['sourceAfter'] = source_map(source_paths())
                state['sourceDrift'] = state['sourceBefore'] != state['sourceAfter']
            except Exception as snapshot_error:
                state['sourceError'] = repr(snapshot_error)
    state['workFinishedAt'] = utc()
    state['workComplete'] = True
    write_json(result_path, state)
    while not (run_dir / 'finish-anchor').exists():
        time.sleep(0.05)
    return 0


def cleanup_group(child, identity, run_dir, run_id, deadline, work_complete):
    """Attempt owned cleanup even if /proc or report/marker IO is failing."""
    evidence = {'groupEmpty': False, 'ownedProcessesRemaining': [], 'cleanupErrors': []}
    if child is None:
        evidence['groupEmpty'] = True
        return evidence
    term_sent = False
    term_deadline = min(deadline - 2, time.monotonic() + 3)
    finish_requested = False

    def failed(action, error):
        message = action + ': ' + repr(error)
        if message not in evidence['cleanupErrors']:
            evidence['cleanupErrors'].append(message)

    def signal_group(number, members):
        try:
            if owns_group(identity, members or [], run_id):
                os.killpg(identity['pgid'], number)
                evidence['termAt' if number == signal.SIGTERM else 'killAt'] = utc()
                return True
            failed('group signal refused', RuntimeError('owned group identity not confirmed'))
        except ProcessLookupError:
            return False
        except Exception as error:
            failed('group signal', error)
        return False

    while True:
        now = time.monotonic()
        try:
            child.poll()
            if child.returncode is not None:
                while True:
                    try:
                        reaped, _status = os.waitpid(-1, os.WNOHANG)
                    except ChildProcessError:
                        break
                    if reaped == 0:
                        break
        except Exception as error:
            failed('poll/reap', error)
        if identity is None:
            try:
                candidate = proc(child.pid)
                if candidate and candidate['pid'] == candidate['pgid'] == candidate['sid']:
                    identity = candidate
                    evidence['recoveredGroup'] = identity
            except Exception as error:
                failed('recover group identity', error)
        members = None
        adopted = None
        try:
            inventory = processes()
            members = [item for item in inventory if identity and item['pgid'] == identity['pgid']]
            adopted = [item for item in inventory if item['ppid'] == os.getpid()]
            evidence['ownedProcessesRemaining'] = list({item['pid']: item for item in members + adopted}.values())
            # An identity recovery failure cannot certify a previously launched
            # group empty, even when its leader has already disappeared.
            if identity is not None and not evidence['ownedProcessesRemaining'] and child.returncode is not None:
                evidence['groupEmpty'] = True
                break
        except Exception as error:
            failed('scan complete Linux process inventory', error)
        if now >= deadline:
            break
        if identity is not None:
            only_anchor = members is not None and all(item['pid'] == child.pid for item in members)
            if only_anchor and child.returncode is None and not finish_requested:
                try:
                    (run_dir / 'finish-anchor').touch()
                    finish_requested = True
                except Exception as error:
                    failed('request anchor exit', error)
            elif members and work_complete and not only_anchor:
                evidence['unexpectedResidual'] = True
            if not only_anchor and not term_sent:
                term_sent = signal_group(signal.SIGTERM, members)
            # A broken finish marker must also remain bounded. Keep TERM's
            # caught-signal anchor alive until KILL can reach its whole group.
            if now >= term_deadline and not finish_requested and not term_sent:
                term_sent = signal_group(signal.SIGTERM, members)
            if now >= deadline - 2:
                signal_group(signal.SIGKILL, members)
        time.sleep(0.05)
    evidence['anchorExitCode'] = child.returncode
    if not evidence['groupEmpty'] and not evidence['ownedProcessesRemaining']:
        evidence['ownershipUnconfirmed'] = True
    return evidence


def supervise(options):
    started = time.monotonic()
    run_id = options.run_id or datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex
    run_dir = options.run_dir or ROOT / 'build/offline-ide-audit/native-runs' / run_id
    run_dir = run_dir.resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    report_path = run_dir / 'run.json'
    report = {'schemaVersion': 1, 'runId': run_id, 'runDir': str(run_dir), 'status': 'starting', 'exitCode': 2,
              'supervisorPid': os.getpid(), 'startedAt': utc(), 'group': None, 'groupEmpty': False,
              'ownedProcessesRemaining': [], 'requestedSuites': list(SUITES), 'timedOut': False,
              'maxSeconds': options.max_seconds, 'cleanupSeconds': options.cleanup_seconds,
              'reportPath': str(report_path)}
    write_json(report_path, report)
    print('NATIVE_REPORT ' + str(report_path), flush=True)
    if sys.platform != 'linux' or not Path('/proc/self/stat').exists():
        report.update(status='unavailable', exitCode=3, groupEmpty=True,
                      unavailable=['Linux /proc endpoint required'], finishedAt=utc())
        write_json(report_path, report)
        return 3
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        report.update(status='unavailable', exitCode=3, groupEmpty=True,
                      unavailable=['cannot establish Linux child subreaper'], finishedAt=utc())
        write_json(report_path, report)
        return 3
    interrupted = []
    for value in (signal.SIGTERM, signal.SIGINT):
        signal.signal(value, lambda number, _frame: interrupted.append(number))
    child = None
    identity = None
    try:
        with (run_dir / 'worker-console.log').open('wb') as console:
            child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--worker', str(run_dir)],
                                     env=dict(os.environ, QFLI_NATIVE_RUN_ID=run_id),
                                     stdout=console, stderr=subprocess.STDOUT, start_new_session=True)
            candidate = proc(child.pid)
            if candidate is None or candidate['pid'] != candidate['pgid'] or candidate['pid'] != candidate['sid']:
                raise RuntimeError('new Linux session/group identity was not established')
            identity = candidate
            report.update(status='running', group=identity)
            write_json(report_path, report)
            deadline = started + options.max_seconds - options.cleanup_seconds
            current = {}
            work_complete = False
            while time.monotonic() < deadline and not interrupted:
                if (run_dir / 'worker.json').exists():
                    current = json.loads((run_dir / 'worker.json').read_text(encoding='utf-8'))
                    if current.get('workComplete'):
                        work_complete = True
                        break
                if child.poll() is not None:
                    break
                time.sleep(0.1)
            report.update(current)
            report['timedOut'] = not work_complete and not interrupted and time.monotonic() >= deadline
            if not work_complete:
                report.update(status='interrupted' if interrupted else 'timed_out' if report['timedOut'] else 'failed',
                              exitCode=130 if interrupted else 124 if report['timedOut'] else 2)
            if interrupted:
                report['signalsReceived'] = interrupted
    except Exception as error:
        report.update(status='failed', exitCode=2, error=repr(error))
    finally:
        cleanup_deadline = min(started + options.max_seconds, time.monotonic() + options.cleanup_seconds)
        try:
            report.update(cleanup_group(child, identity, run_dir, run_id, cleanup_deadline,
                                        report.get('workComplete', False)))
            if report.get('recoveredGroup'):
                report['group'] = report['recoveredGroup']
        except Exception as error:
            # This last guard cannot certify cleanup; the host retains its lane.
            report.update(groupEmpty=False, cleanupError=repr(error))
        if not report['groupEmpty']:
            report.update(status='cleanup_incomplete', exitCode=125)
        elif report.get('unexpectedResidual') or (report['status'] == 'passed' and report.get('anchorExitCode') != 0):
            report.update(status='failed', exitCode=2)
        report['finishedAt'] = utc()
        report['elapsedSeconds'] = round(time.monotonic() - started, 3)
        try:
            write_json(report_path, report)
        except Exception as error:
            report.update(status='report_error', exitCode=126, reportIoError=repr(error))
    print(json.dumps({'reportPath': str(report_path), 'exitCode': report['exitCode'],
                      'group': report['group'], 'groupEmpty': report['groupEmpty'],
                      'status': report['status']}), flush=True)
    return report['exitCode']


def main():
    if len(sys.argv) == 3 and sys.argv[1] == '--worker':
        return worker(Path(sys.argv[2]))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, help='new exclusive Linux directory; report is run.json')
    parser.add_argument('--run-id', help='coordinator run identity')
    parser.add_argument('--max-seconds', type=float, default=80)
    parser.add_argument('--cleanup-seconds', type=float, default=15)
    options = parser.parse_args()
    if not 20 <= options.max_seconds <= 80 or not 10 <= options.cleanup_seconds < options.max_seconds:
        parser.error('require total 20..80 seconds and cleanup >=10 seconds below total')
    if options.run_id and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', options.run_id):
        parser.error('run-id must contain 1..128 letters, digits, underscores, dots or hyphens')
    return supervise(options)


if __name__ == '__main__':
    sys.exit(main())
