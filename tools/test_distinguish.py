"""Black-box checks of unlabeled probe questions using the real compiler and repair menu IDs."""

import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from test_propose import GPP, HERE


SOURCE = """module samples;
// π keeps byte offsets distinct from character offsets.
fn target(x: I64, flag: Bool) -> I64 !{} { return x; }
fn positive(a: I64) -> Bool !{} { return target(a, true) > 0; }
fn discard(u: Unit) -> Unit !{} { target(0, true); return u; }
pub fn main() -> I64 !{} { return target(5, false); }
"""


class DistinguishTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory(prefix="distinguish test ")
        self.addCleanup(tmp.cleanup)
        work = Path(tmp.name)
        self.source = work / "source.gpp"
        self.source.write_text(SOURCE)
        self.menu = work / "menu.json"
        self.probes = work / "probes.json"
        catalog = json.loads(subprocess.check_output(
            [GPP, "expressions", self.source, "--function", "target"]))
        expr, = catalog["expressions"]
        self.candidates = [dict(start_byte=expr["start_byte"], end_byte=expr["end_byte"],
                                old=expr["text"], replacement=value)
                           for value in ("x + 1", "1", "1 / x", "if flag { 1 } else { x }")]
        self.original = dict(schema="gpp.repair/1", function="target", revision=catalog["revision"],
                             candidates=self.candidates)
        self.menu.write_text(json.dumps(self.original))

    def run_cli(self, probes, *options):
        self.probes.write_text(json.dumps(probes))
        return subprocess.run([sys.executable, "-B", HERE / "distinguish.py", self.source,
                               "--menu", self.menu, "--probes", self.probes, "--gpp", GPP, *options],
                              text=True, capture_output=True, timeout=30)

    def result(self, probes, *options):
        r = self.run_cli(probes, *options)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_selects_maximum_pair_split_earliest_on_ties_preserving_original_ids(self):
        probes = [{"args": [1, True]}, {"args": [0, False]}, {"function": "main", "args": []},
                  {"args": [8, False]}]
        report = self.result(probes)
        self.assertEqual(report["schema"], "gpp.distinguish/1")
        self.assertEqual(report["revision"], self.original["revision"])
        self.assertEqual((report["status"], report["candidate_count"], report["probes_tested"]),
                         ("question", 4, 4))
        self.assertEqual(report["question"], {
            "function": "main", "args": [], "separated_pairs": 6,
            "outcomes": [{"result": 6, "candidates": [1]}, {"result": 1, "candidates": [2]},
                         {"result": 0, "candidates": [3]}, {"result": 5, "candidates": [4]}]})
        narrowed = self.result(probes, "--candidates", "4,2")
        self.assertEqual(narrowed["candidate_count"], 2)
        self.assertEqual(narrowed["question"], {
            "function": "target", "args": [0, False], "separated_pairs": 1,
            "outcomes": [{"result": 1, "candidates": [2]}, {"result": 0, "candidates": [4]}]})
        self.assertEqual(self.source.read_text(), SOURCE)

    def test_groups_exact_typed_values_and_faults(self):
        bool_result = self.result([{"function": "positive", "args": [-2]}])["question"]
        self.assertEqual(bool_result["separated_pairs"], 4)
        self.assertIs(bool_result["outcomes"][0]["result"], False)
        self.assertIs(bool_result["outcomes"][1]["result"], True)
        self.assertEqual(bool_result["outcomes"][0]["candidates"], [1, 3])
        faults = self.result([{"function": "discard", "args": [None]}])["question"]
        self.assertEqual(faults["outcomes"], [{"result": None, "candidates": [1, 2, 4]},
                                               {"fault": "DivisionByZero", "candidates": [3]}])
        boundary = self.result([{"args": [2**63 - 1, False]}])["question"]
        self.assertIn({"fault": "IntegerOverflow", "candidates": [1]}, boundary["outcomes"])

    def test_no_split_and_small_menus(self):
        cases = [{"args": [0, True]}]
        for options, tested in [(("--candidates", "1,2,4"), 1), (("--candidates", "2"), 0)]:
            r = self.result(cases, *options)
            self.assertEqual((r["status"], r["question"], r["probes_tested"]),
                             ("indistinguishable", None, tested))
        self.menu.write_text(json.dumps(dict(self.original, candidates=[])))
        r = self.result(cases)
        self.assertEqual((r["candidate_count"], r["probes_tested"], r["question"]), (0, 0, None))

    def test_validates_even_unselected_candidates_and_source_revision(self):
        probes = [{"args": [0, True]}]
        for changed in [dict(old="y"), dict(start_byte=True), dict(replacement="return 1;"),
                        dict(replacement="flag")]:
            candidates = self.candidates.copy()
            candidates[-1] = dict(candidates[-1], **changed)
            self.menu.write_text(json.dumps(dict(self.original, candidates=candidates)))
            run = self.run_cli(probes, "--candidates", "1,2")
            self.assertNotEqual(run.returncode, 0)
            self.assertEqual(run.stdout, "")
        self.menu.write_text(json.dumps(self.original))
        self.source.write_text(SOURCE + "// concurrent edit\n")
        stale = self.run_cli(probes)
        self.assertNotEqual(stale.returncode, 0)
        self.assertIn("stale revision", stale.stderr.lower())
        self.assertEqual(self.source.read_text(), SOURCE + "// concurrent edit\n")

    def test_rejects_labels_bad_arity_out_of_range_types_and_unknown_ids(self):
        for probes, options in [([{"args": [0, True], "expected": 1}], ()), ([{"args": []}], ()),
                                ([{"args": [False, True]}], ()), ([{"args": [2**63, True]}], ()),
                                ([{"function": "missing", "args": []}], ()),
                                ([{"args": [0, True]}], ("--candidates", "0,2")),
                                ([{"args": [0, True]}], ("--candidates", "1,1")),
                                ([{"args": [0, True]}], ("--candidates", "20"))]:
            run = self.run_cli(probes, *options)
            self.assertNotEqual(run.returncode, 0)
            self.assertEqual(run.stdout, "")

    def test_accepts_unmodified_product_menu(self):
        public = self.source.parent / "public.json"
        public.write_text('[{"args":[0,true],"expected":1}]')
        menu = subprocess.check_output([sys.executable, "-B", HERE / "repair.py", self.source,
                                        "--function", "target", "--cases", public, "--list", "--gpp", GPP])
        self.menu.write_bytes(menu)
        r = self.result([{"args": [2, False]}, {"args": [3, True]}])
        self.assertEqual(r["status"], "question")
        self.assertEqual(r["candidate_count"], len(json.loads(menu)["candidates"]))
        self.assertEqual(self.menu.read_bytes(), menu)
        self.assertEqual(self.source.read_text(), SOURCE)


if __name__ == "__main__":
    unittest.main()
