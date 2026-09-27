# Matched Quail / candidate-restricted vLLM diagnostic

This is an inference execution reference, not a new Orbweaver optimization or
a 1.0 acceptance campaign. Use the existing complete SciFact development
candidate domain as an adverse, low-fanout case. Do not manufacture graph edges,
duplicate documents to inflate reuse, or compare restricted candidates against
an unconstrained Cartesian product. Graph export is outside this diagnostic;
no end-to-end graph speedup can be inferred from it.

## Fixed contract

- Clean Quail source `41b883b838687cfbf018080f068f3e81bf2f8e64`, Python 3.12,
  vLLM 0.26.0; upstream package dependencies pinned by that revision.
- One H100 SXM, Qwen/Qwen3-4B-FP8 revision
  `96b30dc13593a244a5e59e84687309f53c375cfa`, FP8 weights, BF16 activations/KV.
  Verify the same model-file hashes before either arm. No paid resource is
  launched by these commands.
- All 339 distinct source pairs, 340 binding occurrences. Full title and
  abstract, no gold rationales. Frozen input hash
  `678d0fb5e2c3f23a6d629bd1f12c222c9eb1c066090697c532cb7b6db9d2c8a2`;
  truth hash `b939a0781cb72d597509f40e4ce6dca441340f5d02323ceb7d7399fba109e20c`.
- One fixed Boolean support prompt. SUPPORT maps to TRUE; CONTRADICT and
  NOT_ENOUGH_INFO map to FALSE. This is a new quality evaluation, not a reuse of
  the earlier three-class Qwen/VeriSci quality claim. No tuning on these results.
- Pin Gigatoken and tokenizer files. Match the exact segmented token sequence,
  document orientation, TRUE/FALSE choices, and candidate domain for every pair.
  Reject inputs over 8192 tokens rather than truncate.
- Use a full join, so no existence-based early termination is applicable. Both
  engines get precisely the same graph restriction. Deduplication is common to
  both and original binding multiplicity is restored afterward.

## Arms

**Quail:** the actual candidate bridge and upstream Quail executor, including
its grouped attention, specialized readout and query-managed KV.

**Tuned candidate-restricted vLLM:** upstream `RequestExecution`,
`RequestModelExecution`, `run_join_grouped` and `VLLMEngine` settings. The public
vLLM planner rejects Apply although its runtime already accepts pair inputs.
The reference therefore lowers the same one-join plan to RequestExecution with
the same Foreign pair port. It keeps Quail's chosen anchor, uses anchor-major
request order, enables automatic prefix caching and preserves upstream batch,
sequence and memory limits. A small engine subclass pins model/tokenizer
revisions and sends exact token IDs instead of retokenizing concatenated text.
This is an explicit baseline adaptation, not an unmodified stock-planner run.
The CPU preflight runs the actual upstream request runtime with a recording
decision oracle and verifies every prompt and returned pair.

## Measurement and evaluation

Use separate processes per arm to avoid concurrent model residency. Keep the GPU
exclusive. Run three process repetitions in alternating order, and within each
process retain the cold model-boot execution followed by three measured queries.
Every query starts with empty KV state while model/kernel preparation may remain
warm. Prefix reuse *within* a query stays enabled; no completed-answer cache is
used. Preserve failed workers rather than overwriting or dropping them.

Freeze/tokenize inputs and download/hash model files outside inference timing.
Record input/plan preparation separately. Time `execute_query`, result collection
and original-binding restoration with CUDA synchronization at both boundaries.
Retain the first execution with boot cost separately; do not silently omit it.
Preserve upstream per-node metrics, fresh/cached tokens and all per-pair Boolean
decisions. Verify that every candidate is answered exactly once. Upstream wall
reports may be rounded; use the outer high-resolution timer for comparisons.
PyTorch allocator metrics are not comparable to total device memory used by
vLLM's worker processes; do not claim a memory win from that field.

