# Rust offline surface audit: OHOS manifest INTERNET and reachable network paths

Date: 2026-10-22. Task: `.trellis/tasks/10-22-offline-ide-completeness`.
Owned edits: `ohos/entry/src/main/module.json5` and this report only. No core,
sibling product, `lib/`, script, git or other worker's file was modified (the
pre-existing dirty paths listed in `git status` — `lib/main.dart`,
`lib/native_miri_assets.dart`, `native/README.md`, `native/miri_adapter/*`,
`ohos/AppScope/app.json5`, `ohos/entry/build-profile.json5`,
`scripts/check_native_packaging.py`, `scripts/package_miri_ohos.ps1`,
`test/native_miri_assets_test.dart` — were left untouched). No Flutter/pub/build/
HDC command was run, so nothing here is a runtime or packaging pass.

## 1. Decision (one line)

`ohos.permission.INTERNET` is **removed** from the production OHOS manifest: no
app-owned remote flow is reachable in this offline product, and the only
conceivable loopback consumer (user Rust programs / Ports) is **rejected inside
the shipped interpreter**, so the permission currently enables nothing. The
removal is recorded with a restore precondition in the manifest itself, and the
requested Ports capability stays open in the ledger with its real blocker.

## 2. What changed

`ohos/entry/src/main/module.json5` — `requestPermissions` now contains only
`ohos.permission.READ_PASTEBOARD` (unchanged `reason`/`usedScene`). A JSON5
comment block records: the offline invariant, the audited-and-gated surfaces, the
loopback evidence, and the three-step restore condition. `git diff` is 1 deletion
(`{"name" :  "ohos.permission.INTERNET"},`) + 19 comment lines; no other field,
ability, resource or user edit in the file was touched.

Structural check (no build): the file parses with comments stripped and
`permissions: ohos.permission.READ_PASTEBOARD`. The previously built merged
artifact `ohos/entry/build/default/intermediates/merge_profile/default/module.json`
still lists INTERNET — expected, it is stale; **the release audit HAP must be
rebuilt** for the change to reach a package. No repo script or test asserts the
permission set (`grep INTERNET|requestPermissions|module.json5` over `scripts/`,
`test/`, `integration_test/` → no matches), so nothing in the repo contradicts
the removal.

Sibling precedent that removal is schema/packaging safe in this family: `qfli_dart`,
`qfli_json`, `qfli_lua`, `qfli_python` `ohos/entry/src/main/module.json5` already
ship with **no** INTERNET entry; `qfli_c/java/go/note/sql/web/qflistudio/cloudterminal`
still declare it.

## 3. Reachable-surface audit (Rust offline product)

Product identity: `lib/main.dart` `rustProfile` → `isOffline: true`,
`offlineOnly` defaults to `isOffline` (`qfli_studio_core/lib/services/studio_profile.dart:186-196`).

