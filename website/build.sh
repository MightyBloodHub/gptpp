#!/bin/sh
set -eu

repo_dir=$(CDPATH= cd "$(dirname "$0")/.." && pwd)
source_dir="$repo_dir/website"
brand_dir="$repo_dir/brand"
benchmark_dir="$repo_dir/bench/expression/community"
output_dir="$repo_dir/target/website"
revision=${GPP_SITE_REVISION:-}

if [ -n "$revision" ]; then
  case "$revision" in
    *[!0-9a-f]*) echo 'GPP_SITE_REVISION must contain only lowercase hex digits.' >&2; exit 1 ;;
  esac
  if [ "${#revision}" -ne 40 ]; then
    echo 'GPP_SITE_REVISION must be a full Git commit hash.' >&2
    exit 1
  fi
fi

if ! (
  cd "$repo_dir"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum -c website/playground/verify.sha256
  else
    shasum -a 256 -c website/playground/verify.sha256
  fi
) >/dev/null; then
  echo 'Browser compiler source or binary changed. Rebuild with sh website/playground/build.sh.' >&2
  exit 1
fi

mkdir -p "$output_dir/assets/benchmarks" "$output_dir/playground"
install -m 644 "$source_dir/contract-worker.js" "$output_dir/"
install -m 644 "$source_dir/playground/verify.wasm" "$output_dir/playground/"
install -m 644 "$source_dir/styles.css" "$source_dir/site.js" "$output_dir/"
python3 - "$repo_dir" "$output_dir/index.html" "$revision" <<'PYTHON'
from html import escape
from pathlib import Path
import sys

root, target, revision = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
page = (root / "website/index.html").read_text()
for marker, name in (("GPP_BOOKING_SOURCE", "reservations/booking.gpp"), ("GPP_QUEUE_SOURCE", "capacity.gpp")):
    if page.count(marker) != 1:
        raise SystemExit(f"expected one {marker} in the playground")
    page = page.replace(marker, escape((root / "examples" / name).read_text(), quote=False))
if revision:
    for kind in ("blob", "tree"):
        prefix = f"MightyBloodHub/gptpp/{kind}/"
        page = page.replace(prefix + "master/", prefix + revision + "/")
target.write_text(page)
PYTHON
install -m 644 "$brand_dir/logo/gptpp-dark.svg" "$output_dir/assets/logo.svg"
install -m 644 "$brand_dir/logo/gptpp-mark.svg" "$output_dir/assets/mark.svg"
install -m 644 "$brand_dir/logo/favicon.ico" "$output_dir/favicon.ico"
install -m 644 "$brand_dir/theme.css" "$brand_dir/social-card.png" "$output_dir/assets/"
install -m 644 \
  "$benchmark_dir/acceptance.png" "$benchmark_dir/selection.png" "$benchmark_dir/token-cost.png" \
  "$benchmark_dir/benchmark-summary.csv" "$output_dir/assets/benchmarks/"

printf '%s\n' "$output_dir"
