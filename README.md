# Orbweaver Query

Exact graph scoring for candidate pairs selected by your query, running locally
on an Apple Silicon Mac with Python and NumPy. Compose path and structural scores,
filters and graph expansions, or feed in bindings from Neo4j.

**Development preview: `1.0.0.dev1`.** The original competitive 1.0 goals remain
open. Cypher execution belongs to Neo4j; this package supplies a Python integration.
It does not implement GQL or generate Cypher from natural language.

## Start with a useful graph

The [movie walkthrough](packages/query/examples/README.md) finds related films
through shared cast and writes a local, inspectable HTML report. It verifies the
answers against native Cypher and shows which work the composed plan shares.

The [bring-your-own-graph guide](packages/query/BRING_YOUR_OWN_GRAPH.md) includes a
runnable CSV recipe, Neo4j mapping, resource limits and snapshot refresh behavior.
Start with a conventional structural score; add a learned model only after
validating it for your graph and task.

## Run the NumPy-only trained example

```sh
python3 -m venv .venv-query
source .venv-query/bin/activate
python -m pip install ./packages/query
python -m orbweaver_query.demo
```

The first run downloads a checksum-pinned public WordNet-derived dataset.
The core runtime needs no API key or remote inference service. The bundled model
is specific to its graph; its scores are rankings, not calibrated probabilities.

## Evidence and limits

- [Package/API guide](packages/query/README.md)
- [Performance, including adverse results](packages/query/PERFORMANCE.md)
- [Mac benchmark and complete results](packages/query/benchmarks/results/mac-installed-v1/FINDINGS.md)
- [Semantics](packages/query/SEMANTICS.md) and [model card](packages/query/MODEL_CARD.md)
- [Current release audit](packages/query/RELEASE_AUDIT.md)
- [Movie demo, integration checks and end-to-end preflight](packages/query/benchmarks/results/launch-preview-v2/FINDINGS.md)
- [Complete end-to-end movie costs](packages/query/benchmarks/results/movie-workflow-v2/FINDINGS.md)
- [Contributing](packages/query/CONTRIBUTING.md) and [data handling](packages/query/SECURITY.md)

The installed-wheel benchmark observed a 2.59× geometric ratio against strong
on-demand controls on 24 fixed conditions. It ran under normal mixed use on one
M5 Max; five conditions regressed over 10%, and warm lookup won throughout.
These are descriptive development measurements, not an isolated-performance
certification or a universal speedup. All 648 workers pass answer checks.
Composed/native performance gaps remain open; no Quail throughput-parity claim
is supported. Historical favorable, failed and superseded evidence is retained.

In the complete 63-client movie workflow, the plan loses two of three request
comparisons against the strongest on-demand control; native Cypher has lower
median first-use cost throughout. The requested quiet window remained contended.
The report retains all arms, samples, process ranges and export/setup costs.

Apache-2.0 for the runtime; [third-party notices](packages/query/src/orbweaver_query/assets/THIRD_PARTY_NOTICES.md)
apply separately to data/model artifacts.
