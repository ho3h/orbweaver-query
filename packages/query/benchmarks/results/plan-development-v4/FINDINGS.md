# Filter pushdown: development iteration 4

All 864 frozen workers completed. Output rows, duplicates, ordering, null/support
status and provenance agreed; maximum absolute score difference was
1.1102230246251565e-15. The campaign includes three graphs, four candidate
patterns, two plan shapes, twelve arms and three process repetitions.

This campaign tests default filter-first execution and lazy scoring within shared
feature groups. Only the explicitly ordered arms calibrate; the full-source
controls also receive the default filter-first improvement. The analysis script
was frozen in the original manifest before workers ran. All gates remain open.

## Fixed comparisons

Ratios above one favor the candidate. The strongest declared control is selected
per condition, while each candidate remains fixed. Common model/graph loading is
excluded for every arm. Setup includes arm-specific preparation and calibration.

| Comparison | Steady state | Setup + 1 request | 10 | 100 | 1,000 | Conditional 95% interval, steady state |
|---|---:|---:|---:|---:|---:|---|
| Default / strongest cold | 1.159x | 1.163x | 1.163x | 1.160x | 1.159x | [1.1361, 1.1620] |
| Calibrated / strongest cold | 1.158x | 0.444x | 0.902x | 1.095x | 1.148x | [1.1472, 1.1605] |
| Cached cold / strongest cold | 1.141x | 1.145x | 1.145x | 1.142x | 1.141x | [1.1303, 1.1438] |
| Cached warm / strongest warm | 0.972x | 1.459x | 1.416x | 1.176x | 1.025x | [0.9644, 0.9793] |
| Fused ordered / separate ordered | 1.234x | 1.280x | 1.244x | 1.236x | 1.234x | [1.2253, 1.2564] |
| Calibrated / default | 0.999x | 0.382x | 0.776x | 0.944x | 0.991x | [0.9921, 1.0168] |

Intervals resample processes conditionally on the fixed development workloads
and selected implementation. They are not confirmation on unseen applications.
The uncached default improves over the strongest cold control by 1.159x in the
aggregate. The warm ratio corresponds to about 2.9% greater geometric latency.
Calibration gives no aggregate steady-state benefit beyond the static rule on
this mix, and its setup cost makes short runs substantially worse.

## Remaining regressions

Every default or warm-cached condition with over 10% latency overhead follows.
The calibrated arm also regresses on communication/many-targets/mixed-filter
by about 20%; cached-cold has no condition beyond 10%. Full condition records,
including setup-charged comparisons, are retained in `comparison.json`.

| Candidate | Graph / pattern / shape | Candidate ms | Control ms | Overhead |
|---|---|---:|---:|---:|
| fused | communication / many_targets256 / mixed_filter | 0.654 | 0.554 | 18.1% |
| cached_warm | collaboration / distinct128 / mixed_filter | 0.409 | 0.368 | 11.2% |
| cached_warm | collaboration / hubs128 / mixed_filter | 0.378 | 0.344 | 10.0% |
| cached_warm | friendship / distinct128 / mixed_filter | 0.444 | 0.387 | 14.7% |
| cached_warm | friendship / interleaved256 / mixed_filter | 0.822 | 0.735 | 11.7% |
| cached_warm | friendship / hubs128 / mixed_filter | 0.372 | 0.329 | 13.2% |
| cached_warm | communication / distinct128 / mixed_filter | 0.354 | 0.292 | 21.0% |
| cached_warm | communication / interleaved256 / mixed_filter | 0.594 | 0.476 | 24.9% |
| cached_warm | communication / many_targets256 / mixed_filter | 0.413 | 0.322 | 28.2% |

## Interpretation and priority

A warm pair cache stores completed answers. Its comparison measures request
overhead once inference has already been done. It is a useful control, not the
contribution that would make a graph query engine compelling. Quail instead
compares query-controlled model execution with tuned inference engines that
already enable prefix/KV caching. These are different regimes.

Retain the result and regressions without making stored-answer microbenchmarks
the next optimization priority. The next development target is richer composed
graph-inference queries, first-execution gains against optimized native/batched
pipelines, and ablations that show which inference work disappears. This result
does not establish parity with Quail, novel prediction methods or release readiness.

## Reproduction

`ARCHIVE.json` protects the frozen source, inputs, analysis and all 864 raw worker
records in `workers.jsonl.gz`. Frozen manifest SHA-256:
`aee27b957a872fac4f1991234077ed45398b151675d3aa693dd3901cd707ceef`.

```sh
python packages/query/benchmarks/v1/plan_archive.py verify \
  packages/query/benchmarks/results/plan-development-v4
python packages/query/benchmarks/v1/plan_archive.py restore \
  packages/query/benchmarks/results/plan-development-v4 \
  --output /tmp/plan-v4-replay --with-workers
python /tmp/plan-v4-replay/plan_runtime.py summarize /tmp/plan-v4-replay
python /tmp/plan-v4-replay/plan_comparison.py /tmp/plan-v4-replay \
  /tmp/plan-v4-replayed-comparison.json
```
