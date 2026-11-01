// Type error fixture: a debug session must refuse to run this program and
// report the compile error as an error pause instead of a silent stop.
//
// Line map (kept stable; the C test asserts the diagnostic code only):
//    7 : let value: u32 = "not a number";
fn main() {
    let value: u32 = "not a number";
    println!("{value}");
}
