//! Resolve a single scalar module and lower checked expressions to typed blocks.
use std::collections::{HashMap, HashSet};

use crate::ir::{self, Instr, Op, Term};
use crate::syntax::{
    self, BinOp, Diagnostic, Expr, ExprKind, Intrinsic, Span, Stmt, StmtKind, Type,
};

type Result<T> = std::result::Result<T, Diagnostic>;

pub fn check(module: &syntax::Module) -> Result<ir::Program> {
    check_with_types(module, |_, _| {})
}

/// Visit each typed source expression, including unreachable branches.
pub fn check_with_types(
    module: &syntax::Module,
    mut record_type: impl FnMut(&Expr, Type),
) -> Result<ir::Program> {
    let mut names = HashMap::new();
    for (id, function) in module.functions.iter().enumerate() {
        if names.insert(function.name.as_str(), id).is_some() {
            return Err(duplicate(&function.name, function.span));
        }
    }

    let entry = names.get("main").copied().ok_or_else(|| {
        Diagnostic::new(
            "GPP-ENTRY-001",
            "expected pub fn main() -> I64 !{}",
            Span { start: 0, end: 0 },
        )
    })?;
    let main = &module.functions[entry];
    if !main.public || !main.params.is_empty() || main.result != Type::I64 {
        return Err(Diagnostic::new(
            "GPP-ENTRY-001",
            "bootstrap entry must be pub fn main() -> I64 !{}",
            main.span,
        ));
    }

    let mut functions = Vec::with_capacity(module.functions.len());
    for function in &module.functions {
        functions.push(Builder::new(module, &names, function, &mut record_type).lower()?);
    }
    let mut contract_names = HashSet::new();
    for contract in &module.contracts {
        let predicate = &contract.predicate;
        if !contract_names.insert(&predicate.name) {
            return Err(duplicate(&predicate.name, predicate.span));
        }
        // Resolve references against the production module. Predicates never
        // occupy a runtime function ID and are excluded from native output.
        Builder::new(module, &names, predicate, &mut record_type).lower()?;
    }
    let program = ir::Program { entry, functions };
    ir::validate(&program)
        .map_err(|message| Diagnostic::new("GPP-INTERNAL-001", message, main.span))?;
    Ok(program)
}

fn duplicate(name: &str, span: Span) -> Diagnostic {
    Diagnostic::new(
        "GPP-NAME-002",
        format!("duplicate declaration of '{name}' in this scope"),
        span,
    )
}

fn require(actual: Type, expected: Type, span: Span, subject: &str) -> Result<()> {
    if actual == expected {
        return Ok(());
    }
    Err(Diagnostic::new(
        "GPP-TYPE-001",
        format!("{subject} must have type {expected}, found {actual}"),
        span,
    ))
}

#[derive(Clone, Copy)]
struct Binding {
    slot: usize,
    mutable: bool,
}

#[derive(Default)]
struct OpenBlock {
    instructions: Vec<Instr>,
    term: Option<Term>,
}

struct Builder<'a, 't, F> {
    record_type: &'t mut F,
    module: &'a syntax::Module,
    names: &'a HashMap<&'a str, usize>,
    source: &'a syntax::Function,
    scopes: Vec<HashMap<String, Binding>>,
    slots: Vec<Type>,
    blocks: Vec<OpenBlock>,
    /// None means execution cannot reach the next statement. We still typecheck it.
    current: Option<usize>,
}

impl<'a, 't, F: FnMut(&Expr, Type)> Builder<'a, 't, F> {
    fn new(
        module: &'a syntax::Module,
        names: &'a HashMap<&'a str, usize>,
        source: &'a syntax::Function,
        record_type: &'t mut F,
    ) -> Self {
        Self {
            record_type,
            module,
            names,
            source,
            scopes: vec![HashMap::new()],
            slots: Vec::new(),
            blocks: vec![OpenBlock::default()],
            current: Some(0),
        }
    }

