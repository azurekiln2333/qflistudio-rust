# Authored source and evidence rescue — 2026-11-27

## Scope and safety

Worker A created only this report and `research/preserved-source/**` during the
rescue. The separately requested Chinese guide correction is described below.
Original files, raw logs and all 14 original Git objects remain unchanged.
No move, deletion, Git write, hook execution, build, test, dependency restore,
formatter, analyzer, installer or local validation ran. No junction/reparse
point was traversed. The model remained `gpt-6.1-sol`.

The rescue started with local HEAD `c999df6e75ce0626fe22db04a481a12035629ca0`.
The coordinator subsequently committed preservation work; this worker did not
alter that commit or its staged paths. Deduplication uses stage-0 index blob
contents captured during rescue, not a claim that every staged file was already
published. Index paths and their original blob IDs are recorded in the manifest.

## Exact mapping and hash ledger

`preserved-source/manifest.json` is the complete per-file ledger, containing
636 source/object/log dispositions. Its raw SHA-256 is:

`9521f09701b5aebc749b6329b8ba1ccd311057d9a9c18310a9ca2f77cf872e84`

For every copied entry it records the exact original `source`, relative
`destination`, raw byte length and raw `sha256`. Destination paths are relative
to `research/preserved-source/`. Duplicate entries instead record the exact
tracked path/blob or already-rescued destination. `lfNormalizedSha256` normalizes
CRLF only and is not the raw-byte hash. No current product code was replaced.

| Original namespace | Portable destination rule | Exact copies | Bytes |
| --- | --- | ---: | ---: |
| `build/content-author-scratch/<file>` | `preserved-source/content-author-scratch/<same file>` | 26 | 365419 |
| `build/offline-ide-audit/<helper>` | `preserved-source/offline-ide-audit/<same helper>` | 29 | 289514 |
| `build/offline-ide-audit/fs-patch-{base,source,check}/<path>` | Same suffix under `preserved-source/offline-ide-audit/`; duplicate bytes referenced once | 35 | 1122900 |
| `native/build/.patchwork/{a,b}/<changed path>` | `preserved-source/native-patchwork/{a,b}/<same path>`; one duplicate references the rescued fs base | 11 | 443183 |
| Seven selected small offline-IDE evidence records | Same filename under `preserved-source/offline-ide-audit/` | 7 | 20781 |
| Eleven unique unreachable blobs | `preserved-source/unreachable-blobs/<original Git OID>/<descriptive filename>` | 11 | 88067 |
| **Total exact copies** | **Each exact mapping/hash is in the manifest** | **119** | **2329864** |

Additional authored rescue artifacts are the README, sanitized log summary and
three historical deltas. These are new explanatory/difference records, not
byte-identical copies of one original file.

| Artifact below `preserved-source/` | Bytes | SHA-256 |
| --- | ---: | --- |
| `README.md` | 2285 | `fb4fc232f1a92c0df71682107c318b05133cddadc6ebc1319e1acadffe1d5e8f` |
| `historical-log-summary.md` | 6589 | `1720161dfb59896acf6fedccfe520089b17f469e9a36f6012867a677e8bcf2bf` |
| `native-patchwork/historical-a-to-b.patch` | 26651 | `0549fe1ef7be769c0e5aee13c7bb2d4482d8f5e098b665b488e0149b44a3bc50` |
| `offline-ide-audit/historical-fs-base-to-source.patch` | 57212 | `aa74259005620e0256c7f1b452f4df4e3eef1ea1583f5c598810323a10d027c1` |
| `offline-ide-audit/historical-fs-base-to-check.patch` | 54148 | `bd6b226a0a01dab4150014786aeb7a07bc4c6c98d01d9cff7f599ec4013602b4` |

## Review and selection decisions

The three authorized original roots contained 589 regular files: 52 in
`content-author-scratch`, 263 in `offline-ide-audit`, and 274 in native patchwork.
Bounded traversal found no reparse points. The remaining 47 manifest entries are
the 14 Git blobs and 33 ignored research logs.

- **26 curriculum sources:** preserve 23 Python authoring/check/repair helpers
  and three old Rust variants. Six other Rust snippets already match exact
  LF-normalized code/answer fields in the tracked lesson catalog, so the ledger
  points to their topic IDs and fields rather than duplicating them.
- **29 offline helpers:** preserve authored Python/PowerShell/shell/ArkTS source
  and the small compiler-guide patch. Their original behavior is historical:
  some contain old local SDK/device commands or multi-remote publication code.
  The README prohibits execution/import. They are not installed as active tools.
