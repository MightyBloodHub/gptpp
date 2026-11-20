"""Score the entire frozen repair menu after collecting all model choices."""

import argparse
from pathlib import Path
from tempfile import TemporaryDirectory

import repair_study as study


def audit(path):
    _, rows = study.read_archive(path)
    _, baseline = study.baseline()
    study.verify_rows(rows, baseline)
    tasks = {task["id"]: task for task in study.TASKS}
    tools = study.base.prior.Tools(study.ROOT, study.GPP)
    print("# Withheld audit of the frozen repair menus\n")
    print("After all six trials finished, the scorer tested every candidate in the archived menus. "
          "The two models received identical choices for each task. IDs refer to the original menu order. "
          "This retrospective audit did not affect the selections.\n")
    print("| Task | ID | Replaced expression | Candidate | Withheld result |")
    print("|---|---:|---|---|---|")
    for name, task in tasks.items():
        menus = [r["product"] for r in rows if r["task"] == name]
        revision, candidates = menus[0]["revision"], menus[0]["candidates"]
        if any(m["revision"] != revision or m["candidates"] != candidates for m in menus):
            raise ValueError(f"Models received different menus for {name}.")
        if not candidates:
            print(f"| {name} | — | — | — | Empty menu |")
            continue
        with TemporaryDirectory(prefix="gpp-menu-audit-") as directory:
            file = Path(directory) / "base.gpp"
            file.write_text(study.MODULE + study.source_for(task, "gpp") + study.ENTRY)
            fragment = file.with_suffix(".expr")
            for ordinal, c in enumerate(candidates, 1):
                fragment.write_text(c["replacement"] + "\n")
                result = study.score(tools, task, file, revision, c, fragment)
                summary = result["detail"] or "Passed every withheld case"
                print(f"| {name} | {ordinal} | `{c['old']}` | `{c['replacement']}` | {summary} |")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("archive", type=Path)
    audit(cli.parse_args().archive)
