# Orbweaver Query 1.0: competitive acceptance contract

> 2026-09-27 release constraint: all further work is on a MacBook. Prepare an
> honestly scoped public preview with local installed-distribution evidence.
> The original competitive gates below remain open; H100 execution is no longer
> the release path, and no direct Quail throughput claim is made.

Status: open. Written before 1.0 experiments on 2026-09-26. The 0.1 results
remain historical evidence, not confirmation of these new claims. Do not label
the package 1.0 until the gates below have evidence and any exceptions have been
explicitly resolved. This is a graph inference engine; SQL/LLM token throughput
and graph link prediction latency are not interchangeable benchmarks.

## Release priority: eliminate inference work on useful composed queries

Following the repeated fresh-query results, the immediate next milestone is the
[execution-thesis investigation](EXECUTION_THESIS.md): establish application
headroom and one causal query/model execution mechanism before another full
campaign of small executor optimizations. This changes work priority, not gates.

The release objective is joint graph-query and model execution optimization.
Cache/precomputation comparisons in gate A are necessary controls, not the
contribution or the priority for further optimization. Warm answer lookup stores
completed predictions; Quail's vLLM baseline instead reuses intermediate KV state
while still performing inference. Winning one comparison does not establish the
other. Do not treat a microsecond improvement over a stored answer as the reason
to release 1.0.

The next development priority is gate C: richer composed graph queries in which
model results determine subsequent candidate work, with inspectable physical
execution and exact sharing/pruning inside model preparation. First-execution
workloads with previously unscored candidates must demonstrate material savings
against well-batched native/database and model pipelines. Report which graph
traversals, feature computations or model evaluations disappear, and isolate
their contribution with ablations. Keep equal evidence, model and answer-quality
contracts; charge all required setup at the same end-to-end boundary.

Keep repeated-query caches enabled in the applicable comparisons and retain all
existing adverse results. A cache-only win, or an implementation of conventional
structural scores, cannot by itself satisfy the release's novelty case. This
priority clarification does not close or weaken any gate below.

## A. Exact query execution versus strong reuse

Compare independent execution, consecutive reuse, a bounded multi-source LRU,
full precomputation, and the proposed planner. Include the best applicable
baseline for each workload. Report cold construction, warm request latency,
amortization by request count, and process RSS separately. Charge preprocessing
and invalidation to the arm that needs them. Precomputation is allowed to win.

Workloads must include single and many candidate targets, distinct and repeated
sources, duplicate requests, hub nodes, multiple model operators, low/high reuse,
small/large memory budgets, and changed graph/model identities. Use at least
three graph families and three process repetitions. Declare all workloads before
measurement. Retain every failed run. No tuning on confirmation workloads.

Gate: identical support, null/order/bag/provenance semantics; numerical error
at most 1e-12 absolute and 1e-12 relative for explicitly equivalent kernels.
No hidden candidate pruning. At least parity (within 5% aggregate median latency)
with the strongest feasible baseline across the declared mix, plus a repeatable
2x improvement on a practically motivated query class. Report each regression
over 10%, confidence intervals, and memory tradeoffs, not just the aggregate.

## B. Matched prediction applications versus Neo4j GDS

Pin Neo4j Community 2026.09.0 and GDS 2026.09.0, Java, checksums and configuration.
Use equal CPU limits; also report GDS's supported four-thread setting. Compare
at least three public graph families with explicit evidence/training/development/
confirmation splits, no pair leakage, the same candidate domain and full held-out
denominator. GDS's undirected link task must be matched explicitly; the earlier
typed WN18RR experiment is not that comparison. Include tuned GDS pipelines
(FastRP and node features, logistic regression and random forest as applicable),
simple structural controls and Orbweaver alternatives. Give arms equal development
selection budgets. Keep final confirmation data sealed until configuration freeze.

Gate: primary quality metric within one percentage point of the strongest
baseline on every application, and no statistically supported quality loss in
the pooled result. Show a useful latency/memory/setup advantage at that quality.
Report unsupported pairs as misses; do not evaluate only reached positives.
Publish quality-versus-cost curves rather than imply equal algorithms.

## C. Query-aware execution breadth

Validated, inspectable multi-operator plans with explicit model and feature
contracts; exact reuse across compatible operators; predicate ordering based
on measured costs/selectivities; source/candidate selection; batched execution;
well-defined nulls, bag semantics, limits and graph/model invalidation. Exercise
at least two independently implemented model backends and composed query shapes.
Keep Cypher delegated to Neo4j until an actual language implementation exists.

Compare relevant capabilities with Quail and LOTUS. Use their own supported
models/tasks if making a direct runtime claim, with the same hardware, inputs,
model, precision, quality and strongest enabled caches. Our CPU path scorer is
not evidence of Quail/LLM runtime parity. A graph-specific contribution needs
its own strong matched evidence, not an unsupported universal superiority claim.

## D. Reproducible release and novelty

Retain pinned data/source/configuration manifests, executable baselines, independent
correctness checks and raw outcomes. Run compatibility CI and installed-distribution
examples. Explain what is conventional (path features, caching, operator ordering)
and what new combination or measured behavior the system demonstrates. The public
claim must survive the strongest observed baseline and include adverse results.

## Experiment log

- 0.1 baseline: grouped execution versus LRU averaged about parity in the three
  measured Neo4j workflows; there is no broad cache advantage established yet.
- First development hypothesis: bound-target inference can avoid constructing
  unused terminal path features while retaining the entire evidence graph and
  exact walk normalization. This needs independent numerical validation and
  timing versus both LRU and precomputation before any performance claim.
- 2026-09-27 confirmation checkpoint: the [frozen GDS assessment](../results/gds-application-confirmation-v1/FINDINGS.md)
  meets gate B's original quality conditions on three graphs at one/four threads.
  This does not establish simultaneous one-point noninferiority against every
  control, and the observed host contention limits application timing. Gate B's
  useful cost advantage remains unproven; gates A, B, C and D remain open.

Sources: [Quail launch](https://fsdatalab.github.io/blog/introducing-quail/),
[GDS compatibility](https://neo4j.com/docs/graph-data-science/current/installation/supported-neo4j-versions/),
[GDS pipelines](https://neo4j.com/docs/graph-data-science/current/machine-learning/linkprediction-pipelines/link-prediction/),
[LOTUS](https://github.com/lotus-data/lotus).
