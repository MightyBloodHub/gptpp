//! Revision-bound expression observations from one call in the reference interpreter.
use crate::interpreter::{self, Fault, Observer, Scope, Value};
use crate::syntax::{self, Contract, Expr, ExprSite, Function, Module, Span, Type};
use crate::{check, diagnostic, edit, json_string};
use std::collections::{BTreeMap, HashMap};
use std::ffi::OsString;
use std::fs;
use std::io::{self, Write};
use std::path::PathBuf;

const USAGE: &str =
    "gpp trace FILE --function TARGET (--call ENTRY|--contract NAME) [ARG ...] [--fuel N]";
const SAMPLE_LIMIT: usize = 3;

pub struct Request {
    path: PathBuf,
    target: String,
    entry: String,
    contract: bool,
    args: Vec<String>,
    fuel: u64,
}

impl Request {
    pub fn parse(mut args: impl Iterator<Item = OsString>) -> Result<Self, String> {
        let path = PathBuf::from(args.next().ok_or(USAGE)?);
        if args.next().as_deref() != Some("--function".as_ref()) {
            return Err(USAGE.into());
        }
        let target = args
            .next()
            .and_then(|s| s.into_string().ok())
            .ok_or(USAGE)?;
        let contract = match args.next().as_deref().and_then(|s| s.to_str()) {
            Some("--call") => false,
            Some("--contract") => true,
            _ => return Err(USAGE.into()),
        };
        let entry = args
            .next()
            .and_then(|s| s.into_string().ok())
            .ok_or(USAGE)?;
        let mut values = Vec::new();
        let mut fuel = interpreter::DEFAULT_FUEL;
        while let Some(arg) = args.next() {
            if arg == "--fuel" {
                fuel = args
                    .next()
                    .and_then(|s| s.to_str()?.parse().ok())
                    .ok_or("--fuel needs a nonnegative integer")?;
                if args.next().is_some() {
                    return Err(USAGE.into());
                }
                break;
            }
            values.push(arg.into_string().map_err(|_| USAGE)?);
        }
        Ok(Self {
            path,
            target,
            entry,
            contract,
            args: values,
            fuel,
        })
    }

    pub fn execute(self) -> Result<(), String> {
        let source =
            fs::read_to_string(&self.path).map_err(|e| format!("{}: {e}", self.path.display()))?;
        let report = |err| diagnostic(&self.path, &source, err, false);
        let module = syntax::parse(&source).map_err(report)?;
        let target = edit::target(&module, &self.target)?;
        let mut trace = Trace::default();
        check::check_with_types(&module, |expr, ty| {
            if target.body_span.start <= expr.span.start
                && expr.span.end <= target.body_span.end
                && expr.site != ExprSite::Synthetic
            {
                trace.sites.insert(
                    expr.span,
                    Site {
                        ty,
                        hits: 0,
                        observations: Vec::new(),
                    },
                );
            }
        })
        .map_err(report)?;
        let (args, result) = if self.contract {
            let predicate = find_contract(&module, &self.entry)?;
            let args = parse_witness(predicate, &self.args)?;
            let result =
                interpreter::eval_contract(&module, predicate, args.clone(), self.fuel, &mut trace);
            (args, result)
        } else {
            let entry = edit::target(&module, &self.entry)?;
            let args = parse_values(entry, &self.args)?;
            let result =
                interpreter::invoke(&module, &self.entry, args.clone(), self.fuel, &mut trace);
            (args, result)
        };
        let revision = edit::revision(source.as_bytes())?;
        let mut out = io::BufWriter::new(io::stdout().lock());
        let mut emit = || -> io::Result<()> {
            write!(
                out,
                "{{\"schema\":\"gpp.trace/1\",\"revision\":{},\"function\":{},\"start_byte\":{},\"end_byte\":{},\"call\":{},\"args\":[",
                json_string(&revision),
                json_string(&self.target),
                target.span.start,
                target.span.end,
                json_string(&self.entry)
            )?;
            for (i, v) in args.iter().enumerate() {
                if i > 0 {
                    write!(out, ",")?;
                }
                write_value(&mut out, *v)?;
            }
            write!(out, "],")?;
            if self.contract {
                write!(out, "\"entry_kind\":\"contract\",")?;
            }
            write_result(&mut out, "result", result)?;
            write!(out, ",\"expressions\":[")?;
            for (i, expr) in edit::expressions(target).iter().enumerate() {
                if i > 0 {
                    write!(out, ",")?;
                }
                let site = &trace.sites[&expr.span];
                let Span { start, end } = expr.span;
                let binary_gap = match &expr.kind {
                    syntax::ExprKind::Binary(_, left, right) if self.contract => {
                        format!("\"binary_gap\":[{},{}],", left.span.end, right.span.start)
                    }
                    _ => String::new(),
                };
                write!(
                    out,
                    "{{\"start_byte\":{start},\"end_byte\":{end},{binary_gap}\"text\":{},\"type\":\"{}\",\"hits\":{},\"observations\":[",
                    json_string(&source[start..end]),
                    site.ty,
                    site.hits
                )?;
                for (i, obs) in site.observations.iter().enumerate() {
                    if i > 0 {
                        write!(out, ",")?;
                    }
                    write!(out, "{{\"locals\":{{")?;
                    for (i, (name, value)) in obs.locals.iter().enumerate() {
                        if i > 0 {
                            write!(out, ",")?;
                        }
                        write!(out, "{}:", json_string(name))?;
                        write_value(&mut out, *value)?;
                    }
                    write!(out, "}},")?;
                    write_result(&mut out, "value", obs.result.expect("every visit finishes"))?;
                    write!(out, "}}")?;
                }
                write!(out, "]}}")?;
            }
            writeln!(out, "]}}")?;
            out.flush()
        };
        emit().map_err(|e| e.to_string())
    }
}

