# Document filters now control graph candidate selection

The optional bridge now composes **semantic document filters → captured graph
candidate selection → semantic pair filtering** using Quail's existing operators.
Either or both document roles can filter. The actual Quail dependency runner,
Foreign callback, physical output conversion and final projection are exercised;
fixed Boolean decisions replace only model operators. All six conditions on the
complete SciFact candidate domain agree with independent native Cypher.

This is CPU correctness evidence, not model quality, CUDA execution, KV retention,
early termination or elapsed-time evidence. Oracle decisions are hash assignments,
not SciFact labels or classifier predictions. Byte tokenization exercises wiring;
displayed planner token counts/costs are not valid inference measurements.

| Active document filters | Unique document oracle visits | Pair oracle visits | Output bindings |
|---|---:|---:|---:|
| Head | 300 | 223 | 72 |
| Target | 283 | 230 | 75 |
| Both | 583 | 146 | 46 |

The three corresponding all-rejected conditions each produce zero pair visits
and zero outputs. Every visited pair is in the captured graph domain and has
survived the applicable document filters. Each distinct document is visited once
per filter; repeated source bindings preserve their original order and multiplicity.
Null model inputs do not survive. The underlying domain is 339 distinct pairs
from 340 citation occurrences, with two additional null bindings in the fixture.

Reducing the pair count does not establish a speedup: the document filters add
work and may change application quality. Quail already provides these operators;
this is a more capable integration/reference, not a new inference algorithm.
GPU profiling and the original 1.0 acceptance gates remain open.

## Runtime boundary

The pinned Quail Foreign runtime transposes finalized pairs when consuming a
right-side survivor stream. Filtered bridge plans therefore default to a
materialized barrier and reject an explicit `per_batch`. The physical plans
confirm that no filtered producer pins a survivor stream. Existing unfiltered
plans still support both callback kinds. Upstream source is unchanged and its
strict expected-failure reproducer remains visible. This is not a fix for upstream
streaming or evidence that GPU execution works.

The bridge captures graph candidates and text before inference. Filters restrict
that captured adjacency; they do not issue new multi-hop database traversals.
Correlated existence and broader dependent semantic traversal remain unimplemented.
The earlier frozen single-join CUDA reference is unchanged.

## Verification and retention

- Core source suite: **237 passed, 7 optional skips**.
- Isolated actual-Quail suite: **42 passed, 1 strict expected upstream failure**.
- The same 42 checks pass against a newly built, independently installed wheel;
  the import location is checked outside the checkout with pytest's source-path
  setting cleared. Wheel SHA256:
  `d0831a19b3ba1da88bfb31b88a39fa75a0fa763edcbdd17fa553a1846d9dca0c`.
- Twelve added integration conditions exercise head/target/both filtering, both
  planner orientations, reordered/noncontiguous IDs and empty survivor domains.
- Six full-domain native conditions pass on Neo4j Community 2026.09.0, native ARM
  Java 21.0.10+7 and Python 3.12.13. No user database is touched.
- Pinned Ruff and whitespace checks pass. No new cross-platform/CUDA CI claim.

`native-check.json` retains plans, oracle traces, output hashes and runtime/source
identities. `evidence.tar.gz` includes the full source needed for these checks,
the input data, test files, wheel, successful logs and initial harness failures.
The first native check rejected a malformed independent Cypher reference before
any dependent condition ran; its source and error are preserved. The first wheel
import-location assertion did not normalize macOS's `/tmp` alias; the successful
check resolves both paths. Packaging setup notes retain the missing local build
backend and missing pip in the reference environment; isolated building and a
no-dependency target install resolved those environment issues.

The initial archive replay completed the six native conditions but failed while
recording source hashes because the frozen harness mixed `/tmp` and `/private/tmp`
paths. Its log is retained in `failures/initial-replay.txt`. The current harness
normalizes those paths. Frozen source remains unchanged: run its command from the
restored package directory as shown below so Python resolves the script path
consistently. `replay-check.json` records the subsequent native replay comparison.

Quail is pinned to clean commit `41b883b838687cfbf018080f068f3e81bf2f8e64`.
The original SciFact development input hash remains
`678d0fb5e2c3f23a6d629bd1f12c222c9eb1c066090697c532cb7b6db9d2c8a2`.
Dataset attribution remains in the [SciFact notices](../scifact-reference-development-v1/DATA_LICENSES.md).
No confirmation inputs are included or opened.

Verify bytes or restore without executing archived source:

```sh
python benchmarks/results/quail-dependent-development-v1/verify.py
python benchmarks/results/quail-dependent-development-v1/verify.py --output /tmp/quail-dependent-evidence
```

To repeat the native check in the pinned optional environment, use the restored
source and a new output path:

```sh
cd /tmp/quail-dependent-evidence/packages/query
PYTHONPATH=src python benchmarks/v1/quail_dependent_check.py \
  --neo4j-home /path/to/neo4j-2026.09.0 --java /path/to/native/java \
  --inputs ../../inputs.json --output /tmp/new-dependent-check.json
```

The archive verifier checks integrity only. The command above independently runs
the native/reference comparison; neither command performs model inference.
