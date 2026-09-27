# Orbweaver Query

Exact graph scoring that uses the candidate pairs your query already knows.
Run it locally on an Apple Silicon Mac with Python and NumPy. Compose path and
structural scores, filters and graph expansions, or feed it candidate rows from
Neo4j. Results preserve duplicates, row order, explicit unsupported/null states,
and graph/model provenance.

**Status: `1.0.0.dev1`, a development preview.**
The package is not on PyPI. The original competitive 1.0 gates remain open.
Read the [current release audit](RELEASE_AUDIT.md), [performance and limits](PERFORMANCE.md),
and [comparison with Quail/GDS](POSITIONING.md) before interpreting benchmark claims.

## Run on a Mac

From the repository root, using native Apple Silicon Python 3.11 or newer:

```sh
python3 -m venv .venv-query
source .venv-query/bin/activate
python -m pip install ./packages/query
python -m orbweaver_query.demo
```

The demo downloads a checksum-pinned WN18RR archive, extracts its training member,
and loads the bundled 38 KB trained path model. Later runs verify the local
cache. Use `--data-dir PATH` to choose its location. No API key, cloud service,
GPU or training framework is needed. NumPy is the sole core runtime dependency.
The Mac validation record identifies the actual chip, Python and dependency versions;
it does not promise identical performance on every MacBook.

The example model is specific to its WordNet graph and relations. Its three reused
development splits give mean recall@16 of 28.55% and candidate coverage of 35.30%.
Scores are ranking logits, not probabilities. The [model card](MODEL_CARD.md)
explains the unsupported cases and fitting procedure. Other graphs require a
compatible model or one of the conventional structural scores below.

## A human-readable Neo4j walkthrough

The [movie demo](examples/README.md) starts an owned temporary database from a
pinned public fixture, finds related films through shared cast, and writes a local
HTML report with scores, cast evidence and an inspectable plan. Its answers are
checked against equivalent native Cypher. Both scoring methods are conventional
structural metrics; the report does not claim personalized taste prediction or
assume that fewer expansions mean lower wall time.

The [bring-your-own-graph guide](BRING_YOUR_OWN_GRAPH.md) covers CSV and Neo4j
mapping, stable IDs, null/unsupported results, snapshot refresh, limits and model
choice. A runnable CSV recipe lets you validate your mapping before adding a database.

## Score known pairs

This small example illustrates the API with zero coefficients; it is not a
trained predictor. The demo above supplies the trained example.

```python
import numpy as np
from orbweaver_query import ExplicitPathModel, GraphSnapshot, Session, score_bindings

graph = GraphSnapshot(
    [[0, 0, 1], [1, 0, 2]],
    node_ids=("a", "b", "c"), relations=("RELATED",),
)
model = ExplicitPathModel(np.zeros((1, 16)), relations=graph.relations)
session = Session(graph, model)
rows = [{"head": "a", "relation": "RELATED", "target": "c"}]
result = score_bindings(session, rows)
assert result.rows[0].score == 0.0
print(result.to_records())
```

Bound targets let the path backend avoid constructing terminal features for
unrequested nodes while retaining complete intermediate evidence and walk
normalization. `execution="full"` supplies the equivalent full-expansion control.
`LinkQuery` and `Session.run` support ranking all model-supported candidates.
`BindingCache` supplies bounded exact pair reuse across requests; changing the
graph or model identity cannot hit stale entries.

## Compose scores and filters

```python
from orbweaver_query import NeighborhoodModel, QueryPlan

ra = NeighborhoodModel(relations=graph.relations, metric="resource_allocation")
plan = (QueryPlan(graph)
        .predict("structure", ra)
        .where_score("structure", 0.1)
        .predict("rank", model)
        .project("head", "target", "structure", "rank"))
print(plan.run(rows).to_records())
print(plan.explain())
```

`NeighborhoodModel` also offers common neighbors and Adamic–Adar. These established
methods use undirected topology, ignoring edge types and direction. Plans share
compatible features and skip later scoring for rejected rows. `expand(...)`
adds typed graph traversal between inference stages; independent filters can move
before expansion. `iter_batches` bounds output windows, and explicit resource
limits fail rather than silently prune. Planning adds overhead: the strongest
manual composed control remains faster in the retained study.

## Use Cypher candidate queries

Install the optional driver with `python -m pip install './packages/query[neo4j]'`.
Neo4j executes Cypher; the adapter exports an explicit immutable evidence snapshot
and maps parameterized query results to model inputs. This is a Python integration,
not a Cypher UDF, GQL implementation or natural-language-to-Cypher generator.

```python
from orbweaver_query.neo4j import Neo4jSource

# driver is a caller-owned Neo4j driver; model matches this graph's relation schema.
source = Neo4jSource(driver, database="neo4j")
evidence = source.snapshot(
    nodes="MATCH (n:Entity) RETURN n.id AS id ORDER BY id",
    edges="""MATCH (a:Entity)-[r]->(b:Entity)
             RETURN a.id AS head, type(r) AS relation, b.id AS target""",
    relations=model.relations,
)
session = Session(evidence, model)
result = source.score_pairs(session, """
    MATCH (a:Entity)-[]->()-[]->(b:Entity)
    WHERE a.id = $source
    RETURN a.id AS head, $relation AS relation, b.id AS target
""", {"source": "a", "relation": "RELATED"})
print(result.to_records())
```

`run_plan`/`iter_run_plan` execute composed plans over candidate queries. Candidate
selection does not crop model evidence. Refresh the snapshot when the database
changes; export and refresh costs matter. Query classification guards read-only
execution, while database credentials remain the caller's responsibility.
See the [execution contract](SEMANTICS.md) for transaction cleanup, limits,
support, cache lifetime and provenance.

## Reproduce the measurements

The [Mac benchmark protocol](benchmarks/MAC_RELEASE_PROTOCOL.md) builds a wheel
through its source archive, checks the installed runtime's identity, and measures
24 fixed graph/workload conditions with nine controls and three fresh processes
per condition. It includes JSON serialization, reports loading and cache setup
separately, and retains every condition, including regressions and warm lookup wins.
The [performance page](PERFORMANCE.md) links the results and their limitations.

The complete [evidence inventory](EVIDENCE.md) retains earlier failed and adverse
campaigns. [Model reproduction](MODEL_CARD.md), [competitive context](POSITIONING.md),
and the [introductory article](INTRODUCING.md) explain what these results do and
do not establish. Conventional path features, caches and predicate ordering are
prior art; a new general inference algorithm or Quail-level systems advantage
has not been demonstrated.

The optional [Quail bridge](QUAIL_BRIDGE.md) is experimental research with CPU
planning/semantics checks. Its CUDA execution is outside this Mac-only release
path and has no measured performance claim.

Apache-2.0 for the runtime; [third-party notices](src/orbweaver_query/assets/THIRD_PARTY_NOTICES.md)
apply separately to the example data and model.

[Contributing](CONTRIBUTING.md) · [Data handling and security](SECURITY.md)
