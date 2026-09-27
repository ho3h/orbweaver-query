# Quail candidate bridge: CPU integration evidence

The actual pinned Quail planner and pair runtime accept Neo4j's complete
candidate domain. Both `per_batch` and `barrier` plans preserve **339 distinct
pairs** from **340 citation occurrences**, plus two null bindings and an isolated
document. The captured inference domain contains 300 claims and 283 documents.
For a fixed hash-based Boolean decision oracle, both plans restore **113 ordered
bindings**, exactly matching native Cypher. Source order, duplicates and null
filtering are preserved. A write query is refused before execution.

This is **integration correctness evidence only**. No LLM inference, CUDA timing
or model-quality comparison ran. Byte tokenization is used solely to exercise
planning and request preparation; the displayed token counts and cost estimates
are not model measurements. The oracle bits are not SciFact labels or predictions.
Original Qwen/VeriSci three-class quality results do not apply to the Boolean
Quail prompt. No 1.0 gate closes.

`native-check.json` retains both plans, content/row hashes, dependency versions
and source checksums. The input hash is the existing frozen SciFact development
reference `678d0fb5e2c3f23a6d629bd1f12c222c9eb1c066090697c532cb7b6db9d2c8a2`.
Quail source is the clean commit
`41b883b838687cfbf018080f068f3e81bf2f8e64`. Runtime: Python 3.12.13,
PyArrow 25.0.1, Neo4j driver 6.3.1, local Neo4j Community 5.26.0.
The check creates and removes its own disposable database.

Validation alongside the native check:

- Core source suite: **199 passed, 5 optional skips**.
- Isolated Python 3.12 / actual Quail bridge suite: **22 passed, 1 strict expected
  failure**. It verifies both planner anchor choices, physical graph serialization,
  subset/reordered/noncontiguous row IDs, empty domains, the actual partner-list
  restriction and actual Quail result projection with supplied Boolean decisions.
- Pinned Ruff 0.16.9 and whitespace checks pass.

The expected failure is an upstream diagnostic, not an ignored bridge failure.
Quail's Foreign runtime produces correct batch partner maps for a right-side
survivor stream but transposes its `(l, r)` pairs in the final stored table.
The current bridge has scans on both sides and no upstream survivor stream.
Keep the reproducer and resolve this before adding such streaming composition.
No upstream source was modified or external issue filed.

The captured planner estimates a full 84,900-row cross product although the
Foreign output contains 339 pairs. That is evidence that this callback's graph
cardinality is absent from the estimate, not evidence that Quail evaluates the
cross product. The pair restriction checks demonstrate the opposite. Whether
better graph statistics change a CUDA plan or elapsed time remains unmeasured.

This result supports composing graph selection with the existing inference
engine. It does not establish a new execution contribution. The next experiment
must profile actual inference against the same candidate-restricted backend and
identify additional graph-dependent work that can be removed. Hand-managed use
of the same primitive is an automation-overhead control. The mostly degree-one
SciFact domain should remain an adverse/correctness case, not be inflated into a
high-reuse performance demonstration.

See [bridge usage and reproduction](../../../QUAIL_BRIDGE.md) and the
[architectural decision](../../v1/EXECUTION_THESIS.md).
