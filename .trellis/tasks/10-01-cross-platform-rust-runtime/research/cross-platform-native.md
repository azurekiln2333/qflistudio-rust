# Research: Cross-platform embedded rustc/Miri builds and packaging

- Query: Determine concrete native compiler/interpreter build and packaging routes for Android, iOS, macOS and Web, including compiler-private dependencies and a read-only codegen-backend path.
- Scope: mixed; read-only workspace/toolchain inspection and pinned upstream source/documentation.
- Date: 2026-10-01
- Ownership: this research file only. No code, specification, platform configuration or Git state was changed by the researcher.

## Findings

### Current implementation and missing pieces

The C ABI implementation is shared Rust code, not an OHOS-only parser. It uses upstream rustc for analysis and upstream Miri for interpretation. The exposed C calling convention does not make an OHOS binary usable on Android or Apple platforms.

| Platform | Existing execution implementation | Native build/package evidence in this checkout | Required next work |
| --- | --- | --- | --- |
| Windows/Linux/macOS desktop | `RustProgramRunner` executes Cargo/rustc processes | Desktop path exists; no Apple embedded library integration | Preserve desktop compilation; optionally package the same Miri ABI as a separately selected interpreter |
| OHOS | Miri C ABI, MIR extraction and native ELF packaging | Both native architectures documented as compiled; packaged source execution still unverified | Preserve existing pipeline and pending device acceptance |
| Android | Runner currently rejects this non-desktop platform | No Android host target in adapter build script; no `jniLibs` runtime contents/integration | Build target-host rustc private libraries, adapter and backend, then package their dependency closure |
| iOS | Runner currently rejects this non-desktop platform | No frameworks/static archive, Xcode linkage or target-host compiler build | Source-build compiler host libraries for device/simulator, then embed signed frameworks or implement a full static source build |
| Web | No browser compiler/interpreter | Browser cannot use the current Dart FFI/process/file implementation | A separate WebAssembly/virtual-filesystem design or an explicitly authorized remote runtime is required |

Key workspace patterns:

- `native/miri_adapter/Cargo.toml:9`: output is `cdylib` only; Miri is staged beside it with `default-features = false`, `features = ["stack-cache"]` at line 12.
- `native/miri_adapter/src/lib.rs:1`: compiler-private crates require `#![feature(rustc_private)]` and matching compiler metadata.
- `native/miri_adapter/src/lib.rs:188`: `make_backend()` asks the compiler's default backend for guest target configuration, then uses a `DummyCodegenBackend` for compilation.
- `native/miri_adapter/src/lib.rs:246`: interpretation occurs after rustc analysis and returns `Compilation::Stop`; generated native user code is not executed.
- `native/miri_adapter/src/lib.rs:344`: guest is explicitly `x86_64-unknown-linux-gnu` for every native host.
- `scripts/build_miri_adapter.sh:39`: supported build hosts are Linux x64 and OHOS arm64/x64 only. The default build paths and executable names are Linux-specific.
- `scripts/package_miri_ohos.ps1:92`: native dependencies go to OHOS platform libraries; the optional backend is also copied into extracted sysroot assets at line 117.
- `lib/ohos_miri_runner.dart:359`: loading uses `DynamicLibrary.open(libraryPath)`; ABI symbol registration and worker lifetime already exist.
- `lib/ohos_miri_assets.dart:19`: asset manifest validates schema and guest, but does not select/validate `nativeHost` for multiple platforms/architectures.
- `lib/rust_runner.dart:41`: non-desktop platforms other than its OHOS branch return an unavailable result.

### Authoritative source and toolchain inputs

Pinned compiler: Rust 1.98.1, commit `48a229ceaefd4985c50990b14116b6d856af0985`.

Two locally inspected source roots are useful but incomplete:

