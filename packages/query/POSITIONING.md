# Competitive context and release claims

Assessment as of 2026-09-27. Orbweaver Query remains `1.0.0.dev1`; the
[acceptance gates](benchmarks/v1/ACCEPTANCE.md) are open. This document separates
verified behavior, external authors' results, and our interpretation of likely
reception. It is not a claim that we have tested every alternative.

The current release preparation is Mac-only. CUDA bridge research remains
unexecuted and outside the preview claim. See the [current audit](RELEASE_AUDIT.md)
and [performance page](PERFORMANCE.md) for the public scope; the competitive
assessment below is retained with its adverse evidence.

## Where the systems overlap

| Dimension | Orbweaver Query now | Relevant existing work | Implication for 1.0 |
|---|---|---|---|
| User task | Score explicit graph pairs, filter and project candidate bindings | Quail evaluates natural-language predicates over text; GDS includes graph prediction | Compare graph application outcomes with GDS; compare architecture with Quail |
| Query surface | Python plans with typed graph expansion; Neo4j executes supplied Cypher; optional Quail document filters → graph pairs → semantic join | Quail supports AI-SQL filters, joins and existence tests; LOTUS exposes semantic operators | Materialized filter/join composition has CPU correctness evidence; correlated existence and multi-hop semantic traversal remain missing |
| Shared work | Exact source features and reusable two-hop walk state across compatible models; separate graph/model/pair score caching | Quail plans document KV reuse; ordinary caches and precomputation are strong controls | Model-internal work reuse must survive hand-managed prepared-state controls |
| Planning | Measured group cost/selectivity; exact bound-target preparation; dependency-safe filter movement before expansion | Quail coordinates operator order and model execution; LOTUS uses lazy planning, cascades and proxies | Query awareness and relational predicate pushdown are established prior art |
| Inference | CPU path features and three conventional structural scores; optional Quail bridge verified through CPU planning/projection tests | Quail has GPU LLM execution; GDS has learned pipelines and native structural functions | The bridge has no CUDA measurement; current CPU results do not establish LLM throughput parity |
| Consistency | Immutable evidence identities; explicit graph/model cache invalidation | Native GDS functions can read current Neo4j data | Export, refresh and stale-snapshot behavior are part of the application cost |
| Breadth still missing | No model-generated edges, existence operators or native inference Cypher syntax; the optional text bridge is outside the core graph-model contract | Quail/LOTUS cover broader semantic processing; NGDBench tests richer graph-query settings | Keep these gaps visible; do not imply general GQL or neural-database coverage |