- **Filesystem patch snapshots:** preserve the 12-file base and the two 13-file
  edited snapshots, deduplicating three identical edited files. The small
  historical deltas retain the differences without modifying today's product
  patch or claiming these earlier experiments are correct or buildable.
- **Native patchwork:** only six of the 137 paired paths differ: `src/eval.rs`,
  `src/helpers.rs`, `src/lib.rs`, `src/machine.rs`, `src/shims/os_str.rs`, and
  `src/shims/unix/fs.rs`. Preserve both endpoints for these changes plus the
  historical delta. One endpoint is identical to the rescued filesystem base
  and is referenced there. Do not copy the 262 unchanged upstream pair files.
- **Seven small evidence records:** preserve Android source/APK inspection,
  prose-change results, compiler closure, readiness and SDK `openat` symbol
  observations. These records retain their historical scope and identifiers;
  none is new execution evidence or a current production-pin decision.

The ledger dispositions total: 119 exact copies, 5 exact index duplicates,
4 duplicate rescue contents, 10 catalog-field duplicates, 262 unchanged
patchwork pair files, 39 generated outputs not copied, 164 generated/transient
reports not copied, and 33 logs represented by a sanitized knowledge summary.

Generated executables, rlibs/rmeta, Python caches and binary temporary files
were not copied. Large generated catalog/prose report snapshots, old grants,
process observations and diagnostic exports were not bulk copied. Their
original paths, dispositions and text-report hashes remain in the ledger where
recorded; originals remain present. This is not authorization to delete an
original just because its disposition says `not-copied`.

## All fourteen unreachable blobs

Names below are descriptive labels inferred from content, not proof of an
original pathname, author or chronology. Exact Git object bytes were read through
`cat-file` without writing objects. Three objects already match exact index
content; the other eleven were copied byte-for-byte under their OID directory.
The manifest contains all raw SHA-256 hashes and destination filenames.

| Original Git blob | Disposition / mapping |
| --- | --- |
| `c061fbc2df1ccfe063b18d27e46dcd36730c2ef5` | Exact index duplicate: `.trellis/tasks/11-17-app-installers/implement.jsonl` |
| `ad74351a9e94d774540ea9d989e025d82f7985a1` | `<OID>/EntryAbility-historical.ets` |
| `f7d410bb4372572fcefad1eab8e0e7a8965cf91c` | Exact index duplicate: `.trellis/tasks/11-17-app-installers/design.md` |
| `0536e7023be601e942704411ad6d5a3532a391e3` | `<OID>/installer-prd-historical.md` |
| `85773ae997b66e23833eb39273dd7d0d8e9aa24c` | `<OID>/Cargo-historical.toml` |
| `fd17e8e4886f8b90da8eb99251f79598adda506e` | `<OID>/compiler-boundary-historical.patch` |
| `8f38ee01d0f77d910a1d3422b2008aacbf6aade5` | `<OID>/miri-build-support-historical.py` |
| `a628adeb2b237c0221f6542e452069ee8d668f5b` | `<OID>/compiler-build-provenance-historical.md` |
| `9419652c85cf38acfb7ffa2789776772823a4f22` | `<OID>/ci-support-historical.py` |
| `9f0939861c79333ca58d4022d5dbf14694d414c2` | `<OID>/terminal-prd-historical.md` |
| `bb697a15db8c53c619e4b664934f6e8c4619baab` | `<OID>/installer-task-historical.json` |
| `26eadb67a213e026f04d79bac473085c4de386aa` | Exact index duplicate: `.trellis/tasks/11-17-app-installers/check.jsonl` |
| `56aa20a8e3cf74a67289914bd77b7ec4af5fe454` | `<OID>/installer-implementation-historical.md` |
| `a88e238f9af960b6fce10e06539669634d5911dc` | `<OID>/platform-builds-historical.md` |

The prefix for every `<OID>/...` mapping is
`preserved-source/unreachable-blobs/`. The former content-shape guess of
`85773ae...` as JSON-like was refined to a Cargo/TOML manifest during review;
it was not treated as JSON or executed.

## Thirty-three ignored research logs

Every raw log was read in memory for diagnostic/secret-presence review, hashed,
and left in place. No raw log was copied. The portable summary is
`preserved-source/historical-log-summary.md`; its per-log table separates
prebuild, build, package, test, transfer, process, signing and installation
observations. It references existing tracked release reports instead of
repeating large output.

