# Rust direct offline tools: semantics, reuse and layout review (R4)

Date: 2026-10-22 · Research/review only. No product code, shared core, git or
sibling product file was modified. Nothing here is a completion claim.

## 0. Honesty header (read first)

- This host has **no `rustc`/`cargo`** (`rustc --version` → not recognized;
  `~/.cargo/bin` absent). Every rustc-level claim below is either (a) quoted from
  the Rust Reference grammar, or (b) explicitly tagged
  **[VERIFY-WITH-RUSTC]**. Items tagged (b) **must not be printed in UI copy as
  fact** until the implementer runs them on a toolchain-equipped machine (or
  through the app's own native runner). No behavior was verified empirically here.
- `hdc list targets` now returns `127.0.0.1:5555`, which contradicts the
  "hdc Empty" line in `research/baseline-audit.md`. Device work is unblocked in
  principle; no device run was performed by this review.
- Existing Rust tooling files are `lib/cargo_targets.dart` only. There is **no**
  Rust tools page today: `lib/main.dart:28-57` (`rustProfile`) sets no
  `toolsTabBuilder`, so `FunctionsTab` renders the generic body
  (`qfli_studio_core/lib/pages/quick_tools_page.dart:39-79`).

## 1. Seams that already exist (reuse, do not rebuild)

| Seam | Path | Notes |
| --- | --- | --- |
| `StudioProfile.toolsTabBuilder` | `qfli_studio_core/lib/services/studio_profile.dart:157` | Contract doc at `:144-155` says "Return a ToolsGrid with product sections and the supplied terminal callback". |
| Host wiring | `qfli_studio_core/lib/pages/home_page.dart:224-243` | Passes `store` + `onOpenTerminal`; a non-null builder **replaces** the tab body and the old 功能 entry. |
| `ToolsGrid` / `commonTools` | `qfli_studio_core/lib/pages/tools_grid.dart:38`, `:96` | `commonTools` (9 tools) is always appended by `ToolsGrid`; sections render between 快捷入口 and 通用. |
| `ToolsGridSliver` | `tools_grid.dart:154-195` | Public; card geometry + `mainAxisExtent: ToolsTheme.cardHeight + extraTextHeight` already compensates for text scale. |
| `_OfflineNote` | `tools_grid.dart:198` | **Private** — a product body cannot reuse the "全部本机离线" note. |
| Card/detail tokens | `tool_widgets.dart:10-39` (`ToolsTheme`), `:41` `ToolsSectionHeading`, `:90` `ToolCard`, `:162` `ResultRow`, `:233` `ToolScaffold`, `:283` `ToolField`, `:319` `ToolError`, `:337` `ToolResultCard`, `:219` `Copy` | `ResultRow` uses a **fixed `width: 104`** label box (`:186`), `ToolCard` clips to `maxLines: 1/2` (`:134`,`:143`). |
| Cargo resolver | `lib/cargo_targets.dart` | `decodeCargoTargets` (`:104`), `selectCargoTarget` (`:243`), `cargoNotRunnableMessage` (`:266`), `cargoAmbiguousMessage` (`:275`), `cargoRunArguments` (`:283`). Typed outcomes: `CargoTargetMatch/Unregistered/NotRunnable/Ambiguous` (`:58-101`). |

### 1.1 Blocker B1 — profile wiring belongs to root, not the tools worker

`implement.md` (batch 2) gives the tools worker only "direct Rust tools and tests",
and `design.md` says "Root alone integrates main.dart." So the worker must **not**
edit `lib/main.dart`; it must export `buildRustToolsTab(ProjectStore store, VoidCallback onOpenTerminal)`
and hand root the exact one-line wiring:

```dart
toolsTabBuilder: buildRustToolsTab,   // inside rustProfile, lib/main.dart
```

Until root lands that line, **R4 has zero acceptance evidence**: the tab still
renders the generic body. Add the positive guard the C product uses
(`../qfli_c/test/forge_tools_test.dart:10`: `expect(forgeProfile.toolsTabBuilder, isNotNull)`).

### 1.2 Blocker B2 — three sibling products already diverge on composition

- **C** (`../qfli_c/lib/main.dart:37` → `ForgeToolsBody`) hand-rolls a
  `SingleChildScrollView` and **drops `commonTools` entirely**
  (`../qfli_c/lib/forge_tools_page.dart:22-88`). Copying this fails the design
  line "Keep shared common tools accessible" and R4's common-tools visibility.
- **SQL** (`../qfli_sql/lib/sql_tools_tab.dart`) uses `ListView` + inline
  `ListTile`s and re-imports `commonTools` to re-render the 9 shared tools,
  duplicating `ToolsGrid`'s `tool.onTap ?? builder` dispatch and the private note text.
- **Dart** (`../qfli_dart/lib/dart_tools_page.dart:592-612`) repeats the same
  hand-rolled `commonTools` loop incl. the `onTap`/`builder` fallback.
- **Lua/Java/Python** (`../qfli_lua/lib/lua_tools_page.dart:16-52`,
  `../qfli_java/lib/java_tools_page.dart:84-97`, `../qfli_python/lib/python_tools_page.dart:16`)
  return a real `ToolsGrid` with `builder:` cards → each tool is a second-level page.

So "flat on the tools page" (the user's wording, and PRD R4 "no
dedicated-feature detour") and "keep the shared common group" are only jointly
satisfiable in one of two shapes; pick deliberately and record it:

| Shape | Flat inline panels | Keeps `commonTools` | Layout/2x reuse | Duplication cost |
| --- | --- | --- | --- | --- |
| **A. Inline sections + `ToolsGridSliver(tools: commonTools)`** inside one `CustomScrollView` (**recommended**) | yes | yes (explicitly, incl. 终端 card via `onTap`) | card geometry for the shared group only; panels are custom | must re-author section headings + the offline note (private `_OfflineNote`) |
| B. `ToolsGrid(onOpenTerminal:, sections: [...])` with `builder:` cards (Lua shape) | no (one nav level per tool) | yes (automatic) | full | near-zero, but contradicts "no 二级页面" |
| C. C/SQL shape (inline panels + hand-rolled commonTools `ListTile`s) | yes | yes | none (custom) | duplicated dispatch + duplicated note text |

Recommendation: **A**, because it satisfies both R4 clauses and keeps the shared
card grid (which already handles 2× text) for the shared group. Ask the core owner
(C coordinator) for either an exported `OfflineToolsNote` widget or accept a
one-line text copy; do **not** silently fork `ToolsGrid`.

## 2. Tool family A — Rust integer literals, type bounds, wrapping arithmetic

### 2.1 Exact literal grammar (Rust Reference, lexical `INTEGER_LITERAL`)

```text
INTEGER_LITERAL : (DEC_LITERAL | BIN_LITERAL | OCT_LITERAL | HEX_LITERAL) INTEGER_SUFFIX?
DEC_LITERAL : DEC_DIGIT (DEC_DIGIT | '_')*
BIN_LITERAL : '0b' (BIN_DIGIT | '_')* BIN_DIGIT (BIN_DIGIT | '_')*
OCT_LITERAL : '0o' (OCT_DIGIT | '_')* OCT_DIGIT (OCT_DIGIT | '_')*
HEX_LITERAL : '0x' (HEX_DIGIT | '_')* HEX_DIGIT (HEX_DIGIT | '_')*
INTEGER_SUFFIX : i8|i16|i32|i64|i128|isize|u8|u16|u32|u64|u128|usize
```

Consequences the tool must honour (these are exactly where a naive port breaks):

1. **`_` is legal after the radix prefix**: `0x_FF`, `0o_17`, `0b_1010` are valid
   (once digit follows). `0x_` is invalid.
2. **`1_000` is valid**; `1__2` is valid; a literal cannot be only `_`.
3. Decimal trailing `_` (`1_`) and `1_u8`: grammar permits, but acceptance is
   **[VERIFY-WITH-RUSTC]** — do not claim either way in UI copy before testing.
4. `-` is **not part of the literal**: `-128` is unary negation applied to `128`.
   `-128i8` is therefore signed literal `128i8` → out of range
   **[VERIFY-WITH-RUSTC]**; the exemption that allows `let x: i8 = -128;`
   (suffix-less, context-typed) is a lint/typing rule, not a lexical one.
   The tool must model "suffix decides the range" and prefer `i8::MIN` wording.
5. Unsuffixed literals: default type `i32`; a value that does not fit `i32` needs a
   suffix or context. Show "推断为 i32（默认）" instead of declaring an error.
6. `0b`/`0o`/`0x` values still range-check against the suffix (`0xFFu8` ok,
   `0xFFi8` out of range). Hex/oct/bin are never "sign-magnitude".
7. Suffix immediately followed by an identifier char (`1u8x`) is an error, not 1u8.

### 2.2 Type bounds table (must be generated from BigInt, not hardcoded Dart int)

| Type | min | max |
| --- | --- | --- |
| i8 / u8 | -128 / 0 | 127 / 255 |
| i16 / u16 | -32768 / 0 | 32767 / 65535 |
| i32 / u32 | -2147483648 / 0 | 2147483647 / 4294967295 |
| i64 / u64 | -9223372036854775808 / 0 | 9223372036854775807 / 18446744073709551615 |
| i128 / u128 | -170141183460469231731687303715884105728 / 0 | 170141183460469231731687303715884105727 / 340282366920938463463374607431768211455 |
| isize / usize | -2⁶³ / 0 | 2⁶³-1 / 2⁶⁴-1 **only when 64-bit** |

Dart-specific accuracy hazards (all real, all in scope):

- `int` is 64-bit signed on the VM. `int.parse('340282366920938463463374607431768211455')`
  **throws**; `u64::MAX` also exceeds `int` for some ops. Use `BigInt.parse` /
  `BigInt.one << 128` everywhere for 128-bit and for any `u64` comparison at the
  boundary. Never `int.tryParse` a Rust literal.
- `BigInt` has no bit-width; masks must be explicit: `mask = (BigInt.one << width) - BigInt.one`,
  `signed = pattern >= (BigInt.one << (width-1)) ? pattern - (BigInt.one << width) : pattern`.
- `usize` is **not** universally 64-bit (32-bit on armv7/wasm32). Design requires
  stating the target assumption. Show a `usize/isize 位宽` selector (32/64) with the
  current default (OHOS arm64/aarch64 → 64) and label it "假设值，非编译器输出".
- Alternating `~` on a `BigInt` yields a negative infinite-precision value; always
  `~pattern & mask`.

### 2.3 Arithmetic-mode semantics the tool must compute exactly

For each of `+ - * / % << >> neg abs pow`, offer `普通 / wrapping / checked / overflowing / saturating`
and reproduce **std**, not an approximation:

| Case | Expected result |
| --- | --- |
| `255u8.wrapping_add(1)` | `0` |
| `0u8.wrapping_sub(1)` | `255` |
| `250u8.checked_add(10)` | `None` |
| `250u8.saturating_add(10)` | `255` |
| `250u8.overflowing_add(10)` | `(4, true)` |
| `i8::MIN.wrapping_neg()` / `wrapping_abs()` | `i8::MIN` |
| `i8::MIN.checked_div(-1)` | `None` |
| `i8::MIN.wrapping_div(-1)` | `i8::MIN`; `wrapping_rem(-1)` → `0` |
| `i8::MIN / -1`, any `x / 0`, `x % 0` | **panic** (must be shown as panic, never 0/None) |
| `-7i32 % 3`, `7i32 % -3` | `-1` (truncated; sign follows dividend) |
| `1u8.checked_shl(8)` | `None`; `wrapping_shl(8)` → `0` (shift masked to `% 8`) |
| `1u8 << 8` | debug: panic "attempt to shift left with overflow"; release: masked **[VERIFY-WITH-RUSTC]** |
| `200u8.pow(2)` | overflow: debug panic / release wrap; `checked_pow`/`wrapping_pow` defined |
| `-1i32 as u128` | `u128::MAX` (sign-extend then reinterpret) |
| `u128::MAX as i32` | `-1` (truncate low 32 bits) |
| `300i32 as u8` | `44` (curriculum already teaches this: `rust-tutorial-015`) |
| `1.0e30_f64 as i32` | `i32::MAX`; `f64::NAN as u8` → `0` (saturating since 1.45) |
| `1u8 << true`-style misuse | not expressible; don't invent ops |

Cross-check with shipped curriculum so the tool never contradicts the lessons:
`assets/content_rust/tutorials.json` → `rust-tutorial-015` lesson already prints
`checked_add(10) = None`, `wrapping_add(10) = 4`, `saturating_add(10) = 255`,
`300 as u8 = 44`. The tool's outputs for those exact inputs must match verbatim.

### 2.4 Do **not** reuse `../qfli_c/lib/forge_integer_tools.dart` as-is

It is C-semantics, and a straight port would print wrong answers for Rust:

- `parseToolInteger` (`:1-22`) rejects `1_000` (`BigInt.tryParse` fails on `_`) and
  rejects `0x_FF` → both **valid Rust**.
- `IntegerWord` (`:38`) throws for widths outside `{8,16,32,64}` → no `i128/u128/usize`.
- Shift handling (`:66-70`) throws "移位量必须在 0 到 N-1 之间" instead of modelling
  `wrapping_shl` masking vs `checked_shl` → `None`.
- No division/modulo, no `as` casts, no `pow`, no suffix parsing.

Reusable *ideas*: the `IntegerWord` pattern/signed/`mask` triple and the
`%`/panic-free design. Reuse the `AsciiCharacter` idea separately (see §3) but note
Rust `'\x7F'` is the maximum hex escape for `char`/`str`, unlike C's arbitrary bytes.

## 3. Tool family B — Rust string literals, raw escaping, UTF-8

### 3.1 Rules the tool must implement (both directions: text → literal, literal → value)

1. **Escapes legal in `"..."`**: `\n \r \t \\ \0 \' \"`, plus
   - `\xNN`: **must be ≤ 0x7F inside `str`/`char`** (otherwise rustc E0786-style
     "out of range hex escape"). Full `0x00–0xFF` is only legal inside `b"..."`.
   - `\u{...}`: 1–6 hex digits, no `+`/`_`, value ≤ `0x10FFFF`, **surrogates
     D800–DFFF rejected**, encodes as UTF-8.
   - `\` + newline: strips the newline and leading whitespace **[VERIFY-WITH-RUSTC for
     the exact whitespace-strip rule]**.
2. **Raw strings**: `r"…"`, `r#"…"#` … up to 255 `#`; no escapes at all; may span
   lines; content may not contain `"` followed by exactly that many `#`; `\` is
   literal. Byte variants `b"…"`, `br"…"`, `br#"…"#`.
3. **char literals**: exactly one Unicode scalar; `'a'`, `'\''`, `'\u{1F600}'`,
   `'\x7F'` max; a surrogate is not a `char`.
4. **Byte-length vs char-count vs UTF-16 units** are three different numbers and the
   tool must show all three: `"é"` → 2 / 1 / 1; `"😀"` → 4 / 1 / 2;
   `"你好, Rust"` per `rust-tutorial-018`. std has **no grapheme cluster API** — do
   not claim grapheme counts.
5. **Do not silently normalize**: Rust `str` forbids unpaired surrogates; Dart
   `String` is UTF-16 and *can* hold them, and `utf8.encode` replaces them with
   U+FFFD. Detect `codeUnits` in D800–DFFF outside a valid pair and return an
   explicit error ("该文本含孤立代理项，无法表示为合法 Rust 字符串") instead of
   emitting a corrupt literal. Iterate `runes` for code points, never `codeUnits`.
6. Lossless round-trip requirement: the encode form must re-decode to the identical
   code-point sequence (property to assert in tests). Prefer the shortest
   escaping: printable ASCII verbatim, `\"` `\\` `\n` `\r` `\t` `\0` for those,
   `\u{7F}`/`\u{…}` for other controls (Rust `str` accepts non-ASCII verbatim), and
   offer a raw-string form when it is lossless and shorter (mirrors Lua's
   `LuaStringLiteral.encode/longBracket` design in
   `../qfli_lua/lib/lua_tools.dart:233-300`, which is the best in-repo template for a
   bidirectional literal tool — but its escape set and `\u{...}` semantics are Lua's,
   not Rust's).
7. **[VERIFY-WITH-RUSTC]** CRLF inside a literal (raw and non-raw): whether rustc
   keeps `\r\n` or normalizes to `\n` in the literal value. Do not assert either
   until tested; until then the tool should preserve bytes and say nothing.

### 3.2 Relationship to the shared common tools (no duplicate feature)

`commonTools` already ships `UnicodeToolPage` (`字符/Unicode`, single character →
code point, `\uXXXX`, UTF-8/UTF-16 hex) and `Base64`/`Hash`. The Rust tool must be
clearly different in purpose: **whole-string Rust-literal authoring/parsing**
(multi-character, raw/byte/char forms, escapes validity, lengths). Label/description
must say so (e.g. "Rust 字符串字面量：转义、raw 字符串、字节长度") so the two cards
don't read as duplicates in the same tab. Keep both visible (§1.2 shape A).

## 4. Tool family C — local Cargo target/project inspection via the existing resolver

### 4.1 Use the resolver as the single decode boundary

- `decodeCargoTargets(metadataJson)` (`lib/cargo_targets.dart:104`) is a **pure**
  function over `cargo metadata --no-deps --format-version 1` text. Then
  `selectCargoTarget(targets:, entryFile:)` (`:243`) and the two message builders
  (`:266`,`:275`), plus `cargoRunArguments(manifestPath, target)` (`:283`) to show the
  exact `cargo run --manifest-path … --package … --bin|--example …` the Run button
  will spawn.
- Never infer targets from file names (spec `rust-run-controls.md` §3: "Cargo
  supplies target/package names; do not derive them from basenames").
- Four outcomes must stay distinguishable in the UI — `Unregistered` (standalone
  rustc), `NotRunnable` (library/test/bench/build script/library-shaped example),
  `Ambiguous` (two runnable owners), and malformed metadata (`FormatException`,
  `:112-120`). Malformed metadata must never render as "无目标".

### 4.2 Device reality and the unavailability contract

`cargo` does not exist on OHOS/Android (`rust_runner.dart` only shells out on
desktop; `rust_terminal_commands.dart:46` gates on `rust/cargo` availability). So:

- Preferred shape: **paste/read metadata JSON** → pure decode + inspection
  (works identically on device and desktop, no process, no network).
- Optional desktop extra: run `cargo metadata` itself, but only by mirroring
  `rust-run-controls.md` (prepend `--offline`, set `CARGO_NET_OFFLINE=true`, bounded
  timeout, capture stdout privately). **Do not** spawn Cargo on mobile, and never
  show a fabricated target list when metadata is unavailable — the truthful state is
  "本机没有 cargo，无法解析自动发现的目标；可粘贴 cargo metadata 输出，或查看
  Cargo.toml 的显式声明".
- Static `Cargo.toml` reading (from `store.projects`, `ProjectStore.projects`
  is recency-sorted, `Project.isCloud` must be skipped) may show `[package]
  name/edition`, explicit `[[bin]]`/`[[example]]` `name`+`path`, `default-run`, and
  `[workspace] members`. It must label auto-discovered `src/bin/*.rs` sources as
  "Cargo 自动发现，需以 cargo metadata 为准" and must not claim runnability.
  `default-run` never overrides `entryFile` (spec §3: entryFile is authoritative).

### 4.3 Shipped content gives real, non-synthetic cases (use them in tests)

| Example | Cargo shape | What the tool must show |
| --- | --- | --- |
| `rust-example-112` | `Cargo.toml` + `src/lib.rs` + `src/main.rs`, pkg `csv_min` | 2 targets; `lib` → NotRunnable, `main` → runnable `--bin`, `cargoVerify: test` |
| `rust-example-106` | pkg `prime_app`, `default-run`, explicit `[[bin]] name="thin" path="bin/thin.rs"` | target name comes from `[[bin]]` (not from `bin/thin.rs`); `default-run` ≠ entryFile authority |
| `rust-example-007` | `[workspace] members=[crates/mathlib, crates/cli]` + root `[[bin]] path="src/main.rs"` | multi-package; same `src/main.rs` owned only by the root package; `--package` disambiguates a reused target name |
| `rust-example-151` | `[workspace] members=["macros"]` + path dependency | member `lib` target is NotRunnable; root bin runnable |

Path matching is `p.absolute` + `p.normalize` + `p.equals` (`cargo_targets.dart:243-250`),
so the UI must accept entry paths in either separator/case form and must not
string-compare. Existing coverage to not regress: `test/cargo_targets_test.dart`
(14 tests incl. "matching is path-canonical, not string-equal", ambiguous, lib-shaped example).

## 5. Narrow / 2× layout regressions the implementer must cover

Measured anchors: `ToolsTheme.horizontalPadding` = 16/24/32 at <600/≥600/≥1200
(`tool_widgets.dart:12-14`); `cardMaxWidth 320`, `cardHeight 132`, `cardSpacing 12`,
`cardPadding 16`, `contentMaxWidth 1000`; `ToolsGridSliver` reserves
`cardHeight + extra(title 1 line + 2 body lines)` from `MediaQuery.textScalerOf`
(`tools_grid.dart:154-195`).

1. **`ResultRow` has a hard `width: 104` label column** (`tool_widgets.dart:186`).
   At 320 dp × 2.0 scale, `labelMedium` ≈ 24 px ⇒ ~4 CJK glyphs fit. Labels must be
   ≤ 4 CJK chars ("u128 上界" is borderline) or the row must not use `ResultRow`.
   Long values (u128 = 39 digits, `0x`+32 hex) land in `Expanded(SelectableText)` and
   wrap — acceptable, but assert **no `RenderFlex` exception** and that the copy
   button remains hit-testable.
2. **Do not build `Row(children: [label, Expanded(TextField), IconButton])`** for
   inline panels. At 320 × 2.0 that Row's fixed children exceed the width. Use
   `LayoutBuilder` with a stacked branch when
   `constraints.maxWidth < ~420 * (textScaler.scale(16)/16)`, or `Wrap`.
3. **Chip/segmented groups must be `Wrap`**, never `Row` (`普通/checked/wrapping/
   overflowing/saturating` × `i8…u128` selectors overflow immediately).
4. **Shift/index operands and hex dumps** must not use fixed `SizedBox(width: 200)`;
   horizontal overflow guards (`SingleChildScrollView(scrollDirection: horizontal)`
   or soft-wrap `SelectableText`).
5. **No nested `Scaffold`/`AppBar`/`TabBar`** inside `toolsTabBuilder` (host provides
   them; `FunctionsTab` already wraps in a `Scaffold`, `quick_tools_page.dart:40-56`).
   C's `ForgeToolsBody` is correct on this point; assert
   `find.byType(Scaffold), findsOneWidget` + `findsNothing` for `TabBar`/`TabBarView`.
6. **Scroll identity/state**: give the body a stable `PageStorageKey`
   (`tools_grid.dart:125` uses `'tools-scroll'`; SQL uses `'sql-tools-scroll'`) so
   scroll offset survives tab switches. Controllers inside inline panels must live in
   `StatefulWidget`s; if `FunctionsTab`'s `PageView` disposes them, use
   `AutomaticKeepAliveClientMixin` — verify by entering text, switching tabs, and
   re-reading the controller in a widget test.
7. **Keyboard on device**: inline `TextField`s near the bottom nav must stay reachable
   (`Scrollable.ensureVisible` after focus); the C test harness already wraps
   `show(target)` with `ensureVisible` — reuse that helper shape.
8. **Text-scale card heights**: if any Rust-specific card goes through
   `ToolCard`, description > 2 lines is ellipsized (not an overflow) but loses
   information; keep descriptions ≤ ~2 lines at 2× (≈24 CJK chars at 320 dp).
9. Required matrix for widget tests, mirroring `../qfli_c/test/forge_tools_test.dart:131-138`:
   `(320, 1.0)`, `(1024, 1.0)`, `(320, 2.0)`, `(1024, 2.0)`, each ending with
   `expect(tester.takeException(), isNull)`, plus a live re-layout resize
   (`320 ↔ 1024`) asserting controllers keep their text and results stay identical
   (C does exactly this at `:283-310`).
10. Light/dark: core asserts reachability in both brightnesses
    (`qfli_studio_core/test/tools_grid_test.dart:125+`); Rust panels should not
    hard-code colours — use `ColorScheme` like `ToolsTheme.cardDecoration`.

## 6. Test plan this reviewer expects (names + what they must prove)

Pure-logic tests (new `test/rust_tools_test.dart`, no widgets):
- literal accept/reject table: `0x_FF` ✔, `0x_` ✘, `1_000` ✔, `1__2` ✔, `0xFFu8` ✔,
  `0xFFi8` ✘ (out of range), `1u8x` ✘, `340282366920938463463374607431768211455u128`
  ✔, `…456u128` ✘, `i8::MIN` bounds, `usize` 32 vs 64 assumption.
- mode table: every row of §2.3, incl. panics for `MIN/-1`, `/0`, `%0`, and
  `checked_div → None`, `wrapping_rem → 0`.
- `as`-cast table: `300i32 as u8 == 44`, `-1i32 as u128 == u128::MAX`,
  `u128::MAX as i32 == -1`, float→int saturation/NaN = 0.
- string: encode→decode round trip over ASCII/CJK/emoji/NUL/control/quotes/backslash;
  `\xFF` rejected inside `str` but accepted inside `b""`; `\u{D800}` rejected;
  lone surrogate Dart input → explicit error; lengths (`bytes/chars/utf16`) for
  `"é"`, `"😀"`, `"你好, Rust"`; raw-string delimiter selection (`r#"…"#` when text
  contains `"`) and the "cannot be represented" case.
- Cargo: feed the four real bundles' `Cargo.toml`/metadata fixtures (§4.3) and assert
  the four `CargoTargetLookup` outcomes and the exact `cargoRunArguments` list;
  malformed JSON → error text, never "无目标".

Widget tests (new `test/rust_tools_page_test.dart`): §5 matrix + terminal callback
invoked once + `Scaffold`/`AppBar` uniqueness + shared `commonTools` titles still
present (9 titles) + no `TabBar` + per-tool result text visible at 320×2.0.

**[VERIFY-WITH-RUSTC] must be resolved (or the UI copy softened) before merging:
`1_` / `1_u8` acceptance, `-128i8` vs `-128`, release-mode `<<` masking, `\`-newline
whitespace stripping, CRLF inside literals.** Cheapest route once a toolchain exists:
`python scripts/verify_rust_content.py --rustc <path>` semantics for the general
toolchain, and one-off `rustc --edition=2021 - --emit=metadata` snippets for each
item; optionally run the same snippets through the packaged native runner so device
and tool agree.

## 7. Recommendation summary and open blockers

- Implement shape **A** (§1.2): one `CustomScrollView` body — 快捷入口 (终端 card),
  Rust sections (int literals/bit ops, string/UTF-8, Cargo targets), then the shared
  `commonTools` via `ToolsGridSliver`, then the offline note. No new Scaffold, no hub page.
- New files (worker-owned): `lib/rust_integer_tools.dart` (pure semantics),
  `lib/rust_string_literals.dart` (pure semantics), `lib/rust_cargo_inspector.dart`
  (thin wrapper over `lib/cargo_targets.dart`), `lib/rust_tools_page.dart`
  (`buildRustToolsTab`), plus the two test files.
- Blockers: **B1** profile wiring is root-owned (`lib/main.dart`) — R4 stays red until
  root lands the one line; **B2** composition choice must be recorded against the
  `StudioProfile.toolsTabBuilder` doc contract ("Return a ToolsGrid…") which shapes A
  and the C/SQL/Dart precedents all violate — either follow `ToolsGrid` (B) or get the
  contract text updated by its owner; **B3** `_OfflineNote` is private so shape A must
  duplicate one sentence; **B4** no host `rustc`, so §6's VERIFY items cannot be
  closed on this machine and no UI copy may assert them yet.
