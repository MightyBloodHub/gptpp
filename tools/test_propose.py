"""Exercise the actual CLI and compiler against a deterministic loopback Ollama stub."""

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest


HERE = Path(__file__).resolve().parent
GPP = HERE.parent / "target/debug/gpp"
SOURCE = """module demo;
fn offset() -> I64 !{} { return 123456; }
fn target(x: I64) -> I64 !{} {
    // original comment with a }
    return x;
}
pub fn main() -> I64 !{} { return target(4); }
"""


@contextmanager
def mock_ollama(completions=(), *, remote=False, infill=False, parameters=None, on_generate=None,
                model_name="mock:latest", digest=None):
    calls = []
    replies = iter(completions)

    class Handler(BaseHTTPRequestHandler):
        def send_json(self, value):
            body = json.dumps(value).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            calls.append((self.path, None))
            if self.path != "/api/tags":
                self.send_error(404)
                return
            self.send_json({"models": [{"name": model_name, "digest": digest}]})

        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append((self.path, request))
            if self.path == "/api/show":
                info = {"template": "{{ .Prompt }}\n{{ .Response }}"}
                if parameters is not None:
                    info["parameters"] = parameters
                if infill:
                    info["template"] = "{{ if .Suffix }}{{ .Prompt }}{{ .Suffix }}{{ else }}{{ .Response }}{{ end }}"
                if remote:
                    info["remote_host"] = "test.invalid"
                self.send_json(info)
            elif self.path == "/api/generate":
                if on_generate:
                    on_generate()
                self.send_json({"done": True, "response": next(replies, "")})
            else:
                self.send_error(404)

        def log_message(self, *_):
            pass

    with HTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
        thread.start()
        try:
            yield server.server_port, calls
        finally:
            server.shutdown()
            thread.join()


class ProposeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="gpp proposal ")
        self.addCleanup(self.tmp.cleanup)
        self.file = Path(self.tmp.name) / "example code.gpp"
        self.file.write_text(SOURCE)
        self.output = Path(self.tmp.name) / "proposed fragment"
        self.cases = Path(self.tmp.name) / "examples.json"

    def invoke(self, port, form="expr", *options, model="mock"):
        model_flag = ["--model", model] if model else []
        return subprocess.run([sys.executable, "-B", HERE / "propose.py", self.file, *model_flag,
                               "--function", "target", "--task", "Return x plus one.", "--" + form,
                               "-o", self.output, "--port", str(port), "--gpp", GPP, *options],
                              capture_output=True, text=True, timeout=15)

    def test_preview_and_explicit_revision_guarded_apply(self):
        with mock_ollama(["x + 1;\n}"]) as (port, calls):
            result = self.invoke(port)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.file.read_text(), SOURCE)
        self.assertEqual(self.output.read_text(), "x + 1\n")
        self.assertIn("+    return x + 1;", result.stdout)
        base = subprocess.check_output([GPP, "revision", self.file], text=True).strip()
        self.assertIn("Base revision: " + base, result.stdout)
        request = calls[-1][1]
        self.assertIn("fn target(x: I64) -> I64 !{} {\n    return ", request["template"])
        self.assertIn("fn offset() -> I64 !{}", request["prompt"])
        self.assertNotIn("123456", request["prompt"])  # neighboring body
        self.assertNotIn("original comment", request["prompt"])
        subprocess.run([GPP, "edit", self.file, "--function", "target", "--expr", self.output,
                        "--expect", base], check=True)
        self.assertEqual(subprocess.check_output([GPP, "run", "--interpreter", self.file]), b"5\n")

    def test_body_repair_gets_compiler_diagnostic(self):
        with mock_ollama(["return true;\n}", "return x + 1;\n} // close"]) as (port, calls):
            result = self.invoke(port, "body")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.file.read_text(), SOURCE)
        requests = [payload for path, payload in calls if path == "/api/generate"]
        self.assertEqual(len(requests), 2)
        self.assertIn("GPP-TYPE", requests[1]["prompt"])
        self.assertTrue(self.output.read_text().startswith("return x + 1;"))

    def test_scope_escape_rejected_and_no_output_published(self):
        bad = "0; } fn injected() -> I64 !{} { return 10; }"
        with mock_ollama([bad, bad]) as (port, _):
            result = self.invoke(port)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.file.read_text(), SOURCE)

    def test_native_infill_uses_literal_source_and_protected_suffix(self):
        with mock_ollama(["x+1"], infill=True) as (port, calls):
            result = self.invoke(port, "expr", "--infill")
        self.assertEqual(result.returncode, 0, result.stderr)
        request = calls[-1][1]
        self.assertTrue(request["prompt"].endswith("fn target(x: I64) -> I64 !{} {\n    return "))
        self.assertIn("// Current GPT++ implementation:", request["prompt"])
        self.assertEqual(request["suffix"], ";\n}\n")
        self.assertNotIn("template", request)
        self.assertNotIn("system", request)
        self.assertNotIn("stop", request["options"])
        self.assertEqual(self.output.read_text(), "x + 1\n")

    def test_maintenance_native_full_body_and_one_caller_retry(self):
        self.cases.write_text('[{"function":"main","args":[],"expected":5},{"args":[-2],"expected":-1}]')
        with mock_ollama(["return x;", "return x + 1;"], infill=True, parameters='stop "<end>"',
                         model_name="qwen2.5-coder:7b") as (port, calls):
            result = self.invoke(port, "maintenance", "--cases", self.cases, model=None)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.file.read_text(), SOURCE)
        self.assertEqual(self.output.read_text(), "return x + 1;\n")
        requests = [r for endpoint, r in calls if endpoint == "/api/generate"]
        self.assertEqual(len(requests), 2)
        first, retry = requests
        self.assertEqual(first["prompt"],
                         "// Return x plus one.\n// Examples\n// main() = 5\n// target(-2) = -1\n"
                         "// Replace the current body\n// return x;\n"
                         "// GPT++ uses if flag { return value; }, let for constants and var for mutable locals.\n"
                         "fn target(x: I64) -> I64 !{} {\n    ")
        self.assertIn("// Previous insertion\n// return x;\n// main() returned 4. Expected 5.", retry["prompt"])
        self.assertIn("pub fn main()", retry["prompt"])
        self.assertLess(retry["prompt"].index("Read-only caller excerpts"), retry["prompt"].index("Replace the current body"))
        for i, r in enumerate(requests):
            self.assertEqual(r["model"], "qwen2.5-coder:7b")
            self.assertEqual(r["suffix"], "\n}\n")
            self.assertEqual(r["keep_alive"], "3m")
            self.assertEqual(r["options"], dict(seed=42+i, temperature=0 if not i else 0.25,
                                                num_predict=240, num_ctx=2048, stop=["<end>", "\n}"]))

    def test_maintenance_target_and_check_failures_end_after_one_call(self):
        for candidate, row in [("return x;", {"args": [1], "expected": 2}),
                               ("return true;", {"function": "main", "args": [], "expected": 5}),
                               ("return x;", {"function": "offset", "args": [], "expected": 1})]:
            with self.subTest(row=row), mock_ollama([candidate], infill=True) as (port, calls):
                self.cases.write_text(json.dumps([row]))
                result = self.invoke(port, "maintenance", "--cases", self.cases)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(sum(endpoint == "/api/generate" for endpoint, _ in calls), 1)
                self.assertFalse(self.output.exists())

    def test_maintenance_validates_setup_and_provides_model_hint(self):
        with mock_ollama() as (port, calls):
            missing = self.invoke(port, "maintenance")
            self.assertIn("--maintenance requires --cases", missing.stderr)
            exclusive = self.invoke(port, "expr", "--maintenance", "--cases", self.cases)
            self.assertIn("not allowed with argument", exclusive.stderr)
            self.assertFalse(calls)
            self.cases.write_text('[{"args":[1],"expected":2}]')
            uninstalled = self.invoke(port, "maintenance", "--cases", self.cases, model=None)
            self.assertIn("ollama pull qwen2.5-coder:7b", uninstalled.stderr)
            no_fim = self.invoke(port, "maintenance", "--cases", self.cases)
            self.assertIn("no .Suffix infill template", no_fim.stderr)
            self.assertIn("qwen2.5-coder:7b", no_fim.stderr)
            self.assertFalse(any(endpoint == "/api/generate" for endpoint, _ in calls))

    def test_maintenance_starcoder_raw_transport_uses_verified_digest(self):
        self.cases.write_text('[{"args":[3],"expected":4}]')
        model = "starcoder2:3b"
        digest = "f67ae0f64584a4d1d7c609bf4778dd0d07054582362d21ca4f0eddea22aafd0c"
        with mock_ollama(["return x + 1;"], model_name=model, digest=digest) as (port, calls):
            result = self.invoke(port, "maintenance", "--cases", self.cases, model=model)
        self.assertEqual(result.returncode, 0, result.stderr)
        request = calls[-1][1]
        self.assertTrue(request["raw"])
        self.assertTrue(request["prompt"].startswith("<fim_prefix>// Return x plus one."))
        self.assertTrue(request["prompt"].endswith("    <fim_suffix>\n}\n<fim_middle>"))
        self.assertNotIn("suffix", request)
        self.assertEqual(request["options"]["stop"], ["<file_sep>", "<fim_prefix>", "<fim_suffix>",
                                                    "<fim_middle>", "<|endoftext|>", "\n}"])
        self.output.unlink()
        with mock_ollama(model_name=model, digest="unrecognized") as (port, calls):
            result = self.invoke(port, "maintenance", "--cases", self.cases, model=model)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(endpoint == "/api/generate" for endpoint, _ in calls))

    def test_maintenance_prepend_protects_body_and_checks_changes_and_preservation(self):
        self.cases.write_text('[{"function":"main","args":[],"expected":5},{"args":[77],"expected":77}]')
        with mock_ollama(["if x == 4 { return x + 1; }"], infill=True) as (port, calls):
            result = self.invoke(port, "maintenance", "--prepend", "--cases", self.cases)
        self.assertEqual(result.returncode, 0, result.stderr)
        request = calls[-1][1]
        self.assertIn("Insert early returns for changed cases above the existing body.", request["prompt"])
        self.assertNotIn("return x;", request["prompt"])
        self.assertEqual(request["suffix"], "\n    return x;\n}\n")
        self.assertEqual(self.output.read_text(), "if x == 4 {\n    return x + 1;\n}\nreturn x;\n")
        self.output.unlink()
        with mock_ollama(["return 5; } fn escape() -> I64 !{} { return 0; }"], infill=True) as (port, calls):
            result = self.invoke(port, "maintenance", "--prepend", "--cases", self.cases)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.file.read_text(), SOURCE)
        self.assertEqual(sum(p == "/api/generate" for p, _ in calls), 1)
        self.file.write_text(SOURCE.replace("return x;", "if x == 4 { return 4; } return x;"))
        self.cases.write_text('[{"args":[4],"expected":4}]')
        with mock_ollama(["if x == 99 { return 99; } else"], infill=True) as (port, calls):
            result = self.invoke(port, "maintenance", "--prepend", "--cases", self.cases)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("protected original statement boundary", result.stderr)
        self.assertFalse(self.output.exists())

    def test_boundary_stops_merge_with_defaults_on_both_attempts(self):
        self.cases.write_text('[{"args":[2],"expected":3}]')
        combinations = [
            ("gpp", ["\n}"]),
            ("python", ["\ndef ", "\nclass ", "\nimport ", "\nfrom ", "\nassert ", "\nprint(", "\nif __name__", "\n@"]),
        ]
        for surface, stops in combinations:
            with self.subTest(surface=surface):
                params = "\n".join(["temperature 0.2", "stop " + json.dumps("<end>"),
                                    "stop " + json.dumps(stops[0]), "stop " + json.dumps("<end>")])
                with mock_ollama(["x", "x + 1"], infill=True, parameters=params) as (port, calls):
                    result = self.invoke(port, "expr", "--infill", "--surface", surface,
                                         "--stop-at-boundary", "--cases", self.cases)
                self.assertEqual(result.returncode, 0, result.stderr)
                requests = [r for endpoint, r in calls if endpoint == "/api/generate"]
                self.assertEqual(len(requests), 2)
                self.assertTrue(all(r["options"]["stop"] == ["<end>", *stops] for r in requests))
                self.assertIn("target(x=2) returned 2", requests[1]["prompt"])
                self.output.unlink()

    def test_boundary_stops_do_not_discard_invalid_generated_code(self):
        for surface, raw in [("gpp", "x;\n}\nfn other() -> I64 !{} { return 1; }"),
                             ("python", "x\ndef other(): return 1")]:
            with self.subTest(surface=surface), mock_ollama([raw, raw], infill=True) as (port, _):
                result = self.invoke(port, "expr", "--infill", "--surface", surface, "--stop-at-boundary")
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.output.exists())
        with mock_ollama() as (port, calls):
            result = self.invoke(port, "expr", "--stop-at-boundary")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("requires --infill", result.stderr)
            self.assertFalse(calls)

    def test_projected_infill_preserves_signature_and_checked_integer_semantics(self):
        self.file.write_text("""module demo;
fn target(x: I64, flag: Bool) -> I64 !{} { return x; }
pub fn main() -> I64 !{} { return target(-5, true); }
""")
        original = self.file.read_bytes()
        with mock_ollama(["x // 2 if flag else -x"], infill=True) as (port, calls):
            result = self.invoke(port, "expr", "--infill", "--surface", "python")
        self.assertEqual(result.returncode, 0, result.stderr)
        request = calls[-1][1]
        self.assertTrue(request["prompt"].endswith("def target(x: int, flag: bool) -> int:\n    return "))
        self.assertIn("# fn target(x: I64, flag: Bool) -> I64 !{} {", request["prompt"])
        self.assertEqual(request["suffix"], "\n\n# End of function\n")
        self.assertNotIn("template", request)
        self.assertEqual(self.output.read_text(), "if flag { x / 2 } else { -x }\n")
        self.assertEqual(self.file.read_bytes(), original)
        candidate = subprocess.check_output([GPP, "edit", self.file, "--function", "target", "--expr",
                                             self.output, "--stdout"])
        preview = self.file.with_name("verify.gpp")
        preview.write_bytes(candidate)
        self.assertEqual(subprocess.check_output([GPP, "run", "--interpreter", preview]), b"-2\n")

    def test_projected_builtin_proposal_checks_public_cases(self):
        self.cases.write_text('[{"args":[4],"expected":1},{"args":[-1],"expected":0}]')
        with mock_ollama(["min(abs(x - 3), max(x, 0))"], infill=True) as (port, calls):
            result = self.invoke(port, "expr", "--infill", "--surface", "python", "--cases", self.cases)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Passed 2 supplied cases", result.stdout)
        self.assertNotIn("abs(", self.output.read_text())
        self.assertIn("abs(x)", calls[-1][1]["prompt"])
        self.assertEqual(self.file.read_text(), SOURCE)

    def test_policy_infill_keeps_checked_fallback_and_publishes_only_native_body(self):
        self.cases.write_text('[{"args":[-3],"expected":3},{"args":[0],"expected":7},'
                              '{"function":"main","args":[],"expected":4}]')
        defaults = 'stop "<end>"\nstop "\\nelse"'
        with mock_ollama(["x < 0 => abs(x)\nwhen x == 0 => 7"], infill=True,
                         parameters=defaults) as (port, calls):
            result = self.invoke(port, "body", "--infill", "--surface", "policy", "--attempts", "1",
                                 "--cases", self.cases)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Passed 3 supplied cases", result.stdout)
        request = calls[-1][1]
        self.assertTrue(request["prompt"].endswith("\nwhen "))
        self.assertIn("# fn target(x: I64) -> I64", request["prompt"])
        self.assertIn("when <condition> => <value>", request["prompt"])
        self.assertNotIn("when amount", request["prompt"])
        self.assertNotIn("fn offset", request["prompt"])
        self.assertEqual(request["suffix"], "\nelse => @keep\n")
        self.assertEqual(request["options"]["stop"], ["<end>", "\nelse", "\n#", chr(96) * 3])
        self.assertNotIn("template", request)
        self.assertIn("if x == 0 {\n    return 7;", self.output.read_text())
        self.assertTrue(self.output.read_text().endswith("return x;\n"))
        self.assertEqual(self.file.read_text(), SOURCE)

    def test_policy_chat_supports_checked_bool_result_and_explicit_default(self):
        source = """module demo;
fn target(x: I64) -> Bool !{} { return false; }
pub fn main() -> I64 !{} { return if target(2) { 1 } else { 0 }; }
"""
        self.file.write_text(source)
        self.cases.write_text('[{"args":[2],"expected":true},{"args":[1],"expected":false}]')
        with mock_ollama(["when x == 2 => True\nelse => False"]) as (port, calls):
            result = self.invoke(port, "body", "--surface", "policy", "--cases", self.cases)
        self.assertEqual(result.returncode, 0, result.stderr)
        request = calls[-1][1]
        self.assertIn(chr(96) * 3 + "policy\n{{ .Response }}", request["template"])
        self.assertNotIn("suffix", request)
        self.assertIn("if x == 2 {\n    return true;", self.output.read_text())
        self.assertEqual(self.file.read_text(), source)

    def test_one_shot_rejects_policy_boundary_escape_without_saving_or_retrying(self):
        for completion in ["x != 0 => x\nelse => 999", "True => target(8)", "True => False"]:
            with self.subTest(completion=completion), mock_ollama([completion], infill=True) as (port, calls):
                result = self.invoke(port, "body", "--infill", "--surface", "policy", "--attempts", "1")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Completion failed validation", result.stderr)
                self.assertEqual(sum(path == "/api/generate" for path, _ in calls), 1)
                self.assertFalse(self.output.exists())
                self.assertEqual(self.file.read_text(), SOURCE)

    def test_policy_requires_body_and_scalar_signature_before_inference(self):
        with mock_ollama() as (port, calls):
            result = self.invoke(port, "expr", "--surface", "policy")
            self.assertIn("requires --body", result.stderr)
            self.file.write_text("module demo; fn target(x: Unit) -> I64 !{} { return 3; } "
                                 "pub fn main() -> I64 !{} { return 3; }")
            result = self.invoke(port, "body", "--surface", "policy")
            self.assertIn("Parameter x: Unit", result.stderr)
            self.assertFalse(calls)

    def test_caller_only_retry_uses_case_and_rejects_target_and_static_failures_on_first_attempt(self):
        options = ("--infill", "--surface", "policy", "--attempts", "caller", "--cases", self.cases)
        self.cases.write_text('[{"function":"main","args":[],"expected":5}]')
        with mock_ollama(["x == 8 => 9", "x == 4 => 5"], infill=True) as (port, calls):
            result = self.invoke(port, "body", *options)
        self.assertEqual(result.returncode, 0, result.stderr)
        prompts = [request["prompt"] for path, request in calls if path == "/api/generate"]
        self.assertEqual(len(prompts), 2)
        self.assertNotIn("fn main()", prompts[0])
        self.assertIn("fn main()", prompts[1])
        self.assertIn("main() returned 4; expected 5", prompts[1])
        self.output.unlink()
        for case, raw in [({"args": [4], "expected": 5}, "x == 8 => 9"),
                          ({"function": "offset", "args": [], "expected": 0}, "x == 4 => 5"),
                          ({"function": "main", "args": [], "expected": 5}, "x => x")]:
            with self.subTest(case=case, raw=raw), mock_ollama([raw], infill=True) as (port, calls):
                self.cases.write_text(json.dumps([case]))
                result = self.invoke(port, "body", *options)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(sum(path == "/api/generate" for path, _ in calls), 1)
                self.assertFalse(self.output.exists())
        self.assertEqual(self.file.read_text(), SOURCE)

    def test_retry_can_use_an_exact_caller_result_or_fall_back_to_excerpts(self):
        helper = Path(self.tmp.name) / "caller-obligation"
        subprocess.run(["rustc", "--edition=2024", HERE / "caller_obligation.rs", "-o", helper], check=True)
        self.cases.write_text('[{"function":"main","args":[],"expected":5}]')
        for body, exact in [("return target(4);", True),
                            ("if target(4) == 5 { return 5; } return 0;", False)]:
            self.file.write_text(SOURCE.replace("return target(4);", body))
            for form, completions in [("expr", ["x", "x + 1"]), ("maintenance", ["return x;", "return x + 1;"])]:
                with self.subTest(form=form, exact=exact), mock_ollama(completions, infill=True) as (port, calls):
                    result = self.invoke(port, form, "--infill", "--caller-obligation", helper, "--cases", self.cases)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    prompts = [request["prompt"] for path, request in calls if path == "/api/generate"]
                    self.assertEqual(len(prompts), 2)
                    self.assertNotIn("fn main()", prompts[0])
                    self.assertNotIn("caller requires", prompts[0])
                    self.assertEqual("caller requires target(4) = 5." in prompts[1], exact)
                    self.assertEqual("Read-only caller excerpts" in prompts[1], not exact)
                    self.output.unlink()

    def test_projected_body_rejects_dedent_and_translates_a_valid_retry(self):
        with mock_ollama(["return x\ndef escape(): return 1",
                          "if x > 0:\n        return x\n    return -x"], infill=True) as (port, calls):
            result = self.invoke(port, "body", "--infill", "--surface", "python")
        self.assertEqual(result.returncode, 0, result.stderr)
        recheck = calls[-1][1]
        self.assertIn("protected Python function body", recheck["prompt"])
        self.assertTrue(recheck["prompt"].endswith("def target(x: int) -> int:\n    "))
        self.assertEqual(self.output.read_text(), "if x > 0 {\n    return x;\n}\nreturn -x;\n")

    def test_infill_requires_suffix_support_and_python_requires_infill(self):
        with mock_ollama() as (port, calls):
            result = self.invoke(port, "expr", "--infill")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(".Suffix", result.stderr)
            self.assertFalse(any(endpoint == "/api/generate" for endpoint, _ in calls))
        with mock_ollama(infill=True) as (port, calls):
            result = self.invoke(port, "expr", "--surface", "python")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires --infill", result.stderr)
        self.assertFalse(calls)
        self.assertFalse(self.output.exists())

    def test_concurrent_source_edit_invalidates_base_revision(self):
        with mock_ollama(["x+1;"], on_generate=lambda: self.file.write_text(SOURCE + "// edited\n")) as (port, _):
            result = self.invoke(port)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("stale revision", result.stderr)
        self.assertFalse(self.output.exists())
        self.assertTrue(self.file.read_text().endswith("// edited\n"))

    def test_existing_or_concurrently_created_output_is_preserved(self):
        with mock_ollama(["x+1;"], on_generate=lambda: self.output.write_text("another proposal")) as (port, _):
            result = self.invoke(port)
        self.assertNotEqual(result.returncode, 0)
        with mock_ollama() as (port, calls):
            result = self.invoke(port)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(calls)
        self.assertEqual(self.output.read_text(), "another proposal")

    def test_cases_repair_compile_valid_answer_on_fourth_example(self):
        self.cases.write_text(json.dumps([
            {"args": [2], "expected": 2}, {"args": [0], "expected": 0},
            {"args": [2**63-1], "expected": 2**63-1}, {"args": [-1], "expected": 1},
        ]))
        with mock_ollama(["x", "if x < 0 { -x } else { x }"]) as (port, calls):
            result = self.invoke(port, "expr", "--cases", self.cases)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Passed 4 supplied cases", result.stdout)
        attempts = [value["prompt"] for path, value in calls if path == "/api/generate"]
        self.assertEqual(len(attempts), 2)
        self.assertIn("target(x=2) gives 2", attempts[0])
        self.assertIn("Case 4: target(x=-1) returned -1; expected 1.", attempts[1])
        self.assertEqual(self.output.read_text(), "if x < 0 { -x } else { x }\n")
        self.assertEqual(self.file.read_text(), SOURCE)

    def test_both_wrong_answers_or_faults_leave_no_proposal(self):
        self.cases.write_text('[{"args":[0],"expected":1}]')
        with mock_ollama(["1 / x", "x"]) as (port, calls):
            result = self.invoke(port, "expr", "--cases", self.cases)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("target(x=0) returned 0", result.stderr)
        self.assertIn("DivisionByZero", calls[-1][1]["prompt"])
        self.assertFalse(self.output.exists())

    def test_cases_validate_json_shape_arity_scalar_type_and_bounds_before_generation(self):
        rows = [
            [], [{}], [{"args": [], "expected": 0}], [{"args": [1, 2], "expected": 1}],
            [{"args": [True], "expected": 1}], [{"args": [1], "expected": False}],
            [{"args": [1.0], "expected": 1}], [{"args": ["1; return 3"], "expected": 1}],
            [{"args": [2**63], "expected": 1}], [{"args": [-(2**63)-1], "expected": 1}],
            [{"args": [0], "expected": 2**63}],
        ]
        with mock_ollama() as (port, calls):
            for invalid in rows:
                with self.subTest(invalid=invalid):
                    self.cases.write_text(json.dumps(invalid))
                    result = self.invoke(port, "expr", "--cases", self.cases)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(self.output.exists())
            self.assertFalse(calls)

    def test_bool_and_unit_arguments_call_the_original_main(self):
        source = """module demo;
fn __original_main() -> I64 !{} { return 9; }
fn target(flag: Bool, u: Unit) -> Bool !{} { return false; }
pub fn main() -> I64 !{} { return __original_main(); }
"""
        self.file.write_text(source)
        self.cases.write_text('[{"args":[true,null],"expected":true},{"args":[false,null],"expected":false}]')
        with mock_ollama(["flag && main() == 9"]) as (port, _):
            result = self.invoke(port, "expr", "--cases", self.cases)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.file.read_text(), source)
        self.assertIn("Passed 2 supplied cases", result.stdout)

    def test_unit_result_requires_termination_within_the_case_budget(self):
        source = """module demo;
fn target(x: I64) -> Unit !{} { return (); }
pub fn main() -> I64 !{} { return 0; }
"""
        self.file.write_text(source)
        self.cases.write_text(json.dumps([{"args": [-(2**63)], "expected": None}]))
        with mock_ollama(["while true { }", "return ();"]) as (port, calls):
            result = self.invoke(port, "body", "--cases", self.cases)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ResourceLimit", calls[-1][1]["prompt"])
        self.assertEqual(self.file.read_text(), source)

    def test_cases_can_target_the_entry_itself(self):
        self.cases.write_text('[{"args":[],"expected":7}]')
        with mock_ollama(["7"]) as (port, _):
            result = self.invoke(port, "expr", "--function", "main", "--cases", self.cases)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.file.read_text(), SOURCE)
        self.assertIn("Passed 1 supplied cases", result.stdout)

    def test_caller_context_and_caller_case_repair_leave_callers_untouched(self):
        source = """module demo;
fn target(x: I64) -> I64 !{} { return x; }
fn report(x: I64, alarm: Bool) -> I64 !{} {
    let points = target(x);
    if alarm { return points + 7; }
    return points;
}
fn decoy() -> I64 !{} { // target(72)
    return 123456;
}
pub fn main() -> I64 !{} { return report(2, true); }
"""
        self.file.write_text(source)
        self.cases.write_text('[{"function":"report","args":[2,true],"expected":10},'
                              '{"function":"main","args":[],"expected":10}]')
        with mock_ollama(["x", "x + 1"], infill=True) as (port, calls):
            result = self.invoke(port, "expr", "--infill", "--surface", "python", "--caller-context", "--cases", self.cases)
        self.assertEqual(result.returncode, 0, result.stderr)
        prompts = [r["prompt"] for endpoint, r in calls if endpoint == "/api/generate"]
        self.assertEqual(len(prompts), 2)
        self.assertIn("Read-only caller excerpts", prompts[0])
        self.assertIn("let points = target(x);", prompts[0])
        self.assertIn("[calls report]", prompts[0])
        self.assertNotIn("123456", prompts[0])
        self.assertIn("report(x=2, alarm=true) returned 9; expected 10", prompts[1])
        self.assertEqual(self.output.read_text(), "x + 1\n")
        self.assertEqual(self.file.read_text(), source)

    def test_deferred_context_adds_read_only_callers_on_named_behavior_failure(self):
        source = SOURCE.replace("pub fn main()", "fn target_report() -> I64 !{} { return target(2); }\npub fn main()")
        self.file.write_text(source)
        self.cases.write_text('[{"function":"target_report","args":[],"expected":3}]')
        with mock_ollama(["x", "x+1"], infill=True) as (port, calls):
            result = self.invoke(port, "expr", "--infill", "--caller-context-on-failure", "--cases", self.cases)
        self.assertEqual(result.returncode, 0, result.stderr)
        prompts = [r["prompt"] for endpoint, r in calls if endpoint == "/api/generate"]
        self.assertEqual(len(prompts), 2)
        self.assertIn("target_report() gives 3.", prompts[0])
        self.assertNotIn("Read-only caller excerpts", prompts[0])
        self.assertNotIn("Available functions:", prompts[0])
        self.assertNotIn("fn target_report()", prompts[0])
        self.assertIn("fn target_report()", prompts[1])
        self.assertIn("return target(2);", prompts[1])
        self.assertIn("target_report() returned 2; expected 3", prompts[1])
        self.assertNotIn("fn offset()", prompts[1])
        self.assertEqual(self.file.read_text(), source)

    def test_deferred_context_uses_checked_caller_faults(self):
        self.cases.write_text('[{"function":"main","args":[],"expected":5}]')
        with mock_ollama(["while true {} return x;", "return x + 1;"], infill=True) as (port, calls):
            result = self.invoke(port, "body", "--infill", "--caller-context-on-failure", "--cases", self.cases)
        self.assertEqual(result.returncode, 0, result.stderr)
        prompts = [r["prompt"] for endpoint, r in calls if endpoint == "/api/generate"]
        self.assertNotIn("fn main()", prompts[0])
        self.assertIn("fn main()", prompts[1])
        self.assertIn("main() raised fault: ResourceLimit", prompts[1])
        self.assertEqual(self.file.read_text(), SOURCE)

    def test_deferred_context_stays_hidden_for_unrelated_recursive_functions(self):
        self.file.write_text(SOURCE + """
fn report(n: I64) -> I64 !{} { if n == 0 { return 17; } return relay(n - 1); }
fn relay(n: I64) -> I64 !{} { return report(n); }
""")
        self.cases.write_text('[{"function":"report","args":[1],"expected":18}]')
        with mock_ollama(["x", "x+1"], infill=True) as (port, calls):
            result = self.invoke(port, "expr", "--infill", "--caller-context-on-failure", "--cases", self.cases)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.output.exists())
        prompts = [r["prompt"] for endpoint, r in calls if endpoint == "/api/generate"]
        self.assertEqual(len(prompts), 2)
        self.assertIn("report(n=1) returned 17; expected 18", prompts[1])
        self.assertTrue(all("Read-only caller excerpts" not in p and "fn main()" not in p for p in prompts))

    def test_deferred_context_recognizes_a_transitive_caller(self):
        self.file.write_text(SOURCE + "\nfn report() -> I64 !{} { return main(); }\n")
        self.cases.write_text('[{"function":"report","args":[],"expected":5}]')
        with mock_ollama(["x", "x+1"], infill=True) as (port, calls):
            result = self.invoke(port, "expr", "--infill", "--caller-context-on-failure", "--cases", self.cases)
        self.assertEqual(result.returncode, 0, result.stderr)
        prompts = [r["prompt"] for endpoint, r in calls if endpoint == "/api/generate"]
        self.assertNotIn("Read-only caller excerpts", prompts[0])
        self.assertIn("Read-only caller excerpts", prompts[1])
        self.assertIn("fn report()", prompts[1])

    def test_deferred_context_stays_target_only_on_target_and_static_failures(self):
        self.cases.write_text('[{"args":[4],"expected":5},{"function":"main","args":[],"expected":5}]')
        for previous, diagnostic in [("x", "target(x=4) returned 4"),
                                     ("true", "GPP-TYPE"), (";", "no code"), ("1 / 0", "DivisionByZero")]:
            with self.subTest(previous=previous), mock_ollama([previous, "x+1"]) as (port, calls):
                result = self.invoke(port, "expr", "--caller-context-on-failure", "--cases", self.cases)
                self.assertEqual(result.returncode, 0, result.stderr)
                prompts = [r["prompt"] for endpoint, r in calls if endpoint == "/api/generate"]
                self.assertEqual(len(prompts), 2)
                self.assertIn(diagnostic, prompts[1])
                self.assertTrue(all("Read-only caller excerpts" not in p and "Available functions:" not in p
                                    and "fn main()" not in p for p in prompts))
                self.output.unlink()

    def test_caller_modes_are_mutually_exclusive(self):
        with mock_ollama() as (port, calls):
            result = self.invoke(port, "expr", "--caller-context", "--caller-context-on-failure")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(calls)

    def test_case_function_must_resolve_to_a_checked_declaration(self):
        for unknown in [42, "target); return 3;", "other"]:
            self.cases.write_text(json.dumps([{"function": unknown, "args": [], "expected": 0}]))
            with self.subTest(unknown=unknown), mock_ollama() as (port, calls):
                result = self.invoke(port, "expr", "--cases", self.cases)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("unknown function", result.stderr)
                self.assertFalse(calls)

    def test_remote_alias_rejected_before_source_is_sent(self):
        with mock_ollama(remote=True) as (port, calls):
            result = self.invoke(port)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(path == "/api/generate" for path, _ in calls))
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
