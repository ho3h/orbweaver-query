# Prediction-dependent graph expansion: development iteration 1

**The capability works, but the strongest manual pipelines are faster.** Of 72
workers, 69 completed with exactly matching scores, support/provenance and ordered
output bags. All three eager friendship/two-expansion workers failed explicitly
at the 100,000 intermediate-row bound. Automatic and both manual arms completed
every declared condition. Failed workers are retained verbatim, not counted as
correctness passes or assigned an invented latency.

## Matched fresh-request results

Every invocation starts with empty answer and feature caches. In-request reuse
is allowed equally. Times include result construction and JSON serialization;
immutable graph/model loading is common setup outside these request times.

| Graph / shape | Output rows | Automatic ms | Eager ms | Best manual ms | Manual winner | Automatic overhead |
|---|---:|---:|---:|---:|---|---:|
| collaboration / one_expansion | 0 | 0.533 | 1.007 | 0.250 | manual_targeted | 113.4% |
| collaboration / two_expansions | 0 | 0.468 | 8.315 | 0.126 | manual_targeted | 271.1% |
| friendship / one_expansion | 262 | 17.558 | 29.202 | 13.930 | manual_targeted | 26.0% |
| friendship / two_expansions | 500 | 31.635 | row-budget failure | 20.066 | manual_full_lru | 57.7% |
| communication / one_expansion | 0 | 0.605 | 9.324 | 0.400 | manual_targeted | 51.3% |
| communication / two_expansions | 0 | 0.521 | 622.244 | 0.261 | manual_targeted | 99.8% |

The fixed automatic candidate / strongest manual geometric speed ratio is
**0.525x**, conditional process-bootstrap 95% interval **[0.446, 0.602]**.
That is about 90% greater geometric request latency, with every condition more
than 10% slower than its strongest manual control. This evidence contradicts a
steady-state parity claim for the current implementation.

Charging extra per-arm setup to one request reverses the ratio to 22.77x
(interval [18.19, 24.67]), but the manual controls build an additional Python
adjacency index from canonical triples, costing roughly 30–151 ms. The automatic
executor uses the already available packed GraphSnapshot. That setup asymmetry
is an implementation choice in these controls, not a fundamental advantage.
A future strong control should traverse the existing packed representation too.
Do not use the setup-inclusive ratio as the release headline.

## Work avoided and limits of these workloads

| Graph / shape | Automatic typed edge visits | Eager typed edge visits | Best-manual typed edge visits |
|---|---:|---:|---:|
| collaboration / one_expansion | 0 | 84 | 0 |
| collaboration / two_expansions | 0 | 998 | 0 |
| friendship / one_expansion | 262 | 1392 | 262 |
| friendship / two_expansions | 762 | failed before a complete profile | 762 |
| communication / one_expansion | 0 | 1272 | 0 |
| communication / two_expansions | 0 | 73786 | 0 |

Predicate movement eliminates the same traversal work as a correctly hand-ordered
pipeline. The eager ablation demonstrates that mechanism; it does not establish
a novel optimization or a win against the strongest competitor. Four of six
conditions return no rows, so their large eager/automatic ratios would make a
particularly weak application story. Friendship produces 262 and 500 rows.
Its two-expansion manual full-feature control uses 20,300 model type visits
versus 40,408 for automatic target preparation, exposing another concrete gap.

Profiler inspection after collection identifies repeated planning/identity and
validation overhead in the empty-result cases, and explicit-path preparation as
the main expense in the nonempty friendship case. This diagnosis is not a timing
comparison. Next work should improve execution of nonempty composed workloads,
include a manual traversal control over packed evidence, and compare alternative
model-preparation strategies. Do not tune merely to the empty-result conditions.

## Reproduction and failure handling

The original protocol, implementation, models and inputs were frozen before
measurement; manifest SHA-256:
`fdcd803d6d6a34ee46a0fc8a264cae40882e5344260972790245e9af5c910230`.

The original summarizer assumed every worker completed. A separately retained
`graph_pipeline_analysis.py` was added after collection to accept missing eager
results while requiring complete primary arms. `ANALYSIS_RECEIPT.json` records
that exception and its source checksum. The declared primary comparisons and
bootstrap remain unchanged. `results.json` explicitly scopes score parity to
completed workers and includes all three failure traces.

`ARCHIVE.json` protects all frozen inputs, the supplementary analysis, results
and the exact bytes of all 72 successful/failed worker records in
`workers.jsonl.gz`. Verification and restoration preserve successes and failures.
Restore then reproduce the summary with:

```sh
python packages/query/benchmarks/v1/plan_archive.py verify \
  packages/query/benchmarks/results/graph-pipeline-development-v1
python packages/query/benchmarks/v1/plan_archive.py restore \
  packages/query/benchmarks/results/graph-pipeline-development-v1 \
  --output /tmp/graph-pipeline-v1-replay --with-workers
python /tmp/graph-pipeline-v1-replay/graph_pipeline_analysis.py summarize \
  /tmp/graph-pipeline-v1-replay
```

All release gates remain open. This is graph-query execution evidence, not
held-out prediction quality, native GDS latency or a direct Quail comparison.
