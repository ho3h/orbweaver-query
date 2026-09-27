"""Physical plan transformations must preserve independently scored row semantics."""

from dataclasses import replace

import numpy as np
import pytest
from test_execution import fixture

from orbweaver_query import (
    BindingCache,
    CostEstimate,
    ExplicitPathModel,
    GraphSnapshot,
    Limits,
    NeighborhoodModel,
    PlanStatistics,
    QueryPlan,
    ResourceLimitError,
    Session,
    score_bindings,
)


def candidates(graph):
    rows = [
        {
            "head": h,
            "relation": graph.relations[i % len(graph.relations)],
            "target": t,
            "ordinal": i,
            "keep": "payload",
        }
        for i, (h, t) in enumerate((h, t) for h in graph.node_ids for t in graph.node_ids)
    ]
    return [
        *rows,
        rows[5],
        {"head": None, "relation": "not-a-relation", "target": 42, "ordinal": -1},
    ]


def assert_records(actual, expected):
    assert len(actual) == len(expected)
    for a, b in zip(actual, expected):
        assert list(a) == list(b)
        for key in a:
            if isinstance(a[key], dict) and "score" in a[key]:
                assert {k: v for k, v in a[key].items() if k != "score"} == {
                    k: v for k, v in b[key].items() if k != "score"
                }
                if b[key]["score"] is None:
                    assert a[key]["score"] is None
                else:
                    assert a[key]["score"] == pytest.approx(b[key]["score"], abs=1e-12)
            else:
                assert a[key] == b[key]


@pytest.mark.parametrize("window_size", [3, 64])
@pytest.mark.parametrize("fused", [False, True])
def test_duplicate_bindings_preserve_payloads_and_distinct_later_group_outputs(window_size, fused):
    _, graph, path = fixture(seed=19, n=9, r=2)
    structural = NeighborhoodModel(relations=graph.relations)
    opposite = ExplicitPathModel(-path.coefficient, relations=graph.relations)
    rows = []
    for repeat in range(2):
        for target in ("n2", "n5", None, "n8", "n2"):
            for relation in ("r0", "r1", None):
                rows.append({"head": "n0", "relation": "r0", "target": "n4",
                             "other": target, "other_relation": relation,
                             "ordinal": len(rows), "payload": [repeat, target]})
    # Nulls short circuit even otherwise malformed values. These rows must not
    # alias a nonnull fused binding with the same endpoints.
    rows.extend([{**rows[0], "head": None, "relation": [], "ordinal": len(rows) + i}
                 for i in range(2)])
    limits = Limits(window_size=window_size)
    plan = (QueryPlan(graph, limits=limits).predict("first", path)
            .predict("opposite", opposite, relation="other_relation")
            .predict("later", structural, relation="other_relation", target="other"))
    expected = rows
    for name, model, relation, target in (
        ("first", path, "relation", "target"),
        ("opposite", opposite, "other_relation", "target"),
        ("later", structural, "other_relation", "other"),
    ):
        expected = score_bindings(Session(graph, model, limits=limits), expected,
                                 relation=relation, target=target).to_records(prediction_column=name)
    for cache in (None, BindingCache(max_entries=2)):
        actual = plan.run(rows, fused=fused, cache=cache)
        assert_records(actual.to_records(), expected)
        assert actual.report()["duplicate_bindings"] > 0
        filtered = plan.where_score("later", 0).project("ordinal", "first", "opposite", "later")
        wanted = [{c: row[c] for c in filtered.projection} for row in expected
                  if row["later"]["score"] is not None and row["later"]["score"] >= 0]
        assert_records(filtered.run(rows, fused=fused, cache=cache).to_records(), wanted)


