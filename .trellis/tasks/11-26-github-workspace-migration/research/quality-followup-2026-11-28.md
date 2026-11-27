# Quality follow-up — 2026-11-28

Historical snapshot from the deferred follow-up before the first core wave.
The later `core-wave-quality-2026-11-28.md` records the expanded terminal repair
and manual workspace-test reflow. The frozen-file wording below describes
this earlier handoff, not the subsequent source state.

## Assigned test fixture

`test/rust_terminal_commands_test.dart` used `compilerPath!` in the bundled
GNU linker tests. The helper returns an empty list on non-Windows hosts, while
the test fixture only discovers `native/build/miri-windows/compiler/bin` and
therefore returns null on the Linux application-quality runner. The test now
asserts the documented empty result on non-Windows, keeps the six flag
assertions for Windows, and uses the host environment for the Cargo config
presence check when no Windows override exists.

No real invocation, exit-status or output assertion was removed. No timeout or
skip was added.

## Unresolved hosted quality findings

The quality run at source `dde374cdcdbca4ee0f093b5b62261a65da32d125`
reported `cargo 1.100.0` where the test expected `cargo 1.98.1`. The current
quality workflow does not install or prepend the pinned native compiler. The
application contract says desktop packages use system `cargo` and `rustc`,
while the 1.98.1 pin belongs to native compiler provenance. The Cargo test now
requires exact 1.98.1 output when the bundled Windows compiler is selected and
requires a semantic Cargo version from the real system tool on other hosts.
The process claim, zero exit status and output checks remain intact.

The formatter report named `test/rust_code_analyzer_test.dart` and
`test/rust_workspace_integration_test.dart`. Their exact hosted formatter
output is unavailable locally, and this workspace forbids running the formatter.
Those files remain frozen pending hosted diff evidence.

## Validation boundary

No local formatter, analyzer, Flutter test, build, dependency restore or
artifact download was run. Hosted rerun remains required.
