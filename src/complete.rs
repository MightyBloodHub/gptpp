//! Complete one typed expression hole against all source contracts. The search
//! grammar reads the hole's lexical scope; the verifier independently checks
//! the complete program, including callers and multi-step properties.
use crate::check::{self, Hole};
#[path = "completion_grammar.rs"]
mod completion_grammar;
use crate::interpreter::{self, Fault, Value};
use crate::syntax::{self, Function, Module, Type, TypeKind};
use crate::{diagnostic, edit, json_string, trace, verify};
use std::collections::{HashMap, HashSet, VecDeque};
use std::ffi::OsString;
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::rc::Rc;

const USAGE: &str = "gpp complete FILE --hole NAME [--fill EXPRESSION_FILE] [--search hybrid|grammar|minimum|piecewise] [--limit N] [--budget N] [--expect REVISION] [--stdout]";
const PROBE_LIMIT: usize = 64;

#[derive(Clone, Copy, Eq, PartialEq)]
enum SearchMode {
    Hybrid,
    Grammar,
    Minimum,
    Piecewise,
}

struct Options {
    file: PathBuf,
    name: String,
    fragment: Option<PathBuf>,
    limit: usize,
    budget: u64,
    expected: Option<String>,
    stdout: bool,
    mode: SearchMode,
}

impl Options {
    fn parse(mut args: impl Iterator<Item = OsString>) -> Result<Self, String> {
        let file = PathBuf::from(args.next().ok_or(USAGE)?);
        let (mut name, mut fragment, mut limit, mut budget, mut expected) =
            (None, None, None, None, None);
        let mut stdout = false;
        let mut guidance = None;
        while let Some(flag) = args.next() {
            match flag.to_str() {
                Some("--hole") if name.is_none() => {
                    name = Some(
                        args.next()
                            .and_then(|s| s.into_string().ok())
                            .ok_or(USAGE)?,
                    )
                }
                Some("--fill") if fragment.is_none() => {
                    fragment = Some(PathBuf::from(args.next().ok_or(USAGE)?))
                }
                Some("--limit") if limit.is_none() => {
                    limit = Some(
                        args.next()
                            .and_then(|n| n.to_str()?.parse::<usize>().ok())
                            .filter(|n| (1..=4096).contains(n))
                            .ok_or("--limit requires 1..4096")?,
                    )
                }
                Some("--budget") if budget.is_none() => {
                    budget = Some(
                        args.next()
                            .and_then(|n| n.to_str()?.parse().ok())
                            .ok_or("--budget requires a nonnegative assignment count")?,
                    )
                }
                Some("--search") if guidance.is_none() => {
                    guidance = Some(match args.next().as_deref().and_then(|s| s.to_str()) {
                        Some("hybrid") => SearchMode::Hybrid,
                        Some("grammar") => SearchMode::Grammar,
                        Some("minimum") => SearchMode::Minimum,
                        Some("piecewise") => SearchMode::Piecewise,
                        _ => {
                            return Err(
                                "--search requires hybrid, grammar, minimum or piecewise".into()
                            );
                        }
                    });
                }
                Some("--expect") if expected.is_none() => {
                    expected = Some(
                        args.next()
                            .and_then(|s| s.into_string().ok())
                            .ok_or(USAGE)?,
                    )
                }
                Some("--stdout") if !stdout => stdout = true,
                _ => return Err(USAGE.into()),
            }
        }
        Ok(Self {
            file,
            name: name.ok_or(USAGE)?,
            fragment,
            limit: limit.unwrap_or(256),
            budget: budget.unwrap_or(verify::DEFAULT_BUDGET),
            expected,
            stdout,
            mode: guidance.unwrap_or(SearchMode::Hybrid),
        })
    }
}

