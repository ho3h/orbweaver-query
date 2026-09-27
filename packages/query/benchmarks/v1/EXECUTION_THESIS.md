# Execution thesis reset: establish the opportunity before another optimization loop

2026-09-26. Development decision following the user's request to step back from
repeated parity campaigns. All acceptance gates remain open and unchanged.

## Current decision: Mac-only public preview (2026-09-27)

The user has constrained all further work to a MacBook and requested public
release preparation. This supersedes the H100-dependent next steps in the
historical investigation below. Keep the CUDA reference/profile as unexecuted
research; do not wait for a GPU or substitute CPU planning for GPU evidence.

Prepare the existing NumPy runtime for public evaluation: harden claims, validate
installed distributions natively on the Mac, and reproduce exact bound-target
performance with strong controls and complete serialization/setup boundaries.
Retain the adverse composed/native comparisons. No new model selection uses the
opened confirmation labels. A public preview is distinct from satisfying all
original competitive 1.0 gates; none is silently waived.

## Historical decision and investigation

Current checkpoint: the Quail execution reference is frozen and CPU-preflighted;
the original-workload GDS reservation check has completed successfully at one and
four threads. No model retuning or further reservation campaign is indicated by
that result. The next architectural decision needs the supported GPU run and an
application-derived profile of residual expensive work. Earlier investigations
below are retained as the rationale, not instructions to repeat completed work.
The broader matched GDS quality/cost and other original release gates remain open.

The separate matched GDS application comparison now has a
[version 2 protocol](GDS_APPLICATION_PROTOCOL.md). Its native arm uses the validated
per-source adaptive queues and 60-second task retention. Preparation, repeated
feature generation, candidate transfer and Python ranking are charged; full-score
answer checks and resource checks remain outside timing. The small live fixture
passes at one/four threads, including exact tie handling and zero outstanding task
reservations. The [complete 18-worker development campaign](../results/gds-application-development-v2/FINDINGS.md)
now retains all selected models' prediction artifacts, 48 condition summaries and
432 timed request samples. The 352-file archive verifies, its restored frozen
summary is byte-identical, and a separate numerical implementation reconstructs
all development metrics and returned rankings. The separately frozen confirmation
assessment below uses those same prediction artifacts.
This advances the separate GDS application assessment; it is not another CPU
planner optimization or the GPU research milestone, and does not replace the
earlier interrupted/failed campaigns.
During this campaign, host process snapshots showed unrelated Python computation
overlapping a live worker. The timestamped observation is retained with the run
as `HOST_ACTIVITY_OBSERVATION.json`. This violates the intended workload-isolation
condition: retain the full campaign for correctness and quality assessment, but
treat its timing as descriptive evidence with an unquantified contention effect.
A numerical replay cannot certify host isolation, and these timings alone cannot
close a competitive latency gate. Do not silently restart or discard the run.

The [confirmation protocol](GDS_CONFIRMATION_PROTOCOL.md) fixed the quality
assessment before labels were inspected. Its evaluator and synthetic fixtures
passed within the 306-test core suite (seven optional skips), and were committed
before the separate manifest was frozen. The
[completed held-out assessment](../results/gds-application-confirmation-v1/FINDINGS.md)
retains all 18 workers and 460 positive queries, without new model selection.
The original gate B quality conditions pass at both thread settings, with a
supported pooled advantage over learned GDS. Stronger simultaneous one-point
noninferiority against every structural control/view is not established.
The opened labels must not become a new tuning target. Cost advantage and all
complete release gates remain unproven; the next research step is still GPU
profiling of a useful graph-dependent execution mechanism.

The [separate profiling harness](../results/quail-profile-preflight-v1/FINDINGS.md)
is now bundled with the original package version, avoiding bridge-version drift
against the frozen reference. Its real request-runtime CPU preflight and synthetic
multi-process trace-analysis tests pass, including restored replay. Worker RPCs
and GPU traces remain unexecuted. On an approved H100 host, complete the original
unprofiled runs first, then use this separate capture to attribute remaining cost.
Do not infer headroom or implementation success from CPU preparation alone.

