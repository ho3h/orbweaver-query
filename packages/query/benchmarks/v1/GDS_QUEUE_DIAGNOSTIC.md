# Bounded native queue diagnostic

2026-09-26. This is a baseline investigation, not an Orbweaver speedup campaign.
The preceding 18-worker application attempt is interrupted and retained: four
workers completed, worker 4 was interrupted, and workers 5–17 were not attempted.
Do not summarize it as a complete application comparison.

The matching GDS 2026.09.0 source is commit
`1317dc9fcc12322d55c11dc598f024debeea18c8`. Its
[exhaustive predictor](https://github.com/neo4j/graph-data-science/blob/1317dc9fcc12322d55c11dc598f024debeea18c8/procedures/pipelines-facade/src/main/java/org/neo4j/gds/procedures/pipelines/ExhaustiveLinkPrediction.java)
loops over the upper triangle of the graph's node IDs and checks source/target
label restrictions before scoring. In the benchmark's Query-to-Node case, the
outer loop includes all nodes; source filtering does not avoid all pair-position
checks. This is distinct from the smaller number of actual model predictions.

More seriously, its
[bounded priority queue](https://github.com/neo4j/graph-data-science/blob/1317dc9fcc12322d55c11dc598f024debeea18c8/core/src/main/java/org/neo4j/gds/core/utils/queue/BoundedLongLongPriorityQueue.java)
inserts into sorted arrays. Every accepted prediction shifts array suffixes.
Setting global topN to the complete directed candidate count creates quadratic
copying even while the queue is not full. For M unique predictions and capacity B
(B >= M), the three 8-byte arrays copy at least
`24 * (M*B - M*(M+1)/2)` logical bytes. This is a source-derived lower bound on
array-copy volume, not measured DRAM traffic, FLOPs or a causal timing attribution.
Do not attribute all observed latency to this mechanism without a diagnostic.

Use friendship/one-thread, the first completed worker of the interrupted frozen
campaign, without selecting on speedup. Preserve its graph, sources, selected
FastRP64 pipeline, classifier-selection budget, seed, runtime and 8 GiB heap.
Freeze a new owned database and one trained model. Add singleton source labels
before GDS projection; these labels partition output requests, while Node covers
the same complete feature-evidence graph. Record label/projection setup separately.

Compare two native physical requests with the same trained model and output:

1. The original exhaustive global queue, retaining the full candidate count and
   doing per-source top-16 ranking in Cypher.
2. Exhaustive singleton-source requests batched through one Cypher UNWIND per
   adaptive round. Start with topN=min(32, per-source candidate count). Increase
   only unresolved sources until the lowest retained rounded score is strictly
   below the kth score, or the complete source domain is returned. Sort ties by
   stable application ID. This preserves exact top-16 results, including large
   tie groups and empty sources. It may repeat FastRP preparation; charge that
   cost rather than assuming the model-intermediate state is cached.

Stream full global scores once before timing and verify complete coverage.
Compare both arms with the independent client ranking of those scores, and
report whether the refitted model matches the prior worker's raw scores. Model
differences across separately fitted processes do not invalidate this within-model
diagnostic; both measured arms must use the same current model.

One database process, one warmup and three measured requests per arm, arm order
shuffled with seed 7620. Include the same read-only/EXPLAIN adapter boundary and
JSON serialization. Record all raw samples, outputs, adaptive-round counters,
model configuration and setup. No concurrent benchmark/test process. This is a
bounded descriptive probe, not a confidence interval, release gate, general GDS
claim or Orbweaver contribution. If this control is stronger, replace the weak
control before restarting a full matched comparison. Approximate-search quality/
cost tradeoffs remain a separate requirement.
