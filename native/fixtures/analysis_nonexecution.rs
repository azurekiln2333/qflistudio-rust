// Valid program whose only observable behaviour requires execution.
// Analysis must report no diagnostics and must not run it: if it did, the
// interpreter would write EXECUTED to stdout and exit with status 7.
fn main() {
    println!("EXECUTED");
    std::process::exit(7);
}
