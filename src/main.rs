mod check;
mod complete;
mod edit;
mod guided_search;
mod holes;
mod interpreter;
mod ir;
mod library;
mod minimal_search;
mod native;
mod probe;
mod symbolic;
mod syntax;
mod trace;
mod verify;

use std::env;
use std::ffi::OsString;
use std::fmt::Write as _;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::ExitCode;

const USAGE: &str = "\
Usage:
  gpp check [--format=json] FILE
  gpp run --interpreter [--fuel N] FILE
  gpp build [-O0|-O2] [-o EXECUTABLE] FILE
  gpp holes FILE [--function NAME] [--format=json]
  gpp complete FILE --hole NAME [--fill EXPRESSION_FILE] [--search hybrid|grammar|minimum] [--limit N] [--budget N] [--expect REVISION] [--stdout]
  gpp prove FILE [--contract NAME] [--timeout-ms N]
  gpp library FILE (-o OUTPUT|--header) [-O0|-O2]
  gpp ast FILE
  gpp emit-llvm FILE
  gpp verify FILE [--contract NAME] [--budget N] [--format=json]
  gpp trace FILE --function TARGET (--call ENTRY|--contract NAME) [ARG ...] [--fuel N]
  gpp probe FILE --function TARGET --expect REVISION (--cases CASES.tsv [--wrapped]|--contract-cases CASES.tsv) [--filter]";

#[derive(PartialEq)]
enum Action {
    Check,
    Run,
    Build,
    Ast,
    EmitLlvm,
}

struct Options {
    action: Action,
    file: PathBuf,
    output: Option<PathBuf>,
    json: bool,
    optimize: bool,
    fuel: u64,
}

impl Options {
    fn parse(args: impl IntoIterator<Item = OsString>) -> Result<Self, String> {
        let mut args = args.into_iter();
        let action = match args.next().as_deref().and_then(|s| s.to_str()) {
            Some("check") => Action::Check,
            Some("run") => Action::Run,
            Some("build") => Action::Build,
            Some("ast") => Action::Ast,
            Some("emit-llvm") => Action::EmitLlvm,
            _ => return Err(USAGE.into()),
        };
        let mut file: Option<PathBuf> = None;
        let mut output = None;
        let mut json = false;
        let mut optimize = false;
        let mut interpret = false;
        let mut fuel = interpreter::DEFAULT_FUEL;
        let mut positional = false;
        while let Some(arg) = args.next() {
            match arg.to_str().filter(|_| !positional) {
                Some("--") => positional = true,
                Some("--format=json") if action == Action::Check => json = true,
                Some("--interpreter") if action == Action::Run => interpret = true,
                Some("--fuel") if action == Action::Run => {
                    fuel = args
                        .next()
                        .and_then(|n| n.to_str()?.parse().ok())
                        .ok_or("--fuel requires a nonnegative integer")?;
                }
                Some("-o") if action == Action::Build => {
                    output = Some(PathBuf::from(args.next().ok_or("-o requires a path")?));
                }
                Some("-O0") if action == Action::Build => optimize = false,
                Some("-O2") if action == Action::Build => optimize = true,
                Some(flag) if flag.starts_with('-') => {
                    return Err(format!("unexpected option {flag}\n{USAGE}"));
                }
                _ => {
                    if file.replace(PathBuf::from(arg)).is_some() {
                        return Err("expected one source file".into());
                    }
                }
            }
        }
        if action == Action::Run && !interpret {
            return Err("run requires --interpreter".into());
        }
        Ok(Self {
            action,
            file: file.ok_or("missing source file")?,
            output,
            json,
            optimize,
            fuel,
        })
    }
}

fn json_string(s: &str) -> String {
    let mut out = String::from("\"");
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            c if c.is_control() => write!(out, "\\u{:04x}", c as u32).unwrap(),
            c => out.push(c),
        }
    }
    out.push('"');
    out
}

