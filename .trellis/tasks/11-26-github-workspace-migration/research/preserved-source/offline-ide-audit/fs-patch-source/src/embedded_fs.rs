//! Explicit, per-interpreter local filesystem capability for embedded hosts.
//!
//! The root is chosen by the embedding application, never by a guest environment
//! variable. Linux/Android/OHOS lookups walk pinned directory descriptors without
//! following symlinks. Other hosts fail closed until they provide equivalent APIs.
use std::fs::{self, File, Metadata, OpenOptions, ReadDir};
use std::io::{self, ErrorKind};
use std::path::{Component, Path, PathBuf};
use std::sync::Mutex;
use std::sync::atomic::{AtomicU64, Ordering};

#[derive(Debug)]
pub struct EmbeddedFileSystem {
    root: PathBuf,
    root_dir: File,
    cwd: Mutex<PathBuf>,
    temporary: PathBuf,
    temporary_dir: Option<File>,
}

static NEXT_TEMPORARY: AtomicU64 = AtomicU64::new(1);

fn denied() -> io::Error {
    io::Error::new(ErrorKind::PermissionDenied, "path is outside the embedded project or uses a symlink")
}

impl EmbeddedFileSystem {
    /// Authorize one existing project directory. The application must select this
    /// directory explicitly, and must not pass a runtime/sysroot or ambient cwd.
    /// The returned temporary directory is fresh and belongs to this capability.
    pub fn new(root: &Path) -> io::Result<Self> {
        if !root.is_absolute() { return Err(denied()); }
        let root = fs::canonicalize(root)?;
        if root.parent().is_none() { return Err(denied()); }
        let root_dir = open_root(&root)?;
        let mut fs = Self {
            cwd: Mutex::new(PathBuf::new()),
            temporary: PathBuf::new(),
            temporary_dir: None,
            root,
            root_dir,
        };
        // Do not reuse another session's directory, even after a process restart.
        loop {
            let id = NEXT_TEMPORARY.fetch_add(1, Ordering::Relaxed);
            let name = PathBuf::from(format!(".qfli-miri-tmp-{id}"));
            match fs.create_dir(&name, 0o700) {
                Ok(()) => {
                    let directory = match fs.directory(&name) {
                        Ok(directory) => directory,
                        Err(error) => {
                            // No guest can run yet. Roll back only the empty
                            // entry just created, never recursively remove it.
                            if let Ok(parent) = descriptor_path(&fs.root_dir) {
                                let _ = fs::remove_dir(parent.join(&name));
                            }
                            return Err(error);
                        }
                    };
                    fs.temporary_dir = Some(directory);
                    fs.temporary = fs.root.join(name);
                    break;
                }
                Err(error) if error.kind() == ErrorKind::AlreadyExists => continue,
                Err(error) => return Err(error),
            }
        }
        Ok(fs)
    }

    pub fn root(&self) -> &Path { &self.root }
    pub fn temporary_dir(&self) -> &Path { &self.temporary }

    pub fn current_dir(&self) -> io::Result<PathBuf> {
        let cwd = self.cwd.lock().map_err(|_| io::Error::other("embedded cwd lock poisoned"))?;
        Ok(if cwd.as_os_str().is_empty() {
            self.root.clone()
        } else {
            self.root.join(&*cwd)
        })
    }

    pub fn set_current_dir(&self, path: &Path) -> io::Result<()> {
        let relative = self.relative(path)?;
        // Validate the complete directory before changing only our session state.
        let _directory = self.directory(&relative)?;
        *self.cwd.lock().map_err(|_| io::Error::other("embedded cwd lock poisoned"))? = relative;
        Ok(())
    }

    fn relative(&self, path: &Path) -> io::Result<PathBuf> {
        if path.as_os_str().is_empty() { return Err(io::Error::from(ErrorKind::NotFound)); }
        let mut result;
        let tail;
        if path.is_absolute() {
            result = PathBuf::new();
            tail = path.strip_prefix(&self.root).map_err(|_| denied())?;
        } else {
            result = self.cwd.lock().map_err(|_| io::Error::other("embedded cwd lock poisoned"))?.clone();
            tail = path;
        }
        for component in tail.components() {
            match component {
                Component::Normal(name) => result.push(name),
                Component::CurDir => {},
                Component::ParentDir => { if !result.pop() { return Err(denied()); } },
                Component::RootDir | Component::Prefix(_) => return Err(denied()),
            }
        }
        Ok(result)
    }

    fn directory(&self, relative: &Path) -> io::Result<File> {
        let mut directory = self.root_dir.try_clone()?;
        for component in relative.components() {
            let Component::Normal(name) = component else { return Err(denied()); };
            directory = open_directory_at(&directory, name)?;
        }
        Ok(directory)
    }

