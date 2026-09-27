# A stronger native GDS control

2026-09-26. The same native GDS model returns the same recommendation answers in
**6.846 seconds instead of 31.755 seconds** using small per-source result queues.
The descriptive ratio is **4.638x**. This improves our GDS baseline; it is not an
Orbweaver speedup, a general GDS result or a closed release gate.

The [predeclared bounded protocol](../../v1/GDS_QUEUE_DIAGNOSTIC.md) uses the
friendship graph, 64 sources, top-16 recommendations and one configured thread.
One fresh native ARM Neo4j/GDS 2026.09.0 process trains one FastRP64/logistic
regression pipeline. Both arms use that model and the same complete evidence
graph. The refitted scores also match the preceding worker exactly (maximum
absolute difference 0.0). No expensive random-forest explanation applies to
this selected model.

| Native request | Median seconds | Measured requests | Result queue capacity |
|---|---:|---:|---:|
| Global exhaustive output, then per-source ranking | 31.755200 | 3 | 256,664 |
| Singleton-source exhaustive output, exact adaptive ranking | 6.846461 | 3 | 32 per source |

Each arm has one preceding warmup. Every request matched the independent ranking
of the full raw score matrix, covering 256,664 directed candidates / 254,658
unique undirected predictions. The per-source requests needed one adaptive round,
64 native procedure calls and 2,048 returned pairs. Cutoff ties trigger additional
fetches when needed; live adversarial fixtures exercised that behavior at one and
four threads. Equal scores use rounded-12-decimal values and stable application IDs.

The native queue [implementation at the matching source commit](https://github.com/neo4j/graph-data-science/blob/1317dc9fcc12322d55c11dc598f024debeea18c8/core/src/main/java/org/neo4j/gds/core/utils/queue/BoundedLongLongPriorityQueue.java)
inserts into sorted arrays and shifts their suffixes. For this global capacity
and prediction count, the source-derived lower bound is 790,465,562,424 logical
copied bytes. That is not measured DRAM traffic or an attribution of elapsed
time. The [exhaustive predictor](https://github.com/neo4j/graph-data-science/blob/1317dc9fcc12322d55c11dc598f024debeea18c8/procedures/pipelines-facade/src/main/java/org/neo4j/gds/procedures/pipelines/ExhaustiveLinkPrediction.java)
also checks pair positions outside the selected source domain before actual
scoring. Per-source requests change traversal repetition, feature preparation,
queue sizes and output assembly together. This diagnostic identifies a stronger
request formulation; it does not isolate a queue kernel's causal speedup.

Setup remains visible and separate: database startup 5.629s, import 2.762s,
labels/projection 2.499s, fitting 36.029s and the independent full-score audit
36.764s. Both timed arms include read-only adapter/EXPLAIN checks and normalized
JSON output. The per-source arm pays repeated pipeline preparation; it does not
assume hidden intermediate caching. Singleton labels are prepared for this fixed
owned fixture; broader request/setup economics require separate validation.

The consequence is to replace the weak reference before any new full matched
campaign, check other graph/thread settings, and examine approximate-search
quality/cost tradeoffs separately. One process with three samples is not a
confidence interval. The [interrupted attempt](../gds-application-interrupted-v1/FINDINGS.md)
is preserved without an aggregate claim. No confirmation data were opened.

## Evidence and reproduction

The 35-file `evidence.tar.gz` contains frozen source, protocol, graph/development
inputs, previous scores, the current complete score matrix, both request outputs,
model-selection record, all samples, setup timings and logs. `ARCHIVE.json`
indexes the bytes. Frozen manifest SHA256:
`4c44a85d970206ba569ff5ac03be661f1cbbeb86ceeb9d73dd93d9da9471ac4b`.

From `packages/query`:

```sh
python benchmarks/v1/gds_queue_archive.py verify benchmarks/results/gds-queue-diagnostic-development-v1
python benchmarks/v1/gds_queue_archive.py restore benchmarks/results/gds-queue-diagnostic-development-v1 --output /tmp/gds-queue-evidence
```

These commands verify bytes and the result envelope, including exact agreement
between retained request outputs. They do not run a database or recompute scores.
For numerical replay, load `graph.npz`, development `sources` and `scores.npz`
with the frozen package, then call frozen `gds_ranking.rank_scores(scores, graph,
sources, 16)`; compare the result to both saved outputs. That replay was performed
after archive restoration and reproduces both outputs exactly.

To repeat timing, copy only `manifest.json` and the files indexed by its `files`
map to a new directory. Set all six numeric-library thread ceilings from frozen
`gds_quality.THREADS` to 1, then run its frozen `gds_queue_diagnostic.py worker`
with `--neo4j-home`, `--java` and `--gds-jar` matching the manifest runtime.
The worker refuses a changed native runtime and uses its own disposable database.
Do not overwrite the retained results or run other benchmark/test jobs concurrently.
