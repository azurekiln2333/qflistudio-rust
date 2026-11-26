// 062 answer: explicit `ref` binding
fn first_name(people: &[(String, u32)]) -> Option<&str> {
    match people.first() {
        // 显式 ref：name / age 都是引用
        Some((ref name, ref age)) => {
            let _ = age;
            Some(name.as_str())
        }
        None => None,
    }
}

fn main() {
    let people = vec![(String::from("Ada"), 36), (String::from("Alan"), 41)];
    println!("{:?}", first_name(&people));
    println!("{:?}", first_name(&[]));
}