Useful retained knowledge includes the dev-only Android registrant failure,
the cancellation expected-130/actual-null regression followed by a later
seven-case result, the distinction between six- and seven-case runs, the
OHOS signing configuration failure, the missing strip task, and the actual
unsigned-install rejection `9568320` / `no signature file`. Small excerpts
exclude machine paths, device IDs and credentials. Historical success lines
are not upgraded to current GitHub or device acceptance.

## Secret review and unresolved boundaries

A limited in-memory presence scan checked selected candidates and all 33 logs
for private-key headers, selected provider-token formats, credential-bearing
HTTP URLs and literal sensitive assignments/JSON fields. It found no selected
rule hit in copied candidates or these logs. Values were never printed. This
is not a complete secret/history audit or a guarantee that arbitrary content
is public-safe. Final outgoing-file review belongs to the coordinator.

Remaining uncertainties and gates:

1. Snapshot/blob provenance and obsolete helper behavior remain historical and
   unverified. Do not import or run rescued scripts, apply historical patches,
   or treat old task statuses as authoritative current progress.
2. The 164 non-copied generated/transient records and 39 generated outputs remain
   original. Their exclusion is not a cleanup decision. Further unique-knowledge
   requests need per-file review before any deletion.
3. Unchanged upstream patchwork trees are not replicated; only authored deltas
   and changed endpoints were rescued. Keep originals until upstream provenance
   and receiving-clone preservation gates are satisfied.
4. No syntax, test, build, lint or patch-application pass is claimed. Any required
   executable checks must run on GitHub-hosted runners, including checking how
   cloud source inventories exclude historical research scripts from test entry
   points while still preserving their bytes.
5. Receiver diagnostics remain exactly `Hook failed` / `hook exited with code 1`.
   No hook identity or traceback was supplied. No root cause or hook repair is
   inferred, and no hook was run locally.
6. Credential rotation/history actions remain with the credential owner. No
   force rewrite, pruning, repack, object deletion or credential publication ran.

## Separately requested hosted-lint correction

The coordinator relayed cloud run `45890223129` at app commit `c859677`:
source-policy selftest passed and the guide had exactly three hard
synonym-rotation findings with baseline zero. Worker A corrected only
`docs/native-github-build.zh-CN.md`: use the running term consistently, use the
deletion term consistently, and call the shared WSL resource space rather than
rotating save/storage terms. No rule suppression or baseline increase was added.
Technical requirements and modality were preserved. The document was read back;
no local lint or validation ran. A new hosted run must confirm the correction.

## Raw-byte Git correction — 2026-11-27

The coordinator reported that commit
`a07511394cfc8a8079e226e37468c571b9d0ed1e` contains normalized Git blobs for
43 of the 119 rescued copies. Those Git blob bytes differ from the manifest's
raw SHA-256 values because CRLF normalization occurred during staging. The
earlier exact-copy claims describe the rescue worktree bytes, not a successful
raw-byte publication contract for that initial commit. Retain `a075113` as the
historical normalized representation; do not amend or rewrite its history.

A read-only worktree inventory on 2026-11-27 at 05:06 +08:00 found all 119
manifest-listed copied files present, with zero raw byte-length/hash differences.
The raw manifest remains unchanged at SHA-256
`9521f09701b5aebc749b6329b8ba1ccd311057d9a9c18310a9ca2f77cf872e84`.
Original source files and original Git objects were not modified.

The corrective contract is the new directory-local file
`.trellis/tasks/11-26-github-workspace-migration/research/preserved-source/.gitattributes`.
Its rule is `* -text`. It disables Git text normalization only for this
historical rescue tree, including descendants, archived patches/evidence and
the raw-hash manifest. No root or sibling attribute rule was changed. Existing
line endings in these archived files are evidence, not a formatting defect.

The coordinator must restage the existing exact worktree copies with this
attribute contract active, compare every resulting index blob with its recorded
raw SHA-256/length, and publish a corrective follow-up commit. Adding the
attribute file alone does not repair blobs already in the index or in history.
The corrected index, follow-up commit and receiving-clone byte identity remain
pending until the coordinator reports that evidence. Worker A performed no
staging, commit, checkout, renormalization, hook execution or local check.

The coordinator also reported that all four cloud-check jobs passed at
`a075113`. That hosted result is retained as reported evidence for its checked
scope; it does not prove raw-byte rescue identity or validate a not-yet-created
corrective commit. No new hosted result or local execution is claimed here.
