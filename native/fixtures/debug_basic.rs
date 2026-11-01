// Stepping fixture with fixed line numbers and deterministic scalar locals.
//
// Line map (kept stable; the C test asserts these exact lines):
//    9 : let a = 1;
//   10 : let b = 2;
//   11 : let sum = a + b;
//   12 : println!("{sum}");
fn main() {
    let a = 1;
    let b = 2;
    let sum = a + b;
    println!("{sum}");
}
