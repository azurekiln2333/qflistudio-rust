# -*- coding: utf-8 -*-
"""Lessons 024..032 (Domain B, part 2)."""

LESSONS = [
{
    "id": 24,
    "title": "函数、参数与返回类型",
    "level": "beginner",
    "domain": "syntax-types",
    "summary": "定义带类型参数的函数，理解返回值、表达式尾值、多返回值与递归。",
    "concepts": ["fn", "参数类型", "返回类型", "尾表达式", "递归"],
    "objective": "能写出签名单一职责的函数，区分尾表达式与 `return`，并实现简单递归。",
    "prerequisites": ["019"],
    "explain": "函数用 `fn name(param: Type, ...) -> Ret { body }` 定义，参数与返回类型都必须标注（不像局部变量可推断）。函数体的最后一行若不加分号就是尾表达式，其值即返回值；`return` 用于提前返回，但惯用风格是尽量用尾表达式，减少控制流跳跃。返回 `()` 时可省略 `-> ()`。多个返回值用元组或结构体。递归函数必须要有收敛条件，否则栈溢出；Rust 没有强制尾调用优化，深递归应改成迭代。函数可以嵌套定义（内部 fn 可访问外部类型），也可通过 `impl` 关联函数与方法（下一课）。签名设计原则：参数用最小够用的抽象（`&[T]` 而非 `&Vec<T>`），返回 `Option`/`Result` 表达可能失败，而不是靠魔法值。",
    "code": "fn compose_greeting(name: &str, times: usize) -> String {\n    let mut out = String::new();\n    for i in 0..times {\n        if i > 0 {\n            out.push_str(\", \");\n        }\n        out.push_str(name);\n    }\n    out\n}\n\nfn factorial(n: u64) -> u64 {\n    if n <= 1 {\n        1\n    } else {\n        n * factorial(n - 1)\n    }\n}\n\nfn divmod(a: u32, b: u32) -> (u32, u32) {\n    (a / b, a % b)\n}\n\nfn main() {\n    println!(\"{}\", compose_greeting(\"Rust\", 3));\n    println!(\"factorial(5) = {}\", factorial(5));\n    let (q, r) = divmod(17, 5);\n    println!(\"divmod(17, 5) = ({}, {})\", q, r);\n}\n",
    "output": "Rust, Rust, Rust\nfactorial(5) = 120\ndivmod(17, 5) = (3, 2)\n",
    "pitfalls": [
        "忘记标注参数类型：函数签名不允许类型推断，必须显式写出。",
        "尾表达式加了分号：返回值会变成 `()`，与声明的返回类型不符而报错。",
        "递归没有基例：会无限递归导致栈溢出（不是编译错误）。"
    ],
    "exercise": {
        "prompt": "写函数 `is_power_of_two(n: u64) -> bool` 与 `count_digits(n: u64) -> usize`，并在 main 中打印 `is_power_of_two(64)` 与 `count_digits(12345)`。",
        "hint": "2 的幂满足 `n != 0 && n & (n - 1) == 0`；位数用循环除以 10 计数。",
        "answer": "fn is_power_of_two(n: u64) -> bool {\n    n != 0 && n & (n - 1) == 0\n}\n\nfn count_digits(mut n: u64) -> usize {\n    if n == 0 {\n        return 1;\n    }\n    let mut count = 0;\n    while n > 0 {\n        count += 1;\n        n /= 10;\n    }\n    count\n}\n\nfn main() {\n    println!(\"{}\", is_power_of_two(64));\n    println!(\"{}\", count_digits(12345));\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 25,
    "title": "复合类型：struct 定义与实例化",
    "level": "beginner",
    "domain": "syntax-types",
    "summary": "用命名字段的结构体给数据加语义，掌握字段初始化简写、更新语法与元组结构体。",
    "concepts": ["struct", "字段", "字段初始化简写", "..update", "元组结构体"],
    "objective": "能定义结构体并实例化，正确使用简写与更新语法，理解其内存布局是字段顺序排列。",
    "prerequisites": ["024"],
    "explain": "`struct Name { field: Type, ... }` 把一组相关数据打包成命名类型，比元组更具可读性，也为后续实现方法、trait 提供载体。实例化 `Name { field: value }`；若变量名与字段名相同可用简写 `Name { x, y }`。更新语法 `Name { field: new, ..old }` 复用旧实例的其余字段（要求 old 的类型兼容，未复制的字段若是非 Copy 会被移动）。元组结构体 `struct Point(i32, i32);` 有位置字段 `.0`，适合轻量包装；单元结构体 `struct Marker;` 常作类型标记。结构体默认在栈上（除非含堆字段）。要注意 `repr(Rust)`（默认表示）既**不保证字段按声明顺序排列**——编译器可自由重排字段以减小体积或对齐——也不保证与 C 的布局兼容；因此依赖字段顺序做二进制解释、序列化或 FFI 都是错误的，需要稳定布局时显式使用 `repr(C)`（后续 FFI 课）。实例化必须提供所有字段，除非有 `Default`。",
    "code": "#[derive(Debug)]\nstruct Rectangle {\n    width: u32,\n    height: u32,\n}\n\n#[derive(Debug, Clone, Copy)]\nstruct Point(i32, i32);\n\nfn main() {\n    let width = 6;\n    let r1 = Rectangle { width, height: 4 };\n    println!(\"r1 = {:?}\", r1);\n    println!(\"面积 = {}\", r1.width * r1.height);\n\n    let r2 = Rectangle { width: 10, ..r1 };\n    println!(\"r2 = {:?}\", r2);\n\n    let p = Point(3, -2);\n    println!(\"p = {:?}, p.0 = {}\", p, p.0);\n\n    let Point(x, y) = p;\n    println!(\"解构 point: x = {}, y = {}\", x, y);\n}\n",
    "output": "r1 = Rectangle { width: 6, height: 4 }\n面积 = 24\nr2 = Rectangle { width: 10, height: 4 }\np = Point(3, -2), p.0 = 3\n解构 point: x = 3, y = -2\n",
    "pitfalls": [
        "实例化漏字段：必须给出全部字段，或用 `..base` 复用，或实现 `Default`。",
        "更新语法误以为深拷贝：非 Copy 字段会被移动，之后不能再使用旧实例的那个字段。",
        "依赖字段顺序做二进制兼容：默认 repr(Rust) 布局未保证，跨语言/序列化要用 `repr(C)` 或显式编码。"
    ],
    "exercise": {
        "prompt": "定义 `Book { title: String, pages: u32 }`，实例化两本，用更新语法基于第一本生成第二本（只改 pages），并打印两本的标题与页数。",
        "hint": "第二本写 `Book { pages: 500, ..first.clone() }`，避免 first 的 title 被移动。",
        "answer": "#[derive(Debug, Clone)]\nstruct Book {\n    title: String,\n    pages: u32,\n}\n\nfn main() {\n    let first = Book { title: String::from(\"Rust 入门\"), pages: 320 };\n    let second = Book { pages: 500, ..first.clone() };\n    println!(\"first  = {} ({} 页)\", first.title, first.pages);\n    println!(\"second = {} ({} 页)\", second.title, second.pages);\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 26,
    "title": "方法、关联函数与 `impl`",
    "level": "beginner",
    "domain": "syntax-types",
    "summary": "在 impl 块中为结构体添加方法与关联函数，理解 self、&self、&mut self 的接收者差异。",
    "concepts": ["impl", "self", "&mut self", "关联函数", "多重 impl"],
    "objective": "能区分关联函数与方法的调用方式，并根据是否需要修改选择接收者形式。",
    "prerequisites": ["025"],
    "explain": "`impl Type { fn ... }` 为类型添加方法：接收者是 `self`（按值，消费实例）、`&self`（共享借用，只读）、`&mut self`（独占借用，可改）。接收者写成 `self: &Self` 等形式，`.` 调用会自动借用。没有 self 的函数是关联函数，用 `Type::func()` 调用，典型是构造函数 `Type::new(...)`。可以有多个 `impl` 块，`impl` 也能为泛型类型或带约束的类型实现方法。方法解析顺序：先找固有方法，再找 trait 方法；有冲突时用 `Type::method(&obj)` 或完全限定语法消歧。设计上，构造函数返回 `Self`，可能失败的构造返回 `Result<Self, E>`；getter 用 `&self`，mutator 用 `&mut self`，消费型转换用 `self`。把与类型强相关的行为放进 `impl`，可让 API 面向对象地表达。",
    "code": "#[derive(Debug)]\nstruct Counter {\n    value: i64,\n    step: i64,\n}\n\nimpl Counter {\n    // 关联函数：构造器\n    fn new(step: i64) -> Self {\n        Counter { value: 0, step }\n    }\n\n    // &mut self：修改内部状态\n    fn tick(&mut self) {\n        self.value += self.step;\n    }\n\n    // &self：只读访问\n    fn value(&self) -> i64 {\n        self.value\n    }\n\n    // self：消费并转换\n    fn into_doubled(self) -> i64 {\n        self.value * 2\n    }\n}\n\nfn main() {\n    let mut counter = Counter::new(3);\n    counter.tick();\n    counter.tick();\n    println!(\"value = {}\", counter.value());\n    let doubled = counter.into_doubled();\n    println!(\"doubled = {}\", doubled);\n}\n",
    "output": "value = 6\ndoubled = 12\n",
    "pitfalls": [
        "在 `&self` 方法里改字段：只读借用不能可变访问，需要 `&mut self`。",
        "把关联函数当方法调用：`Type::new()` 没有 self 接收者，写成 `obj.new()` 会失败。",
        "调用消费型 `self` 方法后继续用原实例：所有权已移走，后续使用会报 E0382。"
    ],
    "exercise": {
        "prompt": "定义 `Stack { items: Vec<i32> }`，实现 `new()`、`push(&mut self, v)`、`pop(&mut self) -> Option<i32>`、`peek(&self) -> Option<i32>`，在 main 中演示入栈、查看与出栈。",
        "hint": "用 `Vec` 的 push/pop/last；peek 用 `self.items.last().copied()` 返回副本。",
        "answer": "struct Stack {\n    items: Vec<i32>,\n}\n\nimpl Stack {\n    fn new() -> Self {\n        Stack { items: Vec::new() }\n    }\n\n    fn push(&mut self, v: i32) {\n        self.items.push(v);\n    }\n\n    fn pop(&mut self) -> Option<i32> {\n        self.items.pop()\n    }\n\n    fn peek(&self) -> Option<i32> {\n        self.items.last().copied()\n    }\n}\n\nfn main() {\n    let mut s = Stack::new();\n    s.push(1);\n    s.push(2);\n    println!(\"peek = {:?}\", s.peek());\n    println!(\"pop  = {:?}\", s.pop());\n    println!(\"peek = {:?}\", s.peek());\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 27,
    "title": "枚举与携带数据",
    "level": "beginner",
    "domain": "syntax-types",
    "summary": "用枚举表达“多选一”的取值，理解变体可携带不同数据，形成代数数据类型。",
    "concepts": ["enum", "变体", "携带数据", "代数数据类型", "Option 本质"],
    "objective": "能定义携带数据的枚举并用 match 处理，理解枚举是“标签 + 数据”的联合。",
    "prerequisites": ["026"],
    "explain": "枚举定义一组互斥的变体：`enum Shape { Circle(f64), Rect { w: f64, h: f64 }, Point }`。每个变体可携带不同数据（元组式、结构体式或单元式），因此枚举是“标签联合”，本质是代数数据类型，能精确建模“要么…要么…”。`Option<T>` 和 `Result<T, E>` 就是标准库枚举。构造变体用 `Shape::Circle(1.0)` 或 `Shape::Rect { w: 2.0, h: 3.0 }`。处理枚举用 match 并逐一列出变体——编译器会强制你覆盖，新增变体时相关 match 会编译失败提醒更新，这是巨大优势。枚举可带 impl、可实现 trait、可泛型。相比“用一个 flag 加若干可为空的字段”，枚举让非法状态不可表示（make illegal states unrepresentable）。",
    "code": "#[derive(Debug)]\nenum Shape {\n    Circle(f64),\n    Rect { width: f64, height: f64 },\n    Square(f64),\n}\n\nimpl Shape {\n    fn area(&self) -> f64 {\n        match self {\n            Shape::Circle(r) => std::f64::consts::PI * r * r,\n            Shape::Rect { width, height } => width * height,\n            Shape::Square(side) => side * side,\n        }\n    }\n}\n\nfn main() {\n    let shapes = [Shape::Circle(1.0), Shape::Rect { width: 2.0, height: 3.0 }, Shape::Square(4.0)];\n    for s in &shapes {\n        println!(\"{:?} -> area = {:.4}\", s, s.area());\n    }\n}\n",
    "output": "Circle(1.0) -> area = 3.1416\nRect { width: 2.0, height: 3.0 } -> area = 6.0000\nSquare(4.0) -> area = 16.0000\n",
    "pitfalls": [
        "用字符串或整数常量代替枚举：会失去类型安全与穷尽检查，改不动时才发现拼错。",
        "match 里只处理部分变体：编译报 E0004，必须覆盖所有变体或加 `_`（但加 `_` 会失去穷尽保护）。",
        "在 `&self` 方法中移动枚举内的非 Copy 数据：应借用或克隆，不能把 `self` 里的值移出。"
    ],
    "exercise": {
        "prompt": "定义 `enum Token { Number(i64), Ident(String), Op(char) }`，实现 `describe(&self) -> String` 返回可读描述，并在 main 中打印三种 token 的描述。",
        "hint": "match 三个变体，Number 用 format!(\"数字 {}\", n)，Op 判断是否为已知运算符。",
        "answer": "#[derive(Debug)]\nenum Token {\n    Number(i64),\n    Ident(String),\n    Op(char),\n}\n\nimpl Token {\n    fn describe(&self) -> String {\n        match self {\n            Token::Number(n) => format!(\"数字 {}\", n),\n            Token::Ident(name) => format!(\"标识符 {}\", name),\n            Token::Op(c) => format!(\"运算符 '{}'\", c),\n        }\n    }\n}\n\nfn main() {\n    let tokens = [Token::Number(42), Token::Ident(String::from(\"sum\")), Token::Op('+')];\n    for t in &tokens {\n        println!(\"{}\", t.describe());\n    }\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 28,
    "title": "类型别名、常量与静态变量",
    "level": "beginner",
    "domain": "syntax-types",
    "summary": "用 type 给类型起别名、用 const 定义编译期常量、用 static 定义全局变量，并理解三者边界。",
    "concepts": ["type 别名", "const", "static", "static mut", "编译期求值"],
    "objective": "能根据用途在 type/const/static 之间选择，并说明为什么 `static mut` 不安全。",
    "prerequisites": ["024"],
    "explain": "`type Alias = T;` 只是编译期的重命名，不产生新类型，`Alias` 与 `T` 完全等价（不像 newtype 能区分）。`const NAME: T = value;` 是必须编译期可求值的常量，每次使用都内联替换，没有固定地址，可用于数组长度与 const 泛型。`static NAME: T = value;` 有固定内存地址、生命周期是 `'static`，在程序中仅一份；可变的 `static mut` 需要 `unsafe` 访问，极易造成数据竞争，在多线程场景应改用 `Atomic*` 或 `Mutex`。常量命名惯例是 `SCREAMING_SNAKE_CASE`。用 const 表达配置上限、用 static 表达单例只读表、用 type 简化复杂签名（如 `type Table = HashMap<String, Vec<i32>>;`）。三者的选择影响性能（const 可被优化内联）与语义（static 有地址）。",
    "code": "use std::collections::HashMap;\n\ntype Table = HashMap<String, Vec<i32>>;\n\nconst MAX_LEN: usize = 4;\nconst GREETING: &str = \"hello\";\nstatic DEFAULT_STEP: i32 = 2;\n\nfn main() {\n    let mut table: Table = Table::new();\n    table.insert(String::from(\"a\"), vec![1, 2, 3, 4]);\n\n    for (key, values) in &table {\n        let trimmed: Vec<i32> = values.iter().copied().take(MAX_LEN).collect();\n        println!(\"{} -> {:?}\", key, trimmed);\n    }\n\n    println!(\"GREETING = {}, DEFAULT_STEP = {}\", GREETING, DEFAULT_STEP);\n    println!(\"数组长度取自 const:\");\n    let buffer = [0u8; MAX_LEN];\n    println!(\"buffer_len = {}\", buffer.len());\n}\n",
    "output": "a -> [1, 2, 3, 4]\nGREETING = hello, DEFAULT_STEP = 2\n数组长度取自 const:\nbuffer_len = 4\n",
    "pitfalls": [
        "以为 type 别名是强类型：它与原类型完全同一，需要区分时用 newtype 结构体。",
        "用 `static mut` 做全局可变状态：需要 unsafe 且易数据竞争，应改原子类型或锁。",
        "把运行期才能算出的值写成 const：const 必须编译期可求值，否则编译失败。"
    ],
    "exercise": {
        "prompt": "用 `type Matrix = Vec<Vec<i32>>;` 与 `const SIZE: usize = 3;` 构造一个 3x3 单位矩阵并打印每一行。",
        "hint": "双重循环，`row[i] = if i == j { 1 } else { 0 }`。",
        "answer": "type Matrix = Vec<Vec<i32>>;\nconst SIZE: usize = 3;\n\nfn main() {\n    let mut m: Matrix = vec![vec![0; SIZE]; SIZE];\n    for i in 0..SIZE {\n        for j in 0..SIZE {\n            m[i][j] = if i == j { 1 } else { 0 };\n        }\n    }\n    for row in &m {\n        println!(\"{:?}\", row);\n    }\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 29,
    "title": "强类型新类型模式（newtype）",
    "level": "beginner",
    "domain": "syntax-types",
    "summary": "用只含一个字段的结构体包装基础类型，在编译期区分语义不同的值，防止参数顺序错误。",
    "concepts": ["newtype", "类型安全", "零成本抽象", "智能构造器", "Deref 预告"],
    "objective": "能用 newtype 消除“同为 u64 却含义不同”的混乱，并实现校验型构造函数。",
    "prerequisites": ["027"],
    "explain": "newtype 是 `struct Meters(f64);` 这样的单字段元组结构体。编译后它与内层类型通常有相同布局（零成本），但类型系统视其为全新类型，因此不能把 `Meters` 当 `Seconds` 传参，避免量纲混淆。它还能在不违反孤儿规则的前提下为外部类型实现外部 trait（因为 `Meters` 是本地类型）。常用手法是“智能构造器”：`fn new(v: f64) -> Option<Self>`，把不变量（非负、范围内）固化成类型保证，之后内部代码可信任该不变量。要访问内部值需解构 `m.0` 或实现 `Deref`；也可用 `From`/`Into` 提供显式转换。大量同构数值（id、金额、长度）混用时，newtype 能以极低代价显著提升正确性与可读性。",
    "code": "use std::ops::Add;\n\n#[derive(Debug, Clone, Copy, PartialEq)]\nstruct Meters(f64);\n\n#[derive(Debug, Clone, Copy, PartialEq)]\nstruct Seconds(f64);\n\nimpl Meters {\n    fn new(value: f64) -> Option<Self> {\n        if value.is_finite() && value >= 0.0 {\n            Some(Meters(value))\n        } else {\n            None\n        }\n    }\n}\n\nimpl Add for Meters {\n    type Output = Meters;\n    fn add(self, rhs: Meters) -> Meters {\n        Meters(self.0 + rhs.0)\n    }\n}\n\nfn speed(distance: Meters, time: Seconds) -> f64 {\n    distance.0 / time.0\n}\n\nfn main() {\n    let a = Meters::new(100.0).unwrap();\n    let b = Meters::new(50.0).unwrap();\n    println!(\"sum = {:?}\", a + b);\n    println!(\"invalid = {:?}\", Meters::new(-1.0));\n    println!(\"speed = {:.2} m/s\", speed(a, Seconds(10.0)));\n}\n",
    "output": "sum = Meters(150.0)\ninvalid = None\nspeed = 10.00 m/s\n",
    "pitfalls": [
        "直接把内层值公开：若外部能随意构造，不变量就守不住，应提供受校验的构造函数。",
        "把 newtype 当零负担就一定方便：访问内部值需 `.0` 或 Deref，转换要显式，别滥用。",
        "为 newtype 实现 Deref 到内层以图省事：这会削弱类型区分，通常不如显式方法。"
    ],
    "exercise": {
        "prompt": "定义 newtype `Percentage(u8)`，构造函数只接受 0..=100，实现 `value(&self) -> u8`，并在 main 中演示合法与非法输入。",
        "hint": "`fn new(v: u8) -> Option<Self> { (v <= 100).then_some(Percentage(v)) }`。",
        "answer": "#[derive(Debug, Clone, Copy)]\nstruct Percentage(u8);\n\nimpl Percentage {\n    fn new(value: u8) -> Option<Self> {\n        if value <= 100 {\n            Some(Percentage(value))\n        } else {\n            None\n        }\n    }\n\n    fn value(&self) -> u8 {\n        self.0\n    }\n}\n\nfn main() {\n    println!(\"{:?}\", Percentage::new(75).map(|p| p.value()));\n    println!(\"{:?}\", Percentage::new(120));\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 30,
    "title": "运算符重载预告：`Add` 背后的 trait",
    "level": "beginner",
    "domain": "syntax-types",
    "summary": "通过为自定义类型实现 `Add` 等运算 trait，理解 `+` 只是方法调用的语法糖。",
    "concepts": ["std::ops::Add", "trait 实现", "运算符方法", "AddAssign", "语法糖"],
    "objective": "能为自定义类型实现 `Add`/`Mul`，并解释运算符表达式如何被脱糖为 trait 方法。",
    "prerequisites": ["026"],
    "explain": "Rust 的运算符是 trait 的语法糖：`a + b` 会脱糖为 `Add::add(a, b)`。要让自己类型支持 `+`，实现 `std::ops::Add` 并指定 `type Output`。类似地，`+=` 对应 `AddAssign`，`*` 对应 `Mul`，`[]` 对应 `Index`，`==` 对应 `PartialEq`。这些 trait 定义在标准库，符合孤儿规则的实现是允许的（因为你的类型是本地类型）。注意实现应遵守运算的数学期望（如加法交换律），否则会让使用者困惑。对 newtype 数值特别有用：你可以精确控制哪些运算允许、与何种类型运算。若要让 `f64 + Meters` 之类也成立，需要为内层类型一侧也实现 trait——但受孤儿规则限制，只有当一侧是本地类型时才可。",
    "code": "use std::ops::{Add, Mul};\n\n#[derive(Debug, Clone, Copy, PartialEq)]\nstruct Vec2 {\n    x: f64,\n    y: f64,\n}\n\nimpl Add for Vec2 {\n    type Output = Vec2;\n    fn add(self, rhs: Vec2) -> Vec2 {\n        Vec2 { x: self.x + rhs.x, y: self.y + rhs.y }\n    }\n}\n\nimpl Mul<f64> for Vec2 {\n    type Output = Vec2;\n    fn mul(self, rhs: f64) -> Vec2 {\n        Vec2 { x: self.x * rhs, y: self.y * rhs }\n    }\n}\n\nfn main() {\n    let a = Vec2 { x: 1.0, y: 2.0 };\n    let b = Vec2 { x: 3.0, y: 4.0 };\n    println!(\"a + b  = {:?}\", a + b);\n    println!(\"a * 2  = {:?}\", a * 2.0);\n    println!(\"a + b == vec2(4, 6): {}\", a + b == Vec2 { x: 4.0, y: 6.0 });\n}\n",
    "output": "a + b  = Vec2 { x: 4.0, y: 6.0 }\na * 2  = Vec2 { x: 2.0, y: 4.0 }\na + b == vec2(4, 6): true\n",
    "pitfalls": [
        "忘了指定 `type Output`：Add trait 要求关联类型 Output，缺了会编译失败。",
        "实现违反直觉语义：让 `+` 做减法之类会严重误导使用者，运算符应遵守惯用含义。",
        "试图为两个外部类型实现 trait：违反孤儿规则，至少一侧必须是本地类型。"
    ],
    "exercise": {
        "prompt": "定义 `struct Money(i64)`（单位：分），实现 `Add` 使金额可相加，并实现 `AddAssign<i64>` 使 `+=` 接受增量分值；在 main 中演示。",
        "hint": "`Add for Money` 返回 `Money(self.0 + rhs.0)`；`AddAssign<i64>` 里 `self.0 += rhs`。",
        "answer": "use std::ops::{Add, AddAssign};\n\n#[derive(Debug, Clone, Copy, PartialEq)]\nstruct Money(i64);\n\nimpl Add for Money {\n    type Output = Money;\n    fn add(self, rhs: Money) -> Money {\n        Money(self.0 + rhs.0)\n    }\n}\n\nimpl AddAssign<i64> for Money {\n    fn add_assign(&mut self, rhs: i64) {\n        self.0 += rhs;\n    }\n}\n\nfn main() {\n    let mut m = Money(1999);\n    m += 501;\n    println!(\"{:?}\", m);\n    println!(\"{:?}\", Money(1000) + Money(250));\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 31,
    "title": "格式化输出：`Display`/`Debug`/格式说明符",
    "level": "beginner",
    "domain": "syntax-types",
    "summary": "区分 Display 与 Debug 两种格式化 trait，掌握宽度、精度、进制与命名参数等说明符。",
    "concepts": ["Display", "Debug", "格式说明符", "宽度精度", "命名参数"],
    "objective": "能为自定义类型实现 Display 与 Debug，并按需组合格式说明符产生稳定输出。",
    "prerequisites": ["025"],
    "explain": "`{}` 需要 `Display`，`{:?}` 需要 `Debug`，`{:#?}` 是美化 Debug。标准库为多数内置类型实现了它们；自定义结构体用 `#[derive(Debug)]` 最省事，而 `Display` 必须手写（因为它表达面向用户的展示语义）。格式说明符可组合：宽度 `{:>8}`、填充 `{:*^8}`、精度 `{:.3}`、进制 `{:x}`/`{:b}`/`{:o}`、加号 `{:+}`、命名参数 `{name}`、按位置 `{0}`。格式化是实现 `std::fmt::Display` 的 `fmt` 方法，向 `f` 写入。`println!`/`format!`/`write!` 共用同一套机制。注意 Display 不应产生歧义或隐藏信息（那属于 Debug），且实现应稳定——测试常依赖格式化输出。",
    "code": "use std::fmt;\n\n#[derive(Debug)]\nstruct Temperature {\n    celsius: f64,\n}\n\nimpl fmt::Display for Temperature {\n    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {\n        write!(f, \"{:.1}°C\", self.celsius)\n    }\n}\n\nfn main() {\n    let t = Temperature { celsius: 36.6 };\n    println!(\"Display: {}\", t);\n    println!(\"Debug:   {:?}\", t);\n\n    let pi = std::f64::consts::PI;\n    println!(\"默认 {:.3}\", pi);\n    println!(\"宽度 [{:>8.3}]\", pi);\n    println!(\"左对齐填充 [{:*<8.3}]\", pi);\n    println!(\"进制: hex={:x} bin={:b}\", 255, 10);\n    println!(\"命名参数 {name} 今年 {age} 岁\", name = \"Rust\", age = 14);\n}\n",
    "output": "Display: 36.6°C\nDebug:   Temperature { celsius: 36.6 }\n默认 3.142\n宽度 [   3.142]\n左对齐填充 [3.142***]\n进制: hex=ff bin=1010\n命名参数 Rust 今年 14 岁\n",
    "pitfalls": [
        "给自定义类型用 `{}` 却没实现 Display：会报 trait bound 未满足，需派生 Debug 用 `{:?}` 或手写 Display。",
        "把 Display 写成调试细节：Display 面向用户，应简明稳定；内部字段细节留给 Debug。",
        "格式说明符顺序写错：`{:0>5}` 是填充字符+对齐+宽度，乱序会被解析为其他含义或报错。"
    ],
    "exercise": {
        "prompt": "定义 `struct Fraction { num: i64, den: i64 }`，实现 Display 输出 `num/den`，并在 main 中分别用 `{}` 与 `{:?}`（派生 Debug）打印 3/4。",
        "hint": "Display 里 `write!(f, \"{}/{}\", self.num, self.den)`，同时 `#[derive(Debug)]`。",
        "answer": "use std::fmt;\n\n#[derive(Debug)]\nstruct Fraction {\n    num: i64,\n    den: i64,\n}\n\nimpl fmt::Display for Fraction {\n    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {\n        write!(f, \"{}/{}\", self.num, self.den)\n    }\n}\n\nfn main() {\n    let fr = Fraction { num: 3, den: 4 };\n    println!(\"{}\", fr);\n    println!(\"{:?}\", fr);\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 32,
    "title": "实战：一个无依赖的命令行计算器",
    "level": "beginner",
    "domain": "syntax-types",
    "summary": "综合枚举、match、函数与错误处理，实现一个解析并求值简单表达式的计算器，输入写死在程序里以保证确定性。",
    "concepts": ["综合应用", "词法切分", "枚举求值", "错误处理", "确定性输入"],
    "objective": "能把“词法切分→中缀求值→输出”串成完整程序，并用枚举表达运算与错误。",
    "prerequisites": ["022"],
    "explain": "本课把前面语法元素综合成一个计算器：先用 `split_whitespace` 把输入切成 token，再解析成数字与运算符，然后按优先级执行两趟（先乘除后加减）。为保持确定性且不依赖 stdin，表达式以字符串字面量写死。求值过程用 `Result` 表达错误（如除零、token 非法），把失败原因作为枚举返回并通过 `Display` 打印。实现要点：把运算符建模成枚举而不是字符串比较；把错误建模成枚举而不是 panic；核心求值逻辑写成纯函数便于测试。这个骨架正是后续“命令解析器”“CSV 解析库”等实战的思想基础——先用类型把语法与错误表达清楚，再写处理循环。",
    "code": "use std::fmt;\n\n#[derive(Debug, Clone, Copy, PartialEq)]\nenum Op {\n    Add,\n    Sub,\n    Mul,\n    Div,\n}\n\n#[derive(Debug, PartialEq)]\nenum CalcError {\n    UnknownToken(String),\n    DivideByZero,\n    TrailingOperand,\n}\n\nimpl fmt::Display for CalcError {\n    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {\n        match self {\n            CalcError::UnknownToken(t) => write!(f, \"未知 token: {}\", t),\n            CalcError::DivideByZero => write!(f, \"除以零\"),\n            CalcError::TrailingOperand => write!(f, \"表达式以运算符结尾\"),\n        }\n    }\n}\n\nfn parse_op(tok: &str) -> Option<Op> {\n    match tok {\n        \"+\" => Some(Op::Add),\n        \"-\" => Some(Op::Sub),\n        \"*\" => Some(Op::Mul),\n        \"/\" => Some(Op::Div),\n        _ => None,\n    }\n}\n\nfn apply(acc: f64, op: Op, rhs: f64) -> Result<f64, CalcError> {\n    Ok(match op {\n        Op::Add => acc + rhs,\n        Op::Sub => acc - rhs,\n        Op::Mul => acc * rhs,\n        Op::Div => {\n            if rhs == 0.0 {\n                return Err(CalcError::DivideByZero);\n            }\n            acc / rhs\n        }\n    })\n}\n\nfn eval(input: &str) -> Result<f64, CalcError> {\n    let tokens: Vec<&str> = input.split_whitespace().collect();\n    // 第一趟：乘除\n    let mut reduced: Vec<String> = Vec::new();\n    let mut i = 0;\n    while i < tokens.len() {\n        let tok = tokens[i];\n        if let Some(op) = parse_op(tok) {\n            if matches!(op, Op::Mul | Op::Div) {\n                let lhs: f64 = reduced.pop()\n                    .ok_or_else(|| CalcError::UnknownToken(tok.to_string()))?\n                    .parse().map_err(|_| CalcError::UnknownToken(tok.to_string()))?;\n                let rhs_tok = tokens.get(i + 1).ok_or(CalcError::TrailingOperand)?;\n                let rhs: f64 = rhs_tok.parse().map_err(|_| CalcError::UnknownToken(rhs_tok.to_string()))?;\n                let value = apply(lhs, op, rhs)?;\n                reduced.push(value.to_string());\n                i += 2;\n                continue;\n            }\n        }\n        reduced.push(tok.to_string());\n        i += 1;\n    }\n    // 第二趟：加减\n    let mut acc: f64 = reduced.first()\n        .ok_or(CalcError::TrailingOperand)?\n        .parse().map_err(|_| CalcError::UnknownToken(reduced[0].clone()))?;\n    let mut j = 1;\n    while j + 1 < reduced.len() {\n        let op = parse_op(&reduced[j]).ok_or_else(|| CalcError::UnknownToken(reduced[j].clone()))?;\n        let rhs: f64 = reduced[j + 1].parse().map_err(|_| CalcError::UnknownToken(reduced[j + 1].clone()))?;\n        acc = apply(acc, op, rhs)?;\n        j += 2;\n    }\n    if j != reduced.len() {\n        return Err(CalcError::TrailingOperand);\n    }\n    Ok(acc)\n}\n\nfn main() {\n    let inputs = [\"2 + 3 * 4\", \"10 / 4 - 1\", \"7 * 0\", \"5 / 0\", \"3 +\"];\n    for expr in inputs {\n        match eval(expr) {\n            Ok(v) => println!(\"{} = {}\", expr, v),\n            Err(e) => println!(\"{} -> 错误: {}\", expr, e),\n        }\n    }\n}\n",
    "output": "2 + 3 * 4 = 14\n10 / 4 - 1 = 1.5\n7 * 0 = 0\n5 / 0 -> 错误: 除以零\n3 + -> 错误: 表达式以运算符结尾\n",
    "pitfalls": [
        "用字符串比较运算符：应解析为枚举，既能穷尽匹配又避免拼写错误。",
        "求值时遇到错误直接 panic：应返回 Result，让调用方决定如何呈现。",
        "忘记处理多余/缺失的操作数：应显式返回 TrailingOperand 之类错误，而不是索引越界。"
    ],
    "exercise": {
        "prompt": "在原计算器（支持 + - * / 且先乘除后加减）基础上，增加一元前缀 `neg`：它把紧随其后的一个数字取负，例如 `neg 5 + 2` 求值为 -3，`neg 3 * 4` 求值为 -12。要求保留原有的乘除优先级与所有错误处理，写出完整可编译程序，并对 `2 + 3 * 4`、`neg 5 + 2`、`neg 3 * 4`、`10 / 4 - 1`、`5 / 0`、`3 +` 六条输入打印结果。",
        "hint": "把 `neg` 视为词法归一化：遇到 neg 就把它后面的数字取反后作为一个普通数字 token 压入，之后再走原有的两趟求值；这样乘除优先级、除零与尾运算符错误都自然保留。",
        "answer": "use std::fmt;\n\n#[derive(Debug, Clone, Copy, PartialEq)]\nenum Op {\n    Add,\n    Sub,\n    Mul,\n    Div,\n}\n\n#[derive(Debug, PartialEq)]\nenum CalcError {\n    Empty,\n    UnknownToken(String),\n    DivideByZero,\n    TrailingOperand,\n}\n\nimpl fmt::Display for CalcError {\n    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {\n        match self {\n            CalcError::Empty => write!(f, \"空表达式\"),\n            CalcError::UnknownToken(t) => write!(f, \"未知 token: {}\", t),\n            CalcError::DivideByZero => write!(f, \"除以零\"),\n            CalcError::TrailingOperand => write!(f, \"表达式以运算符结尾\"),\n        }\n    }\n}\n\nfn parse_op(tok: &str) -> Option<Op> {\n    match tok {\n        \"+\" => Some(Op::Add),\n        \"-\" => Some(Op::Sub),\n        \"*\" => Some(Op::Mul),\n        \"/\" => Some(Op::Div),\n        _ => None,\n    }\n}\n\nfn apply(acc: f64, op: Op, rhs: f64) -> Result<f64, CalcError> {\n    Ok(match op {\n        Op::Add => acc + rhs,\n        Op::Sub => acc - rhs,\n        Op::Mul => acc * rhs,\n        Op::Div => {\n            if rhs == 0.0 {\n                return Err(CalcError::DivideByZero);\n            }\n            acc / rhs\n        }\n    })\n}\n\n// neg 是一元前缀：对紧随其后的一个数字取负，仍产生一个数字 token，\n// 因此完整保留原有“先乘除、后加减”的优先级。\nfn normalize(input: &str) -> Result<Vec<String>, CalcError> {\n    let toks: Vec<&str> = input.split_whitespace().collect();\n    if toks.is_empty() {\n        return Err(CalcError::Empty);\n    }\n    let mut out: Vec<String> = Vec::new();\n    let mut i = 0;\n    while i < toks.len() {\n        if toks[i] == \"neg\" {\n            let raw = toks.get(i + 1).ok_or(CalcError::TrailingOperand)?;\n            let n: f64 = raw.parse().map_err(|_| CalcError::UnknownToken(raw.to_string()))?;\n            out.push((-n).to_string());\n            i += 2;\n        } else {\n            out.push(toks[i].to_string());\n            i += 1;\n        }\n    }\n    Ok(out)\n}\n\nfn eval(input: &str) -> Result<f64, CalcError> {\n    let tokens = normalize(input)?;\n    // 第一趟：先处理乘除\n    let mut reduced: Vec<String> = Vec::new();\n    let mut i = 0;\n    while i < tokens.len() {\n        let tok = tokens[i].as_str();\n        if let Some(op) = parse_op(tok) {\n            if matches!(op, Op::Mul | Op::Div) {\n                let lhs: f64 = reduced.pop()\n                    .ok_or_else(|| CalcError::UnknownToken(tok.to_string()))?\n                    .parse().map_err(|_| CalcError::UnknownToken(tok.to_string()))?;\n                let rhs_tok = tokens.get(i + 1).ok_or(CalcError::TrailingOperand)?;\n                let rhs: f64 = rhs_tok.parse()\n                    .map_err(|_| CalcError::UnknownToken(rhs_tok.to_string()))?;\n                reduced.push(apply(lhs, op, rhs)?.to_string());\n                i += 2;\n                continue;\n            }\n        }\n        reduced.push(tokens[i].clone());\n        i += 1;\n    }\n    // 第二趟：再处理加减\n    let mut acc: f64 = reduced.first().ok_or(CalcError::TrailingOperand)?\n        .parse().map_err(|_| CalcError::UnknownToken(reduced[0].clone()))?;\n    let mut j = 1;\n    while j < reduced.len() {\n        let op = parse_op(&reduced[j]).ok_or_else(|| CalcError::UnknownToken(reduced[j].clone()))?;\n        let rhs: f64 = reduced.get(j + 1).ok_or(CalcError::TrailingOperand)?\n            .parse().map_err(|_| CalcError::UnknownToken(reduced[j + 1].clone()))?;\n        acc = apply(acc, op, rhs)?;\n        j += 2;\n    }\n    Ok(acc)\n}\n\nfn main() {\n    let inputs = [\n        \"2 + 3 * 4\",\n        \"neg 5 + 2\",\n        \"neg 3 * 4\",\n        \"10 / 4 - 1\",\n        \"5 / 0\",\n        \"3 +\",\n    ];\n    for expr in inputs {\n        match eval(expr) {\n            Ok(v) => println!(\"{} = {}\", expr, v),\n            Err(e) => println!(\"{} -> 错误: {}\", expr, e),\n        }\n    }\n}\n"
    },
    "runtime": "desktop"
},
]
