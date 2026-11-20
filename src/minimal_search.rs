//! Bounded bottom-up synthesis for sampled scalar input/output relations.
//! A semantic vector is an index into the search. Only the caller's normal
//! checker and verifier decide whether an expression may be published.
use crate::check::Hole;
use crate::guided_search::Example;
use crate::interpreter::Value;
use crate::syntax::Type;
use std::collections::{HashMap, HashSet};
use std::rc::Rc;

const WORK: usize = 120_000;
const MAX_SIZE: usize = 11;
const WIDTH: usize = 192;
const EXTRA: usize = 6;
type Cell = Option<i64>;
type Vector = Rc<[Cell]>;

#[derive(Default)]
pub(crate) struct Pool {
    pub expressions: Vec<String>,
    pub vectors: usize,
}

#[derive(Clone)]
struct Term {
    text: Rc<str>,
    constant: bool,
    flag: bool,
    cost: usize,
    values: Vector,
    matches: u32,
    above: bool,
    below: bool,
}

#[derive(Copy, Clone, PartialEq, Eq)]
enum Op {
    Add,
    Sub,
    Mul,
    Div,
    Rem,
    Min,
    Max,
    Lt,
    Le,
    Eq,
    Ne,
    And,
    Or,
}

impl Op {
    fn apply(self, x: Cell, y: Cell) -> Cell {
        let x = x?;
        if self == Self::And && x == 0 {
            return Some(0);
        }
        if self == Self::Or && x != 0 {
            return Some(1);
        }
        let y = y?;
        Some(match self {
            Self::Add => x.checked_add(y)?,
            Self::Sub => x.checked_sub(y)?,
            Self::Mul => x.checked_mul(y)?,
            Self::Div => x.checked_div(y)?,
            Self::Rem if y != 0 => x.wrapping_rem(y),
            Self::Rem => return None,
            Self::Min => x.min(y),
            Self::Max => x.max(y),
            Self::Lt => i64::from(x < y),
            Self::Le => i64::from(x <= y),
            Self::Eq => i64::from(x == y),
            Self::Ne => i64::from(x != y),
            Self::And | Self::Or => y,
        })
    }
    fn flag(self) -> bool {
        matches!(
            self,
            Self::Lt | Self::Le | Self::Eq | Self::Ne | Self::And | Self::Or
        )
    }
    fn symmetric(self) -> bool {
        matches!(
            self,
            Self::Add | Self::Mul | Self::Min | Self::Max | Self::Eq | Self::Ne
        )
    }
    fn text(self, a: &str, b: &str) -> String {
        let op = match self {
            Self::Min => return format!("min({a}, {b})"),
            Self::Max => return format!("max({a}, {b})"),
            Self::Add => "+",
            Self::Sub => "-",
            Self::Mul => "*",
            Self::Div => "/",
            Self::Rem => "%",
            Self::Lt => "<",
            Self::Le => "<=",
            Self::Eq => "==",
            Self::Ne => "!=",
            Self::And => "&&",
            Self::Or => "||",
        };
        format!("({a} {op} {b})")
    }
}

struct Bank<'a> {
    target: &'a [i64],
    flag: bool,
    all: u32,
    seen: HashMap<(bool, Vector), usize>,
    // Preserve alternative minimal results when they disagree on the extra
    // input environments. They are still checked and probed in the real module.
    solutions: HashMap<Vector, (usize, String)>,
    terms: Vec<Term>,
    levels: Vec<Vec<usize>>,
    vectors: usize,
}

