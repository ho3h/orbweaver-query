# Corrected stage target preparation: development iteration 5

All **324 workers completed**, with matching ordered bags, support and provenance.
Maximum score difference is **2.6645352591003757e-15**. Graphs, models, queries,
arms and analysis are unchanged from iteration 4. The source now checks whether
each compatible model actually exposes a target-union builder before calling it.
Both complete campaigns, totaling 648 workers, are retained.

**Competitive parity remains open.** Automatic execution measures **0.785x**
against the strongest of four manual controls, conditional process-bootstrap 95%
interval **[0.700, 0.811]**: about **27% greater geometric request latency**.
Including additional setup for one request gives **0.672x**, interval
**[0.601, 0.704]**. The preceding campaign measured 0.789x and 0.678x respectively.
These are development results on a fixed mix, not independent application confirmation.

## All declared conditions

Each time is the median of three process medians, with three fresh-request samples
per process. Every invocation starts with empty answer and intermediate-state
caches. Nine of twelve conditions return rows; empty outcomes remain included.

| Graph / shape / threshold | Rows | Automatic ms | Best manual ms | Winner | Overhead | Prefix / coalesced |
|---|---:|---:|---:|---|---:|---:|
| collaboration / one_expansion / 0.0 | 154 | 7.562 | 5.567 | manual_coalesced | 35.8% | 0.820x |
| collaboration / one_expansion / 0.2 | 64 | 1.903 | 1.569 | manual_targeted | 21.3% | 0.996x |
| collaboration / two_expansions / 0.0 | 864 | 21.002 | 20.197 | manual_prepared | 4.0% | 0.983x |
| collaboration / two_expansions / 0.2 | 0 | 0.641 | 0.337 | manual_targeted | 90.4% | 0.811x |
| friendship / one_expansion / 0.0 | 1310 | 339.273 | 302.951 | manual_prepared | 12.0% | 0.846x |
| friendship / one_expansion / 0.2 | 674 | 168.093 | 156.821 | manual_coalesced | 7.2% | 1.208x |
| friendship / two_expansions / 0.0 | 3212 | 107.937 | 87.613 | manual_coalesced | 23.2% | 0.951x |
| friendship / two_expansions / 0.2 | 0 | 0.267 | 0.190 | manual_prepared | 40.9% | 1.256x |
| communication / one_expansion / 0.0 | 1146 | 143.367 | 109.618 | manual_coalesced | 30.8% | 0.932x |
| communication / one_expansion / 0.2 | 54 | 17.264 | 15.855 | manual_prepared | 8.9% | 0.868x |
| communication / two_expansions / 0.0 | 15248 | 383.363 | 314.263 | manual_coalesced | 22.0% | 1.090x |
| communication / two_expansions / 0.2 | 0 | 0.261 | 0.169 | manual_targeted | 54.2% | 0.993x |

Nine conditions regress by more than 10%; only collaboration/two-expansions/0.0
is within 5% of the best control. No condition establishes an automatic-execution
win. The manual controls include exact targeting, full-feature/score reuse,
prefix reuse and stage-target coalescing using the same new primitive.

## Work reduction does not establish a latency gain

The descriptive prefix / coalesced ratio is **0.970x** across all conditions:
coalescing is nominally about 3% slower, consistent with no aggregate benefit in
iteration 4 (0.990x). The six conditions that do not prepare state still have
different timings despite executing essentially the same code. Small process
sample counts and variability prohibit interpreting every ratio as a causal effect.

| Condition with target preparation | Union type visits | Prefix type visits | Union retained bytes | Prefix retained bytes |
|---|---:|---:|---:|---:|
| collaboration / two_expansions / 0.0 | 28070 | 49678 | 18128 | 17952 |
| friendship / one_expansion / 0.0 | 1656246 | 2588262 | 91944 | 323232 |
| friendship / one_expansion / 0.2 | 925142 | 1369998 | 29416 | 105696 |
| friendship / two_expansions / 0.0 | 213954 | 503250 | 97896 | 107616 |
| communication / one_expansion / 0.0 | 990478 | 1234446 | 85040 | 163104 |
| communication / two_expansions / 0.0 | 246910 | 2466606 | 257536 | 57888 |

