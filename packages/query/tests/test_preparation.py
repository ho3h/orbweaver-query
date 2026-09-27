"""Reusable walk prefixes must agree with independent individual-walk enumeration."""

from dataclasses import replace

import numpy as np
import pytest
from test_execution import enumerate_reference, fixture
from test_plan import assert_records

from orbweaver_query import (
    BindingCache,
    ExplicitPathModel,
    GraphSnapshot,
    Limits,
    QueryPlan,
    ResourceLimitError,
)
from orbweaver_query.preparation import PreparationScope


@pytest.mark.parametrize("seed", range(8))
def test_prepared_completions_match_full_features_and_independent_walks(seed):
    edges, graph, model = fixture(seed)
    for head in range(9):
        prepared = model.prepare_source(graph, head, Limits())
        for targets in ((), (head,), (0,), (1, 4, 7), tuple(range(9))):
            features = prepared.expand_targets(targets, Limits())
            reference = model.expand_targets(graph, head, targets, Limits())
            for name in ("candidates", "base", "row", "column", "proportions"):
                np.testing.assert_array_equal(getattr(features, name), getattr(reference, name))
            for relation in range(3):
                scores = model.score(features, relation)
                expected = enumerate_reference(edges, 9, 3, head, relation, model.coefficient)
                np.testing.assert_allclose(scores, [expected[f"n{n}"] for n in features.candidates],
                                           rtol=1e-12, atol=1e-12)
        for array in (prepared.nodes, prepared.codes, prepared.values):
            with pytest.raises(ValueError):
                array.setflags(write=True)


def branch_graph():
    graph = GraphSnapshot([[0, 0, 1], *[[1, 0, n] for n in range(2, 26)],
                           *[[n, 0, n + 24] for n in range(2, 26)]],
                          node_ids=[f"n{i}" for i in range(50)], relations=("r",))
    model = ExplicitPathModel(np.ones((1, 16)), relations=graph.relations)
    return graph, model


def test_new_target_completions_reuse_intermediate_work_without_answer_caching():
    graph, model = branch_graph()
    prepared = model.prepare_source(graph, 0, Limits())
    fresh, repeated = 0, prepared.type_visits
    for target in range(26, 50):
        independent = model.expand_targets(graph, 0, (target,), Limits())
        completed = prepared.expand_targets((target,), Limits())
        np.testing.assert_array_equal(completed.base, independent.base)
        np.testing.assert_array_equal(model.score(completed, 0), model.score(independent, 0))
        fresh += independent.type_visits
        repeated += completed.type_visits
    assert repeated < fresh / 2


def test_pipeline_reuses_prefix_across_batches_with_no_answer_cache_and_bounded_lifetime():
    graph, model = branch_graph()
    plan = (QueryPlan(graph, limits=Limits(window_size=4))
            .expand(source="seed", target="candidate", direction="both")
            .predict("score", model, target="candidate"))
    rows = [{"head": "n0", "relation": "r", "seed": "n1"}]
    reusable = plan.run(rows)
    independent = plan.run(rows, reuse_preparation=False)
    assert_records(reusable.to_records(), independent.to_records())
    assert reusable.report()["preparation_builds"] == 1
    assert reusable.report()["preparation_hits"] > 0
    assert reusable.report()["type_visits"] < independent.report()["type_visits"]
    assert reusable.report()["peak_preparation_bytes"] <= plan.limits.max_prepared_bytes
    # Another invocation starts with no retained intermediate model state.
    assert plan.run(rows).report()["preparation_builds"] == 1
    disabled = replace(plan, stages=tuple(replace(s, limits=replace(s.limits, max_prepared_bytes=0))
                                         for s in plan.stages))
    assert disabled.run(rows).report()["preparation_builds"] == 0
    assert_records(disabled.run(rows).to_records(), independent.to_records())
    with pytest.raises(ValueError, match="reuse_preparation"):
        plan.run([], reuse_preparation=1)


def test_preparation_scope_eviction_and_graph_and_feature_identity():
    graph, model = branch_graph()
    size = model.prepare_source(graph, 0, Limits()).numeric_bytes
    scope = PreparationScope(size)
    scope.eligible.update(scope.key(model, graph, h) for h in (0, 49))
    first, cost = scope.expand(model, graph, 0, (26,), Limits())
    assert cost > 0 and scope.bytes == size and scope.builds == 1
    again, cost = scope.expand(model, graph, 0, (27,), Limits())
    assert cost == 0 and scope.hits == 1
    assert first.candidates.tolist() == [26] and again.candidates.tolist() == [27]
    scope.expand(model, graph, 49, (0,), Limits())
    assert scope.bytes <= size and scope.evictions == 1
    changed = GraphSnapshot([[0, 0, 1]], node_ids=graph.node_ids, relations=graph.relations)
    assert scope.key(model, graph, 0) != scope.key(model, changed, 0)
    compatible = ExplicitPathModel(-model.coefficient, relations=model.relations)
    assert scope.key(model, graph, 0) == scope.key(compatible, graph, 0)
    tiny = PreparationScope(1)
    tiny.eligible.add(tiny.key(model, graph, 0))
    tiny.expand(model, graph, 0, (26,), Limits())
    tiny.expand(model, graph, 0, (27,), Limits())
    assert tiny.builds == 1 and tiny.bytes == tiny.hits == 0


