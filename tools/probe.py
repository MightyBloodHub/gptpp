"""Stream independent edits through one revision-bound scalar compiler process."""

from contextlib import contextmanager
import json
from queue import Empty, Queue
import subprocess
from tempfile import TemporaryFile
from threading import Thread

import propose


@contextmanager
def session(binary, snapshot, function, revision, work, calls, *, wrapped=False, expected=None):
    cases_file = work / "calls.tsv"
    fields = [[name, *args] for name, args in calls]
    if expected is not None:
        for row, value in zip(fields, expected, strict=True):
            row.append(value)
    cases_file.write_text("".join("\t".join(row) + "\n" for row in fields), encoding="utf-8")
    command = [binary, "probe", snapshot, "--function", function, "--expect", revision, "--cases", cases_file]
    if wrapped:
        command.append("--wrapped")
    if expected is not None:
        command.append("--filter")
    with TemporaryFile() as errors, subprocess.Popen(
        command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors,
    ) as process:
        replies = Queue()

        def read_lines():
            for raw in process.stdout:
                replies.put(raw)
            replies.put(None)

        reader = Thread(target=read_lines, daemon=True)
        reader.start()

        def failure():
            errors.seek(0)
            return propose.ProposalError(errors.read().decode(errors="replace").strip() or
                                         f"Compiler probe closed its output ({process.poll()}).")

        def receive():
            try:
                line = replies.get(timeout=60)
            except Empty as exc:
                raise propose.ProposalError("Compiler probe timed out.") from exc
            if line is None:
                raise failure()
            return json.loads(line)

        def evaluate(candidate, *, check_only=False):
            fragment = candidate["replacement"].encode()
            flag = " check" if check_only else ""
            header = f"{candidate['start_byte']}:{candidate['end_byte']} {len(fragment)}{flag}\n"
            try:
                process.stdin.write(header.encode("ascii") + fragment)
                process.stdin.flush()
            except BrokenPipeError as exc:
                raise failure() from exc
            result = receive()
            if result.get("status") == "invalid" and isinstance(result.get("error"), str):
                return result
            if expected is not None and not check_only:
                if result.get("status") != "ok" or type(result.get("matches")) is not bool:
                    raise propose.ProposalError("Invalid compiler filter response.")
                return result
            count = 0 if check_only else len(calls)
            outcomes = result.get("outcomes")
            if (result.get("status") != "ok" or not isinstance(outcomes, list) or len(outcomes) != count or
                    any(not isinstance(r, dict) or set(r) not in ({"result"}, {"fault"}) for r in outcomes)):
                raise propose.ProposalError("Invalid compiler probe response.")
            return result

        try:
            hello = receive()
            if hello != {"schema": "gpp.probe/1", "revision": revision, "cases": len(calls)}:
                raise propose.ProposalError("Compiler probe opened a different revision or case set.")
            yield evaluate
            process.stdin.close()
            if process.wait(timeout=60):
                raise failure()
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
            reader.join()
