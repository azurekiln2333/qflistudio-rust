pub fn double(value: i32) -> i32 {
    value + value
}

pub fn total(values: &[i32]) -> i32 {
    values.iter().map(|value| double(*value)).sum()
}
