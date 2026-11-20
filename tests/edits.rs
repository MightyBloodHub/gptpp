use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::sync::atomic::{AtomicU64, Ordering};

// Braces inside comments and an effect set precede the selected body.
const PREFIX: &str = "module m;\r\n// λ {}\r\nfn solve(x: I64) -> I64 !{} // }\r\n{";
const SUFFIX: &str = "} // end\r\npub fn main() -> I64 !{} { return solve(2); }\r\n";

struct Fixture {
    dir: PathBuf,
    source: PathBuf,
    fragment: PathBuf,
}

impl Fixture {
    fn new() -> Self {
        static SERIAL: AtomicU64 = AtomicU64::new(0);
        let dir = loop {
            let id = SERIAL.fetch_add(1, Ordering::Relaxed);
            let dir =
                std::env::temp_dir().join(format!("gpp-edit-test-{}-{id}", std::process::id()));
            match fs::create_dir(&dir) {
                Ok(()) => break dir,
                Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => continue,
                Err(e) => panic!("{e}"),
            }
        };
        let source = dir.join("demo.gpp");
        fs::write(&source, format!("{PREFIX} return x; {SUFFIX}")).unwrap();
        let fragment = dir.join("fragment");
        Self {
            dir,
            source,
            fragment,
        }
    }

    fn revision(&self) -> String {
        let output = cli().arg("revision").arg(&self.source).output().unwrap();
        success(&output).trim().to_owned()
    }

    fn edit(&self, kind: &str, fragment: &Path) -> Command {
        let mut cmd = cli();
        cmd.arg("edit")
            .arg(&self.source)
            .args(["--function", "solve", kind])
            .arg(fragment);
        cmd
    }

    fn preview(&self, kind: &str, fragment: &str) -> Output {
        fs::write(&self.fragment, fragment).unwrap();
        self.edit(kind, &self.fragment)
            .arg("--stdout")
            .output()
            .unwrap()
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.dir);
    }
}

fn cli() -> Command {
    Command::new(env!("CARGO_BIN_EXE_gpp"))
}

fn success(output: &Output) -> &str {
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    std::str::from_utf8(&output.stdout).unwrap()
}

#[test]
fn previews_replace_only_the_selected_body() {
    let fixture = Fixture::new();
    let original = fs::read(&fixture.source).unwrap();
    for (kind, frag, contents) in [
        ("--expr", "x + 3 // sample", "    return x + 3; // sample"),
        ("--body", "{ return x*2; }", " return x*2; "),
        ("--body", "return x+2; // }", "return x+2; // }"),
    ] {
        let shown = fixture.preview(kind, frag);
        assert_eq!(
            success(&shown),
            format!("{PREFIX}\r\n{contents}\r\n{SUFFIX}")
        );
        assert_eq!(fs::read(&fixture.source).unwrap(), original);
    }
    assert_eq!(fs::read_dir(&fixture.dir).unwrap().count(), 2);
}

#[test]
fn rejects_escape_attempts_and_checks_full_candidate_before_commit() {
    let fixture = Fixture::new();
    let original = fs::read(&fixture.source).unwrap();
    let base = fixture.revision();
    for (kind, frag) in [
        ("--expr", "0; return 5"),
        ("--expr", "true"),
        ("--expr", "missing(1)"),
        (
            "--body",
            "{ return x; } fn surprise() -> I64 !{} { return 2; }",
        ),
        ("--body", "return x; } fn replace() -> I64 !{} { return 8;"),
        ("--body", "let x = 1;"),
        ("--body", "if false { return 2; }"),
    ] {
        fs::write(&fixture.fragment, frag).unwrap();
        let output = fixture
            .edit(kind, &fixture.fragment)
            .args(["--expect", &base])
            .output()
            .unwrap();
        assert!(!output.status.success(), "{frag}");
        assert!(output.stdout.is_empty());
        assert_eq!(fs::read(&fixture.source).unwrap(), original);
    }
}

