# Native ARM structural request comparison

Nine disposable Neo4j/GDS workers completed, covering 432 physical conditions
across three fixed public graphs, four candidate patterns, two filter shapes and
six execution alternatives. Every output agrees with the independent set oracle
and across alternatives: order, multiplicity, payloads, null/support status and
provenance match. Maximum absolute score difference is 1.4210854715202004e-14.

This replaces the original timing interpretation following the
[runtime architecture audit](../native-runtime-audit-v1/FINDINGS.md). Both Python
and Java now run natively on ARM. Neo4j/GDS are 2026.09.0 and Java is Temurin
21.0.10+7-LTS, matching the original Java version. Frozen runtime checks reject
the old x86_64 VM. Current Orbweaver source differs from the original campaign;
the difference in ratios does not isolate the cost of architecture translation.

## Descriptive results

Ratios are fastest declared control latency divided by the fixed candidate's
latency, geometrically averaged over 24 conditions. Above one favors Orbweaver.
Cold controls are native GDS scalar functions, fused Cypher and selective Cypher.
Warm controls also include exact working-set precomputed lookup. Each condition
has two warmups and five measurements in each of three database repetitions.

| Candidate | Request only | Export/preparation over 1 request | 10 requests | 100 requests | 1,000 requests |
|---|---:|---:|---:|---:|---:|
| Local cold | 1.059x | 0.014x | 0.120x | 0.573x | 0.970x |
| Local warm | 0.889x | 0.014x | 0.120x | 0.605x | 0.897x |

The warm request-only ratio corresponds to about 12.5% greater local latency.
Four cold and thirteen warm conditions exceed 10% regression against their best
control. Median evidence export costs are 0.660 seconds (collaboration), 2.359
seconds (friendship), and 0.600 seconds (communication). Native controls operate
on the database and do not pay snapshot export. Shared database startup/import
is recorded separately and excluded from these ratios for every alternative.

The existing analysis script resamples whole database repetitions within graph.
Its conditional central 95% ranges are [0.962, 1.066] for cold and [0.836, 0.935]
for warm request-only ratios. Only three independent repetitions per graph and
re-selection of the best control make these descriptive ranges; they are not a
well-calibrated significance test or evidence about unseen workloads. The script
and results are hashed in `ANALYSIS_RECEIPT.json`. No method or workload was
changed in response to the new timings.

These results do not establish a substantial native advantage or close a 1.0
gate. They are not learned-pipeline timings, a concurrency-four GDS evaluation,
a Quail comparison, or an update/memory-pressure experiment. Confirmation labels
are absent. The local evidence graph remains an immutable exported snapshot;
the fixture does not test concurrent database writes. Process RSS covers each
whole worker across all alternatives and cannot establish per-arm memory savings.

## Reproduction

`ARCHIVE.json` protects frozen source, protocol, graph/query inputs, runtime
identity, results and compressed exact worker records. Archive verification
checked all nine worker records with no failures. All graph/query inputs come
unchanged from `plan-development-v3`: SNAP ca-GrQc, facebook_combined and
email-Eu-core, with undirected existence semantics as declared in the retained
protocol. Model assets retain their embedded third-party notices.

```sh
python packages/query/benchmarks/v1/plan_archive.py verify \
  packages/query/benchmarks/results/native-structural-arm64-development-v1
python packages/query/benchmarks/v1/plan_archive.py restore \
  packages/query/benchmarks/results/native-structural-arm64-development-v1 \
  --output /tmp/native-arm-replay --with-workers
python /tmp/native-arm-replay/structural_neo4j.py summarize /tmp/native-arm-replay
```

The archive does not ship Neo4j, GDS or Java. A timing rerun requires the frozen
runtime artifacts and matching native architecture; launch the restored script's
`execute` command in a fresh restored directory without `--with-workers`, passing
`--neo4j-home`, `--java` and `--gds-jar`. Preserve the original run and failures.