1. `D:/AppData/Local/Temp/qfli-miri-ohos-source`: `.git/info/sparse-checkout` selects `src/tools/miri`. Top-level Cargo/bootstrap example files exist, but `compiler/`, `library/` and `src/bootstrap/` are not checked out. Do not run `x.py` and assume this is a complete compiler source tree.
2. `D:/AppData/Local/Temp/qfli-rust-toolchain/rustup/toolchains/stable-x86_64-pc-windows-gnu/lib/rustlib/rustc-src/rust`: compiler source including `rustc_driver`, `rustc_interface` and Cranelift exists. `library/std/Cargo.toml`, `library/backtrace/Cargo.toml`, `library/Cargo.toml`, root `Cargo.toml`, `x.py`, bootstrap and LLVM source are absent. This is compiler browsing material from `rustc-dev`, not a bootstrap checkout.

The installed toolchain's `lib/rustlib/multirust-channel-manifest.toml` records official Rust 1.98.1 components:

- Lines 33731-33736: `rustc-dev` available for `aarch64-apple-darwin`.
- Lines 33938-33943: `rustc-dev` available for `x86_64-apple-darwin`.
- Lines 33956-33961: `rustc-dev` available for `x86_64-pc-windows-gnu`; tar.xz checksum `b9914adb9e2d5769fdd49afee5055247fe7673137932f745f594a2f2b9f6e51d`.
- There are no `rustc-dev` sections for `aarch64-linux-android`, `x86_64-linux-android`, `aarch64-apple-ios` or `x86_64-apple-ios`.

The pinned upstream platform table confirms Android/iOS are Tier 2 without host tools. Installing `rust-std` for those targets is insufficient for embedding rustc. MacOS has official compiler host distributions and can reuse matching `rustc-dev`.

`scripts/check_rustc_x64_ohos.sh:13` already pins the complete Rust source archive checksum to `be1816e7f6c40abb90245ad6e024bed2a7e88d7dda4561e4d5470207df616b9f`. A reusable source-bootstrap script can use that same complete archive and verify its revision/source completeness. Download and extraction were not performed by this research agent.

Cache inspection without Git commands:

- The sparse repository's `.git/config` has `remote.origin.promisor = true` and `partialclonefilter = blob:none`; its three promisor pack files total about 5.47 MB. This is consistent with tree objects and the sparse checkout's requested blobs, not evidence of a complete local Rust source archive.
- This research role forbids Git operations, so no lazy fetch, checkout expansion, `git show` or `git cat-file` was run. An implementer can check required blobs with `GIT_NO_LAZY_FETCH=1 git cat-file -e HEAD:compiler/rustc_driver/Cargo.toml` and equivalent standard-library/bootstrap paths. Check object bodies, not just present tree entries. Full completeness needs a source manifest/archive verification rather than two sample paths.
- The cached Windows GNU `rustc-dev` archive exists at `D:/AppData/Local/Temp/qfli-rust-toolchain/rustup/downloads/b9914adb9e2d5769fdd49afee5055247fe7673137932f745f594a2f2b9f6e51d`, length 144352100 bytes. Its filename matches the pinned manifest checksum; this agent did not extract or independently hash the archive.

### Real reusable source-bootstrap route

The OHOS source-bootstrap script provides the reusable structure: native executable stage0 compiler on build host B, compiler library runtime host H, `local-rebuild = true`, source revision checks, private metadata from that same bootstrap, and matching build-host proc macros. Generalize platform/toolchain selection rather than substituting OHOS libraries for Android/Apple libraries.

Concrete command sequence, once complete source, stage0 and platform linker inputs exist:

```sh
python3 <complete-rust-source>/x.py build --config <platform-bootstrap.toml> \
  --stage 1 --host <H> --target <H> compiler/rustc_driver
python3 <complete-rust-source>/x.py build --config <platform-bootstrap.toml> \
  --stage 1 --host <H> --target <H> compiler
```

On Windows use its executable Python and compiler tools; these commands do not inherently require WSL. Existing `build_miri_adapter.sh` is Linux-hosted, so supporting native Windows builds requires a PowerShell/Python equivalent or an explicitly supported native shell/tool layout.

Minimum bootstrap configuration derives from the existing source-build script:

