"""Run the example-filtered repair workflow through its public CLI and checked editor."""

import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from test_propose import GPP, HERE, mock_ollama


SOURCE = """module example;
// UTF-8 π shifts the source offsets.
fn target(x: I64) -> I64 !{} { return x; }
pub fn main() -> I64 !{} { return target(-7); }
"""


class RepairTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory(prefix="repair test ")
        self.addCleanup(tmp.cleanup)
        work = Path(tmp.name)
        self.source = work / "original.gpp"
        self.source.write_text(SOURCE)
        self.output = work / "suggested expression"
        self.cases = work / "public.json"
        self.cases.write_text('[{"function":"main","args":[],"expected":-6},{"args":[4],"expected":5}]')

    def invoke(self, *args):
        return subprocess.run(
            [sys.executable, "-B", HERE / "repair.py", self.source, "--function", "target",
             "--gpp", GPP, "--cases", self.cases, *args],
            capture_output=True, text=True, timeout=30,
        )

    def choose(self, port):
        return self.invoke("--port", str(port), "--model", "mock", "--task", "Increment x.",
                           "-o", self.output)

    def test_menu_needs_no_model_and_uses_exact_span_for_caller_failure(self):
        result = self.invoke("--list", "--port", "0")
        self.assertEqual(result.returncode, 0, result.stderr)
        menu = json.loads(result.stdout)
        start = SOURCE.encode().index(b"x;")
        self.assertEqual(menu["candidates"], [
            dict(start_byte=start, end_byte=start + 1, old="x", replacement="x + 1")
        ])
        self.assertEqual(menu["status"], "listed")
        self.assertEqual(menu["stop_reason"], "grammar_complete")
        self.assertEqual(menu["observations"][0], dict(call="main()", actual="-7", expected="-6"))
        self.assertEqual(self.source.read_text(), SOURCE)

    def test_model_selects_only_checked_fragment_and_apply_is_revision_guarded(self):
        with mock_ollama(['{"choice":1}']) as (port, calls):
            run = self.choose(port)
        self.assertEqual(run.returncode, 0, run.stderr)
        menu = json.loads(run.stdout)
        self.assertEqual((menu["status"], menu["selected"]), ("selected", 1))
        self.assertEqual(self.source.read_text(), SOURCE)
        self.assertEqual(self.output.read_text(), "x + 1\n")
        request, = [p for path, p in calls if path == "/api/generate"]
        self.assertEqual(request["format"]["properties"]["choice"]["enum"], [0, 1])
        self.assertIn("main() returned -7, expected -6", request["prompt"])
        subprocess.run(menu["apply"], check=True, capture_output=True, timeout=10)
        self.assertEqual(subprocess.check_output([GPP, "run", "--interpreter", self.source]), b"-6\n")
        self.assertIn(b"stale revision", subprocess.run(menu["apply"], capture_output=True).stderr)

    def test_abstention_invalid_choice_and_concurrent_revision(self):
        for reply in ('{"choice":0}', '{"choice":2}', '{"choice":true}', '{"choice":0,"choice":1}'):
            with self.subTest(reply=reply), mock_ollama([reply]) as (port, _):
                run = self.choose(port)
                if reply == '{"choice":0}':
                    self.assertEqual(run.returncode, 0, run.stderr)
                    self.assertEqual(json.loads(run.stdout)["status"], "abstained")
                else:
                    self.assertNotEqual(run.returncode, 0)
                self.assertFalse(self.output.exists())
        changed = SOURCE + "// another editor\n"
        with mock_ollama(['{"choice":1}'], on_generate=lambda: self.source.write_text(changed)) as (port, _):
            run = self.choose(port)
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("stale revision", run.stderr)
        self.assertEqual(self.source.read_text(), changed)
        self.assertFalse(self.output.exists())

    def test_unreachable_target_passing_source_and_exhausted_budget(self):
        for source, cases, status, reason, tested in [
            (SOURCE.replace("target(-7)", "-7"), '[{"function":"main","args":[],"expected":9}]',
             "no_candidates", "grammar_complete", 0),
            (SOURCE, '[{"args":[4],"expected":4}]', "already_passes", "already_passes", 0),
            (SOURCE, '[{"args":[4],"expected":8}]', "no_candidates", "budget", 1),
        ]:
            with self.subTest(reason=reason):
                self.source.write_text(source)
                self.cases.write_text(cases)
                run = self.invoke("--list", "--budget", "1")
                self.assertEqual(run.returncode, 0, run.stderr)
                result = json.loads(run.stdout)
                self.assertEqual((result["status"], result["stop_reason"], result["tested"]),
                                 (status, reason, tested))
                self.assertEqual(result["exhausted"], reason == "budget")
                self.assertEqual(result["candidates"], [])

    def test_arithmetic_fault_can_be_traced_and_repaired(self):
        self.source.write_text(SOURCE.replace("return x;", "return x / 0;"))
        self.cases.write_text('[{"args":[5],"expected":5},{"args":[2],"expected":2}]')
        run = self.invoke("--list")
        self.assertEqual(run.returncode, 0, run.stderr)
        result = json.loads(run.stdout)
        self.assertEqual(result["observations"][0]["actual"], "fault: DivisionByZero")
        self.assertTrue(any(c["old"] == "x / 0" and c["replacement"] == "x"
                            for c in result["candidates"]))


if __name__ == "__main__":
    unittest.main()
