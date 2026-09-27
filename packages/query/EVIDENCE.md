> Development evidence inventory retained from the pre-release README.
> For current installation and claims, start with [README](README.md) and [performance](PERFORMANCE.md).

# Orbweaver Query

A query-aware execution engine for graph-native models. This branch develops
1.0; the [competitive acceptance gates](benchmarks/v1/ACCEPTANCE.md) remain open.
It supplies an immutable graph projection, bounded inference, shared preparation,
typed ranking results, and a read-only Cypher adapter. The
[release audit](RELEASE_AUDIT.md) maps its supported scope to the validation
evidence. The package has not yet been published to PyPI.
The [competitive context](POSITIONING.md) compares the current scope with Quail,
LOTUS and Neo4j GDS, and states which novelty/performance claims need more evidence.
An optional [experimental Quail bridge](QUAIL_BRIDGE.md) now supplies native
Cypher candidate pairs to Quail's existing Boolean semantic join, with optional
document filters controlling subsequent graph candidate selection. CPU planning,
dependency and result-semantics checks pass; CUDA inference and performance remain
unmeasured. Filtered plans materialize survivors to avoid a pinned upstream
streaming defect.

The runtime installs independently of Orbweaver's MLX application:

```sh
python -m pip install ./packages/query
```

For a Neo4j connection, install `./packages/query[neo4j]`. The core needs only
NumPy and Python 3.11+, with no GPU or training framework. The 0.1 baseline wheel built from the
sdist passed installed runtime tests and its trained quickstart on Ubuntu, macOS
and Windows with Python 3.11–3.14. Live integration covers Neo4j 5.26 with driver
5.28 and 6.x; the core also passes with NumPy 1.26.4 on Python 3.11.

## Trained quickstart

Run the bundled 38 KB WN18RR path model on its reproducible evidence graph:

```sh
python -m orbweaver_query.demo
```

The first run downloads a checksum-pinned public archive and extracts only its
training member. Later runs use the verified local cache. The demo needs NumPy
only, rebuilds the model's exact graph snapshot, and prints ranked candidates,
an execution plan and reuse counters. Use `--data-dir PATH` for an existing
verified `train.txt`, or `--head ENTITY_ID --relation _hypernym` for a query.

Read the [model card](MODEL_CARD.md) before interpreting these scores. On three
reused development splits, mean recall@16 is 28.55%; candidate coverage is only
35.30%. The score is a ranking logit. The model was trained for WN18RR relations
and does not supply a model for an arbitrary Neo4j database.

To rebuild all three models and evaluate their controls independently:

```sh
python -m pip install './packages/query[train]'
python -m orbweaver_query.reproduce freeze model-run
python -m orbweaver_query.reproduce execute model-run
python -m orbweaver_query.reproduce verify model-run
```

The [frozen reproduction](benchmarks/results/model-reproduction-v1/FINDINGS.md)
records the protocol, source, data and model identities and complete per-relation
metrics. Training dependencies are optional and unused by inference. Keep the
same installed source through freeze/execute/verify and use a fresh directory
for each run.

## Minimal API example

The following uses zero coefficients to demonstrate execution semantics on a
tiny graph. Use the trained quickstart above for actual learned scores.

```python
import numpy as np
from orbweaver_query import ExplicitPathModel, GraphSnapshot, LinkQuery, Session

graph = GraphSnapshot(
    [[0, 0, 1], [1, 0, 2]],
    node_ids=("a", "b", "c"),
    relations=("RELATED",),
)
model = ExplicitPathModel(np.zeros((1, 16)), relations=graph.relations)
session = Session(graph, model)
result = session.run([LinkQuery("a", "RELATED")])
assert result.rows[0].top(5) == [("c", 0.0)]
print(session.explain())
print(result.report())
```

`ExplicitPathModel.save(path)` writes a versioned, checksummed numeric artifact;
`ExplicitPathModel.load(path)` validates it without executable deserialization.
Ordered relation names must exactly match the graph's schema.

## Structural scores and composed plans

`NeighborhoodModel` supplies common neighbors, Adamic–Adar, and resource
allocation without fitting. These conventional methods use undirected topology;
edge types and direction do not affect their scores. Every non-self, non-adjacent
pair has a score, including zero for disconnected nodes. This support differs
from the learned path model's two/three-hop support.