fn fill(
    opts: &Options,
    source: &str,
    function: &Function,
    hole: &Hole,
    expr: &str,
) -> Result<(String, Module), String> {
    let (candidate, module) = edit::replace_node(
        &opts.file,
        opts.fragment.as_deref().unwrap_or(Path::new("<candidate>")),
        source,
        function,
        hole.span,
        expr,
    )?;
    let end = candidate.len() - (source.len() - hole.span.end);
    let mut actual = None;
    check::check_with_types(&module, |node, ty| {
        if node.span.start == hole.span.start && node.span.end == end {
            actual = Some(ty);
        }
    })
    .map_err(|d| diagnostic(&opts.file, &candidate, d, true))?;
    if actual != Some(hole.ty) {
        return Err(format!(
            "hole '{}' requires {}; replacement has {}",
            hole.name,
            module.type_name(hole.ty),
            actual
                .map(|t| module.type_name(t))
                .unwrap_or("unresolved type")
        ));
    }
    Ok((candidate, module))
}

// Fairly vary all argument positions, including fields of a record, within a
// fixed probe budget. These calls can witness a difference, never equivalence.
fn product(columns: &[Vec<Value>], limit: usize) -> Vec<Vec<Value>> {
    if columns.iter().any(Vec::is_empty) {
        return vec![];
    }
    let total = columns
        .iter()
        .fold(1usize, |n, c| n.saturating_mul(c.len()));
    let mut indices = vec![0; columns.len()];
    let mut rows = Vec::new();
    for n in 0..total.min(limit) {
        if total > limit {
            // A deterministic mix including both same-index and independent variations.
            let mut rng = (n as u64 + 1).wrapping_mul(6364136223846793005);
            for (i, col) in columns.iter().enumerate() {
                rng = rng
                    .wrapping_mul(6364136223846793005)
                    .wrapping_add(1442695040888963407);
                indices[i] = if n < 8 {
                    n % col.len()
                } else {
                    ((rng >> 32) as usize) % col.len()
                };
            }
        }
        rows.push(
            columns
                .iter()
                .zip(&indices)
                .map(|(c, &i)| c[i].clone())
                .collect(),
        );
        for (idx, c) in indices.iter_mut().zip(columns).rev() {
            *idx += 1;
            if *idx < c.len() {
                break;
            }
            *idx = 0;
        }
    }
    rows
}

fn samples(module: &Module, ty: Type, depth: usize) -> Vec<Value> {
    match ty {
        Type::Bool => vec![Value::Bool(false), Value::Bool(true)],
        Type::Unit => vec![Value::Unit],
        Type::I64 => [0, 1, -1, 2, 3, 4, 8, 9, i64::MIN, i64::MAX]
            .into_iter()
            .map(Value::Int)
            .collect(),
        Type::Named(i) => {
            let decl = &module.types[i];
            match &decl.kind {
                TypeKind::Enum(variants) => variants
                    .iter()
                    .take(PROBE_LIMIT)
                    .map(|s| Value::Enum(Rc::new((decl.name.clone(), s.clone()))))
                    .collect(),
                TypeKind::Record(fields) if depth < 3 && fields.len() <= 16 => {
                    let cols = fields
                        .iter()
                        .map(|f| samples(module, f.ty, depth + 1))
                        .collect::<Vec<_>>();
                    product(&cols, 16)
                        .into_iter()
                        .map(|row| {
                            Value::Record(Rc::new((
                                decl.name.clone(),
                                fields.iter().map(|f| f.name.clone()).zip(row).collect(),
                            )))
                        })
                        .collect()
                }
                _ => vec![],
            }
        }
    }
}

fn known_bad(result: &Result<Value, Fault>) -> bool {
    matches!(
        result,
        Ok(Value::Bool(false))
            | Err(Fault::IntegerOverflow | Fault::DivisionByZero | Fault::InvalidBounds)
    )
}

