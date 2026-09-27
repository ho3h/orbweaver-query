# Native queue control: four completed conditions, two failures

All six predeclared graph/thread conditions were attempted once, sequentially.
Four completed and both collaboration conditions failed. **This is a failed
suite with no aggregate timing result and no closed release gate.** The frozen
sources, inputs, all six full-score matrices, successful records and both errors
are retained. No worker was restarted, heap increased or memory guard bypassed.

## Completed conditions

Each row describes one fitted native model/process, one warmup and three measured
requests per arm. Both arms return exactly the independently ranked full-score
reference. These are descriptive medians, not independent-process confidence
intervals or Orbweaver speedups.

| Graph | Threads | Global seconds | Partitioned seconds | Global / partitioned | Stable-ID recall@16 |
|---|---:|---:|---:|---:|---:|
| Friendship | 1 | 53.8031 | 7.7575 | 6.9356x | 0.4800 |
| Friendship | 4 | 43.5486 | 4.3555 | 9.9986x | 0.4800 |
| Communication | 1 | 3.9632 | 1.8110 | 2.1884x | 0.3798 |
| Communication | 4 | 3.5715 | 1.4970 | 2.3857x | 0.3798 |
| Collaboration | 1 | — | Failed | — | — |
| Collaboration | 4 | — | Failed | — | — |

The completed pipelines selected logistic regression from the existing fitting
budget. Native versions, ARM runtime checks, configured thread ceilings, evidence,
candidate domains and development-selected feature configurations are unchanged.
Read-only adapter/EXPLAIN and output serialization remain charged. Setup and
model fitting are recorded separately. Partitioning also changes repeated feature
preparation and output assembly, so this is not a queue-kernel-only ablation.

Friendship timings vary materially: its one-thread partitioned samples are
7.362, 7.758 and 11.578 seconds; its four-thread global samples are 44.425,
43.549 and 29.125 seconds. Do not combine this check with the earlier 4.638x
friendship diagnostic to manufacture a pooled speedup or attribute differences
across separately run campaigns to a code change.

## Collaboration failures

At both thread settings, the full-score audit, partitioned warmup and first
measured partitioned request succeeded. The second measured partitioned request
failed with `AvailableMemoryReservationExceededException`: FastRP required
16,606,944 reserved bytes with 3,267,884 available. The global timed arm was
therefore not reached. No median is reported from the single measured request.

Successful partitioned requests in these conditions needed nine adaptive rounds,
89 native procedure calls and 29,682 returned pairs; maximum per-source topN was
5,241. Exact cutoff ties therefore required substantially more overfetch than
friendship's one round, 64 calls, 2,048 returned pairs and maximum topN 32.

The matching public GDS source distinguishes reservation accounting from actual
free JVM heap: [MemoryTracker.availableMemory](https://github.com/neo4j/graph-data-science/blob/1317dc9fcc12322d55c11dc598f024debeea18c8/memory-tracking/src/main/java/org/neo4j/gds/memory/tracking/MemoryTracker.java)
subtracts tracked graph/task reservations from its initial budget. Completion
events release task reservations. The prediction executor reruns transient node
feature steps and removes their properties in a finally block. This establishes
what the exception means; it does not identify which lifecycle caused it here.
`analysis/memory-source-review.json` retains pinned source URLs and hashes.

No runtime reservation trace was captured, so transaction lifetime, task completion
and duplicate reservation accounting remain hypotheses. Do not describe this as
proven heap exhaustion, an identified GDS leak or a demonstrated transaction fix.
A bounded resource diagnostic must inspect reservations, active tasks and heap
across fully consumed requests before changing the reference. The four completed
conditions also do not establish long-running memory stability.

All six saved score matrices cover their complete candidate domains. Completed
outputs and quality reproduce independently from those scores. The failed
conditions' partial request outputs and model-selection metadata were not written
by the frozen worker before failure; console messages establish their progress,
not independent replay of those partial outputs. Their full-score quality is
retained in `ATTEMPT.json` without a successful request timing claim.

## Retention and verification

The 224-file archive preserves all six terminal outcomes. `ATTEMPT.json` explicitly
records four completed, two failed and zero unattempted conditions. There is no
`summary.json`. Analysis/retention tools were added after the workers terminated;
all original frozen inputs and scripts remain unchanged.

- Core tests: **251 passed, seven optional skips**; pinned Ruff and whitespace checks pass.
- Nine new archive checks reject missing/conflicting outcomes, misidentified
  errors, changed source, altered summary timings and false successful summaries.
- The earlier 35-file queue archive still verifies with the updated helper.
- The new archive restores, and its frozen-score audit reproduces `ATTEMPT.json`
  exactly; see `REPLAY.json`. Byte verification and numerical replay are separate.
- No confirmation data, CUDA execution, hosted CI or additional model fit was involved.

From `packages/query`:

```sh
python benchmarks/v1/gds_queue_archive.py verify \
  benchmarks/results/gds-queue-generalization-development-v1
python benchmarks/v1/gds_queue_archive.py restore \
  benchmarks/results/gds-queue-generalization-development-v1 \
  --output /tmp/gds-queue-generalization-replay
python /tmp/gds-queue-generalization-replay/analysis/benchmarks/v1/gds_queue_attempt_audit.py \
  /tmp/gds-queue-generalization-replay \
  --output /tmp/gds-queue-generalization-replay/replayed-attempt.json
```

The original six-condition summary command must reject this failed suite. The
separate audit does not waive that requirement. It checks available evidence
without substituting a four-condition success for the declared six conditions.

The native reference is materially stronger on the four completed conditions,
but collaboration and repeated-request resource behavior remain unresolved.
Approximate GDS search still needs its own quality/cost comparison. This finding
does not justify another Orbweaver CPU planner campaign; the performance research
milestone remains expensive-inference profiling against a strong combined graph
and model execution reference.
