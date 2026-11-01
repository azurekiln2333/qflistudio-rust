// Decisive check that analysis does not enable `cfg(miri)`: the run path sets
// it, the analysis path must not, so this fixture is clean for analysis and an
// error for interpretation-mode compilation.
#[cfg(miri)]
compile_error!("analysis must not enable cfg(miri)");

fn main() {
    let value: u32 = 1 + 1;
    println!("{value}");
}