fn outcome(value: Result<Value, Fault>) -> Result<Option<String>, String> {
    if matches!(
        value,
        Err(Fault::ResourceLimit | Fault::InvalidCheckedProgram)
    ) {
        return Ok(None);
    }
    let mut bytes = Vec::new();
    trace::write_result(&mut bytes, "result", value).map_err(|e| e.to_string())?;
    Ok(Some(format!("{{{}}}", String::from_utf8(bytes).unwrap())))
}

// A signed literal costs one node in this ranking even when the syntax tree
// represents its minus sign separately. Parentheses never affect the score.
fn expression_cost(expr: &syntax::Expr) -> usize {
    use syntax::ExprKind::*;
    1 + match &expr.kind {
        Unary(syntax::UnOp::Neg, e) if matches!(e.kind, Int(_)) => 0,
        Field(e, _) | AsI64(e) | Unary(_, e) => expression_cost(e),
        Binary(_, a, b) => expression_cost(a) + expression_cost(b),
        If { cond, yes, no } => expression_cost(cond) + expression_cost(yes) + expression_cost(no),
        Call(_, args) => args.iter().map(expression_cost).sum(),
        _ => 0,
    }
}

fn inputs_json(function: &Function, args: &[Value]) -> Result<String, String> {
    let mut input = Vec::new();
    for (i, (p, v)) in function.params.iter().zip(args).enumerate() {
        if i > 0 {
            input.push(b',');
        }
        write!(input, "{}:", json_string(&p.name)).unwrap();
        trace::write_value(&mut input, v.clone()).map_err(|e| e.to_string())?;
    }
    Ok(format!("{{{}}}", String::from_utf8(input).unwrap()))
}

struct Winner {
    expression: String,
    source: String,
    report: String,
}

fn verification(module: &Module, source: &str, budget: u64) -> Result<String, String> {
    let mut output = Vec::new();
    verify::verify_module(
        module,
        &edit::revision(source.as_bytes())?,
        None,
        budget,
        &mut output,
    )?;
    Ok(String::from_utf8(output).unwrap().trim().to_owned())
}

