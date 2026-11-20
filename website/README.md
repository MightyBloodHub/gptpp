# GPT++ website

The GPT++ website is served as static files. The build copies the site's HTML, CSS and JavaScript, the shared brand artwork and theme, the browser verifier and its worker, and the charts and CSV from the historical maintenance benchmark. [Project website](https://gptpp.sandoog.co/) · [Benchmark data and methods](../bench/expression/README.md#charts-and-data)

From the repository root, build and preview the site locally.

```sh
sh website/build.sh
python3 -m http.server 8080 --bind 127.0.0.1 --directory target/website
```

Open [the local preview](http://127.0.0.1:8080/). The Trace tab illustrates `target/debug/gpp trace examples/add.gpp --function add --call main`. Run it from the repository root to inspect the full JSON.

The [finite-contract playground](https://gptpp.sandoog.co/#finite-contracts) starts with the complete `examples/reservations/booking.gpp` module. The preset menu also loads `examples/capacity.gpp`. The static build embeds the exact repository sources with Python 3. Source text runs locally in a dedicated browser worker. The playground allows up to 32 KiB of UTF-8 source and 10,000 assignments, and terminates a worker after eight seconds. A budget-limited compiler report and a browser timeout are distinguishable in the result panel. Preview on localhost or HTTPS so the worker can compute the source revision.

The normal site build verifies the checked-in WebAssembly compiler and its Rust sources against `website/playground/verify.sha256`. To regenerate it after compiler changes and compare eleven reports with the native CLI, including the reservation module, its double-release defect and an exhausted assignment budget, run from the repository root.

```sh
rustup target add wasm32-unknown-unknown
sh website/playground/build.sh
cargo build --locked --offline
node website/playground/check.mjs
sh website/build.sh
```

To publish, build from the Git revision being released with `GPP_SITE_REVISION=$(git rev-parse HEAD) sh website/build.sh`. The release links its reports and source to that exact commit. Connect to the origin serving `gptpp.sandoog.co` and confirm that `/opt/gptpp/current` points to the previous website release. Stage the contents of `target/website` in `/opt/gptpp/releases/<release>/website`, verify their checksums, then atomically switch `/opt/gptpp/current` to that directory. Check the public HTML and assets against the build. The previous release directory remains available for rollback.
