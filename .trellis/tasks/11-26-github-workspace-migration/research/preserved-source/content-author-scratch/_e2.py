# -*- coding: utf-8 -*-
"""Lessons 077..084 (Domain E, part 2: Box<dyn>, std traits, coherence, capstone)."""

LESSONS = [
{
    "id": 77,
    "title": "`Box<dyn Trait>` 与异构集合",
    "level": "advanced",
    "domain": "traits-generics",
    "summary": "用 `Box<dyn Trait>` 把不同具体类型装进同一集合，构建插件式的可扩展结构。",
    "concepts": ["Box<dyn Trait>", "异构集合", "插件模式", "所有权转移", "trait 对象容器"],
    "objective": "能用 Box<dyn Trait> 承载运行时选择的实现，并写出对集合统一操作的代码。",
    "prerequisites": ["075"],
    "explain": "`Box<dyn Trait>` 把具体类型的值放到堆上，用一个胖指针（数据指针 + 虚表指针）表示，从而让大小不同的不同类型拥有统一类型。它是异构集合的标准载体：`Vec<Box<dyn Fn()>>`、`Vec<Box<dyn Exporter>>`。与泛型 `Vec<T>` 的区别是 T 必须单一；与枚举的区别是枚举需预先列出所有变体，而 trait 对象允许在运行时来自任意实现（包括其他 crate）。构建插件系统时，注册表持有 `Vec<Box<dyn Plugin>>`，遍历调用统一接口。要点：Box 转移所有权，放入后由集合持有；需要共享则用 `Rc<dyn Trait>`/`Arc<dyn Trait>`；需要可变调用则用 `Box<dyn Trait>` 并让方法接收 `&mut self`。也要注意对象安全的限制。相比 enum dispatch，trait 对象提供了开放扩展（新增实现无需改枚举），代价是虚表调用。",
    "code": "trait Formatter {\n    fn name(&self) -> &'static str;\n    fn format(&self, value: i64) -> String;\n}\n\nstruct Plain;\nstruct Hex;\nstruct Padded(usize);\n\nimpl Formatter for Plain {\n    fn name(&self) -> &'static str {\n        \"plain\"\n    }\n    fn format(&self, value: i64) -> String {\n        value.to_string()\n    }\n}\n\nimpl Formatter for Hex {\n    fn name(&self) -> &'static str {\n        \"hex\"\n    }\n    fn format(&self, value: i64) -> String {\n        format!(\"{:#x}\", value)\n    }\n}\n\nimpl Formatter for Padded {\n    fn name(&self) -> &'static str {\n        \"padded\"\n    }\n    fn format(&self, value: i64) -> String {\n        format!(\"{:0>width$}\", value, width = self.0)\n    }\n}\n\nfn main() {\n    let formatters: Vec<Box<dyn Formatter>> = vec![\n        Box::new(Plain),\n        Box::new(Hex),\n        Box::new(Padded(6)),\n    ];\n\n    for f in &formatters {\n        println!(\"{:<8} => {}\", f.name(), f.format(255));\n    }\n}\n",
    "output": "plain    => 255\nhex      => 0xff\npadded   => 000255\n",
    "pitfalls": [
        "想用 `Vec<dyn Trait>`：trait 对象是 DST，必须经 Box/引用间接化。",
        "对 Box<dyn Trait> 想调用泛型方法：受对象安全限制，需 Self: Sized 的具体类型调用。",
        "需要共享所有权却用 Box：多所有者应改用 `Rc<dyn Trait>`/`Arc<dyn Trait>`。"
    ],
    "exercise": {
        "prompt": "定义 trait `Exporter { fn ext(&self) -> &'static str; fn export(&self, rows: &[&str]) -> String; }`，实现 Csv（逗号连接）与 Lines（换行连接），放进 `Vec<Box<dyn Exporter>>`，对同一行数据导出并打印各自扩展名与结果。",
        "hint": "Csv 用 `rows.join(\",\")`；Lines 用 `rows.join(\"\\n\")`；遍历调用。",
        "answer": "trait Exporter {\n    fn ext(&self) -> &'static str;\n    fn export(&self, rows: &[&str]) -> String;\n}\n\nstruct Csv;\nstruct Lines;\n\nimpl Exporter for Csv {\n    fn ext(&self) -> &'static str {\n        \"csv\"\n    }\n    fn export(&self, rows: &[&str]) -> String {\n        rows.join(\",\")\n    }\n}\n\nimpl Exporter for Lines {\n    fn ext(&self) -> &'static str {\n        \"txt\"\n    }\n    fn export(&self, rows: &[&str]) -> String {\n        rows.join(\"\\n\")\n    }\n}\n\nfn main() {\n    let exporters: Vec<Box<dyn Exporter>> = vec![Box::new(Csv), Box::new(Lines)];\n    let rows = [\"a\", \"b\", \"c\"];\n    for e in &exporters {\n        println!(\"[{}] {}\", e.ext(), e.export(&rows));\n    }\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 78,
    "title": "关联类型 vs 泛型参数",
    "level": "advanced",
    "domain": "traits-generics",
    "summary": "区分关联类型（每个实现只有一个取值）与泛型参数（可多次实例化），掌握各自适用场景。",
    "concepts": ["关联类型", "type Item", "泛型参数", "单一实现", "多实现"],
    "objective": "能判断一个 trait 该用关联类型还是泛型参数，并解释二者对调用方的影响。",
    "prerequisites": ["073"],
    "explain": "关联类型 `trait Producer { type Item; fn produce(&self) -> Self::Item; }` 表示“每个实现只对应一种输出类型”，由实现者固定，调用方写 `P::Item`。泛型参数 `trait Convert<T> { fn convert(&self) -> T; }` 表示“同一类型可针对多种 T 实现”，一个类型能有多个 `impl Convert<A>`、`impl Convert<B>`。选择依据：若概念上“一个实现对应一个 X”，用关联类型（Iterator::Item 是典型，每个迭代器只有一种元素类型）；若同一类型需要针对多种目标参数实现、或签名里要泛化输入，用泛型参数。关联类型让调用签名更简洁（不必到处写泛型），也能在 trait 对象中通过 `<dyn Trait<Item = T>>` 具体化。泛型参数更灵活但会让签名变长，且可能引入类型推断歧义（需 turbofish）。标准库中 `Add` 用关联类型 `Output`（每个类型的加法结果唯一），`From<T>` 用泛型参数（一个类型可从多种来源转换）。",
    "code": "trait Producer {\n    type Item;\n    fn produce(&self) -> Self::Item;\n}\n\nstruct NumberBox(i32);\nstruct WordBox(String);\n\nimpl Producer for NumberBox {\n    type Item = i32;\n    fn produce(&self) -> i32 {\n        self.0\n    }\n}\n\nimpl Producer for WordBox {\n    type Item = String;\n    fn produce(&self) -> String {\n        self.0.clone()\n    }\n}\n\n// 泛型参数版本：同一类型可针对多种目标实现\nstruct Celsius(f64);\n\ntrait Convert<T> {\n    fn convert(&self) -> T;\n}\n\nimpl Convert<f64> for Celsius {\n    fn convert(&self) -> f64 {\n        self.0\n    }\n}\n\nimpl Convert<String> for Celsius {\n    fn convert(&self) -> String {\n        format!(\"{:.1}°C\", self.0)\n    }\n}\n\nfn main() {\n    println!(\"number = {:?}\", NumberBox(7).produce());\n    println!(\"word   = {:?}\", WordBox(String::from(\"hi\")).produce());\n\n    let c = Celsius(21.5);\n    let as_f64: f64 = c.convert();\n    let as_str: String = c.convert();\n    println!(\"as_f64 = {}, as_str = {}\", as_f64, as_str);\n}\n",
    "output": "number = 7\nword   = \"hi\"\nas_f64 = 21.5, as_str = 21.5°C\n",
    "pitfalls": [
        "把关联类型换成泛型参数导致歧义：同一 trait 多个实现时需 turbofish 指定。",
        "在 trait 对象中忘记具体化关联类型：`dyn Producer<Item = i32>` 才可用。",
        "概念上“每个实现唯一”却用泛型参数：会让 API 变复杂且更难推断。"
    ],
    "exercise": {
        "prompt": "定义 `trait Container { type Item; fn put(&mut self, item: Self::Item); fn count(&self) -> usize; }`，用 `Vec<i32>` 版本 `IntBox` 与 `Vec<String>` 版本 `StrBox` 实现，在 main 中各自放入元素并打印计数与内容。",
        "hint": "两个 struct 各持 Vec，关联类型分别为 i32 与 String；count 返回 len。",
        "answer": "trait Container {\n    type Item;\n    fn put(&mut self, item: Self::Item);\n    fn count(&self) -> usize;\n}\n\nstruct IntBox {\n    items: Vec<i32>,\n}\n\nstruct StrBox {\n    items: Vec<String>,\n}\n\nimpl Container for IntBox {\n    type Item = i32;\n    fn put(&mut self, item: i32) {\n        self.items.push(item);\n    }\n    fn count(&self) -> usize {\n        self.items.len()\n    }\n}\n\nimpl Container for StrBox {\n    type Item = String;\n    fn put(&mut self, item: String) {\n        self.items.push(item);\n    }\n    fn count(&self) -> usize {\n        self.items.len()\n    }\n}\n\nfn main() {\n    let mut ints = IntBox { items: Vec::new() };\n    ints.put(1);\n    ints.put(2);\n    println!(\"ints = {:?}, count = {}\", ints.items, ints.count());\n\n    let mut strs = StrBox { items: Vec::new() };\n    strs.put(String::from(\"a\"));\n    println!(\"strs = {:?}, count = {}\", strs.items, strs.count());\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 79,
    "title": "常用标准 trait：`From`/`Into`/`TryFrom`",
    "level": "advanced",
    "domain": "traits-generics",
    "summary": "用 From/Into 做无损转换、TryFrom/TryInto 做可失败转换，掌握 `?` 与 From 的自动衔接。",
    "concepts": ["From", "Into", "TryFrom", "TryInto", "自动转换"],
    "objective": "能为自定义类型实现 From/TryFrom，并解释为何只需实现 From 就自动获得 Into。",
    "prerequisites": ["074"],
    "explain": "`From`/`Into` 表达无损、不会失败的转换：实现 `From<A> for B` 后，标准库通过 blanket impl 自动得到 `Into<B> for A`，因此只需实现 From 即可用 `.into()`。`TryFrom`/`TryInto` 表达可能失败的转换，返回 Result；`?` 在错误类型可通过 From 转换时自动传播。这些 trait 让 API 更通用：函数参数接收 `impl Into<String>` 就能同时接受 `&str` 与 `String`；错误传播用 `From` 把底层错误自动转成上层错误类型。要点：`From` 必须表达**真正无损**的转换——它不能丢弃或改变信息（例如不能用 `len()` 之类只保留长度），否则语义被破坏；若转换可能失败或有损，用 `TryFrom` 或提供命名构造函数；不要为“看起来像”的类型随意实现 From（会破坏语义）；`Into` 一般不手写，交给 blanket impl。标准库已有大量实现（`From<&str> for String`、`TryFrom<i64> for u8`），善用它们能减少自定义代码。",
    "code": "use std::convert::TryFrom;\n\n// 1) 可失败转换用 TryFrom：范围校验，失败返回原因。\n#[derive(Debug, PartialEq)]\nstruct Percentage(u8);\n\nimpl TryFrom<i64> for Percentage {\n    type Error = String;\n\n    fn try_from(value: i64) -> Result<Self, Self::Error> {\n        if (0..=100).contains(&value) {\n            Ok(Percentage(value as u8))\n        } else {\n            Err(format!(\"{} 不在 0..=100\", value))\n        }\n    }\n}\n\n// 2) 无损转换用 From：UserId 原样保存字符串，绝不丢信息。\n#[derive(Debug, PartialEq, Eq)]\nstruct UserId(String);\n\nimpl From<String> for UserId {\n    fn from(value: String) -> Self {\n        UserId(value) // 原样保留全部文本\n    }\n}\n\nimpl From<&str> for UserId {\n    fn from(value: &str) -> Self {\n        UserId(value.to_string()) // 原样保留全部文本\n    }\n}\n\n// label 接收 impl Into<String>，&str 与 String 都能无成本传入。\nfn label(value: impl Into<String>) -> String {\n    format!(\"<{}>\", value.into())\n}\n\nfn main() {\n    // TryFrom：范围校验\n    assert_eq!(Percentage::try_from(42), Ok(Percentage(42)));\n    assert!(Percentage::try_from(150).is_err());\n    println!(\"{:?}\", Percentage::try_from(42));\n    println!(\"{:?}\", Percentage::try_from(150));\n\n    // From 无损：原文本完整保留\n    let a: UserId = \"user-中文-01\".into();\n    let b: UserId = String::from(\"keep me exactly\").into();\n    assert_eq!(a, UserId(String::from(\"user-中文-01\")));\n    assert_eq!(b, UserId(String::from(\"keep me exactly\")));\n    println!(\"a = {:?}\", a);\n    println!(\"b = {:?}\", b);\n\n    // 关键：长度相同但内容不同的两个 id 必须仍然不相等（证明没有按长度退化）\n    let x: UserId = \"abcd\".into();\n    let y: UserId = \"wxyz\".into();\n    assert_ne!(x, y, \"同样长度、不同文本的 id 必须不相等\");\n    assert_eq!(x.0.len(), y.0.len());\n    println!(\"x = {:?}, y = {:?}, x == y: {}\", x, y, x == y);\n\n    println!(\"{}\", label(\"static str\"));\n    println!(\"{}\", label(String::from(\"owned\")));\n}\n",
    "output": "Ok(Percentage(42))\nErr(\"150 不在 0..=100\")\na = UserId(\"user-中文-01\")\nb = UserId(\"keep me exactly\")\nx = UserId(\"abcd\"), y = UserId(\"wxyz\"), x == y: false\n<static str>\n<owned>\n",
    "pitfalls": [
        "实现 Into 而非 From：手写 Into 会丢失 blanket impl 的便利，通常只实现 From。",
        "用 From 做可失败/有损转换：应使用 TryFrom，否则调用方无法处理失败。",
        "滥用 From 做语义不符的转换：会误导使用者，应改用命名构造函数。"
    ],
    "exercise": {
        "prompt": "为 `struct UserId(String)` 实现无损的 `From<String>`（原样保留文本），以及可失败的 `TryFrom<&str>`（要求非空且全为 ASCII 数字，错误为 String）；在 main 中展示无损转换（含中文/非数字文本）与 TryFrom 的合法、非法与空输入。注意不要同时写 `From<&str>` 与 `TryFrom<&str>`，二者会因 core 的 blanket impl 冲突。",
        "hint": "元组 From 直接构造；TryFrom<&str> 用 split_once(',') 与 parse。",
        "answer": "use std::convert::TryFrom;\n\n#[derive(Debug, PartialEq)]\nstruct UserId(String);\n\n// From<String> 是无损转换：原样保留文本（不做任何解释/截断）\nimpl From<String> for UserId {\n    fn from(value: String) -> Self {\n        UserId(value)\n    }\n}\n\n// 注意：不能同时写 From<&str> 和 TryFrom<&str>——core 有 blanket impl\n// `impl<T, U> TryFrom<U> for T where U: Into<T>`，两者会冲突（E0119）。\n// 因此这里只提供 TryFrom<&str>：要求非空且全为 ASCII 数字，并保留原文本。\nimpl TryFrom<&str> for UserId {\n    type Error = String;\n\n    fn try_from(value: &str) -> Result<Self, Self::Error> {\n        let trimmed = value.trim();\n        if trimmed.is_empty() {\n            return Err(String::from(\"空 id\"));\n        }\n        if !trimmed.chars().all(|c| c.is_ascii_digit()) {\n            return Err(format!(\"id 必须是数字: {}\", trimmed));\n        }\n        Ok(UserId(trimmed.to_string()))\n    }\n}\n\nfn main() {\n    // 无损 From<String>：任意文本都原样保留\n    let a: UserId = String::from(\"user-中文-01\").into();\n    let b: UserId = String::from(\"keep me exactly\").into();\n    println!(\"a = {:?}\", a);\n    println!(\"b = {:?}\", b);\n\n    // TryFrom<&str>：只接受数字 id，并保留原文本\n    println!(\"{:?}\", UserId::try_from(\" 12345 \"));\n    println!(\"{:?}\", UserId::try_from(\"12a\"));\n    println!(\"{:?}\", UserId::try_from(\"\"));\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 80,
    "title": "`Display`/`Debug`/`FromStr` 协同",
    "level": "advanced",
    "domain": "traits-generics",
    "summary": "让一个类型同时支持打印（Display/Debug）与解析（FromStr），形成对称的文本接口。",
    "concepts": ["Display", "Debug", "FromStr", "字符串往返", "对称接口"],
    "objective": "能为自定义类型实现 Display 与 FromStr，实现“打印后再解析回等价值”的往返。",
    "prerequisites": ["079"],
    "explain": "`FromStr` 是标准库 trait：`fn from_str(s: &str) -> Result<Self, Self::Err>`，与 `.parse()` 对接。当类型同时实现 `Display` 与 `FromStr`，就得到对称的文本接口：`to_string()` 的输出能被 `parse()` 读回。实现要点：Display 面向人类、格式稳定；FromStr 应接受 Display 的输出（往返一致），并给出精确错误。`parse()` 的返回类型由上下文推断，因此 `let v: T = s.parse()?;` 或 `T::from_str(s)`。实现 FromStr 的 Error 应实现 Display（便于 `?` 与用户提示），常见用 String 或领域错误枚举。注意 `Debug` 是调试格式（含结构信息），不适合作为持久化/往返格式；往返应基于 Display。这一协同让自定义类型像内置数字一样好用：既能打印又能解析，是配置、协议、CLI 参数解析的基础。",
    "code": "use std::fmt;\nuse std::str::FromStr;\n\n#[derive(Debug, PartialEq)]\nstruct Point {\n    x: i32,\n    y: i32,\n}\n\nimpl fmt::Display for Point {\n    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {\n        write!(f, \"({}, {})\", self.x, self.y)\n    }\n}\n\nimpl FromStr for Point {\n    type Err = String;\n\n    fn from_str(s: &str) -> Result<Self, Self::Err> {\n        let inner = s.trim().trim_start_matches('(').trim_end_matches(')');\n        let (a, b) = inner.split_once(',').ok_or_else(|| format!(\"缺少逗号: {}\", s))?;\n        let x: i32 = a.trim().parse().map_err(|_| format!(\"非法 x: {}\", a))?;\n        let y: i32 = b.trim().parse().map_err(|_| format!(\"非法 y: {}\", b))?;\n        Ok(Point { x, y })\n    }\n}\n\nfn main() {\n    let p = Point { x: 3, y: -4 };\n    let text = p.to_string();\n    println!(\"display = {}\", text);\n\n    let parsed: Result<Point, _> = text.parse();\n    println!(\"round-trip = {:?}\", parsed);\n    println!(\"equal = {}\", parsed.as_ref().map(|q| *q == p).unwrap_or(false));\n\n    let bad: Result<Point, _> = \"(1;2)\".parse();\n    println!(\"bad = {:?}\", bad);\n}\n",
    "output": "display = (3, -4)\nround-trip = Ok(Point { x: 3, y: -4 })\nequal = true\nbad = Err(\"缺少逗号: (1;2)\")\n",
    "pitfalls": [
        "Display 与 FromStr 不对称：往返解析失败，持久化数据会读不回，需保持一致。",
        "把 Debug 当往返格式：Debug 含类型名与转义，不是稳定格式。",
        "FromStr 的 Err 不实现 Display：`?` 传播与用户提示会受限。"
    ],
    "exercise": {
        "prompt": "为 `#[derive(Debug, PartialEq)] struct Version { major: u8, minor: u8, patch: u8 }` 实现 Display（\"maj.min.patch\"）与 FromStr（解析三段），在 main 中做一次往返并测试一个非法输入。",
        "hint": "Display 用 `write!(f, \"{}.{}.{}\", ...)`；FromStr 用 split('.') 且要求三段。",
        "answer": "use std::fmt;\nuse std::str::FromStr;\n\n#[derive(Debug, PartialEq)]\nstruct Version {\n    major: u8,\n    minor: u8,\n    patch: u8,\n}\n\nimpl fmt::Display for Version {\n    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {\n        write!(f, \"{}.{}.{}\", self.major, self.minor, self.patch)\n    }\n}\n\nimpl FromStr for Version {\n    type Err = String;\n\n    fn from_str(s: &str) -> Result<Self, Self::Err> {\n        let parts: Vec<&str> = s.split('.').collect();\n        if parts.len() != 3 {\n            return Err(format!(\"需要三段版本号: {}\", s));\n        }\n        let parse = |p: &str| p.parse::<u8>().map_err(|_| format!(\"非法段: {}\", p));\n        Ok(Version { major: parse(parts[0])?, minor: parse(parts[1])?, patch: parse(parts[2])? })\n    }\n}\n\nfn main() {\n    let v = Version { major: 1, minor: 2, patch: 3 };\n    let text = v.to_string();\n    println!(\"{}\", text);\n    let back: Result<Version, _> = text.parse();\n    println!(\"{:?}\", back);\n    let bad: Result<Version, _> = \"1.2\".parse();\n    println!(\"{:?}\", bad);\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 81,
    "title": "派生宏与 `derive` 的边界",
    "level": "advanced",
    "domain": "traits-generics",
    "summary": "理解 derive 是“按字段生成实现”的宏，掌握它做不到什么、何时必须手写。",
    "concepts": ["derive 宏", "按字段生成", "手写实现", "语义边界", "声明式 vs 派生"],
    "objective": "能判断某 trait 该派生还是手写，并说明派生背后的按字段语义。",
    "prerequisites": ["080"],
    "explain": "`#[derive]` 是过程宏的一种，编译器为类型生成 trait 实现。大多数标准 trait（Debug、Clone、PartialEq、Eq、Hash、PartialOrd、Ord、Default）都能派生，生成逻辑是“逐字段应用对应操作”：PartialEq 逐字段比较、Hash 逐字段哈希、Default 逐字段默认。边界在于：派生语义是机械的，若你想要不同的语义就必须手写。例如忽略某字段的相等比较、把浮点按容差比较、按 id 而非全字段判等、Default 提供非零值、Clone 做自定义深拷贝。派生还受字段约束传递：某字段不实现该 trait，派生就失败；含 f64 的类型不能派生 Eq/Ord。理解“派生的实现代码长这样”有助于判断何时派生更省事、何时必须手写。想深入宏机制见后续宏章节；本课聚焦使用与选择。补充：`PartialEq` 的契约要求**对称性与传递性**（`a==b` 蕴含 `b==a`，且 `a==b && b==c` 蕴含 `a==c`），并不强制自反；`Eq` 才额外要求自反（`a==a`，且是等价关系）。因此浮点因 `NaN != NaN` 只能实现 `PartialEq` 而非 `Eq`。若手写 `PartialEq` 用按位比较（如 `f64::to_bits`），它是对称且传递的，但会把 `+0.0` 与 `-0.0` 视为不等、把同一位模式的 `NaN` 视为相等——这属于**有意选择**，必须显式记录，否则使用者会误以为遵循 IEEE 的 `==` 语义。",
    "code": "use std::collections::HashSet;\n\n#[derive(Debug, Clone, PartialEq, Eq, Hash)]\nstruct User {\n    id: u32,\n    name: String,\n}\n\n// 手写 PartialEq：只按 id 判等，忽略 name\nstruct Account {\n    id: u32,\n    balance_cents: i64,\n}\n\nimpl PartialEq for Account {\n    fn eq(&self, other: &Self) -> bool {\n        self.id == other.id\n    }\n}\n\nimpl Eq for Account {}\n\nfn main() {\n    let a = User { id: 1, name: String::from(\"Ada\") };\n    let b = a.clone();\n    println!(\"User derive eq = {}\", a == b);\n\n    let mut set: HashSet<User> = HashSet::new();\n    set.insert(a.clone());\n    set.insert(b);\n    println!(\"unique users = {}\", set.len());\n\n    let x = Account { id: 7, balance_cents: 100 };\n    let y = Account { id: 7, balance_cents: 999 };\n    println!(\"Account eq by id = {}\", x == y);\n}\n",
    "output": "User derive eq = true\nunique users = 1\nAccount eq by id = true\n",
    "pitfalls": [
        "以为派生能自定义语义：它只做逐字段机械实现，特殊语义必须手写。",
        "手写 PartialEq 却忘 Eq：需要全等价语义时二者应一起实现（且无浮点字段）。",
        "派生 Hash 却手写 PartialEq 指不同字段：违反“相等则哈希相同”的契约，容器行为错乱。"
    ],
    "exercise": {
        "prompt": "定义 `#[derive(Debug, Clone)] struct TempReading { sensor: String, celsius: f64 }`，手写**满足等价关系**（自反/对称/传递）的 `PartialEq`（逐字段精确相等），并另写独立的 `approx_eq(&self, other: &Self, tolerance: f64) -> bool` 方法表达带容差的近似比较；在 main 中演示精确相等与 0.5 容差的近似结果（含 20.0 与 20.6 不近似以说明传递性问题）。",
        "hint": "手写 eq：`self.sensor == other.sensor && (self.celsius - other.celsius).abs() < 0.5`。",
        "answer": "#[derive(Debug, Clone)]\nstruct TempReading {\n    sensor: String,\n    celsius: f64,\n}\n\n// PartialEq 的契约是【对称性 + 传递性】（并不要求自反；自反是 Eq 的额外要求）。\n// 这里做逐字段精确相等：sensor 相等，且 celsius 的二进制位相同（to_bits）。\nimpl PartialEq for TempReading {\n    fn eq(&self, other: &Self) -> bool {\n        self.sensor == other.sensor && self.celsius.to_bits() == other.celsius.to_bits()\n    }\n}\n\nimpl Eq for TempReading {}\n\nimpl TempReading {\n    // 近似相等是“容差比较”，不是等价关系，故用独立方法表达，而不是 PartialEq\n    fn approx_eq(&self, other: &Self, tolerance: f64) -> bool {\n        self.sensor == other.sensor && (self.celsius - other.celsius).abs() <= tolerance\n    }\n}\n\nfn main() {\n    let a = TempReading { sensor: String::from(\"s1\"), celsius: 20.0 };\n    let b = TempReading { sensor: String::from(\"s1\"), celsius: 20.3 };\n    let c = TempReading { sensor: String::from(\"s1\"), celsius: 20.6 };\n    let d = TempReading { sensor: String::from(\"s2\"), celsius: 20.0 };\n\n    // 精确相等：只有完全相同才为真\n    println!(\"a == b: {}\", a == b);\n    println!(\"a == clone: {}\", a == a.clone());\n\n    // 容差比较：独立方法，避免破坏 PartialEq 的传递性\n    println!(\"a ~ b (0.5): {}\", a.approx_eq(&b, 0.5));\n    println!(\"b ~ c (0.5): {}\", b.approx_eq(&c, 0.5));\n    println!(\"a ~ c (0.5): {}\", a.approx_eq(&c, 0.5));\n    println!(\"a ~ d (0.5): {}\", a.approx_eq(&d, 0.5));\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 82,
    "title": "blanket impl 概念与 coherence",
    "level": "advanced",
    "domain": "traits-generics",
    "summary": "理解“为所有满足条件的类型实现某 trait”的 blanket impl，以及 coherence 对冲突实现和孤儿规则的保护。",
    "concepts": ["blanket impl", "coherence", "重叠实现", "孤儿规则", "标记 trait"],
    "objective": "能解释标准库为何能 `impl<T: Display> ToString for T`，以及为何你不能写冲突实现。",
    "prerequisites": ["079"],
    "explain": "blanket impl 指泛型化的 trait 实现：`impl<T: fmt::Display> ToString for T { ... }` 为所有实现 Display 的类型统一提供 ToString。标准库大量使用它（`From`→`Into`、`Fn`→`FnMut` 等），从而“实现一个就免费获得另一个”。coherence 是保证全局唯一性的规则：对任一类型与 trait，最多只有一个实现，编译器拒绝重叠实现。它配合孤儿规则（trait 或类型至少一个本地）确保不同 crate 不会提供冲突实现。这带来便利也带来限制：你无法为外部类型实现外部 trait，也不能写出与标准库 blanket impl 冲突的实现。理解 coherence 能解释很多“为什么这个 impl 不允许”的报错。想做类似扩展时，标准做法是定义本地 trait 并用 blanket impl 为满足条件的外部类型实现它，或为外部类型做 newtype 包装。blanket impl 要谨慎：过度使用会限制未来新增具体实现的空间。",
    "code": "use std::fmt;\n\n// 本地 trait + blanket impl：为所有实现 Display 的类型提供 banner 能力\npub trait Banner {\n    fn banner(&self) -> String;\n}\n\nimpl<T: fmt::Display> Banner for T {\n    fn banner(&self) -> String {\n        format!(\"=== {} ===\", self)\n    }\n}\n\n// 本地标记 trait，演示 coherence 下的自定义约束\npub trait Primary {}\n\nstruct Conn;\nimpl Primary for Conn {}\n\nfn requires_primary<T: Primary>(_value: &T) -> &'static str {\n    \"ok\"\n}\n\nfn main() {\n    println!(\"{}\", 42.banner());\n    println!(\"{}\", \"text\".banner());\n    println!(\"{}\", \"list\".banner());\n    println!(\"primary = {}\", requires_primary(&Conn));\n    println!(\"coherence 保证全局唯一实现, 拒绝冲突与孤儿实现\");\n}\n",
    "output": "=== 42 ===\n=== text ===\n=== list ===\nprimary = ok\ncoherence 保证全局唯一实现, 拒绝冲突与孤儿实现\n",
    "pitfalls": [
        "尝试为外部类型实现外部 trait：违反孤儿规则，改用本地 trait 或 newtype。",
        "写出重叠的 blanket impl：coherence 会报冲突，即使逻辑上不冲突也要满足编译器规则。",
        "blanket impl 覆盖过广：会阻碍未来为具体类型添加特化实现。"
    ],
    "exercise": {
        "prompt": "定义本地 trait `Doublable { fn doubled(&self) -> Self; }` 并为所有 `Copy + std::ops::Add<Output = Self>` 的类型提供 blanket impl（`*self + *self`），在 main 中对 i32 与 f64 调用并打印。",
        "hint": "`impl<T: Copy + Add<Output = T>> Doublable for T { fn doubled(&self) -> T { *self + *self } }`。",
        "answer": "use std::ops::Add;\n\ntrait Doublable {\n    fn doubled(&self) -> Self;\n}\n\nimpl<T: Copy + Add<Output = T>> Doublable for T {\n    fn doubled(&self) -> Self {\n        *self + *self\n    }\n}\n\nfn main() {\n    println!(\"{}\", 21.doubled());\n    println!(\"{}\", 1.5_f64.doubled());\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 83,
    "title": "扩展 trait（extension trait）模式",
    "level": "advanced",
    "domain": "traits-generics",
    "summary": "为外部类型定义本地扩展 trait 添加方法，绕过孤儿规则同时保持调用点自然。",
    "concepts": ["扩展 trait", "孤儿规则", "本地 trait", "方法链", "trait 导入"],
    "objective": "能写一个扩展 trait，为外部类型添加方法，并说明为何这比自由函数更自然。",
    "prerequisites": ["070"],
    "explain": "你无法直接为外部类型（如 String、Vec）添加固有方法，但可以为它们定义本地 trait 并实现方法——这就是扩展 trait。调用点只需 `use` 该 trait 即可像固有方法一样 `.my_method()`，可读性优于自由函数。要点：扩展 trait 应是本地的（满足孤儿规则）；方法接收者一般用 `&self`/`&mut self`；命名应避免与标准库方法冲突（冲突时需完全限定或改名）。许多流行库（itertools、serde 的扩展）都靠这一模式提供流畅 API。设计上，扩展 trait 适合“在既有类型上组合出领域常用操作”，而不改其定义；也可为泛型约束提供统一扩展。注意 trait 需要在使用处 in scope，否则方法不可见，这是新手的常见困惑。若扩展方法很多，可用 `impl<T: Bound> Ext for T` 做 blanket 扩展，统一服务一类类型。",
    "code": "// 扩展 trait：为 str 添加本地方法\npub trait StrExt {\n    fn shout(&self) -> String;\n    fn word_count(&self) -> usize;\n}\n\nimpl StrExt for str {\n    fn shout(&self) -> String {\n        format!(\"{}!\", self.to_uppercase())\n    }\n\n    fn word_count(&self) -> usize {\n        self.split_whitespace().count()\n    }\n}\n\n// 为所有 Clone + Display 的迭代器元素提供扩展\npub trait SliceExt<T> {\n    fn second(&self) -> Option<&T>;\n}\n\nimpl<T> SliceExt<T> for [T] {\n    fn second(&self) -> Option<&T> {\n        self.get(1)\n    }\n}\n\nfn main() {\n    let text = \"rust ownership model\";\n    println!(\"{}\", text.shout());\n    println!(\"words = {}\", text.word_count());\n\n    let data = [10, 20, 30];\n    println!(\"second = {:?}\", data.second());\n}\n",
    "output": "RUST OWNERSHIP MODEL!\nwords = 3\nsecond = Some(20)\n",
    "pitfalls": [
        "忘记 `use` 扩展 trait：方法不可见，编译器提示 trait 未导入。",
        "扩展方法与标准库方法同名：会产生歧义，需改名或用完全限定语法。",
        "为外部 trait 与外部类型同时做扩展：违反孤儿规则，扩展 trait 必须是本地的。"
    ],
    "exercise": {
        "prompt": "定义扩展 trait `NumExt`，为所有 `PartialOrd + Copy` 类型提供 `clamp_between(&self, lo: Self, hi: Self) -> Self`，在 main 中对 i32 与 f32 调用并打印。",
        "hint": "`impl<T: PartialOrd + Copy> NumExt for T`；实现里用 if 比较返回。",
        "answer": "trait NumExt {\n    fn clamp_between(&self, lo: Self, hi: Self) -> Self;\n}\n\nimpl<T: PartialOrd + Copy> NumExt for T {\n    fn clamp_between(&self, lo: Self, hi: Self) -> Self {\n        let v = *self;\n        if v < lo {\n            lo\n        } else if v > hi {\n            hi\n        } else {\n            v\n        }\n    }\n}\n\nfn main() {\n    println!(\"{}\", 150.clamp_between(0, 100));\n    println!(\"{}\", (-5.0_f32).clamp_between(0.0, 1.0));\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 84,
    "title": "实战：可插拔的序列化抽象（无外部 crate）",
    "level": "advanced",
    "domain": "traits-generics",
    "summary": "用 trait 对象与扩展设计一个可插拔的序列化层，支持多种格式并在运行时选择。",
    "concepts": ["可插拔设计", "trait 对象", "序列化抽象", "策略模式", "确定性输出"],
    "objective": "能设计一个序列化 trait 与多种实现，通过注册表按名选择并统一调用。",
    "prerequisites": ["077"],
    "explain": "综合本域能力，设计一个“可插拔序列化”小系统：定义 `trait Codec { fn name(&self) -> &'static str; fn encode(&self, record: &Record) -> String; }`，为 Json（手写简易）、KeyValue、Csv（单记录）分别实现；用 `Vec<Box<dyn Codec>>` 注册；提供按名查找并编码。要点：用 trait 把“格式”与“数据”解耦；用 trait 对象让运行时选择成为可能；输出确定性（固定字段顺序、固定分隔符）。实现手写 JSON 时注意字符串转义与字段顺序，避免依赖 HashMap 的迭代顺序（用切片保序）。这是“策略模式”在 Rust 中的典型落地：接口 + 多实现 + 注册表。它预演了后续章节的序列化、插件与插件式命令行设计。设计时把错误与格式细节封装在各实现内，调用方只面对统一接口。",
    "code": "trait Codec {\n    fn name(&self) -> &'static str;\n    fn encode(&self, record: &Record) -> String;\n}\n\n#[derive(Debug)]\nstruct Record {\n    id: u32,\n    name: String,\n    note: String,\n    active: bool,\n}\n\n// 完整 JSON 字符串转义：引号、反斜杠、常见控制字符，其余控制字符用 \\u00XX 表示。\nfn json_escape(s: &str) -> String {\n    let mut out = String::with_capacity(s.len());\n    for c in s.chars() {\n        match c {\n            '\"' => out.push_str(\"\\\\\\\"\"),\n            '\\\\' => out.push_str(\"\\\\\\\\\"),\n            '\\n' => out.push_str(\"\\\\n\"),\n            '\\r' => out.push_str(\"\\\\r\"),\n            '\\t' => out.push_str(\"\\\\t\"),\n            '\\u{08}' => out.push_str(\"\\\\b\"),\n            '\\u{0c}' => out.push_str(\"\\\\f\"),\n            c if (c as u32) < 0x20 => out.push_str(&format!(\"\\\\u{:04x}\", c as u32)),\n            c => out.push(c),\n        }\n    }\n    out\n}\n\n// RFC 4180 风格 CSV 字段转义：含逗号/引号/换行时用双引号包裹，内部引号翻倍。\nfn csv_escape(s: &str) -> String {\n    if s.contains(',') || s.contains('\"') || s.contains('\\n') || s.contains('\\r') {\n        format!(\"\\\"{}\\\"\", s.replace('\"', \"\\\"\\\"\"))\n    } else {\n        s.to_string()\n    }\n}\n\n// key=value 也需转义分隔符，避免值里的 ';' / '=' 破坏结构。\nfn kv_escape(s: &str) -> String {\n    s.replace('\\\\', \"\\\\\\\\\").replace(';', \"\\\\;\").replace('=', \"\\\\=\")\n}\n\nstruct JsonCodec;\nstruct KeyValueCodec;\nstruct CsvCodec;\n\nimpl Codec for JsonCodec {\n    fn name(&self) -> &'static str {\n        \"json\"\n    }\n    fn encode(&self, r: &Record) -> String {\n        format!(\n            \"{{\\\"id\\\":{},\\\"name\\\":\\\"{}\\\",\\\"note\\\":\\\"{}\\\",\\\"active\\\":{}}}\",\n            r.id, json_escape(&r.name), json_escape(&r.note), r.active\n        )\n    }\n}\n\nimpl Codec for KeyValueCodec {\n    fn name(&self) -> &'static str {\n        \"kv\"\n    }\n    fn encode(&self, r: &Record) -> String {\n        format!(\n            \"id={};name={};note={};active={}\",\n            r.id,\n            kv_escape(&r.name),\n            kv_escape(&r.note),\n            r.active\n        )\n    }\n}\n\nimpl Codec for CsvCodec {\n    fn name(&self) -> &'static str {\n        \"csv\"\n    }\n    fn encode(&self, r: &Record) -> String {\n        format!(\n            \"{},{},{},{}\",\n            r.id, csv_escape(&r.name), csv_escape(&r.note), r.active\n        )\n    }\n}\n\nfn registry() -> Vec<Box<dyn Codec>> {\n    vec![Box::new(JsonCodec), Box::new(KeyValueCodec), Box::new(CsvCodec)]\n}\n\nfn encode_with(registry: &[Box<dyn Codec>], name: &str, record: &Record) -> Option<String> {\n    registry\n        .iter()\n        .find(|c| c.name() == name)\n        .map(|c| c.encode(record))\n}\n\nfn main() {\n    // 含中文、引号、反斜杠、换行、逗号、制表符与分号的记录\n    let record = Record {\n        id: 7,\n        name: String::from(\"a\\\"b\\\\c\"),\n        note: String::from(\"行1\\n行2, 带\\\"引号\\\"\\t与中文; 分隔=符\"),\n        active: true,\n    };\n    let reg = registry();\n    for name in [\"json\", \"kv\", \"csv\", \"yaml\"] {\n        match encode_with(&reg, name, &record) {\n            Some(text) => println!(\"{:<5} => {}\", name, text),\n            None => println!(\"{:<5} => 未注册\", name),\n        }\n    }\n}\n",
    "output": "json  => {\"id\":7,\"name\":\"a\\\"b\\\\c\",\"note\":\"行1\\n行2, 带\\\"引号\\\"\\t与中文; 分隔=符\",\"active\":true}\nkv    => id=7;name=a\"b\\\\c;note=行1\n行2, 带\"引号\"\t与中文\\; 分隔\\=符;active=true\ncsv   => 7,\"a\"\"b\\c\",\"行1\n行2, 带\"\"引号\"\"\t与中文; 分隔=符\",true\nyaml  => 未注册\n",
    "pitfalls": [
        "序列化依赖 HashMap 迭代顺序：输出不确定，应用切片或排序保证字段顺序。",
        "忘记转义特殊字符：手写 JSON 时引号/反斜杠会导致非法输出。",
        "把格式选择写死在调用点：用注册表 + trait 对象才能运行时插拔。"
    ],
    "exercise": {
        "prompt": "扩展本序列化系统：为包含中文、引号、反斜杠、换行、逗号与制表符的记录实现正确转义——`json_escape` 处理 `\" \\ \\n \\r \\t \\b \\f` 及其余控制字符（`\\u00XX`），`csv_escape` 按 RFC 4180 在含逗号/引号/换行时用双引号包裹并将内部引号翻倍；实现 JsonCodec 与 CsvCodec 并在 main 中打印两者的真实输出。",
        "hint": "复制 JsonCodec 的 escape；格式字符串用 `\\n` 换行；name 字段类型标注 string。",
        "answer": "trait Codec {\n    fn name(&self) -> &'static str;\n    fn encode(&self, record: &Record) -> String;\n}\n\n#[derive(Debug)]\nstruct Record {\n    id: u32,\n    name: String,\n    note: String,\n    active: bool,\n}\n\n// 完整 JSON 字符串转义：引号、反斜杠、常见控制字符，其余控制字符用 \\u00XX 表示。\nfn json_escape(s: &str) -> String {\n    let mut out = String::with_capacity(s.len());\n    for c in s.chars() {\n        match c {\n            '\"' => out.push_str(\"\\\\\\\"\"),\n            '\\\\' => out.push_str(\"\\\\\\\\\"),\n            '\\n' => out.push_str(\"\\\\n\"),\n            '\\r' => out.push_str(\"\\\\r\"),\n            '\\t' => out.push_str(\"\\\\t\"),\n            '\\u{08}' => out.push_str(\"\\\\b\"),\n            '\\u{0c}' => out.push_str(\"\\\\f\"),\n            c if (c as u32) < 0x20 => out.push_str(&format!(\"\\\\u{:04x}\", c as u32)),\n            c => out.push(c),\n        }\n    }\n    out\n}\n\n// RFC 4180 风格 CSV 字段转义：含逗号/引号/换行时用双引号包裹，内部引号翻倍。\nfn csv_escape(s: &str) -> String {\n    if s.contains(',') || s.contains('\"') || s.contains('\\n') || s.contains('\\r') {\n        format!(\"\\\"{}\\\"\", s.replace('\"', \"\\\"\\\"\"))\n    } else {\n        s.to_string()\n    }\n}\n\nstruct JsonCodec;\nstruct CsvCodec;\n\nimpl Codec for JsonCodec {\n    fn name(&self) -> &'static str {\n        \"json\"\n    }\n    fn encode(&self, r: &Record) -> String {\n        format!(\n            \"{{\\\"id\\\":{},\\\"name\\\":\\\"{}\\\",\\\"note\\\":\\\"{}\\\",\\\"active\\\":{}}}\",\n            r.id, json_escape(&r.name), json_escape(&r.note), r.active\n        )\n    }\n}\n\nimpl Codec for CsvCodec {\n    fn name(&self) -> &'static str {\n        \"csv\"\n    }\n    fn encode(&self, r: &Record) -> String {\n        format!(\n            \"{},{},{},{}\",\n            r.id, csv_escape(&r.name), csv_escape(&r.note), r.active\n        )\n    }\n}\n\nfn main() {\n    // 含中文、引号、反斜杠、换行、逗号、制表符的记录\n    let record = Record {\n        id: 7,\n        name: String::from(\"a\\\"b\\\\c\"),\n        note: String::from(\"行1\\n行2, 带\\\"引号\\\"\\t与中文\"),\n        active: true,\n    };\n\n    let codecs: Vec<Box<dyn Codec>> = vec![Box::new(JsonCodec), Box::new(CsvCodec)];\n    for codec in &codecs {\n        println!(\"{} => {}\", codec.name(), codec.encode(&record));\n    }\n}\n"
    },
    "runtime": "desktop"
},
]
