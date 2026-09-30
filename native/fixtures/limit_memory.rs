fn main() {
    let bytes = Vec::<u8>::with_capacity(128 * 1024 * 1024);
    std::hint::black_box(bytes);
}
