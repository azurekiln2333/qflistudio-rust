# -*- coding: utf-8 -*-
"""Lessons 069..076 (Domain E, part 1: traits, generics, trait objects)."""

LESSONS = [
{
    "id": 69,
    "title": "定义与实现 trait",
    "level": "intermediate",
    "domain": "traits-generics",
    "summary": "用 trait 描述共享行为契约，为多个类型实现同一 trait，理解孤儿规则与一致性。",
    "concepts": ["trait", "impl Trait for Type", "行为契约", "孤儿规则", "多态雏形"],
    "objective": "能定义 trait、为多个类型实现，并在泛型/动态语境中使用它。",
    "prerequisites": ["026"],
    "explain": "trait 定义一组方法签名，描述“能做什么”。`trait Greet { fn greet(&self) -> String; }` 声明契约，`impl Greet for User { ... }` 为具体类型实现。trait 可含必需方法与默认方法（下一课）。实现受孤儿规则限制：只有当 trait 或类型至少有一个属于本 crate 时才能实现，防止冲突实现。trait 是 Rust 多态的基石：既可用于静态分发（泛型约束 `T: Greet`，单态化，零成本），也可用于动态分发（`dyn Greet`，运行时虚表）。方法签名中的 `&self` 决定是否需要可变/消费。trait 还能有自己的关联类型与关联常量。设计 trait 时应聚焦“行为”而非“数据”，并让方法粒度适中。常见标准 trait（Display、Iterator、Add）都是这种契约的实例。",
    "code": "trait Greet {\n    fn name(&self) -> &str;\n    fn greet(&self) -> String {\n        format!(\"你好, {}!\", self.name())\n    }\n}\n\nstruct English;\nstruct Chinese {\n    name: String,\n}\n\nimpl Greet for English {\n    fn name(&self) -> &str {\n        \"World\"\n    }\n\n    // 覆写默认方法\n    fn greet(&self) -> String {\n        format!(\"Hello, {}!\", self.name())\n    }\n}\n\nimpl Greet for Chinese {\n    fn name(&self) -> &str {\n        &self.name\n    }\n}\n\nfn welcome_all<T: Greet>(items: &[T]) {\n    for item in items {\n        println!(\"{}\", item.greet());\n    }\n}\n\nfn main() {\n    let en = [English];\n    welcome_all(&en);\n\n    let zh = [Chinese { name: String::from(\"锈语言\") }];\n    welcome_all(&zh);\n}\n",
    "output": "Hello, World!\n你好, 锈语言!\n",
    "pitfalls": [
        "违反孤儿规则：trait 与类型都不属于本 crate 时无法实现，需用 newtype 包装。",
        "trait 方法缺少 self：没有接收者就不是可分发的方法，而是关联函数。",
        "把数据放进 trait：trait 描述行为，实例数据属于实现类型。"
    ],
    "exercise": {
        "prompt": "定义 trait `Area { fn area(&self) -> f64; }`，为 `struct Circle { r: f64 }` 与 `struct Rect { w: f64, h: f64 }` 实现，并写泛型函数 `describe<T: Area>(shape: &T) -> f64` 返回面积；在 main 中打印两者。",
        "hint": "泛型函数直接 `shape.area()`；impl 中按公式计算。",
        "answer": "trait Area {\n    fn area(&self) -> f64;\n}\n\nstruct Circle {\n    r: f64,\n}\n\nstruct Rect {\n    w: f64,\n    h: f64,\n}\n\nimpl Area for Circle {\n    fn area(&self) -> f64 {\n        std::f64::consts::PI * self.r * self.r\n    }\n}\n\nimpl Area for Rect {\n    fn area(&self) -> f64 {\n        self.w * self.h\n    }\n}\n\nfn describe<T: Area>(shape: &T) -> f64 {\n    shape.area()\n}\n\nfn main() {\n    println!(\"{:.2}\", describe(&Circle { r: 1.0 }));\n    println!(\"{:.2}\", describe(&Rect { w: 3.0, h: 4.0 }));\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 70,
    "title": "默认方法与方法解析",
    "level": "intermediate",
    "domain": "traits-generics",
    "summary": "用默认方法提供可选行为，理解方法解析顺序与固有方法、trait 方法的优先级。",
    "concepts": ["默认方法", "方法解析", "固有方法优先", "完全限定语法", "trait 组合"],
    "objective": "能写出带默认方法的 trait，并在命名冲突时用完全限定语法消歧。",
    "prerequisites": ["069"],
    "explain": "trait 方法可有默认实现，实现者按需覆写。默认方法可调用同一 trait 的其他方法（通常调用必需方法），形成“基于最小契约构建丰富行为”的模式，例如 Iterator 只需实现 next，就免费获得 map/filter 等。方法解析顺序：先找固有方法（inherent impl），再找 trait 方法；若多个 trait 提供同名方法且都 in scope，则必须用完全限定语法 `<Type as Trait>::method(&value)` 消歧，或调用时显式指定。默认实现不能假设实现者会覆写某方法而只调用它（小心相互递归）。trait 还可以有 supertrait（`trait A: B`），表示实现 A 必须先实现 B。默认方法让 API 演进更平滑：新增带默认实现的方法不会破坏现有实现者（这与直接加必需方法是破坏性变更形成对比）。",
    "code": "trait Summary {\n    fn title(&self) -> String; // 必需\n    fn author(&self) -> String {\n        String::from(\"匿名\") // 默认\n    }\n    fn summarize(&self) -> String {\n        // 默认方法基于其他方法构建\n        format!(\"{} — 作者: {}\", self.title(), self.author())\n    }\n}\n\nstruct Article {\n    title: String,\n    author: String,\n}\n\nstruct Note {\n    title: String,\n}\n\nimpl Summary for Article {\n    fn title(&self) -> String {\n        self.title.clone()\n    }\n\n    fn author(&self) -> String {\n        self.author.clone()\n    }\n}\n\nimpl Summary for Note {\n    fn title(&self) -> String {\n        self.title.clone()\n    }\n    // 使用默认 author\n}\n\nfn main() {\n    let a = Article { title: String::from(\"Rust 泛型\"), author: String::from(\"Alice\") };\n    let n = Note { title: String::from(\"备忘\") };\n    println!(\"{}\", a.summarize());\n    println!(\"{}\", n.summarize());\n\n    // 完全限定语法（此处演示语法，即使不冲突也可显式指定）\n    println!(\"{}\", Summary::title(&a));\n}\n",
    "output": "Rust 泛型 — 作者: Alice\n备忘 — 作者: 匿名\nRust 泛型\n",
    "pitfalls": [
        "默认方法互相调用形成死循环：两个默认方法互相依赖会无限递归。",
        "同名方法冲突不消歧：多个 trait 提供同名方法时须用 `<T as Trait>::m()` 指定。",
        "以为默认方法一定被使用：实现者可覆写，调用的是运行时决定的那一个。"
    ],
    "exercise": {
        "prompt": "定义 trait `Shape { fn sides(&self) -> u32; fn describe(&self) -> String { format!(\"{} 边形\", self.sides()) } }`，为 Triangle(3) 与 Square(4) 实现 `sides`，在 main 中打印两者的 describe。",
        "hint": "只实现 sides，describe 用默认方法。",
        "answer": "trait Shape {\n    fn sides(&self) -> u32;\n\n    fn describe(&self) -> String {\n        format!(\"{} 边形\", self.sides())\n    }\n}\n\nstruct Triangle;\nstruct Square;\n\nimpl Shape for Triangle {\n    fn sides(&self) -> u32 {\n        3\n    }\n}\n\nimpl Shape for Square {\n    fn sides(&self) -> u32 {\n        4\n    }\n}\n\nfn main() {\n    println!(\"{}\", Triangle.describe());\n    println!(\"{}\", Square.describe());\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 71,
    "title": "泛型函数与单态化",
    "level": "intermediate",
    "domain": "traits-generics",
    "summary": "写泛型函数复用逻辑，理解单态化在编译期为每个具体类型生成专用代码、零运行时开销。",
    "concepts": ["泛型函数", "类型参数", "单态化", "零成本抽象", "代码膨胀"],
    "objective": "能把重复逻辑抽成泛型函数，并解释单态化的收益与代价。",
    "prerequisites": ["070"],
    "explain": "泛型函数用类型参数 `fn largest<T>(items: &[T]) -> Option<&T>` 复用于多种类型。编译器通过单态化（monomorphization）在调用点为每个具体类型生成一份专用副本，因此泛型调用是静态分发、可内联、无虚表开销——这就是“零成本抽象”。代价是二进制膨胀：用很多类型实例化同一泛型会生成多份机器码；极端情况可用 `Box<dyn Trait>` 换回一份代码（动态分发）。泛型参数还可用作返回类型与结构体字段。写泛型时要注意类型参数约束：没有约束时只能做与所有类型都合法的操作（移动、借用），需要比较就要 `T: PartialOrd`，需要显示就 `T: Display`。泛型与 trait 约束是 Rust 抽象的核心组合；先在具体类型上写对，再参数化，往往能更快得到正确约束。",
    "code": "use std::fmt::Display;\n\nfn largest<T: PartialOrd + Copy>(items: &[T]) -> Option<T> {\n    let mut best = *items.first()?;\n    for &item in &items[1..] {\n        if item > best {\n            best = item;\n        }\n    }\n    Some(best)\n}\n\nfn print_all<T: Display>(label: &str, items: &[T]) {\n    print!(\"{}: \", label);\n    for item in items {\n        print!(\"{} \", item);\n    }\n    println!();\n}\n\nfn main() {\n    println!(\"largest ints = {:?}\", largest(&[3, 9, 2, 7]));\n    println!(\"largest chars = {:?}\", largest(&['a', 'z', 'm']));\n    println!(\"largest empty = {:?}\", largest::<i32>(&[]));\n\n    print_all(\"numbers\", &[1, 2, 3]);\n    print_all(\"words\", &[\"alpha\", \"beta\"]);\n}\n",
    "output": "largest ints = Some(9)\nlargest chars = Some('z')\nlargest empty = None\nnumbers: 1 2 3 \nwords: alpha beta \n",
    "pitfalls": [
        "泛型参数缺约束：直接比较 `T` 会编译失败，需要加 `T: PartialOrd` 等。",
        "对非 Copy 类型用 `*item`：需要 `T: Copy` 或改为借用比较，否则报移动错误。",
        "忽视单态化的代码膨胀：为大量类型实例化会增大二进制，必要时改用 trait 对象。"
    ],
    "exercise": {
        "prompt": "写泛型函数 `last<T>(items: &[T]) -> Option<&T>`（返回最后一个元素的引用）与 `first_or<'a, T>(items: &'a [T], default: &'a T) -> &'a T`（空则返回 default），在 main 中用整数与非空/空切片测试。",
        "hint": "`items.last()` 返回 Option<&T>；first_or 用 `items.first().unwrap_or(default)`。",
        "answer": "fn last<T>(items: &[T]) -> Option<&T> {\n    items.last()\n}\n\nfn first_or<'a, T>(items: &'a [T], default: &'a T) -> &'a T {\n    items.first().unwrap_or(default)\n}\n\nfn main() {\n    let data = [10, 20, 30];\n    println!(\"{:?}\", last(&data));\n    println!(\"{}\", first_or(&data, &0));\n    let empty: [i32; 0] = [];\n    println!(\"{}\", first_or(&empty, &-1));\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 72,
    "title": "trait 约束（bound）语法",
    "level": "intermediate",
    "domain": "traits-generics",
    "summary": "为泛型参数施加一个或多个 trait 约束，理解 `+` 组合、约束传播与最小约束原则。",
    "concepts": ["trait bound", "T: Trait", "多约束 +", "约束传播", "最小约束"],
    "objective": "能根据函数体实际用到的能力添加恰好足够的约束，避免过约束或欠约束。",
    "prerequisites": ["071"],
    "explain": "trait 约束告诉编译器“泛型 T 具备哪些能力”。语法 `fn f<T: Trait>(...)` 或 `fn f<T>(...) where T: Trait`。多约束用 `+` 组合：`T: Display + Clone`。约束会传播：若泛型函数 A 调用泛型函数 B，A 通常需要在签名上声明相同约束。原则是“最小约束”：约束刚好覆盖函数体用到的操作即可，多写会让调用方更难满足，少写则编译失败。`impl Trait` 是约束的语法糖（下一课）。std 中常用 trait 约束：`PartialOrd`（比较）、`Display`（格式化）、`Clone`、`Default`、`IntoIterator`。约束也可施加在关联类型上：`T: Iterator<Item = u32>`。要点：当同一泛型被多个类型参数交叉约束时（如 `A: PartialEq<B>`），签名可能变复杂，此时先抽出具体用例再泛化更稳妥。",
    "code": "use std::fmt::{Debug, Display};\n\nfn show_pair<A: Display, B: Debug>(a: &A, b: &B) -> String {\n    format!(\"a={} b={:?}\", a, b)\n}\n\nfn largest_by<T, F>(items: &[T], score: F) -> Option<&T>\nwhere\n    F: Fn(&T) -> i64,\n{\n    items.iter().max_by_key(|item| score(item))\n}\n\nfn main() {\n    println!(\"{}\", show_pair(&42, &vec![1, 2]));\n    println!(\"{}\", show_pair(&\"text\", &(3, 4)));\n\n    let words = [String::from(\"hi\"), String::from(\"longest\"), String::from(\"mid\")];\n    let longest = largest_by(&words, |w| w.len() as i64);\n    println!(\"longest = {:?}\", longest);\n}\n",
    "output": "a=42 b=[1, 2]\na=text b=(3, 4)\nlongest = Some(\"longest\")\n",
    "pitfalls": [
        "约束不足：函数体调用了未约束的方法会编译失败。",
        "约束过度：加了用不到的 trait，会让调用方不必要地实现它。",
        "调用泛型函数时约束未传播：被调函数要求 `T: Clone`，调用方签名也要声明。"
    ],
    "exercise": {
        "prompt": "写泛型函数 `max_by_len<T: AsRef<str>>(items: &[T]) -> Option<&T>` 返回字符串长度最大的元素；在 main 中用 `&[String]` 与 `&[&str]` 两种输入测试。",
        "hint": "用 `items.iter().max_by_key(|s| s.as_ref().len())`；AsRef<str> 让 String 与 &str 都可用。",
        "answer": "fn max_by_len<T: AsRef<str>>(items: &[T]) -> Option<&T> {\n    items.iter().max_by_key(|s| s.as_ref().len())\n}\n\nfn main() {\n    let owned = vec![String::from(\"a\"), String::from(\"bbb\"), String::from(\"cc\")];\n    println!(\"{:?}\", max_by_len(&owned));\n    let borrowed = [\"x\", \"yyyy\", \"zz\"];\n    println!(\"{:?}\", max_by_len(&borrowed));\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 73,
    "title": "`where` 子句与可读性",
    "level": "intermediate",
    "domain": "traits-generics",
    "summary": "用 where 子句把复杂约束从参数列表移出，提升长签名与多约束函数的可读性。",
    "concepts": ["where 子句", "可读性", "复杂约束", "关联类型约束", "签名组织"],
    "objective": "能在约束较长或涉及关联类型时改用 where 子句，让签名层次清晰。",
    "prerequisites": ["072"],
    "explain": "`where` 子句写在返回类型之后、函数体之前，把约束集中列出：`fn f<T, U>(t: T, u: U) -> R where T: Clone + Debug, U: Into<T>`。当约束多、含关联类型（`T: Iterator<Item = V>`）、或需要对多个泛型交叉约束时，where 明显比行内 `<T: ...>` 更易读。行内与 where 等价，可混用，但惯例是：简单单约束用行内，复杂/多约束用 where。where 也用于 impl 块与 trait 定义。注意 where 与生命周期约束共处：`where 'a: 'b` 表示 'a 至少活得和 'b 一样久。可读性上，把“类型做了什么”放在 where 里，函数签名的主体（参数与返回）保持简洁，有助于快速扫读 API。它也是许多标准库签名的组织方式。",
    "code": "use std::fmt::Debug;\n\n#[derive(Debug)]\nstruct Pair<T, U> {\n    left: T,\n    right: U,\n}\n\nimpl<T, U> Pair<T, U>\nwhere\n    T: Debug + Clone,\n    U: Debug + Clone,\n{\n    fn new(left: T, right: U) -> Self {\n        Pair { left, right }\n    }\n\n    fn swapped(&self) -> Pair<U, T>\n    where\n        U: Clone,\n        T: Clone,\n    {\n        Pair { left: self.right.clone(), right: self.left.clone() }\n    }\n}\n\nfn collect_strings<I, S>(iter: I) -> Vec<String>\nwhere\n    I: IntoIterator<Item = S>,\n    S: Into<String>,\n{\n    iter.into_iter().map(Into::into).collect()\n}\n\nfn main() {\n    let pair = Pair::new(1, \"one\");\n    println!(\"pair = {:?}\", pair);\n    println!(\"swapped = {:?}\", pair.swapped());\n\n    let strings = collect_strings(vec![\"a\", \"b\"]);\n    println!(\"strings = {:?}\", strings);\n}\n",
    "output": "pair = Pair { left: 1, right: \"one\" }\nswapped = Pair { left: \"one\", right: 1 }\nstrings = [\"a\", \"b\"]\n",
    "pitfalls": [
        "where 与行内约束重复：同一约束不必写两处，冗余且易不同步。",
        "把生命周期约束写错方向：`'a: 'b` 表示 'a 比 'b 长，方向反了会导致误判。",
        "为简单函数也写 where：单约束行内更紧凑，where 留给复杂场景。"
    ],
    "exercise": {
        "prompt": "用 where 子句写泛型函数 `zip_print<A, B>(a: &[A], b: &[B])`，要求 `A: std::fmt::Display, B: std::fmt::Debug`，把对齐的元素配对打印；在 main 中用两个切片测试（长度取较短）。",
        "hint": "`a.iter().zip(b.iter()).for_each(|(x, y)| println!(\"{} | {:?}\", x, y));`。",
        "answer": "use std::fmt::{Debug, Display};\n\nfn zip_print<A, B>(a: &[A], b: &[B])\nwhere\n    A: Display,\n    B: Debug,\n{\n    for (x, y) in a.iter().zip(b.iter()) {\n        println!(\"{} | {:?}\", x, y);\n    }\n}\n\nfn main() {\n    zip_print(&[1, 2, 3], &[\"a\", \"b\"]);\n    zip_print(&[\"x\"], &[true, false]);\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 74,
    "title": "`impl Trait` 参数与返回值",
    "level": "advanced",
    "domain": "traits-generics",
    "summary": "用 `impl Trait` 简化参数约束与返回类型，理解它在参数位的泛型糖与返回位的不透明类型。",
    "concepts": ["impl Trait", "参数位", "返回位", "不透明类型", "RPIT"],
    "objective": "能区分 `impl Trait` 在参数位（泛型糖）与返回位（隐藏具体类型）的不同语义。",
    "prerequisites": ["072"],
    "explain": "在参数位，`fn f(x: impl Display)` 等价于泛型参数 `fn f<T: Display>(x: T)`，调用点可传任何满足约束的类型，静态分发、零成本。它让只被调用一次的辅助函数签名更简短，但缺点是调用方无法用 turbofish 显式指定类型。在返回位，`fn f() -> impl Iterator<Item = u32>` 表示“返回某个实现该 trait 的类型，但调用方不必知道具体是什么”（RPIT，不透明返回类型）。它保留了静态分发与零成本，同时隐藏复杂类型（如嵌套迭代器/closures 的类型无法书写）。限制：同一函数的所有返回路径必须是同一具体类型（不能返回两种不同 impl 类型）；不能对不透明类型调用超出约束的方法。要点：参数位 `impl Trait` 与泛型参数选择上，若需要 turbofish 或需在签名多处复用同一类型，用命名泛型；只在返回复杂闭包/迭代器时用返回位 impl Trait。",
    "code": "fn print_labeled(label: impl std::fmt::Display, value: impl std::fmt::Debug) {\n    println!(\"{}: {:?}\", label, value);\n}\n\n// 返回位 impl Trait：隐藏复杂的链式迭代器类型\nfn evens_doubled(limit: u32) -> impl Iterator<Item = u32> {\n    (1..=limit).filter(|n| n % 2 == 0).map(|n| n * 2)\n}\n\n// 返回闭包类型：无法写出具体类型，只能用 impl Fn\nfn make_adder(base: i32) -> impl Fn(i32) -> i32 {\n    move |x| base + x\n}\n\nfn main() {\n    print_labeled(\"count\", 3);\n    print_labeled(\"items\", vec![1, 2]);\n\n    let values: Vec<u32> = evens_doubled(10).collect();\n    println!(\"evens_doubled = {:?}\", values);\n\n    let add5 = make_adder(5);\n    println!(\"add5(10) = {}\", add5(10));\n}\n",
    "output": "count: 3\nitems: [1, 2]\nevens_doubled = [4, 8, 12, 16, 20]\nadd5(10) = 15\n",
    "pitfalls": [
        "返回位 impl Trait 的多个分支返回不同类型：编译失败，必须统一为同一具体类型。",
        "对返回的 impl Trait 调用未在约束中声明的方法：不透明类型只能用它承诺的 trait。",
        "参数位 impl Trait 想用 turbofish 指定类型：不支持，需改用命名泛型参数。"
    ],
    "exercise": {
        "prompt": "写函数 `fn odds(limit: u32) -> impl Iterator<Item = u32>` 返回 1..=limit 中的奇数，和 `fn apply_twice(f: impl Fn(i32) -> i32, x: i32) -> i32` 把 f 连续应用两次；在 main 中打印 odds(9) 的收集结果与 `apply_twice(|v| v * 3, 2)`。",
        "hint": "odds 用 `(1..=limit).filter(|n| n % 2 == 1)`；apply_twice 返回 `f(f(x))`。",
        "answer": "fn odds(limit: u32) -> impl Iterator<Item = u32> {\n    (1..=limit).filter(|n| n % 2 == 1)\n}\n\nfn apply_twice(f: impl Fn(i32) -> i32, x: i32) -> i32 {\n    f(f(x))\n}\n\nfn main() {\n    let vals: Vec<u32> = odds(9).collect();\n    println!(\"{:?}\", vals);\n    println!(\"{}\", apply_twice(|v| v * 3, 2));\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 75,
    "title": "trait 对象 `dyn Trait` 与动态分发",
    "level": "advanced",
    "domain": "traits-generics",
    "summary": "用 `Box<dyn Trait>` 或 `&dyn Trait` 做运行时多态，理解虚表与静态分发的取舍。",
    "concepts": ["dyn Trait", "动态分发", "虚表", "对象安全", "异构集合"],
    "objective": "能在需要异构集合或运行时选择实现时使用 trait 对象，并解释其开销来源。",
    "prerequisites": ["074"],
    "explain": "trait 对象 `dyn Trait` 表示“某个实现了 Trait 的类型”，但具体类型在编译期未知，调用通过虚表（vtable）在运行时查找，实现动态分发。两种常见形式：`&dyn Trait`（借用）与 `Box<dyn Trait>`（拥有）。它能装进同一集合持有不同具体类型（`Vec<Box<dyn Shape>>`），也可作为结构体字段在运行时更换实现。代价：每次方法调用有间接跳转（通常可接受），且失去泛型的内联与单态化。trait 对象要求对象安全（下一课）。选择原则：类型在编译期已知且追求性能 → 泛型静态分发；需要异构集合或运行时多态 → trait 对象。也可混合：`Vec<Box<dyn Trait>>` 装不同实现，内部实现各自可泛型。注意 `dyn Trait` 默认生命周期是 `'static`（在 Box 中），要含借用需写 `Box<dyn Trait + 'a>`。",
    "code": "trait Shape {\n    fn area(&self) -> f64;\n    fn name(&self) -> &'static str;\n}\n\nstruct Circle(f64);\nstruct Square(f64);\nstruct Triangle {\n    base: f64,\n    height: f64,\n}\n\nimpl Shape for Circle {\n    fn area(&self) -> f64 {\n        std::f64::consts::PI * self.0 * self.0\n    }\n    fn name(&self) -> &'static str {\n        \"circle\"\n    }\n}\n\nimpl Shape for Square {\n    fn area(&self) -> f64 {\n        self.0 * self.0\n    }\n    fn name(&self) -> &'static str {\n        \"square\"\n    }\n}\n\nimpl Shape for Triangle {\n    fn area(&self) -> f64 {\n        0.5 * self.base * self.height\n    }\n    fn name(&self) -> &'static str {\n        \"triangle\"\n    }\n}\n\nfn main() {\n    let shapes: Vec<Box<dyn Shape>> = vec![\n        Box::new(Circle(1.0)),\n        Box::new(Square(3.0)),\n        Box::new(Triangle { base: 4.0, height: 5.0 }),\n    ];\n\n    let total: f64 = shapes.iter().map(|s| s.area()).sum();\n    for s in &shapes {\n        println!(\"{:<9} area = {:.2}\", s.name(), s.area());\n    }\n    println!(\"total = {:.2}\", total);\n}\n",
    "output": "circle    area = 3.14\nsquare    area = 9.00\ntriangle  area = 10.00\ntotal = 22.14\n",
    "pitfalls": [
        "把泛型参数当 trait 对象：`Vec<dyn Trait>` 缺 Box/引用，编译失败。",
        "在热路径用 dyn 却追求极致性能：动态分发有虚表开销，静态分发可内联。",
        "trait 对象含借用却用默认 'static：需要 `Box<dyn Trait + 'a>` 显式标注。"
    ],
    "exercise": {
        "prompt": "定义 trait `Animal { fn sound(&self) -> &'static str; }`，为 Dog/Cow/Cat 实现，放进 `Vec<Box<dyn Animal>>`，遍历打印每种叫声并统计数量。",
        "hint": "三个 struct 各自 impl；遍历 `animals.iter()` 调用 sound()。",
        "answer": "trait Animal {\n    fn sound(&self) -> &'static str;\n}\n\nstruct Dog;\nstruct Cow;\nstruct Cat;\n\nimpl Animal for Dog {\n    fn sound(&self) -> &'static str {\n        \"woof\"\n    }\n}\n\nimpl Animal for Cow {\n    fn sound(&self) -> &'static str {\n        \"moo\"\n    }\n}\n\nimpl Animal for Cat {\n    fn sound(&self) -> &'static str {\n        \"meow\"\n    }\n}\n\nfn main() {\n    let animals: Vec<Box<dyn Animal>> = vec![Box::new(Dog), Box::new(Cow), Box::new(Cat)];\n    for a in &animals {\n        println!(\"{}\", a.sound());\n    }\n    println!(\"count = {}\", animals.len());\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 76,
    "title": "对象安全（object safety）规则",
    "level": "advanced",
    "domain": "traits-generics",
    "summary": "理解哪些 trait 能变成 trait 对象、哪些不能，以及泛型方法、Self 返回值为何破坏对象安全。",
    "concepts": ["对象安全", "object safety", "Self: Sized", "泛型方法", "dyn 兼容"],
    "objective": "能判断一个 trait 是否可作为 `dyn Trait`，并在需要时用 `where Self: Sized` 修复。",
    "prerequisites": ["075"],
    "explain": "并非所有 trait 都能做成 `dyn Trait`，这称为对象安全（object safety）。破坏对象安全的常见原因：方法有泛型参数（无法为无限多类型生成虚表项）、返回 `Self`、把 `Self` 用在参数位置（除接收者）、或含关联常量。若某方法确实不参与动态调用，可以用 `where Self: Sized` 把它排除在 vtable 之外，从而让 trait 整体仍可对象安全——这类方法只能对具体类型（或静态分发）调用，不能在 `dyn` 上调用。理解对象安全有助于设计 API：若希望支持 `Box<dyn Trait>`，就避免在核心方法上使用泛型/返回 Self；必须有的泛型方法就标注 `Self: Sized`。另一个限制：关联类型在 trait 对象中必须被具体化（`dyn Iterator<Item = u32>`），或通过 `dyn Trait<Item = X>` 指定。要点：对象安全是“可被当类型使用”的资格，混入一个不兼容方法就整体失效（除非 Sized 排除）。",
    "code": "trait Drawable {\n    fn draw(&self) -> String;\n\n    // 泛型方法破坏对象安全，用 Self: Sized 排除出 vtable\n    fn draw_twice<T: std::fmt::Display>(&self, tag: T) -> String\n    where\n        Self: Sized,\n    {\n        format!(\"[{}] {} {}\", tag, self.draw(), self.draw())\n    }\n}\n\nstruct Dot;\nstruct Line(u32);\n\nimpl Drawable for Dot {\n    fn draw(&self) -> String {\n        String::from(\".\")\n    }\n}\n\nimpl Drawable for Line {\n    fn draw(&self) -> String {\n        format!(\"{}\", \"-\".repeat(self.0 as usize))\n    }\n}\n\nfn main() {\n    let items: Vec<Box<dyn Drawable>> = vec![Box::new(Dot), Box::new(Line(4))];\n    for item in &items {\n        println!(\"{}\", item.draw()); // 只调用对象安全的方法\n    }\n\n    // draw_twice 需要 Self: Sized，对具体类型可用\n    println!(\"{}\", Dot.draw_twice(\"tag\"));\n}\n",
    "output": ".\n----\n[tag] . .\n",
    "pitfalls": [
        "在 dyn 上调用泛型方法：即使有 default 实现也会失败，被 Self: Sized 排除了。",
        "方法返回 Self：破坏对象安全，除非加 `where Self: Sized`。",
        "关联类型未具体化就做 trait 对象：`Box<dyn Iterator>` 不行，需 `dyn Iterator<Item = T>`。"
    ],
    "exercise": {
        "prompt": "定义 trait `Store { fn get(&self, key: &str) -> Option<u32>; fn set(&mut self, key: &str, value: u32); fn entries(&self) -> Vec<(String, u32)>; fn merge(&mut self, other: &Self) where Self: Sized; }`，为 `InMemory` 实现 get/set/entries 与一个**真实合并**的 merge（把 other 的键值写入 self，右侧覆盖、缺失补齐），在 main 中合并两个实例并按 key 排序打印结果，同时把 InMemory 放进 `Vec<Box<dyn Store>>` 演示对象安全方法。",
        "hint": "merge 用默认空实现 + Self: Sized 排除；get/set 用 HashMap 实现。",
        "answer": "use std::collections::HashMap;\n\ntrait Store {\n    fn get(&self, key: &str) -> Option<u32>;\n    fn set(&mut self, key: &str, value: u32);\n\n    // merge 需要具体类型，故用 Self: Sized 排除出 vtable（见对象安全课）\n    fn merge(&mut self, other: &Self)\n    where\n        Self: Sized,\n    {\n        for (k, v) in other.entries() {\n            self.set(&k, v);\n        }\n    }\n\n    // 供 merge 默认实现读取的辅助方法（也可被具体类型覆写）\n    fn entries(&self) -> Vec<(String, u32)>;\n}\n\nstruct InMemory {\n    map: HashMap<String, u32>,\n}\n\nimpl InMemory {\n    fn new() -> Self {\n        InMemory { map: HashMap::new() }\n    }\n}\n\nimpl Store for InMemory {\n    fn get(&self, key: &str) -> Option<u32> {\n        self.map.get(key).copied()\n    }\n\n    fn set(&mut self, key: &str, value: u32) {\n        self.map.insert(key.to_string(), value);\n    }\n\n    fn entries(&self) -> Vec<(String, u32)> {\n        let mut pairs: Vec<(String, u32)> = self.map.iter().map(|(k, v)| (k.clone(), *v)).collect();\n        pairs.sort();\n        pairs\n    }\n}\n\nfn main() {\n    let mut left = InMemory::new();\n    left.set(\"a\", 1);\n    left.set(\"b\", 2);\n\n    let mut right = InMemory::new();\n    right.set(\"b\", 20);\n    right.set(\"c\", 30);\n\n    left.merge(&right); // 真实合并：b 被右侧覆盖，新增 c\n\n    let mut items: Vec<(String, u32)> = left.entries();\n    items.sort();\n    for (k, v) in items {\n        println!(\"{} = {}\", k, v);\n    }\n    println!(\"{:?}\", left.get(\"missing\"));\n\n    // 仍可作为 trait 对象使用（只调用对象安全的方法）\n    let mut stores: Vec<Box<dyn Store>> = vec![Box::new(InMemory::new())];\n    stores[0].set(\"x\", 9);\n    println!(\"trait object get(x) = {:?}\", stores[0].get(\"x\"));\n}\n",
    },
    "runtime": "desktop"
},
]
