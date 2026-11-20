//! Internal scalar control-flow IR. Operands refer to function-local slots.
//! Every instruction assigns one slot; a call always has a destination, even for Unit.
use std::collections::HashSet;

pub use crate::syntax::{BinOp, Intrinsic, Type, UnOp};

#[derive(Debug)]
pub struct Program {
    pub functions: Vec<Function>,
    pub entry: usize,
}

#[derive(Debug)]
pub struct Function {
    pub name: String,
    /// Parameters are stored in the first `params` slots on entry.
    pub params: usize,
    pub result: Type,
    pub slots: Vec<Type>,
    pub blocks: Vec<Block>,
}

#[derive(Debug)]
pub struct Block {
    pub instructions: Vec<Instr>,
    pub term: Term,
}

#[derive(Debug)]
pub struct Instr {
    pub dst: usize,
    pub op: Op,
}

#[derive(Debug)]
pub enum Op {
    Int(i64),
    Bool(bool),
    Unit,
    Copy(usize),
    BoolToI64(usize),
    Intrinsic(Intrinsic, Vec<usize>),
    Unary(UnOp, usize),
    Binary(BinOp, usize, usize),
    Call(usize, Vec<usize>),
}

#[derive(Debug)]
pub enum Term {
    Jump(usize),
    Branch {
        condition: usize,
        yes: usize,
        no: usize,
    },
    Return(usize),
}

pub(crate) fn unary_types(op: UnOp) -> (Type, Type) {
    match op {
        UnOp::Neg => (Type::I64, Type::I64),
        UnOp::Not => (Type::Bool, Type::Bool),
    }
}

pub(crate) fn binary_result(op: BinOp, left: Type, right: Type) -> Option<Type> {
    use BinOp::*;
    if left != right {
        return None;
    }
    match op {
        Add | Sub | Mul | Div | Rem if left == Type::I64 => Some(Type::I64),
        Lt | Le | Gt | Ge if left == Type::I64 => Some(Type::Bool),
        Eq | Ne => Some(Type::Bool),
        And | Or if left == Type::Bool => Some(Type::Bool),
        _ => None,
    }
}

/// Reject malformed indices, types, control flow, and reads that can reach
/// the function entry without passing through a definition.
pub fn validate(program: &Program) -> Result<(), String> {
    let entry = program
        .functions
        .get(program.entry)
        .ok_or("invalid entry index")?;
    if entry.name != "main" || entry.params != 0 || entry.result != Type::I64 {
        return Err("invalid bootstrap entry signature".into());
    }
    for function in &program.functions {
        validate_function(program, function)
            .map_err(|message| format!("{}: {message}", function.name))?;
    }
    Ok(())
}

