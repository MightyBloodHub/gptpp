"""Offline parser, semantics and compiler integration tests for scalar policies."""

from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from policy_ir import MAX_SOURCE_BYTES, lower_policy


HERE = Path(__file__).resolve().parent
GPP = HERE.parent / "target/debug/gpp"
PARAMS = [("x", "int"), ("flag", "bool")]


class PolicyTests(unittest.TestCase):
    def test_order_and_determinism(self):
        rules = "# Offset rule\r\nwhen x < 0 => abs(x)\nwhen flag => 10\n\nelse => x"
        body = lower_policy(rules, PARAMS)
        self.assertEqual(body, "if x < 0 {\n    return if x < 0 { -x } else { x };\n}\n"
                               "if flag {\n    return 10;\n}\nreturn x;")
        self.assertEqual(body, lower_policy(rules, iter(PARAMS)))
        self.assertEqual(lower_policy("else => not flag", PARAMS, "bool"), "return !flag;")
        self.assertEqual(lower_policy("else => keep", [("keep", "int")]), "return keep;")
        self.assertEqual(lower_policy("else => @keep", [], original_body="    return 8;\n"), "return 8;")

    def test_malformed_and_unsupported_rules(self):
        for source in [
                "", "# only", "when True => 4", "else => 0\nwhen True => 2", "else => 4\nelse => 1",
                "else if x => 1", "when => 2\nelse => 1", "case True => 1\nelse => 0",
                "when True => => 1\nelse => 0", "else => ", "when True => @keep\nelse => 1",
                "else => @keep", "else => x # trailing", "else => 1; return 3", "else => x) + (7",
                "else => x.__class__", "else => evil(x)", "else => x / 3", "else => 'text'",
                "else => unknown", "else => 9223372036854775808", "else => Ｘ",
                "when 1 => 1\nelse => 2", "when flag => False\nelse => 1",
                "when True => 1\nelse => flag", "else => min(flag, flag)",
                "else => 1 if x else 0", "else => x and 1", "else => (" * 8000,
                "#" * (MAX_SOURCE_BYTES + 1)]:
            with self.subTest(source=source[:120]), self.assertRaises(ValueError):
                lower_policy(source, PARAMS)
        with self.assertRaisesRegex(ValueError, "policy line 3"):
            lower_policy("# header\nwhen flag => 4\nelse => False", PARAMS)
        with self.assertRaises(ValueError):
            lower_policy("else => 1", PARAMS, result="bool")
        for params in ([("x", "int"), ("x", "bool")], [("fn", "int")], ["ab"], None):
            with self.subTest(params=params), self.assertRaises(ValueError):
                lower_policy("else => @keep", params, original_body="return 1;")

    def test_interpreted_types_short_circuit_and_faults(self):
        cases = [
            ("when x < 0 => 3\nwhen flag => 1 // 0\nelse => 9", "-2, true", "3"),
            ("when flag and 1 // x > 0 => 8\nelse => -5 % 3", "0, false", "-2"),
            ("when flag and 1 // x > 0 => 8\nelse => -5 % 3", "0, true", "fault: DivisionByZero"),
            ("when x > 0 => 9223372036854775807 + x\nelse => 0", "1, false", "fault: IntegerOverflow"),
            ("when not flag => -7 // 3\nelse => min(4, 1 // 0)", "0, false", "-2"),
            ("when flag => max(3, abs(x))\nelse => @keep", "-6, true", "6"),
            ("when flag => max(3, abs(x))\nelse => @keep", "4, false", "12"),
        ]
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.gpp"
            for policy, args, expected in cases:
                with self.subTest(policy=policy, args=args):
                    body = lower_policy(policy, PARAMS, original_body="return x * 3;")
                    path.write_text("module demo; fn policy(x: I64, flag: Bool) -> I64 !{} {\n"
                                    + body + "\n}\npub fn main() -> I64 !{} { return policy(" + args + "); }")
                    r = subprocess.run([GPP, "run", "--interpreter", path], capture_output=True, text=True)
                    self.assertEqual((r.stdout or r.stderr).strip(), expected)
                    self.assertEqual(r.returncode == 0, not expected.startswith("fault:"))

    def test_offline_cli_preview_and_apply(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.gpp"
            original = ("module demo;\nfn allowed(x: I64) -> Bool !{} { return x < 0; }\n"
                        "pub fn main() -> I64 !{} {\n"
                        "    if allowed(3) && allowed(-1) && !allowed(1) { return 123; }\n    return 0;\n}\n")
            path.write_text(original)
            cmd = [sys.executable, "-B", HERE / "policy_ir.py", "--source", path, "--function", "allowed"]
            rules = "when x == 3 => True\nelse => @keep\n"
            preview = subprocess.check_output([*cmd, "--preview"], input=rules, text=True)
            self.assertEqual(path.read_text(), original)
            self.assertTrue(preview.endswith(original[original.index("\npub fn main"):]))
            bad = subprocess.run([*cmd, "--apply"], input="else => 99", text=True, capture_output=True)
            self.assertNotEqual(bad.returncode, 0)
            self.assertEqual(path.read_text(), original)
            subprocess.run([*cmd, "--apply"], input=rules, text=True, capture_output=True, check=True)
            self.assertEqual(path.read_text(), preview)
            self.assertEqual(subprocess.check_output([GPP, "run", "--interpreter", path], text=True), "123\n")


if __name__ == "__main__":
    unittest.main()
