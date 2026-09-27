# GDS task retention removes the small reproduction's reservation growth

The native GDS failure has a bounded reproduction and a tested configuration
workaround. **This is resource-lifecycle evidence on 96 nodes, not a performance
result or proof that the original collaboration workload now completes.** The
earlier six-condition suite and its two failures remain unchanged.

## Observations

Four fresh native Neo4j/GDS 2026.09.0 processes used the same deterministic graph,
rich FastRP256/16-negative pipeline configuration and classifier-selection budget,
one thread and 8 GiB heap. Each ran five standalone FastRP mutate/drop cycles,
one fit and five exact partitioned prediction requests. GDS's memory guard stayed
enabled; no library binary, model definition, authentication or heap limit changed.

| Condition | Task retention | Reservation increase per standalone FastRP | Increase per prediction request | Final task reservations |
|---|---:|---:|---:|---:|
| Original grouped calls | 0 s | 304,416 B | 2,435,616 B | 14,606,744 B |
| Separate source transactions | 0 s | 304,416 B | 2,435,616 B | 14,606,744 B |
| Fresh grouped control | 0 s | 304,416 B | 2,435,616 B | 14,606,744 B |
| Fresh grouped deferred cleanup | 60 s | 0 B | 0 B | 0 B |

Every checkpoint reports no active GDS tasks. The zero-retention conditions retain
reservation entries for already completed Loading/FastRP/other tasks even after
standalone embedding properties are dropped. Splitting transactions does not
remove the growth. JVM heap usage at checkpoints ranges from about 79 MB to
252 MB across the four conditions, well below the unchanged 8 GiB limit. These
are sampled heap observations, not peak-memory measurements or evidence that no
other resource issue can exist.

All **20 prediction outputs match exactly**, within each process and across its
independently fitted controls. The fresh default and retained conditions have
identical frozen sources and manifests except for the declared retention value.
The effective database settings are read back: progress tracking remains enabled,
and task retention changes from `0s` to `1m`. No task reservation remains at any
checkpoint in the 60-second condition, including immediately after fitting.

## Why zero retention can lose the release notification

In the matching [PerDatabaseTaskStore](https://github.com/neo4j/graph-data-science/blob/1317dc9fcc12322d55c11dc598f024debeea18c8/progress-tracking/src/main/java/org/neo4j/gds/progress/registration/PerDatabaseTaskStore.java),
`markCompleted` visits each listener, then iterates the same task collection for
that listener. The [TaskStoreCleaner](https://github.com/neo4j/graph-data-science/blob/1317dc9fcc12322d55c11dc598f024debeea18c8/progress-tracking/src/main/java/org/neo4j/gds/progress/registration/TaskStoreCleaner.java)
synchronously clears the collection when retention is zero. If it runs before
the memory listener, that listener sees an empty collection and never receives
the completed tasks needed to release their reservations. A CopyOnWriteArrayList
does not prevent this: the next listener starts a new iteration after the clear.

The [provider registers the memory listener](https://github.com/neo4j/graph-data-science/blob/1317dc9fcc12322d55c11dc598f024debeea18c8/procedures/integration/GraphDataScienceProceduresProvider.java);
the [memory tracker](https://github.com/neo4j/graph-data-science/blob/1317dc9fcc12322d55c11dc598f024debeea18c8/memory-tracking/src/main/java/org/neo4j/gds/memory/tracking/MemoryTracker.java)
releases reservations on completion callbacks. This source-level ordering defect
explains the observed growth and why deferred cleanup prevents it in the probe.
The listener collection has no guaranteed order, so do not claim every zero-retention
process must fail. Raw callback order was not instrumented directly.

GDS exposes [task retention as a supported setting](https://github.com/neo4j/graph-data-science/blob/1317dc9fcc12322d55c11dc598f024debeea18c8/neo4j-settings/src/main/java/org/neo4j/gds/settings/ProgressFeatureSettings.java).
The disposable runner now accepts the explicit opt-in
`gds_progress_retention_seconds=60`. Its default remains unchanged. This delays
removal of completed progress records; it does not retain reservations, model
outputs or embeddings. Retained task metadata has a resource cost that still
needs assessment on the full workload. A source-level fix would deliver completion
events over a snapshot independent of cleanup; no GDS patch was applied or posted.

## What changes next

Use a new, explicitly configured diagnostic to check the previously failing
collaboration workload against its complete-score references. Keep the heap,
guard, model, candidate domain and thread settings matched. Inspect task reservations
after repeated requests and preserve model-selection records before later failures.
Do not relabel the original failed cohort as successful or pool its timings with
new configurations. Approximate-search quality/cost and all 1.0 gates remain open.

This resolves the small reproduction and rejects transaction splitting as a fix.
It does not establish full-graph reliability, a general repair for GDS, an Orbweaver
speedup, or a reason to resume broad CPU planner tuning. Expensive-inference
profiling against a strong combined graph/model reference remains the research
priority, pending supported GPU access.

## Evidence and replay

The **172-file archive** retains both original probe processes, the fresh
zero/60-second controls, pre-execution manifests, source snapshots, fitted-model
records, checkpoints, outputs, consoles and the post-run audit. Pinned source
URLs/hashes are in `source-review.json`. No confirmation data was opened.

The archive verifies and restores. Recomputing reservation deltas, checking
effective settings and comparing all 20 outputs reproduces the saved summary
byte for byte (`REPLAY.json`). These checks execute no database or model.
Core regression tests: **251 passed, seven optional skips**. Pinned Ruff and
whitespace checks pass. These are local results, not hosted CI or CUDA validation.

From `packages/query`:

```sh
python benchmarks/results/gds-memory-diagnostic-development-v1/verify.py \
  --output /tmp/gds-memory-replay
python /tmp/gds-memory-replay/gds_memory_audit.py /tmp/gds-memory-replay
```

Live reproduction uses each restored condition's `gds_memory_probe.py`, native
runtime paths and one-thread environment from its manifest. Preserve the original
outputs and run in a new directory containing only the frozen input files and
manifest; the worker deliberately refuses an existing result directory. These
instrumented probes do not report elapsed-time comparisons.
