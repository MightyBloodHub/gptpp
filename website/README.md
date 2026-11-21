# GPT++ website

The GPT++ website is served as static files. The build copies the site's HTML, CSS and JavaScript, the shared brand artwork and theme, the browser verifier and its worker, and the charts and CSV from the historical maintenance benchmark. [Project website](https://gptpp.sandoog.co/) · [Benchmark data and methods](../bench/expression/README.md#charts-and-data)

From the repository root, build and preview the site locally.

```sh
sh website/build.sh
python3 -m http.server 8080 --bind 127.0.0.1 --directory target/website
```

Open [the local preview](http://127.0.0.1:8080/). The Trace tab illustrates `target/debug/gpp trace examples/add.gpp --function add --call main`. Run it from the repository root to inspect the full JSON.

The [finite-contract playground](https://gptpp.sandoog.co/#finite-contracts) starts with two formulas from a native search report for seven calibration readings. The checkbox supplies an eighth observation. The preset menu also loads the reservation ledger and eight-slot queue. Link to the booking example with `?example=booking#finite-contracts`. The static build embeds the exact repository sources with Python 3. Source text runs locally in a dedicated browser worker. The playground allows up to 32 KiB of UTF-8 source and 10,000 assignments, and terminates a worker after eight seconds. A budget-limited compiler report and a browser timeout are distinguishable in the result panel. Preview on localhost or HTTPS so the worker can compute the source revision.

The [makes10 preset](https://gptpp.sandoog.co/?example=makes10#finite-contracts) starts with the archived edit and runs the 24 public examples before checking interchangeability. “Try correct reference” verifies symmetry for all 576 ordered pairs. “Try weaker rule” runs the archived edit again with a property covering only the 24 pairs where the second argument is ten. The build embeds these expressions, obligations and replayed observations from the [development example](../examples/makes10/README.md).

The normal site build verifies the checked-in WebAssembly compiler and its Rust sources against `website/playground/verify.sha256`. To regenerate it after compiler changes and compare eighteen reports with the native CLI, including the packaged makes10 presets, the reservation module, its double-release defect and an exhausted assignment budget, run from the repository root.

```sh
rustup target add wasm32-unknown-unknown
sh website/playground/build.sh
cargo build --locked --offline
node website/playground/check.mjs
sh website/build.sh
```

To publish, build from the Git revision being released with `GPP_SITE_REVISION=$(git rev-parse HEAD) sh website/build.sh`. The release links current reports and source to that commit. Earlier studies link to their original release. Connect to the origin serving `gptpp.sandoog.co` and confirm that `/opt/gptpp/current` points to the previous website release. Stage the contents of `target/website` in `/opt/gptpp/releases/<release>/website`, verify their checksums, then atomically switch `/opt/gptpp/current` to that directory. Check the public HTML and assets against the build. The previous release directory remains available for rollback.
