//! Type-directed candidate enumeration. The same operators can combine lexical
//! values, existing source expressions and a bounded frontier of new terms.
use crate::check::Hole;
use crate::edit;
use crate::syntax::{self, BinOp, Expr, ExprKind, Function, Module, Span, Type, TypeKind};
use std::collections::{HashMap, HashSet, VecDeque};

#[derive(Clone)]
struct Term {
    text: String,
    ty: Type,
    precedence: u8,
    variable: bool,
}

impl Term {
    fn atom(text: impl Into<String>, ty: Type, variable: bool) -> Self {
        Self {
            text: text.into(),
            ty,
            precedence: 9,
            variable,
        }
    }

    fn operand(&self, minimum: u8) -> String {
        if self.precedence < minimum {
            format!("({})", self.text)
        } else {
            self.text.clone()
        }
    }

    fn binary(op: BinOp, a: &Term, b: &Term, ty: Type) -> Self {
        let p = op.precedence();
        Self {
            text: format!("{} {op} {}", a.operand(p), b.operand(p + 1)),
            ty,
            precedence: p,
            variable: a.variable || b.variable,
        }
    }

    fn call(name: &str, args: &[&Term], ty: Type) -> Self {
        let args_text = args.iter().map(|t| t.text.as_str()).collect::<Vec<_>>();
        Self::atom(
            format!("{name}({})", args_text.join(", ")),
            ty,
            args.iter().any(|t| t.variable),
        )
    }
}

struct Pool {
    terms: Vec<Term>,
    names: HashSet<String>,
}

impl Pool {
    fn new() -> Self {
        Self {
            terms: Vec::new(),
            names: HashSet::new(),
        }
    }
    fn push(&mut self, term: Term) {
        if self.names.insert(term.text.clone()) {
            self.terms.push(term);
        }
    }
    fn of_type(&self, ty: Type) -> Vec<&Term> {
        self.terms.iter().filter(|t| t.ty == ty).take(32).collect()
    }
}

// Bound the syntax size of harvested subtrees, and check every free variable
// against the binding visible at the hole (a nested scope may shadow a name).
fn reusable(
    expr: &Expr,
    hole: &Hole,
    types: &HashMap<Span, Type>,
    remaining: &mut usize,
) -> Option<bool> {
    *remaining = remaining.checked_sub(1)?;
    let mut child = |e: &Expr| reusable(e, hole, types, remaining);
    Some(match &expr.kind {
        ExprKind::Hole(..) => return None,
        ExprKind::Name(n) => {
            if !hole
                .locals
                .iter()
                .any(|(name, ty)| name == n && Some(ty) == types.get(&expr.span))
            {
                return None;
            }
            true
        }
        ExprKind::Int(_) | ExprKind::Bool(_) | ExprKind::Unit | ExprKind::Variant(..) => false,
        ExprKind::Field(e, _) | ExprKind::Unary(_, e) | ExprKind::AsI64(e) => child(e)?,
        ExprKind::Binary(_, a, b) => child(a)? | child(b)?,
        ExprKind::If { cond, yes, no } => child(cond)? | child(yes)? | child(no)?,
        ExprKind::Call(name, args) => {
            if name == &hole.function || hole.locals.iter().any(|(local, _)| local == name) {
                return None;
            }
            let mut variable = false;
            for arg in args {
                variable |= child(arg)?;
            }
            variable
        }
    })
}

fn context(module: &Module, function: &Function, hole: &Hole, types: &HashMap<Span, Type>) -> Pool {
    let mut nodes = edit::expressions(function);
    nodes.sort_by_key(|e| (e.span.start.abs_diff(hole.span.start), e.span.start));
    let mut pool = Pool::new();
    for e in nodes {
        if pool.terms.len() >= 64 {
            break;
        }
        if e.span.end - e.span.start > 128
            || matches!(
                e.kind,
                ExprKind::Hole(..)
                    | ExprKind::Name(_)
                    | ExprKind::Field(..)
                    | ExprKind::Variant(..)
                    | ExprKind::Unit
            )
        {
            continue;
        }
        let Some(&ty) = types.get(&e.span) else {
            continue;
        };
        let Some(variable) = reusable(e, hole, types, &mut 9) else {
            continue;
        };
        let mut text = String::new();
        syntax::print_expr(module, e, 0, &mut text);
        let precedence = match e.kind {
            ExprKind::Binary(op, ..) => op.precedence(),
            ExprKind::If { .. } => 0,
            ExprKind::AsI64(_) => 7,
            ExprKind::Unary(..) => 8,
            _ => 9,
        };
        pool.push(Term {
            text,
            ty,
            precedence,
            variable,
        });
    }
    pool
}

