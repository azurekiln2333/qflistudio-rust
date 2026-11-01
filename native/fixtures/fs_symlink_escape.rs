use std::fs::{self, OpenOptions};

// Harness setup: root/escape-dir -> an outside directory containing sentinel.txt;
// root/escape-file -> that outside sentinel.txt. The sentinel must start and end
// with the exact bytes "outside-unchanged". Neither link is guest-created.
fn main() {
    for path in ["escape-dir/sentinel.txt", "escape-file"] {
        assert!(fs::read(path).is_err());
        assert!(OpenOptions::new().write(true).truncate(true).open(path).is_err());
        assert!(fs::canonicalize(path).is_err());
    }
    assert!(fs::create_dir("escape-dir/new-directory").is_err());
    assert!(std::env::set_current_dir("escape-dir").is_err());
    let link = fs::symlink_metadata("escape-file").unwrap();
    assert!(link.file_type().is_symlink());
    // Removing the link itself is safe; it must not remove the outside target.
    fs::remove_file("escape-file").unwrap();
    println!("filesystem-symlink-escape-denied");
}