    fn lower(mut self) -> Result<ir::Function> {
        for param in &self.source.params {
            let slot = self.slot(param.ty);
            self.define(
                &param.name,
                param.span,
                Binding {
                    slot,
                    mutable: false,
                },
            )?;
        }
        self.statements(&self.source.body)?;
        if self.current.is_some() {
            if self.source.result != Type::Unit {
                return Err(Diagnostic::new(
                    "GPP-RETURN-001",
                    format!(
                        "function '{}' can complete without returning {}",
                        self.source.name, self.source.result
                    ),
                    self.source.span,
                ));
            }
            let unit = self.value(Type::Unit, Op::Unit);
            self.terminate(Term::Return(unit));
        }
        let blocks = self
            .blocks
            .into_iter()
            .map(|block| {
                let term = block.term.ok_or_else(|| {
                    Diagnostic::new(
                        "GPP-INTERNAL-001",
                        "unterminated IR block",
                        self.source.span,
                    )
                })?;
                Ok(ir::Block {
                    instructions: block.instructions,
                    term,
                })
            })
            .collect::<Result<_>>()?;
        Ok(ir::Function {
            name: self.source.name.clone(),
            params: self.source.params.len(),
            result: self.source.result,
            slots: self.slots,
            blocks,
        })
    }

    fn slot(&mut self, ty: Type) -> usize {
        let index = self.slots.len();
        self.slots.push(ty);
        index
    }

    fn value(&mut self, ty: Type, op: Op) -> usize {
        let slot = self.slot(ty);
        self.write(slot, op);
        slot
    }

    fn write(&mut self, dst: usize, op: Op) {
        if let Some(block) = self.current {
            self.blocks[block].instructions.push(Instr { dst, op });
        }
    }

    fn block(&mut self) -> usize {
        let index = self.blocks.len();
        self.blocks.push(OpenBlock::default());
        index
    }

    fn terminate(&mut self, term: Term) {
        if let Some(block) = self.current.take() {
            self.blocks[block].term = Some(term);
        }
    }

    fn define(&mut self, name: &str, span: Span, binding: Binding) -> Result<()> {
        let scope = self.scopes.last_mut().expect("a function has a root scope");
        if scope.contains_key(name) {
            return Err(duplicate(name, span));
        }
        scope.insert(name.to_owned(), binding);
        Ok(())
    }

    fn lookup(&self, name: &str) -> Option<Binding> {
        self.scopes
            .iter()
            .rev()
            .find_map(|scope| scope.get(name).copied())
    }

    fn resolve(&self, name: &str, span: Span) -> Result<Binding> {
        self.lookup(name).ok_or_else(|| {
            Diagnostic::new("GPP-NAME-001", format!("undefined local '{name}'"), span)
        })
    }

    fn nested(&mut self, statements: &[Stmt]) -> Result<()> {
        self.scopes.push(HashMap::new());
        let result = self.statements(statements);
        self.scopes.pop();
        result
    }

    fn statements(&mut self, statements: &[Stmt]) -> Result<()> {
        for stmt in statements {
            match &stmt.kind {
                StmtKind::Bind {
                    mutable,
                    name,
                    annotation,
                    value,
                } => {
                    let init = self.expr(value)?;
                    let ty = self.slots[init];
                    if let Some(expected) = annotation {
                        require(ty, *expected, value.span, "initializer")?;
                    }
                    // A new binding owns a slot even when initialized from another local.
                    let slot = self.value(ty, Op::Copy(init));
                    self.define(
                        name,
                        stmt.span,
                        Binding {
                            slot,
                            mutable: *mutable,
                        },
                    )?;
                }
                StmtKind::Assign { name, value } => {
                    let binding = self.resolve(name, stmt.span)?;
                    if !binding.mutable {
                        return Err(Diagnostic::new(
                            "GPP-MUT-001",
                            format!("cannot assign to immutable '{name}'"),
                            stmt.span,
                        ));
                    }
                    let new = self.expr(value)?;
                    require(
                        self.slots[new],
                        self.slots[binding.slot],
                        value.span,
                        "assigned value",
                    )?;
                    self.write(binding.slot, Op::Copy(new));
                }
                StmtKind::Return(value) => {
                    let result = self.expr(value)?;
                    require(
                        self.slots[result],
                        self.source.result,
                        value.span,
                        "return value",
                    )?;
                    self.terminate(Term::Return(result));
                }
                StmtKind::If {
                    cond,
                    then_body,
                    else_body,
                } => self.conditional(cond, then_body, else_body)?,
                StmtKind::While { cond, body } => self.while_loop(cond, body)?,
                StmtKind::Expr(value) => {
                    self.expr(value)?;
                }
            }
        }
        Ok(())
    }

