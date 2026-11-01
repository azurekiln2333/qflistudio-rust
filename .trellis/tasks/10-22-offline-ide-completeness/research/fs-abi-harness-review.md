# Project filesystem ABI regression harness

Owned additions are `native/miri_adapter/fs_abi_test.c` and
`native/fixtures/fs_session_{first,second}.rs`. They use the actual dynamically
loaded adapter; no runtime stub is linked. This is a host regression harness,
not packaged OHOS execution evidence.

## Run on the pinned Linux reference build

From the repository root, build the C harness with the host C compiler:

```sh
cc -std=c11 -Wall -Wextra -Werror native/miri_adapter/fs_abi_test.c \
  -ldl -o /tmp/qfli-fs-abi-test
/tmp/qfli-fs-abi-test /absolute/libqfli_miri.so /absolute/MIR-sysroot \
  "$PWD/native/fixtures" /absolute/backend.so \
  "$PWD/build/offline-ide-audit/fs-abi-catalog"
```

Use `-` for the backend to select the adapter's existing default. Omit the last
argument to get explicit `NOT_RUN` for authored 164/165. Keep the existing
`abi_test.c` suite as a separate mandatory stream/limit/cancel regression; the
filesystem suite does not replace it.

| Exit | Meaning |
| --- | --- |
| 0 | Runtime checks and both compiler boundary probes passed |
| 1 | Runtime/invariant failure, including a blocking run without final result |
| 2 | Setup/usage failure |
| 3 | Additive create symbol absent; NOT_RUN |
| 4 | Runtime checks passed; compiler include/env boundary remains open |

Never convert exit 4 into a full sandbox pass. The runtime capability alone does
not restrict rustc's `include_str!`/`include_bytes!`/module loading or compile-time
host environment. The probes seed an actual outside file and host-only secret.
They require compile rejection before MIR blocks, no secret disclosure and a
relevant rejection diagnostic. Missing-file errors and the word `outside` in
the filename cannot satisfy the include boundary. Captured compiler output is
redacted in the harness report.

## Export exact authored 164/165 programs

Run this Python code from the repository root (the shell heredoc is for Linux).
It verifies the inventory against authored sources before exporting, validates
source and attached-file SHA-256, and writes exact UTF-8 bytes:

```sh
python3 scripts/generate_rust_native_catalog.py --check
python3 - <<'PY'
from pathlib import Path
import hashlib
import json

catalog = json.loads(Path('assets/content_rust/native_catalog.json').read_text(encoding='utf-8'))
for name, expected in catalog['catalog']['sourceSha256'].items():
    assert hashlib.sha256((Path('tool/rust_content') / name).read_bytes()).hexdigest() == expected, name
selected = [case for case in catalog['cases'] if case['topicId'] in (164, 165)]
expected_ids = {f'rust-catalog-{topic:03d}-{kind}' for topic in (164, 165) for kind in ('example', 'answer')}
assert len(selected) == 4 and {case['id'] for case in selected} == expected_ids
destination = Path('build/offline-ide-audit/fs-abi-catalog')
destination.mkdir(parents=True, exist_ok=True)
for case in selected:
    source = case['source'].encode('utf-8')
    assert hashlib.sha256(source).hexdigest() == case['sourceSha256'], case['id']
    assert case['expectedExitCode'] == 0, case['id']
    files = case['files'] or {}
    assert set(files) == set(case['filesSha256'] or {}), case['id']
    for name, content in files.items():
        assert hashlib.sha256(content.encode('utf-8')).hexdigest() == case['filesSha256'][name], (case['id'], name)
    if files:
        assert files[case['entryFile']] == case['source'], case['id']
    (destination / (case['id'] + '.rs')).write_bytes(source)
    assert (case['kind'] == 'example') == case['stdoutAsserted'], case['id']
    if case['stdoutAsserted']:
        (destination / (case['id'] + '.stdout')).write_bytes(case['expectedStdout'].encode('utf-8'))
    else:
        assert case['expectedStdout'] is None, case['id']
    print(case['id'], len(source), case['sourceSha256'], 'stdout=' + str(case['stdoutAsserted']))
PY
```

This optional subset executes the unchanged main source of each selected
example and answer. Examples assert exact output bytes. Authored answers have
no stdout expectation and retain an explicit exit-status-only contract. This
does not execute Cargo tests or attached libraries, does not cover all 332
programs and does not replace the hash-bound native catalog/device verifier.

## Coverage and review

- Real disk roundtrip; outside path/symlink denial with unchanged real sentinels;
  ordinary project files preserved; no outside file/directory creation.
- Private mode 0700 session temporaries, exact cwd/temp output, two simultaneously
  alive sessions, destruction of only the owning temporary, subsequent fresh run.
- Host cwd and seeded host environment unchanged after operations; all ABI path
  inputs destroyed immediately after create to check the adapter's copies.
- Network fixture must stop at the actual socket isolation operation. A second
  probe targets a real ephemeral loopback listener and verifies no connection
  reached it; an arbitrary nonzero guest exit cannot pass this check.
- Invalid roots, root `/`, out-of-root source and in-root symlink to outside
  source rejected by the additive constructor.
- Compiler boundary leakage detection scans complete byte buffers, including
  bytes after embedded NUL. Authored stdout compares complete buffer lengths.
- Rejected runs or missing/nonfinal blocking results abort with exit 1 before any
  session destruction, preventing unsafe cleanup if the ABI contract is broken.

## Verification in this worker

SDK 23 Clang C11 syntax/warning/type checks passed with `-Wall -Wextra -Werror
-fsyntax-only` for both `x86_64-linux-ohos` and `aarch64-linux-ohos`, using
`D:/ProgramFiles/Huawei/OpenHarmony/Sdk/23/native/sysroot`.
`python scripts/generate_rust_native_catalog.py --check` passed for 166 topics,
332 programs and 23 bundles. The documented export code ran successfully and
the four hash-validated programs plus example stdout files are prepared under
`build/offline-ide-audit/fs-abi-catalog/`. No Linux adapter execution, OHOS execution, Flutter
analysis/tests or heavy compiler build was run by this worker. Parent owns those
serialized verification windows and the separate compiler-loader boundary.
