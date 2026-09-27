# Real trained-model Cypher workflow

All 36 fresh clients completed and the verifier reproduced the measurements and
gate. Every client exported exactly the preselected model's evidence snapshot;
all candidate bindings and scored JSON outputs matched bitwise across strategies
and repetitions. The imported disposable Neo4j 5.26 fixture contains 40,559 nodes
and 69,420 directed edges. Fixture import took 10.50 s, outside query timing.

Median warm time includes parameterized Cypher compilation/execution and Bolt
transfer, inference, and complete scored-row JSON serialization. The immutable
evidence snapshot is prepared once per client; inference caches reset each batch.

| 256-request workload | Independent | Consecutive cache | Multi-source LRU | Grouped |
| --- | ---: | ---: | ---: | ---: |
| Distinct sources | 111.880 ms | 112.383 ms | 112.924 ms | 113.026 ms |
| Clustered shared sources | 88.769 ms | 30.827 ms | 31.106 ms | 32.659 ms |
| Interleaved shared sources | 95.760 ms | 95.042 ms | 33.600 ms | 30.433 ms |

The declared primary gate passes: grouped warm workflow is 3.12x faster than
consecutive caching on interleaved requests (minimum 1.25x). The stronger LRU
control captures nearly the same benefit. Its 256-source/16-MiB numeric cache
fits this workload; grouping should not be advertised as 3x faster than general
caching. Clustered requests show grouped about 5.9% slower than consecutive
caching; distinct sources show about 0.6% overhead. Preserve those observations.

For interleaved requests, grouped medians are 18.727 ms for the candidate query
and transfer, 11.355 ms for inference, and 0.390 ms for serialization. Consecutive
inference is 74.867 ms. LRU inference is 11.743 ms. Phase medians need not sum to
the median complete workflow. Each condition has 15 measured batches across
three fresh client processes; all raw observations and p95 values are retained.

Initial evidence query/transfer/snapshot construction takes roughly 0.92–1.12 s
at the condition-median level, dominating a first call. Observed worker-entry to
first result spans 1.12–2.70 s, including imports/connection/model and artifact
validation. It excludes interpreter startup; outer process wall observations
include all six batches. This supports a prepared-snapshot workflow, not a claim
of a large speedup when the complete graph must be exported for every query.

Both grouped and LRU perform 32 expansions on the interleaved workload; the
consecutive cache performs 256. LRU retains 615,880 bytes of numeric features and
scores there (3,548,424 bytes for distinct256), excluding Python containers and
outputs. The largest single source feature array is 44,440 bytes on shared-source
workloads. These quantities are not directly interchangeable cache/memory totals.
Peak client process RSS is approximately 120 MiB, reaching 122.1 MiB for the
distinct-source LRU; no substantial process-memory win is claimed here.

The candidate query selects a minimum-ID, nonadjacent two-hop endpoint using
graph evidence alone. Three distinct-source requests have null targets and remain
null scored rows. No predictions or held-out labels selected these fixtures.
This checks query composition and runtime behavior, not recommendation quality.
Results are loopback, single-client, one graph/model observations; they do not
cover remote-network costs, persistent cross-batch caches or concurrent services.

Reproduce after the standalone runtime campaign:

```sh
python packages/query/benchmarks/neo4j_workflow.py freeze workflow-run --runtime-run runtime-run
python packages/query/benchmarks/neo4j_workflow.py execute workflow-run \
  --neo4j-home /path/to/neo4j --java /path/to/java
python packages/query/benchmarks/neo4j_workflow.py verify workflow-run
```

The executor always creates a fresh temporary database on a random loopback
port and removes it on completion. It accepts no existing database destination.
