use std::process::Command;

#[test]
fn rebooking_preserves_capacity_in_both_clients() {
    let output = Command::new("python3")
        .arg(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/examples/reservations/reopen_demo.py"
        ))
        .args(["--gpp", env!("CARGO_BIN_EXE_gpp")])
        .output()
        .expect("reservation rebooking tests require Python 3");
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
}
