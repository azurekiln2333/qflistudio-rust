// Breakpoint fixture: a call on a known line, plus a nested function so that
// step-in and step-over produce visibly different stop positions.
//
// Line map (kept stable; the C test asserts these exact lines):
//   10 : value + value      (inside `double`, reached by step-in)
//   14 : let value = 21;
//   15 : let doubled = double(value);   (breakpoint line)
//   16 : assert_eq!(doubled, 42);
fn double(value: i32) -> i32 {
    value + value
}

fn main() {
    let value = 21;
    let doubled = double(value);
    assert_eq!(doubled, 42);
    println!("{doubled}");
}
