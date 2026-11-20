//! Check independent expression edits against one immutable source snapshot.
//! Input frames are START:END LENGTH[ check]\n followed by LENGTH UTF-8 bytes.
use crate::interpreter::{self, Fault, Value};
use crate::syntax::{self, Function, Module, Span, Type};
use crate::{check, diagnostic, edit, json_string, trace};
use std::ffi::OsString;
use std::fs;
use std::io::{self, BufRead, Read, Write};
use std::path::{Path, PathBuf};

const USAGE: &str =
    "gpp probe FILE --function TARGET --expect REVISION --cases CASES.tsv [--wrapped] [--filter]";
const MAX_HEADER_BYTES: u64 = 96;
const MAX_FRAGMENT_BYTES: usize = 4 * 1024 * 1024;

pub struct Request {
    file: PathBuf,
    function: String,
    expected: String,
    cases: PathBuf,
    wrapped: bool,
    filter: bool,
}

impl Request {
    pub fn parse(mut args: impl Iterator<Item = OsString>) -> Result<Self, String> {
        let file = PathBuf::from(args.next().ok_or(USAGE)?);
        let mut option = |flag: &str| {
            if args.next().as_deref() != Some(flag.as_ref()) {
                return Err(USAGE.to_owned());
            }
            args.next().ok_or_else(|| USAGE.to_owned())
        };
        let function = option("--function")?.into_string().map_err(|_| USAGE)?;
        let expected = option("--expect")?.into_string().map_err(|_| USAGE)?;
        let cases = PathBuf::from(option("--cases")?);
        let (mut wrapped, mut filter) = (false, false);
        for flag in args {
            match flag.to_str() {
                Some("--wrapped") if !wrapped => wrapped = true,
                Some("--filter") if !filter => filter = true,
                _ => return Err(USAGE.into()),
            }
        }
        Ok(Self {
            file,
            function,
            expected,
            cases,
            wrapped,
            filter,
        })
    }

    pub fn execute(self) -> Result<(), String> {
        let source =
            fs::read_to_string(&self.file).map_err(|e| format!("{}: {e}", self.file.display()))?;
        let revision = edit::revision(source.as_bytes())?;
        if self.expected != revision {
            return Err(format!(
                "stale revision: expected {}, found {revision}",
                self.expected
            ));
        }
        let report = |err| diagnostic(&self.file, &source, err, false);
        let module = syntax::parse(&source).map_err(report)?;
        check::check(&module).map_err(report)?;
        let function = edit::target(&module, &self.function)?;
        let cases = read_cases(&self.cases, &module, self.wrapped, self.filter)?;
        let mut input = io::stdin().lock();
        let mut out = io::BufWriter::new(io::stdout().lock());
        let mut serve = || -> io::Result<()> {
            writeln!(
                out,
                "{{\"schema\":\"gpp.probe/1\",\"revision\":{},\"cases\":{}}}",
                json_string(&revision),
                cases.len()
            )?;
            out.flush()?;
            while let Some(edit) = next_edit(&mut input)? {
                match edit::replace_node(
                    &self.file,
                    Path::new("<fragment>"),
                    &source,
                    function,
                    edit.span,
                    &edit.fragment,
                ) {
                    Ok((_, _)) if edit.check_only => {
                        writeln!(out, "{{\"status\":\"ok\",\"outcomes\":[]}}")?;
                    }
                    Ok((_, candidate)) if self.filter => {
                        let matches = cases.iter().all(|case| {
                            case.execute(&candidate)
                                .is_ok_and(|v| Some(v) == case.expected)
                        });
                        writeln!(out, "{{\"status\":\"ok\",\"matches\":{matches}}}")?;
                    }
                    Ok((_, candidate)) => {
                        write!(out, "{{\"status\":\"ok\",\"outcomes\":[")?;
                        for (i, case) in cases.iter().enumerate() {
                            if i != 0 {
                                write!(out, ",")?;
                            }
                            write!(out, "{{")?;
                            trace::write_result(&mut out, "result", case.execute(&candidate))?;
                            write!(out, "}}")?;
                        }
                        writeln!(out, "]}}")?;
                    }
                    Err(message) => writeln!(
                        out,
                        "{{\"status\":\"invalid\",\"error\":{}}}",
                        json_string(&message)
                    )?,
                }
                out.flush()?;
            }
            Ok(())
        };
        serve().map_err(|e| format!("probe stream: {e}"))
    }
}

enum Invocation {
    Direct(String, Vec<Value>),
    Wrapped(Function, Type),
}

struct Call {
    invoke: Invocation,
    expected: Option<Value>,
}

