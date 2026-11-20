//! Checked single-function edits against an exact source revision.
use crate::{check, diagnostic, syntax};
use std::ffi::OsString;
use std::fs::{self, File, OpenOptions};
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

pub const USAGE: &str = "\
  gpp revision FILE
  gpp edit FILE --function NAME (--expr|--body) FRAGMENT_FILE (--expect REVISION|--stdout [--expect REVISION])

Use gpp revision FILE to obtain the sha256:... token for an in-place edit.
--stdout writes the checked candidate to stdout and leaves FILE untouched.";

pub enum Request {
    Revision(PathBuf),
    Replace(Edit),
}

pub struct Edit {
    file: PathBuf,
    function: String,
    fragment: PathBuf,
    kind: FragmentKind,
    expected: Option<String>,
    preview: bool,
}

#[derive(Clone, Copy)]
enum FragmentKind {
    Expression,
    Body,
}

pub fn parse(args: impl IntoIterator<Item = OsString>) -> Result<Request, String> {
    let mut args = args.into_iter();
    let revision = args.next().as_deref() == Some("revision".as_ref());
    let file = PathBuf::from(args.next().ok_or(USAGE)?);
    if revision {
        if args.next().is_some() {
            return Err(USAGE.into());
        }
        return Ok(Request::Revision(file));
    }
    let mut function = None;
    let mut fragment = None;
    let mut expected = None;
    let mut preview = false;
    while let Some(option) = args.next() {
        match option.to_str() {
            Some("--function") if function.is_none() => {
                function = Some(
                    args.next()
                        .and_then(|s| s.into_string().ok())
                        .ok_or(USAGE)?,
                );
            }
            Some(kind @ ("--body" | "--expr")) if fragment.is_none() => {
                let kind = if kind == "--expr" {
                    FragmentKind::Expression
                } else {
                    FragmentKind::Body
                };
                fragment = Some((kind, PathBuf::from(args.next().ok_or(USAGE)?)));
            }
            Some("--expect") if expected.is_none() => {
                let rev = args
                    .next()
                    .and_then(|s| s.into_string().ok())
                    .ok_or(USAGE)?;
                if !rev.strip_prefix("sha256:").is_some_and(valid_digest) {
                    return Err(
                        "invalid --expect revision; obtain it with gpp revision FILE".into(),
                    );
                }
                expected = Some(rev);
            }
            Some("--stdout") if !preview => preview = true,
            _ => return Err(USAGE.into()),
        }
    }
    if !preview && expected.is_none() {
        return Err(
            "in-place edits require --expect; obtain the base revision with gpp revision FILE"
                .into(),
        );
    }
    let (kind, fragment) = fragment.ok_or(USAGE)?;
    Ok(Request::Replace(Edit {
        file,
        function: function.ok_or(USAGE)?,
        fragment,
        kind,
        expected,
        preview,
    }))
}

fn valid_digest(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
}

// Use the host's SHA-256 implementation. Hash the bytes that were actually
// parsed rather than having the utility re-open a possibly changed file.
fn revision(bytes: &[u8]) -> Result<String, String> {
    for (program, args) in [("sha256sum", &[][..]), ("shasum", &["-a", "256"][..])] {
        let mut child = match Command::new(program)
            .args(args)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
        {
            Ok(child) => child,
            Err(e) if e.kind() == io::ErrorKind::NotFound => continue,
            Err(e) => return Err(format!("cannot start {program}: {e}")),
        };
        let written = child.stdin.take().unwrap().write_all(bytes);
        let output = child.wait_with_output().map_err(|e| e.to_string())?;
        if !output.status.success() {
            return Err(format!(
                "{program} failed: {}",
                String::from_utf8_lossy(&output.stderr).trim()
            ));
        }
        written.map_err(|e| format!("cannot hash source: {e}"))?;
        let text = String::from_utf8(output.stdout).map_err(|e| e.to_string())?;
        let hash = text
            .split_ascii_whitespace()
            .next()
            .filter(|s| valid_digest(s))
            .ok_or_else(|| format!("invalid SHA-256 result from {program}"))?;
        return Ok(format!("sha256:{hash}"));
    }
    Err("computing revisions requires sha256sum or shasum on PATH".into())
}