def test_repeated_bindings_evaluate_pair_guard_once_and_preserve_every_row():
    _, graph, path = fixture()

    class Guarded(UnsharedModel):
        def __init__(self):
            super().__init__(path, path.model_id)
            self.guards = []

        def rejects_pair(self, graph, head, target):
            self.guards.append((head, target))
            return path.rejects_pair(graph, head, target)

    model = Guarded()
    rows = [{"head": "n0", "relation": "r0", "target": "n0", "ordinal": i}
            for i in range(100)]
    actual = QueryPlan(graph).predict("p", model).run(rows)
    assert model.guards == [(0, 0)]
    assert actual.report()["binding_evaluations"] == 1
    assert actual.report()["duplicate_bindings"] == 99
    assert [row["ordinal"] for row in actual.rows] == list(range(100))
    assert all(row["p"].status == "unsupported" for row in actual.rows)


@pytest.mark.parametrize("seed", range(4))
def test_fusion_and_order_match_independent_models_with_bags_nulls_and_projection(seed):
    _, graph, path = fixture(seed, n=12, r=2)
    models = {
        "path": path,
        **{
            metric: NeighborhoodModel(relations=graph.relations, metric=metric)
            for metric in NeighborhoodModel.metrics
        },
    }
    rows = candidates(graph)
    plan = QueryPlan(graph)
    expected = rows
    for name, model in models.items():
        plan = plan.predict(name, model)
        expected = score_bindings(Session(graph, model), expected).to_records(
            prediction_column=name
        )
    fused, separate = plan.run(rows), plan.run(rows, fused=False)
    assert_records(fused.to_records(), expected)
    assert_records(separate.to_records(), expected)
    assert fused.report()["expansions"] == 2 * len(graph.node_ids)
    assert separate.report()["expansions"] == 4 * len(graph.node_ids)
    # Metadata belongs to the scoring model, even when preparation is shared.
    assert len({fused.rows[0][name].model_id for name in models}) == 4
    filtered = plan.where_score("resource_allocation", 0.3).where_score("path", -1e6)
    selected = [
        row
        for row in expected
        if row["resource_allocation"]["score"] is not None
        and row["resource_allocation"]["score"] >= 0.3
        and row["path"]["score"] is not None
        and row["path"]["score"] >= -1e6
    ]
    statistics = PlanStatistics(
        filtered.plan_id,
        True,
        (
            CostEstimate(("path",), 10.0, 0.9, len(rows)),
            CostEstimate(tuple(NeighborhoodModel.metrics), 1.0, 0.1, len(rows)),
        ),
    )
    assert filtered.explain(statistics=statistics)["physical_groups"][0] == list(
        NeighborhoodModel.metrics
    )
    assert_records(filtered.run(rows, statistics=statistics).to_records(), selected)
    assert_records(filtered.run(rows, fused=False).to_records(), selected)
    projected = filtered.project("ordinal", "path")
    assert_records(
        projected.run(rows).to_records(), [{k: r[k] for k in ("ordinal", "path")} for r in selected]
    )
    assert plan.project().run(rows).to_records() == [{}] * len(rows)


def test_shared_path_features_keep_distinct_coefficients_and_relation_columns():
    _, graph, first = fixture(n=10, r=2)
    second = ExplicitPathModel(-first.coefficient, relations=graph.relations)
    rows = [{**r, "other_relation": "r1"} for r in candidates(graph)]
    plan = QueryPlan(graph).predict("a", first).predict("b", second, relation="other_relation")
    result = plan.run(rows)
    assert result.report()["expansions"] == 10
    expected = score_bindings(Session(graph, first), rows).to_records(prediction_column="a")
    expected = score_bindings(
        Session(graph, second), expected, relation="other_relation"
    ).to_records(prediction_column="b")
    assert_records(result.to_records(), expected)