impl Call {
    fn execute(&self, module: &Module) -> Result<Value, Fault> {
        match &self.invoke {
            Invocation::Direct(name, args) => interpreter::invoke(
                module,
                name,
                args.clone(),
                interpreter::DEFAULT_FUEL,
                &mut (),
            ),
            Invocation::Wrapped(wrapper, ty) => {
                interpreter::invoke_wrapper(module, wrapper).map(|value| match (ty, value) {
                    (Type::Bool, Value::Int(n)) => Value::Bool(n != 0),
                    (Type::Unit, _) => Value::Unit,
                    _ => value,
                })
            }
        }
    }
}

fn read_cases(
    path: &Path,
    module: &Module,
    wrapped: bool,
    filter: bool,
) -> Result<Vec<Call>, String> {
    let entries = fs::read_to_string(path).map_err(|e| format!("{}: {e}", path.display()))?;
    let mut prefix = String::from("__gpp_probe");
    while module.functions.iter().any(|f| f.name.starts_with(&prefix)) {
        prefix.push('_');
    }
    let mut cases = Vec::new();
    for (i, line) in entries.lines().enumerate() {
        let mut fields = line.split('\t');
        let name = fields.next().unwrap_or_default();
        let expected_text = if filter { fields.next_back() } else { None };
        let args = fields.map(str::to_owned).collect::<Vec<_>>();
        let entry = edit::target(module, name).map_err(|e| format!("case {}: {e}", i + 1))?;
        let values =
            trace::parse_values(entry, &args).map_err(|e| format!("case {}: {e}", i + 1))?;
        let expected = if filter {
            Some(
                expected_text
                    .and_then(|s| trace::parse_value(entry.result, s))
                    .ok_or_else(|| {
                        format!(
                            "case {}: expected a {} result in the final field",
                            i + 1,
                            entry.result
                        )
                    })?,
            )
        } else {
            None
        };
        let invoke = if wrapped {
            // Reproduce the public-case runner's entry, including literal argument
            // evaluation, boolean branches, Unit conversion, fuel and call depth.
            let literals = values
                .iter()
                .map(|v| match v {
                    Value::Int(n) => n.to_string(),
                    Value::Bool(b) => b.to_string(),
                    Value::Unit => "()".to_owned(),
                })
                .collect::<Vec<_>>();
            let call = format!("{name}({})", literals.join(", "));
            let body = match entry.result {
                Type::I64 => format!("return {call};"),
                Type::Bool => format!("if {call} {{ return 1; }} return 0;"),
                Type::Unit => format!("{call}; return 0;"),
            };
            let wrapper = format!("{prefix}{i}");
            let text = format!("module probe; fn {wrapper}() -> I64 !{{}} {{ {body} }}");
            let mut wrapper_module = syntax::parse(&text)
                .map_err(|err| diagnostic(Path::new("<case>"), &text, err, false))?;
            Invocation::Wrapped(wrapper_module.functions.remove(0), entry.result)
        } else {
            Invocation::Direct(name.to_owned(), values)
        };
        cases.push(Call { invoke, expected });
    }
    if cases.is_empty() {
        return Err("expected one or more probe cases".into());
    }
    Ok(cases)
}

struct Candidate {
    span: Span,
    fragment: String,
    check_only: bool,
}

fn next_edit(input: &mut impl BufRead) -> io::Result<Option<Candidate>> {
    let invalid = || {
        io::Error::new(
            io::ErrorKind::InvalidData,
            "expected START:END LENGTH[ check] and newline",
        )
    };
    let mut header = String::new();
    if input.take(MAX_HEADER_BYTES).read_line(&mut header)? == 0 {
        return Ok(None);
    }
    let fields: Vec<_> = header
        .strip_suffix('\n')
        .ok_or_else(invalid)?
        .split(' ')
        .collect();
    let (range, length, check_only) = match fields.as_slice() {
        [range, len] => (range, len, false),
        [range, len, "check"] => (range, len, true),
        _ => return Err(invalid()),
    };
    let (start, end) = range.split_once(':').ok_or_else(invalid)?;
    let parse = |v: &str| -> io::Result<usize> {
        if !v.bytes().all(|b| b.is_ascii_digit()) {
            return Err(invalid());
        }
        v.parse().map_err(|_| invalid())
    };
    let span = Span {
        start: parse(start)?,
        end: parse(end)?,
    };
    let len = parse(length)?;
    if len > MAX_FRAGMENT_BYTES {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "expression exceeds 4 MiB frame limit",
        ));
    }
    let mut bytes = vec![0; len];
    input.read_exact(&mut bytes)?;
    let fragment =
        String::from_utf8(bytes).map_err(|e| io::Error::new(io::ErrorKind::InvalidData, e))?;
    Ok(Some(Candidate {
        span,
        fragment,
        check_only,
    }))
}