fn candidate(edit: &Edit, source: &str, fragment: &str) -> Result<String, String> {
    let module = syntax::parse(source).map_err(|e| diagnostic(&edit.file, source, e, false))?;
    let mut matches = module.functions.iter().filter(|f| f.name == edit.function);
    let function = matches
        .next()
        .ok_or_else(|| format!("unknown function '{}'", edit.function))?;
    if matches.next().is_some() {
        return Err(format!("ambiguous function '{}'", edit.function));
    }
    let fragment_error = |e| diagnostic(&edit.fragment, fragment, e, false);
    let newline = if source.contains("\r\n") {
        "\r\n"
    } else {
        "\n"
    };
    let contents = match edit.kind {
        FragmentKind::Expression => {
            let end = syntax::expression_end(fragment).map_err(fragment_error)?;
            // A trailing line comment must not consume the return's semicolon.
            format!("    return {};{}", &fragment[..end], &fragment[end..])
        }
        FragmentKind::Body => syntax::body_fragment(fragment)
            .map_err(fragment_error)?
            .to_owned(),
    };
    let span = function.body_span;
    let mut result =
        String::with_capacity(source.len() - (span.end - span.start) + contents.len() + 6);
    result.push_str(&source[..span.start + 1]);
    if !contents.starts_with(['\r', '\n']) {
        result.push_str(newline);
    }
    result.push_str(&contents);
    if !contents.ends_with(['\r', '\n']) {
        result.push_str(newline);
    }
    result.push_str(&source[span.end - 1..]);
    let report = |e| diagnostic(&edit.file, &result, e, false);
    let checked = syntax::parse(&result).map_err(report)?;
    check::check(&checked).map_err(report)?;
    Ok(result)
}

pub fn execute(request: Request) -> Result<(), String> {
    match request {
        Request::Revision(path) => {
            let bytes = fs::read(&path).map_err(|e| format!("{}: {e}", path.display()))?;
            println!("{}", revision(&bytes)?);
            Ok(())
        }
        Request::Replace(edit) => replace(edit),
    }
}

fn replace(edit: Edit) -> Result<(), String> {
    // Resolve symlinks once so a commit updates the source and preserves its link.
    let path = edit
        .file
        .canonicalize()
        .map_err(|e| format!("{}: {e}", edit.file.display()))?;
    let parent = path.parent().ok_or("source has no parent directory")?;
    // A lock on the source inode would become obsolete after rename. Lock its
    // containing directory, which persists across atomic source replacements.
    let directory = if edit.preview {
        None
    } else {
        let directory = File::open(parent).map_err(|e| e.to_string())?;
        directory
            .lock()
            .map_err(|e| format!("cannot lock source directory: {e}"))?;
        Some(directory)
    };
    let source = fs::read_to_string(&path).map_err(|e| format!("{}: {e}", path.display()))?;
    if let Some(expected) = &edit.expected {
        let actual = revision(source.as_bytes())?;
        if expected != &actual {
            return Err(format!(
                "stale revision: expected {expected}, found {actual}"
            ));
        }
    }
    let fragment = fs::read_to_string(&edit.fragment)
        .map_err(|e| format!("{}: {e}", edit.fragment.display()))?;
    let result = candidate(&edit, &source, &fragment)?;
    if let Some(directory) = directory {
        commit(&path, parent, &source, &result)?;
        directory
            .sync_all()
            .map_err(|e| format!("edit committed but directory sync failed: {e}"))?;
    } else {
        io::stdout()
            .lock()
            .write_all(result.as_bytes())
            .map_err(|e| e.to_string())?;
    }
    Ok(())
}

fn commit(path: &Path, parent: &Path, source: &str, result: &str) -> Result<(), String> {
    // Check write access to the source itself before replacing its directory entry.
    let current = OpenOptions::new()
        .write(true)
        .open(path)
        .map_err(|e| e.to_string())?;
    let metadata = current.metadata().map_err(|e| e.to_string())?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt;
        if metadata.nlink() != 1 {
            return Err("cannot atomically replace a source with multiple hard links".into());
        }
    }
    // An atomic rename on the same filesystem leaves the old file intact if
    // staging or validation fails. create_new never truncates an existing path.
    let mut options = OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut serial: u64 = 0;
    let (staged, mut file) = loop {
        let temp = parent.join(format!(".gpp-edit-{}-{serial}", std::process::id()));
        match options.open(&temp) {
            Ok(file) => break (temp, file),
            Err(e) if e.kind() == io::ErrorKind::AlreadyExists => serial += 1,
            Err(e) => return Err(format!("cannot create staged source: {e}")),
        }
    };
    let install = (|| -> io::Result<()> {
        file.write_all(result.as_bytes())?;
        file.set_permissions(metadata.permissions())?;
        file.sync_all()?;
        if fs::read(path)? != source.as_bytes() {
            return Err(io::Error::other("source changed while checking the edit"));
        }
        fs::rename(&staged, path)
    })();
    if let Err(e) = install {
        let _ = fs::remove_file(&staged);
        return Err(format!("cannot install edit: {e}"));
    }
    Ok(())
}
