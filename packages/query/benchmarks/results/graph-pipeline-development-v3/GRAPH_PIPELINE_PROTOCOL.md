# Fresh composed graph-inference queries: development protocol 3

This follow-up isolates model-internal preparation reuse on fresh composed queries
after matching the ordinary kernel's per-node adjacency filtering to prepared
completion. The earlier campaigns remain immutable, including empty outputs,
slower automatic execution and eager row-budget failures. This protocol is frozen
before timing; it neither confirms held-out quality nor closes 1.0 gates.

Copy the exact graphs, trained models and query JSON files from verified
`graph-pipeline-development-v2`; do not regenerate or select new candidates.
Confirmation labels remain sealed. The v2 selection used a deterministic
two-hop graph query, not model scores: permute
non-isolated source indices with NumPy seed 8501; keep the first eight sources
with at least one nonadjacent two-hop target; sample up to two distinct targets
per source from their sorted domain. One-expansion queries use all eight source
buckets; two-expansion queries use the first two sources and the first target of
each. Append a duplicate of the first row (ordinal 1000) and a null row (-1).
This models bounded two-hop candidate generation. Workload files must match v2
byte for byte; older v1 used a different candidate mix and remains incomparable.

Expand `seed` to `one` over BOTH directions and all types. The two-expansion
shape then expands `one` to `two`. Logically place a resource-allocation filter on
`(head, seed)` after these expansions; the two-expansion shape also filters
`(head, one)`. For each shape run both fixed thresholds 0.0 and 0.2. Zero accepts
supported zero scores, but never self/adjacent unsupported pairs or null inputs.
Score the final endpoint with the frozen learned path model. Preserve complete
evidence, ordered edge bags, all score metadata and null/support distinctions.
Every declared case, including any empty result or resource failure, is retained.

Seven arms, with the same inputs, models, evidence and 256-row model batch bound:

- `automatic`: dependency-aware movement and reusable source preparation.
- `automatic_unprepared`: same movement, with cross-batch preparation disabled.
- `automatic_fresh_prepared`: identical automatic eligibility and completion
  kernel, but discard each prepared prefix after its completion and rebuild on
  the next eligible batch. This benchmark-only scope is installed inside its
  isolated worker; it does not change the production API. Zero preparation hits
  are required. Compare its builds, type visits and latency with `automatic` to
  isolate retaining intermediate state. The ordinary unprepared comparison still
  includes differences in prefix pruning and representation.
- `eager`: logical predicate placement; preparation reuse remains available.
- `manual_targeted`: hand-ordered grouped binding pipeline with exact target
  expansion and independent vector traversal over the existing packed graph.
- `manual_full_lru`: the same control with a 16 MiB numeric full-feature/score LRU.
- `manual_prepared`: the same control with a 16 MiB numeric LRU of two-hop walk
  state, using the new model preparation primitive directly. This control does
  not use the query planner, its stage executor or its automatic reuse heuristic.

The manual controls construct no separate Python adjacency index. Common graph
and model loading is separate; record all additional per-arm setup. All arms
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

Use three isolated process repetitions per arm/graph/shape/threshold: 252 workers.
Single-thread numerical libraries, one untimed warmup, three timed samples, fresh
request state each time. Include record construction and JSON serialization.
Shuffle workers with seed 8502. Do not run competing timing campaigns concurrently.
Freeze source, protocol, inputs and analysis before execution; retain every raw
success/error record and per-sample latency, profiles, setup and peak RSS.

Compare the fixed automatic candidate against the fastest of all three manual
controls per condition. Report steady request latency and setup charged to one
request, each >10% regression and work counters. Report the no-preparation and
eager arms separately as ablations. Geometric aggregation covers all 12 declared
conditions only when the primary comparison is complete. Conditional process
bootstrap: 10,000 resamples, seed 8503, reselect the best manual control in each
resample. Verify complete ordered bags and metadata, with 1e-12 absolute/relative
score tolerance. These are development results, not universal superiority or a
well-powered cross-application significance test.
