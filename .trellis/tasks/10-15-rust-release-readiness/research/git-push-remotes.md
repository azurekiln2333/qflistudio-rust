# Rust Git push destinations

Verified on 2026-10-16 in `D:/MyNewProjects/qfli_rust`, branch `main`.
Both the current directory and `git rev-parse --show-toplevel` identify this
repository. No sibling repository or global Git configuration was changed.

The repository-local `origin` fetch URL is:

```text
https://github.com/azurekiln2333/qflistudio-rust.git
```

The repository-local `origin` push URLs are configured in this exact order:

```text
https://github.com/azurekiln2333/qflistudio-rust.git
https://gitee.com/azurekiln/qflistudio-rust.git
https://gitlab.com/azurekiln-team/qflistudio-rust.git
https://gitcode.com/azurekiln/qflistudio-rust.git
https://cnb.cool/azurekiln/qflistudio-rust
```

`git push origin main` now targets all five destinations. Configuration does not
change branch upstreams, `push.default`, credentials or force/mirror behavior.
Remote configuration lives in the local Git config and is not part of a commit;
this note records the requested setup for review.

Read-only validation completed successfully:

```powershell
git rev-parse --show-toplevel
git remote get-url origin
git remote get-url --push --all origin
git config --local --show-scope --get-regexp '^remote\.origin\.'
git remote -v
```

The effective fetch URL and all five effective push URLs match the requested
strings and order; every `remote.origin` entry has `local` scope. No actual push,
authentication or remote-access verification was performed.