#[test]
fn missing_or_ambiguous_targets_reject_an_edit() {
    let fixture = Fixture::new();
    for declaration in ["fn other", "fn solve"] {
        let fragment = if declaration == "fn other" {
            "module m; fn other() -> I64 !{} { return 1; }".into()
        } else {
            format!("{PREFIX} return x; {SUFFIX} fn solve() -> I64 !{{}} {{ return 3; }}")
        };
        fs::write(&fixture.source, &fragment).unwrap();
        let out = fixture.preview("--expr", "0");
        assert!(!out.status.success());
        assert!(out.stdout.is_empty());
        assert_eq!(fs::read_to_string(&fixture.source).unwrap(), fragment);
    }
}

#[test]
fn revisions_guard_commits_and_remain_optional_for_preview() {
    let fixture = Fixture::new();
    fs::write(&fixture.source, "abc").unwrap();
    assert_eq!(
        fixture.revision(),
        "sha256:ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    );
    // Repair a source which already has a type error outside the syntax parser.
    fs::write(&fixture.source, format!("{PREFIX} return false; {SUFFIX}")).unwrap();
    let base = fixture.revision();
    fs::write(&fixture.fragment, "x * 2").unwrap();
    let cmd = || fixture.edit("--expr", &fixture.fragment);
    assert!(!cmd().output().unwrap().status.success());
    let preview = cmd()
        .args(["--expect", &base, "--stdout"])
        .output()
        .unwrap();
    let proposed = success(&preview);
    success(&cmd().args(["--expect", &base]).output().unwrap());
    assert_eq!(fs::read_to_string(&fixture.source).unwrap(), proposed);
    assert_ne!(fixture.revision(), base);
    for preview in [false, true] {
        let mut retry = cmd();
        retry.args(["--expect", &base]);
        if preview {
            retry.arg("--stdout");
        }
        let stale = retry.output().unwrap();
        assert!(!stale.status.success());
        assert!(String::from_utf8_lossy(&stale.stderr).contains("stale revision"));
        assert_eq!(fs::read_to_string(&fixture.source).unwrap(), proposed);
    }
}

#[test]
fn concurrent_commits_allow_exactly_one_writer_per_revision() {
    let fixture = Fixture::new();
    let base = fixture.revision();
    let second = fixture.dir.join("another");
    fs::write(&fixture.fragment, "10").unwrap();
    fs::write(&second, "20").unwrap();
    let children: Vec<_> = [&fixture.fragment, &second]
        .into_iter()
        .map(|path| {
            fixture
                .edit("--expr", path)
                .args(["--expect", &base])
                .stdout(std::process::Stdio::piped())
                .stderr(std::process::Stdio::piped())
                .spawn()
                .unwrap()
        })
        .collect();
    let results: Vec<_> = children
        .into_iter()
        .map(|c| c.wait_with_output().unwrap())
        .collect();
    assert_eq!(results.iter().filter(|o| o.status.success()).count(), 1);
    let rejected = results.iter().find(|o| !o.status.success()).unwrap();
    assert!(String::from_utf8_lossy(&rejected.stderr).contains("stale revision"));
    let run = cli()
        .args(["run", "--interpreter"])
        .arg(&fixture.source)
        .output()
        .unwrap();
    assert!(matches!(success(&run), "10\n" | "20\n"));
}

#[cfg(unix)]
#[test]
fn a_symlink_preserves_its_target_and_file_permissions() {
    use std::os::unix::fs::{PermissionsExt, symlink};
    let fixture = Fixture::new();
    let alias = fixture.dir.join("alias.gpp");
    symlink(&fixture.source, &alias).unwrap();
    fs::set_permissions(&fixture.source, fs::Permissions::from_mode(0o640)).unwrap();
    fs::write(&fixture.fragment, "100").unwrap();
    let run = cli()
        .arg("edit")
        .arg(&alias)
        .args(["--function", "solve", "--expr"])
        .arg(&fixture.fragment)
        .args(["--expect", &fixture.revision()])
        .output()
        .unwrap();
    success(&run);
    assert!(alias.is_symlink());
    assert_eq!(
        fs::metadata(&fixture.source).unwrap().permissions().mode() & 0o777,
        0o640
    );
    assert!(
        fs::read_to_string(&fixture.source)
            .unwrap()
            .contains("return 100;")
    );
}
