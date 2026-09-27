# Stronger composed-plan controls: development iteration 3

All **864 workers** completed and agreed on output rows, ordering, duplicates,
null/support status and provenance. Maximum score difference was
1.1102230246251565e-15. This iteration tests persistent plan caching and adaptive
structural preparation against stronger full-cache target lookup, separately
ordered operators and selective-first pair execution. The frozen mix still has
three graphs, four candidate patterns, two plan shapes and three process repeats.

The stronger controls materially reduce the apparent advantage. The earlier
3.30x ratio against cold full-source LRUs is not the result against the strongest
currently observed cold competitor. Warm cached plans also remain too slow on
filtered workloads. Gate A stays open.

## Fixed candidate/control comparisons

A ratio above 1 favors the candidate. Each condition uses its fastest declared
control; geometric means cover the same 24 conditions. The candidate is fixed
across conditions, not retrospectively selected. Setup includes calibration and
preparation, while common graph/model loading is excluded for every arm.

| Candidate and control regime | Steady-state ratio | 1 request, setup charged | 10 requests | 100 requests | 1,000 requests |
|---|---:|---:|---:|---:|---:|
| Ordered plan / strongest cold control | 1.089x | 0.463x | 0.906x | 1.053x | 1.085x |
| Cold cached plan / strongest cold control | 1.036x | 0.452x | 0.869x | 1.004x | 1.032x |
| Warm cached plan / strongest warm control | 0.803x | 0.776x | 0.791x | 0.820x | 0.817x |
| Ordered fused / separately ordered | 1.171x | 1.259x | 1.209x | 1.187x | 1.174x |
| Ordered fused / fused declared order | 1.408x | 0.568x | 1.130x | 1.353x | 1.401x |

The cold control set includes independent plans, separately ordered plans,
selective-first pair execution and full-source LRUs with 64 KiB/16 MiB numeric
budgets. Warm controls include warm pair caching, warm 16 MiB full-source LRU
and oracle working-set precomputation. Numeric LRU budgets exclude Python
containers and transient arrays; process RSS is recorded separately.

Conditional 95% process-bootstrap intervals for steady-state ratios are
[1.0792, 1.0947] for ordered/cold, [1.0260, 1.0405] for cached-cold/cold, and
[0.7995, 0.8140] for cached-warm/warm. These condition on the fixed development
inputs and implementation choices, and do not establish performance on new
applications. `comparison.json` retains every condition and all amortization
regimes. The analysis script and declaration were copied and hashed before
starting the timing workers; both are retained in this archive.

## Regressions and the next implementation target

Three ordered-plan conditions exceed 10% regression against the strongest cold
control, all with the resource-allocation filter and selective-first pair
execution as the winner:

| Condition | Ordered plan | Pair control | Plan latency overhead |
|---|---:|---:|---:|
| Communication, many targets | 1.303 ms | 0.581 ms | 124% |
| Collaboration, many targets | 1.858 ms | 1.311 ms | 42% |
| Collaboration, interleaved | 2.437 ms | 2.127 ms | 15% |

The cold cached plan also regresses on these three conditions. Warm cached
plans exceed 10% regression in all twelve filtered conditions; the aggregate
0.803x ratio corresponds to about 25% greater geometric latency. For example,
the communication many-target request takes 0.770 ms versus 0.323 ms for the warm
pair pipeline. It returns zero rows, which remains part of the declared mix.

The profiler/code explain an actionable inefficiency: a fused structural group
constructs later predictions even for rows rejected by its resource-allocation
filter. Sharing source preparation does not require eagerly scoring/materializing
all operators. Default declared group order also forces calibration to move an
unfiltered path operator after the only filtered group, although that move needs
no sampled cost estimate. These are implementation hypotheses for the next
iteration; this archive makes no claim that a subsequent change fixes them.

## Reproduction and scope

`workers.jsonl.gz` retains all 864 exact worker records, with per-record hashes.
`ARCHIVE.json` protects the frozen sources/inputs, results, workers and declared
analysis. Archive verification succeeded. Restore and rerun from the repository:

```sh
python packages/query/benchmarks/v1/plan_archive.py verify \
  packages/query/benchmarks/results/plan-development-v3
python packages/query/benchmarks/v1/plan_archive.py restore \
  packages/query/benchmarks/results/plan-development-v3 \
  --output /tmp/plan-v3-replay --with-workers
python /tmp/plan-v3-replay/plan_runtime.py summarize /tmp/plan-v3-replay
python /tmp/plan-v3-replay/plan_comparison.py /tmp/plan-v3-replay \
  /tmp/plan-v3-replayed-comparison.json
```

The restore includes the original comparison file; choose a fresh output path
for recomputation. These are development workloads, not production-query or
confirmation evidence. Graph/model-update costs and broader memory-pressure
workloads remain outstanding, along with the separate native Neo4j comparison.
