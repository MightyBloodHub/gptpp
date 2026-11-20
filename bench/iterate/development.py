"""Run the bounded fragment workflow on four previously published development tasks."""

import json
import sys
from pathlib import Path
from run_study import fragment_trial, pilot, Tools


def main(path):
    forms = {"median_index": "expr", "digit_descents": "body",
             "maintenance_reserve_floor": "body", "maintenance_rotating_index": "expr"}
    tasks = [dict(t, form=forms[t["id"]]) for t in pilot.SYNTHESIS + pilot.MAINTENANCE if t["id"] in forms]
    tools = Tools(pilot.ROOT, pilot.ROOT / "target/debug/gpp")
    tools.canaries()
    with path.open("x", buffering=1) as out:
        for model in pilot.MODELS:
            base = pilot.request("show", {"name": model})["template"]
            for task in tasks:
                row = fragment_trial(tools, model, task, "gpp", base)
                print(json.dumps(row, ensure_ascii=False), file=out)
                print(model, task["id"], row["attempts"][-1]["outcome"], flush=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
