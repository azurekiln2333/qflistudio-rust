use std::{env, fs, path::Path};

fn main() {
    let root = env::current_dir().unwrap();
    let temporary = env::temp_dir();
    assert_eq!(temporary.parent(), Some(root.as_path()));
    assert!(!Path::new("session-first.txt").exists());
    assert_eq!(fs::read("session-work/session-first.txt").unwrap(), b"first-session-file");
    fs::write("session-second.txt", b"second-session-file").unwrap();
    println!("temporary={}", temporary.display());
    println!("cwd={}", root.display());
}
