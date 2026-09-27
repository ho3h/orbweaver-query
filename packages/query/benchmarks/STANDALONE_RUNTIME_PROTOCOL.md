# Standalone public runtime campaign v1

Use all three verified graph/model exports from the standalone public WN18RR
model-reproduction pipeline (seeds 71, 83, 97). Check the parent manifest, result,
verification and every selected artifact identity before copying. No imports or
data dependencies from the research directory. This broadens evidence/model
seeds within one graph family; it is not cross-domain confirmation.

Compare independent expansion, a one-source consecutive cache, and bounded
grouping. All use exactly the same packed graph and learned model. Windows bound
source grouping; the benchmark intentionally collects complete request batches
and serializes every candidate ID/score. This measures retained-batch use, not
bounded streaming memory. The earlier campaign retains the external legacy
implementation reference; this campaign tests the current execution strategies.

For each evidence seed, choose sources using only its node IDs and degrees,
with NumPy RNG seed 20260926 + evidence seed. Define these workloads before
measurement: single request; 256 distinct sources; 32 clustered sources with
eight unique relation requests each; the same 256 requests interleaved by
relation; 256 identical requests; the 16 highest-degree sources; and 128 sources
with eight unique relation requests interleaved across a 1,024-row window.
Default window is 256; the last workload uses 1,024 for all arms.

Run three fresh processes per seed/workload/strategy: 189 workers, in fixed
random order. Each worker restricts native threads to one before importing NumPy,
records process RSS/import/model-and-graph preparation, performs one warm-up,
then measures five complete batches. Record inference and full JSON serialization
separately and jointly, all raw samples, profile counters, and outer process wall
time. A fresh session call resets reuse each batch. Verify all complete output
digests agree across arms and repetitions. Grouping must not change scores,
candidate support, order, duplicate requests or serialized results.

Primary gate: grouped execution including serialization is at least 1.25x faster
than consecutive caching on interleaved256 in each of the three evidence seeds.
Regression gate: grouped median batch time is at most 1.15x consecutive caching
on single, distinct256, clustered256 and hubs16 for each seed. Report failures
without changing thresholds. Duplicate and 1,024-window results test mechanisms;
they are not substituted for a failed primary gate.

Report median and p95 batch time across 15 warm samples per condition, full cold
process wall observations, separately measured import and artifact preparation,
inference/serialization and peak process RSS. A single-source fixture is one
request identity, not a population latency distribution. These timings exclude
database extraction and network transfer. End-to-end Cypher timing remains a
separate release requirement.

Record the first batch's inference/serialization and the interval from worker
entry through its first serialized result. That interval excludes interpreter
startup and this script's standard-library imports. Outer process wall time
includes all six batches and must not be labeled first-request latency.
