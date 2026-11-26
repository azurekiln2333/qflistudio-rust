# Direct offline Rust tools

## 1. Scope / Trigger

Apply to RustToolsTab, rust_tool_utilities.dart and StudioProfile.toolsTabBuilder.
The shared application owns the tools Scaffold and common tools.

## 2. Signatures

```dart
RustToolsTab({required ProjectStore store, required VoidCallback onOpenTerminal,
  RustProjectInspector Function()? inspectorFactory});
RustIntegerLiteral parseRustInteger(String input);
RustIntegerView({required BigInt value, required String type, int pointerWidth = 64});
```

Keep the complete parser/inspector contracts in rust_tool_utilities.dart.

## 3. Contracts

Place useful Rust tool sections directly on the tools page, retain common tools
and the terminal action, and avoid a nested Scaffold or secondary Rust hub.
Wide integers use BigInt; signed wrapping and endian bytes reflect the chosen
width, with explicit32/64 usize assumptions. Rust literal/UTF8 inspection preserves
Unicode. Local Cargo inspection uses real offline metadata and the existing target
decoder, never runs builds/scripts/downloads and never modifies project source.
Changing project selection invalidates stale asynchronous inspection results.

## 4. Validation & Error Matrix

| Condition | Required result |
| --- | --- |
| Invalid/oversized literal or scalar escape | Clear inline error |
| Outside selected integer type | Show exact bounds/bit representation |
| Missing desktop Cargo | Explicit unavailable metadata result |
| Mobile without Cargo CLI | Useful local manifest result, no invented target data |
| Project changes during inspection | Ignore stale result |

## 5. Good / Base / Bad Cases

Good: u128 maximum stays exact and emits16 bytes. Base: UTF8 inspection displays
the bytes of CJK and non-BMP text. Bad: converting u128 through double or hiding
the new sections behind another route.

## 6. Tests Required

Run rust_tool_utilities_test and rust_tools_tab_test. Cover wide integer math,
literal round trips, real Cargo metadata with a nonexecuted build.rs, responsive
widgets and common-tool/terminal navigation. Scroll lazy sections into view
before interacting; offscreen lazy content is not a failed tool action.

## 7. Wrong vs Correct

Wrong: use floating-point parsing for a Rust128-bit integer.
Correct: keep BigInt throughout parsing, bounds, wrapping and byte conversion.