Prioritize an AI-Cypher execution layer that combines native graph selection with
an established inference backend. Reuse Quail's inference machinery where its
operator/model contract fits; do not start by rebuilding its GPU engine. Retain
our exact graph-model backends and correctness infrastructure, but stop treating
further CPU planner tuning as the route to Quail-like gains.

There is no measured Orbweaver-versus-Quail performance gap: the two sets of
numbers use different tasks, models, hardware and controls. The demonstrated
difference is architectural. Quail controls expensive transformer execution;
our current runtime controls graph features and scoring calls. A new semantic
backend requires a separate contract for prompt/input identity and dependencies;
it cannot pretend to satisfy `GraphModel`'s source-only feature contract.

Keep the next decision bounded. Finish the published-model quality comparison
on the labeled reference, then assess one application with substantial dependent
graph traversal and repeated expensive semantic work. Build its strong native
Neo4j plus inference-backend reference first. Compare the graph-aware prototype
against that reference and disable its proposed mechanism in an ablation. The
same primitive managed by hand is an additional automation-overhead control.
Do not launch another broad optimization campaign before a measured cost
breakdown supports the existing 2x practical-class target.

Make that headroom test quantitative: if a proposed mechanism can affect a
fraction `f` of end-to-end reference time, eliminating that cost completely has
an optimistic speedup ceiling of `1 / (1 - f)`. Affecting 10% permits at most
1.11x; reaching 2x requires eliminating at least half of reference time. Use
non-overlapping measured costs and include added planning/transfer work in the
achievable estimate. This bound screens hypotheses; it is not measured speedup.
Warm completed-answer lookup remains a reuse/overhead control, not this research
target. A Text2Cypher corpus can test query coverage and candidate shapes, but
does not by itself establish inference cost, answer quality or execution headroom.

Quail already supports semantic joins and EXISTS/NOT EXISTS. Adding those names
to graph syntax is not the contribution. The hypothesis must identify additional
work removed by graph dependencies or state lifetimes beyond the reference.
If no such opportunity survives the strong control, reject that performance
hypothesis. A useful graph/inference integration and a new systems result are
different release claims, and backend-provided speedups belong to the backend.

