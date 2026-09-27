# Bounded generalization of the native GDS queue control

2026-09-26. Declare this six-condition check before measuring any of its conditions.
The first friendship/one-thread diagnostic showed an exact native improvement;
do not assume it applies to other graphs or concurrency settings. The original
interrupted 18-worker campaign and the first bounded diagnostic remain unchanged.

Use all three previously declared graph families (collaboration, friendship,
communication), each at one and four configured threads. One fresh native ARM
Neo4j/GDS process and one trained model per condition. This is six model fits,
not the full three-process-repetition acceptance campaign. Shuffle condition
order with seed 7621. Each condition independently uses arm-order seed 7620,
one warmup and three measured requests per arm. Run conditions sequentially,
without overlapping model/test jobs. Do not select conditions based on timings.

Reuse the original outer graph, 64 development sources, held-out positives and
previously selected GDS pipeline: rich FastRP256/16 negatives for collaboration,
FastRP64 for friendship and communication. Keep the original classifier selection
budget and seed. No model retuning, new data split or confirmation reads. Set
training, FastRP/degree and prediction concurrency plus Python numeric-library
ceilings to each condition's setting. Preserve the native architecture/runtime
guard, Neo4j/GDS 2026.09.0, Java 21.0.10+7, 8 GiB heap and 900-second transaction
ceiling. These are configured thread ceilings, not OS affinity measurements.

Within each condition compare exactly the same trained native model through:

1. Global exhaustive output at full candidate capacity, followed by server-side
   per-source top-16 selection.
2. Singleton-source exhaustive calls with topN initially min(32, domain size),
   increasing only unresolved cutoff ties until exact stable-ID top-16 is known.

The details and sorted-array source finding remain in
[the first diagnostic protocol](GDS_QUEUE_DIAGNOSTIC.md). Both arms pay the
read-only adapter/EXPLAIN and JSON boundary. Singleton labels/projection setup
and model fit are recorded separately. The partitioned arm pays all repeated
native pipeline preparation; no additional intermediate cache is introduced.
These requests jointly change queue size, traversal repetition and output
assembly, so their ratio is not an isolated queue-kernel ablation.

Before timing, stream complete native scores, validate every candidate and
independently rank the expected output. Require exact output equality for every
warmup and measured request. Retain every raw sample, score matrix, model-selection
record, adaptive-round counter and setup phase. Record old/current score
differences only when a completed prior worker exists at the same graph/thread
setting; otherwise report unavailable. Across separately fitted conditions,
models may differ, especially at four threads. Record raw-score development
quality and actual stable-ID recall rather than assuming earlier quality holds.

The summary requires all six conditions and recomputes coverage, rankings and
raw-score quality from saved scores. Retain errors without overwriting or silently
restarting workers. Report per-condition descriptive medians and regressions;
do not manufacture confidence intervals from three requests in one process.
If the partitioned formulation loses somewhere, retain the stronger native
alternative there. Do not generalize the first 4.64x result.

This answers which native reference to carry into a future matched application
comparison. It does not measure Orbweaver, compare approximate search, close a
release gate or justify another campaign of CPU planner tuning. The separate
CUDA profile and a graph-specific inference mechanism remain the research goal.
