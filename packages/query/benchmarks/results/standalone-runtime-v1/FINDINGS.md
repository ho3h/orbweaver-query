# Standalone public runtime campaign v1

All 189 isolated workers completed and the replay verified every worker identity,
output digest, aggregate and gate. All strategies and repetitions serialize
identical full results, including candidate IDs, scores, request order and bags.
The three graph/model pairs come from the verified public reproduction pipeline;
no research-directory modules or artifacts are required.

Median warm batch time including complete JSON serialization:

| Evidence seed | Interleaved256 consecutive | Grouped | Speedup |
| --- | ---: | ---: | ---: |
| 71 | 79.012 ms | 18.482 ms | 4.28x |
| 83 | 83.023 ms | 19.670 ms | 4.22x |
| 97 | 96.920 ms | 21.793 ms | 4.45x |

Each condition contains 15 measured batches across three fresh worker processes.
Grouping reduces expansions from 256 to 32 for these 256 distinct head/relation
queries. The primary gate requires at least 1.25x over consecutive caching on
each seed; all pass. Across single, distinct256, clustered256 and hubs16, grouped
execution ranges from 2.9% faster to 1.3% slower. All pass the predeclared 15%
regression ceiling. Larger 1,024-row interleaved windows show 4.28–4.39x speedups.
Identical-request workloads show 1.19–1.68x from avoiding repeated score calls.

Peak client process RSS across all strategies/workloads is 61.7–100.8 MiB.
The report includes all inference/serialization samples, median/p95 batch times,
separate import and graph/model preparation, first-batch measurements, outer
process wall time, memory and reuse counters. Worker-entry-to-first-result
measurements exclude interpreter startup; outer process wall includes warm-up
and five measured batches. Neither should be relabeled as population request
latency. Benchmarks retain complete batches; streaming memory is a separate case.

Scope: three transductive evidence samples of one 40,559-node WN18RR graph family,
three fixed learned models, CPU execution on the recorded local environment.
The fixture sources are selected from IDs/degrees without consulting predictions
or held-out labels. These measurements exclude database export, network transfer
and the caller's application work. They support source-sharing benefits in this
workload, not a universal end-to-end graph-query speedup or model-quality claim.

The earlier runtime-v1b/v2/v3 campaigns retain the legacy implementation comparison
and their regressions. This campaign compares three current packed strategies
using standalone public artifacts and a larger scope of seeds and windows.

Reproduce after completing the model-card reproduction commands:

```sh
python packages/query/benchmarks/standalone.py freeze runtime-run --model-run model-run
python packages/query/benchmarks/standalone.py execute runtime-run
python packages/query/benchmarks/standalone.py verify runtime-run
```

Install the local package before invoking the harness. Freeze copies the complete
runtime and harness; later workers use only those frozen copies. Use a fresh
directory for another run. Reports, protocol, source and all 189 raw worker JSON
observations are preserved here; numeric graph/query artifacts are regenerated.
