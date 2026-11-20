"""Exercise checked agent-generated patches and retries through the public CLI."""

import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from test_propose import GPP, HERE, mock_ollama


class AgentEditTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory(prefix="agent-edit-")
        self.addCleanup(tmp.cleanup)
        work = Path(tmp.name)
        self.file, self.cases, self.fragment = work / "demo.gpp", work / "cases.json", work / "edit.expr"
        self.source = (HERE.parent / "examples/add.gpp").read_text()
        self.file.write_text(self.source)
        self.cases.write_text(json.dumps([{"args": [8, 3], "expected": 5},
                                          {"function": "main", "args": [], "expected": -2}]))

    def invoke(self, port):
        return subprocess.run([sys.executable, "-B", HERE / "agent_edit.py", self.file,
                               "--function", "add", "--task", "Return left minus right.",
                               "--cases", self.cases, "--model", "mock", "--gpp", GPP, "--port",
                               str(port), "-o", self.fragment], text=True, capture_output=True, timeout=20)

    def test_public_failure_retries_against_original_then_publishes_guarded_patch(self):
        bad = json.dumps({"site": "1", "replacement": "left + right"})
        fix = json.dumps({"site": "1", "replacement": "left - right"})
        with mock_ollama([bad, fix]) as (port, calls):
            result = self.invoke(port)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual([a["status"] for a in data["attempts"]], ["wrong_answer", "pass"])
        self.assertEqual(self.fragment.read_text(), "left - right\n")
        prompts = [body["prompt"] for path, body in calls if path == "/api/generate"]
        self.assertEqual(len(prompts), 2)
        self.assertIn("add(8, 3) returned 11. Expected 5.", prompts[1])
        self.assertIn("left + right", prompts[1])
        self.assertEqual(self.file.read_text(), self.source)
        subprocess.run(data["apply"], check=True, capture_output=True)
        self.assertEqual(subprocess.check_output([GPP, "run", "--interpreter", self.file], text=True), "-2\n")

    def test_stale_source_preserves_the_new_revision_and_publishes_nothing(self):
        changed = self.source + "// concurrent edit\n"
        fix = json.dumps({"site": "1", "replacement": "left - right"})
        with mock_ollama([fix], on_generate=lambda: self.file.write_text(changed)) as (port, _):
            result = self.invoke(port)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Source changed", result.stderr)
        self.assertEqual(self.file.read_text(), changed)
        self.assertFalse(self.fragment.exists())


if __name__ == "__main__":
    unittest.main()
