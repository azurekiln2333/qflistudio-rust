# -*- coding: utf-8 -*-
"""Round-6 exact-defect fixes: 057 answer (F 整十) and 068 answer (Quit)."""

import io
import json
import os

HERE = os.path.join(os.path.abspath("."), "build", "content-author-scratch")


def read_draft(name):
    with io.open(os.path.join(HERE, name), encoding="utf-8") as fh:
        return fh.read()


NEW_057_ANSWER = read_draft("_r6_057.rs")
NEW_068_ANSWER = read_draft("_r6_068_answer.rs")


def replace_json_string(src, field, new_value, anchor):
    start = src.index(anchor)
    key = '"' + field + '": "'
    ks = src.index(key, start)
    vs = ks + len(key)
    i = vs
    while True:
        if src[i] == "\\":
            i += 2
            continue
        if src[i] == '"':
            break
        i += 1
    return src[:ks] + key + json.dumps(new_value, ensure_ascii=False)[1:-1] + src[i:]


def main():
    p = os.path.join(HERE, "_d1.py")
    src = io.open(p, encoding="utf-8").read()
    src = replace_json_string(src, "answer", NEW_057_ANSWER, '"id": 57,')
    io.open(p, "w", encoding="utf-8").write(src)
    print("057 answer fixed (F 整十 branch + asserts)")

    p = os.path.join(HERE, "_d2.py")
    src = io.open(p, encoding="utf-8").read()
    src = replace_json_string(src, "answer", NEW_068_ANSWER, '"id": 68,')
    io.open(p, "w", encoding="utf-8").write(src)
    print("068 answer fixed (Quit variant + zero-arg success/error + asserts)")


if __name__ == "__main__":
    main()