impl Bank<'_> {
    fn insert(
        &mut self,
        flag: bool,
        cost: usize,
        values: Vec<Cell>,
        render: impl FnOnce() -> String,
    ) {
        self.vectors += 1;
        let mut mask = 0;
        let mut above = true;
        let mut below = true;
        for (i, (&v, &t)) in values.iter().zip(self.target).enumerate() {
            mask |= u32::from(v == Some(t)) << i;
            above &= v.is_some_and(|n| n >= t);
            below &= v.is_some_and(|n| n <= t);
        }
        let correct = flag == self.flag && mask == self.all;
        if !correct
            && (self.levels[cost].len() >= WIDTH * 4
                || values[..self.target.len()].iter().all(Option::is_none))
        {
            return;
        }
        let vector: Vector = values.into();
        let key = (flag, vector.clone());
        if !correct && self.seen.get(&key).is_some_and(|k| *k <= cost) {
            return;
        }
        let text = render();
        if correct {
            let rank = |v: &(usize, String)| (v.0, v.1.len());
            let incoming = (cost, text.clone());
            if self.solutions.len() >= 128 && !self.solutions.contains_key(&vector) {
                // Bound retained alternatives independently of input agreement.
                // Tie-break by expression text to keep the table deterministic.
                let (key, worst) = self
                    .solutions
                    .iter()
                    .max_by(|(_, a), (_, b)| rank(a).cmp(&rank(b)).then(a.1.cmp(&b.1)))
                    .unwrap();
                if rank(&incoming)
                    .cmp(&rank(worst))
                    .then(incoming.1.cmp(&worst.1))
                    .is_lt()
                {
                    let key = key.clone();
                    self.solutions.remove(&key);
                }
            }
            if self.solutions.len() < 128 || self.solutions.contains_key(&vector) {
                let entry = self
                    .solutions
                    .entry(vector.clone())
                    .or_insert_with(|| incoming.clone());
                if rank(&incoming)
                    .cmp(&rank(entry))
                    .then(incoming.1.cmp(&entry.1))
                    .is_lt()
                {
                    *entry = incoming;
                }
            }
        }
        if self.levels[cost].len() < WIDTH * 4 && self.seen.get(&key).is_none_or(|k| *k > cost) {
            self.seen.insert(key, cost);
            let id = self.terms.len();
            self.terms.push(Term {
                text: text.into(),
                constant: vector.iter().all(|v| v == &vector[0]),
                flag,
                cost,
                values: vector,
                matches: mask,
                above,
                below,
            });
            self.levels[cost].push(id);
        }
    }

    fn pair(&mut self, op: Op, a: usize, b: usize) {
        if self.vectors >= WORK {
            return;
        }
        let (a, b) = (&self.terms[a], &self.terms[b]);
        if a.constant && b.constant {
            return;
        }
        let cost = 1 + a.cost + b.cost;
        if cost > MAX_SIZE {
            return;
        }
        let values = a
            .values
            .iter()
            .zip(&*b.values)
            .map(|(&x, &y)| op.apply(x, y))
            .collect();
        let (left, right) = (a.text.clone(), b.text.clone());
        self.insert(op.flag(), cost, values, || op.text(&left, &right));
    }

    fn unary(&mut self, level: usize, stop: usize) {
        for id in self.levels[level - 1].clone() {
            if self.vectors >= stop {
                break;
            }
            let t = &self.terms[id];
            if t.flag {
                let text = format!("(!{})", t.text);
                let cast = format!("({} as I64)", t.text);
                let values = t.values.to_vec();
                self.insert(
                    true,
                    level,
                    values.iter().map(|v| v.map(|n| 1 - n)).collect(),
                    || text,
                );
                if self.vectors < stop {
                    self.insert(false, level, values, || cast);
                }
            } else {
                let text = format!("(-{})", t.text);
                let values = t
                    .values
                    .iter()
                    .map(|v| v.and_then(i64::checked_neg))
                    .collect();
                self.insert(false, level, values, || text);
            }
        }
    }

    fn layer(&mut self, cost: usize, stop: usize) {
        self.unary(cost, (self.vectors + WIDTH * 2).min(stop));
        let int_ops = [
            Op::Add,
            Op::Sub,
            Op::Min,
            Op::Max,
            Op::Mul,
            Op::Rem,
            Op::Div,
            Op::Lt,
            Op::Le,
            Op::Eq,
            Op::Ne,
        ];
        let bool_ops = [Op::Ne, Op::And, Op::Or, Op::Eq];
        // Alternate size partitions and traverse each operand grid diagonally.
        // Chaining with an atom and combining two compound children both get work.
        let halves: Vec<_> = (1..=(cost - 1) / 2)
            .map(|l| (self.levels[l].clone(), self.levels[cost - 1 - l].clone()))
            .collect();
        for diagonal in 0..WIDTH * 2 {
            for (left, right) in &halves {
                let start = diagonal.saturating_sub(right.len().saturating_sub(1));
                for (i, &a) in left.iter().enumerate().take(diagonal + 1).skip(start) {
                    let Some(&b) = right.get(diagonal - i) else {
                        continue;
                    };
                    if self.terms[a].flag != self.terms[b].flag
                        || (self.terms[a].cost == self.terms[b].cost && a > b)
                    {
                        continue;
                    }
                    let ops = if self.terms[a].flag {
                        &bool_ops[..]
                    } else {
                        &int_ops[..]
                    };
                    for &op in ops {
                        if self.vectors >= stop {
                            return;
                        }
                        self.pair(op, a, b);
                        if !op.symmetric() && a != b && self.vectors < stop {
                            self.pair(op, b, a);
                        }
                    }
                }
            }
        }
    }

    fn prioritize(&mut self, cost: usize) {
        // Retain representatives by goal-match mask as well as insertion order.
        // A rare partial result can be the entire answer on one side of a guard.
        let layer = &mut self.levels[cost];
        if layer.len() <= WIDTH {
            return;
        }
        let mut ranked = layer.clone();
        ranked.sort_by_key(|&id| {
            let t = &self.terms[id];
            (std::cmp::Reverse(t.matches.count_ones()), id)
        });
        let mut masks = HashSet::new();
        let mut kept: Vec<_> = ranked
            .into_iter()
            .filter(|&id| {
                let t = &self.terms[id];
                masks.insert((t.flag, t.matches))
            })
            .take(WIDTH / 2)
            .collect();
        for &id in layer.iter() {
            if kept.len() == WIDTH {
                break;
            }
            if !kept.contains(&id) {
                kept.push(id);
            }
        }
        *layer = kept;
    }

    fn joins(&mut self, stop: usize) {
        let mut choices: Vec<_> = self
            .levels
            .iter()
            .flatten()
            .copied()
            .filter(|&id| self.terms[id].flag == self.flag && self.terms[id].matches != 0)
            .collect();
        choices.sort_by_key(|&id| {
            (
                self.terms[id].cost,
                std::cmp::Reverse(self.terms[id].matches.count_ones()),
                id,
            )
        });
        // One cheap representative for each matching subset and direction.
        let mut masks = HashSet::new();
        choices.retain(|&id| {
            let t = &self.terms[id];
            masks.insert((t.matches, t.above, t.below))
        });
        choices.truncate(192);
        if !self.flag {
            for (i, &a) in choices.iter().enumerate() {
                for &b in &choices[..i] {
                    if self.vectors >= stop {
                        return;
                    }
                    let (x, y) = (&self.terms[a], &self.terms[b]);
                    if (x.matches | y.matches) != self.all || 1 + x.cost + y.cost > MAX_SIZE {
                        continue;
                    }
                    if x.above && y.above {
                        self.pair(Op::Min, a, b);
                    } else if x.below && y.below {
                        self.pair(Op::Max, a, b);
                    }
                }
            }
        }
        let mut guards = HashSet::new();
        let conditions: Vec<_> = self
            .levels
            .iter()
            .flatten()
            .copied()
            .filter_map(|id| {
                let g = &self.terms[id];
                if !g.flag {
                    return None;
                }
                let mut mask = 0;
                for (i, &v) in g.values[..self.target.len()].iter().enumerate() {
                    mask |= u32::from(v? != 0) << i;
                }
                (mask != 0 && mask != self.all && guards.insert(mask)).then_some((id, mask))
            })
            .take(128)
            .collect();
        for (g, mask) in conditions {
            let yes: Vec<_> = choices
                .iter()
                .copied()
                .filter(|&id| self.terms[id].matches & mask == mask)
                .take(3)
                .collect();
            let no: Vec<_> = choices
                .iter()
                .copied()
                .filter(|&id| self.terms[id].matches & !mask & self.all == (!mask & self.all))
                .take(3)
                .collect();
            for &a in &yes {
                for &b in &no {
                    if self.vectors >= stop {
                        return;
                    }
                    let (c, x, y) = (&self.terms[g], &self.terms[a], &self.terms[b]);
                    let cost = 1 + c.cost + x.cost + y.cost;
                    if cost > MAX_SIZE {
                        continue;
                    }
                    let text = format!("if {} {{ {} }} else {{ {} }}", c.text, x.text, y.text);
                    let values = c
                        .values
                        .iter()
                        .zip(&*x.values)
                        .zip(&*y.values)
                        .map(|((&test, &yes), &no)| if test? != 0 { yes } else { no })
                        .collect();
                    self.insert(self.flag, cost, values, || text);
                }
            }
        }
    }
}

