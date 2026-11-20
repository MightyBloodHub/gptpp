//! Syntax of the bootstrap language. All spans are half-open UTF-8 byte offsets.
use std::collections::{HashMap, HashSet};
use std::fmt::{self, Write};

#[derive(Clone, Copy, Debug, Default, Eq, PartialEq, Hash)]
pub struct Span {
    pub start: usize,
    pub end: usize,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Diagnostic {
    pub code: &'static str,
    pub message: String,
    pub span: Span,
}

impl Diagnostic {
    pub fn new(code: &'static str, message: impl Into<String>, span: Span) -> Self {
        Self {
            code,
            message: message.into(),
            span,
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Type {
    I64,
    Bool,
    Unit,
    Named(usize),
}

impl fmt::Display for Type {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(match self {
            Self::I64 => "I64",
            Self::Bool => "Bool",
            Self::Unit => "Unit",
            Self::Named(index) => return write!(f, "type #{index}"),
        })
    }
}

#[derive(Clone, Debug)]
pub struct Module {
    pub name: String,
    pub functions: Vec<Function>,
    pub contracts: Vec<Contract>,
    pub types: Vec<TypeDecl>,
}

#[derive(Clone, Debug)]
pub struct TypeDecl {
    pub name: String,
    pub kind: TypeKind,
    pub span: Span,
}

#[derive(Clone, Debug)]
pub enum TypeKind {
    Record(Vec<Param>),
    Enum(Vec<String>),
}

impl Module {
    pub fn type_name(&self, ty: Type) -> &str {
        match ty {
            Type::I64 => "I64",
            Type::Bool => "Bool",
            Type::Unit => "Unit",
            Type::Named(id) => &self.types[id].name,
        }
    }
    pub fn declaration(&self, name: &str) -> Option<(usize, &TypeDecl)> {
        self.types.iter().enumerate().find(|(_, t)| t.name == name)
    }
}

#[derive(Clone, Debug)]
pub struct Contract {
    /// A private Bool predicate with one return expression. Contract names are
    /// in a separate namespace and never enter the runtime function table.
    pub predicate: Function,
    pub domains: Vec<Domain>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Domain {
    Bool,
    I64 { low: i64, high: i64 },
}

#[derive(Clone, Debug)]
pub struct Function {
    pub public: bool,
    pub name: String,
    pub params: Vec<Param>,
    pub result: Type,
    pub body: Vec<Stmt>,
    pub body_span: Span,
    pub span: Span,
}

#[derive(Clone, Debug)]
pub struct Param {
    pub name: String,
    pub ty: Type,
    pub span: Span,
}

#[derive(Clone, Debug)]
pub struct Stmt {
    pub kind: StmtKind,
    pub span: Span,
}

#[derive(Clone, Debug)]
pub enum StmtKind {
    Bind {
        mutable: bool,
        name: String,
        annotation: Option<Type>,
        value: Expr,
    },
    Assign {
        name: String,
        value: Expr,
    },
    Return(Expr),
    If {
        cond: Expr,
        then_body: Vec<Stmt>,
        else_body: Vec<Stmt>,
    },
    While {
        cond: Expr,
        body: Vec<Stmt>,
    },
    Expr(Expr),
}

#[derive(Clone, Debug)]
pub struct Expr {
    pub kind: ExprKind,
    pub span: Span,
    pub site: ExprSite,
}

/// Where an expression can be replaced in concrete source.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ExprSite {
    Ordinary,
    /// An unbraced tail in `else if ...` needs a block for other replacements.
    ElseIf,
    /// Compound assignment introduces a read and a binary operation in the AST.
    Synthetic,
}

#[derive(Clone, Debug)]
pub enum ExprKind {
    Int(i64),
    Bool(bool),
    Unit,
    Name(String),
    Variant(String, String),
    Field(Box<Expr>, String),
    Hole(String, Type),
    Call(String, Vec<Expr>),
    Unary(UnOp, Box<Expr>),
    AsI64(Box<Expr>),
    Binary(BinOp, Box<Expr>, Box<Expr>),
    If {
        cond: Box<Expr>,
        yes: Box<Expr>,
        no: Box<Expr>,
    },
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum UnOp {
    Neg,
    Not,
}

/// Fallback callable names in the scalar profile. User declarations take priority.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Intrinsic {
    Min,
    Max,
    Clamp,
}

impl Intrinsic {
    pub fn named(name: &str) -> Option<Self> {
        match name {
            "min" => Some(Self::Min),
            "max" => Some(Self::Max),
            "clamp" => Some(Self::Clamp),
            _ => None,
        }
    }

    pub fn arity(self) -> usize {
        match self {
            Self::Min | Self::Max => 2,
            Self::Clamp => 3,
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum BinOp {
    Add,
    Sub,
    Mul,
    Div,
    Rem,
    Eq,
    Ne,
    Lt,
    Le,
    Gt,
    Ge,
    And,
    Or,
}

impl BinOp {
    fn from_token(token: &str) -> Option<Self> {
        Some(match token {
            "+" => Self::Add,
            "-" => Self::Sub,
            "*" => Self::Mul,
            "/" => Self::Div,
            "%" => Self::Rem,
            "==" => Self::Eq,
            "!=" => Self::Ne,
            "<" => Self::Lt,
            "<=" => Self::Le,
            ">" => Self::Gt,
            ">=" => Self::Ge,
            "&&" => Self::And,
            "||" => Self::Or,
            _ => return None,
        })
    }

    pub(crate) fn precedence(self) -> u8 {
        match self {
            Self::Or => 1,
            Self::And => 2,
            Self::Eq | Self::Ne => 3,
            Self::Lt | Self::Le | Self::Gt | Self::Ge => 4,
            Self::Add | Self::Sub => 5,
            Self::Mul | Self::Div | Self::Rem => 6,
        }
    }

    fn spelling(self) -> &'static str {
        match self {
            Self::Add => "+",
            Self::Sub => "-",
            Self::Mul => "*",
            Self::Div => "/",
            Self::Rem => "%",
            Self::Eq => "==",
            Self::Ne => "!=",
            Self::Lt => "<",
            Self::Le => "<=",
            Self::Gt => ">",
            Self::Ge => ">=",
            Self::And => "&&",
            Self::Or => "||",
        }
    }
}

#[derive(Clone, Copy, Debug)]
struct Token<'a> {
    text: &'a str,
    span: Span,
}

fn is_reserved(word: &str) -> bool {
    matches!(
        word,
        "module"
            | "pub"
            | "fn"
            | "let"
            | "var"
            | "return"
            | "if"
            | "else"
            | "while"
            | "true"
            | "false"
            | "use"
            | "record"
            | "enum"
            | "const"
            | "test"
            | "requires"
            | "ensures"
            | "for"
            | "in"
            | "match"
            | "break"
            | "continue"
            | "assert"
    )
}

fn ident_start(byte: u8) -> bool {
    byte == b'_' || byte.is_ascii_alphabetic()
}

fn is_identifier(text: &str) -> bool {
    text.bytes().next().is_some_and(ident_start) && !is_reserved(text)
}

fn bidirectional_control(c: char) -> bool {
    matches!(c, '\u{061c}' | '\u{200e}' | '\u{200f}' | '\u{202a}'..='\u{202e}' | '\u{2066}'..='\u{2069}')
}

fn lex(source: &str) -> Result<Vec<Token<'_>>, Diagnostic> {
    if let Some((start, c)) = source
        .char_indices()
        .find(|&(_, c)| bidirectional_control(c))
    {
        return Err(Diagnostic::new(
            "GPP-LEX-002",
            "bidirectional control character in source",
            Span {
                start,
                end: start + c.len_utf8(),
            },
        ));
    }
    let bytes = source.as_bytes();
    let mut pos = 0;
    let mut tokens = Vec::new();
    while pos < bytes.len() {
        let start = pos;
        let byte = bytes[pos];
        pos += 1;
        if byte.is_ascii_whitespace() {
            continue;
        }
        if byte == b'/' && bytes.get(pos) == Some(&b'/') {
            while pos < bytes.len() && !matches!(bytes[pos], b'\n' | b'\r') {
                pos += 1;
            }
            continue;
        }
        if ident_start(byte) {
            while pos < bytes.len() && (ident_start(bytes[pos]) || bytes[pos].is_ascii_digit()) {
                pos += 1;
            }
        } else if byte.is_ascii_digit() {
            while pos < bytes.len() && bytes[pos].is_ascii_digit() {
                pos += 1;
            }
        } else if byte == b'.' && bytes.get(pos..pos + 2) == Some(b".=") {
            pos += 2;
        } else if matches!(
            (byte, bytes.get(pos)),
            (b'-', Some(b'>'))
                | (
                    b'=' | b'!' | b'<' | b'>' | b'+' | b'-' | b'*' | b'/' | b'%',
                    Some(b'=')
                )
                | (b':', Some(b':'))
                | (b'&', Some(b'&'))
                | (b'|', Some(b'|'))
        ) {
            pos += 1;
        } else if !b"?;.,:(){}+-*/%=!<>".contains(&byte) {
            let c = source[start..].chars().next().unwrap();
            return Err(Diagnostic::new(
                "GPP-LEX-001",
                format!("unexpected character {c:?} in scalar source"),
                Span {
                    start,
                    end: start + c.len_utf8(),
                },
            ));
        }
        tokens.push(Token {
            text: &source[start..pos],
            span: Span { start, end: pos },
        });
    }
    tokens.push(Token {
        text: "",
        span: Span {
            start: pos,
            end: pos,
        },
    });
    Ok(tokens)
}

const MAX_DEPTH: usize = 64;

fn check_depth(depth: usize, span: Span) -> Result<(), Diagnostic> {
    if depth > MAX_DEPTH {
        Err(Diagnostic::new(
            "GPP-PARSE-004",
            format!("scalar syntax nesting exceeds {MAX_DEPTH}"),
            span,
        ))
    } else {
        Ok(())
    }
}

// Pratt recursion alone does not bound the height of a left-associated expression.
// Keep its height during parsing so later AST visitors and drop also stay bounded.
struct ParsedExpr {
    expr: Expr,
    height: usize,
}

struct Parser<'a> {
    tokens: Vec<Token<'a>>,
    at: usize,
    type_names: HashMap<&'a str, usize>,
}

pub fn parse(source: &str) -> Result<Module, Diagnostic> {
    Parser::new(source)?.module()
}

/// Parse exactly one expression and return its byte extent, excluding exterior trivia.
pub fn expression_span(source: &str) -> Result<Span, Diagnostic> {
    Ok(parse_expression(source)?.span)
}

pub fn parse_expression(source: &str) -> Result<Expr, Diagnostic> {
    let mut parser = Parser::new(source)?;
    let expr = parser.expression(0)?;
    parser.end()?;
    Ok(expr)
}

/// Return the exact interior of a complete braced block or a list of statements.
pub fn body_fragment<'a>(source: &'a str, module: &Module) -> Result<&'a str, Diagnostic> {
    let mut parser = Parser::new(source)?;
    parser.type_names.extend(
        module
            .types
            .iter()
            .enumerate()
            .map(|(id, decl)| (decl.name.as_str(), id)),
    );
    if parser.peek().text == "{" {
        let start = parser.peek().span.end;
        parser.block(0)?;
        let end = parser.tokens[parser.at - 1].span.start;
        parser.end()?;
        Ok(&source[start..end])
    } else {
        while !parser.peek().text.is_empty() {
            parser.statement(0)?;
        }
        Ok(source)
    }
}