fn vocabulary(module: &Module, hole: &Hole) -> Pool {
    let mut pool = Pool::new();
    for (name, ty) in &hole.locals {
        pool.push(Term::atom(name, *ty, true));
        if let Type::Named(id) = ty
            && let TypeKind::Record(fields) = &module.types[*id].kind
        {
            for field in fields.iter().take(48) {
                pool.push(Term::atom(format!("{name}.{}", field.name), field.ty, true));
            }
        }
        if pool.terms.len() >= 64 {
            break;
        }
    }
    for (i, decl) in module.types.iter().enumerate() {
        if hole.ty != Type::Named(i) && !pool.terms.iter().any(|t| t.ty == Type::Named(i)) {
            continue;
        }
        if let TypeKind::Enum(tags) = &decl.kind {
            for tag in tags.iter().take(32) {
                pool.push(Term::atom(
                    format!("{}::{tag}", decl.name),
                    Type::Named(i),
                    false,
                ));
            }
        }
    }
    for n in ["0", "1", "2", "-1"] {
        pool.push(Term::atom(n, Type::I64, false));
    }
    for b in ["false", "true"] {
        pool.push(Term::atom(b, Type::Bool, false));
    }
    pool.push(Term::atom("()", Type::Unit, false));
    pool
}

// Give each operation a turn. A long arithmetic Cartesian product can never
// exhaust the entire request before comparisons, calls or conditionals begin.
struct Lanes {
    streams: Vec<VecDeque<String>>,
    width: usize,
}
impl Lanes {
    fn add(&mut self, items: impl IntoIterator<Item = String>) {
        let stream: VecDeque<_> = items.into_iter().take(self.width).collect();
        if !stream.is_empty() {
            self.streams.push(stream);
        }
    }
    fn finish(mut self, seeds: impl IntoIterator<Item = String>) -> Vec<String> {
        let mut output = Vec::new();
        let mut seen = HashSet::new();
        for s in seeds {
            if seen.insert(s.clone()) {
                output.push(s);
            }
            if output.len() == self.width {
                return output;
            }
        }
        while !self.streams.is_empty() {
            for stream in &mut self.streams {
                while let Some(value) = stream.pop_front() {
                    if seen.insert(value.clone()) {
                        output.push(value);
                        break;
                    }
                }
                if output.len() == self.width {
                    return output;
                }
            }
            self.streams.retain(|s| !s.is_empty());
        }
        output
    }
}

