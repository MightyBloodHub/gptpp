//! Fit bounded arithmetic families to observed local inputs. These templates
//! propose source expressions. The compiler rechecks each proposal normally.
use super::{Bank, Example, Search, Term, seed};
use crate::{
    check::Hole,
    syntax::{Module, Type},
};
use std::collections::HashSet;

const MAX_TESTS: usize = 8192;
struct Fits {
    solutions: Vec<(usize, String)>,
    tests: usize,
}

impl Fits {
    fn test(
        &mut self,
        term: &Term,
        rows: &[Example],
        text: String,
        cost: usize,
        compute: impl Fn(i64) -> Option<i64>,
    ) {
        if self.tests >= MAX_TESTS {
            return;
        }
        self.tests += 1;
        if term
            .values
            .iter()
            .zip(rows)
            .all(|(x, r)| x.and_then(&compute) == Some(r.answer))
        {
            self.solutions.push((term.cost + cost, text));
        }
    }
}

fn gcd(mut a: u128, mut b: u128) -> u128 {
    while b != 0 {
        (a, b) = (b, a % b);
    }
    a
}

fn periods(modulus: u128) -> Vec<i64> {
    let mut values = Vec::new();
    if modulus > 1 {
        for d in 2..=12 {
            if modulus.is_multiple_of(d) {
                values.push(d as i64);
                if let Ok(other) = i64::try_from(modulus / d)
                    && other > 1
                {
                    values.push(other);
                }
            }
        }
        if let Ok(m) = i64::try_from(modulus) {
            values.push(m);
        }
    }
    values.sort_unstable();
    values.dedup();
    values
}

fn integers(term: &Term, rows: &[Example], fits: &mut Fits) {
    let mut modulus = 0;
    let (mut low, mut high) = (1u128, i64::MAX as u128);
    let mut min = i64::MAX;
    let mut max = i64::MIN;
    for (&x, r) in term.values.iter().zip(rows) {
        let Some(x) = x else { return };
        let y = r.answer;
        modulus = gcd(modulus, (i128::from(x) - i128::from(y)).unsigned_abs());
        min = min.min(y);
        max = max.max(y);
        let (a, b) = (u128::from(x.unsigned_abs()), u128::from(y.unsigned_abs()));
        if y != 0 && x.signum() != y.signum() {
            high = 0;
        }
        // For a positive divisor d and quotient magnitude b, b*d <= a < (b+1)*d.
        low = low.max(a / (b + 1) + 1);
        if let Some(bound) = a.checked_div(b) {
            high = high.min(bound);
        }
    }
    let a = &term.text;
    for d in periods(modulus) {
        fits.test(term, rows, format!("({a} % {d})"), 2, |x| Some(x % d));
    }
    if low <= high {
        for d in [low, high]
            .into_iter()
            .filter_map(|n| i64::try_from(n).ok())
            .filter(|n| *n > 1)
        {
            fits.test(term, rows, format!("({a} / {d})"), 2, |x| x.checked_div(d));
        }
    }
    if min < max {
        fits.test(term, rows, format!("min({a}, {max})"), 2, |x| {
            Some(x.min(max))
        });
        fits.test(term, rows, format!("max({a}, {min})"), 2, |x| {
            Some(x.max(min))
        });
        fits.test(term, rows, format!("clamp({a}, {min}, {max})"), 3, |x| {
            Some(x.clamp(min, max))
        });
    }
}