```python
from orbweaver_query import NeighborhoodModel, QueryPlan

ra = NeighborhoodModel(relations=graph.relations, metric="resource_allocation")
aa = NeighborhoodModel(relations=graph.relations, metric="adamic_adar")
plan = (QueryPlan(graph)
        .predict("resource_allocation", ra)
        .where_score("resource_allocation", 0.1)
        .predict("adamic_adar", aa)
        .project("head", "target", "resource_allocation", "adamic_adar"))
rows = [{"head": "a", "relation": "RELATED", "target": "c"}]
result = plan.run(rows)
print(result.to_records())
print(plan.explain())
```

Compatible models share feature preparation within a bounded window. The same
plan can also contain learned path predictions, with separate preparation for
that feature contract. By default, groups with score filters run before unfiltered
groups, retaining declared order within each category. Within a shared-feature
group, filtered predictions run first and rejected rows skip later predictions.
This avoids unnecessary score lookups and output construction even with a warm
cache. One source's features remain available for its surviving operators.
`plan.calibrate(sample_rows)` measures each physical
group's cost and filter pass rate; pass the returned statistics to
`plan.run(rows, statistics=statistics)` to order groups by measured cost per
rejected row. Calibration has a real cost and should use representative rows.
It is a heuristic: correlated predicates and source reuse can change costs.
`fused=False` disables cross-operator sharing as an execution control.

The [pushdown campaign](benchmarks/results/plan-development-v4/FINDINGS.md)
preserves exact outputs in 864 workers. Default plans are 1.159x faster geometrically
than the strongest cold control on its fixed mix; warm cached plans have about
2.9% greater geometric latency than the best warm control. Calibration adds no
aggregate steady-state benefit on this mix and hurts short workloads. Adverse
cases and the [earlier comparison](benchmarks/results/plan-development-v3/FINDINGS.md)
are retained. These controls validate implementation tradeoffs; the 1.0 target is
substantial work elimination in richer composed graph-inference queries, as
described in the [competitive context](POSITIONING.md).

The [native structural verification](benchmarks/results/native-structural-verification-v1/README.md)
also preserves all 144 conditions across local plans, native GDS functions,
shared-traversal Cypher and precomputed lookup. Scores agree within 1.43e-14;
nulls, order, duplicates and support metadata agree. This is correctness evidence;
the subsequent [original request campaign](benchmarks/results/native-structural-development-v1/FINDINGS.md)
completed nine database workers, but used x86_64 Java with native arm64 Python.
Its former 1.23x latency claim is withdrawn as evidence of a fair native comparison.
See the [runtime architecture audit](benchmarks/results/native-runtime-audit-v1/FINDINGS.md)
for the retained identities, corrected protocol and replacement campaign. The
original frozen artifacts remain intact; answer agreement is separate from timing.
The [ARM replacement](benchmarks/results/native-structural-arm64-development-v1/FINDINGS.md)
verifies all 432 conditions. Current cold requests show a descriptive 1.059x
ratio before export and 0.970x with export spread over 1,000 requests. This does
not establish a substantial native advantage or close a release gate.

The separate [per-source recommendation protocol](benchmarks/v1/GDS_APPLICATION_PROTOCOL.md)
aligns learned GDS and local prediction at a top-16 application boundary. It
keeps exhaustive candidate coverage, ranks native structural results in Neo4j,
and uses adaptive per-source GDS queues with final ranking after transfer. It
includes native structural, manual and precomputed controls at one/four configured
threads. The [first attempt was interrupted](benchmarks/results/gds-application-interrupted-v1/FINDINGS.md)
after four completed workers when a source audit identified an unnecessarily
expensive global result queue. All completed and interrupted evidence is retained.
The [bounded native control](benchmarks/results/gds-queue-diagnostic-development-v1/FINDINGS.md)
returns exactly the same top-16 answers from the same trained GDS model using
small per-source queues: 6.85 seconds versus 31.76 seconds in one process.
This 4.64x descriptive improvement belongs to the GDS baseline, not Orbweaver.
The [complete replacement campaign](benchmarks/results/gds-application-development-v2/FINDINGS.md)
now verifies all 18 workers, 48 condition summaries and independent raw-score
reconstruction. Observed unrelated host computation limits timing interpretation;
the results do not establish isolated performance parity. The
[held-out confirmation](benchmarks/results/gds-application-confirmation-v1/FINDINGS.md)
meets the original quality conditions at both thread settings. Structural methods
remain strong competitors, and simultaneous one-point noninferiority against all
controls is not established. Cost advantage and all complete 1.0 gates remain open.

