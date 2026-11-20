//! Reference semantics over checked source trees. This path shares no control-flow
//! lowering or arithmetic implementation with native code generation.
use std::collections::HashMap;
use std::fmt;
use std::rc::Rc;

use crate::syntax::{
    BinOp, Contract, Domain, Expr, ExprKind, Function, Intrinsic, Module, Stmt, StmtKind, TypeKind,
    UnOp,
};

pub const DEFAULT_FUEL: u64 = 1_000_000;
const MAX_NESTING: usize = 128;

pub type RecordValue = (String, Vec<(String, Value)>);

#[derive(Debug, Clone, PartialEq)]
pub enum Value {
    Int(i64),
    Bool(bool),
    Unit,
    Enum(Rc<(String, String)>),
    Record(Rc<RecordValue>),
}

#[derive(Debug, Clone, Copy)]
pub enum Fault {
    IntegerOverflow,
    DivisionByZero,
    InvalidBounds,
    ResourceLimit,
    InvalidCheckedProgram,
}

impl fmt::Display for Fault {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{self:?}")
    }
}

impl Value {
    fn int(&self) -> Result<i64, Fault> {
        match self {
            Self::Int(n) => Ok(*n),
            _ => Err(Fault::InvalidCheckedProgram),
        }
    }

    fn boolean(&self) -> Result<bool, Fault> {
        match self {
            Self::Bool(b) => Ok(*b),
            _ => Err(Fault::InvalidCheckedProgram),
        }
    }
}

struct Interpreter<'a, 'o, O> {
    module: &'a Module,
    observer: &'o mut O,
    functions: HashMap<&'a str, &'a Function>,
    fuel: u64,
}

pub type Scope<'a> = HashMap<&'a str, Value>;
type Frame<'a> = Vec<Scope<'a>>;

/// An observation spans the evaluation of one expression, including nested calls.
pub trait Observer<'a> {
    type Visit;
    fn enter(&mut self, expr: &Expr, scopes: &[Scope<'a>]) -> Self::Visit;
    fn leave(&mut self, visit: Self::Visit, result: &Result<Value, Fault>);
}

impl Observer<'_> for () {
    type Visit = ();
    fn enter(&mut self, _: &Expr, _: &[Scope<'_>]) {}
    fn leave(&mut self, _: (), _: &Result<Value, Fault>) {}
}

pub fn run(module: &Module, fuel: u64) -> Result<i64, Fault> {
    invoke(module, "main", vec![], fuel, &mut ())?.int()
}

pub fn invoke<'a>(
    module: &'a Module,
    entry: &str,
    args: Vec<Value>,
    fuel: u64,
    observer: &mut impl Observer<'a>,
) -> Result<Value, Fault> {
    Interpreter::new(module, fuel, observer).call(entry, args, 0)
}

pub fn in_domain(domain: Domain, value: &Value) -> bool {
    match (domain, value) {
        (Domain::Bool, Value::Bool(_)) => true,
        (Domain::I64 { low, high }, Value::Int(n)) => (low..=high).contains(n),
        _ => false,
    }
}

/// Evaluate a checked contract without installing it as a callable name.
pub fn eval_contract<'a>(
    module: &'a Module,
    contract: &'a Contract,
    values: Vec<Value>,
    fuel: u64,
    observer: &mut impl Observer<'a>,
) -> Result<Value, Fault> {
    contract_evaluator(module, contract, fuel, observer)(&values)
}

/// Reuse the function index across tuples. Each tuple starts with fresh
/// bindings and the full interpreter fuel budget.
pub fn contract_evaluator<'a>(
    module: &'a Module,
    contract: &'a Contract,
    fuel: u64,
    observer: &mut impl Observer<'a>,
) -> impl FnMut(&[Value]) -> Result<Value, Fault> {
    let mut interpreter = Interpreter::new(module, fuel, observer);
    move |values| {
        if values.len() != contract.domains.len()
            || !values
                .iter()
                .zip(&contract.domains)
                .all(|(v, &d)| in_domain(d, v))
        {
            return Err(Fault::InvalidCheckedProgram);
        }
        interpreter.fuel = fuel;
        interpreter.step(0)?;
        interpreter.body(&contract.predicate, values, 0)
    }
}

/// Execute a private entry wrapper against the checked source functions.
pub fn invoke_wrapper<'a>(module: &'a Module, wrapper: &'a Function) -> Result<Value, Fault> {
    let mut observer = ();
    let mut interpreter = Interpreter::new(module, DEFAULT_FUEL, &mut observer);
    interpreter.functions.insert(&wrapper.name, wrapper);
    interpreter.call(&wrapper.name, Vec::new(), 0)
}

