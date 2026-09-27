# Matched native Neo4j structural requests

All nine disposable database workers completed: three repetitions on each of
three public graphs, covering 432 physical request conditions. Every arm agreed
with the independent set oracle and the other arms on rows, ordering, duplicates,
null/support status and provenance. Maximum absolute score difference was
1.4210854715202004e-14. These are fixed development fixtures with supplied external
pair IDs, not a survey of arbitrary Cypher candidate queries or concurrent updates.

The measured boundary includes a read transaction, EXPLAIN, candidate execution,
Bolt transfer, scoring/filtering, common prediction metadata and JSON serialization.
All arms use the same client, fetch size and slotted query runtime. Local plans
read a complete exported immutable snapshot; native functions/Cypher read the
same static graph directly in Neo4j. Each condition has two warmups and five
measured requests in each database repetition. Raw samples and setup are retained.

## Observed application costs

The local cold-cache plan is 1.229x faster geometrically than the fastest of
native GDS, fused Cypher and selective Cypher across the fixed 24 conditions,
excluding export. The warm local plan is 0.859x as fast as the strongest warm
control including exact working-set precomputation, corresponding to about 16%
greater geometric latency. These measurements precede the next filter-pushdown
implementation; they do not validate that subsequent code.

| Regime | Request latency only | Export/preparation over 1 request | 10 requests | 100 requests | 1,000 requests |
|---|---:|---:|---:|---:|---:|
| Local cold cache versus strongest native control | 1.229x | 0.010x | 0.089x | 0.525x | 1.080x |
| Local warm cache versus strongest warm control | 0.859x | 0.010x | 0.089x | 0.550x | 0.868x |

Ratios above one favor the local plan. Snapshot export takes about 1.24 seconds
for collaboration, 2.51 seconds for friendship, and 1.19 seconds for communication
(medians across database repetitions). Native arms do not pay that cost. Shared
database startup/import is excluded from both sides. Thus a short-lived request
sequence favors native execution even when local inference itself is faster.

Examples retained in the raw report:

| Condition | Local cold request | Fastest native request |
|---|---:|---:|
| Collaboration, hubs, unfiltered | 8.206 ms | 14.812 ms (fused Cypher) |
| Friendship, hubs, filtered | 8.241 ms | 14.858 ms (fused Cypher) |
| Communication, interleaved, filtered | 20.109 ms | 13.312 ms (fused Cypher) |
| Communication, distinct, unfiltered | 15.613 ms | 13.775 ms (fused Cypher) |

The last two examples are >10% cold regressions. Several warm conditions also
regress against precomputed lookup. Some warm requests are slower than cold ones
in these observations, indicating substantial database/client timing variation;
cache hits are not a guarantee of lower observed wall time in a small sample.

## Uncertainty and reproduction

`analysis.json` provides descriptive whole-database bootstrap resampling, pairing
arms/conditions within each repetition and resampling separately by graph. With
only three database repetitions and re-selection of the fastest control in each
draw, the central 95% resampling range is [1.068, 1.214] for the cold ratio and
[0.771, 0.928] for warm. The cold point estimate lies outside that resampling
range; this small-sample, non-smooth best-control estimator does not support a
well-calibrated significance claim. At 1,000 requests the cold range spans parity.
The analysis was written after collection and is explicitly descriptive.

Python/Java peak RSS covers the entire database worker across all arms. It does
not establish a per-arm memory advantage. Neither these structural requests nor
the earlier all-score GDS stream timings prove learned-pipeline top-16 latency,
Quail throughput parity, or the broader 1.0 gates.

The archive retains all nine exact worker records, frozen code/inputs, native
function signatures, runtime artifact hashes and verified summaries. Verify and
restore with the common worker archive tool:

```sh
python packages/query/benchmarks/v1/plan_archive.py verify \
  packages/query/benchmarks/results/native-structural-development-v1
python packages/query/benchmarks/v1/plan_archive.py restore \
  packages/query/benchmarks/results/native-structural-development-v1 \
  --output /tmp/native-request-replay --with-workers
python /tmp/native-request-replay/structural_neo4j.py summarize /tmp/native-request-replay
```

The separate [correctness archive](../native-structural-verification-v1/README.md)
retains the pre-timing verification. No confirmation labels are present or loaded.
