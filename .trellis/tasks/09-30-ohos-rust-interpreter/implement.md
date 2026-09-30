# Implementation Plan

- [ ] Pin the Rust and DevEco toolchain paths and create a reproducible OHOS
      native probe build with explicit output and ABI checks.
- [ ] Package the probe in the app and invoke it from a device-installed HAP;
      capture the device architecture, installation, call result and logs.
- [ ] Pin compatible upstream rustc/Miri revisions and test an OHOS host build
      of their required crates; save exact commands and errors.
- [ ] Integrate the viable upstream source-to-MIR-to-execution path through a
      native session boundary, including I/O, diagnostics and cancellation.
- [ ] Exercise valid, invalid, stdin, nonzero-exit and cancellation fixtures on
      device; compare with desktop reference behavior.
- [ ] Run relevant Flutter analysis/tests and a HAP build; review capability
      claims and commit each validated batch with a conventional message.

## Review Gates

- A cross-compiled `.so` alone does not pass the HAP loader gate.
- A probe call does not pass the interpreter gate or enable the runtime UI.
- An OHOS target build does not pass the rustc/Miri OHOS host gate.

## Risky Files

`ohos/entry/src/main/ets/entryability/EntryAbility.ets` contains unrelated
uncommitted user work. Native verification should avoid changing it. Any later
integration touching it must preserve and review that diff explicitly.
