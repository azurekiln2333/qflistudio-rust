# -*- coding: utf-8 -*-
"""Lessons 053..060 (Domain D, part 1: derives, enums, matching)."""

LESSONS = [
{
    "id": 53,
    "title": "`Debug`/`PartialEq`/`Clone` 派生",
    "level": "beginner",
    "domain": "data-modeling",
    "summary": "用 `#[derive(...)]` 自动获得常用 trait 实现，理解各派生 trait 的语义与适用条件。",
    "concepts": ["derive", "Debug", "PartialEq", "Clone", "Eq/PartialOrd"],
    "objective": "能按需求选择合适的派生集合，并说明每个派生对类型字段的要求。",
    "prerequisites": ["025"],
    "explain": "`#[derive(Trait)]` 让编译器生成样板实现。常见的有：`Debug`（`{:?}`，几乎所有类型都该有）、`Clone`（`.clone()`）、`Copy`（需所有字段 Copy 且无 Drop）、`PartialEq`/`Eq`（`==`，Eq 要求完全等价关系，f64 只有 PartialEq）、`PartialOrd`/`Ord`（排序比较）、`Hash`（用于 HashMap/HashSet 的 key）。派生对字段有传递要求：例如 `#[derive(PartialEq)]` 要求所有字段都 PartialEq，否则编译失败。`Eq` 与 `PartialEq` 的区别在浮点：NaN != NaN，故 f64 只能 PartialEq 不能 Eq，含 f64 的结构体也一样。`Ord` 要求全序，含浮点字段不能派生。实践里为数据载体派生 `Debug, Clone, PartialEq` 是安全默认；只有当类型语义真的无法全序/全等时才省略对应派生。",
    "code": "#[derive(Debug, Clone, PartialEq)]\nstruct User {\n    name: String,\n    age: u32,\n}\n\n#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]\nstruct Version {\n    major: u16,\n    minor: u16,\n}\n\nfn main() {\n    let a = User { name: String::from(\"Alice\"), age: 30 };\n    let b = a.clone();\n    println!(\"a = {:?}\", a);\n    println!(\"a == b: {}\", a == b);\n\n    let v1 = Version { major: 1, minor: 2 };\n    let v2 = Version { major: 1, minor: 10 };\n    println!(\"v1 < v2: {}\", v1 < v2);\n    let mut sorted = vec![v2, v1];\n    sorted.sort();\n    println!(\"sorted = {:?}\", sorted);\n}\n",
    "output": "a = User { name: \"Alice\", age: 30 }\na == b: true\nv1 < v2: true\nsorted = [Version { major: 1, minor: 2 }, Version { major: 1, minor: 10 }]\n",
    "pitfalls": [
        "含 f64 字段却派生 `Eq`/`Ord`：编译失败，浮点不满足全序/全等。",
        "以为 Clone 一定是深拷贝：对含 Rc/Arc 的字段，clone 只增加引用计数（浅共享）。",
        "给需要自定义相等语义的类型盲派 PartialEq：派生是按字段逐一比较，语义不符时要手写。"
    ],
    "exercise": {
        "prompt": "定义 `#[derive(Debug, Clone, PartialEq, Eq, Hash)] struct Point { x: i32, y: i32 }`，用它作为 `HashMap` key 存入两个点并查询其中一个，打印查询结果。",
        "hint": "Hash 派生让结构体可作 HashMap key；用 `map.insert(Point{..}, \"a\")` 与 `map.get(&Point{..})`。",
        "answer": "use std::collections::HashMap;\n\n#[derive(Debug, Clone, PartialEq, Eq, Hash)]\nstruct Point {\n    x: i32,\n    y: i32,\n}\n\nfn main() {\n    let mut map: HashMap<Point, &str> = HashMap::new();\n    map.insert(Point { x: 0, y: 0 }, \"origin\");\n    map.insert(Point { x: 1, y: 2 }, \"one-two\");\n    println!(\"{:?}\", map.get(&Point { x: 1, y: 2 }));\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 54,
    "title": "`Default` 与构建器模式",
    "level": "intermediate",
    "domain": "data-modeling",
    "summary": "用 Default 提供合理初值，用构建器把可选配置的可读性提升到方法链。",
    "concepts": ["Default", "构建器模式", "方法链", "..Default::default()", "派生 Default"],
    "objective": "能为配置结构体实现 Default 并写一个链式构建器，理解二者的互补关系。",
    "prerequisites": ["053"],
    "explain": "`Default::default()` 给出类型的默认值，可用 `#[derive(Default)]`（要求所有字段实现 Default），或手写以提供非零默认。结构体更新语法 `Config { port: 8080, ..Default::default() }` 让你只覆盖关心的字段，其余取默认。构建器模式进一步：定义一个 builder 结构体，每个 `with_xxx(mut self, v) -> Self` 返回自身，最后 `build(self) -> Target` 产出目标（可做校验）。相比大量参数的结构体字面量，构建器让调用点自解释、可省略、可校验，尤其适合配置文件、网络客户端、请求对象。缺点是额外的类型与代码量，因此对字段少、必填多的简单结构体，直接用结构体字面量即可。二者常配合：builder 从 Default 出发，未设置的字段取默认，build 时统一校验。",
    "code": "#[derive(Debug, Clone)]\nstruct ServerConfig {\n    host: String,\n    port: u16,\n    max_connections: usize,\n    verbose: bool,\n}\n\nimpl Default for ServerConfig {\n    fn default() -> Self {\n        ServerConfig {\n            host: String::from(\"127.0.0.1\"),\n            port: 8080,\n            max_connections: 128,\n            verbose: false,\n        }\n    }\n}\n\nstruct ServerConfigBuilder {\n    config: ServerConfig,\n}\n\nimpl ServerConfigBuilder {\n    fn new() -> Self {\n        ServerConfigBuilder { config: ServerConfig::default() }\n    }\n\n    fn host(mut self, host: &str) -> Self {\n        self.config.host = host.to_string();\n        self\n    }\n\n    fn port(mut self, port: u16) -> Self {\n        self.config.port = port;\n        self\n    }\n\n    fn verbose(mut self, on: bool) -> Self {\n        self.config.verbose = on;\n        self\n    }\n\n    fn build(self) -> Result<ServerConfig, String> {\n        if self.config.port == 0 {\n            return Err(String::from(\"port 不能为 0\"));\n        }\n        Ok(self.config)\n    }\n}\n\nfn main() {\n    let default = ServerConfig::default();\n    println!(\"default = {:?}\", default);\n\n    let built = ServerConfigBuilder::new().host(\"0.0.0.0\").port(9000).verbose(true).build();\n    println!(\"built = {:?}\", built);\n\n    let bad = ServerConfigBuilder::new().port(0).build();\n    println!(\"bad = {:?}\", bad);\n}\n",
    "output": "default = ServerConfig { host: \"127.0.0.1\", port: 8080, max_connections: 128, verbose: false }\nbuilt = Ok(ServerConfig { host: \"0.0.0.0\", port: 9000, max_connections: 128, verbose: true })\nbad = Err(\"port 不能为 0\")\n",
    "pitfalls": [
        "派生 Default 却想要非零默认：需要手写 impl，而非 derive。",
        "构建器方法不返回 Self：链式调用会中断，必须 `-> Self`。",
        "在 build 中忘记校验：把不变量检查集中在 build，别让非法配置流出。"
    ],
    "exercise": {
        "prompt": "为 `struct RetryPolicy { attempts: u32, delay_ms: u64 }` 实现 Default（attempts=3, delay_ms=500）与链式构建器方法 `attempts`/`delay_ms`/`build`，在 main 中基于默认只改 attempts 为 5 并打印。",
        "hint": "用 `..Default::default()` 思想：builder 持有 RetryPolicy，方法修改字段并返回 self。",
        "answer": "#[derive(Debug, Clone)]\nstruct RetryPolicy {\n    attempts: u32,\n    delay_ms: u64,\n}\n\nimpl Default for RetryPolicy {\n    fn default() -> Self {\n        RetryPolicy { attempts: 3, delay_ms: 500 }\n    }\n}\n\nstruct Builder {\n    policy: RetryPolicy,\n}\n\nimpl Builder {\n    fn new() -> Self {\n        Builder { policy: RetryPolicy::default() }\n    }\n\n    fn attempts(mut self, n: u32) -> Self {\n        self.policy.attempts = n;\n        self\n    }\n\n    fn delay_ms(mut self, ms: u64) -> Self {\n        self.policy.delay_ms = ms;\n        self\n    }\n\n    fn build(self) -> RetryPolicy {\n        self.policy\n    }\n}\n\nfn main() {\n    let p = Builder::new().attempts(5).build();\n    println!(\"{:?}\", p);\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 55,
    "title": "枚举建模状态机",
    "level": "intermediate",
    "domain": "data-modeling",
    "summary": "用枚举表示有限状态，用转移函数显式描述合法迁移，让非法状态无法表示。",
    "concepts": ["状态机", "枚举状态", "转移函数", "非法状态", "match 驱动"],
    "objective": "能把业务状态建模为枚举，并写出只允许合法转移的 `transition` 函数。",
    "prerequisites": ["027"],
    "explain": "状态机的核心是“有限状态 + 合法转移”。用枚举表示状态，把状态转移写成 `fn transition(&self, event: Event) -> Result<State, TransitionError>`：合法迁移返回新状态，非法迁移返回错误。这样“哪些迁移合法”由类型与 match 明确表达，新增状态或事件时编译器强制你处理所有分支。相比用布尔/整数标志，枚举建模能让“非法组合”在类型层被排除（如订单不能既 Cancelled 又 Shipped）。要点：状态应是纯数据，转移尽量无副作用；若状态转换依赖外部条件，把条件作为参数或错误来源显式传入。状态机常配合“当前状态 + 历史”结构使用。注意避免让状态携带矛盾信息；若某状态下某些字段无意义，应把字段放进该状态的变体里（如 `Loading(progress)`），而不是放在外层结构。",
    "code": "#[derive(Debug, Clone, Copy, PartialEq, Eq)]\nenum Door {\n    Closed,\n    Open,\n}\n\n#[derive(Debug, Clone, Copy, PartialEq, Eq)]\nenum Event {\n    Open,\n    Close,\n    Lock,\n}\n\n#[derive(Debug, PartialEq, Eq)]\nenum TransitionError {\n    AlreadyInState(Door),\n    Locked,\n}\n\nfn transition(state: Door, event: Event) -> Result<Door, TransitionError> {\n    match (state, event) {\n        (Door::Closed, Event::Open) => Ok(Door::Open),\n        (Door::Open, Event::Close) => Ok(Door::Closed),\n        (Door::Closed, Event::Close) => Err(TransitionError::AlreadyInState(state)),\n        (Door::Open, Event::Open) => Err(TransitionError::AlreadyInState(state)),\n        (_, Event::Lock) => Err(TransitionError::Locked),\n    }\n}\n\nfn main() {\n    let mut state = Door::Closed;\n    for event in [Event::Open, Event::Open, Event::Close, Event::Lock] {\n        match transition(state, event) {\n            Ok(next) => {\n                println!(\"{:?} --{:?}--> {:?}\", state, event, next);\n                state = next;\n            }\n            Err(e) => println!(\"{:?} --{:?}--> 错误 {:?}\", state, event, e),\n        }\n    }\n    println!(\"最终状态 = {:?}\", state);\n}\n",
    "output": "Closed --Open--> Open\nOpen --Open--> 错误 AlreadyInState(Open)\nOpen --Close--> Closed\nClosed --Lock--> 错误 Locked\n最终状态 = Closed\n",
    "pitfalls": [
        "用 (bool, bool) 表示状态：非法组合能构造出来，应改用枚举。",
        "转移函数用 panic 处理非法迁移：应返回 Result，让调用方决定策略。",
        "把外部条件硬编码进状态转移：条件应作为参数或错误来源显式表达。"
    ],
    "exercise": {
        "prompt": "建模一个三态任务 `Todo/Done/Archived`：`Todo->Done->Archived`，`Done->Todo` 允许（重开），`Archived` 不可再变。写 `transition` 与 `struct Task`，在 main 中演示一次合法与一次非法转移。",
        "hint": "用 match (state, event) 穷尽；Archived 的所有 event 都返回错误。",
        "answer": "// 055 answer: implement Task (not just transition)\n#[derive(Debug, Clone, Copy, PartialEq, Eq)]\nenum Status {\n    Todo,\n    Done,\n    Archived,\n}\n\n#[derive(Debug, Clone, Copy, PartialEq, Eq)]\nenum Action {\n    Complete,\n    Reopen,\n    Archive,\n}\n\n#[derive(Debug)]\nstruct Task {\n    name: String,\n    status: Status,\n}\n\nimpl Task {\n    fn new(name: &str) -> Self {\n        Task { name: name.to_string(), status: Status::Todo }\n    }\n\n    fn transition(&mut self, action: Action) -> Result<Status, &'static str> {\n        let next = match (self.status, action) {\n            (Status::Todo, Action::Complete) => Status::Done,\n            (Status::Done, Action::Reopen) => Status::Todo,\n            (Status::Done, Action::Archive) => Status::Archived,\n            (Status::Archived, _) => return Err(\"已归档不可变\"),\n            _ => return Err(\"非法转移\"),\n        };\n        self.status = next;\n        Ok(next)\n    }\n}\n\nfn main() {\n    let mut task = Task::new(\"写文档\");\n    let ok = task.transition(Action::Complete);\n    println!(\"{} -> {:?}, status = {:?}\", task.name, ok, task.status);\n\n    let archived = task.transition(Action::Archive);\n    println!(\"archive -> {:?}, status = {:?}\", archived, task.status);\n\n    let bad = task.transition(Action::Reopen);\n    println!(\"reopen  -> {:?}, status = {:?}\", bad, task.status);\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 56,
    "title": "`match` 解构：结构体、枚举、嵌套",
    "level": "intermediate",
    "domain": "data-modeling",
    "summary": "在 match 中解构结构体、枚举与嵌套组合，用 `..` 忽略字段、用绑定提取内部值。",
    "concepts": ["解构", "嵌套模式", ".. 忽略", "绑定", "struct/enum 模式"],
    "objective": "能对嵌套数据结构写出解构式 match，一次取出多层字段。",
    "prerequisites": ["055"],
    "explain": "match 的模式可以深入到数据结构内部：`Point { x, y }` 解构结构体并绑定字段；`Shape::Circle { radius }` 解构枚举变体；可组合成嵌套模式如 `Message::Move { x: Point { x, .. }, .. }`。`..` 忽略剩余字段，`_` 忽略单个位置。绑定默认按值移动，若要只借用则用 `ref`（现代 Rust 更常用 `&` 模式或在引用上匹配）。解构匹配引用时，字段绑定会得到引用。解构让“根据数据形状分派”变得集中而清晰，是 Rust 处理 AST、协议消息、配置树的惯用方式。要点：尽量让模式覆盖具体形状而非用 `_` 兜底，以保留穷尽性检查；绑定名字要能表达语义；嵌套过深时可先解构外层再处理内层，提升可读性。",
    "code": "#[derive(Debug)]\nstruct Point {\n    x: i32,\n    y: i32,\n}\n\n#[derive(Debug)]\nenum Shape {\n    Circle { center: Point, radius: f64 },\n    Rect { top_left: Point, width: u32, height: u32 },\n    Empty,\n}\n\nfn describe(shape: &Shape) -> String {\n    match shape {\n        Shape::Circle { center: Point { x, y }, radius } => {\n            format!(\"圆: 圆心=({}, {}) 半径={}\", x, y, radius)\n        }\n        Shape::Rect { top_left, width, height } => {\n            format!(\"矩形: 左上={:?} 宽={} 高={}\", top_left, width, height)\n        }\n        Shape::Empty => String::from(\"空形状\"),\n    }\n}\n\nfn main() {\n    let shapes = [\n        Shape::Circle { center: Point { x: 0, y: 0 }, radius: 2.5 },\n        Shape::Rect { top_left: Point { x: 1, y: 1 }, width: 4, height: 3 },\n        Shape::Empty,\n    ];\n    for shape in &shapes {\n        println!(\"{}\", describe(shape));\n    }\n}\n",
    "output": "圆: 圆心=(0, 0) 半径=2.5\n矩形: 左上=Point { x: 1, y: 1 } 宽=4 高=3\n空形状\n",
    "pitfalls": [
        "嵌套解构时忘记 `..`：结构体模式要么列出所有字段，要么用 `..` 忽略其余。",
        "在 `&Shape` 上解构却试图移动 String 字段：会得到借用，移动会报错。",
        "过度使用 `_`：虽能通过编译，但会丢失新增变体的编译期提醒。"
    ],
    "exercise": {
        "prompt": "定义 `enum Tree { Leaf(i32), Node(Box<Tree>, Box<Tree>) }`，写函数 `sum(&Tree) -> i32` 用解构式 match 递归求和，在 main 中测试 `Node(Leaf(1), Node(Leaf(2), Leaf(3)))`。",
        "hint": "match self { Tree::Leaf(v) => *v, Tree::Node(l, r) => sum(l) + sum(r) }。",
        "answer": "enum Tree {\n    Leaf(i32),\n    Node(Box<Tree>, Box<Tree>),\n}\n\nfn sum(tree: &Tree) -> i32 {\n    match tree {\n        Tree::Leaf(v) => *v,\n        Tree::Node(l, r) => sum(l) + sum(r),\n    }\n}\n\nfn main() {\n    let t = Tree::Node(\n        Box::new(Tree::Leaf(1)),\n        Box::new(Tree::Node(Box::new(Tree::Leaf(2)), Box::new(Tree::Leaf(3)))),\n    );\n    println!(\"{}\", sum(&t));\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 57,
    "title": "匹配守卫与 `@` 绑定",
    "level": "intermediate",
    "domain": "data-modeling",
    "summary": "用 `if` 守卫给模式附加条件，用 `@` 同时绑定并测试值，表达更精细的分支。",
    "concepts": ["匹配守卫", "if guard", "@ 绑定", "范围绑定", "条件分支"],
    "objective": "能在 match 分支上使用守卫与 `@`，写出“匹配某范围并同时使用该值”的模式。",
    "prerequisites": ["056"],
    "explain": "守卫是写在模式后的 `if cond`，只有模式匹配且条件为真才选该分支，条件可引用模式绑定的变量。`@` 绑定让你在测试模式的同时把值绑定成变量：`n @ 1..=5 => println!(\"small {}\", n)`。两者组合能表达“形状匹配 + 值约束”，避免把逻辑塞进分支体里。注意穷尽性分析会把守卫视为“可能失败”，因此带守卫的分支不能单独满足穷尽性，仍需 `_` 或穷尽分支兜底。守卫里可调用函数，但要避免副作用，因为它可能被求值多次（编译器不保证次数）。`@` 也可用于解构：`Point { x: x @ 1..=9, .. }`。这些模式不改变运行时性能，只是更精确地表达意图，常用于解析器、分类器与配置校验。",
    "code": "fn classify(n: i32) -> String {\n    match n {\n        0 => String::from(\"zero\"),\n        x @ 1..=9 if x % 2 == 0 => format!(\"small even {}\", x),\n        x @ 1..=9 => format!(\"small odd {}\", x),\n        x if x < 0 => format!(\"negative {}\", x),\n        x => format!(\"large {}\", x),\n    }\n}\n\nfn main() {\n    for n in [0, 4, 7, -3, 42] {\n        println!(\"{} -> {}\", n, classify(n));\n    }\n}\n",
    "output": "0 -> zero\n4 -> small even 4\n7 -> small odd 7\n-3 -> negative -3\n42 -> large 42\n",
    "pitfalls": [
        "以为带守卫的分支能保证穷尽：守卫可能为假，编译器仍要求兜底分支。",
        "在守卫里做有副作用的操作：求值次数无保证，应保持纯函数。",
        "`@` 绑定与范围混用时忘记括号：`n @ (1 | 2)` 之类需注意模式优先级。"
    ],
    "exercise": {
        "prompt": "写函数 `bucket(score: u32) -> &'static str`，用 `@` 绑定与 `if` 守卫共同实现：0..=59 返回 \"F\"，60..=69 返回 \"D\"，70..=79 返回 \"C\"，80..=89 返回 \"B\"，90..=100 返回 \"A\"，其中当分数是整十（s % 10 == 0）时返回带“(整十)”后缀的等级（如 60 -> \"D(整十)\"、90 -> \"A(整十)\"），其他（如 120）返回 \"invalid\"；在 main 中测试 45、72、70、60、95、90、120。",
        "hint": "用范围模式 `s @ 0..=59 => ...`；越界用 `_ => \"invalid\"`。",
        "answer": "// 057 answer: `@` binding + `if` guards, with a complete F(整十) branch\nfn bucket(score: u32) -> &'static str {\n    match score {\n        s @ 0..=59 if s % 10 == 0 => {\n            let _ = s;\n            \"F(整十)\"\n        }\n        s @ 0..=59 => {\n            let _ = s;\n            \"F\"\n        }\n        s @ 60..=69 if s % 10 == 0 => {\n            let _ = s;\n            \"D(整十)\"\n        }\n        s @ 60..=69 => {\n            let _ = s;\n            \"D\"\n        }\n        s @ 70..=79 if s % 10 == 0 => {\n            let _ = s;\n            \"C(整十)\"\n        }\n        s @ 70..=79 => {\n            let _ = s;\n            \"C\"\n        }\n        s @ 80..=89 if s % 10 == 0 => {\n            let _ = s;\n            \"B(整十)\"\n        }\n        s @ 80..=89 => {\n            let _ = s;\n            \"B\"\n        }\n        s @ 90..=100 if s % 10 == 0 => {\n            let _ = s;\n            \"A(整十)\"\n        }\n        s @ 90..=100 => {\n            let _ = s;\n            \"A\"\n        }\n        _ => \"invalid\",\n    }\n}\n\nfn main() {\n    // 断言整十（含 F 段）与非整十都正确\n    assert_eq!(bucket(0), \"F(整十)\");\n    assert_eq!(bucket(10), \"F(整十)\");\n    assert_eq!(bucket(50), \"F(整十)\");\n    assert_eq!(bucket(55), \"F\");\n    assert_eq!(bucket(60), \"D(整十)\");\n    assert_eq!(bucket(65), \"D\");\n    assert_eq!(bucket(90), \"A(整十)\");\n    assert_eq!(bucket(120), \"invalid\");\n\n    for s in [0, 10, 50, 55, 72, 70, 60, 95, 90, 120] {\n        println!(\"{} -> {}\", s, bucket(s));\n    }\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 58,
    "title": "`Option<T>` 的完整处理",
    "level": "intermediate",
    "domain": "data-modeling",
    "summary": "用 match、map、and_then、unwrap_or、ok_or 等把“可能没有”表达清楚，杜绝空指针式错误。",
    "concepts": ["Option", "map", "and_then", "unwrap_or_else", "ok_or"],
    "objective": "能根据不同场景选择 Option 的展开与组合方法，避免滥用 unwrap。",
    "prerequisites": ["056"],
    "explain": "`Option<T>` 是 `Some(T)` 或 `None`，把“可能缺失”编码进类型。展开方式按场景选：`unwrap`（确定有值，否则 panic，仅测试或逻辑保证时用）、`expect`（带信息）、`unwrap_or`/`unwrap_or_else`/`unwrap_or_default`（提供回退）、`map`（对 Some 变换）、`and_then`（链式可能失败的步骤）、`or`/`or_else`（提供候选）、`filter`（附加条件）、`ok_or`/`ok_or_else`（转 Result）。`?` 在返回 Option 的函数里可提前传播 None。`if let`/`match` 适合需要不同处理的情况。要点：不要用 magic number（如 -1）表示缺失，用 Option；组合子能表达“仅在 Some 时继续”的意图，避免层层 if。注意 `Option<&T>` 与 `Option<&mut T>` 的引用语义；`as_ref`/`as_mut` 可在不移动的情况下借用。`Option::take` 能安全取出并置 None，常用在状态迁移。",
    "code": "fn first_char(text: &str) -> Option<char> {\n    text.chars().next()\n}\n\nfn parse_bool(text: &str) -> Option<bool> {\n    match text.trim().to_lowercase().as_str() {\n        \"true\" | \"yes\" | \"1\" => Some(true),\n        \"false\" | \"no\" | \"0\" => Some(false),\n        _ => None,\n    }\n}\n\nfn main() {\n    println!(\"first = {:?}\", first_char(\"rust\"));\n    println!(\"empty = {:?}\", first_char(\"\"));\n\n    // map / and_then 链\n    let flag = first_char(\"yes\").map(|c| c.to_string()).and_then(|s| parse_bool(&s));\n    println!(\"flag = {:?}\", flag);\n\n    // 回退与转换\n    println!(\"or_default = {}\", parse_bool(\"nope\").unwrap_or(false));\n    println!(\"ok_or = {:?}\", parse_bool(\"maybe\").ok_or(\"无法解析\"));\n\n    // 借用而不移动\n    let opt = Some(String::from(\"value\"));\n    let len = opt.as_ref().map(|s| s.len());\n    println!(\"len = {:?}, still = {:?}\", len, opt);\n}\n",
    "output": "first = Some('r')\nempty = None\nflag = None\nor_default = false\nok_or = Err(\"无法解析\")\nlen = Some(5), still = Some(\"value\")\n",
    "pitfalls": [
        "到处 `unwrap`：一旦是 None 就 panic，应在可控点解包或提供回退。",
        "用 map 里返回 Option 导致嵌套 Option：需要扁平化时用 `and_then`。",
        "持有 `Option<String>` 却想借用再继续用：用 `as_ref()` 避免把内部值移走。"
    ],
    "exercise": {
        "prompt": "写函数 `divide(a: f64, b: f64) -> Option<f64>`（除零返回 None）与 `first_positive(xs: &[i32]) -> Option<i32>`；在 main 中组合它们：对 `divide(10.0, 2.0)` 的结果取整后查第一个正数（用 and_then），并打印。",
        "hint": "`divide(10.0,2.0).map(|v| v as i32).and_then(|n| first_positive(&[n]))`。",
        "answer": "fn divide(a: f64, b: f64) -> Option<f64> {\n    if b == 0.0 { None } else { Some(a / b) }\n}\n\nfn first_positive(xs: &[i32]) -> Option<i32> {\n    xs.iter().copied().find(|v| *v > 0)\n}\n\nfn main() {\n    let r = divide(10.0, 2.0)\n        .map(|v| v as i32)\n        .and_then(|n| first_positive(&[n]));\n    println!(\"{:?}\", r);\n    println!(\"{:?}\", divide(1.0, 0.0));\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 59,
    "title": "`Result<T, E>` 的完整处理",
    "level": "intermediate",
    "domain": "data-modeling",
    "summary": "用 Result 表达可恢复错误，掌握 match、map、map_err、unwrap_or、? 的使用与错误类型设计。",
    "concepts": ["Result", "map_err", "and_then", "unwrap_or_else", "错误类型"],
    "objective": "能写出返回 Result 的解析/校验函数，并在调用点选择恰当的展开方式。",
    "prerequisites": ["058"],
    "explain": "`Result<T, E>` 是 `Ok(T)` 或 `Err(E)`，用于可恢复失败。与 Option 类似有组合子：`map`（成功时变换）、`map_err`（失败时变换错误，常用于统一错误类型）、`and_then`（链式可能失败）、`unwrap_or`/`unwrap_or_else`/`unwrap_or_default`（回退）、`ok()`（丢弃错误变 Option）、`err()`。`?` 在返回 Result 的函数中传播错误，并在错误类型可实现 `From` 时自动转换。调用点若要忽略错误可用 `let _ =`，但通常应显式处理。错误类型设计见后续课程：小项目可用 `String`/`&'static str`，生产代码建议定义领域错误枚举或实现 Error trait。要点：区分 panic（不可恢复/编程错误）与 Result（可预期失败）；不要用 Result 包装永远不会失败的操作；错误信息应可操作而非泛泛。",
    "code": "#[derive(Debug, PartialEq)]\nenum ParseError {\n    Empty,\n    NotANumber(String),\n    OutOfRange(i64),\n}\n\nfn parse_percent(text: &str) -> Result<u8, ParseError> {\n    let trimmed = text.trim();\n    if trimmed.is_empty() {\n        return Err(ParseError::Empty);\n    }\n    let digits = trimmed.strip_suffix('%').unwrap_or(trimmed);\n    let value: i64 = digits.parse().map_err(|_| ParseError::NotANumber(digits.to_string()))?;\n    if !(0..=100).contains(&value) {\n        return Err(ParseError::OutOfRange(value));\n    }\n    Ok(value as u8)\n}\n\nfn main() {\n    for input in [\"42%\", \" 100 \", \"\", \"abc\", \"150%\"] {\n        match parse_percent(input) {\n            Ok(v) => println!(\"{:?} -> {}\", input, v),\n            Err(e) => println!(\"{:?} -> 错误 {:?}\", input, e),\n        }\n    }\n\n    // 组合子: map_err 统一错误展示\n    let msg = parse_percent(\"oops\").map_err(|e| format!(\"{:?}\", e));\n    println!(\"combined = {:?}\", msg);\n}\n",
    "output": "\"42%\" -> 42\n\" 100 \" -> 100\n\"\" -> 错误 Empty\n\"abc\" -> 错误 NotANumber(\"abc\")\n\"150%\" -> 错误 OutOfRange(150)\ncombined = Err(\"NotANumber(\\\"oops\\\")\")\n",
    "pitfalls": [
        "对可预期失败用 panic：解析用户输入应返回 Result，让调用方处理。",
        "忽略 `?` 的错误自动转换：要求错误类型实现 From，否则需 map_err。",
        "错误类型不带上下文：尽量携带出错的原始片段，便于诊断。"
    ],
    "exercise": {
        "prompt": "写函数 `parse_range(text: &str) -> Result<(i32, i32), String>`，解析形如 \"3-7\" 的区间（两端整数、start<=end），在 main 中测试合法与三种非法输入（缺分隔、非数字、逆序）。",
        "hint": "用 `text.split_once('-')` 取得两端，再 `parse::<i32>()`；错误用 String 描述具体原因。",
        "answer": "fn parse_range(text: &str) -> Result<(i32, i32), String> {\n    let (a, b) = text.split_once('-').ok_or_else(|| format!(\"缺少分隔符: {}\", text))?;\n    let start: i32 = a.trim().parse().map_err(|_| format!(\"非法起点: {}\", a))?;\n    let end: i32 = b.trim().parse().map_err(|_| format!(\"非法终点: {}\", b))?;\n    if start > end {\n        return Err(format!(\"起点大于终点: {} > {}\", start, end));\n    }\n    Ok((start, end))\n}\n\nfn main() {\n    for input in [\"3-7\", \"5\", \"a-9\", \"9-2\"] {\n        println!(\"{:?} -> {:?}\", input, parse_range(input));\n    }\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 60,
    "title": "用枚举替代布尔与魔法值",
    "level": "intermediate",
    "domain": "data-modeling",
    "summary": "把 `bool`/整数标志升级为语义明确的枚举，让非法状态不可表示、让代码自解释。",
    "concepts": ["布尔盲区", "魔法值", "语义枚举", "可读性", "非法状态"],
    "objective": "能识别应被枚举替换的布尔参数与魔法数字，并完成重构。",
    "prerequisites": ["055"],
    "explain": "布尔参数最大的问题是调用点不可读：`connect(true, false)` 没人知道含义。整数魔法值同样：`set_mode(3)` 需要查文档。把它们换成枚举后，调用点自解释：`connect(Tls::Enabled, Retry::Off)`、`set_mode(Mode::Compact)`。枚举还让非法组合不可表示：两个 bool 有 4 种组合但常常只有 3 种合法。重构信号：函数有多个布尔参数、出现注释解释参数含义、整数常量代表模式、状态字段是 bool 却会互斥。做法：定义语义化枚举，把分支逻辑移到 match，把默认值放进枚举或 Default。注意枚举比 bool 多几字节（通常 1 且被优化），性能影响可忽略。唯一例外是纯性能热点且语义确为二分，才保留 bool。另外，本课的 `render` 一律按 `chars()` 的字符数计算宽度与截断，绝不用 `text.len()`/`&text[..n]` 这类按字节的操作——否则中文等多字节字符会被截断在多字节序列中间而 panic。",
    "code": "#[derive(Debug, Clone, Copy, PartialEq, Eq)]\nenum Alignment {\n    Left,\n    Center,\n    Right,\n}\n\n#[derive(Debug, Clone, Copy, PartialEq, Eq)]\nenum Overflow {\n    Wrap,\n    Ellipsis,\n}\n\n// 按字符数（而非字节数）选取前 width 个字符，遇到多字节 UTF-8（如中文）不会 panic。\nfn take_chars(text: &str, width: usize) -> String {\n    text.chars().take(width).collect()\n}\n\nfn pad(text: &str, width: usize, align: Alignment) -> String {\n    let len = text.chars().count();\n    if len >= width {\n        return text.to_string();\n    }\n    let total = width - len;\n    match align {\n        Alignment::Left => format!(\"{}{}\", text, \" \".repeat(total)),\n        Alignment::Right => format!(\"{}{}\", \" \".repeat(total), text),\n        Alignment::Center => {\n            let left = total / 2;\n            let right = total - left;\n            format!(\"{}{}{}\", \" \".repeat(left), text, \" \".repeat(right))\n        }\n    }\n}\n\nfn render(text: &str, width: usize, align: Alignment, overflow: Overflow) -> String {\n    let shown = if text.chars().count() > width {\n        match overflow {\n            Overflow::Wrap => text.to_string(),\n            Overflow::Ellipsis => {\n                if width == 0 {\n                    String::new()\n                } else {\n                    format!(\"{}…\", take_chars(text, width - 1))\n                }\n            }\n        }\n    } else {\n        text.to_string()\n    };\n    pad(&shown, width, align)\n}\n\nfn main() {\n    println!(\"[{}]\", render(\"hi\", 6, Alignment::Left, Overflow::Wrap));\n    println!(\"[{}]\", render(\"hi\", 6, Alignment::Right, Overflow::Wrap));\n    println!(\"[{}]\", render(\"hi\", 6, Alignment::Center, Overflow::Wrap));\n    println!(\"[{}]\", render(\"toolong\", 5, Alignment::Left, Overflow::Ellipsis));\n    println!(\"[{}]\", render(\"你好世界\", 6, Alignment::Center, Overflow::Ellipsis));\n    println!(\"[{}]\", render(\"中文\", 6, Alignment::Left, Overflow::Wrap));\n}\n",
    "output": "[hi    ]\n[    hi]\n[  hi  ]\n[tool…]\n[ 你好世界 ]\n[中文    ]\n",
    "pitfalls": [
        "保留布尔参数只为省事：调用点可读性损失远大于定义枚举的代价。",
        "枚举分支用 `_` 兜底：会丢掉穷尽性保护，新增变体时无法被提醒。",
        "把枚举与整数互转却依赖具体数值：枚举判别值未保证稳定，序列化应显式映射。"
    ],
    "exercise": {
        "prompt": "把 `fn set_speed(level: u8)`（1=低速、2=中速、3=高速）重构为枚举 `Speed` 版本 `fn set_speed(speed: Speed) -> &'static str` 返回描述；在 main 中展示三种速度。",
        "hint": "定义 `enum Speed { Low, Medium, High }`，match 返回描述字符串。",
        "answer": "#[derive(Debug, Clone, Copy)]\nenum Speed {\n    Low,\n    Medium,\n    High,\n}\n\nfn set_speed(speed: Speed) -> &'static str {\n    match speed {\n        Speed::Low => \"低速\",\n        Speed::Medium => \"中速\",\n        Speed::High => \"高速\",\n    }\n}\n\nfn main() {\n    for s in [Speed::Low, Speed::Medium, Speed::High] {\n        println!(\"{:?} -> {}\", s, set_speed(s));\n    }\n}\n"
    },
    "runtime": "desktop"
},
]