External capability sources: [Quail README at 41b883b](https://github.com/fsdatalab/quail/blob/41b883b838687cfbf018080f068f3e81bf2f8e64/README.md),
[Quail design and launch evaluation](https://fsdatalab.github.io/blog/introducing-quail/),
[LOTUS README at 136ae4f](https://github.com/lotus-data/lotus/blob/136ae4f4a344a2f75d89f811e516dfcb0de30e46/README.md).
The native GDS functions were also executed against pinned 2026.09.0; see the
[matched structural protocol](benchmarks/v1/STRUCTURAL_NEO4J_PROTOCOL.md).

## How to interpret the performance numbers

Quail's launch reports a 1.84x geometric speedup over stock vLLM on 29 queries,
winning 27, using the same Qwen3-4B FP8 model, BF16 KV and H100. Its controls use
optimized operator ordering and reuse-friendly request scheduling. It also
reports AGENT-1 taking 2.32x as long as stock vLLM. These are the authors'
measurements, not our reproduction. [Launch evaluation](https://fsdatalab.github.io/blog/introducing-quail/).

This is not a comparison with cached final answers. Quail's stock and pipelined
vLLM controls enable automatic prefix caching: they reuse intermediate attention
state and still execute model work for the requested predictions. The pinned
[vLLM backend](https://github.com/fsdatalab/quail/blob/41b883b838687cfbf018080f068f3e81bf2f8e64/quail/backends/vllm.py#L182-L194)
explicitly sets `enable_prefix_caching=True`. Quail's contribution coordinates
query execution with KV lifetimes/reuse, scheduling and specialized inference
execution. Our warm pair cache stores completed scores. It is a useful overhead
control and a realistic winner for repeated requests, not the research target.

Our final targeted-inference development iteration measured 2.00x against the
strongest guarded on-demand control on its own fixed graph workload mix. That
ratio has a different denominator, task and hardware; comparing 2.00 with 1.84
would not show that Orbweaver beats Quail. Warm precomputation remains faster.
[Retained target experiments](benchmarks/results/v1-development/FINDINGS.md).

The first composed-plan experiment measured 3.30x against its cold full-source
LRUs, excluding calibration, while warm pair caching won every workload. A
many-target case regressed 10.5%. We strengthened the full-cache target lookup,
added persistent plan caching and adaptive exact preparation. The strengthened
864-worker campaign found a 1.09x geometric advantage against the best cold control,
but about 25% greater warm cached latency. That gap motivates further filter
pushdown; the earlier 3.30x ratio must not represent the stronger comparison.
[Earlier composed-plan evidence](benchmarks/results/plan-development-v3/FINDINGS.md).

The follow-up pushdown campaign completed another 864 workers. The default plan
measured 1.159x against the strongest cold control; warm cached execution measured
0.972x against the strongest warm control. Calibration adds no aggregate steady
state advantage on this mix. These are useful implementation checks, not evidence
of a Quail-level contribution or general superiority. Further development should
prioritize richer query/model execution, rather than optimizing the remaining
stored-answer overhead. [Pushdown evidence](benchmarks/results/plan-development-v4/FINDINGS.md).

The GDS development results compare common outer evidence and candidate domains,
but the learned algorithms and internal fitting examples differ. Structural
scores already available natively in GDS must also compete. The native comparison
therefore includes scalar GDS functions and shared-traversal Cypher, with the same
returned records and separately charged evidence export. The original
[development grid](benchmarks/results/gds-retry-development-v1/FINDINGS.md)
does not establish held-out quality or native application cost parity.

The [runtime architecture audit](benchmarks/results/native-runtime-audit-v1/FINDINGS.md)
subsequently found that the original native structural timing campaign ran x86_64
Java on this ARM Mac while Python ran natively. Its 1.23x local latency advantage
cannot support a fair native comparison. The original quality/correctness records
remain evidence about those executions; original GDS timing must not establish
native cost parity. The benchmark now rejects mismatched/translated runtimes.
The [native ARM replacement](benchmarks/results/native-structural-arm64-development-v1/FINDINGS.md)
verifies 432 conditions with current source: the cold ratio is only 1.059x before
export and 0.970x when export is spread over 1,000 requests. Warm execution is
0.889x against the strongest warm control. These descriptive development results
reinforce the architecture reset; they are not evidence of broad superiority.

The subsequent learned-GDS application campaign was also stopped to strengthen
its control. A [source audit and bounded within-model diagnostic](benchmarks/results/gds-queue-diagnostic-development-v1/FINDINGS.md)
found that small per-source native queues return the same answers in 6.85 seconds
instead of 31.76 seconds. The original global queue retained the full candidate
domain; its sorted-array implementation makes that expensive. This 4.64x
descriptive native improvement is a correction to our comparison, not an
Orbweaver speedup or an isolated measurement of queue cost. Four completed
workers and the interrupted fifth worker are retained without an aggregate claim.
Use the stronger control before drawing conclusions about learned-pipeline cost.

The [six-condition generalization check](benchmarks/results/gds-queue-generalization-development-v1/FINDINGS.md)
completed friendship and communication at one/four threads, with descriptive
native improvements of 2.19x–10.00x and exactly matching full-score outputs.
Both collaboration conditions failed during repeated partitioned requests with
the same GDS memory-reservation rejection. All six were attempted and retained;
there is no complete suite result. Long-running resource behavior and collaboration
were unresolved by that attempt; the later resource checks below address the
reservation failure without replacing the failed timing evidence.

A [bounded memory diagnostic](benchmarks/results/gds-memory-diagnostic-development-v1/FINDINGS.md)
now reproduces reservation accumulation after completed calls, even with separate
transactions. Source review identifies a zero-retention completion-listener
ordering defect. A supported 60-second task-retention setting removes the growth
on the small fixture with all 20 outputs unchanged. This supplies a configuration
workaround, initially checked on a small fixture. The
[original-workload validation](benchmarks/results/gds-retention-application-development-v1/FINDINGS.md)
now completes both one/four-thread collaboration processes: all ten repeated
requests match the independent full-score reference, all 18 resource checkpoints
have zero reservations, and retained task records expire. Both full-score arrays
match the earlier failed runs exactly. This is bounded reliability evidence,
not long-running stability, a replacement timing suite or an Orbweaver speedup.

The [complete application campaign](benchmarks/results/gds-application-development-v2/FINDINGS.md)
now covers all 18 one/four-thread workers, with byte-identical archived replay and
independent reconstruction of each method's predictions and development quality.
Selected local methods exceed learned GDS's development recall, but native
structural methods remain strong cost controls and the communication path method
is expensive. Unrelated host computation was observed during the campaign, so
its timing is descriptive and cannot by itself establish competitive latency.
The [held-out confirmation assessment](benchmarks/results/gds-application-confirmation-v1/FINDINGS.md)
now meets the original quality conditions on all three graphs and both thread
settings. Selected-method recall@16 is 83.058%, 50.992% and 45.366%, versus learned
GDS's 75.021%, 42.180% and 32.203%. The first two selected methods are conventional
resource allocation and tie the strongest structural controls. The path model's
communication advantage over resource allocation is uncertain. The paired analysis
supports a pooled quality advantage over learned GDS on these fixed graphs, but
does not establish one-point noninferiority against every structural control/view.
No cost, novelty or complete release gate is closed by that quality result.

## Novelty and likely reception

Our strongest prospective contribution is an exact, inspectable execution layer
that lets bound graph queries control preparation and reuse across graph models,
while retaining explicit evidence, score-support and invalidation contracts.
Whether that combination merits a research novelty claim requires a fuller
literature comparison and confirmed execution results.

The individual prediction methods are established: random-walk/path learning has
longstanding prior art, including [Lao, Mitchell and Cohen, 2011](https://aclanthology.org/D11-1049/).
Caching, conjunction ordering and common-neighbor scores are conventional. Using
an existing algorithm successfully is a product advantage when the application
benefits; it is not a new prediction algorithm.

The path backend now exposes target-independent two-hop state that the query
executor can retain for later scoring batches and discard at a root-window
boundary. This gives query execution explicit control over model-intermediate
lifetimes. Dynamic programming and intermediate-state reuse themselves are not
new algorithms. Their system value needs comparison with both full-feature
precomputation and hand-managed use of the same prepared-state primitive; the
revised fresh-query protocol includes those controls.
The [completed second campaign](benchmarks/results/graph-pipeline-development-v2/FINDINGS.md)
validates all 216 workers and more nonempty workloads. Prepared execution helps
the automatic pipeline, but it still has about 53% greater geometric latency than
the best manual control on this new mix. The prepared-state control usually wins;
the current implementation cannot claim automatic-planner parity from that result.

The [third campaign](benchmarks/results/graph-pipeline-development-v3/FINDINGS.md)
holds the input files fixed, improves ordinary target completion and adds a
same-kernel fresh-prefix ablation. All 252 workers agree on answers; automatic
execution still has about 46% greater geometric latency than the best manual
control. The descriptive retained-state benefit is 1.120x across this mix, with
regressions and timing differences even in cases that perform no preparation.
Repeated third-hop completion remains substantial: on the largest communication
case, the automatic pipeline reports about ten times the full-feature control's
type visits. Eliminating that repeated inference work is a stronger next target
than polishing warm answer-cache overhead. These results do not establish novelty.

The [stage-target preparation follow-up](benchmarks/results/graph-pipeline-development-v5/FINDINGS.md)
retains two more complete 324-worker campaigns, including a repeat after an
optional-backend capability fix. The corrected implementation still has about
27% greater geometric latency than the strongest manual control. Coalescing
cuts counted visits by about 90% on the largest communication case, yet has no
aggregate latency advantage over prefix reuse. The counters include edges rejected
before weighted accumulation; they do not measure FLOPs. The full pipeline's
kernel, validation, row-construction and serialization costs remain material.
These results improve our understanding of the implementation, without establishing
the release's competitive or novelty claim.

The [binding follow-up](benchmarks/results/graph-pipeline-development-v6/FINDINGS.md)
adds 360 verified workers, but its 1.018x descriptive deduplication ablation and
33.5% automatic overhead reinforce the need to reassess the architecture. The
[next research milestone](benchmarks/v1/EXECUTION_THESIS.md) is to identify a useful
graph/inference application and quantify its avoidable model, scheduling and
memory costs. Quail's expensive transformer workloads and specialized forward
execution do not imply equivalent headroom for this CPU path scorer.

The [existing-transformer diagnostic](benchmarks/results/spider-headroom-development-v1/FINDINGS.md)
finds only a descriptive 1.180x scalar/prefix ratio for current pair-local reviews.
A proposed shared-context task shows 2.482x, but fails numerical equivalence;
neither establishes a new execution contribution. The
[targeted prior-art review](benchmarks/v1/EXECUTION_PRIOR_ART.md) also identifies
SubGCache, Reforge and exact incremental GNN computation as relevant existing
work. Graph context and intermediate-state reuse alone are insufficient novelty
claims. The immediate task is a useful application and strong combined reference.

The following is our assessment, not measured user feedback:

- Database practitioners will likely care most about a small integration, clear
  snapshot refresh costs, bounded resource behavior and latency on their own
  candidate distributions. A cache that already fits may be hard to improve on.
- Systems researchers will ask whether savings survive optimized caches,
  precomputation and native database execution, and which optimization causes
  each improvement. The cold/warm and fusion/ordering controls address that.
- Graph-ML researchers will ask for held-out quality, full positive denominators,
  stronger models and broader query tasks. Development wins from standard
  structural methods alone are insufficient for an inference-quality novelty claim.

Broader neural graph work is relevant too: [NGDBench v2](https://arxiv.org/abs/2603.05529v2)
combines noisy observed graphs, latent graphs, Cypher queries and dynamic updates
across five domains. We have not evaluated Orbweaver on it; pair-ranking evidence
cannot be presented as parity on that scope.

A compelling 1.0 demonstration must show useful composed graph queries where
inference results determine subsequent candidate work, and where the planner
avoids substantial computation on previously unscored inputs. It should expose
the physical plan and work counters, preserve the same answer contract under
strong batched/native controls, and identify the benefit of each optimization.
Sharing preparation, setup break-even points and correct graph/model invalidation
are supporting requirements. Typed expansion now permits predictions to control
subsequent graph work, with independent semantic tests and a native Cypher check.
That capability alone is not a novelty claim. The fresh-query comparison includes
hand-ordered targeted and full-feature controls so conventional predicate pushdown
cannot be presented as a win over the strongest pipeline without measurement.
The [first measured comparison](benchmarks/results/graph-pipeline-development-v1/FINDINGS.md)
finds about 90% greater geometric request latency than the best manual control,
despite avoiding eager traversal work. Four of six conditions produce no rows;
the next workload mix also needs more useful nonempty results.
The release claim should name the application class and measured
advantage. Broad superiority remains unsubstantiated while the acceptance gates
are open.
