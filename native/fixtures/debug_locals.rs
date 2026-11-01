// Locals fixture: exercises every value state the adapter can report.
//
// Line map (kept stable; the C test asserts these exact lines):
//   12 : let small = -1i8;        (negative signed scalar)
//   13 : let letter = 'A';        (char)
//   14 : let flag = true;         (bool)
//   15 : let pair = (1, 2);       (aggregate -> unsupported, never guessed)
//   16 : let text = "hi";         (reference -> unsupported)
//   17 : let later;               (declared, not yet initialized)
//   18 : later = small as i32;    (assigned here)
fn main() {
    let small = -1i8;
    let letter = 'A';
    let flag = true;
    let pair = (1, 2);
    let text = "hi";
    let later;
    later = small as i32;
    println!("{later}{letter}{flag}{text}{:?}", pair);
}
