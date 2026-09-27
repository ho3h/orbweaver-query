# Stage target preparation: development iteration 4

All **324 workers completed**, with matching ordered bags, score support and
provenance; maximum score difference **2.6645352591003757e-15**. Graphs, models
and query files are byte-identical to iterations 2 and 3. Nine of twelve
conditions return results. Every request starts with empty answer and state caches.

**Parity remains open.** Automatic execution measures **0.789x** against the
best of four manual controls, conditional process-bootstrap interval
**[0.713, 0.836]**, or about **27% greater geometric request latency**.
With additional setup charged to one request the ratio is **0.678x**, interval
**[0.620, 0.723]**. Manual setup no longer includes unnecessary plan construction.

## Complete condition table

| Graph / shape / threshold | Rows | Automatic ms | Best manual ms | Winner | Overhead | Prefix / coalesced |
|---|---:|---:|---:|---|---:|---:|
| collaboration / one_expansion / 0.0 | 154 | 7.707 | 6.767 | manual_coalesced | 13.9% | 0.958x |
| collaboration / one_expansion / 0.2 | 64 | 2.212 | 1.655 | manual_coalesced | 33.7% | 0.840x |
| collaboration / two_expansions / 0.0 | 864 | 27.004 | 21.400 | manual_prepared | 26.2% | 0.752x |
| collaboration / two_expansions / 0.2 | 0 | 0.651 | 0.336 | manual_targeted | 93.6% | 0.902x |
| friendship / one_expansion / 0.0 | 1310 | 341.165 | 301.630 | manual_coalesced | 13.1% | 0.958x |
| friendship / one_expansion / 0.2 | 674 | 193.776 | 192.226 | manual_coalesced | 0.8% | 1.055x |
| friendship / two_expansions / 0.0 | 3212 | 102.145 | 99.412 | manual_targeted | 2.7% | 1.272x |
| friendship / two_expansions / 0.2 | 0 | 0.257 | 0.181 | manual_coalesced | 41.9% | 1.149x |
| communication / one_expansion / 0.0 | 1146 | 146.302 | 120.505 | manual_coalesced | 21.4% | 1.217x |
| communication / one_expansion / 0.2 | 54 | 21.042 | 16.198 | manual_coalesced | 29.9% | 0.765x |
| communication / two_expansions / 0.0 | 15248 | 444.582 | 378.174 | manual_coalesced | 17.6% | 1.160x |
| communication / two_expansions / 0.2 | 0 | 0.284 | 0.189 | manual_targeted | 50.5% | 1.016x |

Ten conditions regress by more than 10%; the two remaining conditions are within
5% of the best manual control. No condition establishes an automatic-execution win.

## What changed and what the evidence supports

The model can prepare exact features for the union of targets already present in
a bounded stage, then supply subsets to scoring batches. Retention includes the
numeric target and feature arrays, respects source/graph/feature identities and
ends with the root window. A new manual control uses the same primitive, hint and
retention budget. Existing targeted, full-feature and prefix controls remain.
Internal execution also avoids redundant owned-row copies, final projections,
physical-plan reconstruction and recursive profile serialization.

Coalescing has **no aggregate latency benefit** in this campaign: prefix /
coalesced geometric latency is **0.990x**. The largest communication case reduces
counted type visits from **2,466,606 to 246,910**, but its latency ratio is only
**1.160x**. A visit count includes inspected adjacency symbols, including ones
filtered before typed accumulation; it is not a FLOP count or direct runtime
prediction. Union preparation, subset construction, row handling and serialization
all have costs. The fresh-prefix / retained-prefix ablation measures **1.187x**
descriptively. Neither ablation establishes competitive parity or novelty.

## Compatibility follow-up

After measurement, a new regression test exposed an optional-backend edge case:
compatible feature/preparation identities do not imply that every model exposes
a target-union builder. The frozen source calls that builder without checking its
availability when another model has supplied a shared target hint. The built-in
benchmark models do not exercise this case; all recorded benchmark answers match.
The working implementation adds a capability guard and the failing regression
test now passes. Iteration 5 repeats this complete frozen workload on the corrected
source. These iteration-4 bytes and outcomes remain unchanged.

## Reproduction

Manifest SHA-256:
`a3ace769d5e65d20d23b8274f9d1b4758a0471f1e9c91446d59f783444fe5ef0`.

```sh
python packages/query/benchmarks/v1/plan_archive.py verify \
  packages/query/benchmarks/results/graph-pipeline-development-v4
python packages/query/benchmarks/v1/plan_archive.py restore \
  packages/query/benchmarks/results/graph-pipeline-development-v4 \
  --output /tmp/graph-pipeline-v4-replay --with-workers
python /tmp/graph-pipeline-v4-replay/graph_pipeline.py summarize \
  /tmp/graph-pipeline-v4-replay
```

All raw success records, source, inputs, protocol and analysis are retained under
checksums. Restoring the archive and rerunning the summary/bootstrap reproduced
`results.json` byte for byte. No confirmation labels were opened. All 1.0 release
gates remain open.