- `[build]`: `build = B`, `host = [H]`, `target = [H]`, absolute build directory, explicit executable stage0 rustc/cargo, `local-rebuild = true`, disable unavailable optional profiler/sanitizer tools.
- `[rust]`: pinned stable channel; `download-rustc = false`; select `codegen-backends = ["cranelift"]` for the existing LLVM-free route; no jemalloc/JIT, LLD/profiler tool distribution or debug info unless needed.
- `[target.H]`: explicit platform `cc`, `cxx`, `linker`, `ar`, `ranlib`; correct SDK/sysroot/deployment version and platform link flags.
- The assembled runtime inputs are under `build/H/stage1`; the executable stage0's cross-target private metadata is under `build/B/stage0-sysroot` in the current OHOS pattern. Discover actual output paths and validate them rather than assuming every bootstrap layout.
- Build the staged adapter using the pinned executable compiler, that bootstrap's compiler-private sysroot, `--target H`, and both Cargo and rustc `dual-proc-macros` mode. Preserve `--locked` and the existing upstream Miri patch/fingerprint validation.

Pinned upstream bootstrap source explains why these inputs must stay together:

- `src/bootstrap/src/core/build_steps/compile.rs:990`: `Rustc.target` is the platform where the built compiler runs.
- Lines 1128-1135: build scripts/proc macros also require the executable build host's standard library.
- Lines 1181-1187: most distributed rustc crates are metadata only; object code is inside `librustc_driver`.
- Lines 1359 and 2399: bootstrap chooses the default backend and assembles its host-specific artifacts.
- Lines 2727-2733: host proc-macro artifacts are handled separately. Do not mix official compiler macros with a custom compiler's private metadata.

### Codegen backend ownership and optional ABI extension

The exact pinned `compiler/rustc_interface/src/util.rs` is available in the local `rustc-src` root and was also fetched from the pinned upstream revision:

- Lines 338-354: `get_codegen_backend()` stores the first factory in a process-global `OnceLock`.
- Lines 341-344: selection uses explicit name, target default, compiler build's `CFG_DEFAULT_CODEGEN_BACKEND`, then dummy.
- Lines 347-348: a name containing `.` is treated as an explicit executable-library path.
- Lines 351-352: LLVM is built into `rustc_interface` when its `llvm` feature is enabled. An official LLVM compiler does not require a separate codegen-backend asset, but its driver/LLVM dynamic dependency closure still matters.
- Lines 512-517: an external default backend is searched using the compiler's native `host_tuple()`, not the interpreted guest target.
- Lines 357-359: loading a backend built against a different driver can cause undefined behavior.

The proposed optional symbol is appropriate:

```c
QfliSession *qfli_miri_create_with_backend(
    const QfliConfig *config, const char *backend_path);
```

Implementation requirements:

1. Keep ABI version 1, existing `QfliConfig` layout and `qfli_miri_create()` unchanged.
2. Copy/validate UTF-8 backend input into the session. An explicit absolute framework/native-library path should come from the app bundle/native library directory, not project user input.
3. Pass `Some(path)` through the callbacks' `make_codegen_backend` closure to `get_codegen_backend()`.
4. Require a single backend identity for the process. The upstream cache will not honor later backend changes; reject conflicting requests before running rather than implying the choice is session-local.
5. Keep libraries loaded until process exit. Preserve serialization and cancellation/destroy ordering.
6. Dart should detect the optional symbol; when the selected platform requires explicit backend loading, report incompatible runtime rather than silently selecting an extracted executable asset.

An Apple path such as `/.../Frameworks/QfliCodegen.framework/QfliCodegen` contains `.` in `.framework` and reaches upstream's explicit-path loader. Android can pass an absolute extracted native-library path. No change to MIR sysroot file paths is required for this extension.

Cranelift feasibility is source-backed, not build-verified here: the pinned `compiler/rustc_codegen_cranelift/Cargo.toml:11` enables `all-native-arch`; JIT dependencies/features are optional at lines 15 and 46-47. `src/lib.rs:156-197` implements x64/ARM64 target configuration. The adapter only needs target configuration and never calls its user-code generator. This supports reusing the OHOS architecture while retaining real upstream semantics. It does not prove a new mobile host build succeeded.

