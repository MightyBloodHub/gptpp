//! A versioned C ABI with checked scalar inputs and recoverable arithmetic faults.
use crate::syntax::{Function, Type};
use crate::{check, diagnostic, native, syntax};
use std::ffi::OsString;
use std::fmt::Write;
use std::fs;
use std::path::PathBuf;

const HELP: &str = "usage: gpp library FILE (-o SHARED_LIBRARY | --header) [-O0|-O2]";

fn scalar(ty: Type) -> bool {
    matches!(ty, Type::I64 | Type::Bool | Type::Unit)
}

fn llvm_type(ty: Type) -> &'static str {
    if ty == Type::I64 { "i64" } else { "i1" }
}

fn export(
    function: &Function,
    id: usize,
    llvm: &mut String,
    shim: &mut String,
    header: &mut String,
) {
    let mut c_args = Vec::new();
    let mut bridge_args = Vec::new();
    let mut llvm_args = Vec::new();
    let mut conversions = String::new();
    let mut checked_args = Vec::new();
    let mut invalid = vec!["!out".to_string()];
    for (i, param) in function.params.iter().enumerate() {
        let arg = format!("a{i}");
        c_args.push(format!("int64_t {arg}"));
        bridge_args.push(arg.clone());
        llvm_args.push(format!("i64 %{arg}"));
        if param.ty == Type::I64 {
            checked_args.push(format!("i64 %{arg}"));
        } else {
            if param.ty == Type::Bool {
                invalid.push(format!("({arg} != 0 && {arg} != 1)"));
            } else {
                invalid.push(format!("{arg} != 0"));
            }
            writeln!(conversions, "  %n{i} = trunc i64 %{arg} to i1").unwrap();
            checked_args.push(format!("i1 %n{i}"));
        }
    }
    let args = llvm_args.join(", ");
    let call = checked_args.join(", ");
    let result_ty = llvm_type(function.result);
    writeln!(llvm, "define hidden i64 @gpp_bridge_{id}({args}) {{\n{conversions}  %v = call {result_ty} @gpp_fn_{id}({call})").unwrap();
    if function.result == Type::I64 {
        llvm.push_str("  ret i64 %v\n}\n");
    } else if function.result == Type::Bool {
        llvm.push_str("  %w = zext i1 %v to i64\n  ret i64 %w\n}\n");
    } else {
        llvm.push_str("  ret i64 0\n}\n");
    }
    let bridge_decl = if c_args.is_empty() {
        "void".into()
    } else {
        c_args.join(", ")
    };
    c_args.push("int64_t *out".into());
    let decl = format!("int32_t gpp_v1_{}({})", function.name, c_args.join(", "));
    writeln!(header, "{decl};").unwrap();
    let invalid = invalid.join(" || ");
    let call = bridge_args.join(", ");
    writeln!(
        shim,
        "extern int64_t gpp_bridge_{id}({bridge_decl});
__attribute__((visibility(\"default\"))) {decl} {{
    if ({invalid}) return 4;
    jmp_buf frame;
    jmp_buf *prior = gpp_boundary;
    if (setjmp(frame)) {{
        gpp_boundary = prior;
        return gpp_fault_code;
    }}
    gpp_boundary = &frame;
    int64_t value = gpp_bridge_{id}({call});
    gpp_boundary = prior;
    *out = value;
    return 0;
}}"
    )
    .unwrap();
}

pub fn run(mut args: impl Iterator<Item = OsString>) -> Result<u8, String> {
    let file = PathBuf::from(args.next().ok_or(HELP)?);
    let mut output = None;
    let mut header_only = false;
    let mut optimize = true;
    while let Some(arg) = args.next() {
        match arg.to_str() {
            Some("-o") if output.is_none() => {
                output = Some(PathBuf::from(args.next().ok_or(HELP)?))
            }
            Some("--header") => header_only = true,
            Some("-O0") => optimize = false,
            Some("-O2") => optimize = true,
            _ => return Err(HELP.into()),
        }
    }
    if header_only == output.is_some() {
        return Err(HELP.into());
    }
    if let Some(out) = &output
        && let Ok(path) = fs::canonicalize(out)
        && Some(path) == fs::canonicalize(&file).ok()
    {
        return Err("library output would overwrite the input source".into());
    }
    let source = fs::read_to_string(&file).map_err(|e| format!("{}: {e}", file.display()))?;
    let module = syntax::parse(&source).map_err(|d| diagnostic(&file, &source, d, false))?;
    let program = check::check(&module).map_err(|d| diagnostic(&file, &source, d, false))?;
    let mut llvm = native::emit_functions(&program)?;
    let mut shim = include_str!("library_runtime.c").to_string();
    let mut header = String::from(
        "/* GPT++ scalar ABI v1. I64 uses int64_t, Bool uses 0/1, Unit uses 0.\n * Status: 0 success, 1 integer overflow, 2 division by zero, 3 invalid bounds,\n * 4 invalid ABI argument. Only success writes the non-null output pointer. */\n#include <stdint.h>\n#ifdef __cplusplus\nextern \"C\" {\n#endif\n",
    );
    let mut count = 0;
    for (id, function) in module.functions.iter().enumerate() {
        if !function.public || function.name == "main" {
            continue;
        }
        if !scalar(function.result) || function.params.iter().any(|p| !scalar(p.ty)) {
            return Err(format!(
                "{}: exported functions require I64, Bool or Unit parameters and results; use a scalar facade for structured values",
                function.name
            ));
        }
        export(function, id, &mut llvm, &mut shim, &mut header);
        count += 1;
    }
    if count == 0 {
        return Err("no public functions to export besides main".into());
    }
    if let Some(out) = output {
        native::link(&llvm, &shim, &out, optimize, true)?;
    } else {
        print!("{header}#ifdef __cplusplus\n}}\n#endif\n");
    }
    Ok(0)
}
