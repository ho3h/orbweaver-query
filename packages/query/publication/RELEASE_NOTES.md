# Orbweaver Query development preview

Score graph pairs selected by your query, locally on an Apple Silicon Mac.
The preview includes exact target-aware path scoring, conventional structural
metrics, inspectable Python plans and a read-only Neo4j adapter.

Start with the public movie walkthrough: related films, visible cast evidence,
a shared-preparation plan and an equivalent native Cypher answer. The CSV guide
then shows how to supply your own evidence and candidate pairs.

This is version `1.0.0.dev1`, not a stable 1.0 release. The runtime needs Python
3.11+ and NumPy; Neo4j and training dependencies are optional. The bundled trained
WordNet model is an example for its recorded graph, not an arbitrary-graph model.

Read `packages/query/PERFORMANCE.md` for complete measured scope. The existing
Mac timing campaign observed a 2.59× on-demand ratio under mixed use on fixed
development workloads, with five >10% regressions and warm lookup wins throughout.
It is not an isolated-performance certification, a general speedup, or a direct
Quail comparison. Composed/native competitive gaps remain open.

The complete 63-client movie workflow passes all answer checks. The plan loses
two of three request comparisons to the strongest on-demand control; native
Cypher has lower median first-use cost in all three. Background activity remained
high, so the report makes no isolated-latency claim. Every sample is retained.

Source and wheel/sdist artifacts are available from `ho3h/orbweaver-query`.
The package is not on PyPI; use the source-install instructions or the attached
wheel. The research repository remains private. This repository begins with a
selected snapshot and new history; historical benchmark evidence is retained.