impl<'a, 'o, O: Observer<'a>> Interpreter<'a, 'o, O> {
    fn new(module: &'a Module, fuel: u64, observer: &'o mut O) -> Self {
        Self {
            module,
            observer,
            functions: module
                .functions
                .iter()
                .map(|f| (f.name.as_str(), f))
                .collect(),
            fuel,
        }
    }

    fn step(&mut self, depth: usize) -> Result<(), Fault> {
        if depth > MAX_NESTING || self.fuel == 0 {
            return Err(Fault::ResourceLimit);
        }
        self.fuel -= 1;
        Ok(())
    }

    fn call(&mut self, name: &str, args: Vec<Value>, depth: usize) -> Result<Value, Fault> {
        self.step(depth)?;
        let Some(&function) = self.functions.get(name) else {
            if let Some((_, decl)) = self.module.declaration(name) {
                let TypeKind::Record(fields) = &decl.kind else {
                    return Err(Fault::InvalidCheckedProgram);
                };
                if fields.len() != args.len() {
                    return Err(Fault::InvalidCheckedProgram);
                }
                let values = fields.iter().map(|p| p.name.clone()).zip(args).collect();
                return Ok(Value::Record(Rc::new((name.to_owned(), values))));
            }
            return match (Intrinsic::named(name), args.as_slice()) {
                (Some(Intrinsic::Min), [Value::Int(a), Value::Int(b)]) => Ok(Value::Int(*a.min(b))),
                (Some(Intrinsic::Max), [Value::Int(a), Value::Int(b)]) => Ok(Value::Int(*a.max(b))),
                (Some(Intrinsic::Clamp), [Value::Int(n), Value::Int(lo), Value::Int(hi)]) => {
                    if lo > hi {
                        Err(Fault::InvalidBounds)
                    } else {
                        Ok(Value::Int((*n).clamp(*lo, *hi)))
                    }
                }
                _ => Err(Fault::InvalidCheckedProgram),
            };
        };
        self.body(function, &args, depth)
    }

    fn body(
        &mut self,
        function: &'a Function,
        args: &[Value],
        depth: usize,
    ) -> Result<Value, Fault> {
        let params = function
            .params
            .iter()
            .map(|p| p.name.as_str())
            .zip(args.iter().cloned())
            .collect();
        let mut frame = vec![params];
        Ok(self
            .statements(&function.body, &mut frame, depth + 1)?
            .unwrap_or(Value::Unit))
    }

    fn block(
        &mut self,
        body: &'a [Stmt],
        frame: &mut Frame<'a>,
        depth: usize,
    ) -> Result<Option<Value>, Fault> {
        frame.push(Scope::new());
        let result = self.statements(body, frame, depth);
        frame.pop();
        result
    }

    fn statements(
        &mut self,
        body: &'a [Stmt],
        frame: &mut Frame<'a>,
        depth: usize,
    ) -> Result<Option<Value>, Fault> {
        for stmt in body {
            self.step(depth)?;
            let returned = match &stmt.kind {
                StmtKind::Bind { name, value, .. } => {
                    let value = self.expr(value, frame, depth + 1)?;
                    frame
                        .last_mut()
                        .ok_or(Fault::InvalidCheckedProgram)?
                        .insert(name, value);
                    None
                }
                StmtKind::Assign { name, value } => {
                    let value = self.expr(value, frame, depth + 1)?;
                    let local = frame
                        .iter_mut()
                        .rev()
                        .find_map(|scope| scope.get_mut(name.as_str()));
                    *local.ok_or(Fault::InvalidCheckedProgram)? = value;
                    None
                }
                StmtKind::Expr(expr) => {
                    self.expr(expr, frame, depth + 1)?;
                    None
                }
                StmtKind::Return(expr) => Some(self.expr(expr, frame, depth + 1)?),
                StmtKind::If {
                    cond,
                    then_body,
                    else_body,
                } => {
                    let branch = if self.expr(cond, frame, depth + 1)?.boolean()? {
                        then_body
                    } else {
                        else_body
                    };
                    self.block(branch, frame, depth + 1)?
                }
                StmtKind::While { cond, body } => {
                    while self.expr(cond, frame, depth + 1)?.boolean()? {
                        if let Some(value) = self.block(body, frame, depth + 1)? {
                            return Ok(Some(value));
                        }
                    }
                    None
                }
            };
            if returned.is_some() {
                return Ok(returned);
            }
        }
        Ok(None)
    }

    fn expr(&mut self, expr: &'a Expr, frame: &Frame<'a>, depth: usize) -> Result<Value, Fault> {
        let visit = self.observer.enter(expr, frame);
        let result = self.eval(expr, frame, depth);
        self.observer.leave(visit, &result);
        result
    }

    fn eval(&mut self, expr: &'a Expr, frame: &Frame<'a>, depth: usize) -> Result<Value, Fault> {
        self.step(depth)?;
        match &expr.kind {
            ExprKind::If { cond, yes, no } => {
                let selected = if self.expr(cond, frame, depth + 1)?.boolean()? {
                    yes
                } else {
                    no
                };
                self.expr(selected, frame, depth + 1)
            }
            ExprKind::Int(n) => Ok(Value::Int(*n)),
            ExprKind::Bool(b) => Ok(Value::Bool(*b)),
            ExprKind::Unit => Ok(Value::Unit),
            ExprKind::Hole(..) => Err(Fault::InvalidCheckedProgram),
            ExprKind::Variant(name, variant) => {
                Ok(Value::Enum(Rc::new((name.clone(), variant.clone()))))
            }
            ExprKind::Field(base, field) => {
                let Value::Record(record) = self.expr(base, frame, depth + 1)? else {
                    return Err(Fault::InvalidCheckedProgram);
                };
                record
                    .1
                    .iter()
                    .find(|(name, _)| name == field)
                    .map(|(_, v)| v.clone())
                    .ok_or(Fault::InvalidCheckedProgram)
            }
            ExprKind::Name(name) => frame
                .iter()
                .rev()
                .find_map(|scope| scope.get(name.as_str()).cloned())
                .ok_or(Fault::InvalidCheckedProgram),
            ExprKind::Call(name, args) => {
                let values = args
                    .iter()
                    .map(|arg| self.expr(arg, frame, depth + 1))
                    .collect::<Result<_, _>>()?;
                self.call(name, values, depth + 1)
            }
            ExprKind::AsI64(inner) => match self.expr(inner, frame, depth + 1)? {
                Value::Bool(b) => Ok(Value::Int(i64::from(b))),
                v @ Value::Int(_) => Ok(v),
                _ => Err(Fault::InvalidCheckedProgram),
            },
            ExprKind::Unary(op, inner) => {
                let value = self.expr(inner, frame, depth + 1)?;
                match op {
                    UnOp::Not => Ok(Value::Bool(!value.boolean()?)),
                    UnOp::Neg => checked(value.int()?.checked_neg()),
                }
            }
            ExprKind::Binary(op, left, right) => {
                let left = self.expr(left, frame, depth + 1)?;
                match op {
                    BinOp::And if !left.boolean()? => return Ok(Value::Bool(false)),
                    BinOp::Or if left.boolean()? => return Ok(Value::Bool(true)),
                    _ => {}
                }
                let right = self.expr(right, frame, depth + 1)?;
                binary(*op, left, right)
            }
        }
    }
}

