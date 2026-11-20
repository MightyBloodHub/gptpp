#!/bin/sh
set -eu

repo_dir=$(CDPATH= cd "$(dirname "$0")/.." && pwd)
source_dir="$repo_dir/website"
brand_dir="$repo_dir/brand"
benchmark_dir="$repo_dir/bench/expression/community"
output_dir="$repo_dir/target/website"

mkdir -p "$output_dir/assets/benchmarks"
install -m 644 "$source_dir/index.html" "$source_dir/styles.css" "$source_dir/site.js" "$output_dir/"
install -m 644 "$brand_dir/logo/gptpp-dark.svg" "$output_dir/assets/logo.svg"
install -m 644 "$brand_dir/logo/gptpp-mark.svg" "$output_dir/assets/mark.svg"
install -m 644 "$brand_dir/logo/favicon.ico" "$output_dir/favicon.ico"
install -m 644 "$brand_dir/theme.css" "$brand_dir/social-card.png" "$output_dir/assets/"
install -m 644 \
  "$benchmark_dir/acceptance.png" "$benchmark_dir/selection.png" "$benchmark_dir/token-cost.png" \
  "$benchmark_dir/benchmark-summary.csv" "$output_dir/assets/benchmarks/"

printf '%s\n' "$output_dir"
