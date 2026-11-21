"""Run the frozen comparison and its matched-helper sensitivity into a new directory."""

import argparse
from pathlib import Path

import matched_helpers
import study


def compare(directory, port):
    study.verify_freeze()
    matched_helpers.pin()
    directory.mkdir(parents=True, exist_ok=False)
    primary = directory / "primary"
    study.collect(primary, port)
    matched_helpers.collect(primary, directory / "matched_helpers", port)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--port", type=int, default=11434)
    args = parser.parse_args()
    compare(args.directory, args.port)
