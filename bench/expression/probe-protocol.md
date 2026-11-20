# Persistent compiler evaluation

Compare the public repair and distinguishing-input commands from revision 245cb7e with their current versions. Both use debug builds made with the pinned Rust toolchain on the same host. This measures authoring latency and CPU time within GPT++.

The repair roster contains all three expression fixtures and all three earlier upstream-transfer fixtures. Supply every public example and the default 512-edit budget, using the offline list mode. The distinguishing-input roster contains all three frozen task menus and all supplied pools from the previous distinguishing-input study. It runs each full menu once, without requesting an expected result.

Run three repetitions of every workload and alternate the old/current execution order by repetition. Measure elapsed time and child-process CPU time for the complete public CLI invocation. Each invocation uses a fresh temporary directory. Require parsed JSON outputs to match exactly across versions and across repetitions, including candidates, order, tested count, faults, stop reason and chosen question. Any mismatch fails the comparison. No model runs and no withheld labels influence either version.

Report each workload, both medians and the observed ratio. Report the sum of per-workload medians as a summary with equal weight per workload. Keep raw observations, source fingerprints, compiler fingerprints, platform and command versions. These tasks are development fixtures. This comparison establishes implementation behavior and host-specific speed, with no cross-language ranking.
