//! SMT translation for pure scalar contracts. Every value has a separate
//! definedness term so checked arithmetic and lazy evaluation agree with GPT++.
use crate::interpreter::{self, Fault, Value};
use crate::syntax::{
    self, BinOp, Contract, Domain, Expr, ExprKind, Function, Intrinsic, Module, Stmt, StmtKind,
    Type, TypeKind, UnOp,
};
use crate::{check, diagnostic, edit, json_string, trace};
use std::collections::HashMap;
use std::ffi::OsString;
use std::fmt::Write as _;
use std::fs;
use std::io::Write;
use std::path::PathBuf;
use std::process::{Command, Stdio};

const USAGE: &str = "gpp prove FILE [--contract NAME] [--timeout-ms N]";
const TRANSLATION_LIMIT: usize = 8192;

#[derive(Clone)]
struct Term {
    value: String,
    defined: String,
    ty: Type,
}

type Env = HashMap<String, Term>;
type Translate<T> = Result<T, &'static str>;

fn bv(x: i64) -> String {
    format!("#x{:016x}", x as u64)
}

fn sort(ty: Type) -> String {
    match ty {
        Type::Bool | Type::Unit => "Bool".into(),
        Type::I64 => "(_ BitVec 64)".into(),
        Type::Named(i) => format!("T{i}"),
    }
}

// Compiler-local numeric IDs keep source identifiers out of the solver input.
// Mutually-declared sorts allow forward references to enum fields.
fn datatypes(module: &Module) -> String {
    if module.types.is_empty() {
        return String::new();
    }
    let mut sorts = Vec::new();
    let mut bodies = Vec::new();
    for (i, decl) in module.types.iter().enumerate() {
        sorts.push(format!("(T{i} 0)"));
        let body = match &decl.kind {
            TypeKind::Enum(names) => (0..names.len())
                .map(|j| format!("(v{i}_{j})"))
                .collect::<Vec<_>>()
                .join(" "),
            TypeKind::Record(fields) => {
                let params = fields
                    .iter()
                    .enumerate()
                    .map(|(j, f)| format!("(f{i}_{j} {})", sort(f.ty)))
                    .collect::<Vec<_>>()
                    .join(" ");
                format!("(mk{i} {params})")
            }
        };
        bodies.push(format!("({body})"));
    }
    format!(
        "(declare-datatypes ({}) ({}))\n",
        sorts.join(" "),
        bodies.join(" ")
    )
}

fn constant(value: String, ty: Type) -> Term {
    Term {
        value,
        ty,
        defined: "true".into(),
    }
}

struct Encoder<'a> {
    module: &'a Module,
    smt: String,
    nodes: usize,
    calls: Vec<String>,
}