def test_calibration_and_statistics_are_bound_to_entire_plan():
    _, graph, path = fixture(n=10)
    neighborhood = NeighborhoodModel(relations=graph.relations)
    plan = (
        QueryPlan(graph, limits=Limits(window_size=17))
        .predict("a", path)
        .predict("b", neighborhood)
    )
    rows = candidates(graph)
    stats = plan.calibrate(iter(rows))
    assert len(stats.estimates) == 2
    assert all(
        e.sample_rows == 17 and e.seconds_per_row > 0 and e.pass_fraction == 1
        for e in stats.estimates
    )
    assert_records(plan.run(rows, statistics=stats).to_records(), plan.run(rows).to_records())
    changed = [
        plan.where_score("a", 0),
        plan.project("a"),
        replace(plan, limits=Limits(window_size=18)),
        replace(
            plan,
            graph=GraphSnapshot(
                np.empty((0, 3), dtype=np.int64), node_ids=graph.node_ids, relations=graph.relations
            ),
        ),
    ]
    for other in changed:
        with pytest.raises(ValueError, match="Statistics do not match"):
            other.run(rows, statistics=stats)
    with pytest.raises(ValueError, match="Statistics do not match"):
        plan.run(rows, statistics=stats, fused=False)
    with pytest.raises(ValueError, match="cover"):
        plan.run(rows, statistics=replace(stats, estimates=stats.estimates[:1]))
    with pytest.raises(ValueError, match="nonempty"):
        plan.calibrate([])
    with pytest.raises(ValueError, match="boolean"):
        plan.run([], fused=1)


class UnsharedModel:
    """A conforming backend without an optional cross-model feature contract."""

    def __init__(self, delegate, identity):
        self.delegate, self.model_id, self.relations = delegate, identity, delegate.relations
        self.calls = 0

    def expand(self, graph, head, limits):
        self.calls += 1
        return self.delegate.expand(graph, head, limits)

    def score(self, features, relation):
        return self.delegate.score(features, relation)


def test_unshared_backends_remain_separate_and_validation_precedes_execution():
    _, graph, path = fixture()
    first, second = UnsharedModel(path, "one"), UnsharedModel(path, "two")
    plan = (
        QueryPlan(graph)
        .predict("a", first)
        .where_score("a", 1e10)
        .predict("b", second, target="other")
    )
    assert plan.explain()["physical_groups"] == [["a"], ["b"]]
    good = {"head": "n0", "relation": "r0", "target": "n1", "other": "n2"}
    for bad in ({**good, "other": "unknown"}, {**good, "b": None}, {**good, "other": 42}, {}, 42):
        with pytest.raises(ValueError):
            plan.run([good, bad])
        assert first.calls == second.calls == 0
    unrestricted = QueryPlan(graph).predict("a", first).predict("b", second)
    assert unrestricted.run([good]).report()["expansions"] == 2
    assert first.calls == second.calls == 1


def test_streaming_is_bounded_and_output_is_immutable():
    _, graph, path = fixture()
    plan = QueryPlan(graph, limits=Limits(window_size=2)).predict("a", path)
    seen = []

    def stream():
        for index in range(5):
            seen.append(index)
            yield {"head": "n0", "relation": "r0", "target": "n3", "ordinal": index}

    batches = plan.iter_batches(stream())
    first = next(batches)
    assert seen == [0, 1]
    assert [r["ordinal"] for r in first.rows] == [0, 1]
    with pytest.raises(TypeError):
        first.rows[0]["ordinal"] = 5
    assert [len(batch.rows) for batch in batches] == [2, 1]
    assert plan.run([]).to_records() == []
    assert QueryPlan(graph).run([{"value": 3}, {"value": 3}]).to_records() == [
        {"value": 3},
        {"value": 3},
    ]


def test_known_rejections_do_not_expand_evidence():
    graph = GraphSnapshot([[0, 0, 1], [1, 0, 2]], node_ids=("a", "b", "c"), relations=("r",))
    path = ExplicitPathModel(np.zeros((1, 16)), relations=graph.relations)
    plan = (
        QueryPlan(graph, limits=Limits(max_type_visits=1, max_neighbor_visits=1))
        .predict("path", path)
        .predict("structural", NeighborhoodModel(relations=graph.relations))
    )
    rows = [
        {"head": h, "relation": "r", "target": t}
        for h, t in (("a", "a"), ("a", "b"), ("b", "c"), (None, None))
    ]
    result = plan.run(rows)
    assert result.report()["expansions"] == result.report()["model_calls"] == 0
    for name in ("path", "structural"):
        assert [row[name].status for row in result.rows] == ["unsupported"] * 3 + ["null_input"]
    with pytest.raises(ValueError):
        plan.run([{"head": "a", "relation": "r", "target": "unknown"}])


