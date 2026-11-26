use std::fmt;

#[derive(Debug, PartialEq)]
enum Command {
    Set { key: String, value: String },
    Del { key: String },
}

#[derive(Debug, PartialEq)]
enum ParseError {
    Empty,
    Unknown(String),
    MissingArgs { command: String, expected: usize, got: usize },
}

impl fmt::Display for ParseError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ParseError::Empty => write!(f, "空命令"),
            ParseError::Unknown(c) => write!(f, "未知命令: {}", c),
            ParseError::MissingArgs { command, expected, got } => {
                write!(f, "{} 需要 {} 个参数, 实际 {}", command, expected, got)
            }
        }
    }
}

fn parse(input: &str) -> Result<Command, ParseError> {
    let mut parts = input.split_whitespace();
    let name = parts.next().ok_or(ParseError::Empty)?;
    let rest: Vec<&str> = parts.collect();
    match name {
        // set 需要“命令名之后”两个参数：key 与 value；value 可含空格（拼回剩余）
        "set" => {
            if rest.len() < 2 {
                return Err(ParseError::MissingArgs { command: name.into(), expected: 2, got: rest.len() });
            }
            Ok(Command::Set { key: rest[0].into(), value: rest[1..].join(" ") })
        }
        // del 需要“命令名之后”恰好一个参数，多给也算错
        "del" => {
            if rest.len() != 1 {
                return Err(ParseError::MissingArgs { command: name.into(), expected: 1, got: rest.len() });
            }
            Ok(Command::Del { key: rest[0].into() })
        }
        other => Err(ParseError::Unknown(other.into())),
    }
}

fn main() {
    for input in ["set mode dark fast", "del mode", "set only", "del a b", "nope"] {
        match parse(input) {
            Ok(c) => println!("ok  {:?} => {:?}", input, c),
            Err(e) => println!("err {:?} => {}", input, e),
        }
    }
}
