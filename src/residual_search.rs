//! Join partial expressions by looking up their required contribution on each
//! public observation. Exact public agreement only admits a proposal for checking.
use super::{Bank, Example, Search, Term, seed};
use crate::check::Hole;
use crate::syntax::{Module, Type};
use std::collections::{HashMap, HashSet};

const LIMIT: usize = 40_000;
type Column = Vec<i64>;
#[derive(Clone)]
struct Feature {
    code: String,
    cost: usize,
    values: Column,
}
#[derive(Clone)]
struct Predicate {
    code: String,
    cost: usize,
    mask: u32,
}

struct Collector {
    answers: Vec<(usize, String)>,
    work: usize,
}
impl Collector {
    fn tick(&mut self) -> bool {
        if self.work == LIMIT {
            false
        } else {
            self.work += 1;
            true
        }
    }
    fn hit(&mut self, cost: usize, expr: String) {
        if self.answers.len() < 384 {
            self.answers.push((cost, expr));
        }
    }
}

fn bits(xs: &[i64], p: impl Fn(i64) -> bool) -> u32 {
    xs.iter()
        .enumerate()
        .fold(0, |m, (i, &x)| m | (u32::from(p(x)) << i))
}

fn features(
    terms: Vec<Term>,
    rows: &[Example],
    out: &mut Collector,
) -> (Vec<Feature>, Vec<Predicate>) {
    let mut ints = vec![];
    let mut flags = vec![];
    let mut seen = HashSet::new();
    for t in terms {
        let Some(v) = t.values.into_iter().collect::<Option<Vec<_>>>() else {
            continue;
        };
        if t.boolean {
            flags.push(Predicate {
                code: t.text,
                cost: t.cost,
                mask: bits(&v, |n| n != 0),
            });
        } else if seen.insert(v.clone()) {
            ints.push(Feature {
                code: t.text,
                cost: t.cost,
                values: v,
            });
        }
    }
    let vars: Vec<_> = ints
        .iter()
        .filter(|t| t.values.windows(2).any(|p| p[0] != p[1]))
        .take(8)
        .cloned()
        .collect();
    for (i, a) in vars.iter().enumerate() {
        for b in &vars[..i] {
            for op in ["+", "-", "reverse"] {
                out.tick();
                let (a, b) = if op == "reverse" { (b, a) } else { (a, b) };
                let v: Option<Vec<_>> = a
                    .values
                    .iter()
                    .zip(&b.values)
                    .map(|(&x, &y)| {
                        if op == "+" {
                            x.checked_add(y)
                        } else {
                            x.checked_sub(y)
                        }
                    })
                    .collect();
                if let Some(values) = v
                    && seen.insert(values.clone())
                {
                    ints.push(Feature {
                        code: format!(
                            "({} {} {})",
                            a.code,
                            if op == "+" { "+" } else { "-" },
                            b.code
                        ),
                        cost: a.cost + b.cost + 1,
                        values,
                    });
                }
            }
            for op in ["<", "==", "<="] {
                out.tick();
                let mask = a
                    .values
                    .iter()
                    .zip(&b.values)
                    .enumerate()
                    .fold(0, |m, (i, (x, y))| {
                        m | (u32::from(match op {
                            "<" => x < y,
                            "==" => x == y,
                            _ => x <= y,
                        }) << i)
                    });
                flags.push(Predicate {
                    code: format!("({} {op} {})", a.code, b.code),
                    cost: a.cost + b.cost + 1,
                    mask,
                });
            }
        }
    }
    let base: Vec<_> = ints
        .iter()
        .filter(|t| t.values.windows(2).any(|p| p[0] != p[1]))
        .take(24)
        .cloned()
        .collect();
    for a in &base {
        for d in 2..=12 {
            out.tick();
            let values: Vec<_> = a.values.iter().map(|x| x % d).collect();
            if seen.insert(values.clone()) {
                ints.push(Feature {
                    values,
                    code: format!("({} % {d})", a.code),
                    cost: a.cost + 2,
                });
            }
        }
    }
    let all = u32::MAX >> (32 - rows.len());
    for a in &ints {
        let mut bounds = a.values.clone();
        bounds.sort_unstable();
        bounds.dedup();
        for k in bounds {
            for op in ["==", "!=", ">=", "<="] {
                if !out.tick() {
                    break;
                }
                let mask = bits(&a.values, |x| match op {
                    "==" => x == k,
                    "!=" => x != k,
                    ">=" => x >= k,
                    _ => x <= k,
                });
                if mask != 0 && mask != all {
                    flags.push(Predicate {
                        mask,
                        code: format!("({} {op} {k})", a.code),
                        cost: a.cost + 2,
                    });
                }
            }
        }
    }
    flags.sort_by(|a, b| (a.cost, a.code.len(), &a.code).cmp(&(b.cost, b.code.len(), &b.code)));
    // Keep a small number of different spellings of each observed predicate.
    let mut count = HashMap::<u32, usize>::new();
    flags.retain(|p| {
        let n = count.entry(p.mask).or_default();
        *n += 1;
        *n <= 2
    });
    (ints, flags)
}

