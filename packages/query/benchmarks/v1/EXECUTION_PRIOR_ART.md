# Execution research: prior art and the next decision

Assessment dated 2026-09-26. This is a targeted literature check for choosing the
next experiment, not an exhaustive novelty review or a benchmark comparison.
External performance numbers are the authors' results and are not comparable to
our different models, inputs and hardware.

| Work | Relevant established idea | Consequence for Orbweaver |
|---|---|---|
| [Quail launch](https://fsdatalab.github.io/blog/introducing-quail/) | Query-controlled KV lifetimes, grouped join attention and specialized GPU execution, evaluated against prefix-cached vLLM with the same logical plan | A Cypher frontend or ordinary prefix reuse does not reproduce the research contribution. A new system claim needs an execution change and an ablation. |
| [SubGCache, AAAI 2026](https://ojs.aaai.org/index.php/AAAI/article/view/40827) | Cluster queries by retrieved subgraph, build a representative shared context and reuse its KV | Shared whole-graph context for candidate reviews has direct prior art. It changes the input context and needs application quality validation; it cannot be called exact reuse of different original prompts. |
| [Reforge, arXiv v2](https://arxiv.org/abs/2501.08547v2) | Selectively recompute precomputed GNN embeddings and parallelize computation graphs | Reusing graph-model intermediates is already a developed systems direction. Its approximation/accuracy tradeoff must be distinguished from an exact contract. Earlier versions were titled OMEGA. |
| [Incremental GNN Embedding Computation, ICDE 2026](https://arxiv.org/abs/2603.20622v1) | Reorder fine-grained operators to update affected computation while preserving full-neighbor semantics | Exact graph-update-aware inference is not a blank research area either. An incremental backend would need a comparison with this class of methods. |
| [GraphSeek](https://arxiv.org/abs/2602.11052) | LLM planning over a semantic operator catalog with a separate deterministic execution plane | An inspectable graph/LLM operator catalog is useful product architecture, but not sufficient evidence of novel execution. |
| [Text2Cypher](https://arxiv.org/abs/2412.10064) | Train/evaluate translation from natural language to Cypher | These datasets help query generation and frontend coverage. They do not alone specify repeated in-query model calls, graph evidence and hardware costs for an inference benchmark. |

## Recommended product direction

Make the next vertical slice an inference-bearing graph query: native graph
candidate selection, an expensive semantic relation test, a per-root existence
condition, and graph expansion driven by surviving results. Use a concrete task
such as finding entities with at least one review-ready missing relationship.
This is a proposed workload specification, not a claim of useful accuracy from
the current six-class classifier or implemented AI-Cypher syntax.

Keep Neo4j responsible for ordinary graph operations. Use an existing inference
backend for model execution. Quail/vLLM are the appropriate CUDA references;
the local MLX classifier is a way to investigate input structure and costs on
available hardware, not a performance substitute for their H100 comparison.
Retain the current CPU graph models as supported reference backends and the
existing correctness/provenance work as infrastructure.

The product opportunity is making this composed workload simple, bounded and
inspectable. A systems novelty claim is a separate, still unproven opportunity:
the graph query must expose a dependency or state lifetime that allows expensive
work to be removed beyond what the best ordinary inference stack already does.
Graph syntax, a larger model, or a scalar baseline does not establish that.

## Evidence required before more optimizer development

1. Choose an application with useful positive and negative outcomes, source
   evidence and a held-out quality check. Preserve exact input semantics between
   execution arms. A shared-context redesign is a separate model-quality study.
2. Build the strong reference first: native graph filtering, batching with prefix
   caching together, safe early termination, explicit resource limits, and
   appropriate precomputation. Include updates and graph/model transfer costs.
3. Attribute elapsed time, not only token or edge counts. If the removable
   fraction is p, even eliminating it entirely has an Amdahl bound of 1/(1-p).
   A 2x target requires at least half the original elapsed time to be removable.
4. Write down the additional graph/query fact the reference does not exploit,
   its exactness argument, the closest prior art and an achievable cost estimate.
   Reject hypotheses without sufficient residual headroom before implementation.
5. Test one mechanism with an ablation and adverse cases. Expand to a release
   campaign only after it produces a material matched advantage with preserved
   quality. Attribute improvements supplied by Quail or another backend to it.

Keep three questions separate in the results: an existing external stack tests
competitive value; the same new primitive hand-managed tests automation overhead;
and disabling that primitive tests its causal benefit. Sharing our primitive
with a manual control is good experimental practice, but the resulting planner
tax must not be mistaken for a test of whether the primitive improves existing
software. Conversely, beating an unbatched scalar loop is not a strong external
comparison. The release claim needs all three kinds of evidence.

The existing release gates remain unchanged and open. Automatic execution
approaching a hand-written optimum is valuable automation evidence, but cannot
by itself substantiate a new inference algorithm. Warm completed-answer lookup
remains a deployment control; it is not the mechanism behind Quail's results.
