"""Cross-check the Dart SHA-256 transcription in lib/rust_native_catalog.dart.

The device harness re-verifies every authored digest in Dart so a report can
never describe bytes it did not run. Flutter tests are serialized by the root
owner, so this script proves the *algorithm* independently: it transcribes the
same constant tables and the same step flow from the Dart source and compares
against hashlib over the real catalog payloads.

This is a check on the algorithm, not a substitute for running the Dart test.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[4]
DART = ROOT / "lib/rust_native_catalog.dart"
MASK = 0xFFFFFFFF


def rotl_free_rotr(value: int, bits: int) -> int:
    value &= MASK
    return ((value >> bits) | (value << (32 - bits))) & MASK


def tables_from_dart(source: str) -> tuple[list[int], list[int]]:
    k_block = re.search(r"const k = <int>\[(.*?)\];", source, re.S)
    h_block = re.search(r"final hash = <int>\[(.*?)\];", source, re.S)
    if not k_block or not h_block:
        raise SystemExit("could not locate the SHA-256 tables in the Dart source")
    k = [int(value, 16) for value in re.findall(r"0x[0-9a-fA-F]+", k_block.group(1))]
    h = [int(value, 16) for value in re.findall(r"0x[0-9a-fA-F]+", h_block.group(1))]
    if len(k) != 64 or len(h) != 8:
        raise SystemExit(f"unexpected table sizes: k={len(k)} hash={len(h)}")
    return k, h


def sha256_k(k: list[int], initial: list[int], data: bytes) -> bytes:
    """Port of the Dart implementation: same padding, same message schedule."""
    h = list(initial)
    padded = bytearray(data)
    padded.append(0x80)
    while len(padded) % 64 != 56:
        padded.append(0)
    # SHA-256 stores the *message* bit length, matching Dart's
    # `final bitLength = bytes.length * 8`.
    padded += (len(data) * 8).to_bytes(8, "big")

    w = [0] * 64
    for offset in range(0, len(padded), 64):
        for index in range(16):
            base = offset + index * 4
            w[index] = (
                (padded[base] << 24)
                | (padded[base + 1] << 16)
                | (padded[base + 2] << 8)
                | padded[base + 3]
            )
        for index in range(16, 64):
            s0 = rotl_free_rotr(w[index - 15], 7) ^ rotl_free_rotr(w[index - 15], 18) ^ (w[index - 15] >> 3)
            s1 = rotl_free_rotr(w[index - 2], 17) ^ rotl_free_rotr(w[index - 2], 19) ^ (w[index - 2] >> 10)
            w[index] = (w[index - 16] + s0 + w[index - 7] + s1) & MASK
        a, b, c, d, e, f, g, hh = h
        for index in range(64):
            s1 = rotl_free_rotr(e, 6) ^ rotl_free_rotr(e, 11) ^ rotl_free_rotr(e, 25)
            ch = (e & f) ^ (~e & g)
            temp1 = (hh + s1 + ch + k[index] + w[index]) & MASK
            s0 = rotl_free_rotr(a, 2) ^ rotl_free_rotr(a, 13) ^ rotl_free_rotr(a, 22)
            maj = (a & b) ^ (a & c) ^ (b & c)
            temp2 = (s0 + maj) & MASK
            hh, g, f, e = g, f, e, (d + temp1) & MASK
            d, c, b, a = c, b, a, (temp1 + temp2) & MASK
        h = [(current + new) & MASK for current, new in zip(h, (a, b, c, d, e, f, g, hh))]
    return b"".join(value.to_bytes(4, "big") for value in h)


def main() -> int:
    source = DART.read_text(encoding="utf-8")
    k, initial = tables_from_dart(source)

    samples = [
        b"",
        b"abc",
        b"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq",
        b"a" * 200,
        "\u4e2d\u6587".encode("utf-8"),
        b"a" * 55,
        b"a" * 56,
        b"a" * 64,
        b"a" * 65,
    ]
    failures = []
    for sample in samples:
        expected = hashlib.sha256(sample).hexdigest()
        actual = sha256_k(k, initial, sample).hex()
        if actual != expected:
            failures.append((sample[:20], expected, actual))

    catalog_path = ROOT / "assets/content_rust/native_catalog.json"
    document = json.loads(catalog_path.read_text(encoding="utf-8"))
    checked = 0
    for case in document["cases"]:
        payload = case["source"].encode("utf-8")
        actual = sha256_k(k, initial, payload).hex()
        expected = hashlib.sha256(payload).hexdigest()
        if actual != expected or actual != case["sourceSha256"]:
            failures.append((case["id"], expected, actual))
        checked += 1
        for name, text in (case["files"] or {}).items():
            payload = text.encode("utf-8")
            actual = sha256_k(k, initial, payload).hex()
            expected = hashlib.sha256(payload).hexdigest()
            if actual != expected or actual != case["filesSha256"][name]:
                failures.append((f"{case['id']}:{name}", expected, actual))
            checked += 1

    if failures:
        for item in failures[:10]:
            print("MISMATCH", item, file=sys.stderr)
        print(f"{len(failures)} digest mismatches", file=sys.stderr)
        return 1
    print(
        f"sha256 transcription matches hashlib for {len(samples)} samples "
        f"and {checked} catalog payloads"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
