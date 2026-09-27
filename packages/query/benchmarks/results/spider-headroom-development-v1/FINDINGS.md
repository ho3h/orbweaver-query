# Existing transformer application: architectural diagnostic

The existing Qwen3-4B pair-review application has substantially different costs
from the query package's small CPU scorer. This bounded local investigation
completed **45 measurements with no worker exceptions**, but **failed the
predeclared inference-equivalence contract**. It establishes no new algorithm,
Quail performance comparison, model-quality result or release-gate completion.

## What the inputs and timings show

Three existing synthetic application themes supply three original event prompts
and 11 candidate-pair reviews. Selection was frozen without consulting model
outputs or quality labels. All execution controls use the same model, head and
exact input tokens within each shape. The graph-scoped variant changes the
context supplied to the model; it is a separate proposed task, not an equivalent
replacement for the current pair scan.

| Input shape | Rows | Requested tokens | Unlimited reusable prefix tokens | Reused fraction | Scalar median | Prefix-input median | Scalar / prefix-input |
|---|---:|---:|---:|---:|---:|---:|---:|
| Original independent events | 3 | 5,000 | 474 | 9.5% | 5.613 s | 5.470 s | 1.026x |
| Current pair-local review | 11 | 9,710 | 2,374 | 24.4% | 10.322 s | 8.749 s | 1.180x |
| Proposed shared graph context | 11 | 16,876 | 12,229 | 72.5% | 18.230 s | 7.345 s | 2.482x; equivalence failed |

These are descriptive ratios from three repetitions in one process, not
independent-process estimates or confirmed speedups. Prefix retention is an
ordinary MLX KV cache with a 512 MiB numeric LRU budget. It stores no completed
answers. Graph overlap does not imply identical token prefixes: the current
pair-local contexts have much less reuse than the shared-context variant.

All ordinary controls are retained:

| Shape | Scalar | Batch 4 | Batch 8 | Prefix input order | Prefix sorted |
|---|---:|---:|---:|---:|---:|
| Independent events | 5.613 s | 4.834 s | 5.991 s | 5.470 s | 5.124 s |
| Pair-local review | 10.322 s | 10.860 s | 12.426 s | 8.749 s | 9.134 s |
| Shared graph context | 18.230 s | 19.712 s | 19.552 s | 7.345 s | 7.345 s |

The independent-events batch arms actually perform the same single batch. Their
different timings illustrate why these repeated-process samples cannot support
claims about batch-size superiority. No arm selection or tuning follows them.

Scalar model-forward time accounts for approximately 99.7–99.8% of median
execution time. This boundary includes host dispatch and synchronized GPU work;
it does not identify GPU compute versus internal scheduling as the bottleneck.
The six-class head already bypasses the vocabulary projection. Optimizing the
small amount of work outside the forward boundary cannot supply a 2x gain here.
Peak retained KV stays below 512 MiB; allocator peaks, per-phase timings and
every output vector are in the raw records.

## Equivalence and existence results

There are **111 field-level discrepancies across repetitions**, not 111 distinct
input cases. Pair-scan batching changes one ordered APS prediction list in each
replicate for each batch arm. The shared-context prefix arms exceed declared
logit/probability tolerances on eight rows per arm per replicate and also change
some APS ordering. The largest probability difference is **0.08611** (8.61
percentage points). Top classes and unordered APS memberships remain unchanged
on these inputs, but the full declared output contract still fails.

The cause of the prefix numerical differences has not been isolated; do not
attribute it to harmless rounding or loosen the tolerance. The apparent 2.482x
ratio cannot be promoted as an equivalent-inference optimization. All differences
remain in `spider-headroom-development-v5/results.json` and its raw workers.

The offline correlated-existence check finds no singleton `add_link` or
`merge_entities` result in any scoped review. All 11 candidates would be needed;
these fixtures provide no early-termination opportunity under that criterion.
This is not a measurement of model accuracy or calibration coverage.

## Decision

Reject this probe as a 1.0 performance or novelty demonstration. Conventional
prefix reuse offers modest descriptive benefit on the current pair scan. The
larger benefit requires a different context, fails the numerical contract, and
overlaps existing [SubGCache work](https://ojs.aaai.org/index.php/AAAI/article/view/40827).
Do not launch another campaign to tune this cache or manufacture a favorable
input shape. A future backend correctness investigation can address the recorded
discrepancy separately before production use.

The next milestone is the useful application and strong reference described in
the [execution decision](../../v1/EXECUTION_PRIOR_ART.md): native graph selection,
expensive semantic relations, per-root existence and dependent expansion, with
useful positive/negative outcomes and held-out quality evidence. The reference
must combine batching, prefix reuse and early termination. Only a demonstrated
remaining cost attributable to graph/query knowledge justifies new optimizer work.

## Scope, failures and reproduction

Hardware is one Apple M5 Max; model is pinned Qwen3-4B Instruct 2507 in MLX 4-bit,
with the unchanged six-class artifact. This is not Quail's FP8/H100 setup. Model
loading is recorded separately. Graph loading/candidate extraction, updates and
complete database-to-answer latency are excluded. There is no joint batched-prefix
arm and no vLLM/Quail execution. Sources are synthetic application fixtures.

All five capture attempts are retained in `evidence.tar.gz` with their exact
source and file checksums in `ARCHIVE.json`. The first failed
fixture loading; the second recorded invalid token IDs; the third failed warmup
on changed serialized prompt order; a token-only preflight rejected the fourth.
None of those attempts completed a model forward or timing worker. The fifth
preserves event key order and validates every serialized prompt before freezing.
The bundle's `attempts.json` explains these statuses; no failed capture was overwritten.

The 237 archived evidence files pass SHA-256 verification, and the completed
summary replays byte for byte from frozen source and raw outputs. Run, with NumPy
installed:

```sh
python packages/query/benchmarks/results/spider-headroom-development-v1/verify.py
```

Completed input manifest SHA-256:
`1f50a4325b54d8122a20d045a2b16f6ed2aa34eb16dec58a50df2902b5f1d4f6`.
The downloadable base weights are represented by pinned revision and checksums,
not duplicated in this repository. Five targeted tests cover token IDs, scenario
serialization, prefix accounting, bounded retention, and a small real MLX model.
Full source validation: **177 passed, four optional skips**; pinned Ruff passes.
No production runtime change or new installed-wheel claim accompanies this probe.
