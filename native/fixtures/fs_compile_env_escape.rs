// Negative compiler fixture. The harness sets QFLI_SANDBOX_HOST_SECRET in its
// host process only. Guest compilation must not inherit that ambient value.
// This fixture must fail compilation, without printing the secret value.
const SECRET: &str = env!("QFLI_SANDBOX_HOST_SECRET");

fn main() {
    println!("{SECRET}");
}
