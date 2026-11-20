//! Derive an exact target result from a public mismatch in an unchanged scalar caller.
//! Build and CLI examples are in caller_obligation.md. The checker supplies verified CFGs.
#[path = "../src/check.rs"]
mod check;
#[allow(dead_code)]
#[path = "../src/ir.rs"]
mod ir;
#[allow(dead_code)]
#[path = "../src/syntax.rs"]
mod syntax;

use ir::{Op, Program, Term};
use std::io::Read;
use std::{env, fs, process};
use syntax::{BinOp, Intrinsic, Type, UnOp};

type Analysis<T> = Result<T, &'static str>;
const LIMIT: &str = "analysis limit reached";
const OVERFLOW: &str = "integer overflow";
const SYMBOLIC: &str = "operation needs a concrete value";
const MAX_SOURCE_BYTES: u64 = 65_536;
const FUEL: usize = 16_384;
const MAX_DEPTH: usize = 32;

/// On every successful execution, this value equals `coefficient * target + offset`.
/// Candidate replay additionally enforces the I64 domain at every intermediate step.
#[derive(Clone, Copy, Debug, PartialEq)]
enum Value {
    Num { coefficient: i128, offset: i128 },
    Bool(bool),
    Unit,
}

impl Value {
    fn int(x: i64) -> Self {
        Self::Num {
            coefficient: 0,
            offset: i128::from(x),
        }
    }

    fn number(self) -> Analysis<(i128, i128)> {
        match self {
            Self::Num {
                coefficient,
                offset,
            } => Ok((coefficient, offset)),
            _ => Err("expected a number"),
        }
    }

    fn scalar(self) -> Analysis<i64> {
        let (a, b) = self.number()?;
        if a != 0 {
            return Err(SYMBOLIC);
        }
        i64::try_from(b).map_err(|_| OVERFLOW)
    }

    fn boolean(self) -> Analysis<bool> {
        match self {
            Self::Bool(b) => Ok(b),
            _ => Err("expected a concrete boolean"),
        }
    }

    fn literal(self) -> Analysis<String> {
        match self {
            Self::Num { .. } => Ok(self.scalar()?.to_string()),
            Self::Bool(b) => Ok(b.to_string()),
            Self::Unit => Err("only I64 and Bool target arguments are supported"),
        }
    }
}

fn affine(coefficient: Option<i128>, offset: Option<i128>) -> Analysis<Value> {
    let coefficient = coefficient.ok_or(OVERFLOW)?;
    let offset = offset.ok_or(OVERFLOW)?;
    if coefficient == 0 {
        i64::try_from(offset).map_err(|_| OVERFLOW)?;
    }
    Ok(Value::Num {
        coefficient,
        offset,
    })
}

fn unary(op: UnOp, v: Value) -> Analysis<Value> {
    match op {
        UnOp::Not => Ok(Value::Bool(!v.boolean()?)),
        UnOp::Neg => {
            let (a, b) = v.number()?;
            affine(a.checked_neg(), b.checked_neg())
        }
    }
}

fn binary(op: BinOp, left: Value, right: Value) -> Analysis<Value> {
    use BinOp::*;
    if matches!(op, Eq | Ne) {
        if matches!(left, Value::Num { .. }) {
            left.scalar()?;
            right.scalar()?;
        }
        return Ok(Value::Bool((left == right) == (op == Eq)));
    }
    let (a, b) = left.number()?;
    let (c, d) = right.number()?;
    match op {
        Add => affine(a.checked_add(c), b.checked_add(d)),
        Sub => affine(a.checked_sub(c), b.checked_sub(d)),
        Mul if a == 0 => affine(c.checked_mul(b), d.checked_mul(b)),
        Mul if c == 0 => affine(a.checked_mul(d), b.checked_mul(d)),
        Mul => Err("nonlinear product"),
        Div if c == 0 && d == 1 => Ok(left),
        Div if c == 0 && d == -1 => unary(UnOp::Neg, left),
        Div | Rem => {
            let divisor = right.scalar()?;
            if divisor == 0 {
                return Err("division by zero");
            }
            let dividend = left.scalar()?;
            // GPT++ defines MIN % -1 as zero but faults on MIN / -1.
            let value = if op == Div {
                dividend.checked_div(divisor).ok_or(OVERFLOW)?
            } else {
                dividend.wrapping_rem(divisor)
            };
            Ok(Value::int(value))
        }
        Lt | Le | Gt | Ge => {
            let (l, r) = (left.scalar()?, right.scalar()?);
            Ok(Value::Bool(match op {
                Lt => l < r,
                Le => l <= r,
                Gt => l > r,
                _ => l >= r,
            }))
        }
        _ => Err("unsupported binary operation"),
    }
}

