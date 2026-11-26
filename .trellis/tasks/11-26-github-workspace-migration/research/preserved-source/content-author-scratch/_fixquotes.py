# -*- coding: utf-8 -*-
"""Remove duplicated closing quotes from JSON string value lines."""
import io
import re

PATHS = [
    "build/content-author-scratch/_a1.py", "build/content-author-scratch/_a2.py",
    "build/content-author-scratch/_b1.py", "build/content-author-scratch/_b2.py",
    "build/content-author-scratch/_c1.py", "build/content-author-scratch/_c2.py",
    "build/content-author-scratch/_c3.py", "build/content-author-scratch/_d1.py",
    "build/content-author-scratch/_d2.py", "build/content-author-scratch/_e1.py",
    "build/content-author-scratch/_e2.py",
]
FIELD_RE = re.compile(r'^\s*"([a-zA-Z]+)": "')


def fix_line(line):
    s = line.rstrip()
    if not FIELD_RE.match(s):
        return line
    if s.endswith('"",'):
        return s[:-3] + '",'
    if s.endswith('""'):
        return s[:-2] + '"'
    return line


for path in PATHS:
    with io.open(path, encoding="utf-8") as fh:
        lines = fh.read().split("\n")
    n = 0
    for i, ln in enumerate(lines):
        new = fix_line(ln)
        if new != ln:
            lines[i] = new
            n += 1
    if n:
        with io.open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
    print(path, "fixed", n)