fn boolean(target: u32, flags: &[Predicate], out: &mut Collector) {
    for p in flags {
        if p.mask == target {
            out.hit(p.cost, p.code.clone());
        }
    }
    // A true disjunction requires both operands to stay within its target
    // mask. A conjunction requires each operand to cover the target.
    for (op, keep) in [("||", false), ("&&", true)] {
        let part: Vec<_> = flags
            .iter()
            .filter(|p| {
                if keep {
                    p.mask & target == target
                } else {
                    p.mask & target == p.mask
                }
            })
            .take(126)
            .collect();
        for (i, a) in part.iter().enumerate() {
            for b in &part[..i] {
                if !out.tick() {
                    return;
                }
                if (if keep {
                    a.mask & b.mask
                } else {
                    a.mask | b.mask
                }) == target
                {
                    out.hit(a.cost + b.cost + 1, format!("({} {op} {})", a.code, b.code));
                }
            }
        }
    }
    let by_mask: HashMap<_, _> = flags.iter().rev().map(|p| (p.mask, p)).collect();
    for p in flags {
        if !out.tick() {
            return;
        }
        if let Some(q) = by_mask.get(&(p.mask ^ target)) {
            out.hit(p.cost + q.cost + 1, format!("({} != {})", p.code, q.code));
        }
    }
}

fn sums(rows: &[Example], mut ints: Vec<Feature>, flags: &[Predicate], out: &mut Collector) {
    let leaves: Vec<_> = ints
        .iter()
        .filter(|t| t.cost <= 2)
        .take(24)
        .cloned()
        .collect();
    let mut seen: HashSet<_> = ints.iter().map(|t| t.values.clone()).collect();
    for f in flags.iter().take(260) {
        for a in &leaves {
            if !out.tick() {
                return;
            }
            let values: Vec<_> = a
                .values
                .iter()
                .enumerate()
                .map(|(i, &v)| if f.mask & (1 << i) == 0 { 0 } else { v })
                .collect();
            if seen.insert(values.clone()) {
                ints.push(Feature {
                    values,
                    cost: f.cost + a.cost + 2,
                    code: format!("(if {} {{ {} }} else {{ 0 }})", f.code, a.code),
                });
            }
        }
    }
    ints.sort_by(|a, b| (a.cost, a.code.len(), &a.code).cmp(&(b.cost, b.code.len(), &b.code)));
    let lookup: HashMap<_, _> = ints
        .iter()
        .rev()
        .map(|t| (t.values.as_slice(), t))
        .collect();
    for a in &ints {
        if !out.tick() {
            return;
        }
        let delta: Option<Vec<_>> = rows
            .iter()
            .zip(&a.values)
            .map(|(r, x)| r.answer.checked_sub(*x))
            .collect();
        let Some(delta) = delta else { continue };
        if let Some(b) = lookup.get(delta.as_slice()) {
            out.hit(a.cost + b.cost + 1, format!("({} + {})", a.code, b.code));
        }
    }
    // Limit the third-term join to the cheapest residual models. Validate the
    // actual grouping and any intermediate overflow in the compiler.
    for (i, a) in ints.iter().take(240).enumerate() {
        for b in &ints[..i] {
            if !out.tick() {
                return;
            }
            let delta: Option<Vec<_>> = rows
                .iter()
                .zip(&a.values)
                .zip(&b.values)
                .map(|((r, x), y)| r.answer.checked_sub(x.checked_add(*y)?))
                .collect();
            if let Some(v) = delta
                && let Some(c) = lookup.get(v.as_slice())
            {
                out.hit(
                    a.cost + b.cost + c.cost + 2,
                    format!("(({} + {}) + {})", a.code, b.code, c.code),
                );
            }
        }
    }
}

pub(super) fn candidates(module: &Module, hole: &Hole, rows: &[Example]) -> (Vec<String>, usize) {
    if rows.len() < 3 {
        return (vec![], 0);
    }
    let mut stats = Search::default();
    let mut bank = Bank {
        target_bool: hole.ty == Type::Bool,
        target: rows.iter().map(|r| Some(r.answer)).collect(),
        terms: vec![],
        solutions: vec![],
        seen: HashSet::new(),
        stats: &mut stats,
    };
    seed(&mut bank, module, hole, rows);
    let mut out = Collector {
        answers: vec![],
        work: 0,
    };
    let (ints, flags) = features(bank.terms, rows, &mut out);
    if hole.ty == Type::Bool {
        let target = rows
            .iter()
            .enumerate()
            .fold(0, |m, (i, r)| m | (u32::from(r.answer != 0) << i));
        boolean(target, &flags, &mut out);
    } else {
        sums(rows, ints, &flags, &mut out);
    }
    out.answers
        .sort_by(|(c, a), (d, b)| c.cmp(d).then(a.len().cmp(&b.len())).then(a.cmp(b)));
    out.answers.dedup();
    (
        out.answers.into_iter().take(48).map(|(_, s)| s).collect(),
        out.work,
    )
}
