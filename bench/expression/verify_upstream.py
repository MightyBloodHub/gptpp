"""Compare the frozen Python extracts to compiled calculations from pinned upstream files.

Run `python3 bench/expression/verify_upstream.py` with Python 3.10+, cc and go.
The first run fetches the upstream sources. Subsequent runs can use --offline.
"""

import argparse
import ctypes
from hashlib import sha256
from itertools import product
from pathlib import Path
import random
import subprocess
import sys
from tempfile import NamedTemporaryFile, TemporaryDirectory
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from bench.expression.tasks import TASKS

REDIS = "redis/redis"
LED = "FastLED/FastLED"
GO = "golang/go"
REDIS_BEFORE = "3db0f1a284e4fba703419b892b2d5b8d385afc06"
REDIS_AFTER = "b458b2999b749950c5ea9468cfa5ab74782848c3"
LED_BEFORE = "5b93491f66da32c118f177619375f582c938f128"
LED_AFTER = "fee800a12e0ccde471379e8e4bd613d13fe1526b"
GO_BEFORE = "7f83fbe6a6d0b4f7bc29f0e88ec42562e47e0b6b"
GO_AFTER = "4f25c33e83df34f27e939f40109c27831e508b09"

# Cache by raw content SHA-256. The two FastLED caller headers are byte-identical.
SOURCES = {
    "redis_starter": (REDIS, REDIS_BEFORE, "src/object.c", "57e2ea1c05c7754d46c047c430ddbdb7d487e4560b3c47d6ff58e401fe9d631c"),
    "redis_reference": (REDIS, REDIS_AFTER, "src/object.c", "a7e56b4dc5632a527f32af4335eb1d8da39847dd4e87b52ed6d51976dff90b58"),
    "redis_constants": (REDIS, REDIS_AFTER, "src/server.h", "f3d2c5cd9d8c3168f686346fd18126cb07f077d57ca346631668fa82cd363cf3"),
    "led_starter": (LED, LED_BEFORE, "lib8tion/scale8.h", "785bbd493360c5ab0940c952b81cb05ac964dcc713baaece5db77f7d466d7709"),
    "led_reference": (LED, LED_AFTER, "lib8tion/scale8.h", "7d804af22e814aa054faef19208ef600c6bbc1956568b0c1fb7101ee414827f8"),
    "led_callers": (LED, LED_AFTER, "lib8tion.h", "288078f0d869913e327b5de6c43d65fde7b599dd648e70449975e21216ca55dd"),
    "go_starter": (GO, GO_BEFORE, "src/time/zoneinfo.go", "198928e8d2573d88d8743db57b86777a26506f17ef2b0283882a9f5c884979b7"),
    "go_reference": (GO, GO_AFTER, "src/time/zoneinfo.go", "416a39440581a499d295be88acfc694f4cd396e13763e48d776a1b5ec3e273c2"),
    "go_calendar": (GO, GO_AFTER, "src/time/time.go", "e909960d7e4ec5cb2e5248b6b3e17f5f8e2e07a49839133301c64beff37441c7"),
}


def pinned_sources(cache, offline):
    cache.mkdir(parents=True, exist_ok=True)
    sources = {}
    for name, (repo, commit, path, digest) in SOURCES.items():
        cached = cache / digest
        url = f"https://raw.githubusercontent.com/{repo}/{commit}/{path}"
        if cached.is_file():
            data = cached.read_bytes()
        elif offline:
            raise ValueError(f"Missing cached source: {url}. Run once without --offline.")
        else:
            with urlopen(url, timeout=30) as response:
                data = response.read()
        if sha256(data).hexdigest() != digest:
            raise ValueError(f"SHA-256 mismatch for {url}. Expected {digest}. Cache path: {cached}")
        if not cached.exists():
            with NamedTemporaryFile(dir=cache, delete=False) as temp:
                temp.write(data)
            Path(temp.name).replace(cached)
        sources[name] = data.decode()
    return sources


def fixture(task_id, variant):
    task = next(t for t in TASKS if t["id"] == task_id)
    namespace = {}
    exec(task[variant]["python"] + "\n\n" + task["callers"]["python"], namespace)
    return namespace


def expect_equal(name, inputs, translated, upstream):
    if translated != upstream:
        raise ValueError(f"{name}{inputs}: fixture returned {translated}, upstream returned {upstream}")


def compile_c(work, name, source):
    file, library = work / f"{name}.c", work / f"{name}.so"
    file.write_text(source)
    subprocess.run(["cc", "-shared", "-fPIC", "-O2", "-o", library, file], check=True)
    return ctypes.CDLL(str(library))


def through_end_of_function(source, first_line):
    """The pinned C and Go files put top-level closing braces at column zero."""
    start = source.index(first_line)
    return source[start:source.index("\n}", start) + 2]