Plans currently compose pair predictions, conjunctive score filters, and a
terminal projection. They preserve row order and duplicates, validate all
declared inputs before executing a window, and attach model/snapshot provenance
to each prediction. `plan.iter_batches(rows)` bounds retained output; `run`
collects it. Pass `cache=BindingCache(max_entries=16384)` to `run` or `iter_batches`
to reuse exact pair scores across calls, including scores populated through
`score_bindings`. Cache entries are committed only after every operator in the
window succeeds. Graph/model identities prevent stale reuse; changing a filter
or projection can still reuse the underlying scores. Calibration measures
uncached costs, which can differ substantially from warm execution. Ordinary
aggregation and arbitrary Cypher execution remain the database's responsibility.

### Predictions that control graph expansion

`expand` turns a pair plan into a `GraphPipeline`. Its typed graph joins can run
between inference stages, so predictions decide which branches get expanded:

```python
pipeline = (QueryPlan(graph)
    .expand(source="target", target="neighbor", direction="both")
    .predict("affinity", NeighborhoodModel(relations=graph.relations))
    .where_score("affinity", 0.2)
    .predict("rank", model, target="neighbor")
    .project("head", "target", "neighbor", "affinity", "rank"))

print(pipeline.explain()["predicate_moves"])
result = pipeline.run(candidate_rows)
print(result.report()["edge_visits"])
```

Although written after the expansion, `affinity` uses only the original pair.
The planner moves that filter before the graph join; rejected candidates create
no neighbor rows and require no downstream ranking. A filter that needs a newly
bound endpoint stays after its producing expansion. Compatible models still
share preparation within each inference stage. `optimize=False` disables movement
across expansions for comparison; it preserves within-stage optimizations.

Expansions use the immutable evidence snapshot. They support `out`, `in` and
`both`, an optional fixed `relation`, an `edge_relation` output column, and
`optional=True` to preserve a parent with null bindings when no edge matches.
Distinct edge types and reciprocal edges preserve their bag multiplicities;
repeated parents remain repeated. Chained expansions may revisit edges or nodes;
this is not a Cypher variable-length-path implementation. Projection is terminal.

`Neo4jSource.run_plan` and `iter_run_plan` accept pipelines as well as pair plans.
Each expansion stage has a `Limits.max_intermediate_rows` bound (100,000 by
default) per root window; visit limits also apply. Exceeding a budget raises an
error, never truncates. Stages materialize bounded intermediate rows, so the
input window size alone is not a bound on intermediate memory. New cached scores
commit only after the entire root window succeeds. See the
[execution contract](SEMANTICS.md) and
[fresh-query benchmark protocol](benchmarks/v1/GRAPH_PIPELINE_PROTOCOL.md).

The [first fresh-query comparison](benchmarks/results/graph-pipeline-development-v1/FINDINGS.md)
retains 69 matching completed workers and three eager row-budget failures.
Automatic planning avoids traversal work, but its geometric request latency is
about 90% greater than the strongest hand-ordered pipeline. Four of six conditions
return no rows. These results identify an execution gap; they do not establish
competitive parity or a release performance claim.

Pipelines now also reuse model-internal preparation across scoring batches for
repeated sources. The path model prepares exact features for the union of known
stage targets, then supplies subsets to bounded scoring batches. It can instead
retain two-hop walk state and complete target features on demand; pass
`coalesce_targets=False` for that strategy. This state lives only for a root input window and is
limited by `Limits.max_prepared_bytes` (16 MiB of numeric arrays by default).
`reuse_preparation=False` disables both strategies; `report()` exposes preparation
builds, hits, target-union builds/hits and peak retained numeric bytes. Retained
target features count against the same budget; model-specific scores remain
separate. The [216-worker prefix comparison](benchmarks/results/graph-pipeline-development-v2/FINDINGS.md)
gives the manual controls access to the same prepared state and packed evidence.
Nine of twelve conditions return rows; all workers agree within numerical tolerance.
Prepared execution is 1.314x faster geometrically than the automatic pipeline's
disabled-preparation control, but automatic execution still has about 53% greater
latency than the strongest manual control. That ablation includes completion-kernel
differences as well as state reuse; it does not isolate the benefit of reuse alone.

The [252-worker follow-up](benchmarks/results/graph-pipeline-development-v3/FINDINGS.md)
keeps the exact same inputs, improves the ordinary target kernel and adds a
same-kernel control that rebuilds prefixes for each batch. All answers match.
Automatic execution still has about 46% greater geometric latency than the best
manual pipeline. Retaining prefixes gives a descriptive 1.120x latency ratio over
rebuilding them across the declared mix, with variable timings and regressions.
This is evidence about fresh inference execution; competitive parity remains open.

