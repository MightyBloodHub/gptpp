"""Render shareable benchmark charts and CSV from the frozen expression archives."""

import argparse
from collections import defaultdict
import csv
from dataclasses import asdict, dataclass, field
from hashlib import sha256
from itertools import product
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

HERE = Path(__file__).resolve().parent
WORKFLOWS = {
    "given": "Supplied location",
    "full": "Whole-body edit",
    "locate": "Copy, then edit",
    "combined": "Copy and edit",
    "catalog": "Numbered catalog",
}
LANGUAGES = {"gpp": "GPT++", "python": "Typed Python", "rust": "Rust"}
PAPER = "#f5f2e9"
INK = "#12151f"
SLATE = "#505a69"
VIOLET = "#513a9c"
TINT = "#e6dff9"
RULE = "#d3cfc3"


@dataclass
class Usage:
    accepted: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    model_calls: int = 0

    def add(self, calls, accepted):
        self.accepted += accepted
        self.input_tokens += sum(call["input_tokens"] for call in calls)
        self.output_tokens += sum(call["output_tokens"] for call in calls)
        self.model_calls += len(calls)

    def tokens_per_accepted(self):
        if self.accepted:
            return (self.input_tokens + self.output_tokens) / self.accepted
        return None


@dataclass
class Summary:
    assigned: int = 0
    valid_locations: int | None = None
    first: Usage = field(default_factory=Usage)
    final: Usage = field(default_factory=Usage)

    def add(self, row, workflow):
        self.assigned += 1
        if workflow in ("locate", "combined", "catalog"):
            self.valid_locations = (self.valid_locations or 0) + (row.get("span") is not None)
        calls = row["attempts"]
        self.first.add([a for a in calls if a["stage"] != "retry"], row["first_accepted"])
        self.final.add(calls, row["accepted"])

    def table_usage(self, workflow):
        return self.first if workflow == "given" else self.final


def load_archive(name):
    path = HERE / "results" / name
    payload = path.read_bytes()
    manifest, *rows = map(json.loads, payload.splitlines())
    return payload, manifest, rows


def summarize():
    expression_bytes, expression, rows = load_archive("expression.jsonl")
    _, catalog, catalog_rows = load_archive("catalog.jsonl")
    models, tasks = expression["models"], expression["tasks"]
    ordinary_arms = {f"{lang}_{mode}" for lang in LANGUAGES for mode in WORKFLOWS if mode != "catalog"}
    if (
        expression["study"] != "upstream-expression-maintenance-v9"
        or catalog["study"] != "catalog-followup-v9"
        or set(expression["conditions"]) != ordinary_arms
        or catalog["original_archive_sha256"] != sha256(expression_bytes).hexdigest()
    ):
        raise ValueError("Expected the paired v9 expression and catalog archives")

    ordinary_roster = set(product(models, tasks, ordinary_arms))
    catalog_roster = set(product(models, tasks, LANGUAGES))
    ordinary_keys = {(r["model"], r["task"], r["condition"]) for r in rows}
    catalog_keys = {(r["model"], r["task"], r["language"]) for r in catalog_rows}
    if ordinary_keys != ordinary_roster or len(rows) != len(ordinary_roster):
        raise ValueError("Incomplete or duplicate expression trials")
    if catalog_keys != catalog_roster or len(catalog_rows) != len(catalog_roster):
        raise ValueError("Incomplete or duplicate catalog trials")

    stats = defaultdict(Summary)
    for row in rows:
        language, workflow = row["condition"].split("_", 1)
        if language != row["language"]:
            raise ValueError("Expression trial language differs from its condition")
        stats[workflow, row["model"], language].add(row, workflow)
    for row in catalog_rows:
        reply = row["reply"]
        accepted = row["outcome"] == "accepted"
        calls = [
            dict(stage="edit", input_tokens=reply["prompt_eval_count"], output_tokens=reply["eval_count"])
        ]
        stats["catalog", row["model"], row["language"]].add(
            dict(row, attempts=calls, first_accepted=accepted, accepted=accepted), "catalog"
        )
    return stats, models


def export_csv(path, stats):
    rows = []
    for (workflow, model, language), summary in sorted(stats.items()):
        row = {
            "workflow": workflow,
            "model": model,
            "language": language,
            "assigned_trials": summary.assigned,
            "valid_locations": summary.valid_locations,
        }
        for label, usage in (("first_edit", summary.first), ("full_budget", summary.final)):
            for field, value in asdict(usage).items():
                row[f"{label}_{field}"] = value
            cost = usage.tokens_per_accepted()
            row[f"{label}_tokens_per_accepted_edit"] = "" if cost is None else f"{cost:.2f}"
        rows.append(row)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def canvas(size, title, subtitle):
    fig = plt.figure(figsize=size, facecolor=PAPER)
    fig.text(0.065, 0.927, title, color=INK, size=22, weight="bold", va="top")
    fig.text(0.065, 0.827, subtitle, color=SLATE, size=11.5, va="top", linespacing=1.45)
    return fig


def save(fig, output, name):
    fig.text(
        0.065,
        0.054,
        "GPT++ RESEARCH  /  EXPRESSION STUDY V9",
        color=SLATE,
        size=9,
        family="monospace",
        va="bottom",
    )
    fig.savefig(output / name, dpi=220, metadata={"Software": "GPT++ benchmark charts"})
    plt.close(fig)


