mod arithmetic {
    pub fn double<T>(value: T) -> T
    where
        T: Copy + std::ops::Add<Output = T>,
    {
        value + value
    }
}

fn main() {
    let values = vec![1, 2, 3];
    let borrowed = &values;
    let total: i32 = borrowed.iter().map(|v| arithmetic::double(*v)).sum();
    assert_eq!(total, 12);
    println!("total={total}");
    eprintln!("items={}", borrowed.len());
}