impl Encoder<'_> {
    fn bind(&mut self, value: String, ty: Type, defined: String) -> Translate<Term> {
        if self.nodes >= TRANSLATION_LIMIT {
            return Err("symbolic expression limit reached");
        }
        let n = self.nodes;
        self.nodes += 1;
        let name = format!("e{n}");
        writeln!(self.smt, "(define-fun {name} () {} {value})", sort(ty)).unwrap();
        writeln!(self.smt, "(define-fun d{n} () Bool {defined})").unwrap();
        Ok(Term {
            value: name,
            defined: format!("d{n}"),
            ty,
        })
    }

    fn choose(&mut self, cond: Term, yes: Term, no: Term) -> Translate<Term> {
        self.bind(
            format!("(ite {} {} {})", cond.value, yes.value, no.value),
            yes.ty,
            format!(
                "(and {} (ite {} {} {}))",
                cond.defined, cond.value, yes.defined, no.defined
            ),
        )
    }

    fn binary(&mut self, op: BinOp, left: Term, right: Term) -> Translate<Term> {
        use BinOp::*;
        let (a, b) = (&left.value, &right.value);
        let smtop = match op {
            Add => "bvadd",
            Sub => "bvsub",
            Mul => "bvmul",
            Div => "bvsdiv",
            Rem => "bvsrem",
            Lt => "bvslt",
            Le => "bvsle",
            Gt => "bvsgt",
            Ge => "bvsge",
            Eq => "=",
            Ne => "distinct",
            And => "and",
            Or => "or",
        };
        let value = format!("({smtop} {a} {b})");
        let ty = crate::ir::binary_result(op, left.ty, right.ty)
            .ok_or("unsupported binary operation")?;
        let guard = match op {
            Add | Sub | Mul => {
                let extra = if op == Mul { 64 } else { 1 };
                format!(
                    "(= ((_ sign_extend {extra}) {value}) ({smtop} ((_ sign_extend {extra}) {a}) ((_ sign_extend {extra}) {b})))"
                )
            }
            Div => format!(
                "(and (distinct {b} {}) (not (and (= {a} {}) (= {b} {}))))",
                bv(0),
                bv(i64::MIN),
                bv(-1)
            ),
            Rem => format!("(distinct {b} {})", bv(0)),
            _ => "true".into(),
        };
        let defined = match op {
            And => format!("(and {} (=> {a} {}))", left.defined, right.defined),
            Or => format!("(and {} (=> (not {a}) {}))", left.defined, right.defined),
            _ => format!("(and {} {} {guard})", left.defined, right.defined),
        };
        self.bind(value, ty, defined)
    }

    fn expression(&mut self, expr: &Expr, env: &Env) -> Translate<Term> {
        match &expr.kind {
            ExprKind::Int(n) => Ok(constant(bv(*n), Type::I64)),
            ExprKind::Bool(b) => Ok(constant(b.to_string(), Type::Bool)),
            ExprKind::Unit => Ok(constant("false".into(), Type::Unit)),
            ExprKind::Name(n) => env.get(n).cloned().ok_or("unresolved symbolic binding"),
            ExprKind::Unary(op, arg) => {
                let t = self.expression(arg, env)?;
                match op {
                    UnOp::Not => self.bind(format!("(not {})", t.value), Type::Bool, t.defined),
                    UnOp::Neg => self.bind(
                        format!("(bvneg {})", t.value),
                        Type::I64,
                        format!(
                            "(and {} (distinct {} {}))",
                            t.defined,
                            t.value,
                            bv(i64::MIN)
                        ),
                    ),
                }
            }
            ExprKind::AsI64(arg) => {
                let t = self.expression(arg, env)?;
                if t.ty == Type::I64 {
                    return Ok(t);
                }
                self.bind(
                    format!("(ite {} {} {})", t.value, bv(1), bv(0)),
                    Type::I64,
                    t.defined,
                )
            }
            ExprKind::Binary(op, left, right) => {
                let a = self.expression(left, env)?;
                let b = self.expression(right, env)?;
                self.binary(*op, a, b)
            }
            ExprKind::If { cond, yes, no } => {
                let c = self.expression(cond, env)?;
                let a = self.expression(yes, env)?;
                let b = self.expression(no, env)?;
                self.choose(c, a, b)
            }
            ExprKind::Call(name, args) => {
                let args = args
                    .iter()
                    .map(|e| self.expression(e, env))
                    .collect::<Translate<Vec<_>>>()?;
                self.call(name, &args)
            }
            ExprKind::Field(base, field) => {
                let rec = self.expression(base, env)?;
                let Type::Named(i) = rec.ty else {
                    return Err("expected a record");
                };
                let TypeKind::Record(fields) = &self.module.types[i].kind else {
                    return Err("expected a record");
                };
                let j = fields
                    .iter()
                    .position(|f| &f.name == field)
                    .ok_or("unknown record field")?;
                self.bind(
                    format!("(f{i}_{j} {})", rec.value),
                    fields[j].ty,
                    rec.defined,
                )
            }
            ExprKind::Variant(ty, variant) => {
                let (i, decl) = self.module.declaration(ty).ok_or("unknown enum")?;
                let TypeKind::Enum(variants) = &decl.kind else {
                    return Err("expected an enum");
                };
                let j = variants
                    .iter()
                    .position(|v| v == variant)
                    .ok_or("unknown enum variant")?;
                Ok(constant(format!("v{i}_{j}"), Type::Named(i)))
            }
            ExprKind::Hole(_, _) => Err("unfilled typed hole"),
        }
    }

    fn call(&mut self, name: &str, args: &[Term]) -> Translate<Term> {
        let valid = args
            .iter()
            .map(|t| t.defined.as_str())
            .collect::<Vec<_>>()
            .join(" ");
        if let Some((i, decl)) = self.module.declaration(name) {
            if let TypeKind::Record(_) = decl.kind {
                let vals = args
                    .iter()
                    .map(|a| a.value.as_str())
                    .collect::<Vec<_>>()
                    .join(" ");
                let value = if vals.is_empty() {
                    format!("mk{i}")
                } else {
                    format!("(mk{i} {vals})")
                };
                return self.bind(value, Type::Named(i), format!("(and true {valid})"));
            }
            return Err("expected a record constructor");
        }
        if let Some(function) = self.module.functions.iter().find(|f| f.name == name) {
            if self.calls.len() >= 32 || self.calls.iter().any(|n| n == name) {
                return Err("recursive or deeply nested symbolic call");
            }
            self.calls.push(name.to_owned());
            let env = function
                .params
                .iter()
                .zip(args)
                .map(|(p, v)| (p.name.clone(), v.clone()))
                .collect();
            let t = self.body(function, env)?;
            self.calls.pop();
            return self.bind(t.value, t.ty, format!("(and {} {valid})", t.defined));
        }
        let Some(intrinsic) = Intrinsic::named(name) else {
            return Err("unsupported symbolic call");
        };
        let a = &args[0].value;
        let b = &args[1].value;
        let (value, guard) = match intrinsic {
            Intrinsic::Min => (format!("(ite (bvsle {a} {b}) {a} {b})"), "true".into()),
            Intrinsic::Max => (format!("(ite (bvsge {a} {b}) {a} {b})"), "true".into()),
            Intrinsic::Clamp => {
                let c = &args[2].value;
                (
                    format!("(ite (bvslt {a} {b}) {b} (ite (bvsgt {a} {c}) {c} {a}))"),
                    format!("(bvsle {b} {c})"),
                )
            }
        };
        self.bind(value, Type::I64, format!("(and {guard} {valid})"))
    }

    fn body(&mut self, f: &Function, env: Env) -> Translate<Term> {
        let fallback = (f.result == Type::Unit).then(|| constant("false".into(), Type::Unit));
        self.block(&f.body, env, fallback, 0)
    }

    fn block(
        &mut self,
        body: &[Stmt],
        mut env: Env,
        fallback: Option<Term>,
        depth: usize,
    ) -> Translate<Term> {
        if depth > 48 {
            return Err("symbolic branch nesting limit reached");
        }
        let mut eager = vec!["true".to_owned()];
        let mut result = fallback;
        for (i, stmt) in body.iter().enumerate() {
            match &stmt.kind {
                StmtKind::Bind {
                    mutable: false,
                    name,
                    value,
                    ..
                } => {
                    let t = self.expression(value, &env)?;
                    eager.push(t.defined.clone());
                    env.insert(name.clone(), t);
                }
                StmtKind::Expr(expr) => eager.push(self.expression(expr, &env)?.defined),
                StmtKind::Return(expr) => {
                    result = Some(self.expression(expr, &env)?);
                    break;
                }
                StmtKind::If {
                    cond,
                    then_body,
                    else_body,
                } => {
                    let rest = &body[i + 1..];
                    if !rest.is_empty() {
                        result = Some(self.block(rest, env.clone(), result, depth + 1)?);
                    }
                    if let ExprKind::Bool(flag) = cond.kind {
                        let arm = if flag { then_body } else { else_body };
                        result = Some(self.block(arm, env, result, depth + 1)?);
                        break;
                    }
                    let c = self.expression(cond, &env)?;
                    let yes = self.block(then_body, env.clone(), result.clone(), depth + 1)?;
                    let no = self.block(else_body, env, result, depth + 1)?;
                    result = Some(self.choose(c, yes, no)?);
                    break;
                }
                _ => return Err("mutable locals and loops are outside the symbolic subset"),
            }
        }
        let t = result.ok_or("unsupported symbolic fallthrough")?;
        eager.push(t.defined);
        self.bind(t.value, t.ty, format!("(and {})", eager.join(" ")))
    }
}

