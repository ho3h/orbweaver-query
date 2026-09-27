# Real Text2Cypher corpus: adapter conformance passed

Repeated all 1,806 normalized query strings from 1,949 movies-alias rows in the
pinned 2024v1 training corpus against a fresh disposable Neo4j 5.26.0 database.
The same pinned public movies fixture contains 171 nodes and 253 relationships.
The adapter code is unchanged from v1. The comparison oracle now treats only
`db.schema.visualization()`'s per-call virtual IDs as ephemeral while preserving
its complete schema properties, edge types, endpoints and multiplicity.

| Outcome | Queries |
| --- | ---: |
| Success on both paths | 1,798 |
| Nonempty successful output | 1,589 |
| Empty successful output | 209 |
| Identical raw bags and sequences | 1,797 |
| Equivalent virtual schema output | 1 |
| Matched missing-APOC failures | 7 |
| Matched 5,000-row limit failures | 1 |
| Unexplained mismatches / adapter-only failures | 0 |

The predeclared v2 gate passes. All raw and normalized output digests, query
inventory, result counts and gate were independently verified from saved
responses. The original v1 failure remains preserved. Tests show the virtual-ID
normalization still detects changed properties and reversed edge endpoints and
rejects ordinary database IDs.

Nonempty successful coverage includes 609 aggregations, 480 WITH queries,
898 WHERE queries, 661 ORDER BY, 780 LIMIT, 180 DISTINCT, 17 UNWIND, two OPTIONAL
MATCH queries, two variable-path queries and two shortest-path calls. These
categories overlap. No query was repaired based on its result and no official
test split or remote demo database was accessed.

The pinned graph lacks the `votes` property used by some corpus queries. Empty
or null-valued results are preserved, not counted as text-to-query correctness.
The seven APOC-dependent queries remain unsupported by this plugin-free fixture.
The row-limited query is not counted as a successful result comparison.

This verifies the adapter transports real engine results faithfully. It does
not measure inference quality, natural-language query generation, ISO GQL
conformance or end-to-end speed. Adapter/direct timings are descriptive because
cache and compilation order are not balanced. The 2025 release substantially
overlaps this corpus and is not treated as independent confirmation.

Reproduce with PyArrow, the Neo4j Python driver, an installed local Neo4j 5.26
distribution and Java 21 (all database data/configuration is temporary):

```sh
python packages/query/tools/text2cypher_execute.py freeze corpus-run \
  --parquet external_data/text2cypher/text2cypher-2024v1-train.parquet
python packages/query/tools/text2cypher_execute.py execute corpus-run \
  --neo4j-home /path/to/neo4j --java /path/to/java
python packages/query/tools/text2cypher_execute.py verify corpus-run
```

Use the audited corpus download command first. Freeze downloads the pinned movies
script separately. The source script and raw movie-value responses are not
redistributed in this results directory; the manifest records their identities.
The query inventory comes from Neo4j's Apache-2.0 Text2Cypher training dataset.