### Android: build and packaging

- Use hosts `aarch64-linux-android` and `x86_64-linux-android`, mapped to `arm64-v8a` and `x86_64`.
- `android/local.properties` selects `D:/ProgramData/Android/Sdk`. NDK `27.0.12077973` contains actual Windows-host Clang target wrappers and LLVM tools. NDK `28.2.13676358` contains only `.installer` during inspection, so do not select that incomplete installation by directory name.
- Verified tool directory: `D:/ProgramData/Android/Sdk/ndk/27.0.12077973/toolchains/llvm/prebuilt/windows-x86_64/bin`. `clang.exe`, `llvm-ar.exe`, `llvm-ranlib.exe`, `llvm-readelf.exe`, `llvm-readobj.exe` and both API 21 arm64/x64 Clang `.cmd` wrappers exist. CMake is installed under `D:/ProgramData/Android/Sdk/cmake/3.22.1`.
- Select API level consistent with `minSdk`; NDK wrappers include names such as `aarch64-linux-android21-clang.cmd` and `x86_64-linux-android21-clang.cmd`. Build bootstrap compiler dependencies with the same NDK/target/API linkage.
- On a Linux build host use an actual Linux-hosted NDK. Windows NDK `.exe`/`.cmd` tools cannot be treated as Linux native linker executables.
- Set 16 KiB ELF load-segment alignment where required by the chosen Android release/NDK; validate program headers and dependency alignment. NDK 27 builds should supply the appropriate max-page-size linker flag rather than assuming its old default works on 16 KiB devices.
- Put adapter, custom rustc driver, Cranelift backend and all non-system `DT_NEEDED` dependencies in `android/app/src/main/jniLibs/<ABI>/`.
- Validate target architecture, ELF shared-object type and complete dependencies with NDK `llvm-readobj`/`llvm-readelf`. Bionic/system dependencies may stay platform-owned; include matching `libc++_shared.so` if required. Never package Linux glibc or OHOS musl libraries into an Android ABI directory.
- A `nativeLibraryDir` absolute backend path requires physical library extraction. Set the appropriate Gradle `packaging.jniLibs.useLegacyPackaging` behavior or implement APK-backed loading explicitly; do not assume Flutter always extracts native binaries.
- Add a narrow platform method that returns `applicationInfo.nativeLibraryDir` and select the backend from that read-only installation directory. Ensure dependencies can resolve by their packaged SONAMEs.
- Keep guest MIR `.rlib` data and license assets in Flutter's flattened manifest. Do not copy the executable backend into writable guest data for Android.
- Current Gradle config uses `ndkVersion = flutter.ndkVersion`; an available NDK needs to be selected explicitly or installed before claiming the build can run.

No Android native compiler or app execution test was run by this researcher. The observed NDK makes local cross-compilation possible once complete source/private library build inputs are prepared; it is not evidence of a ready Android interpreter.

### iOS: source build, frameworks and static-link limitations

- Supported device host: `aarch64-apple-ios`. Supported simulator hosts: `aarch64-apple-ios-sim` and `x86_64-apple-ios`. Treat device and simulator as distinct platform variants even when their CPU is arm64.
- Build on a Mac with Xcode's `iPhoneOS.sdk`/`iPhoneSimulator.sdk`, an executable pinned Mac stage0 compiler and complete source. Set `SDKROOT`/`IPHONEOS_DEPLOYMENT_TARGET`, `xcrun` SDK/linker choices and each host's build config.
- Official iOS `rust-std` is not compiler-private metadata. Source-bootstrap the target-host compiler and use its matching build-host proc macros to build Miri.
- The existing dynamic route can produce separate runtime/driver/backend libraries, then wrap each non-system Mach-O dynamic library as an embedded signed framework. Give the framework executable a valid `LC_ID_DYLIB`; rewrite all non-system dependency load commands to `@rpath/<Framework>.framework/<Executable>`.
- `QfliMiri.framework`, a compiler-driver framework and `QfliCodegen.framework` are examples of ownership, not already-existing files. Additional dynamic std/C++/LLVM dependencies must also be resolved correctly; audit with `otool -L` and `lipo`/Mach-O header inspection.
- Package device/simulator slices into proper XCFramework variants (`xcodebuild -create-xcframework`). Do not use a single arm64 universal binary to merge device and simulator.
- In Runner add linking plus Embed & Sign for the selected dynamic frameworks. Return `Bundle.main.privateFrameworksPath` through the platform channel for explicit FFI/backend lookup. Existing `LD_RUNPATH_SEARCH_PATHS` includes `@executable_path/Frameworks`, but there are no runtime frameworks linked or copied today.
- Keep executable binaries in the signed application bundle. Guest metadata and license data may be extracted to app storage; the backend must stay in the signed framework location.