def plot_acceptance(output, stats, models):
    fig = canvas(
        (7, 4.55),
        "Which edits passed?",
        "Accepted changes per workflow and language\n3 historical fixes × 2 models per cell",
    )
    ax = fig.add_axes([0.065, 0.13, 0.87, 0.57])
    ax.set(xlim=(0, 1), ylim=(0, 6))
    ax.axis("off")

    columns = (0.52, 0.71, 0.91)
    for x, title in zip(columns, LANGUAGES.values()):
        ax.text(x, 5.53, title, ha="center", va="center", color=INK, size=12, weight="bold")
    for index, (workflow, label) in enumerate(WORKFLOWS.items()):
        y = 4.5 - index
        ax.axhline(y + 0.5, linewidth=0.7, color=RULE)
        note = {"given": "One edit attempt", "full": "Caller-triggered retry allowed"}.get(workflow)
        ax.text(0, y + (0.13 if note else 0), label, va="center", color=INK, size=14, weight="bold")
        if note:
            ax.text(0, y - 0.23, note, va="center", color=SLATE, size=9)
        for x, lang in zip(columns, LANGUAGES):
            summaries = [stats[workflow, model, lang] for model in models]
            eligible = sum(s.assigned for s in summaries)
            accepted = sum(s.table_usage(workflow).accepted for s in summaries)
            if accepted:
                ax.add_patch(Rectangle((x - 0.067, y - 0.28), 0.134, 0.56, fc=TINT, lw=0))
            ax.text(
                x,
                y,
                f"{accepted}/{eligible}",
                ha="center",
                va="center",
                size=15,
                color=VIOLET if accepted else SLATE,
                weight="bold" if accepted else "normal",
            )
    save(fig, output, "acceptance.png")


def plot_selection(output, stats, models):
    fig = canvas(
        (5.7, 4.70),
        "Finding an expression",
        "3 historical fixes × 2 models × 3 languages\n18 trials for each workflow",
    )
    ax = fig.add_axes([0.065, 0.17, 0.87, 0.53])
    ax.set(xlim=(0, 1), ylim=(0, 3.67))
    ax.axis("off")
    ax.text(0.0, 3.4, "Valid locations", color=VIOLET, size=12, weight="bold")
    ax.text(1, 3.4, "Accepted edits", color=INK, size=12, weight="bold", ha="right")
    ax.axhline(3.22, color=RULE, lw=0.8)
    for y, workflow in zip((2.67, 1.57, 0.47), ("locate", "combined", "catalog")):
        summaries = [stats[workflow, model, language] for model, language in product(models, LANGUAGES)]
        valid = sum(s.valid_locations for s in summaries)
        accepted = sum(s.final.accepted for s in summaries)
        assigned = sum(s.assigned for s in summaries)
        ax.text(0, y + 0.17, WORKFLOWS[workflow], size=14, va="center", color=INK, weight="bold")
        ax.barh(y - 0.23, 0.50, height=0.19, color=RULE, align="center")
        ax.barh(y - 0.23, 0.50 * valid / assigned, height=0.19, color=VIOLET, align="center")
        ax.text(0.53, y - 0.23, f"{valid}/{assigned}", va="center", size=14, color=VIOLET, weight="bold")
        ax.text(1, y - 0.23, f"{accepted}/{assigned}", va="center", ha="right", size=14, color=INK)
    save(fig, output, "selection.png")


def plot_cost(output, stats, model):
    model_label = "StarCoder2 3B" if model == "starcoder2:3b" else model
    fig = canvas(
        (5.7, 4.70),
        "Cost per accepted edit",
        f"{model_label} · Supplied location · One attempt\nInput and output tokens across 3 historical fixes",
    )
    gpp = stats["given", model, "gpp"].first
    python = stats["given", model, "python"].first
    rust = stats["given", model, "rust"].first

    ax = fig.add_axes([0.065, 0.20, 0.87, 0.48], facecolor=PAPER)
    limit = max(gpp.tokens_per_accepted(), rust.tokens_per_accepted()) * 1.16
    ax.set(xlim=(0, limit), ylim=(-0.11, 2.68))
    ax.set_axis_off()
    ax.axvline(0, ymin=0.11, ymax=0.91, color=RULE, lw=1, clip_on=False)
    for y, language, usage, color in ((1.93, "gpp", gpp, VIOLET), (0.60, "rust", rust, SLATE)):
        cost = usage.tokens_per_accepted()
        assigned = stats["given", model, language].assigned
        ax.text(
            0,
            y + 0.27,
            f"{LANGUAGES[language]} · {usage.accepted}/{assigned} accepted",
            va="bottom",
            color=INK,
            size=13,
            weight="bold",
        )
        ax.barh(y, cost, height=0.32, color=color)
        ax.text(cost + limit * 0.025, y, f"{cost:,.0f}", va="center", color=INK, size=14, weight="bold")
    ax.text(limit, 0.07, "Lower is better", va="bottom", ha="right", color=SLATE, size=10)
    python_assigned = stats["given", model, "python"].assigned
    fig.text(
        0.065,
        0.121,
        f"Typed Python · {python.accepted}/{python_assigned} accepted · cost undefined",
        color=SLATE,
        size=11,
    )
    save(fig, output, "token-cost.png")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "community")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    stats, models = summarize()
    export_csv(args.output / "benchmark-summary.csv", stats)
    plot_acceptance(args.output, stats, models)
    plot_selection(args.output, stats, models)
    plot_cost(args.output, stats, "starcoder2:3b")


if __name__ == "__main__":
    main()
