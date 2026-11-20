//! Derive local input/output examples from public contracts and use them to
//! propose expressions. A proposal always goes back through the full checker.
use crate::check::Hole;
use crate::interpreter::{self, Fault, Observer, Scope, Value};
use crate::syntax::{Domain, Expr, ExprKind, Module, Type};
use std::collections::HashSet;

#[path = "parameter_search.rs"]
mod parameter_search;
#[path = "residual_search.rs"]
mod residual_search;

const MAX_ROWS: usize = 32;
const MAX_RUNS: usize = 768;
const SAMPLE_FUEL: u64 = 4096;
const MAX_COLUMNS: usize = 24;
const MAX_TERMS: usize = 800;
const MAX_VECTORS: usize = 24_000;

#[derive(Default)]
pub struct Search {
    pub expressions: Vec<String>,
    pub runs: usize,
    pub rows: usize,
    pub vectors: usize,
    pub joins: usize,
}

struct Experiment<'h> {
    hole: &'h Hole,
    answer: Value,
    capture: bool,
    locals: Option<Vec<Value>>,
    known: &'h [Example],
    numbers: Vec<i64>,
}

impl<'a> Observer<'a> for Experiment<'_> {
    type Visit = ();
    fn enter(&mut self, _: &Expr, _: &[Scope<'a>]) {}
    fn leave(&mut self, _: (), result: &Result<Value, Fault>) {
        if self.capture
            && let Ok(Value::Int(n)) = result
            && self.numbers.len() < 24
            && !self.numbers.contains(n)
        {
            self.numbers.push(*n);
        }
    }
    fn hole_value(&mut self, scopes: &[Scope<'a>]) -> Result<Value, Fault> {
        let locals = self
            .hole
            .locals
            .iter()
            .map(|(name, _)| {
                scopes
                    .iter()
                    .rev()
                    .find_map(|s| s.get(name.as_str()).cloned())
            })
            .collect::<Option<Vec<_>>>()
            .ok_or(Fault::InvalidCheckedProgram)?;
        // A known prefix can carry state into a later invocation of the hole.
        // Every use of an identical lexical environment must agree.
        if let Some(row) = self.known.iter().find(|r| r.locals == locals) {
            return Ok(if self.hole.ty == Type::Bool {
                Value::Bool(row.answer != 0)
            } else {
                Value::Int(row.answer)
            });
        }
        if let Some(input) = &self.locals {
            if *input != locals {
                return Err(Fault::ResourceLimit);
            }
        } else {
            self.locals = Some(locals);
        }
        Ok(self.answer.clone())
    }
}

#[derive(PartialEq)]
pub(crate) struct Example {
    pub(crate) locals: Vec<Value>,
    pub(crate) answer: i64,
}

fn assignments(domains: &[Domain]) -> Vec<Vec<Value>> {
    let width = |domain: &Domain| match domain {
        Domain::Bool => 2,
        Domain::I64 { low, high } => (i128::from(*high) - i128::from(*low) + 1) as u128,
    };
    let size = domains
        .iter()
        .fold(1u128, |n, d| n.saturating_mul(width(d)));
    let count = size.min(MAX_ROWS as u128);
    (0..count)
        .map(|row| {
            let intervals = (count - 1).max(1);
            let mut index =
                ((size - 1) / intervals) * row + (size - 1) % intervals * row / intervals;
            let mut args = domains
                .iter()
                .rev()
                .map(|d| {
                    let offset = index % width(d);
                    index /= width(d);
                    match d {
                        Domain::Bool => Value::Bool(offset != 0),
                        Domain::I64 { low, .. } => {
                            Value::Int((i128::from(*low) + offset as i128) as i64)
                        }
                    }
                })
                .collect::<Vec<_>>();
            args.reverse();
            args
        })
        .collect()
}

fn examples(module: &Module, hole: &Hole, max_runs: usize, stats: &mut Search) -> Vec<Example> {
    let mut rows = vec![];
    let cases: Vec<_> = module
        .contracts
        .iter()
        .take(MAX_ROWS)
        .map(|c| assignments(&c.domains))
        .collect();
    let mut sampled = 0;
    for index in 0..MAX_ROWS {
        for (c, inputs) in module.contracts.iter().zip(&cases) {
            let Some(args) = inputs.get(index) else {
                continue;
            };
            if sampled == MAX_ROWS || stats.runs >= max_runs {
                return rows;
            }
            sampled += 1;
            let boolean = hole.ty == Type::Bool;
            let value = |n| {
                if boolean {
                    Value::Bool(n != 0)
                } else {
                    Value::Int(n)
                }
            };
            let mut probe = Experiment {
                hole,
                answer: value(0),
                capture: true,
                known: &rows,
                locals: None,
                numbers: vec![],
            };
            let base = interpreter::eval_contract(module, c, args.clone(), SAMPLE_FUEL, &mut probe);
            stats.runs += 1;
            let Some(locals) = probe.locals.clone() else {
                continue;
            };
            if matches!(base, Err(Fault::ResourceLimit)) {
                continue;
            }
            let mut hit = matches!(base, Ok(Value::Bool(true))).then_some(0);
            let mut options = vec![1];
            if !boolean {
                options.extend([-1, 2, -2]);
                for &n in probe.numbers.iter().rev() {
                    if n != 0 && !options.contains(&n) {
                        options.push(n);
                    }
                }
            }
            probe.capture = false;
            for n in options {
                if stats.runs >= max_runs {
                    return rows;
                }
                probe.answer = value(n);
                stats.runs += 1;
                if matches!(
                    interpreter::eval_contract(module, c, args.clone(), SAMPLE_FUEL, &mut probe),
                    Ok(Value::Bool(true))
                ) {
                    if hit.is_some() {
                        hit = None;
                        break;
                    }
                    hit = Some(n);
                }
            }
            if let Some(answer) = hit {
                let row = Example { locals, answer };
                if !rows.contains(&row) {
                    rows.push(row);
                }
            }
        }
    }
    rows
}

#[derive(Clone)]
struct Term {
    text: String,
    boolean: bool,
    values: Vec<Option<i64>>,
    cost: usize,
}

struct Bank<'a> {
    target_bool: bool,
    target: Vec<Option<i64>>,
    seen: HashSet<(bool, Vec<Option<i64>>)>,
    terms: Vec<Term>,
    solutions: Vec<(usize, String)>,
    stats: &'a mut Search,
}

impl Bank<'_> {
    fn add(&mut self, term: Term) {
        if self.stats.vectors >= MAX_VECTORS {
            return;
        }
        self.stats.vectors += 1;
        if term.boolean == self.target_bool
            && term.values == self.target
            && self.solutions.len() < 128
            && !self.solutions.iter().any(|(_, s)| s == &term.text)
        {
            self.solutions.push((term.cost, term.text.clone()));
        }
        if self.terms.len() < MAX_TERMS && self.seen.insert((term.boolean, term.values.clone())) {
            self.terms.push(term);
        }
    }
}

