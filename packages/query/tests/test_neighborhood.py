"""Structural backends must match independently constructed topology and pair queries."""

import json

import numpy as np
import pytest
from test_execution import fixture

from orbweaver_query import (
    BindingCache,
    GraphSnapshot,
    Limits,
    LinkQuery,
    NeighborhoodModel,
    ResourceLimitError,
    Session,
    score_bindings,
)


@pytest.mark.parametrize("seed", range(6))
def test_full_and_selected_features_match_independent_neighbor_sets(seed):
    edges, graph, _ = fixture(seed, n=20)
    adjacency = [set() for _ in graph.node_ids]
    for a, _, b in edges:
        adjacency[int(a)].add(int(b))
        adjacency[int(b)].add(int(a))
    for metric in NeighborhoodModel.metrics:
        model = NeighborhoodModel(relations=graph.relations, metric=metric)
        session = Session(graph, model)
        rows = session.run([LinkQuery(f"n{h}", "r0") for h in range(20)]).rows
        for head, row in enumerate(rows):
            expected = {}
            for target in range(20):
                if head == target or target in adjacency[head]:
                    continue
                common = sorted(adjacency[head] & adjacency[target])
                if metric == "common_neighbors":
                    value = len(common)
                elif metric == "adamic_adar":
                    value = sum(1 / np.log(len(adjacency[n])) for n in common)
                else:
                    value = sum(1 / len(adjacency[n]) for n in common)
                expected[f"n{target}"] = value
            assert set(row.candidate_ids) == set(expected)
            np.testing.assert_allclose(
                row.scores, [expected[k] for k in row.candidate_ids], atol=1e-14
            )
            features = model.expand_targets(graph, head, (2, 5, 11), Limits())
            selected = model.score(features, 0)
            for target, value in zip(features.candidates, selected):
                assert value == row.score_for(f"n{target}")
        assert row.support == "all_nonself_nonadjacent_nodes"
        assert row.score_kind == "structural_link_score"
        assert session.run([LinkQuery("n0", "r0")]).profile.neighbor_visits > 0


def test_disconnected_zero_scores_are_distinct_from_unsupported_and_null():
    graph = GraphSnapshot([[0, 0, 1]], node_ids=("a", "b", "c"), relations=("r",))
    model = NeighborhoodModel(relations=graph.relations)
    session, cache = Session(graph, model), BindingCache()
    rows = [{"head": "a", "relation": "r", "target": t} for t in ("c", "b", None, "c")]
    result = score_bindings(session, rows, cache=cache)
    assert [r.status for r in result.rows] == ["scored", "unsupported", "null_input", "scored"]
    assert [r.score for r in result.rows] == [0, None, None, 0]
    assert score_bindings(session, rows, cache=cache).to_records() == result.to_records()
    assert cache.info().hits == 2
    other = Session(graph, NeighborhoodModel(relations=graph.relations, metric="adamic_adar"))
    assert other.explain()["feature_contract"] == session.explain()["feature_contract"]
    assert other.model.model_id != model.model_id


def test_artifact_identity_and_validation(tmp_path):
    model = NeighborhoodModel(relations=("r", "s"))
    path = tmp_path / "model.json"
    model.save(path)
    assert NeighborhoodModel.load(path).model_id == model.model_id
    data = json.loads(path.read_text())
    data["metric"] = "common_neighbors"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="identity"):
        NeighborhoodModel.load(path)
    for metric in ("unknown", None):
        with pytest.raises(ValueError):
            NeighborhoodModel(relations=("r",), metric=metric)


def test_resource_limits_are_exact_failures():
    _, graph, _ = fixture(12, n=30)
    model = NeighborhoodModel(relations=graph.relations)
    with pytest.raises(ResourceLimitError, match="max_expansion_states"):
        model.expand(graph, 0, Limits(max_expansion_states=1))
    with pytest.raises(ResourceLimitError, match="max_neighbor_visits"):
        model.expand(graph, 0, Limits(max_neighbor_visits=1))
    with pytest.raises(ResourceLimitError, match="max_neighbor_visits"):
        model.expand_targets(graph, 0, tuple(range(30)), Limits(max_neighbor_visits=1))
    for targets in ((True,), (30,), (-1,)):
        with pytest.raises(ValueError, match="Target index"):
            model.expand_targets(graph, 0, targets, Limits())


def test_streaming_fallback_agrees_and_empty_domain_requires_no_expansion():
    _, graph, _ = fixture(12, n=30)
    for metric in NeighborhoodModel.metrics:
        model = NeighborhoodModel(relations=graph.relations, metric=metric)
        fast = model.expand(graph, 0, Limits())
        streaming = model.expand(graph, 0, Limits(max_expansion_states=30))
        np.testing.assert_array_equal(streaming.values, fast.values)
        assert streaming.peak_states <= 30 < fast.peak_states
        with pytest.raises(ValueError):
            streaming.values.setflags(write=True)
    graph = GraphSnapshot([[0, 0, 1], [0, 0, 2]], node_ids=("a", "b", "c"), relations=("r",))
    empty = NeighborhoodModel(relations=graph.relations).expand(
        graph, 0, Limits(max_neighbor_visits=1)
    )
    assert len(empty.candidates) == empty.neighbor_visits == 0


def test_many_target_preparation_can_choose_full_work_without_changing_evidence():
    graph = GraphSnapshot(
        [[0, 0, i] for i in range(1, 100)], node_ids=[str(i) for i in range(100)], relations=("r",)
    )
    model = NeighborhoodModel(relations=graph.relations)
    targets = tuple(range(2, 80))
    selected = model.expand_targets(graph, 1, targets, Limits())
    # One traversal through the hub replaces 78 separate neighbor intersections.
    assert selected.neighbor_visits == 99
    full = model.expand(graph, 1, Limits())
    np.testing.assert_array_equal(selected.values, full.values[: len(targets)])
    # A smaller state budget cannot use the full kernel, but exact intersections
    # still fit. Resource limits apply to work actually chosen, not a hypothetical plan.
    constrained = model.expand_targets(graph, 1, targets, Limits(max_expansion_states=80))
    assert constrained.neighbor_visits == 2 * len(targets)
    np.testing.assert_array_equal(selected.values, constrained.values)