pub(crate) fn find_contract<'a>(module: &'a Module, name: &str) -> Result<&'a Contract, String> {
    module
        .contracts
        .iter()
        .find(|c| c.predicate.name == name)
        .ok_or_else(|| format!("unknown contract '{name}'"))
}

pub(crate) fn parse_witness(contract: &Contract, raw: &[String]) -> Result<Vec<Value>, String> {
    let values = parse_values(&contract.predicate, raw)?;
    for ((param, domain), value) in contract
        .predicate
        .params
        .iter()
        .zip(&contract.domains)
        .zip(&values)
    {
        if !interpreter::in_domain(*domain, *value) {
            return Err(format!(
                "value outside contract domain for '{}'",
                param.name
            ));
        }
    }
    Ok(values)
}

pub(crate) fn parse_values(entry: &Function, raw: &[String]) -> Result<Vec<Value>, String> {
    if raw.len() != entry.params.len() {
        return Err(format!(
            "'{}' expects {} arguments, found {}",
            entry.name,
            entry.params.len(),
            raw.len()
        ));
    }
    entry
        .params
        .iter()
        .zip(raw)
        .map(|(param, s)| {
            parse_value(param.ty, s).ok_or_else(|| {
                format!(
                    "expected {} for argument '{}', found {s}",
                    param.ty, param.name
                )
            })
        })
        .collect()
}

pub(crate) fn parse_value(ty: Type, text: &str) -> Option<Value> {
    match ty {
        Type::I64 => text.parse::<i64>().ok().map(Value::Int),
        Type::Bool => text.parse::<bool>().ok().map(Value::Bool),
        Type::Unit if text == "()" => Some(Value::Unit),
        _ => None,
    }
}

pub(crate) fn write_value(out: &mut impl Write, value: Value) -> io::Result<()> {
    match value {
        Value::Int(n) => write!(out, "{n}"),
        Value::Bool(b) => write!(out, "{b}"),
        Value::Unit => write!(out, "null"),
    }
}

pub(crate) fn write_result(
    out: &mut impl Write,
    key: &str,
    result: Result<Value, Fault>,
) -> io::Result<()> {
    match result {
        Ok(value) => {
            write!(out, "\"{key}\":")?;
            write_value(out, value)
        }
        Err(fault) => write!(out, "\"fault\":\"{fault}\""),
    }
}

struct Observation<'a> {
    locals: BTreeMap<&'a str, Value>,
    result: Option<Result<Value, Fault>>,
}

struct Site<'a> {
    ty: Type,
    hits: u64,
    observations: Vec<Observation<'a>>,
}

#[derive(Default)]
struct Trace<'a> {
    sites: HashMap<Span, Site<'a>>,
}

impl<'a> Observer<'a> for Trace<'a> {
    type Visit = Option<(Span, usize)>;

    fn enter(&mut self, expr: &Expr, scopes: &[Scope<'a>]) -> Self::Visit {
        if expr.site == ExprSite::Synthetic {
            return None;
        }
        let site = self.sites.get_mut(&expr.span)?;
        site.hits += 1;
        let index = site.observations.len();
        if index == SAMPLE_LIMIT {
            return None;
        }
        // Inner bindings replace shadowed outer values. Reserve the sample on
        // entry so recursive calls to this exact site keep their own results.
        let locals = scopes.iter().flatten().map(|(&n, &v)| (n, v)).collect();
        site.observations.push(Observation {
            locals,
            result: None,
        });
        Some((expr.span, index))
    }

    fn leave(&mut self, visit: Self::Visit, result: Result<Value, Fault>) {
        if let Some((span, i)) = visit {
            self.sites.get_mut(&span).unwrap().observations[i].result = Some(result);
        }
    }
}