    fn condition(&mut self, expr: &Expr) -> Result<usize> {
        let value = self.expr(expr)?;
        require(self.slots[value], Type::Bool, expr.span, "condition")?;
        Ok(value)
    }

    fn branches(&mut self, cond: &Expr) -> Result<(Option<usize>, Option<usize>)> {
        let condition = self.condition(cond)?;
        Ok(match (self.current, &cond.kind) {
            (None, _) => (None, None),
            (start, ExprKind::Bool(true)) => (start, None),
            (start, ExprKind::Bool(false)) => (None, start),
            (Some(_), _) => {
                let yes = self.block();
                let no = self.block();
                self.terminate(Term::Branch { condition, yes, no });
                (Some(yes), Some(no))
            }
        })
    }

    fn conditional(&mut self, cond: &Expr, then_body: &[Stmt], else_body: &[Stmt]) -> Result<()> {
        let (yes, no) = self.branches(cond)?;
        self.current = yes;
        self.nested(then_body)?;
        let left = self.current;
        self.current = no;
        self.nested(else_body)?;
        self.join(left);
        Ok(())
    }

    fn join(&mut self, left: Option<usize>) {
        self.current = match (left, self.current) {
            (Some(left), Some(right)) => {
                let join = self.block();
                self.blocks[left].term = Some(Term::Jump(join));
                self.blocks[right].term = Some(Term::Jump(join));
                Some(join)
            }
            (left, right) => left.or(right),
        };
    }

    fn conditional_value(&mut self, cond: &Expr, yes: &Expr, no: &Expr) -> Result<usize> {
        let (then_block, else_block) = self.branches(cond)?;
        self.current = then_block;
        let first = self.expr(yes)?;
        let ty = self.slots[first];
        let result = self.value(ty, Op::Copy(first));
        let left = self.current;
        self.current = else_block;
        let second = self.expr(no)?;
        require(self.slots[second], ty, no.span, "else value")?;
        self.write(result, Op::Copy(second));
        self.join(left);
        Ok(result)
    }

    fn while_loop(&mut self, cond: &Expr, body: &[Stmt]) -> Result<()> {
        if self.current.is_none() {
            self.condition(cond)?;
            return self.nested(body);
        }
        let header = self.block();
        self.terminate(Term::Jump(header));
        self.current = Some(header);
        let condition = self.condition(cond)?;
        let yes = self.block();
        // This subset has no break, so a literal true loop cannot fall through.
        let exit = if matches!(cond.kind, ExprKind::Bool(true)) {
            self.terminate(Term::Jump(yes));
            None
        } else {
            let no = self.block();
            self.terminate(Term::Branch { condition, yes, no });
            Some(no)
        };
        self.current = Some(yes);
        self.nested(body)?;
        self.terminate(Term::Jump(header));
        self.current = exit;
        Ok(())
    }