    fn parent(&self, path: &Path) -> io::Result<GuardedPath> {
        let relative = self.relative(path)?;
        let Some(name) = relative.file_name() else { return Err(denied()); };
        let parent = relative.parent().unwrap_or(Path::new(""));
        let directory = self.directory(parent)?;
        GuardedPath::new(directory, name)
    }

    pub(crate) fn open(&self, path: &Path, mut options: OpenOptions) -> io::Result<File> {
        let guarded = self.parent(path)?;
        // O_NONBLOCK prevents a pre-existing FIFO from blocking the interpreter.
        // O_NOFOLLOW is required on the final component as well as each parent.
        set_no_follow(&mut options)?;
        let file = options.open(&guarded.path)?;
        let ty = file.metadata()?.file_type();
        if !ty.is_file() && !ty.is_dir() { return Err(denied()); }
        Ok(file)
    }

    pub(crate) fn metadata(&self, path: &Path, follow_symlink: bool) -> io::Result<Metadata> {
        let relative = self.relative(path)?;
        if relative.as_os_str().is_empty() { return self.root_dir.metadata(); }
        let guarded = self.parent(path)?;
        let file = metadata_file(&guarded)?;
        let metadata = file.metadata()?;
        let ty = metadata.file_type();
        if ty.is_symlink() {
            if follow_symlink { return Err(denied()); }
        } else if !ty.is_file() && !ty.is_dir() {
            return Err(denied());
        }
        Ok(metadata)
    }

    pub(crate) fn create_dir(&self, path: &Path, mode: u32) -> io::Result<()> {
        let guarded = self.parent(path)?;
        #[cfg_attr(not(unix), allow(unused_mut))]
        let mut builder = fs::DirBuilder::new();
        #[cfg(unix)] { use std::os::unix::fs::DirBuilderExt; builder.mode(mode & 0o777); }
        #[cfg(not(unix))] let _ = mode;
        builder.create(&guarded.path)
    }

    pub(crate) fn remove_file(&self, path: &Path) -> io::Result<()> {
        let guarded = self.parent(path)?;
        fs::remove_file(&guarded.path)
    }

    pub(crate) fn remove_dir(&self, path: &Path) -> io::Result<()> {
        let guarded = self.parent(path)?;
        fs::remove_dir(&guarded.path)
    }

    pub(crate) fn rename(&self, from: &Path, to: &Path) -> io::Result<()> {
        let from = self.parent(from)?;
        let to = self.parent(to)?;
        // rename/unlink never dereference the final directory entry.
        fs::rename(&from.path, &to.path)
    }

    pub(crate) fn read_dir(&self, path: &Path) -> io::Result<ReadDir> {
        let directory = self.directory(&self.relative(path)?)?;
        // read_dir opens its own descriptor while `directory` is still alive.
        // DirEntry metadata uses that retained descriptor, never a guest path.
        fs::read_dir(descriptor_path(&directory)?)
    }

    pub(crate) fn canonicalize(&self, path: &Path) -> io::Result<PathBuf> {
        let relative = self.relative(path)?;
        self.metadata(path, true)?;
        Ok(self.root.join(relative))
    }
}

impl Drop for EmbeddedFileSystem {
    fn drop(&mut self) {
        // Keep the created directory alive so its identity cannot be reused.
        // A guest may rename it and replace the old name with ordinary data.
        // Never chase a renamed temporary or recursively delete its replacement.
        // Drop follows interpreter exit; external concurrent host renames are
        // outside this per-interpreter capability's namespace guarantees.
        if let Some(owned) = &self.temporary_dir {
            if let Ok(guarded) = self.parent(&self.temporary) {
                if let Ok(current) = metadata_file(&guarded) {
                    if same_directory(owned, &current).unwrap_or(false) {
                        let _ = fs::remove_dir_all(&guarded.path);
                    }
                }
            }
        }
    }
}

#[cfg(any(target_os = "linux", target_os = "android"))]
fn same_directory(owned: &File, current: &File) -> io::Result<bool> {
    use std::os::unix::fs::MetadataExt;
    let owned = owned.metadata()?;
    let current = current.metadata()?;
    Ok(current.is_dir() && owned.dev() == current.dev() && owned.ino() == current.ino())
}
#[cfg(not(any(target_os = "linux", target_os = "android")))]
fn same_directory(_owned: &File, _current: &File) -> io::Result<bool> { Ok(false) }