The pinned Quail source already provides a concrete integration route:
[`Apply(ids="pairs")`](https://github.com/fsdatalab/quail/blob/41b883b838687cfbf018080f068f3e81bf2f8e64/quail/logical/nodes.py)
accepts a registered function returning allowed pairs of existing document row IDs.
It supports both per-batch survivor input and a barrier over all survivors.
[`JoinStage.pairs_from`](https://github.com/fsdatalab/quail/blob/41b883b838687cfbf018080f068f3e81bf2f8e64/quail/physical/nodes.py)
connects those pairs to a semantic join, and the
[`partner_maps` execution path](https://github.com/fsdatalab/quail/blob/41b883b838687cfbf018080f068f3e81bf2f8e64/quail/backends/quail/graph.py)
restricts each anchor to its supplied partners. Therefore candidate-edge
restriction alone is already representable in Quail; it does not justify a new
GPU backend or a novelty claim. The [experimental bridge](../../QUAIL_BRIDGE.md)
now verifies the actual planning, pair restriction and projection interfaces,
including the full 339-pair SciFact graph domain in a disposable Neo4j instance.
This is CPU correctness evidence, not a CUDA measurement. It checks application-ID
domains, captured-content identity and result multiplicity. Its readout must also
match the application's class contract; a Boolean Quail predicate cannot silently
replace the three-way SciFact classifier.

## What the Quail comparison actually teaches

The launch evaluation reports 1.84x geometric speedup over tuned stock vLLM on
29 queries (27 wins), with 14.04x on the larger BIO-4 experiment. It also reports
a 2.32x slowdown on AGENT-1. These are the authors' results, not our reproduction.
The vLLM controls receive the same model, prompts, logical plan and optimized
operator order, plus prefix caching, cache-friendly request ordering and the
same tokenizer. A pipelined vLLM control is included where applicable.

Quail's system has a concrete mechanism for changing expensive work:

- Query-driven KV retention keeps reusable document prefixes across operators,
  discards predicate suffix state, and releases filtered or expired documents.
- Batches of related requests and CPU/GPU overlap reduce scheduling overhead
  that would otherwise leave the accelerator idle.
- Join attention groups partners sharing an anchor; it changes how the forward
  pass consumes shared KV, beyond merely storing a prefix between requests.
- A restricted output head computes only the answer classes needed by the query.
  Fused kernels reduce launches and intermediate memory traffic.

On BIO-4 the authors identify host overhead as the primary inefficiency, with
KV recomputation a second source. Stock vLLM is about 27.55x their optimistic
hardware lower bound; Quail is 1.96x. The reported token accounting implies only
about a 1.23x ratio in fresh-token work (174.6M / 142.3M), which cannot by itself explain
the 14.04x wall-time difference. That arithmetic is our inference from their
reported minimum and regret counts, not a per-optimization causal ablation.
We have not independently reproduced or apportioned their headline speedup.

Primary sources, pinned code at 41b883b838687cfbf018080f068f3e81bf2f8e64:

- [Launch methodology and results](https://fsdatalab.github.io/blog/introducing-quail/)
- [Enabled vLLM prefix caching and request backends](https://github.com/fsdatalab/quail/blob/41b883b838687cfbf018080f068f3e81bf2f8e64/quail/backends/vllm.py)
- [Attention and fused kernels](https://github.com/fsdatalab/quail/blob/41b883b838687cfbf018080f068f3e81bf2f8e64/quail/backends/quail/executor/attention.py)
- [Restricted answer readout](https://github.com/fsdatalab/quail/blob/41b883b838687cfbf018080f068f3e81bf2f8e64/quail/backends/quail/executor/readout.py)
- [Survivor-aware retention](https://github.com/fsdatalab/quail/blob/41b883b838687cfbf018080f068f3e81bf2f8e64/quail/backends/quail/retention.py)

## What our evidence establishes, and what it does not

Orbweaver Query currently has a useful correctness and integration foundation:
immutable graph/model identities, exact targeted path features, structural
scores, model contracts, bounded execution, complete bag/null/provenance semantics,
and an adapter to Neo4j. It has not demonstrated a Quail-like systems advantage.

We chose a small CPU path scorer and structural models before establishing the
application's dominant avoidable cost. Query scheduling around these backends
cannot be assumed to have the economics of long-document transformer inference.
Work counters are not elapsed time: the v5 campaign reduced counted type visits
by 90% on one condition without a corresponding large wall-time improvement.

Our strongest manual controls intentionally receive the same improved inference
primitives, intermediate state and candidate targeting. Those controls answer
whether automatic orchestration approaches a skilled manual implementation.
They cannot establish a new inference algorithm simply because the automatic
planner eventually removes its own overhead. Keep these controls; do not weaken
them or relabel conventional deduplication/caching as novel inference.

The v6 campaign was already running when the user raised this concern. Finish,
verify and retain it. Do not use its outcome to trigger another full campaign of
small Python executor edits. Those edits can be useful maintenance, but the next
research milestone is evidence for an execution advantage on a useful application.

## Next milestone: a bounded architectural investigation

1. Specify three application-derived graph/inference query shapes before timing:
   repeated node/edge evidence across semantic predicates, a correlated existence
   query with expensive inference, and a graph-model query with overlapping
   computation. These are candidate investigations, not implemented features or
   new accepted workloads. Include low-reuse and adverse cases, and identify who
   needs each answer. A larger model alone is not a justification.
2. Build one strong end-to-end reference for each feasible shape. Delegate ordinary
   graph operations to Neo4j where appropriate. Use well-batched model execution,
   enabled intermediate/answer caches, appropriate precomputation and hand-tuned
   early termination. Charge graph export, model loading, transfer, setup and
   invalidation at the same boundaries. Keep the strongest manual equivalent as
   a separate automation-overhead control.
3. Attribute time and bytes to graph access, candidate generation, model forward
   work, repeated model state, scheduling, transfers and output assembly. Establish
   an optimistic lower bound and an achievable cost estimate. Counter reductions
   alone do not prove headroom. Report which costs the proposed engine can change.
4. Select one graph/query fact that permits a real execution change: overlapping
   graph-model subcomputations, shared entity/document state across semantic joins,
   or safe termination once an existence result is known. Respect actual model
   dependencies; shared node IDs do not automatically imply shareable activations.
5. Implement the smallest vertical prototype that tests that mechanism, with
   independent answer/quality checks and an ablation. Prefer existing Quail/vLLM
   infrastructure for an LLM backend; do not port CUDA kernels by default. For a
   graph-neural backend, compare full/precomputed and sampled/batched alternatives
   under exactly the same inference semantics and evidence.
6. Expand implementation only if the measured mechanism has enough headroom for
   the existing release gate's repeatable 2x practical-class advantage. If the
   optimistic bound cannot support that target, record the rejection and examine
   the next hypothesis. Do not manufacture expensive work, weaken the baseline,
   hide quality loss or reduce the original acceptance contract.

The choice between a graph-model-focused product and an AI-Cypher frontend with
LLM semantic operators is material and remains explicit. The current scorer is
a reference backend, not evidence that every relevant graph model shares its
performance characteristics. Neither path is assumed novel merely because it
uses graph syntax. Identify prior art and the graph-specific execution benefit
before presenting a public 1.0 contribution.

No paid GPU run, external publication, language-conformance claim or release is
authorized by this document. Local investigation and implementation can proceed
within the existing task. The GDS quality/cost, four-thread, resource/update and
compatibility requirements remain part of the full objective.

## Follow-through: the existing transformer application

The root Orbweaver application already has a Qwen3-4B transformer with a trained
six-class repair head. Its current pair scan constructs a separate local graph
context for each candidate. This is a more relevant place to investigate costly
model execution than increasing the number of cheap path-score microbenchmarks.
The head already bypasses vocabulary projection, so Quail's restricted-output
readout is not an additional opportunity here.

The [bounded diagnostic](SPIDER_HEADROOM_PROTOCOL.md) compares scalar execution,
ordinary batching and exact prefix retention on existing application fixtures.
It distinguishes current pair-local input from a proposed shared graph context;
the latter changes the inference task and cannot be substituted silently.
It is an opportunity assessment, not an Orbweaver-versus-Quail result.

The [targeted prior-art review](EXECUTION_PRIOR_ART.md) identifies direct overlap
with SubGCache for shared graph-context KV, Reforge for graph-model intermediate
reuse, and incremental GNN work for exact update-aware computation. These are
reasons to demand a precise contribution, not to treat the graph domain as
unoccupied. The recommended next vertical slice combines native graph selection,
expensive semantic relation tests, per-root existence and dependent expansion.
Its reference must combine batching, prefix reuse and safe early termination
before we identify any residual execution opportunity.

The [completed diagnostic](../results/spider-headroom-development-v1/FINDINGS.md)
retains all 45 measurements and rejected captures. Current pair-local reviews
show only a descriptive 1.180x scalar/prefix ratio. Shared context shows 2.482x
but violates the declared numerical-equivalence contract; no scoped case permits
early termination. This is a rejection of that probe as a release demonstration,
not a reason to tune its cache repeatedly. Establish useful application outcomes
and a combined strong reference before further performance implementation.

The [SciFact application reference](../results/scifact-reference-development-v1/FINDINGS.md)
now provides independent labels and native graph query verification. The fixed
Qwen prompt reaches development macro F1 0.77846 on all 339 distinct cited pairs;
its shared-document witness query has F1 0.68421. All 12 native Cypher checks
match the set-based reference. This is a qualified development model and a useful
low-fanout application, not a speedup or competitive-quality result.

The [completed published-model comparison](../results/verisci-reference-development-v1/FINDINGS.md)
evaluates the recommended VeriSci pipeline on that same complete candidate domain.
Its macro F1 is 0.72981 versus Qwen's 0.77846. The paired development interval for
the difference is [-0.01745, 0.11576], so it supports neither a superiority claim
nor noninferiority within one percentage point. All 12 native graph conditions
also match for VeriSci and its controls, including an actual contradiction veto.
Keep the fixed Qwen model as a viable application reference; do not tune it on
this outcome or promote the 2020 comparator to a claim against today's best models.
The next step is a strong execution reference using the existing Quail pair-input
route where its readout contract fits, plus an application-derived assessment of
residual graph-specific headroom. Preserve the stronger-baseline requirement and
the full set of open 1.0 gates.

The bridge establishes that native graph candidate restriction can be composed
with Quail without implementing a GPU engine. Both barrier and per-batch plans
preserve the captured candidate domain. Integration tests retain an upstream
right-stream finalization failure. Unfiltered plans have no upstream survivor
stream; optional document filters use materialized barriers. No inference or
timing result is inferred from these CPU tests. Build
the next performance decision around measured residual costs on a supported CUDA
stack; the current low-fanout SciFact case is a correctness/adverse reference,
not a demonstrated source of 2x execution headroom.

The [matched execution reference](QUAIL_EXECUTION_PROTOCOL.md) is now frozen and
CPU-preflighted. It lowers the same candidate join into Quail's existing vLLM
request runtime despite the public request planner's Apply restriction. Both
plans preserve the exact 339-pair domain and the same real-tokenizer input
sequences (150,780 requested tokens). The archive restores and replays, and the
runner requires identical model files, physical plans and a supported H100 SXM.
No CUDA inference, quality or timing comparison has run. This establishes a
concrete strong-reference experiment; it does not establish residual headroom or
an Orbweaver execution advantage. Hardware access is the remaining requirement
for this diagnostic, while the broader original acceptance work remains open.

## Stronger baseline finding and next decision

The [native GDS application attempt](../results/gds-application-interrupted-v1/FINDINGS.md)
was stopped after four completed workers, retaining the interrupted fifth and
all frozen inputs. The matching GDS source uses sorted arrays for its bounded
result queue; our full-domain global topN made the reference unnecessarily
expensive. In the [bounded diagnostic](../results/gds-queue-diagnostic-development-v1/FINDINGS.md),
the same trained model returns exactly the same answers in 6.85 rather than
31.76 seconds using small per-source queues with exact cutoff-tie overfetch.
That 4.64x descriptive improvement belongs to the native baseline. Both request
formulation and output assembly change, so this is not an isolated queue-kernel
ablation. Do not restart the original campaign or present its partial timings as
evidence of an Orbweaver advantage.

The [bounded six-condition follow-up](../results/gds-queue-generalization-development-v1/FINDINGS.md)
completed four conditions and failed both collaboration conditions. The completed
native controls preserve exact outputs and improve request time descriptively,
but repeated collaboration requests hit GDS's reservation guard. Retain this as a
failed suite. The subsequent task-lifetime investigation below addresses the
failure without replacing those results; neither baseline improvements nor
failures establish an Orbweaver win.

The [small resource reproduction](../results/gds-memory-diagnostic-development-v1/FINDINGS.md)
rejects transaction splitting as a sufficient remedy. Zero-retention task cleanup
can erase completion events before the memory listener receives them; retaining
completed task records for 60 seconds removes the observed reservation growth
without changing the 20 checked outputs. The
[original-workload check](../results/gds-retention-application-development-v1/FINDINGS.md)
now validates that setting at one and four threads, with ten exact repeated
outputs, unchanged full-score matrices, zero outstanding reservations and task
record expiry. This finishes the bounded reservation investigation. It does not
repair or replace the failed timing suite, establish long-running stability, or
justify another broad CPU tuning campaign.

The performance research decision remains sequential: establish a strong combined
native graph/inference reference, profile its residual expensive work, and test
one graph-dependent mechanism. The prepared Quail/vLLM CUDA experiment supplies
the execution reference, while the low-reuse SciFact application remains an
adverse case. A useful dependent traversal/existence application must still show
enough avoidable cost after prefix reuse, batching, native filtering and safe
early termination. No additional broad CPU optimization campaign is justified
by the current evidence. If the measured headroom cannot support the existing
2x practical-class target, reject the mechanism rather than iterate around it.

The [dependent correctness reference](../results/quail-dependent-development-v1/FINDINGS.md)
now composes document filters, captured graph candidate selection and a semantic
pair predicate through Quail's actual dependency runner. Both document roles can
filter; the bridge rejects streaming composition affected by the pinned upstream
defect and uses a materialized barrier. Six native conditions over all 339 SciFact
pairs match independent Cypher under fixed decisions. This supplies a richer
execution reference, not an additional optimization or evidence of headroom:
document filters themselves add model work. Correlated existence, live dependent
multi-hop traversal and GPU profiling remain open. The frozen single-join CUDA
reference is unchanged; these new operators require their own matched profile.
