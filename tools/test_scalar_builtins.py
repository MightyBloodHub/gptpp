"""Checks for the product-only scalar builtin expansion, using the existing interpreter."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from scalar_builtins import lower_fragment


GPP = Path(__file__).resolve().parents[1] / "target/debug/gpp"


class ScalarBuiltinTests(unittest.TestCase):
    def test_checked_values_lazy_context_and_eager_fault_order(self):
        cases = [
            ("min(abs(-7 - 2), max(3, 6))", "6"),
            ("max(-5, -5)", "-5"),
            ("min(9223372036854775807, -9223372036854775808)", "-9223372036854775808"),
            ("abs(-9223372036854775808)", "fault: IntegerOverflow"),
            ("min(0, 1 // 0)", "fault: DivisionByZero"),
            ("max(1 // 0, abs(-9223372036854775808))", "fault: DivisionByZero"),
            ("max(abs(-9223372036854775808), 1 // 0)", "fault: IntegerOverflow"),
            ("7 if True else min(abs(-9223372036854775808), 1 // 0)", "7"),
            ("max(1 if True else 1 // 0, 4)", "4"),
        ]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "builtin.gpp"
            for expr, expected in cases:
                with self.subTest(expr=expr):
                    native = lower_fragment(expr, "expr", [])
                    path.write_text("module testmod; pub fn main() -> I64 !{} { return " + native + "; }")
                    result = subprocess.run([GPP, "run", "--interpreter", "--fuel", "100000", path],
                                            capture_output=True, text=True, timeout=4)
                    self.assertEqual((result.stdout or result.stderr).strip(), expected)
                    self.assertEqual(result.returncode == 0, not expected.startswith("fault"))

    def test_rejects_ambient_calls_wrong_types_shadowing_and_large_expansions(self):
        invalid = [
            ("abs(flag)", "expr"), ("min(True, False)", "expr"), ("max(1, True)", "expr"),
            ("sum(x)", "expr"), ("x.abs()", "expr"), ("abs(value=x)", "expr"),
            ("abs(*x)", "expr"), ("min(1)", "expr"), ("max(1,2,3)", "expr"),
            ("abs(1,2)", "expr"), ("return abs(x)\nabs = 2", "body"),
            ("abs(" * 25 + "x" + ")" * 25, "expr"),
        ]
        for text, mode in invalid:
            with self.subTest(text=text), self.assertRaises(ValueError):
                lower_fragment(text, mode, [("flag", "bool"), ("x", "int")])
        with self.assertRaisesRegex(ValueError, "shadowed"):
            lower_fragment("max(1,2)", "expr", [("max", "int")])
        # Existing supported source can still use one of these names as data.
        self.assertEqual(lower_fragment("max + 1", "expr", [("max", "int")]), "max + 1")

    def test_body_nested_calls_can_use_typed_local_bindings(self):
        code = lower_fragment("delta = abs(position - left)\nreturn min(delta, 6)", "body",
                              [("position", "int"), ("left", "int")])
        src = "module demo; fn fn1(position: I64, left: I64) -> I64 !{} {\n" + code \
              + "\n} pub fn main() -> I64 !{} { return fn1(-2, 5); }"
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "local.gpp"
            path.write_text(src)
            self.assertEqual(subprocess.check_output([GPP, "run", "--interpreter", path]), b"6\n")


if __name__ == "__main__":
    unittest.main()
