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

mkdir -p "$output_dir/assets/benchmarks"
install -m 644 "$source_dir/index.html" "$source_dir/styles.css" "$source_dir/site.js" "$output_dir/"
if [ -n "$revision" ]; then
  short_revision=$(printf '%.7s' "$revision")
  sed -e "s|MightyBloodHub/gptpp/blob/master/|MightyBloodHub/gptpp/blob/$revision/|g" \
      -e "s|MightyBloodHub/gptpp/tree/master/|MightyBloodHub/gptpp/tree/$revision/|g" \
      -e "s|commits/master/\">Scorecard source history|commit/$revision\">Scorecard source · $short_revision|" \
      "$source_dir/index.html" > "$output_dir/index.html"
fi
install -m 644 "$brand_dir/logo/gptpp-dark.svg" "$output_dir/assets/logo.svg"
install -m 644 "$brand_dir/logo/gptpp-mark.svg" "$output_dir/assets/mark.svg"
install -m 644 "$brand_dir/logo/favicon.ico" "$output_dir/favicon.ico"
install -m 644 "$brand_dir/theme.css" "$brand_dir/social-card.png" "$output_dir/assets/"
install -m 644 \
  "$benchmark_dir/acceptance.png" "$benchmark_dir/selection.png" "$benchmark_dir/token-cost.png" \
  "$benchmark_dir/benchmark-summary.csv" "$output_dir/assets/benchmarks/"

printf '%s\n' "$output_dir"