Report all nine measured query times per arm and process-level medians, cold
boot times, per-node cost breakdown, fresh-token counts, pairwise decision
agreement and separate binary confusion/precision/recall/F1 for each backend.
Report disagreement and failures explicitly. Do not infer numerical equivalence
from matching token inputs or hide quality differences behind timing ratios.
This small development case supplies no universal superiority or novelty claim.

The architectural question is which expensive costs remain after this strong
reference, and whether a useful graph dependency removes them. A 2x target
requires at least half of baseline elapsed time to be removable even under an
optimistic zero-cost replacement. Measure that opportunity before implementing
another optimizer. Quail-provided gains belong to Quail.

### Follow-up profiling boundary

The frozen worker records elapsed time and upstream metrics; it does not yet
capture the CPU/GPU traces needed to attribute idle time. Keep its timing runs
unchanged. A separately frozen instrumentation run must preserve all candidate
decisions and report its overhead relative to the uninstrumented reference.
The [prepared profiling bundle](../results/quail-profile-preflight-v1/FINDINGS.md)
now provides capture hooks and the original package version, with passing CPU
preflight and trace-analysis tests. Its CUDA APIs and worker RPCs remain
unvalidated; use its separate protocol after completing the unprofiled workers.

The pinned upstream experiments provide concrete instrumentation to adapt:
[`vllm_join_profile_worker.py`](https://github.com/fsdatalab/quail/blob/41b883b838687cfbf018080f068f3e81bf2f8e64/experiments/vllm_join_profile_worker.py)
captures both the request driver and vLLM worker, including scheduler scopes;
[`profile_quail.py`](https://github.com/fsdatalab/quail/blob/41b883b838687cfbf018080f068f3e81bf2f8e64/experiments/profile_quail.py)
records forward-pass CUDA events, KV accounting and selected profiler windows.
Their entry points reference the authors' Modal applications and volumes; do not
invoke those entry points for this local/approved-host experiment. Their workload
and Cartesian-pair counts also need adaptation to the frozen restricted domain.

Use common query boundaries and the union of GPU kernel/copy intervals, clipping
overlapping streams rather than adding their durations. A driver-only trace
misses vLLM's separate model process. Sampled Quail windows cannot establish
whole-query utilization. GPU idle time alone does not prove scheduler causation:
correlate it with request preparation, scheduling and dependency waits. Retain
startup, graph/export and result-assembly costs separately; this inference-only
reference still cannot establish an end-to-end graph advantage. No such profile
has run on the available Mac, and this note changes no frozen source or result.

## Commands

From the repository with the pinned Quail checkout installed in the active
Python 3.12 environment:

```sh
export PYTHONPATH=packages/query/src
python packages/query/benchmarks/v1/quail_execution_reference.py freeze RUN \
  --inputs /path/to/scifact-reference/inputs.json \
  --truth /path/to/scifact-reference/truth.json
python packages/query/benchmarks/v1/quail_execution_reference.py verify RUN
python packages/query/benchmarks/v1/quail_execution_reference.py preflight RUN \
  --output /tmp/new-preflight.json
```

Freeze downloads tokenizer/configuration metadata only. On an existing approved
H100 SXM machine, the worker downloads/verifies the pinned weights before timing:

```sh
CUDA_VISIBLE_DEVICES=0 python RUN/quail_execution_reference.py worker RUN \
  --arm quail --output RUN/workers/quail-0
CUDA_VISIBLE_DEVICES=0 python RUN/quail_execution_reference.py worker RUN \
  --arm vllm --output RUN/workers/vllm-0
```

For repetition 1 use vLLM then Quail, and for repetition 2 use Quail then vLLM,
with fresh output names. Each worker verifies frozen files, input identity,
per-pair token hashes, model-file hashes and the physical plan. It records a
failure and stops on unsupported hardware or a changed contract. The protocol
does not authorize renting hardware or publishing results.

After all six workers complete, run:

```sh
python RUN/quail_execution_reference.py summarize RUN --output RUN/summary.json
```

The summarizer refuses missing/failed workers, mixed hardware/dependency
identities, incomplete candidate decisions and incorrect trial counts. It
reports all quality metrics and decision disagreements alongside descriptive
timing. It does not promote this diagnostic into an acceptance result.