| Candidate network surface | Entry point | Offline reachability | Evidence |
| --- | --- | --- | --- |
| Agreement WebView (remote https page in `Web`) | `EntryAbility.openAgreement` (`ohos/entry/src/main/ets/entryability/EntryAbility.ets:48-62`) → `pages/AgreementReader.ets` (`Web({src:url})`, `loadUrl`, `onHttpErrorReceive`) | **Not reachable**: login/register hidden offline, profile agreement/ICP footer gated | `profile_page.dart:49,86,110-241` (`offlineOnly` early-return and `!offlineOnly` guards, incl. `_icpFooter()` at `:241`), `home_page.dart:164-168` comment + `login_page.dart:85-99` only from the login page |
| ICP filing query page (`https://beian.miit.gov.cn/`) | `profile_page._icpFooter` → `AgreementPage(url: ComplianceConfig.icpQueryUrl)` | **Not reachable** (guard above) | `config/compliance_config.dart:3`, `profile_page.dart:340-357` |
| AI panel / AI service (`HttpClient`) | `AiPanel` in the editor bottom panel, `services/ai_service.dart:99` | **Not reachable**: AI toggle and panel gated | `editor_page.dart:1490-1503,1670-1735,1918-1930,1983` (`showAi`/AI branches all `offlineOnly != true`) |
| Community / posts / points / checkin / audit / task config | `ApiClient.instance` call sites | **Not reachable**: destinations and sections hidden offline | `home_page.dart:143-168` (`offlineOnly` hides sections), `profile_page.dart:110-241`, call sites limited to `pages/community/*`, `points_page`, `audit_page`, `task_config_page`, `my_posts_page`, `login/register/account_login` |
| Cloud projects / cloud sync / git-over-cloud | `CloudSyncService.open`, `ApiClient.cloudProjects` | **Not reachable**: guarded | `editor_page.dart:211` (`isCloud && offlineOnly != true`), `home_page.dart:775` (`if (offlineOnly == true) return;`) |
| Online terminal | `TerminalPane.showOnline/runOnlineProject` | **Not reachable**: `onlineEnabled`/branches gated | `editor_page.dart:1076,1167,1191,1983`; `terminal_pane.dart` only enters online on those calls |
| System browser launch (`openUrl` → `startAbility`) | `RunnerService.openUrl` (`runner_service.dart:226-236`) | Reachable only through the `.html` run path; no InterNET needed by *our* app anyway (target app owns its permission) | callers: `runner_service.dart:146-147`, `editor_page.dart:1124` |
| App-owned loopback preview server | `LocalWebServer` (`services/local_web_server.dart:74` `HttpServer.bind(loopbackIPv4, 0)`) | **Not reachable in the Rust profile**: only started from the `.html` branch, and an `.html` file can never be the run target — tap Run resolves `main.rs` via `entryFileNames`, and active-file run rejects non-`.rs` | `runner_service.dart:120-150`, `editor_page.dart:1061-1062,1090-1101,1264-1268`, `lib/main.dart:44` `supportedFileExtensions: ['.rs']` |
| Native platform channel | `qflistudio/platform` → `startupProgress`, `openAgreement`, `openUrl`, `shareText`, picker methods | Local IPC only (Share Kit / file picker); no network | `EntryAbility.ets:38-100`, `PickerBridge.ets:12-46`, `services/picker_service.dart:39-89`, `services/share_service.dart` |
| Dart plugins that could open sockets/webviews | plugin registry | Only `integration_test` + `path_provider_ohos`; core pubspec has no `webview_flutter`/`url_launcher`/`connectivity` | `ohos/entry/src/main/ets/plugins/GeneratedPluginRegistrant.ets:16-19`, `qfli_studio_core/pubspec.yaml` |
| Auth/session startup | `AuthStore.load()` | Local file read only; `_token` dropped unless the service origin is ours | `store/auth_store.dart:28-50` (no network in `load`) |

Conclusion: for the Rust offline product, **every app-owned remote path is gated
by `offlineOnly`, and the loopback server has no reachable caller**. The
permission had no live production consumer.

## 4. Ports / loopback: the real blocker is interpreter isolation, not "no listener"

The user asked not to dismiss Ports merely because the bundled examples contain no
listener. That caution is right — and the actual finding is stronger. The shipped
runtime **is** technically able to serve sockets, but the adapter runs it in
Miri's default isolation, which rejects the host operation outright:

1. Miri ships full real socket shims: `native/build/miri-windows/miri/src/shims/unix/foreign_items.rs:656-760` dispatches `socket`, `bind`, `listen`, `accept`, `accept4`, `connect`, `send`, `recv`, `setsockopt`, `getsockname`; implementations in `shims/unix/socket.rs:300,380,450,503,610`; `virtual_socket.rs` additionally provides interpreter-internal socket pairs.
2. Every such shim first checks `machine.isolated_op`: `shims/unix/socket.rs:308-313` returns `EACCES` (or aborts) when it is `IsolatedOp::Reject`, with the comment "Reject if isolation is enabled".
3. `MiriConfig::default()` sets `isolated_op: IsolatedOp::Reject(RejectOpWith::Abort)` (`native/build/miri-windows/miri/src/eval.rs:196`; enum at `src/machine.rs:88-99` — `Reject` = do not communicate with the host, `Allow` = disable isolation).
4. The adapter only overrides `args`, `embedded_session`, `short_fd_operations` and takes `..MiriConfig::default()` (`native/miri_adapter/src/lib.rs:342-347`). It never sets `IsolatedOp::Allow`.