fn encode(module: &Module, c: &Contract, timeout: u32) -> Translate<String> {
    let mut e = Encoder {
        module,
        smt: format!(
            "(set-option :timeout {timeout})\n(set-logic {})\n{}",
            if module.types.is_empty() {
                "QF_BV"
            } else {
                "ALL"
            },
            datatypes(module)
        ),
        nodes: 0,
        calls: vec![],
    };
    let mut env = Env::new();
    for (i, (p, domain)) in c.predicate.params.iter().zip(&c.domains).enumerate() {
        let name = format!("p{i}");
        writeln!(e.smt, "(declare-fun {name} () {})", sort(p.ty)).unwrap();
        if let Domain::I64 { low, high } = domain {
            writeln!(
                e.smt,
                "(assert (and (bvsle {} {name}) (bvsle {name} {})))",
                bv(*low),
                bv(*high)
            )
            .unwrap();
        }
        env.insert(p.name.clone(), constant(name, p.ty));
    }
    let t = e.body(&c.predicate, env)?;
    writeln!(
        e.smt,
        "(assert (not (and {} {})))\n(check-sat)",
        t.defined, t.value
    )
    .unwrap();
    Ok(e.smt)
}

fn solve(query: &str, timeout: u32) -> Result<String, String> {
    let mut child = Command::new("z3")
        .args([
            "-in",
            "-smt2",
            &format!("-T:{}", timeout.div_ceil(1000) + 1),
        ])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("cannot run z3: {e}"))?;
    let mut input = child.stdin.take().unwrap();
    let (sent, output) = std::thread::scope(|scope| {
        let write = scope.spawn(move || input.write_all(query.as_bytes()));
        let out = child.wait_with_output();
        (write.join().unwrap(), out)
    });
    let output = output.map_err(|e| e.to_string())?;
    let text = String::from_utf8(output.stdout).map_err(|e| e.to_string())?;
    if !output.status.success() || text.contains("(error") {
        return Err(format!("solver could not finish: {}", text.trim()));
    }
    sent.map_err(|e| e.to_string())?;
    Ok(text)
}

