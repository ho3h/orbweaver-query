# GDS and structural prediction: development checkpoint

Follow-up: the [extended-time retry completed](../gds-retry-development-v1/FINDINGS.md)
with 32.99% friendship recall@16, leaving the strongest development selection
unchanged. The original attempt and historical checkpoint below are retained.

Eleven native GDS experiments completed, with exhaustive candidate coverage in
every completed run. One larger training attempt terminated under the 900-second
transaction ceiling and is retained, including its frozen source, error and log.
The unchanged configuration will be retried with a longer time allowance. Final
confirmation labels remain sealed and have not been evaluated.

## Observed quality

Expected recall@16 per held-out positive, with uniform score ties and unsupported
positives counted as misses. These are reused development observations, not
independent confirmation. Selection among these results is exploratory.

| Model/configuration | Collaboration | Friendship | Communication |
|---|---:|---:|---:|
| Path model | 78.26% | 48.44% | **46.63%** |
| Common neighbors | 79.37% | 51.82% | 43.51% |
| Adamic–Adar | 79.61% | 55.11% | 45.67% |
| Resource allocation | **81.05%** | **56.44%** | 44.23% |
| GDS FastRP64 | 64.86% | 48.00% | 37.98% |
| GDS FastRP256 | 68.15% | 26.37% | 26.61% |
| GDS FastRP256 + degree/cosine | 65.29% | 25.11% | 28.82% |
| GDS rich features + 16 negatives | 74.82% | Terminated; retry pending | 37.04% |
| Positive query count | 46 | 225 | 208 |

All configurations use the same outer-training evidence and candidate domain.
There are 64 query sources per graph, sampled before fitting or inspecting labels.
Every development positive incident to those sources is evaluated. The path
model supports 89.13% of collaboration positives and 100% of the other two sets;
its unsupported collaboration positives stay in the denominator. Structural
scores and all completed GDS runs cover 100%. Zero GDS/structural scores are
valid predictions, not unsupported results.

The important development finding is model diversity: the path model does not
dominate simple methods. Resource allocation is strongest on collaboration and
friendship; the path model is strongest on communication. The production engine
now supports all four choices. Its structural scores were independently checked
against these SciPy matrices: 1,962,927 eligible pair scores, maximum absolute
error zero. See the [backend verification](../v1-development/backend-verification-v1/README.md).

## Comparison boundary

Native GDS 2026.09.0 runs on Neo4j Community 2026.09.0 and Java 21. The native
pipeline selects logistic regression or random forest by internal three-fold
AUCPR. The four external configurations change FastRP dimension, feature inputs
and negative ratio, while retaining the classifier choices and random seed.
The larger grid uses an 8 GiB heap ceiling and one training/prediction thread.
Neither that ceiling nor occasional process snapshots measure peak memory.

Outer train/development/confirmation roles are 80/10/10, assigned to canonical
unordered pairs. Reverse directions cannot leak across roles. Email is evaluated
as any communication, not edge direction. Models see the same outer information,
but the native GDS and explicit-path internal fitting examples and algorithms
are different. Four external choices per side do not imply identical fitting
budgets: GDS also selects between its two classifiers internally.

The current GDS prediction timing includes streaming every candidate score over
Bolt and converting native IDs. It is not comparable to an in-process kernel
time or a top-16 response. The raw logs preserve these diagnostic stage times;
no GDS latency or memory superiority claim is supported here. A matched returned-
result boundary, repeats and the supported four-thread setting remain required.

The small positive counts, reused development selection, one unresolved native
configuration and absent confirmation prevent closing the 1.0 quality gate. In
particular, the pending configuration must not be treated as a zero-quality
result or silently excluded from the final selection.

## Reproduction and retained evidence

The four run directories contain the exact source, protocols, inputs, models,
score matrices, native training details, per-positive outcomes, logs and failed
attempt. `summary.json` records all available configurations and explicitly lists
the failure. `ARCHIVE.json` checksums the experiment payload. It was verified
and restored into a fresh directory without executing another training run.

From the repository root:

```sh
python packages/query/benchmarks/v1/quality_archive.py verify \
  packages/query/benchmarks/results/gds-development-v1
python packages/query/benchmarks/v1/quality_archive.py restore \
  packages/query/benchmarks/results/gds-development-v1 \
  --configuration gds-quality-development-v1 --output /tmp/gds-replay
python /tmp/gds-replay/gds_quality.py execute /tmp/gds-replay \
  --dataset collaboration --neo4j-home /path/to/neo4j-2026.09.0 \
  --java /path/to/java-21 --gds-jar /path/to/gds-2026.09.0.jar
```

Install the optional training and Neo4j dependencies for execution. The frozen
worker starts an isolated loopback database and removes it afterward. Replaying
uses development labels only. The confirmation files are hashed/copied as opaque
bytes; the evaluator and verifier never load their arrays.

The broader [protocol](../../v1/GDS_COMPARISON_PROTOCOL.md) records the resource
retry, and the [1.0 acceptance contract](../../v1/ACCEPTANCE.md) remains open.
This work implements conventional prediction methods and query optimizations;
the graph-specific case must rest on matched execution evidence, not a claim to
invent resource allocation, path features, caching or filter ordering.

Sources: [SNAP collaboration](https://snap.stanford.edu/data/ca-GrQc.html),
[SNAP friendship](https://snap.stanford.edu/data/ego-Facebook.html),
[SNAP email](https://snap.stanford.edu/data/email-Eu-core.html),
[native GDS prediction](https://neo4j.com/docs/graph-data-science/current/machine-learning/linkprediction-pipelines/predict/).
