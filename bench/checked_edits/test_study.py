"""Regression checks for the paired collector. Uses only public assignments and a recorded-response stub."""

from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import study


def generator(responses):
    replies = iter(responses)

    def generate(port, endpoint, payload):
        assert endpoint == "generate"
        return dict(done=True, response=json.dumps({"expression": next(replies)}),
                    prompt_eval_count=10, eval_count=3, done_reason="stop")
    return generate


def alternatives(inputs, expressions, values):
    return dict(status="ambiguous", question={
        "inputs": inputs,
        "alternatives": [dict(expression=e, outcome={"result": v})
                         for e, v in zip(expressions, values, strict=True)],
    })


class PairedCollector(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.work = Path(tmp.name)
        self.tasks = {task.name: task for task in study.TASKS}

    def run_cell(self, task, arm, replies=()):
        output = StringIO()
        with patch.object(study, "ollama", side_effect=generator(replies)):
            result = study.trial(task, "gpp", arm, self.work, output, 0)
        calls = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(result["model_calls"], len(calls))
        self.assertEqual(result["input_tokens"], 10 * len(calls))
        self.assertEqual(result["output_tokens"], 3 * len(calls))
        return result, [call["prompt"]["prompt"] for call in calls]

    def test_direct_controls_share_the_first_prompt_and_differ_only_in_retry_feedback(self):
        task = self.tasks["seal_press"]
        first = {}
        for arm in ("direct", "direct_retry", "direct_witness"):
            with self.subTest(arm=arm):
                result, prompts = self.run_cell(task, arm, [task.previous, task.reference])
                first[arm] = prompts[0]
                self.assertFalse(result["first_pass"])
                self.assertEqual(result["candidates"][0]["reason"], "contract_counterexample")
                if arm == "direct":
                    self.assertEqual((result["decision"], len(prompts)), ("abstain", 1))
                else:
                    self.assertEqual((result["decision"], len(prompts)), ("accept", 2))
                    self.assertEqual(prompts[1].splitlines()[-2], task.previous)
                    if arm == "direct_witness":
                        witness = json.loads(prompts[1].splitlines()[-1])
                        self.assertEqual(witness, dict(input={"phase": 0, "key": 2}, observed=2,
                                                       violated_rule=task.request))
                    else:
                        self.assertNotIn('"observed"', prompts[1])
        self.assertEqual(len(set(first.values())), 1)

    def test_compiler_witness_refers_to_the_expression_that_failed(self):
        task = self.tasks["seal_press"]
        found = alternatives({"phase": 2, "key": 1}, [task.previous, "0"], [1, 0])
        with patch.object(study.acceptance, "search", return_value=found):
            result, prompts = self.run_cell(task, "workflow", [task.reference])
        self.assertEqual([r["decision"] for r in result["candidates"]], ["reject", "reject", "accept"])
        self.assertEqual(len(prompts), 1)
        self.assertEqual(prompts[0].splitlines()[-2], task.previous)
        self.assertEqual(json.loads(prompts[0].splitlines()[-1])["observed"], 2)

    def test_compiler_only_abstains_on_an_unsettled_question_without_external_calls(self):
        task = self.tasks["weighbridge"]
        other = "if gross == 7 { 0 } else { gross - tare }"
        found = alternatives({"gross": 7, "tare": 0}, [task.reference, other], [7, 0])
        with patch.object(study.acceptance, "search", return_value=found):
            result, prompts = self.run_cell(task, "search")
        self.assertEqual(prompts, [])
        self.assertEqual(result["decision"], "abstain")
        self.assertEqual([r["decision"] for r in result["candidates"]], ["accept", "accept"])
        self.assertEqual(result["question"]["calls"], 0)
        self.assertEqual(result["question"]["labels"], 0)

    def test_workflow_skips_generation_only_after_public_acceptance(self):
        task = self.tasks["weighbridge"]
        found = dict(status="verified", selected=task.reference)
        with patch.object(study.acceptance, "search", return_value=found):
            result, prompts = self.run_cell(task, "workflow")
        self.assertEqual(prompts, [])
        self.assertTrue(result["first_pass"])
        self.assertEqual(result["decision"], "accept")
        accepted, = result["candidates"]
        self.assertEqual(accepted["public_examples"]["status"], "passed")
        self.assertEqual(accepted["obligations"][0]["status"], "passed")

    def test_malformed_reply_is_charged_and_missing_usage_has_an_incomplete_receipt(self):
        task = self.tasks["weighbridge"]
        for reply in [dict(done=True, response="invalid json", prompt_eval_count=11, eval_count=4),
                      dict(done=True, response="{}")]:
            with self.subTest(reply=reply):
                output = StringIO()
                with patch.object(study, "ollama", return_value=reply):
                    if "eval_count" in reply:
                        row = study.trial(task, "gpp", "direct", self.work, output, 0)
                        self.assertEqual((row["decision"], row["input_tokens"], row["output_tokens"]),
                                         ("abstain", 11, 4))
                    else:
                        with self.assertRaises(RuntimeError):
                            study.trial(task, "gpp", "direct", self.work, output, 0)
                        call = json.loads(output.getvalue())
                        self.assertEqual(call["kind"], "unmetered_call")
                        self.assertIsNone(call["input_tokens"])
                        self.assertIsNone(call["output_tokens"])

    def test_preflight_checks_reference_and_mutant_against_the_obligation_itself(self):
        rows = study.preflight(self.work)
        self.assertEqual({row["task"] for row in rows}, set(self.tasks))
        for row in rows:
            with self.subTest(task=row["task"]):
                reference, mutant = row["reference"], row["mutant"]
                self.assertEqual(reference["obligations"][0]["status"], "passed")
                self.assertEqual(mutant["public_examples"]["status"], "passed")
                self.assertEqual(mutant["reason"], "contract_counterexample")
                self.assertEqual(mutant["obligations"][0]["status"], "counterexample")
                self.assertEqual(row["public_assignments"],
                                 len(list(study.points(self.tasks[row["task"]]))))


if __name__ == "__main__":
    unittest.main()
