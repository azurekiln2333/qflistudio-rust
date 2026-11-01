fn main() {
    let retained: &'static str = Box::leak(String::from("retained").into_boxed_str());
    println!("{retained}");
}
