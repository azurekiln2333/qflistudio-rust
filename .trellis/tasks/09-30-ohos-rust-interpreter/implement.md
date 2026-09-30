# Implementation Plan

- [x] Pin the Rust and DevEco toolchain paths and create a reproducible OHOS
      native probe build with explicit output and ABI checks.
- [x] Package the probe in the app and invoke it from a device-installed HAP;
      capture the device architecture, installation, call result and logs.
- [ ] Pin compatible upstream rustc/Miri revisions and test an OHOS host build
      of their required crates; save exact commands and errors.
      AArch64 Miri core-library compilation now passes with Linux host
      compiler components; shared-library embedding and x64 private compiler
      components remain pending.
      The upstream Linux CLI and MIR standard library now pass five source
      fixtures (modules/generics, stdin, exit 7, E0502 and E0308); this is
      reference behavior, not the HAP acceptance gate.
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
- The current debug signing profile is bound to `com.azurekiln.qfli.forge`, while
  this app declares `com.azurekiln.qfli.rustcore`; signing fails with Hvigor
  00303074. The x86_64 simulator at `127.0.0.1:5555` accepts the unsigned debug
  HAP and passed the loader/call gate. A matching profile is still needed for
  physical-device signing.

## Risky Files

`ohos/entry/src/main/ets/entryability/EntryAbility.ets` contains unrelated
uncommitted user work. Native verification should avoid changing it. Any later
integration touching it must preserve and review that diff explicitly.