pub fn run(args: impl Iterator<Item = OsString>) -> Result<u8, String> {
    let opts = Options::parse(args)?;
    let source = fs::read_to_string(&opts.file).map_err(|e| e.to_string())?;
    let revision = edit::revision(source.as_bytes())?;
    if opts.expected.as_ref().is_some_and(|s| s != &revision) {
        return Err("stale source revision".into());
    }
    let fail = |d| diagnostic(&opts.file, &source, d, true);
    let module = syntax::parse(&source).map_err(fail)?;
    let mut types = HashMap::new();
    let holes = check::holes_with_types(&module, |expr, ty| {
        if expr.site != syntax::ExprSite::Synthetic {
            types.insert(expr.span, ty);
        }
    })
    .map_err(fail)?;
    let [hole] = holes.as_slice() else {
        return Err("completion requires exactly one typed hole in the module".into());
    };
    if hole.name != opts.name {
        return Err(format!("unknown hole '{}'", opts.name));
    }
    let function = edit::target(&module, &hole.function)?;
    let manual = opts.fragment.is_some();
    let candidates = if let Some(file) = &opts.fragment {
        vec![fs::read_to_string(file).map_err(|e| e.to_string())?]
    } else {
        completion_grammar::candidates(&module, function, hole, &types, opts.limit)
    };
    let mut truncated = candidates.len() > opts.limit;
    let mut queue: VecDeque<_> = candidates.into();
    let mut attempted = HashSet::new();
    let piecewise = opts.mode == SearchMode::Piecewise;
    let minimum = (opts.mode == SearchMode::Minimum || piecewise) && !manual;
    let mut guide_after = (opts.mode == SearchMode::Hybrid && !manual && opts.limit >= 8)
        .then_some((opts.limit / 2).min(queue.len()));
    let mut guidance = crate::guided_search::Search::default();
    let mut minimum_vectors = 0;
    let mut numeric_tests = 0;
    let mut partitions = 0;
    let mut residuals = 0;
    let mut costs = HashMap::new();
    if minimum && !module.contracts.is_empty() {
        let (found, work) = crate::guided_search::minimum(&module, hole, opts.budget, piecewise);
        guidance = found;
        minimum_vectors = work.vectors;
        numeric_tests = work.numeric;
        partitions = work.partitions;
        residuals = work.residuals;
        let mut unique = HashSet::new();
        let mut batch: Vec<_> = guidance
            .expressions
            .iter()
            .cloned()
            .chain(queue)
            .filter(|s| unique.insert(s.clone()))
            .collect();
        truncated |= batch.len() > opts.limit;
        batch.truncate(opts.limit);
        for term in &batch {
            if let Ok(parsed) = syntax::parse_expression(term) {
                costs.insert(term.clone(), expression_cost(&parsed));
            }
        }
        batch.sort_by_key(|e| costs.get(e).copied().unwrap_or(usize::MAX));
        queue = batch.into();
    }
    let calls = if manual || function.params.len() > 16 {
        vec![]
    } else {
        product(
            &function
                .params
                .iter()
                .map(|p| samples(&module, p.ty, 0))
                .collect::<Vec<_>>(),
            PROBE_LIMIT,
        )
    };
    let mut witnesses: Vec<(usize, Vec<Value>)> = vec![];
    let mut tested = 0;
    let mut survivors = 0;
    let mut incomplete = module.contracts.is_empty();
    let mut winner: Option<Winner> = None;
    // An exhausted interpreter run gives no observation. A later pair of
    // terminating candidates may still disagree on this same probe.
    let mut observations: Vec<Option<(String, String)>> = vec![None; calls.len()];
    let mut detail = String::new();
    let mut ambiguous = false;
    let mut best_cost = None;
    let mut longer_passing = 0;
    let mut longer_question = None;
    if !incomplete {
        while tested < opts.limit {
            if guide_after == Some(tested) {
                guide_after = None;
                if survivors == 0 {
                    guidance = crate::guided_search::suggest(&module, hole, opts.budget);
                    // Prefer guided suggestions at this point. Moving a duplicate
                    // forward preserves the number of distinct full candidates.
                    for item in guidance.expressions.iter().rev() {
                        if !attempted.contains(item) {
                            queue.retain(|other| other != item);
                            queue.push_front(item.clone());
                        }
                    }
                    truncated |= tested + queue.len() > opts.limit;
                }
            }
            let Some(expr) = queue.pop_front() else { break };
            attempted.insert(expr.clone());
            tested += 1;
            let (text, candidate) = match fill(&opts, &source, function, hole, &expr) {
                Ok(v) => v,
                Err(e) => {
                    if manual {
                        detail = format!(",\"diagnostic\":{}", json_string(&e));
                    }
                    continue;
                }
            };
            if witnesses.iter().any(|(i, vs)| {
                known_bad(&interpreter::eval_contract(
                    &candidate,
                    &candidate.contracts[*i],
                    vs.clone(),
                    interpreter::DEFAULT_FUEL,
                    &mut (),
                ))
            }) {
                continue;
            }
            let mut remaining = opts.budget;
            let mut passed = true;
            for (i, contract) in candidate.contracts.iter().enumerate() {
                let row = verify::evaluate(&candidate, contract, remaining)?;
                remaining -= row.checked;
                match row.outcome {
                    verify::Outcome::Passed => continue,
                    verify::Outcome::Counterexample { args, .. } => witnesses.push((i, args)),
                    verify::Outcome::Incomplete(_) => incomplete = true,
                }
                passed = false;
                break;
            }
            if !passed {
                if manual {
                    detail = format!(
                        ",\"verification\":{}",
                        verification(&candidate, &text, opts.budget)?
                    );
                }
                continue;
            }
            survivors += 1;
            let mut longer = false;
            if minimum {
                let cost = costs[&expr];
                longer = cost > *best_cost.get_or_insert(cost);
                longer_passing += usize::from(longer);
            }
            for (args, previous) in calls.iter().zip(&mut observations) {
                let Some(current) = outcome(interpreter::invoke(
                    &candidate,
                    &function.name,
                    args.clone(),
                    interpreter::DEFAULT_FUEL,
                    &mut (),
                ))?
                else {
                    continue;
                };
                if let Some((first, prior)) = previous {
                    if *prior != current {
                        let witness = format!(
                            "{{\"function\":{},\"inputs\":{},\"alternatives\":[{{\"expression\":{},\"outcome\":{prior}}},{{\"expression\":{},\"outcome\":{current}}}]}}",
                            json_string(&function.name),
                            inputs_json(function, args)?,
                            json_string(first),
                            json_string(&expr)
                        );
                        if longer {
                            longer_question.get_or_insert(witness);
                        } else {
                            detail = format!(",\"question\":{witness}");
                            ambiguous = true;
                        }
                        break;
                    }
                } else if !longer {
                    *previous = Some((expr.clone(), current));
                }
            }
            if ambiguous {
                break;
            }
            if winner.is_none() {
                winner = Some(Winner {
                    expression: expr.trim().to_owned(),
                    report: verification(&candidate, &text, opts.budget)?,
                    source: text,
                });
            }
        }
    } else {
        detail = ",\"reason\":\"no_contracts\"".into();
    }
    if fs::read(&opts.file).map_err(|e| e.to_string())? != source.as_bytes() {
        return Err("source changed during completion".into());
    }
    let (status, code) = if ambiguous {
        ("ambiguous", 3)
    } else if winner.is_some() {
        ("verified", 0)
    } else if incomplete || truncated {
        ("incomplete", 3)
    } else {
        ("rejected", 1)
    };
    let selected = if code == 0 { winner.as_ref() } else { None };
    if let Some(w) = selected {
        detail = format!(
            ",\"selected\":{},\"verification\":{}",
            json_string(&w.expression),
            w.report
        );
    }
    if ambiguous && let Some(w) = &winner {
        detail.push_str(&format!(
            ",\"first_passing\":{}",
            json_string(&w.expression)
        ));
    }
    if minimum {
        let cost = best_cost
            .map(|v| v.to_string())
            .unwrap_or_else(|| "null".into());
        detail.push_str(&format!(",\"selection\":{{\"policy\":\"minimum_ast_cost\",\"cost\":{cost},\"value_vectors\":{minimum_vectors},\"numeric_hypotheses\":{numeric_tests},\"longer_passing\":{longer_passing},\"longer_disagreement\":{}}}",longer_question.as_deref().unwrap_or("null")));
    }
    if piecewise && !manual {
        detail.push_str(&format!(",\"piecewise\":{{\"subset_operations\":{partitions},\"residual_operations\":{residuals}}}"));
    }
    let report = format!(
        "{{\"schema\":\"gpp.complete/1\",\"revision\":{},\"hole\":{},\"status\":{},\"tested\":{tested},\"witnesses\":{},\"passing_candidates_seen\":{survivors},\"candidate_limit\":{},\"grammar_truncated\":{truncated},\"guidance\":{{\"contract_runs\":{},\"examples\":{},\"value_vectors\":{},\"branch_joins\":{},\"proposals\":{}}},\"probe_calls_per_passing_candidate\":{}{} }}",
        json_string(&revision),
        json_string(&hole.name),
        json_string(status),
        witnesses.len(),
        opts.limit,
        guidance.runs,
        guidance.rows,
        guidance.vectors,
        guidance.joins,
        guidance.expressions.len(),
        calls.len(),
        detail
    );
    if opts.stdout {
        if let Some(w) = selected {
            print!("{}", w.source);
        } else {
            eprintln!("{report}");
        }
    } else {
        println!("{report}");
    }
    Ok(code)
}