The [stage-target comparison and corrected repeat](benchmarks/results/graph-pipeline-development-v5/FINDINGS.md)
retain another 648 matching workers and add a manual coalescing control. The
corrected implementation has about 27% greater geometric request latency than
the strongest manual pipeline. Coalescing reduces counted traversal work but
shows no aggregate latency benefit over prefix reuse. It is an available execution
strategy, not an established performance or novelty claim; all 1.0 gates remain open.

The [360-worker binding follow-up](benchmarks/results/graph-pipeline-development-v6/FINDINGS.md)
preserves all answers but still measures about 33.5% greater geometric latency than
the best manual control. Deduplicating binding processing gives only a descriptive
1.018x ablation ratio. Further small executor campaigns are no longer the immediate
priority: the [execution-thesis investigation](benchmarks/v1/EXECUTION_THESIS.md)
requires evidence for a substantial, application-relevant query/model execution
advantage before broader implementation. The existing acceptance gates are unchanged.

The [bounded transformer diagnostic](benchmarks/results/spider-headroom-development-v1/FINDINGS.md)
examines the existing application's Qwen3-4B classifier. Ordinary prefix reuse
offers only a descriptive 1.180x ratio on current pair-local inputs; the larger
shared-context ratio fails the declared output contract. This is retained
negative evidence, not a new runtime feature or a Quail performance comparison.

## Cypher integration

Provide a model evidence projection explicitly, then stream candidate bindings
from a parameterized Cypher query. `Neo4jSource` delegates Cypher parsing and
ordinary query execution to Neo4j. It does not add custom functions to the
database or claim ISO GQL conformance.

```python
from orbweaver_query import ExplicitPathModel, Session
from orbweaver_query.neo4j import Neo4jSource

# driver is a caller-owned Neo4j Python driver.
source = Neo4jSource(driver, database="neo4j")
model = ExplicitPathModel.load("model.npz")
evidence = source.snapshot(
    nodes="MATCH (n:Entity) RETURN n.id AS id ORDER BY id",
    edges="""MATCH (a:Entity)-[r]->(b:Entity)
             RETURN a.id AS head, type(r) AS relation, b.id AS target""",
    relations=model.relations,
)
session = Session(evidence, model)
candidate_query = """
    MATCH (a:Entity)-[]->()-[]->(b:Entity)
    WHERE a.id = $source
    RETURN a.id AS head, $relation AS relation, b.id AS target
"""
result = source.score_pairs(session, candidate_query, {"source": "a", "relation": "RELATED"})
print(result.to_records())
```

Run a composed plan over the same candidate query with `run_plan`:

```python
from orbweaver_query import BindingCache, NeighborhoodModel, QueryPlan

plan = (QueryPlan(evidence)
        .predict("rank", model)
        .predict("structure", NeighborhoodModel(relations=evidence.relations))
        .where_score("structure", 0.1)
        .project("head", "target", "rank", "structure"))
cache = BindingCache(max_entries=16384)
result = source.run_plan(plan, candidate_query,
                         {"source": "a", "relation": "RELATED"}, cache=cache)
print(result.to_records())
```

`iter_run_plan` yields bounded result windows. Both entry points close the
candidate transaction on inference or validation errors; close the streaming
generator explicitly when stopping early. Candidate reads use the plan's existing
evidence snapshot and do not refresh it. The caller retains ownership of the driver.

Use `iter_score_pairs` for bounded result windows and close its generator if
stopping early. Duplicate query rows retain their identity and multiplicity.
The adapter checks the database's `EXPLAIN` query classification before executing
supplied statements. The live integration test verifies that a write query never
executes. Projection endpoints and relation types must all be declared; unknown
IDs raise an error. Null candidate inputs yield `null_input`; known targets
outside model support yield `unsupported`. Neither case becomes a negative fact.

Candidate queries restrict outputs. They do not restrict model evidence.
Export the context used by the model, including required boundary degrees and
other neighbors. The snapshot is immutable after export; database transaction
isolation and coordination with concurrent writers remain the caller's concern.

## Execution and measured scope

`Session.run` collects all output; `iter_batches` bounds retained result windows.
`Limits` bounds window size, typed-edge/neighbor visits and expansion states. Exceeding an
exact-inference limit raises `ResourceLimitError` rather than silently pruning.
Feature-byte profiles describe final numeric feature arrays, not peak process
memory or temporary Python containers. Process RSS is measured in the benchmark.

The three strategies are independent per-request execution, consecutive-source
reuse, and grouping compatible source queries inside bounded windows. Grouping
also reuses identical relation scores and restores original row order. Reuse is
local to one call unless the caller supplies a bounded `BindingCache`.

