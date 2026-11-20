#!/bin/sh
# Prerequisite: rustup target add wasm32-unknown-unknown for the pinned toolchain.
set -eu
export LC_ALL=C
cd "$(dirname "$0")/../.."
toolchain=$(sed -n 's/^channel = "\([^"]*\)"$/\1/p' rust-toolchain.toml)
test -n "$toolchain"
out=$(mktemp website/playground/.verify.XXXXXX)
manifest=$(mktemp website/playground/.sha256.XXXXXX)
trap 'rm -f "$out" "$manifest"' EXIT
rustup run "$toolchain" rustc --edition=2024 --crate-type=cdylib --crate-name=gpp_playground \
  --target=wasm32-unknown-unknown --remap-path-prefix "$(pwd)=." \
  -C panic=abort -C opt-level=z -C lto=fat -C codegen-units=1 -C strip=symbols \
  website/playground/wasm.rs -o "$out"
chmod 644 "$out"
mv -f "$out" website/playground/verify.wasm
set -- rust-toolchain.toml src/*.rs src/*.c website/playground/wasm.rs \
  website/playground/build.sh website/playground/verify.wasm
if command -v sha256sum >/dev/null 2>&1; then
  sha256sum "$@" > "$manifest"
else
  shasum -a 256 "$@" > "$manifest"
fi
chmod 644 "$manifest"
mv -f "$manifest" website/playground/verify.sha256
