# Composed-plan runtime development protocol

Declared before timing this campaign. This extends, and does not replace, the
1.0 acceptance contract. No final confirmation outcomes are used.

Use the three frozen outer-training graphs and fitted path models from the GDS
development comparison. Each has a distinct graph family. Compare two logical
shapes: (1) resource allocation, Adamic–Adar and common-neighbor predictions;
(2) a path prediction followed by those three predictions, with a resource
allocation threshold of 0.2. Return every named prediction plus head, relation,
target and input ordinal. The threshold is a fixed ranking filter, not a quality
or confidence policy. It is chosen before this runtime measurement.

Four input patterns: 128 distinct sources; 256 interleaved rows on 16 sources;
256 targets from one source; 128 rows on eight highest-degree sources. Choose
sources and targets using seed 8103. Three quarters of endpoints come from a
two-step random walk; one quarter are uniform over the full declared node domain.
Do not remove unsupported, adjacent, self, repeated or zero-score pairs. Include
an additional null row. Calibration uses 64 independently sampled rows from the
same input-only generator, with seed 8104, and is charged separately.

Compare separate target-aware operators, fused target-aware operators, and fused
operators ordered using measured cost/selectivity. Strong controls use a shared
full-source feature/score LRU at 64 KiB and 16 MiB, cold; the 16 MiB LRU warm; and
an oracle full-source working-set precomputation with a 1 GiB numeric cap. The
LRU shares features across compatible models and scores by model/relation. It
uses the same planner, validation, metadata and serialization boundary. All these
controls also get measured operator ordering. Precomputation knows the workload's
source/relation set and prepares all candidate scores before filtering. Report
its preparation separately and do not present warm lookup as free cold execution.
Also include the public binding API's warm pair cache, with the selective model
first. Charge its prewarming and retain the same returned rows and metadata.

Freeze source, graph/model/query artifacts, protocol and randomized job order
before execution. Run three separate processes per condition and arm, one warmup
and three measured repetitions. Limit numerical-library threads to one. Do not
run the timing campaign concurrently with the GDS training jobs. The timing
boundary includes row validation, inference, filtering, materializing records and
JSON serialization. Loading/imports are excluded equally. Compare all outputs
within 1e-12 absolute and relative tolerance and preserve support/null statuses,
order, duplicates and provenance. Keep every failed attempt.

Report median elapsed time, calibration, preparation, numeric cache bytes,
process peak RSS and raw samples. Report cold/warm regimes separately; show
setup-amortized cost at 1, 10, 100 and 1,000 requests. No isolated speedup in this
development campaign completes the larger 1.0 gate. Snapshot/model updates,
independent confirmation and the aligned Neo4j GDS application boundary remain
separate required work.

## Declared second measured iteration

After preserving the complete v2 campaign, add four controls: separately executed
operators with measured ordering; the public binding API's selective-first cold
pair cache; and cold/warm persistent pair caching inside QueryPlan. Keep all data,
query shapes, seeds, thresholds and process/sample counts unchanged. There are
now 864 workers. Both public binding controls execute the same valid workload;
their late validation of subsequently filtered rows is not a substitute for the
composed planner's all-declared-input validation semantics on malformed inputs.

Strengthen the full-source controls by projecting their already prepared features
and scores to requested targets with sorted index lookup. Continue charging full
preparation and retaining full candidate scores in the cache. This removes the
previous common planner's per-request full candidate dictionary construction and
full-score validation overhead on warm lookups. Preserve the original campaign.

The new runtime shares validation for identical input column triples, supports
the caller-owned BindingCache with whole-window commit, and lets NeighborhoodModel
choose an exact full traversal for many targets when a topology-only work estimate
favors it and all limits allow it. The estimate charges sixteen units per bound
intersection plus endpoint degrees, versus two units per graph node plus two-hop
neighbor visits for full preparation. This is a heuristic, not an optimality or
quality claim. Freeze these choices before the next timings; repeat only after
the long native GDS retry stops to avoid local CPU contention.
