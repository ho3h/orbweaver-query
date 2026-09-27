# Text2Cypher supplies a realistic query corpus

Audited the pinned training splits from Neo4j's
[2024 dataset](https://huggingface.co/datasets/neo4j/text2cypher-2024v1) and
[2025 dataset](https://huggingface.co/datasets/neo4j/text2cypher-2025v1). Both cards
declare Apache-2.0. Only the two train parquet files were downloaded/read. No
queries were executed. Exact revisions and SHA256 identities are in
[the report](REPORT.json).

| Training corpus | Rows | Rows with database alias | Exact schema strings |
| --- | ---: | ---: | ---: |
| 2024v1 | 39,554 | 22,093 | 966 |
| 2025v1 | 35,946 | 18,976 | 965 |

The files contain question, schema, Cypher, source, instance ID and optional
database alias. They do not contain graph snapshots, execution results, model
scores or labeled missing-link/merge decisions. A database alias identifies a
possible route to a fixture; it does not prove a current accessible endpoint or
reproducible snapshot. Remote databases have not been contacted.

## Representation and overlap

35,922 rows in 2025 encode clause separators using literal escaped newlines.
The first raw audit found only three byte-identical queries in common. After
explicitly decoding layout outside quoted strings/identifiers and normalizing
whitespace outside them, the corpora share **33,839 query strings** and contain
**37,321 distinct normalized queries** altogether. They also share 35,927
instance IDs. These are textual overlap measures, not proof of query semantic
equivalence. Preserve quoted literal contents during preprocessing.

Do not treat the two releases as independent training/confirmation datasets.
Retain row provenance, deduplicate by query/schema/task lineage, and use database
or schema groups for reserved coverage tests. Public test splits remain unread.

## Useful coverage

On the larger 2024 training split, lexical indicators include 8,945 `WITH`
queries, 11,876 aggregation queries, 874 `UNION` queries, 3,103 relation patterns
containing `*`, 59 `OPTIONAL MATCH` queries and 98 `UNWIND` queries. Indicators
ignore comments and quoted strings; they are not a parser or validity checker.
Representative instance IDs and both corpora's full counts are in the report.

Use these as a source for realistic adapter conformance and mixed query
workloads, then validate statements with a real engine against pinned public
graph fixtures. Scoring operations should consume explicitly mapped bindings
from those queries while retaining the correct model evidence. Performance and
model supervision require execution data and task labels beyond text/query
pairs. The corpus can also support a separate future Text2Cypher frontend, if
requested; no language model is being trained by this audit.

Reproduce (PyArrow is an audit-only dependency):

```sh
python packages/query/tools/text2cypher_audit.py --download \
  --data-dir external_data/text2cypher \
  --output packages/query/benchmarks/results/text2cypher-audit-v2/REPORT.json
```

The command checksum-verifies existing files and refuses to replace a different
report. Tests cover quoted-string preservation, encoded-layout normalization
and representative coverage indicators.