Bound candidate rows now use exact target-aware expansion when the backend
supports it. Intermediate evidence and random-walk normalization remain complete;
the engine avoids building terminal features for unrequested endpoints.
`execution="full"` retains full expansion as a correctness/performance control.
An explicit cache can reuse scores across requests, including unsupported pairs:

```python
from orbweaver_query import BindingCache, score_bindings

cache = BindingCache(max_entries=16384)
rows = [{"head": "a", "relation": "RELATED", "target": "c"}]
first = score_bindings(session, rows, cache=cache)
again = score_bindings(session, rows, cache=cache)
assert first.to_records() == again.to_records()
print(cache.info())
```

The cache keys include graph and model content identities. Replacing either
artifact cannot hit stale entries. Its capacity counts entries, not total bytes;
it is caller-owned and intended for sequential use. It does not track live
database mutations: export a new immutable snapshot when evidence changes.
The measurements below describe the earlier 0.1 engine. New development evidence
is recorded in the [first 1.0 checkpoint](benchmarks/results/v1-development/FINDINGS.md)
and is not a completed 1.0 claim.

The [completed GDS development grid](benchmarks/results/gds-retry-development-v1/FINDINGS.md)
covers four native configurations on three public graphs with full candidate denominators. It motivated
the additional structural backend: resource allocation wins two development
applications and the path model wins one. The longer friendship retry completed
without improving GDS's best development result. The later application campaign
reports matched request boundaries and setup costs, with the host-contention
limitation above. The separately frozen confirmation now supplies held-out quality
evidence as described above; it does not establish a 1.0 latency or novelty claim.

The [third frozen experiment](benchmarks/results/runtime-v3/FINDINGS.md) passed
both declared runtime gates with bitwise score parity. On one 40,559-node WN18RR
evidence graph, grouped execution plus serialization was 4.04x faster than the
previous cache baseline for 256 interleaved requests sharing 32 sources. Other
declared workloads ranged from 1.6% faster to 6.8% slower. Peak process RSS was
about 67–76 MiB versus 105–106 MiB. These results exclude database extraction and
network transfer and use one fixed trained model; they are not a universal
speedup or a new predictive-quality result. The first two iterations and their
regressions are preserved alongside it.

Reproduce the standalone public benchmark after the model-reproduction commands:

```sh
python packages/query/benchmarks/standalone.py freeze runtime-run --model-run model-run
python packages/query/benchmarks/standalone.py execute runtime-run
python packages/query/benchmarks/standalone.py verify runtime-run
```

The [standalone campaign](benchmarks/results/standalone-runtime-v1/FINDINGS.md)
passes the speedup and regression gates on all three evidence/model seeds, with
4.22–4.45x speedup on interleaved256 and bitwise output parity. Its other gated
workloads range from 2.9% faster to 1.3% slower. It records cold preparation,
serialization, process memory, larger windows and all 189 isolated workers.
The older harness and its research-fixture results remain preserved as historical
evidence; new public runs use the standalone pipeline above.

The [real Neo4j workflow](benchmarks/results/neo4j-workflow-v1/FINDINGS.md) includes
candidate-query execution, Bolt transfer, inference and serialization. With a
prepared evidence snapshot, interleaved256 takes 95 ms with consecutive caching,
30 ms with grouping and 34 ms with a bounded multi-source LRU. Initial evidence
export takes roughly one second. Grouping does not provide a large advantage
over a cache that already retains every repeated source.

From the source checkout, after the standalone runtime campaign, install the
Neo4j extra and run:

```sh
python -m pip install './packages/query[neo4j]'
python packages/query/benchmarks/neo4j_workflow.py freeze workflow-run --runtime-run runtime-run
python packages/query/benchmarks/neo4j_workflow.py execute workflow-run \
  --neo4j-home /path/to/neo4j --java /path/to/java
python packages/query/benchmarks/neo4j_workflow.py verify workflow-run
```

Use a local Neo4j 5.26 distribution and Java 21. The command imports the fixture
only into a new temporary database, then terminates and removes that database.
It does not connect to an existing user database.

See [execution semantics](SEMANTICS.md) for the precise inference, filtering,
projection, null and evidence contracts.

It treats directed typed edges as evidence. The path backend considers nodes
reachable in two or three steps, excluding the source and every existing
neighbor. Its results are ranking scores, not calibrated link probabilities.
Duplicate identical edges are evidence-set duplicates; different relation types
between the same endpoints are retained. A missing candidate means unsupported
by this model's search space, not a negative judgment.

The standalone training pipeline reproduces choices from the graph research
program without importing its code or artifacts. The current runtime does not provide a validated entity-merge model, calibrated
probabilities, joint transaction beliefs, or autonomous graph edits.
