"""Reproduce the supplemental v8 differential check with pinned upstream source.

From the repository root:
    target/empirical-venv/bin/python -B bench/policy/verify_upstream_sources.py

Requires clang++ (GNU C++17 mode), Node, and HTTPS access to raw.githubusercontent.com
on first use. Supply --cache DIRECTORY to retain and reuse the eight verified files.
"""

import argparse
import calendar
import ctypes
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
import json
from pathlib import Path
import random
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from bench.policy.upstream import TASKS

LINUX = "torvalds/linux"
GODOT = "godotengine/godot"
MOMENT = "moment/moment"
FILES = {
    "old_div": (LINUX, "4cbe5a555fa58a79b6ecbb6c531b8bab0650778d", "include/linux/kernel.h",
                "de55a38ff09bc3d65b33b5352b20025de287bd304a93b9e2a0fc0a0004dcf58d"),
    "new_div": (LINUX, "b6d86d3d6d6e4c9b588d81615c81b5a8292b62ed", "include/linux/kernel.h",
                "c363e837ba6e3c548e236a34245b72b4cb9148b4e9e9f123f044a86d0d4eabd6"),
    "old_month": (MOMENT, "71c41b12344b31feef467d5a7225376e442226ee", "src/lib/units/month.js",
                  "4902dacfff504e99c64a7199e247f711300f3d9587f672f1c9aecd5010972ad3"),
    "new_month": (MOMENT, "f5953bdf32bca2b48581f6058469008aed1de027", "src/lib/units/month.js",
                  "a950ceae62a01889c22f38c65b568ac00f694584e0908e3fb44d2a4b3a9bb21b"),
    "new_year": (MOMENT, "f5953bdf32bca2b48581f6058469008aed1de027", "src/lib/units/year.js",
                 "a9edf52aa01ad5a3d5f5c6865339d6ab59d5578b180684221fbd3ab9896c604c"),
    "mod": (MOMENT, "f5953bdf32bca2b48581f6058469008aed1de027", "src/lib/utils/mod.js",
            "24a639c80787b07e39dcb3fe3e6ee13e14903fa6a7d1cf252c3c63c9f7aeb9b1"),
    "old_rect": (GODOT, "d7822cbf2136b5dcff899b498c80c139b7701c9e", "core/math/rect2.h",
                 "96bca40810d54b5acc1b5e248864f95a1c166718975d73384ab62f232f115cac"),
    "new_rect": (GODOT, "23a4fe5b27c191eae1dde05aa522463e67b0766f", "core/math/rect2.h",
                 "9213b52a1908d6477932a81f6ed225961492103c455ecc8d8e0d2dc7d4590d5c"),
}


def fetch(cache):
    cache.mkdir(parents=True, exist_ok=True)
    sources = {}
    for label, (repo, commit, path, digest) in FILES.items():
        dest = cache / (commit + "-" + Path(path).name)
        if dest.exists():
            data = dest.read_bytes()
        else:
            with urlopen(f"https://raw.githubusercontent.com/{repo}/{commit}/{path}", timeout=30) as reply:
                data = reply.read()
        if sha256(data).hexdigest() != digest:
            raise ValueError(f"Upstream content differs for {repo} {commit} {path}")
        if not dest.exists():
            dest.write_bytes(data)
        sources[label] = data.decode()
    return sources


def corpus():
    rng = random.Random(195188)
    divide = [(rng.randrange(-1000000, 1000001), rng.randrange(1, 10001)) for _ in range(1500)]
    months = [(y, m) for y in [*range(-5, 105), -400, 1200, 1900, 1999, 2000, 2400] for m in range(-12, 24)]
    rects = [(w, h, x, y, ow, oh) for w, h, ow, oh in [(3, 4, 2, 1), (1, 8, 10, 5), (13, 1, 2, 20)]
             for x in range(-ow-1, w+2) for y in range(-oh-1, h+2)]
    return divide, months, rects


def oracle(index, args):
    if index == 0:
        x, d = args
        return int((Decimal(x) / d).to_integral_value(rounding=ROUND_HALF_UP))
    if index == 1:
        year, month = args
        carry, mm = divmod(month, 12)
        return calendar.monthrange(year + carry, mm + 1)[1]
    w, h, x, y, ow, oh = args
    pixels = {(i, j) for i in range(w) for j in range(h)}
    return int(any((i, j) in pixels for i in range(x, x + ow) for j in range(y, y + oh)))


def original_results(sources, rev, work, inputs):
    header = sources[rev + "_div"].splitlines()
    begin = next(i for i, line in enumerate(header) if line.startswith("#define DIV_ROUND_CLOSEST("))
    end = next(i for i in range(begin, len(header)) if not header[i].endswith(chr(92)))
    macro = "\n".join(header[begin:end + 1])
    h = sources[rev + "_rect"]
    start = h.index("\tinline bool intersects(const Rect2i")
    predicate = h[start:h.index("\n\tinline bool encloses(const Rect2i", start)]
    code = macro + """
extern "C" long long nearest(long long v, long long d) { return DIV_ROUND_CLOSEST(v, d); }
struct V { int x, y; };
struct S { int width, height; };
struct Rect2i { V position; S size;
""" + predicate + """
};
extern "C" int intersect(int w, int h, int x, int y, int ow, int oh) {
    Rect2i a{{0, 0}, {w, h}}, b{{x, y}, {ow, oh}};
    return a.intersects(b);
}
"""
    library = work / (rev + ".so")
    subprocess.run(["clang++", "-std=gnu++17", "-x", "c++", "-shared", "-fPIC", "-o", library, "-"],
                   input=code, text=True, check=True)
    compiled = ctypes.CDLL(str(library))
    compiled.nearest.argtypes = [ctypes.c_longlong] * 2
    compiled.nearest.restype = ctypes.c_longlong
    compiled.intersect.argtypes = [ctypes.c_int] * 6
    month = re.search(r"export (function daysInMonth\(.*?\n\})", sources[rev + "_month"], re.S)[1]
    if rev == "new":
        month += "\n" + re.search(r"export (function isLeapYear\(.*?\n\})", sources["new_year"], re.S)[1]
        month += "\n" + sources["mod"].replace("export default ", "")
    js = month + "\nconst input = JSON.parse(require('fs').readFileSync(0, 'utf8'));\n" \
        + "process.stdout.write(JSON.stringify(input.map(args => daysInMonth(...args))));"
    dates = json.loads(subprocess.check_output(["node", "-e", js], input=json.dumps(inputs[1]), text=True))
    return [compiled.nearest(*a) for a in inputs[0]], dates, [compiled.intersect(*a) for a in inputs[2]]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cache", type=Path)
    args = p.parse_args()
    with TemporaryDirectory(prefix="gpp-upstream-oracles-") as tmp:
        work = Path(tmp)
        sources, inputs = fetch(args.cache or work), corpus()
        for rev, variant in (("old", "starter"), ("new", "reference")):
            results = original_results(sources, rev, work, inputs)
            for i, (task, tests, expected) in enumerate(zip(TASKS, inputs, results)):
                namespace = {}
                # Execute only the local, authored fixture translation for differential comparison.
                exec(task[variant]["python"], namespace)
                fn = namespace[task["target"]]
                if len(expected) != len(tests):
                    raise ValueError("Upstream oracle returned the wrong number of results")
                for arguments, value in zip(tests, expected):
                    if fn(*arguments) != value or (rev == "new" and oracle(i, arguments) != value):
                        raise ValueError(f"{task['id']} {variant} disagrees on {arguments}")
                print(f"{variant} {task['id']}: {len(tests)} matched")


if __name__ == "__main__":
    main()