Therefore a user program doing `TcpListener::bind("127.0.0.1:0")` under the packaged
runtime fails at the interpreter layer regardless of the manifest permission — so
INTERNET cannot be justified by "user programs can use loopback" **as the runtime
is configured today**.

Ledger entry (R7), to stay open and honest:

- **Ports / local loopback debugging: feasible in principle, blocked by adapter isolation.**
  Enabling it requires (a) `native/miri_adapter` to set `isolated_op: IsolatedOp::Allow`
  (a deliberate, auditable security-posture change — it also permits host filesystem/clock
  communication, so it must be reviewed, not flipped casually), (b) an actual product flow
  that exposes the guest's listening port, and (c) re-adding `ohos.permission.INTERNET`
  on OHOS, because a listening socket is a network operation for the OS sandbox.
  Until all three exist, "Ports" must not be shown in the UI and must not be claimed as
  delivered. This is exactly the restore condition written into `module.json5`.
  (Whether OHOS specifically exempts `127.0.0.1` from INTERNET is **UNVERIFIED** here —
  no device run was allowed — which is another reason not to depend on the permission
  being removable *after* enabling isolation is decided.)

## 5. Proposals requiring other owners (not applied)

1. **Android inconsistency (owner: whoever owns the Android manifest).**
   `android/app/src/main/AndroidManifest.xml` declares **no** `<uses-permission>` at
   all, while OHOS previously requested INTERNET. That is consistent with the Rust
   product's current offline reality (no app-owned network), so nothing needs to be
   added now — but whoever enables loopback/Ports later must add
   `<uses-permission android:name="android.permission.INTERNET"/>` there too, in the
   same change as the adapter isolation change. If instead the team wants Android and
   OHOS byte-for-byte symmetric for store review, the OHOS state is now the reference
   (no INTERNET) and Android matches it already.
2. **`AgreementReader.ets` is now dead code in this product (owner: root).**
   It is a remote-WebView page reachable only via the `openAgreement` channel, which
   only the (hidden) login page and the (gated) ICP footer call. Options: keep it as
   shared scaffolding for the networked umbrella app, or delete it — but do **not**
   leave a remote WebView wired to a channel that any Dart caller can invoke while
   claiming "no network surface"; if it stays, an offline build guard (e.g. reject
   `openAgreement` when `StudioProfile.current?.offlineOnly == true`) would make the
   invariant enforced rather than convention. That guard is native code and out of my
   ownership.
3. **R7 panels seam (already requested by root, seq147).** Unchanged by this audit:
   `_BottomPanel` (`editor_page.dart:54`) still has no product extension point, so
   Output/Debug Console/Ports have no host surface. The Ports requirement above should
   be evaluated together with that seam so the ledger records one coherent plan.
4. **Docs/store copy (owner: root).** If the release notes or privacy declaration
   mention network capability, they should now state "no network permission declared;
   all features are local", matching the manifest.

## 6. Residual risks and verification needed later

- **Rebuild required**: the packaged HAP still carries INTERNET until the next
  release build regenerates `intermediates/merge_profile/default/module.json`
  (currently stale with 2 permissions). Root should confirm the rebuilt HAP reports
  exactly `READ_PASTEBOARD` (and no INTERNET) in its `module.json`, e.g. via
  `hdc shell bm dump -n com.azurekiln.qfli.rust` after install — device evidence is
  explicitly out of scope for this audit.
- **Pasteboard permission kept deliberately**: the Flutter OHOS engine requests it at
  runtime (`ohos/oh_modules/.../PasteboardUtils.ets:34-52`
  `requestPermissionsFromUser([... 'ohos.permission.READ_PASTEBOARD'])`), so removing
  it would break editor paste.
- **`deviceTypes`** is `["phone"]` only; unrelated to offline, untouched.
- **No negative test exists** for the invariant. Suggested (owner: root/C): a
  test/CI grep asserting the OHOS production manifest contains no `INTERNET` entry
  while `rustProfile.offlineOnly` is true, plus a test that no `offlineOnly` product
  can reach `AgreementPage`/`ApiClient` from the visible tabs. This audit found the
  gating correct by reading; a guard would keep it correct.
