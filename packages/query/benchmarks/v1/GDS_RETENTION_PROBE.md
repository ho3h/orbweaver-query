# Test deferred task cleanup without changing inference

The initial 96-node probe showed identical reservation growth with grouped and
separate transactions, including standalone FastRP calls. Every observed task
list was empty after calls finished, while task reservations accumulated. It
therefore rejects transaction splitting as a sufficient remedy.

Pinned GDS source suggests a completion-listener ordering defect:
`PerDatabaseTaskStore.markCompleted` iterates listeners, each over the same
mutable task collection. `TaskStoreCleaner` clears that collection synchronously
when retention is zero. A subsequent `MemoryTracker` listener can then receive
no tasks and cannot release their reservations. The task collection uses a
CopyOnWriteArrayList, but each listener begins its own iteration; the later
listener sees the cleared collection. Listener order is not guaranteed.

Test this hypothesis with two fresh, sequential grouped-call probe processes.
Both use exactly the original deterministic 96-node fixture, five standalone
FastRP mutate/drop cycles, rich FastRP256/16-negative fit and five exact repeated
partitioned requests. The two processes use identical frozen source and differ
only in task retention: default zero versus the supported configuration
`gds.progress_tracking_retention_period=60s`. Read back the effective settings.
Record reservations, active tasks and available JVM heap diagnostics at every
checkpoint. Keep the 8 GiB heap, guard, model/configuration, native runtime and
thread ceiling unchanged. Do not alter GDS source, clear its tracker manually,
change authentication or reuse either database from the original probe.

Compare reservations and exact outputs. A successful small probe identifies a
configuration workaround for this reproduction, not a general GDS patch or proof
that the original collaboration workload now completes. Keep both previous failed
conditions and original source snapshots unchanged. Any later full-graph check
must be a new explicitly configured diagnostic.