The largest communication case cuts counted type visits by about **90%**, from
2,466,606 to 246,910, but measures only **1.090x** prefix / coalesced latency.
Type visits count inspected adjacency symbols, including edges filtered before
weighted accumulation. They are not FLOPs or a direct prediction of elapsed time.
Coalescing adds union planning, retained features and subset construction. On that
case it retains 257,536 numeric bytes versus 57,888 for prefixes. Both stay below
16 MiB; Python containers and transient arrays are excluded, while worker RSS is
reported separately in the raw records.

The separate fresh-prefix / retained-prefix ratio is **1.178x** descriptively.
That comparison disables target coalescing in both arms and uses the same prefix
completion kernel. It must not be confused with the coalescing comparison.

## Implementation and remaining work

Target preparation computes exact features for targets already present in a
bounded stage, then supplies subsets to scoring batches. Domains, compatible
feature identities and numeric retention limits are checked; incompatible new
domains rebuild state. Prepared state is discarded at the root-window boundary.
Fallbacks retain source-only preparation for backends without a target builder.
Final model-specific scores remain under the separate answer-cache contract.

Internal execution also avoids redundant owned-row copies, repeated terminal
projections, physical-stage reconstruction and recursive profile serialization.
Correctness tests preserve validation-before-execution and atomic cache writes.
The first campaign exposed a missing optional-capability guard; the fix has a
regression test and this campaign freezes the corrected implementation.

Profiling still identifies model-kernel work, binding validation, row assembly
and serialization as material costs. Further work should measure actual expensive
operations and execution overhead, rather than optimize the visit counter alone.
A prepared execution plan with charged setup and array-based kernel/binding work
is a concrete next direction. Broader inference operators, matched GDS quality
and cost, update/resource workloads and the compatibility matrix remain required.

## Validation and reproducibility

- Source: **166 tests passed**, four optional tests skipped.
- Wheel built from the sdist: **164 tests passed**, six optional tests skipped,
  independently on Python 3.13 / NumPy 2.5.3 / Neo4j driver 6.3.1 and Python 3.11 /
  NumPy 1.26.4 / Neo4j driver 5.28.0.
- **Three live Neo4j 5.26 tests passed in each installed environment**, including
  target coalescing across scoring batches and a native Cypher expansion check.
- Independent walk enumeration, exact feature-subset checks, domain changes,
  compatible backends, retention limits, uncached targets and pending-answer
  exclusion are covered. Pinned Ruff 0.16.9 passes.
- All **23 current implementation/protocol/artifact files** match frozen inputs.
- Both new archives verify and restore; their summary/bootstrap analyses reproduce
  `results.json` byte for byte from the restored raw workers.
- The preceding-head GitHub compatibility matrix was refused before execution
  by account billing; these local checks do not claim that matrix passed.

Manifest SHA-256:
`7ec5864c1bb5022c05b2332a148fe6bf1c780a0558f940b68408f24006d1ca88`.

```sh
python packages/query/benchmarks/v1/plan_archive.py verify \
  packages/query/benchmarks/results/graph-pipeline-development-v5
python packages/query/benchmarks/v1/plan_archive.py restore \
  packages/query/benchmarks/results/graph-pipeline-development-v5 \
  --output /tmp/graph-pipeline-v5-replay --with-workers
python /tmp/graph-pipeline-v5-replay/graph_pipeline.py summarize \
  /tmp/graph-pipeline-v5-replay
```

Every raw worker, source file, protocol, input and analysis artifact is retained
under checksums. Confirmation labels remain sealed and all 1.0 gates remain open.