fn model_values(reply: &str, c: &Contract) -> Option<Vec<Value>> {
    let mut parts = reply
        .split(|c: char| c == '(' || c == ')' || c.is_ascii_whitespace())
        .filter(|s| !s.is_empty());
    if parts.next()? != "sat" {
        return None;
    }
    let mut values = vec![];
    for (i, p) in c.predicate.params.iter().enumerate() {
        if parts.next()? != format!("p{i}") {
            return None;
        }
        let raw = parts.next()?;
        values.push(match p.ty {
            Type::Bool => Value::Bool(raw.parse().ok()?),
            Type::I64 => Value::Int(u64::from_str_radix(raw.strip_prefix("#x")?, 16).ok()? as i64),
            _ => return None,
        });
    }
    parts.next().is_none().then_some(values)
}

struct ResultRow {
    status: &'static str,
    details: String,
}

fn reason(status: &'static str, message: &str) -> ResultRow {
    ResultRow {
        status,
        details: format!(",\"reason\":{}", json_string(message)),
    }
}

fn prove(module: &Module, c: &Contract, timeout: u32) -> Result<ResultRow, String> {
    let mut query = match encode(module, c, timeout) {
        Ok(q) => q,
        Err(s) => return Ok(reason("unsupported", s)),
    };
    let result = match solve(&query, timeout) {
        Ok(s) => s,
        Err(e) => return Ok(reason("unknown", &e)),
    };
    match result.trim() {
        "unsat" => {
            return Ok(ResultRow {
                status: "proved",
                details: String::new(),
            });
        }
        "sat" => {}
        other => return Ok(reason("unknown", other)),
    }
    let values = if c.predicate.params.is_empty() {
        vec![]
    } else {
        let names = (0..c.predicate.params.len())
            .map(|i| format!("p{i}"))
            .collect::<Vec<_>>()
            .join(" ");
        writeln!(query, "(get-value ({names}))").unwrap();
        match solve(&query, timeout) {
            Ok(s) => match model_values(&s, c) {
                Some(values) => values,
                None => return Ok(reason("unknown", "model unavailable")),
            },
            Err(e) => return Ok(reason("unknown", &e)),
        }
    };
    let actual = interpreter::eval_contract(
        module,
        c,
        values.clone(),
        interpreter::DEFAULT_FUEL,
        &mut (),
    );
    if !matches!(
        actual,
        Ok(Value::Bool(false))
            | Err(Fault::IntegerOverflow | Fault::DivisionByZero | Fault::InvalidBounds)
    ) {
        return Ok(reason(
            "unknown",
            "solver witness did not reproduce a semantic failure",
        ));
    }
    let mut buf = Vec::new();
    for (i, (p, v)) in c.predicate.params.iter().zip(&values).enumerate() {
        if i > 0 {
            buf.push(b',');
        }
        write!(buf, "{}:", json_string(&p.name)).unwrap();
        trace::write_value(&mut buf, v.clone()).map_err(|e| e.to_string())?;
    }
    let mut outcome = Vec::new();
    trace::write_result(&mut outcome, "result", actual).map_err(|e| e.to_string())?;
    Ok(ResultRow {
        status: "refuted",
        details: format!(
            ",\"counterexample\":{{\"inputs\":{{{}}},{}}}",
            String::from_utf8(buf).unwrap(),
            String::from_utf8(outcome).unwrap()
        ),
    })
}

