"""Exercise typed-hole authoring and solver agreement through the shipped CLI."""

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_propose import GPP


class CompletionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.work = Path(temp.name)
        self.src = self.work / "sketch.gpp"

    def gpp(self, command, *args):
        return subprocess.run([GPP, command, self.src, *args], capture_output=True, text=True, timeout=30)

    def module(self, declarations):
        self.src.write_text("module evalcase;\n" + declarations + "\npub fn main() -> I64 !{} {return 0;}\n")

    def test_hole_type_enforced_even_if_expression_is_discarded(self):
        self.module("fn unused(x: I64) -> Bool !{} { ?v: Bool; return true; }\ncontract ok(){unused(1)}")
        patch = self.work / "patch"
        patch.write_text("x")
        p = self.gpp("complete", "--hole", "v", "--fill", patch, "--stdout")
        self.assertEqual(p.returncode, 1, p.stderr)
        self.assertEqual(p.stdout, "")
        self.assertIn("Bool", json.loads(p.stderr)["diagnostic"])
        patch.write_text("x == 0")
        self.assertEqual(self.gpp("complete", "--hole", "v", "--fill", patch).returncode, 0)

    def test_ambiguous_pair_has_a_concrete_disagreement(self):
        self.module("fn pick(x: I64) -> I64 !{} {return ?which: I64;}\ncontract zero(){pick(0)==0}")
        p = self.gpp("complete", "--hole", "which", "--stdout")
        self.assertEqual(p.returncode, 3, p.stderr)
        self.assertFalse(p.stdout)
        report = json.loads(p.stderr)
        self.assertEqual(report["status"], "ambiguous")
        self.assertIsInstance(report["first_passing"], str)
        q = report["question"]
        self.assertNotEqual(q["inputs"]["x"], 0)
        self.assertNotEqual(q["alternatives"][0]["outcome"], q["alternatives"][1]["outcome"])
        self.assertIn("?which", self.src.read_text())

    def test_a_resource_limited_first_candidate_cannot_hide_two_concrete_answers(self):
        self.module("""
fn spin() -> I64 !{} { return spin(); }
fn pick(x:I64) -> I64 !{} {
    let a=?h: I64;
    if x==0 { return 0; }
    if a==x { return spin(); }
    return a;
}
contract public_case() { pick(0)==0 }
""")
        p = self.gpp("complete", "--hole", "h", "--limit", "5")
        self.assertEqual(p.returncode, 3)
        report = json.loads(p.stdout)
        self.assertEqual(report["status"], "ambiguous")
        a, b = report["question"]["alternatives"]
        self.assertNotEqual(a["outcome"]["result"], b["outcome"]["result"])

    def test_guidance_infers_two_integer_coefficients_under_the_same_candidate_cap(self):
        self.module("""
fn adjust(x:I64,y:I64)->I64 !{} { return ?v:I64; }
contract measured(x:I64 in -2..=2,y:I64 in -2..=2){adjust(x,y)==7*x+3*y-4}
""")
        args = ("--hole", "v", "--limit", "32")
        grammar = json.loads(self.gpp("complete", *args, "--search", "grammar").stdout)
        self.assertEqual(grammar["status"], "incomplete")
        self.assertEqual(grammar["guidance"]["contract_runs"], 0)
        p = self.gpp("complete", *args)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        report = json.loads(p.stdout)
        self.assertEqual(report["verification"]["checked"], 25)
        self.assertEqual(report["guidance"]["examples"], 25)
        self.assertGreater(report["guidance"]["proposals"], 0)
        self.assertLessEqual(report["tested"], 32)
        completed = self.gpp("complete", *args, "--stdout").stdout
        self.src.write_text(completed + "\ncontract exclude_samples(){adjust(71,-13)==454}")
        self.assertEqual(self.gpp("verify").returncode, 0)

    def test_guidance_rechecks_public_constraints_outside_its_sample(self):
        self.module("""
fn adjust(x:I64)->I64 !{} { return ?v:I64; }
contract trend(x:I64 in 0..=49){adjust(x)==17*x+5}
contract incompatible(){adjust(40)==0}
""")
        r = self.gpp("complete", "--hole", "v", "--limit", "32", "--stdout")
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(r.stdout)
        report = json.loads(r.stderr)
        self.assertGreater(report["guidance"]["contract_runs"], 0)
        self.assertEqual(report["passing_candidates_seen"], 0)

    def test_minimum_mode_reports_longer_disagreement_and_abstains_on_equal_cost(self):
        self.module("""
fn pick(x:I64,y:I64)->I64 !{} {return ?v:I64;}
contract origin(){pick(0,0)==0}
contract unit(){pick(1,1)==1}
""")
        p = self.gpp("complete", "--hole", "v", "--search", "minimum", "--limit", "48", "--stdout")
        self.assertEqual(p.returncode, 3, p.stderr)
        self.assertFalse(p.stdout)
        row = json.loads(p.stderr)
        self.assertEqual(row["selection"]["cost"], 1)
        self.assertEqual(row["status"], "ambiguous")
        self.assertEqual({a["expression"] for a in row["question"]["alternatives"]}, {"x", "y"})

        with self.src.open("a") as out:
            out.write("contract off_diagonal(){pick(1,2)==1}")
        p = self.gpp("complete", "--hole", "v", "--search", "minimum", "--limit", "48")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        row = json.loads(p.stdout)
        self.assertEqual(row["selected"], "x")
        self.assertEqual(row["selection"]["cost"], 1)
        self.assertGreater(row["selection"]["longer_passing"], 0)
        self.assertIsNotNone(row["selection"]["longer_disagreement"])
        self.assertEqual(row["verification"]["checked"], 3)

    def test_no_contract_budget_and_multiple_holes(self):
        self.module("fn pick(x: I64) -> I64 !{} {return ?v: I64;}")
        p = self.gpp("complete", "--hole", "v")
        self.assertEqual(json.loads(p.stdout)["reason"], "no_contracts")
        with self.src.open("a") as out:
            out.write("contract all(x: I64 in 0..=2){pick(x) == x}")
        p = self.gpp("complete", "--hole", "v", "--budget", "0")
        self.assertEqual(p.returncode, 3, p.stderr)
        self.assertEqual(json.loads(p.stdout)["status"], "incomplete")
        self.module("fn pick(x: I64) -> I64 !{} {return ?v: I64 + ?w: I64;}")
        self.assertEqual(self.gpp("complete", "--hole", "v").returncode, 2)

    @unittest.skipUnless(shutil.which("z3"), "requires the optional Z3 executable")
    def test_symbolic_full_width_witness_and_faults(self):
        self.module("""
fn ignore(x: I64) -> Bool !{} { return true; }
fn literal_branch(x: I64) -> I64 !{} { if true { return x; } }
contract lazy(x: I64 in -9223372036854775808..=9223372036854775807) {
    x == -9223372036854775808 || x + 0 == x
}
contract overflow(x: I64 in -9223372036854775808..=9223372036854775807) { ignore(x + 1) }
contract eager(x: I64 in -2..=2) { ignore(1 / x) }
contract remainder(){-9223372036854775808 % -1 == 0}
contract branch(){false && 1 / 0 == 0 || true}
contract guaranteed(x: I64 in -9223372036854775808..=9223372036854775807){literal_branch(x)==x}
""")
        for name in ["lazy", "remainder", "branch", "guaranteed"]:
            p = self.gpp("prove", "--contract", name)
            self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        for name, x, fault in [("overflow", 2**63-1, "IntegerOverflow"), ("eager", 0, "DivisionByZero")]:
            row = json.loads(self.gpp("prove", "--contract", name).stdout)["contracts"][0]
            self.assertEqual(row["status"], "refuted")
            self.assertEqual(row["counterexample"], {"inputs": {"x": x}, "fault": fault})

    @unittest.skipUnless(shutil.which("z3"), "requires the optional Z3 executable")
    def test_symbolic_agrees_with_enumeration_on_eager_lazy_and_aggregate_code(self):
        helper = """
enum State { Open, Closed }
record Reply { state: State, count: I64 }
fn choose(x: I64, b: Bool) -> Reply !{} {
    if b { return Reply(State::Open, x); } return Reply(State::Closed, -x);
}
fn exact(x: I64) -> Bool !{} { let hidden = clamp(0, x, 1); return true; }
"""
        for predicate in [
            "choose(x, b) == choose(x, b)",
            "choose(x, b).count == x",
            "choose(x, b).state == (if b {State::Open} else {State::Closed})",
            "x == 0 || (x / x == 1 && x % x == 0)",
            "exact(x)", "x < 2 || !b",
            "(x * x) >= 0 && min(x, 0) + max(x, 0) == x",
            "x <= 1 || 9223372036854775807 + x > 0",
        ]:
            with self.subTest(predicate=predicate):
                self.module(helper + "\ncontract c(x: I64 in -3..=3,b: Bool) {" + predicate + "}")
                finite = self.gpp("verify")
                proof = self.gpp("prove")
                self.assertIn(finite.returncode, [0, 1], finite.stderr)
                self.assertEqual(proof.returncode, finite.returncode, proof.stderr + proof.stdout)
                self.assertEqual(json.loads(proof.stdout)["status"], "proved" if finite.returncode == 0 else "refuted")

    def test_solver_unsupported_loop_and_missing_program(self):
        self.module("fn count() -> I64 !{} {var i=0; while i < 3 {i+=1;} return i;}\ncontract c(){count()==3}")
        p = self.gpp("prove")
        self.assertEqual(p.returncode, 3)
        self.assertEqual(json.loads(p.stdout)["status"], "unsupported")