impl<'a> Parser<'a> {
    fn new(source: &'a str) -> Result<Self, Diagnostic> {
        let tokens = lex(source)?;
        let mut type_names = HashMap::new();
        for pair in tokens.windows(2) {
            if matches!(pair[0].text, "record" | "enum") {
                let name = pair[1].text;
                if matches!(name, "Bool" | "I64" | "Unit")
                    || type_names.insert(name, type_names.len()).is_some()
                {
                    return Err(Diagnostic::new(
                        "GPP-NAME-002",
                        format!("duplicate type '{name}'"),
                        pair[1].span,
                    ));
                }
            }
        }
        Ok(Self {
            tokens,
            type_names,
            at: 0,
        })
    }

    fn end(&self) -> Result<(), Diagnostic> {
        if self.peek().text.is_empty() {
            Ok(())
        } else {
            Err(self.expected("end of fragment"))
        }
    }

    fn peek(&self) -> Token<'a> {
        self.tokens[self.at]
    }

    fn bump(&mut self) -> Token<'a> {
        let token = self.peek();
        if !token.text.is_empty() {
            self.at += 1;
        }
        token
    }

    fn eat(&mut self, text: &str) -> bool {
        if self.peek().text == text {
            self.bump();
            true
        } else {
            false
        }
    }

    fn span_from(&self, start: usize) -> Span {
        Span {
            start,
            end: self.tokens[self.at - 1].span.end,
        }
    }

    fn expected(&self, what: &str) -> Diagnostic {
        let token = self.peek();
        let found = if token.text.is_empty() {
            "end of input".into()
        } else {
            format!("'{}'", token.text)
        };
        Diagnostic::new(
            "GPP-PARSE-001",
            format!("expected {what}, found {found}"),
            token.span,
        )
    }

    fn require(&mut self, text: &str) -> Result<(), Diagnostic> {
        if self.eat(text) {
            Ok(())
        } else {
            Err(self.expected(&format!("'{text}'")))
        }
    }

    fn identifier(&mut self) -> Result<String, Diagnostic> {
        if is_identifier(self.peek().text) {
            Ok(self.bump().text.to_owned())
        } else {
            Err(self.expected("an identifier"))
        }
    }

    fn ty(&mut self) -> Result<Type, Diagnostic> {
        let ty = match self.peek().text {
            "I64" => Type::I64,
            "Bool" => Type::Bool,
            "Unit" => Type::Unit,
            name if self.type_names.contains_key(name) => Type::Named(self.type_names[name]),
            _ if is_identifier(self.peek().text) => {
                return Err(Diagnostic::new(
                    "GPP-PARSE-002",
                    format!("type '{}' is outside the scalar profile", self.peek().text),
                    self.peek().span,
                ));
            }
            _ => return Err(self.expected("a scalar type")),
        };
        self.bump();
        Ok(ty)
    }

    fn module(mut self) -> Result<Module, Diagnostic> {
        self.require("module")?;
        let mut name = self.identifier()?;
        while self.eat(".") {
            name.push('.');
            name.push_str(&self.identifier()?);
        }
        self.require(";")?;
        let mut functions = Vec::new();
        let mut contracts = Vec::new();
        let mut types = Vec::new();
        while !self.peek().text.is_empty() {
            if matches!(self.peek().text, "record" | "enum") {
                types.push(self.type_decl()?);
            } else if self.peek().text == "contract" {
                contracts.push(self.contract()?);
            } else {
                functions.push(self.function()?);
            }
        }
        Ok(Module {
            name,
            functions,
            contracts,
            types,
        })
    }

    fn type_decl(&mut self) -> Result<TypeDecl, Diagnostic> {
        let keyword = self.bump();
        let name = self.identifier()?;
        self.require("{")?;
        let mut seen = HashSet::new();
        let mut fields = Vec::new();
        let mut variants = Vec::new();
        while self.peek().text != "}" {
            let start = self.peek().span.start;
            let member = self.identifier()?;
            if !seen.insert(member.clone()) {
                return Err(Diagnostic::new(
                    "GPP-NAME-002",
                    format!("duplicate member '{member}' of '{name}'"),
                    self.span_from(start),
                ));
            }
            if keyword.text == "record" {
                self.require(":")?;
                let ty = self.ty()?;
                fields.push(Param {
                    name: member,
                    ty,
                    span: self.span_from(start),
                });
            } else {
                variants.push(member);
            }
            if !self.eat(",") {
                break;
            }
        }
        self.require("}")?;
        let span = self.span_from(keyword.span.start);
        let kind = if keyword.text == "record" {
            TypeKind::Record(fields)
        } else if variants.is_empty() {
            return Err(Diagnostic::new(
                "GPP-TYPE-001",
                "an enum requires at least one variant",
                span,
            ));
        } else {
            TypeKind::Enum(variants)
        };
        Ok(TypeDecl { name, kind, span })
    }

    fn bound(&mut self) -> Result<i64, Diagnostic> {
        let start = self.peek().span.start;
        let negative = self.eat("-");
        let token = self.peek();
        if token.text.is_empty() || !token.text.bytes().all(|b| b.is_ascii_digit()) {
            return Err(self.expected("an integer range bound"));
        }
        self.bump();
        let sign = if negative { "-" } else { "" };
        format!("{sign}{}", token.text).parse().map_err(|_| {
            Diagnostic::new(
                "GPP-PARSE-003",
                "contract bound is outside I64",
                self.span_from(start),
            )
        })
    }

    fn contract(&mut self) -> Result<Contract, Diagnostic> {
        let start = self.bump().span.start;
        let name = self.identifier()?;
        self.require("(")?;
        let mut params = Vec::new();
        let mut domains = Vec::new();
        while self.peek().text != ")" {
            let param_start = self.peek().span.start;
            let name = self.identifier()?;
            self.require(":")?;
            let ty = self.ty()?;
            let domain = match ty {
                Type::Bool => Domain::Bool,
                Type::I64 => {
                    self.require("in")?;
                    let low = self.bound()?;
                    self.require("..=")?;
                    let high = self.bound()?;
                    if low > high {
                        return Err(Diagnostic::new(
                            "GPP-DOMAIN-001",
                            "contract range has inverted bounds",
                            self.span_from(param_start),
                        ));
                    }
                    Domain::I64 { low, high }
                }
                Type::Unit | Type::Named(_) => {
                    return Err(Diagnostic::new(
                        "GPP-DOMAIN-001",
                        "contract parameters require Bool or a bounded I64",
                        self.span_from(param_start),
                    ));
                }
            };
            params.push(Param {
                name,
                ty,
                span: self.span_from(param_start),
            });
            domains.push(domain);
            if !self.eat(",") {
                break;
            }
        }
        self.require(")")?;
        let body_start = self.peek().span.start;
        self.require("{")?;
        let expr = self.expression(0)?;
        self.require("}")?;
        let span = expr.span;
        Ok(Contract {
            predicate: Function {
                public: false,
                name,
                params,
                result: Type::Bool,
                body: vec![Stmt {
                    kind: StmtKind::Return(expr),
                    span,
                }],
                body_span: self.span_from(body_start),
                span: self.span_from(start),
            },
            domains,
        })
    }

    fn function(&mut self) -> Result<Function, Diagnostic> {
        let start = self.peek().span.start;
        let public = self.eat("pub");
        if matches!(
            self.peek().text,
            "use" | "record" | "enum" | "const" | "test"
        ) {
            return Err(Diagnostic::new(
                "GPP-PARSE-002",
                format!(
                    "'{}' declarations are outside the scalar profile",
                    self.peek().text
                ),
                self.peek().span,
            ));
        }
        self.require("fn")?;
        let name = self.identifier()?;
        self.require("(")?;
        let mut params = Vec::new();
        while self.peek().text != ")" {
            let param_start = self.peek().span.start;
            let name = self.identifier()?;
            self.require(":")?;
            let ty = self.ty()?;
            params.push(Param {
                name,
                ty,
                span: self.span_from(param_start),
            });
            if !self.eat(",") {
                break;
            }
        }
        self.require(")")?;
        self.require("->")?;
        let result = self.ty()?;
        self.require("!")?;
        self.require("{")?;
        if is_identifier(self.peek().text) {
            return Err(Diagnostic::new(
                "GPP-PARSE-002",
                "scalar functions require an empty effect set",
                self.peek().span,
            ));
        }
        self.require("}")?;
        let body_start = self.peek().span.start;
        let body = self.block(0)?;
        let body_span = self.span_from(body_start);
        Ok(Function {
            public,
            name,
            params,
            result,
            body,
            body_span,
            span: self.span_from(start),
        })
    }

    fn block(&mut self, depth: usize) -> Result<Vec<Stmt>, Diagnostic> {
        check_depth(depth, self.peek().span)?;
        self.require("{")?;
        let mut body = Vec::new();
        while !self.eat("}") {
            if self.peek().text.is_empty() {
                return Err(self.expected("'}'"));
            }
            body.push(self.statement(depth)?);
        }
        Ok(body)
    }

    fn statement(&mut self, depth: usize) -> Result<Stmt, Diagnostic> {
        let token = self.peek();
        let kind = match token.text {
            "let" | "var" => {
                self.bump();
                let name = self.identifier()?;
                let annotation = if self.eat(":") {
                    Some(self.ty()?)
                } else {
                    None
                };
                self.require("=")?;
                let value = self.expression(depth)?;
                self.require(";")?;
                StmtKind::Bind {
                    mutable: token.text == "var",
                    name,
                    annotation,
                    value,
                }
            }
            "return" => {
                self.bump();
                let value = self.expression(depth)?;
                self.require(";")?;
                StmtKind::Return(value)
            }
            "if" => return self.if_stmt(depth),
            "while" => {
                self.bump();
                let cond = self.expression(depth)?;
                let body = self.block(depth + 1)?;
                StmtKind::While { cond, body }
            }
            "for" | "break" | "continue" | "match" | "assert" => {
                return Err(Diagnostic::new(
                    "GPP-PARSE-002",
                    format!("'{}' statements are outside the scalar profile", token.text),
                    token.span,
                ));
            }
            name if is_identifier(name)
                && matches!(
                    self.tokens[self.at + 1].text,
                    "=" | "+=" | "-=" | "*=" | "/=" | "%="
                ) =>
            {
                self.bump();
                let assignment = self.bump();
                let rhs = self.binary(1, depth)?;
                let value = if assignment.text == "=" {
                    rhs.expr
                } else {
                    // Assignment targets are names, so the ordinary binary expression
                    // evaluates the old value once and inherits the checked operation.
                    let op = BinOp::from_token(&assignment.text[..1]).unwrap();
                    let span = self.span_from(token.span.start);
                    check_depth(rhs.height + 1, span)?;
                    let local = Expr {
                        kind: ExprKind::Name(name.to_owned()),
                        span: token.span,
                        site: ExprSite::Synthetic,
                    };
                    Expr {
                        kind: ExprKind::Binary(op, Box::new(local), Box::new(rhs.expr)),
                        span,
                        site: ExprSite::Synthetic,
                    }
                };
                self.require(";")?;
                StmtKind::Assign {
                    name: name.to_owned(),
                    value,
                }
            }
            _ => {
                let value = self.expression(depth)?;
                self.require(";")?;
                StmtKind::Expr(value)
            }
        };
        Ok(Stmt {
            kind,
            span: self.span_from(token.span.start),
        })
    }

    fn if_stmt(&mut self, depth: usize) -> Result<Stmt, Diagnostic> {
        check_depth(depth, self.peek().span)?;
        let start = self.bump().span.start;
        let cond = self.expression(depth)?;
        let then_body = self.block(depth + 1)?;
        let else_body = if !self.eat("else") {
            Vec::new()
        } else if self.peek().text == "if" {
            vec![self.if_stmt(depth + 1)?]
        } else {
            self.block(depth + 1)?
        };
        Ok(Stmt {
            kind: StmtKind::If {
                cond,
                then_body,
                else_body,
            },
            span: self.span_from(start),
        })
    }

    fn expression(&mut self, depth: usize) -> Result<Expr, Diagnostic> {
        Ok(self.binary(1, depth)?.expr)
    }

    fn binary(&mut self, minimum: u8, depth: usize) -> Result<ParsedExpr, Diagnostic> {
        check_depth(depth, self.peek().span)?;
        let mut left = self.prefix(depth)?;
        // Casts bind less tightly than prefix operators and more tightly than
        // every binary operator. "as" remains an identifier in prefix position.
        while self.eat("as") {
            self.require("I64")?;
            let span = self.span_from(left.expr.span.start);
            let height = left.height + 1;
            check_depth(height, span)?;
            left = ParsedExpr {
                expr: Expr {
                    kind: ExprKind::AsI64(Box::new(left.expr)),
                    span,
                    site: ExprSite::Ordinary,
                },
                height,
            };
        }
        while let Some(op) = BinOp::from_token(self.peek().text) {
            if op.precedence() < minimum {
                break;
            }
            self.bump();
            let right = self.binary(op.precedence() + 1, depth + 1)?;
            let span = Span {
                start: left.expr.span.start,
                end: right.expr.span.end,
            };
            let height = 1 + left.height.max(right.height);
            check_depth(height, span)?;
            left = ParsedExpr {
                expr: Expr {
                    kind: ExprKind::Binary(op, Box::new(left.expr), Box::new(right.expr)),
                    span,
                    site: ExprSite::Ordinary,
                },
                height,
            };
        }
        Ok(left)
    }

    fn braced_expression(&mut self, depth: usize) -> Result<ParsedExpr, Diagnostic> {
        self.require("{")?;
        let value = self.binary(1, depth)?;
        self.require("}")?;
        Ok(value)
    }

    fn prefix(&mut self, depth: usize) -> Result<ParsedExpr, Diagnostic> {
        let mut value = self.atom(depth)?;
        while self.eat(".") {
            let field = self.identifier()?;
            let span = self.span_from(value.expr.span.start);
            value.height += 1;
            check_depth(value.height, span)?;
            value.expr = Expr {
                kind: ExprKind::Field(Box::new(value.expr), field),
                span,
                site: ExprSite::Ordinary,
            };
        }
        Ok(value)
    }

    fn atom(&mut self, depth: usize) -> Result<ParsedExpr, Diagnostic> {
        check_depth(depth, self.peek().span)?;
        let token = self.peek();
        let mut height = 1;
        let kind = match token.text {
            "if" => {
                self.bump();
                let cond = self.binary(1, depth + 1)?;
                let yes = self.braced_expression(depth + 1)?;
                self.require("else")?;
                let no = if self.peek().text == "if" {
                    let mut tail = self.prefix(depth + 1)?;
                    tail.expr.site = ExprSite::ElseIf;
                    tail
                } else {
                    self.braced_expression(depth + 1)?
                };
                height = 1 + cond.height.max(yes.height).max(no.height);
                ExprKind::If {
                    cond: Box::new(cond.expr),
                    yes: Box::new(yes.expr),
                    no: Box::new(no.expr),
                }
            }
            "-" | "!" => {
                self.bump();
                // The minimum is the only I64 whose absolute value doesn't fit in I64.
                if token.text == "-"
                    && self.peek().text.trim_start_matches('0') == "9223372036854775808"
                {
                    self.bump();
                    ExprKind::Int(i64::MIN)
                } else {
                    let child = self.prefix(depth + 1)?;
                    height = child.height + 1;
                    let op = if token.text == "-" {
                        UnOp::Neg
                    } else {
                        UnOp::Not
                    };
                    ExprKind::Unary(op, Box::new(child.expr))
                }
            }
            "(" => {
                self.bump();
                if self.eat(")") {
                    ExprKind::Unit
                } else {
                    let mut child = self.binary(1, depth + 1)?;
                    self.require(")")?;
                    child.expr.span = self.span_from(token.span.start);
                    return Ok(child);
                }
            }
            "?" => {
                self.bump();
                let label = self.identifier()?;
                self.require(":")?;
                ExprKind::Hole(label, self.ty()?)
            }
            "true" | "false" => {
                self.bump();
                ExprKind::Bool(token.text == "true")
            }
            word if word.as_bytes().first().is_some_and(u8::is_ascii_digit) => {
                self.bump();
                let n = word.parse::<i64>().map_err(|_| {
                    Diagnostic::new(
                        "GPP-PARSE-003",
                        "integer literal is outside the I64 range",
                        token.span,
                    )
                })?;
                ExprKind::Int(n)
            }
            word if is_identifier(word) => {
                self.bump();
                if self.eat("::") {
                    ExprKind::Variant(word.to_owned(), self.identifier()?)
                } else if self.eat("(") {
                    let mut args = Vec::new();
                    while self.peek().text != ")" {
                        let arg = self.binary(1, depth + 1)?;
                        height = height.max(arg.height + 1);
                        args.push(arg.expr);
                        if !self.eat(",") {
                            break;
                        }
                    }
                    self.require(")")?;
                    ExprKind::Call(word.to_owned(), args)
                } else {
                    ExprKind::Name(word.to_owned())
                }
            }
            _ => return Err(self.expected("an expression")),
        };
        let span = self.span_from(token.span.start);
        check_depth(height, span)?;
        Ok(ParsedExpr {
            expr: Expr {
                kind,
                span,
                site: ExprSite::Ordinary,
            },
            height,
        })
    }
}

