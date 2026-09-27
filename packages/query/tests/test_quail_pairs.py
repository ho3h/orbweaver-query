"""Candidate semantics independent of the optional Quail installation."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from orbweaver_query.model import ResourceLimitError
from orbweaver_query.quail import QuailPairQuery, QuailPairs


def binding(head="c1", target="d1", **payload):
    return dict(head=head, target=target, head_text=f"claim {head}",
                target_text=f"document {target}", **payload)


def test_ordered_bag_nulls_identity_and_isolation():
    rows = [binding(ordinal=0, payload=[1]), binding("c2", "d2", ordinal=1),
            binding(ordinal=2), {**binding(ordinal=3), "target_text": None}]
    original = deepcopy(rows)
    candidates = QuailPairs(iter(rows))
    assert candidates.candidate_pairs == (("c1", "d1"), ("c2", "d2"))
    assert candidates.describe() == dict(identity=candidates.identity, input_bindings=4,
        candidate_pairs=2, null_bindings=1, left_documents=2, right_documents=2,
        text_bytes=38)
    rows[0]["payload"].append(2)
    result = candidates.restore([("c1", "d1")])
    assert result == (original[0], original[2])
    result[0]["payload"].append(3)
    assert candidates.restore([("c1", "d1")])[0] == original[0]
    assert QuailPairs(rows).identity == candidates.identity  # Payload is not model input.
    assert QuailPairs(reversed(original)).identity != candidates.identity
    changed = deepcopy(original)
    changed[1]["head_text"] = "changed input"
    assert QuailPairs(changed).identity != candidates.identity
    # Backend result ordering never replaces the source binding order.
    assert candidates.restore(reversed(candidates.candidate_pairs)) == tuple(original[:3])


@pytest.mark.parametrize("change", [dict(head=""), dict(target=1), dict(head_text=[]),
                                    dict(target_text=False)])
def test_invalid_inputs(change):
    with pytest.raises(ValueError):
        QuailPairs([{**binding(), **change}])


def test_conflicting_content_and_missing_fields():
    with pytest.raises(ValueError, match="Conflicting"):
        QuailPairs([binding(), {**binding(), "head_text": "another claim"}])
    with pytest.raises(ValueError, match="must supply"):
        QuailPairs([{"head": "c1"}])
    # One ID may play two distinct document roles.
    assert len(QuailPairs([binding("same", "same")]).candidate_pairs) == 1


@pytest.mark.parametrize("positive", [[("c1", "other")], [("c1", "d1")]*2,
                                     [("c1",)], [["c1", None]]])
def test_invalid_backend_pairs(positive):
    with pytest.raises(ValueError):
        QuailPairs([binding()]).restore(positive)


@pytest.mark.parametrize("limits", [dict(max_bindings=0), dict(max_documents=1),
                                    dict(max_text_bytes=1)])
def test_resource_limits_close_the_source(limits):
    closed = []

    def source():
        try:
            yield binding()
        finally:
            closed.append(True)

    with pytest.raises(ResourceLimitError):
        QuailPairs(source(), **limits)
    assert closed == [True]
    with pytest.raises(ValueError):
        QuailPairs([], max_bindings=True)


def test_empty_query_and_template_contract_without_quail():
    candidates = QuailPairs([{**binding(), "head": None}])
    bound = candidates.bind(None, "Does {1} support {0}?")
    assert bound.collect() == ()
    assert bound.run().backend_result is None
    for predicate in ("", "{0}", "{0} {0} {1}", "{0!r} {1}", "{x} {1}"):
        with pytest.raises(ValueError):
            candidates.bind(None, predicate)
    with pytest.raises(ValueError, match="namespace"):
        candidates.bind(None, "{0} {1}", namespace="not-an-identifier")
    with pytest.raises(ValueError, match="kind"):
        candidates.bind(None, "{0} {1}", kind="anything")


def test_from_neo4j_forwards_query_and_limits():
    calls = []

    def iterate(cypher, parameters):
        calls.append((cypher, parameters))
        yield binding()

    source = SimpleNamespace(iter_candidates=iterate)
    assert QuailPairs.from_neo4j(source, "query", {"id": "c1"}).candidate_pairs
    assert calls == [("query", {"id": "c1"})]
    with pytest.raises(ResourceLimitError):
        QuailPairs.from_neo4j(source, "query", max_bindings=0)


def test_query_rejects_unexpected_result_schema():
    query = SimpleNamespace(run=lambda: SimpleNamespace(
        collect=lambda: SimpleNamespace(column_names=["wrong"])))
    with pytest.raises(ValueError, match="schema"):
        QuailPairQuery(QuailPairs([binding()]), query).run()


@pytest.mark.parametrize("side", ["head_predicate", "target_predicate"])
def test_document_predicate_contract_validates_before_session_mutation(side):
    candidates = QuailPairs([])
    # Empty input still validates the complete plan and invokes no optional dependency.
    assert candidates.bind(None, "{0} {1}", **{side: "Eligible: {0}"}).collect() == ()
    for invalid in ("", "{1}", "{0} {0}", "{0!r}", "{0:10}", 1):
        with pytest.raises(ValueError, match=side):
            candidates.bind(None, "{0} {1}", **{side: invalid})
    with pytest.raises(ValueError, match="streamed-pair"):
        candidates.bind(None, "{0} {1}", kind="per_batch", **{side: "Eligible: {0}"})