fn seed(bank: &mut Bank<'_>, module: &Module, hole: &Hole, rows: &[Example]) {
    let column = |bank: &mut Bank<'_>, name: String, values: Vec<&Value>| {
        let Some(first) = values.first() else { return };
        match first {
            Value::Bool(_) | Value::Int(_) => bank.add(Term {
                text: name,
                boolean: matches!(first, Value::Bool(_)),
                values: values
                    .iter()
                    .map(|v| match v {
                        Value::Bool(b) => Some(i64::from(*b)),
                        Value::Int(n) => Some(*n),
                        _ => None,
                    })
                    .collect(),
                cost: 1,
            }),
            Value::Enum(e) => {
                let mut variants = Vec::new();
                for v in &values {
                    if let Value::Enum(tag) = v
                        && !variants.contains(&tag.1)
                    {
                        variants.push(tag.1.clone());
                    }
                }
                for variant in variants {
                    bank.add(Term {
                        text: format!("({name} == {}::{variant})", e.0),
                        boolean: true,
                        values: values
                            .iter()
                            .map(|v| Some(i64::from(matches!(v,Value::Enum(t) if t.1 == variant))))
                            .collect(),
                        cost: 3,
                    });
                }
            }
            _ => {}
        }
    };
    for (i, (name, _)) in hole.locals.iter().enumerate() {
        if bank.terms.len() >= MAX_COLUMNS {
            break;
        }
        if let Value::Record(record) = &rows[0].locals[i] {
            for (j, (field, _)) in record.1.iter().enumerate().take(MAX_COLUMNS) {
                let values = rows
                    .iter()
                    .filter_map(|r| match &r.locals[i] {
                        Value::Record(v) => Some(&v.1[j].1),
                        _ => None,
                    })
                    .collect();
                column(bank, format!("{name}.{field}"), values);
            }
        } else {
            column(
                bank,
                name.clone(),
                rows.iter().map(|r| &r.locals[i]).collect(),
            );
        }
    }
    // Constants already used by the production function are part of its local vocabulary.
    if let Some(function) = module.functions.iter().find(|f| f.name == hole.function) {
        let mut seen = HashSet::new();
        for expr in crate::edit::expressions(function) {
            if let ExprKind::Int(n) = expr.kind
                && seen.insert(n)
            {
                bank.add(Term {
                    text: n.to_string(),
                    boolean: false,
                    values: vec![Some(n); rows.len()],
                    cost: 1,
                });
                if seen.len() == 8 {
                    break;
                }
            }
        }
    }
    for (n, t, b) in [
        (0, "false", true),
        (1, "true", true),
        (0, "0", false),
        (1, "1", false),
        (-1, "-1", false),
        (2, "2", false),
    ] {
        bank.add(Term {
            text: t.into(),
            boolean: b,
            values: vec![Some(n); rows.len()],
            cost: 1,
        });
    }
}

