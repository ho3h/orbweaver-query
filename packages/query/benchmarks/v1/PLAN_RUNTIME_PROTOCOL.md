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

## V3 analysis declaration, before execution

`plan_comparison.py` reports five fixed comparisons: ordered plans and cold
cached plans each against the best of separate, separately ordered, uncached
pair execution, and both cold full-source LRUs; warm cached plans against the
best of warm pair caching, warm full-source LRU and known-working-set
precomputation; ordered versus separately ordered to isolate fusion; and ordered
versus fused declared-order execution to isolate ordering. It never selects the
candidate arm retrospectively per workload.

Report steady-state request latency and calibration/preparation amortized over
1, 10, 100 and 1,000 requests. For amortized results, take the median of each
process's request latency plus its own setup/request-count, preserving their
association. Report each >10% regression. Use 10,000 independent resamples of the
three process medians per arm/condition, seed 8107, recomputing the strongest
control per resample. Intervals condition on this fixed development mix and do
not measure new-application generalization. Confirmation and update/memory
workloads remain separate gates.

The v3 runtime manifest was already frozen. Its additional analysis declaration
records that manifest's hash and a copied analysis script's hash before the first
timing worker executes; it does not alter the frozen runtime or queries.

## V4 declaration: default filter pushdown

V3 exposed three cold regressions and twelve warm filtered regressions against
selective-first pair execution. The next iteration applies filters within shared
feature groups before later scores/output construction, retains preparation for
one source at a time, and places filtered groups before unfiltered groups without
requiring sampled statistics. Whole-window input validation and deferred cache
commit remain mandatory.

Use the same 24 conditions, twelve arms and three process repetitions (864
workers). Only the explicitly `ordered` and `separate_ordered` arms calibrate.
The `fused` arm now represents the default static filter ordering; `cached_*`
and full-source cache/precompute controls also use their new default static
ordering without calibration. Thus the controls benefit from the same filter
pushdown and avoid unnecessary setup too. The pair controls are unchanged.

Add a fixed `default_vs_cold` comparison against the same strongest cold control
set. The former ordered/fused comparison becomes `calibration_vs_default`, since
default execution now already moves the only filtered group first in this query
mix. Preserve the other comparisons, setup amortization, bootstrap procedure and
all adverse cases. Copy `plan_comparison.py` into the initial manifest so both
measurement and analysis code are frozen before execution. This remains a
reused development mix; no confirmation labels are opened.