fn side_number(column: usize, row: usize) -> i64 {
    const VALUES: [i64; 10] = [-2, 0, 1, 3, -1, 7, 2, 11, i64::MAX, i64::MIN];
    match row {
        0 => column as i64 + 2,
        1 => -(column as i64 + 1),
        _ => VALUES[(column * 3 + row * (2 * column + 1)) % VALUES.len()],
    }
}

fn seed_column(bank: &mut Bank<'_>, name: String, cost: usize, values: Vec<&Value>, column: usize) {
    match values[0] {
        Value::Int(_) | Value::Bool(_) => {
            let flag = matches!(values[0], Value::Bool(_));
            let mut data: Vec<_> = values
                .iter()
                .map(|v| match v {
                    Value::Int(n) => Some(*n),
                    Value::Bool(b) => Some(i64::from(*b)),
                    _ => None,
                })
                .collect();
            for i in 0..EXTRA {
                data.push(Some(if flag {
                    i64::from((((column * 17 + 9) % 61 + 1) >> i) & 1 != 0)
                } else {
                    side_number(column, i)
                }));
            }
            bank.insert(flag, cost, data, || name);
        }
        Value::Enum(e) => {
            let mut tags = Vec::new();
            for v in &values {
                if let Value::Enum(v) = v
                    && !tags.contains(&v.1)
                {
                    tags.push(v.1.clone());
                }
            }
            for (j, tag) in tags.iter().enumerate() {
                let mut data: Vec<_> = values
                    .iter()
                    .map(|v| Some(i64::from(matches!(v,Value::Enum(t) if t.1==*tag))))
                    .collect();
                for i in 0..EXTRA {
                    data.push(Some(i64::from((i + column) % tags.len() == j)));
                }
                bank.insert(true, cost + 2, data, || {
                    format!("({name} == {}::{tag})", e.0)
                });
            }
        }
        _ => {}
    }
}

