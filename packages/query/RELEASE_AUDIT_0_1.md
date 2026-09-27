> Historical 0.1 audit. This does not certify the current development package.

# 0.1.0 release-candidate audit

Scope: an independent NumPy execution library, a trained WN18RR example,
read-only Cypher integration through Python, and reproducible evaluation tools.
The candidate is ready for public release within this scope. It does not install
Cypher UDFs, implement ISO GQL, provide a general graph foundation model, or run
an inference service. Publication, repository visibility and merging remain
separate actions.

The [original release requirements](../../docs/QUERY_ENGINE_RELEASE.md) are
addressed below. Measurements are tied to their frozen source snapshots; later
packaging, import-order and documentation fixes do not replace those records.
The final distribution command checks also repeat both benchmark pipelines.

| Requirement | Evidence and result |
| --- | --- |
| Useful query surface | Installed local and live Neo4j examples pass. Parameterized reads compose with scoring, filtering and projection, preserving bags, order, nulls and provenance. `explain` and per-window profiles expose the inference plan and work. [Semantics](SEMANTICS.md) states the database and evidence boundaries. |
| Correct execution | An independent individual-walk oracle checks all candidate support and scores on 12 randomized graphs. Boundary checks cover direction, duplicate/multitype edges, isolated nodes, ties, bounded windows, replacement evidence/models, invalid inputs, artifacts, budgets and transaction cleanup. A [second public graph/schema](benchmarks/results/public-movies-model-v1/FINDINGS.md) checks 3,894 scores. All [1,806 movies-alias corpus queries](benchmarks/results/text2cypher-movies-v2/FINDINGS.md) have matching adapter/direct outcomes under the declared exact/virtual-schema comparison. |
| Measured runtime value | [189 isolated workers](benchmarks/results/standalone-runtime-v1/FINDINGS.md) retain complete output equality, cold and warm measurements, serialization, memory, larger windows and all declared gates. The [36-client Cypher workflow](benchmarks/results/neo4j-workflow-v1/FINDINGS.md) includes actual database queries, transfer and evidence export, plus an independently checked bounded LRU. Failed early campaigns and slower clustered workloads remain visible. |
| Useful model behavior | The bundled model and all controls rebuild from pinned public training data. [Three-seed training and replay](benchmarks/results/model-reproduction-v1/FINDINGS.md) pass all 24 comparisons, with a [separate clean installation](benchmarks/results/model-installed-v1/FINDINGS.md). The [model card](MODEL_CARD.md) reports full-denominator recall, 35.30% support coverage, untrained relation behavior, reused development splits and the limits of these controls. There is no confidence, transfer or state-of-the-art claim. |
| Reliable packaging | Wheel built through sdist, isolated installed tests, current/minimum NumPy, twelve Python/OS combinations, two Neo4j driver lines and real Neo4j 5.26. Numeric artifacts reject executable deserialization and check schema/content identities. The 74 KB wheel has NumPy as its sole runtime dependency, complete Apache text and dataset/model notices. |
| Release material | [README](README.md), [semantics/architecture](SEMANTICS.md), [model card](MODEL_CARD.md), [introductory article](INTRODUCING.md), [changelog](CHANGELOG.md), four evaluation protocols and retained findings. All four documented Python snippets execute using the installed wheel, including the live Cypher/filter/projection example. The trained CLI and both complete benchmark command sequences execute from the distribution. |

## Validation record

The runtime platform matrix and both database driver jobs passed in
[GitHub Actions](https://github.com/ho3h/orbweaver/actions/runs/36252781748):
Ubuntu, macOS and Windows with Python 3.11–3.14; NumPy 1.26.4 separately on
Python 3.11; Neo4j drivers 5.28.0 and 6.x against server 5.26. Full training,
export and independent replay also passed in the
[initial training job](https://github.com/ho3h/orbweaver/actions/runs/36251881500).
That initial workflow failed its separate lint jobs; those findings were fixed
and the succeeding platform run passed lint too. CI now explicitly requires the
model-quality gate in addition to successful replay.

Final local source checks: 51 pass, with the opt-in database check run separately.
Installed-wheel checks: 49 pass, with two optional scientific-training checks and
the opt-in database check skipped in the minimal environment; the latter passes
separately on a newly created Neo4j instance. Full scientific checks run in the
training environment and CI. The installed package import check verifies that
inference does not import SciPy, scikit-learn, MLX, PyTorch or research modules.

Distribution command validation rebuilt 189 runtime workers and 36 real-database
workflow workers from the extracted 0.1.0 sdist, using the installed wheel for
preparation and the frozen release source for execution. Both independent
verifiers pass output parity and all declared gates. These repeats check the
published commands; the introductory article retains the earlier frozen
measurements and does not select faster repeat timings. The source archive
contains the benchmark tools and protocols, excludes local runs and bytecode,
and both archives pass package-metadata checks. A checksum-pinned fresh-data
quickstart and all article/README Python snippets pass from the wheel.

## Claims that the evidence supports

On the recorded interleaved fixture, grouping is 4.22–4.45x faster than a
consecutive one-source cache in the isolated runtime, and about 3.12x faster
including a warm local Cypher query and transfer. A multi-source LRU captures
nearly the same benefit. Exporting the evidence graph costs roughly one second
and dominates a cold first call. Grouping can be slower for clustered inputs.
These are fixed-workload, prepared-snapshot results, not a universal speedup.

The trained example has mean recall@16 of 28.55% on reused development splits.
It cannot reach roughly 65% of held-out targets and cannot predict another
relation between an already adjacent pair. Scores are ranking logits, not
probabilities. The Text2Cypher corpus supplies query conformance workloads;
it does not supply missing-link supervision, nor does this package generate
Cypher from natural language.

Future work can add independently evaluated model backends, other database
adapters and a broader query planner. Those capabilities are not advertised by
this candidate, and their absence does not relax the six tested requirements
for the implemented surface.
