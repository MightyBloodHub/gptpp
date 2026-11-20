# Compiler evaluation latency

Three alternating repetitions of each complete public CLI command ran on the same host. Every parsed result matched exactly across versions and repetitions. The comparison includes source reads, process startup, candidate checking and execution.

| Command | Task | Previous median s | Current median s | Speedup | Previous CPU s | Current CPU s |
|---|---|---:|---:|---:|---:|---:|
| repair | redis_lru_timestamp | 6.427 | 0.180 | 35.72× | 6.034 | 0.173 |
| repair | fastled_fixed_scale | 2.956 | 0.149 | 19.89× | 2.751 | 0.142 |
| repair | go_footer_year_end | 3.601 | 0.164 | 21.97× | 3.355 | 0.157 |
| repair | upstream_linux_round_closest | 2.334 | 0.145 | 16.12× | 2.172 | 0.137 |
| repair | upstream_moment_month_length | 0.860 | 0.132 | 6.54× | 0.802 | 0.125 |
| repair | upstream_godot_rect_intersects | 7.354 | 0.268 | 27.39× | 6.849 | 0.262 |
| distinguish | redis_lru_timestamp | 0.446 | 0.098 | 4.55× | 0.411 | 0.092 |
| distinguish | fastled_fixed_scale | 4.068 | 0.104 | 39.18× | 3.748 | 0.097 |
| distinguish | go_footer_year_end | 0.096 | 0.095 | 1.01× | 0.092 | 0.089 |

The sum of workload medians fell from 28.143 to 1.334 seconds (21.10× faster). Menus and questions matched, so acceptance and model usage are unchanged by this optimization. Both versions used debug compiler builds. Timings depend on the host and workload.