pub(crate) fn candidates(hole: &Hole, rows: &[Example]) -> Pool {
    if rows.is_empty() || !matches!(hole.ty, Type::I64 | Type::Bool) {
        return Pool::default();
    }
    let rows = &rows[..rows.len().min(32)];
    let target: Vec<_> = rows.iter().map(|r| r.answer).collect();
    let n = rows.len();
    let mut bank = Bank {
        target: &target,
        flag: hole.ty == Type::Bool,
        all: u32::MAX >> (32 - n),
        seen: HashMap::new(),
        solutions: HashMap::new(),
        terms: vec![],
        levels: vec![vec![]; MAX_SIZE + 1],
        vectors: 0,
    };
    let mut column = 0;
    for (i, (name, _)) in hole.locals.iter().enumerate() {
        if column >= 24 {
            break;
        }
        let Some(value) = rows[0].locals.get(i) else {
            return Pool::default();
        };
        if let Value::Record(r) = value {
            for (field, (f, _)) in r.1.iter().enumerate() {
                if column >= 24 {
                    break;
                }
                let vs: Option<Vec<_>> = rows
                    .iter()
                    .map(|row| match row.locals.get(i)? {
                        Value::Record(r) => Some(&r.1.get(field)?.1),
                        _ => None,
                    })
                    .collect();
                if let Some(vs) = vs {
                    seed_column(&mut bank, format!("{name}.{f}"), 2, vs, column);
                    column += 1;
                }
            }
        } else {
            let Some(vs) = rows
                .iter()
                .map(|r| r.locals.get(i))
                .collect::<Option<Vec<_>>>()
            else {
                return Pool::default();
            };
            seed_column(&mut bank, name.clone(), 1, vs, column);
            column += 1;
        }
    }
    let mut integers = vec![0, 1, 2, -1, 3];
    let mut vocab = Vec::new();
    for row in rows {
        if !bank.flag {
            vocab.push(row.answer);
        }
        vocab.extend(row.locals.iter().filter_map(|v| match v {
            Value::Int(x) => Some(*x),
            _ => None,
        }));
    }
    if !bank.flag {
        if let Some(&hi) = target.iter().max()
            && let Some(cap) = hi.checked_add(1)
        {
            vocab.push(cap);
        }
        if let Some(&lo) = target.iter().min()
            && let Some(cap) = lo.checked_sub(1)
        {
            vocab.push(cap);
        }
    }
    vocab.sort_by_key(|x| (x.unsigned_abs(), *x));
    vocab.dedup();
    for n in vocab.into_iter().filter(|x| x.unsigned_abs() <= 64) {
        if !integers.contains(&n) {
            integers.push(n);
        }
        if integers.len() == 12 {
            break;
        }
    }
    if target.iter().all(|n| n == &target[0]) && !bank.flag && !integers.contains(&target[0]) {
        integers.push(target[0]);
    }
    for n in integers {
        bank.insert(false, 1, vec![Some(n); rows.len() + EXTRA], || {
            n.to_string()
        });
    }
    for (b, name) in [(0, "false"), (1, "true")] {
        bank.insert(true, 1, vec![Some(b); rows.len() + EXTRA], || name.into());
    }
    let budgets = [
        0, 0, 1200, 6500, 9000, 15_000, 15_000, 15_000, 14_000, 13_000, 12_000, 10_000,
    ];
    for (cost, quota) in budgets.into_iter().enumerate().skip(2) {
        let stop = (bank.vectors + quota).min(WORK);
        bank.layer(cost, stop);
        bank.prioritize(cost);
        bank.joins((bank.vectors + 512).min(WORK));
        let Some(best) = bank.solutions.values().map(|s| s.0).min() else {
            continue;
        };
        if cost >= best {
            break;
        }
    }
    let mut answers: Vec<_> = bank.solutions.into_values().collect();
    answers.sort_by(|(c, a), (d, b)| {
        c.cmp(d)
            .then_with(|| a.len().cmp(&b.len()))
            .then_with(|| a.cmp(b))
    });
    answers.truncate(64);
    Pool {
        expressions: answers.into_iter().map(|(_, s)| s).collect(),
        vectors: bank.vectors,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{check, interpreter, syntax};

    fn hole() -> Hole {
        Hole {
            name: "v".into(),
            function: "f".into(),
            ty: Type::I64,
            span: syntax::Span::default(),
            locals: vec![("a".into(), Type::I64), ("b".into(), Type::I64)],
        }
    }
    fn row(a: i64, b: i64, answer: i64) -> Example {
        Example {
            locals: vec![Value::Int(a), Value::Int(b)],
            answer,
        }
    }

    #[test]
    fn separate_inputs_retain_observable_alternatives() {
        let h = hole();
        let rows = [row(0, 0, 0), row(1, 1, 1)];
        let a = candidates(&h, &rows);
        let b = candidates(&h, &rows);
        assert_eq!(a.expressions, b.expressions);
        assert_eq!(a.vectors, b.vectors);
        assert!(a.expressions.contains(&"a".to_owned()));
        assert!(a.expressions.contains(&"b".to_owned()));
    }

    #[test]
    fn composes_two_nonterminal_children_and_replays_checked_semantics() {
        let mut rows = Vec::new();
        for a in -2..=2 {
            for b in -2..=2 {
                rows.push(row(a, b, (a - b) * (a + b)));
            }
        }
        let pool = candidates(&hole(), &rows);
        assert!(pool.vectors <= WORK);
        assert!(!pool.expressions.is_empty());
        let mut extrapolates = false;
        for expr in &pool.expressions {
            let text = format!(
                "module study; fn f(a:I64,b:I64)->I64 !{{}} {{return {expr};}} pub fn main()->I64 !{{}} {{return 0;}}"
            );
            let m = syntax::parse(&text).unwrap();
            check::check(&m).unwrap();
            for r in &rows {
                assert_eq!(
                    interpreter::invoke(&m, "f", r.locals.clone(), 1000, &mut ()).unwrap(),
                    Value::Int(r.answer),
                    "{expr}"
                );
            }
            extrapolates |= [(7, 4), (11, 10), (-3, 17)].iter().all(|&(a, b)| {
                interpreter::invoke(&m, "f", vec![Value::Int(a), Value::Int(b)], 1000, &mut ())
                    .unwrap()
                    == Value::Int((a - b) * (a + b))
            });
        }
        assert!(extrapolates);
    }

    #[test]
    fn arithmetic_faults_and_decisive_boolean_operands() {
        assert_eq!(Op::Add.apply(Some(i64::MAX), Some(1)), None);
        assert_eq!(Op::Div.apply(Some(i64::MIN), Some(-1)), None);
        assert_eq!(Op::Rem.apply(Some(i64::MIN), Some(-1)), Some(0));
        assert_eq!(Op::Rem.apply(Some(1), Some(0)), None);
        assert_eq!(Op::And.apply(Some(0), None), Some(0));
        assert_eq!(Op::Or.apply(Some(1), None), Some(1));
    }
}
