//! Checked single-function edits against an exact source revision.
use crate::syntax::{Expr, ExprKind, ExprSite, Function, Module, Span, Stmt, StmtKind};
use crate::{check, diagnostic, json_string, syntax, verify};
use std::ffi::OsString;
use std::fs::{self, File, OpenOptions};
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

pub const USAGE: &str = "\
  gpp revision FILE
  gpp expressions FILE --function NAME
  gpp edit FILE --function NAME ([--at START:END] --expr|--body) FRAGMENT_FILE (--expect REVISION|--stdout [--expect REVISION]) [--verify [--budget N]]

Use gpp revision FILE to obtain the sha256:... token for an in-place edit.
--stdout writes the checked candidate to stdout and leaves FILE untouched.";

pub enum Request {
    Revision(PathBuf),
    Expressions(PathBuf, String),
    Replace(Edit),
}

pub struct Edit {
    file: PathBuf,
    function: String,
    fragment: PathBuf,
    kind: FragmentKind,
    at: Option<Span>,
    expected: Option<String>,
    preview: bool,
    verify_budget: Option<u64>,
}

#[derive(Clone, Copy)]
enum FragmentKind {
    Expression,
    Body,
}

pub fn parse(args: impl IntoIterator<Item = OsString>) -> Result<Request, String> {
    let mut args = args.into_iter();
    let command = args.next().ok_or(USAGE)?;
    let file = PathBuf::from(args.next().ok_or(USAGE)?);
    if command == "revision" {
        if args.next().is_some() {
            return Err(USAGE.into());
        }
        return Ok(Request::Revision(file));
    }
    if command == "expressions" {
        if args.next().as_deref() != Some("--function".as_ref()) {
            return Err(USAGE.into());
        }
        let name = args
            .next()
            .and_then(|s| s.into_string().ok())
            .ok_or(USAGE)?;
        if args.next().is_some() {
            return Err(USAGE.into());
        }
        return Ok(Request::Expressions(file, name));
    }
    let mut at = None;
    let mut function = None;
    let mut fragment = None;
    let mut expected = None;
    let mut preview = false;
    let mut verify = false;
    let mut budget = None;
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
            Some("--at") if at.is_none() => {
                let raw = args
                    .next()
                    .and_then(|s| s.into_string().ok())
                    .ok_or(USAGE)?;
                at = Some(parse_span(&raw).ok_or("--at requires a nonempty START:END byte range")?);
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
            Some("--verify") if !verify => verify = true,
            Some("--budget") if budget.is_none() => {
                budget = Some(
                    args.next()
                        .and_then(|n| n.to_str()?.parse::<u64>().ok())
                        .ok_or("--budget needs a nonnegative integer")?,
                );
            }
            _ => return Err(USAGE.into()),
        }
    }
    if !preview && expected.is_none() {
        return Err(
            "in-place edits require --expect; obtain the base revision with gpp revision FILE"
                .into(),
        );
    }
    if budget.is_some() && !verify {
        return Err("edit --budget requires --verify".into());
    }
    let (kind, fragment) = fragment.ok_or(USAGE)?;
    if at.is_some() && matches!(kind, FragmentKind::Body) {
        return Err("--at selects an expression and requires --expr".into());
    }
    Ok(Request::Replace(Edit {
        file,
        function: function.ok_or(USAGE)?,
        fragment,
        kind,
        at,
        expected,
        preview,
        verify_budget: verify.then(|| budget.unwrap_or(verify::DEFAULT_BUDGET)),
    }))
}

fn parse_span(raw: &str) -> Option<Span> {
    let (start, end) = raw.split_once(':')?;
    if !start.bytes().chain(end.bytes()).all(|c| c.is_ascii_digit()) {
        return None;
    }
    let span = Span {
        start: start.parse().ok()?,
        end: end.parse().ok()?,
    };
    (span.start < span.end).then_some(span)
}

fn valid_digest(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
}

// Use the host's SHA-256 implementation. Hash the bytes that were actually
// parsed rather than having the utility re-open a possibly changed file.
pub(crate) fn revision(bytes: &[u8]) -> Result<String, String> {
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

pub(crate) fn target<'a>(module: &'a Module, name: &str) -> Result<&'a Function, String> {
    let mut matches = module.functions.iter().filter(|f| f.name == name);
    let function = matches
        .next()
        .ok_or_else(|| format!("unknown function '{name}'"))?;
    if matches.next().is_some() {
        return Err(format!("ambiguous function '{name}'"));
    }
    Ok(function)
}

pub(crate) fn expressions(function: &Function) -> Vec<&Expr> {
    fn walk_expr<'a>(expr: &'a Expr, nodes: &mut Vec<&'a Expr>) {
        if expr.site != ExprSite::Synthetic {
            nodes.push(expr);
        }
        match &expr.kind {
            ExprKind::If { cond, yes, no } => {
                for child in [cond, yes, no] {
                    walk_expr(child, nodes);
                }
            }
            ExprKind::Binary(_, lhs, rhs) => {
                walk_expr(lhs, nodes);
                walk_expr(rhs, nodes);
            }
            ExprKind::Unary(_, arg) | ExprKind::AsI64(arg) | ExprKind::Field(arg, _) => {
                walk_expr(arg, nodes)
            }
            ExprKind::Call(_, args) => {
                for arg in args {
                    walk_expr(arg, nodes);
                }
            }
            ExprKind::Int(_)
            | ExprKind::Bool(_)
            | ExprKind::Name(_)
            | ExprKind::Variant(..)
            | ExprKind::Hole(..)
            | ExprKind::Unit => {}
        }
    }

    fn walk_body<'a>(stmts: &'a [Stmt], nodes: &mut Vec<&'a Expr>) {
        for stmt in stmts {
            match &stmt.kind {
                StmtKind::Bind { value, .. }
                | StmtKind::Assign { value, .. }
                | StmtKind::Expr(value)
                | StmtKind::Return(value) => walk_expr(value, nodes),
                StmtKind::If {
                    cond,
                    then_body,
                    else_body,
                } => {
                    walk_expr(cond, nodes);
                    walk_body(then_body, nodes);
                    walk_body(else_body, nodes);
                }
                StmtKind::While { cond, body } => {
                    walk_expr(cond, nodes);
                    walk_body(body, nodes);
                }
            }
        }
    }

    let mut nodes = Vec::new();
    walk_body(&function.body, &mut nodes);
    nodes
}

