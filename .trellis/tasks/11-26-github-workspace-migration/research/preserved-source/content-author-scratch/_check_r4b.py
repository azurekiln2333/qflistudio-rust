# -*- coding: utf-8 -*-
"""Targeted assertion of the round-4 completion fixes (079 code, 081 comment, 048)."""
import json

by = {l["id"]: l for l in json.load(open("tool/rust_content/topics_001_084.json", encoding="utf-8"))}

checks = {
    "079 code lossless UserId(String)": "UserId(String)" in by[79]["code"] and "value.len()" not in by[79]["code"],
    "079 code asserts same-length distinct": "assert_ne!" in by[79]["code"] and "\"abcd\"" in by[79]["code"] and "\"wxyz\"" in by[79]["code"],
    "079 output x==y false": "x == y: false" in by[79]["output"],
    "079 output no UserId(4)": "UserId(4)" not in by[79]["output"],
    "079 explain lossless": "真正无损" in by[79]["explain"],
    "079 answer lossless": "From<String>" in by[79]["exercise"]["answer"],
    "081 answer no reflexive claim": "自反、对称、传递" not in by[81]["exercise"]["answer"],
    "081 answer documents symmetry+transitivity": "对称性 + 传递性" in by[81]["exercise"]["answer"],
    "048 take needs Default (first sentence)": "`take` 需要 `T: Default`" in by[48]["explain"],
    "048 first sentence corrected": by[48]["explain"].index("set`/`replace`/`into_inner`") < by[48]["explain"].index("`get` 要求"),
}

for k, v in checks.items():
    print(("PASS " if v else "FAIL ") + k)
print("ALL:", all(checks.values()))
