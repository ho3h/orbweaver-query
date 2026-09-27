"""Expansion and predicate movement against an independent eager relational oracle."""

from dataclasses import replace

import numpy as np
import pytest
from test_execution import fixture
from test_plan import UnsharedModel, assert_records

from orbweaver_query import (
    BindingCache,
    ExplicitPathModel,
    GraphSnapshot,
    Limits,
    NeighborhoodModel,
    QueryPlan,
    ResourceLimitError,
    Session,
    score_bindings,
)


def expand_reference(graph, rows, operation):
    """Use canonical triples, not packed adjacency or the production executor."""
    edges = graph.triples().tolist()
    result = []
    for row in rows:
        matches = []
        for h, r, t in edges:
            if operation.relation is not None and graph.relations[r] != operation.relation:
                continue
            if operation.direction != "in" and graph.node_ids[h] == row[operation.source]:
                matches.append((t, r, r))
            if operation.direction != "out" and graph.node_ids[t] == row[operation.source]:
                matches.append((h, r + len(graph.relations), r))
        for target, _, relation in sorted(matches):
            value = {**row, operation.target: graph.node_ids[target]}
            if operation.edge_relation is not None:
                value[operation.edge_relation] = graph.relations[relation]
            result.append(value)
        if not matches and operation.optional:
            value = {**row, operation.target: None}
            if operation.edge_relation is not None:
                value[operation.edge_relation] = None
            result.append(value)
    return result


def eager_reference(plan, rows):
    rows = [dict(row) for row in rows]
    for index, stage in enumerate(plan.stages):
        for p in stage.predictions:
            scored = score_bindings(Session(plan.graph, p.model, limits=plan.limits), rows,
                                    head=p.head, relation=p.relation, target=p.target,
                                    execution="full")
            if p.name in dict(stage.thresholds):
                scored = scored.where_score(dict(stage.thresholds)[p.name])
            rows = scored.to_records(prediction_column=p.name)
        if index < len(plan.expansions):
            rows = expand_reference(plan.graph, rows, plan.expansions[index])
    if plan.projection is not None:
        rows = [{c: row[c] for c in plan.projection} for row in rows]
    return rows


@pytest.mark.parametrize("direction", ["out", "in", "both"])
@pytest.mark.parametrize("optional", [False, True])
@pytest.mark.parametrize("relation", [None, "r"])
def test_typed_bag_expansion_matches_triple_oracle(direction, optional, relation):
    graph = GraphSnapshot([[0, 0, 1], [0, 1, 1], [1, 0, 0], [1, 0, 2], [0, 0, 1]],
                          node_ids=("a", "b", "c", "isolated"), relations=("r", "s"))
    plan = QueryPlan(graph, limits=Limits(window_size=2)).expand(
        source="source", target="target", relation=relation, direction=direction,
        edge_relation="type", optional=optional)
    rows = [{"source": s, "ordinal": i} for i, s in enumerate(
        ("a", "b", "a", None, "isolated", "c"))]
    expected = eager_reference(plan, rows)
    for optimize in (True, False):
        actual = plan.run(rows, optimize=optimize)
        assert actual.to_records() == expected
        assert actual.report()["model_calls"] == 0
        assert all(len(b.rows) <= 2 for b in plan.iter_batches(rows, optimize=optimize))
        assert all(s.operator == "expand" for s in actual.steps)


@pytest.mark.parametrize("seed", range(4))
def test_multistage_predicate_movement_preserves_independent_scores_and_order(seed):
    _, graph, path = fixture(seed, n=12, r=2)
    cn = NeighborhoodModel(relations=graph.relations, metric="common_neighbors")
    plan = (QueryPlan(graph, limits=Limits(window_size=7))
            .expand(source="seed", target="one", edge_relation="type", direction="both", optional=True)
            .expand(source="one", target="two", direction="out", optional=True)
            .predict("root", cn, target="seed").where_score("root", 1)
            .predict("middle", cn, relation="type", target="one").where_score("middle", 1)
            .predict("leaf", path, target="two"))
    rows = [{"head": "n0", "relation": "r0", "seed": t, "ordinal": i}
            for i, t in enumerate((*graph.node_ids, "n4", None))]
    moves = plan.explain()["predicate_moves"]
    assert [(m["prediction"], m["from_stage"], m["to_stage"]) for m in moves] == [
        ("root", 2, 0), ("middle", 2, 1)]
    assert plan.explain(optimize=False)["predicate_moves"] == []
    expected = eager_reference(plan, rows)
    for optimize in (True, False):
        for fused in (True, False):
            assert_records(plan.run(rows, optimize=optimize, fused=fused).to_records(), expected)
    projected = plan.project("ordinal", "seed", "two", "root", "middle", "leaf")
    assert_records(projected.run(rows).to_records(), eager_reference(projected, rows))
    assert len(plan.project().run(rows).rows) == len(expected)


def branch_fixture():
    graph = GraphSnapshot([[0, 0, 1], [1, 0, 2], [2, 0, 3], [2, 0, 4], [5, 0, 6], [5, 0, 7]],
                          node_ids=tuple("abcdefgh"), relations=("r",))
    model = NeighborhoodModel(relations=graph.relations, metric="common_neighbors")
    plan = (QueryPlan(graph).expand(source="seed", target="next", direction="both")
            .predict("keep", model, target="seed").where_score("keep", 1)
            .predict("after", model, target="next"))
    rows = [{"head": "a", "relation": "r", "seed": s} for s in ("c", "f", "c", None)]
    return graph, model, plan, rows


