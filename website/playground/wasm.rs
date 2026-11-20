// The playground shares the CLI frontend, diagnostics and finite verifier. Link
// as a library so the CLI entry point and host-only backends are eliminated.
// The included native build driver uses a mutable options object only on Unix.
#![allow(dead_code, unused_mut)]
include!("../../src/main.rs");

use std::cell::RefCell;

const HASH_BYTES: usize = 64;
const MAX_SOURCE_BYTES: usize = 32 * 1024;
const PLAYGROUND_FILE: &str = "playground.gpp";

struct Bridge {
    input: Vec<u8>,
    output: Vec<u8>,
}

thread_local! {
    static BRIDGE: RefCell<Bridge> = const { RefCell::new(Bridge {
        input: Vec::new(),
        output: Vec::new(),
    }) };
}

fn invalid(message: &str) -> String {
    diagnostic(
        Path::new(PLAYGROUND_FILE),
        "",
        syntax::Diagnostic::new("GPP-IO-001", message, syntax::Span::default()),
        true,
    )
}

fn check_input(input: &[u8], budget: u32) -> Result<Vec<u8>, String> {
    let (digest, bytes) = input
        .split_at_checked(HASH_BYTES)
        .ok_or_else(|| invalid("expected a SHA-256 digest and at most 32 KiB of source"))?;
    if !digest
        .iter()
        .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(c))
    {
        return Err(invalid("expected 64 lowercase hexadecimal digest bytes"));
    }
    if u64::from(budget) > verify::DEFAULT_BUDGET {
        return Err(invalid("playground assignment budget exceeds 10000"));
    }
    let source = std::str::from_utf8(bytes).map_err(|_| invalid("source must be valid UTF-8"))?;
    let report = |d| diagnostic(Path::new(PLAYGROUND_FILE), source, d, true);
    let module = syntax::parse(source).map_err(report)?;
    check::check(&module).map_err(report)?;
    let revision = format!("sha256:{}", std::str::from_utf8(digest).unwrap());
    let mut output = Vec::new();
    verify::verify_module(&module, &revision, None, u64::from(budget), &mut output)
        .map_err(|message| invalid(&message))?;
    Ok(output)
}

/// Reserve a digest + source frame. The caller writes into the returned
/// linear-memory address before calling verify_input. Zero indicates bad size.
#[unsafe(no_mangle)]
pub extern "C" fn input_buffer(len: u32) -> u32 {
    BRIDGE.with_borrow_mut(|bridge| {
        bridge.output.clear();
        bridge.input.clear();
        if !(HASH_BYTES..=HASH_BYTES + MAX_SOURCE_BYTES).contains(&(len as usize)) {
            return 0;
        }
        bridge.input.resize(len as usize, 0);
        bridge.input.as_mut_ptr() as u32
    })
}

/// Produce exactly one UTF-8 JSON result, including on malformed requests.
#[unsafe(no_mangle)]
pub extern "C" fn verify_input(budget: u32) -> u32 {
    BRIDGE.with_borrow_mut(|bridge| {
        bridge.output = check_input(&bridge.input, budget).unwrap_or_else(String::into_bytes);
        bridge.output.len() as u32
    })
}

/// Valid until the next input_buffer or verify_input call.
#[unsafe(no_mangle)]
pub extern "C" fn output_buffer() -> u32 {
    BRIDGE.with_borrow(|bridge| {
        if bridge.output.is_empty() {
            0
        } else {
            bridge.output.as_ptr() as u32
        }
    })
}
