# Fresh composed graph-inference queries: development protocol 4

This follow-up tests bounded preparation for the union of a query stage's targets,
avoiding repeated third-hop completion across scoring batches. It also reduces
redundant internal row copies, physical-plan reconstruction and reporting work.
The earlier campaigns remain immutable, including empty outputs, slower automatic
execution and eager row-budget failures. This protocol is frozen before timing;
it neither confirms held-out quality nor closes 1.0 gates.

Copy the exact graphs, trained models and query JSON files from verified
`graph-pipeline-development-v3`; do not regenerate or select new candidates.
Confirmation labels remain sealed. The v2 selection used a deterministic
two-hop graph query, not model scores: permute
non-isolated source indices with NumPy seed 8501; keep the first eight sources
with at least one nonadjacent two-hop target; sample up to two distinct targets
per source from their sorted domain. One-expansion queries use all eight source
buckets; two-expansion queries use the first two sources and the first target of
each. Append a duplicate of the first row (ordinal 1000) and a null row (-1).
This models bounded two-hop candidate generation. Workload files must match v2/v3
byte for byte; older v1 used a different candidate mix and remains incomparable.

Expand `seed` to `one` over BOTH directions and all types. The two-expansion
shape then expands `one` to `two`. Logically place a resource-allocation filter on
`(head, seed)` after these expansions; the two-expansion shape also filters
`(head, one)`. For each shape run both fixed thresholds 0.0 and 0.2. Zero accepts
supported zero scores, but never self/adjacent unsupported pairs or null inputs.
Score the final endpoint with the frozen learned path model. Preserve complete
evidence, ordered edge bags, all score metadata and null/support distinctions.
Every declared case, including any empty result or resource failure, is retained.

Nine arms, with the same inputs, models, evidence and 256-row scoring batch bound:

- `automatic`: dependency-aware movement and bounded stage target coalescing.
- `automatic_prefix`: same movement, retaining only target-independent two-hop
  state. This disables coalescing but retains the previous reuse strategy.
- `automatic_unprepared`: same movement, with cross-batch preparation disabled.
- `automatic_fresh_prepared`: identical automatic eligibility and completion
  kernel, but discard each prepared prefix after its completion and rebuild on
  the next eligible batch. This benchmark-only scope is installed inside its
  isolated worker; it does not change the production API. Zero preparation hits
  are required. Compare its builds, type visits and latency with `automatic` to
  isolate retaining intermediate state against `automatic_prefix`. The ordinary unprepared comparison still
  includes differences in prefix pruning and representation.
- `eager`: logical predicate placement; preparation reuse remains available.
- `manual_targeted`: hand-ordered grouped binding pipeline with exact target
  expansion and independent vector traversal over the existing packed graph.
- `manual_full_lru`: the same control with a 16 MiB numeric full-feature/score LRU.
- `manual_prepared`: the same control with a 16 MiB numeric LRU of two-hop walk
  state, using the new model preparation primitive directly. This control does
  not use the query planner, its stage executor or its automatic reuse heuristic.
- `manual_coalesced`: the hand-ordered pipeline uses the same stage-target hint,
  bounded retention and target-preparation primitive as automatic execution. Its
  graph expansion and binding executor remain independent of the query planner.

Coalescing remains a heuristic: sources must span scoring batches. The hint
collects targets already present in the bounded stage, excluding resolved pairs.
Preparation is lazy, computes exact features only for the declared union, and
keeps no model-specific scores. Each scoring batch receives its feature subset.
The retention budget includes the union's numeric target and feature arrays.
Retained domains are checked before reuse; a new stage may rebuild them. A single
coalesced preparation can hit a model work/state limit where smaller batches
would succeed; that is an explicit failure and is retained, never silently pruned.

The manual controls construct no separate Python adjacency index or query plan
for execution. Unlike v3, their explanatory plan is constructed only after request
and setup timing is complete. Automatic plan construction is charged to its setup;
report both request latency and setup charged to one request. Common graph and
model loading is separate. All arms
receive a fresh 1,048,576-entry pair cache for each request to avoid evictions
confounding preparation reuse. Neither completed answers nor feature/prefix
states survive between requests. Allow within-request reuse, report its work and
memory, and include cache reset/construction in timing. Numeric state budgets
exclude Python containers, original evidence and transient arrays; also report
process RSS. The automatic scope lives only for one root input window. Oversized
prepared states may be used once but are not retained or repeatedly rebuilt.

The same 100,000 intermediate-row, expansion-state and visit limits apply to all
arms. Failures are explicit, never truncated. A completed independent manual
control is required to validate each condition. If any primary arm is incomplete,
report condition-level outcomes and failures but no all-condition speed ratio.

Use three isolated process repetitions per arm/graph/shape/threshold: 324 workers.
Single-thread numerical libraries, one untimed warmup, three timed samples, fresh
request state each time. Include record construction and JSON serialization.
Shuffle workers with seed 8502. Do not run competing timing campaigns concurrently.
Freeze source, protocol, inputs and analysis before execution; retain every raw
success/error record and per-sample latency, profiles, setup and peak RSS.

Compare the fixed automatic candidate against the fastest of all four manual
controls per condition. Report steady request latency and setup charged to one
request, each >10% regression and work counters. Report the no-preparation and
eager arms separately as ablations. Report `automatic_prefix / automatic` as the
descriptive coalescing ratio, and fresh-prefix / automatic-prefix for retained
prefix reuse. These ratios are not interchangeable. Geometric aggregation covers all 12 declared
conditions only when the primary comparison is complete. Conditional process
bootstrap: 10,000 resamples, seed 8503, reselect the best manual control in each
resample. Verify complete ordered bags and metadata, with 1e-12 absolute/relative
score tolerance. These are development results, not universal superiority or a
well-powered cross-application significance test.