/// Retains the parent descriptor until the host operation is complete. The only
/// symlink followed here is the kernel's own /proc/self/fd entry for that pinned
/// descriptor, not a guest-controlled filesystem entry.
struct GuardedPath { _directory: File, path: PathBuf }
impl GuardedPath {
    fn new(directory: File, name: &std::ffi::OsStr) -> io::Result<Self> {
        let path = descriptor_path(&directory)?.join(name);
        Ok(Self { _directory: directory, path })
    }
}

#[cfg(any(target_os = "linux", target_os = "android"))]
fn descriptor_path(file: &File) -> io::Result<PathBuf> {
    use std::os::fd::AsRawFd;
    Ok(PathBuf::from(format!("/proc/self/fd/{}", file.as_raw_fd())))
}
#[cfg(not(any(target_os = "linux", target_os = "android")))]
fn descriptor_path(_file: &File) -> io::Result<PathBuf> {
    Err(io::Error::new(ErrorKind::Unsupported, "embedded filesystem requires descriptor-relative host access"))
}

#[cfg(any(target_os = "linux", target_os = "android"))]
fn open_root(path: &Path) -> io::Result<File> {
    use std::os::unix::fs::OpenOptionsExt;
    OpenOptions::new().read(true).custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW).open(path)
}
#[cfg(not(any(target_os = "linux", target_os = "android")))]
fn open_root(_path: &Path) -> io::Result<File> { Err(io::Error::from(ErrorKind::Unsupported)) }

#[cfg(any(target_os = "linux", target_os = "android"))]
fn open_directory_at(directory: &File, name: &std::ffi::OsStr) -> io::Result<File> {
    use std::ffi::CString;
    use std::os::fd::{AsRawFd, FromRawFd};
    use std::os::unix::ffi::OsStrExt;
    let name = CString::new(name.as_bytes()).map_err(|_| denied())?;
    // SAFETY: directory is live, name is NUL-terminated, and ownership of a
    // successful new descriptor is immediately transferred to File.
    let fd = unsafe { libc::openat(directory.as_raw_fd(), name.as_ptr(),
        libc::O_RDONLY | libc::O_CLOEXEC | libc::O_DIRECTORY | libc::O_NOFOLLOW) };
    if fd < 0 { return Err(io::Error::last_os_error()); }
    Ok(unsafe { File::from_raw_fd(fd) })
}
#[cfg(not(any(target_os = "linux", target_os = "android")))]
fn open_directory_at(_directory: &File, _name: &std::ffi::OsStr) -> io::Result<File> {
    Err(io::Error::from(ErrorKind::Unsupported))
}

#[cfg(any(target_os = "linux", target_os = "android"))]
fn set_no_follow(options: &mut OpenOptions) -> io::Result<()> {
    use std::os::unix::fs::OpenOptionsExt;
    options.custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK);
    Ok(())
}
#[cfg(not(any(target_os = "linux", target_os = "android")))]
fn set_no_follow(_options: &mut OpenOptions) -> io::Result<()> { Err(io::Error::from(ErrorKind::Unsupported)) }

#[cfg(any(target_os = "linux", target_os = "android"))]
fn metadata_file(guarded: &GuardedPath) -> io::Result<File> {
    use std::os::unix::fs::OpenOptionsExt;
    OpenOptions::new().read(true).custom_flags(libc::O_PATH | libc::O_NOFOLLOW).open(&guarded.path)
}
#[cfg(not(any(target_os = "linux", target_os = "android")))]
fn metadata_file(_guarded: &GuardedPath) -> io::Result<File> { Err(io::Error::from(ErrorKind::Unsupported)) }

#[cfg(all(test, any(target_os = "linux", target_os = "android")))]
mod tests {
    use super::*;
    use std::io::{Read, Write};
    use std::os::unix::fs::symlink;

    struct Fixture(PathBuf);
    impl Fixture {
        fn new() -> Self {
            let id = NEXT_TEMPORARY.fetch_add(1, Ordering::Relaxed);
            let path = std::env::temp_dir().join(format!("qfli-embedded-fs-test-{}-{id}", std::process::id()));
            fs::create_dir(&path).unwrap();
            Self(path)
        }
    }
    impl Drop for Fixture { fn drop(&mut self) { let _ = fs::remove_dir_all(&self.0); } }

