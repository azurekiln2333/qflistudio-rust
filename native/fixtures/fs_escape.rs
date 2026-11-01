use std::fs::{self, OpenOptions};
use std::path::Path;

fn main() {
    let original = std::env::current_dir().unwrap();
    for path in [
        Path::new("../qfli-outside-sentinel.txt"),
        Path::new("/etc/passwd"),
        Path::new("/proc/self/environ"),
    ] {
        assert!(fs::read(path).is_err(), "read escaped: {}", path.display());
        assert!(fs::write(path, b"forbidden").is_err(), "write escaped: {}", path.display());
        assert!(fs::canonicalize(path).is_err(), "canonicalize escaped: {}", path.display());
    }
    assert!(std::env::set_current_dir("..").is_err());
    assert_eq!(std::env::current_dir().unwrap(), original);
    assert!(fs::create_dir("../qfli-outside-directory").is_err());
    let local = std::env::temp_dir().join("owned.txt");
    fs::write(&local, b"retained").unwrap();
    assert!(fs::rename(&local, "../qfli-outside-sentinel.txt").is_err());
    assert_eq!(fs::read(&local).unwrap(), b"retained");
    assert!(OpenOptions::new().write(true).create_new(true)
        .open("../qfli-outside-created.txt").is_err());
    println!("filesystem-escape-denied");
}