def test_persistent_pair_cache_reuses_bindings_and_invalidates_by_artifact_identity():
    _, graph, path = fixture(10, n=12, r=2)
    structural = NeighborhoodModel(relations=graph.relations)
    rows = candidates(graph)
    cache = BindingCache(max_entries=1024)
    # The existing binding API and a composed plan use the same pure score keys.
    score_bindings(Session(graph, path), rows, cache=cache)
    plan = QueryPlan(graph).predict("path", path).predict("structural", structural)
    first = plan.run(rows, cache=cache)
    assert first.report()["expansions"] == len(graph.node_ids)
    again = plan.run(rows, cache=cache)
    assert again.report()["expansions"] == again.report()["model_calls"] == 0
    assert again.report()["cache_hits"] > 0 and again.report()["cache_misses"] == 0
    assert_records(first.to_records(), again.to_records())
    assert_records(again.to_records(), plan.run(rows).to_records())
    filtered = plan.where_score("structural", 0.2).project("ordinal", "path")
    assert_records(filtered.run(rows, cache=cache).to_records(), filtered.run(rows).to_records())
    different = ExplicitPathModel(-path.coefficient, relations=graph.relations)
    changed = QueryPlan(graph).predict("path", different).predict("structural", structural)
    assert changed.run(rows, cache=cache).report()["model_calls"] > 0
    assert_records(changed.run(rows, cache=cache).to_records(), changed.run(rows).to_records())
    _, next_graph, _ = fixture(11, n=12, r=2)
    changed = replace(plan, graph=next_graph)
    result = changed.run(rows, cache=cache)
    assert result.report()["expansions"] > 0
    assert_records(result.to_records(), changed.run(rows).to_records())
    tiny = BindingCache(max_entries=3)
    for _ in range(2):
        assert_records(plan.run(rows, cache=tiny).to_records(), again.to_records())
        assert tiny.info().entries <= 3 and tiny.info().evictions > 0
    with pytest.raises(TypeError, match="BindingCache"):
        plan.run(rows, cache={})


def test_failed_later_operator_does_not_commit_earlier_cached_predictions():
    _, graph, path = fixture(10, n=12, r=2)

    class FailingModel(UnsharedModel):
        def score(self, features, relation):
            raise ValueError("deliberate scoring failure")

    plan = (
        QueryPlan(graph)
        .predict("good", NeighborhoodModel(relations=graph.relations))
        .predict("failed", FailingModel(path, "failing"))
    )
    cache = BindingCache()
    with pytest.raises(ValueError, match="deliberate scoring failure"):
        plan.run(candidates(graph), cache=cache)
    assert cache.info().entries == 0
    # Input validation also precedes cache reads and model work for the whole window.
    before = cache.info()
    with pytest.raises(ValueError):
        plan.run(
            [
                {"head": "n0", "relation": "r0", "target": "n2"},
                {"head": "n0", "relation": "r0", "target": "unknown"},
            ],
            cache=cache,
        )
    assert cache.info() == before


def test_invalid_plans_and_resource_failures():
    _, graph, path = fixture(n=20)
    plan = QueryPlan(graph).predict("a", path)
    for make in (
        lambda: plan.predict("a", path),
        lambda: plan.where_score("missing", 0),
        lambda: plan.where_score("a", np.nan),
        lambda: plan.project("a", "a"),
        lambda: plan.project("a").predict("b", path),
        lambda: plan.project("a").where_score("a", 0),
        lambda: plan.predict("b", path, head="target"),
    ):
        with pytest.raises(ValueError):
            make()
    assert dict(plan.where_score("a", 2).where_score("a", 1).thresholds) == {"a": 2}
    with pytest.raises(ValueError, match="missing input"):
        plan.project("missing").run([{"head": "n0", "relation": "r0", "target": "n3"}])
    with pytest.raises(ResourceLimitError):
        replace(plan, limits=Limits(max_type_visits=1)).run(candidates(graph))
    for seconds, fraction, size in (
        (-1, 0.5, 3),
        (np.inf, 0.5, 3),
        (1, np.nan, 3),
        (1, 2, 3),
        (1, 0.5, 0),
        (1, 0.5, True),
    ):
        with pytest.raises(ValueError):
            CostEstimate(("a",), seconds, fraction, size)