def test_preparation_and_completion_validate_limits_and_targets():
    graph, model = branch_graph()
    for budget in (Limits(max_type_visits=1), Limits(max_expansion_states=1)):
        with pytest.raises(ResourceLimitError):
            model.prepare_source(graph, 0, budget)
    prepared = model.prepare_source(graph, 0, Limits())
    for target in (-1, True, 50, 1.5):
        with pytest.raises(ValueError, match="Target index"):
            prepared.expand_targets((target,), Limits())
    with pytest.raises(ResourceLimitError, match="max_type_visits"):
        prepared.expand_targets((26,), Limits(max_type_visits=prepared.type_visits))
    with pytest.raises(ResourceLimitError, match="max_expansion_states"):
        prepared.expand_targets((26,), Limits(max_expansion_states=1))


def test_compatible_models_share_prefix_but_keep_distinct_scores_and_provenance():
    graph, model = branch_graph()
    other = ExplicitPathModel(-model.coefficient, relations=graph.relations)
    plan = (QueryPlan(graph, limits=Limits(window_size=4))
            .expand(source="seed", target="candidate", direction="both")
            .predict("first", model, target="candidate")
            .predict("second", other, target="candidate"))
    rows = [{"head": "n0", "relation": "r", "seed": "n1"}]
    prepared = plan.run(rows, fused=False)
    assert prepared.report()["preparation_builds"] == 1
    assert prepared.report()["preparation_hits"] > 1
    assert_records(prepared.to_records(), plan.run(rows, reuse_preparation=False).to_records())
    assert {r['first'].model_id for r in prepared.rows} == {model.model_id}
    assert {r['second'].model_id for r in prepared.rows} == {other.model_id}


def test_pending_pair_answers_are_excluded_from_later_feature_requests():
    graph, model = branch_graph()

    class Tracked:
        relations, model_id = model.relations, model.model_id
        feature_id, candidate_support = model.feature_id, model.candidate_support
        score_kind, score = model.score_kind, model.score
        rejects_pair = model.rejects_pair

        def __init__(self):
            self.targets = []

        def expand_targets(self, graph, head, targets, limits):
            self.targets.append(targets)
            return model.expand_targets(graph, head, targets, limits)

    tracked = Tracked()
    cache = BindingCache()
    plan = QueryPlan(graph).predict("score", tracked)
    row = {"head": "n0", "relation": "r", "target": "n26"}
    plan.run([row], cache=cache)
    plan.run([row, {**row, "target": "n27"}], cache=cache)
    assert tracked.targets == [(26,), (27,)]


@pytest.mark.parametrize("seed", range(8))
def test_prepared_target_subsets_match_individual_expansion_and_walk_oracle(seed):
    edges, graph, model = fixture(seed)
    for head in range(9):
        prepared = model.prepare_targets(graph, head, (0, 1, 4, 7, head), Limits())
        for targets in ((), (head,), (0,), (1, 4, 1), (0, 1, 4, 7)):
            features = prepared.expand_targets(targets, Limits())
            independent = model.expand_targets(graph, head, targets, Limits())
            for name in ("candidates", "base", "row", "column", "proportions"):
                np.testing.assert_array_equal(getattr(features, name), getattr(independent, name))
            assert features.type_visits == 0
            for relation in range(3):
                expected = enumerate_reference(edges, 9, 3, head, relation, model.coefficient)
                np.testing.assert_allclose(model.score(features, relation),
                    [expected[f"n{n}"] for n in features.candidates], rtol=1e-12, atol=1e-12)
        for array in (prepared.targets, prepared.features.base, prepared.features.proportions):
            with pytest.raises(ValueError):
                array.setflags(write=True)


def fan_graph():
    graph = GraphSnapshot([[0, 0, 1], [1, 0, 2], *[[2, 0, n] for n in range(3, 52)]],
                          node_ids=[f"n{i}" for i in range(52)], relations=("r",))
    return graph, ExplicitPathModel(np.arange(16).reshape(1, 16), relations=graph.relations)


