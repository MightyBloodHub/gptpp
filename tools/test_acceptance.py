"""Exercise the opt-in evidence ledger and its budgets using the shipped compiler."""
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import acceptance
from test_propose import GPP


DEV = Path(__file__).resolve().parents[1] / "examples/makes10"
OLD = "(((b + a) == 10) || (b == 10))"
RULE = [{"name": "symmetric", "mode": "finite", "declaration":
         "contract symmetric(a:I64 in -5..=18,b:I64 in -5..=18) {transition(a,b)==transition(b,a)}",
         "rule": "Swap the two arguments without changing the answer."}]


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        work = TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.sketch = Path(work.name) / "public.gpp"
        self.sketch.write_bytes((DEV / "public.gpp").read_bytes())

    def check(self, expression, contracts=RULE, **opts):
        return acceptance.check_candidate(GPP, self.sketch, expression, "test", contracts, **opts)

    def test_examples_are_distinct_from_acceptance_and_replayed_observations(self):
        result = self.check(OLD)
        self.assertEqual(result["public_examples"]["checked"], 24)
        self.assertEqual(result["public_examples"]["status"], "passed")
        self.assertEqual(result["decision"], "reject")
        self.assertEqual(result["obligations"][0]["domain"], "a:I64 in -5..=18,b:I64 in -5..=18")
        feedback = result["feedback"]
        self.assertEqual(feedback["replay"]["probe"], {"result": False})
        self.assertEqual(feedback["observed"], [
            {"locals": {"a": -5, "b": 10}, "value": True},
            {"locals": {"a": 10, "b": -5}, "value": False},
        ])
        self.assertEqual(feedback["edit_site"]["previous"], OLD)
        self.assertEqual(self.check(OLD, [])["decision"], "abstain")
        weak = self.check(OLD, json.loads((DEV / "weak.json").read_text()))
        self.assertEqual(weak["decision"], "accept")
        self.assertEqual(weak["obligations"][0]["checked"], 24)
        self.assertIn("unconstrained", weak["obligations"][0]["limitation"])

    @unittest.skipUnless(shutil.which("z3"), "optional symbolic verifier")
    def test_exact_rule_controls_and_proof_replay(self):
        contracts = json.loads((DEV / "contracts.json").read_text())
        good = self.check("a == 10 || b == 10 || a+b == 10", contracts)
        self.assertEqual(good["decision"], "accept")
        self.assertEqual([c["status"] for c in good["obligations"]], ["passed", "proved"])
        self.assertEqual(good["obligations"][0]["checked"], 576)
        wrong = self.check(OLD, contracts[1:])
        self.assertEqual(wrong["decision"], "reject")
        self.assertEqual(wrong["obligations"][0]["status"], "refuted")
        self.assertEqual(wrong["feedback"]["observed"][0]["value"], False)

    def test_type_example_and_obligation_failures_stay_distinct(self):
        wrong_type = self.check("a+b")
        self.assertEqual(wrong_type["decision"], "reject")
        self.assertEqual(wrong_type["public_examples"]["status"], "not_run")
        self.assertIn("diagnostic", wrong_type["feedback"])
        wrong_example = self.check("false")
        self.assertEqual(wrong_example["reason"], "public_example")
        self.assertEqual(wrong_example["feedback"]["args"], [])
        self.assertEqual(wrong_example["feedback"]["observed"][0]["locals"], {"a": 9, "b": 10})
        self.assertIn("transition(9, 10)", wrong_example["feedback"]["rule"])
        # First counterexample in this domain happens before the 24-case budget;
        # use the correct expression to test an unfinished proof.
        correct = self.check("a==10 || b==10 || a+b==10", budget=24)
        self.assertEqual(correct["obligations"][0]["status"], "incomplete")
        self.assertEqual(correct["obligations"][0]["checked"], 24)

    def test_timeout_and_unsupported_cannot_publish_or_request_a_repair(self):
        real = acceptance._compiler

        def timeout(binary, *args, **kwargs):
            if args[0] == "verify":
                raise subprocess.TimeoutExpired([str(binary), *args], 1)
            return real(binary, *args, **kwargs)

        with patch.object(acceptance, "_compiler", timeout):
            row = self.check(OLD)
        self.assertEqual((row["decision"], row["obligations"][0]["status"]), ("abstain", "timeout"))
        c = dict(RULE[0], mode="prove", declaration="""
fn loops() -> I64 !{} { var i=0; while i<3 {i+=1;} return i; }
contract symmetric() { loops()==3 }""")
        row = self.check(OLD, [c])
        self.assertEqual((row["decision"], row["obligations"][0]["status"]), ("abstain", "unsupported"))
        self.assertIsNone(row["feedback"])

    def test_contract_only_slot_needs_no_example_labels(self):
        source = self.sketch.read_text().split("contract sample_0")[0]
        self.sketch.write_text(source)
        rule = [dict(RULE[0], declaration="contract symmetric(a:I64 in 0..=2) {transition(a,a)}")]
        row = self.check("true", rule)
        self.assertEqual(row["decision"], "accept")
        self.assertEqual(row["public_examples"], {"status": "not_provided", "checked": 0, "contracts": []})
        self.assertEqual(row["obligations"][0]["checked"], 3)
        self.assertEqual(self.check("false", rule)["feedback"]["observed"][0]["value"], False)
        self.assertEqual(self.check("a", rule)["decision"], "reject")
        self.assertEqual(self.check("true", [])["decision"], "abstain")
        outcome = acceptance.run_workflow(GPP, self.sketch, rule, lambda feedback: "true")
        self.assertEqual((outcome["decision"], outcome["model_calls"]), ("accept", 1))

    def test_malformed_runtime_observations_abstain(self):
        run = acceptance._compiler

        def malformed(binary, *args, **kwargs):
            proc = run(binary, *args, **kwargs)
            if args[0] == "trace":
                row = json.loads(proc.stdout)
                for e in row["expressions"]:
                    e["observations"] = [{}]
                proc.stdout = json.dumps(row).encode()
            return proc

        with patch.object(acceptance, "_compiler", malformed):
            r = self.check(OLD)
        self.assertEqual((r["decision"], r["reason"]), ("abstain", "tool_error"))
        self.assertIsNone(r["feedback"])

    def test_checked_question_and_authorized_answer(self):
        self.sketch.write_text("""module q;
fn pick(x:I64,y:I64)->I64 !{} {return ?change:I64;}
pub fn main()->I64 !{} {return 0;}
contract origin(){pick(0,0)==0}
contract unit(){pick(1,1)==1}""")
        contract = [{"name": "diagonal", "mode": "finite", "rule": "Preserve equal inputs.",
                     "declaration": "contract diagonal(v:I64 in 0..=5){pick(v,v)==v}"}]
        found = acceptance.search(GPP, self.sketch, limit=48)
        self.assertEqual(found["status"], "ambiguous")

        def check(expr, source):
            return acceptance.check_candidate(GPP, self.sketch, expr, source, contract)

        no_model = lambda _: self.fail("ambiguity must not spend a model call")
        unknown = acceptance.run_policy(found, check, no_model)
        self.assertEqual(unknown["decision"], "abstain")
        self.assertEqual(unknown["question"]["calls"], 0)
        self.assertEqual(unknown["model_calls"], 0)
        def too_slow(inputs):
            raise TimeoutError("reference exceeded its deadline")

        timeout = acceptance.run_policy(found, check, no_model, authority={"source": "test", "answer": too_slow})
        self.assertEqual(timeout["decision"], "abstain")
        self.assertEqual(timeout["question"]["calls"], 1)
        self.assertEqual(timeout["question"]["labels"], 0)
        self.assertEqual(timeout["question"]["reason"], "source_timeout")
        source = self.sketch.with_name("reference.gpp")
        source.write_text(self.sketch.read_text().replace("?change:I64", "x"))
        answer = acceptance.public_reference(GPP, source, "pick")
        labeled = acceptance.run_policy(found, check, no_model, authority=answer)
        self.assertEqual(labeled["decision"], "accept")
        self.assertEqual(labeled["selected"], "x")
        self.assertEqual(labeled["question"]["calls"], 1)
        self.assertEqual(labeled["question"]["labels"], 1)
        self.assertIn("sha256:", labeled["question"]["source"])
        self.assertEqual(labeled["question"]["answer"], found["question"]["inputs"]["x"])

    def test_budget_for_a_failed_suggestion_and_unsolved_search(self):
        calls = []

        def answer(feedback):
            calls.append(feedback)
            return OLD

        run = acceptance.run_policy({"status": "rejected"}, lambda expr, _: self.check(expr), answer)
        self.assertEqual(run["decision"], "abstain")
        self.assertEqual(run["model_calls"], 2)
        self.assertIsNone(calls[0])
        self.assertIn("observed", calls[1])
        self.assertFalse(run["first_pass"])
        good = lambda _: "a==10 || b==10 || a+b==10"
        repaired = acceptance.run_policy({"status": "verified", "selected": OLD},
                                         lambda expr, _: self.check(expr), good)
        self.assertEqual(repaired["model_calls"], 1)
        self.assertEqual(repaired["decision"], "accept")
        self.assertFalse(repaired["first_pass"])
        only = acceptance.run_policy({"status": "verified", "selected": OLD},
                                     lambda expr, _: self.check(expr), None)
        self.assertEqual((only["decision"], only["model_calls"]), ("abstain", 0))


if __name__ == "__main__":
    unittest.main()
