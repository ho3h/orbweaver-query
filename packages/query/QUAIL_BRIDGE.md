# Experimental Neo4j → Quail bridge

The bridge supplies graph-selected candidate pairs to Quail's existing semantic
join, optionally after semantic filters on either document role. It is a step
toward a strong execution reference, not a new inference
engine, an AI-Cypher parser, or evidence of a speedup. Ordinary graph operations
stay in Neo4j. Quail owns model execution.

Tested against Quail commit
`41b883b838687cfbf018080f068f3e81bf2f8e64`, using its real planner,
`Apply(ids="pairs")`, `ForeignRuntime`, partner restriction and projection.
The local checks use byte tokens and fixed Boolean decisions; no CUDA model
forward pass has run. The core package still requires only NumPy and Python 3.11+.

## Use

Install the optional reference in a separate Python 3.12 environment. This
Quail revision requires Python 3.12; its model execution requires a supported
CUDA GPU and backend dependencies.

```sh
python3.12 -m venv .venv-quail
.venv-quail/bin/python -m pip install './packages/query[neo4j]'
.venv-quail/bin/python -m pip install \
  'quail-engine @ git+https://github.com/fsdatalab/quail.git@41b883b838687cfbf018080f068f3e81bf2f8e64'
```

The following uses an application-owned Neo4j `driver` and its Claim/Document
schema. Execution is local to the process with the Quail session; the remote
server's callback deployment is not supported by this bridge.

```python
import quail
from orbweaver_query.neo4j import Neo4jSource
from orbweaver_query.quail import QuailPairs

candidates = QuailPairs.from_neo4j(Neo4jSource(driver), """
    MATCH (c:Claim)-[e:CITES]->(d:Document)
    RETURN c.id AS head, d.id AS target,
           c.text AS head_text, d.text AS target_text, e.id AS citation_id
    ORDER BY head, citation_id, target
""", max_bindings=100_000, max_documents=50_000, max_text_bytes=64*1024*1024)

with quail.Session(quail.EngineConfig(
        model="qwen3-4b-fp8", device="h100-sxm", backend="quail")) as session:
    bound = candidates.bind(session, "Does document {1} support claim {0}?")
    print(bound.query.plan().graph.explain())
    result = bound.run()  # Requires CUDA; not exercised by CPU correctness checks.
    print(result.rows)
    print(result.backend_result.report)
```

The bridge returns an empty result without registering documents or invoking
inference when there are no non-null candidate pairs. In that case `bound.query`
and `result.backend_result` are `None`; inspect `candidates.describe()` first if
using the underlying Quail objects.

Optional document predicates use `{0}` for that role's text. They run on unique
documents before the captured graph's pair callback, so rejected documents have
no downstream pair evaluations:

```python
qualified = candidates.bind(
    session, "Does document {1} support claim {0}?",
    head_predicate="Does this claim concern a medical treatment? {0}",
    target_predicate="Does this abstract report an experiment? {0}",
    namespace="treatment_evidence",
)
print(qualified.query.plan().graph.explain())
```

This composes Quail's existing operators. It adds document evaluations while
reducing the pair domain; a speed or quality benefit has not been measured.
The default callback kind is `barrier` when either document predicate is present
and `per_batch` otherwise. An explicit `per_batch` with document predicates is
rejected because the tested Quail revision has a right-stream finalization defect.
The barrier consumes materialized survivors and does not enter that broken path.

## Contract and scope

- Each binding supplies `head`, `target`, `head_text`, and `target_text`.
  IDs are stable nonempty application strings. Within each side's non-null
  inference domain, one ID must have exactly one text value. The two sides can
  give the same ID different text roles.
- In the pair predicate, `{0}` denotes `head_text` and `{1}` denotes `target_text`,
  each exactly once. Each optional document predicate uses `{0}` exactly once
  for its own role's text. Arbitrary payload fields do not enter any prompt.
- Inference operates on distinct candidate pairs. This assumes a Boolean
  predicate of the fixed document pair, not an independent random draw for each
  duplicate binding. Positive pairs restore the original ordered bag and copied
  payloads. Any null model input has unknown predicate truth and is excluded by
  the semantic WHERE filter. Unknown or duplicate returned pairs raise an error.