fn list_expressions(path: &Path, name: &str) -> Result<(), String> {
    let source = fs::read_to_string(path).map_err(|e| format!("{}: {e}", path.display()))?;
    let report = |err| diagnostic(path, &source, err, false);
    let module = syntax::parse(&source).map_err(report)?;
    let function = target(&module, name)?;
    check::check(&module).map_err(report)?;
    let nodes = expressions(function);
    let revision = revision(source.as_bytes())?;
    let stdout = io::stdout();
    let mut out = io::BufWriter::new(stdout.lock());
    let mut emit = || -> io::Result<()> {
        write!(
            out,
            "{{\"schema\":\"gpp.expressions/1\",\"revision\":{},\"function\":{},\"start_byte\":{},\"end_byte\":{},\"expressions\":[",
            json_string(&revision),
            json_string(name),
            function.span.start,
            function.span.end
        )?;
        for (i, expr) in nodes.iter().enumerate() {
            if i != 0 {
                write!(out, ",")?;
            }
            let Span { start, end } = expr.span;
            write!(
                out,
                "{{\"start_byte\":{start},\"end_byte\":{end},\"text\":{}}}",
                json_string(&source[start..end])
            )?;
        }
        writeln!(out, "]}}")?;
        out.flush()
    };
    emit().map_err(|err| err.to_string())
}

pub(crate) fn replace_node(
    path: &Path,
    fragment_path: &Path,
    source: &str,
    function: &Function,
    span: Span,
    fragment: &str,
) -> Result<(String, Module), String> {
    let selected = expressions(function)
        .into_iter()
        .find(|expr| expr.span == span)
        .ok_or_else(|| {
            format!(
                "range {}:{} does not select an expression in '{}'",
                span.start, span.end, function.name
            )
        })?;
    let frag = syntax::expression_span(fragment)
        .map_err(|err| diagnostic(fragment_path, fragment, err, false))?;
    let text = &fragment[frag.start..frag.end];
    let splice = |value: &str| {
        let mut result = source.to_owned();
        result.replace_range(span.start..span.end, value);
        result
    };

    // Preserve the author's spelling when the inserted bytes still form exactly
    // one AST node. This detects both precedence changes and merged tokens.
    let bare = splice(text);
    if let Ok(module) = syntax::parse(&bare) {
        let replacement = Span {
            start: span.start,
            end: span.start + text.len(),
        };
        if expressions(target(&module, &function.name)?)
            .iter()
            .any(|node| node.span == replacement)
        {
            check::check(&module).map_err(|err| diagnostic(path, &bare, err, false))?;
            return Ok((bare, module));
        }
    }
    let grouped = if selected.site == ExprSite::ElseIf {
        format!("{{{text}}}")
    } else {
        format!("({text})")
    };
    checked_source(path, splice(&grouped))
}

fn candidate(edit: &Edit, source: &str, fragment: &str) -> Result<(String, Module), String> {
    let module = syntax::parse(source).map_err(|e| diagnostic(&edit.file, source, e, false))?;
    let function = target(&module, &edit.function)?;
    if let Some(span) = edit.at {
        return replace_node(&edit.file, &edit.fragment, source, function, span, fragment);
    }
    let fragment_error = |e| diagnostic(&edit.fragment, fragment, e, false);
    let newline = if source.contains("\r\n") {
        "\r\n"
    } else {
        "\n"
    };
    let contents = match edit.kind {
        FragmentKind::Expression => {
            let end = syntax::expression_span(fragment)
                .map_err(fragment_error)?
                .end;
            // A trailing line comment must not consume the return's semicolon.
            format!("    return {};{}", &fragment[..end], &fragment[end..])
        }
        FragmentKind::Body => syntax::body_fragment(fragment, &module)
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
    checked_source(&edit.file, result)
}

fn checked_source(path: &Path, result: String) -> Result<(String, Module), String> {
    let report = |e| diagnostic(path, &result, e, false);
    let checked = syntax::parse(&result).map_err(report)?;
    check::check(&checked).map_err(report)?;
    Ok((result, checked))
}

pub fn execute(request: Request) -> Result<(), String> {
    match request {
        Request::Revision(path) => {
            let bytes = fs::read(&path).map_err(|e| format!("{}: {e}", path.display()))?;
            println!("{}", revision(&bytes)?);
            Ok(())
        }
        Request::Expressions(path, name) => list_expressions(&path, &name),
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
    let (result, module) = candidate(&edit, &source, &fragment)?;
    if let Some(budget) = edit.verify_budget {
        let mut report = Vec::new();
        let revision = revision(result.as_bytes())?;
        if verify::verify_module(&module, &revision, None, budget, &mut report)? != 0 {
            return Err(String::from_utf8(report)
                .map_err(|e| e.to_string())?
                .trim_end()
                .to_owned());
        }
    }
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