    #[test]
    fn real_roundtrip_keeps_host_cwd_and_creates_unique_local_temporary_dirs() {
        let fixture = Fixture::new();
        let original_cwd = std::env::current_dir().unwrap();
        let first = EmbeddedFileSystem::new(&fixture.0).unwrap();
        let second = EmbeddedFileSystem::new(&fixture.0).unwrap();
        assert_ne!(first.temporary_dir(), second.temporary_dir());
        assert!(first.temporary_dir().starts_with(&fixture.0));
        first.create_dir(Path::new("work"), 0o700).unwrap();
        first.set_current_dir(Path::new("work")).unwrap();
        assert_eq!(first.current_dir().unwrap(), fixture.0.join("work"));
        assert_eq!(second.current_dir().unwrap().as_os_str(), fixture.0.as_os_str());
        assert_eq!(std::env::current_dir().unwrap(), original_cwd);
        let second_temporary = second.temporary_dir().to_owned();
        drop(second);
        assert!(!second_temporary.exists());
        assert!(first.temporary_dir().is_dir());
        let mut options = OpenOptions::new();
        options.write(true).create_new(true);
        let mut file = first.open(Path::new("hello.txt"), options).unwrap();
        file.write_all("你好\n".as_bytes()).unwrap();
        file.sync_all().unwrap();
        drop(file);
        first.rename(Path::new("hello.txt"), Path::new("renamed.txt")).unwrap();
        let mut options = OpenOptions::new(); options.read(true);
        let mut contents = String::new();
        first.open(Path::new("renamed.txt"), options).unwrap().read_to_string(&mut contents).unwrap();
        assert_eq!(contents, "你好\n");
        assert_eq!(first.metadata(Path::new("renamed.txt"), true).unwrap().len(), 7);
        let entries = first.read_dir(Path::new(".")).unwrap().collect::<io::Result<Vec<_>>>().unwrap();
        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].file_name(), "renamed.txt");
        first.remove_file(Path::new("renamed.txt")).unwrap();
        first.set_current_dir(Path::new("..")).unwrap();
        assert_eq!(first.current_dir().unwrap().as_os_str(), fixture.0.as_os_str());
        first.remove_dir(Path::new("work")).unwrap();
    }

    #[test]
    fn cleanup_preserves_replacement_directory_and_symlink() {
        for replace_with_symlink in [false, true] {
            let fixture = Fixture::new();
            let sandbox = EmbeddedFileSystem::new(&fixture.0).unwrap();
            let temporary = sandbox.temporary_dir().to_owned();
            let moved = fixture.0.join("renamed-temporary");
            let ordinary = fixture.0.join("ordinary");
            fs::write(temporary.join("owned.txt"), b"owned").unwrap();
            fs::create_dir(&ordinary).unwrap();
            fs::write(ordinary.join("keep.txt"), b"ordinary-project-data").unwrap();
            sandbox.rename(&temporary, &moved).unwrap();
            if replace_with_symlink {
                symlink(&ordinary, &temporary).unwrap();
            } else {
                sandbox.rename(&ordinary, &temporary).unwrap();
            }
            drop(sandbox);
            assert_eq!(fs::read(temporary.join("keep.txt")).unwrap(), b"ordinary-project-data");
            assert_eq!(fs::read(moved.join("owned.txt")).unwrap(), b"owned");
        }
    }

    #[test]
    fn refuses_parent_absolute_and_both_leaf_and_intermediate_symlink_escapes() {
        let fixture = Fixture::new();
        let project = fixture.0.join("project");
        let outside = fixture.0.join("outside");
        fs::create_dir(&project).unwrap();
        fs::create_dir(&outside).unwrap();
        fs::write(outside.join("secret.txt"), b"unchanged").unwrap();
        symlink(&outside, project.join("escape")).unwrap();
        symlink(outside.join("secret.txt"), project.join("leaf")).unwrap();
        let sandbox = EmbeddedFileSystem::new(&project).unwrap();
        for path in [Path::new("../outside/secret.txt"), outside.as_path(), Path::new("escape/secret.txt"), Path::new("leaf")] {
            let mut options = OpenOptions::new(); options.read(true).write(true).truncate(true);
            assert!(sandbox.open(path, options).is_err(), "allowed {}", path.display());
            assert!(sandbox.canonicalize(path).is_err(), "canonicalized {}", path.display());
        }
        assert!(sandbox.create_dir(Path::new("escape/new"), 0o700).is_err());
        assert!(sandbox.rename(Path::new("leaf"), Path::new("../moved")).is_err());
        assert!(sandbox.set_current_dir(Path::new("escape")).is_err());
        assert_eq!(fs::read(outside.join("secret.txt")).unwrap(), b"unchanged");
        assert!(!outside.join("new").exists());
        assert!(sandbox.metadata(Path::new("leaf"), false).unwrap().file_type().is_symlink());
        // Unlinking a symlink removes the project entry, never its target.
        sandbox.remove_file(Path::new("leaf")).unwrap();
        assert_eq!(fs::read(outside.join("secret.txt")).unwrap(), b"unchanged");
    }
}