    fn expr(&mut self, expr: &Expr) -> Result<usize> {
        let slot = match &expr.kind {
            ExprKind::Int(number) => self.value(Type::I64, Op::Int(*number)),
            ExprKind::Bool(boolean) => self.value(Type::Bool, Op::Bool(*boolean)),
            ExprKind::Unit => self.value(Type::Unit, Op::Unit),
            ExprKind::Name(name) => self.resolve(name, expr.span)?.slot,
            ExprKind::Call(name, arguments) => self.call(name, arguments, expr.span)?,
            ExprKind::If { cond, yes, no } => self.conditional_value(cond, yes, no)?,
            ExprKind::AsI64(operand) => {
                let slot = self.expr(operand)?;
                match self.slots[slot] {
                    Type::I64 => slot,
                    Type::Bool => self.value(Type::I64, Op::BoolToI64(slot)),
                    Type::Unit => {
                        return Err(Diagnostic::new(
                            "GPP-TYPE-001",
                            "cannot convert Unit to I64",
                            operand.span,
                        ));
                    }
                }
            }
            ExprKind::Unary(op, operand) => {
                let slot = self.expr(operand)?;
                let (expected, result) = ir::unary_types(*op);
                require(self.slots[slot], expected, operand.span, "unary operand")?;
                self.value(result, Op::Unary(*op, slot))
            }
            ExprKind::Binary(op @ (BinOp::And | BinOp::Or), left, right) => {
                self.logical(*op, left, right)?
            }
            ExprKind::Binary(op, left, right) => {
                let a = self.expr(left)?;
                let b = self.expr(right)?;
                let lhs = self.slots[a];
                let rhs = self.slots[b];
                let result = ir::binary_result(*op, lhs, rhs).ok_or_else(|| {
                    Diagnostic::new(
                        "GPP-TYPE-001",
                        format!("operator '{op}' cannot take {lhs} and {rhs}"),
                        expr.span,
                    )
                })?;
                self.value(result, Op::Binary(*op, a, b))
            }
        };
        (self.record_type)(expr, self.slots[slot]);
        Ok(slot)
    }

    fn call(&mut self, name: &str, arguments: &[Expr], span: Span) -> Result<usize> {
        if self.lookup(name).is_some() {
            return Err(Diagnostic::new(
                "GPP-TYPE-001",
                format!("local '{name}' is not callable"),
                span,
            ));
        }
        if let Some(&id) = self.names.get(name) {
            let callee = &self.module.functions[id];
            let slots =
                self.arguments(name, arguments, callee.params.iter().map(|p| p.ty), span)?;
            return Ok(self.value(callee.result, Op::Call(id, slots)));
        }
        let intrinsic = Intrinsic::named(name).ok_or_else(|| {
            Diagnostic::new("GPP-NAME-001", format!("undefined function '{name}'"), span)
        })?;
        let slots = self.arguments(
            name,
            arguments,
            std::iter::repeat_n(Type::I64, intrinsic.arity()),
            span,
        )?;
        Ok(self.value(Type::I64, Op::Intrinsic(intrinsic, slots)))
    }

    fn arguments(
        &mut self,
        name: &str,
        arguments: &[Expr],
        types: impl ExactSizeIterator<Item = Type>,
        span: Span,
    ) -> Result<Vec<usize>> {
        if arguments.len() != types.len() {
            return Err(Diagnostic::new(
                "GPP-CALL-001",
                format!(
                    "'{name}' expects {} arguments, found {}",
                    types.len(),
                    arguments.len()
                ),
                span,
            ));
        }
        let mut slots = Vec::with_capacity(arguments.len());
        for (argument, ty) in arguments.iter().zip(types) {
            let slot = self.expr(argument)?;
            require(self.slots[slot], ty, argument.span, "argument")?;
            slots.push(slot);
        }
        Ok(slots)
    }

