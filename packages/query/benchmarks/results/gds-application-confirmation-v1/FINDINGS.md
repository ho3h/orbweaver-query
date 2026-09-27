# Frozen GDS confirmation quality assessment

The selected local methods meet the original gate B **quality conditions** on
these three fixed graphs at both one/four-thread settings: primary point estimates
are within one percentage point of every declared control, with no statistically
supported pooled loss. **Gate B remains open:** this result does not establish a
useful competitive cost advantage, and the separate application's timing has an
observed host-contention limitation. Gates A, C and D remain open too.

A stronger simultaneous one-percentage-point noninferiority claim against every
control/view is **not established**. An interval spanning zero does not establish
parity. Conventional structural methods remain competitive: the selected local
model is itself resource allocation on collaboration and friendship, and the path
model's communication advantage over resource allocation is uncertain.

## Protocol and access history

The evaluator and synthetic checks were committed and pushed in `1f1cf06` before
this separate confirmation manifest was frozen and before the original sealed
labels were parsed. The core suite passed 306 tests with seven optional skips.
All 18 application workers had completed, the 352-file application archive had
verified, its frozen numerical summary had reproduced exactly, and an independent
implementation had reconstructed its development quality and outputs.

The confirmation run reuses those frozen prediction matrices. No fitting,
configuration choice, preferred repetition, ensemble or threshold changed. The
original development manifest still disallows confirmation access; this separate
manifest explicitly permits the declared evaluation. Its first evaluation
succeeded. Numerical replay repeats the same fixed calculation for verification;
it is not another experiment or opportunity for model selection.

There are 460 directed positive queries incident to the original sampled sources:
44 collaboration, 211 friendship and 205 communication. Every positive is retained,
including unsupported predictions as misses. There are 64 original sources per
graph; zero-positive sources remain in resampling. The three process repetitions
reuse seed 71 and are averaged before uncertainty estimation, not counted as new
labels or independent training seeds. Common neighbors is an untimed quality
control computed from the same outer evidence.

## Primary quality: raw-score expected recall@16

Arithmetic means of all three repetitions. The reported aggregate quality is
identical across the one/four-thread conditions; `summary.json` retains both
separately. Uniform ties are averaged rather than broken using application IDs.

| Graph | Positive queries | Selected local | Learned GDS | Common neighbors | Resource allocation | Adamic–Adar |
|---|---:|---:|---:|---:|---:|---:|
| collaboration | 44 | 83.058% | 75.021% | 82.206% | 83.058% | 83.058% |
| friendship | 211 | 50.992% | 42.180% | 48.361% | 50.992% | 50.992% |
| communication | 205 | 45.366% | 32.203% | 39.046% | 43.910% | 41.471% |

Local minus the strongest observed declared control is 0.000, 0.000 and +1.456
percentage points respectively. The first two applications tie resource allocation
and Adamic–Adar; resource allocation is the strongest communication control.
These ties do not establish a new prediction method.

## Actual returned top-16 quality

The application rounds scores to 12 decimal places and then breaks ties by
ascending string ID. This deployed-answer metric is distinct from the primary
uniform-tie metric. Both remain fixed in the predeclared protocol.

| Graph | Positive queries | Selected local | Learned GDS | Common neighbors | Resource allocation | Adamic–Adar |
|---|---:|---:|---:|---:|---:|---:|
| collaboration | 44 | 84.091% | 75.000% | 81.818% | 84.091% | 84.091% |
| friendship | 211 | 51.185% | 42.180% | 47.867% | 51.185% | 51.185% |
| communication | 205 | 45.366% | 32.195% | 38.537% | 43.902% | 41.463% |

## Secondary metrics

Raw-score recall@64, reciprocal average tie rank (not expected reciprocal rank),
and supported-positive fraction. Every method uses the full positive denominator.
Rounded-score metrics and every individual positive outcome remain in the archive;
they do not replace the primary metric or its decision rule.

