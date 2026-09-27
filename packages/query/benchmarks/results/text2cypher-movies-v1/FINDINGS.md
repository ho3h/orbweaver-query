# First real corpus execution: failed raw-identity gate

Executed all 1,806 distinct normalized queries from 1,949 movies-alias rows of
the pinned 2024v1 training corpus against a disposable Neo4j 5.26.0 server.
The pinned official movies script creates 171 nodes and 253 relationships.
Its properties do not include the `votes` field mentioned by some corpus schemas.
No remote demo database or official test split was accessed.

- 1,798 queries completed within the 5,000-row cap on both adapter and direct
  driver paths: 1,589 nonempty, 209 empty.
- 1,797 of those queries have identical complete raw row bags and sequences.
- Seven queries use unavailable APOC functions and fail with the same engine
  syntax code on both paths. One exceeds the retained-row cap on both paths.
- All required structural categories have nonempty successful examples,
  including OPTIONAL MATCH (2) and UNWIND (17).
- The remaining successful query, `CALL db.schema.visualization()`, differs only
  in per-invocation negative virtual node/relationship IDs. The raw-ID gate is
  therefore **failed**, not retrospectively reclassified as passed.

The full output replay verified raw response hashes, inventory, aggregates and
the failed gate. This is an adapter comparison using the same underlying engine,
not Text2Cypher answer accuracy, graph inference quality or GQL certification.
Descriptive timings are unbalanced for compilation/cache order and do not support
an adapter speed claim. A v2 oracle will compare the virtual schema structure
explicitly while retaining raw identities and repeating the full corpus.
