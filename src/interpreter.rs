//! Reference semantics over checked source trees. This path shares no control-flow
//! lowering or arithmetic implementation with native code generation.
use std::collections::HashMap;
use std::fmt;

use crate::syntax::{BinOp, Expr, ExprKind, Function, Module, Stmt, StmtKind, UnOp};

pub const DEFAULT_FUEL: u64 = 1_000_000;
const MAX_NESTING: usize = 128;

#[derive(Debug, Clone, Copy, PartialEq)]
enum Value {
    Int(i64),
    Bool(bool),
    Unit,
}

#[derive(Debug, Clone, Copy)]
pub enum Fault {
    IntegerOverflow,
    DivisionByZero,
    ResourceLimit,
    InvalidCheckedProgram,
}

impl fmt::Display for Fault {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{self:?}")
    }
}

impl Value {
    fn int(self) -> Result<i64, Fault> {
        match self {
            Self::Int(n) => Ok(n),
            _ => Err(Fault::InvalidCheckedProgram),
        }
    }

    fn boolean(self) -> Result<bool, Fault> {
        match self {
            Self::Bool(b) => Ok(b),
            _ => Err(Fault::InvalidCheckedProgram),
        }
    }
}

struct Interpreter<'a> {
    functions: HashMap<&'a str, &'a Function>,
    fuel: u64,
}

type Scope<'a> = HashMap<&'a str, Value>;
type Frame<'a> = Vec<Scope<'a>>;

pub fn run(module: &Module, fuel: u64) -> Result<i64, Fault> {
    let mut interpreter = Interpreter {
        functions: module
            .functions
            .iter()
            .map(|f| (f.name.as_str(), f))
            .collect(),
        fuel,
    };
    interpreter.call("main", vec![], 0)?.int()
}

impl<'a> Interpreter<'a> {
    fn step(&mut self, depth: usize) -> Result<(), Fault> {
        if depth > MAX_NESTING || self.fuel == 0 {
            return Err(Fault::ResourceLimit);
        }
        self.fuel -= 1;
        Ok(())
    }

    fn call(&mut self, name: &str, args: Vec<Value>, depth: usize) -> Result<Value, Fault> {
        self.step(depth)?;
        let function = *self
            .functions
            .get(name)
            .ok_or(Fault::InvalidCheckedProgram)?;
        let params = function
            .params
            .iter()
            .map(|p| p.name.as_str())
            .zip(args)
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
            ExprKind::Name(name) => frame
                .iter()
                .rev()
                .find_map(|scope| scope.get(name.as_str()).copied())
                .ok_or(Fault::InvalidCheckedProgram),
            ExprKind::Call(name, args) => {
                let values = args
                    .iter()
                    .map(|arg| self.expr(arg, frame, depth + 1))
                    .collect::<Result<_, _>>()?;
                self.call(name, values, depth + 1)
            }
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
