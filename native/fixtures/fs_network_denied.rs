// Negative fixture: expect isolation failure at the socket shim. This program
// must never finish successfully or initiate a host socket/connection.
fn main() {
    let _ = std::net::TcpStream::connect("127.0.0.1:9");
    panic!("embedded filesystem capability unexpectedly permitted a socket");
}
