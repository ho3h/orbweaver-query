"""A benchmark cache must preserve identity and account for every retained array."""

import importlib.util
import sys
from pathlib import Path

import numpy as np
from test_execution import fixture
from test_plan import assert_records, candidates

from orbweaver_query import ExplicitPathModel, NeighborhoodModel, QueryPlan


def reference():
    name = 'plan_reference_test'
    if name not in sys.modules:
        path = Path(__file__).resolve().parents[1]/'benchmarks/v1/plan_reference.py'
        spec = importlib.util.spec_from_file_location(name,path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def test_full_feature_lru_shares_features_and_keeps_model_scores_separate():
    _, graph, path = fixture(4,n=15,r=2)
    models = [path, ExplicitPathModel(-path.coefficient,relations=graph.relations),
              NeighborhoodModel(relations=graph.relations,metric='adamic_adar'),
              NeighborhoodModel(relations=graph.relations)]
    rows = candidates(graph)
    expected = QueryPlan(graph)
    for i, model in enumerate(models):
        expected = expected.predict(str(i),model)
    for budget in (1,1024,1024*1024):
        cache = reference().SharedFeatureLRU(budget)
        plan = QueryPlan(graph)
        for i, model in enumerate(models):
            plan = plan.predict(str(i),reference().CachedModel(model,cache))
        assert_records(plan.run(rows).to_records(),expected.run(rows).to_records())
        before = cache.info()
        assert_records(plan.run(rows).to_records(),expected.run(rows).to_records())
        assert 0 <= cache.bytes <= cache.peak_bytes <= budget
        assert cache.bytes == sum(e.numeric_bytes for e in cache.entries.values())
        if budget == 1024*1024:
            assert cache.info()['expansions'] == before['expansions'] == 2*len(graph.node_ids)
            assert cache.info()['score_calls'] == before['score_calls']
        else:
            assert cache.info()['expansions'] > before['expansions']
    # A different snapshot cannot see any old full-source features.
    _, changed, _ = fixture(5,n=15,r=2)
    before = cache.expansions
    actual = QueryPlan(changed).predict('a',reference().CachedModel(path,cache))
    direct = QueryPlan(changed).predict('a',path)
    assert_records(actual.run(rows).to_records(),direct.run(rows).to_records())
    assert cache.expansions == before+len(changed.node_ids)
    assert all(np.isfinite(s).all() for entry in cache.entries.values() for s in entry.scores.values())
