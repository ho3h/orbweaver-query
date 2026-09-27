# Query-aware graph inference: release track

Status: the 0.1.0 candidate has completed its release-readiness audit. This track implements the
user's request for a GQL/Cypher counterpart to Quail that is strong enough for
public release. A working prototype or a faster microbenchmark does not complete
that goal. Existing graph-model experiments and their claims remain separate.

## Intended product

A portable execution engine makes typed graph-model operations available in
graph query workflows. Exact graph matching supplies bindings and evidence;
the planner batches model work, reuses compatible graph computation, and
returns scores or validated decisions with provenance. Cypher is the first
database integration. A language-independent logical plan and backend contract
must support additional GQL implementations without coupling inference to a
single database. Any supported dialect subset must be explicit and reject
unsupported constructs instead of silently approximating them.

The initial graph-native backend consumes structured graph evidence, with no
language-model backbone. Models remain replaceable. Ranking scores are not
probabilities. An optional LLM backend can be evaluated later without attributing
its capabilities to the graph model.

## Public release requirements

1. **Useful query surface.** Runnable local and Neo4j examples, parameterized
   Cypher integration, composable inference/filter/projection operations, and
   explain/profile output. Document the actual GQL/Cypher support boundary.
   Verify a real database end to end and preserve row order/multiplicity and
   null/unknown semantics at every supported boundary.
2. **Correct execution.** Compare optimized execution with an independent
   reference on randomized graphs, duplicate/multitype edges, isolated nodes,
   repeated/interleaved requests, empty results, ties, malformed inputs,
   graph/model updates, resource limits, and failure paths. Compare candidate
   support and scores before ranking. Reordering must not change model context
   or query meaning. No implicit independence assumptions or graph writes.
3. **Measured runtime value.** Reproducible benchmarks on real public graph
   evidence, realistic query mixes, a strong caching/batching baseline, and
   mechanism ablations. Include cold start, graph extraction/construction,
   serialization, memory, warm throughput and latency distributions. Preserve
   regressions. An acceleration claim requires matching frozen models, inputs,
   candidate support and outputs; quality/work tradeoffs need separate results.
4. **Useful model behavior.** At least one publicly reproducible trained model
   and meaningful task evaluation with strong references and honest candidate
   recall limits. Validate compatibility of relation schema and input features.
   Do not use runtime gains to imply a new architecture or factual calibration.
   Confidence/abstention claims require their own held-out policy evaluation.
5. **Reliable packaging.** Lightweight independent installation, versioned
   artifacts without executable deserialization, deterministic schema and
   snapshot identity, bounded execution, actionable errors, supported-platform
   tests, and clean-environment wheel/sdist verification. No dependency on local
   research directories or private services for the quickstart.
6. **Release material.** README, architecture/operator/semantics documentation,
   model card and dataset provenance, runnable quickstart and benchmark command,
   limitations, license notices, changelog, and an evidence-backed introductory
   article. Check every advertised command from the built distribution.

The final completion audit must inspect current artifacts and runtime evidence
for all six requirements. External publishing can follow a verified release
candidate; no release claim is made merely by adding packaging or documentation.

## Iteration 1: reuse without changing predictions

Diagnosis: the existing path-runtime study reports substantial shared-source
reuse benefits for explicit path features, with different tradeoffs for compact
query-conditioned models. Its per-node Python graph storage also dominates
startup memory. See `research/graph_native/results/path-runtime-v1/FINDINGS.md`.

Implement a separate NumPy-only package under `packages/query`. Begin with an
immutable packed graph snapshot, a model interface, the existing conventional
learned explicit-path scorer, and a bounded planner grouping compatible source
queries. Keep stable request identity and restore input order. Use exact schema
and content identity and avoid caches surviving snapshot/model replacement.

Controls: independent expansion per request; ordinary one-source consecutive
reuse; planned grouping within a bounded window; the original research runtime
as an external implementation oracle. Include already clustered shared sources,
interleaved shared sources, all-distinct sources, repeated identical requests,
and high-degree sources. Compare all candidate scores, including unsupported
targets, before applying any top-K.

Freeze benchmark inputs, protocol, source hashes, and acceptance criteria before
measurement. The first promotion gate is output parity plus a material gain on
interleaved shared-source queries, with regressions on other workloads reported.
This is a systems implementation gate, not the full public release gate.