fn predicate(term: &Term, rows: &[Example], fits: &mut Fits) {
    let a = &term.text;
    for label in [0, 1] {
        let mut class = term
            .values
            .iter()
            .zip(rows)
            .filter(|(_, r)| r.answer == label)
            .filter_map(|(&v, _)| v);
        let Some(first) = class.next() else { return };
        let (mut lo, mut hi, mut modulus) = (first, first, 0u128);
        for n in class {
            lo = lo.min(n);
            hi = hi.max(n);
            modulus = gcd(modulus, (i128::from(n) - i128::from(first)).unsigned_abs());
        }
        let positive = label == 1;
        let op = if positive { "==" } else { "!=" };
        if lo == hi {
            fits.test(term, rows, format!("({a} {op} {lo})"), 2, |x| {
                Some(i64::from((x == lo) == positive))
            });
        }
        if positive {
            fits.test(term, rows, format!("({a} >= {lo})"), 2, |x| {
                Some(i64::from(x >= lo))
            });
            fits.test(term, rows, format!("({a} <= {hi})"), 2, |x| {
                Some(i64::from(x <= hi))
            });
        }
        for d in periods(modulus) {
            let rest = first % d;
            fits.test(term, rows, format!("(({a} % {d}) {op} {rest})"), 4, |x| {
                Some(i64::from((x % d == rest) == positive))
            });
        }
    }
}

pub(super) fn candidates(module: &Module, hole: &Hole, rows: &[Example]) -> (Vec<String>, usize) {
    if rows.len() < 3 {
        return (vec![], 0);
    }
    let mut stats = Search::default();
    let mut seeds = Bank {
        target_bool: hole.ty == Type::Bool,
        target: rows.iter().map(|r| Some(r.answer)).collect(),
        terms: vec![],
        solutions: vec![],
        seen: HashSet::new(),
        stats: &mut stats,
    };
    seed(&mut seeds, module, hole, rows);
    let vars: Vec<_> = seeds
        .terms
        .into_iter()
        .filter(|t| !t.boolean && t.values.windows(2).any(|p| p[0] != p[1]))
        .take(8)
        .collect();
    let mut fits = Fits {
        solutions: vec![],
        tests: 0,
    };
    let process = |t: &Term, fits: &mut Fits| {
        if hole.ty == Type::Bool {
            predicate(t, rows, fits)
        } else {
            integers(t, rows, fits)
        }
    };
    for t in &vars {
        process(t, &mut fits);
    }
    // Visit primitive integer projections by coefficient magnitude. Equivalent
    // rescalings consume no extra probes. Both directions matter for division.
    for magnitude in 2..=8 {
        for p in -4i64..=4 {
            for q in -4i64..=4 {
                if p == 0
                    || q == 0
                    || p.abs() + q.abs() != magnitude
                    || gcd(u128::from(p.unsigned_abs()), u128::from(q.unsigned_abs())) != 1
                {
                    continue;
                }
                for (i, a) in vars.iter().enumerate() {
                    for b in &vars[..i] {
                        if fits.tests >= MAX_TESTS {
                            break;
                        }
                        let factor = |t: &Term, k: i64| {
                            if k == 1 {
                                t.text.clone()
                            } else {
                                format!("({} * {k})", t.text)
                            }
                        };
                        let op = if q > 0 { "+" } else { "-" };
                        let values = a
                            .values
                            .iter()
                            .zip(&b.values)
                            .map(|(&x, &y)| {
                                let x = x?.checked_mul(p)?;
                                let y = y?.checked_mul(q.abs())?;
                                if q > 0 {
                                    x.checked_add(y)
                                } else {
                                    x.checked_sub(y)
                                }
                            })
                            .collect();
                        let t = Term {
                            text: format!("({} {op} {})", factor(a, p), factor(b, q.abs())),
                            boolean: false,
                            values,
                            cost: a.cost
                                + b.cost
                                + 1
                                + 2 * usize::from(p != 1)
                                + 2 * usize::from(q.abs() != 1),
                        };
                        process(&t, &mut fits);
                    }
                }
            }
        }
    }
    fits.solutions
        .sort_by(|(c, a), (d, b)| c.cmp(d).then(a.len().cmp(&b.len())).then(a.cmp(b)));
    fits.solutions.dedup();
    (
        fits.solutions
            .into_iter()
            .take(32)
            .map(|(_, s)| s)
            .collect(),
        fits.tests,
    )
}