def test_stage_target_union_avoids_repeated_completion_without_final_answer_cache():
    graph, model = fan_graph()
    plan = (QueryPlan(graph, limits=Limits(window_size=4))
            .expand(source="seed", target="candidate", direction="both")
            .predict("score", model, target="candidate"))
    rows = [{"head": "n0", "relation": "r", "seed": "n2"}]
    coalesced = plan.run(rows)
    prefix = plan.run(rows, coalesce_targets=False)
    individual = plan.run(rows, reuse_preparation=False)
    assert_records(coalesced.to_records(), prefix.to_records())
    assert_records(coalesced.to_records(), individual.to_records())
    work = coalesced.report()
    assert work["target_preparation_builds"] == 1
    assert work["target_preparation_hits"] > 1
    assert work["type_visits"] < prefix.report()["type_visits"] / 5
    assert work["model_calls"] == prefix.report()["model_calls"]
    assert work["peak_preparation_bytes"] <= plan.limits.max_prepared_bytes
    assert plan.run(rows).report()["target_preparation_builds"] == 1
    assert plan.explain()["target_coalescing"]
    assert not plan.explain(reuse_preparation=False)["target_coalescing"]
    with pytest.raises(ValueError, match="coalesce_targets"):
        plan.run([], coalesce_targets=1)
    with pytest.raises(ValueError, match="coalesce_targets"):
        plan.explain(coalesce_targets=1)


def test_new_stage_targets_rebuild_preparation_and_tiny_budget_falls_back():
    graph, model = fan_graph()
    plan = QueryPlan(graph).predict("score", model)
    groups = plan._groups(True)
    scope, tiny = PreparationScope(2**20), PreparationScope(1)
    for targets in ((3, 4, 5, 6), (7, 8, 9, 10)):
        rows = [{"head": "n0", "relation": "r", "target": f"n{t}"} for t in targets]
        scope.hint(graph, rows, groups, 2)
        features, cost = scope.expand(model, graph, 0, targets[:2], Limits())
        assert features.candidates.tolist() == list(targets[:2])
        assert cost > 0
        again, cost = scope.expand(model, graph, 0, targets[2:], Limits())
        assert again.candidates.tolist() == list(targets[2:])
        assert cost == 0
    assert scope.target_builds == 2 and scope.target_hits == 2 and scope.evictions == 1
    tiny.hint(graph, rows, groups, 2)
    tiny.expand(model, graph, 0, targets[:2], Limits())
    later, _ = tiny.expand(model, graph, 0, targets[2:], Limits())
    assert tiny.target_builds == 1 and tiny.bytes == tiny.hits == 0
    assert later.candidates.tolist() == list(targets[2:])


def test_target_union_omits_already_resolved_pairs_and_checks_prepared_domain():
    graph, model = fan_graph()
    plan = QueryPlan(graph).predict("score", model)
    rows = [{"head": "n0", "relation": "r", "target": f"n{t}"} for t in range(3, 11)]
    cache = BindingCache()
    plan.run(rows[:2], cache=cache)
    pending = {(graph.snapshot_id, model.model_id, 0, 0, 5): 1.}
    scope = PreparationScope(2**20)
    scope.hint(graph, rows, plan._groups(True), 2, cache=cache, pending=pending)
    assert scope.targets[scope.key(model, graph, 0)] == set(range(6, 11))
    prepared = model.prepare_targets(graph, 0, (3, 4), Limits())
    for targets in ((5,), (-1,), (True,), (1.5,)):
        with pytest.raises(ValueError, match="prepared domain"):
            prepared.expand_targets(targets, Limits())
    with pytest.raises(ResourceLimitError, match="max_type_visits"):
        prepared.expand_targets((3,), Limits(max_type_visits=1))
    with pytest.raises(ResourceLimitError, match="max_expansion_states"):
        prepared.expand_targets((3,), Limits(max_expansion_states=1))


def test_compatible_backend_without_target_builder_keeps_source_preparation():
    graph, model = fan_graph()

    class PrefixOnly:
        model_id, relations = model.model_id, model.relations
        feature_id, preparation_id = model.feature_id, model.preparation_id
        candidate_support, score_kind = model.candidate_support, model.score_kind
        score, rejects_pair = model.score, model.rejects_pair
        expand, expand_targets, prepare_source = model.expand, model.expand_targets, model.prepare_source

    plan = (QueryPlan(graph, limits=Limits(window_size=4))
            .expand(source="seed", target="candidate", direction="both")
            .predict("prefix", PrefixOnly(), target="candidate")
            .predict("union", model, target="candidate"))
    rows = [{"head": "n0", "relation": "r", "seed": "n2"}]
    expected = plan.run(rows, coalesce_targets=False, fused=False)
    assert_records(plan.run(rows, fused=False).to_records(), expected.to_records())
