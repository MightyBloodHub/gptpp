"""Exercise numbered expression edits against a real compiler and a loopback Ollama stub."""

import json
from pathlib import Path
import shlex
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from indexed_edit import edit_request, order_spans, read_change
from test_propose import GPP, HERE, mock_ollama


SOURCE = """module demo;
// π outside the target changes its UTF-8 byte offset.
fn target(x: I64) -> I64 !{} {
    // Keep this π comment.
    return x - x;
}
pub fn main() -> I64 !{} { return target(123456); }
"""


class IndexedEditTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory(prefix="indexed edit ")
        self.addCleanup(tmp.cleanup)
        work = Path(tmp.name)
        self.file = work / "source file.gpp"
        self.output = work / "saved fragment"
        self.cases = work / "cases.json"
        self.file.write_text(SOURCE)
        self.cases.write_text(json.dumps([{"function": "main", "args": [], "expected": -1},
                                          {"args": [7], "expected": -1}]))

    def invoke(self, port):
        return subprocess.run(
            [sys.executable, "-B", HERE / "indexed_edit.py", self.file, "--function", "target",
             "--task", "Increase the right operand of the subtraction by one.", "--cases", self.cases,
             "--model", "mock", "--port", str(port), "--gpp", GPP, "-o", self.output],
            capture_output=True, text=True, timeout=15,
        )

    def test_duplicate_text_distinct_sites_publish_only_the_second_edit(self):
        with mock_ollama([json.dumps({"site": "3", "replacement": "x + 1"})]) as (port, calls):
            result = self.invoke(port)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.file.read_text(), SOURCE)
        self.assertEqual(self.output.read_bytes(), b"x + 1\n")
        request, = [payload for path, payload in calls if path == "/api/generate"]
        self.assertIn("1 (L3) x - x\n2 (L3) x\n3 (L3) x\n", request["prompt"])
        self.assertIn("main() = -1", request["prompt"])
        self.assertNotIn("123456", request["prompt"])
        self.assertEqual(request["format"]["properties"]["site"]["enum"], ["1", "2", "3"])
        self.assertFalse(request["format"]["additionalProperties"])
        self.assertIn("-    return x - x;\n+    return x - (x + 1);", result.stdout)

        command = shlex.split(result.stdout.splitlines()[-1])
        start = SOURCE.encode().index(b"x;", SOURCE.encode().index(b"return x - "))
        self.assertEqual(command[command.index("--at") + 1], f"{start}:{start + 1}")
        revision = subprocess.check_output([GPP, "revision", self.file], text=True).strip()
        self.assertEqual(command[command.index("--expect") + 1], revision)
        subprocess.run(command, check=True, capture_output=True, timeout=10)
        self.assertEqual(self.file.read_text(), SOURCE.replace("return x - x;", "return x - (x + 1);"))
        self.assertEqual(subprocess.check_output([GPP, "run", "--interpreter", self.file]), b"-1\n")
        second = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertNotEqual(second.returncode, 0)
        self.assertIn("stale revision", second.stderr)

    def test_wrong_duplicate_caller_failure_and_invalid_edits_publish_nothing(self):
        for site, fragment, error in [
            ("2", "x + 1", "expected -1"),          # Editing the first x produces +1.
            ("3", "true", "GPP-TYPE"),              # Type error at the selected expression.
            ("3", "1; return 8;", "GPP-"),          # The replacement must be one expression.
            ("4", "0", "outside the checked catalog"),
        ]:
            reply = json.dumps({"site": site, "replacement": fragment})
            with self.subTest(site=site, fragment=fragment), mock_ollama([reply]) as (port, calls):
                result = self.invoke(port)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(error, result.stderr)
                self.assertFalse(self.output.exists())
                self.assertEqual(self.file.read_text(), SOURCE)
                self.assertEqual(sum(path == "/api/generate" for path, _ in calls), 1)

    def test_source_changed_during_generation_is_preserved(self):
        updated = SOURCE.replace("Keep this π comment", "Edited concurrently")
        reply = json.dumps({"site": "3", "replacement": "x + 1"})
        with mock_ollama([reply], on_generate=lambda: self.file.write_text(updated)) as (port, _):
            result = self.invoke(port)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("stale revision", result.stderr)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.file.read_text(), updated)


class IndexedRequestTests(unittest.TestCase):
    def test_order_of_nested_sites_and_duplicate_ranges(self):
        self.assertEqual(order_spans([(3, 4), (0, 1), (0, 5), (0, 1)]), [(0, 5), (0, 1), (3, 4)])
        with self.assertRaisesRegex(ValueError, "no selectable expressions"):
            edit_request("mock", "gpp", "task", [], "", [])

    def test_response_requires_exact_fields_and_a_canonical_string_id(self):
        spans = [(1, 7), (1, 2)]
        for bad in (None, [], {}, {"site": "1"}, {"site": "1", "replacement": "x", "note": "ok"},
                    *({"site": site, "replacement": "x"} for site in [0, 1, True, "0", "3", "01", " 1", "١"]),
                    *({"site": "1", "replacement": v} for v in [None, 1, [], "", "  \n "])):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                read_change(json.dumps(bad), spans)
        for raw in ('{"site":"1","site":"2","replacement":"x"}',
                    '{"site":"1","replacement":"7","replacement":"8"}',
                    '{"site":"1","replacement":"x"} trailing'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                read_change(raw, spans)
        self.assertEqual(read_change('{"replacement":"a + b","site":"2"}', spans), ((1, 2), "a + b"))


if __name__ == "__main__":
    unittest.main()
