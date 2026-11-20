"""Replay a frozen agent-expression archive using the specified pre-extension compiler."""

import argparse
from pathlib import Path

import agent_study
import fresh_agent_study


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("archive", type=Path)
    cli.add_argument("--gpp", type=Path, required=True)
    args = cli.parse_args()
    agent_study.GPP = args.gpp.resolve(strict=True)
    meta, _ = agent_study.prior.read_archive(args.archive)
    runner = {"fresh-agent-expression-v1": fresh_agent_study.run,
              "matched-agent-expression-v1": agent_study.run}[meta["study"]]
    runner(args.archive, True, None)
