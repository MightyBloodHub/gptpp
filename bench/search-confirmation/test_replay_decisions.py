"""Run from the repository root with python3 -B bench/search-confirmation/test_replay_decisions.py."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from confirm import HERE, ROOT, corpus, engine, followup, native, study
from replay_decisions import replay


class ArchivedRegression(unittest.TestCase):
    def test_routing(self):
        report = replay()
        self.assertEqual(report["new_model_calls"], 0)
        self.assertEqual(report["counts"], {
            "piecewise": {"correct": 4, "wrong": 3, "abstained": 4},
            "qwen": {"correct": 7, "wrong": 0, "abstained": 4},
            "piecewise_then_qwen": {"correct": 5, "wrong": 3, "abstained": 3},
        })
        rows = report["decisions"]
        self.assertEqual(len(rows), 11)
        self.assertEqual([r["task"] for r in rows if r["qwen"] != r["piecewise_then_qwen"]],
                         ["makes10", "nearHundred", "posNeg"])
        self.assertEqual([r["task"] for r in rows if r["piecewise"] != r["piecewise_then_qwen"]],
                         ["more20"])
        self.assertEqual(report["archived_model_usage"]["piecewise_then_qwen"],
                         {"calls": 4, "input_tokens": 1487, "output_tokens": 121})

    def test_current_compiler_on_all_eleven(self):
        # Regression data only. None of these inputs belong in fresh qualification.
        captured = {r["task"]: r for r in json.loads((HERE / "preflight.json").read_text())
                    if r["language"] == "gpp"}
        compiler = ROOT / "target/release/gpp"
        with TemporaryDirectory() as tmp:
            for task in corpus.TASKS:
                with self.subTest(task=task.name):
                    program = native.Program(task, "gpp", Path(tmp) / task.name, compiler)
                    for expr, correct in [(task.old, False), (task.reference, True)]:
                        fragment = engine.render(followup.reference_tree(expr), "gpp")
                        checked = study.check(program, fragment, trusted=True)
                        self.assertIs(checked["accepted"], correct)
                        if correct:
                            self.assertEqual(checked["score"], captured[task.name]["reference"])


if __name__ == "__main__":
    unittest.main()
