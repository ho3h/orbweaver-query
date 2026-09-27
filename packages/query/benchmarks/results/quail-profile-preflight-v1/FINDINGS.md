# Profiling reference prepared; CUDA capture remains unvalidated

The new harness supplies separate instrumentation for the frozen Quail/vLLM
execution reference. It changes no inference algorithm, candidate domain, prompt,
model selection or original timing protocol. No model or GPU profiler has run.

It also fixes an execution-preparation problem: the current candidate bridge has
changed since the reference was frozen, so its original hash check rejects the
current package. The new bundle retains the entire package from reference commit
`fcb8aa0ae05f29faf2ae45246d9543fe38c084f5`, alongside the original manifest, tokenizer,
plans, input pairs and license notices. The original reference stays unchanged.

The CPU preflight uses the actual upstream request executor, Foreign callback,
join submission and projection. Both fresh-query executions preserve all 339
candidate decisions, the 150,780-token prompt multiset, one prefix-cache reset
per execution and 160 restored bindings under the fixed oracle. One execution
passes through the instrumentation wrapper's dry path. The original callable
is restored afterward. These oracle bits are not classifier outputs or quality
evidence; the dry path never calls torch's profiler or a vLLM worker RPC.

The first preparation failed because `execute_query` stores the explicitly
lowered request plan on the Query object; the second preflight expected its
original Quail join plan. Fresh queries resolve that harness error. The original
failed harness, manifest and failure record are retained under
`preparation-history/initial`; unchanged dependencies can be reconstructed from
the final bundle. Later preparation adds partial-trace retention on failure and
includes the data, tokenizer and repository license notices. No failed inference
run has been discarded: no inference run was launched.

## What the new code is intended to measure

Quail receives local CPU/CUDA capture around its post-boot graph execution.
The vLLM path configures the engine profiler and a worker extension that annotates
the actual configured scheduler. Before GPU execution, the harness requires a
completed original unprofiled worker with three stable measured answer sets.
The profiled environment and every decision must match that reference.
GPU capture APIs, worker extension loading and actual trace production still
require validation on the supported H100 host.

The trace analyzer aligns separate epoch time bases, clips events to the graph
interval, merges concurrent kernel/copy activity and reports scheduler overlap.
It rejects absent GPU events, missing scheduler instrumentation, incorrect process
identity, invalid durations, failed captures and unverified answers. Activity is
not FLOP utilization; overlap alone does not prove which work caused GPU idle time.
Model boot, outer result restoration and graph export remain separate costs.

Implementation references: Quail's pinned
[vLLM profiler](https://github.com/fsdatalab/quail/blob/41b883b838687cfbf018080f068f3e81bf2f8e64/experiments/vllm_join_profile_worker.py),
its [GPU timeline analysis](https://github.com/fsdatalab/quail/blob/41b883b838687cfbf018080f068f3e81bf2f8e64/experiments/profile_gpu_timeline.py),
and the [vLLM 0.26.0 single-process executor](https://github.com/vllm-project/vllm/blob/v0.26.0/vllm/v1/executor/uniproc_executor.py).

## Verification and use

The local core suite passes **258 tests, with seven optional skips**. Seven
new deterministic trace tests exercise multi-process time alignment, clipping,
overlap, ignored driver GPU activity and capture failures. The 54-file archive
verifies and restores; the restored CPU preflight is byte-identical and the same
seven trace tests pass outside the checkout. Ruff and whitespace checks pass.
These results do not certify the GPU-only capture branches or establish speedup.

```sh
python packages/query/benchmarks/results/quail-profile-preflight-v1/verify.py \
  --output /tmp/quail-profile-ready
python /tmp/quail-profile-ready/quail_profile_reference.py preflight \
  /tmp/quail-profile-ready --output /tmp/replayed-quail-preflight.json
python -m pytest -q /tmp/quail-profile-ready/validation/tests
```

Use Python 3.12 with the clean pinned Quail checkout for the preflight. The bundle
selects its frozen Orbweaver package automatically. See `QUAIL_PROFILE_PROTOCOL.md`
inside the restored bundle for unprofiled-worker and separate capture commands.
No cloud application, paid resource or CUDA worker was started by preparation.

Archive SHA256:
`227d2450716296ac27a2f63e6eb37afba1bc3b10685a19164df00de5625b5277`.
All 1.0 gates remain open. Supported GPU access and a useful application's
measured residual costs are still required before another optimizer decision.