pub fn run(mut args: impl Iterator<Item = OsString>) -> Result<u8, String> {
    let path = PathBuf::from(args.next().ok_or(USAGE)?);
    let mut target = None;
    let mut timeout = None;
    while let Some(flag) = args.next() {
        match flag.to_str() {
            Some("--contract") if target.is_none() => {
                target = Some(
                    args.next()
                        .and_then(|s| s.into_string().ok())
                        .ok_or(USAGE)?,
                )
            }
            Some("--timeout-ms") if timeout.is_none() => {
                timeout = Some(
                    args.next()
                        .and_then(|s| s.to_str()?.parse::<u32>().ok())
                        .filter(|n| (1..=120000).contains(n))
                        .ok_or("--timeout-ms requires 1..120000")?,
                )
            }
            _ => return Err(USAGE.into()),
        }
    }
    let timeout = timeout.unwrap_or(5000);
    let source = fs::read_to_string(&path).map_err(|e| e.to_string())?;
    let module = syntax::parse(&source).map_err(|d| diagnostic(&path, &source, d, true))?;
    check::check(&module).map_err(|d| diagnostic(&path, &source, d, true))?;
    if target
        .as_ref()
        .is_some_and(|n| !module.contracts.iter().any(|c| c.predicate.name == *n))
    {
        return Err("unknown contract".into());
    }
    let mut rows = vec![];
    let mut status = "proved";
    for c in &module.contracts {
        if target.as_ref().is_some_and(|n| n != &c.predicate.name) {
            continue;
        }
        let r = prove(&module, c, timeout)?;
        rows.push(format!(
            "{{\"name\":{},\"status\":{}{} }}",
            json_string(&c.predicate.name),
            json_string(r.status),
            r.details
        ));
        if r.status != "proved" {
            status = r.status;
            break;
        }
    }
    if rows.is_empty() {
        status = "no_contracts";
    }
    let revision = edit::revision(source.as_bytes())?;
    println!(
        "{{\"schema\":\"gpp.prove/1\",\"solver\":\"z3\",\"revision\":{},\"status\":{},\"contracts\":[{}]}}",
        json_string(&revision),
        json_string(status),
        rows.join(",")
    );
    Ok(match status {
        "proved" => 0,
        "refuted" => 1,
        _ => 3,
    })
}