impl fmt::Display for BinOp {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.spelling())
    }
}

impl fmt::Display for UnOp {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(match self {
            Self::Neg => "-",
            Self::Not => "!",
        })
    }
}

/// Stable source-like AST dump. Comments and redundant grouping are trivia.
pub fn print(module: &Module) -> String {
    let mut text = String::new();
    writeln!(text, "module {};", module.name).unwrap();
    for decl in &module.types {
        let (keyword, members) = match &decl.kind {
            TypeKind::Enum(variants) => ("enum", variants.join(", ")),
            TypeKind::Record(fields) => (
                "record",
                fields
                    .iter()
                    .map(|p| format!("{}: {}", p.name, module.type_name(p.ty)))
                    .collect::<Vec<_>>()
                    .join(", "),
            ),
        };
        writeln!(text, "\n{keyword} {} {{ {members} }}", decl.name).unwrap();
    }
    for function in &module.functions {
        text.push('\n');
        if function.public {
            text.push_str("pub ");
        }
        write!(text, "fn {}(", function.name).unwrap();
        for (index, param) in function.params.iter().enumerate() {
            if index != 0 {
                text.push_str(", ");
            }
            write!(text, "{}: {}", param.name, module.type_name(param.ty)).unwrap();
        }
        write!(text, ") -> {} !{{}} ", module.type_name(function.result)).unwrap();
        print_block(module, &function.body, 0, &mut text);
        text.push('\n');
    }
    for c in &module.contracts {
        write!(text, "\ncontract {}(", c.predicate.name).unwrap();
        for (i, (param, domain)) in c.predicate.params.iter().zip(&c.domains).enumerate() {
            if i != 0 {
                text.push_str(", ");
            }
            write!(text, "{}: {}", param.name, module.type_name(param.ty)).unwrap();
            if let Domain::I64 { low, high } = domain {
                write!(text, " in {low}..={high}").unwrap();
            }
        }
        text.push_str(") { ");
        let StmtKind::Return(expr) = &c.predicate.body[0].kind else {
            unreachable!("contract predicate")
        };
        print_expr(module, expr, 0, &mut text);
        text.push_str(" }\n");
    }
    text
}

