# GPT++ website

The GPT++ website is served as static files. The build copies the site's HTML, CSS and JavaScript, the shared brand artwork and theme, and the charts and CSV from the historical maintenance benchmark. [Project website](https://gptpp.sandoog.co/) · [Benchmark data and methods](../bench/expression/README.md#charts-and-data)

From the repository root, build and preview the site locally.

```sh
sh website/build.sh
python3 -m http.server 8080 --bind 127.0.0.1 --directory target/website
```

Open [the local preview](http://127.0.0.1:8080/). The Trace tab illustrates `target/debug/gpp trace examples/add.gpp --function add --call main`. Run it from the repository root to inspect the full JSON.

To publish, build from the Git revision being released with `GPP_SITE_REVISION=$(git rev-parse HEAD) sh website/build.sh`. The release links its reports and source to that exact commit. Connect to the origin serving `gptpp.sandoog.co` and confirm that `/opt/gptpp/current` points to the previous website release. Stage the contents of `target/website` in `/opt/gptpp/releases/<release>/website`, verify their checksums, then atomically switch `/opt/gptpp/current` to that directory. Check the public HTML and assets against the build. The previous release directory remains available for rollback.
