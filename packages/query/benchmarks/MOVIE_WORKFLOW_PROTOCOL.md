# Native Mac movie workflow, version 1

This is an application walkthrough and an end-to-end cost comparison on one
small public graph. It is not a replacement for the three-family competitive
acceptance gates, a learned recommendation-quality study, or evidence of a new
structural algorithm. Freeze this protocol, code, fixture, wheel, workloads,
expected outputs and software identities before measurement. No timing-driven
changes to inputs, controls, thresholds or repetition counts are allowed.

## Task and fixed inputs

Use the pinned Neo4j movies fixture at commit
`51cf90d18c1a7f74bce7a77083543697dfb0139d`, SHA-256
`7be04aba2193790e0051308e6aa8550236e651cae652ea7da44b7dc01f4c4e69`.
The demo downloads this fixture on request; it is not part of the wheel. Only a
newly created temporary local database may receive its writes. Native ARM Java
21 and Neo4j Community 2026.09.0 are required, with 256 MiB heap, 64 MiB page cache
and no GDS plugin. Freeze library hashes, VM identity and server version.

Project Movie nodes, people with acting credits, and distinct ACTED_IN edges.
Use type-prefixed title/name strings as application IDs. Candidate Cypher finds
films sharing cast with each requested film, restricts candidate release years,
and preserves duplicate input requests using an ordinal. Evidence retains every
acting credit, including films outside the candidate year filter. The plan scores
common-neighbor count, filters by that count, then scores resource allocation.
Return all qualifying rows, shared cast names, both scores and provenance in
ordinal/title order. Ranking in the HTML is presentation-only and is not timed.

Predeclared workloads, independent of any measured outputs:

| Workload | Requested titles | Candidate year floor | Minimum shared cast |
| --- | --- | ---: | ---: |
| single | The Matrix | 1990 | 1 |
| basket_with_repeat | The Matrix; Top Gun; Apollo 13; The Matrix | 1990 | 1 |
| filtered_basket | The Matrix; Top Gun; Apollo 13; The Matrix | 2000 | 2 |

No claim about personalized taste or held-out relevance follows from this task.
The fixture is an intentionally incomplete movie graph.

## Controls

1. `native_cypher`: one native traversal/aggregation query computes both scores
   and applies the filter before transfer. It needs no Python evidence export.
2. `manual_intersection`: independent Python set intersections, both scores in
   one pass, with full adjacency sets prepared once and charged to preparation.
3. `full_source_shared`: full-source feature expansion shared between both models
   and reused across every requested pair for that source inside a call. An O(1)
   target lookup avoids a weak linear-search control. The tiny fixture fits in
   memory; no eviction is needed. Nothing persists between calls.
4. `plan`: the public composed plan with compatible preparation sharing.
5. `plan_unfused`: the same public plan with preparation sharing disabled.
6. `warm_pair_cache`: the public plan with prepopulated exact pair-score cache;
   the preparation query and inference are charged outside request timing.
7. `precomputed_scores`: favorable oracle lookup for every requested source and
   every movie target, with independent structural scores and charged preparation.

All local arms run the same candidate query on every request, including warm
arms. All native and local paths use the adapter's read-only query classification,
Bolt transfer, equivalent returned fields and JSON encoding. The native arm adds
matching graph/model provenance in Python from the frozen fixture identity. That
identity is justified only because this owned benchmark database is fixed.
Do not apply that shortcut to a mutable production database.

The on-demand comparison uses the fastest of native Cypher, manual intersection,
and shared full-source expansion per workload. Report warm controls separately;
allow any control to win. Do not present the unfused ablation as the competitive
baseline or infer wall-time savings solely from work counts.

## Boundaries and repetitions

63 fresh client processes: three workloads × seven arms × three repetitions,
shuffled with seed 2026092801. Native numerical thread variables are fixed to one.
One owned database serves the campaign; database page/plan caches may remain warm.
Each client connects, exports evidence if required, performs its arm's preparation,
and makes eight complete calls. Report the first call separately; summarize the
next seven by their median. This is a single-client loopback study, not concurrent
service throughput or a cold-server experiment.

Request timing includes query guard, native execution, transfer, local inference,
result materialization, JSON serialization and UTF-8 encoding. Record query/transfer,
local materialization, and JSON components. Native query/transfer time includes
its scoring; local model time is in the local component, so individual component
labels must not be interpreted as equal database-only work across arms.

Client first-use wall time starts before driver construction and ends at the first
encoded result, including connection, evidence export, arm preparation and intervening
client setup. Record each setup component separately. Interpreter/library imports,
manifest checks and host telemetry are outside that boundary. Parent subprocess
wall time covers all eight calls and startup, not just the first result.
Campaign-level database startup and fixture import are separate recorded costs;
do not charge native controls for a graph export they do not need.

Report all samples, three process medians, first-use cost, snapshot export, preparation,
client peak RSS and database configured memory. Peak client RSS is not combined
Java+Python peak memory. No inference cache crosses requests except the two warm
arms. No server or graph update occurs during requests; repeated export measures
the snapshot-refresh cost on unchanged data, not incremental update throughput.

## Isolation, correctness and interpretation

Run final measurements during a user-arranged quiet Mac window. Record aggregate
process CPU use, load average and available thermal status before/after each worker.
The `--host-use` label is explicit. Telemetry and operator confirmation do not prove
perfect isolation; report observed interference and retain all samples. A mixed-use
run remains descriptive and cannot silently substitute for the requested quiet run.
No selective repeats, deleted outliers or timing-based stopping rule.

A separate seven-arm preflight on basket_with_repeat checks execution and outputs;
its samples are not part of the campaign aggregate. Compare every result with
native Cypher fixed before measurement, including bags/order and all provenance,
with score tolerance 1e-12 absolute/relative. Check request JSON digests, timing
component sums and medians. All workers and failures remain retained. Verify the
independent manual scorer against both native and composed outputs.

Report every arm/workload, not only the fastest favorable case. Three process
replicates on one small graph are insufficient for a broad latency claim; use
per-process spread instead of a falsely precise generalization interval. This
comparison can legitimately favor native Cypher, especially when export dominates.

## Commands

After installing a wheel built through the source archive, from the package folder:

```sh
python -I benchmarks/movie_workflow.py freeze movie-run \
  --wheel dist/orbweaver_query-1.0.0.dev1-py3-none-any.whl \
  --neo4j-home /path/to/neo4j-community-2026.09.0 --java /path/to/native-java21/bin/java
python -I movie-run/benchmarks/movie_workflow.py preflight movie-run \
  --neo4j-home /path/to/neo4j-community-2026.09.0 --java /path/to/native-java21/bin/java
# During the arranged quiet interval:
python -I movie-run/benchmarks/movie_workflow.py execute movie-run --host-use quiet-window \
  --neo4j-home /path/to/neo4j-community-2026.09.0 --java /path/to/native-java21/bin/java
python -I movie-run/benchmarks/movie_workflow.py verify movie-run
```

Use a new directory; existing campaign output is never silently resumed or overwritten.
Verification uses the retained records and does not start a database or new timings.
