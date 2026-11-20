"""Run one function against fixed cases using isolated, bounded child processes."""

import ast
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import sys
import tempfile


def signature(task, language):
    types = {
        "python": {"int": "int", "bool": "bool"},
        "rust": {"int": "i64", "bool": "bool"},
        "gpp": {"int": "I64", "bool": "Bool"},
    }[language]
    params = ", ".join(f"{name}: {types[kind]}" for name, kind in task["params"])
    return {
        "python": f"def solve({params}) -> int:",
        "rust": f"fn solve({params}) -> i64",
        "gpp": f"fn solve({params}) -> I64 !{{}}",
    }[language]


def literal(value, language):
    if type(value) is bool and language != "python":
        return str(value).lower()
    return str(value)


def arguments(args, language):
    return ", ".join(literal(value, language) for value in args)


def static_python_check(code, task):
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return str(exc)
    if (
        len(tree.body) != 1
        or not isinstance(tree.body[0], ast.FunctionDef)
        or tree.body[0].name != "solve"
    ):
        return "Return one typed function named solve."
    expected = ast.parse(signature(task, "python") + "\n    pass").body[0]
    fn = tree.body[0]
    if (
        ast.dump(fn.args) != ast.dump(expected.args)
        or ast.dump(fn.returns) != ast.dump(expected.returns)
        or fn.decorator_list
    ):
        return f"Use the required signature: {signature(task, 'python')}"
    return None


