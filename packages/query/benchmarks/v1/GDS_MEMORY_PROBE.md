# Bounded reservation-lifecycle diagnostic

The six-condition native queue check failed on collaboration at both thread
settings after the partitioned warmup and one measured request. The public
reservation guard is not a direct JVM-free-heap measurement. Diagnose the
lifecycle before changing heap size, bypassing guards or restarting that cohort.

Use a disposable native Neo4j/GDS 2026.09.0 instance and the existing ARM Java
21.0.10+7 runtime. Keep the 8 GiB heap, one configured thread and existing rich
FastRP256/16-negative pipeline/classifier-selection budget. Generate 96 nodes
with undirected ring and seven-step chord edges, and request the first four
nodes. This synthetic fixture diagnoses resource accounting; it cannot establish
real-graph performance, application quality or release parity.

In each of two fresh processes, capture GDS memory lists/summaries and task state
after projection, after five standalone FastRP mutate/drop cycles, after fitting,
and after five complete exact partitioned requests. Preserve the initial fitted
model record, every request output, counters and all intermediate checkpoints.
Run one process with the current grouped UNWIND calls and the other with one
fully consumed read transaction per source call. Use identical graph, fit settings
and request semantics. Compare every output with the first request in its process
and compare the independently fitted one-thread processes separately.

Obtain JVM heap usage only if the installed native diagnostics expose it; record
unavailability explicitly. Retain all errors. Do not infer leaked physical memory
from reservation totals, infer a fix from a tiny fixture, or report these heavily
instrumented calls as performance measurements. Inspect resource deltas and source
before deciding whether a further reproduction on the failed graph is warranted.