    fn logical(&mut self, op: BinOp, left: &Expr, right: &Expr) -> Result<usize> {
        let lhs = self.condition(left)?;
        let result = self.value(Type::Bool, Op::Copy(lhs));
        if self.current.is_none() {
            self.condition(right)?;
            return Ok(result);
        }
        let evaluate_rhs = self.block();
        let join = self.block();
        let (yes, no) = if op == BinOp::And {
            (evaluate_rhs, join)
        } else {
            (join, evaluate_rhs)
        };
        self.terminate(Term::Branch {
            condition: lhs,
            yes,
            no,
        });
        self.current = Some(evaluate_rhs);
        let rhs = self.condition(right)?;
        self.write(result, Op::Copy(rhs));
        self.terminate(Term::Jump(join));
        self.current = Some(join);
        Ok(result)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn check_source(body: &str) -> Result<ir::Program> {
        let module = syntax::parse(&format!("module test_suite; {body}"))?;
        check(&module)
    }

    #[test]
    fn checks_both_value_arms_conditions_and_compound_assignment_targets() {
        for (body, code) in [
            ("let n = if 1 { 3 } else { 4 }; return n;", "GPP-TYPE-001"),
            ("return if true { 3 } else { false };", "GPP-TYPE-001"),
            ("return if true { 3 } else { missing };", "GPP-NAME-001"),
            ("let n = 0; n += 1; return n;", "GPP-MUT-001"),
            ("var n = 0; n *= true; return n;", "GPP-TYPE-001"),
        ] {
            let err =
                check_source(&format!("pub fn main() -> I64 !{{}} {{ {body} }}")).unwrap_err();
            assert_eq!(err.code, code, "{body}");
        }
    }

    #[test]
    fn same_scope_duplicates_are_errors_but_a_nested_scope_can_shadow() {
        let good = "pub fn main() -> I64 !{} {
            var x = 1; if true { let x = x + 1; return x; } return x;
        }";
        check_source(good).unwrap();
        let cases = [
            "fn f(x: I64) -> I64 !{} { let x = 1; return x; }",
            "fn f(x: I64, x: Bool) -> Unit !{} {}",
            "fn f() -> Unit !{} {} fn f() -> Unit !{} {}",
        ];
        for case in cases {
            let error = check_source(&format!("{good} {case}")).unwrap_err();
            assert_eq!(error.code, "GPP-NAME-002", "{case}");
        }
    }

    #[test]
    fn unreachable_statements_and_uncalled_functions_are_checked() {
        let good = "pub fn main() -> I64 !{} { return 42; }";
        for bad in [
            "fn f() -> Unit !{} { return (); unknown(); }",
            "fn f() -> Unit !{} { while true {} if missing {} }",
            "fn f() -> Unit !{} { let a = a; }",
        ] {
            assert_eq!(
                check_source(&format!("{good} {bad}")).unwrap_err().code,
                "GPP-NAME-001"
            );
        }
    }

    #[test]
    fn unit_fallthrough_forward_calls_and_noncompleting_loops() {
        let text = "pub fn main() -> I64 !{} { no_op(); return later(false); }
                    fn forever() -> I64 !{} { if true { while true {} } }
                    fn later(flag: Bool) -> I64 !{} {
                        if flag { return forever(); } else { return 42; }
                    }
                    fn no_op() -> Unit !{} {}";
        check_source(text).unwrap();
        let partial = "pub fn main() -> I64 !{} { return 0; }
                       fn f(x: Bool) -> I64 !{} { if x { return 1; } }";
        assert_eq!(check_source(partial).unwrap_err().code, "GPP-RETURN-001");
    }

    #[test]
    fn error_codes_and_spans_point_at_the_offending_value() {
        let text = "module demo; fn f(n: Bool) -> I64 !{} { return 0; }
                    pub fn main() -> I64 !{} { return f(42); }";
        let err = check(&syntax::parse(text).unwrap()).unwrap_err();
        assert_eq!(err.code, "GPP-TYPE-001");
        assert_eq!(&text[err.span.start..err.span.end], "42");
        assert!(err.message.contains("Bool") && err.message.contains("I64"));
    }
}
