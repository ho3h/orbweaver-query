# Trained-model Neo4j workflow v1

Use the preselected seed-71 model and evidence graph from the verified standalone
WN18RR reproduction. Copy/check their hashes and identities and freeze this
protocol, all harness/runtime/reference source, and request fixtures before
measurement. No labels or scores guide fixture source selection. Only a newly
created disposable loopback Neo4j 5.26 database may receive fixture writes.

Import all 40,559 declared nodes and 69,420 evidence triples, using application
IDs and the exact relation names. Export nodes and edges through the public
read-only adapter and require the resulting snapshot ID to equal the original
artifact before scoring. Report import setup time separately. The server uses
the helper's fixed 256 MiB maximum Java heap and 64 MiB page cache; no plugins.

Workloads: the same seed-71 distinct256, clustered256 and interleaved256 request
fixtures from the standalone runtime campaign. Each request receives a unique
ordinal. Parameterized Cypher looks up its source, finds two-hop endpoints that
are neither source nor an existing neighbor, selects the minimum endpoint ID,
and returns head/relation/target/ordinal in ordinal order. OPTIONAL MATCH retains
sources without a supported two-hop target. This input-only candidate selection
is not a recommendation-quality task. The complete evidence graph remains fixed.

Compare independent expansion, consecutive single-source caching, bounded source
grouping and an independent multi-source LRU reference. The LRU retains at most
256 sources and 16 MiB of numeric feature/score arrays, reuses relation scores,
evicts least-recently-used sources and bypasses oversize entries. This cap is
not total process memory. Every arm begins each batch with empty inference caches;
no result memoization crosses batches. The prepared graph/model and database
page/plan caches may remain warm. Grouping need not beat a cache that fits all
repeated sources; its benefit must be stated relative to the measured comparator.

Run three fresh client processes per strategy/workload: 36 workers in fixed
random order, native numerical threads fixed to one. Each worker loads the model,
exports evidence through the adapter, then runs one warm-up and five timed
complete candidate-query/inference/JSON-serialization batches. Reset inference
caches on every call. Record the first batch separately. The model and snapshot
may be retained across batches; database data is never mutated during scoring.

Measure separately: client imports/connection, model artifact loading, evidence
query execution plus Bolt transfer and snapshot construction, candidate query
compilation/execution plus Bolt transfer, inference, and full scored-row JSON
serialization. Record raw samples and process peak RSS. The adapter combines
evidence transfer and snapshot construction, so do not claim separate timings
for those two internals. Candidate timings include its EXPLAIN guard. Record
worker-entry-through-first-result time; it excludes interpreter startup and
standard-library imports. Outer client process wall includes all six batches.

Require exact evidence identity and complete candidate-binding/scored-output
digest equality across strategies and repetitions, preserving order, nulls and
duplicates. Verify LRU outputs independently on eviction/bypass fixtures first.
Recompute summaries and all gates from saved worker records. Preserve failures.
Performance hypothesis: grouped warm workflow median is at least 1.25x faster
than consecutive caching on interleaved256. Compare grouped versus LRU and all
other conditions descriptively; do not change the reference to rescue a claim.
No claim about remote-server network latency, persistent caches, concurrent
service throughput, other graph families, or query populations follows from
this loopback single-client experiment.
