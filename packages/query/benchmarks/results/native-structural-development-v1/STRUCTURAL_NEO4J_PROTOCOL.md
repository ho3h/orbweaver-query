# Native structural-score application comparison

Declared before measurements. This is an additional development comparison,
not a substitute for the learned GDS pipeline comparison or final confirmation.

## Why this control is required

GDS 2026.09.0 supplies `gds.linkprediction.resourceAllocation`,
`gds.linkprediction.adamicAdar` and `gds.linkprediction.commonNeighbors`.
Their actual signatures and a toy execution were checked in a disposable
database; the older `gds.alpha.linkprediction.*` names are deprecated aliases.
The structural quality results cannot establish an advantage over
GDS as a whole merely by beating its learned FastRP pipeline. Compare identical
structural scoring rules through the actual database/application boundary.
Also include a Cypher implementation that shares common-neighbor enumeration;
calling three separate native functions must not be the only baseline.

## Data and logical requests

Use the three frozen outer-training graphs and candidate rows from
`plan-development-v3`. They have a single undirected LINK relation, no self edges,
and no parallel relationships. Import each canonical unordered pair once into
an isolated Neo4j Community/GDS 2026.09.0 database, with unique external string
IDs matching the Orbweaver snapshot. This simple-graph restriction makes distinct
neighbor degrees match raw database relationship degrees. It does not prove
equivalence on arbitrary multigraphs or filtered evidence projections.

For every graph, run the four declared candidate workloads with (a) three
structural scores and (b) the same scores filtered by resource allocation >=0.2.
Preserve input order, duplicates, nulls, unsupported self/adjacent pairs, valid
zero scores and all payload fields. The input rows are schema-valid; malformed-
input behavior remains covered by the product tests. Node IDs and relationship
type are indexed/schema-checked; parameter values never become query text.

## Physical alternatives

1. `Neo4jSource.run_plan`: read the candidate bindings over Bolt, then execute
   the three models locally against the complete exported snapshot. Evaluate
   uncached and persistent-pair-cache regimes; charge export and warming separately.
2. Native GDS scalar functions inside the read query. Apply the selective score
   before the remaining functions when filtering, while preserving null/status
   semantics. Return the same logical rows and score fields.
3. Two Cypher subqueries that enumerate distinct common neighbors once per pair
   and compute each neighbor's degree once. The fused variant accumulates all
   three scores. The selective variant retains the degree list, computes resource
   allocation, filters, and then computes the other two scores. Do not crop
   intermediate evidence to requested targets.
4. Exact precomputed pair scores for the declared working set, with construction,
   retained size and warm lookup reported separately. This is an oracle reuse
   control, not a free cold-start comparison.

All read paths use the adapter's same read-transaction/EXPLAIN boundary, fetch
size and Python driver. Return normalized scalar records through one common
metadata/JSON serialization path; raw server score fields are independently
compared with the frozen SciPy matrices/production scorer before timing. Do not
charge full graph export to native functions that can operate directly in Neo4j.
Also report inference-only measurements separately, not as database latency.

## Measurement and scope

Freeze source, protocol, graph/query hashes and job order before execution.
Use at least three independent process/database repetitions, warm the Cypher
query compiler, and retain three or more measured requests per condition. Record
import, evidence export, precomputation, client-observed request latency and peak
process memory separately. The request boundary includes candidate execution,
Bolt transfer, inference/filtering and normalized serialization. Preserve all
failed attempts. Avoid overlap with the ongoing native training and Python
runtime campaigns. Configuration-specific concurrency must be recorded; the
native scalar functions do not take the learned pipeline's concurrency parameter.

The executable freezes nine database workers (three datasets x three repetitions),
six arms x four workloads x two shapes per worker, two unmeasured compiler/request
warmups and five measured requests per condition. Worker order uses seed 8201;
condition order uses seed 8202 plus the frozen worker index. All queries use the
Community `slotted` runtime, 1,000-row driver fetches, a 2 GiB JVM heap and 64 MiB
page cache. Hash the GDS jar, Neo4j libraries and Java binary/release before running.
Native function signatures are recorded from `SHOW FUNCTIONS` in each worker.

`local_cold` clears the bounded pair cache for every request; the evidence snapshot
and compiled database query remain resident. `local_warm` primes the same plan's
pair cache once. `precomputed` constructs a lookup table for exactly the declared
working set, including score metadata, and still reads candidate rows through
Bolt on every request. Its serialized table size is reported as serialized size,
not a resident-memory estimate. All local arms pay separately reported full
evidence export; native arms do not. Report export plus preparation amortized over
1/10/100/1,000 requests, alongside warm request latency. Database import is shared
setup for all arms. Python and Java peak RSS cover each whole worker across arms;
they cannot establish a per-arm memory advantage. The local inference-only samples
exclude Bolt but retain validation, filtering, materialization and serialization.

These are fixed, immutable fixtures. Raw Neo4j functions read live database
state, while Orbweaver reads an exported immutable snapshot. Concurrent writes,
partial evidence projections and multigraphs need separate equivalence protocols;
do not silently treat native functions as a drop-in backend for such snapshots.
This experiment can show latency/setup tradeoffs at equal structural quality;
it cannot establish novel algorithms or general GDS/Quail superiority.

Sources checked on 2026-09-26:
[GDS topological link prediction](https://neo4j.com/docs/graph-data-science/current/algorithms/linkprediction/),
[resource allocation](https://neo4j.com/docs/graph-data-science/current/alpha-algorithms/resource-allocation/),
[learned pipeline prediction](https://neo4j.com/docs/graph-data-science/current/machine-learning/linkprediction-pipelines/predict/).
The resource-allocation page can expose older cached documentation; the actual
2026.09.0 runtime signatures take precedence over those older function names.
