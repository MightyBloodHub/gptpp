//! LLVM lowering for the bootstrap ABI. Each IR slot starts as a stack cell.
//! LLVM's optimization pipeline may promote these cells to SSA registers.

use crate::ir::{self, BinOp, Function, Intrinsic, Op, Program, Term, Type, UnOp};
use std::env;
use std::fmt::Write as _;
use std::fs;
use std::io;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};

const RUNNER: &str = include_str!("bootstrap.c");
const LLVM_RELEASE: &str = "22.1.8";

// Bool and Unit share an internal representation. Unit's only value is false.
// The public bootstrap entry always returns i64 to the C runner.
fn llvm_type(ty: Type) -> &'static str {
    match ty {
        Type::I64 => "i64",
        Type::Bool | Type::Unit => "i1",
    }
}

fn emit_arithmetic_helpers(out: &mut String) {
    out.push_str("declare void @gpp_fault(i32) noreturn\n");
    for op in ["add", "sub", "mul"] {
        writeln!(
            out,
            "
declare {{ i64, i1 }} @llvm.s{op}.with.overflow.i64(i64, i64)
define internal i64 @checked_{op}(i64 %a, i64 %b) {{
entry:
  %pair = call {{ i64, i1 }} @llvm.s{op}.with.overflow.i64(i64 %a, i64 %b)
  %overflow = extractvalue {{ i64, i1 }} %pair, 1
  br i1 %overflow, label %fault, label %ok
fault:
  call void @gpp_fault(i32 1)
  unreachable
ok:
  %value = extractvalue {{ i64, i1 }} %pair, 0
  ret i64 %value
}}"
        )
        .unwrap();
    }
    out.push_str(
        "
define internal i64 @checked_div(i64 %a, i64 %b) {
entry:
  %zero = icmp eq i64 %b, 0
  br i1 %zero, label %by_zero, label %check_overflow
by_zero:
  call void @gpp_fault(i32 2)
  unreachable
check_overflow:
  %min = icmp eq i64 %a, -9223372036854775808
  %minus_one = icmp eq i64 %b, -1
  %overflow = and i1 %min, %minus_one
  br i1 %overflow, label %bad_quotient, label %ok
bad_quotient:
  call void @gpp_fault(i32 1)
  unreachable
ok:
  %quotient = sdiv i64 %a, %b
  ret i64 %quotient
}

define internal i64 @checked_rem(i64 %a, i64 %b) {
entry:
  %zero = icmp eq i64 %b, 0
  br i1 %zero, label %by_zero, label %ok
by_zero:
  call void @gpp_fault(i32 2)
  unreachable
ok:
  ; Both 1 and -1 give remainder zero. Selecting 1 also makes MIN % -1 defined.
  %minus_one = icmp eq i64 %b, -1
  %divisor = select i1 %minus_one, i64 1, i64 %b
  %value = srem i64 %a, %divisor
  ret i64 %value
}
",
    );
}

struct FunctionEmitter<'a> {
    out: &'a mut String,
    function: &'a Function,
    next_reg: usize,
}

