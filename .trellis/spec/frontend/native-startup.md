# Native Startup

All new builds/tests/validation run only on GitHub-hosted runners under
[Cloud-only workspace](../guides/cloud-only-workspace.md). Historical results
below retain their original date and do not authorize local reruns.

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
- A hosted OHOS startup fixture must select the phone shell explicitly with
  `QfliApp(formFactor: AppFormFactor.phone)`. The OHOS debug platform override
  controls the startup branch, but core resolves its default form factor from
  the actual host OS. A Linux runner does not become a phone through that
  override alone.
- Keep the real entry point and its startup state when applying this fixture
  input. Preserve the original app key, stores, readiness notifier, navigator
  key and GitHub controller. Do not replace readiness, progress, timing or
  first-frame assertions with a fabricated ready application.

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

For the hosted phone fixture, call `application.main()` and observe the
deferred splash first. Rebuild the existing `QfliApp` with its original
dependencies and `formFactor: AppFormFactor.phone` before advancing startup
time. Keep the `ready` notifier produced by the entry point and require the
same `HomePage`, progress fractions and frame-release ordering.

Follow-up on 2026-11-28: quality run `46082334790` at source
`8b92ddc98151a394a57a5d5ce3eb0bea35f2266e` reported the startup test as failed.
Its public error did not expose the underlying exception body or stack.
The explicit phone input is a source-reviewed fixture correction against
core `8e031313ffc8d531c5a6b4d131f721f35da04c86`; the new repair is UNRUN.
It does not establish that form-factor selection caused that exact failure.
See the dated [quality input evidence](../../tasks/11-26-github-workspace-migration/research/quality-inputs-8b92ddc-2026-11-28.md).

Verified on 2026-10-01: `dart analyze lib test`, the startup regression test,
and the native ArkTS compile passed. Device checks remain paused by the user.

```text
flutter test --no-pub test/native_startup_test.dart --reporter expanded
```

For a new ArkTS compilation, provision the compatible JBR, Node and OHOS SDK
in a GitHub-hosted job and invoke Hvigor from that runner's `ohos/` checkout.
Do not copy historical machine-specific DevEco paths into local commands.
The task name is `default@CompileArkTS`; bare `CompileArkTS` does not resolve
in this project. Record the hosted SDK/Flutter identities and job outcome.
This compile does not sign, install or validate a HAP.

## 7. Wrong vs Correct

Wrong: call `allowFirstFrame()` when stores finish, or hide the native splash
when its progress reaches 100%, before the home page finishes layout.

Correct: await readiness, display timing and `endOfFrame`, release the first
frame in `finally`, and let `FlutterPage` remove its splash on the engine's
first-frame notification.
