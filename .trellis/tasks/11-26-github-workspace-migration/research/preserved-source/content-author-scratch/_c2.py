# -*- coding: utf-8 -*-
"""Lessons 041..047 (Domain C, part 2: lifetimes, slices, aliasing)."""

LESSONS = [
{
    "id": 41,
    "title": "生命周期省略规则",
    "level": "advanced",
    "domain": "ownership-borrowing",
    "summary": "掌握三条省略规则，理解编译器何时自动补齐生命周期、何时必须手写。",
    "concepts": ["省略规则", "输入/输出生命周期", "&self 规则", "E0106", "自动推断"],
    "objective": "能手判一个函数签名是否需要手写生命周期，并说出省略规则给出的推断结果。",
    "prerequisites": ["039"],
    "explain": "生命周期省略规则有三条：1) 每个引用参数获得各自独立的生命周期参数；2) 若只有一个输入生命周期（无论是否含 self），它被赋给所有输出生命周期；3) 若方法有 `&self` 或 `&mut self`，则 `self` 的生命周期被赋给所有输出生命周期。只要规则能唯一确定输出，就无需手写。例如 `fn first(s: &str) -> &str` 由规则 2 成立；`fn get(&self, key: &str) -> &str` 由规则 3 把输出绑到 self 而非 key（这是关键——key 只是查找条件）。反之 `fn pick(a: &str, b: &str) -> &str` 因有两个输入且无 self，输出无法确定，规则 1 各自独立后没有规则决定输出，必须手写。理解这一点能解释很多“为什么这里要写 `'a`”的疑问，也能避免错误地把输出绑定到短命输入。",
    "code": "#[derive(Debug)]\nstruct Registry {\n    entries: Vec<(String, String)>,\n}\n\nimpl Registry {\n    fn new() -> Self {\n        Registry { entries: Vec::new() }\n    }\n\n    fn insert(&mut self, key: &str, value: &str) {\n        self.entries.push((key.to_string(), value.to_string()));\n    }\n\n    // 规则 3: 输出绑定到 &self，而不是 key\n    fn lookup(&self, key: &str) -> Option<&str> {\n        self.entries.iter()\n            .find(|(k, _)| k == key)\n            .map(|(_, v)| v.as_str())\n    }\n}\n\n// 规则 2: 唯一输入的生命周期赋给输出\nfn trim_ascii(text: &str) -> &str {\n    text.trim()\n}\n\nfn main() {\n    let mut reg = Registry::new();\n    reg.insert(\"name\", \"Rust\");\n    reg.insert(\"year\", \"2015\");\n    println!(\"lookup(name) = {:?}\", reg.lookup(\"name\"));\n    println!(\"trim = {:?}\", trim_ascii(\"  spaced  \"));\n    println!(\"省略规则 3: 输出绑定 &self, 与临时 key 无关\");\n}\n",
    "output": "lookup(name) = Some(\"Rust\")\ntrim = \"spaced\"\n省略规则 3: 输出绑定 &self, 与临时 key 无关\n",
    "pitfalls": [
        "以为多输入就能省略：无 self 且有多个输入引用时输出无法推断，必须手写 `'a`。",
        "误解方法返回绑到 key：规则 3 把输出绑到 `&self`，key 可以更短命。",
        "在 `&self` 方法上仍手写生命周期：能省略就省略，手写反而增加出错机会。"
    ],
    "exercise": {
        "prompt": "写一个 `struct Text<'a> { body: &'a str }` 和 `impl`，实现 `fn longest_line(&self) -> &'a str`（返回最长的一行，生命周期随 body），在 main 中打印结果。",
        "hint": "用 `self.body.lines().max_by_key(|l| l.len()).unwrap_or(self.body)`；返回 `&'a str` 说明来自 body。",
        "answer": "struct Text<'a> {\n    body: &'a str,\n}\n\nimpl<'a> Text<'a> {\n    fn new(body: &'a str) -> Self {\n        Text { body }\n    }\n\n    fn longest_line(&self) -> &'a str {\n        self.body.lines().max_by_key(|l| l.len()).unwrap_or(self.body)\n    }\n}\n\nfn main() {\n    let doc = \"short\\na much longer line\\nmid\";\n    let t = Text::new(doc);\n    println!(\"{}\", t.longest_line());\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 42,
    "title": "`'static` 与字符串字面量",
    "level": "advanced",
    "domain": "ownership-borrowing",
    "summary": "理解 `'static` 意味着“活到程序结束”，区分静态生命周期与静态变量，避免滥用 `'static` 约束。",
    "concepts": ["'static", "字符串字面量", "常量传播", "trait 对象默认生命周期", "泄漏 lease"],
    "objective": "能解释字符串字面量为何是 `&'static str`，并判断何时不该要求 `'static`。",
    "prerequisites": ["041", "039"],
    "explain": "`'static` 是最长的生命周期：引用在整个程序运行期有效。字符串字面量被编译进二进制只读段，因此是 `&'static str`；`static` 变量本身也有 `'static` 地址。注意 `'static` 描述的是引用有效期，不是变量可变性——一个 `&'static T` 仍可指向内部可变的值。常见误用是在结构体或函数上硬性要求 `'static`，这会让调用方无法传入临时数据，应改为泛型生命周期 `<'a>`。`Box<dyn Trait>` 默认是 `Box<dyn Trait + 'static>`，即 trait 对象内部不借任何短命数据；若要允许借短命数据需写 `Box<dyn Trait + 'a>`。稳定引用可以用 `Box::leak` 或 `String::leak` 得到 `&'static mut`，但这会永久占用内存，仅在初始化一次的场景可接受。",
    "code": "static APP_NAME: &str = \"qfli\";\n\nfn greeting(name: &str) -> String {\n    format!(\"欢迎使用 {}，{}!\", APP_NAME, name)\n}\n\n// 返回 'static 引用: 允许，因为字面量活到程序结束\nfn default_role() -> &'static str {\n    \"guest\"\n}\n\nstruct Holder {\n    label: &'static str,\n}\n\nfn main() {\n    let literal: &'static str = \"compile-time\";\n    println!(\"literal len = {}\", literal.len());\n    println!(\"default_role = {}\", default_role());\n    let holder = Holder { label: default_role() };\n    println!(\"holder.label = {}\", holder.label);\n\n    // 把 String 泄漏成 'static（仅初始化一次时使用）\n    let leaked: &'static str = Box::leak(String::from(\"leaked\").into_boxed_str());\n    println!(\"leaked = {}\", leaked);\n    let _ = greeting(literal);\n}\n",
    "output": "literal len = 12\ndefault_role = guest\nholder.label = guest\nleaked = leaked\n",
    "pitfalls": [
        "把 `'static` 当“全局/可变”：它只表示引用的有效期，不代表值不可变或一定在全局。",
        "在函数上强制 `&'static str` 参数：会拒绝临时字符串，应用泛型生命周期。",
        "滥用 `Box::leak`：泄漏的内存不会回收，只有刻意要做常驻单例时才用。"
    ],
    "exercise": {
        "prompt": "写函数 `fn pick_static() -> &'static [&'static str]` 返回一个固定的语言名数组，并在 main 中遍历打印。",
        "hint": "用 `static LANGS: [&str; 3] = [...]` 再返回 `&LANGS` 切片。",
        "answer": "static LANGS: [&str; 3] = [\"Rust\", \"C\", \"Python\"];\n\nfn pick_static() -> &'static [&'static str] {\n    &LANGS\n}\n\nfn main() {\n    for lang in pick_static() {\n        println!(\"{}\", lang);\n    }\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 43,
    "title": "切片 API 与借用拆分",
    "level": "intermediate",
    "domain": "ownership-borrowing",
    "summary": "用 `iter`/`iter_mut`/`chunks`/`windows`/`split_at` 在借用视角下处理数据，避免索引与所有权冲突。",
    "concepts": ["iter", "iter_mut", "chunks", "windows", "split_at_mut"],
    "objective": "能优先用切片 API 表达遍历与分段，减少手写索引带来的越界与借用问题。",
    "prerequisites": ["037"],
    "explain": "切片 API 是借用友好的一等工具：`iter()` 给出 `&T`，`iter_mut()` 给出 `&mut T`，`chunks(k)` 给不重叠块，`windows(k)` 给滑动窗口，`split_at(i)`/`split_at_mut(i)` 把切片一分为二（后者的两个可变借用互不重叠，是安全的拆分手段）。用这些 API 时借用关系由库保证，通常比手写 `for i in 0..len { &mut xs[i] }` 更清晰也更难出错。`iter_mut` 通常配合 `*x = ...` 或 `x.method_mut()`。`chunks_mut` 能同时安全地可变遍历多个块。要同时读一块、写另一块时，`split_at_mut` 是标准解法。注意 `windows`/`chunks` 返回的是切片迭代器，元素本身就是 `&[T]`，直接借用不必再取地址。这些 API 让“先取索引再修改”的绕路写法大幅减少。",
    "code": "fn moving_average(xs: &[f64], window: usize) -> Vec<f64> {\n    if window == 0 {\n        return Vec::new();\n    }\n    xs.windows(window)\n        .map(|w| w.iter().sum::<f64>() / window as f64)\n        .collect()\n}\n\nfn main() {\n    let data = [1.0, 2.0, 3.0, 4.0, 5.0];\n    println!(\"avg(2) = {:?}\", moving_average(&data, 2));\n\n    let mut buf = [1, 2, 3, 4, 5, 6];\n    for chunk in buf.chunks_mut(2) {\n        for v in chunk.iter_mut() {\n            *v *= 10;\n        }\n    }\n    println!(\"chunks_mut -> {:?}\", buf);\n\n    let (left, right) = buf.split_at_mut(3);\n    left[0] = 999;\n    right[0] = 888;\n    println!(\"split_at_mut -> {:?}\", buf);\n}\n",
    "output": "avg(2) = [1.5, 2.5, 3.5, 4.5]\nchunks_mut -> [10, 20, 30, 40, 50, 60]\nsplit_at_mut -> [999, 20, 30, 888, 50, 60]\n",
    "pitfalls": [
        "window 为 0 导致 `windows(0)` panic：必须先校验窗口大小。",
        "手写 `&mut xs[i]` 循环：容易触发借用冲突，优先用 `iter_mut`/`chunks_mut`。",
        "`chunks` 最后一块可能更短：聚合时要注意不能假设每块都等长。"
    ],
    "exercise": {
        "prompt": "写函数 `pairwise_max(xs: &[i32]) -> Vec<i32>` 用 `windows(2)` 返回相邻两元素的最大值序列，并在 main 中测试 `[3,1,4,1,5]`。",
        "hint": "`xs.windows(2).map(|w| w[0].max(w[1])).collect()`。",
        "answer": "fn pairwise_max(xs: &[i32]) -> Vec<i32> {\n    xs.windows(2).map(|w| w[0].max(w[1])).collect()\n}\n\nfn main() {\n    println!(\"{:?}\", pairwise_max(&[3, 1, 4, 1, 5]));\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 44,
    "title": "可变借用的独占性与别名禁令",
    "level": "advanced",
    "domain": "ownership-borrowing",
    "summary": "理解同一时刻只能有一个可变借用，从编译期消除别名导致的数据竞争。",
    "concepts": ["独占借用", "别名", "数据竞争", "E0499", "重新借用"],
    "objective": "能解释为什么“两个 &mut 指向同一数据”被禁止，并用重新借用或作用域拆分解决。",
    "prerequisites": ["037"],
    "explain": "可变借用是独占的：同一作用域内对同一数据只能存在一个 `&mut`，且不能与任何 `&` 共存。这条规则在单线程下消除了别名写写、读写竞争；在并发下它也是 `Mutex`/线程安全的基础。编译器报 E0499（cannot borrow as mutable more than once）时，通常是同时持有两个 `&mut`，或在一个 `&mut` 仍存活时又借了一次。正确做法：让前一个借用提前结束（NLL 推动），或使用“重新借用”：函数参数 `&mut T` 在调用其它函数时会自动重新借用而非移动，例如在持有 `&mut Vec` 的方法里连续调用 `v.push(...)`。另一种模式是分阶段：先取出需要的索引/值，再把可变借用交给下一步。必要时用 `split_at_mut` 把一个大切片拆成两个不重叠的可变借用。",
    "code": "fn fill_and_sum(values: &mut Vec<i32>, n: i32) -> i32 {\n    // 重新借用：values 仍是同一个 &mut，push 时自动 reborrow\n    for i in 1..=n {\n        values.push(i);\n    }\n    values.iter().sum()\n}\n\nfn swap_ends(values: &mut [i32]) {\n    // split_at_mut 得到两个不重叠的可变借用\n    if values.len() >= 2 {\n        let mid = values.len() / 2;\n        let (left, right) = values.split_at_mut(mid);\n        std::mem::swap(&mut left[0], &mut right[right.len() - 1]);\n    }\n}\n\nfn main() {\n    let mut data = Vec::new();\n    let sum = fill_and_sum(&mut data, 5);\n    println!(\"sum = {}, data = {:?}\", sum, data);\n\n    swap_ends(&mut data);\n    println!(\"after swap_ends = {:?}\", data);\n}\n",
    "output": "sum = 15, data = [1, 2, 3, 4, 5]\nafter swap_ends = [5, 2, 3, 4, 1]\n",
    "pitfalls": [
        "同时保留两个 `&mut`：编译报 E0499，需让其中一个提前结束或改用 split 方案。",
        "把 `&mut` 当可复制：可变引用自身是不可 Copy 的，传参是移动（除非重新借用）。",
        "误用 `mem::swap` 交换同一元素：同一切片内两个索引需要 split 后才能安全获得可变借用。"
    ],
    "exercise": {
        "prompt": "写函数 `double_first(values: &mut Vec<i32>)` 把第一个元素翻倍（若存在），并在 main 中调用后打印向量。",
        "hint": "`if let Some(first) = values.first_mut() { *first *= 2; }`。",
        "answer": "fn double_first(values: &mut Vec<i32>) {\n    if let Some(first) = values.first_mut() {\n        *first *= 2;\n    }\n}\n\nfn main() {\n    let mut v = vec![7, 8, 9];\n    double_first(&mut v);\n    println!(\"{:?}\", v);\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 45,
    "title": "迭代式修改：借用与索引的取舍",
    "level": "intermediate",
    "domain": "ownership-borrowing",
    "summary": "比较 `iter_mut` 就地修改与“先收集索引再索引修改”两种模式，理解各自的借用含义与性能。",
    "concepts": ["iter_mut", "索引修改", "retain", "借用冲突", "中间收集"],
    "objective": "能根据“是否需要跨元素判断/删除/重排”选择就地迭代或索引模式。",
    "prerequisites": ["043"],
    "explain": "就地修改用 `for x in v.iter_mut()` 或 `v.iter_mut().for_each(...)`，语义是“每个元素独立变换”，借用清晰、无越界风险。需要根据兄弟元素决定当前元素（如去重、滑动依赖）时，往往要先读取再修改，此时不能同时持有整段的只读与可变借用；标准解法是先把需要的值/索引收集成临时集合（`Vec<usize>`/`Vec<T>`），借用结束后再修改。删除元素优先用 `retain`（原地、单次遍历）或 `drain`，它们能避免手写索引与搬移。需要按条件替换用 `iter_mut().zip`。索引写法的代价是每次越界检查与潜在 panic，以及更容易触发借用冲突；但当算法本质是随机访问（例如原地快排分区）时，索引配合 `split_at_mut` 反而更自然。原则：能用迭代器表达意图就别手写索引，只有随机访问模式才退回索引。",
    "code": "fn normalize(values: &mut [f64]) {\n    let max = values.iter().copied().fold(f64::MIN, f64::max);\n    if max == 0.0 {\n        return;\n    }\n    // 先读取 max（不可变借用结束），再可变借用整体\n    for v in values.iter_mut() {\n        *v /= max;\n    }\n}\n\nfn dedup_keep_order(values: &mut Vec<i32>) {\n    let mut seen = std::collections::HashSet::new();\n    values.retain(|v| seen.insert(*v));\n}\n\nfn main() {\n    let mut data = [2.0, 4.0, 8.0];\n    normalize(&mut data);\n    println!(\"normalized = {:?}\", data);\n\n    let mut numbers = vec![1, 2, 1, 3, 2, 4];\n    dedup_keep_order(&mut numbers);\n    println!(\"deduped = {:?}\", numbers);\n}\n",
    "output": "normalized = [0.25, 0.5, 1.0]\ndeduped = [1, 2, 3, 4]\n",
    "pitfalls": [
        "在遍历中删除元素：会使迭代器失效或触发借用冲突，应改用 `retain`。",
        "把整段只读借用与 `iter_mut` 混用：先算好需要的聚合值（如 max），再进入可变阶段。",
        "误以为 retain 保留条件与直觉相反：`retain` 保留闭包返回 true 的元素。"
    ],
    "exercise": {
        "prompt": "写函数 `clamp_to_range(values: &mut Vec<i32>, lo: i32, hi: i32)` 用 `iter_mut` 把每个元素限制到 [lo, hi]，并在 main 中测试含越界值的向量。",
        "hint": "`for v in values.iter_mut() { *v = (*v).clamp(lo, hi); }`。",
        "answer": "fn clamp_to_range(values: &mut Vec<i32>, lo: i32, hi: i32) {\n    for v in values.iter_mut() {\n        *v = (*v).clamp(lo, hi);\n    }\n}\n\nfn main() {\n    let mut v = vec![-5, 3, 12, 7, 99];\n    clamp_to_range(&mut v, 0, 10);\n    println!(\"{:?}\", v);\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 46,
    "title": "`split_at_mut` 与安全拆分借用",
    "level": "advanced",
    "domain": "ownership-borrowing",
    "summary": "用 `split_at_mut` 在安全 Rust 中得到两个互不重叠的可变借用，理解它为何不违反独占规则。",
    "concepts": ["split_at_mut", "不重叠借用", "内部 unsafe", "边界校验", "安全抽象"],
    "objective": "能用 split_at_mut 或迭代器组合替代“同一容器两个可变借用”的非法写法。",
    "prerequisites": ["044"],
    "explain": "对同一 Vec 想要两个 `&mut` 通常是非法的，但若两个借用指向互不重叠的子区间，就是安全的。标准库提供 `split_at_mut(i)` 返回 `(&mut [T], &mut [T])`：它内部用 unsafe 断言两段不重叠，从而在安全接口下给出两个可变借用。还有 `split_first_mut`、`split_last_mut`、`chunks_mut`、`iter_mut().zip()` 等组合。典型场景是“拿两个不同元素做交换、合并、双指针分区、滑动窗口两端同时改”。若你的算法需要随时按任意两个索引取可变引用，且无法用上述 API 表达，才可能需要 unsafe 并自己证明不重叠——但通常都能用安全 API 重构。理解 `split_at_mut` 也是理解“为什么有些 unsafe 是必要的、但接口可以安全”的绝佳例子：不变量由库维护，使用者只需遵守下标约束。",
    "code": "fn swap_two(values: &mut [i32], i: usize, j: usize) {\n    if i == j || i >= values.len() || j >= values.len() {\n        return;\n    }\n    if i < j {\n        let (left, right) = values.split_at_mut(j);\n        std::mem::swap(&mut left[i], &mut right[0]);\n    } else {\n        let (left, right) = values.split_at_mut(i);\n        std::mem::swap(&mut left[j], &mut right[0]);\n    }\n}\n\nfn pairwise_double(values: &mut Vec<i32>) {\n    // 用 zip 把相邻两个不重叠的可变引用配成对\n    let mut it = values.iter_mut();\n    while let (Some(a), Some(b)) = (it.next(), it.next()) {\n        *a *= 2;\n        *b *= 2;\n    }\n}\n\nfn main() {\n    let mut data = [1, 2, 3, 4, 5];\n    swap_two(&mut data, 0, 4);\n    println!(\"swapped = {:?}\", data);\n\n    let mut nums = vec![1, 2, 3, 4, 5];\n    pairwise_double(&mut nums);\n    println!(\"doubled = {:?}\", nums);\n}\n",
    "output": "swapped = [5, 2, 3, 4, 1]\ndoubled = [2, 4, 6, 8, 5]\n",
    "pitfalls": [
        "split_at_mut 下标越界：会 panic，调用前必须校验 `i <= len`。",
        "以为 split 后两半能重叠：它们必然不重叠，算法必须尊重这个前提。",
        "为了两个可变借用直接上 unsafe：多数情况能用 split/zip/chunks 安全表达，先尝试标准 API。"
    ],
    "exercise": {
        "prompt": "写函数 `swap_halves(values: &mut [i32])` 把前半与后半逐位交换（长度取较短者），用 split_at_mut 实现，并在 main 中测试 `[1,2,3,4,5,6]`。",
        "hint": "`let (l, r) = values.split_at_mut(values.len()/2);` 再 `for (a, b) in l.iter_mut().zip(r.iter_mut()) { swap }`。",
        "answer": "fn swap_halves(values: &mut [i32]) {\n    let mid = values.len() / 2;\n    let (left, right) = values.split_at_mut(mid);\n    for (a, b) in left.iter_mut().zip(right.iter_mut()) {\n        std::mem::swap(a, b);\n    }\n}\n\nfn main() {\n    let mut v = [1, 2, 3, 4, 5, 6];\n    swap_halves(&mut v);\n    println!(\"{:?}\", v);\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 47,
    "title": "生命周期与返回引用：常见错误修复",
    "level": "advanced",
    "domain": "ownership-borrowing",
    "summary": "汇总返回引用时的典型编译错误，并给出“借用入参/返回拥有型/改结构”三类修复思路。",
    "concepts": ["返回引用", "E0515", "拥有型返回值", "借用入参", "重构策略"],
    "objective": "面对返回引用的报错，能判断是改为返回拥有型、绑定入参生命周期，还是调整数据归属。",
    "prerequisites": ["040", "039"],
    "explain": "返回引用时的常见错误有三类。其一，E0515「返回局部变量引用」：函数内部创建的 String/Vec 在结束时释放，返回其切片非法——修复是返回拥有型值（String/Vec）或改为接收外部数据并借用它。其二，E0106「缺少生命周期标注」：多个引用输入时编译器无法确定返回来自谁——修复是标注 `'a` 把输出绑定到正确输入。其三，结构体自引用：想同时拥有数据与指向它的引用，这在安全 Rust 中不允许，需改用索引、`Rc`+`Weak`、或把两者拆开。另一类常被忽视的坑是**按字节切片多字节字符串**：`&text[start..]` 的 `start` 必须落在 UTF-8 字符边界，否则运行时 panic；`text.len() - n` 这类“按字节数取尾部”的做法在中文等文本上会出错，应按 `chars()`/`char_indices()` 换算。通用策略：先问“这个引用的数据属于谁、活多久”，如果答案在函数外，就让签名接收该借用的生命周期；如果答案在函数内，就返回拥有型；如果需要长期持有且跨调用，考虑拥有数据或在结构里用索引引用。避免无脑 clone 作为默认修复。",
    "code": "// 错误示范（不可编译）: fn bad() -> &str { &String::from(\"x\") }\n// 修复 1: 返回拥有型\nfn owned_upper(text: &str) -> String {\n    text.to_uppercase()\n}\n\n// 修复 2: 把输出生命周期绑定到入参。\n// 注意：这里按**字符**而不是字节取尾部，避免在多字节 UTF-8（如中文）上 panic。\nfn tail<'a>(text: &'a str, n: usize) -> &'a str {\n    let count = text.chars().count();\n    if n >= count {\n        return text;\n    }\n    let cut = count - n;\n    // char_indices 给出每个字符的字节边界，切点必然落在边界上\n    let byte_idx = text.char_indices().nth(cut).map(|(i, _)| i).unwrap_or(text.len());\n    &text[byte_idx..]\n}\n\n// 修复 3: 结构体改为持有索引而非引用（避免自引用）\nstruct LineIndex {\n    offsets: Vec<usize>,\n}\n\nimpl LineIndex {\n    fn build(text: &str) -> Self {\n        let mut offsets = vec![0];\n        for (i, b) in text.bytes().enumerate() {\n            if b == b'\\n' {\n                offsets.push(i + 1);\n            }\n        }\n        LineIndex { offsets }\n    }\n\n    fn line<'a>(&self, text: &'a str, idx: usize) -> Option<&'a str> {\n        let start = *self.offsets.get(idx)?;\n        let end = self.offsets.get(idx + 1).copied().unwrap_or(text.len());\n        Some(&text[start..end].trim_end_matches('\\n'))\n    }\n}\n\nfn main() {\n    println!(\"owned_upper = {}\", owned_upper(\"abc\"));\n    println!(\"tail = {}\", tail(\"abcdef\", 3));\n    println!(\"tail(cn) = {}\", tail(\"你好世界\", 2));\n\n    let doc = \"alpha\\nbeta\\ngamma\";\n    let index = LineIndex::build(doc);\n    println!(\"line(1) = {:?}\", index.line(doc, 1));\n}\n",
    "output": "owned_upper = ABC\ntail = def\ntail(cn) = 世界\nline(1) = Some(\"beta\")\n",
    "pitfalls": [
        "返回局部值引用：E0515，直接改为返回拥有型或改为借用入参。",
        "硬要结构体同时存数据和引用：安全 Rust 禁止自引用，改用索引或 Rc/Weak。",
        "用 clone 作为万能修复：会掩盖真正的所有权设计问题，先分析数据归属。",
        "对字符串按字节切片：`&text[start..]` 的 start 必须落在 UTF-8 字符边界，否则运行时会 panic；中文等多字节文本应先按 `chars()`/`char_indices()` 换算边界（本课 tail 已改为按字符取尾）。"
    ],
    "exercise": {
        "prompt": "写函数 `repeat_until_len(text: &str, min: usize) -> String`，把 text 重复拼接直到长度不小于 min（超出保留），返回拥有型字符串；在 main 中测试。",
        "hint": "先 `let mut out = String::new();` 循环 `while out.len() < min { out.push_str(text); }`，注意空 text 时避免死循环。",
        "answer": "fn repeat_until_len(text: &str, min: usize) -> String {\n    let mut out = String::new();\n    if text.is_empty() {\n        return out;\n    }\n    while out.len() < min {\n        out.push_str(text);\n    }\n    out\n}\n\nfn main() {\n    println!(\"{:?}\", repeat_until_len(\"ab\", 5));\n    println!(\"{:?}\", repeat_until_len(\"\", 5));\n}\n"
    },
    "runtime": "desktop"
},
]
