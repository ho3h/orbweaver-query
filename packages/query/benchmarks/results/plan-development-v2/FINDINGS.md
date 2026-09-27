# Composed-plan development results

All 576 workers agree on row order, duplicates, null/unsupported status and model/
snapshot provenance, with maximum score difference 1.11e-15. The experiment spans
three public graphs, four synthetic candidate patterns, two composed query shapes,
eight strategies and three process repetitions. It ran after the GDS grid stopped.
This is development evidence; the 1.0 gates remain open.

Ordered target-aware plans have a 3.30x geometric-mean latency advantage over the
better cold shared full-source LRU (64 KiB or 16 MiB) across the fixed 24 conditions.
The conditional process-bootstrap interval is 3.28–3.30x. That narrow interval
represents resampling these process repetitions, not generalization to new graph
families or real query distributions. Calibration is excluded from that ratio.

Warm pair caching is fastest in every condition. Some warm full-source caches
also beat the planner substantially. The friendship many-target structural query
is 10.5% slower than the better cold full-source control (3.081 vs 2.788 ms).
Communication has smaller regressions on many-target queries. These adverse
results motivate persistent pair caching in QueryPlan and choosing preparation
based on target count/topology. Neither improvement is claimed by this campaign.

The controls share the same planner, metadata and serialization boundary; the
full-source LRU shares features across compatible models, caches model/relation
scores, and gets measured filter ordering. The warm public binding API control
uses an explicit pair cache and evaluates the selective model first. Precomputation
knows the working source/relation set, retains all candidate scores with a 1 GiB
numeric cap and reports construction separately. The byte limits exclude Python
objects and transient arrays; process peak RSS is retained in the raw records.
A 16 MiB cache can still thrash on a large working set. Full-source controls use
full candidate arrays through the common planner; further optimizing their target
lookup remains a possible stronger control.

Preparation/calibration and amortized costs at 1, 10, 100 and 1,000 requests are
in `results.json`. Warm controls must be charged their preparation when answering
cold-start questions. The table below shows query execution plus materialization/
JSON serialization only. Structural queries return all input rows; mixed queries
apply the fixed resource-allocation threshold 0.2 and return all four predictions.
The communication many-target mixed query returns zero rows, which is reported
rather than dropped from the workload mix. These filters have no quality claim.

| Graph | Workload | Shape | Output rows | Ordered plan ms | Best cold LRU ms | Warm pair ms |
|---|---|---|---:|---:|---:|---:|
| collaboration | distinct128 | structural | 129 | 1.994 | 32.417 | 0.969 |
| collaboration | distinct128 | mixed_filter | 19 | 3.748 | 42.411 | 0.357 |
| collaboration | interleaved256 | structural | 257 | 2.683 | 7.610 | 1.868 |
| collaboration | interleaved256 | mixed_filter | 38 | 2.779 | 10.310 | 0.670 |
| collaboration | many_targets256 | structural | 257 | 2.637 | 2.750 | 1.848 |
| collaboration | many_targets256 | mixed_filter | 31 | 2.230 | 4.268 | 0.599 |
| collaboration | hubs128 | structural | 129 | 1.535 | 4.661 | 0.954 |
| collaboration | hubs128 | mixed_filter | 18 | 12.446 | 62.967 | 0.351 |
| friendship | distinct128 | structural | 129 | 2.450 | 30.677 | 0.981 |
| friendship | distinct128 | mixed_filter | 22 | 108.873 | 942.687 | 0.386 |
| friendship | interleaved256 | structural | 257 | 3.393 | 7.993 | 1.927 |
| friendship | interleaved256 | mixed_filter | 41 | 110.230 | 459.165 | 0.740 |
| friendship | many_targets256 | structural | 257 | 3.081 | 2.788 | 1.957 |
| friendship | many_targets256 | mixed_filter | 55 | 12.011 | 40.796 | 0.824 |
| friendship | hubs128 | structural | 129 | 1.844 | 5.094 | 0.957 |
| friendship | hubs128 | mixed_filter | 16 | 138.621 | 511.021 | 0.329 |
| communication | distinct128 | structural | 129 | 2.585 | 11.798 | 0.972 |
| communication | distinct128 | mixed_filter | 11 | 34.681 | 346.994 | 0.286 |
| communication | interleaved256 | structural | 257 | 3.468 | 4.027 | 1.915 |
| communication | interleaved256 | mixed_filter | 13 | 34.047 | 197.859 | 0.483 |
| communication | many_targets256 | structural | 257 | 2.628 | 2.509 | 1.818 |
| communication | many_targets256 | mixed_filter | 0 | 1.913 | 1.797 | 0.320 |
| communication | hubs128 | structural | 129 | 1.878 | 2.596 | 0.962 |
| communication | hubs128 | mixed_filter | 32 | 97.142 | 345.779 | 0.464 |

## Retained evidence and replay

`manifest.json` pins the graph/model/query artifacts, source and randomized job
order. `workers.jsonl.gz` preserves the exact original bytes and SHA-256 of every
worker record, including samples, complete outputs, preparation and memory.
`ARCHIVE.json` checksums the frozen experiment payload. Restoring all 576 worker
files and rerunning the numerical summary produced a byte-identical results file.
`analysis.json` contains the conditional bootstrap method and adverse cases.

```sh
python packages/query/benchmarks/v1/plan_archive.py verify \
  packages/query/benchmarks/results/plan-development-v2
python packages/query/benchmarks/v1/plan_archive.py restore \
  packages/query/benchmarks/results/plan-development-v2 \
  --output /tmp/plan-replay --with-workers
python /tmp/plan-replay/plan_runtime.py summarize /tmp/plan-replay
```

Omit `--with-workers` and run `execute` followed by `summarize` for fresh processes.
The frozen campaign uses Unix process-RSS collection. The current harness also
runs timing/correctness on Windows, reporting RSS as unavailable there. That
portability fix does not alter the frozen measurements.

The earlier `plan-development-v1` directory was frozen but never timed; before
measurement, v2 added cheap pair rejection to both plans and full-source controls
and avoided recursive copying during result serialization. No measured failure
or regression was discarded. The [declared protocol](PLAN_RUNTIME_PROTOCOL.md)
and [acceptance contract](../../v1/ACCEPTANCE.md) define the wider remaining scope.
