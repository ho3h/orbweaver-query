# Existing transformer application: bounded headroom diagnostic 1

This is an architectural investigation, not a release performance campaign or a
new model-quality evaluation. Use the existing frozen Qwen3-4B classifier head
and its exact shipped prompt builder, chat template and 4096-token left truncation.
Base: `mlx-community/Qwen3-4B-Instruct-2507-4bit`, revision
`50d427756c6b1b2fe0c0a10f67fbda1fc8e82c1b`. Record checksums of base files,
head, calibration, input, implementation and relevant installed runtime sources.
All inference is local on the available Apple GPU. No paid service is used.

Select the first three distinct application themes in the existing synthetic
`data/v1.5/train_mixed.jsonl`, in file order. Do not inspect model outputs or
quality labels to select them. Load each graph into a newly created disposable
Neo4j database. Use the existing `all_blockers(limit_per_blocker=3)` and
`subgraph_snapshot` implementations, without changing their graph rendering.
Never stage or apply repairs. Retain capture failures; never replace a selected
graph because of its measured results.
Use the product's existing `load_cypher` fixture loader so semicolon-separated
CREATE clauses preserve their variable bindings. The first capture attempt's
direct query submission failed before any model timing; retain that failure.

Three application-derived input shapes:

1. `independent_events`: the three original graph/event prompts.
2. `pair_scan`: candidate-pair review events with the existing pair-local snapshots.
   This is the current product's classification input path.
3. `scoped_review`: the same candidate events with their complete, fixed source
   graph as context. This represents a proposed graph-scoped review query, not
   current product equivalence. All controls receive identical prompts within
   this shape. More context changes the inference task; no cross-shape quality
   or speedup claim is permitted.

Capture exact post-truncation token IDs using explicit `return_dict=False` for
Transformers 5 compatibility; reject
non-integer IDs before freezing. The second capture accidentally recorded two
dictionary key names per prompt, was rejected before timing, and is retained.
This compatibility adaptation preserves the intended shipped prompt tokens.
Capture uses MLX-LM's tokenizer wrapper, as the shipped loader does. Captures
three and four exposed a serialization bug: sorting event JSON keys changed the
shipped prompt's token order on reload. The third attempt failed on warmup,
and the fourth was rejected by a token-only preflight. Neither ran a forward
pass or timing worker. Preserve scenario object order and check every serialized
input's tokenization on reload before freezing. Retain all rejected captures.
Count shared graph contexts separately
from shared token prefixes: overlapping nodes do not imply reusable transformer
activations. Report unlimited prefix-trie fresh-token and causal-attention-pair
work as optimistic *work* bounds, not hardware latency bounds. Prefix reuse
always leaves the final token for evaluation, even for identical prompts.

Five ordinary execution controls, with a fresh request-scoped state each time:

- `scalar`: current single-prompt body forward, followed by the existing head.
- `batch4` and `batch8`: length-ordered full-prompt batching, at most 4 or 8 rows
  and 16,384 padded tokens per batch. Right-pad under causal attention, gather
  each row's final real token, and avoid unnecessary KV writes. Restore row order.
- `prefix_input`: ordinary longest-prefix lookup over a 512 MiB numeric KV LRU
  in input order, using MLX's existing cache implementation.
- `prefix_sorted`: the same implementation after lexicographic token ordering.
  This is a strong conventional request-ordering control, not a new query planner.

Prefix storage excludes the final token and stores no final answers. Compact
retained KV arrays and account for all numeric state bytes. Lookup, copying,
retention, evictions and request ordering are timed. Transient memory and model
weights are outside the retention cap; report MLX peak allocation separately.
No inference kernels, model weights, prompts, context lengths or precisions vary
between arms. The classifier already bypasses the full vocabulary output head.

Freeze before model timing. Load one model process and warm each arm once on
the first original scenario. Run three measured repetitions per shape/arm in
seed-20260927 shuffled order. Include tokenization, planning/cache handling,
GPU-synchronized body forward, classifier head, CPU copies and JSON output.
Record model loading separately. Do not run competing tests/builds/model probes
while timing. Per-phase instrumentation is diagnostic and adds overhead.
These are repeated measurements in one process, not independent process repeats
or a basis for a release significance claim. Retain all raw outputs and failures.

Compare all six class probabilities to the scalar control with absolute and
relative tolerance 1e-3, and logits with absolute 1e-2 / relative 1e-3 tolerance.
Require identical top class and complete ordered APS prediction sets for every
row and repetition. Report every numerical or decision disagreement; do not
loosen tolerances after observing results. This is inference equivalence, not
verification of real-world classification accuracy or conformal coverage.

Use scoped-review outputs to count how many candidates a correlated per-graph
existence query would need before its first review-ready singleton `add_link`
or `merge_entities` result. Include all candidates for negative results. This is
an offline work-count bound, not a measured early-termination implementation.
The eventual baseline must use the same early termination too.

Decision: quantify whether the actual transformer application has material
avoidable cost and which conventional controls already remove it. A large gain
over scalar execution alone is not novelty or parity with Quail. This probe does
not yet optimize joint batched-prefix execution, compare vLLM/Quail on matched
hardware, or time complete database/inference/update workflows. Those remain
necessary before promoting a mechanism into a release claim.