def audit_redis(work, sources, variant, rng):
    target = fixture("redis_lru_timestamp", variant)["access_stamp"]
    code = sources["redis_" + variant]
    start = code.index("lru_idle = lru_idle*lru_multiplier")
    end = code.index("val->lru = lru_abs;", start)
    keys = ("#define LRU_BITS ", "#define LRU_CLOCK_MAX ", "#define LRU_CLOCK_RESOLUTION ")
    defines = [line for line in sources["redis_constants"].splitlines() if line.startswith(keys)]
    source = "\n".join(defines + [
        "long long stamp(long long lru_clock, long long lru_idle, int lru_multiplier) {",
        code[start:end], "return lru_abs;", "}",
    ])
    stamp = compile_c(work, "redis_" + variant, source).stamp
    stamp.restype = ctypes.c_longlong
    stamp.argtypes = [ctypes.c_longlong, ctypes.c_longlong, ctypes.c_int]
    count = 0
    for _ in range(2048):
        age = rng.randrange(10001)
        clock = rng.choice([0, 16777215, max(0, age - 1), age, age + 1, rng.randrange(16777216)])
        for multiplier in (1, 1000):
            idle = age if multiplier == 1000 else age * 1000 + rng.randrange(1000)
            args = (clock, idle, multiplier)
            expect_equal("access_stamp", args, target(*args), stamp(*args))
            count += 1
    return count


def audit_led(work, sources, variant, rng):
    targets = fixture("fastled_fixed_scale", variant)
    header = sources["led_" + variant]
    start = header.index("LIB8STATIC uint8_t scale8(")
    end = header.index("#elif SCALE8_AVRASM", start)
    calls = [through_end_of_function(sources["led_callers"], f"LIB8STATIC uint8_t {name}(")
             for name in ("lerp8by8", "map8")]
    count = 0
    for mode in (False, True):
        source = "\n".join([
            "#include <stdint.h>", "typedef uint8_t fract8;", "#define LIB8STATIC",
            "#define SCALE8_C 1", f"#define FASTLED_SCALE8_FIXED {int(mode)}",
            header[start:end], "#endif", "}", *calls,
        ])
        library = compile_c(work, f"led_{variant}_{int(mode)}", source)
        lerp_inputs = (tuple(rng.randrange(256) for _ in range(3)) for _ in range(1024))
        map_inputs = ((rng.randrange(256), *sorted((rng.randrange(256), rng.randrange(256))))
                      for _ in range(1024))
        for name, native, arity, cases in [
            ("scale_channel", library.scale8, 2, product(range(256), repeat=2)),
            ("interpolate_byte", library.lerp8by8, 3, lerp_inputs),
            ("map_byte", library.map8, 3, map_inputs),
        ]:
            native.restype = ctypes.c_ubyte
            native.argtypes = [ctypes.c_ubyte] * arity
            for args in cases:
                inputs = (*args, mode)
                expect_equal(name, inputs, targets[name](*inputs), native(*args))
                count += 1
    return count


GO_WRAPPER = """package main
import "fmt"
const secondsPerDay = 86400
func interval(year int, ysec int64) (string, int, int64, int64, bool, bool) {
    const ystart, startSec, endSec int64 = 0, 6048000, 26784000
    const stdName, dstName = "", ""
    const stdOffset, dstOffset = 0, 0
    const stdIsDST, dstIsDST = false, true
"""

GO_DRIVER = """func main() {
    var year int
    var elapsed int64
    for {
        if _, err := fmt.Scan(&year, &elapsed); err != nil { return }
        _, _, _, end, _, _ := interval(year, elapsed)
        fmt.Println(end)
    }
}
"""


def audit_go(work, sources, variant):
    target = fixture("go_footer_year_end", variant)["period_end"]
    calculation = through_end_of_function(sources["go_" + variant], "if ysec < startSec {")
    leap = through_end_of_function(sources["go_calendar"], "func isLeap(")
    file = work / f"{variant}.go"
    file.write_text("\n".join([GO_WRAPPER, calculation, leap, GO_DRIVER]))
    instants = (0, 6047999, 6048000, 26783999, 26784000, 31449601)
    cases = list(product(range(1600, 2401), instants))
    inputs = "".join(f"{year} {elapsed}\n" for year, elapsed in cases)
    result = subprocess.check_output(["go", "run", file], input=inputs, text=True)
    for args, line in zip(cases, result.splitlines(), strict=True):
        expect_equal("period_end", args, target(*args), int(line))
    return len(cases)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=ROOT / "target/expression-sources/blobs")
    parser.add_argument("--offline", action="store_true", help="Require all pinned files in the cache.")
    options = parser.parse_args()
    sources = pinned_sources(options.cache, options.offline)
    counts = {"Redis": 0, "FastLED": 0, "Go": 0}
    with TemporaryDirectory(prefix="gpp-upstream-") as temp:
        work = Path(temp)
        for variant in ("starter", "reference"):
            rng = random.Random(43107)
            counts["Redis"] += audit_redis(work, sources, variant, rng)
            counts["FastLED"] += audit_led(work, sources, variant, rng)
            counts["Go"] += audit_go(work, sources, variant)
    for project, count in counts.items():
        print(f"{project}: {count:,} native comparisons")
    print(f"Total: {sum(counts.values()):,} comparisons, zero mismatches")


if __name__ == "__main__":
    main()
