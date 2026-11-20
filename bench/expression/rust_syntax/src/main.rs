//! Print source ranges for a Rust function's expressions or check one proposed expression.
use std::io::{self, Read};
use syn::{Expr, Item, spanned::Spanned, visit::Visit};

struct Catalog;

impl<'ast> Visit<'ast> for Catalog {
    fn visit_expr(&mut self, expression: &'ast Expr) {
        let span = expression.span().byte_range();
        println!("{} {}", span.start, span.end);
        syn::visit::visit_expr(self, expression);
    }
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mode = std::env::args()
        .nth(1)
        .ok_or("expected --check or a function name")?;
    let mut text = String::new();
    io::stdin().read_to_string(&mut text)?;
    if mode == "--check" {
        syn::parse_str::<Expr>(&text)?;
    } else {
        let module = syn::parse_file(&text)?;
        for item in module.items {
            if let Item::Fn(function) = item
                && function.sig.ident == mode
            {
                Catalog.visit_block(&function.block);
                return Ok(());
            }
        }
        return Err("target function missing".into());
    }
    Ok(())
}
