# Bring your own graph

Start with a conventional structural score to validate your data mapping. The
bundled WordNet model is specific to its graph and relation schema; loading it
against unrelated data does not produce a validated predictor for that data.

## Choose the evidence and the question

Keep two inputs separate:

- **Evidence:** the complete graph projection needed by the scorer, including
  all relevant neighbors and their degrees. Export it once and keep it immutable.
- **Candidates:** the pairs your application asks to score. Filtering candidate
  rows does not remove evidence and does not change the scoring rule.

For example, in a Person → ACTED_IN → Movie graph, movie pairs can be ranked by
shared cast. Resource allocation sums `1 / degree(common neighbor)`; an actor
with many films contributes less. This is a structural ranking, not a probability
or a personalized recommendation model. Common neighbors, Adamic–Adar and resource
allocation all ignore direction and edge labels. Project only relationships whose
undirected topology makes sense for the task. The path model instead uses typed,
directional path features and needs a fitted artifact with the exact schema.

## Start from CSV

Use stable, unique, nonempty **string** application IDs. Keep numeric-looking IDs
such as `001` as strings. Declare isolated nodes too. CSV files use UTF-8 and headers.

`nodes.csv`:

```csv
id
a
b
c
d
```

`edges.csv`:

```csv
head,relation,target
a,RELATED,b
b,RELATED,c
```

`candidates.csv`:

```csv
head,relation,target,request_id
a,RELATED,c,first
a,RELATED,d,disconnected
a,RELATED,b,already_adjacent
a,RELATED,,missing
a,RELATED,c,repeated
```

From the repository root after installing the package:

```sh
python -I packages/query/examples/score_csv.py \
  --nodes nodes.csv --edges edges.csv --candidates candidates.csv \
  --relation RELATED --metric resource_allocation > scores.jsonl
```

The output retains `request_id` and row order. The first/repeated pair scores 0.5,
the disconnected pair scores 0.0, the adjacent pair is `unsupported`, and the empty
target is `null_input`. Zero is a valid structural score; null/unsupported is not
zero and does not assert a negative fact. Unknown non-null IDs are errors.
Duplicate candidate rows stay duplicated. Duplicate identical evidence edges
collapse in the immutable snapshot; different relation types remain distinct.

This recipe accepts at most 100,000 node records and 1,000,000 edge records before
snapshot construction. Candidate results stream in windows of 256 by default.
The graph itself is resident in memory; windowing is not an out-of-core graph
implementation. An error can occur after earlier JSONL windows have been written;
write to a temporary output and publish it only after a successful process exit
if your application needs an all-or-nothing file.

## Read candidates from Neo4j

Install the optional Neo4j driver. Supply your own authenticated driver using
application configuration; the library does not own its credentials or lifecycle.
Use read-only database permissions for this integration.

```python
from orbweaver_query import NeighborhoodModel, Session
from orbweaver_query.neo4j import Neo4jSource

# driver is your caller-owned, authenticated Neo4j driver.
source = Neo4jSource(driver, database="neo4j")
graph = source.snapshot(
    nodes="MATCH (n:Entity) RETURN n.id AS id ORDER BY id",
    edges="""MATCH (a:Entity)-[:RELATED]->(b:Entity)
             RETURN a.id AS head, 'RELATED' AS relation, b.id AS target""",
    relations=("RELATED",), max_nodes=100000, max_edges=1000000,
)
model = NeighborhoodModel(relations=graph.relations, metric="resource_allocation")
session = Session(graph, model)
query = """UNWIND $pairs AS p
           RETURN p.head AS head, 'RELATED' AS relation, p.target AS target"""
result = source.score_pairs(session, query, {"pairs": [{"head": "a", "target": "c"}]})
print(result.to_records())
```

Queries are parameterized. Neo4j parses and executes Cypher; the adapter checks
its read-only classification before execution. It neither installs a database
function nor implements GQL. Node and edge export run in one transaction, with
the isolation guarantees of the database configuration. Coordinate concurrent
writers yourself when a consistent point-in-time projection is required.

## Refresh and persistence

`graph.save("evidence.npz")` and `GraphSnapshot.load("evidence.npz")` preserve a
versioned, checked snapshot without executable deserialization. Model artifacts
also carry schema and content identities. A caller-owned `BindingCache` keys
entries by graph and model identity, so a replacement artifact cannot reuse stale
scores. It is an entry-count cap for sequential use, not a byte or process-memory
limit.

A live database update does **not** refresh an existing snapshot. Export a new
snapshot and create a new Session/QueryPlan when the evidence changes. Keep the
old identity in existing result records so answers remain attributable. Charge
export/refresh cost when deciding whether local scoring benefits your workload.

## Limits and model choice

`Limits` bounds window size, expansion states, neighbor/type visits, intermediate
pipeline rows and prepared numeric bytes. Exceeding a limit raises
`ResourceLimitError`; the runtime does not return a silently pruned approximation.
Use `result.report()` or its per-batch profiles to inspect actual work and
`plan.explain()` to inspect preparation sharing and operator order. Numeric feature
bytes are narrower than peak process RSS. The [semantics contract](SEMANTICS.md)
describes these boundaries and generator cleanup.

Once the mapping works, evaluate any learned model on your own held-out task
before using its rankings. Keep a strong native/manual structural baseline.
For a single structural query, Neo4j may be faster and avoids graph export. The
[public movie demo](examples/README.md) and [performance page](PERFORMANCE.md)
make that tradeoff explicit.