fn combine(bank: &mut Bank<'_>, a: &Term, b: &Term) {
    if a.boolean != b.boolean {
        return;
    }
    let ops = if a.boolean {
        &["&&", "||", "!=", "=="][..]
    } else {
        &["+", "-", "min", "max", "*", "/", "%", "<", "<=", "==", "!="][..]
    };
    for &op in ops {
        if bank.stats.vectors >= MAX_VECTORS {
            break;
        }
        let values = a
            .values
            .iter()
            .zip(&b.values)
            .map(|(&x, &y)| {
                let x = x?;
                if op == "&&" && x == 0 {
                    return Some(0);
                }
                if op == "||" && x != 0 {
                    return Some(1);
                }
                let y = y?;
                match op {
                    "+" => x.checked_add(y),
                    "-" => x.checked_sub(y),
                    "*" => x.checked_mul(y),
                    "/" => x.checked_div(y),
                    "%" => {
                        if y == 0 {
                            None
                        } else {
                            Some(x.wrapping_rem(y))
                        }
                    }
                    "min" => Some(x.min(y)),
                    "max" => Some(x.max(y)),
                    "<" => Some(i64::from(x < y)),
                    "<=" => Some(i64::from(x <= y)),
                    "==" => Some(i64::from(x == y)),
                    "!=" => Some(i64::from(x != y)),
                    "&&" | "||" => Some(y),
                    _ => unreachable!(),
                }
            })
            .collect();
        let text = if matches!(op, "min" | "max") {
            format!("{op}({}, {})", a.text, b.text)
        } else {
            format!("({} {op} {})", a.text, b.text)
        };
        bank.add(Term {
            text,
            values,
            boolean: a.boolean || matches!(op, "<" | "<=" | "==" | "!="),
            cost: 1 + a.cost + b.cost,
        });
    }
}

// Identify integer coefficients directly from observations. Constants need
// not be present in the source vocabulary. Validate every arithmetic step
// with checked I64 semantics before offering a program to the full checker.
fn fit_scale(bank: &mut Bank<'_>, term: &Term, guard: Option<(&Term, i64)>) {
    if term.boolean || bank.target_bool || bank.target.len() < 3 {
        return;
    }
    let points = term
        .values
        .iter()
        .zip(&bank.target)
        .map(|(&x, &y)| Some((x?, y?)))
        .collect::<Option<Vec<_>>>();
    let Some(points) = points else { return };
    let mut subset = points
        .iter()
        .enumerate()
        .filter(|(i, _)| guard.is_none_or(|(g, b)| g.values[*i] == Some(b)))
        .map(|(_, p)| p);
    let Some(&(x0, y0)) = subset.next() else {
        return;
    };
    let Some(&(x1, y1)) = subset.find(|(x, _)| *x != x0) else {
        return;
    };
    let dx = i128::from(x1) - i128::from(x0);
    let dy = i128::from(y1) - i128::from(y0);
    if dy % dx != 0 {
        return;
    }
    let Ok(scale) = i64::try_from(dy / dx) else {
        return;
    };
    let Ok(offset) = i64::try_from(i128::from(y0) - i128::from(scale) * i128::from(x0)) else {
        return;
    };
    if scale == 0 || (scale == 1 && offset == 0) {
        return;
    }
    if guard.is_some()
        && !subset
            .all(|(x, y)| x.checked_mul(scale).and_then(|n| n.checked_add(offset)) == Some(*y))
    {
        return;
    }
    let product = if scale == 1 {
        term.text.clone()
    } else {
        format!("({} * {scale})", term.text)
    };
    let text = if offset == 0 {
        product
    } else {
        format!("({product} + {offset})")
    };
    bank.add(Term {
        text,
        boolean: false,
        cost: term.cost + 2 * usize::from(scale != 1) + 2 * usize::from(offset != 0),
        values: points
            .iter()
            .map(|(x, _)| x.checked_mul(scale)?.checked_add(offset))
            .collect(),
    });
}

