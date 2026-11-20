//! Exhaust a contract's finite Cartesian domain, stopping on the first witness or limit.
use crate::interpreter::{self, Fault, Value};
use crate::syntax::{self, Contract, Domain, Module};
use crate::{check, diagnostic, edit, json_string, trace};
use std::ffi::OsString;
use std::fs;
use std::io::{self, Write};
use std::path::PathBuf;

const USAGE: &str = "gpp verify FILE [--contract NAME] [--budget N] [--format=json]";
pub(crate) const DEFAULT_BUDGET: u64 = 10_000;

enum Outcome {
    Passed,
    Counterexample {
        args: Vec<Value>,
        fault: Option<Fault>,
    },
    Incomplete(&'static str),
}

impl Outcome {
    fn status(&self) -> (&'static str, u8) {
        match self {
            Self::Passed => ("passed", 0),
            Self::Counterexample { .. } => ("counterexample", 1),
            Self::Incomplete(_) => ("incomplete", 3),
        }
    }
}

struct Report<'a> {
    contract: &'a Contract,
    checked: u64,
    outcome: Outcome,
}

fn first(domain: Domain) -> Value {
    match domain {
        Domain::Bool => Value::Bool(false),
        Domain::I64 { low, .. } => Value::Int(low),
    }
}

/// Carry the rightmost binding first. No product or range length must fit a machine integer.
fn advance(domains: &[Domain], values: &mut [Value]) -> bool {
    for (&domain, slot) in domains.iter().zip(values).rev() {
        match (domain, *slot) {
            (Domain::Bool, Value::Bool(false)) => {
                *slot = Value::Bool(true);
                return true;
            }
            (Domain::I64 { high, .. }, Value::Int(n)) if n < high => {
                *slot = Value::Int(n + 1);
                return true;
            }
            _ => *slot = first(domain),
        }
    }
    false
}

fn evaluate<'a>(
    module: &'a Module,
    contract: &'a Contract,
    limit: u64,
) -> Result<Report<'a>, String> {
    let mut args: Vec<_> = contract.domains.iter().copied().map(first).collect();
    let mut observer = ();
    let mut run =
        interpreter::contract_evaluator(module, contract, interpreter::DEFAULT_FUEL, &mut observer);
    let mut checked = 0;
    let outcome = loop {
        if checked == limit {
            break Outcome::Incomplete("budget");
        }
        checked += 1;
        match run(&args) {
            Ok(Value::Bool(true)) => {
                if !advance(&contract.domains, &mut args) {
                    break Outcome::Passed;
                }
            }
            Ok(Value::Bool(false)) => break Outcome::Counterexample { args, fault: None },
            Err(Fault::ResourceLimit) => break Outcome::Incomplete("resource_limit"),
            Err(
                fault @ (Fault::DivisionByZero | Fault::IntegerOverflow | Fault::InvalidBounds),
            ) => {
                break Outcome::Counterexample {
                    args,
                    fault: Some(fault),
                };
            }
            _ => return Err("internal error evaluating checked contract".into()),
        }
    };
    Ok(Report {
        contract,
        checked,
        outcome,
    })
}

fn write_report(out: &mut impl Write, row: &Report<'_>) -> io::Result<()> {
    let predicate = &row.contract.predicate;
    write!(
        out,
        "{{\"name\":{},\"status\":\"{}\",\"checked\":{}",
        json_string(&predicate.name),
        row.outcome.status().0,
        row.checked
    )?;
    match &row.outcome {
        Outcome::Passed => {}
        Outcome::Incomplete(reason) => write!(out, ",\"reason\":\"{reason}\"")?,
        Outcome::Counterexample { args, fault } => {
            write!(out, ",\"counterexample\":{{\"inputs\":{{")?;
            for (i, (param, value)) in predicate.params.iter().zip(args).enumerate() {
                if i > 0 {
                    write!(out, ",")?;
                }
                write!(out, "{}:", json_string(&param.name))?;
                trace::write_value(out, *value)?;
            }
            write!(out, "}},\"args\":[")?;
            for (i, value) in args.iter().enumerate() {
                if i > 0 {
                    write!(out, ",")?;
                }
                trace::write_value(out, *value)?;
            }
            write!(out, "],")?;
            match fault {
                Some(f) => write!(out, "\"fault\":\"{f}\"")?,
                None => write!(out, "\"result\":false")?,
            }
            write!(out, "}}")?;
        }
    }
    write!(out, "}}")
}

pub fn run(mut args: impl Iterator<Item = OsString>) -> Result<u8, String> {
    let file = PathBuf::from(args.next().ok_or(USAGE)?);
    let mut target = None;
    let mut budget = None;
    let mut format = false;
    while let Some(flag) = args.next() {
        match flag.to_str() {
            Some("--contract") if target.is_none() => {
                target = Some(
                    args.next()
                        .and_then(|s| s.into_string().ok())
                        .ok_or(USAGE)?,
                )
            }
            Some("--budget") if budget.is_none() => {
                budget = Some(
                    args.next()
                        .and_then(|s| s.to_str()?.parse::<u64>().ok())
                        .ok_or("--budget needs a nonnegative integer")?,
                )
            }
            Some("--format=json") if !format => format = true,
            _ => return Err(USAGE.into()),
        }
    }
    let budget = budget.unwrap_or(DEFAULT_BUDGET);
    let source = fs::read_to_string(&file).map_err(|e| format!("{}: {e}", file.display()))?;
    let report = |d| diagnostic(&file, &source, d, true);
    let module = syntax::parse(&source).map_err(report)?;
    check::check(&module).map_err(report)?;
    let revision = edit::revision(source.as_bytes())?;
    verify_module(
        &module,
        &revision,
        target.as_deref(),
        budget,
        &mut io::BufWriter::new(io::stdout().lock()),
    )
}

/// Verify a fully type-checked module. The caller supplies the revision of
/// precisely those bytes, including for a candidate that has not been saved.
pub(crate) fn verify_module(
    module: &Module,
    revision: &str,
    target: Option<&str>,
    budget: u64,
    out: &mut impl Write,
) -> Result<u8, String> {
    if let Some(name) = target
        && !module.contracts.iter().any(|c| c.predicate.name == name)
    {
        return Err(format!("unknown contract '{name}'"));
    }
    let mut checked = 0;
    let mut rows = Vec::new();
    for contract in &module.contracts {
        if target.is_some_and(|name| name != contract.predicate.name) {
            continue;
        }
        let row = evaluate(module, contract, budget - checked)?;
        checked += row.checked;
        let done = !matches!(row.outcome, Outcome::Passed);
        rows.push(row);
        if done {
            break;
        }
    }
    let outcome = rows
        .last()
        .map(|r| &r.outcome)
        .unwrap_or(&Outcome::Incomplete("no_contracts"));
    let (status, code) = outcome.status();
    let mut emit = || -> io::Result<()> {
        write!(
            out,
            "{{\"schema\":\"gpp.verify/1\",\"revision\":{},\"status\":\"{status}\",\"checked\":{checked},\"budget\":{budget}",
            json_string(revision)
        )?;
        if let Outcome::Incomplete(reason) = outcome {
            write!(out, ",\"reason\":\"{reason}\"")?;
        }
        write!(out, ",\"contracts\":[")?;
        for (i, row) in rows.iter().enumerate() {
            if i > 0 {
                write!(out, ",")?;
            }
            write_report(out, row)?;
        }
        writeln!(out, "]}}")?;
        out.flush()
    };
    emit().map_err(|e| e.to_string())?;
    Ok(code)
}