Simply changing the adapter output to `staticlib` is not a completed static iOS solution. The pinned upstream `compiler/rustc_driver/Cargo.toml:7` declares only `dylib`, and distribution metadata alone cannot be statically linked. The custom Cranelift backend also declares `dylib` and is loaded dynamically by current code. A full static solution requires rebuilding the compiler dependency graph with linkable Rust objects/rlibs, changing driver/backend linkage (or using a built-in LLVM backend), retaining exported C ABI symbols with the app linker, and using `DynamicLibrary.process()` in Dart. This is a separate larger build path. Signed dynamic frameworks are the closest reuse of the existing architecture.

There is no macOS/Xcode execution environment on this Windows host; iOS build/signing/device tests should be skipped here, with that limitation recorded. The Windows absence of Xcode is a local tooling limitation, not proof that a source-built signed iOS interpreter is impossible.

### macOS: official compiler host path

- Pinned official `rustc` plus `rustc-dev` exists for both `aarch64-apple-darwin` and `x86_64-apple-darwin` in the inspected distribution manifest.
- On the matching Mac install those components, stage and patch Miri as the current script does, then build the adapter with the executable same-revision compiler and matching private libraries. Extend output selection to `libqfli_miri.dylib` and use platform-appropriate compiler search paths.
- Official LLVM backend is built into the compiler driver; a custom Cranelift build still needs its external backend and explicit read-only path.
- Bundle the dylib closure under the app's `Contents/Frameworks`, rewrite install names to `@rpath`, and sign embedded code in the Runner build. Audit all architecture/dependency slices before composing a universal application.
- Preserve the existing desktop Cargo execution path. Its use of external user toolchains is a separate desktop workflow from the packaged interpreter.
- Existing macOS release entitlements enable app sandboxing; working directory/file access and external Cargo dependencies require actual Mac app evidence. Do not promise that desktop process execution inside a signed release bundle has been validated by Windows checks.

### Guest MIR portability

Miri's pinned README lines 149-155 explicitly describes `x86_64-unknown-linux-gnu` cross-interpretation independent of host OS. The ABI's fixed Linux guest is therefore a valid shared design for Android/iOS/macOS and avoids interpreting an unsupported iOS guest.

Guest `.rlib` files must be built with encoded MIR, not supplied by an ordinary downloaded `rust-std` package. `scripts/prepare_miri_sysroot.sh` uses the pinned upstream Miri/cargo-miri setup; pinned `cargo-miri/src/setup.rs:93-113` routes the standard-library build through Miri, and lines 135-139 choose the setup flags.

Reuse of those data files across hosts remains conditional on the same compiler revision and compatible metadata/build flags. Validate the guest library with each newly built host compiler. Custom compiler-private metadata and native proc macros are host-specific; do not conflate them with the fixed guest MIR data.

Multi-platform packaging requires per-host manifests or explicit host entries. A single `assets/miri/manifest.json` currently describes one native architecture and cannot simultaneously identify Android arm64/x64, Apple device/simulator and OHOS without selection changes.

### Web constraint

The current implementation cannot be turned into a browser interpreter by adding `wasm32-unknown-unknown` to its target list:

