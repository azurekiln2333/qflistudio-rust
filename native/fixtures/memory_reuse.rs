fn main() {
    for _ in 0..100 {
        let bytes = vec![0u8; 2 * 1024 * 1024];
        std::hint::black_box(bytes);
    }
    println!("reused");
}