## Subsequent work

Carry the strongest measured implementation forward. Add compact/shared graph
backends and cost-aware execution where evidence justifies them. Complete the
Cypher frontend and live adapter, portable training/export and model validation,
full end-to-end benchmarks, installation CI, and launch material. Revisit this
sequence when measurements identify a more important limit. Preserve failed
iterations and the full public-release objective.

## Completed implementation and experiments, 2026-09-26

The independent package now implements all planned operators, explicit evidence
and candidate contracts, safe numeric artifacts, bounded execution, a portable
trained example, and the live Cypher adapter. Its current source suite has 51
passing checks plus one opt-in live check, which passes separately. The rebuilt
0.1.0 wheel passes 49 runtime checks with three optional checks skipped, then
passes the actual Neo4j check in a newly created local database.

The user-suggested Text2Cypher data supplied realistic query workloads. The
[pinned corpus audit](../packages/query/benchmarks/results/text2cypher-audit-v2/FINDINGS.md)
finds 75,500 training rows but only 37,321 distinct normalized queries, with
substantial overlap between releases. The
[complete movies-alias execution](../packages/query/benchmarks/results/text2cypher-movies-v2/FINDINGS.md)
compares all 1,806 distinct queries against a pinned public graph: 1,797 exact
raw successes, one structurally equivalent virtual-schema result, seven matched
missing-APOC failures and one matched row-limit failure. The first virtual-ID
comparison failure remains preserved. This is adapter conformance, not
natural-language generation accuracy or missing-link supervision.

The [model reproduction](../packages/query/benchmarks/results/model-reproduction-v1/FINDINGS.md)
trains all 12 controls before development evaluation and independently replays
every outcome. All 24 declared comparisons pass; mean recall@16 is 28.55%,
versus 26.78% for positional marginals. Candidate coverage is only 35.30%.
The [clean training installation](../packages/query/benchmarks/results/model-installed-v1/FINDINGS.md)
repeats those results with newer scientific dependencies. Official validation
and test members remain unread. These reused development splits establish
reproducibility, not new held-out model-quality confirmation.

Three early runtime iterations preserve both regressions and the optimization
that resolved them. The [standalone campaign](../packages/query/benchmarks/results/standalone-runtime-v1/FINDINGS.md)
then runs 189 isolated workers over three evidence/model seeds without research
dependencies. Every output matches bitwise. Interleaved requests are 4.22–4.45x
faster than consecutive caching, with the other gated workloads ranging from
2.9% faster to 1.3% slower. Cold preparation, complete serialization, all timing
samples and process RSS are retained.

The [real Cypher workflow](../packages/query/benchmarks/results/neo4j-workflow-v1/FINDINGS.md)
adds database execution/transfer, evidence export, and a bounded multi-source
LRU control. Its 36 fresh clients retain exact evidence/binding/output parity.
Prepared-snapshot interleaved medians are 95 ms consecutive, 30 ms grouped and
34 ms LRU. Initial evidence export costs roughly one second; clustered inputs
show a 5.9% grouped regression. No broad advantage over a well-sized cache,
remote-server speedup, or concurrent-service throughput is claimed.

A [second public graph/schema](../packages/query/benchmarks/results/public-movies-model-v1/FINDINGS.md)
passes an independent individual-walk oracle for all 3,894 checked scores and
four strategy workloads. Fixed random coefficients make this a backend
correctness check, with no claim of useful movie predictions or model transfer.

## Final release audit

All six original requirements above are satisfied for the implemented release
surface. The [requirement-by-requirement audit](../packages/query/RELEASE_AUDIT.md)
links the executable evidence, supported-platform checks, final distribution
commands and limits on the public claims. The candidate includes complete
license text and notices, a runnable trained example, a live Cypher example,
operator/architecture documentation, a model card, and an introductory article.

Two final distribution command checks repeat all 189 runtime workers and 36
real-database workflow clients from the extracted sdist; every output matches
and all declared gates pass. Installed-wheel examples and live integration pass.
The runtime CI matrix passes on twelve Python/OS combinations, minimum NumPy and
both tested Neo4j driver lines. The original CI lint failures and experiment
regressions remain in their records; they were not relabeled as successful runs.

This completes release-candidate preparation. Merging, external publication and
repository visibility changes are separate actions and have not been performed.