- Dart Web has no native `dart:ffi` library loader or desktop process API.
- The native crate uses compiler-private host libraries, filesystem paths, synchronization, time and dynamic compiler backend loading. No rustc host tools are distributed for `wasm32-unknown-unknown`.
- Pinned upstream WebAssembly target docs state that ordinary `std::fs` returns errors and `std::thread::spawn` panics; Miri also depends on `mio` OS polling/network APIs.
- A complete browser route would need a separately ported/compiler runtime, browser workers, a virtual filesystem, JavaScript/Wasm interop and guest asset transport. This has not been implemented or proven by the native code.

Report native-ABI support as unavailable on Web unless that separate design is implemented. Introducing a remote execution service changes the user's local native runtime requirement and needs an explicit product decision.

### Recommended implementation ownership

| Files/responsibility | Action |
| --- | --- |
| `native/miri_adapter/src/lib.rs`, `qfli_miri.h`, native ABI fixture | Optional backend-path symbol, copied inputs, callback propagation, consistent process backend |
| `scripts/build_miri_adapter.sh` plus native Windows equivalent | General host target/linker/output selection; preserve pinned source/private metadata checks |
| New reusable source-bootstrap script | Complete pinned source, platform host configuration, compiler and matching backend/private metadata outputs |
| New platform packaging script(s) | Validate and package ELF/Mach-O closure and guest/license manifests for the selected host |
| `lib/ohos_miri_runner.dart`, `lib/ohos_miri_assets.dart`, `lib/rust_runner.dart` | Reuse ABI session lifecycle across native platforms, select manifest/native library/backend path, preserve Cargo desktop runner |
| Android Gradle/MainActivity | Native library extraction/ABI selection and native directory platform method |
| Apple Runner/Xcode build files | Native bundle path method, platform slice linkage, framework embedding/install-name repair/signing |
| Documentation/platform capability status | Separate completed integration, built native artifacts and packaged source-execution evidence |

Completion requires a real produced runtime for each buildable platform and native source execution on available hosts. A successful loader, fake ABI fixture or missing-library error test does not demonstrate real compiler/interpreter support.

### Files found

- `.trellis/spec/backend/native-runtime.md`: pinned ABI, matching metadata, guest target and current validation gates.
- `native/miri_adapter/src/lib.rs`: shared compiler callbacks, Miri session and C ABI exports.
- `native/miri_adapter/Cargo.toml`: staged Miri dependency/features and shared-library output.
- `native/miri_adapter/qfli_miri.h`: stable C ABI layouts and lifecycle.
- `native/patches/miri-1.98.1-embedded-session.patch`: upstream in-process I/O/session integration.
- `scripts/build_miri_adapter.sh`: Linux/OHOS adapter staging/build pipeline.
- `scripts/check_rustc_x64_ohos.sh`: source archive/revision checks and custom compiler bootstrap pattern.
- `scripts/package_miri_ohos.ps1`: ELF closure inspection and flattened asset manifest.
- `scripts/prepare_miri_sysroot.sh`: pinned MIR-encoded Linux guest standard library preparation.
- `lib/ohos_miri_assets.dart`: current single-manifest storage extraction.
- `lib/ohos_miri_runner.dart`: C ABI binding, worker execution, bounded I/O and lifecycle.
- `lib/rust_runner.dart`: OHOS/native dispatch and existing desktop Cargo path.
- `android/app/build.gradle.kts`: default Flutter NDK/config without a Miri ABI integration.
- `ios/Runner.xcodeproj/project.pbxproj`: existing Runner linkage/copy phases without runtime frameworks.
- `macos/Runner.xcodeproj/project.pbxproj`: existing app framework paths without embedded Rust runtime.
- `macos/Runner/Release.entitlements`: app sandbox enabled for the release bundle.
- `web/index.html`: regular Flutter loader; no Wasm compiler bridge.
- External Miri sparse source and installed `rustc-src` roots listed above: authoritative pinned code browsing inputs, incomplete source-bootstrap roots.

### External references and versions

Fetched/read on this date unless marked otherwise:

