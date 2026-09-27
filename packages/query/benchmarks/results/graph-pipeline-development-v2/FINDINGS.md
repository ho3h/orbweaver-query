# Prepared model state on fresh graph queries: development iteration 2

All **216 workers completed**, with matching ordered bags, score support and
provenance. Maximum score difference was **2.6645352591003757e-15**. Nine of the
twelve declared conditions return results, including up to 15,248 rows. The
previous campaign, including its failures, remains unchanged.

**Competitive parity is still not established.** Automatic execution has a
**0.655x** geometric speed ratio against the strongest of three manual controls,
conditional 95% process-bootstrap interval **[0.610, 0.670]**. That corresponds
to about **53% greater geometric request latency**. Charging additional setup to
one request gives **0.729x**, interval **[0.682, 0.750]**. Manual controls now use
the existing packed evidence and no longer build a separate adjacency index.

## Full declared condition table

Times are medians across three process medians, with three fresh-request timed
samples per process. Ratios above one favor automatic execution. All request
caches start empty; ordinary reuse within each request is allowed equally.

| Graph / shape / threshold | Rows | Automatic ms | Best manual ms | Winner | Automatic overhead | Disabled-preparation / automatic |
|---|---:|---:|---:|---|---:|---:|
| collaboration / one_expansion / 0.0 | 154 | 7.982 | 7.174 | manual_prepared | 11.3% | 0.981x |
| collaboration / one_expansion / 0.2 | 64 | 1.963 | 1.755 | manual_prepared | 11.8% | 0.909x |
| collaboration / two_expansions / 0.0 | 864 | 21.197 | 17.705 | manual_prepared | 19.7% | 1.269x |
| collaboration / two_expansions / 0.2 | 0 | 0.680 | 0.341 | manual_prepared | 99.3% | 1.028x |
| friendship / one_expansion / 0.0 | 1310 | 324.941 | 273.829 | manual_prepared | 18.7% | 2.052x |
| friendship / one_expansion / 0.2 | 674 | 192.151 | 171.263 | manual_prepared | 12.2% | 1.785x |
| friendship / two_expansions / 0.0 | 3212 | 104.309 | 89.503 | manual_prepared | 16.5% | 1.632x |
| friendship / two_expansions / 0.2 | 0 | 0.409 | 0.136 | manual_prepared | 200.9% | 0.891x |
| communication / one_expansion / 0.0 | 1146 | 183.164 | 126.990 | manual_prepared | 44.2% | 1.698x |
| communication / one_expansion / 0.2 | 54 | 37.971 | 15.170 | manual_prepared | 150.3% | 1.031x |
| communication / two_expansions / 0.0 | 15248 | 424.076 | 354.020 | manual_prepared | 19.8% | 2.301x |
| communication / two_expansions / 0.2 | 0 | 0.355 | 0.133 | manual_targeted | 166.8% | 1.061x |

Every condition is more than 10% slower than its strongest manual control.
The current results cannot be compared directly with the previous 0.525x
aggregate as a before/after speedup: candidate generation, thresholds and
controls changed. All-condition parity remains open.

## What the preparation ablation establishes

The descriptive geometric ratio for disabled-preparation / automatic is **1.314x**.
The largest ratio is 2.301x for communication/two-expansions/threshold 0.0.
The smaller or empty cases sometimes regress; all appear above. This ablation
compares the legacy target kernel with prepared execution, so it combines
intermediate-state reuse with differences in the completion kernel. It does not
isolate the latency contribution of reuse alone. A fresh-prefix-per-batch arm
would be required for that stronger attribution.

The preparation primitive is also available to the manual control. That control
wins eleven conditions, while manual targeted execution wins the remaining
empty condition. This avoids presenting a kernel improvement available to all
executors as evidence of planner superiority.

| Nonempty multi-batch condition | Prefix builds / hits | Retained prefix bytes | Type visits, automatic | Type visits, disabled preparation |
|---|---:|---:|---:|---:|
| collaboration / two_expansions / 0.0 | 2 / 2 | 17952 | 49678 | 61830 |
| friendship / one_expansion / 0.0 | 5 / 5 | 323232 | 2588262 | 2870492 |
| friendship / one_expansion / 0.2 | 2 / 2 | 105696 | 1369998 | 1499470 |
| friendship / two_expansions / 0.0 | 2 / 6 | 107616 | 503250 | 523976 |
| communication / one_expansion / 0.0 | 4 / 4 | 163104 | 1234446 | 1254978 |
| communication / two_expansions / 0.0 | 2 / 48 | 57888 | 2466606 | 2588704 |

The byte column counts retained numeric arrays, not total process memory or
temporary objects. `results.json` retains per-arm peak RSS and all work counters.
The same model/evidence and full answer contract apply to every arm.

## Next implementation evidence

The communication one-expansion selective case is especially informative:
automatic execution performs no cross-batch preparation and takes 37.971 ms,
while manually preparing one source once takes 15.170 ms. Both execute almost
the same number of type visits. The prepared completion kernel filters a node's
adjacency once before processing its path prefixes, whereas the ordinary target
kernel repeats that condition inside its prefix loop. That code difference is a
concrete next optimization to isolate; it is not proof of causation from timing
alone. The remaining composed-execution overhead also needs profiling after
kernel choices are matched.

A separate independent walk-enumeration test confirms that reusable two-hop
state avoids repeated prefix work across different targets without an answer
cache. Other tests cover exact feature arrays, compatible coefficient models,
numeric retention limits, eviction, graph identity, immutable arrays and explicit
resource failures. These are mechanism/correctness checks, not speed claims.

## Reproduction

Manifest SHA-256:
`aac2b68616b436797c772cefb4c0202893c4139b5a7c7d716d8f5aae554f7a5d`.
Source, protocol, inputs, controls and analysis were frozen before execution.
No post-collection analysis replacement was needed. All 216 raw worker records
are retained exactly in `workers.jsonl.gz` under `ARCHIVE.json` checksums.

```sh
python packages/query/benchmarks/v1/plan_archive.py verify \
  packages/query/benchmarks/results/graph-pipeline-development-v2
python packages/query/benchmarks/v1/plan_archive.py restore \
  packages/query/benchmarks/results/graph-pipeline-development-v2 \
  --output /tmp/graph-pipeline-v2-replay --with-workers
python /tmp/graph-pipeline-v2-replay/graph_pipeline.py summarize \
  /tmp/graph-pipeline-v2-replay
```

This is development evidence. Confirmation labels remain sealed; no GDS quality,
native database latency, direct Quail parity or general novelty claim follows.
All release gates remain open.
