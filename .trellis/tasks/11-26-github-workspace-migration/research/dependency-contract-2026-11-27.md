# Consumer dependency correction

The core owner and independent source inspection confirmed the consumer contract
at core `476a30acee21dc486ee2849dd8064a7be665e4d5` on 2026-11-27. The root
consumer must override both `re_editor` and `xterm` to the pinned sibling core's
`vendor` directories. Dependency overrides inside core are not inherited.

Core source identities reported by the dependency reviewer:

| Source | Git object |
| --- | --- |
| Core pubspec | `66fbd3089c1c915659782d84cb5f3eb979b25cba` |
| Core lockfile | `54d498ab61eeb9e801e3f6c4ec9142d44007467e` |
| Vendored xterm tree | `6d835af4db19464ae682bc9c779d931341609af2` |
| xterm utils export | `c0c877cc802ae817929be664f604aad31c7686b4` |
| UnicodeV11 implementation | `fd95ba0b8f1031edb13fcf052df13ac179315fd7` |
| Shortcut platform switch | `8efa83d79372f4ab2c532ca28128a69d0cd6955a` |

The vendored implementation supplies `int wcwidth(int)` and the custom-platform
shortcut case. Rust installer run `45966800141` instead compiled registry
`xterm-4.0.0`, explaining its UnicodeV11 and OHOS switch errors. No core cast,
SDK replacement or old tooling override is part of this correction.

The first source correction adds the root override and exact path lock row,
checks all three core/vendor paths before and after restoration, and records
resolved roots and lock/config hashes. It deliberately leaves the remaining
resolver additions for review from a fresh hosted diagnostic. Quality retains
both its selected-input hashes and whole tracked-tree cleanliness requirements.
Bounded diagnostics expose only known dependency/registration source diffs;
other changed files receive path/hash evidence only.

The 17:00 core-last ruling holds this core pin through consumer migration. A
later brain-coordinated `CORE_REF` bump follows final core publication. Actual
hosted format, analysis and full root tests remain required. Source inspection
and authored helper regressions do not establish those passes. No local checks,
dependency restoration or artifact downloads were performed for this correction.
