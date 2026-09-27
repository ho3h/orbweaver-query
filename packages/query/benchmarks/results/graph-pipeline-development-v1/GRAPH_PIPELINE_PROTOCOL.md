# Fresh composed graph-inference queries: development protocol 1

This experiment tests graph expansion interleaved with model predicates, not
retrieval of previously cached answers. It is a capability and development
comparison; it does not establish Quail parity or close a release gate.

Use the three evidence graphs and trained path artifacts retained in
`plan-development-v4`, verifying its archive before copying inputs. Confirmation
labels remain sealed. From each frozen `distinct128` candidate list take the
first eight rows for one expansion, or first four for two expansions. Rename
`target` to `seed`, append a duplicate of the first row with ordinal 1000 and a
null-head/null-seed row with ordinal -1. Selection uses no scores or outcomes.

Logical queries expand `seed` to `one` over BOTH directions and all evidence
types. The two-expansion shape additionally expands `one` to `two`. At the end,
filter the root pair by resource allocation >= 0.2; the two-expansion shape also
filters `(head, one)` by the same threshold. Score `(head, final endpoint)` with
the frozen learned path model. Keep complete evidence and scores. Return ordinal,
head, seed, expansion endpoints and all predictions, preserving every duplicate
and canonical edge order. These are ordinary expansions, not optional matches.

Four fixed arms:

- `automatic`: GraphPipeline moves eligible predicates before expansions.
- `eager`: identical pipeline, predicate movement disabled; within-stage grouping
  remains enabled. This is an ablation, not the strongest competitor.
- `manual_targeted`: independent adjacency expansion built from canonical triples;
  hand-order predicates before expansions; grouped binding API with exact
  target-aware features. No GraphPipeline/QueryPlan executor in this control.
- `manual_full_lru`: the same hand-ordered pipeline, with a shared 16 MiB numeric
  full-source feature/score LRU, reset before each request. Python overhead and
  transient arrays are outside that numeric budget; report process RSS too.

Every arm gets a fresh 16,384-entry pair cache at the beginning of each request,
allowing ordinary reuse within that request but retaining no predictions from
earlier requests. Each model batch contains at most 256 rows. Each expansion
stage is capped at 100,000 rows per root window; exceeding that or model work
limits is a recorded failure, never truncation. Strong manual controls must
enforce equivalent bounds. The immutable graph and model load are common setup.
Charge extra manual adjacency construction separately and at one request.

Use three independent process repetitions per arm/graph/shape (72 workers),
single-thread numerical libraries, one untimed warmup and three timed samples.
Reset request caches for warmup and every sample. Include record construction and
JSON serialization in latency. Record all raw results, profiles, setup, peak RSS
and failures. Shuffle worker order with seed 8401. Freeze source, protocol,
inputs and analysis before running workers. Do not run competing benchmarks at
the same time. No timing claims from unit tests or work-count ratios.

Verify ordered output bags, all prediction metadata and null/support status
against the independent manual controls, with score tolerance 1e-12 absolute and
relative. Report fixed `automatic` versus the strongest manual arm per condition,
both steady state and with setup charged to one request. Report automatic/eager
separately as an ablation; retain each >10% regression, all zero-output cases,
and work counts. Aggregate the six condition ratios geometrically. Conditional
process bootstrap: 10,000 resamples, seed 8402, reselect the strongest manual
control in every resample. This is exploratory development evidence, not a
confirmation or a well-powered cross-application significance claim.
