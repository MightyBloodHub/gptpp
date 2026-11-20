"""Black-box checks of the shipped CLI, interpreter and standalone executables."""
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

GPP = Path(sys.argv.pop(1)).resolve()
ROOT = Path(__file__).resolve().parents[1]


def invoke(*args, timeout=30, cwd=None, env=None):
    return subprocess.run(
        args, text=True, capture_output=True, timeout=timeout, cwd=cwd, env=env,
    )


def module(body, helpers=""):
    return f"module samples.main;\n{helpers}\npub fn main() -> I64 !{{}} {{ {body} }}\n"


def generate_expression(rng, depth):
    """Generate a bounded I64 expression along with its Python integer oracle."""
    if depth == 0 or rng.randrange(5) == 0:
        n = rng.randrange(-5, 6)
        return str(n), n
    a, x = generate_expression(rng, depth - 1)
    b, y = generate_expression(rng, depth - 1)
    op = rng.choice(["+", "-", "*", "larger"])
    if op == "larger":
        return f"larger({a}, {b})", max(x, y)
    value = {"+": x + y, "-": x - y, "*": x * y}[op]
    return f"({a} {op} {b})", value


class Bootstrap(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.work = Path(temp.name)
        self.source = self.work / "main.gpp"
        self.exe = self.work / "program"

    def assert_ok(self, process):
        self.assertEqual(process.returncode, 0, process.stderr)

    def assert_engines(self, source, kind, expected):
        self.source.write_text(source, encoding="utf-8")
        if kind == "fault":
            outcome = (1, "", f"fault: {expected}\n")
        else:
            outcome = (0, f"{expected}\n", "")

        def compare(process):
            self.assertEqual((process.returncode, process.stdout, process.stderr), outcome, source)

        compare(invoke(GPP, "run", "--interpreter", self.source, timeout=5))
        for level in ("-O0", "-O2"):
            with self.subTest(level=level):
                self.assert_ok(invoke(GPP, "build", level, self.source, "-o", self.exe))
                compare(invoke(self.exe, cwd=self.work, timeout=5))

    def test_fixtures(self):
        self.assert_engines((ROOT / "examples/add.gpp").read_text(), "result", 42)
        for path in sorted((ROOT / "tests/fixtures").glob("*.gpp")):
            with self.subTest(fixture=path.name):
                source = path.read_text(encoding="utf-8")
                _, kind, expected = source.splitlines()[0].split()
                self.assertIn(kind, ("fault", "result"))
                self.assert_engines(source, kind, expected)

    def trace(self, target, entry, *args):
        process = invoke(GPP, "trace", self.source, "--function", target, "--call", entry, *args)
        self.assert_ok(process)
        return json.loads(process.stdout)

    def test_trace_tracks_scope_catalog_skips_and_faults(self):
        source = module("return tally(4, true, ());", """// λ
fn tally(n: I64, safe: Bool, u: Unit) -> I64 !{} {
    var i = 0;
    while i < n { let n = i + 1; i += 1; n; }
    if safe || 1 / (n - n) > 0 { return i; }
    return -1;
}""")
        self.source.write_bytes(source.replace("\n", "\r\n").encode())
        trace = self.trace("tally", "main")
        self.assertEqual(trace["schema"], "gpp.trace/1")
        self.assertEqual(trace["result"], 4)
        self.assertNotIn("fault", trace)
        catalog = json.loads(invoke(GPP, "expressions", self.source, "--function", "tally").stdout)
        for key in ("revision", "function", "start_byte", "end_byte"):
            self.assertEqual(trace[key], catalog[key])
        self.assertEqual(catalog["expressions"], [
            {k: row[k] for k in ("text", "start_byte", "end_byte")} for row in trace["expressions"]
        ])
        rows = trace["expressions"]
        shadow = next(r for r in rows if r["text"] == "n" and r["hits"] == 4)
        self.assertEqual([o["value"] for o in shadow["observations"]], [1, 2, 3])
        self.assertEqual(shadow["observations"][0]["locals"], {"i": 1, "n": 1, "safe": True, "u": None})
        first = next(r for r in rows if r["text"] == "i + 1")["observations"][0]
        self.assertEqual((first["locals"]["n"], first["locals"]["i"], first["value"]), (4, 0, 1))
        skipped = next(r for r in rows if r["text"] == "1 / (n - n)")
        self.assertEqual((skipped["hits"], skipped["observations"], skipped["type"]), (0, [], "I64"))
        condition = next(r for r in rows if r["text"].startswith("safe ||"))
        self.assertEqual(condition["type"], "Bool")
        self.assertIs(condition["observations"][0]["value"], True)

        bad = self.trace("tally", "tally", "-2", "false", "()")
        self.assertEqual(bad["args"], [-2, False, None])
        self.assertEqual(bad["fault"], "DivisionByZero")
        self.assertNotIn("result", bad)
        obs = next(r for r in bad["expressions"] if r["text"] == skipped["text"])["observations"]
        self.assertEqual(obs, [{"locals": {"n": -2, "safe": False, "u": None, "i": 0},
                                "fault": "DivisionByZero"}])
        untouched = self.trace("main", "tally", "4", "true", "()")
        self.assertTrue(all(r["hits"] == 0 for r in untouched["expressions"]))
        for invalid in [(("2", "1", "()"), "expected Bool"), ((), "expects 3 arguments"),
                        (("9223372036854775808", "true", "()"), "expected I64")]:
            args, error = invalid
            p = invoke(GPP, "trace", self.source, "--function", "tally", "--call", "tally", *args)
            self.assertNotEqual(p.returncode, 0)
            self.assertEqual(p.stdout, "")
            self.assertIn(error, p.stderr)
        self.assertEqual(self.source.read_bytes(), source.replace("\n", "\r\n").encode())

    def test_trace_recursion_limits_and_unit(self):
        self.source.write_text(module("return sum_down(4);", """
fn sum_down(n: I64) -> I64 !{} {
    if n == 0 { return 1; }
    return n + sum_down(n - 1);
}
fn empty() -> Unit !{} { return (); }"""))
        trace = self.trace("sum_down", "main")
        nested = next(r for r in trace["expressions"] if r["text"].startswith("n +"))
        self.assertEqual(nested["hits"], 4)
        self.assertEqual([(o["locals"]["n"], o["value"]) for o in nested["observations"]],
                         [(4, 11), (3, 7), (2, 4)])
        unit = self.trace("empty", "empty")
        self.assertIsNone(unit["result"])
        self.assertEqual(unit["expressions"][0]["type"], "Unit")
        self.assertEqual(unit["expressions"][0]["observations"], [{"locals": {}, "value": None}])
        for fuel in ("0", "10", "40", "100"):
            trace = self.trace("sum_down", "main", "--fuel", fuel)
            run = invoke(GPP, "run", "--interpreter", "--fuel", fuel, self.source)
            if run.returncode:
                self.assertEqual(run.stderr, f"fault: {trace['fault']}\n")
            else:
                self.assertEqual(int(run.stdout), trace["result"])

    def test_probe_stream_editor_parity_and_validation(self):
        source = module("return target(3, false);", """// π
fn target(x: I64, b: Bool) -> I64 !{} { return 2 * x; }
fn positive() -> Bool !{} { return target(3, true) > 0; }
fn discard(v: Unit) -> Unit !{} { target(3, true); return v; }
fn __gpp_probe0() -> I64 !{} { return 77; }""")
        self.source.write_bytes(source.replace("\n", "\r\n").encode())
        base = invoke(GPP, "revision", self.source).stdout.strip()
        end = self.source.read_bytes().index(b"x;") + 1
        span = f"{end-1}:{end}"
        calls = self.work / "calls.tsv"
        command = [GPP, "probe", self.source, "--function", "target", "--expect", base, "--cases", calls]

        def frame(text, where=span, check=False):
            data = text.encode()
            return f"{where} {len(data)}{' check' if check else ''}\n".encode() + data

        def probe(data, *flags):
            p = subprocess.run([*command, *flags], input=data, capture_output=True, timeout=10)
            self.assertEqual(p.returncode, 0, p.stderr)
            hello, *rows = [json.loads(line) for line in p.stdout.splitlines()]
            self.assertEqual(hello, dict(schema="gpp.probe/1", revision=base, cases=len(calls.read_text().splitlines())))
            return rows

        calls.write_text("main\npositive\ndiscard\t()\n__gpp_probe0\n")
        fragments = ["x + // π\n1", "b", "1 / (x - x)", "if b { -2 } else { 9 }"]
        payload = b"".join(frame(f) for f in fragments) + frame("1", "1:2") + frame("1", check=True)
        for flags in [(), ("--wrapped",)]:
            good, bad, fault, conditional, outside, check = probe(payload, *flags)
            self.assertEqual(good["outcomes"], [{"result": 8}, {"result": True}, {"result": None}, {"result": 77}])
            self.assertEqual((bad["status"], outside["status"]), ("invalid", "invalid"))
            self.assertEqual(fault["outcomes"], [{"fault": "DivisionByZero"}] * 3 + [{"result": 77}])
            self.assertEqual(conditional["outcomes"], [{"result": 18}, {"result": False}, {"result": None}, {"result": 77}])
            self.assertEqual(check, {"status": "ok", "outcomes": []})
        calls.write_text("main\t8\npositive\ttrue\ndiscard\t()\t()\n")
        rows = probe(payload, "--wrapped", "--filter")
        self.assertEqual([r.get("matches") for r in rows], [True, None, False, False, None, None])
        original = self.source.read_bytes()
        for broken in [b"1:2 9\nx", b"header\n", b"1:2 5000000000\n", b"1:2 1\n\xff", b"1:2 1", b"0" * 97]:
            p = subprocess.run([*command, "--filter"], input=broken, capture_output=True, timeout=5)
            self.assertNotEqual(p.returncode, 0)
            self.assertEqual(len(p.stdout.splitlines()), 1)  # Only the successful opening handshake.
        calls.write_text("target\t3\t2\n")
        for flags in [(), ("--wrapped", "--wrapped")]:
            p = subprocess.run([*command, *flags], input=payload, capture_output=True, timeout=5)
            self.assertNotEqual(p.returncode, 0)
            self.assertEqual(p.stdout, b"")
        calls.write_text("positive\t9\n")
        p = subprocess.run([*command, "--filter"], input=payload, capture_output=True, timeout=5)
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(p.stdout, b"")
        self.assertEqual(self.source.read_bytes(), original)
        self.source.write_bytes(original + b"// changed\n")
        p = subprocess.run(command, input=payload, capture_output=True, timeout=5)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn(b"stale revision", p.stderr)
        self.assertEqual(p.stdout, b"")

    def test_probe_preserves_wrapped_call_depth_and_fuel(self):
        self.source.write_text(module("return 7;", """
fn depth(n: I64) -> I64 !{} { if n == 0 { return 0; } return depth(n - 1); }
fn spin(n: I64) -> I64 !{} { (); (); var i = 0; while i < n { i += 1; } return i; }
"""))
        revision = invoke(GPP, "revision", self.source).stdout.strip()
        pos = self.source.read_bytes().index(b"7;")
        payload = f"{pos}:{pos+1} 1\n7".encode()
        cases = self.work / "calls.tsv"
        names = [("depth", n) for n in range(36, 45)] + [("spin", 142855)] * 2
        cases.write_text("".join(f"{name}\t{n}\n" for name, n in names))
        cmd = [GPP, "probe", self.source, "--function", "main", "--expect", revision, "--cases", cases]

        def results(flags):
            p = subprocess.run([*cmd, *flags], input=payload, capture_output=True, timeout=10, check=True)
            return json.loads(p.stdout.splitlines()[1])["outcomes"]

        direct, wrapped = results([]), results(["--wrapped"])
        # The outer entry consumes depth and steps of its own. Evaluate the
        # identical public-case entry independently through the original CLI.
        original = self.source.read_text()
        for (name, n), result in zip(names, wrapped):
            self.source.write_text(original.replace("return 7;", f"return {name}({n});"))
            actual = invoke(GPP, "run", "--interpreter", self.source)
            expected = {"fault": "ResourceLimit"} if actual.returncode else {"result": int(actual.stdout)}
            self.assertEqual(result, expected)
        self.assertNotEqual(direct, wrapped)
        self.assertEqual(direct[-2:], [{"result": 142855}] * 2)  # Each call gets fresh fuel.
        self.assertEqual(wrapped[-2:], [{"fault": "ResourceLimit"}] * 2)

    def test_scalar_casts_and_intrinsics_across_engines(self):
        source = module("""
            if false as I64 != 0 || !false as I64 != 1 { return 1; }
            if -(true as I64) != -1 || 8 * (3 > 2) as I64 != 8 { return 2; }
            if -127 as I64 as I64 != -127 || as(as(3)) != 3 { return 3; }
            if min(-9223372036854775808, 9223372036854775807) != -9223372036854775808 { return 4; }
            if max(-9223372036854775808, 9223372036854775807) != 9223372036854775807 { return 5; }
            if clamp(-11, -10, 7) != -10 || clamp(8, -10, 7) != 7 { return 6; }
            if clamp(5, -10, 7) != 5 || clamp(12, 0, 0) != 0 { return 7; }
            return 42;""", "fn as(as: I64) -> I64 !{} { return as as I64; }")
        self.assert_engines(source, "result", 42)
        printed = invoke(GPP, "ast", self.source).stdout
        self.assertIn("-(true as I64)", printed)
        self.assert_engines(printed, "result", 42)
        for expr, fault in [
            ("clamp(1, 4, -3)", "InvalidBounds"),
            ("min(0, 1 / 0)", "DivisionByZero"),
            ("max(9223372036854775807 + 1, 1 / 0)", "IntegerOverflow"),
            ("clamp(1 / 0, 3, 2)", "DivisionByZero"),
            ("clamp(1, 9223372036854775807, 9223372036854775807 + 1)", "IntegerOverflow"),
        ]:
            with self.subTest(expr=expr):
                self.assert_engines(module(f"return {expr};"), "fault", fault)
        self.assert_engines(module("return min(true) + max(3) + clamp();", """
            fn min(flag: Bool) -> I64 !{} { return flag as I64; }
            fn max(max: I64) -> I64 !{} { return max; }
            fn clamp() -> I64 !{} { return 6; }"""), "result", 10)

    def test_intrinsic_argument_visits_and_cast_edit_spans(self):
        self.source.write_text(module("return clamp(visit(false as I64), visit(1), visit(3));",
                                      "fn visit(x: I64) -> I64 !{} { return x; }"))
        trace = self.trace("visit", "main")
        expr, = trace["expressions"]
        self.assertEqual(expr["hits"], 3)
        self.assertEqual([obs["value"] for obs in expr["observations"]], [0, 1, 3])
        trace = self.trace("main", "main")
        self.assertEqual(trace["result"], 1)
        cast = next(r for r in trace["expressions"] if r["text"] == "false as I64")
        self.assertEqual(cast["type"], "I64")
        before = self.source.read_bytes()
        a, b = cast["start_byte"], cast["end_byte"]
        self.assertEqual(before[a:b], b"false as I64")
        fragment = self.work / "change"
        fragment.write_text("max(1, 2)")
        edited = invoke(GPP, "edit", self.source, "--function", "main", "--at", f"{a}:{b}", "--expr",
                        fragment, "--expect", trace["revision"], "--stdout")
        self.assert_ok(edited)
        self.assertEqual(edited.stdout.encode(), before[:a] + fragment.read_bytes() + before[b:])
        self.assertEqual(self.source.read_bytes(), before)
        self.assert_engines(edited.stdout, "result", 2)

    def test_rejects_unsupported_casts_and_intrinsic_signatures(self):
        for source, code in [
            (module("return () as I64;"), "GPP-TYPE-001"),
            (module("return 1 as Bool;"), "GPP-PARSE-001"),
            (module("return true as Unit;"), "GPP-PARSE-001"),
            (module("return true as U32;"), "GPP-PARSE-001"),
            (module("return true as I64" + " as I64" * 65 + ";"), "GPP-PARSE-004"),
            (module("return clamp(true, 0, 4);"), "GPP-TYPE-001"),
            (module("return max(2);"), "GPP-CALL-001"),
            (module("return min(0, 2);", "fn min() -> I64 !{} { return 9; }"), "GPP-CALL-001"),
            (module("let min = 7; return min(0, 3);"), "GPP-TYPE-001"),
        ]:
            self.source.write_text(source)
            p = invoke(GPP, "check", "--format=json", self.source)
            self.assertNotEqual(p.returncode, 0)
            self.assertEqual(json.loads(p.stderr)["code"], code)

    def verify(self, code, *flags):
        p = invoke(GPP, "verify", self.source, *flags, "--format=json", timeout=10)
        self.assertEqual(p.returncode, code, (p.stdout, p.stderr))
        result = json.loads(p.stdout)
        self.assertEqual(result["schema"], "gpp.verify/1")
        self.assertEqual(result["revision"], invoke(GPP, "revision", self.source).stdout.strip())
        return result

    def test_verify_exhaustion_witness_order_and_runtime_isolation(self):
        production = module("return 42;", "fn accept(x: I64, b: Bool) -> Bool !{} { return x != -1 || !b; }")
        # The contract and ordinary function share a name. Calls still resolve
        # exclusively against program functions, and declarations may precede them.
        contracts = """
contract yes() { true }
contract accept(x: I64 in -2..=2, b: Bool) { accept(x, b) }
contract never_run() { 1 / 0 == 0 }
"""
        source = production.replace("fn accept", contracts + "fn accept", 1)
        self.source.write_text(source)
        result = self.verify(1)
        self.assertEqual((result["status"], result["checked"]), ("counterexample", 5))
        self.assertEqual(result["contracts"][0], {"name": "yes", "status": "passed", "checked": 1})
        self.assertEqual(result["contracts"][1], {
            "name": "accept", "status": "counterexample", "checked": 4,
            "counterexample": {"inputs": {"x": -1, "b": True}, "args": [-1, True], "result": False}})
        self.assertEqual(len(result["contracts"]), 2)
        limited = self.verify(3, "--budget", "4")
        self.assertEqual((limited["reason"], limited["checked"]), ("budget", 4))
        self.assertEqual(limited["contracts"][1]["checked"], 3)
        selected = self.verify(0, "--contract", "yes", "--budget", "1")
        self.assertEqual((selected["status"], selected["checked"]), ("passed", 1))
        self.assertEqual(self.source.read_text(), source)
        self.assert_engines(source, "result", 42)
        compiled = invoke(GPP, "emit-llvm", self.source).stdout
        normalized = invoke(GPP, "ast", self.source).stdout
        self.source.write_text(normalized)
        self.assertEqual(self.verify(1)["contracts"], result["contracts"])
        self.assertEqual(invoke(GPP, "ast", self.source).stdout, normalized)
        self.source.write_text(production)
        self.assertEqual(invoke(GPP, "emit-llvm", self.source).stdout, compiled)

    def test_verify_budget_full_width_arithmetic_faults_and_resources(self):
        source = module("return 1;", "fn spins() -> Bool !{} { while true {} }")
        self.source.write_text(source)
        self.assertEqual(self.verify(3)["reason"], "no_contracts")
        hi, lo = 2**63 - 1, -(2**63)
        self.source.write_text(source + f"""
contract huge(x: I64 in {lo}..={hi}, y: I64 in {lo}..={hi}) {{ x == x && y == y }}
contract last(x: I64 in {hi-1}..={hi}) {{ true }}
contract overflow(x: I64 in {hi}..={hi}) {{ x + 1 > x }}
contract invalid() {{ clamp(1, 4, 3) > 0 }}
contract divzero(b: Bool) {{ !b || 0 / 0 == 1 }}
contract resource() {{ spins() }}
""")
        for n in (0, 1, 7):
            limited = self.verify(3, "--contract", "huge", "--budget", str(n))
            self.assertEqual((limited["reason"], limited["checked"]), ("budget", n))
        self.assertEqual(self.verify(0, "--contract", "last", "--budget", "2")["checked"], 2)
        for name, values, fault, count in [("overflow", [hi], "IntegerOverflow", 1),
                                           ("invalid", [], "InvalidBounds", 1),
                                           ("divzero", [True], "DivisionByZero", 2)]:
            report = self.verify(1, "--contract", name)
            witness = report["contracts"][0]["counterexample"]
            self.assertEqual((witness["args"], witness["fault"], report["checked"]), (values, fault, count))
            self.assertNotIn("result", witness)
        exhausted = self.verify(3, "--contract", "resource")
        self.assertEqual((exhausted["reason"], exhausted["checked"]), ("resource_limit", 1))
        self.assertNotIn("counterexample", exhausted["contracts"][0])

    def test_contract_typechecking_scope_and_domain_errors(self):
        for declarations, code in [
                ("contract p(x: I64) { true }", "GPP-PARSE-001"),
                ("contract p(x: I64 in 1..=0) { true }", "GPP-DOMAIN-001"),
                ("contract p(x: I64 in -9223372036854775809..=0) { true }", "GPP-PARSE-003"),
                ("contract p(x: Unit) { true }", "GPP-DOMAIN-001"),
                ("contract p(x: Bool, x: Bool) { x }", "GPP-NAME-002"),
                ("contract p() { true } contract p() { true }", "GPP-NAME-002"),
                ("contract p() { 1 }", "GPP-TYPE-001"),
                ("contract p() { true || missing }", "GPP-NAME-001"),
                ("contract p() { true } contract q() { p() }", "GPP-NAME-001")]:
            self.source.write_text(module("return 0;") + declarations)
            for cmd, flags in [("check", ["--format=json", self.source]), ("verify", [self.source, "--format=json"])]:
                p = invoke(GPP, cmd, *flags)
                self.assertNotEqual(p.returncode, 0)
                self.assertEqual(p.stdout, "")
                d = json.loads(p.stderr)
                self.assertEqual(d["code"], code)
                self.assertLess(d["location"]["start_byte"], d["location"]["end_byte"])
        self.source.write_text(module("return 0;") + "contract p() { true }")
        unknown = invoke(GPP, "verify", self.source, "--contract", "absent")
        self.assertEqual(unknown.returncode, 2)
        self.assertIn("unknown contract", unknown.stderr)

    def test_arithmetic(self):
        hi, lo = "9223372036854775807", "-9223372036854775808"
        cases = [
            (lo, "result", lo), (hi, "result", hi),
            ("-17 / 5", "result", -3), ("-17 % 5", "result", -2),
            (f"{lo} % -1", "result", 0),
            (f"{hi} + 1", "fault", "IntegerOverflow"),
            (f"{lo} - 1", "fault", "IntegerOverflow"),
            (f"{hi} * 2", "fault", "IntegerOverflow"),
            (f"-({lo})", "fault", "IntegerOverflow"),
            ("0 / 0", "fault", "DivisionByZero"), ("7 % 0", "fault", "DivisionByZero"),
            (f"{lo} / -1", "fault", "IntegerOverflow"),
        ]
        for expr, kind, expected in cases:
            with self.subTest(expr=expr):
                self.assert_engines(module(f"return {expr};"), kind, expected)
        self.assert_engines(module(f"{hi} + 1; return 0;"), "fault", "IntegerOverflow")

    def test_generated_programs(self):
        # Fixed seeds reproduce every tree. At depth four even 5**16 fits I64.
        for seed in (17, 43, 101, 389):
            rng = random.Random(seed)
            checks = []
            for index in range(1, 25):
                expr, value = generate_expression(rng, 4)
                checks.append(f"if ({expr}) != {value} {{ return {index}; }}")
            helpers = "fn larger(a: I64, b: I64) -> I64 !{} { if a >= b { return a; } return b; }"
            with self.subTest(seed=seed):
                self.assert_engines(module("\n".join([*checks, "return 0;"]), helpers), "result", 0)

    def test_diagnostics(self):
        cases = [
            (module("return missing;"), "GPP-NAME-001"),
            (module("let x = 1; let x = 2; return x;"), "GPP-NAME-002"),
            (module("let x = 1; x = 2; return x;"), "GPP-MUT-001"),
            (module("return twice(true);", "fn twice(n: I64) -> I64 !{} { return n+n; }"), "GPP-TYPE-001"),
            (module("return false;"), "GPP-TYPE-001"),
            (module("if 42 { return 1; } return 0;"), "GPP-TYPE-001"),
            (module("if 1 < 2 { return 1; }"), "GPP-RETURN-001"),
            (module("if true { let only = 1; } return only;"), "GPP-NAME-001"),
            (module("return 0; return missing;"), "GPP-NAME-001"),
            (module("return zero(2);", "fn zero() -> I64 !{} { return 0; }"), "GPP-CALL-001"),
            (module("return 1;").replace("pub fn main", "fn main"), "GPP-ENTRY-001"),
            (module("return 1;").replace("!{}", "!{net}"), "GPP-PARSE-002"),
            (module("return 9223372036854775808;"), "GPP-PARSE-003"),
            (module("return true")[:-3], "GPP-PARSE-001"),
        ]
        # A quoted filename and multibyte comment exercise JSON escaping and byte locations.
        source_file = self.work / 'a"b.gpp'
        for source, code in cases:
            source = "// λ🚀\n" + source
            with self.subTest(source=source):
                source_file.write_text(source, encoding="utf-8")
                p = invoke(GPP, "check", "--format=json", source_file)
                self.assertEqual(p.returncode, 1, p.stderr)
                self.assertEqual(p.stdout, "")
                d = json.loads(p.stderr)
                self.assertEqual(d["code"], code)
                loc = d["location"]
                self.assertEqual(loc["file"], str(source_file))
                encoded = source.encode("utf-8")
                self.assertTrue(0 <= loc["start_byte"] <= loc["end_byte"] <= len(encoded))
                if "return missing;" in source:
                    self.assertEqual(encoded[loc["start_byte"]:loc["end_byte"]], b"missing")

    def test_limits_and_outputs(self):
        self.source.write_text(module("while true {}"))
        p = invoke(GPP, "run", "--interpreter", "--fuel", "10", self.source, timeout=5)
        self.assertEqual((p.returncode, p.stderr), (1, "fault: ResourceLimit\n"))
        self.source.write_text(module("return 7;"))
        self.assert_ok(invoke(GPP, "build", self.source, "-o", self.exe))
        old = self.exe.read_bytes()
        # A link/toolchain failure must preserve a previously successful build.
        broken_tools = {**os.environ, "GPP_LLVM_BIN": str(self.work)}
        p = invoke(GPP, "build", self.source, "-o", self.exe, env=broken_tools)
        self.assertEqual(p.returncode, 1)
        self.assertIn("GPP_LLVM_BIN", p.stderr)
        self.assertEqual(self.exe.read_bytes(), old)
        p = invoke(GPP, "build", self.source, "-o", self.source)
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(self.source.read_text(), module("return 7;"))
        self.source.write_text(module("return nope;"))
        self.assertNotEqual(invoke(GPP, "build", self.source, "-o", self.exe).returncode, 0)
        self.assertEqual(self.exe.read_bytes(), old)

    def test_value_records_and_enum_tags(self):
        helpers = """
fn copy(s: State) -> State !{} { return State(s.n, s.tag, s.flag, ()); }
record State { n: I64, tag: Tag, flag: Bool, empty: Unit }
enum Tag { Old, New }
record Empty {}
"""
        body = """
    var s: State = State(-7, Tag::Old, true, ());
    let old = s;
    s = State(0, Tag::New, false, ());
    let chosen = (if s != old { old } else { s }).n;
    let equal = old == copy(old) && Empty() == Empty() && s.tag != old.tag;
    return if equal { -copy(old).n + chosen } else { 99 };
"""
        self.assert_engines(module(body, helpers), "result", 0)
        # A strict constructor evaluates discarded fields in source order.
        self.assert_engines(module("State(1 / 0, Tag::Old, 1 + 9223372036854775807 > 1, ()); return 0;", helpers),
                            "fault", "DivisionByZero")
        self.source.write_text(module(body, helpers))
        ast = invoke(GPP, "ast", self.source)
        self.assert_ok(ast)
        self.source.write_text(ast.stdout)
        self.assertEqual(invoke(GPP, "ast", self.source).stdout, ast.stdout)
        self.assert_ok(invoke(GPP, "check", self.source))
        value = {"n": -9223372036854775808, "tag": "Tag::New", "flag": False, "empty": None}
        traced = self.trace("copy", "copy", "State(-9223372036854775808, Tag::New, false, ())")
        self.assertEqual(traced["args"], [value])
        self.assertEqual(traced["result"], value)
        row = next(r for r in traced["expressions"] if r["text"] == "s.tag")
        self.assertEqual((row["type"], row["observations"][0]), ("Tag", {"locals": {"s": value}, "value": "Tag::New"}))
        for invalid in ["State(0, Tag::Missing, false, ())", "State(0, Tag::New, 0, ())",
                        "State(0, Tag::New, true, (), ())", "copy(State(0, Tag::New, false, ()))"]:
            p = invoke(GPP, "trace", self.source, "--function", "copy", "--call", "copy", invalid)
            self.assertNotEqual(p.returncode, 0)
            self.assertIn("expected State", p.stderr)

    def test_structured_body_edits_and_batch_probe(self):
        source = module("return copy(R(1, E::A)).n;", """
enum E { A, B }
record R { n: I64, e: E }
fn copy(r: R) -> R !{} { return R(r.n, r.e); }""")
        self.source.write_text(source)
        fragment = self.work / "new-body"
        fragment.write_text("let value: R = R(r.n + 1, E::B); return value;")
        p = invoke(GPP, "edit", self.source, "--function", "copy", "--body", fragment, "--stdout")
        self.assert_ok(p)
        self.assertIn("let value: R", p.stdout)
        self.assertEqual(self.source.read_text(), source)
        exprs = self.trace("copy", "main")
        tag = next(r for r in exprs["expressions"] if r["text"] == "r.e")
        cases = self.work / "calls.tsv"
        cases.write_text("copy\tR(9, E::A)\tR(9, E::B)\n")
        cmd = [GPP, "probe", self.source, "--function", "copy", "--expect",
               exprs["revision"], "--cases", cases, "--filter"]
        def frame(expr):
            return f"{tag['start_byte']}:{tag['end_byte']} {len(expr)}\n{expr}"
        p = subprocess.run(cmd, input=frame("E::B") + frame("r.e"), text=True,
                           capture_output=True, timeout=10)
        self.assert_ok(p)
        rows = list(map(json.loads, p.stdout.splitlines()))
        self.assertEqual([r["matches"] for r in rows[1:]], [True, False])
        self.assertEqual(self.source.read_text(), source)

    def test_nominal_types_and_typed_hole_context(self):
        helpers = "record R { v: I64 } record S { v: I64 } enum E { X } enum F { X }"
        for expr in ["R(1) == S(1)", "E::X == F::X", "R(true)", "E::Missing", "R(1).missing",
                     "R(1, 2)", "E::X as I64", "R(1) as I64", "E::X < E::X"]:
            with self.subTest(expr=expr):
                self.source.write_text(module(f"{expr}; return 0;", helpers))
                p = invoke(GPP, "check", "--format=json", self.source)
                self.assertEqual(p.returncode, 1)
                self.assertIn(json.loads(p.stderr)["code"], ["GPP-NAME-001", "GPP-TYPE-001", "GPP-CALL-001"])
        for decl in ["record R { me: R }", "record R { x: I64, x: Bool }", "enum E { X, X }",
                     "enum E {}", "record R {} enum R { X }", "enum I64 { E }"]:
            self.source.write_text(module("return 0;", decl))
            self.assertNotEqual(invoke(GPP, "check", self.source).returncode, 0)
        source = module("return 0;", helpers + """
// λ
fn make(src: S, b: Bool) -> R !{} {
    let n = src.v;
    if b {
        let n = true;
        let r: R = ?create: R;
        return r;
    }
    return R(?value: I64);
}
""")
        self.source.write_text(source)
        for cmd in [("check",), ("run", "--interpreter"), ("emit-llvm",), ("verify",)]:
            p = invoke(GPP, *cmd, self.source)
            self.assertNotEqual(p.returncode, 0)
            self.assertIn("GPP-HOLE-001", p.stderr)
        p = invoke(GPP, "holes", self.source, "--function", "make", "--format=json")
        self.assert_ok(p)
        catalog = json.loads(p.stdout)
        self.assertEqual(catalog["schema"], "gpp.holes/1")
        self.assertEqual(catalog["revision"], invoke(GPP, "revision", self.source).stdout.strip())
        actual = []
        for h in catalog["holes"]:
            actual.append((h["name"], h["type"], source.encode()[h["start_byte"]:h["end_byte"]].decode(),
                           {slot["name"]: slot["type"] for slot in h["locals"]}))
        self.assertEqual(actual, [
            ("create", "R", "?create: R", {"src": "S", "b": "Bool", "n": "Bool"}),
            ("value", "I64", "?value: I64", {"src": "S", "b": "Bool", "n": "I64"}),
        ])
        for bad in [source.replace("?value: I64", "?value: Bool"),
                    source.replace("?value: I64", "missing"), source + "contract weak() { ?spec: Bool }"]:
            self.source.write_text(bad)
            self.assertNotEqual(invoke(GPP, "holes", self.source).returncode, 0)

    def test_line_endings(self):
        for newline in ("\r", "\n", "\r\n"):
            with self.subTest(newline=newline):
                self.source.write_bytes(("// λ" + newline + "module ;").encode("utf-8"))
                p = invoke(GPP, "check", self.source)
                self.assertEqual(p.returncode, 1)
                self.assertIn(f"{self.source}:2:8:", p.stderr)


if __name__ == "__main__":
    unittest.main()
