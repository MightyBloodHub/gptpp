# GPT++ website

The GPT++ website is served as static files. The build copies the site's HTML, CSS and JavaScript, the shared brand artwork and theme, and the charts and CSV from the historical maintenance benchmark. [Project website](https://gptpp.sandoog.co/) · [Benchmark data and methods](../bench/expression/README.md#charts-and-data)

From the repository root, build and preview the site locally.

```sh
sh website/build.sh
python3 -m http.server 8080 --bind 127.0.0.1 --directory target/website
```

Open [the local preview](http://127.0.0.1:8080/). To publish an update, stage the contents of `target/website` in a new release under `/opt/gptpp/releases/` on the Sandoog host. Verify the release files, switch the `/opt/gptpp/current` symlink to the new release, and check the public URL. The previous release directory can be used for rollback.