fn print_block(module: &Module, body: &[Stmt], indent: usize, text: &mut String) {
    text.push_str("{\n");
    for stmt in body {
        text.push_str(&"    ".repeat(indent + 1));
        match &stmt.kind {
            StmtKind::Bind {
                mutable,
                name,
                annotation,
                value,
            } => {
                write!(text, "{} {name}", if *mutable { "var" } else { "let" }).unwrap();
                if let Some(ty) = annotation {
                    write!(text, ": {}", module.type_name(*ty)).unwrap();
                }
                text.push_str(" = ");
                print_expr(module, value, 0, text);
                text.push(';');
            }
            StmtKind::Assign { name, value } => {
                write!(text, "{name} = ").unwrap();
                print_expr(module, value, 0, text);
                text.push(';');
            }
            StmtKind::Return(value) => {
                text.push_str("return ");
                print_expr(module, value, 0, text);
                text.push(';');
            }
            StmtKind::If {
                cond,
                then_body,
                else_body,
            } => {
                text.push_str("if ");
                print_expr(module, cond, 0, text);
                text.push(' ');
                print_block(module, then_body, indent + 1, text);
                if !else_body.is_empty() {
                    text.push_str(" else ");
                    print_block(module, else_body, indent + 1, text);
                }
            }
            StmtKind::While { cond, body } => {
                text.push_str("while ");
                print_expr(module, cond, 0, text);
                text.push(' ');
                print_block(module, body, indent + 1, text);
            }
            StmtKind::Expr(expr) => {
                let start = text.len();
                print_expr(module, expr, 0, text);
                // A leading bare "if" is parsed as a statement.
                if text[start..].starts_with("if ") {
                    text.insert(start, '(');
                    text.push(')');
                }
                text.push(';');
            }
        }
        text.push('\n');
    }
    text.push_str(&"    ".repeat(indent));
    text.push('}');
}

