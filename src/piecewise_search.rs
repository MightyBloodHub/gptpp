//! Fit a small decision tree to public hole observations. Each node partitions
//! a bit mask of examples. A full candidate must still pass normal verification.
use crate::check::Hole;
use crate::guided_search::Example;
use crate::interpreter::Value;
use crate::syntax::Type;
use std::collections::{HashMap, HashSet};

const MAX_WORK: usize = 110_000;
const MAX_DEPTH: usize = 3;
const MAX_ROWS: usize = 32;
const MAX_ROOTS: usize = 48;
type Mask = u32;
type Values = Vec<Option<i64>>;

#[derive(Default)]
pub(crate) struct Pool {
    pub expressions: Vec<String>,
    pub work: usize,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct Code {
    text: String,
    cost: usize,
}

impl Code {
    fn new(text: impl Into<String>, cost: usize) -> Self {
        Self {
            text: text.into(),
            cost,
        }
    }
    fn rank(&self) -> (usize, usize, &str) {
        (self.cost, self.text.len(), &self.text)
    }
}

#[derive(Clone)]
struct Feature {
    code: Code,
    values: Values,
}

#[derive(Default)]
struct Budget(usize);
impl Budget {
    fn take(&mut self) -> bool {
        if self.0 >= MAX_WORK {
            return false;
        }
        self.0 += 1;
        true
    }
}

fn keep(list: &mut Vec<Code>, cand: Code, cap: usize) {
    if list.iter().any(|c| c.text == cand.text) {
        return;
    }
    let p = list.partition_point(|c| c.rank() <= cand.rank());
    if p < cap {
        list.insert(p, cand);
        list.truncate(cap);
    }
}

struct Data {
    target: Vec<i64>,
    flag: bool,
    all: Mask,
    leaves: HashMap<Mask, Vec<Code>>,
    guards: HashMap<(Mask, Mask), Vec<Code>>,
    work: Budget,
}

impl Data {
    fn leaf(&mut self, code: Code, values: &[Option<i64>]) {
        if !self.work.take() {
            return;
        }
        let mask = values
            .iter()
            .zip(&self.target)
            .enumerate()
            .fold(0, |m, (i, (&x, &y))| m | (u32::from(x == Some(y)) << i));
        if mask != 0 {
            keep(self.leaves.entry(mask).or_default(), code, 6);
        }
    }
    fn guard(&mut self, code: Code, values: &[Option<bool>]) {
        if !self.work.take() {
            return;
        }
        let mut valid = 0;
        let mut yes = 0;
        for (i, v) in values.iter().enumerate() {
            if let Some(b) = v {
                valid |= 1 << i;
                yes |= u32::from(*b) << i;
            }
        }
        if yes == 0 || yes == valid {
            return;
        }
        if self.flag {
            let mask = values
                .iter()
                .zip(&self.target)
                .enumerate()
                .fold(0, |m, (i, (&v, &y))| {
                    m | (u32::from(v.map(i64::from) == Some(y)) << i)
                });
            if mask != 0 {
                keep(self.leaves.entry(mask).or_default(), code.clone(), 6);
            }
            let neg = valid & !mask;
            if neg != 0 {
                keep(
                    self.leaves.entry(neg).or_default(),
                    Code::new(format!("(!{})", code.text), 1 + code.cost),
                    6,
                );
            }
        }
        keep(self.guards.entry((yes, valid)).or_default(), code, 2);
    }
}

fn scalar(code: Code, values: Vec<&Value>, features: &mut Vec<Feature>, data: &mut Data) {
    if !data.work.take() {
        return;
    }
    match values[0] {
        Value::Int(_) => {
            let xs = values
                .iter()
                .map(|v| match v {
                    Value::Int(n) => Some(*n),
                    _ => None,
                })
                .collect();
            features.push(Feature { code, values: xs });
        }
        Value::Bool(_) => {
            let xs: Vec<_> = values
                .iter()
                .map(|v| match v {
                    Value::Bool(b) => Some(*b),
                    _ => None,
                })
                .collect();
            data.guard(code.clone(), &xs);
            features.push(Feature {
                code: Code::new(format!("({} as I64)", code.text), code.cost + 1),
                values: xs.into_iter().map(|x| x.map(i64::from)).collect(),
            });
        }
        Value::Enum(tag) => {
            let mut tags = Vec::new();
            for v in &values {
                if let Value::Enum(t) = v
                    && !tags.contains(&t.1)
                {
                    tags.push(t.1.clone());
                }
            }
            for variant in tags {
                let xs: Vec<_> = values
                    .iter()
                    .map(|v| Some(matches!(v,Value::Enum(t) if t.1==variant)))
                    .collect();
                data.guard(
                    Code::new(
                        format!("({} == {}::{variant})", code.text, tag.0),
                        code.cost + 2,
                    ),
                    &xs,
                );
            }
        }
        _ => {}
    }
}

fn features(hole: &Hole, rows: &[Example], data: &mut Data) -> (Vec<Feature>, usize) {
    let mut v = vec![];
    let mut cols = 0;
    for (i, (name, _)) in hole.locals.iter().enumerate() {
        if cols >= 16 {
            break;
        }
        let Some(first) = rows[0].locals.get(i) else {
            continue;
        };
        if let Value::Record(record) = first {
            for (j, (f, _)) in record.1.iter().enumerate() {
                if cols >= 16 {
                    break;
                }
                let xs: Option<Vec<_>> = rows
                    .iter()
                    .map(|r| match r.locals.get(i)? {
                        Value::Record(rr) => Some(&rr.1.get(j)?.1),
                        _ => None,
                    })
                    .collect();
                if let Some(xs) = xs {
                    scalar(Code::new(format!("{name}.{f}"), 2), xs, &mut v, data);
                    cols += 1;
                }
            }
        } else if let Some(xs) = rows
            .iter()
            .map(|r| r.locals.get(i))
            .collect::<Option<Vec<_>>>()
        {
            scalar(Code::new(name, 1), xs, &mut v, data);
            cols += 1;
        }
    }
    let n = v.len();
    let mut seen: HashSet<_> = v.iter().map(|t| t.values.clone()).collect();
    for i in 0..n.min(8) {
        for j in 0..i {
            for op in ["+", "-", "reverse", "min", "max", "*"] {
                if v.len() >= 64 || !data.work.take() {
                    break;
                }
                let (a, b) = if op == "reverse" {
                    (&v[j], &v[i])
                } else {
                    (&v[i], &v[j])
                };
                let values: Values = a
                    .values
                    .iter()
                    .zip(&b.values)
                    .map(|(&x, &y)| {
                        let (x, y) = (x?, y?);
                        match op {
                            "+" => x.checked_add(y),
                            "-" | "reverse" => x.checked_sub(y),
                            "*" => x.checked_mul(y),
                            "min" => Some(x.min(y)),
                            _ => Some(x.max(y)),
                        }
                    })
                    .collect();
                if !seen.insert(values.clone()) {
                    continue;
                }
                let text = if matches!(op, "min" | "max") {
                    format!("{op}({}, {})", a.code.text, b.code.text)
                } else {
                    format!(
                        "({} {} {})",
                        a.code.text,
                        if op == "reverse" { "-" } else { op },
                        b.code.text
                    )
                };
                let cost = 1 + a.code.cost + b.code.cost;
                v.push(Feature {
                    code: Code::new(text, cost),
                    values,
                });
            }
        }
    }
    (v, n)
}

fn predicates(v: &[Feature], original: usize, data: &mut Data) {
    for (i, t) in v.iter().enumerate() {
        let mut cuts = vec![];
        for &n in t.values.iter().flatten() {
            cuts.push(n);
            if let Some(k) = n.checked_sub(1) {
                cuts.push(k);
            }
        }
        cuts.extend([0, 1, -1]);
        cuts.sort_by_key(|x| (x.unsigned_abs(), *x));
        cuts.dedup();
        for k in cuts.into_iter().take(if i < original { 64 } else { 24 }) {
            for op in ["<=", "=="] {
                let values: Vec<_> = t
                    .values
                    .iter()
                    .map(|v| v.map(|x| if op == "==" { x == k } else { x <= k }))
                    .collect();
                data.guard(
                    Code::new(format!("({} {op} {k})", t.code.text), t.code.cost + 2),
                    &values,
                );
            }
        }
        for s in v.iter().take(original.min(8)) {
            if s.code.text == t.code.text {
                continue;
            }
            for op in ["<", "<=", "=="] {
                let values: Vec<_> = t
                    .values
                    .iter()
                    .zip(&s.values)
                    .map(|(&a, &b)| {
                        let (a, b) = (a?, b?);
                        Some(match op {
                            "<" => a < b,
                            "<=" => a <= b,
                            _ => a == b,
                        })
                    })
                    .collect();
                data.guard(
                    Code::new(
                        format!("({} {op} {})", t.code.text, s.code.text),
                        1 + t.code.cost + s.code.cost,
                    ),
                    &values,
                );
            }
        }
    }
}

fn affine(t: &Feature, scale: i64, offset: i64) -> Code {
    let mut text = t.code.text.clone();
    let mut cost = t.code.cost;
    if scale == -1 {
        text = format!("(-{text})");
        cost += 1;
    } else if scale != 1 {
        text = format!("({text} * {scale})");
        cost += 2;
    }
    if offset != 0 {
        text = format!("({text} + {offset})");
        cost += 2;
    }
    Code::new(text, cost)
}

fn leaves(v: &[Feature], original: usize, data: &mut Data) {
    if data.flag {
        for (b, t) in [(0, "false"), (1, "true")] {
            data.leaf(Code::new(t, 1), &vec![Some(b); data.target.len()]);
        }
        return;
    }
    let mut constants = data.target.clone();
    constants.extend([0, 1, -1]);
    constants.sort();
    constants.dedup();
    for n in constants {
        data.leaf(
            Code::new(n.to_string(), 1),
            &vec![Some(n); data.target.len()],
        );
    }
    for t in v {
        data.leaf(t.code.clone(), &t.values);
    }
    for t in v.iter().take((original + 8).min(20)) {
        let mut fitted = HashSet::new();
        for i in 0..t.values.len() {
            let Some(x) = t.values[i] else {
                continue;
            };
            let z = data.target[i];
            // Translation through one observation is a cheap one-parameter fit.
            if let Some(offset) = z.checked_sub(x) {
                fitted.insert((1, offset));
            }
            for j in 0..i {
                if !data.work.take() {
                    return;
                }
                let Some(y) = t.values[j] else {
                    continue;
                };
                if y == x {
                    continue;
                }
                let dx = i128::from(x) - i128::from(y);
                let dz = i128::from(z) - i128::from(data.target[j]);
                if dz % dx != 0 {
                    continue;
                }
                let Ok(m) = i64::try_from(dz / dx) else {
                    continue;
                };
                if m == 0 {
                    continue;
                }
                if let Ok(k) = i64::try_from(i128::from(z) - i128::from(m) * i128::from(x)) {
                    fitted.insert((m, k));
                }
            }
        }
        let mut fits: Vec<_> = fitted.into_iter().collect();
        fits.sort_by_key(|&(m, k)| (m != 1, k != 0, m.unsigned_abs(), k.unsigned_abs(), m, k));
        for (m, k) in fits.into_iter().take(96) {
            let xs: Vec<_> = t
                .values
                .iter()
                .map(|&x| x?.checked_mul(m)?.checked_add(k))
                .collect();
            data.leaf(affine(t, m, k), &xs);
        }
    }
}

struct Leaf {
    mask: Mask,
    code: Code,
}
struct Guard {
    yes: Mask,
    valid: Mask,
    code: Code,
}
struct Solver {
    leaves: Vec<Leaf>,
    guards: Vec<Guard>,
    // For an exact leaf, it suffices to scan leaves covering any one hard row.
    covering: Vec<Vec<usize>>,
    direct: HashMap<Mask, Vec<Code>>,
    cache: HashMap<(Mask, usize), Vec<Code>>,
    flag: bool,
    work: Budget,
}

impl Solver {
    fn matching(&mut self, mask: Mask) -> Vec<Code> {
        if let Some(codes) = self.direct.get(&mask) {
            return codes.clone();
        }
        let i = (0..self.covering.len())
            .filter(|i| mask & (1 << i) != 0)
            .min_by_key(|i| self.covering[*i].len())
            .unwrap();
        let mut found: Vec<Code> = vec![];
        for &id in &self.covering[i] {
            if !self.work.take() {
                break;
            }
            let l = &self.leaves[id];
            if !found.is_empty() && l.code.cost > found[0].cost {
                break;
            }
            if l.mask & mask == mask {
                keep(&mut found, l.code.clone(), 4);
            }
        }
        self.direct.insert(mask, found.clone());
        found
    }

