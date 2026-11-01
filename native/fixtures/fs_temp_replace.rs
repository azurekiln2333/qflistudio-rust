use std::{env, fs};

// Harness setup: the project contains retained-cleanup-directory/sentinel.txt
// with exact bytes "ordinary-project-directory-retained". After this program
// exits, destroying the session must preserve that directory at the remembered
// temporary pathname and must not chase the moved original by another path.
fn main() -> std::io::Result<()> {
    let temporary = env::temp_dir();
    let moved = env::current_dir()?.join("renamed-owned-temporary");
    assert!(!moved.exists());
    fs::write(
        temporary.join("owned-marker.txt"),
        b"original-session-temporary",
    )?;
    fs::rename(&temporary, &moved)?;
    fs::rename("retained-cleanup-directory", &temporary)?;
    assert_eq!(
        fs::read(temporary.join("sentinel.txt"))?,
        b"ordinary-project-directory-retained"
    );
    println!("filesystem-temporary-replaced");
    Ok(())
}
