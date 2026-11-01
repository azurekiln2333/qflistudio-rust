use std::{env, fs};

fn main() {
    let root = env::current_dir().unwrap();
    let temporary = env::temp_dir();
    assert_eq!(temporary.parent(), Some(root.as_path()));
    env::set_current_dir("session-work").unwrap();
    fs::write("session-first.txt", b"first-session-file").unwrap();
    println!("temporary={}", temporary.display());
    println!("cwd={}", env::current_dir().unwrap().display());
}
