"""Independently verify the native-comparison harness, including its live queries."""

import importlib.util
import os
import sys
from pathlib import Path

import numpy as np
import pytest

from orbweaver_query import BindingCache, GraphSnapshot
from orbweaver_query.neo4j import Neo4jSource


def harness():
    name = 'structural_neo4j_test'
    if name not in sys.modules:
        path = Path(__file__).resolve().parents[1]/'benchmarks/v1/structural_neo4j.py'
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def fixture():
    pairs = [(0, 2), (1, 2), (2, 3), (2, 4), (2, 5), (6, 7)]
    triples = [(a, 0, b) for x, y in pairs for a, b in ((x, y), (y, x))]
    graph = GraphSnapshot(np.array(triples), node_ids=[str(i) for i in range(10)], relations=('LINK',))
    rows = [{'head': str(h), 'relation': 'LINK', 'target': str(t), 'ordinal': i}
            for i, (h, t) in enumerate(((0, 1), (0, 1), (0, 0), (0, 2), (0, 8), (8, 9), (7, 0)))]
    rows += [{'head': None, 'relation': 'LINK', 'target': '1', 'ordinal': 10},
             {'head': '0', 'relation': None, 'target': '1', 'ordinal': 11},
             {'head': '0', 'relation': 'LINK', 'target': None, 'ordinal': 12}]
    return graph, rows


def test_structural_comparison_oracle_and_output_checks():
    module = harness()
    graph, rows = fixture()
    for filtered in (False, True):
        models, plan = module.model_plan(graph, filtered)
        expected = module.oracle(graph, rows, models, filtered)
        module.assert_equal(plan.run(rows).to_records(), expected)
        assert len(expected) == (2 if filtered else len(rows))
        if not filtered:
            statuses = [r['resource_allocation']['status'] for r in expected]
            assert statuses == ['scored', 'scored', 'unsupported', 'unsupported',
                                'scored', 'scored', 'scored', 'null_input', 'null_input', 'null_input']
            assert expected[4]['resource_allocation']['score'] == 0
        wrong = [dict(r) for r in expected]
        wrong[0]['ordinal'] = -999
        with pytest.raises(ValueError, match='order/bag/payload'):
            module.assert_equal(wrong, expected)


def test_structural_oracle_on_random_graphs():
    module = harness()
    for seed in range(5):
        rng = np.random.default_rng(seed)
        n = 20
        pairs = np.argwhere(np.triu(rng.random((n, n)) < .2, k=1))
        triples = [(int(a), 0, int(b)) for x, y in pairs for a, b in ((x, y), (y, x))]
        graph = GraphSnapshot(np.array(triples), node_ids=[str(i) for i in range(n)], relations=('LINK',))
        rows = [{'head': str(h), 'relation': 'LINK', 'target': str(t), 'ordinal': h*n+t}
                for h in range(n) for t in range(n)]
        for filtered in (False, True):
            models, plan = module.model_plan(graph, filtered)
            module.assert_equal(plan.run(rows).to_records(), module.oracle(graph, rows, models, filtered))


@pytest.mark.skipif(not os.getenv('ORBWEAVER_QUERY_GDS_TEST_URI'), reason='requires disposable GDS 2026.09.0')
def test_live_structural_comparison_all_arms():
    from neo4j import GraphDatabase

    module = harness()
    graph, rows = fixture()
    with GraphDatabase.driver(os.environ['ORBWEAVER_QUERY_GDS_TEST_URI'], auth=None) as driver:
        module.import_graph(driver, graph)
        source = Neo4jSource(driver, fetch_size=2)
        exported = module.export_graph(source)
        assert exported.snapshot_id == graph.snapshot_id
        for filtered in (False, True):
            models, plan = module.model_plan(exported, filtered)
            _, unfiltered = module.model_plan(exported, False)
            table = module.precompute(unfiltered, rows)
            cache = BindingCache(max_entries=100)
            expected = module.oracle(graph, rows, models, filtered)
            for arm in module.ARMS:
                for _ in range(2):
                    actual = module.request(arm, source, plan, models, rows, filtered, cache, table)
                    module.assert_equal(actual, expected)