impl FunctionEmitter<'_> {
    fn register(&mut self, instruction: &str) -> String {
        let name = format!("%v{}", self.next_reg);
        self.next_reg += 1;
        writeln!(self.out, "  {name} = {instruction}").unwrap();
        name
    }

    fn load(&mut self, slot: usize) -> String {
        let ty = llvm_type(self.function.slots[slot]);
        self.register(&format!("load {ty}, ptr %s{slot}"))
    }

    fn value(&mut self, op: &Op, ty: &str) -> Result<String, String> {
        Ok(match op {
            Op::Int(n) => n.to_string(),
            Op::Bool(b) => b.to_string(),
            Op::Unit => "false".into(),
            Op::Copy(slot) => self.load(*slot),
            Op::BoolToI64(slot) => {
                let bit = self.load(*slot);
                self.register(&format!("zext i1 {bit} to i64"))
            }
            Op::Intrinsic(op, args) => {
                let callee = match op {
                    Intrinsic::Min => "llvm.smin.i64",
                    Intrinsic::Max => "llvm.smax.i64",
                    Intrinsic::Clamp => "checked_clamp",
                };
                let operands = args
                    .iter()
                    .map(|&s| format!("i64 {}", self.load(s)))
                    .collect::<Vec<_>>();
                self.register(&format!("call i64 @{callee}({})", operands.join(", ")))
            }
            Op::Unary(op, slot) => {
                let a = self.load(*slot);
                match op {
                    UnOp::Neg => self.register(&format!("call i64 @checked_sub(i64 0, i64 {a})")),
                    UnOp::Not => self.register(&format!("xor i1 {a}, true")),
                }
            }
            Op::Binary(op, left, right) => {
                let operand_type = llvm_type(self.function.slots[*left]);
                let a = self.load(*left);
                let b = self.load(*right);
                let code = match op {
                    BinOp::Add => "add",
                    BinOp::Sub => "sub",
                    BinOp::Mul => "mul",
                    BinOp::Div => "div",
                    BinOp::Rem => "rem",
                    BinOp::Eq => "eq",
                    BinOp::Ne => "ne",
                    BinOp::Lt => "slt",
                    BinOp::Le => "sle",
                    BinOp::Gt => "sgt",
                    BinOp::Ge => "sge",
                    BinOp::And | BinOp::Or => {
                        return Err("logical operator requires IR branches".into());
                    }
                };
                match op {
                    BinOp::Add | BinOp::Sub | BinOp::Mul | BinOp::Div | BinOp::Rem => {
                        self.register(&format!("call i64 @checked_{code}(i64 {a}, i64 {b})"))
                    }
                    _ => self.register(&format!("icmp {code} {operand_type} {a}, {b}")),
                }
            }
            Op::Call(callee, args) => {
                let mut operands = Vec::with_capacity(args.len());
                for &slot in args {
                    let arg_type = llvm_type(self.function.slots[slot]);
                    operands.push(format!("{arg_type} {}", self.load(slot)));
                }
                self.register(&format!(
                    "call {ty} @gpp_fn_{callee}({})",
                    operands.join(", ")
                ))
            }
        })
    }

    fn emit(mut self, id: usize) -> Result<(), String> {
        let function = self.function;
        let result = llvm_type(function.result);
        let params: Vec<_> = function.slots[..function.params]
            .iter()
            .enumerate()
            .map(|(i, &ty)| format!("{} %arg{i}", llvm_type(ty)))
            .collect();
        writeln!(
            self.out,
            "\ndefine internal {result} @gpp_fn_{id}({}) {{\nentry:",
            params.join(", ")
        )
        .unwrap();
        for (i, &ty) in function.slots.iter().enumerate() {
            writeln!(self.out, "  %s{i} = alloca {}", llvm_type(ty)).unwrap();
        }
        for (i, &ty) in function.slots[..function.params].iter().enumerate() {
            writeln!(self.out, "  store {} %arg{i}, ptr %s{i}", llvm_type(ty)).unwrap();
        }
        self.out.push_str("  br label %bb0\n");
        for (index, block) in function.blocks.iter().enumerate() {
            writeln!(self.out, "bb{index}:").unwrap();
            for instruction in &block.instructions {
                let dst = instruction.dst;
                let ty = llvm_type(function.slots[dst]);
                let value = self.value(&instruction.op, ty)?;
                writeln!(self.out, "  store {ty} {value}, ptr %s{dst}").unwrap();
            }
            match block.term {
                Term::Jump(dest) => writeln!(self.out, "  br label %bb{dest}").unwrap(),
                Term::Branch { condition, yes, no } => {
                    let test = self.load(condition);
                    writeln!(self.out, "  br i1 {test}, label %bb{yes}, label %bb{no}").unwrap();
                }
                Term::Return(slot) => {
                    let value = self.load(slot);
                    writeln!(self.out, "  ret {result} {value}").unwrap();
                }
            }
        }
        self.out.push_str("}\n");
        Ok(())
    }
}

pub fn emit_llvm(program: &Program) -> Result<String, String> {
    ir::validate(program)?;
    let mut out = String::new();
    emit_arithmetic_helpers(&mut out);
    out.push_str("declare i64 @llvm.smin.i64(i64, i64)\ndeclare i64 @llvm.smax.i64(i64, i64)\n");
    if program
        .functions
        .iter()
        .flat_map(|f| &f.blocks)
        .flat_map(|b| &b.instructions)
        .any(|i| matches!(i.op, Op::Intrinsic(Intrinsic::Clamp, _)))
    {
        out.push_str(
            "
define internal i64 @checked_clamp(i64 %x, i64 %lo, i64 %hi) {
entry:
  %inverted = icmp sgt i64 %lo, %hi
  br i1 %inverted, label %fault, label %ok
fault:
  call void @gpp_fault(i32 3)
  unreachable
ok:
  %lower = call i64 @llvm.smax.i64(i64 %x, i64 %lo)
  %result = call i64 @llvm.smin.i64(i64 %lower, i64 %hi)
  ret i64 %result
}
",
        );
    }
    for (id, function) in program.functions.iter().enumerate() {
        FunctionEmitter {
            out: &mut out,
            function,
            next_reg: 0,
        }
        .emit(id)?;
    }
    writeln!(
        out,
        "\ndefine i64 @gpp_entry() {{\n  %result = call i64 @gpp_fn_{}()\n  ret i64 %result\n}}",
        program.entry
    )
    .unwrap();
    Ok(out)
}

// Stage all outputs on the destination filesystem. Failed or concurrent builds
// leave the last successfully linked executable intact.
struct BuildDir(PathBuf);

impl BuildDir {
    fn create(parent: &Path) -> io::Result<Self> {
        static NEXT: AtomicU64 = AtomicU64::new(0);
        loop {
            let serial = NEXT.fetch_add(1, Ordering::Relaxed);
            let path = parent.join(format!(".gpp-build-{}-{serial}", std::process::id()));
            let mut dir = fs::DirBuilder::new();
            #[cfg(unix)]
            {
                use std::os::unix::fs::DirBuilderExt;
                dir.mode(0o700);
            }
            match dir.create(&path) {
                Ok(()) => return Ok(Self(path)),
                Err(e) if e.kind() == io::ErrorKind::AlreadyExists => continue,
                Err(e) => return Err(e),
            }
        }
    }
}

