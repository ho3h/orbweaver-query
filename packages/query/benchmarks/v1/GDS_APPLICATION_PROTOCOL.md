# Native per-source recommendation requests

Version 2, declared before new timing. This fills the matched application-cost
and one/four thread development gaps; it does not reopen model selection or
confirmation. The original interrupted v1 campaign and the failed queue
diagnostic remain separate immutable evidence, with no substituted results.

Reuse the outer graphs and 64 development sources from the original GDS
comparison. Freeze the development-selected GDS configurations: rich FastRP256
with 16 negatives for collaboration; FastRP64 for friendship and communication.
Freeze Orbweaver's selected methods: resource allocation for collaboration and
friendship, path model for communication. Keep the original fitting split and
parameters. Train the selected GDS pipeline in each fresh process. For the path
arm, refit from the original evidence/fitting arrays. No confirmation data is
copied or opened. Node IDs, not internal Neo4j IDs, identify results.

Each request supplies the ordered 64 source IDs and returns up to 16 non-self,
non-neighbor recommendations per source. Preserve empty sources. Unsupported path
predictions remain missing; zero structural scores are valid and participate.
Rank by score rounded to 12 decimal places, then application string ID ascending.
This explicit numerical tie contract avoids treating floating summation order as
meaningful ranking information. Retain raw scores and both original raw-score and
rounded-score uniform-tie quality metrics; do not silently replace earlier quality
results. The actual deterministic-ID recommendation recall is reported separately.

GDS `topN` is global. Timed requests use the validated singleton-source strategy:
prepare each source's candidate count and singleton label in Neo4j, include those
labels in the projection, and charge that preparation separately. For each source,
request min(32, candidate count) predictions with sampleRate=1 and threshold=0.
Group unresolved sources in one Bolt query per round. Double their limits until
the lowest retained rounded score is below the kth score or the entire source
domain is returned. Rank transferred predictions in Python using the declared ID
tie rule. This gives exact answers despite GDS's unspecified cutoff-tie order.
Retain all five native request outputs and their rounds, procedure calls, returned
pairs and maximum topN (cache construction, one warmup and three timed requests).
Repeated native feature preparation, Bolt transfer, overfetch and Python ranking
remain inside each request timer. No learned-feature cache is introduced.

Before timing, use the global queue with the complete directed candidate count
(an upper bound on unique undirected pairs) to stream every score once, fan out
undirected predictions to queried endpoints, and independently calculate expected
recommendations and quality. Missing/duplicate predictions invalidate the worker.
This full-domain correctness stream is untimed and cannot supply a timed answer.

Controls: native GDS structural scalar resource allocation, shared-traversal
Cypher resource allocation and Adamic-Adar, and a manual equivalent of the selected
local scorer (sparse matrix multiplication for structural scores; direct backend
calls for path scores). Shared-traversal Cypher prepares node degrees once, ranks
positive two-hop candidates, and fills with valid zero-score candidates as needed.
Charge that preparation separately. GDS's learned pipeline reruns its node-property
steps during prediction; retain this native behavior. Precomputed selected-model
and GDS recommendation lookups are explicit warm-answer controls; measure their
construction through the actual request, never treat oracle validation as free
preparation. These controls cannot establish new prediction algorithms.

Use the same read-only adapter/EXPLAIN boundary and fetch size for every request.
Local execution reads source IDs over Bolt, computes against an exported immutable
snapshot, and ranks results. Structural native arms rank in Neo4j; the learned GDS
arm transfers its adaptively selected candidates and ranks them in Python. This
application comparison permits different execution strategies. All produce the same output
schema and JSON serialization; algorithms may produce different recommendations.
Validate each arm against its own independent full-score reference. Record graph
import, GDS source preparation, projection, graph export, model fitting and answer-cache construction
separately. Native arms do not pay export. Do not compare total setup as if both
algorithms had identical fitting tasks. Report amortization and whole-process RSS,
not unsupported per-arm memory claims.

Freeze 18 workers: three datasets, one/four configured threads, three repetitions.
Worker order uses seed 7610; condition order uses seed 7611 plus worker index.
One unmeasured request warms each arm, followed by three measured requests.
Set GDS training, FastRP, degree and prediction concurrency to the chosen setting;
set native Python numeric-library thread ceilings to the same value. The Python
executor can remain serial. These are configured algorithm/library ceilings, not
OS CPU affinity or proof of actual core utilization. Scalar Cypher/GDS functions
have no concurrency parameter and use the Community slotted query runtime.

Require the architecture guard, pin Neo4j/GDS 2026.09.0 and native Java
21.0.10+7-LTS, use an 8 GiB heap, 64 MiB page cache and 900-second transaction
ceiling. Run workers sequentially without overlapping other model/test workloads.
Set GDS progress tracking retention to 60 seconds and verify the effective setting
is `1m`, with progress tracking enabled. The native GDS listener-order defect at
zero retention was diagnosed separately; the 60-second workaround preserved full
scores and all repeated answers in the collaboration one/four-thread audit.
After projection, fitting, the full-score audit and each of the five GDS requests,
save native memory summaries/details and active progress outside timing. Require
zero active tasks and zero task reservations. This is an operational prerequisite,
not an Orbweaver performance improvement. It does not establish concurrent or
long-running service reliability.
Keep all failures, full scores, returned recommendations and raw timing samples.
Four-thread fitting may change model outputs; report new quality and classifier
selection instead of assuming equality to one thread or historical x86 results.
Summaries require every worker. No release gate closes from development selection
or from this fixed, repeated-source workload. The separate CUDA investigation
remains the next research-performance decision.

Primary references: [GDS prediction](https://neo4j.com/docs/graph-data-science/current/machine-learning/linkprediction-pipelines/predict/),
[GDS training](https://neo4j.com/docs/graph-data-science/current/machine-learning/linkprediction-pipelines/training/).
