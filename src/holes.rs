//! Discover typed expressions to fill and the visible bindings at each source span.
use crate::{check, diagnostic, edit, json_string, syntax};
use std::io::{self, Write};
use std::{ffi::OsString, fs, path::PathBuf};

pub fn run(mut args: impl Iterator<Item = OsString>) -> Result<u8, String> {
    let usage = "gpp holes FILE [--function NAME] [--format=json]";
    let path = PathBuf::from(args.next().ok_or(usage)?);
    let mut target = None;
    let mut format = false;
    while let Some(flag) = args.next() {
        match flag.to_str() {
            Some("--function") if target.is_none() => {
                target = Some(
                    args.next()
                        .and_then(|s| s.into_string().ok())
                        .ok_or(usage)?,
                )
            }
            Some("--format=json") if !format => format = true,
            _ => return Err(usage.into()),
        }
    }
    let source = fs::read_to_string(&path).map_err(|e| format!("{}: {e}", path.display()))?;
    let report = |e| diagnostic(&path, &source, e, true);
    let module = syntax::parse(&source).map_err(report)?;
    if let Some(name) = &target {
        edit::target(&module, name)?;
    }
    let holes = check::holes(&module).map_err(report)?;
    let revision = edit::revision(source.as_bytes())?;
    let mut out = io::BufWriter::new(io::stdout().lock());
    let mut emit = || -> io::Result<()> {
        write!(
            out,
            "{{\"schema\":\"gpp.holes/1\",\"revision\":{},\"function\":{},\"holes\":[",
            json_string(&revision),
            target.as_deref().map_or("null".into(), json_string)
        )?;
        for (i, h) in holes
            .iter()
            .filter(|h| target.as_ref().is_none_or(|t| t == &h.function))
            .enumerate()
        {
            if i > 0 {
                write!(out, ",")?;
            }
            write!(
                out,
                "{{\"name\":{},\"function\":{},\"type\":{},\"start_byte\":{},\"end_byte\":{},\"locals\":[",
                json_string(&h.name),
                json_string(&h.function),
                json_string(module.type_name(h.ty)),
                h.span.start,
                h.span.end
            )?;
            for (j, (name, ty)) in h.locals.iter().enumerate() {
                if j > 0 {
                    write!(out, ",")?;
                }
                write!(
                    out,
                    "{{\"name\":{},\"type\":{}}}",
                    json_string(name),
                    json_string(module.type_name(*ty))
                )?;
            }
            write!(out, "]}}")?;
        }
        writeln!(out, "]}}")?;
        out.flush()
    };
    emit().map_err(|e| e.to_string())?;
    Ok(0)
}
