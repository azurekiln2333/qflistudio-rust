# Implementation Plan

1. Replace the placeholder Rust backend with Cargo and rustc execution, stream forwarding, temporary output management, and cancellation.
2. Update existing backend tests to assert actual execution and failure behavior; keep profile and entry-routing tests.
3. Run Dart formatting, Flutter analyze, and Flutter tests. Exercise real Rust compilation when the toolchain is available.
4. Review the diff for unrelated files and commit the completed batch with a conventional message.