def test_filter_pushdown_eliminates_traversals_without_cached_answers():
    _, _, plan, rows = branch_fixture()
    early, late = plan.run(rows), plan.run(rows, optimize=False)
    assert_records(early.to_records(), eager_reference(plan, rows))
    assert_records(early.to_records(), late.to_records())
    assert early.rows
    assert early.report()["edge_visits"] < late.report()["edge_visits"]
    assert [s.input_rows for s in early.steps if s.operator == "expand"] == [2]
    assert [s.input_rows for s in late.steps if s.operator == "expand"] == [4]


def test_root_validation_precedes_model_work_even_for_rejected_branches():
    graph, model, _, rows = branch_fixture()
    tracked = UnsharedModel(model, "tracked")
    plan = (QueryPlan(graph).predict("reject", tracked, target="seed").where_score("reject", 1e9)
            .expand(source="seed", target="next")
            .predict("later", model, head="other", target="next"))
    good = {**rows[0], "other": "a"}
    for bad in ({**good, "other": "unknown"}, {**good, "seed": 42},
                {**good, "next": "c"}, {**good, "reject": None}, {}, 1):
        cache = BindingCache()
        with pytest.raises(ValueError):
            plan.run([good, bad], cache=cache)
        assert tracked.calls == cache.info().entries == cache.info().misses == 0


def test_pipeline_cache_atomicity_identity_and_late_failure():
    graph, model, plan, rows = branch_fixture()
    cache = BindingCache()
    first = plan.run(rows, cache=cache)
    again = plan.run(rows, cache=cache)
    assert_records(first.to_records(), again.to_records())
    assert again.report()["model_calls"] == again.report()["expansions"] == 0
    other_graph = GraphSnapshot([[0, 0, 1], [1, 0, 2]], node_ids=graph.node_ids, relations=graph.relations)
    changed = replace(plan, stages=tuple(replace(s, graph=other_graph) for s in plan.stages))
    assert_records(changed.run(rows, cache=cache).to_records(), changed.run(rows).to_records())
    assert changed.plan_id != plan.plan_id

    class Failure(UnsharedModel):
        def score(self, features, relation):
            raise ValueError("deliberate downstream failure")

    failure = (QueryPlan(graph).predict("before", model, target="seed")
               .expand(source="seed", target="next")
               .predict("failed", Failure(model, "failing"), target="next"))
    cache = BindingCache()
    with pytest.raises(ValueError, match="downstream"):
        failure.run(rows, cache=cache)
    assert cache.info().entries == 0


def test_bounded_stages_fail_explicitly_and_never_commit_partial_scores():
    graph, model, _, rows = branch_fixture()
    for limits, message in [(Limits(max_intermediate_rows=1), "max_intermediate_rows"),
                            (Limits(max_neighbor_visits=1), "max_neighbor_visits"),
                            (Limits(max_type_visits=1), "max_type_visits")]:
        plan = (QueryPlan(graph, limits=limits).predict("before", model, target="seed")
                .expand(source="seed", target="next", direction="both"))
        cache = BindingCache()
        with pytest.raises(ResourceLimitError, match=message):
            plan.run(rows[:1], cache=cache)
        assert cache.info().entries == 0


def test_invalid_dependencies_and_terminal_projection():
    graph, model, plan, _ = branch_fixture()
    for make in (
        lambda: plan.expand(source="next", target="next"),
        lambda: plan.expand(source="keep", target="child"),
        lambda: plan.expand(source="next", target="head"),
        lambda: plan.expand(source="next", target="child", relation="unknown"),
        lambda: plan.expand(source="next", target="child", direction="sideways"),
        lambda: plan.expand(source="next", target="child", optional=1),
        lambda: plan.predict("keep", model),
        lambda: plan.predict("new", model, target="keep"),
        lambda: plan.project("keep").expand(source="next", target="child"),
        lambda: QueryPlan(graph).project("head").expand(source="head", target="next"),
        lambda: plan.project("keep", "keep"),
    ):
        with pytest.raises(ValueError):
            make()
    for kwargs in ({"fused": 1}, {"optimize": 1}, {"cache": {}}):
        with pytest.raises((ValueError, TypeError)):
            plan.run([], **kwargs)


def test_null_optional_expansion_and_bounded_root_stream():
    graph = GraphSnapshot([[0, 0, 1]], node_ids=("a", "b", "c"), relations=("r",))
    model = ExplicitPathModel(np.zeros((1, 16)), relations=graph.relations)
    plan = (QueryPlan(graph, limits=Limits(window_size=2))
            .expand(source="source", target="next", optional=True, edge_relation="type")
            .predict("score", model, head="source", relation="type", target="next"))
    seen = []

    def inputs():
        for s in (None, "c", "a", "b", "c"):
            seen.append(s)
            yield {"source": s}

    iterator = plan.iter_batches(inputs())
    batch = next(iterator)
    assert seen == [None, "c"]
    assert [row["score"].status for row in batch.rows] == ["null_input", "null_input"]
    with pytest.raises(TypeError):
        batch.rows[0]["next"] = "a"
    iterator.close()
    assert seen == [None, "c"]
