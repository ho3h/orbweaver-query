# Matched execution reference: prepared and CPU-verified

The next inference comparison is now concretely runnable on a supported CUDA
host. It has **not run model inference**. There is no speedup, quality, memory,
headroom or completed-acceptance result in this archive.

The complete frozen domain contains 339 distinct claim/document pairs and 340
binding occurrences. Both inference plans use the same Qwen3-4B FP8 revision,
Boolean prompt, tokenizer, document orientation and restricted pair domain.
The actual tokenizer produces **150,780 requested input tokens**; the largest
prompt is **1,533 tokens**. Nothing is truncated. The earlier three-class model
results do not transfer to this new Boolean support predicate.

The public Quail vLLM planner rejects Apply, but its request executor already
supports pair ports. The reference lowers the existing full join to that
RequestExecution node without expanding the candidate domain. It keeps tuned
vLLM batch/memory settings and prefix caching, pins model/tokenizer revisions,
and submits exact segmented token IDs. This is a disclosed baseline adaptation,
not a stock-planner run or an Orbweaver inference optimization.

The CPU preflight runs Quail's actual Foreign, RequestModelExecution,
run_join_grouped and projection paths with a recording decision oracle. All
339 requests have the same token-hash multiset as the Quail join plan; every
returned decision maps to the correct application pair. It verifies the prefix
cache reset and restores 160 original bindings for the fixed oracle bits.
Those bits are not model predictions and are not evaluated as model quality.

The runner checks exact model-file hashes, device requirements, frozen source,
inputs, prompts and physical plans. It retains cold-boot execution separately
from three measured queries per worker, and refuses overwritten output paths.
The six-worker summarizer rejects missing/failed workers and mixed environments,
reports binary quality and decision disagreement, and never closes a release
gate. Graph export is outside this diagnostic. It cannot establish end-to-end
graph performance or graph-specific novelty.

Validation: **28 optional Quail tests passed, one strict expected upstream
stream-finalization failure** (already documented by the bridge). **199 core
tests passed, six optional skips**. Pinned Ruff and whitespace checks pass.
No CUDA worker or paid resource was launched. A compatible existing H100 SXM host
is still needed; all 1.0 gates remain open.

The initial v1 preparation remains unchanged locally. The archived v2 adds
hardware identity and runtime cache checks before any GPU measurements. Inputs,
prompt hashes and both preflight outcomes are unchanged.

## Verify and restore

```sh
python packages/query/benchmarks/results/quail-execution-preflight-v1/verify.py
python packages/query/benchmarks/results/quail-execution-preflight-v1/verify.py \
  --output /tmp/quail-reference-ready
```

After installing the clean pinned Quail checkout in Python 3.12 and setting
`PYTHONPATH` to this commit's `packages/query/src`:

```sh
python /tmp/quail-reference-ready/quail_execution_reference.py verify /tmp/quail-reference-ready
python /tmp/quail-reference-ready/quail_execution_reference.py preflight /tmp/quail-reference-ready \
  --output /tmp/new-preflight.json
```

The archive includes frozen input/truth, tokenizer files, plans, per-pair prompt
hashes, source/protocol, model-weight checksums and the CPU preflight result.
Its verifier checks every byte without executing the stored benchmark code.
See the [execution protocol](../../v1/QUAIL_EXECUTION_PROTOCOL.md) for CUDA worker
commands, measurement boundaries, quality checks and required repetitions.