fn checked(value: Option<i64>) -> Result<Value, Fault> {
    value.map(Value::Int).ok_or(Fault::IntegerOverflow)
}

fn binary(op: BinOp, left: Value, right: Value) -> Result<Value, Fault> {
    match op {
        BinOp::Eq => return Ok(Value::Bool(left == right)),
        BinOp::Ne => return Ok(Value::Bool(left != right)),
        BinOp::And | BinOp::Or => return Ok(Value::Bool(right.boolean()?)),
        _ => {}
    }
    let (a, b) = (left.int()?, right.int()?);
    match op {
        BinOp::Add => checked(a.checked_add(b)),
        BinOp::Sub => checked(a.checked_sub(b)),
        BinOp::Mul => checked(a.checked_mul(b)),
        BinOp::Div | BinOp::Rem if b == 0 => Err(Fault::DivisionByZero),
        BinOp::Div => checked(a.checked_div(b)),
        BinOp::Rem => Ok(Value::Int(a.wrapping_rem(b))),
        BinOp::Lt => Ok(Value::Bool(a < b)),
        BinOp::Le => Ok(Value::Bool(a <= b)),
        BinOp::Gt => Ok(Value::Bool(a > b)),
        BinOp::Ge => Ok(Value::Bool(a >= b)),
        _ => Err(Fault::InvalidCheckedProgram),
    }
}
