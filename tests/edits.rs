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

fn span_at(source: &str, text: &str) -> String {
    let start = source.find(text).unwrap();
    format!("{start}:{}", start + text.len())
}

#[test]
fn catalog_is_revision_bound_and_lists_only_source_expressions() {
    let fixture = Fixture::new();
    let source = format!("{PREFIX} var total = 3; total += x*2; return total; {SUFFIX}");
    fs::write(&fixture.source, &source).unwrap();
    let list = cli()
        .arg("expressions")
        .arg(&fixture.source)
        .args(["--function", "solve"])
        .output()
        .unwrap();
    let expected_nodes: Vec<_> = ["3", "x*2", "x", "2", "total"]
        .iter()
        .zip([
            source.find('3').unwrap(),
            source.find("x*2").unwrap(),
            source.find("x*2").unwrap(),
            source.find("x*2").unwrap() + 2,
            source.find("return total").unwrap() + 7,
        ])
        .map(|(text, start)| {
            format!(
                "{{\"start_byte\":{start},\"end_byte\":{},\"text\":\"{text}\"}}",
                start + text.len()
            )
        })
        .collect();
    assert_eq!(
        success(&list),
        format!(
            "{{\"schema\":\"gpp.expressions/1\",\"revision\":\"{}\",\"function\":\"solve\",\"start_byte\":{},\"end_byte\":{},\"expressions\":[{}]}}\n",
            fixture.revision(),
            source.find("fn solve").unwrap(),
            source.find("} // end").unwrap() + 1,
            expected_nodes.join(",")
        )
    );
    fs::write(
        &fixture.source,
        format!("{PREFIX} return missing; {SUFFIX}"),
    )
    .unwrap();
    let invalid = cli()
        .arg("expressions")
        .arg(&fixture.source)
        .args(["--function", "solve"])
        .output()
        .unwrap();
    assert!(!invalid.status.success());
    assert!(invalid.stdout.is_empty());
}

#[test]
fn selected_edit_preserves_bytes_grouping_and_revision() {
    let fixture = Fixture::new();
    let source = format!("{PREFIX}\r\n    return x * // α {{}}\r\n        x;\r\n{SUFFIX}");
    fs::write(&fixture.source, &source).unwrap();
    let last_x = source.find("x;\r\n").unwrap();
    let span = format!("{last_x}:{}", last_x + 1);
    let rev = fixture.revision();
    fs::write(&fixture.fragment, " // note\nx + 1 // trailing").unwrap();
    let cmd = || {
        let mut cmd = fixture.edit("--expr", &fixture.fragment);
        cmd.args(["--expect", &rev, "--at", &span]);
        cmd
    };
    let expected = format!("{}(x + 1){}", &source[..last_x], &source[last_x + 1..]);
    assert_eq!(success(&cmd().arg("--stdout").output().unwrap()), expected);
    assert_eq!(fs::read_to_string(&fixture.source).unwrap(), source);
    success(&cmd().output().unwrap());
    assert_eq!(fs::read_to_string(&fixture.source).unwrap(), expected);
    let evaluated = cli()
        .args(["run", "--interpreter"])
        .arg(&fixture.source)
        .output()
        .unwrap();
    assert_eq!(success(&evaluated), "6\n");
    let stale = cmd().output().unwrap();
    assert!(String::from_utf8_lossy(&stale.stderr).contains("stale revision"));
}

#[test]
fn source_context_drives_grouping_and_else_if_blocks() {
    let fixture = Fixture::new();
    for (body, old, raw, inserted) in [
        ("return x * 100;", "100", "3", "3"),
        ("return x - 100;", "100", "x - 1", "(x - 1)"),
        ("return(x);", "(x)", "x + 1", "(x + 1)"),
        (
            "return if x < 0 { 0 } else if x == 2 { 4 } else { 1 };",
            "if x == 2 { 4 } else { 1 }",
            "x + 1",
            "{x + 1}",
        ),
        (
            "return if x < 0 { 0 } else { if x == 2 { 4 } else { 1 } };",
            "if x == 2 { 4 } else { 1 }",
            "x + 1",
            "x + 1",
        ),
        ("var n = 2; n += x*3; return n;", "x*3", "x + 1", "x + 1"),
        ("return 100 + (x + 4);", "(x + 4)", "x + 1", "(x + 1)"),
    ] {
        let source = format!("{PREFIX} {body} {SUFFIX}");
        let span = span_at(&source, old);
        fs::write(&fixture.source, &source).unwrap();
        fs::write(&fixture.fragment, raw).unwrap();
        let output = fixture
            .edit("--expr", &fixture.fragment)
            .args(["--at", &span, "--stdout"])
            .output()
            .unwrap();
        assert_eq!(
            success(&output),
            source.replacen(old, inserted, 1),
            "{body}"
        );
    }
}

#[test]
fn arbitrary_ranges_cross_function_edits_and_invalid_fragments_are_rejected() {
    let fixture = Fixture::new();
    let source = format!("{PREFIX} var n = x; n += x + 1; return n; {SUFFIX}");
    fs::write(&fixture.source, &source).unwrap();
    let valid = span_at(&source, "x + 1");
    let utf8 = source.find('λ').unwrap() + 1;
    let lhs = source.find("n +=").unwrap();
    for (at, fragment, flag) in [
        (span_at(&source, "x +"), "x", "--expr"),
        (span_at(&source, "solve(2)"), "2", "--expr"),
        (span_at(&source, "n += x + 1"), "3", "--expr"),
        (format!("{lhs}:{}", lhs + 1), "x", "--expr"),
        (format!("{utf8}:{}", utf8 + 1), "0", "--expr"),
        ("9:9".into(), "0", "--expr"),
        ("3:2".into(), "0", "--expr"),
        (valid.clone(), "true", "--expr"),
        (valid.clone(), "0; return 42", "--expr"),
        (valid, "return 4;", "--body"),
    ] {
        fs::write(&fixture.fragment, fragment).unwrap();
        let rejected = fixture
            .edit(flag, &fixture.fragment)
            .args(["--at", &at, "--expect", &fixture.revision()])
            .output()
            .unwrap();
        assert!(!rejected.status.success(), "{at} {fragment}");
        assert!(rejected.stdout.is_empty());
        assert_eq!(fs::read_to_string(&fixture.source).unwrap(), source);
    }
}