#[derive(Clone, Copy)]
enum Mode {
    Trace,
    Substitute(i64),
}

struct Execution {
    target: usize,
    mode: Mode,
    target_args: Option<Vec<Value>>,
    fuel: usize,
}

impl Execution {
    fn new(target: usize, mode: Mode) -> Self {
        Self {
            target,
            mode,
            target_args: None,
            fuel: FUEL,
        }
    }

    fn step(&mut self) -> Analysis<()> {
        self.fuel = self.fuel.checked_sub(1).ok_or(LIMIT)?;
        Ok(())
    }

    fn call(
        &mut self,
        program: &Program,
        id: usize,
        args: Vec<Value>,
        depth: usize,
    ) -> Analysis<Value> {
        self.step()?;
        if depth > MAX_DEPTH {
            return Err(LIMIT);
        }
        if id == self.target {
            for arg in &args {
                match arg {
                    Value::Num { .. } => {
                        arg.scalar()?;
                    }
                    Value::Bool(_) => (),
                    Value::Unit => return Err("only I64 and Bool target arguments are supported"),
                }
            }
            if let Some(seen) = &self.target_args {
                if seen != &args {
                    return Err("multiple distinct target argument tuples");
                }
            } else {
                self.target_args = Some(args);
            }
            return Ok(match self.mode {
                Mode::Substitute(value) => Value::int(value),
                Mode::Trace => Value::Num {
                    coefficient: 1,
                    offset: 0,
                },
            });
        }
        // Slot indices, operand types and definite assignment are verified by check::check.
        let function = &program.functions[id];
        let mut slots = vec![Value::Unit; function.slots.len()];
        slots[..args.len()].copy_from_slice(&args);
        let mut block_index = 0;
        loop {
            self.step()?;
            let block = &function.blocks[block_index];
            for instruction in &block.instructions {
                self.step()?;
                slots[instruction.dst] = match &instruction.op {
                    Op::Int(n) => Value::int(*n),
                    Op::Bool(b) => Value::Bool(*b),
                    Op::Unit => Value::Unit,
                    Op::Copy(s) => slots[*s],
                    Op::BoolToI64(s) => Value::int(i64::from(slots[*s].boolean()?)),
                    Op::Intrinsic(op, args) => {
                        // Selection is piecewise, so infer only with concrete operands.
                        let a = slots[args[0]].scalar()?;
                        let b = slots[args[1]].scalar()?;
                        Value::int(match op {
                            Intrinsic::Min => a.min(b),
                            Intrinsic::Max => a.max(b),
                            Intrinsic::Clamp => {
                                let hi = slots[args[2]].scalar()?;
                                if b > hi {
                                    return Err("invalid clamp bounds");
                                }
                                a.clamp(b, hi)
                            }
                        })
                    }
                    Op::Unary(op, s) => unary(*op, slots[*s])?,
                    Op::Binary(op, l, r) => binary(*op, slots[*l], slots[*r])?,
                    Op::Call(callee, params) => {
                        let args = params.iter().map(|p| slots[*p]).collect();
                        self.call(program, *callee, args, depth + 1)?
                    }
                };
            }
            block_index = match block.term {
                Term::Return(v) => return Ok(slots[v]),
                Term::Jump(next) => next,
                Term::Branch { condition, yes, no } => {
                    if slots[condition].boolean()? {
                        yes
                    } else {
                        no
                    }
                }
            };
        }
    }
}

#[derive(Debug, PartialEq)]
struct Obligation {
    args: Vec<Value>,
    expected: i64,
}

fn derive(
    program: &Program,
    caller: usize,
    target: usize,
    args: Vec<Value>,
    expected: i64,
) -> Analysis<Obligation> {
    if caller == target {
        return Err("caller must differ from target");
    }
    if [caller, target]
        .iter()
        .any(|&id| program.functions[id].result != Type::I64)
    {
        return Err("only I64 caller and target results are supported");
    }
    let mut trace = Execution::new(target, Mode::Trace);
    let (coefficient, offset) = trace.call(program, caller, args.clone(), 0)?.number()?;
    let target_args = trace
        .target_args
        .ok_or("the caller did not invoke the target")?;
    if coefficient == 0 {
        return Err("caller output does not determine a target result");
    }
    let delta = i128::from(expected).checked_sub(offset).ok_or(OVERFLOW)?;
    if delta.checked_rem(coefficient).ok_or(OVERFLOW)? != 0 {
        return Err("required target result is nonintegral");
    }
    let candidate = i64::try_from(delta.checked_div(coefficient).ok_or(OVERFLOW)?)
        .map_err(|_| "required target result is outside I64")?;
    // A formal affine solution can overflow a dropped intermediate or a source-order
    // subexpression that later cancels. Replaying catches every such operation.
    let mut replay = Execution::new(target, Mode::Substitute(candidate));
    if replay.call(program, caller, args, 0)?.scalar()? != expected
        || replay.target_args != Some(target_args.clone())
    {
        return Err("inferred result failed concrete replay");
    }
    Ok(Obligation {
        args: target_args,
        expected: candidate,
    })
}