// Diagonal traversal varies both operands before moving deep into either list.
fn pairs<'a>(a: &'a [&'a Term], b: &'a [&'a Term]) -> impl Iterator<Item = (&'a Term, &'a Term)> {
    (0..a.len() + b.len()).flat_map(move |sum| {
        (sum.saturating_sub(b.len().saturating_sub(1))..a.len().min(sum + 1))
            .filter_map(move |i| Some((a[i], *b.get(sum - i)?)))
    })
}

fn operands(local: &[&Term], nearby: &[&Term], derived: &[&Term]) -> Vec<Term> {
    let mut p = Pool::new();
    for t in nearby
        .iter()
        .filter(|t| t.variable && t.precedence < 9)
        .take(6)
    {
        p.push((**t).clone());
    }
    // Put new constants found in code beside the language's basic constants.
    for t in local.iter().chain(nearby).chain(derived) {
        p.push((**t).clone());
    }
    p.terms.truncate(36);
    p.terms
}

fn frontier(bindings: &Pool, source: &Pool) -> Pool {
    let mut result = Pool::new();
    let ints = bindings.of_type(Type::I64);
    let variables: Vec<_> = ints.iter().copied().filter(|t| t.variable).collect();
    let one = Term::atom("1", Type::I64, false);
    for v in &variables {
        for op in [BinOp::Add, BinOp::Sub] {
            result.push(Term::binary(op, v, &one, Type::I64));
        }
    }
    for (a, b) in pairs(&variables, &variables)
        .filter(|(a, b)| a.text != b.text)
        .take(12)
    {
        for op in [BinOp::Sub, BinOp::Add] {
            result.push(Term::binary(op, a, b, Type::I64));
        }
        for op in [BinOp::Eq, BinOp::Lt] {
            result.push(Term::binary(op, a, b, Type::Bool));
        }
    }
    for f in bindings
        .of_type(Type::Bool)
        .into_iter()
        .filter(|t| t.variable)
    {
        result.push(Term::atom(format!("!{}", f.operand(8)), Type::Bool, true));
        result.push(Term {
            text: format!("{} as I64", f.operand(7)),
            ty: Type::I64,
            precedence: 7,
            variable: true,
        });
    }
    for v in &variables {
        let zero = Term::atom("0", Type::I64, false);
        for op in [BinOp::Eq, BinOp::Gt] {
            result.push(Term::binary(op, v, &zero, Type::Bool));
        }
    }
    for t in source
        .terms
        .iter()
        .filter(|t| t.ty == Type::Bool && t.variable)
        .take(4)
    {
        result.push(Term {
            text: format!("{} as I64", t.operand(7)),
            ty: Type::I64,
            precedence: 7,
            variable: true,
        });
    }
    result
}

// A bound built from the value being bounded often reduces to a copy on the
// observed states. Prefer distinct operands when assembling these expressions.
fn distinct_inputs(a: &Term, b: &Term) -> bool {
    let is_token = |c: char| c.is_ascii_alphanumeric() || matches!(c, '_' | '.');
    a.text != b.text
        && !b.text.split(|c| !is_token(c)).any(|s| s == a.text)
        && !a.text.split(|c| !is_token(c)).any(|s| s == b.text)
}

fn arithmetic(
    lanes: &mut Lanes,
    variables: &[&Term],
    primary: &[&Term],
    terms: &[&Term],
    module: &Module,
    hole: &Hole,
) {
    let builtin = |name: &str| {
        !module.functions.iter().any(|f| f.name == name)
            && module.declaration(name).is_none()
            && !hole.locals.iter().any(|(n, _)| n == name)
    };
    // Keep a divisor or modulus simple. A computed divisor introduces an
    // additional potential zero even when neither input is zero.
    let mut divisors = primary.to_vec();
    divisors.sort_by_key(|t| t.variable);
    for op in [BinOp::Add, BinOp::Sub, BinOp::Rem, BinOp::Mul, BinOp::Div] {
        let rhs = if matches!(op, BinOp::Div | BinOp::Rem) {
            &divisors[..]
        } else {
            primary
        };
        lanes.add(
            pairs(variables, rhs)
                .filter(move |(a, b)| match op {
                    BinOp::Add | BinOp::Sub => b.text != "0",
                    BinOp::Rem => !matches!(b.text.as_str(), "0" | "1" | "-1") && a.text != b.text,
                    BinOp::Mul => !matches!(b.text.as_str(), "0" | "1"),
                    BinOp::Div => !matches!(b.text.as_str(), "0" | "1") && a.text != b.text,
                    _ => false,
                })
                .map(move |(a, b)| Term::binary(op, a, b, Type::I64).text),
        );
    }
    for op in ["min", "max"].into_iter().filter(|name| builtin(name)) {
        lanes.add(
            pairs(variables, terms)
                .filter(|(a, b)| distinct_inputs(a, b))
                .map(|(a, b)| Term::call(op, &[a, b], Type::I64).text),
        );
    }
    // Saturating a state update between an observed bound and zero is common;
    // vary the updated term and upper bound independently.
    if builtin("clamp") {
        let zero = Term::atom("0", Type::I64, false);
        lanes.add(
            pairs(terms, terms)
                .filter(|(a, b)| {
                    a.variable && distinct_inputs(a, b) && !matches!(b.text.as_str(), "0" | "-1")
                })
                .map(|(a, b)| Term::call("clamp", &[a, &zero, b], Type::I64).text),
        );
    }
    lanes.add(variables.iter().map(|t| format!("-{}", t.operand(8))));
}

fn boolean(
    lanes: &mut Lanes,
    variables: &[&Term],
    ints: &[&Term],
    flags: &[&Term],
    source: &Pool,
    bindings: &Pool,
    module: &Module,
) {
    let plain: Vec<_> = bindings
        .of_type(Type::Bool)
        .into_iter()
        .filter(|t| t.variable)
        .collect();
    let conditions: Vec<_> = flags.iter().copied().filter(|t| t.variable).collect();
    for op in [BinOp::Ne, BinOp::Eq, BinOp::And, BinOp::Or] {
        let simple = pairs(&plain, &plain).filter(|(a, b)| a.text < b.text);
        let composed = pairs(&conditions, &conditions).filter(|(a, b)| a.text != b.text);
        lanes.add(
            simple
                .chain(composed)
                .map(|(a, b)| Term::binary(op, a, b, Type::Bool).text),
        );
    }
    for op in [
        BinOp::Eq,
        BinOp::Ne,
        BinOp::Lt,
        BinOp::Le,
        BinOp::Gt,
        BinOp::Ge,
    ] {
        lanes.add(
            pairs(variables, ints)
                .filter(|(a, b)| a.text != b.text)
                .map(|(a, b)| Term::binary(op, a, b, Type::Bool).text),
        );
    }
    lanes.add(
        flags
            .iter()
            .filter(|t| t.variable)
            .map(|t| format!("!{}", t.operand(8))),
    );
    let mut equals = Vec::new();
    for (i, _) in module.types.iter().enumerate() {
        if equals.len() >= lanes.width {
            break;
        }
        let ty = Type::Named(i);
        let fields = bindings.of_type(ty);
        let more = source.of_type(ty);
        for a in fields.iter().filter(|a| a.variable) {
            for b in fields.iter().chain(&more) {
                if a.text != b.text {
                    equals.push(Term::binary(BinOp::Eq, a, b, Type::Bool).text);
                    equals.push(Term::binary(BinOp::Ne, a, b, Type::Bool).text);
                }
                if equals.len() >= lanes.width {
                    break;
                }
            }
        }
    }
    lanes.add(equals);
}

fn conditionals(lanes: &mut Lanes, flags: &[&Term], choices: &[&Term]) {
    // Rotate predicates alongside the arms to avoid exploring every pair of
    // branches for the first condition before looking at the second one.
    let guards: Vec<_> = flags
        .iter()
        .copied()
        .filter(|t| t.variable)
        .take(8)
        .collect();
    let branches: Vec<_> = choices.iter().copied().take(18).collect();
    lanes.add(
        pairs(&branches, &branches)
            .filter(|(a, b)| a.text != b.text)
            .flat_map(|(a, b)| {
                guards
                    .iter()
                    .map(move |f| format!("if {} {{ {} }} else {{ {} }}", f.text, a.text, b.text))
            }),
    );
}

// Existing nonrecursive leaf helpers are vocabulary too. Use their checked
// argument signatures and avoid calling back into the sketch being completed.
fn helper_calls(lanes: &mut Lanes, module: &Module, hole: &Hole, bank: &Pool) {
    let helpers = module.functions.iter().filter(|f| {
        f.name != hole.function
            && f.name != "main"
            && f.result == hole.ty
            && (1..=2).contains(&f.params.len())
            && !hole.locals.iter().any(|(name, _)| name == &f.name)
    });
    for f in helpers.take(12) {
        if edit::expressions(f).iter().any(|e| matches!(&e.kind, ExprKind::Call(name,_) if module.functions.iter().any(|other| &other.name==name))) {continue;}
        let args = bank.of_type(f.params[0].ty);
        if let Some(p) = f.params.get(1) {
            let seconds = bank.of_type(p.ty);
            lanes.add(
                pairs(&args, &seconds)
                    .filter(|(a, b)| a.variable || b.variable)
                    .map(|(a, b)| Term::call(&f.name, &[a, b], f.result).text),
            );
        } else {
            lanes.add(
                args.iter()
                    .filter(|a| a.variable)
                    .map(|a| Term::call(&f.name, &[a], f.result).text),
            );
        }
    }
}

fn record_updates(module: &Module, id: usize, bank: &Pool, lanes: &mut Lanes) {
    let decl = &module.types[id];
    let TypeKind::Record(fields) = &decl.kind else {
        return;
    };
    if fields.len() > 16 {
        return;
    }
    let members: Vec<_> = fields.iter().map(|f| bank.of_type(f.ty)).collect();
    if members.iter().any(Vec::is_empty) {
        return;
    }
    let build = |values: &[String]| format!("{}({})", decl.name, values.join(", "));
    let record_values = bank.of_type(Type::Named(id));
    let mut bases = record_values
        .iter()
        .filter(|t| t.variable && t.precedence == 9)
        .take(4)
        .map(|t| {
            fields
                .iter()
                .map(|f| format!("{}.{}", t.text, f.name))
                .collect::<Vec<_>>()
        })
        .collect::<Vec<_>>();
    bases.push(
        members
            .iter()
            .map(|choices| choices[0].text.clone())
            .collect(),
    );
    for base in bases {
        let mut outputs = vec![build(&base)];
        for i in 0..32 {
            for (field, alternatives) in members.iter().enumerate() {
                if let Some(term) = alternatives.get(i)
                    && term.text != base[field]
                {
                    let mut opts = base.clone();
                    opts[field] = term.text.clone();
                    outputs.push(build(&opts));
                }
            }
            if outputs.len() >= lanes.width {
                break;
            }
        }
        lanes.add(outputs);
    }
}

pub(super) fn candidates(
    module: &Module,
    function: &Function,
    hole: &Hole,
    types: &HashMap<Span, Type>,
    limit: usize,
) -> Vec<String> {
    let bindings = vocabulary(module, hole);
    let source = context(module, function, hole, types);
    let derived = frontier(&bindings, &source);
    let scoped = bindings.of_type(hole.ty);
    let flags = bindings.of_type(Type::Bool);
    let mut lanes = Lanes {
        streams: Vec::new(),
        width: limit + 1,
    };
    let mut bank = Pool::new();
    for t in bindings
        .terms
        .iter()
        .chain(&source.terms)
        .chain(&derived.terms)
    {
        bank.push(t.clone());
    }
    if matches!(hole.ty, Type::Named(_) | Type::Unit) {
        if let Type::Named(id) = hole.ty
            && matches!(module.types[id].kind, TypeKind::Record(_))
        {
            if !hole
                .locals
                .iter()
                .any(|(name, _)| name == &module.types[id].name)
            {
                record_updates(module, id, &bank, &mut lanes);
            }
            helper_calls(&mut lanes, module, hole, &bank);
        }
        conditionals(&mut lanes, &flags, &scoped);
        return lanes.finish(scoped.into_iter().map(|t| t.text.clone()));
    }
    let iv = bindings.of_type(Type::I64);
    let vars: Vec<_> = iv.iter().copied().filter(|t| t.variable).collect();
    let integers = operands(&iv, &source.of_type(Type::I64), &derived.of_type(Type::I64));
    let bools = operands(
        &flags,
        &source.of_type(Type::Bool),
        &derived.of_type(Type::Bool),
    );
    let ints: Vec<_> = integers.iter().collect();
    let bools: Vec<_> = bools.iter().collect();
    if hole.ty == Type::I64 {
        let mut primary = iv.clone();
        let constants = source.of_type(Type::I64);
        primary.extend(
            constants
                .iter()
                .copied()
                .filter(|t| !t.variable && t.precedence == 9),
        );
        arithmetic(&mut lanes, &vars, &primary, &ints, module, hole);
        conditionals(&mut lanes, &bools, &ints);
    } else {
        boolean(&mut lanes, &vars, &ints, &bools, &source, &bindings, module);
        conditionals(&mut lanes, &bools, &bools);
    }
    helper_calls(&mut lanes, module, hole, &bank);
    lanes.add(derived.of_type(hole.ty).iter().map(|t| t.text.clone()));
    let seeds = scoped
        .iter()
        .chain(&source.of_type(hole.ty))
        .take(24)
        .map(|t| t.text.clone())
        .collect::<Vec<_>>();
    lanes.finish(seeds)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::check;

    #[test]
    fn composed_terms_use_visible_typed_source_and_the_candidate_cap() {
        let text = "module testcase;
record Meter { n: I64, cap: I64 }
fn doubled(x:I64)->I64 !{} {return x*2;}
fn next(m:Meter, active:Bool)->I64 !{} {
    if active { let hidden = m.n * 7; hidden; }
    let advanced = m.n + 3;
    return ?edit: I64;
}
pub fn main()->I64 !{} {return 0;}";
        let module = syntax::parse(text).unwrap();
        let mut types = HashMap::new();
        let holes = check::holes_with_types(&module, |expr, ty| {
            types.insert(expr.span, ty);
        })
        .unwrap();
        let hole = &holes[0];
        let function = edit::target(&module, "next").unwrap();
        let grammar = candidates(&module, function, hole, &types, 256);
        assert_eq!(grammar.len(), 257);
        assert!(grammar.iter().any(|s| s == "max(m.cap, m.n + 3)"));
        assert!(grammar.iter().any(|s| s == "doubled(m.n)"));
        assert!(grammar.iter().any(|s| s.starts_with("if ")));
        for term in &grammar {
            assert!(!term.contains("hidden"));
            let source = text.replace("?edit: I64", &format!("({term})"));
            let filled = syntax::parse(&source).unwrap();
            check::check(&filled).unwrap_or_else(|d| panic!("{term}: {}", d.message));
        }
        assert_eq!(candidates(&module, function, hole, &types, 8).len(), 9);
    }
}