impl Drop for BuildDir {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn llvm_bin() -> Result<PathBuf, String> {
    let has_tools = |dir: &Path| dir.join("opt").is_file() && dir.join("clang").is_file();
    let dir = if let Some(value) = env::var_os("GPP_LLVM_BIN") {
        let dir = PathBuf::from(value);
        if !has_tools(&dir) {
            return Err(format!(
                "GPP_LLVM_BIN={} must contain opt and clang",
                dir.display()
            ));
        }
        dir
    } else {
        let path = env::var_os("PATH").unwrap_or_default();
        env::split_paths(&path)
            .chain(["/opt/homebrew/opt/llvm/bin", "/usr/local/opt/llvm/bin"].map(PathBuf::from))
            .find(|d| has_tools(d))
            .ok_or_else(|| {
                "cannot find opt and clang together; set GPP_LLVM_BIN to your LLVM bin directory"
                    .to_string()
            })?
    };
    let dir = dir
        .canonicalize()
        .map_err(|e| format!("LLVM tool directory: {e}"))?;
    for name in ["opt", "clang"] {
        let tool = dir.join(name);
        let version = Command::new(&tool)
            .arg("--version")
            .output()
            .map_err(|e| format!("could not query {}: {e}", tool.display()))?;
        let banner = String::from_utf8_lossy(&version.stdout);
        let release = banner
            .split_once("version ")
            .and_then(|(_, rest)| rest.split_whitespace().next());
        if !version.status.success() || release != Some(LLVM_RELEASE) {
            return Err(format!(
                "{} reports version {}. Set GPP_LLVM_BIN to the bin directory of LLVM {LLVM_RELEASE}.",
                tool.display(),
                release.unwrap_or("unknown")
            ));
        }
    }
    Ok(dir)
}

fn run(command: &mut Command) -> Result<(), String> {
    let tool = command.get_program().to_string_lossy().into_owned();
    let output = command
        .output()
        .map_err(|e| format!("could not run {tool}: {e}"))?;
    if !output.status.success() {
        let error = String::from_utf8_lossy(&output.stderr);
        return Err(format!(
            "{tool} failed ({}): {}",
            output.status,
            error.trim()
        ));
    }
    Ok(())
}

#[cfg(target_os = "macos")]
fn macos_sdk(clang: &mut Command) -> Result<(), String> {
    let sdk = match env::var_os("SDKROOT").filter(|p| !p.is_empty()) {
        Some(path) => PathBuf::from(path),
        None => {
            let query = Command::new("xcrun")
                .args(["--sdk", "macosx", "--show-sdk-path"])
                .output()
                .map_err(|e| format!("cannot locate the macOS SDK: {e}"))?;
            if !query.status.success() {
                return Err(format!(
                    "xcrun could not locate the macOS SDK: {}",
                    String::from_utf8_lossy(&query.stderr).trim()
                ));
            }
            PathBuf::from(
                String::from_utf8(query.stdout)
                    .map_err(|e| e.to_string())?
                    .trim(),
            )
        }
    };
    clang.arg("-isysroot").arg(sdk);
    Ok(())
}

pub fn build(program: &Program, output: &Path, optimize: bool) -> Result<(), String> {
    let module = emit_llvm(program)?;
    let tools = llvm_bin()?;
    let stage = BuildDir::create(output.parent().unwrap_or(Path::new(".")))
        .map_err(|e| format!("creating build directory for {}: {e}", output.display()))?;
    fs::write(stage.0.join("module.ll"), module).map_err(|e| e.to_string())?;
    fs::write(stage.0.join("bootstrap.c"), RUNNER).map_err(|e| e.to_string())?;

    let level = if optimize { "O2" } else { "O0" };
    run(Command::new(tools.join("opt"))
        .current_dir(&stage.0)
        .arg(format!("-passes=verify,default<{level}>,verify"))
        .args(["-verify-each", "module.ll", "-o", "verified.bc"]))?;
    let clang = || {
        let mut command = Command::new(tools.join("clang"));
        command.current_dir(&stage.0);
        #[cfg(target_os = "macos")]
        macos_sdk(&mut command)?;
        Ok::<_, String>(command)
    };
    // opt owns the IR pipeline. Keep its verified bitcode intact through clang's
    // frontend while selecting the corresponding machine-code optimization level.
    run(clang()?.arg(format!("-{level}")).args([
        "-Xclang",
        "-disable-llvm-passes",
        "-Wno-override-module",
        "-c",
        "verified.bc",
        "-o",
        "module.o",
    ]))?;
    run(clang()?.args(["-std=c11", "bootstrap.c", "module.o", "-o", "program"]))?;
    fs::rename(stage.0.join("program"), output)
        .map_err(|e| format!("installing executable at {}: {e}", output.display()))
}
