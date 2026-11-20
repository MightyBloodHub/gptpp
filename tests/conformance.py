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

    def test_line_endings(self):
        for newline in ("\r", "\n", "\r\n"):
            with self.subTest(newline=newline):
                self.source.write_bytes(("// λ" + newline + "module ;").encode("utf-8"))
                p = invoke(GPP, "check", self.source)
                self.assertEqual(p.returncode, 1)
                self.assertIn(f"{self.source}:2:8:", p.stderr)


if __name__ == "__main__":
    unittest.main()
