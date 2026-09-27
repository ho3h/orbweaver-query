# Matched completion kernels and fresh-prefix ablation: iteration 3

All **252 workers completed**, with matching ordered bags, score support and
provenance. Maximum score difference was **2.6645352591003757e-15**. The nine
graph/model/query input files are byte-identical to iteration 2; all twelve
conditions and all strong controls remain in the comparison. Nine conditions
return results, with up to 15,248 rows. Every request starts with empty answer
and intermediate-state caches. Within-request reuse is allowed equally.

**Competitive parity remains open.** Automatic execution measures **0.684x**
against the strongest manual control, conditional process-bootstrap 95% interval
**[0.605, 0.753]**: about **46% greater geometric request latency**. Charging
additional setup to one request gives **0.763x**, interval **[0.635, 0.824]**.
These are development measurements, not confirmation or a Quail runtime comparison.

## Complete condition table

Times are medians of three process medians, each with three fresh-request samples.
Ratios above one favor automatic execution. The fresh-prefix column uses the same
completion kernel and eligibility heuristic, rebuilding rather than retaining
intermediate state. No result or workload was removed after measurement.

| Graph / shape / threshold | Rows | Automatic ms | Best manual ms | Winner | Automatic overhead | Fresh-prefix / automatic |
|---|---:|---:|---:|---|---:|---:|
| collaboration / one_expansion / 0.0 | 154 | 7.240 | 5.725 | manual_targeted | 26.5% | 0.959x |
| collaboration / one_expansion / 0.2 | 64 | 1.917 | 1.552 | manual_prepared | 23.5% | 1.129x |
| collaboration / two_expansions / 0.0 | 864 | 25.010 | 19.580 | manual_targeted | 27.7% | 1.295x |
| collaboration / two_expansions / 0.2 | 0 | 0.813 | 0.374 | manual_targeted | 117.3% | 1.190x |
| friendship / one_expansion / 0.0 | 1310 | 313.945 | 269.285 | manual_prepared | 16.6% | 1.532x |
| friendship / one_expansion / 0.2 | 674 | 168.144 | 196.408 | manual_prepared | -14.4% | 1.622x |
| friendship / two_expansions / 0.0 | 3212 | 125.823 | 90.479 | manual_targeted | 39.1% | 0.912x |
| friendship / two_expansions / 0.2 | 0 | 0.385 | 0.145 | manual_targeted | 166.6% | 0.979x |
| communication / one_expansion / 0.0 | 1146 | 137.220 | 122.257 | manual_prepared | 12.2% | 1.139x |
| communication / one_expansion / 0.2 | 54 | 23.084 | 14.249 | manual_targeted | 62.0% | 0.740x |
| communication / two_expansions / 0.0 | 15248 | 493.823 | 337.077 | manual_full_lru | 46.5% | 1.149x |
| communication / two_expansions / 0.2 | 0 | 0.347 | 0.156 | manual_targeted | 123.4% | 1.086x |

Eleven conditions regress by more than 10% against their best manual control.
Only friendship/one-expansion/0.2 favors automatic execution in this campaign.
Manual targeted execution wins seven manual comparisons, prepared execution four,
and the full-feature LRU one. The improved target kernel is available to every arm.

## What the ablation establishes

The all-condition descriptive fresh-prefix / retained-prefix latency ratio is
**1.120x**. It must not be presented as a uniform or precisely estimated causal
speedup: six conditions build no prefix under either strategy, yet their timings
differ. Three process repetitions leave appreciable variability, especially in
small requests. The full condition table and raw samples retain those outcomes.

The ablation isolates the execution choice more cleanly than iteration 2: eligible
completions use the same preparation and completion code; the ablation releases
each prefix and rebuilds it for the next batch. It records zero preparation hits.
An independent test verifies that the additional work equals exactly the cost
of the additional prefix builds, with unchanged scores and model calls.

| Condition with preparation | Automatic builds / hits | Fresh-prefix builds / hits | Automatic type visits | Fresh-prefix type visits |
|---|---:|---:|---:|---:|
| collaboration / two_expansions / 0.0 | 2 / 2 | 4 / 0 | 49678 | 61174 |
| friendship / one_expansion / 0.0 | 5 / 5 | 10 / 0 | 2588262 | 2866740 |
| friendship / one_expansion / 0.2 | 2 / 2 | 4 / 0 | 1369998 | 1499262 |
| friendship / two_expansions / 0.0 | 2 / 6 | 8 / 0 | 503250 | 522000 |
| communication / one_expansion / 0.0 | 4 / 4 | 8 / 0 | 1234446 | 1253954 |
| communication / two_expansions / 0.0 | 2 / 48 | 50 / 0 | 2466606 | 2575128 |

## Implementation and next evidence

The ordinary target kernel now filters adjacency once per node and hop before
iterating typed path prefixes. It retains original evidence degrees, type
multiplicities, accumulation order, resource limits and visit accounting.
Transient inference stages also use the enclosing pipeline identity, avoiding
redundant plan hashing. Independent walk-enumeration and pipeline-oracle tests
continue to pass. These are conventional implementation improvements.

The remaining work is not primarily warm-answer lookup. For communication /
two-expansions / 0.0, automatic execution still reports **2,466,606 type visits**,
versus **247,158** for the full-feature control. Reusing two-hop state avoids
prefix rebuilding but leaves repeated third-hop completion across scoring batches.
A concrete next hypothesis is bounded preparation for the union of targets already
known within a query stage, with the same primitive made available to manual
controls. Its setup, retention memory, pruning and row-construction costs must all
be charged; no performance claim follows from the work counters alone.

Setup-to-one-request is secondary: this harness constructs the plan in every
arm to obtain output columns and an explanation, although manual execution itself
does not need the planner. Common evidence/model loading remains separate. The
primary request comparison avoids claiming that diagnostic setup as a planner win.
Numeric retention counters exclude Python containers and transient arrays; peak
process RSS is retained in every worker.

## Validation and reproduction

- 153 source tests pass; three optional integrations skip in the source suite.
- A wheel built from the sdist passes 151 tests in a clean Python 3.13 environment
  with NumPy 2.5.3; five optional integration/training tests skip.
- Both live Neo4j 5.26 tests pass against that installed wheel.
- Pinned Ruff 0.16.9 checks pass. Current implementation/protocol bytes match the
  frozen campaign source.
- The archive verifies and restores; rerunning summary and bootstrap from restored
  raw workers reproduces `results.json` byte for byte.
- GitHub compatibility CI was blocked before jobs ran by account billing at the
  preceding head; local checks do not substitute for that matrix.

Manifest SHA-256:
`c936e7e5eca50a0ebd69b3b1e8450f91ba28accf9fe97783c8b3c922658f241a`.

Source, analysis, protocol, inputs and jobs were frozen before execution. The
archive retains every exact worker record under checksums. Restore the raw
workers and rerun the frozen analysis with:

```sh
python packages/query/benchmarks/v1/plan_archive.py verify \
  packages/query/benchmarks/results/graph-pipeline-development-v3
python packages/query/benchmarks/v1/plan_archive.py restore \
  packages/query/benchmarks/results/graph-pipeline-development-v3 \
  --output /tmp/graph-pipeline-v3-replay --with-workers
python /tmp/graph-pipeline-v3-replay/graph_pipeline.py summarize \
  /tmp/graph-pipeline-v3-replay
```

All 1.0 release gates remain open. Confirmation quality labels remain sealed.
