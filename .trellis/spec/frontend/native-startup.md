# Native Startup

## 1. Scope / Trigger

OHOS startup crosses Dart, the platform channel and ArkUI. Follow the native
startup implementation in `../qflistudio` so Flutter initialization does not
expose an empty engine surface.

Owners: `lib/main.dart`,
`ohos/entry/src/main/ets/entryability/EntryAbility.ets`, and
`ohos/entry/src/main/ets/pages/Index.ets`. The shared core's
`AppBootstrap` in `../qfli_studio_core/lib/splash_screen.dart` loads project,
authentication and settings stores and sets `ready.value = true`.

## 2. Signatures

```dart
const platformChannel = MethodChannel('qflistudio/platform');
await platformChannel.invokeMethod<void>('startupProgress', {
  'progress': progress,
});
```

The native handler emits `EVENT_STARTUP_PROGRESS` through the ability's
`eventHub`. `StartupSplash` subscribes in `aboutToAppear()` and unsubscribes
the same callback in `aboutToDisappear()`.

## 3. Contracts

- Request: `{progress: double}`, a finite completion fraction. Native code
  clamps valid numbers to `[0, 1]` and returns `success(null)`.
- The native splash converts fractions to percentages for a linear progress
  indicator. It uses `app.media.icon` and `app.color.start_window_background`.
- `FlutterPage({viewId, splashScreenView: this.startupSplash})` owns the splash
  lifetime; the engine's first-frame callback removes it. Progress `1.0` only
  updates the indicator.
- Only OHOS defers engine frames. Call `binding.deferFirstFrame()` before
  `runApp`; start bootstrap from the first post-frame callback.
- Match the main project: initial delay 160 ms, minimum display 1100 ms from
  bootstrap callback entry, and completion delay 320 ms after store loading.
  The minimum-display and completion waits run concurrently.
- After loading and timing waits, await `binding.endOfFrame` so the home page
  has finished build/layout. Call `binding.allowFirstFrame()` in `finally`.
- Other platforms keep the shared Flutter startup screen and do not report
  native progress. No new dependencies or environment keys are introduced.

## 4. Validation & Error Matrix

| Condition | Behavior |
| --- | --- |
| Finite number in `[0, 1]` | Emit the fraction; return success. |
| Finite number outside `[0, 1]` | Clamp before emitting; return success. |
| Missing, nonnumeric or nonfinite progress | Return `INVALID_PROGRESS`; do not emit. |
| Channel throws `PlatformException` | Log its code; continue startup. |
| Channel throws `MissingPluginException` | Continue startup. |
| One store load fails | Shared bootstrap logs the failure, counts completion and still sets ready. |
| Startup completion throws | The `finally` block releases deferred frames; the exception still propagates. |

## 5. Good / Base / Bad Cases

- Good: all stores finish, progress reports `1/3`, `2/3`, `1.0`, and the first
  submitted Flutter frame contains the home page.
- Base: a progress channel is unavailable; initialization and frame release
  still complete.
- Bad: removing the native splash on progress `1.0` exposes the engine before
  Flutter submits the home page.

## 6. Tests Required

`test/native_startup_test.dart` runs the real entry point with mocked local
storage and platform channels. Assert that frames remain deferred during
loading, the three completion fractions are emitted, and `HomePage` is built
before frame release. After the timing and frame waits, assert frames are
enabled and no Flutter exception was captured.

Verified on 2026-10-01: `dart analyze lib test`, the startup regression test,
and the native ArkTS compile passed. Device checks remain paused by the user.

```text
flutter test --no-pub test/native_startup_test.dart --reporter expanded
```

For ArkTS compilation, run from `ohos/` with the local DevEco JBR and SDK:

```powershell
$env:JAVA_HOME = 'D:/ProgramFiles/Huawei/DevEco Studio/jbr'
$env:DEVECO_SDK_HOME = 'D:/ProgramFiles/Huawei/DevEco Studio/sdk'
& 'D:/ProgramFiles/Huawei/DevEco Studio/tools/node/node.exe' `
  'D:/ProgramFiles/Huawei/DevEco Studio/tools/hvigor/bin/hvigorw.js' `
  --mode module -p product=default -p module=entry@default `
  -p buildMode=debug default@CompileArkTS --no-daemon
```

The task name must be `default@CompileArkTS`; bare `CompileArkTS` does not
resolve in this project. This compile does not sign, install or validate a HAP.

## 7. Wrong vs Correct

Wrong: call `allowFirstFrame()` when stores finish, or hide the native splash
when its progress reaches 100%, before the home page finishes layout.

Correct: await readiness, display timing and `endOfFrame`, release the first
frame in `finally`, and let `FlutterPage` remove its splash on the engine's
first-frame notification.