// Fit two independent inputs using exact differences. A singular sample or
// overflowing determinant yields no suggestion. The full vector and all
// public contracts still have to agree with the proposed program.
fn fit_plane(bank: &mut Bank<'_>, a: &Term, b: &Term) -> Option<()> {
    let points = a
        .values
        .iter()
        .zip(&b.values)
        .zip(&bank.target)
        .map(|((&x, &y), &z)| Some((i128::from(x?), i128::from(y?), i128::from(z?))))
        .collect::<Option<Vec<_>>>()?;
    let &(x, y, z) = points.first()?;
    let mut diffs = points.iter().map(|(a, b, c)| (a - x, b - y, c - z));
    let (p, q, r) = diffs.find(|(p, q, _)| *p != 0 || *q != 0)?;
    let det = |a: i128, b: i128, c: i128, d: i128| a.checked_mul(d)?.checked_sub(b.checked_mul(c)?);
    for (u, v, w) in diffs {
        let divisor = det(p, q, u, v)?;
        if divisor == 0 {
            continue;
        }
        let m = det(r, q, w, v)?;
        let n = det(p, r, u, w)?;
        if m.checked_rem(divisor)? != 0 || n.checked_rem(divisor)? != 0 {
            return None;
        }
        let (m, n) = (
            i64::try_from(m.checked_div(divisor)?).ok()?,
            i64::try_from(n.checked_div(divisor)?).ok()?,
        );
        if m == 0 || n == 0 {
            return None;
        }
        let k = i64::try_from(
            z.checked_sub(i128::from(m) * x)?
                .checked_sub(i128::from(n) * y)?,
        )
        .ok()?;
        let scaled = |term: &Term, c| {
            if c == 1 {
                term.text.clone()
            } else {
                format!("({} * {c})", term.text)
            }
        };
        let mut text = format!("({} + {})", scaled(a, m), scaled(b, n));
        if k != 0 {
            text = format!("({text} + {k})");
        }
        bank.add(Term {
            text,
            boolean: false,
            cost: a.cost
                + b.cost
                + 1
                + 2 * (usize::from(m != 1) + usize::from(n != 1) + usize::from(k != 0)),
            values: a
                .values
                .iter()
                .zip(&b.values)
                .map(|(&x, &y)| {
                    x?.checked_mul(m)?
                        .checked_add(y?.checked_mul(n)?)?
                        .checked_add(k)
                })
                .collect(),
        });
        return Some(());
    }
    None
}

// Combine branch programs that independently match the required results on
// each side of a guard. Bit masks make this join independent of tuple order.
fn branches(bank: &mut Bank<'_>) {
    let count = bank.target.len();
    let all = (1u64 << count) - 1;
    let mut guards = Vec::new();
    let mut results = Vec::new();
    for t in &bank.terms {
        if t.boolean && t.values.iter().all(Option::is_some) {
            let mask = t
                .values
                .iter()
                .enumerate()
                .fold(0, |mask, (i, v)| mask | (u64::from(*v == Some(1)) << i));
            if mask != 0 && mask != all {
                guards.push((mask, t));
            }
        }
        if t.boolean == bank.target_bool {
            let matches = t
                .values
                .iter()
                .zip(&bank.target)
                .enumerate()
                .fold(0, |mask, (i, (a, b))| mask | (u64::from(a == b) << i));
            if matches != 0 && matches != all {
                results.push((matches, t));
            }
        }
    }
    // Retain short branches for each partition. Check every proposed join on
    // all public contracts later, including ones outside the sample.
    let mut joins = vec![];
    for (mask, guard) in guards {
        let other = all ^ mask;
        let yes = results.iter().filter(|(ok, _)| ok & mask == mask).take(2);
        for (_, a) in yes {
            for (_, b) in results.iter().filter(|(ok, _)| ok & other == other).take(2) {
                joins.push((
                    guard.cost + a.cost + b.cost + 1,
                    format!("if {} {{ {} }} else {{ {} }}", guard.text, a.text, b.text),
                ));
            }
        }
    }
    bank.stats.joins = joins.len();
    bank.solutions.extend(joins);
}

