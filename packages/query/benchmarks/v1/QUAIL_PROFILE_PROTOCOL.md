# Separate CPU/GPU profiling of the frozen execution reference

This harness prepares an instrumented follow-up to the unchanged 339-pair
Quail/vLLM reference. It implements no optimizer and cannot establish an
Orbweaver speedup. No CUDA capture has been validated on the available Mac.

The bundle pins the entire Orbweaver package at the reference's original commit,
including its earlier candidate bridge. This avoids silently substituting the
newer filtered bridge into an already frozen single-join experiment. It also
retains the original reference manifest, prompts, tokenizer and physical plans.
The CPU preflight runs the actual upstream request runtime on two fresh queries, checks every
prompt and pair decision, exercises the profiling wrapper on the second call,
and verifies restoration of the original callable. It does not exercise torch
profiling, a vLLM worker RPC or CUDA execution.

Complete the six uninstrumented workers in QUAIL_EXECUTION_PROTOCOL.md first,
using the bundled package rather than the current development checkout:

```sh
PYTHONPATH=PROFILE/source CUDA_VISIBLE_DEVICES=0 \
  python PROFILE/reference/quail_execution_reference.py worker PROFILE/reference \
  --arm quail --output PROFILE/reference/workers/quail-0
```

Follow the original alternating order for all six workers, with a fresh output
name each time. This preserves the original reference manifest and package.
For each arm, use a separate fresh process, one cold warmup and one instrumented
query. The harness wraps the full graph execution after model boot. Quail captures
local CPU and CUDA activity; vLLM captures driver CPU activity and uses the engine's
profiler API plus worker extension to capture worker activity and annotate the
configured scheduler. No Modal application, volume or rented resource is created.

The completed unprofiled worker supplied with `--baseline` must have the same
original manifest and three measured trials. Profiled environment identity must
match it exactly, and all profiled decisions must match all three unprofiled
trials. Disagreements, missing traces or absent scheduler scopes fail explicitly.
Both successful partial records and errors are retained in a fresh directory.

The instrumented graph interval includes candidate callbacks, prefix-cache reset
where applicable, inference and physical result preparation. It excludes model
boot, graph export, outer result collection/restoration and trace export. Those
remain separately accounted for by the execution reference; this is not an
end-to-end graph profile. The surrounding instrumented worker timer also includes
profiler startup/teardown and vLLM trace flushing, so it is not a benchmark result.

The analyzer clips kernel/copy events to a common wall-clock interval and merges
overlap across GPU streams. Scheduler scope durations are elapsed intervals,
not exclusive CPU utilization. It reports overlap with GPU activity/idle intervals
without attributing causality or deriving a speedup ceiling from idle time alone.
GPU activity fraction is not model FLOP utilization. The retained token/KV metrics
come from the unchanged upstream report. The small low-fanout application remains
an adverse reference, not a demonstrated source of 2x headroom.

```sh
python packages/query/benchmarks/v1/quail_profile_reference.py freeze PROFILE \
  --reference /path/to/restored-quail-reference --repository . \
  --package-revision fcb8aa0ae05f29faf2ae45246d9543fe38c084f5
python PROFILE/quail_profile_reference.py preflight PROFILE --output PROFILE/preflight.json
```

After the unprofiled reference finishes on an existing approved H100 SXM host:

```sh
CUDA_VISIBLE_DEVICES=0 python PROFILE/quail_profile_reference.py worker PROFILE \
  --arm quail --baseline /path/to/unprofiled/workers/quail-0 --output PROFILE/quail-capture
CUDA_VISIBLE_DEVICES=0 python PROFILE/quail_profile_reference.py worker PROFILE \
  --arm vllm --baseline /path/to/unprofiled/workers/vllm-0 --output PROFILE/vllm-capture
python PROFILE/quail_trace_audit.py PROFILE/vllm-capture
```

Review whole-query timings, decisions and profiles together before choosing a
mechanism. Keep all original acceptance gates open. A prepared capture harness
and synthetic trace-analysis checks are not model execution evidence.
