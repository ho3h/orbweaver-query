# Graph inference that starts with the query's candidate pairs

Orbweaver Query is a small Python library for scoring graph pairs locally on a
Mac. A Cypher query often already knows which endpoints matter. The path backend
uses those bindings to avoid building scores and terminal features for unrelated
endpoints, while preserving the complete intermediate evidence used by its model.

The useful distinction is between doing less inference work and looking up an
answer already computed. Both matter; they need different controls. The
[Mac demonstration](PERFORMANCE.md) compares exact target-aware execution with
full expansion, bounded feature/score caches and guarded controls, and separately
shows the wins from warm pair caches and precomputation. Every returned row and
score is checked. Loading, setup, serialization and memory have explicit boundaries.
These are reused development workloads, not a general performance guarantee.

From the repository, run the trained example:

```sh
python -m pip install ./packages/query
python -m orbweaver_query.demo
```

It downloads a pinned WordNet-derived graph and runs a bundled 38 KB model with
Python and NumPy. No remote inference service or GPU is involved. The model is
small and limited: mean recall@16 is 28.55% on reused development splits, with
35.30% candidate coverage. It supplies rankings for its own graph, not an
arbitrary database. The [model card](MODEL_CARD.md) contains the full limitations.

The library also exposes conventional common-neighbor, Adamic–Adar and resource
allocation scores. Python plans compose scores, filters and typed graph
expansions, preserve row duplicates and nulls, and record model/snapshot identities.
A read-only Neo4j adapter supplies candidate rows from parameterized Cypher.
The [README](README.md) has runnable local examples and the integration pattern.
It does not implement GQL, add inference syntax to Cypher, or translate natural
language into queries.

The inspiration came from [Quail](https://fsdatalab.github.io/blog/introducing-quail/),
which coordinates AI-SQL execution with transformer inference. Its authors compare
against tuned vLLM with intermediate prefix caching enabled; they are not simply
beating a final-answer cache. Our backend, task and hardware differ, so our speedup
ratios cannot establish superiority over Quail. An optional bridge has CPU
correctness checks, but no CUDA performance result and no role in the Mac release.

The evidence also limits the broader story. Strong structural methods remain
competitive with learned models. Automatic composed execution is still slower
than the strongest manual pipeline in the retained study. Warm lookup is faster
when the same answers recur. Exporting a graph can dominate a first database
request. The [performance page](PERFORMANCE.md) presents these alongside favorable
cases; the [full inventory](EVIDENCE.md) retains failed and superseded campaigns.

This is a `1.0.0.dev1` preview being prepared for public use. Its contribution is
an inspectable integration of exact graph scoring with bound query rows, supported
by reproducible evidence. A new general inference algorithm, broad database
advantage and competitive 1.0 completion remain unproven.
