# -*- coding: utf-8 -*-
"""Lessons 061..068 (Domain D, part 2: Box, ref patterns, matches!, capstones)."""

LESSONS = [
{
    "id": 61,
    "title": "递归数据结构与 `Box` 预告",
    "level": "intermediate",
    "domain": "data-modeling",
    "summary": "用 `Box` 打破递归类型的无限大小问题，构建链表/树并实现递归操作。",
    "concepts": ["递归类型", "Box<T>", "无限大小", "链表", "递归遍历"],
    "objective": "能解释为什么递归枚举必须用 Box，并实现一个可用的链表/表达式树。",
    "prerequisites": ["055"],
    "explain": "递归类型如 `enum List { Cons(i32, List), Nil }` 无法确定大小：List 内含 List，无限嵌套，编译器报 E0072（recursive type has infinite size）。解决方法是引入间接层：`Cons(i32, Box<List>)`，Box 是固定大小的指针，指向堆上的下一节点，从而大小可计算。Box 是唯一拥有权、堆分配的最小智能指针；除打破递归外，也用于在枚举变体间转移大对象所有权、或用 `Box<dyn Trait>` 做 trait 对象（后续课）。实现链表要小心所有权：`push` 用 `mem::replace` 取得旧头，`pop` 匹配 `Box<List>` 并用 `*` 解引用移出。递归遍历用 `&self` 借用，避免移动。树同理（二叉树、AST）。要点：递归结构必须有终止变体（Nil/Leaf）；drop 深层链可能递归爆栈，生产代码可用迭代 drop 或保持深度可控。",
    "code": "#[derive(Debug, PartialEq)]\nenum List {\n    Cons(i32, Box<List>),\n    Nil,\n}\n\nimpl List {\n    fn new() -> Self {\n        List::Nil\n    }\n\n    fn push_front(self, value: i32) -> Self {\n        List::Cons(value, Box::new(self))\n    }\n\n    fn len(&self) -> usize {\n        match self {\n            List::Cons(_, tail) => 1 + tail.len(),\n            List::Nil => 0,\n        }\n    }\n\n    fn sum(&self) -> i32 {\n        match self {\n            List::Cons(v, tail) => v + tail.sum(),\n            List::Nil => 0,\n        }\n    }\n}\n\nfn main() {\n    let list = List::new().push_front(3).push_front(2).push_front(1);\n    println!(\"list = {:?}\", list);\n    println!(\"len = {}, sum = {}\", list.len(), list.sum());\n}\n",
    "output": "list = Cons(1, Cons(2, Cons(3, Nil)))\nlen = 3, sum = 6\n",
    "pitfalls": [
        "递归枚举不加 Box：报 E0072 无限大小，必须用 Box/Rc 等间接层。",
        "递归遍历按值接收：会移动数据甚至无法编译，遍历应接收 `&self`。",
        "深层递归 drop 爆栈：极深链表释放时可能递归溢出，必要时改为迭代释放。"
    ],
    "exercise": {
        "prompt": "用 `Box` 实现二叉树 `enum Tree { Leaf(i32), Node(Box<Tree>, Box<Tree>) }`，写 `depth(&Tree) -> usize` 与 `sum(&Tree) -> i32`，在 main 中构造三层树并打印两个结果。",
        "hint": "递归函数 match 两个变体；depth 取左右子树较大者 +1。",
        "answer": "enum Tree {\n    Leaf(i32),\n    Node(Box<Tree>, Box<Tree>),\n}\n\nfn depth(tree: &Tree) -> usize {\n    match tree {\n        Tree::Leaf(_) => 1,\n        Tree::Node(l, r) => 1 + depth(l).max(depth(r)),\n    }\n}\n\nfn sum(tree: &Tree) -> i32 {\n    match tree {\n        Tree::Leaf(v) => *v,\n        Tree::Node(l, r) => sum(l) + sum(r),\n    }\n}\n\nfn main() {\n    let t = Tree::Node(\n        Box::new(Tree::Leaf(1)),\n        Box::new(Tree::Node(Box::new(Tree::Leaf(2)), Box::new(Tree::Leaf(3)))),\n    );\n    println!(\"depth = {}, sum = {}\", depth(&t), sum(&t));\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 62,
    "title": "模式匹配中的引用与 `ref`",
    "level": "advanced",
    "domain": "data-modeling",
    "summary": "理解在匹配引用时绑定得到的是引用，掌握 `ref`/`ref mut` 与匹配人体默认绑定模式。",
    "concepts": ["匹配引用", "ref", "ref mut", "绑定模式", "默认绑定模式"],
    "objective": "能预测在 `&T` 或 `&mut T` 上做模式匹配时各绑定是值还是引用，并避免误移动。",
    "prerequisites": ["056"],
    "explain": "在引用上匹配时存在“默认绑定模式”：匹配 `&T` 时绑定默认是引用（`ref`），匹配 `&mut T` 时默认是 `ref mut`，因此 `match &opt { Some(x) => ... }` 中 `x` 是 `&T`。旧代码里显式写 `ref`/`ref mut`，现代 Rust 更推荐在模式上加 `&`（如 `Some(&x)`）表达意图，或让绑定模式自动推断。若要移动内部值，必须先把引用解引用为拥有型（如 `*s` 或对拥有值匹配）。常见错误：在 `match &some_option { Some(s) => consume(s) }` 中把 `s` 当拥有型传走，实际它是引用，会报类型错误。使用 `ref` 显式声明也能让意图清晰。要点：匹配 `&mut` 时通过 `ref mut` 可获得可变借用；不要在借用上尝试移出非 Copy 数据。",
    "code": "#[derive(Debug)]\nstruct Config {\n    name: String,\n    retries: u8,\n}\n\nfn describe(config: &Option<Config>) -> String {\n    // 匹配 &Option<Config>，绑定默认是引用\n    match config {\n        Some(c) => format!(\"name={} retries={}\", c.name, c.retries),\n        None => String::from(\"<none>\"),\n    }\n}\n\nfn bump_retries(config: &mut Option<Config>) {\n    match config {\n        Some(c) => {\n            // c 是 &mut Config\n            c.retries += 1;\n        }\n        None => {}\n    }\n}\n\nfn main() {\n    let config = Some(Config { name: String::from(\"svc\"), retries: 2 });\n    println!(\"{}\", describe(&config));\n    println!(\"None -> {}\", describe(&None));\n\n    let mut mutable = config;\n    bump_retries(&mut mutable);\n    println!(\"after bump = {:?}\", mutable);\n}\n",
    "output": "name=svc retries=2\nNone -> <none>\nafter bump = Some(Config { name: \"svc\", retries: 3 })\n",
    "pitfalls": [
        "在 `&T` 上匹配却想移出内部值：绑定是引用，移出会报错，需 clone 或改为拥有值匹配。",
        "误以为匹配 `&mut T` 会复制：默认绑定 `ref mut`，得到的是可变借用。",
        "在 `match` 里 `ref` 与 `&` 混用导致模式不匹配：二者表达层级不同，注意一致性。"
    ],
    "exercise": {
        "prompt": "用 `ref` 显式绑定写函数 `first_name(&[(String, u32)]) -> Option<&str>`，返回第一个元组的名字切片；在 main 中用两条记录测试。",
        "hint": "`match people.first() { Some((name, _)) => Some(name.as_str()), None => None }`；name 已是引用。",
        "answer": "// 062 answer: explicit `ref` binding\nfn first_name(people: &[(String, u32)]) -> Option<&str> {\n    match people.first() {\n        // 显式 ref：name / age 都是引用\n        Some((ref name, ref age)) => {\n            let _ = age;\n            Some(name.as_str())\n        }\n        None => None,\n    }\n}\n\nfn main() {\n    let people = vec![(String::from(\"Ada\"), 36), (String::from(\"Alan\"), 41)];\n    println!(\"{:?}\", first_name(&people));\n    println!(\"{:?}\", first_name(&[]));\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 63,
    "title": "`matches!` 与谓词风格",
    "level": "intermediate",
    "domain": "data-modeling",
    "summary": "用 `matches!(value, pattern)` 把“是否符合某形状”写成布尔表达式，简化过滤与条件判断。",
    "concepts": ["matches!", "谓词", "filter", "布尔化简", "可读性"],
    "objective": "能用 matches! 替代冗长的 if let / match 布尔，并判断何时它比真 match 更合适。",
    "prerequisites": ["056"],
    "explain": "`matches!(expr, pattern)` 返回 bool，表示 expr 是否匹配 pattern。它支持带守卫的模式（`matches!(x, Some(n) if *n > 0)`）、范围（`matches!(c, 'a'..='z')`）和嵌套。典型用途是过滤（`.filter(|x| matches!(x, Kind::Active))`）与早退条件。它比 `if let` 更简洁（因为只需布尔结果），比 `match` 更轻量（因为不需要处理所有分支）。但若你需要绑定内部值或处理多个情况，仍应用 match/if let。matches! 与 `..`、`|` 组合能表达复杂形状判断。注意它只回答“是否匹配”，不提供绑定，所以适合“分类/筛选”而非“提取”。用它能让条件表达式保持在单行，减少缩进层级；但不要为了短而牺牲清晰——复杂谓词仍应抽成命名函数。",
    "code": "#[derive(Debug, Clone, Copy, PartialEq)]\nenum Event {\n    Key(char),\n    Click { x: i32, y: i32 },\n    Resize(u32, u32),\n    Quit,\n}\n\nfn is_positional(event: &Event) -> bool {\n    matches!(event, Event::Click { .. })\n}\n\nfn is_vowel_key(event: &Event) -> bool {\n    matches!(event, Event::Key(c) if \"aeiou\".contains(*c))\n}\n\nfn main() {\n    let events = [\n        Event::Key('e'),\n        Event::Click { x: 1, y: 2 },\n        Event::Resize(800, 600),\n        Event::Quit,\n    ];\n\n    let positional: Vec<Event> = events\n        .iter()\n        .copied()\n        .filter(|e| is_positional(e))\n        .collect();\n    println!(\"positional = {:?}\", positional);\n    println!(\"vowel keys = {}\", events.iter().filter(|e| is_vowel_key(e)).count());\n    println!(\"has quit = {}\", events.iter().any(|e| matches!(e, Event::Quit)));\n}\n",
    "output": "positional = [Click { x: 1, y: 2 }]\nvowel keys = 1\nhas quit = true\n",
    "pitfalls": [
        "用 matches! 提取内部值：它只给 bool，要值就用 match/if let。",
        "守卫里引用层级写错：`matches!(x, Some(n) if *n > 0)` 需要按绑定类型解引用。",
        "为求短把复杂逻辑塞进 matches!：可读性优先，复杂谓词应抽函数。"
    ],
    "exercise": {
        "prompt": "定义 `enum Token { Word(String), Number(i64), Punct(char) }`，用 `matches!` 统计 Word 与 Number 的数量，并判断是否存在标点 `';'`；在 main 中输出三项结果。",
        "hint": "用 `.filter(|t| matches!(t, Token::Word(_))).count()` 等；标点判断用 `matches!(t, Token::Punct(';'))`。",
        "answer": "enum Token {\n    Word(String),\n    Number(i64),\n    Punct(char),\n}\n\nfn main() {\n    let tokens = [\n        Token::Word(String::from(\"let\")),\n        Token::Number(42),\n        Token::Punct(';'),\n        Token::Word(String::from(\"x\")),\n    ];\n    let words = tokens.iter().filter(|t| matches!(t, Token::Word(_))).count();\n    let numbers = tokens.iter().filter(|t| matches!(t, Token::Number(_))).count();\n    let has_semi = tokens.iter().any(|t| matches!(t, Token::Punct(';')));\n    println!(\"words = {}, numbers = {}, has_semi = {}\", words, numbers, has_semi);\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 64,
    "title": "状态机实战：交通灯 / 词法扫描",
    "level": "intermediate",
    "domain": "data-modeling",
    "summary": "用枚举 + 循环把“输入事件驱动状态迁移”写成确定性模拟器，覆盖交通灯与简易词法扫描。",
    "concepts": ["状态机实战", "事件循环", "转移表", "词法扫描", "确定性输出"],
    "objective": "能把一个事件序列喂给状态机，打印每次迁移后的状态，得到可复现的轨迹。",
    "prerequisites": ["060"],
    "explain": "实战把前两课的状态建模落到一个“事件循环”：维护当前状态，依次读入事件，调用 transfer 得到新状态或错误，打印轨迹。交通灯是经典：`Red -> Green -> Yellow -> Red`，用计时事件推进。词法扫描是另一个：状态在“普通/数字/字符串”间切换，字符进、token 出。要点：状态与事件都用枚举；转移写成 match；输出确定性（固定事件序列、固定顺序打印）；错误（非法事件）显式返回而非 panic。把状态机与输入解耦，便于测试：给一段事件序列就能复现完整轨迹。这种“纯转移 + 打印”的结构是协议解析、UI 状态、游戏逻辑的共同骨架。",
    "code": "#[derive(Debug, Clone, Copy, PartialEq, Eq)]\nenum Light {\n    Red,\n    Green,\n    Yellow,\n}\n\nimpl Light {\n    fn tick(self) -> Light {\n        match self {\n            Light::Red => Light::Green,\n            Light::Green => Light::Yellow,\n            Light::Yellow => Light::Red,\n        }\n    }\n}\n\nfn main() {\n    let mut light = Light::Red;\n    println!(\"start = {:?}\", light);\n    for step in 1..=6 {\n        light = light.tick();\n        println!(\"tick {} -> {:?}\", step, light);\n    }\n}\n",
    "output": "start = Red\ntick 1 -> Green\ntick 2 -> Yellow\ntick 3 -> Red\ntick 4 -> Green\ntick 5 -> Yellow\ntick 6 -> Red\n",
    "pitfalls": [
        "用局部变量加 if/else 手写状态：改用枚举 + match，新增状态时能被编译器提醒。",
        "状态迁移含副作用或 I/O：把打印放在循环外，转移保持纯粹便于测试。",
        "事件序列不固定：用确定性输入，否则轨迹无法复现与对比。"
    ],
    "exercise": {
        "prompt": "用显式状态机 `enum State { Outside, InWord, InNumber }` 实现简易词法扫描：遇到字母进入 InWord，遇到数字进入 InNumber，遇到空白回到 Outside；每次状态切换（或遇到空白）时先发出已累积的 token，类别变化会切分同一个无空白片段，例如 `a1` 会切成 `word:a` 与 `number:1`。按空白与类别边界输出 `word:值` / `number:值`，对输入 `\"a1 23 bc\"` 打印 4 个 token。",
        "hint": "可用字符匹配的简化实现：遍历字节，按 is_ascii_digit/is_alphabetic 切分 token。",
        "answer": "// 064 answer: explicit Outside / InWord / InNumber state machine\n#[derive(Debug, Clone, Copy, PartialEq, Eq)]\nenum State {\n    Outside,\n    InWord,\n    InNumber,\n}\n\nfn kind(state: State) -> &'static str {\n    match state {\n        State::InWord => \"word\",\n        State::InNumber => \"number\",\n        State::Outside => \"outside\",\n    }\n}\n\nfn scan(input: &str) -> Vec<String> {\n    let mut tokens = Vec::new();\n    let mut state = State::Outside;\n    let mut current = String::new();\n\n    for c in input.chars() {\n        let next = if c.is_whitespace() {\n            State::Outside\n        } else if c.is_ascii_digit() {\n            State::InNumber\n        } else {\n            State::InWord\n        };\n\n        // 进入 Outside，或类别发生变化：先把已积累的 token 发出\n        if next == State::Outside || next != state {\n            if !current.is_empty() {\n                tokens.push(format!(\"{}:{}\", kind(state), current));\n                current.clear();\n            }\n        }\n\n        state = next;\n        if state != State::Outside {\n            current.push(c);\n        }\n    }\n\n    if !current.is_empty() {\n        tokens.push(format!(\"{}:{}\", kind(state), current));\n    }\n    tokens\n}\n\nfn main() {\n    for token in scan(\"a1 23 bc\") {\n        println!(\"{}\", token);\n    }\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 65,
    "title": "错误建模：领域错误枚举",
    "level": "advanced",
    "domain": "data-modeling",
    "summary": "为一个领域定义专属错误枚举，携带上下文并实现 Display，让调用方精确区分失败原因。",
    "concepts": ["领域错误", "错误枚举", "Display", "上下文", "错误分类"],
    "objective": "能为一个模块定义可匹配、可展示、携带上下文错误的枚举，并在调用点分类处理。",
    "prerequisites": ["059"],
    "explain": "良好的错误类型应满足：可区分（调用方能 match 处理不同原因）、带上下文（哪个输入/哪个字段出错）、可展示（实现 Display）、可传播（配合 `?` 与 From）。做法是定义 `enum DomainError { ... }`，每个变体携带该原因需要的数据（如字段名、非法值、期望范围），实现 `std::error::Error`（可给 `source`）与 `Display`。相比 `String` 错误，枚举错误能被 match，从而让上层做重试/降级/用户提示等差异化处理。错误信息应稳定（测试可能断言），但不要把实现细节全部暴露。设计原则：错误变体按“调用方可能需要不同处理”来划分，而非按“代码中出错位置”。若错误集合可能扩展，加 `#[non_exhaustive]`（属高级话题）以免下游穷尽匹配被破坏。",
    "code": "use std::fmt;\n\n#[derive(Debug, PartialEq)]\nenum RegistrationError {\n    EmptyName,\n    NameTooLong { len: usize, max: usize },\n    InvalidAge { age: i32, min: i32, max: i32 },\n}\n\nimpl fmt::Display for RegistrationError {\n    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {\n        match self {\n            RegistrationError::EmptyName => write!(f, \"名字不能为空\"),\n            RegistrationError::NameTooLong { len, max } => {\n                write!(f, \"名字长度 {} 超过上限 {}\", len, max)\n            }\n            RegistrationError::InvalidAge { age, min, max } => {\n                write!(f, \"年龄 {} 不在 [{}, {}] 内\", age, min, max)\n            }\n        }\n    }\n}\n\nimpl std::error::Error for RegistrationError {}\n\n#[derive(Debug, PartialEq)]\nstruct User {\n    name: String,\n    age: i32,\n}\n\nfn register(name: &str, age: i32) -> Result<User, RegistrationError> {\n    if name.trim().is_empty() {\n        return Err(RegistrationError::EmptyName);\n    }\n    if name.chars().count() > 12 {\n        return Err(RegistrationError::NameTooLong { len: name.chars().count(), max: 12 });\n    }\n    if !(0..=150).contains(&age) {\n        return Err(RegistrationError::InvalidAge { age, min: 0, max: 150 });\n    }\n    Ok(User { name: name.to_string(), age })\n}\n\nfn main() {\n    for (name, age) in [(\"\", 20), (\"a-very-long-name\", 20), (\"Bob\", 200), (\"Bob\", 30)] {\n        match register(name, age) {\n            Ok(u) => println!(\"ok: {:?}\", u),\n            Err(e) => println!(\"err: {}\", e),\n        }\n    }\n}\n",
    "output": "err: 名字不能为空\nerr: 名字长度 16 超过上限 12\nerr: 年龄 200 不在 [0, 150] 内\nok: User { name: \"Bob\", age: 30 }\n",
    "pitfalls": [
        "用 String 当错误类型：调用方无法 match 分类，应定义枚举。",
        "错误变体按出错行号划分：应按“调用方需要的处理方式”划分。",
        "Display 输出依赖调试格式（如 {:?}）：面向用户的错误应手写稳定文案。"
    ],
    "exercise": {
        "prompt": "为“除法”定义 `enum DivError { DivideByZero, Overflow }`，实现 `checked_div(a: i64, b: i64) -> Result<i64, DivError>`（b=0 报 DivideByZero，`i64::MIN / -1` 报 Overflow）与 Display，在 main 中测试正常、零、溢出三种。",
        "hint": "守卫 b==0；用 `i128::checked_div(a, b).ok_or(DivError::Overflow)`（i128 一般不会溢出，可用 i64::MIN / -1 场景改 i64）。",
        "answer": "use std::fmt;\n\n#[derive(Debug, PartialEq)]\nenum DivError {\n    DivideByZero,\n    Overflow,\n}\n\nimpl fmt::Display for DivError {\n    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {\n        match self {\n            DivError::DivideByZero => write!(f, \"除数不能为 0\"),\n            DivError::Overflow => write!(f, \"结果溢出\"),\n        }\n    }\n}\n\nfn checked_div(a: i64, b: i64) -> Result<i64, DivError> {\n    if b == 0 {\n        return Err(DivError::DivideByZero);\n    }\n    a.checked_div(b).ok_or(DivError::Overflow)\n}\n\nfn main() {\n    println!(\"{:?}\", checked_div(10, 3));\n    println!(\"{}\", checked_div(1, 0).unwrap_err());\n    println!(\"{}\", checked_div(i64::MIN, -1).unwrap_err());\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 66,
    "title": "不可变更新：结构体更新语法",
    "level": "beginner",
    "domain": "data-modeling",
    "summary": "用 `..base` 从旧实例派生新实例，理解它在不可变风格下如何复用数据、何时发生移动。",
    "concepts": ["结构体更新语法", "..base", "不可变风格", "字段移动", "派生配置"],
    "objective": "能用更新语法从模板派生变体，并预测哪些字段被移动、哪些被复制。",
    "prerequisites": ["054"],
    "explain": "结构体更新语法 `Target { changed, ..base }` 用 base 的字段填充未列出的字段，是“以旧值为基础做少量变更”的惯用写法。它与函数式“不可变更新”理念一致：不修改原实例，而是产生新实例，旧实例保持可用（除非它的非 Copy 字段被移入新实例）。关键细节：只有未显式列出的字段才从 base 取值；若 base 的某非 Copy 字段被移走，之后不能再使用 base 的该字段（整体可能不可再用）。要保留 base 可继续使用，先 `base.clone()` 或让字段类型 Copy/用引用。更新语法也适用泛型与嵌套结构（可先解构再组合）。它常用于配置派生、状态更新（如 `State { count: count + 1, ..state }`）、测试夹具。相比逐个复制字段，它减少样板并降低遗漏字段的风险。",
    "code": "#[derive(Debug, Clone, PartialEq)]\nstruct Theme {\n    name: String,\n    primary: String,\n    font_size: u8,\n    dark: bool,\n}\n\nfn main() {\n    let base = Theme {\n        name: String::from(\"default\"),\n        primary: String::from(\"#3366ff\"),\n        font_size: 14,\n        dark: false,\n    };\n\n    // 基于克隆派生，base 仍可用\n    let dark = Theme { name: String::from(\"dark\"), dark: true, ..base.clone() };\n    println!(\"base = {:?}\", base);\n    println!(\"dark = {:?}\", dark);\n\n    // 状态更新风格：只变一个字段\n    let bigger = Theme { font_size: 18, ..dark.clone() };\n    println!(\"bigger font_size = {}\", bigger.font_size);\n}\n",
    "output": "base = Theme { name: \"default\", primary: \"#3366ff\", font_size: 14, dark: false }\ndark = Theme { name: \"dark\", primary: \"#3366ff\", font_size: 14, dark: true }\nbigger font_size = 18\n",
    "pitfalls": [
        "更新语法后继续用 base 的非 Copy 字段：该字段已被移动，会报 E0382。",
        "以为 `..base` 是整体克隆：它只搬运未被覆盖的字段，非 Copy 字段是移动。",
        "显式列出的字段仍从 base 取：只有未列出的字段才来自 base，列出的以新值为准。"
    ],
    "exercise": {
        "prompt": "定义 `#[derive(Clone, Debug)] struct Param { url: String, timeout_ms: u64, retries: u8 }`，构造一个默认值，再用更新语法派生只改 timeout_ms 的新实例并打印两个实例。",
        "hint": "用 `Param { timeout_ms: 2000, ..base.clone() }`。",
        "answer": "#[derive(Clone, Debug)]\nstruct Param {\n    url: String,\n    timeout_ms: u64,\n    retries: u8,\n}\n\nfn main() {\n    let base = Param { url: String::from(\"https://example.invalid\"), timeout_ms: 1000, retries: 3 };\n    let tuned = Param { timeout_ms: 2000, ..base.clone() };\n    println!(\"{:?}\", base);\n    println!(\"{:?}\", tuned);\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 67,
    "title": "密封模式与 `#[non_exhaustive]` 概念",
    "level": "advanced",
    "domain": "data-modeling",
    "summary": "理解“密封 trait/枚举”的意图：控制扩展点、保持向后兼容，掌握 `#[non_exhaustive]` 的语义。",
    "concepts": ["密封模式", "non_exhaustive", "向后兼容", "private supertrait", "公共 API"],
    "objective": "能解释为何库作者要限制下游扩展，并说明 `#[non_exhaustive]` 对 match 的影响。",
    "prerequisites": ["055"],
    "explain": "密封（sealed）指“只有本 crate 能实现该 trait 或扩展该枚举”，用于保持未来修改自由：若下游能随意实现 trait，库作者新增方法就会破坏它们。手写密封的常见手法是让 trait 继承一个私有 trait：`pub trait Api: private::Sealed {}`，下游无法命名 `private::Sealed` 因而无法实现 `Api`。对枚举，`#[non_exhaustive]` 让其他 crate 在 match 时必须加 `_` 分支，从而允许作者将来新增变体而不算破坏性变更；本 crate 内部仍可穷尽匹配。同理 `#[non_exhaustive]` 也可用在结构体上，禁止外部用结构体字面量构造，只能通过作者提供的构造函数。这些机制服务于 semver：区分“我能改”与“调用方依赖”的边界。代价是增加了下游使用复杂度，因此只在确实需要控制扩展点时使用。要点：密封不是为了限制用户，而是为了长期演进的兼容性。",
    "code": "// 单文件演示“本 crate 内部穷尽、外部需兜底”的语义（用模块模拟 crate 边界）。\nmod api {\n    #[derive(Debug, Clone, Copy, PartialEq)]\n    #[non_exhaustive]\n    pub enum Status {\n        Active,\n        Suspended,\n        Closed,\n    }\n\n    impl Status {\n        pub fn is_terminal(self) -> bool {\n            // 本模块内可穷尽匹配\n            matches!(self, Status::Closed)\n        }\n    }\n}\n\nfn main() {\n    let status = api::Status::Active;\n    println!(\"status = {:?}, terminal = {}\", status, status.is_terminal());\n\n    // 假设这里是“外部使用者”：non_exhaustive 要求加 _ 兜底\n    let label = match api::Status::Suspended {\n        api::Status::Active => \"active\",\n        api::Status::Closed => \"closed\",\n        _ => \"other\",\n    };\n    println!(\"label = {}\", label);\n}\n",
    "output": "status = Active, terminal = false\nlabel = other\n",
    "pitfalls": [
        "给 `#[non_exhaustive]` 枚举做穷尽 match：外部必须加 `_`，否则编译失败。",
        "以为 non_exhaustive 影响本 crate：本 crate 内部仍可穷尽匹配。",
        "滥用密封限制扩展：若确实希望下游实现 trait，就不要密封，否则伤害生态。"
    ],
    "exercise": {
        "prompt": "用私有 supertrait 手法在单文件里建模一个“密封 trait”：定义 `mod sealed { pub trait Sealed {} }` 与 `pub trait Shape: sealed::Sealed { fn area(&self) -> f64; }`，为本地的 Circle 与 Square 实现二者，在 main 中打印两个面积。",
        "hint": "为每个类型同时 `impl sealed::Sealed for X {}` 与 `impl Shape for X`。",
        "answer": "mod sealed {\n    pub trait Sealed {}\n}\n\npub trait Shape: sealed::Sealed {\n    fn area(&self) -> f64;\n}\n\nstruct Circle(f64);\nstruct Square(f64);\n\nimpl sealed::Sealed for Circle {}\nimpl sealed::Sealed for Square {}\n\nimpl Shape for Circle {\n    fn area(&self) -> f64 {\n        std::f64::consts::PI * self.0 * self.0\n    }\n}\n\nimpl Shape for Square {\n    fn area(&self) -> f64 {\n        self.0 * self.0\n    }\n}\n\nfn main() {\n    println!(\"{:.2}\", Circle(1.0).area());\n    println!(\"{:.2}\", Square(3.0).area());\n}\n"
    },
    "runtime": "desktop"
},
{
    "id": 68,
    "title": "实战：命令解析器（枚举 + 匹配）",
    "level": "intermediate",
    "domain": "data-modeling",
    "summary": "把一行命令文本解析为命令枚举，实现带参数校验的解析器并在 main 中打印执行计划。",
    "concepts": ["命令解析", "枚举建模", "参数校验", "错误处理", "确定性输出"],
    "objective": "能定义命令枚举并把文本解析为结构化命令，对非法输入给出精确错误。",
    "prerequisites": ["064"],
    "explain": "命令解析器把非结构化文本转成结构化枚举：`enum Command { Move { dx, dy }, Say(String), Quit }`。流程：按空白切词，取首个词分派，校验参数数量与类型，构造枚举或返回错误。要点：每个命令的参数数量不同，需分别校验；数字参数用 parse 并给出上下文错误；未知命令返回错误而非 panic。把解析结果与执行分离：解析产生 `Result<Command, ParseError>`，执行单独函数，便于测试（给固定文本就能复现）。这种结构与前面计算器实战互补：计算器解析表达式，本课解析“命令 + 参数”。实现时可用一个小辅助函数解析“恰好 N 个参数”，减少重复。输出确定性来自固定输入与固定打印顺序。",
    "code": "use std::fmt;\n\n#[derive(Debug, PartialEq)]\nenum Command {\n    Move { dx: i32, dy: i32 },\n    Say(String),\n    Repeat { times: u32, text: String },\n    Quit,\n}\n\n#[derive(Debug, PartialEq)]\nenum ParseError {\n    Empty,\n    Unknown(String),\n    MissingArgs { command: String, expected: usize, got: usize },\n    BadNumber(String),\n}\n\nimpl fmt::Display for ParseError {\n    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {\n        match self {\n            ParseError::Empty => write!(f, \"空命令\"),\n            ParseError::Unknown(c) => write!(f, \"未知命令: {}\", c),\n            ParseError::MissingArgs { command, expected, got } => {\n                write!(f, \"{} 需要 {} 个参数, 实际 {}\", command, expected, got)\n            }\n            ParseError::BadNumber(s) => write!(f, \"无法解析数字: {}\", s),\n        }\n    }\n}\n\nfn parse(input: &str) -> Result<Command, ParseError> {\n    let mut parts = input.split_whitespace();\n    let name = parts.next().ok_or(ParseError::Empty)?;\n    let rest: Vec<&str> = parts.collect();\n\n    match name {\n        // quit 不接受任何多余参数\n        \"quit\" => {\n            if !rest.is_empty() {\n                return Err(ParseError::MissingArgs { command: name.into(), expected: 0, got: rest.len() });\n            }\n            Ok(Command::Quit)\n        }\n        \"move\" => {\n            if rest.len() != 2 {\n                return Err(ParseError::MissingArgs { command: name.into(), expected: 2, got: rest.len() });\n            }\n            let dx = rest[0].parse().map_err(|_| ParseError::BadNumber(rest[0].into()))?;\n            let dy = rest[1].parse().map_err(|_| ParseError::BadNumber(rest[1].into()))?;\n            Ok(Command::Move { dx, dy })\n        }\n        \"say\" => {\n            if rest.is_empty() {\n                return Err(ParseError::MissingArgs { command: name.into(), expected: 1, got: 0 });\n            }\n            Ok(Command::Say(rest.join(\" \")))\n        }\n        \"repeat\" => {\n            if rest.len() < 2 {\n                return Err(ParseError::MissingArgs { command: name.into(), expected: 2, got: rest.len() });\n            }\n            let times = rest[0].parse().map_err(|_| ParseError::BadNumber(rest[0].into()))?;\n            Ok(Command::Repeat { times, text: rest[1..].join(\" \") })\n        }\n        other => Err(ParseError::Unknown(other.into())),\n    }\n}\n\nfn main() {\n    let inputs = [\n        \"move 3 -4\",\n        \"say hello world\",\n        \"repeat 2 rust\",\n        \"quit\",\n        \"quit now\",\n        \"move 3\",\n        \"move a b\",\n        \"dance\",\n        \"\",\n    ];\n    for input in inputs {\n        match parse(input) {\n            Ok(cmd) => println!(\"ok  {:?} => {:?}\", input, cmd),\n            Err(e) => println!(\"err {:?} => {}\", input, e),\n        }\n    }\n}\n",
    "output": "ok  \"move 3 -4\" => Move { dx: 3, dy: -4 }\nok  \"say hello world\" => Say(\"hello world\")\nok  \"repeat 2 rust\" => Repeat { times: 2, text: \"rust\" }\nok  \"quit\" => Quit\nerr \"quit now\" => quit 需要 0 个参数, 实际 1\nerr \"move 3\" => move 需要 2 个参数, 实际 1\nerr \"move a b\" => 无法解析数字: a\nerr \"dance\" => 未知命令: dance\nerr \"\" => 空命令\n",
    "pitfalls": [
        "未知命令直接 panic：应返回错误，让 REPL/调用方决定提示或退出。",
        "参数数量校验遗漏：`split_whitespace` 可能给出少于预期的参数，必须显式检查。",
        "把整行参数当单个 token：say 这类命令应 `join` 剩余词，保留空格语义。"
    ],
    "exercise": {
        "prompt": "扩展解析器支持 `set k v` 与 `del k`：命令名之后 `set` 需要两个参数（键与值），值可含空格并拼回；`del` 需要恰好一个参数，多给也算错。写 `parse` 返回相应 Command 并在 main 中测试合法与非法各两条；另外让 `quit` 拒绝任何多余参数（命令名之后必须为零个参数）。",
        "hint": "定义新 Command 变体；set 要求 rest.len()>=2，键为 rest[0]，值为 rest[1..].join(\" \")。",
        "answer": "use std::fmt;\n\n#[derive(Debug, PartialEq)]\nenum Command {\n    Set { key: String, value: String },\n    Del { key: String },\n    Quit,\n}\n\n#[derive(Debug, PartialEq)]\nenum ParseError {\n    Empty,\n    Unknown(String),\n    MissingArgs { command: String, expected: usize, got: usize },\n}\n\nimpl fmt::Display for ParseError {\n    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {\n        match self {\n            ParseError::Empty => write!(f, \"空命令\"),\n            ParseError::Unknown(c) => write!(f, \"未知命令: {}\", c),\n            ParseError::MissingArgs { command, expected, got } => {\n                write!(f, \"{} 需要 {} 个参数, 实际 {}\", command, expected, got)\n            }\n        }\n    }\n}\n\nfn parse(input: &str) -> Result<Command, ParseError> {\n    let mut parts = input.split_whitespace();\n    let name = parts.next().ok_or(ParseError::Empty)?;\n    let rest: Vec<&str> = parts.collect();\n    match name {\n        // quit 不接受任何多余参数（命令名之后必须为零个参数）\n        \"quit\" => {\n            if !rest.is_empty() {\n                return Err(ParseError::MissingArgs { command: name.into(), expected: 0, got: rest.len() });\n            }\n            Ok(Command::Quit)\n        }\n        // set 需要“命令名之后”两个参数：key 与 value；value 可含空格（拼回剩余）\n        \"set\" => {\n            if rest.len() < 2 {\n                return Err(ParseError::MissingArgs { command: name.into(), expected: 2, got: rest.len() });\n            }\n            Ok(Command::Set { key: rest[0].into(), value: rest[1..].join(\" \") })\n        }\n        // del 需要“命令名之后”恰好一个参数，多给也算错\n        \"del\" => {\n            if rest.len() != 1 {\n                return Err(ParseError::MissingArgs { command: name.into(), expected: 1, got: rest.len() });\n            }\n            Ok(Command::Del { key: rest[0].into() })\n        }\n        other => Err(ParseError::Unknown(other.into())),\n    }\n}\n\nfn main() {\n    // quit：零参数成功，多参数报错\n    assert_eq!(parse(\"quit\"), Ok(Command::Quit));\n    assert_eq!(\n        parse(\"quit now\"),\n        Err(ParseError::MissingArgs { command: String::from(\"quit\"), expected: 0, got: 1 })\n    );\n    assert_eq!(parse(\"set mode dark fast\"), Ok(Command::Set { key: String::from(\"mode\"), value: String::from(\"dark fast\") }));\n    assert!(parse(\"set only\").is_err());\n    assert_eq!(parse(\"del mode\"), Ok(Command::Del { key: String::from(\"mode\") }));\n    assert!(parse(\"del a b\").is_err());\n\n    for input in [\"quit\", \"quit now\", \"set mode dark fast\", \"del mode\", \"set only\", \"del a b\", \"nope\"] {\n        match parse(input) {\n            Ok(c) => println!(\"ok  {:?} => {:?}\", input, c),\n            Err(e) => println!(\"err {:?} => {}\", input, e),\n        }\n    }\n}\n"
    },
    "runtime": "desktop"
},
]
