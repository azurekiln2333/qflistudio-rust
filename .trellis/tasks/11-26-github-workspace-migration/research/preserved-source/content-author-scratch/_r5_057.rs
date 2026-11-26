// 057 answer: guards (@ binding) AND `if` guards both used
fn bucket(score: u32) -> &'static str {
    match score {
        s @ 0..=59 => {
            let _ = s;
            "F"
        }
        s @ 60..=69 if s % 10 == 0 => {
            let _ = s;
            "D(整十)"
        }
        s @ 60..=69 => {
            let _ = s;
            "D"
        }
        s @ 70..=79 if s % 10 == 0 => {
            let _ = s;
            "C(整十)"
        }
        s @ 70..=79 => {
            let _ = s;
            "C"
        }
        s @ 80..=89 if s % 10 == 0 => {
            let _ = s;
            "B(整十)"
        }
        s @ 80..=89 => {
            let _ = s;
            "B"
        }
        s @ 90..=100 if s % 10 == 0 => {
            let _ = s;
            "A(整十)"
        }
        s @ 90..=100 => {
            let _ = s;
            "A"
        }
        _ => "invalid",
    }
}

fn main() {
    for s in [45, 72, 70, 60, 95, 90, 120] {
        println!("{} -> {}", s, bucket(s));
    }
}
