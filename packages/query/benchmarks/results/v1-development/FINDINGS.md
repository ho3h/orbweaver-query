# First 1.0 development checkpoint — 2026-09-26

The 1.0 acceptance contract remains open. This checkpoint improves exact runtime
execution; it does not establish new prediction quality, GDS superiority, Quail
performance parity, or general query-optimizer completeness.

## Runtime result

In iteration 4, exact bound-target expansion is **2.00x faster geometrically**
across 24 fixed graph/workload conditions than the fastest measured on-demand
control for each condition. The controls include full source grouping, 64 KiB
and 16 MiB feature/score LRU caches, and full/LRU variants that reject self-pairs
and existing edges before inference. Nine arms, three graph families, eight
workloads and three fresh processes per condition produce **648 worker runs**.
All output metadata, order, bags, support and null status agree. Maximum absolute
score difference is **8.88e-16** (declared numerical tolerance 1e-12).

The fully supported distinct-target workload is useful evidence that this is
more than skipping obviously unsupported rows:

| Graph | Rows, all supported | Best on-demand control | Target-aware | Speedup |
| --- | ---: | ---: | ---: | ---: |
| WordNet evidence | 128 | 49.74 ms | 6.97 ms | 7.14x |
| Movies | 128 | 10.02 ms | 4.06 ms | 2.47x |
| Scientific collaboration | 113 | 51.64 ms | 12.56 ms | 4.11x |

The aggregate exploratory bootstrap interval is **1.989–2.020x**, conditional on
these workloads and three process medians per arm. This narrow interval does not
measure generalization to new hardware, graph families or confirmation data.
These are development workloads used during implementation, not untouched tests.
Movies and collaboration use deterministic random coefficients for runtime
validation; they are not transferred or newly trained prediction models.

The smallest workloads expose remaining overhead. Two unsupported single-row
cases take roughly 11 microseconds versus 7 microseconds in the guarded reference.
Duplicate unsupported batches take about 0.29 ms versus 0.25–0.26 ms. A many-target
collaboration batch is about 13% slower than its best control (0.59 versus 0.52 ms).
See the complete per-condition results; no adverse result was removed.

## Persistent caching and precomputation

A caller-owned, entry-bounded `BindingCache` reuses exact pair scores across
requests. Keys include graph and model identities; replacement cannot yield stale
scores. Duplicate requests are deduplicated within a window, then restored in
input order. Unsupported scores are cached without becoming negative facts.

Warm pair caching substantially reduces repeated inference, but an oracle lookup
table built for the entire known source/relation working set remains faster:
roughly 0.05 ms for 128 prepared lookups versus 0.17 ms through the validated public
binding API. The oracle does not repeat schema validation and knows the future
working set. Its construction cost and retained numeric data are reported
separately; the Python dictionary overhead is reflected only in process RSS.
This is a useful warm lower bound, not evidence that preparation is free.
The on-demand aggregate above does **not** include this warm oracle.

## Iteration history

1. Target expansion alone: 315 workers, 21 conditions, 2.48x aggregate against
   the original on-demand controls. No persistent pair cache.
2. Added pair caching and duplicate-request reuse: 441 workers, 21 conditions,
   2.59x aggregate against those same controls.
3. Added stronger guarded baselines and a fully supported workload: 648 workers,
   24 conditions, 1.72x aggregate. This exposed avoidable unsupported-request overhead.
4. Added the cheap rejection capability to the runtime: 648 workers, 24 conditions,
   2.00x aggregate. All four complete frozen runs remain archived.

Changing candidate construction in iteration 3 changes the workload inventory;
iterations 1/2 and 3/4 are not paired speedup measurements. Only 3/4 share the same
candidate input construction. Improvements must still pass an independent
confirmation campaign, real database workflows, update workloads and composed plans.

## Current GDS baseline is executable

A disposable Neo4j Community **2026.09.0** plus GDS **2026.09.0** runs native
FastRP features, logistic-regression/random-forest model selection, and exhaustive
link prediction successfully. The probe used a 300-vertex, 3,541-edge induced
collaboration graph only to validate the native API. Its internal GDS AUCPR is
not comparable to Orbweaver's earlier recall metric and is not a competitive
result. Jar/distribution checksums and the complete probe are retained here.
The helper now supports isolated GDS plugin loading, explicit heap sizing and the
new server entrypoint, without reading or altering an existing database.

## Data, replay and next gates

WordNet is the previously reproduced seed-71 evidence/model snapshot. Movies is
the previously pinned public fixture and random-weight oracle check. Collaboration
comes from [SNAP ca-GrQc](https://snap.stanford.edu/data/ca-GrQc.html): 5,242 vertices
and 14,484 non-self undirected pairs after deduplicating directions and removing
12 self-pairs. Full source identities and input hashes are in the manifests.
The common `inputs/` directory stores exact numeric graph/model artifacts for all
four runs; query rows are stored with each run. Third-party data retains the
original providers' terms and attribution; our package license does not relicense it.

Restore and rerun a frozen campaign from the repository root:

```sh
python packages/query/benchmarks/v1/replay.py \
  packages/query/benchmarks/results/v1-development/targeted-development-v4 replay-run
python replay-run/targeted.py execute replay-run
python replay-run/targeted.py summarize replay-run
```

`workers.jsonl.gz` retains every original worker outcome, timing sample, output
record and profile. `ARCHIVE.json` records its checksum. The restore command
verifies every frozen input/source hash; a restored worker was exercised locally.
No final confirmation split has been evaluated for 1.0.

Next required work: matched outer-held-out prediction tasks against tuned native
GDS; an additional useful model backend; validated multi-operator plans and shared
feature contracts; adaptive preparation/caching under updates and budgets; then
confirmation and real Neo4j end-to-end results. Quail's LLM/GPU throughput remains
a separate matched-hardware evaluation, not a ratio against these CPU path scores.
