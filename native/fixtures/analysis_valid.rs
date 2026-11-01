mod arithmetic {
    pub fn double(value: i32) -> i32 {
        value + value
    }
}

fn main() {
    let values = [1, 2, 3];
    let total: i32 = values.iter().map(|value| arithmetic::double(*value)).sum();
    assert_eq!(total, 12);
    println!("total={total}");
}
