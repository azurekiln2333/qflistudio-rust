fn main() {
    for key in ["HOME", "PATH", "LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH", "USERPROFILE"] {
        assert!(std::env::var_os(key).is_none(), "ambient environment leaked: {key}");
    }
    let temporary = std::env::temp_dir();
    assert!(temporary.starts_with(std::env::current_dir().unwrap()));
    assert!(temporary.is_dir());
    assert_eq!(std::process::id(), 1000);
    println!("filesystem-environment-isolated");
}