pub fn suggest(module: &Module, hole: &Hole, budget: u64) -> Search {
    let mut stats = Search::default();
    if !matches!(hole.ty, Type::Bool | Type::I64) || hole.locals.len() > MAX_COLUMNS {
        return stats;
    }
    let rows = examples(
        module,
        hole,
        budget.min(MAX_RUNS as u64) as usize,
        &mut stats,
    );
    solve(hole, module, &rows, &mut stats);
    stats
}

/// Seed the minimum-cost engine and the hybrid synthesizer with the same
/// contract observations. Only full candidate verification can accept a fill.
pub struct Work {
    pub vectors: usize,
    pub numeric: usize,
    pub partitions: usize,
    pub residuals: usize,
}
pub fn minimum(module: &Module, hole: &Hole, budget: u64, piecewise: bool) -> (Search, Work) {
    let mut work = Work {
        vectors: 0,
        numeric: 0,
        partitions: 0,
        residuals: 0,
    };
    let mut stats = Search::default();
    if !matches!(hole.ty, Type::Bool | Type::I64) || hole.locals.len() > MAX_COLUMNS {
        return (stats, work);
    }
    let rows = examples(
        module,
        hole,
        budget.min(MAX_RUNS as u64) as usize,
        &mut stats,
    );
    solve(hole, module, &rows, &mut stats);
    let pool = crate::minimal_search::candidates(hole, &rows);
    let (parameterized, numeric_tests) = parameter_search::candidates(module, hole, &rows);
    let mut extra = Vec::new();
    if piecewise {
        let trees = crate::piecewise_search::candidates(hole, &rows);
        work.partitions = trees.work;
        let (residuals, work_done) = residual_search::candidates(module, hole, &rows);
        work.residuals = work_done;
        extra = trees.expressions;
        extra.extend(residuals);
    }
    let mut unique = HashSet::new();
    stats.expressions = pool
        .expressions
        .into_iter()
        .chain(parameterized)
        .chain(extra)
        .chain(stats.expressions)
        .filter(|s| unique.insert(s.clone()))
        .collect();
    work.vectors = pool.vectors;
    work.numeric = numeric_tests;
    (stats, work)
}

fn solve(hole: &Hole, module: &Module, rows: &[Example], stats: &mut Search) {
    stats.rows = rows.len();
    if rows.len() < 2 {
        return;
    }
    let mut bank = Bank {
        target_bool: hole.ty == Type::Bool,
        target: rows.iter().map(|r| Some(r.answer)).collect(),
        terms: vec![],
        solutions: vec![],
        seen: HashSet::new(),
        stats,
    };
    seed(&mut bank, module, hole, rows);
    let atoms = bank.terms.clone();
    for a in &atoms {
        if a.boolean {
            bank.add(Term {
                text: format!("({} as I64)", a.text),
                boolean: false,
                values: a.values.clone(),
                cost: a.cost + 1,
            });
        }
        for b in &atoms {
            combine(&mut bank, a, b);
        }
    }
    let simple = bank.terms.clone();
    for t in &simple {
        fit_scale(&mut bank, t, None);
    }
    if !bank.target_bool {
        let variables: Vec<_> = atoms
            .iter()
            .filter(|t| !t.boolean && t.values.windows(2).any(|p| p[0] != p[1]))
            .take(12)
            .collect();
        for (i, &a) in variables.iter().enumerate() {
            for &b in &variables[..i] {
                fit_plane(&mut bank, a, b);
            }
            for g in simple.iter().filter(|t| t.boolean).take(24) {
                for branch in [0, 1] {
                    fit_scale(&mut bank, a, Some((g, branch)));
                }
            }
        }
    }
    let first = simple[atoms.len()..].to_vec();
    for t in &first {
        if bank.stats.vectors >= MAX_VECTORS {
            break;
        }
        for a in &atoms {
            combine(&mut bank, t, a);
            combine(&mut bank, a, t);
        }
    }
    branches(&mut bank);
    bank.solutions
        .sort_by(|(c, a), (d, b)| c.cmp(d).then(a.len().cmp(&b.len())).then(a.cmp(b)));
    bank.solutions.dedup();
    stats.expressions = bank
        .solutions
        .into_iter()
        .take(16)
        .map(|(_, s)| s)
        .collect();
}
