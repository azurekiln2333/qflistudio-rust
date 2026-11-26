# -*- coding: utf-8 -*-
"""Lessons 048..052 (Domain C, part 3: interior mutability preview, collections, Cow, capstone)."""

LESSONS = [
{
    "id": 48,
    "title": "内部可变性预告：为何需要 `RefCell`",
    "level": "advanced",
    "domain": "ownership-borrowing",
    "summary": "用 `Cell` 先感受“在共享引用下也能修改”的需求，理解内部可变性是借用规则的可控逃生门。",
    "concepts": ["内部可变性", "Cell", "RefCell 预告", "共享引用下修改", "运行时借用检查"],
    "objective": "能说明普通 `&T` 下为何不能改值，以及 `Cell<T>` 如何在不破坏类型安全的前提下允许修改。",
    "prerequisites": ["044"],
    "explain": "普通规则要求修改必须拿 `&mut T`，但有些设计（缓存、计数器、观察者）希望在只有 `&self` 时也能更新内部状态——这就是内部可变性（interior mutability）。`Cell<T>` 的 `set`/`replace`/`into_inner` 对**任意** `T` 可用，`take` 需要 `T: Default`（它把内部值取走并留下 `T::default()`）；只有 `get` 要求 `T: Copy`，因为它按值复制出来而无法移动内部值，非 `Copy` 时改用 `take`（留下 `Default`）或 `replace`。它通过按值存取绕过借用检查且从不泄漏内部引用。`RefCell<T>`（下一域详讲）给出 `borrow()`/`borrow_mut()`，把借用检查从编译期推迟到运行时，违反时 panic。二者的安全性都来自“不产生对内部数据的悬垂引用”这一不变量。内部可变性不是绕开设计，而是把“同一逻辑单元的状态”集中到一个可控点。用它时要问：这个状态真的需要共享修改吗？能否改成显式传 `&mut` 更清晰？滥用内部可变性会让借用错误的定位从编译期变到运行期。",
    "code": "use std::cell::Cell;\n\nstruct HitCounter {\n    count: Cell<u32>,\n}\n\nimpl HitCounter {\n    fn new() -> Self {\n        HitCounter { count: Cell::new(0) }\n    }\n\n    // 接收 &self，却仍能修改内部计数\n    fn hit(&self) -> u32 {\n        let next = self.count.get() + 1;\n        self.count.set(next);\n        next\n    }\n\n    fn value(&self) -> u32 {\n        self.count.get()\n    }\n}\n\nfn main() {\n    let counter = HitCounter::new();\n    println!(\"hit1 = {}\", counter.hit());\n    println!(\"hit2 = {}\", counter.hit());\n    println!(\"value = {}\", counter.value());\n    println!(\"&self 下修改靠内部可变性, Cell 只适用 Copy 类型\");\n}\n",
    "output": "hit1 = 1\nhit2 = 2\nvalue = 2\n&self 下修改靠内部可变性, Cell 只适用 Copy 类型\n",
    "pitfalls": [
        "对非 Copy 类型用 Cell：`get` 需要复制，非 Copy 只能用 `take`/`replace`，或改用 RefCell。",
        "把内部可变性当默认：多数状态更适合显式 `&mut self`，只有共享语义真需要时才用。",
        "以为 Cell 没有开销：它确实很轻，但仍会限制优化（无法把值放寄存器），不要滥用。"
    ],
    "exercise": {
        "prompt": "用 `Cell<i64>` 实现 `struct Accumulator { total: Cell<i64> }`，提供 `add(&self, v: i64)` 与 `total(&self) -> i64`，在 main 中累加 3、4、5 并打印总和。",
        "hint": "`add` 里 `self.total.set(self.total.get() + v);`。",
        "answer": "use std::cell::Cell;\n\nstruct Accumulator {\n    total: Cell<i64>,\n}\n\nimpl Accumulator {\n    fn new() -> Self {\n        Accumulator { total: Cell::new(0) }\n    }\n\n    fn add(&self, v: i64) {\n        self.total.set(self.total.get() + v);\n    }\n\n    fn total(&self) -> i64 {\n        self.total.get()\n    }\n}\n\nfn main() {\n    let acc = Accumulator::new();\n    for v in [3, 4, 5] {\n        acc.add(v);\n    }\n    println!(\"{}\", acc.total());\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 49,
    "title": "所有权在集合中的传播",
    "level": "intermediate",
    "domain": "ownership-borrowing",
    "summary": "理解容器拥有其元素，插入/移出如何转移所有权，以及 `entry` API 与迭代如何借用元素。",
    "concepts": ["容器所有权", "插入移动", "entry API", "remove 返回所有权", "迭代借用"],
    "objective": "能预测向 Vec/HashMap 插入、从其中取出时所有权的去向，并选择合适的迭代方式。",
    "prerequisites": ["045"],
    "explain": "容器拥有其元素。向 `Vec`/`HashMap` 插入拥有型值（String）会把所有权交给容器；从容器取出（`remove`、`pop`、`into_iter`）会把所有权交回调用者。容器上的集合操作通过借用进行：`contains`/`get` 借用，`iter` 产生 `&T`，`iter_mut` 产生 `&mut T`。`HashMap::entry` 是高效模式：`map.entry(key).or_insert_with(...)` **按值取得 key 的所有权**（key 会被移动进 map，若需要保留请先 `clone` 或改为先 `get`），并在一次查找内完成“查/插”，避免“先查再插”的两次查找。迭代方式决定所有权：`for x in v` 消费集合、`for x in &v` 借用不可变、`for x in &mut v` 借用可变。`HashMap::remove` 会**删除整个条目**（键和值一起移除，不会留下空洞或 `None` 槽位），它返回 `Option<V>` 只是因为“该键可能本就不存在”；`Vec` 同理没有空洞，`pop` 直接把末尾元素移出。设计 API 时，用 `&` 接收容器，除非确实要消费它。",
    "code": "use std::collections::HashMap;\n\nfn count_words(text: &str) -> HashMap<&str, usize> {\n    let mut counts = HashMap::new();\n    for word in text.split_whitespace() {\n        // entry API: 借用 key，需要时才插入\n        *counts.entry(word).or_insert(0) += 1;\n    }\n    counts\n}\n\nfn main() {\n    // 插入转移所有权\n    let mut owned: Vec<String> = Vec::new();\n    let name = String::from(\"rust\");\n    owned.push(name); // name 被移动\n    println!(\"owned = {:?}\", owned);\n\n    // remove 把所有权交回\n    let taken: Option<String> = owned.pop();\n    println!(\"taken = {:?}, owned = {:?}\", taken, owned);\n\n    let counts = count_words(\"a b a c a b\");\n    let mut pairs: Vec<(&str, usize)> = counts.into_iter().collect();\n    pairs.sort();\n    for (word, n) in pairs {\n        println!(\"{}: {}\", word, n);\n    }\n}\n",
    "output": "owned = [\"rust\"]\ntaken = Some(\"rust\"), owned = []\na: 3\nb: 2\nc: 1\n",
    "pitfalls": [
        "先在循环外借用 key 再插入：会与插入所需的所有权转移冲突，用 `entry` 更顺。",
        "以为 `for x in &map` 能拿到键值对所有权：它给的是 `(&K, &V)`，所有权仍在容器。",
        "用 `get` 后直接改值：需要 `get_mut` 或 `entry`，`get` 只给不可变借用。"
    ],
    "exercise": {
        "prompt": "写函数 `group_by_len(words: &[String]) -> HashMap<usize, Vec<String>>`，按单词长度分组（克隆字符串进结果），在 main 中打印每组的排序结果。",
        "hint": "遍历 `words`，用 `map.entry(w.len()).or_default().push(w.clone())`；打印前对每组 sort。",
        "answer": "use std::collections::HashMap;\n\nfn group_by_len(words: &[String]) -> HashMap<usize, Vec<String>> {\n    let mut groups: HashMap<usize, Vec<String>> = HashMap::new();\n    for w in words {\n        groups.entry(w.len()).or_default().push(w.clone());\n    }\n    groups\n}\n\nfn main() {\n    let words = vec![\n        String::from(\"a\"), String::from(\"bb\"), String::from(\"cc\"), String::from(\"ddd\"),\n    ];\n    let mut groups = group_by_len(&words);\n    let mut keys: Vec<usize> = groups.keys().copied().collect();\n    keys.sort();\n    for k in keys {\n        let list = groups.get_mut(&k).unwrap();\n        list.sort();\n        println!(\"len {} -> {:?}\", k, list);\n    }\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 50,
    "title": "`Cow` 与按需借用",
    "level": "advanced",
    "domain": "ownership-borrowing",
    "summary": "用 `Cow<'a, str>` 表达“通常借用、必要时才拥有”，在字符串处理中避免不必要的分配。",
    "concepts": ["Cow", "Borrowed/Owned", "按需分配", "into_owned", "as_ref"],
    "objective": "能用 Cow 写出“无需修改就借用、需要修改才克隆”的函数，并解释它何时零成本。",
    "prerequisites": ["042"],
    "explain": "`std::borrow::Cow<'a, B>` 是“克隆写（clone-on-write）”枚举：`Cow::Borrowed(&'a B)` 借用、`Cow::Owned(B)` 拥有。它适合“输入往往无需改动、偶尔才需要规范化”的场景：函数返回 `Cow<'a, str>`，无改动时直接返回借用（零分配），有改动时返回 `Owned`。使用方通过 `as_ref()` 得到 `&str`（经 Deref 也能直接当 `&str` 用），用 `into_owned()` 拿到拥有型；`to_mut()` 在需要修改时把借用转成拥有型。Cow 的代价是引入一层枚举分支与类型复杂度，因此只在收益明显（避免频繁分配、API 需要统一返回类型）时使用。它是标准库中“按需分配”思想的代表，也是许多解析/规范化函数的高效签名选择。注意 `Cow<str>` 可实现 `Deref<Target = str>`，所以大多数字符串方法可直接调用。",
    "code": "use std::borrow::Cow;\n\nfn normalize(text: &str) -> Cow<'_, str> {\n    if text.contains('\\t') {\n        // 需要修改：产生拥有型\n        let replaced = text.replace('\\t', \"    \");\n        Cow::Owned(replaced)\n    } else {\n        // 无需修改：零成本借用\n        Cow::Borrowed(text)\n    }\n}\n\nfn main() {\n    let clean = \"no tabs here\";\n    let dirty = \"a\\tb\\tc\";\n\n    let n1 = normalize(clean);\n    let n2 = normalize(dirty);\n    println!(\"n1 = {:?} borrowed={}\", n1, matches!(n1, Cow::Borrowed(_)));\n    println!(\"n2 = {:?} owned={}\", n2, matches!(n2, Cow::Owned(_)));\n    println!(\"长度: {} vs {}\", n1.len(), n2.len());\n}\n",
    "output": "n1 = \"no tabs here\" borrowed=true\nn2 = \"a    b    c\" owned=true\n长度: 12 vs 11\n",
    "pitfalls": [
        "以为 Cow 总是零成本：只有走 Borrowed 分支才省分配，Ow​​ned 分支仍会克隆。",
        "在 Cow 上直接需要可变：要用 `to_mut()`，它会在必要时把借用升级为拥有。",
        "到处用 Cow 增加复杂度：收益不明显时用 `&str` 或 `String` 更直白。"
    ],
    "exercise": {
        "prompt": "写函数 `trim_or_borrow(text: &str) -> Cow<'_, str>`：若首尾有空白则返回去除后的拥有型，否则借用原样；在 main 中用两种输入测试并打印类型标记。",
        "hint": "`if text.trim() != text { Cow::Owned(text.trim().to_string()) } else { Cow::Borrowed(text) }`。",
        "answer": "use std::borrow::Cow;\n\nfn trim_or_borrow(text: &str) -> Cow<'_, str> {\n    let trimmed = text.trim();\n    if trimmed != text {\n        Cow::Owned(trimmed.to_string())\n    } else {\n        Cow::Borrowed(text)\n    }\n}\n\nfn main() {\n    let a = trim_or_borrow(\"clean\");\n    let b = trim_or_borrow(\"  padded  \");\n    println!(\"{:?} borrowed={}\", a, matches!(a, Cow::Borrowed(_)));\n    println!(\"{:?} owned={}\", b, matches!(b, Cow::Owned(_)));\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 51,
    "title": "借用检查器实战：重构一段报错代码",
    "level": "advanced",
    "domain": "ownership-borrowing",
    "summary": "面对“同时只读与可变”的真实冲突，演示拆解问题、逐步重构到通过编译的完整过程。",
    "concepts": ["重构", "借用冲突", "分阶段处理", "索引收集", "代码演进"],
    "objective": "能把一段会报借用错误的“找出并修改最大元素”逻辑重构成安全且高效的版本。",
    "prerequisites": ["047", "045"],
    "explain": "典型冲突场景：想在遍历时找到最大元素并就地修改它，直觉写法 `let max = values.iter().max(); ... values[i] *= 2;` 会同时持有一个指向元素的引用和整段可变借用。重构步骤：1) 只读阶段先算出需要的“位置信息”（最大值的索引）而非引用，结束不可变借用；2) 可变阶段用索引或 `iter_mut` 修改；3) 若需要根据其他元素决定修改目标，先把决策所需的数据提取为拥有的小结构（索引、比较键）。另一类冲突来自“把元素移出容器又继续用容器”，此时用 `remove`/`mem::take`/`Option::take` 明确转移。核心心法：把“读”和“写”分成两个清晰的阶段，中间只传递值/索引。这样不仅让借用检查器满意，通常也让逻辑更易读——借用的困难往往映射着职责混杂。",
    "code": "// 目标: 找到绝对值最大的元素并把它翻倍。\n// 直接同时读写会冲突，这里分两阶段。\n\nfn double_max_abs(values: &mut [i32]) -> Option<usize> {\n    // 只读阶段: 只记录索引，不保留引用\n    let target = values\n        .iter()\n        .enumerate()\n        .max_by_key(|(_, v)| v.abs())\n        .map(|(i, _)| i)?;\n\n    // 可变阶段: 用索引修改，只读借用已结束\n    values[target] *= 2;\n    Some(target)\n}\n\nfn main() {\n    let mut data = [-3, 7, -9, 2];\n    let idx = double_max_abs(&mut data);\n    println!(\"idx = {:?}, data = {:?}\", idx, data);\n\n    let empty: &mut [i32] = &mut [];\n    println!(\"empty -> {:?}\", double_max_abs(empty));\n}\n",
    "output": "idx = Some(2), data = [-3, 7, -18, 2]\nempty -> None\n",
    "pitfalls": [
        "在只读阶段把元素引用带进可变阶段：应改为传递索引或值。",
        "用 clone 整段数据绕过冲突：分阶段通常无需任何复制。",
        "忘记空切片：`max_by_key` 返回 None，用 `?` 向上传播更安全。"
    ],
    "exercise": {
        "prompt": "写函数 `bump_first_negative(values: &mut [i32]) -> bool`，若存在负数则把第一个负数加 100 并返回 true，否则返回 false。分两阶段实现，在 main 中测试含负数与全正数两种输入。",
        "hint": "只读阶段用 `values.iter().position(|v| *v < 0)`；得到索引后再 `values[i] += 100`。",
        "answer": "fn bump_first_negative(values: &mut [i32]) -> bool {\n    match values.iter().position(|v| *v < 0) {\n        Some(i) => {\n            values[i] += 100;\n            true\n        }\n        None => false,\n    }\n}\n\nfn main() {\n    let mut a = [1, -5, 3];\n    println!(\"{}, {:?}\", bump_first_negative(&mut a), a);\n    let mut b = [2, 4, 6];\n    println!(\"{}, {:?}\", bump_first_negative(&mut b), b);\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 52,
    "title": "实战：不带依赖的词频统计（借用优化版）",
    "level": "advanced",
    "domain": "ownership-borrowing",
    "summary": "综合借用、切片、HashMap 与排序，实现一个尽量少复制的词频统计并输出确定顺序的结果。",
    "concepts": ["综合应用", "HashMap<&str, usize>", "借用 key", "确定性排序", "Cow"],
    "objective": "能写出借用地引用输入并输出稳定顺序的词频统计，理解如何避免不必要的字符串克隆。",
    "prerequisites": ["049"],
    "explain": "本课把借用思想用在一个真实任务上：统计文本词频并按频次（再按字典序）排序输出，保证确定性。关键优化是让 HashMap 的 key 借用输入文本（`HashMap<&str, usize>`）而非克隆每个词的 String——只要输入文本在整个统计期间存活，借用就合法，且零字符串分配。流程：`split_whitespace` 得到词切片、`entry` 计数、把 `(&str, usize)` 收集到 Vec、排序（先按计数降序再按词升序）、打印 Top-N。排序闭包要注意稳定性：用 `b.1.cmp(&a.1).then_with(|| a.0.cmp(b.0))` 得到确定的平局顺序。整个实现展示了本章所有要点：借用入参、切片迭代、entry、所有权不转移、输出确定性。也顺带演示 `Cow` 用于规范化大小写时按需分配。",
    "code": "use std::borrow::Cow;\nuse std::collections::HashMap;\n\nfn normalize(word: &str) -> Cow<'_, str> {\n    if word.chars().any(|c| c.is_uppercase()) {\n        Cow::Owned(word.to_lowercase())\n    } else {\n        Cow::Borrowed(word)\n    }\n}\n\nfn top_words(text: &str, limit: usize) -> Vec<(String, usize)> {\n    let mut counts: HashMap<Cow<'_, str>, usize> = HashMap::new();\n    for raw in text.split_whitespace() {\n        let word = normalize(raw.trim_matches(|c: char| !c.is_alphanumeric()));\n        if word.is_empty() {\n            continue;\n        }\n        *counts.entry(word).or_insert(0) += 1;\n    }\n\n    let mut pairs: Vec<(String, usize)> = counts\n        .into_iter()\n        .map(|(w, n)| (w.into_owned(), n))\n        .collect();\n    pairs.sort_by(|a, b| b.1.cmp(&a.1).then_with(|| a.0.cmp(&b.0)));\n    pairs.truncate(limit);\n    pairs\n}\n\nfn main() {\n    let text = \"Rust rust makes systems fast; fast safe code. Rust! safe systems\";\n    for (word, n) in top_words(text, 4) {\n        println!(\"{}: {}\", word, n);\n    }\n}\n",
    "output": "rust: 3\nfast: 2\nsafe: 2\nsystems: 2\n",
    "pitfalls": [
        "克隆每个词进 HashMap：若输入存活，用 `&str`/`Cow` 借用 key 可零分配。",
        "排序只按频次：平局顺序会随哈希顺序变化，必须加次级键（字典序）保证确定性。",
        "忘记去标点：`trim_matches` 只去首尾，词中间的标点需按需处理，否则同一词被拆分。"
    ],
    "exercise": {
        "prompt": "写函数 `char_frequency(text: &str) -> Vec<(char, usize)>` 统计字母（忽略大小写、忽略非字母）出现次数，按次数降序、字符升序返回；在 main 中打印 \"Hello, World!\" 的前 3 项。",
        "hint": "用 `HashMap<char, usize>`，遍历 `text.chars().filter(|c| c.is_alphabetic()).flat_map(|c| c.to_lowercase())`；排序 `b.1.cmp(&a.1).then(a.0.cmp(&b.0))`。",
        "answer": "use std::collections::HashMap;\n\nfn char_frequency(text: &str) -> Vec<(char, usize)> {\n    let mut counts: HashMap<char, usize> = HashMap::new();\n    for c in text.chars().filter(|c| c.is_alphabetic()).flat_map(|c| c.to_lowercase()) {\n        *counts.entry(c).or_insert(0) += 1;\n    }\n    let mut pairs: Vec<(char, usize)> = counts.into_iter().collect();\n    pairs.sort_by(|a, b| b.1.cmp(&a.1).then_with(|| a.0.cmp(&b.0)));\n    pairs\n}\n\nfn main() {\n    let freq = char_frequency(\"Hello, World!\");\n    for (c, n) in freq.into_iter().take(3) {\n        println!(\"{}: {}\", c, n);\n    }\n}\n"
    },
    "runtime": "desktop"
},
]
