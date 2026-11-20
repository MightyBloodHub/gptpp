"""Contract-driven edits through the public compiler and both authoring workflows."""

from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from test_propose import GPP, HERE, mock_ollama


SOURCE = """module sample;
// λ → byte spans differ from character positions.
fn ready(x: I64, b: Bool) -> Bool !{} {
    let cap = 1;
    return (x < cap) // preserve this comment
        || b;
}
fn caller(v: I64, allowed: Bool) -> Bool !{} { return ready(v, allowed); }
pub fn main() -> I64 !{} { return caller(0, true) as I64; }
contract ready(x: I64 in -1..=1, b: Bool) { caller(x,b) == (b && (x <= 0)) }
"""


class Contracts(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.source = self.dir / "original.gpp"
        self.source.write_text(SOURCE)
        self.out = self.dir / "proposal.expr"

    def invoke(self, *arguments, tool="contract_repair.py"):
        proc = subprocess.run([sys.executable, "-B", HERE / tool, self.source, "--function", "ready",
                               "--gpp", GPP, "-o", self.out, *arguments],
                              text=True, capture_output=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def menu(self, *fragments):
        raw = self.source.read_bytes()
        old = "(x < cap) // preserve this comment\n        || b"
        start = raw.index(old.encode())
        rows = [dict(start_byte=start, end_byte=start + len(old), old=old, replacement=f) for f in fragments]
        path = self.dir / "menu.json"
        path.write_text(json.dumps(dict(schema="gpp.repair/1", function="ready",
                                        revision="sha256:" + sha256(raw).hexdigest(), candidates=rows)))
        return path

    def test_counterexample_localizes_indirect_call_and_guarded_apply_rechecks_fragment(self):
        result = self.invoke()
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["verification"]["checked"], 6)
        self.assertIn("// preserve this comment", self.out.read_text())
        self.assertIn("&& b", self.out.read_text())
        self.assertEqual(self.source.read_text(), SOURCE)
        good = self.out.read_text()
        self.out.write_text("true")
        proc = subprocess.run(result["apply"], capture_output=True)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(json.loads(proc.stderr)["status"], "counterexample")
        self.assertEqual(self.source.read_text(), SOURCE)
        self.out.write_text(good)
        subprocess.run(result["apply"], check=True)
        installed = "sha256:" + sha256(self.source.read_bytes()).hexdigest()
        self.assertEqual(installed, result["verification"]["revision"])
        self.assertEqual(self.invoke("-o", self.dir / "next.expr")["status"], "already_passes")

    def test_replay_refines_witnesses_and_menu_abstains_under_ambiguity_or_limits(self):
        path = self.menu("false", "true", "unknown", "b && x < cap", "x <= 0 && b")
        result = self.invoke("--menu", path)
        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual([row["status"] for row in result["outcomes"]],
                         ["rejected", "rejected", "invalid", "passed", "passed"])
        self.assertGreaterEqual(len(result["witnesses"]), 2)
        self.assertGreaterEqual(result["rejected_by_replay"], 1)
        self.assertFalse(self.out.exists())
        result = self.invoke("--menu", path, "--edits", "4")
        self.assertEqual(result["status"], "incomplete")
        self.assertIsNone(result["selected"])
        self.assertFalse(self.out.exists())
        result = self.invoke("--menu", path, "--budget", "5")
        self.assertEqual(result["status"], "incomplete")
        self.assertFalse(self.out.exists())

    def test_witness_arguments_are_typed_and_range_checked(self):
        for args in [["2", "false"], ["0", "1"], []]:
            proc = subprocess.run([GPP, "trace", self.source, "--function", "ready", "--contract", "ready", *args],
                                  capture_output=True)
            self.assertNotEqual(proc.returncode, 0)
            self.assertEqual(proc.stdout, b"")

    def test_local_model_receives_declared_contract_and_a_new_counterexample_for_retry(self):
        incorrect = json.dumps({"site": "1", "replacement": "false"})
        correct = json.dumps({"site": "1", "replacement": "b && x < cap"})
        # Use an expression-only target so its root has a stable first catalog ID.
        self.source.write_text(SOURCE.replace("    let cap = 1;\n", "").replace("x < cap", "x < 1"))
        correct = correct.replace("cap", "1")
        with mock_ollama([incorrect, correct]) as (port, calls):
            result = self.invoke("--contracts", "--model", "mock", "--port", str(port), tool="agent_edit.py")
        self.assertEqual(result["status"], "proposed")
        self.assertEqual([row["status"] for row in result["attempts"]], ["counterexample", "pass"])
        self.assertEqual(result["verification"]["checked"], 6)
        self.assertIn("--verify", result["apply"])
        requests = [data["prompt"] for path, data in calls if path == "/api/generate"]
        self.assertIn("contract ready(", requests[0])
        self.assertIn('"b": false', requests[0])
        self.assertIn('"b": true', requests[1])
        self.assertEqual(self.out.read_text(), "b && x < 1\n")

    def test_incomplete_baseline_never_requests_inference(self):
        result = self.invoke("--contracts", "--port", "0", "--budget", "0", tool="agent_edit.py")
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["attempts"], [])
        self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main()