def test_default_order_pushes_filters_before_unfiltered_groups_without_calibration():
    _, graph, path = fixture(n=10)
    later = UnsharedModel(path, 'must-not-expand')
    plan = (QueryPlan(graph).predict('later', later)
            .predict('selective', NeighborhoodModel(relations=graph.relations))
            .where_score('selective', 1e9))
    assert plan.explain()['physical_groups'] == [['selective'], ['later']]
    assert plan.run(candidates(graph)).rows == ()
    assert later.calls == 0


def test_fused_filter_avoids_later_scores_and_hot_cache_avoids_all_preparation():
    graph = GraphSnapshot([[0, 0, 1], [1, 0, 2]], node_ids=('a', 'b', 'c', 'd'), relations=('r',))
    aa = NeighborhoodModel(relations=graph.relations, metric='adamic_adar')
    ra = NeighborhoodModel(relations=graph.relations, metric='resource_allocation')

    class Tracked(UnsharedModel):
        def __init__(self, model):
            super().__init__(model, model.model_id)
            self.feature_id = model.feature_id
            self.candidate_support, self.score_kind = model.candidate_support, model.score_kind
            self.score_calls = 0

        def expand_targets(self, graph, head, targets, limits):
            self.calls += 1
            return self.delegate.expand_targets(graph, head, targets, limits)

        def score(self, features, relation):
            self.score_calls += 1
            return self.delegate.score(features, relation)

    later, selective = Tracked(aa), Tracked(ra)
    plan = QueryPlan(graph).predict('aa', later).predict('ra', selective).where_score('ra', 1.0)
    assert plan.explain()['within_group_order'] == [['ra', 'aa']]
    rows = [{'head': h, 'relation': 'r', 'target': t}
            for h, t in (('a', 'c'), ('a', 'c'), ('a', 'b'), (None, 'c'))]
    cold = plan.run(rows)
    assert cold.rows == ()
    assert cold.report()['expansions'] == cold.report()['model_calls'] == 1
    assert later.score_calls == 0 and selective.score_calls == 1
    cache = BindingCache()
    score_bindings(Session(graph, ra), rows, cache=cache)
    before = later.calls, selective.calls, later.score_calls, selective.score_calls
    warm = plan.run(rows, cache=cache)
    assert warm.rows == ()
    assert warm.report()['expansions'] == warm.report()['model_calls'] == 0
    assert warm.report()['cache_hits'] == 2 and warm.report()['cache_misses'] == 0
    assert (later.calls, selective.calls, later.score_calls, selective.score_calls) == before


def test_fused_filter_preserves_different_null_relation_columns_under_partial_cache():
    _, graph, first = fixture(5, n=12, r=2)
    second = ExplicitPathModel(-first.coefficient, relations=graph.relations)
    rows = [{**row, 'other_relation': None if i % 3 == 0 else 'r1'}
            for i, row in enumerate(candidates(graph))]
    plan = (QueryPlan(graph).predict('second', second, relation='other_relation')
            .predict('first', first).where_score('first', -1e9))
    expected = score_bindings(Session(graph, first), rows).where_score(-1e9).to_records(
        prediction_column='first')
    expected = score_bindings(Session(graph, second), expected, relation='other_relation').to_records(
        prediction_column='second')
    columns = ('ordinal', 'first', 'second')
    expected = [{c: row[c] for c in columns} for row in expected]
    plan = plan.project(*columns)
    cache = BindingCache(max_entries=1024)
    score_bindings(Session(graph, first), rows[:50], cache=cache)
    for fused in (True, False):
        for _ in range(2):
            assert_records(plan.run(rows, fused=fused, cache=cache).to_records(), expected)