| Graph | Method | Raw recall@64 | Reciprocal average tie rank | Supported positives |
|---|---|---:|---:|---:|
| collaboration | Selected local | 88.767% | 0.499095 | 100.000% |
| collaboration | Learned GDS | 85.587% | 0.328888 | 100.000% |
| collaboration | Common neighbors | 88.767% | 0.490287 | 100.000% |
| collaboration | Resource allocation | 88.767% | 0.499095 | 100.000% |
| collaboration | Adamic–Adar | 88.767% | 0.512096 | 100.000% |
| friendship | Selected local | 86.261% | 0.199155 | 100.000% |
| friendship | Learned GDS | 78.673% | 0.146422 | 100.000% |
| friendship | Common neighbors | 83.050% | 0.183785 | 100.000% |
| friendship | Resource allocation | 86.261% | 0.199155 | 100.000% |
| friendship | Adamic–Adar | 82.944% | 0.194078 | 100.000% |
| communication | Selected local | 73.171% | 0.158202 | 99.024% |
| communication | Learned GDS | 61.495% | 0.103542 | 100.000% |
| communication | Common neighbors | 67.986% | 0.120482 | 100.000% |
| communication | Resource allocation | 72.083% | 0.157168 | 100.000% |
| communication | Adamic–Adar | 71.596% | 0.133609 | 100.000% |

## Paired uncertainty

100,000 source-block bootstrap draws, seed 20260928; all draws were retained.
The calculation uses the same sampled sources across methods, thread settings and
repetitions, independently within each graph. The simultaneous intervals use
Bonferroni correction for all 40 declared differences: four controls, two thread
settings and five views. Complete per-application and pooled comparisons, including
ordinary percentile intervals, are in `summary.json`.

The following pooled values and intervals are identical for both thread settings:

| View | Control | Local minus control, percentage points | Simultaneous 95% interval, percentage points | One-point noninferiority |
|---|---|---:|---:|---|
| equal_application | gds | 10.004 | [3.175, 18.580] | established |
| equal_application | common_neighbors | 3.268 | [-0.922, 7.804] | established |
| equal_application | resource_allocation | 0.485 | [-2.096, 2.997] | not established |
| equal_application | adamic_adar | 1.298 | [-2.565, 5.131] | not established |
| positive_weighted | gds | 10.677 | [2.695, 20.047] | established |
| positive_weighted | common_neighbors | 4.105 | [-1.523, 9.900] | not established |
| positive_weighted | resource_allocation | 0.649 | [-2.887, 3.672] | not established |
| positive_weighted | adamic_adar | 1.736 | [-3.475, 6.697] | not established |

The equal-application difference versus learned GDS is +10.004 percentage points,
with a simultaneous interval [3.175, 18.580]; the positive-weighted difference is
+10.677 points, interval [2.695, 20.047]. This is a supported pooled quality
advantage in the declared analysis on these fixed graphs. It is not universal
superiority over GDS, a new algorithm, or an execution-performance claim.

Intervals against structural controls remain wider. Source resampling is
conditional on these three graphs; connected sources need not be independent,
and the analysis does not establish generalization to other graph populations.
No failed or inconclusive comparison is removed from the result.

## Costs and next decision

Associate these predictions with the complete
[development application cost records](../gds-application-development-v2/FINDINGS.md).
They concern the same fixed sources and prediction artifacts. They are not new
confirmation timing measurements. Unrelated host computation was observed during
that campaign, so its latency observations alone cannot close the cost gate.
Native structural methods and answer precomputation remain relevant controls;
whole-worker RSS is not per-method memory.

The confirmation labels are now opened. Preserve this outcome; do not use them
to repeatedly retune until a gate passes. Further model development requires a
new uncontaminated confirmation design. The next research decision still needs
supported-GPU profiling and a useful graph-dependent execution mechanism, not
another campaign of CPU planner tweaks.

## Reproduction

The archive retains all frozen source, input identities, opened labels, prediction
matrices, per-positive outcomes, all 18 worker records and the original result.
The verifier checks byte integrity and complete records without numerical analysis;
run the frozen evaluator's replay separately for a full reconstruction.

```sh
python packages/query/benchmarks/results/gds-application-confirmation-v1/verify.py \
  --output /tmp/gds-confirmation-replay
python /tmp/gds-confirmation-replay/gds_confirmation.py replay /tmp/gds-confirmation-replay
```

Use the recorded NumPy 2.4.4 environment with Python 3.11 and the frozen application's
Python dependencies. Replay uses no live database, retraining, GPU or new selection.
A fresh restore is required; the original evaluator refuses to overwrite an
existing evaluation or failed attempt.

Manifest SHA256: `e284f7ad4fd1bc7035dcd86b7bcaab4a23d5ad41ed1e13fa3101c6421e9eb1d9`.

Original result SHA256: `d4e8ff3bac515e37fd8e69e84df5e8f2601db5e2208f96da3d76b340b9a2dbdc`.

Archive SHA256: `78133cc0af1f22df976e1862931b29e04f5cc6bda89d5f499bfab8ea9919b996`.
