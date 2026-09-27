"""The strong hand-ordered benchmark must preserve the public plan's contract."""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest
from test_execution import fixture
from test_pipeline import eager_reference
from test_plan import assert_records
from test_preparation import branch_graph

from orbweaver_query import (
    BindingCache,
    ExplicitPathModel,
    GraphSnapshot,
    Limits,
    NeighborhoodModel,
    QueryPlan,
)

DIRECTORY = Path(__file__).resolve().parents[1] / "benchmarks/v1"
sys.path.insert(0, str(DIRECTORY))
spec = importlib.util.spec_from_file_location("pipeline_benchmark", DIRECTORY / "graph_pipeline.py")
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


@pytest.mark.parametrize("shape", benchmark.SHAPES)
@pytest.mark.parametrize("seed", range(3))
@pytest.mark.parametrize("threshold", benchmark.THRESHOLDS)
def test_independent_manual_control_matches_eager_oracle(shape, seed, threshold):
    from plan_reference import CachedModel, SharedFeatureLRU

    _, graph, path = fixture(seed, n=12, r=2)
    structural = NeighborhoodModel(relations=graph.relations)
    rows = [{"head": "n0", "relation": "r0", "seed": s, "ordinal": i}
            for i, s in enumerate((*graph.node_ids, "n5", None))]
    plan = benchmark.make_plan(graph, path, structural, shape, threshold)
    expected = eager_reference(plan, rows)
    adjacency = benchmark.adjacency(graph)
    for mode in ("targeted", "full", "prepared", "coalesced"):
        cache = SharedFeatureLRU(16384)
        p, s = ((CachedModel(path, cache), CachedModel(structural, cache))
                if mode == "full" else (benchmark.PreparedModel(path), structural)
                if mode == "prepared" else (benchmark.CoalescedModel(path), structural)
                if mode == "coalesced" else (path, structural))
        actual, work = benchmark.manual(graph, p, s, shape, rows, adjacency, plan.projection,
                                         BindingCache(max_entries=16384), threshold)
        assert_records(actual, expected)
        optimized = plan.run(rows, cache=BindingCache())
        assert_records(actual, optimized.to_records())
        assert work["edge_visits"] == optimized.report()["edge_visits"]


def test_fresh_preparation_ablation_isolates_reuse_with_the_same_completion_kernel(monkeypatch):
    from orbweaver_query import pipeline

    graph, model = branch_graph()
    plan = (QueryPlan(graph, limits=Limits(window_size=4))
            .expand(source="seed", target="candidate", direction="both")
            .predict("score", model, target="candidate"))
    rows = [{"head": "n0", "relation": "r", "seed": "n1"}]
    prepared = plan.run(rows, coalesce_targets=False)
    monkeypatch.setattr(pipeline, "PreparationScope", benchmark.fresh_preparation_scope())
    fresh = plan.run(rows, coalesce_targets=False)
    assert_records(fresh.to_records(), prepared.to_records())
    cached_work, fresh_work = prepared.report(), fresh.report()
    assert cached_work["preparation_builds"] == 1
    assert cached_work["preparation_hits"] > 0
    assert fresh_work["preparation_hits"] == 0
    assert fresh_work["preparation_builds"] == (cached_work["preparation_builds"] +
                                                 cached_work["preparation_hits"])
    prefix_cost = model.prepare_source(graph, 0, Limits()).type_visits
    assert fresh_work["type_visits"] - cached_work["type_visits"] == (
        fresh_work["preparation_builds"] - 1) * prefix_cost
    assert fresh_work["model_calls"] == cached_work["model_calls"]


def test_manual_target_union_spans_batches_and_matches_independent_graph_oracle():
    graph = GraphSnapshot([[0, 0, 1], [1, 0, 2], *[[2, 0, n] for n in range(3, 604)]],
                          node_ids=[f"n{i}" for i in range(604)], relations=("LINK",))
    path = ExplicitPathModel(np.arange(16).reshape(1, 16), relations=graph.relations)
    structural = NeighborhoodModel(relations=graph.relations)
    rows = [{"head": "n0", "relation": "LINK", "seed": "n2", "ordinal": 0}]
    plan = benchmark.make_plan(graph, path, structural, "one_expansion")
    model = benchmark.CoalescedModel(path)
    actual, _ = benchmark.manual(graph, model, structural, "one_expansion", rows,
                                 benchmark.adjacency(graph), plan.projection, BindingCache())
    assert model.scope.target_builds == 1 and model.scope.target_hits > 0
    assert_records(actual, eager_reference(plan, rows))
    assert_records(actual, plan.run(rows).to_records())


def test_rowwise_ablation_keeps_model_work_and_complete_ordered_bag(monkeypatch):
    _, graph, path = fixture(19, n=9, r=2)
    structural = NeighborhoodModel(relations=graph.relations)
    plan = benchmark.make_plan(graph, path, structural, "two_expansions", 0)
    rows = [{"head": "n0", "relation": "r0", "seed": seed, "ordinal": i}
            for i, seed in enumerate(("n4", "n4", "n5", None))]
    deduplicated = plan.run(rows, cache=BindingCache())
    monkeypatch.setattr(QueryPlan, "_representatives", staticmethod(benchmark.rowwise_bindings))
    rowwise = plan.run(rows, cache=BindingCache())
    assert_records(rowwise.to_records(), eager_reference(plan, rows))
    assert_records(rowwise.to_records(), deduplicated.to_records())
    assert rowwise.report()["duplicate_bindings"] == 0
    assert deduplicated.report()["duplicate_bindings"] > 0
    for key in ("model_calls", "type_visits", "expansions", "edge_visits"):
        assert rowwise.report()[key] == deduplicated.report()[key]
