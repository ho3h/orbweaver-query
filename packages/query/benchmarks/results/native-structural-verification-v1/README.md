# Matched native structural correctness

All 144 conditions passed: three frozen public graphs, four candidate workloads,
two filter shapes and six physical alternatives. The maximum absolute score
difference from the independent Python-set oracle was 1.4210854715202004e-14,
within the declared 1e-12 absolute/relative tolerance. Row counts, order,
duplicates, input payload, null/support status and graph/model metadata agreed.
The full raw records are retained in `verification.json.gz`, with a checksum of
the original uncompressed bytes in `ARCHIVE.json`.

The alternatives are cold/warm local composed plans over Cypher bindings,
GDS 2026.09.0's native `gds.linkprediction.*` functions, fused Cypher accumulation,
selective Cypher over shared neighbor degrees, and exact working-set lookup.
Neo4j evidence was imported as one relationship per unordered pair and exported
in both directions; all exported snapshot identities matched the frozen inputs.

These are correctness observations only. They were collected while another
native model was fitting. There is no timing or memory advantage claim here.
The separately frozen timing campaign uses nine database workers and 432
conditions, with compiler warmup, process repetitions and charged export/setup.
Its manifest hash is
`bfaa9b97994d332d110858a96053e22c7372b7d694dc368ad18ee200a2c4f28d`.

Verify retained bytes or restore the exact source/inputs:

```sh
python packages/query/benchmarks/v1/structural_verification.py verify \
  packages/query/benchmarks/results/native-structural-verification-v1
python packages/query/benchmarks/v1/structural_verification.py restore \
  packages/query/benchmarks/results/native-structural-verification-v1 \
  --output /tmp/native-structural-replay
python /tmp/native-structural-replay/structural_neo4j.py verify \
  /tmp/native-structural-replay --neo4j-home /path/to/neo4j-2026.09.0 \
  --java /path/to/java-21 --gds-jar /path/to/gds-2026.09.0.jar
```

Exact replay checks the original runtime artifact hashes, including Java and
Neo4j libraries. For another platform/runtime build, freeze a new campaign and
report its identity separately. Source arrays and parameters are retained;
confirmation labels are absent from this experiment. The static fixture scope
and live-database/snapshot differences are defined in the copied
[protocol](STRUCTURAL_NEO4J_PROTOCOL.md).
