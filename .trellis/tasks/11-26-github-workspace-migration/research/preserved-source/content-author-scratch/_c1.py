# -*- coding: utf-8 -*-
"""Lessons 033..040 (Domain C, part 1: ownership basics)."""

LESSONS = [
{
    "id": 33,
    "title": "所有权三原则与 move 语义",
    "level": "intermediate",
    "domain": "ownership-borrowing",
    "summary": "理解每个值有唯一所有者、离开作用域即释放、赋值/传参会移动所有权这三条规则。",
    "concepts": ["所有权", "move", "作用域释放", "Drop", "移动后失效"],
    "objective": "能解释一段代码在何处发生移动、何处释放，并预测移动后再使用会报 E0382。",
    "prerequisites": ["018"],
    "explain": "Rust 的所有权规则：每个值有且仅有一个所有者；所有者离开作用域时值被释放（若实现了 Drop 则调用析构）；把值赋给另一个变量或传参给函数会“移动”所有权，之后原变量不可再用。移动语义是编译期概念，运行时通常只是复制指针/字段，不产生深拷贝；真正防止的是释放两次和使用已释放内存。对于栈上的 Copy 类型（整数、bool、char、仅含 Copy 字段的元组/数组）赋值是复制而非移动。堆类型如 String、Vec 在移动后源变量失效：`let a = String::from(\"x\"); let b = a; println!(\"{}\", a);` 会报 E0382。理解移动点，是理解后面借用、生命周期乃至并发的前提。函数返回所有权可以把值“交还”给调用者。",
    "code": "fn consume(text: String) -> usize {\n    // 拥有 text 的所有权，函数结束时释放\n    text.len()\n}\n\nfn main() {\n    let owned = String::from(\"ownership\");\n    let len = consume(owned); // owned 被移动进 consume\n    println!(\"len = {}\", len);\n    // println!(\"{}\", owned); // 取消注释会报 E0382: borrow of moved value\n\n    // Copy 类型是复制而非移动\n    let x = 10;\n    let y = x;\n    println!(\"x = {}, y = {}\", x, y);\n\n    let moved_again = String::from(\"box\");\n    let alias = moved_again; // 移动\n    println!(\"alias = {}\", alias);\n}\n",
    "output": "len = 9\nx = 10, y = 10\nalias = box\n",
    "pitfalls": [
        "移动后再使用原变量：编译报 E0382，需要克隆、借用或调整所有关系。",
        "以为移动是深拷贝：它通常只搬运指针/字段，性能好但源变量随即失效。",
        "在循环里按值传集合：每次迭代都会消耗集合，第二次迭代就报使用已移动值。"
    ],
    "exercise": {
        "prompt": "写函数 `take_last(Vec<i32>) -> Option<i32>` 按值接收向量并返回最后一个元素；在 main 中调用它，再注释说明为什么之后不能继续使用该向量。",
        "hint": "用 `v.into_iter().last()`；按值接收会移动向量。",
        "answer": "fn take_last(v: Vec<i32>) -> Option<i32> {\n    v.into_iter().last()\n}\n\nfn main() {\n    let data = vec![1, 2, 3];\n    let last = take_last(data);\n    println!(\"last = {:?}\", last);\n    // data 已被移动进 take_last，之后使用会报 E0382\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 34,
    "title": "`Clone` 与 `Copy`：何时自动复制",
    "level": "intermediate",
    "domain": "ownership-borrowing",
    "summary": "区分显式克隆与隐式复制，理解 Copy 的约束条件以及为什么实现 Copy 就不能实现 Drop。",
    "concepts": ["Clone", "Copy", "显式克隆", "Copy 约束", "派生"],
    "objective": "能判断一个类型能否实现 Copy，并说明 Clone 与 Copy 的语义差别。",
    "prerequisites": ["033"],
    "explain": "`Clone` 提供显式的 `.clone()`，可做任意深度的复制（可能昂贵，如 Vec/String）。`Copy` 是标记 trait，表示按位复制即可、且复制后源变量仍有效，因此赋值/传参是复制而非移动。Copy 有严格约束：类型所有字段都必须 Copy，且该类型不能实现 Drop（否则复制会带来重复析构）。派生写法是 `#[derive(Clone, Copy)]`。语义差别：Copy 是隐式发生的、廉价的；Clone 必须显式调用、可能昂贵。自定义类型若含堆分配（String、Vec），只能 `Clone` 不能 `Copy`。实践建议：小的纯值类型（坐标、id、单位）实现 Copy 让 API 更好用；含资源或大数据的类型保持移动语义，需要复制时显式 clone，让代价可见。",
    "code": "#[derive(Debug, Clone, Copy, PartialEq)]\nstruct Point {\n    x: i32,\n    y: i32,\n}\n\n#[derive(Debug, Clone, PartialEq)]\nstruct Label {\n    text: String,\n}\n\nfn shift(p: Point, dx: i32) -> Point {\n    // 因为 Point: Copy，p 仍可在别处使用\n    Point { x: p.x + dx, ..p }\n}\n\nfn main() {\n    let p = Point { x: 1, y: 2 };\n    let moved = shift(p, 5);\n    println!(\"p = {:?}, moved = {:?}\", p, moved);\n\n    let label = Label { text: String::from(\"tag\") };\n    let copy = label.clone();\n    println!(\"label = {:?}, clone = {:?}\", label, copy);\n    println!(\"Copy 是隐式且廉价, Clone 是显式且可能昂贵\");\n}\n",
    "output": "p = Point { x: 1, y: 2 }, moved = Point { x: 6, y: 2 }\nlabel = Label { text: \"tag\" }, clone = Label { text: \"tag\" }\nCopy 是隐式且廉价, Clone 是显式且可能昂贵\n",
    "pitfalls": [
        "给含 String/Vec 的类型加 Copy：编译失败，因为字段不是 Copy，且与 Drop 冲突。",
        "在大结构体上滥用 clone：深层复制可能昂贵，应改为借用或 `Rc` 共享。",
        "以为派生 Clone 一定是深拷贝：对含 Rc 的类型，clone 只增加引用计数，仍是浅共享。"
    ],
    "exercise": {
        "prompt": "定义 `#[derive(Clone, Copy)] struct Range { start: i32, end: i32 }` 与 `fn length(r: Range) -> i32`，在 main 中多次传入同一个 Range 以证明它是 Copy。",
        "hint": "Copy 类型传给函数后仍可用，连续调用不报错即可。",
        "answer": "#[derive(Debug, Clone, Copy)]\nstruct Range {\n    start: i32,\n    end: i32,\n}\n\nfn length(r: Range) -> i32 {\n    r.end - r.start\n}\n\nfn main() {\n    let r = Range { start: 3, end: 10 };\n    println!(\"len1 = {}\", length(r));\n    println!(\"len2 = {}\", length(r));\n    println!(\"r 仍可用: {:?}\", r);\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 35,
    "title": "函数中的所有权转移与返还",
    "level": "intermediate",
    "domain": "ownership-borrowing",
    "summary": "用“传入—处理—返回”模式在函数间转移所有权，理解返回值的所有权归属调用者。",
    "concepts": ["所有权转移", "返回所有权", "损耗式 API", "链式调用", "builder 风格"],
    "objective": "能写出按值接收并返回值以保持所有权可追踪的函数，并说明为何有时必须返还所有权。",
    "prerequisites": ["033"],
    "explain": "当一个函数需要消费或转换数据时，常见签名是 `fn f(v: T) -> T`：接收所有权，处理后把新的所有权返还给调用者。这样调用者仍掌握值，可继续链式调用或再次转移。返回位置的值所有权属于调用者，因此 `let s2 = transform(s1);` 后 `s2` 有效、`s1` 失效。若函数只是读取，应改用借用 `&T`，避免所有权来回搬运；若函数需要修改后仍交还，可接收 `mut v: T -> T` 或直接 `&mut T`。返回引用时，编译器要求该引用生命周期与输入绑定（见生命周期课）。链式 builder 就是这一模式的典型：每个方法按值接收 `self`、返回 `Self`，从而组合出流畅 API。理解“谁最后持有所有权”，就能预判哪些变量在哪一步失效。",
    "code": "#[derive(Debug)]\nstruct Builder {\n    parts: Vec<String>,\n}\n\nimpl Builder {\n    fn new() -> Self {\n        Builder { parts: Vec::new() }\n    }\n\n    fn add(mut self, part: &str) -> Self {\n        self.parts.push(part.to_string());\n        self\n    }\n\n    fn finish(self) -> String {\n        self.parts.join(\"-\")\n    }\n}\n\nfn shout(mut text: String) -> String {\n    text.push('!');\n    text\n}\n\nfn main() {\n    let message = String::from(\"hello\");\n    let loud = shout(message);\n    println!(\"loud = {}\", loud);\n\n    let joined = Builder::new().add(\"a\").add(\"b\").add(\"c\").finish();\n    println!(\"joined = {}\", joined);\n}\n",
    "output": "loud = hello!\njoined = a-b-c\n",
    "pitfalls": [
        "链式调用中途使用旧变量：`add` 消费 `self`，旧绑定已失效，应使用返回值。",
        "该借用却按值传：会用移动把调用者的值“吃”掉，导致后续无法使用。",
        "返回局部变量的引用：局部值在函数结束时释放，返回其引用会报生命周期错误。"
    ],
    "exercise": {
        "prompt": "写函数 `append_suffix(String, &str) -> String`，在字符串末尾追加后缀并返回；在 main 中对同一字符串连续追加两个不同后缀（利用返回值）。",
        "hint": "每次调用把上一步返回值作为输入，形成 `s = append_suffix(s, \"...\")`。",
        "answer": "fn append_suffix(mut text: String, suffix: &str) -> String {\n    text.push_str(suffix);\n    text\n}\n\nfn main() {\n    let s = String::from(\"rust\");\n    let s = append_suffix(s, \"-acean\");\n    let s = append_suffix(s, \"-2021\");\n    println!(\"{}\", s);\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 36,
    "title": "引用与借用规则（可变/不可变）",
    "level": "intermediate",
    "domain": "ownership-borrowing",
    "summary": "用 `&T` 与 `&mut T` 在不转移所有权的前提下访问数据，理解“多个只读或一个可变”的核心规则。",
    "concepts": ["&T", "&mut T", "借用规则", "别名与可变性", "解引用"],
    "objective": "能写出借用式函数签名，并解释为什么同一时刻不能既有可变借用又有其他借用。",
    "prerequisites": ["033"],
    "explain": "借用让你在不取得所有权的情况下使用值：`&T` 是不可变引用（可同时存在多个），`&mut T` 是可变引用（同一作用域内只能有一个，且不能与其他任何借用共存）。这条“共享读取或独占写入”规则在编译期消除数据竞争与迭代器失效。获取可变借用的前提是变量本身 `let mut`。函数收 `&T` 表示只读，收 `&mut T` 表示可改，调用处要写 `&x` / `&mut x`。解引用用 `*`，但方法调用会自动引用/解引用，所以 `r.len()` 可直接对 `&String` 调用。借用是临时作用域下的，它的有效期由“最后一次使用”决定（NLL）。写 API 时优先借用而不是拿走所有权，能让调用者保留数据并减少 clone。",
    "code": "fn total(items: &[i32]) -> i32 {\n    items.iter().sum()\n}\n\nfn double_all(items: &mut Vec<i32>) {\n    for x in items.iter_mut() {\n        *x *= 2;\n    }\n}\n\nfn longest_len(a: &str, b: &str) -> usize {\n    a.len().max(b.len())\n}\n\nfn main() {\n    let mut numbers = vec![1, 2, 3, 4];\n    let before = total(&numbers);\n    double_all(&mut numbers);\n    println!(\"before = {}, after = {:?}\", before, numbers);\n\n    let (s1, s2) = (\"rust\", \"ownership\");\n    println!(\"longest_len = {}\", longest_len(s1, s2));\n    println!(\"同一时刻: 多个 &T 或一个 &mut T\");\n}\n",
    "output": "before = 10, after = [2, 4, 6, 8]\nlongest_len = 9\n同一时刻: 多个 &T 或一个 &mut T\n",
    "pitfalls": [
        "同时持有可变与不可变借用：编译报 E0502，需要先结束只读借用的使用范围。",
        "对未声明 mut 的变量取 `&mut`：变量必须 `let mut` 才能被可变借用。",
        "认为函数收 `&mut` 就会一直锁住变量：借用随最后一次使用结束，之后可再次借用。"
    ],
    "exercise": {
        "prompt": "写函数 `increment_all(&mut [i32])` 把切片每个元素加一，以及 `count_positive(&[i32]) -> usize` 统计正数个数；在 main 中先统计再加一后统计。",
        "hint": "`for x in items.iter_mut() { *x += 1; }`；统计用 `iter().filter(|v| **v > 0).count()`。",
        "answer": "fn increment_all(items: &mut [i32]) {\n    for x in items.iter_mut() {\n        *x += 1;\n    }\n}\n\nfn count_positive(items: &[i32]) -> usize {\n    items.iter().filter(|v| **v > 0).count()\n}\n\nfn main() {\n    let mut data = [-2, 0, 3, 5];\n    println!(\"before = {}\", count_positive(&data));\n    increment_all(&mut data);\n    println!(\"after  = {}\", count_positive(&data));\n    println!(\"data   = {:?}\", data);\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 37,
    "title": "借用检查器与 NLL 直觉",
    "level": "intermediate",
    "domain": "ownership-borrowing",
    "summary": "用非词法生命周期（NLL）理解借用何时结束，学会通过缩小借用范围解决常见冲突。",
    "concepts": ["借用检查器", "NLL", "借用范围", "冲突诊断", "重新借用"],
    "objective": "能预测一处借用冲突并使用“缩小作用域/提前取值/分阶段”来修复。",
    "prerequisites": ["036"],
    "explain": "NLL（non-lexical lifetimes）指借用的有效期由数据流决定，而非由 `{}` 块边界决定：借用从创建点开始，到最后一次使用点结束。因此 `let r = &v[0]; println!(\"{}\", r); v.push(1);` 是合法的，因为 `r` 的最后使用在 push 之前。冲突通常出现在“前一个借用的结果被后面用到”：例如同时持有 `&v` 与 `&mut v`，或迭代器借用 `v` 时又去修改 `v`。修复策略有三类：把只读借用的值先取出来（`let n = v.len();`），把可变操作放到只读借用结束之后，或重构为分阶段（先收集索引，再统一修改）。理解 NLL 后，你会发现多数借用错误都能靠“让只读借用早点结束”解决，而不必到处 clone。",
    "code": "fn main() {\n    let mut data = vec![10, 20, 30];\n\n    // 只读借用的最后使用在 println!，之后即可可变借用\n    {\n        let slice = &data[0..2];\n        println!(\"slice = {:?}\", slice);\n    }\n    data.push(40);\n    println!(\"after push = {:?}\", data);\n\n    // 先取出长度，结束不可变借用后再修改\n    let len = data.len();\n    if len > 1 {\n        data.swap(0, len - 1);\n    }\n    println!(\"after swap = {:?}\", data);\n\n    // 分阶段：先收集需要修改的索引\n    let targets: Vec<usize> = data.iter().enumerate()\n        .filter(|(_, v)| **v % 20 == 0)\n        .map(|(i, _)| i)\n        .collect();\n    for i in targets {\n        data[i] += 1;\n    }\n    println!(\"final = {:?}\", data);\n}\n",
    "output": "slice = [10, 20]\nafter push = [10, 20, 30, 40]\nafter swap = [40, 20, 30, 10]\nfinal = [41, 21, 30, 10]\n",
    "pitfalls": [
        "以为借用按块结束：NLL 下按最后一次使用结束，块只是常见边界。",
        "在持有 `&data` 时调用 `data.push`：会与只读借用冲突，需先结束只读使用。",
        "用 clone 掩盖冲突：能靠缩小借用范围解决就别复制，否则造成不必要开销。"
    ],
    "exercise": {
        "prompt": "下面的意图是“打印首元素后把首元素改成 0”。写一个不会触发 E0502 的程序，先读取再修改，并打印修改后的向量。",
        "hint": "先 `let first = data[0]; println!(...)`，再 `data[0] = 0;`，不要同时留着一个指向首元素的引用。",
        "answer": "fn main() {\n    let mut data = vec![7, 8, 9];\n    let first = data[0];\n    println!(\"first = {}\", first);\n    data[0] = 0;\n    println!(\"data = {:?}\", data);\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 38,
    "title": "悬垂引用与生命周期引入",
    "level": "intermediate",
    "domain": "ownership-borrowing",
    "summary": "理解为什么返回局部变量的引用不合法，认识生命周期标注作为“引用有效期”的契约。",
    "concepts": ["悬垂引用", "生命周期", "借用有效性", "E0106", "作用域包含"],
    "objective": "能识别会产生悬垂引用的代码，并说明生命周期标注要表达的是什么关系。",
    "prerequisites": ["036"],
    "explain": "悬垂引用（dangling reference）指向已被释放的内存。Rust 在编译期禁止它：任何引用的生命周期必须不超过它所借用的值。若函数返回引用，编译器需要知道这个引用来源于哪个输入，因此签名要写明生命周期，例如 `fn first<'a>(s: &'a str) -> &'a str`，含义是“返回的引用与输入 s 活得一样久”。生命周期本身不改变值，它只是给借用关系加上可检查的标注，运行时零开销。初学者常遇到的 E0106（missing lifetime specifier）正是因为返回引用而输入有多个、编译器无法推断。修复方法：明确哪个输入被返回，或用 `'static`（仅当数据真的活到程序结束，如字面量），或干脆返回拥有型值（`String`）避免生命周期纠缠。",
    "code": "// 返回引用时用生命周期把“返回值的有效期”绑定到输入\nfn first_word<'a>(text: &'a str) -> &'a str {\n    match text.find(' ') {\n        Some(idx) => &text[..idx],\n        None => text,\n    }\n}\n\nfn make_owned(text: &str) -> String {\n    // 返回拥有型值，避免生命周期标注\n    text.to_uppercase()\n}\n\nstatic GREETING: &str = \"hello static\";\n\nfn static_ref() -> &'static str {\n    GREETING\n}\n\nfn main() {\n    let sentence = String::from(\"rust ownership model\");\n    let word = first_word(&sentence);\n    println!(\"first_word = {}\", word);\n    println!(\"owned = {}\", make_owned(\"abc\"));\n    println!(\"static = {}\", static_ref());\n    println!(\"返回局部变量引用会产生悬垂引用, 编译期被拒绝\");\n}\n",
    "output": "first_word = rust\nowned = ABC\nstatic = hello static\n返回局部变量引用会产生悬垂引用, 编译期被拒绝\n",
    "pitfalls": [
        "返回局部 String 的 `&str`：局部值在函数结束时释放，引用悬垂，编译失败。",
        "返回引用却不标生命周期：当有多个输入引用时编译器无法推断，报 E0106。",
        "用 `'static` 回避问题：只有真正活到程序结束的数据才满足，硬套会编译失败或语义错误。"
    ],
    "exercise": {
        "prompt": "写函数 `last_word<'a>(text: &'a str) -> &'a str` 返回最后一个词，并在 main 中用它打印 \"a b c\" 的最后一个词。",
        "hint": "用 `text.rsplit_once(' ').map(|(_, w)| w).unwrap_or(text)`。",
        "answer": "fn last_word<'a>(text: &'a str) -> &'a str {\n    text.rsplit_once(' ').map(|(_, w)| w).unwrap_or(text)\n}\n\nfn main() {\n    let text = \"a b c\";\n    println!(\"{}\", last_word(text));\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 39,
    "title": "生命周期标注：函数签名",
    "level": "intermediate",
    "domain": "ownership-borrowing",
    "summary": "在函数签名中显式标注生命周期，表达多个引用之间的“同生共死”关系。",
    "concepts": ["生命周期参数", "'a 标注", "关系表达", "泛型生命周期", "编译期检查"],
    "objective": "能读懂并写出带生命周期参数的函数签名，解释每个标注约束了什么。",
    "prerequisites": ["038"],
    "explain": "生命周期参数写在尖括号里且以小写撇开头：`fn f<'a>(x: &'a str) -> &'a str`。它表达“输出引用的有效期不超过输入 `'a`”。当函数有多个输入引用，可按需标注：`fn pick<'a>(x: &'a str, y: &'a str) -> &'a str` 要求两个输入至少都活得和返回引用一样久（编译器取二者交集）；也可以只标注其中一个：`fn take<'a>(x: &'a str, y: &str) -> &'a str` 表示返回只依赖 x。生命周期参数是泛型的一种，实例化时由编译器根据调用点推断，不需要手写具体值。标注不改变运行时行为，只是给借用检查器提供事实。绝大多数函数无需手写生命周期（省略规则会处理），只有当返回引用且来源不唯一时才必须写明。",
    "code": "// 两个输入都需要活得足够久，返回其一\nfn longer<'a>(x: &'a str, y: &'a str) -> &'a str {\n    if x.len() >= y.len() { x } else { y }\n}\n\n// 返回只依赖 x，y 可以更短命\nfn prefixed<'a>(x: &'a str, prefix: &str) -> &'a str {\n    let _ = prefix;\n    x\n}\n\nfn main() {\n    let a = String::from(\"long string here\");\n    let b = String::from(\"short\");\n    println!(\"longer = {}\", longer(&a, &b));\n\n    let owned = String::from(\"body\");\n    {\n        let prefix = String::from(\"pre-\");\n        println!(\"prefixed = {}\", prefixed(&owned, &prefix));\n    }\n    println!(\"owned 仍然有效: {}\", owned);\n}\n",
    "output": "longer = long string here\nprefixed = body\nowned 仍然有效: body\n",
    "pitfalls": [
        "过度标注：能靠省略规则推断的地方手写 `'a` 只会增加噪音。",
        "标注与实际不符：把输出绑到错误的输入上，编译器会按你的声明检查，可能导致误判。",
        "以为生命周期影响性能：它完全是编译期概念，生成的机器码没有额外开销。"
    ],
    "exercise": {
        "prompt": "写函数 `shortest<'a>(a: &'a str, b: &'a str) -> &'a str` 返回较短的字符串，并在 main 中测试两次。",
        "hint": "比较 len 后用 if/else 返回其中一个引用；两个输入同为 'a。",
        "answer": "fn shortest<'a>(a: &'a str, b: &'a str) -> &'a str {\n    if a.len() <= b.len() { a } else { b }\n}\n\nfn main() {\n    println!(\"{}\", shortest(\"abcdef\", \"ab\"));\n    println!(\"{}\", shortest(\"xy\", \"pqr\"));\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 40,
    "title": "结构体中的借用与生命周期参数",
    "level": "advanced",
    "domain": "ownership-borrowing",
    "summary": "让结构体持有引用时必须声明生命周期，理解这带来的“结构体不能超过被借用数据”约束。",
    "concepts": ["结构体生命周期", "借用字段", "约束传播", "拥有 vs 借用", "自引用难题"],
    "objective": "能写出带生命周期参数的结构体并实现其方法，判断何时应改为拥有数据。",
    "prerequisites": ["039"],
    "explain": "结构体字段若是引用，必须显式声明生命周期：`struct Excerpt<'a> { text: &'a str }`。含义是该实例不能比 `text` 指向的数据活得更久。impl 块也要带上参数：`impl<'a> Excerpt<'a> { fn first_line(&self) -> &'a str { ... } }`——这里返回 `&'a str`（来自字段）比返回 `&self` 活得更久，是常见且有用的技巧。结构体持有引用的代价是调用方要保证数据存活，且不能返回“借用局部变量的结构体”。经验法则：若结构体需要长期存储、跨线程、跨函数返回，通常改为拥有数据（String/Vec）更省心；若只是短命的视图/切片包装（解析器、迭代适配、参数聚合），借用结构体可以避免分配。注意结构体不能安全地同时持有数据与指向它的引用（自引用问题），这需要 Pin 或改为索引。",
    "code": "#[derive(Debug)]\nstruct Excerpt<'a> {\n    text: &'a str,\n    start: usize,\n}\n\nimpl<'a> Excerpt<'a> {\n    fn new(text: &'a str, start: usize) -> Self {\n        Excerpt { text, start }\n    }\n\n    // 返回的引用来自字段，生命周期是 'a 而非 &self\n    fn slice(&self) -> &'a str {\n        &self.text[self.start..]\n    }\n\n    fn len(&self) -> usize {\n        self.slice().len()\n    }\n}\n\nfn main() {\n    let document = String::from(\"第一章: 借用; 第二章: 生命周期\");\n    let excerpt = Excerpt::new(&document, \"第一章: \".len());\n    println!(\"slice = {}\", excerpt.slice());\n    println!(\"len = {}\", excerpt.len());\n    println!(\"excerpt 不能比 document 活得更久\");\n}\n",
    "output": "slice = 借用; 第二章: 生命周期\nlen = 31\nexcerpt 不能比 document 活得更久\n",
    "pitfalls": [
        "结构体含引用却不写生命周期：编译报 E0106，字段引用必须有名字。",
        "试图从函数返回借用局部变量的结构体：局部数据已释放，借用无效，需改为拥有型。",
        "impl 块漏写生命周期参数：`impl Excerpt<'a>` 会报未声明的 `'a`，要写 `impl<'a> Excerpt<'a>`。"
    ],
    "exercise": {
        "prompt": "定义 `struct Word<'a> { text: &'a str }`，实现 `new(&'a str) -> Self` 与 `upper(&self) -> String`（返回大写的拥有型字符串），在 main 中打印 \"rust\" 的大写形式。",
        "hint": "`upper` 用 `self.text.to_uppercase()` 返回 String，避免生命周期麻烦。",
        "answer": "struct Word<'a> {\n    text: &'a str,\n}\n\nimpl<'a> Word<'a> {\n    fn new(text: &'a str) -> Self {\n        Word { text }\n    }\n\n    fn upper(&self) -> String {\n        self.text.to_uppercase()\n    }\n}\n\nfn main() {\n    let w = Word::new(\"rust\");\n    println!(\"{}\", w.upper());\n}\n"
    },
    "runtime": "desktop"
},
]
