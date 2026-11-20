use std::process::Command;

#[test]
fn scalar_cli_conformance() {
    let status = Command::new("python3")
        .arg(concat!(env!("CARGO_MANIFEST_DIR"), "/tests/conformance.py"))
        .arg(env!("CARGO_BIN_EXE_gpp"))
        .status()
        .expect("CLI conformance tests require Python 3");
    assert!(status.success(), "scalar CLI conformance failed");
}
