"""Run after cargo build --locked --offline: python3 -B tools/test_scalar_fragment.py

Set GPP_TEST_NATIVE=1 to also build and run each accepted case at -O0 and -O2.
"""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scalar_fragment import lower_fragment


ROOT = Path(__file__).resolve().parents[1]
GPP = ROOT / "target/debug/gpp"
PARAMS = [("flag", "bool"), ("n", "int")]
SOURCE = """module adapter.oracle;
fn solve(flag: Bool, n: I64) -> I64 !{} { return 0; }
pub fn main() -> I64 !{} { return solve(FLAG, 5); }
"""


def run(*args, **kwargs):
    return subprocess.run(args, text=True, capture_output=True, timeout=30, **kwargs)


class ScalarFragments(unittest.TestCase):
    def test_lower_edit_check_execute(self):
        self.assertTrue(GPP.is_file(), "build the compiler with cargo build --locked --offline first")
        # Each tuple supplies the form, source, flag argument and hand-derived observable.
        cases = [
            ("expr", "-9 // 4 + -9 % 4", False, -3),
            ("expr", "-9223372036854775808 // -1", False, "IntegerOverflow"),
            ("expr", "9223372036854775807 + 1 if flag else 5", False, 5),
            ("expr", "9223372036854775807 + 1 if flag else 5", True, "IntegerOverflow"),
            ("expr", "1 if 3 <= n < 9 and (n > 0 or 1 // 0 == 0) else 0", True, 1),
            ("expr", "1 if False and 7 // 0 == 0 else -3 * (5 - (4 - 1))", False, -6),
            ("expr", "-(-9223372036854775808)", False, "IntegerOverflow"),
            ("body", """
                n_local = 2
                n_local_2 = 3
                while n > 0:
                    if n == 1:
                        return n_local * 10 + n_local_2
                    n -= 1
                return -1
            """, False, 23),
            ("body", """
                if flag:
                    var = -9
                    var_local = var // 4
                    return var_local
                elif n == 0:
                    return n + 1
                else:
                    var = -1
                    n *= var
                    return n
            """, False, -5),
            ("body", """
                answer = n
                if flag:
                    answer = 30
                    n = -9
                else:
                    answer += 10
                return answer - n
            """, True, 39),
            ("body", "n = 10\nn //= -3\nn %= -2\nreturn n", False, -1),
            ("body", "if flag:\n    answer = 4\nelse:\n    answer = 9\nanswer = 2\nreturn answer", False, 2),
        ]
        with tempfile.TemporaryDirectory(prefix="gpp-fragment-tests-") as folder:
            work = Path(folder)
            base, fragment, candidate, exe = [work / f for f in ("base.gpp", "fragment", "out.gpp", "app")]
            for form, code, flag, expected in cases:
                with self.subTest(code=code, flag=flag):
                    base.write_text(SOURCE.replace("FLAG", str(flag).lower()))
                    fragment.write_text(lower_fragment(code, form, PARAMS))
                    edit = run(GPP, "edit", base, "--function", "solve", "--" + form, fragment, "--stdout")
                    self.assertEqual(edit.returncode, 0, edit.stderr)
                    candidate.write_text(edit.stdout)
                    checked = run(GPP, "check", candidate)
                    self.assertEqual(checked.returncode, 0, checked.stderr)
                    self.assert_observable(run(GPP, "run", "--interpreter", candidate), expected)
                    if os.environ.get("GPP_TEST_NATIVE") == "1":
                        for level in ("-O0", "-O2"):
                            built = run(GPP, "build", level, candidate, "-o", exe)
                            self.assertEqual(built.returncode, 0, built.stderr)
                            self.assert_observable(run(exe), expected)

    def assert_observable(self, result, expected):
        observed = (result.returncode, result.stdout, result.stderr)
        if isinstance(expected, int):
            self.assertEqual(observed, (0, f"{expected}\n", ""))
        else:
            self.assertEqual(observed, (1, "", f"fault: {expected}\n"))

    def test_rejected_forms(self):
        expressions = ["n if 1 else 2", "abs(4)", "3 / 2", "[]", "True + 1", "n < (n + 1) < 10",
                       "9223372036854775808", "1 if True else False", "3 and 4", "dog", "n << 2", "().__class__"]
        bodies = ["if True:\n    x = 4\nreturn x", "while False:\n    x = n\nreturn x",
                  "import sys\nreturn 42", "x = y = 1\nreturn x", "x = 0\nx = False\nreturn x",
                  "x += 1\nreturn x", "while n > 0:\n    n -= 1\nelse:\n    n = 0\nreturn n",
                  "return", "for i in range(n):\n    return 1", "x: int = 2\nreturn x"]
        for form, cases in (("expr", expressions), ("body", bodies)):
            for code in cases:
                with self.subTest(code=code), self.assertRaises(ValueError):
                    lower_fragment(code, form, PARAMS)

    def test_stdin_cli(self):
        result = run(sys.executable, "-B", ROOT / "tools/scalar_fragment.py", "expr", "--param", "n:int",
                     input="n // -4\n")
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "n / -4\n", ""))


if __name__ == "__main__":
    unittest.main()
