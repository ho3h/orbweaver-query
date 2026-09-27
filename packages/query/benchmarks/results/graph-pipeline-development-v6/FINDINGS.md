# Binding deduplication: development iteration 6

All **360 workers completed**, with matching ordered bags, support and provenance.
Maximum score difference is **2.6645352591003757e-15**. Input graphs, trained models
and query files are unchanged. The ten arms add a rowwise ablation to the preceding
nine-arm protocol. Each request starts with empty answer and intermediate caches.

**This does not establish the required execution advantage.** Automatic execution
measures **0.749x** against the best of four manual controls, conditional process-
bootstrap interval **[0.673, 0.794]**: about **33.5% greater geometric latency**.
Including setup for one request gives **0.644x**, interval **[0.584, 0.689]**.
The rowwise / deduplicated ablation is only **1.018x** descriptively, with mixed
condition-level outcomes. Three process repetitions and their variability do not
establish a repeatable aggregate benefit. This is no basis for a novelty claim.

## All declared conditions

| Graph / shape / threshold | Rows | Automatic ms | Best manual | Manual ms | Overhead | Rowwise / deduplicated | Binding evaluations | Duplicates avoided |
|---|---:|---:|---|---:|---:|---:|---:|---:|
| collaboration / one_expansion / 0.0 | 154 | 8.962 | manual_coalesced | 5.400 | 66.0% | 0.775x | 76 | 93 |
| collaboration / one_expansion / 0.2 | 64 | 2.352 | manual_prepared | 1.783 | 31.9% | 1.072x | 37 | 42 |
| collaboration / two_expansions / 0.0 | 864 | 23.464 | manual_prepared | 20.146 | 16.5% | 1.036x | 213 | 703 |
| collaboration / two_expansions / 0.2 | 0 | 0.595 | manual_prepared | 0.339 | 75.8% | 0.875x | 11 | 25 |
| friendship / one_expansion / 0.0 | 1310 | 290.715 | manual_prepared | 264.146 | 10.1% | 1.189x | 661 | 667 |
| friendship / one_expansion / 0.2 | 674 | 199.219 | manual_coalesced | 176.631 | 12.8% | 1.193x | 354 | 338 |
| friendship / two_expansions / 0.0 | 3212 | 104.614 | manual_coalesced | 94.985 | 10.1% | 0.903x | 952 | 2332 |
| friendship / two_expansions / 0.2 | 0 | 0.298 | manual_targeted | 0.138 | 116.8% | 1.027x | 3 | 1 |
| communication / one_expansion / 0.0 | 1146 | 139.464 | manual_coalesced | 128.940 | 8.2% | 0.981x | 568 | 596 |
| communication / one_expansion / 0.2 | 54 | 17.186 | manual_coalesced | 16.604 | 3.5% | 1.034x | 44 | 28 |
| communication / two_expansions / 0.0 | 15248 | 321.070 | manual_coalesced | 330.941 | -3.0% | 1.124x | 6511 | 8847 |
| communication / two_expansions / 0.2 | 0 | 0.310 | manual_targeted | 0.139 | 122.1% | 1.099x | 3 | 1 |

Nine conditions exceed 10% overhead. Two are within 5% of the best manual time;
one of those has a nominal 3% advantage. Neither a broad win nor a repeatable 2x
practical-class advantage is established. Cross-campaign timing changes cannot
be attributed solely to this implementation change. The same-campaign ablation
isolates deduplication, while both automatic arms use the faster validation path.

## Interpretation and next action

The executor selects stable representatives of complete validated argument tuples
for each feature group in each scoring batch. It restores all surviving original
rows and payloads. Later groups merge into new mappings to prevent shared early
predictions from overwriting distinct later results. Relation/null patterns remain
distinct. Binding counters include unsupported and null inputs; reducing them is
not a reduction in model evaluations. Model-call/traversal parity is separately
covered by the ablation test. Prepared-feature and pair-score caches are unchanged.

The campaign was already running when the user requested an architectural reassessment.
Its adverse results are retained. The next milestone is the
[execution-thesis investigation](../../v1/EXECUTION_THESIS.md), not another full
campaign of small Python executor changes. Establish an application, dominant
avoidable cost and a causal graph/query inference mechanism before expanding
implementation. All existing acceptance gates remain open.

## Validation

- Source: **172 passed**, four optional skips.
- Wheel built from the sdist: **170 passed**, six optional skips, in each of
  Python 3.13 / NumPy 2.5.3 / Neo4j 6.3.1 and Python 3.11 / NumPy 1.26.4 / Neo4j 5.28.0.
- All **three live Neo4j tests pass in each installed environment**.
- Independent binding and graph oracles cover duplicate payloads, fused/unfused
  groups, differing later inputs, nulls, relation patterns, filtering and projection.
- Pinned Ruff 0.16.9 and whitespace checks pass.
- All 32 frozen source/protocol/input files match their current sources.
- The archive verifies and restores; summary/bootstrap results replay byte for byte.

Manifest SHA-256:
`e07a618812c08d89e7c5b7754d34f9fb2a8d05eb63afd18c9a9eb7bd319b7486`.

```sh
python packages/query/benchmarks/v1/plan_archive.py verify \
  packages/query/benchmarks/results/graph-pipeline-development-v6
python packages/query/benchmarks/v1/plan_archive.py restore \
  packages/query/benchmarks/results/graph-pipeline-development-v6 \
  --output /tmp/graph-pipeline-v6-replay --with-workers
python /tmp/graph-pipeline-v6-replay/graph_pipeline.py summarize \
  /tmp/graph-pipeline-v6-replay
```
