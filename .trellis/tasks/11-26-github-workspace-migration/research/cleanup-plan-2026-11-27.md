# Cleanup and ownership plan — qflistudio-rust — 2026-11-27

This plan records an inventory and preservation decision only. It does not
delete, move or unregister anything in the source workspace, target workspace
or WSL. The approved external backup relocation is copy-only in this pass.

## Preserved external backup

The selected scope contains 589 source entries from `build/content-author-scratch`,
`build/offline-ide-audit` and `native/build/.patchwork`. The external backup at
`D:/MyNewProjects/_migration-backup/qflistudio-rust-20261127/` contains 436
copied files totaling 11,575,677 bytes. All copied files match their recorded
source size and SHA-256. The manifest records 153 skipped entries: 138
generated or binary-extension entries and 15 secret-shape classifications.
Those classifications do not prove credentials. Three classified files also
exist in the published rescue ledger (`_b2.py`, `_d2.py` and
`send-production-hap.py`), and `EntryAbility-online-baseline.ets` was skipped
by the extension rule while preserved in the ledger. The backup is selected
scope only, not a complete private or generated-file backup. The copy is not a
Git source tree and is never executed. Originals remain in place.

## Candidate generated or private paths

The following paths are local-only candidates after source/target parity, provenance review, and owner approval:

- root `build/` outputs and caches
- `.dart_tool/`, Flutter ephemeral directories and plugin symlink trees
- Android and OHOS Gradle/Hvigor/node module outputs, local properties and generated registrants
- `native/build/` generated runtime and patchwork outputs
- `assets/miri/*.bin` and generated native manifests
- ignored Flutter logs and historical raw build/device logs
- editor/session state such as `.claude/`, `.cursor/`, `.pi/`, `.zcode/`, `.trellis/.runtime/` and `.trellis/.developer`

These candidates stay untouched because cleanup is inventory-only and the
original object store must remain available until receiving-clone comparison,
ownership review and credential review finish. Reparse points under generated
OHOS/Flutter trees were not followed or copied. Any later relocation must be
separately approved, path-contained and copy-verified before an owner decides
what may be removed.

## WSL inventory

The read-only WSL inventory found these distributions, all stopped at version 2:
`Ubuntu`, `qfli-terminal-test`, `qfli-terminal-al3-clean`,
`qfli-terminal-al3-test` and `qfli-java-build`. No distribution was started,
stopped, unregistered or modified.

## Safe future sequence

1. Confirm GitHub main, source and target tree/blob parity.
2. Confirm the destination Codex has acknowledged the handover.
3. Confirm owners approve any separately proposed relocation or removal.
4. If relocation is approved, copy to a path-contained external backup and
   verify hashes before changing source state.
5. Re-run read-only status and ownership inventories. No deletion is authorized
   by this plan.

No cleanup is authorized by this document.
