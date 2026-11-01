use std::fs::{self, OpenOptions};
use std::io::{Seek, SeekFrom, Write};
use std::time::{SystemTime, UNIX_EPOCH};

fn main() -> std::io::Result<()> {
    let original = std::env::current_dir()?;
    let temporary = std::env::temp_dir();
    assert!(temporary.starts_with(&original));
    assert_eq!(std::process::id(), 1000);
    assert!(SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs() > 0);

    let work = temporary.join("roundtrip");
    fs::create_dir(&work)?;
    std::env::set_current_dir(&work)?;
    fs::write("source.txt", "你好\n")?;
    assert_eq!(fs::read_to_string("source.txt")?, "你好\n");
    let mut file = OpenOptions::new().read(true).write(true).open("source.txt")?;
    assert_eq!(file.seek(SeekFrom::End(0))?, 7);
    file.write_all(b"rust\n")?;
    file.sync_all()?;
    drop(file);
    fs::rename("source.txt", "renamed.txt")?;
    assert_eq!(fs::metadata("renamed.txt")?.len(), 12);
    assert_eq!(fs::read_to_string("renamed.txt")?, "你好\nrust\n");
    assert_eq!(fs::read_dir(".")?.count(), 1);
    assert_eq!(fs::canonicalize("renamed.txt")?, work.join("renamed.txt"));
    std::env::set_current_dir(&original)?;
    fs::remove_dir_all(&work)?;
    assert!(!work.exists());
    println!("filesystem-roundtrip-ok");
    Ok(())
}