fn diagnostic(file: &Path, source: &str, d: syntax::Diagnostic, json: bool) -> String {
    if json {
        format!(
            "{{\"schema\":\"gpp.bootstrap-diagnostic/1\",\"severity\":\"error\",\"code\":{},\"message\":{},\"location\":{{\"file\":{},\"start_byte\":{},\"end_byte\":{}}}}}",
            json_string(d.code),
            json_string(&d.message),
            json_string(&file.to_string_lossy()),
            d.span.start,
            d.span.end
        )
    } else {
        let prefix = &source[..d.span.start];
        let line = 1 + prefix.matches(['\r', '\n']).count() - prefix.matches("\r\n").count();
        let column = prefix
            .rsplit(['\r', '\n'])
            .next()
            .unwrap_or_default()
            .chars()
            .count()
            + 1;
        format!(
            "{}:{line}:{column}: error[{}]: {}",
            file.display(),
            d.code,
            d.message
        )
    }
}

fn execute(options: Options) -> Result<(), String> {
    let source = fs::read_to_string(&options.file).map_err(|e| {
        let message = format!("cannot read source: {e}");
        diagnostic(
            &options.file,
            "",
            syntax::Diagnostic::new("GPP-IO-001", message, syntax::Span { start: 0, end: 0 }),
            options.json,
        )
    })?;
    let report = |d| diagnostic(&options.file, &source, d, options.json);
    let module = syntax::parse(&source).map_err(report)?;
    if options.action == Action::Ast {
        print!("{}", syntax::print(&module));
        return Ok(());
    }
    let program = check::check(&module).map_err(report)?;
    match options.action {
        Action::Check => {}
        Action::Run => {
            let value =
                interpreter::run(&module, options.fuel).map_err(|f| format!("fault: {f}"))?;
            println!("{value}");
        }
        Action::Build => {
            let output = options.output.unwrap_or_else(|| {
                if options.file.extension().is_some_and(|ext| ext == "gpp") {
                    options.file.with_extension("")
                } else {
                    options.file.with_added_extension("out")
                }
            });
            if output
                .canonicalize()
                .is_ok_and(|p| options.file.canonicalize().is_ok_and(|input| p == input))
            {
                return Err("build output would replace the input source file".into());
            }
            native::build(&program, &output, options.optimize)?;
        }
        Action::EmitLlvm => print!("{}", native::emit_llvm(&program)?),
        Action::Ast => unreachable!(),
    }
    Ok(())
}

fn main() -> ExitCode {
    let mut args = env::args_os().skip(1).peekable();
    if args.peek().is_some_and(|s| s == "-h" || s == "--help") {
        println!("{USAGE}\n{}", edit::USAGE);
        return ExitCode::SUCCESS;
    }
    if matches!(
        args.peek().and_then(|s| s.to_str()),
        Some("complete" | "prove" | "holes" | "verify" | "library")
    ) {
        let command = args.next().unwrap();
        let result = match command.to_str().unwrap() {
            "complete" => complete::run(args),
            "prove" => symbolic::run(args),
            "holes" => holes::run(args),
            "library" => library::run(args),
            _ => verify::run(args),
        };
        return match result {
            Ok(code) => ExitCode::from(code),
            Err(message) => {
                eprintln!("{message}");
                ExitCode::from(2)
            }
        };
    }
    enum Invocation {
        Compile(Options),
        Trace(trace::Request),
        Probe(probe::Request),
        Edit(edit::Request),
    }
    let parsed = if args.peek().is_some_and(|s| s == "probe") {
        args.next();
        probe::Request::parse(args).map(Invocation::Probe)
    } else if args.peek().is_some_and(|s| s == "trace") {
        args.next();
        trace::Request::parse(args).map(Invocation::Trace)
    } else if args
        .peek()
        .is_some_and(|s| s == "edit" || s == "revision" || s == "expressions")
    {
        edit::parse(args).map(Invocation::Edit)
    } else {
        Options::parse(args).map(Invocation::Compile)
    };
    let command = match parsed {
        Ok(command) => command,
        Err(message) => {
            eprintln!("{message}");
            return ExitCode::from(2);
        }
    };
    let result = match command {
        Invocation::Compile(options) => execute(options),
        Invocation::Trace(request) => request.execute(),
        Invocation::Probe(request) => request.execute(),
        Invocation::Edit(request) => edit::execute(request),
    };
    match result {
        Ok(()) => ExitCode::SUCCESS,
        Err(message) => {
            eprintln!("{message}");
            ExitCode::FAILURE
        }
    }
}
