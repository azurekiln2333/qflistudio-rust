# -*- coding: utf-8 -*-
"""Lessons 015..023 (Domain B, part 1)."""

LESSONS = [
{
    "id": 15,
    "title": "标量与字面量：整数溢出、`as` 转换",
    "level": "beginner",
    "domain": "syntax-types",
    "summary": "认识整数、浮点、布尔、字符四类标量，理解默认类型、溢出行为与安全转换方式。",
    "concepts": ["整数类型", "字面量后缀", "溢出", "as 转换", "checked_*"],
    "objective": "能根据取值范围选择整数类型，并解释 debug 与 release 下溢出的不同表现。",
    "prerequisites": ["002"],
    "explain": "Rust 的标量有整数（i8..i128、u8..u128、isize/usize）、浮点（f32/f64）、bool 和 char。整数字面量默认推断为 i32，浮点默认 f64；可加后缀 `10u8`、`1.5f32`。溢出在 debug 构建会 panic，在 release 构建会按二进制补码回绕——这种档位差异意味着不能依赖回绕做逻辑。要安全处理，用 `checked_add`（返回 Option）、`wrapping_add`（显式回绕）、`saturating_add`（截断到边界）、`overflowing_add`（返回值+溢出标志）。`as` 是做“可能损失信息”的转换，但**整数/布尔的数值转换本身是安全的、不会 UB**，其行为由语言规定。整数从宽到窄会按二进制补码截断高位（如 `300_i32 as u8 == 44`）。浮点转整数自 Rust 1.45 起是**饱和**的：超出目标范围会取该类型的最小/最大值（`f64::NAN as u8 == 0`，`1e30_f64 as i32 == i32::MAX`，`-1e30 as i32 == i32::MIN`），而不会像 C 那样未定义。浮点到浮点则是**按 IEEE 754 就近舍入**（不是饱和）：f64 转 f32 在超出 f32 范围时会得到正/负无穷（如 `f64::MAX as f32 == f32::INFINITY`），NaN 仍是 NaN，并未“截断到边界”。由于 `as` 会静默丢信息，关键转换应优先用 `try_from`/`try_into` 并在失败时显式处理。字符（`char`）是 4 字节的 Unicode 标量值，不是字节。",
    "code": "fn main() {\n    let a: u8 = 250;\n    println!(\"a = {}\", a);\n    println!(\"checked_add(10)    = {:?}\", a.checked_add(10));\n    println!(\"wrapping_add(10)   = {}\", a.wrapping_add(10));\n    println!(\"saturating_add(10) = {}\", a.saturating_add(10));\n\n    let big: i32 = 300;\n    let narrowed = big as u8;\n    println!(\"300 as u8 = {}\", narrowed);\n\n    let f = 3.9_f64;\n    println!(\"3.9 as i32 = {}\", f as i32);\n    println!(\"try_into 3.9 -> {:?}\", u8::try_from(300).is_err());\n}\n",
    "output": "a = 250\nchecked_add(10)    = None\nwrapping_add(10)   = 4\nsaturating_add(10) = 255\n300 as u8 = 44\n3.9 as i32 = 3\ntry_into 3.9 -> true\n",
    "pitfalls": [
        "依赖释放版本的回绕：debug 会 panic、release 会回绕，行为不一致导致隐性 bug。",
        "用 `as` 做宽到窄转换：高位被静默截断（300 as u8 == 44），关键路径应使用 `try_from`。",
        "以为 char 是 1 字节：它是 4 字节 Unicode 标量，按字节处理字符串要用 `as_bytes()`。"
    ],
    "exercise": {
        "prompt": "写函数 `safe_mul(a: u32, b: u32) -> Option<u32>` 用 `checked_mul` 返回乘积，并在 main 中演示不溢出与溢出两种情况。",
        "hint": "`a.checked_mul(b)` 直接返回 Option<u32>。",
        "answer": "fn safe_mul(a: u32, b: u32) -> Option<u32> {\n    a.checked_mul(b)\n}\n\nfn main() {\n    println!(\"{:?}\", safe_mul(1000, 1000));\n    println!(\"{:?}\", safe_mul(100_000, 100_000));\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 16,
    "title": "元组、数组与解构",
    "level": "beginner",
    "domain": "syntax-types",
    "summary": "用元组打包异构值、用数组表达定长同构序列，并练习多路解构与忽略元素。",
    "concepts": ["元组", "数组 [T; N]", "解构", ".. 忽略", "索引"],
    "objective": "能按需选择元组或数组，并用模式解构一次性取出多个字段。",
    "prerequisites": ["015"],
    "explain": "元组 `(T1, T2, ...)` 是异构定长组合，元素类型可不同，用 `.0`、`.1` 访问；数组 `[T; N]` 是同构定长序列，长度是类型的一部分，用下标访问。两者都是值类型，赋值或传参时默认发生复制（若元素实现 Copy）或移动。解构是最常用的技巧：`let (x, y) = pair;` 一次取出多个字段；`let [first, .., last] = arr;` 取首尾；`_` 忽略不关心的位置。元组可作为函数多返回值（例如 `(bool, usize)`），比定义临时结构体轻量，但字段过多会失去可读性，此时应改用结构体。数组长度可在编译期通过 `arr.len()` 与常量查询，越界下标会 panic——这对桌面程序是安全网，但也要在可预期输入下避免。",
    "code": "fn min_max(xs: &[i32]) -> (i32, i32) {\n    let mut lo = xs[0];\n    let mut hi = xs[0];\n    for &x in xs {\n        if x < lo { lo = x; }\n        if x > hi { hi = x; }\n    }\n    (lo, hi)\n}\n\nfn main() {\n    let point = (3, 7);\n    let (x, y) = point;\n    println!(\"point = ({}, {})\", x, y);\n\n    let week = [\"一\", \"二\", \"三\", \"四\", \"五\", \"六\", \"日\"];\n    let [first, .., last] = week;\n    println!(\"首日 = {}, 末日 = {}, 长度 = {}\", first, last, week.len());\n\n    let (lo, hi) = min_max(&[4, 1, 9, 2, 8]);\n    println!(\"min = {}, max = {}\", lo, hi);\n}\n",
    "output": "point = (3, 7)\n首日 = 一, 末日 = 日, 长度 = 7\nmin = 1, max = 9\n",
    "pitfalls": [
        "把元组当结构体用：字段过多且靠位置访问时语义不清，应改用命名字段的结构体。",
        "以为数组可以随便增长：`[T; N]` 长度固定，需要动态增长用 `Vec<T>`。",
        "解构时漏掉位置：用 `..` 之后不能再出现同名的具名绑定重复，注意模式参数个数要匹配。"
    ],
    "exercise": {
        "prompt": "写函数 `sum_and_count(xs: &[i32]) -> (i32, usize)` 返回总和与元素个数，并在 main 中解构输出。",
        "hint": "用 `xs.iter().sum()` 与 `xs.len()`，或一次遍历同时累加。",
        "answer": "fn sum_and_count(xs: &[i32]) -> (i32, usize) {\n    (xs.iter().sum(), xs.len())\n}\n\nfn main() {\n    let (sum, count) = sum_and_count(&[10, 20, 30]);\n    println!(\"sum = {}, count = {}\", sum, count);\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 17,
    "title": "切片 `&[T]` 与子切片",
    "level": "beginner",
    "domain": "syntax-types",
    "summary": "用切片引用数组或 Vec 的一段，理解其“胖指针（指针+长度）”本质与区间语法。",
    "concepts": ["&[T]", "胖指针", "区间索引", "split_at", "windows/chunks"],
    "objective": "能写出接收 `&[T]` 的函数，并用区间语法与 split_at 安全地切出子片段。",
    "prerequisites": ["016"],
    "explain": "切片 `&[T]` 是对一段连续同构数据的借用，内部是“指针 + 长度”（胖指针），因此 sizeof 是两个字长、运行时知道边界。任何 `&Vec<T>`、`&[T; N]` 都能通过 Deref 强转为 `&[T]`，所以函数签名接收 `&[T]` 最通用。区间索引 `&xs[a..b]` 取半开区间，越界会在运行时 panic；`split_at(i)` 一次性得到 `(&xs[..i], &xs[i..])`，避免两次索引。`windows(k)` 给出滑动窗口迭代器，`chunks(k)` 给出不重叠分块。切片还支持模式匹配 `let [head, tail @ ..] = xs`。记住切片是借用，不拥有数据；返回切片时其生命周期必须与底层数据绑定。",
    "code": "fn average(xs: &[f64]) -> Option<f64> {\n    if xs.is_empty() {\n        return None;\n    }\n    Some(xs.iter().sum::<f64>() / xs.len() as f64)\n}\n\nfn main() {\n    let data = [1.0, 2.0, 3.0, 4.0, 5.0];\n    let slice: &[f64] = &data;\n    println!(\"average = {:?}\", average(slice));\n\n    let (left, right) = slice.split_at(2);\n    println!(\"left = {:?}\", left);\n    println!(\"right = {:?}\", right);\n\n    let windows: Vec<f64> = slice.windows(2).map(|w| w[0] + w[1]).collect();\n    println!(\"相邻和 = {:?}\", windows);\n\n    let [head, tail @ ..] = slice else { return };\n    println!(\"head = {}, tail_len = {}\", head, tail.len());\n}\n",
    "output": "average = Some(3.0)\nleft = [1.0, 2.0]\nright = [3.0, 4.0, 5.0]\n相邻和 = [3.0, 5.0, 7.0, 9.0]\nhead = 1, tail_len = 4\n",
    "pitfalls": [
        "在函数签名里写 `&Vec<T>`：这限制了调用方，应接收 `&[T]` 以兼容数组与切片。",
        "区间写反导致 panic：`&xs[3..1]` 会 panic，构造前应校验 `start <= end <= len`。",
        "切出子切片后丢弃原数据：切片借用了原数据，原数据必须存活到切片使用结束。"
    ],
    "exercise": {
        "prompt": "写函数 `max_slice(xs: &[i32]) -> Option<i32>` 返回切片最大值，并在 main 中同时用数组和其子切片调用。",
        "hint": "`xs.iter().copied().max()`；子切片用 `&arr[1..4]`。",
        "answer": "fn max_slice(xs: &[i32]) -> Option<i32> {\n    xs.iter().copied().max()\n}\n\nfn main() {\n    let arr = [5, 2, 9, 1, 7];\n    println!(\"{:?}\", max_slice(&arr));\n    println!(\"{:?}\", max_slice(&arr[1..4]));\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 18,
    "title": "字符串 `String` vs `&str`：编码与边界",
    "level": "beginner",
    "domain": "syntax-types",
    "summary": "区分布局字符串（UTF-8 字节）与字符串字面量借用，理解为什么不能按下标取字符。",
    "concepts": ["String", "&str", "UTF-8", "字符边界", "chars 迭代"],
    "objective": "能说明 `String` 与 `&str` 的所有权差异，并用字符迭代而非字节下标处理多字节文本。",
    "prerequisites": ["016"],
    "explain": "`String` 是拥有所有权的可增长 UTF-8 字符串（本质是 `Vec<u8>` + 不变量：始终是合法 UTF-8）；`&str` 是借用的 UTF-8 片段，字符串字面量类型是 `&'static str`。因为 UTF-8 中一个字符可能占 1~4 字节，`s[i]` 不是取字符而是取字节，Rust 直接禁止用整数下标索引字符串，避免截断多字节字符。要遍历字符用 `s.chars()`，遍历字节用 `s.bytes()`，需要按行用 `s.lines()`。`&s[a..b]` 只在 a、b 都落在字符边界时才合法，否则 panic；安全做法是先用 `char_indices()` 找到边界。拼接用 `push_str`/`+`（注意 `+` 左边必须是 String 且会移动它）或 `format!`。`String::from` 与 `.to_string()` 从字面量建拥有型字符串。",
    "code": "fn char_count(text: &str) -> usize {\n    text.chars().count()\n}\n\nfn main() {\n    let owned: String = String::from(\"你好, Rust\");\n    let slice: &str = &owned;\n\n    println!(\"bytes  = {}\", owned.len());\n    println!(\"chars  = {}\", char_count(slice));\n\n    let first_two: String = owned.chars().take(2).collect();\n    println!(\"前两字 = {}\", first_two);\n\n    let mut built = String::new();\n    built.push_str(\"前缀-\");\n    built.push('✓');\n    println!(\"拼接   = {}\", built);\n\n    println!(\"字节下标被禁止, 因为可能截断 UTF-8 字符\");\n}\n",
    "output": "bytes  = 12\nchars  = 8\n前两字 = 你好\n拼接   = 前缀-✓\n字节下标被禁止, 因为可能截断 UTF-8 字符\n",
    "pitfalls": [
        "用 `s[0]` 取字符：字符串不能用整数下标，必须用 `chars()` 或字节迭代。",
        "用 `s.len()` 当字符数：它返回字节数，多字节字符会偏大，字符数应用 `chars().count()`。",
        "随意 `&s[a..b]`：跨越字符边界会 panic，应先用 `char_indices()` 确认边界。"
    ],
    "exercise": {
        "prompt": "写函数 `is_palindrome(text: &str) -> bool` 判断文本（忽略空格与大小写）是否回文，并在 main 中用两个样例验证。",
        "hint": "先 `chars().filter(|c| !c.is_whitespace()).flat_map(|c| c.to_lowercase()).collect::<Vec<_>>()`，再与反转比较。",
        "answer": "fn is_palindrome(text: &str) -> bool {\n    let cleaned: Vec<char> = text\n        .chars()\n        .filter(|c| !c.is_whitespace())\n        .flat_map(|c| c.to_lowercase())\n        .collect();\n    cleaned.iter().eq(cleaned.iter().rev())\n}\n\nfn main() {\n    println!(\"{}\", is_palindrome(\"上海自来水来自海上\"));\n    println!(\"{}\", is_palindrome(\"Rust\"));\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 19,
    "title": "变更性、遮蔽与作用域",
    "level": "beginner",
    "domain": "syntax-types",
    "summary": "理解 `let mut` 的显式可变、遮蔽（shadowing）与作用域规则，避免共享可变带来的隐患。",
    "concepts": ["let mut", "遮蔽", "作用域", "不可变默认", "块表达式"],
    "objective": "能区分重新绑定（遮蔽）与重新赋值，并用作用域控制变量可见性。",
    "prerequisites": ["015"],
    "explain": "Rust 变量默认不可变，要修改必须 `let mut`；这是有意的设计，让“哪里会变”在类型与绑定层可见。遮蔽（shadowing）指用新的 `let` 绑定同名变量，它会创建一个新绑定并遮蔽旧的，可改变类型（`let x = 5; let x = x.to_string();`），旧的绑定若不再使用通常被优化掉。作用域由块 `{}` 决定，内层可遮蔽外层，离开块后内层绑定失效。块本身是表达式，末行无分号时其值就是块的值，这让我们能写 `let v = { let t = f(); t * 2 };`。`mut` 只在同类型赋值时有用；需要换类型就用遮蔽。避免用 `mut` 拖很长生命周期：把可变范围收窄到最小块，可减少借用冲突与逻辑错误。",
    "code": "fn main() {\n    let value = 10;\n    let value = value * 2;          // 遮蔽：新绑定，仍是 i32\n    let value = value.to_string();  // 遮蔽：类型变为 String\n    println!(\"value = {}\", value);\n\n    let mut counter = 0;\n    {\n        counter += 1;               // 内层块修改外层 mut 绑定\n        let inner = counter * 10;   // 内层绑定离开块即失效\n        println!(\"inner = {}\", inner);\n    }\n    println!(\"counter = {}\", counter);\n\n    let computed = {\n        let base = 4;\n        base * base                   // 块表达式求值给 computed\n    };\n    println!(\"computed = {}\", computed);\n}\n",
    "output": "value = 20\ninner = 10\ncounter = 1\ncomputed = 16\n",
    "pitfalls": [
        "以为遮蔽会修改原变量：它创建新绑定，旧绑定的内存位置与类型都不同。",
        "滥用 `mut`：把整个函数体变可变会放宽借用检查，可能掩盖设计问题，应尽量收窄可变范围。",
        "忘记块是表达式：末行加了分号就变成 `()`，赋值给变量会得到单元类型导致类型错误。"
    ],
    "exercise": {
        "prompt": "写程序把字符串 `\"123\"` 先解析为 i32，再用遮蔽把它变成两倍的 String，最后打印；同时用一个内部块计算平方后打印。",
        "hint": "`let n = \"123\".parse::<i32>().unwrap(); let n = (n * 2).to_string();` 内层块返回平方值。",
        "answer": "fn main() {\n    let n = \"123\".parse::<i32>().unwrap();\n    let n = (n * 2).to_string();\n    println!(\"doubled = {}\", n);\n\n    let square = {\n        let base = 9;\n        base * base\n    };\n    println!(\"square = {}\", square);\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 20,
    "title": "`if` / `else if` 作为表达式",
    "level": "beginner",
    "domain": "syntax-types",
    "summary": "把 `if` 当表达式使用，理解分支必须类型一致，并区分语句与表达式的差别。",
    "concepts": ["if 表达式", "else if", "类型一致", "语句 vs 表达式", "早返回"],
    "objective": "能用 `if` 表达式给变量赋值或直接返回，并解释各分支类型必须相同。",
    "prerequisites": ["019"],
    "explain": "Rust 里 `if` 是表达式：`let x = if cond { 1 } else { 2 };` 合法，且两个分支的类型必须一致（都是 i32）。如果分支块末尾带分号，它就是 `()`，这也是常见类型错误来源。`if` 可以链式 `else if`，但没有 C 的三元 `?:`，惯用写法是 `let v = if c { a } else { b };`。与 `match` 相比，`if` 适合两三个布尔分支，分支多或要匹配结构时用 `match` 更清晰。`if` 作为表达式可用于提前返回：`if !valid { return None; }`。注意条件位置必须是 `bool`，Rust 不做 truthy 转换，`if 1 { }` 会编译失败。",
    "code": "fn grade(score: u32) -> char {\n    if score >= 90 {\n        'A'\n    } else if score >= 80 {\n        'B'\n    } else if score >= 70 {\n        'C'\n    } else {\n        'F'\n    }\n}\n\nfn max_of(a: i32, b: i32) -> i32 {\n    if a >= b { a } else { b }\n}\n\nfn main() {\n    for score in [95, 83, 71, 60] {\n        println!(\"score = {} -> {}\", score, grade(score));\n    }\n    let m = max_of(12, 27);\n    println!(\"max = {}\", m);\n    println!(\"if 条件必须是 bool, 不存在 truthy 转换\");\n}\n",
    "output": "score = 95 -> A\nscore = 83 -> B\nscore = 71 -> C\nscore = 60 -> F\nmax = 27\nif 条件必须是 bool, 不存在 truthy 转换\n",
    "pitfalls": [
        "分支类型不一致：`if c { 1 } else { \"x\" }` 会报类型错误，各分支必须同型。",
        "在表达式分支末尾加分号：会把分支值变成 `()`，导致赋值类型不匹配。",
        "用 `if` 做真值判断：条件必须是 bool，数字或字符串不会被隐式转换。"
    ],
    "exercise": {
        "prompt": "写函数 `sign_label(n: i32) -> &'static str`，用 `if` 表达式返回 \"正\"/\"零\"/\"负\"，并在 main 中测试 -5、0、7。",
        "hint": "三个分支末尾都不加分号，让每个分支产生 &'static str。",
        "answer": "fn sign_label(n: i32) -> &'static str {\n    if n > 0 {\n        \"正\"\n    } else if n < 0 {\n        \"负\"\n    } else {\n        \"零\"\n    }\n}\n\nfn main() {\n    for n in [-5, 0, 7] {\n        println!(\"{} -> {}\", n, sign_label(n));\n    }\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 21,
    "title": "三种循环：`loop`/`while`/`for` 与循环标签",
    "level": "beginner",
    "domain": "syntax-types",
    "summary": "按场景选择循环：无限循环用 loop 可返回值、条件循环用 while、遍历用 for，并学会用标签跳出多层。",
    "concepts": ["loop", "while", "for", "循环标签", "break 带值"],
    "objective": "能根据“是否需要返回值 / 遍历集合 / 条件退出”选择合适循环，并用标签控制嵌套。",
    "prerequisites": ["020"],
    "explain": "`loop` 是无限循环，`break value` 可以让 loop 表达式产出值（这是 `while`/`for` 做不到的）；`while cond` 在条件为假时结束；`for x in iter` 遍历任何 IntoIterator，是处理集合的首选，因为它避免手动下标越界且性能通常与手写索引相当。嵌套循环可用标签 `'outer: loop { break 'outer; }` 跳出指定层。此外应优先使用迭代器适配器（`map`/`filter`/`take_while`）来表达意图，它们往往比手写循环更清晰。注意 `for` 默认按值消费集合（`for s in vec` 会移走元素），只需引用时写 `for s in &vec` 或 `vec.iter()`。手动 `while i < len` 配下标在 Rust 中不常用，容易越界。",
    "code": "fn first_above(limit: i32, xs: &[i32]) -> Option<i32> {\n    for &x in xs {\n        if x > limit {\n            return Some(x);\n        }\n    }\n    None\n}\n\nfn main() {\n    // loop 带 break 值\n    let mut n = 1u64;\n    let reached = loop {\n        n *= 2;\n        if n >= 100 {\n            break n;\n        }\n    };\n    println!(\"reached = {}\", reached);\n\n    // while\n    let mut countdown = 3;\n    while countdown > 0 {\n        println!(\"countdown = {}\", countdown);\n        countdown -= 1;\n    }\n\n    // for + 标签跳出多层\n    let grid = [[1, 2], [3, 4], [5, 6]];\n    'outer: for row in grid {\n        for cell in row {\n            if cell == 4 {\n                println!(\"found 4, 跳出外层\");\n                break 'outer;\n            }\n        }\n    }\n\n    println!(\"first_above(3) = {:?}\", first_above(3, &[1, 2, 3, 4, 5]));\n}\n",
    "output": "reached = 128\ncountdown = 3\ncountdown = 2\ncountdown = 1\nfound 4, 跳出外层\nfirst_above(3) = Some(4)\n",
    "pitfalls": [
        "用 `while` 也想返回值：只有 `loop` 支持 `break value`，其他循环只能靠外部变量。",
        "`for` 按值消费导致集合不可再用：需要保留时用 `&vec`/`vec.iter()`。",
        "嵌套里 `break` 只跳出内层：要跳出指定层必须加标签。"
    ],
    "exercise": {
        "prompt": "用 `loop` 计算 1+2+...+n 首次超过 100 时的 n 与和，并打印二者。",
        "hint": "loop 里累加并在超过 100 时 `break (n, sum)` 返回元组。",
        "answer": "fn main() {\n    let (n, sum) = {\n        let (mut i, mut acc) = (0i32, 0i32);\n        loop {\n            i += 1;\n            acc += i;\n            if acc > 100 {\n                break (i, acc);\n            }\n        }\n    };\n    println!(\"n = {}, sum = {}\", n, sum);\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 22,
    "title": "`match` 基础：穷尽性与通配",
    "level": "beginner",
    "domain": "syntax-types",
    "summary": "用 match 做多路分支，理解穷尽性检查、`_` 通配与 `|` 多模式。",
    "concepts": ["match", "穷尽性", "_ 通配", "| 多模式", "范围模式"],
    "objective": "能写出穷尽所有情况的 match，并用通配与范围模式简化分支。",
    "prerequisites": ["020"],
    "explain": "`match scrutinee { pattern => expr, ... }` 会依次比较模式，必须覆盖所有可能值，否则编译报 E0004。整数、bool、枚举都能被穷尽检查。`_` 是通配模式，匹配任何值且不绑定；`|` 组合多个模式；范围模式 `1..=5` 匹配闭区间（仅限整数与 char）。match 也是表达式，各分支类型要一致。相比 `if else`，match 在分支多、要解构数据或需要穷尽保证时更合适。可用 `@` 绑定并同时匹配范围，用守卫 `if` 添加额外条件。避免用 `_ =>` 草率吞掉未处理的枚举变体——那样会丢失穷尽性保护；理想情况下枚举分支应逐一列出，让新增变体时编译失败提醒你更新逻辑。",
    "code": "fn classify(n: i32) -> &'static str {\n    match n {\n        0 => \"零\",\n        1 | 2 | 3 => \"小正整数\",\n        4..=9 => \"中正整数\",\n        n if n < 0 => \"负数\",\n        _ => \"大正整数\",\n    }\n}\n\nfn main() {\n    for n in [-3, 0, 2, 7, 42] {\n        println!(\"{:>3} -> {}\", n, classify(n));\n    }\n    let flag = true;\n    let text = match flag {\n        true => \"开\",\n        false => \"关\",\n    };\n    println!(\"flag = {}, text = {}\", flag, text);\n}\n",
    "output": " -3 -> 负数\n  0 -> 零\n  2 -> 小正整数\n  7 -> 中正整数\n 42 -> 大正整数\nflag = true, text = 开\n",
    "pitfalls": [
        "忘记穷尽性：漏掉某个整数范围或枚举变体会直接编译失败（E0004），要补齐或加 `_`。",
        "通配顺序错误：`_` 放前面会吞掉后面所有分支，导致“不可达模式”警告与逻辑错误。",
        "分支类型不一致：每个 `=>` 后面的表达式必须是同一类型。"
    ],
    "exercise": {
        "prompt": "写函数 `day_type(day: u8) -> &'static str`，把 1..=5 归为工作日、6..=7 归为周末、其他归为非法，并用 match 实现后测试 3、6、9。",
        "hint": "用范围模式 `1..=5 => ...` 与 `_ => ...`。",
        "answer": "fn day_type(day: u8) -> &'static str {\n    match day {\n        1..=5 => \"工作日\",\n        6 | 7 => \"周末\",\n        _ => \"非法\",\n    }\n}\n\nfn main() {\n    for d in [3, 6, 9] {\n        println!(\"{} -> {}\", d, day_type(d));\n    }\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 23,
    "title": "`if let` / `while let` / `let else`",
    "level": "beginner",
    "domain": "syntax-types",
    "summary": "用轻量模式匹配语法处理单分支 Option/Result，避免为一种情况写完整 match。",
    "concepts": ["if let", "while let", "let else", "单分支匹配", "Refutable 模式"],
    "objective": "能根据是否需要处理“另一种情况”选择 if let、while let 或 let else。",
    "prerequisites": ["022"],
    "explain": "`if let Some(x) = opt { ... } else { ... }` 只关心一种模式时比整段 match 简洁；可带 `else` 处理不匹配情况。`while let Some(x) = iter.next() { ... }` 在模式持续匹配时循环，适合消费迭代器；不过对常用迭代器，直接 `for` 更清晰。`let else`（Rust 1.65+）用于“否则必须提前退出”的场景：`let Some(x) = opt else { return; };`，它要求发散块（`return`/`continue`/`break`/`panic!`），能让主路径保持在缩进较浅的层级。这些语法只改变形态，不改语义——它们都是 match 的糖。选择原则：只想处理一种情况且无需 else → `if let`；两种情况都要 → `match`；提前失败校验 → `let else`。",
    "code": "fn parse_first_word(text: &str) -> Option<String> {\n    if let Some(word) = text.split_whitespace().next() {\n        Some(word.to_string())\n    } else {\n        None\n    }\n}\n\nfn sum_while_let(values: &[i32]) -> i32 {\n    let mut it = values.iter();\n    let mut acc = 0;\n    while let Some(&v) = it.next() {\n        if v < 0 {\n            continue;\n        }\n        acc += v;\n    }\n    acc\n}\n\nfn describe(value: Option<i32>) -> String {\n    let Some(v) = value else {\n        return String::from(\"无值\");\n    };\n    format!(\"有值: {}\", v)\n}\n\nfn main() {\n    println!(\"first_word = {:?}\", parse_first_word(\"  hello world \"));\n    println!(\"sum = {}\", sum_while_let(&[3, -1, 4, -1, 5]));\n    println!(\"{}\", describe(Some(42)));\n    println!(\"{}\", describe(None));\n}\n",
    "output": "first_word = Some(\"hello\")\nsum = 12\n有值: 42\n无值\n",
    "pitfalls": [
        "用 `if let` 处理需要两种情况的逻辑：会漏掉 None 分支的显式处理，应该用 match。",
        "`let else` 块里没有发散语句：块必须以 return/break/continue/panic! 结束，否则编译失败。",
        "把 `while let` 用在可直接 for 的场景：徒增样板，`for x in iter` 更清晰。"
    ],
    "exercise": {
        "prompt": "写函数 `last_char(text: &str) -> Option<char>`，用 `let else` 处理空串提前返回，并在 main 中测试非空与空串。",
        "hint": "`let Some(last) = text.chars().last() else { return None; };` 然后返回 Some(last)。",
        "answer": "fn last_char(text: &str) -> Option<char> {\n    let Some(last) = text.chars().last() else {\n        return None;\n    };\n    Some(last)\n}\n\nfn main() {\n    println!(\"{:?}\", last_char(\"rust\"));\n    println!(\"{:?}\", last_char(\"\"));\n}\n"
    },
    "runtime": "desktop"
},
]
