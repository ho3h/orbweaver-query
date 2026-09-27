# Query runtime experiment 3

Experiment 2 retained bitwise parity and the primary reuse gain but failed its
regression gate (distinct sources +21%, the fixed single query +28%). Profiling
identifies scalar conversion generators in adjacency decoding and ID restoration.
This iteration replaces them with NumPy bulk conversion, preserving the same
adjacency cache and arithmetic. Keep both previous campaigns and all their
timings. The experiment 2 acceptance criteria remain unchanged.

The first completed campaign (`runtime-v1b`) passed the interleaved-source gate
with bitwise score parity, but packed execution regressed by about 25–28% on
distinct sources and hubs. Preserve that campaign. This iteration caches decoded
adjacency only for nodes touched during one source expansion. It removes repeated
NumPy scalar/slice conversion for the same node across typed-prefix states,
while preserving arithmetic and the full global degree/evidence context.
The new intermediate memory must remain visible in process RSS. Add a retention
gate: grouped median total batch time may be at most 15% slower than the legacy
cache on every workload. No fitting, candidate or coefficient changes.

Freeze this protocol, implementation sources and input artifacts before timing.
No fitting or label-based query selection is permitted. Existing WN18RR training
context and saved explicit-path weights are reused from the completed
`research/graph_native/runs/path-runtime-v1` experiment. Inputs must match that
experiment's recorded checksums. This experiment measures execution parity and
cost; it supplies no fresh predictive-quality result.

## Arms

- `legacy_consecutive`: the prior FlowGraph/ExplicitRuntime, with its one-source
  feature cache and no query reordering.
- `packed_independent`: packed snapshot, one expansion for each query.
- `packed_consecutive`: packed snapshot, one-source cache, input order.
- `packed_grouped`: packed snapshot, stable grouping and duplicate-query reuse
  within windows of 256, restoring input order and multiplicity.

All use the same explicit-path coefficients, graph and full candidate support.
No compressed or different predictive model may substitute for it.

## Workloads

Reuse the previous benchmark's `distinct256`, `shared256`, `hubs16`, and `single`
inputs. Add `interleaved256` by transposing the eight consecutive relation
requests for each of 32 shared heads. No targets or evaluation labels are read.
Shared queries are distinct relation questions; the primary comparison cannot
win merely by reusing identical final answers.

Three fresh processes for every arm/workload, randomized with seed 20260926.
Each process sets native thread limits to one before importing NumPy. Record
imports, artifact verification/loading, graph/model preparation, first full
result serialization, and total worker startup stages. Then run one warmup and
five measured whole batches, materializing and serializing all candidate scores
to JSON in every arm. Cache starts empty for each batch. Preserve each sample.
Measure warm execution and serialization separately; report their summed batch
times as the primary cost and peak process RSS including preparation. Record
numeric graph/parameter/feature bytes separately from process RSS.

## Verification and promotion

Workers save their first complete results and check every repetition against
those same candidate IDs and scores. A separate verification step compares every
arm with the legacy control for its workload: candidate IDs/order exact,
float64 scores with rtol=atol=1e-12, and top-16 candidate ordering exact using
stable ID tie-breaking. Any ordering difference blocks promotion and must be
diagnosed; numerical tolerance alone is insufficient. Reconstruct summaries
from raw samples and validate source/input/output digests.

The primary runtime gate requires median execution-plus-serialization at least
1.25x faster for `packed_grouped` than BOTH `legacy_consecutive` and
`packed_consecutive` on `interleaved256`, with correct predictions everywhere.
Report every workload, including any regressions greater than 15%. This gate
does not certify a universal acceleration or complete the public release.

This first campaign uses one graph and saved seed71 model. It includes process
preparation and output serialization but excludes database extraction/network
transfer. Live Neo4j, additional graph sizes and families, per-request latency,
installation and model-quality validation remain release requirements.
