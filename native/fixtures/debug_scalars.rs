// Every binding stays live at SCALAR_BREAKPOINT. High unsigned bits, an
// address-taken local and escaped chars catch scalar rendering regressions.
fn main() {
    let high8 = u8::MAX;
    let high64 = u64::MAX;
    let high128 = u128::MAX;
    let signed_min = i128::MIN;
    let floating = 1.5f32;
    let negative_zero = -0.0f64;
    let escaped = '\n';
    let emoji = '😀';
    let borrowed = 42u64;
    let address = &borrowed;
    let check = high8 as i32; // SCALAR_BREAKPOINT
    println!("{high8} {high64} {high128} {signed_min} {floating} {negative_zero} {escaped:?} {emoji:?} {address} {check}");
}