fn parse_args(function: &ir::Function, text: &[String]) -> Result<Vec<Value>, String> {
    let params = &function.slots[..function.params];
    if params.len() != text.len() {
        return Err(format!("expected {} caller arguments", params.len()));
    }
    params
        .iter()
        .zip(text)
        .map(|(ty, s)| match ty {
            Type::Bool => s
                .parse::<bool>()
                .map(Value::Bool)
                .map_err(|_| format!("invalid Bool argument: {s}")),
            Type::I64 => s
                .parse::<i64>()
                .map(Value::int)
                .map_err(|_| format!("invalid I64 argument: {s}")),
            Type::Unit => Err("only I64 and Bool caller arguments are supported".into()),
        })
        .collect()
}

fn checked_source(source: &str) -> Result<Program, String> {
    let diagnostic = |d: syntax::Diagnostic| {
        format!(
            "{} at bytes {}..{}: {}",
            d.code, d.span.start, d.span.end, d.message
        )
    };
    check::check(&syntax::parse(source).map_err(diagnostic)?).map_err(diagnostic)
}

fn cli(args: &[String]) -> Result<String, String> {
    if args.len() < 8
        || args[1] != "--caller"
        || args[3] != "--target"
        || args[5] != "--expect"
        || args[7] != "--"
    {
        return Err(
            "usage: caller-obligation FILE --caller NAME --target NAME --expect I64 -- [ARG ...]"
                .into(),
        );
    }
    let mut source = String::new();
    fs::File::open(&args[0])
        .map_err(|e| e.to_string())?
        .take(MAX_SOURCE_BYTES + 1)
        .read_to_string(&mut source)
        .map_err(|e| e.to_string())?;
    if source.len() as u64 > MAX_SOURCE_BYTES {
        return Err("module exceeds 65536 bytes".into());
    }
    let program = checked_source(&source)?;
    let find = |name: &str| {
        program
            .functions
            .iter()
            .position(|f| f.name == name)
            .ok_or_else(|| format!("unknown function: {name}"))
    };
    let caller = find(&args[2])?;
    let target = find(&args[4])?;
    let Ok(expected) = args[6].parse::<i64>() else {
        return Ok(
            r#"{"status":"unsupported","reason":"expected caller result is outside I64"}"#.into(),
        );
    };
    let supplied = parse_args(&program.functions[caller], &args[8..])?;
    match derive(&program, caller, target, supplied, expected) {
        Ok(obligation) => {
            let literals = obligation
                .args
                .into_iter()
                .map(Value::literal)
                .collect::<Analysis<Vec<_>>>()?;
            // Target is a compiler-checked ASCII identifier; literals are decimals/booleans.
            Ok(format!(
                r#"{{"status":"exact","target":"{}","args":[{}],"expected":{}}}"#,
                args[4],
                literals.join(","),
                obligation.expected
            ))
        }
        Err(reason) => Ok(format!(r#"{{"status":"unsupported","reason":"{reason}"}}"#)),
    }
}

fn main() {
    match cli(&env::args().skip(1).collect::<Vec<_>>()) {
        Ok(json) => println!("{json}"),
        Err(message) => {
            eprintln!("{message}");
            process::exit(2);
        }
    }
}

#[cfg(test)]
#[allow(dead_code)]
#[path = "../src/interpreter.rs"]
mod interpreter;

#[cfg(test)]
mod obligations {
    use super::*;

    fn fixture(body: &str) -> Program {
        checked_source(&format!(
            "module tests; fn price(n: I64) -> I64 !{{}} {{ return n; }}
          fn invoice(n: I64) -> I64 !{{}} {{ {body} }} pub fn main() -> I64 !{{}} {{ return 0; }}"
        ))
        .unwrap()
    }

    fn single(body: &str, expected: i64) -> Analysis<Obligation> {
        derive(&fixture(body), 1, 0, vec![Value::int(4)], expected)
    }

    #[test]
    fn negative_coefficient_repeated_and_transitive_wrappers() {
        let p = checked_source(
            "module charges;
            fn quote(n: I64, insured: Bool) -> I64 !{} { return 8; }
            fn net(count: I64, rush: Bool) -> I64 !{} {
                let discount = quote(count / 2, rush);
                return 50 - (discount + quote(count / 2, rush));
            }
            fn statement(units: I64, insured: Bool) -> I64 !{} {
                if units <= 0 { return 0; }
                return 2 * net(units, insured);
            }
            pub fn main() -> I64 !{} { return 0; }",
        )
        .unwrap();
        let derived = derive(&p, 2, 0, vec![Value::int(9), Value::Bool(true)], 84).unwrap();
        assert_eq!(
            derived,
            Obligation {
                args: vec![Value::int(4), Value::Bool(true)],
                expected: 4
            }
        );
    }

    #[test]
    fn zero_answer_existing_answer_and_concrete_branches() {
        assert_eq!(
            single("if n < 0 { return 0; } return price(n) / -1;", 0)
                .unwrap()
                .expected,
            0
        );
        // Caller mismatches are observed in the engine that requested the tip. The
        // shared baseline may already satisfy that example in a cross-language run.
        assert_eq!(single("return price(n) + 2;", 6).unwrap().expected, 4);
        assert_eq!(
            single("var i = 0; while i < n { i += 1; } return price(i);", -5)
                .unwrap()
                .args,
            vec![Value::int(4)]
        );
    }

    #[test]
    fn rejects_ambiguous_and_non_affine_results() {
        for body in [
            "return price(n) + price(n + 1);",
            "return price(price(n));",
            "return 0 * price(n);",
            "return price(n) - price(n);",
            "return price(n) * price(n);",
            "return price(n) / 2;",
            "return price(n) % 1;",
            "return if price(n) > 1 { 10 } else { 2 };",
            "return if price(n) == 3 { 1 } else { 0 };",
            "return n;",
        ] {
            assert!(single(body, 2).is_err(), "{body}");
        }
        assert_eq!(
            single("return -3 * price(n) + 2;", 9),
            Err("required target result is nonintegral")
        );
        assert_eq!(
            derive(&fixture("return price(n);"), 0, 0, vec![Value::int(4)], 2),
            Err("caller must differ from target")
        );
    }

    #[test]
    fn validates_faults_even_in_discarded_symbolic_intermediates() {
        let max = i64::MAX;
        assert_eq!(
            single("return price(n) - 1;", max),
            Err("required target result is outside I64")
        );
        assert_eq!(
            single("let ignored = price(n) + 1; return price(n);", max),
            Err(OVERFLOW)
        );
        assert_eq!(single("return (price(n) + 1) - 1;", max), Err(OVERFLOW));
        assert_eq!(
            single("let unused = 100 / (n - 4); return price(n);", 2),
            Err("division by zero")
        );
        assert_eq!(
            single(
                "let unused = -9223372036854775808 / -1; return price(n);",
                2
            ),
            Err(OVERFLOW)
        );
        assert_eq!(
            single("return -9223372036854775808 % -1 + price(n);", 2)
                .unwrap()
                .expected,
            2
        );
    }

    #[test]
    fn budgets_concrete_control_flow() {
        assert_eq!(single("while true {} return price(n);", 7), Err(LIMIT));
        assert_eq!(single("return invoice(n);", 7), Err(LIMIT));
    }

    #[test]
    fn matches_source_interpreter_for_small_affine_invoices() {
        // Compare the proof against independently interpreted actual target bodies,
        // including rounding-free solution, nonintegral solution and constant output.
        for rate in [-2, 0, 3] {
            for expected in [-7, 2, 8] {
                let body = format!("return 2 + {rate} * price(n);");
                let proof = single(&body, expected).ok().map(|r| r.expected);
                for candidate in -10..=10 {
                    let source = format!(
                        "module replay;
                        fn price(n: I64) -> I64 !{{}} {{ return {candidate}; }}
                        fn invoice(n: I64) -> I64 !{{}} {{ {body} }}
                        pub fn main() -> I64 !{{}} {{ return invoice(4); }}"
                    );
                    let module = syntax::parse(&source).unwrap();
                    check::check(&module).unwrap();
                    let output = interpreter::run(&module, interpreter::DEFAULT_FUEL).unwrap();
                    if rate != 0 {
                        assert_eq!(output == expected, proof == Some(candidate));
                    } else {
                        assert!(proof.is_none());
                    }
                }
            }
        }
    }
}