- The candidate identity hashes document content and ordered pair bindings.
  It is not a model/prompt cache key or a database-wide snapshot identifier.
  Capture happens in one read transaction with the server's isolation semantics;
  the exported model inputs remain fixed afterward.
- Limits bound input row count, unique role-document count and UTF-8 text bytes.
  They do not bound arbitrary payload sizes, Python overhead or GPU memory.
  Candidate input iterators close on exhaustion, validation errors and limits.
- Bindings use a fresh namespace within a caller-owned local Quail session.
  Supported execution is a full Boolean join over captured candidates, optionally
  preceded by one semantic filter on each document role. Quail's own backend/
  multi-GPU planning restrictions still apply. Graph candidates and document
  contents are captured before inference; this does not perform a new database
  traversal after each result. Correlated existence, multi-hop semantic traversal
  and a new GraphModel remain outside the bridge's current scope.
- The existing SciFact Qwen/VeriSci results use a three-class contract. Their
  predictions and quality numbers do not transfer to this Boolean prompt,
  different Quail model or precision.

## Verification and next experiment

The [native check](benchmarks/v1/quail_bridge_check.py) loads only an owned
disposable Neo4j database. On the complete SciFact candidate domain it checks
339 distinct pairs from 340 citation occurrences, plus null and isolated-node
cases, through both actual Quail pair plans. Fixed hash decisions replay to
exactly the same ordered results as native Cypher. The
[retained result](benchmarks/results/quail-bridge-development-v1/native-check.json)
records source, dependency and input identities. It is correctness evidence.

The optional integration tests additionally exercise both anchor orientations,
noncontiguous/reordered survivors, empty domains, plan serialization and actual
Quail result projection. A strict expected failure records a pinned upstream
defect: when a Foreign pair callback consumes a right-side survivor stream,
finalization transposes the stored `(l, r)` pairs. The live batch partner map is
correct. Unfiltered bridge plans have no upstream survivor stream. Filtered bridge
plans require a barrier that materializes survivors, so neither supported form
exercises that defect. Streaming filter composition must resolve it first. The
test remains visible; the upstream source has not been modified.

The [dependent native check](benchmarks/results/quail-dependent-development-v1/FINDINGS.md)
uses the real Quail dependency runner for document filters → graph candidate
selection → pair filtering, substituting fixed decisions only at model operators.
Six full-domain conditions agree with independent native Cypher; rejected
documents never reach the pair oracle. This verifies execution wiring and result
semantics, not inference quality, GPU retention or timing.

```sh
python -m pytest -q packages/query/tests/test_quail_pairs.py \
  packages/query/tests/test_quail_integration.py
PYTHONPATH=packages/query/src python packages/query/benchmarks/v1/quail_bridge_check.py \
  --neo4j-home /path/to/neo4j --java /path/to/java \
  --inputs /path/to/frozen-scifact/inputs.json --output /tmp/new-bridge-check.json
```

For the native check, install Quail from a clean checkout of the pinned commit;
the command verifies that checkout. Omitting `--inputs` runs a tiny built-in
fixture. Frozen SciFact inputs are restorable from the existing
[SciFact evidence archive](benchmarks/results/scifact-reference-development-v1/FINDINGS.md).

The next decision requires one actual CUDA execution profile with identical
candidate pairs, prompt, model, precision and quality checks across the strong
reference and proposed graph mechanism. The reference gets native graph
filtering, batching, prefix reuse and applicable early termination. Charge
export and setup consistently. Include a hand-managed use of the same pair
interface to measure integration overhead. Candidate restriction itself is
already a Quail capability and cannot be claimed as Orbweaver novelty. No
additional optimizer campaign is justified until that profile identifies
sufficient residual avoidable work.

The [matched execution diagnostic](benchmarks/v1/QUAIL_EXECUTION_PROTOCOL.md)
now provides a frozen candidate-restricted vLLM reference beside the Quail plan.
Its [CPU preflight](benchmarks/results/quail-execution-preflight-v1/FINDINGS.md)
verifies all 339 requests with the real tokenizer and actual request runtime.
CUDA inference, binary model quality and elapsed-time comparisons remain pending.
