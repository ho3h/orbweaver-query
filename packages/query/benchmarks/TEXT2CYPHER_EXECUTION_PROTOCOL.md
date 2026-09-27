# Local Text2Cypher adapter conformance v2

Use every row in the pinned 2024v1 training split with database alias
`neo4jlabs_demo_db_movies`. Deduplicate by the audited layout key, preserving
all source instance IDs; use normalized layout but do not repair query logic.
Do not consult official test splits or select queries based on execution results.
The existing audit identifies 1,949 rows and 1,806 normalized query strings.

Download Neo4j's public movies fixture at revision
`51cf90d18c1a7f74bce7a77083543697dfb0139d`, script SHA-256
`7be04aba2193790e0051308e6aa8550236e651cae652ea7da44b7dc01f4c4e69`.
Load its statements only in a disposable, newly created local Neo4j database.
Never connect to corpus-listed remote endpoints or an existing user database.
The source script is downloaded separately, not included in the distribution.
Its schema need not match every property in the corpus's live-demo schema;
report fixture properties/counts and empty results without inventing values.

Freeze the corpus/fixture identities, query inventory, protocol and current
adapter/harness source before execution. Set server transaction timeout 5 s,
client retained-row cap 5,000 and no extra database plugins. Retain syntax errors,
missing procedures, engine/runtime errors, row-limit failures and empty results.
The corpus is untrusted input: exclude external-input clauses (`LOAD CSV`) and
procedure calls other than `db.schema.visualization`, if encountered. This
inventory filter is not the adapter's security mechanism; the adapter still
requires the engine's read-only EXPLAIN classification before any execution.

For each query, execute through the adapter and through an ordinary driver
transaction, using the same database and row cap. The direct path is separately
compiled as read-only before running. Canonicalize Neo4j nodes, relationships,
paths and nested values with explicit type tags. Compare complete row bags with
multiplicity and report sequence identity separately. No ORDER BY means no
guaranteed order; ORDER BY with ties can also admit different sequences or LIMIT
subsets. Preserve every mismatch for diagnosis; do not silently waive it.

Gate: every jointly successful, bounded query must have identical result bags;
adapter-only failures and class/error mismatches must be zero. Dataset syntax
failures and missing dependencies may be matched failures, not successes.
Require nonempty successful coverage of MATCH, WHERE, WITH, aggregation,
ORDER BY, LIMIT, DISTINCT, OPTIONAL MATCH and UNWIND. Report structural-indicator
coverage independently of this gate. This is adapter execution conformance,
not a language-model benchmark, query-meaning accuracy test, inference-quality
evaluation or broad GQL certification. Direct and adapter execution use the same
database engine; the test isolates data transport and boundary behavior.

Record query-level row counts, output digests, error codes and wall times; timing
is descriptive only because query order, compilation and caches are not balanced.
Save the raw results and frozen inventory, then independently recompute aggregate
counts and gates. Whole-workflow extraction/inference/serialization performance
requires a separate timed protocol with a matching trained model and controls.
The v1 run completed all 1,806 queries and failed its raw-identity gate on one
procedure: `db.schema.visualization()` allocates new negative virtual entity IDs
on every invocation. Preserve v1 and its failure. This revision repeats the full
inventory with an explicit comparison for that exact procedure only: alpha-rename
virtual IDs, compare nodes by full label/property descriptions and relationships
by endpoints/type/properties, retain duplicate relationships, and ignore ordering
of the schema's node/relationship lists. All ordinary entities and other queries
keep exact ID/property/list comparison. Preserve original raw IDs and digests as
well as the structural comparison. This change affects the test oracle only;
the adapter continues to return the database's original objects and ordering.
