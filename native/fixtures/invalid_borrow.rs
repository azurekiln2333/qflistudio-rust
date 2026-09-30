fn main() {
    let mut value = String::from("rust");
    let borrowed = &value;
    value.push('!');
    println!("{borrowed}");
}