- [Pinned Rust platform support](https://raw.githubusercontent.com/rust-lang/rust/48a229ceaefd4985c50990b14116b6d856af0985/src/doc/rustc/src/platform-support.md): host-tool availability.
- [Pinned Android targets](https://raw.githubusercontent.com/rust-lang/rust/48a229ceaefd4985c50990b14116b6d856af0985/src/doc/rustc/src/platform-support/android.md): NDK/cross-compile requirement.
- [Pinned iOS targets](https://raw.githubusercontent.com/rust-lang/rust/48a229ceaefd4985c50990b14116b6d856af0985/src/doc/rustc/src/platform-support/apple-ios.md): Xcode SDKs, device/simulator targets and deployment version.
- [Pinned macOS targets](https://raw.githubusercontent.com/rust-lang/rust/48a229ceaefd4985c50990b14116b6d856af0985/src/doc/rustc/src/platform-support/apple-darwin.md): host tools and Mach-O linkage.
- [Pinned backend loader](https://raw.githubusercontent.com/rust-lang/rust/48a229ceaefd4985c50990b14116b6d856af0985/compiler/rustc_interface/src/util.rs): explicit path, default and process cache semantics.
- [Pinned compiler bootstrap](https://raw.githubusercontent.com/rust-lang/rust/48a229ceaefd4985c50990b14116b6d856af0985/src/bootstrap/src/core/build_steps/compile.rs): cross-host private library/metadata/proc-macro assembly.
- [Pinned LLVM bootstrap](https://raw.githubusercontent.com/rust-lang/rust/48a229ceaefd4985c50990b14116b6d856af0985/src/bootstrap/src/core/build_steps/llvm.rs): cross-compilation and iOS-specific configuration are present upstream.
- [Pinned Wasm target](https://raw.githubusercontent.com/rust-lang/rust/48a229ceaefd4985c50990b14116b6d856af0985/src/doc/rustc/src/platform-support/wasm32-unknown-unknown.md): missing OS filesystem/thread behavior.
- [Android NDK prebuilt libraries](https://developer.android.com/ndk/guides/prebuilts): ABI-specific shared/static packaging.
- [Android Gradle native build integration](https://developer.android.com/studio/projects/gradle-external-native-builds): attempted fetch failed with transport EOF; Gradle `jniLibs` recommendation uses established platform conventions and still needs local build validation.
- [Flutter iOS C interop](https://docs.flutter.dev/platform-integration/ios/c-interop): attempted fetch failed with transport EOF; framework/static-link discussion is grounded in inspected Cargo/Xcode files and Mach-O linkage requirements, not a successful doc fetch.

### Related specs

- `.trellis/spec/backend/native-runtime.md`: preserve pinned compiler revision, ABI version/layout, no false runtime availability, cancellation/destruction ordering and per-host metadata.
- `.trellis/spec/backend/index.md`: native-runtime is the documented backend contract; other backend pages remain placeholders.
- `.trellis/spec/guides/cross-layer-thinking-guide.md`: build artifact -> platform package -> manifest -> Dart/native boundary needs one explicit contract and host selection.
- `.trellis/workflow.md:363`: research is persisted under the supplied active task; this file is the sole write scope.

## Caveats / Not Found

- No new native build, interpreter fixture, Android emulator/device, Apple simulator/device, HAP installation, or WSL command was run. Source/SDK findings do not establish platform runtime availability.
- WSL escalation was already rejected for the parent session with an automatic approval HTTP 503. No indirect WSL filesystem, process or distribution access was used here.
- Android's actual installed NDK is 27.0, while the 28.2 directory is incomplete. Complete pinned Rust bootstrap source/private host build outputs are absent in the inspected local roots.
- Apple build and signing need a Mac/Xcode environment; this is a test/build host limitation, not an intrinsic ban on interpreting a Linux guest with signed native code.
- Full static iOS linkage requires additional compiler/backend build work beyond the existing cdylib adapter. Generic FFI process-symbol wiring cannot substitute for the missing static compiler objects.
- Guest metadata portability and new Android/Apple compiler-host source builds remain to be validated. Retain those acceptance items until concrete artifact/build evidence exists.