    fn solve(&mut self, mask: Mask, depth: usize, root: bool) -> Vec<Code> {
        if let Some(hit) = self.cache.get(&(mask, depth)) {
            return hit.clone();
        }
        let mut choices = self.matching(mask);
        let cap = if root { MAX_ROOTS } else { 4 };
        if depth == 0 || choices.first().is_some_and(|c| c.cost <= 1) || !self.work.take() {
            return choices;
        }
        let mut ranked = vec![];
        // Keep an equally cheap alternative for a split. Two thresholds can
        // agree on the public rows and disagree in the gap between observations.
        let mut splits = HashMap::<(Mask, Mask), (usize, Option<(usize, Mask)>)>::new();
        for i in 0..self.guards.len() {
            if !self.work.take() {
                break;
            }
            let g = &self.guards[i];
            let left = mask & g.yes;
            let right = mask & !g.yes;
            if mask & !g.valid != 0 || left == 0 || right == 0 {
                continue;
            }
            let key = (left.min(right), left.max(right));
            let gcost = g.code.cost;
            if let Some((cost, alt)) = splits.get_mut(&key) {
                if *cost == gcost && alt.is_none() {
                    *alt = Some((i, left));
                    let lhs = self.matching(left);
                    let rhs = self.matching(right);
                    self.join(i, &lhs, &rhs, &mut choices, cap);
                }
                continue;
            }
            splits.insert(key, (gcost, None));
            let lhs = self.matching(left);
            let rhs = self.matching(right);
            let gaps = usize::from(lhs.is_empty()) + usize::from(rhs.is_empty());
            let unfitted = if lhs.is_empty() { left.count_ones() } else { 0 }
                + if rhs.is_empty() {
                    right.count_ones()
                } else {
                    0
                };
            let estimate =
                gcost + lhs.first().map_or(4, |a| a.cost) + rhs.first().map_or(4, |b| b.cost);
            ranked.push((
                (
                    gaps,
                    unfitted,
                    estimate,
                    std::cmp::Reverse(left.count_ones().min(right.count_ones())),
                    i,
                ),
                i,
                left,
                right,
            ));
            self.join(i, &lhs, &rhs, &mut choices, cap);
        }
        ranked.sort_by_key(|e| e.0);
        if depth > 1 {
            for (_, i, left, right) in ranked.into_iter().take(if root { 18 } else { 8 }) {
                if !self.work.take() {
                    break;
                }
                let a = self.solve(left, depth - 1, false);
                if a.is_empty() {
                    continue;
                }
                let b = self.solve(right, depth - 1, false);
                self.join(i, &a, &b, &mut choices, cap);
                if let Some((j, alt_left)) = splits[&(left.min(right), left.max(right))].1 {
                    let (lhs, rhs) = if left == alt_left { (&a, &b) } else { (&b, &a) };
                    self.join(j, lhs, rhs, &mut choices, cap);
                }
            }
        }
        self.cache.insert((mask, depth), choices.clone());
        choices
    }
    fn join(&mut self, i: usize, a: &[Code], b: &[Code], out: &mut Vec<Code>, cap: usize) {
        let g = &self.guards[i].code;
        for x in a.iter().take(3) {
            for y in b.iter().take(3) {
                if !self.work.take() {
                    return;
                }
                if x.text == y.text {
                    continue;
                }
                let code = if self.flag && x.text == "true" && y.text == "false" {
                    g.clone()
                } else if self.flag && x.text == "false" && y.text == "true" {
                    Code::new(format!("(!{})", g.text), g.cost + 1)
                } else if self.flag && x.text == "true" {
                    Code::new(format!("({} || {})", g.text, y.text), g.cost + y.cost + 1)
                } else if self.flag && y.text == "false" {
                    Code::new(format!("({} && {})", g.text, x.text), g.cost + x.cost + 1)
                } else {
                    Code::new(
                        format!("if {} {{ {} }} else {{ {} }}", g.text, x.text, y.text),
                        1 + g.cost + x.cost + y.cost,
                    )
                };
                keep(out, code, cap);
            }
        }
    }
}

pub(crate) fn candidates(hole: &Hole, rows: &[Example]) -> Pool {
    if !matches!(hole.ty, Type::Bool | Type::I64) || rows.is_empty() {
        return Pool::default();
    }
    let rows = &rows[..rows.len().min(MAX_ROWS)];
    let mut data = Data {
        target: rows.iter().map(|r| r.answer).collect(),
        flag: hole.ty == Type::Bool,
        all: u32::MAX >> (32 - rows.len()),
        leaves: HashMap::new(),
        guards: HashMap::new(),
        work: Budget::default(),
    };
    let (v, n) = features(hole, rows, &mut data);
    predicates(&v, n, &mut data);
    leaves(&v, n, &mut data);
    let mut leaves: Vec<_> = data
        .leaves
        .into_iter()
        .flat_map(|(mask, codes)| codes.into_iter().map(move |code| Leaf { mask, code }))
        .collect();
    leaves.sort_by(|a, b| a.code.rank().cmp(&b.code.rank()));
    let mut guards: Vec<_> = data
        .guards
        .into_iter()
        .flat_map(|((yes, valid), cs)| cs.into_iter().map(move |code| Guard { yes, valid, code }))
        .collect();
    guards.sort_by(|a, b| a.code.rank().cmp(&b.code.rank()));
    let mut covering = vec![vec![]; rows.len()];
    'index: for (id, leaf) in leaves.iter().enumerate() {
        let mut mask = leaf.mask;
        while mask != 0 {
            if !data.work.take() {
                break 'index;
            }
            covering[mask.trailing_zeros() as usize].push(id);
            mask &= mask - 1;
        }
    }
    let mut s = Solver {
        leaves,
        guards,
        covering,
        direct: HashMap::new(),
        cache: HashMap::new(),
        flag: data.flag,
        work: data.work,
    };
    let answers = s
        .solve(data.all, MAX_DEPTH, true)
        .into_iter()
        .map(|x| x.text)
        .collect();
    Pool {
        expressions: answers,
        work: s.work.0,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{check, interpreter, syntax};

    fn sketch() -> Hole {
        Hole {
            name: "value".into(),
            function: "f".into(),
            span: Default::default(),
            ty: Type::I64,
            locals: vec![("n".into(), Type::I64), ("flag".into(), Type::Bool)],
        }
    }

    fn row(n: i64, flag: bool, answer: i64) -> Example {
        Example {
            locals: vec![Value::Int(n), Value::Bool(flag)],
            answer,
        }
    }

    fn replay(pool: &Pool, rows: &[Example], probe: &[Value]) -> HashSet<i64> {
        assert!(!pool.expressions.is_empty() && pool.expressions.len() <= MAX_ROOTS);
        assert!(pool.work > 0 && pool.work <= MAX_WORK);
        let mut outputs = HashSet::new();
        for expr in &pool.expressions {
            let source = format!(
                "module t; fn f(n:I64,flag:Bool)->I64 !{{}} {{return {expr};}} pub fn main()->I64 !{{}} {{return 0;}}"
            );
            let module = syntax::parse(&source).unwrap();
            check::check(&module).unwrap();
            for r in rows {
                let actual = interpreter::invoke(&module, "f", r.locals.clone(), 5000, &mut ());
                assert_eq!(actual.unwrap(), Value::Int(r.answer), "{expr}");
            }
            if let Ok(Value::Int(out)) =
                interpreter::invoke(&module, "f", probe.to_vec(), 5000, &mut ())
            {
                outputs.insert(out);
            }
        }
        outputs
    }

    #[test]
    fn branches_replay_distinct_affine_rules_with_bounded_deterministic_work() {
        let mut rows = vec![];
        for n in -3..=3 {
            for flag in [false, true] {
                rows.push(row(n, flag, if flag { 2 * n + 3 } else { n - 4 }));
            }
        }
        let pool = candidates(&sketch(), &rows);
        let again = candidates(&sketch(), &rows);
        assert_eq!(
            (&pool.expressions, pool.work),
            (&again.expressions, again.work)
        );
        let out = replay(&pool, &rows, &[Value::Int(10), Value::Bool(true)]);
        assert!(out.contains(&23));
    }

    #[test]
    fn distinct_thresholds_survive_an_unobserved_interval() {
        let rows = [
            row(0, false, 2),
            row(1, false, 2),
            row(5, false, 9),
            row(6, false, 9),
        ];
        let pool = candidates(&sketch(), &rows);
        let out = replay(&pool, &rows, &[Value::Int(3), Value::Bool(false)]);
        assert!(out.contains(&2) && out.contains(&9), "{out:?}");
    }
}
