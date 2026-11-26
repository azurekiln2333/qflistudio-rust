# Implementation

- [x] Write `tool/ci/ci_support.py`: constants, target table, runner, annotations.
- [ ] Add `android-armv7` to the native runtime helpers and their tests.
- [ ] Add `ACTION_PINS` (node24 only) and `tool/ci/test_action_pins.py`.
- [ ] Write `tool/ci/app_build.py` with the stages of `design.md` and `tool/ci/test_app_build.py`.
- [ ] Write `tool/ci/package_installer.py`, `tool/ci/windows_installer.iss` and `tool/ci/test_package_installer.py`.
- [ ] Write `.github/workflows/app-installers.yml` with pinned actions.
- [ ] Write `docs/app-installers.zh-CN.md`. Add pointers in `README.md` and `docs/native-github-build.zh-CN.md`.
- [ ] Run the helper unit tests, the YAML parse check and the controlled Chinese lint.
- [ ] Review the change through a Trellis check agent.
- [ ] Commit with a Conventional Commits message and no AI attribution. Inspect the outgoing range for attribution lines.
- [ ] Push `main` to the GitHub URL only.
- [ ] Observe the real Actions run. Fix reproducible failures on `main` and re-run.
- [ ] Record the run URL and the result of each of the seven jobs, the `android-armv7` native job and the absence of Node.js 20 annotations.
- [ ] Update the local Trellis spec for installer builds.

## Validation

```text
python -m unittest discover -s tool/ci -p "test_*.py" -v
python -c "import sys, yaml; yaml.safe_load(open(sys.argv[1], encoding='utf-8'))" .github/workflows/app-installers.yml
python scripts/ste-lint-zh.py docs/app-installers.zh-CN.md
git log --format="%an <%ae> | %cn <%ce>%n%B" origin/main..HEAD
```

The unit tests need no network and no Flutter SDK. The application builds and
the installers run only on GitHub runners. No local Flutter build is required.

## Review gates

- Sub-agents never commit. The main session reviews their files before the commit.
- The attribution check runs before every push.
- A job result is reported only from the Actions API of the real run.

## Rollback points

- Before the push: discard the working tree changes.
- After the push: revert the commit on `main`. No other file depends on the helpers.
