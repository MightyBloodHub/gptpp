use std::process::Command;

#[test]
fn checked_library_and_reservation_clients() {
    let status = Command::new("python3")
        .arg(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/examples/reservations/check.py"
        ))
        .args(["--gpp", env!("CARGO_BIN_EXE_gpp")])
        .status()
        .expect("reservation integration tests require Python 3");
    assert!(status.success());
}
