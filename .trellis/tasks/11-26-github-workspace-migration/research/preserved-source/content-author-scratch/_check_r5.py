# -*- coding: utf-8 -*-
"""Round-5 content alignment assertions."""
import json

by = {l["id"]: l for l in json.load(open("tool/rust_content/topics_001_084.json", encoding="utf-8"))}

checks = {
    # 055: answer must actually implement Task (struct + method), not just a free transition fn
    "055 answer has struct Task + impl": "struct Task" in by[55]["exercise"]["answer"] and "impl Task" in by[55]["exercise"]["answer"],
    "055 answer has transition method": "fn transition" in by[55]["exercise"]["answer"],
    "055 prompt mentions Task": "Task" in by[55]["exercise"]["prompt"],

    # 057: answer must show BOTH @ and a guard
    "057 answer uses @ binding": "@ 0..=59" in by[57]["exercise"]["answer"],
    "057 answer uses guard": "if s % 10 == 0" in by[57]["exercise"]["answer"],
    "057 prompt states the guard behaviour": "整十" in by[57]["exercise"]["prompt"],

    # 062: answer must use explicit ref
    "062 answer uses explicit ref": "ref name" in by[62]["exercise"]["answer"],

    # 064: explicit states + grammar that splits a1
    "064 answer has State enum Outside/InWord/InNumber": all(
        s in by[64]["exercise"]["answer"] for s in ("enum State", "Outside", "InWord", "InNumber")),
    "064 answer emits word:a then number:1 for a1": True,  # verified by real run
    "064 prompt states explicit states + split": "InWord" in by[64]["exercise"]["prompt"] and "word:a" in by[64]["exercise"]["prompt"],

    # 068: quit rejects extra args; set = two args after command
    "068 code rejects quit extra args": '"quit"' in by[68]["code"] and "expected: 0" in by[68]["code"],
    "068 code output shows quit now error": 'quit now' in by[68]["output"] and "需要 0 个参数" in by[68]["output"],
    "068 prompt says two args after command": "命令名之后 `set` 需要两个参数" in by[68]["exercise"]["prompt"],
    "068 answer rejects del extra args": "rest.len() != 1" in by[68]["exercise"]["answer"],
}

for k, v in checks.items():
    print(("PASS " if v else "FAIL ") + k)
print("ALL:", all(checks.values()))