pub(crate) fn print_expr(module: &Module, expr: &Expr, minimum: u8, text: &mut String) {
    match &expr.kind {
        ExprKind::If { cond, yes, no } => {
            text.push_str("if ");
            print_expr(module, cond, 0, text);
            text.push_str(" { ");
            print_expr(module, yes, 0, text);
            text.push_str(" } else { ");
            print_expr(module, no, 0, text);
            text.push_str(" }");
        }
        ExprKind::Int(n) => write!(text, "{n}").unwrap(),
        ExprKind::Bool(b) => write!(text, "{b}").unwrap(),
        ExprKind::Unit => text.push_str("()"),
        ExprKind::Field(value, field) => {
            if matches!(value.kind, ExprKind::If { .. } | ExprKind::Unary(..)) {
                text.push('(');
                print_expr(module, value, 0, text);
                text.push(')');
            } else {
                print_expr(module, value, 9, text);
            }
            write!(text, ".{field}").unwrap();
        }
        ExprKind::Variant(name, variant) => write!(text, "{name}::{variant}").unwrap(),
        ExprKind::Hole(name, ty) => write!(text, "?{name}: {}", module.type_name(*ty)).unwrap(),
        ExprKind::Name(name) => text.push_str(name),
        ExprKind::Call(name, args) => {
            write!(text, "{name}(").unwrap();
            for (index, arg) in args.iter().enumerate() {
                if index != 0 {
                    text.push_str(", ");
                }
                print_expr(module, arg, 0, text);
            }
            text.push(')');
        }
        ExprKind::Unary(op, child) => {
            write!(text, "{op}").unwrap();
            print_expr(module, child, 8, text);
        }
        ExprKind::AsI64(child) => {
            let grouped = minimum > 7;
            if grouped {
                text.push('(');
            }
            print_expr(module, child, 7, text);
            text.push_str(" as I64");
            if grouped {
                text.push(')');
            }
        }
        ExprKind::Binary(op, left, right) => {
            let precedence = op.precedence();
            let parens = precedence < minimum;
            if parens {
                text.push('(');
            }
            print_expr(module, left, precedence, text);
            write!(text, " {op} ").unwrap();
            print_expr(module, right, precedence + 1, text);
            if parens {
                text.push(')');
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn with_body(body: &str) -> String {
        format!("module demo; pub fn main() -> I64 !{{}} {{ {body} }}")
    }

    #[test]
    fn discarded_conditional_values_survive_printing() {
        let source =
            with_body("(if true { 1 } else { 0 }); (if true { 3 } else { 4 }) + 5; return 0;");
        let printed = print(&parse(&source).unwrap());
        assert!(printed.contains("(if true { 1 } else { 0 });"));
        assert!(printed.contains("(if true { 3 } else { 4 } + 5);"));
        assert_eq!(printed, print(&parse(&printed).unwrap()));
    }

    #[test]
    fn operators_preserve_grouping_and_associativity() {
        let source = with_body("return (2+3)*4-(9-(8/2%3))+(-1);");
        let printed = print(&parse(&source).unwrap());
        assert!(printed.contains("return (2 + 3) * 4 - (9 - 8 / 2 % 3) + -1;"));
        assert_eq!(printed, print(&parse(&printed).unwrap()));

        let expr = &parse(&with_body(
            "return true || false && 1 + 2 * 3 <= 7 == !false;",
        ))
        .unwrap()
        .functions[0]
            .body[0];
        let StmtKind::Return(Expr {
            kind: ExprKind::Binary(BinOp::Or, _, rhs),
            ..
        }) = &expr.kind
        else {
            panic!("expected outer ||");
        };
        assert!(matches!(rhs.kind, ExprKind::Binary(BinOp::And, _, _)));
    }

    #[test]
    fn prints_code_with_parameters_scopes_and_unit() {
        let source = "module demo.math; // demonstration ☺\n
            fn count(stop:I64,) -> Unit !{} {
                var n:I64=0; while n<stop {n=n+1;} return ();
            }
            pub fn main() -> I64 !{} {
                let b:Bool=!false; count(3,); if b {return 4;} else if false {return 2;} else {return 1;}
            }";
        let tree = parse(source).unwrap();
        assert_eq!(tree.name, "demo.math");
        let dump = print(&tree);
        assert!(dump.contains("while n < stop {\n        n = n + 1;"));
        assert!(dump.contains("    let b: Bool = !false;\n    count(3);"));
        assert_eq!(dump, print(&parse(&dump).unwrap()));
    }

    #[test]
    fn minimum_integer_requires_a_negative_literal() {
        let source = with_body("return -9223372036854775808;");
        let tree = parse(&source).unwrap();
        assert!(matches!(
            tree.functions[0].body[0].kind,
            StmtKind::Return(Expr {
                kind: ExprKind::Int(i64::MIN),
                ..
            })
        ));
        for numeral in [
            "9223372036854775808",
            "-9223372036854775809",
            "999999999999999999999999999999",
        ] {
            assert_eq!(
                parse(&with_body(&format!("return {numeral};")))
                    .unwrap_err()
                    .code,
                "GPP-PARSE-003"
            );
        }
    }

    #[test]
    fn reports_utf8_byte_offsets_and_rejects_bidi_controls() {
        let source = with_body("// π\n return é;");
        let error = parse(&source).unwrap_err();
        assert_eq!(&source[error.span.start..error.span.end], "é");
        assert_eq!(
            parse(&with_body("// π\u{2068}\n return 0;"))
                .unwrap_err()
                .code,
            "GPP-LEX-002"
        );
    }

    #[test]
    fn rejects_bad_syntax_at_the_unexpected_token() {
        for (body, unexpected) in [
            ("return;", ";"),
            ("let if = 0;", "if"),
            ("return f(1,,);", ","),
            ("let x 2;", "2"),
            ("while {", "{"),
        ] {
            let source = with_body(body);
            let error = parse(&source).unwrap_err();
            assert_eq!(&source[error.span.start..error.span.end], unexpected);
        }
        let truncated = "module m; fn f() -> I64 !{} { return 1;";
        assert_eq!(
            parse(truncated).unwrap_err().span,
            Span {
                start: truncated.len(),
                end: truncated.len()
            }
        );
        let effectful = with_body("return 0;").replace("!{}", "!{clock}");
        assert_eq!(parse(&effectful).unwrap_err().code, "GPP-PARSE-002");
    }

    #[test]
    fn bounds_recursive_and_left_associated_trees() {
        for expr in [
            format!("{}0{}", "(".repeat(1000), ")".repeat(1000)),
            format!("{}0", "-".repeat(1000)),
            format!("0{}", "+0".repeat(1000)),
        ] {
            let source = with_body(&format!("return {expr};"));
            assert_eq!(parse(&source).unwrap_err().code, "GPP-PARSE-004");
        }
        let mut nested = "if true {".repeat(1000);
        nested.push_str(&"}".repeat(1000));
        assert_eq!(
            parse(&with_body(&nested)).unwrap_err().code,
            "GPP-PARSE-004"
        );
    }
}