class Tools:
    def __init__(self, root, gpp):
        if sys.platform != "darwin" or not Path("/usr/bin/sandbox-exec").is_file():
            raise RuntimeError("This evaluator requires the macOS sandbox-exec worker.")
        self.python = Path(sys.executable).absolute()
        self.rustc = Path(shutil.which("rustc") or "").resolve(strict=True)
        self.gpp = gpp.resolve(strict=True)
        self.read_paths = [Path(sys.base_prefix).resolve(), Path(sys.prefix).resolve()]
        self.sdk = subprocess.check_output(
            ["/usr/bin/xcrun", "--sdk", "macosx", "--show-sdk-path"], text=True
        ).strip()
        self.env_path = "/usr/bin:/bin"
        self.root = root
        self.system_readable = (
            "/System", "/usr", "/bin", "/dev", "/opt/homebrew",
            "/Applications/Xcode.app", "/Library/Developer",
        )

    def run(self, command, work, *, compile_step=False):
        read_paths = [str(work), *self.system_readable, *(str(p) for p in self.read_paths)]
        read_paths.extend(str(Path(path).resolve()) for path in command[:1])
        readable = " ".join(f"(subpath {json.dumps(path)})" for path in read_paths)
        profile = (
            "(version 1) (allow default) (deny network*) "
            '(deny file-read-data (subpath "/Users") (subpath "/Volumes") '
            '(subpath "/private/tmp") (subpath "/private/var/folders") '
            '(subpath "/private/etc") (subpath "/opt/homebrew/etc") '
            '(subpath "/usr/local/etc")) '
            f"(allow file-read-data {readable}) "
            "(deny file-write*) "
            f'(allow file-write* (subpath {json.dumps(str(work))}) (literal "/dev/null")) '
        )
        if not compile_step:
            profile += "(deny process-fork) (deny process-exec (subpath \"/Users\")) "
            profile += f"(allow process-exec (literal {json.dumps(str(Path(command[0]).resolve()))}))"

        def limits():
            resource.setrlimit(resource.RLIMIT_CPU, (8, 9))
            resource.setrlimit(resource.RLIMIT_FSIZE, (1_048_576, 1_048_576))
            resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

        with tempfile.TemporaryFile(dir=work) as stdout, tempfile.TemporaryFile(dir=work) as stderr:
            child = subprocess.Popen(
                ["/usr/bin/sandbox-exec", "-p", profile, *map(str, command)],
                cwd=work,
                env={"PATH": self.env_path, "TMPDIR": str(work), "SDKROOT": self.sdk,
                     "LC_ALL": "C", "PYTHONDONTWRITEBYTECODE": "1"},
                stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                preexec_fn=limits, start_new_session=True,
            )
            try:
                child.wait(timeout=12 if compile_step else 2)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
                return 124, "", "Execution exceeded the time limit."
            stdout.seek(0)
            stderr.seek(0)
            return child.returncode, stdout.read().decode(errors="replace"), stderr.read().decode(errors="replace")

    def canaries(self):
        with tempfile.TemporaryDirectory(prefix="gpp-sandbox-") as folder:
            work = Path(folder).resolve()
            probe = work / "probe.py"
            probe.write_text(
                "import pathlib, socket, sys\n"
                "try:\n pathlib.Path(sys.argv[1]).read_bytes()\n"
                "except PermissionError: print('read denied')\n"
                "try:\n socket.create_connection(('127.0.0.1', 11434), timeout=1)\n"
                "except PermissionError: print('network denied')\n"
                "try:\n pathlib.Path(sys.argv[2]).write_text('probe')\n"
                "except PermissionError: print('write denied')\n"
            )
            rc, out, err = self.run(
                [self.python, "-I", probe, self.root / "README.md", work.parent / (work.name + ".probe")],
                work,
            )
            if rc != 0 or out.splitlines() != ["read denied", "network denied", "write denied"]:
                raise RuntimeError(f"Sandbox preflight failed: {rc}, {out!r}, {err!r}")

    def evaluate(self, task, language, code, cases, *, heldout=False):
        with tempfile.TemporaryDirectory(prefix="gpp-eval-") as folder:
            work = Path(folder).resolve()
            def error(category, rc, out, err):
                detail = (err or out or f"Process exited with status {rc}.").replace(str(work) + "/", "")
                return category, detail.strip()[:600]

            if language == "gpp":
                source = work / "trial.gpp"
                outputs = []
                for args, _ in cases:
                    source.write_text(
                        f"module empirical.trial;\n{code}\n"
                        f"pub fn main() -> I64 !{{}} {{ return solve({arguments(args, language)}); }}\n"
                    )
                    rc, out, err = self.run([self.gpp, "run", "--interpreter", source], work)
                    if rc:
                        category = "check_error" if "error[GPP-" in err else "runtime_error"
                        return error(category, rc, out, err)
                    outputs.extend(out.splitlines())
            elif language == "rust":
                source = work / "trial.rs"
                exe = work / "trial"
                checks = "\n".join(
                    f'    println!("{{}}", call({arguments(args, language)}));' for args, _ in cases
                )
                types = ", ".join({"int": "i64", "bool": "bool"}[kind] for _, kind in task["params"])
                source.write_text(f"{code}\nfn main() {{\n    let call: fn({types}) -> i64 = solve;\n{checks}\n}}\n")
                rc, out, err = self.run(
                    [self.rustc, "--edition=2024", "-C", "overflow-checks=yes", source, "-o", exe],
                    work, compile_step=True,
                )
                if rc:
                    return error("check_error", rc, out, err)
                rc, out, err = self.run([exe], work)
                if rc:
                    return error("runtime_error", rc, out, err)
                outputs = out.splitlines()
            else:
                diagnostic = static_python_check(code, task)
                if diagnostic:
                    return "check_error", diagnostic
                source = work / "trial.py"
                rows = "\n".join(
                    f"emit(solve({arguments(args, language)}))" for args, _ in cases
                )
                source.write_text(
                    f"{code}\n\ndef emit(value: int) -> None:\n"
                    "    if type(value) is not int:\n        raise TypeError('solve must return int')\n"
                    f"    print(value)\n\n{rows}\n"
                )
                if not heldout:
                    config = work / "mypy.ini"
                    config.write_text("[mypy]\n")
                    rc, out, err = self.run(
                        [self.python, "-I", "-m", "mypy", "--strict", "--no-site-packages",
                         "--cache-dir=/dev/null", "--config-file", config, source],
                        work, compile_step=True,
                    )
                    if rc:
                        return error("check_error", rc, err, out)
                rc, out, err = self.run([self.python, "-I", source], work)
                if rc:
                    return error("runtime_error", rc, out, err)
                outputs = out.splitlines()

            if len(outputs) != len(cases):
                return "wrong_answer", f"Expected {len(cases)} values, got {len(outputs)} output lines."
            for (args, expected), actual in zip(cases, outputs):
                if actual != str(expected):
                    return "wrong_answer", f"solve{args} returned {actual[:60]}; expected {expected}."
            return "pass", ""
