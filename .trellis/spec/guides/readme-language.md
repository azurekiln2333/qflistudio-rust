# README language contract

The root README set has three equivalent editions:

- `README.md`: Simplified Chinese, the default edition.
- `README.zh-TW.md`: Traditional Chinese.
- `README.en.md`: English.

Each edition links to all three editions. Keep feature status, platform limits,
commands, catalog counts, dependency paths and evidence boundaries equivalent.
Source code and current validation reports determine factual claims. A host test
or unsigned package does not establish OHOS installation or device execution.
Do not describe a source-only debugger as a validated production feature.

Chinese technical prose uses one action per sentence and active voice. Use one
term for each concept throughout an edition. Instructions contain at most 25
characters and explanations at most 40. Do not join actions with semicolons.
Remove nominalized actions, stock phrases, marketing claims and vague words.
Retain modal words such as 可能 and 也许: they express confidence.

Run the mechanical check first:

```text
python scripts/ste-lint-zh.py README.md README.zh-TW.md
```

Resolve findings without disabling rules or raising the baseline. Review
instructions separately against the 25-character limit. The linter mainly
recognizes Simplified Chinese phrases, so manually review Traditional Chinese
for the equivalent prohibited phrases, term consistency and action count.
A clean linter result alone does not establish compliance.

Review all relative Markdown links and compare the command blocks across
editions. For a documentation-only change, inspect commands against their actual
scripts without starting native builds, SDK tests or device runs.
