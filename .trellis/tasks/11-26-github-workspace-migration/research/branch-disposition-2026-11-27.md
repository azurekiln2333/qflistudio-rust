# Branch disposition — qflistudio-rust — 2026-11-27

The source checkout is on `main` at `f226cf90b51e99c082db025336a17a963e544fd4`. GitHub `main` advertises the same commit.

| advertised source | tip | ancestry | disposition |
|---|---|---|---|
| GitHub `main` | `f226cf90b51e99c082db025336a17a963e544fd4` | source HEAD and live GitHub tip agree | retain as authoritative main; publish only through the orchestra push gate |
| Gitee `feat/rust-offline-ide-20261022` | `b8a69a8df4f9fe81641aa8916b8a10884863813b` | tip is an ancestor of source main | already integrated; preserve as historical mirror evidence; do not push or delete |
| GitCode `feat/rust-offline-ide-20261022` | `b8a69a8df4f9fe81641aa8916b8a10884863813b` | tip is an ancestor of source main | same historical tip as Gitee; preserve as mirror evidence; do not push or delete |
| CNB `feat/rust-offline-ide-20261022` | `b8a69a8df4f9fe81641aa8916b8a10884863813b` | tip is an ancestor of source main | same historical tip as Gitee/GitCode; preserve as mirror evidence; do not push or delete |
| GitLab `feat/rust-offline-ide-20261022` | `553e13928bb4c9af3d1cccf615053c81bca91af5` | tip is an ancestor of source main | already integrated; preserve as historical mirror evidence; do not push or delete |

The source repository's local `origin` retains non-GitHub push URLs for compatibility with the pre-migration checkout. The migration directive forbids publishing to them. The target checkout is already GitHub-only. No remote branch is deleted because ancestry and ownership evidence do not authorize destructive cleanup.

No local branch other than `main` is present. The two mirror tips were verified as ancestors of `main`; no merge is needed and no history is rewritten.
