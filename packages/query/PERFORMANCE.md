# Performance and claim boundaries

The Mac release path uses native Apple Silicon Python and NumPy. The installed
wheel demonstration follows the [frozen protocol](benchmarks/MAC_RELEASE_PROTOCOL.md).
The [completed installed-wheel report](benchmarks/results/mac-installed-v1/FINDINGS.md)
identifies the exact wheel, host, dependencies and all 24 conditions. On an M5 Max
with 128 GiB, the observed on-demand geometric ratio was **2.59×**, including JSON
serialization. All 648 workers pass answer checks; five conditions regress over
10%, and warm precomputation wins every condition. This run had substantial
background activity and is **descriptive normal-mixed-use evidence**, not an
isolated latency certification. Its conditional timing interval does not remove
that limitation. Distinct supported targets show 2.66×–12.04× in these fixed cases.
No headline Quail speedup, universal GDS advantage, or completed 1.0 claim is supported.

The [completed 63-client movie workflow](benchmarks/results/movie-workflow-v2/FINDINGS.md)
passes every native-reference check. Against the fastest native/manual/full-source
on-demand control, request ratios are 0.86× for one film, 0.71× for a repeated basket,
and 1.23× for a filtered basket. Native Cypher has lower median first-use cost in
all three. The requested quiet window still had substantial background activity;
these are descriptive end-to-end costs, not isolated latency certification.
Export, connection, preparation and complete serialization are disclosed.

| Evidence | Measured result | What it supports |
| --- | --- | --- |
| [Targeted development, iteration 4](benchmarks/results/v1-development/FINDINGS.md) | 2.00× geometric ratio against the fastest guarded on-demand control across 24 conditions; fully supported distinct pairs 7.14× WordNet, 2.47× movies, 4.11× collaboration | Exact target-aware graph execution on reused fixtures; this older boundary excludes JSON serialization |
| Same study, warm controls | Prepared lookup faster than validated public bindings; many-target collaboration about 13% slower than its best on-demand control | Reuse and density can favor the baseline; no universal win |
| [Composed pipelines](benchmarks/results/graph-pipeline-development-v6/FINDINGS.md) | Automatic execution about 33.5% greater latency than the best manual control | Correct composition, with a remaining execution gap |
| [Native ARM structural study](benchmarks/results/native-structural-arm64-development-v1/FINDINGS.md) | 1.059× before export, 0.970× amortizing export over 1,000 requests; warm ratio 0.889× | No substantial native application advantage established |
| [Held-out GDS quality](benchmarks/results/gds-application-confirmation-v1/FINDINGS.md) | Original quality conditions met on all three graphs at one/four threads | Matched application quality evidence; simultaneous one-point noninferiority against every control is not established |
| [GDS application timing](benchmarks/results/gds-application-development-v2/FINDINGS.md) | All 18 workers retained; unrelated host computation observed | Descriptive costs, not isolated latency parity |

Here a ratio above one means Orbweaver was faster; below one means its control
was faster. The old 4.22–4.45× grouping result used a consecutive one-source
cache. A multi-source LRU recovered nearly the same benefit. It is retained in
the [historical evidence](EVIDENCE.md), not used as the current headline.

WordNet uses a trained example model. Movies and collaboration in the targeted
runtime study use random coefficients to exercise computation. Those timing
results establish nothing about prediction quality. A separate held-out GDS
assessment compares application rankings and includes strong structural methods.
Its opened labels are not a new tuning set.

The original x86-Java/ARM-Python structural timing claim was withdrawn. The
native ARM replacement above is the relevant comparison. Every failed or
superseded run remains in the [evidence inventory](EVIDENCE.md).

## What is novel?

Path features, structural scores, caches, batching and predicate ordering are
established techniques. Exact target-aware preparation with explicit graph/model
contracts is a useful implementation and integration result; broad algorithmic
novelty or a Quail-like systems contribution has not been demonstrated.
[Positioning](POSITIONING.md) records the prior art and remaining gaps.

Quail controls transformer execution and intermediate KV state. The Mac path
scorer controls graph features. Comparing their separately reported ratios is
not a head-to-head test. The optional bridge does not make Quail's CUDA inference
run on a Mac. Direct Quail throughput parity is outside this release's claim.

## Release interpretation

A useful, reproducible development preview can be public while the ambitious
competitive gates remain open. Stable 1.0 is not certified by a wheel building,
a narrower benchmark winning, or an absence of test failures. The
[current audit](RELEASE_AUDIT.md) tracks actual distribution validation separately
from the [original acceptance gates](benchmarks/v1/ACCEPTANCE.md).