fn validate_function(program: &Program, function: &Function) -> Result<(), String> {
    let count = function.blocks.len();
    if function.params > function.slots.len() || count == 0 {
        return Err("invalid parameter slots or missing entry block".into());
    }
    let mut predecessors = vec![Vec::new(); count];
    let mut definitions = vec![HashSet::new(); count];
    let mut needs_definition = Vec::new();

    for (index, block) in function.blocks.iter().enumerate() {
        let defined = &mut definitions[index];
        for instruction in &block.instructions {
            let mut operand =
                |slot| read_slot(function, defined, &mut needs_definition, index, slot);
            let result = match &instruction.op {
                Op::Int(_) => Type::I64,
                Op::Bool(_) => Type::Bool,
                Op::Unit => Type::Unit,
                Op::Copy(source) => operand(*source)?,
                Op::BoolToI64(source) => {
                    if operand(*source)? != Type::Bool {
                        return Err("invalid Bool-to-I64 operand".into());
                    }
                    Type::I64
                }
                Op::Intrinsic(op, args) => {
                    if args.len() != op.arity() {
                        return Err("incorrect intrinsic arity".into());
                    }
                    for &arg in args {
                        if operand(arg)? != Type::I64 {
                            return Err("intrinsic operand must be I64".into());
                        }
                    }
                    Type::I64
                }
                Op::Unary(op, source) => {
                    let (expected, result) = unary_types(*op);
                    if operand(*source)? != expected {
                        return Err("invalid unary operand type".into());
                    }
                    result
                }
                Op::Binary(BinOp::And | BinOp::Or, _, _) => {
                    return Err("logical operators must lower to branches".into());
                }
                Op::Binary(op, left, right) => {
                    binary_result(*op, operand(*left)?, operand(*right)?)
                        .ok_or("invalid binary operand types")?
                }
                Op::Call(index, arguments) => {
                    let callee = program
                        .functions
                        .get(*index)
                        .ok_or("invalid callee index")?;
                    let parameters = callee
                        .slots
                        .get(..callee.params)
                        .ok_or("invalid signature")?;
                    if arguments.len() != parameters.len() {
                        return Err("incorrect argument count".into());
                    }
                    for (&argument, &expected) in arguments.iter().zip(parameters) {
                        if operand(argument)? != expected {
                            return Err("incorrect argument type".into());
                        }
                    }
                    callee.result
                }
            };
            if function.slots.get(instruction.dst) != Some(&result) {
                return Err("invalid instruction destination or result type".into());
            }
            defined.insert(instruction.dst);
        }
        let mut edge = |target: usize| -> Result<(), String> {
            predecessors
                .get_mut(target)
                .ok_or("invalid branch target")?
                .push(index);
            Ok(())
        };
        match block.term {
            Term::Jump(target) => edge(target)?,
            Term::Branch { condition, yes, no } => {
                if read_slot(function, defined, &mut needs_definition, index, condition)?
                    != Type::Bool
                {
                    return Err("branch condition must be Bool".into());
                }
                edge(yes)?;
                edge(no)?;
            }
            Term::Return(value) => {
                if read_slot(function, defined, &mut needs_definition, index, value)?
                    != function.result
                {
                    return Err("incorrect return type".into());
                }
            }
        }
    }

    // The builder only creates reachable blocks. Enforce that invariant so
    // initialization can consider each predecessor without special cases.
    let mut reachable = vec![false; count];
    let mut work = vec![0];
    while let Some(index) = work.pop() {
        if reachable[index] {
            continue;
        }
        reachable[index] = true;
        match function.blocks[index].term {
            Term::Jump(next) => work.push(next),
            Term::Branch { yes, no, .. } => work.extend([yes, no]),
            Term::Return(_) => {}
        }
    }
    if reachable.contains(&false) {
        return Err("unreachable basic block".into());
    }

    // Start only at actual reads before the first local write in a block.
    // A write in a predecessor kills the query along that incoming edge.
    let mut checked = HashSet::new();
    while let Some((block, slot)) = needs_definition.pop() {
        if !checked.insert((block, slot)) {
            continue;
        }
        if block == 0 && slot >= function.params {
            return Err(format!("slot {slot} can be read before initialization"));
        }
        for &pred in &predecessors[block] {
            if !definitions[pred].contains(&slot) {
                needs_definition.push((pred, slot));
            }
        }
    }
    Ok(())
}

fn read_slot(
    function: &Function,
    defined: &HashSet<usize>,
    needs_definition: &mut Vec<(usize, usize)>,
    block: usize,
    slot: usize,
) -> Result<Type, String> {
    let ty = function.slots.get(slot).ok_or("invalid operand slot")?;
    if !defined.contains(&slot) {
        needs_definition.push((block, slot));
    }
    Ok(*ty)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn program(slots: Vec<Type>, blocks: Vec<Block>) -> Program {
        Program {
            entry: 0,
            functions: vec![Function {
                name: "main".into(),
                params: 0,
                result: Type::I64,
                slots,
                blocks,
            }],
        }
    }

    fn block(writes: Vec<(usize, Op)>, term: Term) -> Block {
        let instructions = writes
            .into_iter()
            .map(|(dst, op)| Instr { dst, op })
            .collect();
        Block { instructions, term }
    }

    #[test]
    fn invalid_references_and_types_fail_validation() {
        let bad_blocks = [
            block(vec![(0, Op::Call(1, vec![]))], Term::Return(0)),
            block(vec![(0, Op::Copy(1))], Term::Return(0)),
            block(vec![(1, Op::Int(42))], Term::Return(0)),
            block(vec![(0, Op::Bool(true))], Term::Return(0)),
            block(
                vec![(0, Op::Int(42))],
                Term::Branch {
                    condition: 0,
                    yes: 0,
                    no: 0,
                },
            ),
            block(vec![], Term::Jump(1)),
            block(vec![], Term::Return(0)),
        ];
        for entry in bad_blocks {
            assert!(validate(&program(vec![Type::I64], vec![entry])).is_err());
        }
    }

    #[test]
    fn a_join_requires_a_definition_on_both_incoming_edges() {
        let mut cfg = program(
            vec![Type::Bool, Type::I64],
            vec![
                block(
                    vec![(0, Op::Bool(true))],
                    Term::Branch {
                        condition: 0,
                        yes: 1,
                        no: 2,
                    },
                ),
                block(vec![(1, Op::Int(42))], Term::Jump(3)),
                block(vec![], Term::Jump(3)),
                block(vec![], Term::Return(1)),
            ],
        );
        assert!(
            validate(&cfg)
                .unwrap_err()
                .contains("before initialization")
        );
        cfg.functions[0].blocks[2].instructions.push(Instr {
            dst: 1,
            op: Op::Int(0),
        });
        validate(&cfg).unwrap();
    }
}
