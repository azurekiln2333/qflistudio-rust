// Negative compiler fixture. Harness must copy this to <project>/main.rs and
// create <project>/../qfli-outside-sentinel.txt containing "outside-unchanged".
// A project-restricted compiler file loader must reject this before execution.
// A mere "file absent" diagnostic does not prove the restriction.
const OUTSIDE: &str = include_str!("../qfli-outside-sentinel.txt");

fn main() {
    println!("{OUTSIDE}");
}
